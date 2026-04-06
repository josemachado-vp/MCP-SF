"""
Business Rules generation tools.

validate_rule_fields: Validates fields, entities, and picklist values against a live SF instance.
generate_rule_spec: Generates a complete rule specification from a natural language requirement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.metadata_parser import parse_metadata_xml
from helpers.credentials import resolve_api_host, get_bearer_token
from models.rule_spec import (
    ActionType,
    ConditionExpression,
    ConditionOperator,
    EventType,
    ExecutionNotes,
    RuleAction,
    RuleCondition,
    RuleSpec,
)
from models.field_validation import FieldValidationResult, ValidationReport


rule_generation_mcp = FastMCP(name="SF Rule Generation Tools")

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _load_knowledge(filename: str) -> dict:
    """Load a knowledge base JSON file."""
    filepath = KNOWLEDGE_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------- Tool 5: validate_rule_fields ----------


@rule_generation_mcp.tool
async def validate_rule_fields(
    fields_to_validate: Annotated[
        list[dict],
        "List of fields to validate. Each dict: {'field': str, 'entity': str, 'values': [optional list of picklist values]}"
    ],
    base_object: Annotated[Optional[str], "Base object for context (e.g., 'JobInformationModel')"] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "Username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "Password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Validate that fields, entities, and picklist values referenced in a proposed
    business rule actually exist in the SAP SuccessFactors instance.

    For each field:
    1. Verifies the entity exists in $metadata
    2. Verifies the field exists on that entity
    3. Checks the field type (string, date, picklist, number)
    4. If picklist values are provided, verifies they exist
    5. Checks if the field is editable (creatable or updatable)

    Example fields_to_validate:
    [
        {"field": "payGroup", "entity": "EmpJob", "values": ["PG_PE_FT", "PG_PE_PT"]},
        {"field": "employeeClass", "entity": "EmpJob", "values": ["FT", "PT"]},
        {"field": "countryOfCompany", "entity": "EmpJob"}
    ]
    """
    api_host = resolve_api_host(data_center)

    validations: list[FieldValidationResult] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Group fields by entity to minimize API calls
    entities_needed = {f.get("entity", "") for f in fields_to_validate if f.get("entity")}

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        # Fetch metadata for each unique entity
        entity_meta_cache: dict[str, dict] = {}
        for entity_name in entities_needed:
            try:
                xml_text = await sf.get_metadata(
                    data_center=api_host,
                    bearer_token=token,
                    entity=entity_name,
                )
                parsed = parse_metadata_xml(xml_text)
                entity_meta_cache[entity_name] = parsed.get("entities", {}).get(entity_name, {})
            except Exception as e:
                errors.append(f"Could not fetch metadata for entity '{entity_name}': {e}")
                entity_meta_cache[entity_name] = {}

        # Validate each field
        for field_info in fields_to_validate:
            field_name = field_info.get("field", "")
            entity_name = field_info.get("entity", "")
            values_to_check = field_info.get("values", [])

            result = FieldValidationResult(field=field_name, entity=entity_name)

            # Check entity metadata exists
            entity_meta = entity_meta_cache.get(entity_name, {})
            if not entity_meta:
                result.notes = f"Entity '{entity_name}' not found or metadata unavailable"
                errors.append(f"Entity '{entity_name}' for field '{field_name}' not found")
                validations.append(result)
                continue

            # Find the field in entity properties
            properties = entity_meta.get("properties", [])
            field_prop = next((p for p in properties if p["name"] == field_name), None)

            if not field_prop:
                result.exists = False
                result.notes = f"Field '{field_name}' not found on entity '{entity_name}'"
                errors.append(f"Field '{field_name}' does not exist on entity '{entity_name}'")
                validations.append(result)
                continue

            # Populate field details
            result.exists = True
            result.type = field_prop.get("type", "")
            result.label = field_prop.get("label", "")
            result.editable = field_prop.get("creatable", False) or field_prop.get("updatable", False)
            result.required = field_prop.get("required", False)

            if not result.editable:
                warnings.append(f"Field '{field_name}' on '{entity_name}' is read-only")

            # Validate picklist values if provided
            if values_to_check:
                result.is_picklist = True
                try:
                    picklist_result = await sf.get_picklist(
                        data_center=api_host,
                        bearer_token=token,
                        picklist_id=field_name,
                    )
                    valid_codes: set[str] = set()
                    for pl in picklist_result.get("d", {}).get("results", []):
                        for opt in pl.get("picklistOptions", {}).get("results", []):
                            valid_codes.add(opt.get("externalCode", ""))

                    invalid = [v for v in values_to_check if v not in valid_codes]
                    result.values_valid = len(invalid) == 0
                    result.invalid_values = invalid
                    if invalid:
                        errors.append(
                            f"Invalid picklist values for '{field_name}': {invalid}. "
                            f"Valid values include: {sorted(list(valid_codes))[:20]}"
                        )
                except Exception as e:
                    warnings.append(f"Could not validate picklist for '{field_name}': {e}")

            validations.append(result)

    report = ValidationReport(
        valid=len(errors) == 0,
        field_validations=validations,
        errors=errors,
        warnings=warnings,
    )
    return report.model_dump()


