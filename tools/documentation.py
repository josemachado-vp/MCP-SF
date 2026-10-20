"""
Project documentation generation tools for SAP SuccessFactors.

Generates functional specifications, cutover checklists, data dictionaries,
and end-to-end test scripts.

These tools combine metadata from the SF instance with knowledge base
data to produce implementation documentation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.metadata_parser import parse_metadata_xml

documentation_mcp = FastMCP(name="SF Documentation Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)
_KB_PATH = Path(__file__).parent.parent / "knowledge"


async def _sf_query(sf, api_host, token, entity, params):
    async with _SF_SEMAPHORE:
        return await sf.query_odata(data_center=api_host, bearer_token=token, entity=entity, params=params)


@documentation_mcp.tool
async def generate_functional_spec(
    entity: Annotated[str, "Primary entity for the spec (e.g., 'EmpJob', 'User')"],
    scope_fields: Annotated[Optional[list[str]], "Specific fields to include in scope. Default: all creatable/updatable fields"] = None,
    include_rules: Annotated[bool, "Include configured business rules in the spec"] = True,
    language: Annotated[str, "Output language: 'en' (English) or 'es' (Spanish)"] = "en",
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Generate a functional specification document for an SF entity/portlet.

    Produces a structured spec with:
    - Entity overview and key fields
    - Field mapping (name, type, label, editability, picklist info)
    - Configured business rules (optional)
    - Navigation properties / relationships
    - Recommendations

    Output is structured for easy conversion to Word/PDF.
    """
    api_host = resolve_api_host(data_center)
    today = date.today().isoformat()
    es = language == "es"

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)

        # Fetch metadata
        xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=entity)
        parsed = parse_metadata_xml(xml_text)
        entity_meta = parsed["entities"].get(entity, {})

        if not entity_meta:
            return {"error": f"Entity '{entity}' not found in metadata"}

        # Fetch rules if requested
        rules = []
        if include_rules:
            # Find base object for this entity
            with open(_KB_PATH / "base_objects.json", encoding="utf-8") as f:
                bo_data = json.load(f)
            base_obj = None
            for bo in bo_data.get("base_objects", []):
                if bo["primary_entity"] == entity:
                    base_obj = bo["id"]
                    break

            if base_obj:
                rules_result = await _sf_query(sf, api_host, token, "RuleHeaderBean", {
                    "$filter": f"baseObject eq '{base_obj}'",
                    "$top": "100",
                })
                rules = rules_result.get("d", {}).get("results", [])

    properties = entity_meta.get("properties", {})
    keys = entity_meta.get("keys", [])
    nav_props = entity_meta.get("navigation_properties", [])

    # Filter fields if scope specified
    if scope_fields:
        properties = {k: v for k, v in properties.items() if k in scope_fields or k in keys}

    # Build field mapping
    field_mapping = []
    for name, prop in sorted(properties.items()):
        field_mapping.append({
            "field": name,
            "type": prop.get("type", ""),
            "label": prop.get("label", name),
            "is_key": name in keys,
            "required": prop.get("required", False),
            "creatable": prop.get("creatable", False),
            "updatable": prop.get("updatable", False),
            "is_picklist": bool(prop.get("sap_picklist")),
            "picklist_id": prop.get("sap_picklist", ""),
        })

    # Build spec
    spec = {
        "title": f"{'Especificación Funcional' if es else 'Functional Specification'}: {entity}",
        "generated_date": today,
        "entity": entity,
        "overview": {
            "entity_name": entity,
            "total_fields": len(properties),
            "key_fields": keys,
            "editable_fields": sum(1 for p in properties.values() if p.get("creatable") or p.get("updatable")),
            "picklist_fields": sum(1 for p in properties.values() if p.get("sap_picklist")),
        },
        "field_mapping": field_mapping,
        "navigation_properties": [
            {"name": np["name"], "target": np.get("target_entity", ""), "relationship": np.get("relationship", "")}
            for np in nav_props
        ],
    }

    if rules:
        spec["business_rules"] = [
            {
                "ruleName": r.get("ruleName", ""),
                "ruleId": r.get("ruleId", ""),
                "ruleScenario": r.get("ruleScenario", ""),
                "ruleStatus": r.get("ruleStatus", ""),
            }
            for r in rules
        ]

    spec["recommendations"] = []
    picklist_fields = [f for f in field_mapping if f["is_picklist"]]
    if picklist_fields:
        spec["recommendations"].append(
            f"{'Verificar valores de picklist para' if es else 'Verify picklist values for'}: {', '.join(f['field'] for f in picklist_fields[:10])}"
        )
    if not rules and include_rules:
        spec["recommendations"].append(
            "No se encontraron reglas de negocio configuradas para esta entidad" if es
            else "No business rules found configured for this entity"
        )

    return spec


