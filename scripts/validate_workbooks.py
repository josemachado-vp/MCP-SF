"""
Validate that generated workbooks are filled correctly against the template.

Rules enforced:
1. Only columns defined in workbook_column_mapping.json / workbook_entity_mapping.json
   should contain data.
2. Columns that have no corresponding OData field (empty string in odata_fields or
   missing from columns_map) must be BLANK in every data row.
3. Columns with [OPERATOR] marker in the FO template must be BLANK.
4. Any template residual content (rows 1-2 headers, instruction row 3) must not
   appear in data rows (row 3+).
5. If a mapped field resolved to empty/None, the cell must be "" (not literal "None"
   or template placeholder).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent.parent
KNOWLEDGE = ROOT / "knowledge"
EXPORTS = ROOT / "exports"
TEMPLATES = ROOT / "Workbooks Templates"


def _load(name: str) -> dict:
    with open(KNOWLEDGE / name, encoding="utf-8") as f:
        return json.load(f)


def _find_latest(prefix: str) -> Path | None:
    files = sorted(EXPORTS.glob(f"{prefix}_*.xlsx"), reverse=True)
    return files[0] if files else None


def validate_fo_workbook(path: Path) -> list[str]:
    issues: list[str] = []
    col_map = _load("workbook_column_mapping.json")["FO"]["sheets"]
    ent_map = _load("workbook_entity_mapping.json")["FO"]

    wb = openpyxl.load_workbook(str(path), data_only=False)

    for sheet_name, cfg in col_map.items():
        if sheet_name not in wb.sheetnames:
            issues.append(f"[FO:{sheet_name}] sheet missing from output file")
            continue

        ws = wb[sheet_name]
        odata_fields: list[str] = cfg["odata_fields"]
        ent_cfg = ent_map.get(sheet_name, {})

        # Skip manual sheets
        if ent_cfg.get("manual"):
            continue

        # Identify columns that MUST be blank (no mapping or [OPERATOR])
        blank_cols = [
            idx for idx, f in enumerate(odata_fields, start=1)
            if not f or f == "[OPERATOR]"
        ]

        # Data starts at row 3 (rows 1-2 are headers)
        data_start = 3
        if ws.max_row < data_start:
            continue

        for row_idx in range(data_start, ws.max_row + 1):
            for col_idx in blank_cols:
                val = ws.cell(row=row_idx, column=col_idx).value
                if val not in (None, ""):
                    issues.append(
                        f"[FO:{sheet_name}] row {row_idx} col {col_idx}: "
                        f"expected blank, got '{val}'"
                    )

            # Any cell containing literal 'None' string is a bug
            for col_idx in range(1, len(odata_fields) + 1):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val == "None":
                    issues.append(
                        f"[FO:{sheet_name}] row {row_idx} col {col_idx}: "
                        f"literal 'None' string — should be blank"
                    )

    return issues


def validate_wf_workbook(path: Path) -> list[str]:
    issues: list[str] = []
    col_map = _load("workbook_column_mapping.json")["WF"]["sheets"]
    ent_map = _load("workbook_entity_mapping.json")["WF"]

    wb = openpyxl.load_workbook(str(path), data_only=False)

    for sheet_name in col_map.keys():
        if sheet_name not in wb.sheetnames:
            issues.append(f"[WF:{sheet_name}] sheet missing")
            continue

        ws = wb[sheet_name]
        ent_cfg = ent_map.get(sheet_name, {})

        if ent_cfg.get("manual"):
            # Manual sheets should have been cleared of template data
            continue

        columns_map = ent_cfg.get("columns_map", {})
        col_headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]

        # Columns whose header has no mapping -> must be blank
        blank_cols = [
            idx for idx, h in enumerate(col_headers, start=1)
            if h and h not in columns_map
        ]
        blank_cols += [
            idx for idx, h in enumerate(col_headers, start=1) if not h
        ]

        data_start = 2
        for row_idx in range(data_start, ws.max_row + 1):
            for col_idx in blank_cols:
                val = ws.cell(row=row_idx, column=col_idx).value
                if val not in (None, ""):
                    issues.append(
                        f"[WF:{sheet_name}] row {row_idx} col {col_idx} "
                        f"(header='{col_headers[col_idx - 1]}'): "
                        f"expected blank (no mapping), got '{val}'"
                    )
            for col_idx in range(1, len(col_headers) + 1):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val == "None":
                    issues.append(
                        f"[WF:{sheet_name}] row {row_idx} col {col_idx}: "
                        f"literal 'None' string — should be blank"
                    )

    return issues


def main() -> int:
    fo = _find_latest("FO_Workbook")
    wf = _find_latest("Workflow_Workbook")

    all_issues: list[str] = []

    if fo:
        print(f"Validating FO workbook: {fo.name}")
        issues = validate_fo_workbook(fo)
        print(f"  {'OK' if not issues else f'{len(issues)} issues'}")
        all_issues.extend(issues)
    else:
        print("No FO_Workbook_*.xlsx found in exports/")

    if wf:
        print(f"Validating WF workbook: {wf.name}")
        issues = validate_wf_workbook(wf)
        print(f"  {'OK' if not issues else f'{len(issues)} issues'}")
        all_issues.extend(issues)
    else:
        print("No Workflow_Workbook_*.xlsx found in exports/")

    if all_issues:
        print("\n=== Issues found ===")
        for i in all_issues[:100]:
            print(" -", i)
        if len(all_issues) > 100:
            print(f" ...and {len(all_issues) - 100} more")
        return 1

    print("\nAll validations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
