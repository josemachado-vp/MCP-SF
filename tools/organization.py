"""
Organization tools for SAP SuccessFactors.

Provides tools to explore organizational structure, positions,
and Foundation Objects.

All queries are read-only OData GET operations.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token

organization_mcp = FastMCP(name="SF Organization Tools")

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


# Mapping from level keywords to FO entities
_ORG_LEVEL_ENTITIES = {
    "company": "FOCompany",
    "division": "FODivision",
    "department": "FODepartment",
    "business_unit": "FOBusinessUnit",
    "cost_center": "FOCostCenter",
    "location": "FOLocation",
    "job_code": "FOJobCode",
    "pay_grade": "FOPayGrade",
}


@organization_mcp.tool
async def get_org_structure(
    level: Annotated[str, "Organizational level to query: 'company', 'division', 'department', 'business_unit', 'cost_center', 'location', 'job_code', 'pay_grade'"],
    parent_code: Annotated[Optional[str], "Filter by parent code (e.g., parent department or company code)"] = None,
    include_headcount: Annotated[bool, "Include employee headcount per unit (requires additional API calls)"] = False,
    active_only: Annotated[bool, "Only return active records"] = True,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get organizational structure at a specific level.

    Queries Foundation Object entities (FOCompany, FODepartment, etc.) to show
    the organizational hierarchy. Can optionally include headcount per unit
    by cross-referencing with EmpJob.

    Levels: company, division, department, business_unit, cost_center, location,
    job_code, pay_grade.
    """
    level_lower = level.lower().replace(" ", "_")
    entity = _ORG_LEVEL_ENTITIES.get(level_lower)
    if not entity:
        return {
            "error": f"Invalid level '{level}'. Valid: {list(_ORG_LEVEL_ENTITIES.keys())}",
        }

    api_host = resolve_api_host(data_center)

    filters = []
    if active_only:
        filters.append("status eq 'A'")
    if parent_code:
        # Different FOs use different parent field names
        if level_lower == "department":
            filters.append(f"parent eq '{parent_code}'")
        elif level_lower in ("division", "cost_center", "location"):
            filters.append(f"company eq '{parent_code}'" if level_lower != "location" else f"companyFlx eq '{parent_code}'")

    params: dict[str, str] = {"$top": "200"}
    if filters:
        params["$filter"] = " and ".join(filters)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        result = await _sf_query(sf, api_host, token, entity, params)

        records = result.get("d", {}).get("results", [])

        # Optionally add headcount
        if include_headcount and records:
            field_map = {
                "company": "company",
                "division": "division",
                "department": "department",
                "location": "location",
                "cost_center": "costCenter",
            }
            job_field = field_map.get(level_lower)
            if job_field:
                headcount_map: dict[str, int] = {}
                # Fetch active employee counts
                emp_result = await _sf_query(sf, api_host, token, "EmpJob", {
                    "$filter": "emplStatus eq 'A'",
                    "$select": f"userId,{job_field}",
                    "$top": "5000",
                    "$orderby": "startDate desc",
                })
                emp_records = emp_result.get("d", {}).get("results", [])
                # Count unique employees per org unit
                seen_users: dict[str, str] = {}
                for emp in emp_records:
                    uid = emp.get("userId", "")
                    code = emp.get(job_field, "")
                    if uid and code and uid not in seen_users:
                        seen_users[uid] = code
                        headcount_map[code] = headcount_map.get(code, 0) + 1

                for record in records:
                    ext_code = record.get("externalCode", "")
                    record["_headcount"] = headcount_map.get(ext_code, 0)

    return {
        "level": level,
        "entity": entity,
        "count": len(records),
        "include_headcount": include_headcount,
        "data": records,
    }


@organization_mcp.tool
async def get_position_details(
    position_code: Annotated[Optional[str], "Specific position code to retrieve"] = None,
    department: Annotated[Optional[str], "Filter positions by department code"] = None,
    vacant_only: Annotated[bool, "Only return vacant positions"] = False,
    max_results: Annotated[int, "Maximum results (1-200)"] = 50,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get position details from Position Management.

    Retrieve specific positions or filter by department/vacancy status.
    Returns position code, name, department, job code, incumbent, and vacancy status.
    """
    api_host = resolve_api_host(data_center)

    filters = []
    if position_code:
        filters.append(f"code eq '{position_code}'")
    if department:
        filters.append(f"department eq '{department}'")
    if vacant_only:
        filters.append("vacant eq true")

    params: dict[str, str] = {"$top": str(min(max_results, 200))}
    if filters:
        params["$filter"] = " and ".join(filters)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        result = await _sf_query(sf, api_host, token, "Position", params)

    records = result.get("d", {}).get("results", [])
    return {
        "entity": "Position",
        "filters": {
            "position_code": position_code,
            "department": department,
            "vacant_only": vacant_only,
        },
        "count": len(records),
        "data": records,
    }


@organization_mcp.tool
async def list_foundation_objects(
    fo_type: Annotated[str, "Foundation Object type: 'company', 'division', 'department', 'business_unit', 'cost_center', 'location', 'job_code', 'pay_grade', or direct entity name like 'FOCompany'"],
    active_only: Annotated[bool, "Only return active records"] = True,
    filter_expr: Annotated[Optional[str], "Additional OData $filter expression"] = None,
    select: Annotated[Optional[str], "Comma-separated fields to return"] = None,
    max_results: Annotated[int, "Maximum results (1-500)"] = 100,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    List Foundation Objects of any type.

    A flexible tool to query any Foundation Object entity. Use friendly names
    like 'company', 'department', 'location' or direct entity names like 'FOCompany'.

    Foundation Objects are the reference/master data that define the organizational
    structure in SuccessFactors.
    """
    # Resolve entity name
    fo_lower = fo_type.lower().replace(" ", "_")
    entity = _ORG_LEVEL_ENTITIES.get(fo_lower, fo_type)

    api_host = resolve_api_host(data_center)

    filters = []
    if active_only:
        filters.append("status eq 'A'")
    if filter_expr:
        filters.append(filter_expr)

    params: dict[str, str] = {"$top": str(min(max_results, 500))}
    if filters:
        params["$filter"] = " and ".join(filters)
    if select:
        params["$select"] = select

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        result = await _sf_query(sf, api_host, token, entity, params)

    records = result.get("d", {}).get("results", [])
    return {
        "fo_type": fo_type,
        "entity": entity,
        "count": len(records),
        "data": records,
    }
