"""
MDF (Metadata Framework) tools for SAP SuccessFactors.

Provides tools to explore custom MDF objects, generate import templates,
and list all MDF objects configured in an instance.

All operations are read-only.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.metadata_parser import parse_metadata_xml, extract_entity_names

mdf_mcp = FastMCP(name="SF MDF Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)


async def _sf_query(sf, api_host, token, entity, params):
    async with _SF_SEMAPHORE:
        return await sf.query_odata(data_center=api_host, bearer_token=token, entity=entity, params=params)


# Common MDF prefixes — entities starting with these are typically standard SAP,
# while custom MDF objects start with "cust_"
_STANDARD_PREFIXES = (
    "Emp", "Per", "FO", "User", "WfRequest", "Position", "Picklist",
    "Rule", "RBP", "Background", "Badge", "Calibration", "Competency",
    "DevGoal", "Form", "Goal", "Job", "Learning", "Offer", "OnboardingEquipment",
    "Pay", "Photo", "Succession", "Talent", "Time", "Todo", "Advance",
    "Currency", "Country", "EmpCostDistribution", "HRISChangeLog",
)


@mdf_mcp.tool
async def get_mdf_object_definition(
    object_name: Annotated[str, "MDF object name / entity name (e.g., 'cust_MyObject', 'Position')"],
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Get complete metadata for an MDF object.

    Returns all fields, types, labels, editability flags, picklist associations,
    and navigation properties. Works for both custom (cust_*) and standard MDF objects.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=object_name)

    parsed = parse_metadata_xml(xml_text)
    entity_meta = parsed["entities"].get(object_name, {})

    if not entity_meta:
        available = list(parsed["entities"].keys())
        return {
            "object_name": object_name,
            "error": f"Object '{object_name}' not found",
            "available_in_response": available[:20],
        }

    properties = entity_meta.get("properties", {})
    keys = entity_meta.get("keys", [])
    nav_props = entity_meta.get("navigation_properties", [])

    # Categorize fields
    key_fields = []
    editable_fields = []
    readonly_fields = []
    picklist_fields = []

    for name, prop in sorted(properties.items()):
        field_info = {
            "name": name,
            "type": prop.get("type", ""),
            "label": prop.get("label", name),
            "required": prop.get("required", False),
            "creatable": prop.get("creatable", False),
            "updatable": prop.get("updatable", False),
        }
        if prop.get("sap_picklist"):
            field_info["picklist_id"] = prop["sap_picklist"]
            picklist_fields.append(field_info)

        if name in keys:
            key_fields.append(field_info)
        elif prop.get("creatable") or prop.get("updatable"):
            editable_fields.append(field_info)
        else:
            readonly_fields.append(field_info)

    is_custom = object_name.startswith("cust_")

    return {
        "object_name": object_name,
        "is_custom": is_custom,
        "total_fields": len(properties),
        "key_fields": key_fields,
        "editable_fields": editable_fields,
        "readonly_fields": readonly_fields,
        "picklist_fields": picklist_fields,
        "navigation_properties": [
            {"name": np["name"], "target": np.get("target_entity", "")}
            for np in nav_props
        ],
    }


@mdf_mcp.tool
async def generate_mdf_import_template(
    object_name: Annotated[str, "MDF object name (e.g., 'cust_MyObject')"],
    include_readonly: Annotated[bool, "Include read-only fields in template"] = False,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Generate an import template for an MDF object.

    Creates a CSV-ready template with key fields, required fields, and
    optionally all editable fields. Includes field type info as comments.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=object_name)

    parsed = parse_metadata_xml(xml_text)
    entity_meta = parsed["entities"].get(object_name, {})

    if not entity_meta:
        return {"error": f"Object '{object_name}' not found in metadata"}

    properties = entity_meta.get("properties", {})
    keys = entity_meta.get("keys", [])

    # Select fields for template
    template_fields = []
    for name, prop in sorted(properties.items()):
        is_key = name in keys
        creatable = prop.get("creatable", False)
        updatable = prop.get("updatable", False)

        if is_key or creatable or updatable or (include_readonly and not is_key):
            template_fields.append({
                "name": name,
                "type": prop.get("type", ""),
                "label": prop.get("label", name),
                "is_key": is_key,
                "required": prop.get("required", False) or is_key,
                "creatable": creatable,
                "updatable": updatable,
                "picklist_id": prop.get("sap_picklist", ""),
            })

    headers = [f["name"] for f in template_fields]
    csv_header = ",".join(headers)

    # Add a comment row with types
    type_row = ",".join(f.get("type", "") for f in template_fields)

    return {
        "object_name": object_name,
        "csv_header": csv_header,
        "type_reference": type_row,
        "fields": template_fields,
        "total_fields": len(template_fields),
        "key_fields": [f["name"] for f in template_fields if f["is_key"]],
        "required_fields": [f["name"] for f in template_fields if f["required"]],
    }


@mdf_mcp.tool
async def list_mdf_objects(
    category: Annotated[Optional[str], "Filter: 'custom' for cust_* objects, 'standard' for SAP standard, 'all' for everything"] = "custom",
    name_search: Annotated[Optional[str], "Search by object name (substring match)"] = None,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    List all MDF objects configured in the SF instance.

    Categories:
    - 'custom': Only cust_* objects (custom MDF)
    - 'standard': Only standard SAP MDF objects
    - 'all': Everything

    Many instances have 50+ custom MDF objects with unclear purposes.
    This tool helps inventory them.
    """
    api_host = resolve_api_host(data_center)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)
        xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=None)

    all_entities = extract_entity_names(xml_text)

    # Filter by category
    if category == "custom":
        entities = [e for e in all_entities if e.startswith("cust_")]
    elif category == "standard":
        entities = [e for e in all_entities if not e.startswith("cust_")]
    else:
        entities = all_entities

    # Filter by name search
    if name_search:
        search_lower = name_search.lower()
        entities = [e for e in entities if search_lower in e.lower()]

    return {
        "category": category,
        "name_search": name_search,
        "total_count": len(entities),
        "custom_count": sum(1 for e in entities if e.startswith("cust_")),
        "standard_count": sum(1 for e in entities if not e.startswith("cust_")),
        "entities": entities,
    }
