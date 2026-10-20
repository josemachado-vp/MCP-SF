"""
Configuration tools for SAP SuccessFactors.

Provides tools to explore business rules and permission roles
configured in the SF instance.

All queries are read-only OData GET operations.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token

configuration_mcp = FastMCP(name="SF Configuration Tools")

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


@configuration_mcp.tool
async def list_business_rules(
    scenario_filter: Annotated[Optional[str], "Filter by rule scenario (e.g., 'Rules for Employee Central')"] = None,
    base_object_filter: Annotated[Optional[str], "Filter by base object (e.g., 'JobInformationModel')"] = None,
    name_search: Annotated[Optional[str], "Search rules by name (substring match)"] = None,
    max_results: Annotated[int, "Maximum results (1-200)"] = 50,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    List business rules configured in the SAP SuccessFactors instance.

    Queries the RuleHeaderBean entity to show configured rules. Filter by
    scenario, base object, or search by name. Useful to understand what
    rules are already in place before creating new ones.
    """
    api_host = resolve_api_host(data_center)

    filters = []
    if scenario_filter:
        filters.append(f"ruleScenario eq '{scenario_filter}'")
    if base_object_filter:
        filters.append(f"baseObject eq '{base_object_filter}'")
    if name_search:
        filters.append(f"substringof('{name_search}', ruleName)")

    params: dict[str, str] = {"$top": str(min(max_results, 200))}
    if filters:
        params["$filter"] = " and ".join(filters)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        result = await _sf_query(sf, api_host, token, "RuleHeaderBean", params)

    records = result.get("d", {}).get("results", [])
    return {
        "entity": "RuleHeaderBean",
        "filters": {
            "scenario": scenario_filter,
            "base_object": base_object_filter,
            "name_search": name_search,
        },
        "count": len(records),
        "data": records,
    }


@configuration_mcp.tool
async def get_permission_roles(
    role_name: Annotated[Optional[str], "Search by role name (substring match)"] = None,
    role_type: Annotated[str, "Type of role: 'rbp' for RBP roles, 'dynamic' for dynamic roles, 'all' for both"] = "all",
    max_results: Annotated[int, "Maximum results per type (1-100)"] = 50,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    List permission roles configured in the SAP SuccessFactors instance.

    Queries RBPRole (Role-Based Permissions) and/or FODynamicRole entities.
    Useful for understanding the security model and role assignments.
    """
    api_host = resolve_api_host(data_center)

    results: dict = {"role_type_queried": role_type}

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)

        tasks = {}

        if role_type in ("rbp", "all"):
            rbp_params: dict[str, str] = {"$top": str(min(max_results, 100))}
            if role_name:
                rbp_params["$filter"] = f"substringof('{role_name}', roleName)"
            tasks["rbp_roles"] = _sf_query(sf, api_host, token, "RBPRole", rbp_params)

        if role_type in ("dynamic", "all"):
            dyn_params: dict[str, str] = {"$top": str(min(max_results, 100))}
            if role_name:
                dyn_params["$filter"] = f"substringof('{role_name}', dynamicRoleName)"
            tasks["dynamic_roles"] = _sf_query(sf, api_host, token, "FODynamicRole", dyn_params)

        keys = list(tasks.keys())
        query_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for key, qr in zip(keys, query_results):
            if isinstance(qr, Exception):
                results[key] = {"error": str(qr), "count": 0, "data": []}
            else:
                records = qr.get("d", {}).get("results", [])
                results[key] = {"count": len(records), "data": records}

    return results
