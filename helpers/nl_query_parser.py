"""
Natural language → OData filter parser.

Pattern-matching based (no LLM). Converts human-readable queries like
"employees in department 40000013" into OData $filter expressions.

Supported patterns:
  - Name search: "John", "John Smith", "Smith"
  - Department: "department 40000013", "dept HR"
  - Country: "country COL", "employees in Colombia"
  - Status: "active employees", "terminated"
  - Manager: "reports to admin", "manager admin"
  - Location: "location NYC"
  - User ID: "user admin", "userId 12345"
  - Company: "company 1000"
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from helpers.odata_utils import escape_odata_string, validate_field_name


@dataclass
class ParsedQuery:
    """Result of parsing a natural language query."""

    entity: str
    filters: list[str] = field(default_factory=list)
    select: Optional[str] = None
    expand: Optional[str] = None
    orderby: Optional[str] = None
    top: int = 20
    interpretation: str = ""


# Load entity mapping at module level
_MAPPING_PATH = Path(__file__).parent.parent / "knowledge" / "entity_mapping.json"


def _load_mapping() -> dict:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_country_code(value: str, mapping: dict) -> str:
    """Resolve country name to ISO code."""
    countries = mapping.get("country_codes", {})
    lower = value.lower()
    if lower in countries:
        return countries[lower]
    # Already a code (3 letters uppercase)?
    if len(value) == 3 and value.isalpha():
        return value.upper()
    return value


def _get_status_code(value: str, mapping: dict) -> str:
    """Resolve status description to emplStatus code.

    Note: The returned value may be raw user input if no mapping is found.
    Callers must call escape_odata_string() before embedding in OData filters.
    """
    statuses = mapping.get("status_codes", {})
    lower = value.lower()
    if lower in statuses:
        return statuses[lower]["emplStatus"]
    # Single letter code
    if len(value) == 1 and value.isalpha():
        return value.upper()
    return value


# Regex patterns for NL extraction (order matters — more specific first)
_PATTERNS: list[tuple[str, str, str]] = [
    # "department X" or "dept X"
    (r"(?:department|dept)\s+([^\s,]+)", "department", "EmpJob"),
    # "country X" or "in Colombia"
    (r"(?:country|pais|país)\s+([^\s,]+)", "country", "EmpJob"),
    # "company X"
    (r"(?:company|empresa)\s+([^\s,]+)", "company", "EmpJob"),
    # "location X"
    (r"(?:location|ubicación|ubicacion|office|site)\s+([^\s,]+)", "location", "EmpJob"),
    # "manager X" or "reports to X"
    (r"(?:manager|reports?\s+to|jefe)\s+([^\s,]+)", "manager", "EmpJob"),
    # "userId X" or "user X"
    (r"(?:userId|user\s*id|user)\s+([^\s,]+)", "userid", "User"),
    # "position X"
    (r"(?:position|posición|posicion)\s+([^\s,]+)", "position", "EmpJob"),
]

# Status keywords
_STATUS_KEYWORDS = {
    "active": "A",
    "activo": "A",
    "activos": "A",
    "activas": "A",
    "terminated": "T",
    "terminado": "T",
    "terminados": "T",
    "inactive": "U",
    "inactivo": "U",
    "inactivos": "U",
    "retired": "R",
    "retirado": "R",
    "retirados": "R",
}


def parse_nl_query(
    query: str,
    search_fields: Optional[list[str]] = None,
    include_inactive: bool = False,
    max_results: int = 20,
) -> ParsedQuery:
    """Parse a natural language query into OData parameters.

    Args:
        query: Natural language search string
        search_fields: Optional list of fields to restrict name search to
        include_inactive: If False, auto-adds active employee filter
        max_results: Maximum records to return

    Returns:
        ParsedQuery with entity, filters, and interpretation
    """
    mapping = _load_mapping()
    query_lower = query.strip().lower()
    filters: list[str] = []
    entity = "User"
    interpretations: list[str] = []

    # Check for status keywords
    found_status = False
    for keyword, code in _STATUS_KEYWORDS.items():
        if keyword in query_lower:
            found_status = True
            if code != "A" or "active" in query_lower or "activo" in query_lower:
                filters.append(f"emplStatus eq '{code}'")
                interpretations.append(f"status={keyword}")
                entity = "EmpJob"
            break

    # Apply regex patterns
    remaining_query = query
    for pattern, ptype, pentity in _PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            captured = match.group(1)
            # Only strip a symmetric surrounding quote pair (e.g. 'value' or "value"),
            # not bare trailing/leading quotes which may be injection characters.
            if (
                len(captured) >= 2
                and captured[0] == captured[-1]
                and captured[0] in ("'", '"')
            ):
                captured = captured[1:-1]
            raw_value = captured
            value = escape_odata_string(raw_value)
            entity = pentity

            if ptype == "department":
                filters.append(f"department eq '{value}'")
                interpretations.append(f"department={raw_value}")
            elif ptype == "country":
                code = _get_country_code(raw_value, mapping)
                filters.append(f"countryOfCompany eq '{escape_odata_string(code)}'")
                interpretations.append(f"country={code}")
            elif ptype == "company":
                filters.append(f"company eq '{value}'")
                interpretations.append(f"company={raw_value}")
            elif ptype == "location":
                filters.append(f"location eq '{value}'")
                interpretations.append(f"location={raw_value}")
            elif ptype == "manager":
                filters.append(f"managerId eq '{value}'")
                interpretations.append(f"manager={raw_value}")
            elif ptype == "userid":
                filters.append(f"userId eq '{value}'")
                entity = "User"
                interpretations.append(f"userId={raw_value}")
            elif ptype == "position":
                filters.append(f"position eq '{value}'")
                interpretations.append(f"position={raw_value}")

            remaining_query = remaining_query[:match.start()] + remaining_query[match.end():]

    # Check for country names in remaining text (e.g., "employees in Colombia")
    for country_name, code in mapping.get("country_codes", {}).items():
        if country_name in query_lower and f"country={code}" not in " ".join(interpretations):
            filters.append(f"countryOfCompany eq '{escape_odata_string(code)}'")
            interpretations.append(f"country={code} (from '{country_name}')")
            entity = "EmpJob"
            remaining_query = re.sub(
                re.escape(country_name), "", remaining_query, flags=re.IGNORECASE
            )
            break

    # Check if remaining text looks like a name search
    remaining_clean = re.sub(
        r"\b(employees?|empleados?|workers?|people|persons?|staff|in|the|all|show|find|search|get|list|buscar|mostrar|listar)\b",
        "",
        remaining_query,
        flags=re.IGNORECASE,
    ).strip(" ,.")

    if remaining_clean and not remaining_clean.isdigit():
        parts = remaining_clean.split()
        name_filters = []
        if search_fields:
            for sf in search_fields:
                try:
                    safe_sf = validate_field_name(sf)
                except ValueError:
                    continue  # skip invalid field names silently
                for part in parts:
                    safe_part = escape_odata_string(part)
                    name_filters.append(f"substringof('{safe_part}', {safe_sf})")
        else:
            for part in parts:
                if len(part) >= 2:
                    safe_part = escape_odata_string(part)
                    name_filters.append(
                        f"(substringof('{safe_part}', firstName) or substringof('{safe_part}', lastName))"
                    )
        if name_filters:
            if entity == "EmpJob":
                pass
            else:
                entity = "User"
            filters.extend(name_filters)
            interpretations.append(f"name contains '{remaining_clean}'")

    # Default: add active filter if not searching inactive
    if not include_inactive and not found_status:
        if entity == "EmpJob":
            filters.append("emplStatus eq 'A'")
            interpretations.append("active only (default)")

    # Build select based on entity
    entities_map = {}
    for cat in mapping["categories"].values():
        entities_map.update(cat.get("entities", {}))

    select = None
    if entity in entities_map:
        select = entities_map[entity].get("common_select")

    filter_str = " and ".join(filters) if filters else None

    return ParsedQuery(
        entity=entity,
        filters=filters,
        select=select,
        top=max_results,
        interpretation="; ".join(interpretations) if interpretations else "general search",
    )


def build_effective_date_filter(entity: str, as_of_date: str) -> str:
    """Build an effective-date filter for time-sliced entities.

    Args:
        entity: Entity name (e.g., 'EmpJob')
        as_of_date: Date string in YYYY-MM-DD format

    Returns:
        OData filter string for effective dating
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", as_of_date):
        raise ValueError(
            f"Invalid date format: '{as_of_date}'. Expected YYYY-MM-DD."
        )
    mapping = _load_mapping()
    entities_map = {}
    for cat in mapping["categories"].values():
        entities_map.update(cat.get("entities", {}))

    entity_info = entities_map.get(entity, {})
    template = entity_info.get("date_filter_template")
    if template:
        return template.format(date=as_of_date)

    # Generic fallback for effective-dated entities
    if entity_info.get("effective_dated"):
        return (
            f"startDate le datetime'{as_of_date}T00:00:00' "
            f"and (endDate ge datetime'{as_of_date}T00:00:00' "
            f"or endDate eq datetime'9999-12-31T00:00:00')"
        )

    return ""


def resolve_entity_for_query(query_type: str) -> str:
    """Resolve a query type keyword to an OData entity name."""
    mapping = _load_mapping()
    query_lower = query_type.lower()

    for cat in mapping["categories"].values():
        for entity_name, entity_info in cat.get("entities", {}).items():
            hints = entity_info.get("nl_hints", [])
            if query_lower in hints or query_lower == entity_name.lower():
                return entity_name

    return query_type
