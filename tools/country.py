"""
Multi-country support tools for SAP SuccessFactors.

Provides tools for country-specific field discovery, compliance validation,
and configuration guidance — with focus on LATAM countries.
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

country_mcp = FastMCP(name="SF Country Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)
_KB_PATH = Path(__file__).parent.parent / "knowledge"


async def _sf_query(sf, api_host, token, entity, params):
    async with _SF_SEMAPHORE:
        return await sf.query_odata(data_center=api_host, bearer_token=token, entity=entity, params=params)


async def _fetch_all(sf, api_host, token, entity, params, max_records=5000, page_size=1000):
    all_records = []
    skip = 0
    while len(all_records) < max_records:
        p = {**params, "$top": str(page_size), "$skip": str(skip)}
        result = await _sf_query(sf, api_host, token, entity, p)
        records = result.get("d", {}).get("results", [])
        if not records:
            break
        all_records.extend(records)
        if len(records) < page_size:
            break
        skip += page_size
    return all_records[:max_records]


def _load_country_config(country_code: str) -> Optional[dict]:
    """Load country configuration from knowledge base."""
    with open(_KB_PATH / "country_configs.json", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("countries", {}).get(country_code.upper())


@country_mcp.tool
async def get_country_specific_fields(
    country_code: Annotated[str, "ISO country code: COL, MEX, PER, CHL, ARG, BRA, USA, ESP"],
    include_live_metadata: Annotated[bool, "Also fetch metadata from the live instance for the country entity"] = False,
    data_center: Annotated[Optional[str], "API host override (required if include_live_metadata=True)"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Get country-specific fields for a PerGlobalInfo entity.

    Returns the required fields, common picklists, compliance notes, and
    typical business rules for the specified country. Covers:
    COL (Colombia), MEX (Mexico), PER (Peru), CHL (Chile),
    ARG (Argentina), BRA (Brazil), USA (United States), ESP (Spain).

    Optionally fetches live metadata from the instance to compare against
    the knowledge base.
    """
    config = _load_country_config(country_code)
    if not config:
        supported = []
        with open(_KB_PATH / "country_configs.json", encoding="utf-8") as f:
            data = json.load(f)
        supported = list(data.get("countries", {}).keys())
        return {
            "error": f"Country '{country_code}' not configured",
            "supported_countries": supported,
        }

    result = {
        "country_code": country_code.upper(),
        "country_name": config["name"],
        "entity": config["entity"],
        "required_fields": config["required_fields"],
        "common_picklists": config["common_picklists"],
        "compliance_notes": config["compliance_notes"],
        "typical_rules": config["typical_rules"],
    }

    if include_live_metadata and data_center:
        from helpers.metadata_parser import parse_metadata_xml
        api_host = resolve_api_host(data_center)

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
            token = await get_bearer_token(http, auth_user_id, auth_password)
            sf = SFClient(http)
            try:
                xml_text = await sf.get_metadata(data_center=api_host, bearer_token=token, entity=config["entity"])
                parsed = parse_metadata_xml(xml_text)
                entity_meta = parsed["entities"].get(config["entity"], {})

                if entity_meta:
                    result["live_metadata"] = {
                        "total_fields": len(entity_meta.get("properties", {})),
                        "keys": entity_meta.get("keys", []),
                        "field_names": sorted(entity_meta.get("properties", {}).keys()),
                    }
                else:
                    result["live_metadata"] = {"error": f"Entity '{config['entity']}' not found in instance"}
            except Exception as e:
                result["live_metadata"] = {"error": str(e)}

    return result


@country_mcp.tool
async def validate_country_compliance(
    country_code: Annotated[str, "ISO country code: COL, MEX, PER, CHL, ARG, BRA, USA, ESP"],
    user_ids: Annotated[Optional[list[str]], "Specific userIds to validate. Default: all employees in the country"] = None,
    max_employees: Annotated[int, "Max employees to check (1-500)"] = 100,
    data_center: Annotated[Optional[str], "API host override"] = None,
    auth_user_id: Annotated[Optional[str], "IAS username override"] = None,
    auth_password: Annotated[Optional[str], "IAS password override"] = None,
) -> dict:
    """
    Validate that employees in a country have all required country-specific fields.

    Checks each employee against the country's required fields (from knowledge base)
    and reports which fields are missing or empty. Essential for payroll and
    compliance readiness.
    """
    config = _load_country_config(country_code)
    if not config:
        return {"error": f"Country '{country_code}' not configured"}

    api_host = resolve_api_host(data_center)
    entity = config["entity"]
    required_fields = [f for f in config["required_fields"] if f.get("type") != "key"]
    field_names = [f["field"] for f in required_fields]

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as http:
        token = await get_bearer_token(http, auth_user_id, auth_password)
        sf = SFClient(http)

        if user_ids:
            # Fetch specific employees
            all_records = []
            for uid in user_ids[:max_employees]:
                result = await _sf_query(sf, api_host, token, entity, {
                    "$filter": f"personIdExternal eq '{uid}'",
                    "$orderby": "startDate desc",
                    "$top": "1",
                })
                records = result.get("d", {}).get("results", [])
                if records:
                    all_records.append(records[0])
        else:
            # Fetch employees for this country
            # First get userIds from EmpJob with this country
            job_records = await _fetch_all(sf, api_host, token, "EmpJob", {
                "$filter": f"countryOfCompany eq '{country_code.upper()}' and emplStatus eq 'A'",
                "$select": "userId",
                "$orderby": "startDate desc",
            }, max_records=max_employees * 2)  # Over-fetch to handle duplicates

            seen = set()
            target_users = []
            for r in job_records:
                uid = r.get("userId", "")
                if uid and uid not in seen:
                    seen.add(uid)
                    target_users.append(uid)
                    if len(target_users) >= max_employees:
                        break

            # Fetch country-specific data
            all_records = []
            for uid in target_users:
                result = await _sf_query(sf, api_host, token, entity, {
                    "$filter": f"personIdExternal eq '{uid}'",
                    "$orderby": "startDate desc",
                    "$top": "1",
                })
                records = result.get("d", {}).get("results", [])
                if records:
                    all_records.append(records[0])

    # Validate each employee
    employee_results = []
    compliant_count = 0
    non_compliant_count = 0

    for record in all_records:
        uid = record.get("personIdExternal", "")
        missing_fields = []
        for req in required_fields:
            field = req["field"]
            value = record.get(field, "")
            if not value or str(value).strip() == "":
                missing_fields.append({
                    "field": field,
                    "label": req.get("label", field),
                    "description": req.get("description", ""),
                })

        if missing_fields:
            non_compliant_count += 1
            employee_results.append({
                "userId": uid,
                "compliant": False,
                "missing_fields": missing_fields,
                "missing_count": len(missing_fields),
            })
        else:
            compliant_count += 1

    # Summary by field
    field_summary = {}
    for er in employee_results:
        for mf in er["missing_fields"]:
            fname = mf["field"]
            field_summary[fname] = field_summary.get(fname, 0) + 1

    field_summary_sorted = sorted(field_summary.items(), key=lambda x: x[1], reverse=True)

    return {
        "country_code": country_code.upper(),
        "country_name": config["name"],
        "entity": entity,
        "employees_checked": len(all_records),
        "compliant": compliant_count,
        "non_compliant": non_compliant_count,
        "compliance_rate": f"{(compliant_count / max(len(all_records), 1) * 100):.1f}%",
        "most_missing_fields": [{"field": f, "missing_count": c} for f, c in field_summary_sorted[:10]],
        "non_compliant_employees": employee_results[:50],
        "compliance_notes": config.get("compliance_notes", []),
    }


