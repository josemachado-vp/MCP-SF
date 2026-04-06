"""
Analytics tools for SAP SuccessFactors.

Provides headcount analytics, compensation statistics, and rule impact
simulation. All analytics are computed client-side since OData v2 does
not support $apply/groupby.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date
from statistics import mean, median
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token

analytics_mcp = FastMCP(name="SF Analytics Tools")

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


async def _fetch_all_pages(
    sf: SFClient,
    api_host: str,
    token: str,
    entity: str,
    base_params: dict[str, str],
    max_records: int = 5000,
    page_size: int = 1000,
) -> list[dict]:
    """Fetch all records with pagination."""
    all_records: list[dict] = []
    skip = 0

    while len(all_records) < max_records:
        params = {**base_params, "$top": str(page_size), "$skip": str(skip)}
        result = await _sf_query(sf, api_host, token, entity, params)
        records = result.get("d", {}).get("results", [])
        if not records:
            break
        all_records.extend(records)
        if len(records) < page_size:
            break
        skip += page_size

    return all_records[:max_records]


@analytics_mcp.tool
async def get_headcount(
    group_by: Annotated[str, "Field to group by: 'department', 'company', 'division', 'location', 'countryOfCompany', 'employmentType', 'employeeClass'"],
    filters: Annotated[Optional[str], "Additional OData $filter expression"] = None,
    include_inactive: Annotated[bool, "Include terminated/inactive employees"] = False,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get headcount grouped by a specific field.

    Aggregates employee counts by department, company, location, country, etc.
    Computed client-side since OData v2 doesn't support $apply/groupby.

    Note: For large organizations, results are based on up to 5000 active
    employee records.
    """
    valid_fields = {
        "department", "company", "division", "location",
        "countryOfCompany", "employmentType", "employeeClass",
        "costCenter", "position", "jobCode",
    }
    if group_by not in valid_fields:
        return {"error": f"Invalid group_by field '{group_by}'. Valid: {sorted(valid_fields)}"}

    api_host = resolve_api_host(data_center)

    base_filter = "emplStatus eq 'A'" if not include_inactive else ""
    if filters:
        base_filter = f"{base_filter} and {filters}" if base_filter else filters

    params: dict[str, str] = {
        "$select": f"userId,{group_by}",
        "$orderby": "startDate desc",
    }
    if base_filter:
        params["$filter"] = base_filter

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        records = await _fetch_all_pages(sf, api_host, token, "EmpJob", params)

    # Deduplicate by userId (keep most recent record due to orderby)
    seen_users: set[str] = set()
    counts: dict[str, int] = defaultdict(int)
    total = 0

    for record in records:
        uid = record.get("userId", "")
        if uid and uid not in seen_users:
            seen_users.add(uid)
            group_value = record.get(group_by, "(empty)")
            if not group_value:
                group_value = "(empty)"
            counts[group_value] += 1
            total += 1

    # Sort by count descending
    sorted_groups = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "group_by": group_by,
        "total_employees": total,
        "groups": [{"value": k, "count": v, "percentage": f"{(v/total*100):.1f}%"} for k, v in sorted_groups] if total > 0 else [],
        "unique_groups": len(counts),
        "include_inactive": include_inactive,
    }


