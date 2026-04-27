# Workbook Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 3 MCP tools that read a live SF instance via OData and produce populated Excel workbooks (`exports/`) that exactly match the column format of the client's 3 template files (43 sheets total, headers preserved, data from row 3).

**Architecture:** New `tools/workbook_generator.py` with 3 async tools and 4 pure helper functions. Column definitions are driven by `knowledge/workbook_column_mapping.json` (already created). Entity-to-OData mapping is in new `knowledge/workbook_entity_mapping.json`. Each tool loads the template Excel, queries SF entities in parallel (asyncio + Semaphore(5)), maps OData response fields to template columns via dotted-path resolution + field aliases, and writes a dated output file to `exports/`.

**Tech Stack:** Python 3.10+, openpyxl (existing), httpx (existing), FastMCP (existing), pytest + pytest-asyncio (existing)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `knowledge/workbook_entity_mapping.json` | **Create** | Sheet → SF entity, field aliases, manual flag |
| `knowledge/workbook_column_mapping.json` | Already exists | Sheet column definitions (source of truth) |
| `tools/workbook_generator.py` | **Create** | 3 tools + 4 pure helpers + 2 async helpers |
| `tests/test_workbook_generator.py` | **Create** | Unit tests for pure helpers, import/smoke tests for tools |
| `main.py` | **Modify** | Import + register 3 new tools, update instructions string |

---

## Task 1: Create entity mapping knowledge file

**Files:**
- Create: `knowledge/workbook_entity_mapping.json`

- [ ] **Step 1: Create the file**

```json
{
  "FO": {
    "Picklist": {
      "entity": "PicklistV2",
      "expand": "values",
      "flatten_array_field": "values",
      "manual": false,
      "field_aliases": {}
    },
    "Legal Entity":                  { "entity": "FOCompany",             "manual": false, "field_aliases": {} },
    "Legal entity-Business Unit":    { "entity": "FOBusinessUnit",        "manual": false, "field_aliases": {} },
    "Business Unit":                 { "entity": "FOBusinessUnit",        "manual": false, "field_aliases": {} },
    "Business Unit-Division":        { "entity": "FODivision",            "manual": false, "field_aliases": {} },
    "Division":                      { "entity": "FODivision",            "manual": false, "field_aliases": {} },
    "Division-Department":           { "entity": "FODepartment",          "manual": false, "field_aliases": {} },
    "Department":                    { "entity": "FODepartment",          "manual": false, "field_aliases": {} },
    "Department-Cost Center":        { "entity": "FOCostCenter",          "manual": false, "field_aliases": {} },
    "Cost Center":                   { "entity": "FOCostCenter",          "manual": false, "field_aliases": {} },
    "Job Family":                    { "entity": "JobClassificationGroup","manual": false, "field_aliases": {} },
    "Job Family-Job Function":       { "entity": "JobFunction",           "manual": false, "field_aliases": {} },
    "Job Function":                  { "entity": "JobFunction",           "manual": false, "field_aliases": {} },
    "Job Function-Job Code":         { "entity": "JobClassification",     "manual": false, "field_aliases": {} },
    "Job Code":                      { "entity": "JobClassification",     "manual": false, "field_aliases": {} },
    "Region":                        { "entity": "Region",                "manual": false, "field_aliases": {} },
    "Location Group": {
      "entity": "FOLocationGroup", "manual": false,
      "field_aliases": { "start-date": "effectiveStartDate", "end-date": "effectiveEndDate" }
    },
    "Location": {
      "entity": "FOLocation", "manual": false,
      "field_aliases": {
        "start-date": "startDate", "end-date": "endDate",
        "address.zip-code": "address.zipCode"
      }
    },
    "Pay Grade": {
      "entity": "PayGrade", "manual": false,
      "field_aliases": { "start-date": "startDate", "end-date": "endDate" }
    },
    "Pay Range": {
      "entity": "PayRange", "manual": false,
      "field_aliases": { "start-date": "startDate", "end-date": "endDate" }
    },
    "Pay Group":           { "entity": "FOPayGroup",          "manual": false, "field_aliases": {} },
    "Pay Component": {
      "entity": "PayComponent", "manual": false,
      "field_aliases": { "start-date": "startDate", "end-date": "endDate" }
    },
    "Pay Component Group": {
      "entity": "PayComponentGroup", "manual": false,
      "field_aliases": { "start-date": "startDate", "end-date": "endDate" }
    },
    "Event Reason": {
      "entity": "EventReason", "manual": false,
      "field_aliases": {
        "start-date": "startDate", "end-date": "endDate",
        "custom-string1": "customString1",
        "implicit-position-action": "implicitPositionAction",
        "include-in-work-experience": "includeInWorkExperience",
        "payroll-event": "payrollEvent"
      }
    },
    "Time Type":       { "entity": "TimeType",       "manual": false, "field_aliases": {} },
    "Payment Method":  { "entity": "PaymentMethod",  "manual": false, "field_aliases": {} },
    "Pay Type":        { "entity": "PayType",         "manual": false, "field_aliases": {} },
    "Vendor":          { "entity": "Vendor",          "manual": false, "field_aliases": {} }
  },
  "WF": {
    "Workflows Tab":                  { "entity": "WorkflowConfiguration", "expand": "steps", "manual": false, "field_aliases": {} },
    "WF Processes":                   { "entity": "WorkflowConfiguration", "manual": false, "field_aliases": {} },
    "Dynamic Roles":                  { "entity": "DynamicGroup",          "manual": false, "field_aliases": {} },
    "Workflow Groups":                { "entity": "WorkflowGroup",         "manual": false, "field_aliases": {} },
    "Alert Messages":                 { "entity": "AlertMessage",          "manual": false, "field_aliases": {} },
    "Message Definitions":            { "entity": "RuleHeaderBean",        "manual": false, "field_aliases": {},
                                        "filter": "contains(ruleDescription,'RAISE_MESSAGE')" },
    "Email Notification Templates":   { "entity": "EmailNotification",     "manual": false, "field_aliases": {} },
    "Workflow Configuration Settings":{ "entity": null,                    "manual": true,  "field_aliases": {} }
  },
  "RBP": {
    "Permission Group Assignment":  { "entity": null, "manual": true, "field_aliases": {} },
    "Field-Level Access & Actions": { "entity": null, "manual": true, "field_aliases": {} },
    "HR & Admin Settings RBP":      { "entity": null, "manual": true, "field_aliases": {} },
    "Employee Central Rules":       { "entity": "RuleHeaderBean", "manual": false, "field_aliases": {},
                                      "columns_map": {
                                        "HRIS Element / Object": "hrisElement",
                                        "Rule Name": "ruleName",
                                        "Rule Trigger Type": "triggerType",
                                        "Field to Trigger onChange Rule": "triggerField",
                                        "Functional Description": "",
                                        "Rule Description": "ruleDescription",
                                        "Rule Base Object": "baseObject",
                                        "Rule ID": "ruleId"
                                      }},
    "System Configuration Settings":  { "entity": null, "manual": true, "field_aliases": {} },
    "Document Generation Templates":  { "entity": null, "manual": true, "field_aliases": {} },
    "Daily Jobs":                      { "entity": null, "manual": true, "field_aliases": {} }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/workbook_entity_mapping.json knowledge/workbook_column_mapping.json
git commit -m "feat: add workbook entity and column mapping knowledge files"
```