@country_mcp.tool
def generate_country_config_guide(
    country_code: Annotated[str, "ISO country code: COL, MEX, PER, CHL, ARG, BRA, USA, ESP"],
    language: Annotated[str, "Output language: 'en' or 'es'"] = "es",
) -> dict:
    """
    Generate a configuration guide for a specific country.

    Includes:
    - Required PerGlobalInfo fields and their purpose
    - Picklists that need to be configured
    - Compliance requirements and notes
    - Typical business rules to implement
    - Data validation recommendations

    No SF API call needed — uses knowledge base.
    """
    config = _load_country_config(country_code)
    if not config:
        return {"error": f"Country '{country_code}' not configured"}

    es = language == "es"
    today = date.today().isoformat()

    # Build guide sections
    sections = []

    # Section 1: Entity setup
    sections.append({
        "title": "Configuración de Entidad" if es else "Entity Setup",
        "content": f"{'Entidad principal' if es else 'Primary entity'}: {config['entity']}",
        "items": [
            f"{'Asegurar que la entidad' if es else 'Ensure entity'} {config['entity']} {'esté habilitada en el modelo de datos' if es else 'is enabled in the data model'}",
            f"{'Configurar campos requeridos en Manage Business Configuration' if es else 'Configure required fields in Manage Business Configuration'}",
        ],
    })

    # Section 2: Required fields
    field_items = []
    for f in config["required_fields"]:
        if f.get("type") == "key":
            continue
        label = f.get("label", f["field"])
        desc = f.get("description", "")
        picklist_note = f" (Picklist: {f['picklist']})" if f.get("picklist") else ""
        field_items.append(f"{label} ({f['field']}): {desc}{picklist_note}")

    sections.append({
        "title": "Campos Requeridos" if es else "Required Fields",
        "content": f"{len(field_items)} {'campos country-specific requeridos' if es else 'country-specific fields required'}",
        "items": field_items,
    })

    # Section 3: Picklists
    sections.append({
        "title": "Picklists a Configurar" if es else "Picklists to Configure",
        "content": f"{len(config['common_picklists'])} {'picklists necesarias' if es else 'picklists needed'}",
        "items": [f"{'Crear/verificar picklist' if es else 'Create/verify picklist'}: {pl}" for pl in config["common_picklists"]],
    })

    # Section 4: Compliance
    sections.append({
        "title": "Requisitos de Cumplimiento" if es else "Compliance Requirements",
        "items": config["compliance_notes"],
    })

    # Section 5: Business rules
    sections.append({
        "title": "Reglas de Negocio Recomendadas" if es else "Recommended Business Rules",
        "items": config["typical_rules"],
    })

    # Section 6: Validation checklist
    sections.append({
        "title": "Checklist de Validación" if es else "Validation Checklist",
        "items": [
            f"{'Verificar que todos los campos requeridos están visibles en el portlet' if es else 'Verify all required fields are visible in the portlet'}",
            f"{'Verificar que los picklists tienen los valores correctos' if es else 'Verify picklists have correct values'}",
            f"{'Ejecutar validate_country_compliance para verificar datos existentes' if es else 'Run validate_country_compliance to verify existing data'}",
            f"{'Probar reglas de negocio con empleados de prueba' if es else 'Test business rules with test employees'}",
            f"{'Verificar reportes legales/fiscales generan correctamente' if es else 'Verify legal/tax reports generate correctly'}",
        ],
    })

    return {
        "title": f"{'Guía de Configuración' if es else 'Configuration Guide'}: {config['name']} ({country_code.upper()})",
        "country_code": country_code.upper(),
        "country_name": config["name"],
        "generated_date": today,
        "entity": config["entity"],
        "total_sections": len(sections),
        "sections": sections,
    }
