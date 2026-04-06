"""
Instance comparison tools for SAP SuccessFactors.

Compares metadata, picklists, business rules, and Foundation Objects
between two SF instances (e.g., DEV vs QA vs PROD).

All operations are read-only.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import httpx
from fastmcp import FastMCP

from helpers.sf_client import SFClient
from helpers.credentials import resolve_api_host, get_bearer_token
from helpers.metadata_parser import parse_metadata_xml

instance_compare_mcp = FastMCP(name="SF Instance Compare Tools")

_SF_SEMAPHORE = asyncio.Semaphore(5)


async def _get_client_and_token(
    http: httpx.AsyncClient,
    data_center: str,
    user_id: Optional[str],
    password: Optional[str],
    tenant_id: str,
) -> tuple[SFClient, str, str]:
    """Resolve host and get token for an instance."""
    api_host = resolve_api_host(data_center)
    token = await get_bearer_token(http, user_id, password, tenant_id=tenant_id)
    return SFClient(http), token, api_host


async def _sf_query(sf, api_host, token, entity, params):
    async with _SF_SEMAPHORE:
        return await sf.query_odata(data_center=api_host, bearer_token=token, entity=entity, params=params)


@instance_compare_mcp.tool
async def compare_instance_config(
    entity: Annotated[str, "Entity to compare (e.g., 'EmpJob', 'User', 'FOCompany')"],
    instance_a_dc: Annotated[str, "Data center or API host for instance A (e.g., 'api8preview.sapsf.com')"],
    instance_b_dc: Annotated[str, "Data center or API host for instance B"],
    instance_a_user: Annotated[Optional[str], "User ID for instance A. Uses .env default if omitted."] = None,
    instance_a_password: Annotated[Optional[str], "Password for instance A. Uses .env default if omitted."] = None,
    instance_b_user: Annotated[Optional[str], "User ID for instance B. Uses .env default if omitted."] = None,
    instance_b_password: Annotated[Optional[str], "Password for instance B. Uses .env default if omitted."] = None,
) -> dict:
    """
    Compare entity metadata between two SF instances.

    Detects fields that exist in one instance but not the other,
    type mismatches, and annotation differences (editability, labels).
    Essential for cutover validation (DEV → QA → PROD).
    """
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as http:
        sf_a, token_a, host_a = await _get_client_and_token(http, instance_a_dc, instance_a_user, instance_a_password, "instance_a")
        sf_b, token_b, host_b = await _get_client_and_token(http, instance_b_dc, instance_b_user, instance_b_password, "instance_b")

        xml_a, xml_b = await asyncio.gather(
            sf_a.get_metadata(data_center=host_a, bearer_token=token_a, entity=entity),
            sf_b.get_metadata(data_center=host_b, bearer_token=token_b, entity=entity),
        )

    parsed_a = parse_metadata_xml(xml_a)
    parsed_b = parse_metadata_xml(xml_b)

    entity_a = parsed_a["entities"].get(entity, {})
    entity_b = parsed_b["entities"].get(entity, {})

    props_a = entity_a.get("properties", {})
    props_b = entity_b.get("properties", {})

    fields_a = set(props_a.keys())
    fields_b = set(props_b.keys())

    only_in_a = sorted(fields_a - fields_b)
    only_in_b = sorted(fields_b - fields_a)
    common = fields_a & fields_b

    differences = []
    for field in sorted(common):
        pa = props_a[field]
        pb = props_b[field]
        diffs = {}
        if pa.get("type") != pb.get("type"):
            diffs["type"] = {"a": pa.get("type"), "b": pb.get("type")}
        if pa.get("label") != pb.get("label"):
            diffs["label"] = {"a": pa.get("label"), "b": pb.get("label")}
        if pa.get("creatable") != pb.get("creatable"):
            diffs["creatable"] = {"a": pa.get("creatable"), "b": pb.get("creatable")}
        if pa.get("updatable") != pb.get("updatable"):
            diffs["updatable"] = {"a": pa.get("updatable"), "b": pb.get("updatable")}
        if diffs:
            differences.append({"field": field, **diffs})

    return {
        "entity": entity,
        "instance_a": instance_a_dc,
        "instance_b": instance_b_dc,
        "fields_only_in_a": only_in_a,
        "fields_only_in_b": only_in_b,
        "field_differences": differences,
        "matching_fields": len(common) - len(differences),
        "total_fields_a": len(fields_a),
        "total_fields_b": len(fields_b),
        "summary": f"{len(only_in_a)} only in A, {len(only_in_b)} only in B, {len(differences)} differ, {len(common) - len(differences)} match",
    }


@instance_compare_mcp.tool
async def compare_picklists(
    picklist_id: Annotated[str, "Picklist ID to compare (e.g., 'eventReason', 'employeeClass')"],
    instance_a_dc: Annotated[str, "Data center or API host for instance A"],
    instance_b_dc: Annotated[str, "Data center or API host for instance B"],
    instance_a_user: Annotated[Optional[str], "User ID for instance A"] = None,
    instance_a_password: Annotated[Optional[str], "Password for instance A"] = None,
    instance_b_user: Annotated[Optional[str], "User ID for instance B"] = None,
    instance_b_password: Annotated[Optional[str], "Password for instance B"] = None,
) -> dict:
    """
    Compare picklist values between two SF instances.

    Detects values that exist in one instance but not the other,
    and label differences for matching values. Critical for ensuring
    picklist consistency during migrations.
    """
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        sf_a, token_a, host_a = await _get_client_and_token(http, instance_a_dc, instance_a_user, instance_a_password, "instance_a")
        sf_b, token_b, host_b = await _get_client_and_token(http, instance_b_dc, instance_b_user, instance_b_password, "instance_b")

        result_a, result_b = await asyncio.gather(
            sf_a.get_picklist(data_center=host_a, bearer_token=token_a, picklist_id=picklist_id),
            sf_b.get_picklist(data_center=host_b, bearer_token=token_b, picklist_id=picklist_id),
        )

    def _extract_options(result):
        options = {}
        for pl in result.get("d", {}).get("results", []):
            for opt in pl.get("picklistOptions", {}).get("results", []):
                code = opt.get("externalCode", "")
                if code:
                    options[code] = {
                        "label": opt.get("optionValue", "") or opt.get("label", ""),
                        "status": opt.get("status", ""),
                    }
        return options

    opts_a = _extract_options(result_a)
    opts_b = _extract_options(result_b)

    codes_a = set(opts_a.keys())
    codes_b = set(opts_b.keys())

    only_in_a = [{"code": c, **opts_a[c]} for c in sorted(codes_a - codes_b)]
    only_in_b = [{"code": c, **opts_b[c]} for c in sorted(codes_b - codes_a)]

    label_diffs = []
    for code in sorted(codes_a & codes_b):
        if opts_a[code]["label"] != opts_b[code]["label"]:
            label_diffs.append({
                "code": code,
                "label_a": opts_a[code]["label"],
                "label_b": opts_b[code]["label"],
            })

    return {
        "picklist_id": picklist_id,
        "instance_a": instance_a_dc,
        "instance_b": instance_b_dc,
        "values_only_in_a": only_in_a,
        "values_only_in_b": only_in_b,
        "label_differences": label_diffs,
        "matching_values": len((codes_a & codes_b)) - len(label_diffs),
        "total_values_a": len(codes_a),
        "total_values_b": len(codes_b),
    }


@instance_compare_mcp.tool
async def compare_business_rules(
    rule_name: Annotated[Optional[str], "Rule name to search for (substring match). If None, compares all rules."] = None,
    instance_a_dc: Annotated[str, "Data center or API host for instance A"] = "",
    instance_b_dc: Annotated[str, "Data center or API host for instance B"] = "",
    instance_a_user: Annotated[Optional[str], "User ID for instance A"] = None,
    instance_a_password: Annotated[Optional[str], "Password for instance A"] = None,
    instance_b_user: Annotated[Optional[str], "User ID for instance B"] = None,
    instance_b_password: Annotated[Optional[str], "Password for instance B"] = None,
) -> dict:
    """
    Compare business rules between two SF instances.

    Shows rules that exist in one instance but not the other, and
    differences in rule properties (scenario, base object, status).
    Essential for cutover validation.
    """
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        sf_a, token_a, host_a = await _get_client_and_token(http, instance_a_dc, instance_a_user, instance_a_password, "instance_a")
        sf_b, token_b, host_b = await _get_client_and_token(http, instance_b_dc, instance_b_user, instance_b_password, "instance_b")

        params: dict[str, str] = {"$top": "500"}
        if rule_name:
            params["$filter"] = f"substringof('{rule_name}', ruleName)"

        async with _SF_SEMAPHORE:
            result_a = await sf_a.query_odata(data_center=host_a, bearer_token=token_a, entity="RuleHeaderBean", params=params)
        async with _SF_SEMAPHORE:
            result_b = await sf_b.query_odata(data_center=host_b, bearer_token=token_b, entity="RuleHeaderBean", params=params)

    rules_a = {r.get("ruleName", ""): r for r in result_a.get("d", {}).get("results", []) if r.get("ruleName")}
    rules_b = {r.get("ruleName", ""): r for r in result_b.get("d", {}).get("results", []) if r.get("ruleName")}

    names_a = set(rules_a.keys())
    names_b = set(rules_b.keys())

    only_in_a = [{"ruleName": n, "scenario": rules_a[n].get("ruleScenario", ""), "baseObject": rules_a[n].get("baseObject", "")} for n in sorted(names_a - names_b)]
    only_in_b = [{"ruleName": n, "scenario": rules_b[n].get("ruleScenario", ""), "baseObject": rules_b[n].get("baseObject", "")} for n in sorted(names_b - names_a)]

    differences = []
    compare_fields = ["ruleScenario", "baseObject", "ruleStatus"]
    for name in sorted(names_a & names_b):
        diffs = {}
        for f in compare_fields:
            va = rules_a[name].get(f, "")
            vb = rules_b[name].get(f, "")
            if str(va) != str(vb):
                diffs[f] = {"a": va, "b": vb}
        if diffs:
            differences.append({"ruleName": name, **diffs})

    return {
        "instance_a": instance_a_dc,
        "instance_b": instance_b_dc,
        "rules_only_in_a": only_in_a,
        "rules_only_in_b": only_in_b,
        "rule_differences": differences,
        "matching_rules": len(names_a & names_b) - len(differences),
        "total_rules_a": len(names_a),
        "total_rules_b": len(names_b),
    }


@instance_compare_mcp.tool
async def compare_foundation_objects(
    fo_type: Annotated[str, "Foundation Object type: 'company', 'department', 'division', 'location', 'cost_center', 'job_code', 'pay_grade' or entity name"],
    instance_a_dc: Annotated[str, "Data center or API host for instance A"] = "",
    instance_b_dc: Annotated[str, "Data center or API host for instance B"] = "",
    instance_a_user: Annotated[Optional[str], "User ID for instance A"] = None,
    instance_a_password: Annotated[Optional[str], "Password for instance A"] = None,
    instance_b_user: Annotated[Optional[str], "User ID for instance B"] = None,
    instance_b_password: Annotated[Optional[str], "Password for instance B"] = None,
) -> dict:
    """
    Compare Foundation Objects between two SF instances.

    Detects FO records that exist in one instance but not the other,
    and field differences for matching records (by externalCode).
    """
    fo_map = {
        "company": "FOCompany", "division": "FODivision", "department": "FODepartment",
        "business_unit": "FOBusinessUnit", "cost_center": "FOCostCenter",
        "location": "FOLocation", "job_code": "FOJobCode", "pay_grade": "FOPayGrade",
    }
    entity = fo_map.get(fo_type.lower().replace(" ", "_"), fo_type)

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        sf_a, token_a, host_a = await _get_client_and_token(http, instance_a_dc, instance_a_user, instance_a_password, "instance_a")
        sf_b, token_b, host_b = await _get_client_and_token(http, instance_b_dc, instance_b_user, instance_b_password, "instance_b")

        params: dict[str, str] = {"$top": "1000"}

        async with _SF_SEMAPHORE:
            result_a = await sf_a.query_odata(data_center=host_a, bearer_token=token_a, entity=entity, params=params)
        async with _SF_SEMAPHORE:
            result_b = await sf_b.query_odata(data_center=host_b, bearer_token=token_b, entity=entity, params=params)

    def _key(record):
        return record.get("externalCode", "") or record.get("code", "")

    recs_a = {_key(r): r for r in result_a.get("d", {}).get("results", []) if _key(r)}
    recs_b = {_key(r): r for r in result_b.get("d", {}).get("results", []) if _key(r)}

    codes_a = set(recs_a.keys())
    codes_b = set(recs_b.keys())

    only_in_a = [{"code": c, "name": recs_a[c].get("name", ""), "status": recs_a[c].get("status", "")} for c in sorted(codes_a - codes_b)]
    only_in_b = [{"code": c, "name": recs_b[c].get("name", ""), "status": recs_b[c].get("status", "")} for c in sorted(codes_b - codes_a)]

    differences = []
    compare_fields = ["name", "status", "description"]
    for code in sorted(codes_a & codes_b):
        diffs = {}
        for f in compare_fields:
            va = recs_a[code].get(f, "")
            vb = recs_b[code].get(f, "")
            if str(va) != str(vb):
                diffs[f] = {"a": va, "b": vb}
        if diffs:
            differences.append({"code": code, **diffs})

    return {
        "fo_type": fo_type,
        "entity": entity,
        "instance_a": instance_a_dc,
        "instance_b": instance_b_dc,
        "records_only_in_a": only_in_a,
        "records_only_in_b": only_in_b,
        "record_differences": differences,
        "matching_records": len(codes_a & codes_b) - len(differences),
        "total_records_a": len(codes_a),
        "total_records_b": len(codes_b),
    }
