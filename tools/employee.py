"""
Employee tools for SAP SuccessFactors.

Provides tools to search employees, retrieve profiles, navigate org charts,
view employment history, and compare employees side by side.

All queries are read-only OData GET operations.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.nl_query_parser import parse_nl_query, build_effective_date_filter

employee_mcp = FastMCP(name="SF Employee Tools")

# Semaphore to limit concurrent SF API calls
_SF_SEMAPHORE = asyncio.Semaphore(5)


async def _sf_query(
    sf: SFClient,
    api_host: str,
    token: str,
    entity: str,
    params: dict[str, str],
) -> dict:
    """Execute an SF query with concurrency limiting."""
    async with _SF_SEMAPHORE:
        return await sf.query_odata(
            data_center=api_host,
            bearer_token=token,
            entity=entity,
            params=params,
        )


@employee_mcp.tool
async def search_employees(
    query: Annotated[str, "Natural language search query. Examples: 'John Smith', 'department 40000013', 'employees in Colombia', 'active employees in location NYC'"],
    search_fields: Annotated[Optional[list[str]], "Fields to search in for name queries. Default: firstName, lastName"] = None,
    max_results: Annotated[int, "Maximum results to return (1-100)"] = 20,
    include_inactive: Annotated[bool, "Include terminated/inactive employees"] = False,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Search for employees using natural language queries.

    Supports searching by:
    - Name: "John", "John Smith", "Smith"
    - Department: "department 40000013", "dept HR"
    - Country: "country COL", "employees in Colombia"
    - Status: "active employees", "terminated employees"
    - Location: "location NYC"
    - Manager: "reports to admin", "manager 12345"
    - Company: "company 1000"
    - User ID: "user admin"

    Combinations work too: "active employees in department 40000013"
    """
    api_host = resolve_api_host(data_center)
    parsed = parse_nl_query(query, search_fields, include_inactive, min(max_results, 100))

    params: dict[str, str] = {"$format": "json", "$top": str(parsed.top)}
    if parsed.filters:
        params["$filter"] = " and ".join(parsed.filters)
    if parsed.select:
        params["$select"] = parsed.select

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        result = await _sf_query(sf, api_host, token, parsed.entity, params)

    records = result.get("d", {}).get("results", [])
    return {
        "query": query,
        "interpretation": parsed.interpretation,
        "entity_queried": parsed.entity,
        "filter_applied": params.get("$filter", "none"),
        "count": len(records),
        "data": records,
    }