# ---------- Tool 6: generate_rule_spec ----------


@rule_generation_mcp.tool
async def generate_rule_spec(
    requirement: Annotated[str, "Natural language description of the business rule requirement"],
    rule_scenario: Annotated[str, "Rule scenario (e.g., 'Rules for Employee Central', 'Event Reason Derivation')"],
    base_object: Annotated[str, "Base object (e.g., 'JobInformationModel', 'CompInfoModel')"],
    event_type: Annotated[str, "Event type: 'onSave', 'onChange', 'onInit', or 'validate'"],
    rule_name: Annotated[Optional[str], "Custom rule name. Auto-generated if not provided."] = None,
    country_scope: Annotated[Optional[list[str]], "Country codes the rule applies to (e.g., ['PE', 'CO'])"] = None,
    conditions_hint: Annotated[
        Optional[list[dict]],
        "Structured conditions if known. Each dict: {'field', 'entity', 'operator', 'value', 'action_field', 'action_value', 'action_entity'}"
    ] = None,
    data_center: Annotated[Optional[str], "API host override. Uses .env default if omitted."] = None,
    auth_user_id: Annotated[Optional[str], "Username override. Uses .env default if omitted."] = None,
    auth_password: Annotated[Optional[str], "Password override. Uses .env default if omitted."] = None,
) -> dict:
    """
    Generate a complete Business Rule specification from a natural language requirement.

    This tool:
    1. Queries the SF instance metadata to identify relevant fields
    2. Validates all referenced fields and picklist values exist
    3. Builds IF/THEN/ELSE condition logic
    4. Generates naming, execution notes, and best practice recommendations

    The output can be passed to generate_rule_doc (documentation) and
    generate_rule_test (test cases).

    Example requirement:
    "When saving Job Information, if the employee's country is Peru and employee
    class is Full-Time, set pay group to PG_PE_FT. If Part-Time, set to PG_PE_PT."
    """
    api_host = resolve_api_host(data_center)

    # Load knowledge base
    base_objects_kb = _load_knowledge("base_objects.json")
    event_types_kb = _load_knowledge("event_types.json")
    best_practices_kb = _load_knowledge("best_practices.json")
    scenarios_kb = _load_knowledge("rule_scenarios.json")

    # Resolve primary entity from base object
    primary_entity = _resolve_primary_entity(base_object, base_objects_kb)

    # Fetch entity metadata
    entity_meta: dict = {}
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)
        try:
            xml_text = await sf.get_metadata(
                data_center=api_host,
                bearer_token=token,
                entity=primary_entity,
            )
            parsed = parse_metadata_xml(xml_text)
            entity_meta = parsed.get("entities", {}).get(primary_entity, {})
        except Exception as e:
            entity_meta = {}

        # Build conditions from hint
        conditions: list[RuleCondition] = []
        fields_referenced: set[str] = set()

        if conditions_hint:
            for i, hint in enumerate(conditions_hint, 1):
                action = None
                if hint.get("action_field"):
                    action = RuleAction(
                        type=ActionType.SET_FIELD,
                        target_field=hint["action_field"],
                        target_entity=hint.get("action_entity", primary_entity),
                        value=hint.get("action_value", ""),
                        value_label=hint.get("action_value_label", ""),
                    )

                condition = RuleCondition(
                    sequence=i,
                    type="IF" if i == 1 else "ELSE_IF",
                    expression=ConditionExpression(
                        field=hint.get("field", ""),
                        entity=hint.get("entity", primary_entity),
                        operator=ConditionOperator(hint.get("operator", "equals")),
                        value=hint.get("value", ""),
                        value_label=hint.get("value_label", ""),
                    ),
                    action=action,
                    nested_conditions=[
                        RuleCondition(
                            sequence=j + 1,
                            type="AND_IF",
                            expression=ConditionExpression(
                                field=nc.get("field", ""),
                                entity=nc.get("entity", primary_entity),
                                operator=ConditionOperator(nc.get("operator", "equals")),
                                value=nc.get("value", ""),
                            ),
                            action=RuleAction(
                                type=ActionType.SET_FIELD,
                                target_field=nc.get("action_field", ""),
                                target_entity=nc.get("action_entity", primary_entity),
                                value=nc.get("action_value", ""),
                                value_label=nc.get("action_value_label", ""),
                            ) if nc.get("action_field") else None,
                        )
                        for j, nc in enumerate(hint.get("nested", []))
                    ],
                )
                conditions.append(condition)

                fields_referenced.add(hint.get("field", ""))
                if hint.get("action_field"):
                    fields_referenced.add(hint["action_field"])
                for nc in hint.get("nested", []):
                    fields_referenced.add(nc.get("field", ""))
                    if nc.get("action_field"):
                        fields_referenced.add(nc["action_field"])

        # Validate referenced fields against metadata
        validation_result = None
        if fields_referenced and entity_meta:
            validation_result = _validate_fields_against_meta(
                fields_referenced, primary_entity, entity_meta
            )

    # Generate rule name
    if not rule_name:
        rule_name = _generate_rule_name(requirement, country_scope)

    # Build execution notes
    execution_notes = _build_execution_notes(event_type, event_types_kb)

    # Resolve HRIS element
    hris_element = _resolve_hris_element(base_object, base_objects_kb)

    # Assemble spec
    spec = RuleSpec(
        rule_name=rule_name,
        rule_id=rule_name.lower().replace(" ", "_").replace("-", "_"),
        scenario=rule_scenario,
        base_object=base_object,
        event_type=EventType(event_type),
        hris_element_assignment=hris_element,
        description=requirement,
        country_scope=country_scope or [],
        conditions=conditions,
        execution_notes=execution_notes,
    )

    result = spec.model_dump()
    result["validation_result"] = validation_result
    result["entity_metadata_summary"] = {
        "entity": primary_entity,
        "total_properties": len(entity_meta.get("properties", [])),
        "available_fields": [
            p["name"] for p in entity_meta.get("properties", [])
        ][:30],
    }
    result["knowledge_context"] = {
        "scenario_info": _find_scenario_info(rule_scenario, scenarios_kb),
        "event_type_info": _find_event_type_info(event_type, event_types_kb),
        "applicable_best_practices": [
            bp for bp in best_practices_kb.get("best_practices", [])
            if bp.get("severity") in ("critical", "important")
        ],
    }

    return result