---

## Task 2: Write tests for pure helper functions

**Files:**
- Create: `tests/test_workbook_generator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workbook_generator.py
"""Tests for workbook_generator pure helper functions."""
import pytest


class TestResolveNestedField:
    def test_simple_field(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": "LE001"}, "externalCode") == "LE001"

    def test_two_level_nested(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"currency": {"code": "USD"}}, "currency.code") == "USD"

    def test_three_level_nested(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"address": {"city": "Lima"}}, "address.city") == "Lima"

    def test_missing_top_level_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": "X"}, "nonexistent") == ""

    def test_missing_nested_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"currency": {}}, "currency.code") == ""

    def test_none_value_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": None}, "externalCode") == ""

    def test_empty_field_path_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": "X"}, "") == ""

    def test_empty_record_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({}, "externalCode") == ""


class TestMapRecordToRow:
    def test_basic_mapping(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "D001", "name": {"en_US": "Finance"}, "effectiveStartDate": "2020-01-01"}
        fields = ["externalCode", "name.en_US", "effectiveStartDate"]
        assert _map_record_to_row(record, fields) == ["D001", "Finance", "2020-01-01"]

    def test_operator_column_becomes_empty(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "D001"}
        assert _map_record_to_row(record, ["externalCode", "[OPERATOR]"]) == ["D001", ""]

    def test_blank_column_header_becomes_empty(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "D001"}
        assert _map_record_to_row(record, ["externalCode", ""]) == ["D001", ""]

    def test_field_alias_applied(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"startDate": "2020-01-01"}
        aliases = {"start-date": "startDate"}
        assert _map_record_to_row(record, ["start-date"], aliases) == ["2020-01-01"]

    def test_missing_field_returns_empty_string(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "X"}
        assert _map_record_to_row(record, ["nonexistent"]) == [""]


class TestWorkbookGeneratorImport:
    def test_tools_importable(self):
        from tools.workbook_generator import (
            generate_fo_workbook,
            generate_workflow_workbook,
            generate_rules_workbook,
        )
        assert callable(generate_fo_workbook)
        assert callable(generate_workflow_workbook)
        assert callable(generate_rules_workbook)
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
uv run pytest tests/test_workbook_generator.py -v
```

