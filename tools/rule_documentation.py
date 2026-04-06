"""
Business Rules documentation and test generation tools.

generate_rule_doc: Step-by-step implementation guide for the SF Rule Editor.
generate_rule_test: Test case matrix with positive, edge case, and negative tests.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP

from models.field_validation import TestCase, TestMatrix


rule_documentation_mcp = FastMCP(name="SF Rule Documentation Tools")


# ---------- Tool 7: generate_rule_doc ----------


@rule_documentation_mcp.tool
async def generate_rule_doc(
    rule_spec: Annotated[dict, "The rule specification output from generate_rule_spec"],
    output_format: Annotated[str, "Output format: 'markdown' (default), 'json', or 'text'"] = "markdown",
    language: Annotated[str, "Documentation language: 'en' for English, 'es' for Spanish"] = "en",
) -> dict:
    """
    Generate step-by-step implementation documentation for a business rule.

    Produces a consultant-ready guide for creating the rule in the SAP
    SuccessFactors Rule Editor UI, including:
    - Navigation steps in Admin Center
    - Rule creation dialog values
    - Each IF/THEN condition to configure
    - HRIS Element assignment instructions
    - Event type configuration
    - Post-implementation verification steps
    """
    rule_name = rule_spec.get("rule_name", "Unnamed Rule")
    scenario = rule_spec.get("scenario", "")
    base_object = rule_spec.get("base_object", "")
    event_type = rule_spec.get("event_type", "")
    hris_element = rule_spec.get("hris_element_assignment", "")
    description = rule_spec.get("description", "")
    conditions = rule_spec.get("conditions", [])
    execution_notes = rule_spec.get("execution_notes", {})

    if output_format == "json":
        steps = _generate_steps_json(
            rule_name, scenario, base_object, event_type,
            hris_element, conditions,
        )
        return {"format": "json", "steps": steps, "rule_name": rule_name}

    doc = _generate_markdown_doc(
        rule_name, scenario, base_object, event_type,
        hris_element, description, conditions, execution_notes, language,
    )

    if output_format == "text":
        doc = doc.replace("#", "").replace("**", "").replace("`", "").replace("|", " ")
        return {"format": "text", "content": doc, "rule_name": rule_name}

    return {"format": "markdown", "content": doc, "rule_name": rule_name}


# ---------- Tool 8: generate_rule_test ----------


@rule_documentation_mcp.tool
async def generate_rule_test(
    rule_spec: Annotated[dict, "The rule specification output from generate_rule_spec"],
    include_edge_cases: Annotated[bool, "Include edge case test scenarios"] = True,
    include_negative_tests: Annotated[bool, "Include negative/no-match test cases"] = True,
) -> dict:
    """
    Generate a comprehensive test case matrix for a business rule.

    Produces test cases covering:
    - Each condition path (positive scenarios)
    - Edge cases (empty fields, null values, boundary conditions)
    - Negative cases (conditions that should NOT trigger the rule)
    - Coverage matrix showing which paths are tested

    Each test case includes preconditions, action, and expected results.
    """
    rule_name = rule_spec.get("rule_name", "Unnamed Rule")
    conditions = rule_spec.get("conditions", [])
    event_type = rule_spec.get("event_type", "onSave")
    base_object = rule_spec.get("base_object", "")

    test_cases: list[TestCase] = []
    tc_counter = 1

    # Positive test cases from conditions
    for condition in conditions:
        expression = condition.get("expression", {})
        action = condition.get("action")
        nested = condition.get("nested_conditions", [])

        if action:
            tc = TestCase(
                id=f"TC{tc_counter:03d}",
                description=(
                    f"When {expression.get('field', '')} "
                    f"{expression.get('operator', '')} "
                    f"'{expression.get('value', '')}' -> "
                    f"{action.get('target_field', '')} = '{action.get('value', '')}'"
                ),
                preconditions={expression.get("field", ""): expression.get("value", "")},
                action=_event_type_to_action(event_type, base_object),
                expected_result={action.get("target_field", ""): action.get("value", "")},
            )
            test_cases.append(tc)
            tc_counter += 1

        for nested_cond in nested:
            n_expr = nested_cond.get("expression", {})
            n_action = nested_cond.get("action")
            if n_action:
                tc = TestCase(
                    id=f"TC{tc_counter:03d}",
                    description=(
                        f"When {expression.get('field', '')}='{expression.get('value', '')}' "
                        f"AND {n_expr.get('field', '')}='{n_expr.get('value', '')}' -> "
                        f"{n_action.get('target_field', '')} = '{n_action.get('value', '')}'"
                    ),
                    preconditions={
                        expression.get("field", ""): expression.get("value", ""),
                        n_expr.get("field", ""): n_expr.get("value", ""),
                    },
                    action=_event_type_to_action(event_type, base_object),
                    expected_result={n_action.get("target_field", ""): n_action.get("value", "")},
                )
                test_cases.append(tc)
                tc_counter += 1

    # Edge case tests
    if include_edge_cases:
        all_fields: set[str] = set()
        for condition in conditions:
            expr = condition.get("expression", {})
            if expr.get("field"):
                all_fields.add(expr["field"])
            for nc in condition.get("nested_conditions", []):
                nc_expr = nc.get("expression", {})
                if nc_expr.get("field"):
                    all_fields.add(nc_expr["field"])

        for field in sorted(all_fields):
            tc = TestCase(
                id=f"TC{tc_counter:03d}",
                description=f"Edge case: '{field}' is empty/null",
                preconditions={field: "<EMPTY>"},
                action=_event_type_to_action(event_type, base_object),
                expected_result={"rule_behavior": "Rule should not trigger, field unchanged"},
                is_edge_case=True,
            )
            test_cases.append(tc)
            tc_counter += 1

    # Negative tests
    if include_negative_tests:
        tc = TestCase(
            id=f"TC{tc_counter:03d}",
            description="Negative: No conditions match - rule should not fire",
            preconditions={"all_condition_fields": "<VALUES_NOT_MATCHING_ANY_CONDITION>"},
            action=_event_type_to_action(event_type, base_object),
            expected_result={"rule_behavior": "No action taken, all fields unchanged"},
        )
        test_cases.append(tc)
        tc_counter += 1

    # Coverage calculation
    total_paths = len(conditions)
    for c in conditions:
        total_paths += len(c.get("nested_conditions", []))

    positive_tests = len([tc for tc in test_cases if not tc.is_edge_case])

    matrix = TestMatrix(
        rule_name=rule_name,
        test_cases=test_cases,
        total_paths=max(total_paths, 1),
        covered_paths=positive_tests,
        coverage_percentage=f"{(positive_tests / max(total_paths, 1)) * 100:.0f}%",
    )

    return matrix.model_dump()


# ---------- Internal helpers ----------


def _generate_markdown_doc(
    rule_name: str,
    scenario: str,
    base_object: str,
    event_type: str,
    hris_element: str,
    description: str,
    conditions: list[dict],
    execution_notes: dict,
    language: str,
) -> str:
    """Generate markdown implementation guide."""
    is_es = language == "es"

    lines = [
        f"# {'Guia de Implementacion' if is_es else 'Implementation Guide'}: {rule_name}",
        "",
        f"> {description}",
        "",
        f"## {'Pasos de Navegacion' if is_es else 'Navigation Steps'}",
        "",
        f"1. {'Iniciar sesion en SAP SuccessFactors como Admin' if is_es else 'Log into SAP SuccessFactors as Admin'}",
        f"2. {'Navegar a' if is_es else 'Navigate to'} **Admin Center**",
        f"3. {'Buscar' if is_es else 'Search for'} **Configure Business Rules**",
        f"4. Click **+** ({'Crear Nueva Regla' if is_es else 'Create New Rule'})",
        "",
        f"## {'Configuracion de la Regla' if is_es else 'Rule Configuration'}",
        "",
        "| Setting | Value |",
        "|---------|-------|",
        f"| Rule Name | `{rule_name}` |",
        f"| Scenario | {scenario} |",
        f"| Base Object | {base_object} |",
        f"| Description | {description[:100]} |",
        "",
        f"## {'Logica de Condiciones' if is_es else 'Condition Logic'}",
        "",
    ]

    for i, condition in enumerate(conditions):
        cond_type = condition.get("type", "IF")
        expression = condition.get("expression", {})
        action = condition.get("action")
        nested = condition.get("nested_conditions", [])

        lines.append(f"### {'Condicion' if is_es else 'Condition'} {i + 1}: {cond_type}")
        lines.append("")
        lines.append(f"- Click **Add Condition**")
        lines.append(f"- Type: `{cond_type}`")
        lines.append(f"- Field: `{expression.get('field', '')}` (Entity: `{expression.get('entity', '')}`)")
        lines.append(f"- Operator: `{expression.get('operator', '')}`")
        lines.append(f"- Value: `{expression.get('value', '')}`")
        lines.append("")

        if action:
            lines.append(f"**{'Accion' if is_es else 'Action'}:**")
            lines.append(f"- Click **Add Action**")
            lines.append(f"- Action Type: `{action.get('type', '')}`")
            lines.append(f"- Target Field: `{action.get('target_field', '')}`")
            lines.append(f"- Value: `{action.get('value', '')}` ({action.get('value_label', '')})")
            lines.append("")

        for j, nc in enumerate(nested):
            n_expr = nc.get("expression", {})
            n_action = nc.get("action")
            lines.append(f"#### Nested {j + 1}: {nc.get('type', 'AND_IF')}")
            lines.append(f"- Field: `{n_expr.get('field', '')}`")
            lines.append(f"- Operator: `{n_expr.get('operator', '')}`")
            lines.append(f"- Value: `{n_expr.get('value', '')}`")
            if n_action:
                lines.append(f"- Action: Set `{n_action.get('target_field', '')}` = `{n_action.get('value', '')}`")
            lines.append("")

    lines.extend([
        f"## {'Asignacion' if is_es else 'Assignment'}",
        "",
        f"1. {'Despues de guardar la regla, ir a' if is_es else 'After saving the rule, go to'} **Manage Business Configuration**",
        f"2. {'Buscar HRIS Element' if is_es else 'Find HRIS Element'}: **{hris_element}**",
        f"3. {'Asignar la regla' if is_es else 'Assign the rule'} **{rule_name}**",
        f"4. {'Tipo de Evento' if is_es else 'Event Type'}: **{event_type}**",
        "",
        f"## {'Verificacion Post-Implementacion' if is_es else 'Post-Implementation Verification'}",
        "",
        f"1. {'Navegar al registro de un empleado' if is_es else 'Navigate to an employee record'}",
        f"2. {'Abrir el portlet relevante' if is_es else 'Open the relevant portlet'}",
        f"3. {'Realizar un cambio que active la regla' if is_es else 'Make a change that should trigger the rule'}",
        f"4. {'Verificar que el campo esperado se lleno correctamente' if is_es else 'Verify the expected field is populated correctly'}",
        f"5. {'Revisar mensajes de error' if is_es else 'Check for error messages'}",
        "",
    ])

    if execution_notes:
        lines.append(f"## {'Notas de Ejecucion' if is_es else 'Execution Notes'}")
        lines.append("")
        if execution_notes.get("order_recommendation"):
            lines.append(f"- **{'Orden' if is_es else 'Order'}**: {execution_notes['order_recommendation']}")
        for dep in execution_notes.get("dependencies", []):
            lines.append(f"- **{'Dependencia' if is_es else 'Dependency'}**: {dep}")
        for edge in execution_notes.get("edge_cases", []):
            lines.append(f"- **Edge Case**: {edge}")

    return "\n".join(lines)


def _generate_steps_json(
    rule_name: str,
    scenario: str,
    base_object: str,
    event_type: str,
    hris_element: str,
    conditions: list[dict],
) -> list[dict]:
    """Generate structured JSON steps."""
    steps = [
        {"step": 1, "action": "navigate", "target": "Admin Center > Configure Business Rules"},
        {"step": 2, "action": "click", "target": "+ (Create New Rule)"},
        {"step": 3, "action": "fill", "field": "Rule Name", "value": rule_name},
        {"step": 4, "action": "select", "field": "Scenario", "value": scenario},
        {"step": 5, "action": "select", "field": "Base Object", "value": base_object},
    ]

    step_num = 6
    for condition in conditions:
        steps.append({
            "step": step_num,
            "action": "add_condition",
            "condition_type": condition.get("type", ""),
            "expression": condition.get("expression", {}),
        })
        step_num += 1

        if condition.get("action"):
            steps.append({
                "step": step_num,
                "action": "add_action",
                "action_type": condition["action"].get("type", ""),
                "target_field": condition["action"].get("target_field", ""),
                "value": condition["action"].get("value", ""),
            })
            step_num += 1

        for nc in condition.get("nested_conditions", []):
            steps.append({
                "step": step_num,
                "action": "add_nested_condition",
                "condition_type": nc.get("type", "AND_IF"),
                "expression": nc.get("expression", {}),
            })
            step_num += 1
            if nc.get("action"):
                steps.append({
                    "step": step_num,
                    "action": "add_action",
                    "action_type": nc["action"].get("type", ""),
                    "target_field": nc["action"].get("target_field", ""),
                    "value": nc["action"].get("value", ""),
                })
                step_num += 1

    steps.append({"step": step_num, "action": "save"})
    step_num += 1
    steps.append({
        "step": step_num,
        "action": "assign_to_hris_element",
        "hris_element": hris_element,
        "event_type": event_type,
    })

    return steps


def _event_type_to_action(event_type: str, base_object: str) -> str:
    """Map event type to a human-readable test action."""
    portlet_map = {
        "JobInformationModel": "Job Information",
        "CompInfoModel": "Compensation Information",
        "PersonalInfoModel": "Personal Information",
        "EmploymentInfoModel": "Employment Details",
    }
    portlet = portlet_map.get(base_object, base_object)

    actions = {
        "onSave": f"Save a record in {portlet}",
        "onChange": f"Change a field value in {portlet} (before saving)",
        "onInit": f"Create a new record in {portlet}",
        "validate": f"Submit/save a change in {portlet}",
    }
    return actions.get(event_type, f"Trigger event '{event_type}' on {portlet}")