@analytics_mcp.tool
async def get_compensation_analytics(
    scope_field: Annotated[str, "Field to scope analysis by: 'department', 'company', 'division', 'location', 'countryOfCompany', 'jobCode'"],
    scope_value: Annotated[Optional[str], "Value to filter scope_field by. If None, shows stats for all values."] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get compensation statistics (average, min, max, median compa-ratio
    and range penetration) grouped by a scope field.

    Queries EmpCompensation joined with EmpJob for the scope field.
    Note: Limited to 5000 records for performance.
    """
    api_host = resolve_api_host(data_center)
    today = date.today().isoformat()

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # Fetch compensation data
        comp_filter = "startDate le datetime'{}T00:00:00'".format(today)
        comp_params: dict[str, str] = {
            "$filter": comp_filter,
            "$select": "userId,compaRatio,rangePenetration,payGroup,payType",
            "$orderby": "startDate desc",
        }
        comp_records = await _fetch_all_pages(sf, api_host, token, "EmpCompensation", comp_params, max_records=5000)

        # If we need a scope field from EmpJob, fetch that too
        job_scope_fields = {"department", "company", "division", "location", "countryOfCompany", "jobCode"}
        user_scope_map: dict[str, str] = {}

        if scope_field in job_scope_fields:
            job_filter = "emplStatus eq 'A'"
            if scope_value:
                job_filter += f" and {scope_field} eq '{scope_value}'"
            job_params: dict[str, str] = {
                "$filter": job_filter,
                "$select": f"userId,{scope_field}",
                "$orderby": "startDate desc",
            }
            job_records = await _fetch_all_pages(sf, api_host, token, "EmpJob", job_params, max_records=5000)

            # Build userId → scope value map (most recent record)
            for rec in job_records:
                uid = rec.get("userId", "")
                if uid and uid not in user_scope_map:
                    user_scope_map[uid] = rec.get(scope_field, "(empty)") or "(empty)"

    # Deduplicate comp records by userId
    seen: set[str] = set()
    by_group: dict[str, list[dict]] = defaultdict(list)

    for rec in comp_records:
        uid = rec.get("userId", "")
        if uid and uid not in seen:
            seen.add(uid)
            if scope_field in job_scope_fields:
                group = user_scope_map.get(uid, "(unknown)")
                if scope_value and group != scope_value:
                    continue
            else:
                group = rec.get(scope_field, "(empty)") or "(empty)"
            by_group[group].append(rec)

    # Compute stats per group
    def _compute_stats(records: list[dict], field: str) -> dict:
        values = []
        for r in records:
            val = r.get(field)
            if val is not None:
                try:
                    values.append(float(str(val)))
                except (ValueError, TypeError):
                    pass
        if not values:
            return {"count": 0, "avg": None, "min": None, "max": None, "median": None}
        return {
            "count": len(values),
            "avg": round(mean(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "median": round(median(values), 4),
        }

    groups_stats = []
    for group_name, group_records in sorted(by_group.items()):
        groups_stats.append({
            "group": group_name,
            "employee_count": len(group_records),
            "compa_ratio": _compute_stats(group_records, "compaRatio"),
            "range_penetration": _compute_stats(group_records, "rangePenetration"),
        })

    return {
        "scope_field": scope_field,
        "scope_value": scope_value,
        "total_employees_analyzed": sum(len(recs) for recs in by_group.values()),
        "groups": groups_stats,
    }


@analytics_mcp.tool
async def simulate_rule_impact(
    rule_spec: Annotated[dict, "Rule specification (from generate_rule_spec) with conditions and actions"],
    target_population: Annotated[Optional[str], "OData $filter to define target population. Default: all active employees."] = None,
    sample_size: Annotated[int, "Maximum employees to evaluate (1-1000)"] = 100,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Simulate the impact of a business rule against real employee data.

    Evaluates the rule's conditions against actual employee records and shows
    which employees would be affected and what changes would be made.
    This is a read-only simulation — no data is modified.

    Useful for impact analysis before deploying a new rule.
    """
    api_host = resolve_api_host(data_center)
    sample_size = min(max(sample_size, 1), 1000)

    # Extract entity and fields needed from rule spec
    conditions = rule_spec.get("conditions", [])
    if not conditions:
        return {"error": "Rule spec has no conditions to evaluate"}

    # Collect all fields referenced in conditions
    needed_fields: set[str] = set()
    for cond in conditions:
        expr = cond.get("expression", {})
        if expr.get("field"):
            needed_fields.add(expr["field"])
        for nested in cond.get("nested_conditions", []):
            nexpr = nested.get("expression", {})
            if nexpr.get("field"):
                needed_fields.add(nexpr["field"])

    # Always include userId
    needed_fields.add("userId")

    base_filter = target_population or "emplStatus eq 'A'"

    params: dict[str, str] = {
        "$filter": base_filter,
        "$select": ",".join(needed_fields),
        "$top": str(sample_size),
        "$orderby": "startDate desc",
    }

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        entity = rule_spec.get("base_object_entity", "EmpJob")
        records = await _fetch_all_pages(
            sf, api_host, token, entity, params, max_records=sample_size
        )

    # Deduplicate
    seen: set[str] = set()
    unique_records: list[dict] = []
    for rec in records:
        uid = rec.get("userId", "")
        if uid and uid not in seen:
            seen.add(uid)
            unique_records.append(rec)

    # Evaluate conditions
    affected: list[dict] = []
    not_affected: list[str] = []

    _OPERATORS = {
        "equals": lambda a, b: str(a) == str(b),
        "notEquals": lambda a, b: str(a) != str(b),
        "in": lambda a, b: str(a) in [v.strip() for v in str(b).split(",")],
        "notIn": lambda a, b: str(a) not in [v.strip() for v in str(b).split(",")],
        "isEmpty": lambda a, b: not a or str(a).strip() == "",
        "isNotEmpty": lambda a, b: a and str(a).strip() != "",
        "contains": lambda a, b: str(b) in str(a),
        "greaterThan": lambda a, b: _safe_compare(a, b, ">"),
        "lessThan": lambda a, b: _safe_compare(a, b, "<"),
    }

    def _safe_compare(a, b, op: str) -> bool:
        try:
            fa, fb = float(str(a)), float(str(b))
            return fa > fb if op == ">" else fa < fb
        except (ValueError, TypeError):
            return False

    def _evaluate_condition(record: dict, cond: dict) -> bool:
        expr = cond.get("expression", {})
        field = expr.get("field", "")
        operator = expr.get("operator", "")
        value = expr.get("value", "")

        record_value = record.get(field, "")
        op_func = _OPERATORS.get(operator)
        if not op_func:
            return False
        return op_func(record_value, value)

    for record in unique_records:
        uid = record.get("userId", "")
        matches = False

        for cond in conditions:
            ctype = cond.get("type", "IF")
            result = _evaluate_condition(record, cond)

            # Evaluate nested conditions
            for nested in cond.get("nested_conditions", []):
                ntype = nested.get("type", "AND_IF")
                nresult = _evaluate_condition(record, nested)
                if ntype == "AND_IF":
                    result = result and nresult
                elif ntype == "OR_IF":
                    result = result or nresult

            if result:
                # Collect what would change
                action = cond.get("action", {})
                affected.append({
                    "userId": uid,
                    "matched_condition": cond.get("sequence", 0),
                    "current_values": {
                        expr.get("field", ""): record.get(expr.get("field", ""), "")
                        for expr in [cond.get("expression", {})]
                        if expr.get("field")
                    },
                    "proposed_action": action if action else "no action defined",
                })
                matches = True
                break  # First matching condition wins

        if not matches:
            not_affected.append(uid)

    return {
        "rule_name": rule_spec.get("rule_name", "unnamed"),
        "total_evaluated": len(unique_records),
        "affected_count": len(affected),
        "not_affected_count": len(not_affected),
        "impact_percentage": f"{(len(affected)/len(unique_records)*100):.1f}%" if unique_records else "0%",
        "affected_employees": affected[:50],  # Limit response size
        "sample_not_affected": not_affected[:10],
    }