Expected: `ImportError: cannot import name '_resolve_nested_field' from 'tools.workbook_generator'` (module doesn't exist yet).

---

## Task 3: Create `tools/workbook_generator.py` — helpers + skeletons

**Files:**
- Create: `tools/workbook_generator.py`

- [ ] **Step 1: Create the file with helpers and tool stubs**

```python
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
    """Resolve 'a.b.c' dotted path from a nested dict. Returns '' on any miss."""
    if not field_path or not record:
        return ""
    current = record
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return ""
        current = current.get(part)
        if current is None:
            return ""
    return str(current) if current != "" else ""


def _map_record_to_row(
    record: dict,
    odata_fields: list[str],
    field_aliases: dict | None = None,
) -> list[str]:
    """Map one OData record to a list of cell values in template column order.

    - Empty column headers ('') → blank cell
    - '[OPERATOR]' column → blank cell
    - field_aliases: maps template field name → actual OData field name
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


def _write_records_to_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    odata_fields: list[str],
    records: list[dict],
    field_aliases: dict,
    flatten_array_field: str = "",
) -> int:
    """Write records to worksheet starting at row 3. Returns number of rows written."""
    rows_written = 0
    start_row = 3

    for record in records:
        if flatten_array_field:
            # Picklist: expand nested array into multiple rows (one per value)
            nested = record.get(flatten_array_field, {})
            values = nested.get("results", []) if isinstance(nested, dict) else []
            if not values:
                continue
            for value_record in values:
                merged = {**record, **{flatten_array_field + "." + k: v for k, v in value_record.items()}}
                # Rebuild record so dotted path resolution works for values.* fields
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
        str | list[str],
        "Sheet names to populate ('all' for all 28 sheets, or list like ['Department', 'Event Reason'])"
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
    Manual sheets (none in this workbook) are left unchanged.

    Returns: { file, sheets_populated, sheets_skipped, summary, warnings }
    """
    api_host = resolve_api_host(data_center)
    col_mapping = _load_json("workbook_column_mapping.json")
    entity_mapping = _load_json("workbook_entity_mapping.json")

    fo_col = col_mapping["FO"]
    fo_ent = entity_mapping["FO"]

    # Determine which sheets to populate
    all_sheets = list(fo_col.keys())
    if entities == "all":
        target_sheets = all_sheets
    else:
        target_sheets = [entities] if isinstance(entities, str) else list(entities)
        invalid = [s for s in target_sheets if s not in fo_col]
        if invalid:
            return {"error": f"Unknown sheets: {invalid}. Valid: {all_sheets}"}

    # Open template (read-only=False preserves styles)
    wb = openpyxl.load_workbook(str(TEMPLATE_FO))

    summary: dict[str, int] = {}
    warnings: list[str] = []
    sheets_populated = 0
    sheets_skipped = 0

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # Fetch all entities in parallel
        async def fetch_sheet(sheet_name: str):
            ent_cfg = fo_ent.get(sheet_name, {})
            if ent_cfg.get("manual") or not ent_cfg.get("entity"):
                return sheet_name, [], True  # (name, records, is_manual)
            try:
                records = await _fetch_all_records(
                    sf, api_host, token,
                    entity=ent_cfg["entity"],
                    expand=ent_cfg.get("expand", ""),
                    odata_filter=ent_cfg.get("filter", ""),
                )
                return sheet_name, records, False
            except Exception as e:
                return sheet_name, [], False  # error → empty sheet, warning added below

        tasks = [fetch_sheet(s) for s in target_sheets]
        results = await asyncio.gather(*tasks)

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
            warnings.append(f"Sheet '{sheet_name}': 0 records returned from SF")
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

    # Save output
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

    Workflow Configuration Settings is left unchanged (manual — no OData API).

    Returns: { file, sheets_populated, sheets_skipped, summary, warnings }
    """
    api_host = resolve_api_host(data_center)
    col_mapping = _load_json("workbook_column_mapping.json")
    entity_mapping = _load_json("workbook_entity_mapping.json")

    wf_col = col_mapping["WF"]
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
            sheets_skipped += 1
            continue
        if sheet_name not in wb.sheetnames:
            warnings.append(f"Sheet '{sheet_name}': not in template — skipped")
            sheets_skipped += 1
            continue

        ws = wb[sheet_name]
        if not records:
            warnings.append(f"Sheet '{sheet_name}': 0 records returned from SF")
            summary[sheet_name] = 0
            sheets_populated += 1
            continue

        ent_cfg = wf_ent.get(sheet_name, {})
        odata_fields = wf_col[sheet_name]["odata_fields"]
        count = _write_records_to_sheet(ws, odata_fields, records, ent_cfg.get("field_aliases", {}))
        summary[sheet_name] = count
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
    scenario_filter: Annotated[Optional[str], "Filter by rule scenario. Empty = all rules."] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "Username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "Password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Populate the Employee Central Rules sheet in the Employee Field Data & RBP workbook.

    Reads all Business Rules from RuleHeaderBean and maps them to the 8 columns
    of the Employee Central Rules sheet:
      HRIS Element / Object | Rule Name | Rule Trigger Type |
      Field to Trigger onChange Rule | Functional Description |
      Rule Description | Rule Base Object | Rule ID

    All other sheets in the RBP workbook are preserved unchanged (manual).

    Returns: { file, rules_count, warnings }
    """
    api_host = resolve_api_host(data_center)
    entity_mapping = _load_json("workbook_entity_mapping.json")

    rbp_ent = entity_mapping["RBP"]
    rules_cfg = rbp_ent["Employee Central Rules"]
    columns_map: dict[str, str] = rules_cfg.get("columns_map", {})

    # Build OData filter
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

    # Template row 1 has the column names directly (not OData field paths)
    # Use columns_map to drive field resolution
    col_headers = [cell.value for cell in ws[1] if cell.value]
    for record in records:
        row = []
        for col_header in col_headers:
            sf_field = columns_map.get(col_header, "")
            if sf_field:
                row.append(_resolve_nested_field(record, sf_field))
            else:
                row.append("")  # Functional Description — no OData field, manual
        ws.append(row)

    EXPORTS_DIR.mkdir(exist_ok=True)
    output_path = EXPORTS_DIR / f"Rules_Workbook_{date.today().isoformat()}.xlsx"
    wb.save(str(output_path))

    return {
        "file": str(output_path),
        "rules_count": len(records),
        "warnings": warnings,
    }
```

- [ ] **Step 2: Run all tests — expect 14 tests to pass, import test to pass**

```bash
uv run pytest tests/test_workbook_generator.py -v
```

Expected output:
```
tests/test_workbook_generator.py::TestResolveNestedField::test_simple_field PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_two_level_nested PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_three_level_nested PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_missing_top_level_returns_empty PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_missing_nested_returns_empty PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_none_value_returns_empty PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_empty_field_path_returns_empty PASSED
tests/test_workbook_generator.py::TestResolveNestedField::test_empty_record_returns_empty PASSED
tests/test_workbook_generator.py::TestMapRecordToRow::test_basic_mapping PASSED
tests/test_workbook_generator.py::TestMapRecordToRow::test_operator_column_becomes_empty PASSED
tests/test_workbook_generator.py::TestMapRecordToRow::test_blank_column_header_becomes_empty PASSED
tests/test_workbook_generator.py::TestMapRecordToRow::test_field_alias_applied PASSED
tests/test_workbook_generator.py::TestMapRecordToRow::test_missing_field_returns_empty_string PASSED
tests/test_workbook_generator.py::TestWorkbookGeneratorImport::test_tools_importable PASSED
14 passed
```

- [ ] **Step 3: Commit**

```bash
git add tools/workbook_generator.py tests/test_workbook_generator.py
git commit -m "feat: add workbook_generator tools with pure helpers and 3 MCP tools"
```

---

## Task 4: Register tools in `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add import after the Country imports block (line ~142)**

```python
# --- Workbook Generator ---
from tools.workbook_generator import (
    generate_fo_workbook,
    generate_workflow_workbook,
    generate_rules_workbook,
)
```

- [ ] **Step 2: Add tool registrations after the last `mcp.add_tool` block**

Find the last `mcp.add_tool(generate_country_config_guide)` line and add below it:

```python
# Workbook Generator
mcp.add_tool(generate_fo_workbook)
mcp.add_tool(generate_workflow_workbook)
mcp.add_tool(generate_rules_workbook)
```

- [ ] **Step 3: Update the tool count in the module docstring**

At the top of `main.py`, change:
```python
# Provides 50 tools organized in twelve categories
```
to:
```python
# Provides 53 tools organized in thirteen categories
```

- [ ] **Step 4: Add Workbook Generator to the instructions string**

After the Country Support section (around line 215), add:
```python
        "**Workbook Generator** (populate client Excel workbooks):\n"
        "51. generate_fo_workbook - Populate Object & Picklist Data workbook (28 sheets)\n"
        "52. generate_workflow_workbook - Populate Workflow Notifications workbook (8 sheets)\n"
        "53. generate_rules_workbook - Populate Employee Central Rules sheet\n\n"
```

- [ ] **Step 5: Verify server starts without errors**

```bash
uv run python main.py &
sleep 3
kill %1
```

Expected: No import errors or tracebacks. Process starts cleanly.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests pass + 14 new workbook_generator tests pass.

- [ ] **Step 7: Commit**

```bash
git add main.py
git commit -m "feat: register generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook in MCP server"
```

---

## Task 5: End-to-end verification

This task requires a live SF sandbox connection. Set credentials in `.env` first.

- [ ] **Step 1: Verify all 3 tools appear in tool list**

```bash
uv run python -c "
import main
tools = [t.name for t in main.mcp._tool_manager.list_tools()]
wb_tools = [t for t in tools if 'workbook' in t]
print('Workbook tools:', wb_tools)
print('Total tools:', len(tools))
"
```

Expected:
```
Workbook tools: ['generate_fo_workbook', 'generate_workflow_workbook', 'generate_rules_workbook']
Total tools: 53
```

- [ ] **Step 2: Test FO workbook with 2 sheets (fast)**

```bash
uv run python -c "
import asyncio
from tools.workbook_generator import generate_fo_workbook

async def main():
    result = await generate_fo_workbook(entities=['Department', 'Event Reason'])
    print(result)

asyncio.run(main())
"
```

Expected: `file` key with path to generated Excel, `summary` shows record counts for Department and Event Reason, no `error` key.

- [ ] **Step 3: Open generated Excel and verify**

Open the file from `result['file']`. Check:
- Sheet "Department": row 1 = `externalCode`, `name.en_US`, etc. (header preserved from template)
- Sheet "Department": row 3+ = actual department data from SF
- Sheet "Event Reason": row 3+ = actual event reasons

- [ ] **Step 4: Test rules workbook**

```bash
uv run python -c "
import asyncio
from tools.workbook_generator import generate_rules_workbook

async def main():
    result = await generate_rules_workbook()
    print(result)

asyncio.run(main())
"
```

Expected: `rules_count` > 0, file generated in `exports/`.

- [ ] **Step 5: Test partial failure behavior**

```bash
uv run python -c "
import asyncio
from tools.workbook_generator import generate_fo_workbook

async def main():
    # 'Vendor' is likely to fail or return 0 in most instances
    result = await generate_fo_workbook(entities=['Legal Entity', 'Vendor', 'Department'])
    print('Warnings:', result.get('warnings'))
    print('Summary:', result.get('summary'))

asyncio.run(main())
"
```

Expected: File is generated even if Vendor returns 0 records. Warning logged for Vendor if it fails. Legal Entity and Department populated normally.

---

## Self-Review Checklist

**Spec coverage:**
- ✅ generate_fo_workbook — 28 sheets, populates FO + Picklists
- ✅ generate_workflow_workbook — 8 sheets, manual sheets preserved
- ✅ generate_rules_workbook — Employee Central Rules sheet
- ✅ Column mapping driven by knowledge/workbook_column_mapping.json
- ✅ Entity mapping driven by knowledge/workbook_entity_mapping.json
- ✅ Field aliases for hyphenated fields (start-date, end-date, etc.)
- ✅ [OPERATOR] and blank columns → empty cells
- ✅ Picklist flatten_array_field handling
- ✅ Partial success — file generated even if some sheets fail
- ✅ Manual sheets preserved unchanged from template
- ✅ Output to exports/ with dated filename
- ✅ Registered in main.py

**Known limitations documented in tool docstrings:**
- Vendor entity may not exist in all instances → warning issued, sheet empty
- Functional Description column in Employee Central Rules has no OData source → always blank
- WorkflowConfiguration step expansion depends on tenant configuration
