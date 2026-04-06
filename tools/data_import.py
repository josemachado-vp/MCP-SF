"""
Data import tools for SAP SuccessFactors.

Provides tools to validate import templates, generate templates with
correct fields and picklist values, and execute upsert operations.

IMPORTANT: execute_upsert defaults to dry_run=True for safety.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.metadata_parser import parse_metadata_xml
from helpers.template_parser import (
    parse_csv_template,
    validate_template_against_metadata,
)

data_import_mcp = FastMCP(name="SF Data Import Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)


async def _sf_query(
    sf: SFClient,
    api_host: str,
    token: str,
    entity: str,
    params: dict[str, str],
) -> dict:
    async with _SF_SEMAPHORE:
        return await sf.query_odata(
            data_center=api_host,
            bearer_token=token,
            entity=entity,
            params=params,
        )


@data_import_mcp.tool
async def validate_import_template(
    entity_name: Annotated[str, "Target SF entity (e.g., 'EmpJob', 'User', 'FODepartment')"],
    headers: Annotated[list[str], "Column headers from the import template"],
    sample_rows: Annotated[Optional[list[dict]], "Optional sample data rows to validate values"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Validate an import template's headers and sample data against SF metadata.

    Checks that all column headers correspond to actual fields on the target entity,
    identifies missing key/required fields, and validates sample data types.
    Use this before executing an import to catch errors early.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(
            data_center=api_host,
            bearer_token=token,
            entity=entity_name,
        )

    parsed = parse_metadata_xml(xml_text)
    entity_meta = parsed["entities"].get(entity_name, {})

    if not entity_meta:
        return {
            "entity": entity_name,
            "valid": False,
            "errors": [f"Entity '{entity_name}' not found in metadata"],
        }

    validation = validate_template_against_metadata(headers, entity_meta)
    validation["entity"] = entity_name

    # Validate sample rows if provided
    if sample_rows:
        row_errors = []
        properties = entity_meta.get("properties", {})
        for i, row in enumerate(sample_rows[:5]):  # Check first 5 rows
            for field, value in row.items():
                if field in properties and value is not None:
                    prop = properties[field]
                    # Basic type checking
                    if prop.get("type") == "Edm.Int32" and not str(value).lstrip("-").isdigit():
                        row_errors.append({
                            "row": i + 1,
                            "field": field,
                            "value": str(value),
                            "expected_type": "integer",
                        })
                    elif prop.get("type") == "Edm.Decimal":
                        try:
                            float(str(value))
                        except ValueError:
                            row_errors.append({
                                "row": i + 1,
                                "field": field,
                                "value": str(value),
                                "expected_type": "decimal",
                            })
        if row_errors:
            validation["row_errors"] = row_errors

    return validation


@data_import_mcp.tool
async def generate_import_template(
    entity_name: Annotated[str, "Target SF entity (e.g., 'EmpJob', 'User', 'FODepartment')"],
    include_fields: Annotated[Optional[list[str]], "Specific fields to include. Default: all creatable/updatable fields"] = None,
    include_picklist_values: Annotated[bool, "Include valid picklist values as comments"] = False,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Generate an import template with correct field headers for an SF entity.

    Creates a CSV-ready template structure with field names, types, and
    whether they are key/required fields. Optionally includes valid picklist
    values to help with data preparation.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(
            data_center=api_host,
            bearer_token=token,
            entity=entity_name,
        )

    parsed = parse_metadata_xml(xml_text)
    entity_meta = parsed["entities"].get(entity_name, {})

    if not entity_meta:
        return {
            "entity": entity_name,
            "error": f"Entity '{entity_name}' not found in metadata",
        }

    properties = entity_meta.get("properties", {})
    keys = entity_meta.get("keys", [])

    # Filter fields
    if include_fields:
        fields = {k: v for k, v in properties.items() if k in include_fields}
    else:
        # Include keys + creatable/updatable fields
        fields = {
            k: v for k, v in properties.items()
            if k in keys or v.get("creatable") or v.get("updatable")
        }

    template_fields = []
    picklist_fields = []
    for name, prop in fields.items():
        field_info = {
            "name": name,
            "type": prop.get("type", ""),
            "label": prop.get("label", name),
            "is_key": name in keys,
            "required": prop.get("required", False) or name in keys,
            "creatable": prop.get("creatable", False),
            "updatable": prop.get("updatable", False),
        }
        template_fields.append(field_info)

        # Track picklist fields for value lookup
        if prop.get("sap_picklist") or "picklist" in name.lower():
            picklist_fields.append(name)

    # Fetch picklist values if requested
    picklist_values = {}
    if include_picklist_values and picklist_fields:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
            token = await get_bearer_token(http, auth_user_id, auth_password)
            sf = SFClient(http)
            for pl_field in picklist_fields[:10]:  # Limit to 10 picklists
                try:
                    result = await sf.get_picklist(
                        data_center=api_host,
                        bearer_token=token,
                        picklist_id=pl_field,
                    )
                    options = []
                    for pl in result.get("d", {}).get("results", []):
                        for opt in pl.get("picklistOptions", {}).get("results", []):
                            if opt.get("status") == "A":
                                options.append({
                                    "code": opt.get("externalCode", ""),
                                    "label": opt.get("optionValue", "") or opt.get("label", ""),
                                })
                    if options:
                        picklist_values[pl_field] = options
                except Exception:
                    pass

    # Build CSV header line
    csv_headers = [f["name"] for f in template_fields]

    return {
        "entity": entity_name,
        "csv_headers": ",".join(csv_headers),
        "fields": template_fields,
        "total_fields": len(template_fields),
        "key_fields": [f["name"] for f in template_fields if f["is_key"]],
        "required_fields": [f["name"] for f in template_fields if f["required"]],
        "picklist_values": picklist_values,
    }


@data_import_mcp.tool
async def execute_upsert(
    entity_name: Annotated[str, "Target SF entity"],
    records: Annotated[list[dict], "List of record dictionaries to upsert"],
    dry_run: Annotated[bool, "If True (default), validates without writing. Set to False to actually execute."] = True,
    batch_size: Annotated[int, "Records per batch (1-50)"] = 10,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Execute an upsert operation against an SF entity.

    IMPORTANT: Defaults to dry_run=True. In dry_run mode, validates all records
    against metadata without making any changes. Set dry_run=False to actually
    write data.

    Records are processed in batches. Each record is sent as an individual
    OData POST (upsert) to the entity endpoint.
    """
    api_host = resolve_api_host(data_center)
    batch_size = min(max(batch_size, 1), 50)

    result = {
        "entity": entity_name,
        "dry_run": dry_run,
        "total_records": len(records),
        "successful": 0,
        "failed": 0,
        "records": [],
        "errors": [],
    }

    if not records:
        result["errors"].append("No records provided")
        return result

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        if dry_run:
            # Validate only — fetch metadata and check fields
            xml_text = await sf.get_metadata(
                data_center=api_host,
                bearer_token=token,
                entity=entity_name,
            )
            parsed = parse_metadata_xml(xml_text)
            entity_meta = parsed["entities"].get(entity_name, {})

            if not entity_meta:
                result["errors"].append(f"Entity '{entity_name}' not found")
                return result

            properties = entity_meta.get("properties", {})
            keys = entity_meta.get("keys", [])

            for i, record in enumerate(records):
                record_result = {"index": i, "key": "", "status": "", "message": "", "data": record}

                # Check for key fields
                missing_keys = [k for k in keys if k not in record]
                if missing_keys:
                    record_result["status"] = "error"
                    record_result["message"] = f"Missing key fields: {', '.join(missing_keys)}"
                    result["failed"] += 1
                else:
                    record_result["key"] = "/".join(str(record.get(k, "")) for k in keys)
                    # Check for unknown fields
                    unknown = [f for f in record if f not in properties]
                    if unknown:
                        record_result["status"] = "warning"
                        record_result["message"] = f"Unknown fields (will be ignored): {', '.join(unknown)}"
                    else:
                        record_result["status"] = "valid"
                        record_result["message"] = "Ready for upsert"
                    result["successful"] += 1

                result["records"].append(record_result)

            return result

        # Actual upsert execution
        for i, record in enumerate(records):
            record_result = {"index": i, "key": "", "status": "", "message": "", "data": {}}

            try:
                async with _SF_SEMAPHORE:
                    response = await sf.upsert_odata(
                        data_center=api_host,
                        bearer_token=token,
                        entity=entity_name,
                        payload=record,
                    )
                record_result["status"] = "success"
                record_result["message"] = "Upserted successfully"
                record_result["data"] = response
                result["successful"] += 1
            except Exception as e:
                record_result["status"] = "error"
                record_result["message"] = str(e)
                result["failed"] += 1

            result["records"].append(record_result)

    return result
