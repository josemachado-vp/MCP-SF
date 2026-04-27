# SF Assistant MCP Server

MCP (Model Context Protocol) server for SAP SuccessFactors. Provides **52 tools** across 15 categories that let an MCP client (Claude Code, Claude Desktop, etc.) query SF live data, generate business rules, validate imports, run analytics, compare instances, audit data, build cutover checklists, and populate client workbooks — all against a real SF tenant via OData v2.

> **Default tenant:** This project ships configured against the **VPMC Sandbox** tenant (`VPMCSandbox` company ID on `api8preview.sapsf.com`). Every credential in the `.env.example` below is meant for that tenant — for any other tenant ask the functional lead for the right OIDC client and IAS host.

Built with [FastMCP](https://github.com/jlowin/fastmcp) (Python) and [httpx](https://www.python-httpx.org/) for async OData calls.

---

## Prerequisites

- **Python 3.10+**
- [**uv**](https://docs.astral.sh/uv/) package manager
- Credentials for the **VPMC Sandbox** tenant (or whichever tenant you target):
  - SF user with OData API permissions
  - OIDC client registered in IAS with an SF dependency
- An MCP client to consume the server (Claude Code, Claude Desktop, etc.)

---

## Quick Start

```bash
# 1. Clone the monorepo and enter this project
git clone https://github.com/VeritasPrime/Jose_Avengers.git
cd Jose_Avengers/sf-mcp-server

# 2. Install dependencies
uv sync

# 3. Configure credentials
cp .env.example .env       # then edit .env with the values below

# 4. Run the MCP server (stdio transport, default)
uv run python main.py

# Or run with SSE transport
MCP_TRANSPORT=sse uv run python main.py
```

---

## Environment Variables (VPMC Sandbox)

The server reads credentials from `.env` at the project root. Every variable below is **required** — `helpers/credentials.py` raises `ValueError` listing the missing ones if any is empty.

| Variable | Required | Description | VPMC Sandbox value |
|---|:---:|---|---|
| `SF_API_HOST` | ✅ | SF API host (full URL or DC code) | `https://api8preview.sapsf.com` |
| `SF_COMPANY_ID` | ✅ | SF company ID (tenant) | `VPMCSandbox` |
| `SF_USER_ID` | ✅ | IAS username (NOT `user@companyId`) | *(ask team lead)* |
| `SF_PASSWORD` | ✅ | IAS password | *(ask team lead)* |
| `IAS_HOST` | ✅ | IAS tenant host | `abkakgd3p.accounts.ondemand.com` |
| `OIDC_CLIENT_ID` | ✅ | OIDC Client ID registered in IAS | *(ask team lead)* |
| `OIDC_CLIENT_SECRET` | ✅ | OIDC Client Secret from IAS | *(ask team lead)* |
| `IAS_DEPENDENCY_NAME` | ✅ | SF dependency name configured in IAS | `SF_DEPENDENCY` |

**Sample `.env` (VPMC Sandbox skeleton — fill the secrets):**

```env
# --- SF Tenant (VPMC Sandbox) ---
SF_API_HOST=https://api8preview.sapsf.com
SF_COMPANY_ID=VPMCSandbox
SF_USER_ID=<your-ias-user>
SF_PASSWORD=<your-ias-password>

# --- IAS / OIDC ---
IAS_HOST=abkakgd3p.accounts.ondemand.com
OIDC_CLIENT_ID=<oidc-client-id>
OIDC_CLIENT_SECRET=<oidc-client-secret>
IAS_DEPENDENCY_NAME=SF_DEPENDENCY
```

> ⚠️ **Never commit `.env`.** It is already in `.gitignore`. If you target a different tenant (DEV, QA, another sandbox), keep a separate `.env.<tenant>` file outside the repo.

All credentials can also be overridden per-request via tool parameters (`data_center`, `auth_user_id`, `auth_password`) for multi-tenant workflows.

---

## Authentication Flow (OIDC 2-step via IAS)

The server authenticates via SAP IAS (Identity Authentication Service) using the OIDC 2-step flow. See `helpers/credentials.py`:

1. **Step 1 — Password grant:** `POST {IAS_HOST}/oauth2/token` with `grant_type=password`, returns an `id_token`.
2. **Step 2 — JWT-bearer exchange:** `POST {IAS_HOST}/oauth2/token` with `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, the `id_token` as assertion and `resource=urn:sap:identity:application:provider:name:{IAS_DEPENDENCY_NAME}`. Returns the SF `access_token`.
3. The token is **cached per-tenant** with a 60-second safety buffer before expiry. Multi-tenant cache lives in `helpers/credentials._token_cache`.

All subsequent OData calls use `Authorization: Bearer {access_token}`.

---

## Project Structure

```
sf-mcp-server/
├── main.py                     # Entry point — creates FastMCP server, registers 52 tools
├── pyproject.toml              # Project config (uv/hatch)
├── uv.lock                     # Locked dependencies
├── .env                        # Credentials (NOT committed)
├── .mcp.json                   # MCP client config
├── CLAUDE.md                   # Claude Code project instructions
│
├── helpers/                    # Cross-cutting infrastructure
│   ├── credentials.py          # OIDC 2-step flow, token cache (per-tenant)
│   ├── credential_store.py     # Pluggable credential storage (env / GCP Secret Manager)
│   ├── sf_client.py            # Async OData client (DC resolution, Bearer auth, GET/POST/PUT/upsert)
│   ├── metadata_parser.py      # EDMX/CSDL XML → structured dicts (with SAP annotations)
│   ├── nl_query_parser.py      # Natural language → OData $filter (no LLM, pattern-based)
│   ├── template_parser.py      # CSV / Excel template parser for imports
│   ├── odata_utils.py          # OData helpers (escaping, pagination, etc.)
│   └── pii_filter.py           # PII redaction layer for tool outputs
│
├── models/                     # Pydantic v2 models (domain objects)
│   ├── rule_spec.py            # RuleSpec, RuleCondition, RuleAction, ExecutionNotes
│   ├── field_validation.py     # FieldValidationResult, ValidationReport, TestCase, TestMatrix
│   ├── employee.py             # EmployeeProfile, OrgNode, EmployeeComparison, EmployeeHistoryRecord
│   ├── organization.py         # FoundationObject, OrgUnit, PositionDetail
│   └── data_import.py          # ImportFieldValidation, ImportValidationReport, UpsertRecord, UpsertResult
│
├── tools/                      # 52 MCP tools, one file per category
│   ├── discovery.py            # Discovery (4)
│   ├── rule_generation.py      # Business Rules — generation (2)
│   ├── rule_documentation.py   # Business Rules — docs (2)
│   ├── employee.py             # Employee (5)
│   ├── organization.py         # Organization (3)
│   ├── configuration.py        # Configuration (2)
│   ├── data_import.py          # Data Import (3)
│   ├── analytics.py            # Analytics (3)
│   ├── instance_compare.py     # Instance Comparison (4)
│   ├── audit.py                # Audit & Troubleshooting (5)
│   ├── documentation.py        # Documentation (4)
│   ├── migration.py            # Migration (4)
│   ├── mdf.py                  # MDF Objects (3)
│   ├── golive.py               # Go-Live (2)
│   ├── country.py              # Country support (3)
│   └── workbook_generator.py   # Workbook Generator (3)
│
├── knowledge/                  # Static JSON knowledge base
│   ├── entity_mapping.json             # Entity catalog with NL hints, dating templates, codes
│   ├── workbook_entity_mapping.json    # Workbook → SF entity column mappings
│   ├── base_objects.json               # Base objects → primary OData entities
│   ├── rule_scenarios.json             # Standard SF rule scenarios
│   ├── event_types.json                # Event types (onSave, onChange, onInit, validate)
│   ├── best_practices.json             # SAP rule configuration best practices
│   └── pii_classification.json         # Field-level PII classification
│
├── docs/                       # Project documentation
│   ├── MCP_SF_Technical_Documentation.docx
│   ├── MCP_SF_Value_Proposition.md
│   ├── SF_Assistant_MCP_Value_Proposition.docx
│   └── superpowers/            # Specs and implementation plans
│
├── scripts/                    # Operational scripts (not MCP tools)
│   ├── generate_pptx.py
│   ├── generate_word_doc.py
│   └── validate_workbooks.py
│
├── tests/                      # pytest suite (uses respx for HTTP mocking)
│   ├── test_sf_client.py
│   ├── test_metadata_parser.py
│   ├── test_models.py
│   └── test_pii_filter.py
│
└── Workbooks Templates/        # Reference Excel templates from clients
    ├── 1_26 Version_ JVL - Employee Field Data & RBP.xlsx
    ├── 1_26 Version_ JVL - Workflow Notifications & Messages.xlsx
    └── 1_26 Version_JVL - Object & Picklist Data.xlsx
```

---

## Tools Reference (52 tools, 15 categories)

| # | Category | Tools |
|---|---|---|
| **1–4** | **Discovery** | `get_entity_metadata`, `list_entities`, `get_picklist_values`, `query_odata` |
| **5–8** | **Business Rules** | `validate_rule_fields`, `generate_rule_spec`, `generate_rule_doc`, `generate_rule_test` |
| **9–13** | **Employee** | `search_employees`, `get_employee_profile`, `get_org_chart`, `get_employee_history`, `compare_employees` |
| **14–16** | **Organization** | `get_org_structure`, `get_position_details`, `list_foundation_objects` |
| **17–18** | **Configuration** | `list_business_rules`, `get_permission_roles` |
| **19–21** | **Data Import** | `validate_import_template`, `generate_import_template`, `execute_upsert` *(dry_run by default)* |
| **22–24** | **Analytics** | `get_headcount`, `get_compensation_analytics`, `simulate_rule_impact` |
| **25–28** | **Instance Comparison** | `compare_instance_config`, `compare_picklists`, `compare_business_rules`, `compare_foundation_objects` |
| **29–33** | **Audit & Troubleshooting** | `audit_employee_data`, `find_data_anomalies`, `trace_rule_execution`, `check_permission_access`, `validate_effective_dating` |
| **34–37** | **Documentation** | `generate_functional_spec`, `generate_cutover_checklist`, `generate_data_dictionary`, `generate_test_script` |
| **38–41** | **Migration** | `validate_migration_file`, `generate_migration_sequence`, `reconcile_data`, `generate_purge_file` |
| **42–44** | **MDF** | `get_mdf_object_definition`, `generate_mdf_import_template`, `list_mdf_objects` |
| **45–46** | **Go-Live** | `run_go_live_checks`, `generate_reconciliation_report` |
| **47–49** | **Country** | `get_country_specific_fields`, `validate_country_compliance`, `generate_country_config_guide` |
| **50–52** | **Workbook Generator** | `generate_fo_workbook`, `generate_workflow_workbook`, `generate_rules_workbook` |

### Typical Workflows

| Goal | Pipeline |
|---|---|
| Build a business rule | `get_entity_metadata` → `validate_rule_fields` → `generate_rule_spec` → `generate_rule_doc` / `generate_rule_test` |
| Find and inspect employees | `search_employees` → `get_employee_profile` → `get_org_chart` |
| Run an import | `generate_import_template` → `validate_migration_file` → `execute_upsert` |
| Cutover prep | `compare_instance_config` → `generate_cutover_checklist` → `run_go_live_checks` |
| Country setup | `get_country_specific_fields` → `generate_country_config_guide` → `validate_country_compliance` |
| Populate client workbooks | `generate_fo_workbook` / `generate_workflow_workbook` / `generate_rules_workbook` |

---

## MCP Client Configuration

To use the server from Claude Code, add this to `.mcp.json` at the **monorepo root** (or wherever your MCP client reads from):

```json
{
  "mcpServers": {
    "sf-assistant": {
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/absolute/path/to/Jose_Avengers/sf-mcp-server"
    }
  }
}
```

For Claude Desktop, point its `claude_desktop_config.json` at the same command. The server responds on **stdio** by default; set `MCP_TRANSPORT=sse` to expose it over HTTP/SSE instead.

---

## Running Tests

```bash
uv sync --dev          # install dev deps (pytest, pytest-asyncio, respx)
uv run pytest          # run all tests
uv run pytest -v       # verbose
uv run pytest tests/test_pii_filter.py -v   # one file
```

Tests use `respx` to mock httpx calls — no live SF tenant needed.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ValueError: Missing OIDC config: ...` | One or more env vars in `.env` are empty. The error message lists exactly which ones. |
| `ValueError: No API host configured` | `SF_API_HOST` is empty. Set it to a full URL or a DC code (e.g., `DC4`, `DC8_PREVIEW`). |
| `OIDC Step 1 failed (401)` | Wrong `SF_USER_ID` / `SF_PASSWORD`, or user is locked in IAS. |
| `OIDC Step 2 failed (400)` | Wrong `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, or `IAS_DEPENDENCY_NAME`. The IAS dependency name must match exactly the one registered in IAS for the SF app. |
| `httpx.ConnectTimeout` | Network / VPN / firewall blocking IAS or SF API. Default timeouts: 30 s for IAS, 60 s for OData (90 s for full `$metadata`). |
| `403 Forbidden` on OData calls | The SF user lacks OData API permissions on the entity. Check Admin Center → Manage Permission Roles. |
| `Unknown data center 'XXX'` | `SF_API_HOST` is neither a known DC code nor a valid URL. Use a full URL or one of the codes in `helpers/sf_client.py`. |

---

## Conventions

- **Async everywhere.** All SF calls use `httpx.AsyncClient` with `asyncio.Semaphore(5)` for rate limiting.
- **Effective-dated entities** (EmpJob, EmpCompensation, PerPersonal) require date filters — the tools enforce this.
- **`execute_upsert` defaults to `dry_run=True`** for safety; flip explicitly to commit.
- **OData v2** lacks `$apply` / groupby — analytics tools aggregate client-side with `$top` limits.
- **One MCP server only.** Each `tools/<category>.py` may build a local `FastMCP` for testing, but `main.py` is the single registration point exposed to clients.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastmcp` | >= 3.0.0 | MCP server framework |
| `httpx` | >= 0.27.0 | Async HTTP client |
| `pydantic` | >= 2.0.0 | Data models / validation |
| `python-dotenv` | (transitive) | Load `.env` |
| `openpyxl` | (transitive) | Workbook generation / template parsing |

**Optional extras:**
- `uv sync --extra gcp` — adds `google-cloud-secret-manager` for the `GCPSecretManagerStore` credential backend.

**Dev:** `pytest`, `pytest-asyncio`, `respx`.

---

## Ownership

| Role | Person |
|---|---|
| Functional Lead | José Machado |
| Stakeholder | Jabin Geary |
| Repo owner | Ryan Summerskill |
| Engineers | Jose Avengers (4 engineers, India) |

For questions on tools, OIDC setup, or VPMC Sandbox access — ping the functional lead.
