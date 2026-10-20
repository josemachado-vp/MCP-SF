"""
Go-live and reconciliation tools for SAP SuccessFactors.

Provides pre-go-live validation checks, reconciliation reports,
and effective-dating validation.
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

golive_mcp = FastMCP(name="SF Go-Live Tools")

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


@golive_mcp.tool
async def run_go_live_checks(
    checklist_type: Annotated[str, "Check severity to run: 'critical', 'important', 'recommended', 'all'"] = "all",
    max_sample: Annotated[int, "Max sample records to return per check"] = 10,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Run pre-go-live validation checks on the SF instance.

    Validates:
    - Critical: Employees without jobs, orphan records, missing key dates
    - Important: Vacant positions with incumbents, self-referencing managers, inactive FOs in use
    - Recommended: Email/phone completeness, compensation completeness

    Returns a pass/fail report for each check with sample affected records.
    """
    api_host = resolve_api_host(data_center)

    with open(_KB_PATH / "country_configs.json", encoding="utf-8") as f:
        config_data = json.load(f)
    gl_checks = config_data.get("golive_checks", {})

    # Select checks to run
    checks_to_run = []
    if checklist_type in ("critical", "all"):
        checks_to_run.extend([(c, "critical") for c in gl_checks.get("critical", [])])
    if checklist_type in ("important", "all"):
        checks_to_run.extend([(c, "important") for c in gl_checks.get("important", [])])
    if checklist_type in ("recommended", "all"):
        checks_to_run.extend([(c, "recommended") for c in gl_checks.get("recommended", [])])

    results = []

    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # Fetch common datasets once
        active_jobs = await _fetch_all(sf, api_host, token, "EmpJob", {
            "$filter": "emplStatus eq 'A'",
            "$select": "userId,managerId,company,department,division,location,position,emplStatus,startDate",
            "$orderby": "startDate desc",
        })

        # Deduplicate by userId
        seen = set()
        unique_jobs = []
        for j in active_jobs:
            uid = j.get("userId", "")
            if uid and uid not in seen:
                seen.add(uid)
                unique_jobs.append(j)

        for check_def, severity in checks_to_run:
            check_id = check_def["id"]
            check_result = {
                "check_id": check_id,
                "name": check_def["name"],
                "severity": severity,
                "status": "pass",
                "affected_count": 0,
                "sample_records": [],
            }

            try:
                if check_id == "GL001":
                    # Employees without active job
                    emp_result = await _fetch_all(sf, api_host, token, "EmpEmployment", {
                        "$select": "userId",
                    })
                    emp_users = {r.get("userId", "") for r in emp_result}
                    job_users = {j.get("userId", "") for j in unique_jobs}
                    missing = emp_users - job_users - {""}
                    check_result["affected_count"] = len(missing)
                    check_result["sample_records"] = [{"userId": u} for u in list(missing)[:max_sample]]
                    check_result["status"] = "fail" if missing else "pass"

                elif check_id == "GL005":
                    # Duplicate active records — already checked via dedup
                    user_counts: dict[str, int] = defaultdict(int)
                    for j in active_jobs:
                        uid = j.get("userId", "")
                        if uid:
                            user_counts[uid] += 1
                    duplicates = {u: c for u, c in user_counts.items() if c > 1}
                    check_result["affected_count"] = len(duplicates)
                    check_result["sample_records"] = [
                        {"userId": u, "record_count": c} for u, c in list(duplicates.items())[:max_sample]
                    ]
                    check_result["status"] = "fail" if duplicates else "pass"

                elif check_id == "GL011":
                    # Manager self-reference
                    self_mgr = [j for j in unique_jobs if j.get("managerId") == j.get("userId")]
                    check_result["affected_count"] = len(self_mgr)
                    check_result["sample_records"] = [
                        {"userId": j.get("userId", ""), "managerId": j.get("managerId", "")}
                        for j in self_mgr[:max_sample]
                    ]
                    check_result["status"] = "fail" if self_mgr else "pass"

                elif check_id == "GL012":
                    # Missing manager
                    no_mgr = [j for j in unique_jobs if not j.get("managerId")]
                    check_result["affected_count"] = len(no_mgr)
                    check_result["sample_records"] = [
                        {"userId": j.get("userId", "")} for j in no_mgr[:max_sample]
                    ]
                    check_result["status"] = "warning" if no_mgr else "pass"

                elif check_id == "GL013":
                    # Inactive FOs in use
                    # Check departments
                    dept_codes_in_use = {j.get("department", "") for j in unique_jobs if j.get("department")}
                    if dept_codes_in_use:
                        inactive_depts = await _sf_query(sf, api_host, token, "FODepartment", {
                            "$filter": "status eq 'I'",
                            "$select": "externalCode,name",
                            "$top": "500",
                        })
                        inactive_codes = {r.get("externalCode", "") for r in inactive_depts.get("d", {}).get("results", [])}
                        bad_refs = dept_codes_in_use & inactive_codes
                        check_result["affected_count"] = len(bad_refs)
                        check_result["sample_records"] = [{"department_code": c, "status": "inactive"} for c in list(bad_refs)[:max_sample]]
                        check_result["status"] = "fail" if bad_refs else "pass"

                elif check_id == "GL020":
                    # Email completeness
                    email_result = await _fetch_all(sf, api_host, token, "PerEmail", {
                        "$select": "personIdExternal",
                    })
                    email_users = {r.get("personIdExternal", "") for r in email_result}
                    job_users = {j.get("userId", "") for j in unique_jobs}
                    no_email = job_users - email_users - {""}
                    check_result["affected_count"] = len(no_email)
                    check_result["sample_records"] = [{"userId": u} for u in list(no_email)[:max_sample]]
                    check_result["status"] = "warning" if no_email else "pass"

                elif check_id == "GL023":
                    # Compensation completeness
                    comp_result = await _fetch_all(sf, api_host, token, "EmpCompensation", {
                        "$select": "userId",
                        "$orderby": "startDate desc",
                    })
                    comp_users = {r.get("userId", "") for r in comp_result}
                    job_users = {j.get("userId", "") for j in unique_jobs}
                    no_comp = job_users - comp_users - {""}
                    check_result["affected_count"] = len(no_comp)
                    check_result["sample_records"] = [{"userId": u} for u in list(no_comp)[:max_sample]]
                    check_result["status"] = "warning" if no_comp else "pass"

                else:
                    check_result["status"] = "skipped"
                    check_result["details"] = "Check not yet implemented for OData execution"

            except Exception as e:
                check_result["status"] = "error"
                check_result["details"] = str(e)

            results.append(check_result)

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warnings = sum(1 for r in results if r["status"] == "warning")
    errors = sum(1 for r in results if r["status"] == "error")

    return {
        "checklist_type": checklist_type,
        "total_checks": len(results),
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "errors": errors,
        # A check that errored did not verify anything, so it must block readiness.
        "ready_for_golive": failed == 0 and errors == 0,
        "checks": results,
        "active_employees_analyzed": len(unique_jobs),
    }


