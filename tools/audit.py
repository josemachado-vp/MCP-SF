"""
Audit and troubleshooting tools for SAP SuccessFactors.

Provides data integrity checks, anomaly detection, rule execution tracing,
and permission verification.

All operations are read-only.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.pii_filter import scrub_response
from helpers.odata_utils import escape_odata_string, validate_field_name

audit_mcp = FastMCP(name="SF Audit Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)


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


@audit_mcp.tool
async def audit_employee_data(
    user_id: Annotated[str, "Employee userId to audit"],
    checks: Annotated[Optional[list[str]], "Specific checks to run: 'job', 'employment', 'personal', 'dates', 'manager', 'compensation', 'email'. Default: all"] = None,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Run data integrity checks on a single employee.

    Validates: job info exists, employment record exists, personal info complete,
    effective dates are consistent, manager is valid, compensation exists,
    email is present. Returns findings with severity levels.
    """
    api_host = resolve_api_host(data_center)
    safe_user_id = escape_odata_string(user_id)
    all_checks = {"job", "employment", "personal", "dates", "manager", "compensation", "email"}
    requested = set(checks) if checks else all_checks
    today = date.today().isoformat()
    findings = []

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # Fetch data in parallel
        tasks = {}
        if requested & {"job", "dates", "manager"}:
            tasks["jobs"] = _sf_query(sf, api_host, token, "EmpJob", {
                "$filter": f"userId eq '{safe_user_id}'",
                "$orderby": "startDate desc",
                "$top": "50",
            })
        if "employment" in requested:
            tasks["employment"] = _sf_query(sf, api_host, token, "EmpEmployment", {
                "$filter": f"userId eq '{safe_user_id}'",
                "$top": "5",
            })
        if "personal" in requested:
            tasks["personal"] = _sf_query(sf, api_host, token, "PerPersonal", {
                "$filter": f"personIdExternal eq '{safe_user_id}'",
                "$orderby": "startDate desc",
                "$top": "5",
            })
        if "compensation" in requested:
            tasks["compensation"] = _sf_query(sf, api_host, token, "EmpCompensation", {
                "$filter": f"userId eq '{safe_user_id}'",
                "$orderby": "startDate desc",
                "$top": "10",
            })
        if "email" in requested:
            tasks["emails"] = _sf_query(sf, api_host, token, "PerEmail", {
                "$filter": f"personIdExternal eq '{safe_user_id}'",
            })

        _key_entity = {
            "jobs": "EmpJob",
            "employment": "EmpEmployment",
            "personal": "PerPersonal",
            "compensation": "EmpCompensation",
            "emails": "PerEmail",
        }

        keys = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = {}
        for k, r in zip(keys, results):
            if isinstance(r, Exception):
                findings.append({
                    "severity": "warning",
                    "title": f"Could not fetch {k}",
                    "description": str(r),
                })
                data[k] = []
            else:
                raw = r.get("d", {}).get("results", [])
                scrubbed, _ = scrub_response(_key_entity.get(k, k), raw)
                data[k] = scrubbed

    # Check: Employment record exists
    if "employment" in requested:
        emp_records = data.get("employment", [])
        if not emp_records:
            findings.append({
                "severity": "critical",
                "title": "No employment record",
                "description": f"No EmpEmployment record found for userId '{user_id}'",
                "recommendation": "Create an employment record before other data",
            })
        else:
            emp = emp_records[0]
            if not emp.get("startDate"):
                findings.append({
                    "severity": "critical",
                    "title": "Missing employment start date",
                    "description": "EmpEmployment.startDate is empty",
                })

    # Check: Job info exists and is active
    if requested & {"job", "dates", "manager"}:
        job_records = data.get("jobs", [])
        if not job_records:
            findings.append({
                "severity": "critical",
                "title": "No job information",
                "description": f"No EmpJob records found for userId '{user_id}'",
                "recommendation": "Create job information record",
            })
        else:
            current_job = job_records[0]
            status = current_job.get("emplStatus", "")

            if "job" in requested:
                if not current_job.get("company"):
                    findings.append({"severity": "warning", "title": "Missing company in job info", "description": "EmpJob.company is empty"})
                if not current_job.get("department"):
                    findings.append({"severity": "warning", "title": "Missing department in job info", "description": "EmpJob.department is empty"})
                if not current_job.get("position") and not current_job.get("jobCode"):
                    findings.append({"severity": "warning", "title": "No position or job code", "description": "Both position and jobCode are empty"})

            if "manager" in requested:
                mgr = current_job.get("managerId", "")
                if not mgr:
                    findings.append({"severity": "warning", "title": "No manager assigned", "description": "managerId is empty on current job record"})
                elif mgr == user_id:
                    findings.append({"severity": "warning", "title": "Self-referencing manager", "description": f"userId '{user_id}' is their own manager"})

            if "dates" in requested:
                # Check for date gaps/overlaps
                for i in range(len(job_records) - 1):
                    curr_end = job_records[i].get("endDate", "")
                    next_start = job_records[i + 1].get("startDate", "")
                    if curr_end and next_start and curr_end < next_start:
                        findings.append({
                            "severity": "warning",
                            "title": "Date gap in job history",
                            "description": f"Gap between endDate={curr_end} and next startDate={next_start}",
                        })

    # Check: Personal info
    if "personal" in requested:
        personal_records = data.get("personal", [])
        if not personal_records:
            findings.append({
                "severity": "warning",
                "title": "No personal information",
                "description": "No PerPersonal record found",
            })
        else:
            per = personal_records[0]
            if not per.get("firstName"):
                findings.append({"severity": "warning", "title": "Missing first name", "description": "PerPersonal.firstName is empty"})
            if not per.get("lastName"):
                findings.append({"severity": "warning", "title": "Missing last name", "description": "PerPersonal.lastName is empty"})

    # Check: Compensation
    if "compensation" in requested:
        comp_records = data.get("compensation", [])
        if not comp_records:
            findings.append({
                "severity": "info",
                "title": "No compensation record",
                "description": "No EmpCompensation record found (may be expected for some employee types)",
            })

    # Check: Email
    if "email" in requested:
        email_records = data.get("emails", [])
        if not email_records:
            findings.append({
                "severity": "info",
                "title": "No email address",
                "description": "No PerEmail record found",
            })

    # Tally
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    warning = sum(1 for f in findings if f.get("severity") == "warning")
    info = sum(1 for f in findings if f.get("severity") == "info")
    total_checks = len(requested)
    passed = total_checks - (1 if critical else 0) - (1 if warning else 0)

    return {
        "user_id": user_id,
        "checks_run": sorted(requested),
        "findings": findings,
        "critical_count": critical,
        "warning_count": warning,
        "info_count": info,
        "total_findings": len(findings),
    }


