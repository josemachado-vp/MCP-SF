"""
Discovery tools for SAP SuccessFactors OData API.

Provides foundational tools to explore entity metadata, picklist values,
and execute flexible OData queries against an SF instance.

Credentials are read from .env by default. Pass parameters to override.
"""

from __future__ import annotations

from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.metadata_parser import parse_metadata_xml, extract_entity_names
from helpers.credentials import resolve_api_host, get_bearer_token


discovery_mcp = FastMCP(name="SF Discovery Tools")


@discovery_mcp.tool
async def get_entity_metadata(
    entity_name: Annotated[str, "Name of the SF entity (e.g., 'EmpJob', 'User', 'FOCompany')"],
    data_center: Annotated[Optional[str], "API host override (e.g., 'api8preview.sapsf.com'). Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Retrieve structured metadata for a specific SAP SuccessFactors entity.

    Returns the entity's properties (fields), their types, whether they are
    editable, required, or picklist-based, plus navigation properties (relationships).

    Use this to understand what fields are available on an entity before building
    business rules that reference those fields.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(
            data_center=api_host,
            bearer_token=token,
            entity=entity_name,
        )

    parsed = parse_metadata_xml(xml_text)

    if entity_name in parsed["entities"]:
        entity_meta = parsed["entities"][entity_name]
        return {
            "entity": entity_name,
            "keys": entity_meta["keys"],
            "total_properties": len(entity_meta["properties"]),
            "properties": entity_meta["properties"],
            "navigation_properties": entity_meta["navigation_properties"],
            "related_entities": [
                np["target_entity"]
                for np in entity_meta["navigation_properties"]
                if np["target_entity"]
            ],
        }

    available = list(parsed["entities"].keys())
    return {
        "entity": entity_name,
        "error": f"Entity '{entity_name}' not found in metadata response",
        "available_entities_in_response": available[:50],
    }


@discovery_mcp.tool
async def list_entities(
    filter_prefix: Annotated[Optional[str], "Optional prefix to filter entities (e.g., 'Emp', 'FO', 'Per')"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    List all available OData entities in the SAP SuccessFactors instance.

    Returns entity set names from $metadata. Optionally filter by prefix
    (e.g., 'Emp' for employment entities, 'FO' for Foundation Objects,
    'Per' for person entities).

    Note: Fetching full metadata can be slow (5-30 seconds). Use filter_prefix
    or query a specific entity with get_entity_metadata instead.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(
            data_center=api_host,
            bearer_token=token,
            entity=None,
        )

    entity_names = extract_entity_names(xml_text)

    if filter_prefix:
        entity_names = [
            n for n in entity_names
            if n.lower().startswith(filter_prefix.lower())
        ]

    return {
        "total_count": len(entity_names),
        "filter_applied": filter_prefix or "none",
        "entities": entity_names,
    }


@discovery_mcp.tool
async def get_picklist_values(
    picklist_id: Annotated[str, "The picklist ID (e.g., 'payGroup', 'employeeClass', 'eventReason')"],
    status_filter: Annotated[Optional[str], "Filter by option status: 'A' for active, 'I' for inactive"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Get all options (values) for a specific picklist in SAP SuccessFactors.

    Picklists are dropdown/select fields. Returns the external code (API value),
    label (display text), and status for each option.

    Use this to validate that picklist values referenced in business rules
    actually exist in the target instance.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        result = await sf.get_picklist(
            data_center=api_host,
            bearer_token=token,
            picklist_id=picklist_id,
        )

    picklist_data = result.get("d", {}).get("results", [])
    options = []
    for pl in picklist_data:
        pl_options = pl.get("picklistOptions", {}).get("results", [])
        for opt in pl_options:
            entry = {
                "external_code": opt.get("externalCode", ""),
                "label": opt.get("optionValue", "") or opt.get("label", ""),
                "id": opt.get("id", ""),
                "status": opt.get("status", ""),
            }
            if status_filter is None or entry["status"] == status_filter:
                options.append(entry)

    return {
        "picklist_id": picklist_id,
        "total_options": len(options),
        "options": options,
    }


@discovery_mcp.tool
async def query_odata(
    entity: Annotated[str, "OData entity name (e.g., 'EmpJob', 'User', 'FOCompany')"],
    filter: Annotated[Optional[str], "OData $filter expression (e.g., \"userId eq 'admin'\")"] = None,
    select: Annotated[Optional[str], "Comma-separated fields to return (e.g., 'userId,firstName')"] = None,
    expand: Annotated[Optional[str], "Navigation properties to expand (e.g., 'companyNav')"] = None,
    top: Annotated[int, "Max records to return (1-1000)"] = 20,
    skip: Annotated[Optional[int], "Number of records to skip for pagination"] = None,
    orderby: Annotated[Optional[str], "Sort field(s) (e.g., 'lastName asc')"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "IAS password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Execute a flexible OData query against any SAP SuccessFactors entity.

    Supports filtering, field selection, navigation expansion, pagination, and sorting.

    Examples:
    - Active employees: entity='EmpEmployment', filter="endDate eq datetime'9999-12-31T00:00:00'"
    - Company details: entity='FOCompany', select='externalCode,name,country'
    - Job info with company: entity='EmpJob', expand='companyNav', top=5
    """
    api_host = resolve_api_host(data_center)

    params: dict[str, str] = {}
    if filter:
        params["$filter"] = filter
    if select:
        params["$select"] = select
    if expand:
        params["$expand"] = expand
    if top:
        params["$top"] = str(min(top, 1000))
    if skip is not None:
        params["$skip"] = str(skip)
    if orderby:
        params["$orderby"] = orderby

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        result = await sf.query_odata(
            data_center=api_host,
            bearer_token=token,
            entity=entity,
            params=params,
        )

    records = result.get("d", {}).get("results", [])
    return {
        "entity": entity,
        "count": len(records),
        "data": records,
    }