@employee_mcp.tool
async def get_employee_profile(
    user_id: Annotated[str, "The userId of the employee to retrieve"],
    sections: Annotated[Optional[list[str]], "Sections to include: 'personal', 'job', 'compensation', 'employment', 'emails', 'phones', 'user'. Default: all"] = None,
    as_of_date: Annotated[Optional[str], "Date for effective-dated entities (YYYY-MM-DD). Default: today"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get a complete employee profile by assembling data from multiple SF entities.

    Fetches User, EmpJob, EmpCompensation, EmpEmployment, PerPersonal, PerEmail,
    and PerPhone in parallel for maximum performance.

    Sections can be filtered to reduce API calls. Effective-dated entities
    (job, compensation, personal) use as_of_date for point-in-time queries.
    """
    api_host = resolve_api_host(data_center)
    effective_date = as_of_date or date.today().isoformat()
    all_sections = {"personal", "job", "compensation", "employment", "emails", "phones", "user"}
    requested = set(sections) if sections else all_sections

    profile: dict = {"user_id": user_id, "as_of_date": effective_date, "sections": []}

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        tasks = {}

        if "user" in requested:
            tasks["user"] = _sf_query(sf, api_host, token, "User", {
                "$filter": f"userId eq '{user_id}'",
                "$top": "1",
            })

        if "job" in requested:
            job_filter = f"userId eq '{user_id}'"
            date_filter = build_effective_date_filter("EmpJob", effective_date)
            if date_filter:
                job_filter += f" and {date_filter}"
            tasks["job"] = _sf_query(sf, api_host, token, "EmpJob", {
                "$filter": job_filter,
                "$top": "1",
                "$orderby": "startDate desc",
            })

        if "compensation" in requested:
            comp_filter = f"userId eq '{user_id}'"
            date_filter = build_effective_date_filter("EmpCompensation", effective_date)
            if date_filter:
                comp_filter += f" and {date_filter}"
            tasks["compensation"] = _sf_query(sf, api_host, token, "EmpCompensation", {
                "$filter": comp_filter,
                "$top": "1",
                "$orderby": "startDate desc",
            })

        if "employment" in requested:
            tasks["employment"] = _sf_query(sf, api_host, token, "EmpEmployment", {
                "$filter": f"userId eq '{user_id}'",
                "$top": "1",
            })

        if "personal" in requested:
            tasks["personal"] = _sf_query(sf, api_host, token, "PerPersonal", {
                "$filter": f"personIdExternal eq '{user_id}'",
                "$top": "1",
                "$orderby": "startDate desc",
            })

        if "emails" in requested:
            tasks["emails"] = _sf_query(sf, api_host, token, "PerEmail", {
                "$filter": f"personIdExternal eq '{user_id}'",
            })

        if "phones" in requested:
            tasks["phones"] = _sf_query(sf, api_host, token, "PerPhone", {
                "$filter": f"personIdExternal eq '{user_id}'",
            })

        # Execute all queries in parallel
        keys = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                profile[key] = {"error": str(result)}
            else:
                records = result.get("d", {}).get("results", [])
                if key in ("emails", "phones"):
                    profile[key] = records
                else:
                    profile[key] = records[0] if records else {}
            profile["sections"].append(key)

    return profile


@employee_mcp.tool
async def get_org_chart(
    user_id: Annotated[str, "The userId to center the org chart on"],
    depth_up: Annotated[int, "Levels of managers above (0-5)"] = 2,
    depth_down: Annotated[int, "Levels of direct reports below (0-3)"] = 1,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get the organizational chart centered on a specific employee.

    Navigates upward through managerId to show the management chain,
    and downward to show direct reports. Uses EmpJob for manager relationships
    and User for names/titles.
    """
    api_host = resolve_api_host(data_center)
    today = date.today().isoformat()

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        async def get_employee_info(uid: str) -> dict:
            """Get basic info for an employee."""
            result = await _sf_query(sf, api_host, token, "EmpJob", {
                "$filter": f"userId eq '{uid}' and emplStatus eq 'A'",
                "$select": "userId,managerId,department,position,jobTitle",
                "$top": "1",
                "$orderby": "startDate desc",
            })
            records = result.get("d", {}).get("results", [])
            if not records:
                return {"userId": uid}
            return records[0]

        async def get_user_name(uid: str) -> dict:
            """Get user's name and title."""
            result = await _sf_query(sf, api_host, token, "User", {
                "$filter": f"userId eq '{uid}'",
                "$select": "userId,firstName,lastName,title,department",
                "$top": "1",
            })
            records = result.get("d", {}).get("results", [])
            if not records:
                return {"userId": uid}
            return records[0]

        async def get_direct_reports(uid: str) -> list[dict]:
            """Get direct reports for a manager."""
            result = await _sf_query(sf, api_host, token, "EmpJob", {
                "$filter": f"managerId eq '{uid}' and emplStatus eq 'A'",
                "$select": "userId,managerId,department,position,jobTitle",
                "$top": "50",
                "$orderby": "startDate desc",
            })
            records = result.get("d", {}).get("results", [])
            # Deduplicate by userId (effective-dated may return duplicates)
            seen = set()
            unique = []
            for r in records:
                uid_r = r.get("userId", "")
                if uid_r and uid_r not in seen:
                    seen.add(uid_r)
                    unique.append(r)
            return unique

        # Build center node
        center_info, center_user = await asyncio.gather(
            get_employee_info(user_id),
            get_user_name(user_id),
        )

        center_node = {
            "userId": user_id,
            "name": f"{center_user.get('firstName', '')} {center_user.get('lastName', '')}".strip(),
            "title": center_user.get("title", "") or center_info.get("jobTitle", ""),
            "department": center_user.get("department", "") or center_info.get("department", ""),
            "position": center_info.get("position", ""),
            "level": 0,
        }

        # Navigate up (managers)
        managers = []
        current_id = center_info.get("managerId", "")
        for level in range(1, min(depth_up, 5) + 1):
            if not current_id or current_id == user_id:
                break
            mgr_info, mgr_user = await asyncio.gather(
                get_employee_info(current_id),
                get_user_name(current_id),
            )
            managers.append({
                "userId": current_id,
                "name": f"{mgr_user.get('firstName', '')} {mgr_user.get('lastName', '')}".strip(),
                "title": mgr_user.get("title", "") or mgr_info.get("jobTitle", ""),
                "department": mgr_user.get("department", "") or mgr_info.get("department", ""),
                "position": mgr_info.get("position", ""),
                "level": -level,
            })
            current_id = mgr_info.get("managerId", "")

        # Navigate down (direct reports)
        direct_reports = []
        if depth_down > 0:
            reports = await get_direct_reports(user_id)
            report_users = await asyncio.gather(
                *[get_user_name(r.get("userId", "")) for r in reports]
            ) if reports else []

            for report, ruser in zip(reports, report_users):
                direct_reports.append({
                    "userId": report.get("userId", ""),
                    "name": f"{ruser.get('firstName', '')} {ruser.get('lastName', '')}".strip(),
                    "title": ruser.get("title", "") or report.get("jobTitle", ""),
                    "department": ruser.get("department", "") or report.get("department", ""),
                    "position": report.get("position", ""),
                    "level": 1,
                })

    return {
        "center": center_node,
        "managers": list(reversed(managers)),
        "direct_reports": direct_reports,
        "total_levels": len(managers) + 1 + (1 if direct_reports else 0),
    }


@employee_mcp.tool
async def get_employee_history(
    user_id: Annotated[str, "The userId to retrieve history for"],
    history_type: Annotated[str, "Type of history: 'job', 'compensation', 'employment'"] = "job",
    limit: Annotated[int, "Maximum records to return (1-50)"] = 10,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get the history of changes for an employee.

    Retrieves effective-dated records ordered by date descending, showing
    the timeline of changes. Supports job (EmpJob), compensation
    (EmpCompensation), and employment (EmpEmployment) history.
    """
    api_host = resolve_api_host(data_center)

    entity_map = {
        "job": "EmpJob",
        "compensation": "EmpCompensation",
        "employment": "EmpEmployment",
    }

    entity = entity_map.get(history_type.lower())
    if not entity:
        return {
            "error": f"Invalid history_type '{history_type}'. Valid: {list(entity_map.keys())}",
        }

    # Use personIdExternal for PerPersonal, userId for others
    filter_field = "personIdExternal" if entity.startswith("Per") else "userId"

    params: dict[str, str] = {
        "$filter": f"{filter_field} eq '{user_id}'",
        "$top": str(min(limit, 50)),
        "$orderby": "startDate desc",
    }

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        result = await _sf_query(sf, api_host, token, entity, params)

    records = result.get("d", {}).get("results", [])
    return {
        "user_id": user_id,
        "history_type": history_type,
        "entity": entity,
        "count": len(records),
        "records": records,
    }


@employee_mcp.tool
async def compare_employees(
    user_ids: Annotated[list[str], "List of userIds to compare (2-5 employees)"],
    compare_fields: Annotated[Optional[list[str]], "Specific fields to compare. Default: job + personal fields"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Compare multiple employees side by side.

    Fetches profiles for all specified employees in parallel and returns
    a comparison matrix highlighting differences. Useful for auditing
    or verifying employee data consistency.
    """
    if len(user_ids) < 2:
        return {"error": "Need at least 2 userIds to compare"}
    if len(user_ids) > 5:
        return {"error": "Maximum 5 employees can be compared at once"}

    api_host = resolve_api_host(data_center)
    today = date.today().isoformat()

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        async def fetch_profile(uid: str) -> dict:
            """Fetch key data for one employee."""
            user_task = _sf_query(sf, api_host, token, "User", {
                "$filter": f"userId eq '{uid}'",
                "$select": "userId,firstName,lastName,email,title,department,division,location",
                "$top": "1",
            })
            job_filter = f"userId eq '{uid}'"
            date_filter = build_effective_date_filter("EmpJob", today)
            if date_filter:
                job_filter += f" and {date_filter}"
            job_task = _sf_query(sf, api_host, token, "EmpJob", {
                "$filter": job_filter,
                "$select": "userId,company,department,division,location,position,jobCode,managerId,emplStatus,employmentType,countryOfCompany",
                "$top": "1",
                "$orderby": "startDate desc",
            })

            user_result, job_result = await asyncio.gather(user_task, job_task)
            user_data = (user_result.get("d", {}).get("results", []) or [{}])[0] if user_result.get("d", {}).get("results") else {}
            job_data = (job_result.get("d", {}).get("results", []) or [{}])[0] if job_result.get("d", {}).get("results") else {}

            # Merge
            merged = {"userId": uid}
            merged.update(user_data)
            merged.update(job_data)
            return merged

        profiles = await asyncio.gather(*[fetch_profile(uid) for uid in user_ids])

    # Determine fields to compare
    if compare_fields:
        fields = compare_fields
    else:
        # Auto-detect: use all fields present in any profile
        all_keys: set[str] = set()
        for p in profiles:
            all_keys.update(p.keys())
        # Exclude metadata fields
        exclude = {"__metadata", "uri", "__deferred"}
        fields = sorted(all_keys - exclude)

    # Find differences
    differences = []
    for field_name in fields:
        values = [p.get(field_name) for p in profiles]
        if len(set(str(v) for v in values)) > 1:
            differences.append(field_name)

    return {
        "user_ids": user_ids,
        "fields_compared": fields,
        "differences": differences,
        "employees": profiles,
    }
