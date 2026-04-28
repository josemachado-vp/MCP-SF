"""Registry of MCP tools exposed to the Gemini agent.

Loads the same 52 tool functions registered in main.py, groups them by
the 15 categories defined in CLAUDE.md, and derives JSON Schemas for
Gemini function-calling.
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

# --- Imports mirror main.py ---
from tools.discovery import (
    get_entity_metadata, list_entities, get_picklist_values, query_odata,
)
from tools.rule_generation import validate_rule_fields, generate_rule_spec
from tools.rule_documentation import generate_rule_doc, generate_rule_test
from tools.employee import (
    search_employees, get_employee_profile, get_org_chart,
    get_employee_history, compare_employees,
)
from tools.organization import (
    get_org_structure, get_position_details, list_foundation_objects,
)
from tools.configuration import list_business_rules, get_permission_roles
from tools.data_import import (
    validate_import_template, generate_import_template, execute_upsert,
)
from tools.analytics import (
    get_headcount, get_compensation_analytics, simulate_rule_impact,
)
from tools.instance_compare import (
    compare_instance_config, compare_picklists,
    compare_business_rules, compare_foundation_objects,
)
from tools.audit import (
    audit_employee_data, find_data_anomalies, trace_rule_execution,
    check_permission_access, validate_effective_dating,
)
from tools.documentation import (
    generate_functional_spec, generate_cutover_checklist,
    generate_data_dictionary, generate_test_script,
)
from tools.migration import (
    validate_migration_file, generate_migration_sequence,
    reconcile_data, generate_purge_file,
)
from tools.mdf import (
    get_mdf_object_definition, generate_mdf_import_template, list_mdf_objects,
)
from tools.golive import run_go_live_checks, generate_reconciliation_report
from tools.country import (
    get_country_specific_fields, validate_country_compliance,
    generate_country_config_guide,
)
from tools.workbook_generator import (
    generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook,
)


CATEGORIES: dict[str, list[Callable]] = {
    "Discovery": [get_entity_metadata, list_entities, get_picklist_values, query_odata],
    "Business Rules": [validate_rule_fields, generate_rule_spec, generate_rule_doc, generate_rule_test],
    "Employee": [search_employees, get_employee_profile, get_org_chart, get_employee_history, compare_employees],
    "Organization": [get_org_structure, get_position_details, list_foundation_objects],
    "Configuration": [list_business_rules, get_permission_roles],
    "Data Import": [validate_import_template, generate_import_template, execute_upsert],
    "Analytics": [get_headcount, get_compensation_analytics, simulate_rule_impact],
    "Instance Comparison": [compare_instance_config, compare_picklists, compare_business_rules, compare_foundation_objects],
    "Audit & Troubleshooting": [audit_employee_data, find_data_anomalies, trace_rule_execution, check_permission_access, validate_effective_dating],
    "Documentation": [generate_functional_spec, generate_cutover_checklist, generate_data_dictionary, generate_test_script],
    "Migration": [validate_migration_file, generate_migration_sequence, reconcile_data, generate_purge_file],
    "MDF": [get_mdf_object_definition, generate_mdf_import_template, list_mdf_objects],
    "Go-Live": [run_go_live_checks, generate_reconciliation_report],
    "Country": [get_country_specific_fields, validate_country_compliance, generate_country_config_guide],
    "Workbook Generator": [generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook],
}

DESTRUCTIVE_TOOL_NAMES: set[str] = {"execute_upsert"}


_PRIMITIVE_MAP = {
    str: "string", int: "integer", float: "number", bool: "boolean",
}


def _python_type_to_schema(annotation: Any) -> dict[str, Any]:
    """Map a python type hint to a minimal JSON Schema fragment."""
    if annotation is inspect._empty or annotation is Any:
        return {"type": "string"}
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[X] / Union[X, None]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_schema(non_none[0])
        return {"type": "string"}

    if origin in (list, typing.List):
        item_schema = _python_type_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    if origin in (dict, typing.Dict):
        return {"type": "object"}

    if annotation in _PRIMITIVE_MAP:
        return {"type": _PRIMITIVE_MAP[annotation]}

    # Pydantic models / dataclasses → object
    return {"type": "object"}


def _build_schema(fn: Callable) -> dict[str, Any]:
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        properties[name] = _python_type_to_schema(param.annotation)
        if param.default is inspect._empty:
            required.append(name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _summary(doc: str | None) -> str:
    if not doc:
        return ""
    first = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
    return first[:500]


@dataclass
class ToolMeta:
    name: str
    category: str
    description: str
    parameters_schema: dict[str, Any]
    is_destructive: bool
    fn: Callable = field(repr=False)


@dataclass
class ToolRegistry:
    tools: list[ToolMeta]
    by_name: dict[str, ToolMeta]
    by_category: dict[str, list[ToolMeta]]


_registry_cache: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    tools: list[ToolMeta] = []
    by_category: dict[str, list[ToolMeta]] = {}

    for category, fns in CATEGORIES.items():
        bucket: list[ToolMeta] = []
        for fn in fns:
            meta = ToolMeta(
                name=fn.__name__,
                category=category,
                description=_summary(fn.__doc__),
                parameters_schema=_build_schema(fn),
                is_destructive=fn.__name__ in DESTRUCTIVE_TOOL_NAMES,
                fn=fn,
            )
            tools.append(meta)
            bucket.append(meta)
        by_category[category] = bucket

    by_name = {t.name: t for t in tools}
    _registry_cache = ToolRegistry(tools=tools, by_name=by_name, by_category=by_category)
    return _registry_cache
