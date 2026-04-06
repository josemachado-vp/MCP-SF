"""
XML parser for SAP SuccessFactors OData $metadata responses.

Parses EDMX/CSDL XML into structured dicts with entity types, properties,
SAP-specific annotations (sap:label, sap:creatable, sap:updatable, etc.),
navigation properties, and associations.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


# XML namespace constants for OData EDMX/CSDL
NAMESPACES = {
    "edmx": "http://schemas.microsoft.com/ado/2007/06/edmx",
    "edm": "http://schemas.microsoft.com/ado/2008/09/edm",
    "sap": "http://www.sap.com/Protocols/SAPData",
}


def parse_metadata_xml(xml_text: str) -> dict[str, Any]:
    """Parse $metadata XML and return structured dict.

    Returns:
        {
            "entities": {
                "EntityName": {
                    "keys": ["keyField1", ...],
                    "properties": [{"name", "type", "nullable", "label", ...}, ...],
                    "navigation_properties": [{"name", "relationship", "target_entity"}, ...]
                }
            },
            "entity_sets": ["EntitySet1", ...]
        }
    """
    root = ET.fromstring(xml_text)
    result: dict[str, Any] = {"entities": {}, "entity_sets": []}

    for schema in root.findall(".//edm:Schema", NAMESPACES):
        for entity_type in schema.findall("edm:EntityType", NAMESPACES):
            entity_name = entity_type.get("Name", "")
            result["entities"][entity_name] = _parse_entity_type(entity_type)

        for container in schema.findall("edm:EntityContainer", NAMESPACES):
            for entity_set in container.findall("edm:EntitySet", NAMESPACES):
                set_name = entity_set.get("Name", "")
                if set_name:
                    result["entity_sets"].append(set_name)

        associations = _parse_associations(schema)
        _resolve_navigation_targets(result["entities"], associations)

    return result


def extract_entity_names(xml_text: str) -> list[str]:
    """Quick extraction of just entity set names from metadata XML."""
    root = ET.fromstring(xml_text)
    names = []
    for entity_set in root.findall(".//edm:EntitySet", NAMESPACES):
        name = entity_set.get("Name", "")
        if name:
            names.append(name)
    return sorted(names)


def _parse_entity_type(entity_type_elem: ET.Element) -> dict[str, Any]:
    """Parse a single EntityType element."""
    keys: list[str] = []
    key_elem = entity_type_elem.find("edm:Key", NAMESPACES)
    if key_elem is not None:
        for prop_ref in key_elem.findall("edm:PropertyRef", NAMESPACES):
            keys.append(prop_ref.get("Name", ""))

    properties = [
        _parse_property(prop)
        for prop in entity_type_elem.findall("edm:Property", NAMESPACES)
    ]

    nav_properties = [
        {
            "name": nav.get("Name", ""),
            "relationship": nav.get("Relationship", ""),
            "target_entity": "",
        }
        for nav in entity_type_elem.findall("edm:NavigationProperty", NAMESPACES)
    ]

    return {
        "keys": keys,
        "properties": properties,
        "navigation_properties": nav_properties,
    }


def _parse_property(prop_elem: ET.Element) -> dict[str, Any]:
    """Parse a Property element including SAP-specific annotations."""
    sap_ns = NAMESPACES["sap"]

    def sap_attr(name: str) -> str | None:
        return prop_elem.get(f"{{{sap_ns}}}{name}")

    def sap_bool(name: str) -> bool:
        val = sap_attr(name)
        return val is not None and val.lower() == "true"

    return {
        "name": prop_elem.get("Name", ""),
        "type": prop_elem.get("Type", ""),
        "nullable": prop_elem.get("Nullable", "true").lower() == "true",
        "label": sap_attr("label") or "",
        "required": sap_bool("required"),
        "creatable": sap_bool("creatable"),
        "updatable": sap_bool("updatable"),
        "upsertable": sap_bool("upsertable"),
        "visible": sap_bool("visible"),
        "sortable": sap_bool("sortable"),
        "filterable": sap_bool("filterable"),
    }


def _parse_associations(schema_elem: ET.Element) -> dict[str, dict]:
    """Parse Association elements for navigation target resolution."""
    associations: dict[str, dict] = {}
    for assoc in schema_elem.findall("edm:Association", NAMESPACES):
        assoc_name = assoc.get("Name", "")
        ends = assoc.findall("edm:End", NAMESPACES)
        if len(ends) == 2:
            associations[assoc_name] = {
                "end1_type": ends[0].get("Type", ""),
                "end1_role": ends[0].get("Role", ""),
                "end2_type": ends[1].get("Type", ""),
                "end2_role": ends[1].get("Role", ""),
            }
    return associations


def _resolve_navigation_targets(
    entities: dict[str, dict], associations: dict[str, dict]
) -> None:
    """Resolve NavigationProperty target entities using Association data."""
    for entity_name, entity_info in entities.items():
        for nav_prop in entity_info["navigation_properties"]:
            relationship = nav_prop["relationship"]
            assoc_name = relationship.split(".")[-1] if "." in relationship else relationship
            if assoc_name in associations:
                assoc = associations[assoc_name]
                source_suffix = f".{entity_name}"
                if assoc["end1_type"].endswith(source_suffix):
                    target_type = assoc["end2_type"].split(".")[-1]
                else:
                    target_type = assoc["end1_type"].split(".")[-1]
                nav_prop["target_entity"] = target_type
