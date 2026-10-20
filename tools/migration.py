"""
Data migration tooling for SAP SuccessFactors.

Provides deep validation of migration files, dependency-based load ordering,
post-migration reconciliation, and purge file generation.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.metadata_parser import parse_metadata_xml

migration_mcp = FastMCP(name="SF Migration Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)
_KB_PATH = Path(__file__).parent.parent / "knowledge"


async def _sf_query(sf, api_host, token, entity, params):
    async with _SF_SEMAPHORE:
        return await sf.query_odata(data_center=api_host, bearer_token=token, entity=entity, params=params)


async def _fetch_all(sf, api_host, token, entity, params, max_records=5000, page_size=1000):
    all_records = []
    skip = 0
    while len(all_records) < max_records:
        p = {**params, "$top": str(page_size), "$skip": str(skip)}
        result = await _sf_query(sf, api_host, token, entity, p)
        records = result.get("d", {}).get("results", [])
        if not records:
            break
        all_records.extend(records)
        if len(records) < page_size:
            break
        skip += page_size
    return all_records[:max_records]


@migration_mcp.tool
async def validate_migration_file(
    entity: Annotated[str, "Target entity (e.g., 'EmpJob', 'FODepartment')"],
    file_content: Annotated[str, "CSV file content as string"],
    strict: Annotated[bool, "Strict mode: also validate picklist values and foreign key references exist"] = False,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Deep validation of a migration/import CSV file.

    Validates:
    - Column headers match entity metadata
    - Key fields are present and populated
    - Data types are correct (dates, numbers, strings)
    - Required fields are populated
    - Picklist values exist (strict mode)
    - Foreign key references exist (strict mode)
    - Date format consistency

    Returns detailed error report per row.
    """
    from helpers.template_parser import parse_csv_template
    api_host = resolve_api_host(data_center)

    parsed_csv = parse_csv_template(file_content)
    headers = parsed_csv["headers"]
    rows = parsed_csv["rows"]

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=entity)
        parsed_meta = parse_metadata_xml(xml_text)
        entity_meta = parsed_meta["entities"].get(entity, {})

        if not entity_meta:
            return {"entity": entity, "valid": False, "errors": [f"Entity '{entity}' not found"]}

        properties = entity_meta.get("properties", {})
        keys = entity_meta.get("keys", [])

        # Header validation
        header_errors = []
        valid_headers = []
        for h in headers:
            if h in properties:
                valid_headers.append(h)
            else:
                header_errors.append(f"Unknown column '{h}' not in entity metadata")

        missing_keys = [k for k in keys if k not in headers]

        # Row-level validation
        row_errors = []
        for i, row in enumerate(rows):
            row_num = i + 2  # +2 for 1-indexed + header row
            errs = []

            # Check key fields populated
            for key in keys:
                if key in row and not str(row.get(key, "")).strip():
                    errs.append(f"Key field '{key}' is empty")

            # Check required fields
            for field_name in valid_headers:
                prop = properties.get(field_name, {})
                if prop.get("required") and not str(row.get(field_name, "")).strip():
                    errs.append(f"Required field '{field_name}' is empty")

                # Type validation
                val = str(row.get(field_name, "")).strip()
                if val:
                    field_type = prop.get("type", "")
                    if field_type == "Edm.Int32" and not val.lstrip("-").isdigit():
                        errs.append(f"Field '{field_name}' expects integer, got '{val}'")
                    elif field_type == "Edm.Decimal":
                        try:
                            float(val)
                        except ValueError:
                            errs.append(f"Field '{field_name}' expects decimal, got '{val}'")
                    elif field_type == "Edm.DateTime" and val:
                        # Basic date format check
                        if not any(c in val for c in ["-", "/"]):
                            errs.append(f"Field '{field_name}' expects date format, got '{val}'")
                    elif field_type == "Edm.Boolean" and val.lower() not in ("true", "false", "1", "0"):
                        errs.append(f"Field '{field_name}' expects boolean, got '{val}'")

            if errs:
                row_errors.append({"row": row_num, "errors": errs})

        # Strict mode: validate picklist values and FKs
        picklist_errors = []
        fk_errors = []

        if strict:
            # Check picklist values
            picklist_fields = {h: properties[h].get("sap_picklist", "") for h in valid_headers if properties.get(h, {}).get("sap_picklist")}
            for pl_field, pl_id in picklist_fields.items():
                if not pl_id:
                    continue
                try:
                    pl_result = await sf.get_picklist(data_center=api_host, bearer_token=token, picklist_id=pl_id)
                    valid_codes = set()
                    for pl in pl_result.get("d", {}).get("results", []):
                        for opt in pl.get("picklistOptions", {}).get("results", []):
                            valid_codes.add(opt.get("externalCode", ""))

                    for i, row in enumerate(rows):
                        val = str(row.get(pl_field, "")).strip()
                        if val and val not in valid_codes:
                            picklist_errors.append({
                                "row": i + 2,
                                "field": pl_field,
                                "value": val,
                                "picklist_id": pl_id,
                            })
                except Exception:
                    pass

            # Check FK references (company, department, etc.)
            fo_field_map = {
                "company": "FOCompany", "department": "FODepartment",
                "division": "FODivision", "location": "FOLocation",
            }
            for fk_field, fo_entity in fo_field_map.items():
                if fk_field in valid_headers:
                    source_values = {str(row.get(fk_field, "")).strip() for row in rows if row.get(fk_field)}
                    if source_values:
                        try:
                            fo_records = await _fetch_all(sf, api_host, token, fo_entity, {"$select": "externalCode"}, max_records=5000)
                            valid_fo_codes = {r.get("externalCode", "") for r in fo_records}
                            invalid_fks = source_values - valid_fo_codes - {""}
                            for inv in invalid_fks:
                                fk_errors.append({"field": fk_field, "value": inv, "reference_entity": fo_entity})
                        except Exception:
                            pass

    total_errors = len(header_errors) + len(row_errors) + len(picklist_errors) + len(fk_errors) + len(missing_keys)

    return {
        "entity": entity,
        "valid": total_errors == 0,
        "total_rows": len(rows),
        "total_headers": len(headers),
        "valid_headers": len(valid_headers),
        "missing_key_fields": missing_keys,
        "header_errors": header_errors,
        "row_errors": row_errors[:50],
        "total_row_errors": len(row_errors),
        "picklist_errors": picklist_errors[:50] if strict else [],
        "fk_errors": fk_errors if strict else [],
        "strict_mode": strict,
    }


