# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Server for SAP SuccessFactors — a complete SF assistant. Built with FastMCP (Python), it provides 24 tools organized in seven categories:

- **Discovery** (`tools/discovery.py`): Explore SF entity metadata, picklist values, and run OData queries against a live SF instance.
- **Business Rules** (`tools/rule_generation.py`, `tools/rule_documentation.py`): Validate fields, generate rule specifications from natural language, produce step-by-step implementation docs, and create test case matrices.
- **Employee** (`tools/employee.py`): Search employees via natural language, retrieve complete profiles, navigate org charts, view employment history, and compare employees side by side.
- **Organization** (`tools/organization.py`): Explore organizational structure by level, query positions, and list any Foundation Object.
- **Configuration** (`tools/configuration.py`): List business rules and permission roles configured in the instance.
- **Data Import** (`tools/data_import.py`): Validate import templates, generate CSV templates with correct fields, and execute upsert operations (dry_run by default).
- **Analytics** (`tools/analytics.py`): Headcount grouped by any field, compensation statistics, and what-if rule impact simulation.

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Install with dev dependencies
uv sync --dev

# Install with GCP optional dependencies
uv sync --extra gcp

# Run the MCP server (stdio transport, default)
uv run python main.py

# Run with SSE transport
MCP_TRANSPORT=sse uv run python main.py

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_metadata_parser.py

# Run a specific test
uv run pytest tests/test_metadata_parser.py::TestParseMetadataXml::test_extracts_keys -v
```

## Architecture

### Entry Point

`main.py` creates a single `FastMCP` server instance named "SF Assistant MCP" and registers all 24 tools directly on it (not as sub-servers). Tools are imported as functions from the `tools/` modules and added via `mcp.add_tool()`. Supports `MCP_TRANSPORT` env var for stdio (default) or SSE transport.

### Tool Categories & Workflows

**Employee queries:** `search_employees` → `get_employee_profile` / `get_org_chart`
**Org exploration:** `get_org_structure` → `list_foundation_objects` / `get_position_details`
**Business rules:** `get_entity_metadata` → `validate_rule_fields` → `generate_rule_spec` → `generate_rule_doc` / `generate_rule_test`
**Data import:** `generate_import_template` → `validate_import_template` → `execute_upsert`
**Analytics:** `get_headcount` / `get_compensation_analytics` / `simulate_rule_impact`

### Credential Resolution

All tools that call the SF API use `helpers/credentials.py` which implements OIDC 2-step flow via IAS (Identity Authentication Service). Reads defaults from `.env` and allows per-request overrides via tool parameters. Token cache is keyed by tenant_id for multi-tenant support.

### Credential Store (`helpers/credential_store.py`)

Pluggable credential storage abstraction:
- `EnvCredentialStore` — reads from env vars (default, backwards-compatible)
- `GCPSecretManagerStore` — reads from Google Cloud Secret Manager (requires `uv sync --extra gcp`)

### SF Client (`helpers/sf_client.py`)

Async HTTP client wrapping httpx. Handles data center resolution (DC codes like "DC4" or full URLs), Bearer token auth (OIDC), and provides methods for `get_metadata` (XML), `query_odata` (JSON), `get_picklist`, `post_odata`, `put_odata`, and `upsert_odata`.

### NL Query Parser (`helpers/nl_query_parser.py`)

Pattern-matching based natural language → OData filter parser (no LLM). Converts queries like "employees in department 40000013" into OData `$filter` expressions. Uses `knowledge/entity_mapping.json` for entity resolution, country codes, and status codes.

### Template Parser (`helpers/template_parser.py`)

Parses CSV and Excel (openpyxl) import templates into headers + rows. Validates headers against SF entity metadata.

### Metadata Parser (`helpers/metadata_parser.py`)

Parses OData EDMX/CSDL XML into structured dicts. Extracts entity types, properties with SAP-specific annotations (sap:label, sap:creatable, sap:updatable, etc.), navigation properties, and resolves association targets.

### Knowledge Base (`knowledge/`)

Static JSON files:
- `entity_mapping.json` — Complete entity mapping with categories, NL hints, effective-dating templates, status/country codes
- `base_objects.json` — Maps base objects to primary OData entities and common fields (7 base objects including TimeAccount, Position, PerGlobalInfo)
- `rule_scenarios.json` — Standard SF rule scenarios
- `event_types.json` — Event type metadata (onSave, onChange, onInit, validate)
- `best_practices.json` — SAP best practices for rule configuration

### Models (`models/`)

Pydantic v2 models organized by domain:
- `rule_spec.py` — `RuleSpec`, `RuleCondition`, `RuleAction`, `ExecutionNotes`
- `field_validation.py` — `FieldValidationResult`, `ValidationReport`, `TestCase`, `TestMatrix`
- `employee.py` — `EmployeeProfile`, `OrgNode`, `EmployeeComparison`, `EmployeeHistoryRecord`
- `organization.py` — `FoundationObject`, `OrgUnit`, `PositionDetail`
- `data_import.py` — `ImportFieldValidation`, `ImportValidationReport`, `UpsertRecord`, `UpsertResult`

## Key Conventions

- Python 3.10+, managed with `uv`
- All SF API calls are async (httpx.AsyncClient) with `asyncio.Semaphore(5)` for rate limiting
- Each tool module creates its own `FastMCP` instance but tools are registered on the main server in `main.py`
- Tests use pytest + pytest-asyncio; HTTP mocking with `respx`
- The `dotenv` package loads `.env` automatically via `helpers/credentials.py`
- Effective-dated entities (EmpJob, EmpCompensation, PerPersonal) require date filters
- `execute_upsert` defaults to `dry_run=True` for safety
- OData v2 lacks `$apply`/groupby — analytics aggregate client-side with `$top` limits
- Condition types in rule specs: IF, ELSE_IF, AND_IF, OR_IF
- Action types: SET_FIELD, RAISE_MESSAGE, SET_FIELD_PROPERTY, TRIGGER_WORKFLOW
