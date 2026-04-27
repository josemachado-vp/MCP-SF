# Design Spec: Workbook Generator Tools

**Date:** 2026-04-13  
**Status:** Approved

## Context

SF consultants maintain three configuration workbooks throughout every implementation project:
- **Object & Picklist Data** (28 sheets) — Foundation Objects and Picklists
- **Workflow Notifications & Messages** (8 sheets) — Workflow configs, Dynamic Roles, Alert Messages
- **Employee Field Data & RBP** (7 sheets) — includes the Employee Central Rules sheet

Currently these workbooks are populated manually by querying the SF Admin Center UI. The goal is to automate population by reading directly from the SF OData API and writing a completed Excel file that matches the existing template format exactly (column order, header rows 1-2 preserved, data from row 3 onward).

## Approach

**Option B selected:** Generate a populated Excel file. The tool reads the existing template from `Workbooks Templates/`, queries SF in parallel per entity, maps OData fields to template columns, and writes output to `exports/`.

## New Tools (3 total)

### 1. `generate_fo_workbook`
Populates the Object & Picklist Data workbook (28 sheets).

**Parameters:**
- `entities` — list of sheet names to populate, or `"all"` (default)
- `data_center`, `auth_user_id`, `auth_password` — credential overrides

**Entity → OData mapping:**

| Sheet | SF OData Entity |
|---|---|
| Picklist | PicklistV2 (expand=values) |
| Legal Entity | FOCompany |
| Legal entity-Business Unit | FOBusinessUnit (nav property) |
| Business Unit | FOBusinessUnit |
| Business Unit-Division | FODivision (nav property) |
| Division | FODivision |
| Division-Department | FODepartment (nav property) |
| Department | FODepartment |
| Department-Cost Center | FOCostCenter (nav property) |
| Cost Center | FOCostCenter |
| Job Family | JobClassificationGroup |
| Job Family-Job Function | JobFunction (nav property) |
| Job Function | JobFunction |
| Job Function-Job Code | JobClassification (nav property) |
| Job Code | JobClassification |
| Region | FOGeozone |
| Location Group | FOLocationGroup |
| Location | FOLocation |
| Pay Grade | PayGrade |
| Pay Range | PayRange |
| Pay Group | FOPayGroup |
| Pay Component | PayComponent |
| Pay Component Group | PayComponentGroup |
| Event Reason | EventReason |
| Time Type | TimeType |
| Payment Method | PaymentMethod |
| Pay Type | PayType |
| Vendor | MDF entity via `query_odata` (skip with warning if not found) |

### 2. `generate_workflow_workbook`
Populates the Workflow Notifications & Messages workbook (8 sheets).

**Entity → OData mapping:**

| Sheet | SF OData Entity | Notes |
|---|---|---|
| Workflows Tab | WorkflowConfiguration | expand steps |
| WF Processes | WorkflowConfiguration | simplified view |
| Dynamic Roles | DynamicGroup | |
| Workflow Groups | WorkflowGroup | |
| Alert Messages | AlertMessage | |
| Message Definitions | list_business_rules (RAISE_MESSAGE actions) | |
| Email Notification Templates | NotificationTemplate | |
| Workflow Configuration Settings | — | **Manual — preserved from template** |

### 3. `generate_rules_workbook`
Populates only the **Employee Central Rules** sheet from the Employee Field Data & RBP workbook.

**Columns to populate:**
`HRIS Element / Object`, `Rule Name`, `Rule Trigger Type`, `Field to Trigger onChange Rule`, `Functional Description`, `Rule Description`, `Rule Base Object`, `Rule ID`

**Source:** `list_business_rules` tool output — direct field mapping.

Other sheets in this workbook (Permission Group Assignment, Field-Level Access, System Configuration Settings, Document Generation Templates, Daily Jobs) are preserved from the template unchanged — they require manual input and/or Provisioning access that is out of scope for security reasons.

## Implementation Details

### New file: `tools/workbook_generator.py`

**Internal flow per tool:**
1. Load template with `openpyxl.load_workbook(template_path)`
2. For each sheet: read rows 1-2 as column definitions (OData field paths)
3. Query SF entities in parallel using `asyncio.gather` + `asyncio.Semaphore(5)`
4. Map OData response fields to template columns by matching field path strings
5. Write rows starting at row 3, preserving header rows 1-2
6. Save to `exports/<Name>_<YYYY-MM-DD>.xlsx`
7. Return summary dict