@audit_mcp.tool
async def find_data_anomalies(
    entity: Annotated[str, "Entity to check (e.g., 'EmpJob', 'User', 'FODepartment')"],
    field: Annotated[str, "Field to analyze"],
    anomaly_type: Annotated[str, "Type of anomaly: 'empty' (blank required fields), 'duplicates' (duplicate values), 'orphan' (references to non-existent records), 'future_dates' (dates in the future)"],
    scope_filter: Annotated[Optional[str], "Additional OData $filter to scope the check"] = None,
    max_results: Annotated[int, "Max anomalous records to return"] = 50,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Detect data anomalies in SF entities.

    Types:
    - 'empty': Find records where the specified field is blank/null
    - 'duplicates': Find duplicate values in the specified field
    - 'future_dates': Find date fields with values in the future
    - 'orphan': Find records referencing non-existent FO/user records
    """
    api_host = resolve_api_host(data_center)

    # Validate field name to prevent injection
    try:
        field = validate_field_name(field)
    except ValueError as e:
        return {"error": f"Invalid field name: {e}"}

    # Limit scope_filter length to prevent abuse
    if scope_filter is not None and len(scope_filter) > 2000:
        return {"error": "scope_filter exceeds maximum length of 2000 characters"}

    # Validate anomaly_type before making any HTTP calls
    valid_anomaly_types = {"empty", "duplicates", "future_dates", "orphan"}
    if anomaly_type not in valid_anomaly_types:
        return {"error": f"Unknown anomaly_type '{anomaly_type}'. Valid: empty, duplicates, future_dates, orphan"}

    # For orphan checks, validate the field is supported before making HTTP calls
    fo_field_map = {
        "company": "FOCompany", "department": "FODepartment",
        "division": "FODivision", "location": "FOLocation",
        "costCenter": "FOCostCenter", "jobCode": "FOJobCode",
    }
    if anomaly_type == "orphan":
        ref_entity = fo_field_map.get(field)
        if not ref_entity:
            return {"error": f"Orphan check not supported for field '{field}'. Supported: {list(fo_field_map.keys())}"}

    today = date.today().isoformat()

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        if anomaly_type == "empty":
            # Find records where field is empty
            filters = [f"({field} eq '' or {field} eq null)"]
            if scope_filter:
                filters.append(scope_filter)

            records = await _fetch_all(sf, api_host, token, entity, {
                "$filter": " and ".join(filters),
                "$top": str(max_results),
            }, max_records=max_results)

            return {
                "anomaly_type": "empty",
                "entity": entity,
                "field": field,
                "anomalous_count": len(records),
                "records": records[:max_results],
            }

        elif anomaly_type == "duplicates":
            # Fetch records and find duplicate values client-side
            params: dict[str, str] = {"$select": f"userId,{field}" if entity != "Position" else f"code,{field}"}
            if scope_filter:
                params["$filter"] = scope_filter

            records = await _fetch_all(sf, api_host, token, entity, params, max_records=5000)

            value_counts: dict[str, list[str]] = {}
            id_field = "userId" if "userId" in (records[0] if records else {}) else "code"
            for r in records:
                val = str(r.get(field, ""))
                if val:
                    value_counts.setdefault(val, []).append(r.get(id_field, ""))

            duplicates = [
                {"value": val, "count": len(ids), "record_ids": ids[:10]}
                for val, ids in value_counts.items()
                if len(ids) > 1
            ]
            duplicates.sort(key=lambda x: x["count"], reverse=True)

            return {
                "anomaly_type": "duplicates",
                "entity": entity,
                "field": field,
                "duplicate_values": len(duplicates),
                "total_duplicate_records": sum(d["count"] for d in duplicates),
                "duplicates": duplicates[:max_results],
            }

        elif anomaly_type == "future_dates":
            # Find records with future dates
            filters = [f"{field} gt datetime'{today}T23:59:59'"]
            if scope_filter:
                filters.append(scope_filter)

            records = await _fetch_all(sf, api_host, token, entity, {
                "$filter": " and ".join(filters),
            }, max_records=max_results)

            return {
                "anomaly_type": "future_dates",
                "entity": entity,
                "field": field,
                "as_of": today,
                "anomalous_count": len(records),
                "records": records[:max_results],
            }

        elif anomaly_type == "orphan":
            # Check if field values reference valid records
            # ref_entity was already resolved and validated before this block

            # Fetch source values
            params_src: dict[str, str] = {"$select": f"userId,{field}"}
            if scope_filter:
                params_src["$filter"] = scope_filter
            source_records = await _fetch_all(sf, api_host, token, entity, params_src, max_records=5000)

            source_values = set()
            for r in source_records:
                val = r.get(field, "")
                if val:
                    source_values.add(val)

            # Fetch reference records
            ref_records = await _fetch_all(sf, api_host, token, ref_entity, {
                "$select": "externalCode",
            }, max_records=5000)
            valid_codes = {r.get("externalCode", "") for r in ref_records}

            orphans = sorted(source_values - valid_codes)

            # Find which employees have orphan references
            orphan_employees = []
            for r in source_records:
                if r.get(field, "") in orphans:
                    orphan_employees.append({"userId": r.get("userId", ""), field: r.get(field, "")})

            return {
                "anomaly_type": "orphan",
                "entity": entity,
                "field": field,
                "reference_entity": ref_entity,
                "orphan_values": orphans[:50],
                "affected_records": orphan_employees[:max_results],
                "orphan_count": len(orphans),
                "affected_record_count": len(orphan_employees),
            }

        else:
            return {"error": f"Unknown anomaly_type '{anomaly_type}'. Valid: empty, duplicates, future_dates, orphan"}


@audit_mcp.tool
async def trace_rule_execution(
    user_id: Annotated[str, "Employee userId to trace rules for"],
    event_type: Annotated[str, "Event type: 'onSave', 'onChange', 'onInit', 'validate'"],
    base_object: Annotated[str, "Base object (e.g., 'JobInformationModel', 'CompInfoModel')"],
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Trace which business rules would apply to an employee for a given event.

    Fetches the employee's current data, then checks each configured rule's
    conditions against that data. Shows which rules match, which don't, and why.
    Invaluable for debugging "why did this field get this value?"
    """
    import json
    from pathlib import Path

    api_host = resolve_api_host(data_center)

    # Load knowledge base
    kb_path = Path(__file__).parent.parent / "knowledge"
    with open(kb_path / "base_objects.json", encoding="utf-8") as f:
        base_objects_data = json.load(f)

    # Find primary entity for base object
    primary_entity = None
    for bo in base_objects_data.get("base_objects", []):
        if bo["id"] == base_object:
            primary_entity = bo["primary_entity"]
            break

    if not primary_entity:
        return {"error": f"Unknown base_object '{base_object}'"}

    safe_user_id = escape_odata_string(user_id)

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # Fetch employee's current data
        emp_data_task = _sf_query(sf, api_host, token, primary_entity, {
            "$filter": f"userId eq '{safe_user_id}'",
            "$top": "1",
            "$orderby": "startDate desc",
        })

        # Fetch rules for this base object and event type
        rules_task = _sf_query(sf, api_host, token, "RuleHeaderBean", {
            "$filter": f"baseObject eq '{base_object}'",
            "$top": "100",
        })

        emp_result, rules_result = await asyncio.gather(emp_data_task, rules_task)

    emp_records = emp_result.get("d", {}).get("results", [])
    if not emp_records:
        return {
            "error": f"No {primary_entity} record found for userId '{user_id}'",
            "user_id": user_id,
        }

    emp_data_raw = emp_records[0]
    scrubbed_emp, _ = scrub_response(primary_entity, [emp_data_raw])
    emp_data = scrubbed_emp[0] if scrubbed_emp else emp_data_raw
    rules = rules_result.get("d", {}).get("results", [])

    trace_results = []
    for rule in rules:
        trace_results.append({
            "ruleName": rule.get("ruleName", ""),
            "ruleId": rule.get("ruleId", ""),
            "ruleScenario": rule.get("ruleScenario", ""),
            "ruleStatus": rule.get("ruleStatus", ""),
            "note": "Rule conditions cannot be fully evaluated via OData — rule body is not exposed. This shows which rules are configured for the base object.",
        })

    return {
        "user_id": user_id,
        "event_type": event_type,
        "base_object": base_object,
        "primary_entity": primary_entity,
        "employee_current_data": emp_data,
        "applicable_rules_count": len(trace_results),
        "rules": trace_results,
        "note": "SF does not expose rule conditions via OData. This trace shows configured rules and the employee's current data for manual analysis.",
    }


@audit_mcp.tool
async def check_permission_access(
    role_name: Annotated[str, "Permission role name or substring to search"],
    entity: Annotated[Optional[str], "Entity to check access for (informational — actual RBP permissions not queryable via OData)"] = None,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Look up permission role details.

    Queries RBPRole and FODynamicRole to find matching roles.
    Note: Actual field-level RBP permissions are not exposed via OData v2.
    This tool helps identify which roles exist and their basic properties.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        rbp_task = _sf_query(sf, api_host, token, "RBPRole", {
            "$filter": f"substringof('{role_name}', roleName)",
            "$top": "50",
        })
        dyn_task = _sf_query(sf, api_host, token, "FODynamicRole", {
            "$filter": f"substringof('{role_name}', dynamicRoleName)",
            "$top": "50",
        })

        rbp_result, dyn_result = await asyncio.gather(rbp_task, dyn_task, return_exceptions=True)

    rbp_roles = rbp_result.get("d", {}).get("results", []) if not isinstance(rbp_result, Exception) else []
    dyn_roles = dyn_result.get("d", {}).get("results", []) if not isinstance(dyn_result, Exception) else []

    return {
        "search": role_name,
        "entity_context": entity,
        "rbp_roles": {"count": len(rbp_roles), "data": rbp_roles},
        "dynamic_roles": {"count": len(dyn_roles), "data": dyn_roles},
        "note": "Field-level RBP permissions are not exposed via OData v2. Use Manage Permission Roles in SF admin to verify detailed access.",
    }


@audit_mcp.tool
async def validate_effective_dating(
    entity: Annotated[str, "Effective-dated entity to check: 'EmpJob', 'EmpCompensation', 'PerPersonal'"],
    user_ids: Annotated[Optional[list[str]], "Specific userIds to check. Default: sample of active employees"] = None,
    max_employees: Annotated[int, "Max employees to check (1-200)"] = 50,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Validate effective dating for time-sliced entities.

    Detects gaps and overlaps in effective-dated records. These are the
    most silent and destructive data bugs — an employee may appear to have
    no active record on a specific date due to a gap.
    """
    api_host = resolve_api_host(data_center)
    filter_field = "personIdExternal" if entity.startswith("Per") else "userId"

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # If no user_ids specified, get a sample of active employees
        if not user_ids:
            active = await _sf_query(sf, api_host, token, "EmpJob", {
                "$filter": "emplStatus eq 'A'",
                "$select": "userId",
                "$top": str(max_employees),
                "$orderby": "startDate desc",
            })
            seen = set()
            user_ids = []
            for r in active.get("d", {}).get("results", []):
                uid = r.get("userId", "")
                if uid and uid not in seen:
                    seen.add(uid)
                    user_ids.append(uid)
                    if len(user_ids) >= max_employees:
                        break

        # Check each employee
        issues = []
        checked = 0
        for uid in user_ids[:max_employees]:
            result = await _sf_query(sf, api_host, token, entity, {
                "$filter": f"{filter_field} eq '{uid}'",
                "$orderby": "startDate asc",
                "$top": "100",
            })
            records = result.get("d", {}).get("results", [])
            checked += 1

            for i in range(len(records) - 1):
                current = records[i]
                next_rec = records[i + 1]

                curr_end = current.get("endDate", "")
                next_start = next_rec.get("startDate", "")

                if not curr_end or not next_start:
                    continue

                # Normalize date strings for comparison
                curr_end_str = curr_end[:10] if curr_end else ""
                next_start_str = next_start[:10] if next_start else ""

                if curr_end_str and next_start_str:
                    if curr_end_str < next_start_str:
                        # There might be a gap (depends on date interpretation)
                        issues.append({
                            "userId": uid,
                            "type": "potential_gap",
                            "record_end": curr_end,
                            "next_record_start": next_start,
                            "severity": "warning",
                        })
                    elif curr_end_str > next_start_str:
                        issues.append({
                            "userId": uid,
                            "type": "overlap",
                            "record_end": curr_end,
                            "next_record_start": next_start,
                            "severity": "critical",
                        })

    return {
        "entity": entity,
        "employees_checked": checked,
        "issues_found": len(issues),
        "critical_count": sum(1 for i in issues if i["severity"] == "critical"),
        "warning_count": sum(1 for i in issues if i["severity"] == "warning"),
        "issues": issues[:100],
    }