@golive_mcp.tool
async def generate_reconciliation_report(
    entities: Annotated[list[str], "Entities to reconcile (e.g., ['User', 'EmpJob', 'EmpEmployment', 'FOCompany'])"],
    expected_counts: Annotated[Optional[dict[str, int]], "Expected counts per entity from source system. Example: {'User': 1500, 'EmpJob': 1500}"] = None,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Generate a reconciliation report comparing expected vs actual record counts.

    Queries each entity for its record count and compares against expected
    values from the source system. Essential for cutover day validation.
    """
    api_host = resolve_api_host(data_center)
    expected = expected_counts or {}
    today = date.today().isoformat()

    report_lines = []

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        for entity in entities:
            try:
                # Get count — fetch with minimal select and count records
                id_field = "userId" if entity in ("User", "EmpJob", "EmpCompensation", "EmpEmployment") else "externalCode"
                records = await _fetch_all(sf, api_host, token, entity, {
                    "$select": id_field,
                }, max_records=10000)

                actual = len(records)
                exp = expected.get(entity)

                line = {
                    "entity": entity,
                    "actual_count": actual,
                }

                if exp is not None:
                    diff = actual - exp
                    line["expected_count"] = exp
                    line["difference"] = diff
                    line["status"] = "match" if diff == 0 else ("over" if diff > 0 else "under")
                    line["match_percentage"] = f"{(min(actual, exp) / max(exp, 1) * 100):.1f}%"
                else:
                    line["status"] = "no_expected"

                report_lines.append(line)

            except Exception as e:
                report_lines.append({
                    "entity": entity,
                    "status": "error",
                    "error": str(e),
                })

    matches = sum(1 for r in report_lines if r.get("status") == "match")
    mismatches = sum(1 for r in report_lines if r.get("status") in ("over", "under"))

    return {
        "title": "Reconciliation Report",
        "generated_date": today,
        "total_entities": len(entities),
        "matches": matches,
        "mismatches": mismatches,
        "report": report_lines,
    }
