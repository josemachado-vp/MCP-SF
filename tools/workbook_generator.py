"""
Workbook generator tools.

generate_fo_workbook: Populate Object & Picklist Data workbook (28 sheets).
generate_workflow_workbook: Populate Workflow Notifications & Messages workbook (8 sheets).
generate_rules_workbook: Populate Employee Central Rules sheet from RBP workbook.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import httpx
import openpyxl
from fastmcp import FastMCP

from helpers.credentials import get_bearer_token, resolve_api_host
from helpers.sf_client import SFClient

workbook_mcp = FastMCP(name="SF Workbook Generator Tools")

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
TEMPLATES_DIR = Path(__file__).parent.parent / "Workbooks Templates"
EXPORTS_DIR = Path(__file__).parent.parent / "exports"

TEMPLATE_FO = TEMPLATES_DIR / "1_26 Version_JVL - Object & Picklist Data.xlsx"
TEMPLATE_WF = TEMPLATES_DIR / "1_26 Version_ JVL - Workflow Notifications & Messages.xlsx"
TEMPLATE_RBP = TEMPLATES_DIR / "1_26 Version_ JVL - Employee Field Data & RBP.xlsx"

_SF_SEMAPHORE = asyncio.Semaphore(5)


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _load_json(filename: str) -> dict:
    with open(KNOWLEDGE_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_nested_field(record: dict, field_path: str) -> str:
    """Resolve 'a.b.c' dotted path from a nested dict. Returns '' on any miss.

    Handles OData expanded nav properties that return {"results": [single_object]}.
    In that case, descends into results[0] automatically.
    """
    if not field_path or not record:
        return ""
    current = record
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return ""
        # Handle OData results array from expanded nav properties (to-many)
        if "results" in current and isinstance(current["results"], list):
            if not current["results"]:
                return ""
            current = current["results"][0]
            if not isinstance(current, dict):
                return ""
        current = current.get(part)
        if current is None:
            return ""
    # Final value might also be a results array (e.g. the field itself is nav)
    if isinstance(current, dict) and "results" in current:
        results = current["results"]
        return str(results[0]) if results else ""
    return str(current) if current != "" else ""


def _map_record_to_row(
    record: dict,
    odata_fields: list[str],
    field_aliases: dict | None = None,
) -> list[str]:
    """Map one OData record to a list of cell values in template column order.

    - Empty column headers ('') -> blank cell
    - '[OPERATOR]' column -> blank cell
    - field_aliases: maps template field name -> actual OData field name
    """
    aliases = field_aliases or {}
    row = []
    for field in odata_fields:
        if not field or field == "[OPERATOR]":
            row.append("")
        else:
            actual = aliases.get(field, field)
            row.append(_resolve_nested_field(record, actual))
    return row


# ── Async helpers ─────────────────────────────────────────────────────────────

async def _fetch_all_records(
    sf: SFClient,
    api_host: str,
    token: str,
    entity: str,
    expand: str = "",
    odata_filter: str = "",
    max_records: int = 5000,
    page_size: int = 200,
) -> list[dict]:
    """Paginated OData fetch. Returns [] on any error (sheet left empty with headers)."""
    records: list[dict] = []
    skip = 0
    while len(records) < max_records:
        params: dict[str, str] = {"$top": str(page_size), "$skip": str(skip)}
        if expand:
            params["$expand"] = expand
        if odata_filter:
            params["$filter"] = odata_filter
        try:
            async with _SF_SEMAPHORE:
                data = await sf.query_odata(
                    data_center=api_host, bearer_token=token,
                    entity=entity, params=params,
                )
            batch = data.get("d", {}).get("results", [])
            if not batch:
                break
            records.extend(batch)
            if len(batch) < page_size:
                break
            skip += page_size
        except Exception:
            break
    return records


def _clear_template_data_rows(ws, from_row: int = 3) -> None:
    """Delete all rows from from_row onward.

    FO template: from_row=3 (rows 1-2 are headers, row 3 is instructions)
    WF template: from_row=2 (row 1 is the only header row)
    """
    if ws.max_row >= from_row:
        ws.delete_rows(from_row, ws.max_row - from_row + 1)


def _write_records_to_sheet(
    ws,
    odata_fields: list[str],
    records: list[dict],
    field_aliases: dict,
    flatten_array_field: str = "",
) -> int:
    """Delete template rows 3+, then write SF records starting at row 3. Returns rows written."""
    _clear_template_data_rows(ws)
    rows_written = 0

    for record in records:
        if flatten_array_field:
            # Picklist: nested array -> one row per value
            nested = record.get(flatten_array_field, {})
            values = nested.get("results", []) if isinstance(nested, dict) else []
            if not values:
                continue
            for value_record in values:
                # Build a flat record where values.* fields resolve correctly
                flat = dict(record)
                flat[flatten_array_field] = value_record
                row = _map_record_to_row(flat, odata_fields, field_aliases)
                ws.append(row)
                rows_written += 1
        else:
            row = _map_record_to_row(record, odata_fields, field_aliases)
            ws.append(row)
            rows_written += 1

    return rows_written


# ── Tools ─────────────────────────────────────────────────────────────────────

@workbook_mcp.tool
async def generate_fo_workbook(
    entities: Annotated[
        str,
        "Sheet names to populate: 'all' for all 28 sheets, or a comma-separated list like 'Department,Event Reason,Location'"
    ] = "all",
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "Username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "Password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Generate a populated Object & Picklist Data workbook from the live SF instance.

    Reads all Foundation Objects (Legal Entity, Business Unit, Division, Department,
    Cost Center, Job Family, Job Function, Job Code, Location, Pay Grade, Pay Range,
    Pay Group, Pay Component, Pay Component Group, Event Reason, Time Type, etc.)
    and Picklists, then writes them to a dated Excel file in exports/.

    The output file format exactly matches the client template column layout.
    Header rows 1-2 are preserved from the template. Data starts at row 3.

    Returns: { file, sheets_populated, sheets_skipped, summary, warnings }
    """
    api_host = resolve_api_host(data_center)
    col_mapping = _load_json("workbook_column_mapping.json")
    entity_mapping = _load_json("workbook_entity_mapping.json")

    fo_col = col_mapping["FO"]["sheets"]
    fo_ent = entity_mapping["FO"]

    all_sheets = list(fo_col.keys())
    if entities == "all":
        target_sheets = all_sheets
    else:
        target_sheets = [s.strip() for s in entities.split(",")]
        invalid = [s for s in target_sheets if s not in fo_col]
        if invalid:
            return {"error": f"Unknown sheets: {invalid}. Valid: {all_sheets}"}

    wb = openpyxl.load_workbook(str(TEMPLATE_FO))

    summary: dict[str, int] = {}
    warnings: list[str] = []
    sheets_populated = 0
    sheets_skipped = 0

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        async def fetch_sheet(sheet_name: str):
            ent_cfg = fo_ent.get(sheet_name, {})
            if ent_cfg.get("manual") or not ent_cfg.get("entity"):
                return sheet_name, [], True
            try:
                records = await _fetch_all_records(
                    sf, api_host, token,
                    entity=ent_cfg["entity"],
                    expand=ent_cfg.get("expand", ""),
                    odata_filter=ent_cfg.get("filter", ""),
                )
                return sheet_name, records, False
            except Exception:
                return sheet_name, [], False

        results = await asyncio.gather(*[fetch_sheet(s) for s in target_sheets])

    for sheet_name, records, is_manual in results:
        if is_manual:
            sheets_skipped += 1
            continue

        if sheet_name not in wb.sheetnames:
            warnings.append(f"Sheet '{sheet_name}': not found in template — skipped")
            sheets_skipped += 1
            continue

        ws = wb[sheet_name]

        if not records:
            _clear_template_data_rows(ws, from_row=3)
            warnings.append(f"Sheet '{sheet_name}': 0 records returned from SF — template example rows cleared")
            summary[sheet_name] = 0
            sheets_populated += 1
            continue

        ent_cfg = fo_ent.get(sheet_name, {})
        odata_fields = fo_col[sheet_name]["odata_fields"]
        aliases = ent_cfg.get("field_aliases", {})
        flatten = ent_cfg.get("flatten_array_field", "")

        count = _write_records_to_sheet(ws, odata_fields, records, aliases, flatten)
        summary[sheet_name] = count
        sheets_populated += 1

    EXPORTS_DIR.mkdir(exist_ok=True)
    output_path = EXPORTS_DIR / f"FO_Workbook_{date.today().isoformat()}.xlsx"
    wb.save(str(output_path))

    return {
        "file": str(output_path),
        "sheets_populated": sheets_populated,
        "sheets_skipped": sheets_skipped,
        "summary": summary,
        "warnings": warnings,
    }