@migration_mcp.tool
def generate_migration_sequence(
    entities: Annotated[list[str], "List of entities to load (e.g., ['User', 'EmpEmployment', 'EmpJob', 'FOCompany'])"],
) -> dict:
    """
    Calculate the correct load order for a set of entities based on dependencies.

    Uses the predefined dependency graph from knowledge base to ensure
    Foundation Objects are loaded before employee data, employment before
    job info, etc.

    Returns the ordered sequence with dependency notes.
    """
    with open(_KB_PATH / "country_configs.json", encoding="utf-8") as f:
        config_data = json.load(f)

    migration_order = config_data.get("migration_entity_order", [])
    order_map = {item["entity"]: item for item in migration_order}

    # Build ordered list
    ordered = []
    unrecognized = []

    for item in migration_order:
        if item["entity"] in entities:
            # Check if dependencies are included
            missing_deps = [d for d in item["dependencies"] if d not in entities]
            ordered.append({
                "order": item["order"],
                "entity": item["entity"],
                "description": item["description"],
                "dependencies": item["dependencies"],
                "missing_dependencies": missing_deps,
                "warning": f"Missing dependencies: {', '.join(missing_deps)}" if missing_deps else "",
            })

    # Add entities not in predefined order
    known = {item["entity"] for item in migration_order}
    for e in entities:
        if e not in known:
            unrecognized.append(e)

    # Check for missing dependencies across the whole set
    all_warnings = [item["warning"] for item in ordered if item["warning"]]

    return {
        "total_entities": len(entities),
        "ordered_sequence": ordered,
        "unrecognized_entities": unrecognized,
        "warnings": all_warnings,
        "note": "Load entities in the order shown. Ensure all dependencies are loaded first.",
    }


