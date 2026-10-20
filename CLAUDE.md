# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Server for SAP SuccessFactors — a complete SF assistant. Built with FastMCP (Python), it exposes **52 tools across 15 categories** registered in `main.py`:

| Category | File | Count | Purpose |
|---|---|:---:|---|
| **Discovery** | `tools/discovery.py` | 4 | Entity metadata, picklist values, OData queries |
| **Business Rules** | `tools/rule_generation.py`, `tools/rule_documentation.py` | 4 | Validate fields, generate rule specs, implementation docs, test matrices |
| **Employee** | `tools/employee.py` | 5 | NL search, profiles, org charts, history, side-by-side comparison |
| **Organization** | `tools/organization.py` | 3 | Org structure by level, position details, foundation objects |
| **Configuration** | `tools/configuration.py` | 2 | List business rules, permission roles |
| **Data Import** | `tools/data_import.py` | 3 | Validate templates, generate templates, upsert (dry_run by default) |
| **Analytics** | `tools/analytics.py` | 3 | Headcount, compensation stats, what-if rule simulation |
| **Instance Comparison** | `tools/instance_compare.py` | 4 | DEV/QA/PROD diff for metadata, picklists, rules, FOs |
| **Audit & Troubleshooting** | `tools/audit.py` | 5 | Data integrity, anomalies, rule tracing, permission lookup, effective dating |
| **Documentation** | `tools/documentation.py` | 4 | Functional specs, cutover checklists, data dictionaries, test scripts |
| **Migration** | `tools/migration.py` | 4 | File validation, load sequencing, reconciliation, purge files |
| **MDF** | `tools/mdf.py` | 3 | MDF object definitions, import templates, inventory |
| **Go-Live** | `tools/golive.py` | 2 | Pre-go-live checks, reconciliation reports |
| **Country** | `tools/country.py` | 3 | Country fields, compliance validation, config guides |
| **Workbook Generator** | `tools/workbook_generator.py` | 3 | Populate FO, Workflow, and Rules client workbooks from live SF data |

> **Default tenant:** This project ships configured against the **VPMC Sandbox** tenant (`VPMCSandbox` company ID on `api8preview.sapsf.com`). See `README.md` and `.env.example` for credential details.

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Install with dev dependencies
uv sync --dev

# Install with GCP optional dependencies (GCPSecretManagerStore backend)
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

`main.py` creates a single `FastMCP` server instance named "SF Assistant MCP" and registers all 52 tools directly on it (not as sub-servers). Tools are imported as functions from the 16 files in `tools/` and added via `mcp.add_tool()`. The server's top-level `instructions` string lists every tool by number — keep it in sync when adding/removing tools. Supports `MCP_TRANSPORT` env var for stdio (default) or SSE transport.

### Tool Categories & Workflows

| Goal | Pipeline |
|---|---|
| Build a business rule | `get_entity_metadata` → `validate_rule_fields` → `generate_rule_spec` → `generate_rule_doc` / `generate_rule_test` |
| Find / inspect employees | `search_employees` → `get_employee_profile` → `get_org_chart` |
| Run an import | `generate_import_template` → `validate_migration_file` → `execute_upsert` |
| Cutover prep | `compare_instance_config` → `generate_cutover_checklist` → `run_go_live_checks` |
| Country setup (LATAM focus) | `get_country_specific_fields` → `generate_country_config_guide` → `validate_country_compliance` |
| Populate client workbooks | `generate_fo_workbook` / `generate_workflow_workbook` / `generate_rules_workbook` |
| Org exploration | `get_org_structure` → `list_foundation_objects` / `get_position_details` |
| Analytics | `get_headcount` / `get_compensation_analytics` / `simulate_rule_impact` |

### Credential Resolution (`helpers/credentials.py`)

OIDC 2-step flow via SAP IAS (Identity Authentication Service):

1. **Step 1** — Password grant → `id_token`
2. **Step 2** — `urn:ietf:params:oauth:grant-type:jwt-bearer` exchange with the `id_token` and `resource=urn:sap:identity:application:provider:name:{IAS_DEPENDENCY_NAME}` → SF `access_token`

Tokens are cached in `_token_cache` with a 60-second pre-expiry buffer, keyed by the **effective identity** `(ias_host, client_id, user_id, password fingerprint, api_host)` resolved *before* lookup, with a per-key `asyncio.Lock` + double-check so concurrent callers share one IAS round-trip. Tools accept `data_center`, `auth_user_id`, `auth_password` as per-request overrides on top of the `.env` defaults, and must pass `api_host=api_host` to `get_bearer_token`.

`data_center` (and `resolve_api_host`) only accept DC codes, the configured `SF_API_HOST`, or hosts in the optional `SF_ALLOWED_HOSTS` env var (`helpers/sf_client.resolve_sf_base_url`); anything else raises `ValueError` before a token is sent. The web backend (`backend/tool_registry.HIDDEN_PARAMS`) hides host/credential overrides from Gemini and strips them from model-supplied args.

Required env vars (all enforced — `ValueError` lists missing ones):
`SF_API_HOST`, `SF_COMPANY_ID`, `SF_USER_ID`, `SF_PASSWORD`, `IAS_HOST`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `IAS_DEPENDENCY_NAME`.

### Credential Store (`helpers/credential_store.py`)

Pluggable credential storage abstraction:
- `EnvCredentialStore` — reads from env vars (default, backwards-compatible)
- `GCPSecretManagerStore` — reads from Google Cloud Secret Manager (requires `uv sync --extra gcp`)

### SF Client (`helpers/sf_client.py`)