@documentation_mcp.tool
async def generate_cutover_checklist(
    entities: Annotated[list[str], "Entities to include in cutover (e.g., ['FOCompany', 'FODepartment', 'EmpJob'])"],
    include_rules: Annotated[bool, "Include business rules in the checklist"] = True,
    include_picklists: Annotated[bool, "Include picklists in the checklist"] = True,
    language: Annotated[str, "Output language: 'en' or 'es'"] = "en",
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Generate a cutover checklist for migrating configuration from DEV to PROD.

    Produces an ordered checklist based on entity dependencies, including:
    - Foundation Objects in correct load order
    - Picklist configurations
    - Business rules
    - User/employee data in dependency order

    Essential for go-live planning.
    """
    es = language == "es"
    today = date.today().isoformat()

    # Load migration sequence
    with open(_KB_PATH / "country_configs.json", encoding="utf-8") as f:
        config_data = json.load(f)
    migration_order = config_data.get("migration_entity_order", [])

    # Build ordered entity list based on dependencies
    order_map = {item["entity"]: item for item in migration_order}
    ordered_entities = []
    for item in migration_order:
        if item["entity"] in entities:
            ordered_entities.append(item)

    # Add any entities not in the predefined order
    known_entities = {item["entity"] for item in migration_order}
    for e in entities:
        if e not in known_entities:
            ordered_entities.append({"order": 99, "entity": e, "description": e, "dependencies": []})

    # Fetch picklists and rules if requested
    picklist_items = []
    rule_items = []

    if (include_picklists or include_rules) and data_center:
        api_host = resolve_api_host(data_center)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
            token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
            sf = SFClient(http)

            if include_rules:
                rules_result = await _sf_query(sf, api_host, token, "RuleHeaderBean", {"$top": "200"})
                for r in rules_result.get("d", {}).get("results", []):
                    rule_items.append({
                        "item": f"{'Regla' if es else 'Rule'}: {r.get('ruleName', '')}",
                        "type": "business_rule",
                        "details": f"Scenario: {r.get('ruleScenario', '')}, Base Object: {r.get('baseObject', '')}",
                    })

    # Build checklist
    checklist = []
    step = 1

    # Phase 1: Foundation Objects
    fo_entities = [e for e in ordered_entities if e["entity"].startswith("FO")]
    if fo_entities:
        for item in fo_entities:
            checklist.append({
                "step": step,
                "phase": "Foundation Objects",
                "item": f"{'Migrar' if es else 'Migrate'} {item['description']} ({item['entity']})",
                "dependencies": item["dependencies"],
                "type": "data_migration",
                "status": "pending",
            })
            step += 1

    # Phase 2: Picklists
    if include_picklists and picklist_items:
        for pl in picklist_items:
            checklist.append({"step": step, "phase": "Picklists", **pl, "status": "pending"})
            step += 1

    # Phase 3: Business Rules
    if include_rules and rule_items:
        for r in rule_items:
            checklist.append({"step": step, "phase": "Business Rules", **r, "status": "pending"})
            step += 1

    # Phase 4: Position data
    pos_entities = [e for e in ordered_entities if e["entity"] == "Position"]
    for item in pos_entities:
        checklist.append({
            "step": step, "phase": "Positions",
            "item": f"{'Migrar' if es else 'Migrate'} {item['description']}",
            "dependencies": item["dependencies"], "type": "data_migration", "status": "pending",
        })
        step += 1

    # Phase 5: Employee data
    emp_entities = [e for e in ordered_entities if not e["entity"].startswith("FO") and e["entity"] != "Position"]
    for item in emp_entities:
        checklist.append({
            "step": step, "phase": "Employee Data",
            "item": f"{'Migrar' if es else 'Migrate'} {item['description']} ({item['entity']})",
            "dependencies": item["dependencies"], "type": "data_migration", "status": "pending",
        })
        step += 1

    # Phase 6: Validation
    checklist.append({
        "step": step, "phase": "Validation",
        "item": "Ejecutar validaciones post-migración" if es else "Run post-migration validations",
        "type": "validation", "status": "pending",
    })
    step += 1
    checklist.append({
        "step": step, "phase": "Validation",
        "item": "Ejecutar reconciliación de conteos" if es else "Run record count reconciliation",
        "type": "validation", "status": "pending",
    })

    return {
        "title": f"{'Checklist de Cutover' if es else 'Cutover Checklist'}",
        "generated_date": today,
        "total_steps": len(checklist),
        "phases": sorted(set(c["phase"] for c in checklist)),
        "checklist": checklist,
    }


@documentation_mcp.tool
async def generate_data_dictionary(
    entities: Annotated[list[str], "Entities to include (e.g., ['EmpJob', 'EmpCompensation', 'PerPersonal'])"],
    include_navigation: Annotated[bool, "Include navigation properties"] = False,
    language: Annotated[str, "Output language: 'en' or 'es'"] = "en",
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Generate a complete data dictionary for multiple SF entities.

    For each entity, produces a field-by-field reference with:
    name, type, label, key status, required, creatable, updatable, picklist info.

    Output is structured as CSV-exportable rows for easy import into Excel.
    """
    api_host = resolve_api_host(data_center)
    today = date.today().isoformat()
    es = language == "es"

    dictionary_rows = []

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password, api_host=api_host)
        sf = SFClient(http)

        for entity_name in entities:
            try:
                xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=entity_name)
                parsed = parse_metadata_xml(xml_text)
                entity_meta = parsed["entities"].get(entity_name, {})

                if not entity_meta:
                    dictionary_rows.append({
                        "entity": entity_name,
                        "field": "(error)",
                        "note": f"Entity not found in metadata",
                    })
                    continue

                keys = entity_meta.get("keys", [])
                for name, prop in sorted(entity_meta.get("properties", {}).items()):
                    dictionary_rows.append({
                        "entity": entity_name,
                        "field": name,
                        "type": prop.get("type", ""),
                        "label": prop.get("label", ""),
                        "is_key": name in keys,
                        "required": prop.get("required", False),
                        "creatable": prop.get("creatable", False),
                        "updatable": prop.get("updatable", False),
                        "picklist_id": prop.get("sap_picklist", ""),
                    })

                if include_navigation:
                    for np in entity_meta.get("navigation_properties", []):
                        dictionary_rows.append({
                            "entity": entity_name,
                            "field": np["name"],
                            "type": "Navigation",
                            "label": np.get("target_entity", ""),
                            "is_key": False,
                            "required": False,
                            "creatable": False,
                            "updatable": False,
                            "picklist_id": "",
                        })
            except Exception as e:
                dictionary_rows.append({
                    "entity": entity_name,
                    "field": "(error)",
                    "note": str(e),
                })

    # Build CSV header
    csv_header = "Entity,Field,Type,Label,Is Key,Required,Creatable,Updatable,Picklist ID"
    csv_rows = [csv_header]
    for row in dictionary_rows:
        if "note" in row:
            csv_rows.append(f"{row['entity']},{row['field']},,{row.get('note', '')},,,,,,")
        else:
            csv_rows.append(
                f"{row['entity']},{row['field']},{row['type']},{row['label']},"
                f"{row['is_key']},{row['required']},{row['creatable']},{row['updatable']},{row['picklist_id']}"
            )

    return {
        "title": "Diccionario de Datos" if es else "Data Dictionary",
        "generated_date": today,
        "entities_included": entities,
        "total_fields": len([r for r in dictionary_rows if "note" not in r]),
        "dictionary": dictionary_rows,
        "csv_export": "\n".join(csv_rows),
    }