@migration_mcp.tool
async def reconcile_data(
    entity: Annotated[str, "Entity to reconcile"],
    expected_count: Annotated[Optional[int], "Expected record count (from source system). If provided, compares against actual."] = None,
    group_by_field: Annotated[Optional[str], "Field to group counts by (e.g., 'company', 'department', 'countryOfCompany')"] = None,
    filter_expr: Annotated[Optional[str], "Additional OData $filter for scoping"] = None,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Reconcile data after migration — compare expected vs actual record counts.

    Can reconcile at entity level (total count) or grouped by a field
    (e.g., count per company, per department). Essential for cutover day
    validation.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)

        params: dict[str, str] = {}
        select_fields = "userId" if "userId" in entity.lower() or entity.startswith("Emp") or entity == "User" else "externalCode"
        if group_by_field:
            select_fields += f",{group_by_field}"
        params["$select"] = select_fields
        if filter_expr:
            params["$filter"] = filter_expr

        records = await _fetch_all(sf, api_host, token, entity, params, max_records=10000)

    actual_count = len(records)

    result: dict = {
        "entity": entity,
        "actual_count": actual_count,
        "filter_applied": filter_expr or "none",
    }

    if expected_count is not None:
        diff = actual_count - expected_count
        result["expected_count"] = expected_count
        result["difference"] = diff
        result["status"] = "match" if diff == 0 else ("over" if diff > 0 else "under")
        result["match_percentage"] = f"{(min(actual_count, expected_count) / max(expected_count, 1) * 100):.1f}%"

    if group_by_field:
        groups: dict[str, int] = defaultdict(int)
        for r in records:
            val = r.get(group_by_field, "(empty)") or "(empty)"
            groups[val] += 1

        result["group_by"] = group_by_field
        result["groups"] = [
            {"value": k, "count": v}
            for k, v in sorted(groups.items(), key=lambda x: x[1], reverse=True)
        ]

    return result


@migration_mcp.tool
async def generate_purge_file(
    entity: Annotated[str, "Entity to generate purge file for"],
    filter_expr: Annotated[str, "OData $filter to identify records to purge"],
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Generate a purge/delete file for SF import.

    Fetches records matching the filter and returns them with the correct
    key fields for deletion via SF import. Output includes CSV content
    ready for the SF Import tool's purge mode.

    IMPORTANT: Review the records carefully before using for deletion.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)

        # First get metadata to know the key fields
        xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=entity)
        parsed = parse_metadata_xml(xml_text)
        entity_meta = parsed["entities"].get(entity, {})

        if not entity_meta:
            return {"error": f"Entity '{entity}' not found in metadata"}

        keys = entity_meta.get("keys", [])
        if not keys:
            return {"error": f"Entity '{entity}' has no key fields defined"}

        # Fetch records matching filter
        records = await _fetch_all(sf, api_host, token, entity, {
            "$filter": filter_expr,
            "$select": ",".join(keys),
        }, max_records=5000)

    # Build CSV for purge
    csv_header = ",".join(keys)
    csv_rows = [csv_header]
    for r in records:
        row_values = []
        for k in keys:
            val = r.get(k, "")
            # Quote values that contain commas
            val_str = str(val) if val is not None else ""
            if "," in val_str:
                val_str = f'"{val_str}"'
            row_values.append(val_str)
        csv_rows.append(",".join(row_values))

    return {
        "entity": entity,
        "filter": filter_expr,
        "key_fields": keys,
        "record_count": len(records),
        "csv_content": "\n".join(csv_rows),
        "warning": "REVIEW CAREFULLY before using for deletion. This action is irreversible.",
        "sample_records": records[:5],
    }