# ---------- Internal helpers ----------


def _resolve_primary_entity(base_object: str, kb: dict) -> str:
    """Map base object to its primary OData entity."""
    for bo in kb.get("base_objects", []):
        if bo["id"] == base_object:
            return bo["primary_entity"]
    fallback = {
        "JobInformationModel": "EmpJob",
        "CompInfoModel": "EmpCompensation",
        "PersonalInfoModel": "PerPersonal",
        "EmploymentInfoModel": "EmpEmployment",
    }
    return fallback.get(base_object, base_object)


def _generate_rule_name(requirement: str, country_scope: Optional[list[str]]) -> str:
    """Generate a rule name from the requirement."""
    words = requirement.lower().split()
    action_keywords = ["derive", "set", "validate", "default", "calculate", "trigger"]
    action = "BR"
    for kw in action_keywords:
        if kw in words:
            action = f"BR_{kw.capitalize()}"
            break

    # Try to extract a target field from common patterns
    target = ""
    for keyword in ["pay group", "paygroup", "cost center", "department", "location", "event reason"]:
        if keyword in requirement.lower():
            target = "_" + keyword.replace(" ", "").title()
            break

    scope = ""
    if country_scope:
        scope = f"_{'_'.join(country_scope)}"

    return f"{action}{target}{scope}"


def _build_execution_notes(event_type: str, event_types_kb: dict) -> ExecutionNotes:
    """Build execution notes from knowledge base."""
    notes = ExecutionNotes()

    for et in event_types_kb.get("event_types", []):
        if et["id"] == event_type:
            notes.order_recommendation = et.get("notes", "")
            break

    notes.edge_cases = [
        "Employees without a company assigned may not be processed",
        "New hires with incomplete data may skip certain conditions",
        "Rehires may have residual data from previous employment",
    ]

    return notes


def _resolve_hris_element(base_object: str, kb: dict) -> str:
    """Determine the HRIS element for the base object."""
    for bo in kb.get("base_objects", []):
        if bo["id"] == base_object:
            elements = bo.get("hris_elements", [])
            return elements[0] if elements else ""
    return ""


def _find_scenario_info(scenario: str, kb: dict) -> dict:
    """Find scenario info from knowledge base."""
    for s in kb.get("scenarios", []):
        if s.get("name") == scenario or s.get("id") == scenario:
            return s
    return {"name": scenario, "description": "Custom scenario"}


def _find_event_type_info(event_type: str, kb: dict) -> dict:
    """Find event type info from knowledge base."""
    for et in kb.get("event_types", []):
        if et["id"] == event_type:
            return et
    return {"id": event_type, "description": "Unknown event type"}


def _validate_fields_against_meta(
    fields: set[str], entity_name: str, entity_meta: dict
) -> dict:
    """Quick validation of fields against cached metadata."""
    prop_map = {p["name"]: p for p in entity_meta.get("properties", [])}
    results = []
    errors = []

    for field_name in fields:
        if not field_name:
            continue
        fv = FieldValidationResult(field=field_name, entity=entity_name)
        if field_name in prop_map:
            prop = prop_map[field_name]
            fv.exists = True
            fv.type = prop.get("type", "")
            fv.label = prop.get("label", "")
            fv.editable = prop.get("creatable", False) or prop.get("updatable", False)
        else:
            fv.exists = False
            errors.append(f"Field '{field_name}' not found on '{entity_name}'")
        results.append(fv)

    return ValidationReport(
        valid=len(errors) == 0,
        field_validations=results,
        errors=errors,
        warnings=[],
    ).model_dump()