@documentation_mcp.tool
async def generate_test_script(
    scenario: Annotated[str, "Test scenario: 'hire', 'promote', 'transfer', 'terminate', 'rehire', 'compensation_change', 'org_change', 'full_lifecycle'"],
    country: Annotated[Optional[str], "Country code for country-specific steps (e.g., 'COL', 'MEX')"] = None,
    language: Annotated[str, "Output language: 'en' or 'es'"] = "en",
) -> dict:
    """
    Generate an end-to-end test script for a specific HR scenario.

    Produces step-by-step test instructions including:
    - Preconditions
    - Step-by-step actions
    - Expected results at each step
    - Business rule validations
    - Country-specific checks

    No SF API calls needed — uses knowledge base.
    """
    es = language == "es"
    today = date.today().isoformat()

    # Load country config if needed
    country_config = None
    if country:
        with open(_KB_PATH / "country_configs.json", encoding="utf-8") as f:
            config_data = json.load(f)
        country_config = config_data.get("countries", {}).get(country)

    scenarios = {
        "hire": {
            "name": "Contratación" if es else "New Hire",
            "preconditions": [
                "Posición vacante disponible" if es else "Vacant position available",
                "Foundation Objects configurados (Empresa, Departamento, Ubicación)" if es else "Foundation Objects configured (Company, Department, Location)",
                "Picklists de evento configurados" if es else "Event picklists configured",
            ],
            "steps": [
                {"step": 1, "action": "Crear registro de empleo (EmpEmployment)" if es else "Create employment record (EmpEmployment)", "entity": "EmpEmployment", "expected": "Registro creado con startDate" if es else "Record created with startDate"},
                {"step": 2, "action": "Crear información personal (PerPersonal)" if es else "Create personal info (PerPersonal)", "entity": "PerPersonal", "expected": "Nombre, género, nacionalidad registrados" if es else "Name, gender, nationality recorded"},
                {"step": 3, "action": "Crear información de trabajo (EmpJob)" if es else "Create job info (EmpJob)", "entity": "EmpJob", "expected": "Empresa, departamento, posición, manager asignados. Reglas onInit ejecutadas." if es else "Company, department, position, manager assigned. onInit rules executed."},
                {"step": 4, "action": "Verificar reglas de negocio ejecutadas" if es else "Verify business rules executed", "entity": "EmpJob", "expected": "Campos derivados por reglas tienen valores correctos" if es else "Fields derived by rules have correct values"},
                {"step": 5, "action": "Crear compensación (EmpCompensation)" if es else "Create compensation (EmpCompensation)", "entity": "EmpCompensation", "expected": "Grupo de pago, tipo de pago asignados" if es else "Pay group, pay type assigned"},
                {"step": 6, "action": "Crear email y teléfono" if es else "Create email and phone", "entity": "PerEmail/PerPhone", "expected": "Contacto registrado" if es else "Contact info recorded"},
                {"step": 7, "action": "Verificar perfil completo" if es else "Verify complete profile", "entity": "User", "expected": "Todos los portlets tienen datos, sin warnings" if es else "All portlets have data, no warnings"},
            ],
        },
        "promote": {
            "name": "Promoción" if es else "Promotion",
            "preconditions": [
                "Empleado activo con job info actual" if es else "Active employee with current job info",
                "Nueva posición o job code disponible" if es else "New position or job code available",
            ],
            "steps": [
                {"step": 1, "action": "Añadir nuevo registro EmpJob con event reason 'Promoción'" if es else "Add new EmpJob record with event reason 'Promotion'", "entity": "EmpJob", "expected": "Nuevo registro effective-dated creado" if es else "New effective-dated record created"},
                {"step": 2, "action": "Cambiar posición/job code/departamento según aplique" if es else "Change position/job code/department as applicable", "entity": "EmpJob", "expected": "Campos actualizados, reglas onChange ejecutadas" if es else "Fields updated, onChange rules executed"},
                {"step": 3, "action": "Verificar que manager se actualizó si es posición diferente" if es else "Verify manager updated if different position", "entity": "EmpJob", "expected": "Manager correcto según nueva posición" if es else "Correct manager per new position"},
                {"step": 4, "action": "Actualizar compensación si aplica" if es else "Update compensation if applicable", "entity": "EmpCompensation", "expected": "Nuevo registro de compensación" if es else "New compensation record"},
                {"step": 5, "action": "Verificar historial muestra cambio" if es else "Verify history shows change", "entity": "EmpJob", "expected": "Registro anterior tiene endDate, nuevo tiene startDate correcto" if es else "Previous record has endDate, new has correct startDate"},
            ],
        },
        "transfer": {
            "name": "Transferencia" if es else "Transfer",
            "preconditions": [
                "Empleado activo" if es else "Active employee",
                "Departamento/ubicación/empresa destino existente" if es else "Target department/location/company exists",
            ],
            "steps": [
                {"step": 1, "action": "Añadir nuevo registro EmpJob con event reason 'Transferencia'" if es else "Add new EmpJob record with event reason 'Transfer'", "entity": "EmpJob", "expected": "Nuevo registro effective-dated" if es else "New effective-dated record"},
                {"step": 2, "action": "Cambiar departamento/ubicación/empresa" if es else "Change department/location/company", "entity": "EmpJob", "expected": "Campos actualizados, reglas derivaron campos dependientes" if es else "Fields updated, rules derived dependent fields"},
                {"step": 3, "action": "Verificar que cost center se actualizó automáticamente" if es else "Verify cost center updated automatically", "entity": "EmpJob", "expected": "Cost center corresponde al nuevo departamento" if es else "Cost center matches new department"},
                {"step": 4, "action": "Verificar que manager cambió si aplica" if es else "Verify manager changed if applicable", "entity": "EmpJob", "expected": "Manager correcto para nuevo departamento" if es else "Correct manager for new department"},
            ],
        },
        "terminate": {
            "name": "Terminación" if es else "Termination",
            "preconditions": [
                "Empleado activo" if es else "Active employee",
                "Event reason de terminación configurado" if es else "Termination event reason configured",
            ],
            "steps": [
                {"step": 1, "action": "Añadir registro EmpJob con emplStatus='T'" if es else "Add EmpJob record with emplStatus='T'", "entity": "EmpJob", "expected": "Status cambiado a terminado" if es else "Status changed to terminated"},
                {"step": 2, "action": "Verificar que EmpEmployment.endDate se actualizó" if es else "Verify EmpEmployment.endDate updated", "entity": "EmpEmployment", "expected": "endDate coincide con fecha de terminación" if es else "endDate matches termination date"},
                {"step": 3, "action": "Verificar que time accounts se cerraron" if es else "Verify time accounts closed", "entity": "TimeAccount", "expected": "Balances de tiempo ajustados" if es else "Time balances adjusted"},
                {"step": 4, "action": "Verificar que posición quedó vacante" if es else "Verify position is now vacant", "entity": "Position", "expected": "Posición marcada como vacante" if es else "Position marked as vacant"},
            ],
        },
        "rehire": {
            "name": "Recontratación" if es else "Rehire",
            "preconditions": [
                "Empleado previamente terminado" if es else "Previously terminated employee",
                "Posición disponible" if es else "Position available",
            ],
            "steps": [
                {"step": 1, "action": "Reactivar empleado — nuevo EmpJob con emplStatus='A'" if es else "Reactivate employee — new EmpJob with emplStatus='A'", "entity": "EmpJob", "expected": "Status activo, nueva fecha de inicio" if es else "Active status, new start date"},
                {"step": 2, "action": "Verificar que EmpEmployment se reactivó" if es else "Verify EmpEmployment reactivated", "entity": "EmpEmployment", "expected": "endDate revertido o nuevo registro" if es else "endDate reverted or new record"},
                {"step": 3, "action": "Verificar datos personales preservados" if es else "Verify personal data preserved", "entity": "PerPersonal", "expected": "Información personal intacta" if es else "Personal info intact"},
                {"step": 4, "action": "Crear nueva compensación" if es else "Create new compensation", "entity": "EmpCompensation", "expected": "Nuevo registro de compensación" if es else "New compensation record"},
                {"step": 5, "action": "Verificar seniority date" if es else "Verify seniority date", "entity": "EmpEmployment", "expected": "Según política: original o nueva" if es else "Per policy: original or new"},
            ],
        },
        "compensation_change": {
            "name": "Cambio de Compensación" if es else "Compensation Change",
            "preconditions": ["Empleado activo con compensación actual" if es else "Active employee with current compensation"],
            "steps": [
                {"step": 1, "action": "Añadir nuevo registro EmpCompensation" if es else "Add new EmpCompensation record", "entity": "EmpCompensation", "expected": "Nuevo registro effective-dated" if es else "New effective-dated record"},
                {"step": 2, "action": "Verificar compa-ratio recalculado" if es else "Verify compa-ratio recalculated", "entity": "EmpCompensation", "expected": "Compa-ratio actualizado" if es else "Compa-ratio updated"},
                {"step": 3, "action": "Verificar range penetration" if es else "Verify range penetration", "entity": "EmpCompensation", "expected": "Dentro de rango del pay grade" if es else "Within pay grade range"},
            ],
        },
        "org_change": {
            "name": "Cambio Organizacional" if es else "Org Change",
            "preconditions": ["FOs actualizados en destino" if es else "Target FOs updated"],
            "steps": [
                {"step": 1, "action": "Actualizar FODepartment/FODivision" if es else "Update FODepartment/FODivision", "entity": "FODepartment", "expected": "FO actualizado con nueva estructura" if es else "FO updated with new structure"},
                {"step": 2, "action": "Verificar empleados impactados" if es else "Verify impacted employees", "entity": "EmpJob", "expected": "Empleados mantienen referencia válida" if es else "Employees maintain valid reference"},
                {"step": 3, "action": "Mover empleados al nuevo FO si aplica" if es else "Move employees to new FO if applicable", "entity": "EmpJob", "expected": "Registros actualizados" if es else "Records updated"},
            ],
        },
        "full_lifecycle": {
            "name": "Ciclo de Vida Completo" if es else "Full Lifecycle",
            "preconditions": ["Instancia configurada completamente" if es else "Fully configured instance"],
            "steps": [
                {"step": 1, "action": "Contratación (ver escenario 'hire')" if es else "Hire (see 'hire' scenario)", "entity": "Multiple", "expected": "Empleado creado y activo" if es else "Employee created and active"},
                {"step": 2, "action": "Promoción (ver escenario 'promote')" if es else "Promotion (see 'promote' scenario)", "entity": "EmpJob", "expected": "Posición/cargo actualizado" if es else "Position/title updated"},
                {"step": 3, "action": "Transferencia (ver escenario 'transfer')" if es else "Transfer (see 'transfer' scenario)", "entity": "EmpJob", "expected": "Departamento cambiado" if es else "Department changed"},
                {"step": 4, "action": "Cambio de compensación" if es else "Compensation change", "entity": "EmpCompensation", "expected": "Salario actualizado" if es else "Salary updated"},
                {"step": 5, "action": "Terminación (ver escenario 'terminate')" if es else "Termination (see 'terminate' scenario)", "entity": "EmpJob", "expected": "Empleado terminado" if es else "Employee terminated"},
                {"step": 6, "action": "Recontratación (ver escenario 'rehire')" if es else "Rehire (see 'rehire' scenario)", "entity": "EmpJob", "expected": "Empleado reactivado" if es else "Employee reactivated"},
                {"step": 7, "action": "Verificar historial completo" if es else "Verify complete history", "entity": "EmpJob", "expected": "Timeline completa sin gaps" if es else "Complete timeline without gaps"},
            ],
        },
    }

    scenario_data = scenarios.get(scenario)
    if not scenario_data:
        return {"error": f"Unknown scenario '{scenario}'. Valid: {list(scenarios.keys())}"}

    # Add country-specific steps if applicable
    if country_config:
        country_steps = []
        for req_field in country_config.get("required_fields", []):
            if req_field.get("type") != "key":
                country_steps.append({
                    "action": f"Verificar {req_field.get('label', req_field['field'])} ({req_field['description']})" if es
                              else f"Verify {req_field.get('label', req_field['field'])} ({req_field['description']})",
                    "entity": country_config["entity"],
                    "expected": f"Campo {req_field['field']} tiene valor válido" if es else f"Field {req_field['field']} has valid value",
                })
        if country_steps:
            last_step = scenario_data["steps"][-1]["step"]
            for i, cs in enumerate(country_steps):
                scenario_data["steps"].append({"step": last_step + i + 1, **cs})

    return {
        "title": f"{'Script de Prueba' if es else 'Test Script'}: {scenario_data['name']}",
        "scenario": scenario,
        "country": country,
        "generated_date": today,
        "preconditions": scenario_data["preconditions"],
        "total_steps": len(scenario_data["steps"]),
        "steps": scenario_data["steps"],
        "country_compliance_notes": country_config.get("compliance_notes", []) if country_config else [],
    }