**Reused from existing code:**
- `helpers/credentials.py` — `resolve_api_host`, `get_bearer_token`
- `helpers/sf_client.py` — `SFClient.query_odata`
- `asyncio.Semaphore(5)` — rate limiting pattern from `tools/analytics.py`
- `openpyxl` — already used in `helpers/template_parser.py`

**Template paths (hardcoded constants):**
```python
TEMPLATE_FO = "Workbooks Templates/1_26 Version_JVL - Object & Picklist Data.xlsx"
TEMPLATE_WORKFLOW = "Workbooks Templates/1_26 Version_ JVL - Workflow Notifications & Messages.xlsx"
TEMPLATE_RBP = "Workbooks Templates/1_26 Version_ JVL - Employee Field Data & RBP.xlsx"
```

### Column mapping strategy

Full column mappings (all sheets, all columns including compressed) are stored in `knowledge/workbook_column_mapping.json`. The implementation reads this file to drive all sheet population — no hardcoded column lists in tool code.

**Key observations from deep analysis:**

- Template row 1 = OData field paths. Row 2 = human labels. Data starts row 3.
- **Empty-string columns (`''`)**: Some sheets have blank header cells from merged Excel cells (e.g., Legal Entity col 2, Business Unit-Division cols 2 & 5). These columns are skipped during data population — cell left blank.
- **`[OPERATOR]` column**: Present in most FO sheets. This is the SF import operation flag. Tool leaves it blank (user fills per import intent: Delimit/Clear/Delete).
- **Hyphenated field names** (Location, Pay Grade, Location Group): Use `start-date`, `end-date`, `zip-code` — these are Foundation Object import API field names, not standard OData. Must query via Foundation Object import API or map to correct OData equivalent.
- **Time Type**: 29 columns — most complex sheet. Queries `TimeType` MDF entity.
- **Dynamic Roles**: 25 columns. Queries `DynamicGroup` MDF entity with all filter criteria fields.
- **Nested paths** (e.g., `currency.code`, `address.city`): Resolved by navigating the OData response dict recursively.

### Output

```
exports/FO_Workbook_<YYYY-MM-DD>.xlsx
exports/Workflow_Workbook_<YYYY-MM-DD>.xlsx
exports/Rules_Workbook_<YYYY-MM-DD>.xlsx
```

Response:
```json
{
  "file": "exports/FO_Workbook_2026-04-13.xlsx",
  "sheets_populated": 25,
  "sheets_skipped": 3,
  "summary": { "Legal Entity": 12, "Department": 340, "Event Reason": 87 },
  "warnings": ["Sheet 'Vendor': entity not found in instance"]
}
```

### Error handling

- **Auth failure** → raise, no file generated
- **Entity not found** → sheet preserved with headers only, added to `warnings`
- **0 records** → sheet preserved with headers only, noted in `summary`
- **Manual sheets** → copied from template unchanged, never modified
- **Partial success** → file generated even if some sheets fail

## Explicitly Out of Scope

- System Configuration Settings — no OData API, Admin Center only
- Document Generation Templates — no OData API, file-based
- Daily Jobs — Provisioning-level, no public API
- Workflow Configuration Settings — internal flags, no OData API
- Provisioning integration — security risk, no public API

## Registration in `main.py`

Add to existing `mcp.add_tool()` calls:
```python
from tools.workbook_generator import generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook
mcp.add_tool(generate_fo_workbook)
mcp.add_tool(generate_workflow_workbook)
mcp.add_tool(generate_rules_workbook)
```

## Verification

1. Run `uv run python main.py` — confirm 3 new tools appear in tool list
2. Call `generate_fo_workbook(entities=["Legal Entity", "Event Reason"])` against sandbox
3. Open generated Excel — verify headers rows 1-2 match template exactly, data starts row 3
4. Call `generate_fo_workbook(entities="all")` — verify partial success behavior if any entity fails
5. Call `generate_workflow_workbook()` — verify Workflow Configuration Settings sheet is untouched
6. Call `generate_rules_workbook()` — verify Employee Central Rules sheet populated, other sheets untouched