Async HTTP client wrapping `httpx.AsyncClient`. Handles data center resolution (DC codes like `DC4`, `DC8_PREVIEW`, or allowlisted hosts/URLs), Bearer token auth via `get_bearer_token()`, and provides `get_metadata` (XML), `query_odata` (JSON), `get_picklist`, `post_odata`, `put_odata`, `upsert_odata`. Default timeout 60 s (90 s for full `$metadata`).

### NL Query Parser (`helpers/nl_query_parser.py`)

Pattern-matching based natural language → OData `$filter` parser (no LLM). Converts queries like *"employees in department 40000013"* into OData filter expressions. Uses `knowledge/entity_mapping.json` for entity resolution, country codes, and status codes.

### Template Parser (`helpers/template_parser.py`)

Parses CSV and Excel (openpyxl) import templates into headers + rows. Validates headers against SF entity metadata.

### Metadata Parser (`helpers/metadata_parser.py`)

Parses OData EDMX/CSDL XML into structured dicts. Extracts entity types, properties with SAP-specific annotations (`sap:label`, `sap:creatable`, `sap:updatable`, etc.), navigation properties, and resolves association targets.

### PII Filter (`helpers/pii_filter.py`)

PII validation + redaction driven by `knowledge/pii_classification.json`. **Enforced centrally in `SFClient.query_odata`**: every query runs `validate_query` first (raises `PIIPolicyError`, no HTTP call, when blocked) and the JSON response goes through the recursive `scrub_payload` (nested dicts, expanded navigations, `results` lists); removed field names come back under the top-level `pii_redacted_fields` key. Every `/` segment of `$select`/`$expand` is checked, `$filter` identifiers are matched exactly (string literals ignored), and entity names must match `^[A-Za-z_][A-Za-z0-9_]*$`. Tools must go through `SFClient` — never call `httpx` directly for OData. Tested in `tests/test_pii_filter.py` and `tests/test_sf_client.py`.

### OData Utils (`helpers/odata_utils.py`)

Shared OData helpers: filter-string escaping, pagination handling, common date-filter builders for effective-dated entities.

### Knowledge Base (`knowledge/`)

Static JSON files:
- `entity_mapping.json` — Complete entity catalog with categories, NL hints, effective-dating templates, status/country codes
- `workbook_entity_mapping.json` — Workbook → SF entity column mappings used by the workbook generator
- `base_objects.json` — Base objects → primary OData entities and common fields (TimeAccount, Position, PerGlobalInfo, etc.)
- `rule_scenarios.json` — Standard SF rule scenarios
- `event_types.json` — Event type metadata (`onSave`, `onChange`, `onInit`, `validate`)
- `best_practices.json` — SAP best practices for rule configuration
- `pii_classification.json` — Field-level PII classification consumed by `pii_filter.py`

### Models (`models/`)

Pydantic v2 models organized by domain:
- `rule_spec.py` — `RuleSpec`, `RuleCondition`, `RuleAction`, `ExecutionNotes`
- `field_validation.py` — `FieldValidationResult`, `ValidationReport`, `TestCase`, `TestMatrix`
- `employee.py` — `EmployeeProfile`, `OrgNode`, `EmployeeComparison`, `EmployeeHistoryRecord`
- `organization.py` — `FoundationObject`, `OrgUnit`, `PositionDetail`
- `data_import.py` — `ImportFieldValidation`, `ImportValidationReport`, `UpsertRecord`, `UpsertResult`

### Scripts (`scripts/`)

Operational scripts (NOT MCP tools — run directly with `uv run python scripts/<name>.py`):
- `generate_pptx.py` — Generate PPTX deliverables
- `generate_word_doc.py` — Generate Word docs
- `validate_workbooks.py` — Validate filled client workbooks before delivery

## Key Conventions

- Python 3.10+, managed with `uv`
- All SF API calls are async (`httpx.AsyncClient`) with `asyncio.Semaphore(5)` for rate limiting
- Each tool module may build a local `FastMCP` for testing, but `main.py` is the **single registration point** exposed to MCP clients
- Tests use pytest + pytest-asyncio; HTTP mocking with `respx` (no live tenant required)
- `python-dotenv` loads `.env` automatically via `helpers/credentials.py`
- Effective-dated entities (`EmpJob`, `EmpCompensation`, `PerPersonal`) require date filters
- `execute_upsert` defaults to `dry_run=True` for safety
- OData v2 lacks `$apply` / groupby — analytics aggregate client-side with `$top` limits
- Condition types in rule specs: `IF`, `ELSE_IF`, `AND_IF`, `OR_IF`
- Action types: `SET_FIELD`, `RAISE_MESSAGE`, `SET_FIELD_PROPERTY`, `TRIGGER_WORKFLOW`
- `.env` is gitignored — never commit it. New engineers copy `.env.example` and ask the functional lead for VPMC Sandbox secrets.

## Monorepo Context

This project lives inside the **`Jose_Avengers`** monorepo at Veritas Prime as `Jose_Avengers/sf-mcp-server/`. Sibling projects (e.g. `data-toolkit/`) are independent — do not hoist dependencies, configs, or docs to the monorepo root.

When adding a new tool:
1. Implement it inside the relevant `tools/<category>.py` (or create a new file for a new category).
2. Import it in `main.py` and call `mcp.add_tool(<fn>)`.
3. Add it to the numbered list inside the `instructions=...` string in `main.py` (clients use that for tool discovery hints).
4. Update the tool count in this file's overview table and in `README.md`.
5. Add tests under `tests/`.
