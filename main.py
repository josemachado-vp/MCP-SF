"""
SAP SuccessFactors Assistant MCP Server.

Provides 53 tools organized in thirteen categories for SF consultants
and implementors:

- Discovery (4): Entity metadata, picklists, OData queries
- Business Rules (4): Validation, spec generation, docs, tests
- Employee (5): Search, profiles, org charts, history, comparison
- Organization (3): Org structure, positions, foundation objects
- Configuration (2): Business rules listing, permission roles
- Data Import (3): Template validation, generation, upsert
- Analytics (3): Headcount, compensation stats, rule simulation
- Instance Compare (4): Metadata, picklists, rules, FO comparison
- Audit (5): Data integrity, anomalies, rule tracing, permissions, effective dating
- Documentation (4): Functional specs, cutover checklists, data dictionaries, test scripts
- Migration (4): File validation, load sequencing, reconciliation, purge files
- MDF (3): Object definitions, import templates, object inventory
- Go-Live (2): Pre-go-live checks, reconciliation reports
- Country (3): Country fields, compliance validation, config guides
- Workbook Generator (3): Foundation Objects, Workflow Notifications, Employee Central Rules

Usage:
    uv run python main.py
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastmcp import FastMCP

# --- Discovery ---
from tools.discovery import (
    get_entity_metadata,
    list_entities,
    get_picklist_values,
    query_odata,
)

# --- Business Rules ---
from tools.rule_generation import (
    validate_rule_fields,
    generate_rule_spec,
)
from tools.rule_documentation import (
    generate_rule_doc,
    generate_rule_test,
)

# --- Employee ---
from tools.employee import (
    search_employees,
    get_employee_profile,
    get_org_chart,
    get_employee_history,
    compare_employees,
)

# --- Organization ---
from tools.organization import (
    get_org_structure,
    get_position_details,
    list_foundation_objects,
)

# --- Configuration ---
from tools.configuration import (
    list_business_rules,
    get_permission_roles,
)

# --- Data Import ---
from tools.data_import import (
    validate_import_template,
    generate_import_template,
    execute_upsert,
)

# --- Analytics ---
from tools.analytics import (
    get_headcount,
    get_compensation_analytics,
    simulate_rule_impact,
)

# --- Instance Compare ---
from tools.instance_compare import (
    compare_instance_config,
    compare_picklists,
    compare_business_rules,
    compare_foundation_objects,
)

# --- Audit & Troubleshooting ---
from tools.audit import (
    audit_employee_data,
    find_data_anomalies,
    trace_rule_execution,
    check_permission_access,
    validate_effective_dating,
)

# --- Documentation ---
from tools.documentation import (
    generate_functional_spec,
    generate_cutover_checklist,
    generate_data_dictionary,
    generate_test_script,
)

# --- Migration ---
from tools.migration import (
    validate_migration_file,
    generate_migration_sequence,
    reconcile_data,
    generate_purge_file,
)

# --- MDF ---
from tools.mdf import (
    get_mdf_object_definition,
    generate_mdf_import_template,
    list_mdf_objects,
)

# --- Go-Live ---
from tools.golive import (
    run_go_live_checks,
    generate_reconciliation_report,
)

# --- Country ---
from tools.country import (
    get_country_specific_fields,
    validate_country_compliance,
    generate_country_config_guide,
)

# --- Workbook Generator ---
from tools.workbook_generator import (
    generate_fo_workbook,
    generate_workflow_workbook,
    generate_rules_workbook,
)


mcp = FastMCP(
    name="SF Assistant MCP",
    instructions=(
        "This server provides 53 tools for SAP SuccessFactors consultants and implementors. "
        "It covers employee data queries, organizational structure, business rules, "
        "data import, analytics, instance comparison, auditing, documentation generation, "
        "migration tooling, MDF objects, go-live validation, multi-country support, and workbook generation.\n\n"
        "Tool categories:\n\n"
        "**Discovery** (explore SF metadata):\n"
        "1. get_entity_metadata - Explore fields on an entity\n"
        "2. list_entities - List all OData entities\n"
        "3. get_picklist_values - Check valid picklist values\n"
        "4. query_odata - Execute flexible OData queries\n\n"
        "**Business Rules** (generate and validate rules):\n"
        "5. validate_rule_fields - Validate fields exist\n"
        "6. generate_rule_spec - Generate rule specification\n"
        "7. generate_rule_doc - Create implementation guide\n"
        "8. generate_rule_test - Create test case matrix\n\n"
        "**Employee** (search and explore employee data):\n"
        "9. search_employees - Natural language employee search\n"
        "10. get_employee_profile - Complete employee profile\n"
        "11. get_org_chart - Organizational chart\n"
        "12. get_employee_history - Employment history\n"
        "13. compare_employees - Side-by-side comparison\n\n"
        "**Organization** (structure and reference data):\n"
        "14. get_org_structure - Org hierarchy by level\n"
        "15. get_position_details - Position management\n"
        "16. list_foundation_objects - Any Foundation Object\n\n"
        "**Configuration** (system config):\n"
        "17. list_business_rules - Rules in the instance\n"
        "18. get_permission_roles - Permission roles\n\n"
        "**Data Import** (import and upsert):\n"
        "19. validate_import_template - Validate headers\n"
        "20. generate_import_template - Generate CSV template\n"
        "21. execute_upsert - Upsert records (dry_run default)\n\n"
        "**Analytics** (reporting and simulation):\n"
        "22. get_headcount - Headcount by group\n"
        "23. get_compensation_analytics - Compensation stats\n"
        "24. simulate_rule_impact - Rule what-if simulation\n\n"
        "**Instance Comparison** (DEV vs QA vs PROD):\n"
        "25. compare_instance_config - Compare entity metadata\n"
        "26. compare_picklists - Compare picklist values\n"
        "27. compare_business_rules - Compare rules\n"
        "28. compare_foundation_objects - Compare FOs\n\n"
        "**Audit & Troubleshooting**:\n"
        "29. audit_employee_data - Data integrity checks\n"
        "30. find_data_anomalies - Detect anomalies\n"
        "31. trace_rule_execution - Rule execution tracing\n"
        "32. check_permission_access - Permission lookup\n"
        "33. validate_effective_dating - Date gap/overlap detection\n\n"
        "**Documentation**:\n"
        "34. generate_functional_spec - Functional specification\n"
        "35. generate_cutover_checklist - Cutover checklist\n"
        "36. generate_data_dictionary - Data dictionary\n"
        "37. generate_test_script - End-to-end test scripts\n\n"
        "**Migration**:\n"
        "38. validate_migration_file - Deep file validation\n"
        "39. generate_migration_sequence - Load order calculation\n"
        "40. reconcile_data - Post-migration reconciliation\n"
        "41. generate_purge_file - Purge file generation\n\n"
        "**MDF Objects**:\n"
        "42. get_mdf_object_definition - MDF object metadata\n"
        "43. generate_mdf_import_template - MDF import template\n"
        "44. list_mdf_objects - Inventory MDF objects\n\n"
        "**Go-Live**:\n"
        "45. run_go_live_checks - Pre-go-live validation\n"
        "46. generate_reconciliation_report - Reconciliation report\n\n"
        "**Country Support** (LATAM focus):\n"
        "47. get_country_specific_fields - Country fields & requirements\n"
        "48. validate_country_compliance - Compliance validation\n"
        "49. generate_country_config_guide - Configuration guide\n\n"
        "**Workbook Generator** (populate client Excel workbooks from live SF data):\n"
        "50. generate_fo_workbook - Populate Object & Picklist Data workbook (28 sheets)\n"
        "51. generate_workflow_workbook - Populate Workflow Notifications workbook (8 sheets)\n"
        "52. generate_rules_workbook - Populate Employee Central Rules sheet\n\n"
        "Typical workflows:\n"
        "- Employee queries: search_employees → get_employee_profile\n"
        "- Rules: get_entity_metadata → validate_rule_fields → generate_rule_spec\n"
        "- Import: generate_import_template → validate_migration_file → execute_upsert\n"
        "- Cutover: compare_instance_config → generate_cutover_checklist → run_go_live_checks\n"
        "- Country setup: get_country_specific_fields → generate_country_config_guide → validate_country_compliance"
    ),
)

# Register all tools on the main server

# Discovery
mcp.add_tool(get_entity_metadata)
mcp.add_tool(list_entities)
mcp.add_tool(get_picklist_values)
mcp.add_tool(query_odata)

# Business Rules
mcp.add_tool(validate_rule_fields)
mcp.add_tool(generate_rule_spec)
mcp.add_tool(generate_rule_doc)
mcp.add_tool(generate_rule_test)

# Employee
mcp.add_tool(search_employees)
mcp.add_tool(get_employee_profile)
mcp.add_tool(get_org_chart)
mcp.add_tool(get_employee_history)
mcp.add_tool(compare_employees)

# Organization
mcp.add_tool(get_org_structure)
mcp.add_tool(get_position_details)
mcp.add_tool(list_foundation_objects)

# Configuration
mcp.add_tool(list_business_rules)
mcp.add_tool(get_permission_roles)

# Data Import
mcp.add_tool(validate_import_template)
mcp.add_tool(generate_import_template)
mcp.add_tool(execute_upsert)

# Analytics
mcp.add_tool(get_headcount)
mcp.add_tool(get_compensation_analytics)
mcp.add_tool(simulate_rule_impact)

# Instance Compare
mcp.add_tool(compare_instance_config)
mcp.add_tool(compare_picklists)
mcp.add_tool(compare_business_rules)
mcp.add_tool(compare_foundation_objects)

# Audit & Troubleshooting
mcp.add_tool(audit_employee_data)
mcp.add_tool(find_data_anomalies)
mcp.add_tool(trace_rule_execution)
mcp.add_tool(check_permission_access)
mcp.add_tool(validate_effective_dating)

# Documentation
mcp.add_tool(generate_functional_spec)
mcp.add_tool(generate_cutover_checklist)
mcp.add_tool(generate_data_dictionary)
mcp.add_tool(generate_test_script)

# Migration
mcp.add_tool(validate_migration_file)
mcp.add_tool(generate_migration_sequence)
mcp.add_tool(reconcile_data)
mcp.add_tool(generate_purge_file)

# MDF
mcp.add_tool(get_mdf_object_definition)
mcp.add_tool(generate_mdf_import_template)
mcp.add_tool(list_mdf_objects)

# Go-Live
mcp.add_tool(run_go_live_checks)
mcp.add_tool(generate_reconciliation_report)

# Country
mcp.add_tool(get_country_specific_fields)
mcp.add_tool(validate_country_compliance)
mcp.add_tool(generate_country_config_guide)

# Workbook Generator
mcp.add_tool(generate_fo_workbook)
mcp.add_tool(generate_workflow_workbook)
mcp.add_tool(generate_rules_workbook)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)