@workbook_mcp.tool
async def generate_workflow_workbook(
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "Username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "Password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Generate a populated Workflow Notifications & Messages workbook from the live SF instance.

    Populates: Workflows Tab, WF Processes, Dynamic Roles, Workflow Groups,
    Alert Messages, Message Definitions, Email Notification Templates.

    Workflow Configuration Settings is preserved unchanged (manual — no OData API).

    Returns: { file, sheets_populated, sheets_skipped, summary, warnings }
    """
    api_host = resolve_api_host(data_center)
    col_mapping = _load_json("workbook_column_mapping.json")
    entity_mapping = _load_json("workbook_entity_mapping.json")

    wf_col = col_mapping["WF"]["sheets"]
    wf_ent = entity_mapping["WF"]

    wb = openpyxl.load_workbook(str(TEMPLATE_WF))
    summary: dict[str, int] = {}
    warnings: list[str] = []
    sheets_populated = 0
    sheets_skipped = 0

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        async def fetch_wf_sheet(sheet_name: str):
            ent_cfg = wf_ent.get(sheet_name, {})
            if ent_cfg.get("manual") or not ent_cfg.get("entity"):
                return sheet_name, [], True
            try:
                records = await _fetch_all_records(
                    sf, api_host, token,
                    entity=ent_cfg["entity"],
                    expand=ent_cfg.get("expand", ""),
                    odata_filter=ent_cfg.get("filter", ""),
                )
                return sheet_name, records, False
            except Exception:
                return sheet_name, [], False

        results = await asyncio.gather(*[fetch_wf_sheet(s) for s in wf_col.keys()])

    for sheet_name, records, is_manual in results:
        if is_manual:
            if sheet_name in wb.sheetnames:
                _clear_template_data_rows(wb[sheet_name], from_row=2)
                warnings.append(f"Sheet '{sheet_name}': cleared (no OData API — fill manually from Admin Center)")
            sheets_skipped += 1
            continue
        if sheet_name not in wb.sheetnames:
            warnings.append(f"Sheet '{sheet_name}': not in template — skipped")
            sheets_skipped += 1
            continue

        ws = wb[sheet_name]
        if not records:
            _clear_template_data_rows(ws, from_row=2)
            warnings.append(f"Sheet '{sheet_name}': 0 records returned from SF — template example rows cleared")
            summary[sheet_name] = 0
            sheets_populated += 1
            continue

        ent_cfg = wf_ent.get(sheet_name, {})
        columns_map: dict[str, str] = ent_cfg.get("columns_map", {})
        flatten = ent_cfg.get("flatten_array_field", "")

        # WF template: row 1 = human labels (no OData paths, no instruction row)
        col_headers = [cell.value for cell in ws[1]]
        _clear_template_data_rows(ws, from_row=2)

        def _write_row(rec: dict) -> None:
            row = []
            for header in col_headers:
                sf_field = columns_map.get(header, "") if header else ""
                row.append(_resolve_nested_field(rec, sf_field) if sf_field else "")
            ws.append(row)

        rows_written = 0
        for record in records:
            if flatten:
                nested = record.get(flatten, {})
                sub_records = nested.get("results", []) if isinstance(nested, dict) else []
                if not sub_records:
                    continue
                for sub in sub_records:
                    flat = dict(record)
                    flat[flatten] = sub
                    _write_row(flat)
                    rows_written += 1
            else:
                _write_row(record)
                rows_written += 1

        summary[sheet_name] = rows_written
        sheets_populated += 1

    EXPORTS_DIR.mkdir(exist_ok=True)
    output_path = EXPORTS_DIR / f"Workflow_Workbook_{date.today().isoformat()}.xlsx"
    wb.save(str(output_path))

    return {
        "file": str(output_path),
        "sheets_populated": sheets_populated,
        "sheets_skipped": sheets_skipped,
        "summary": summary,
        "warnings": warnings,
    }


@workbook_mcp.tool
async def generate_rules_workbook(
    scenario_filter: Annotated[Optional[str], "Filter by rule scenario (e.g. 'Rules for Employee Central'). Empty = all rules."] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "Username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "Password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Populate the Employee Central Rules sheet in the Employee Field Data & RBP workbook.

    Reads all Business Rules from RuleHeaderBean and maps them to the 8 columns:
      HRIS Element / Object | Rule Name | Rule Trigger Type |
      Field to Trigger onChange Rule | Functional Description |
      Rule Description | Rule Base Object | Rule ID

    All other sheets in the RBP workbook are preserved unchanged (manual).

    Returns: { file, rules_count, warnings }
    """
    api_host = resolve_api_host(data_center)
    entity_mapping = _load_json("workbook_entity_mapping.json")

    rules_cfg = entity_mapping["RBP"]["Employee Central Rules"]
    columns_map: dict[str, str] = rules_cfg.get("columns_map", {})

    odata_filter = ""
    if scenario_filter:
        odata_filter = f"ruleScenario eq '{scenario_filter}'"

    wb = openpyxl.load_workbook(str(TEMPLATE_RBP))
    ws = wb["Employee Central Rules"]
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        records = await _fetch_all_records(
            sf, api_host, token,
            entity="RuleHeaderBean",
            odata_filter=odata_filter,
        )

    if not records:
        warnings.append("No business rules found in instance")

    # Template row 1 has the column names (not OData field paths for this sheet)
    col_headers = [cell.value for cell in ws[1] if cell.value]
    for record in records:
        row = []
        for col_header in col_headers:
            sf_field = columns_map.get(col_header, "")
            row.append(_resolve_nested_field(record, sf_field) if sf_field else "")
        ws.append(row)

    EXPORTS_DIR.mkdir(exist_ok=True)
    output_path = EXPORTS_DIR / f"Rules_Workbook_{date.today().isoformat()}.xlsx"
    wb.save(str(output_path))

    return {
        "file": str(output_path),
        "rules_count": len(records),
        "warnings": warnings,
    }
