# SF Business Rules MCP Server

MCP (Model Context Protocol) server for SAP SuccessFactors Business Rules. Provides 8 tools to explore SF entity metadata via the OData v2 API, generate validated business rule specifications, produce implementation documentation, and create test case matrices.

Built with [FastMCP](https://github.com/jlowin/fastmcp) (Python) and [httpx](https://www.python-httpx.org/) for async HTTP.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- SAP SuccessFactors instance with OData API access (Basic Auth)

## Quick Start

```bash
# Install dependencies
uv sync

# Configure credentials (see section below)
cp .env.example .env   # then edit .env

# Run the MCP server
uv run python main.py
```

## Environment Variables

Create a `.env` file in the project root with the following variables:

| Variable | Required | Description | Example |
|---|---|---|---|
| `SF_API_HOST` | Yes | API hostname or data center code | `api10preview.sapsf.com` or `DC4` |
| `SF_COMPANY_ID` | Yes | SAP SF company ID | `myCompanyId` |
| `SF_USER_ID` | Yes | API user (without `@companyId`) | `apiuser` |
| `SF_PASSWORD` | Yes | API user password | `secretPassword` |

Example `.env`:

```env
SF_API_HOST=api10preview.sapsf.com
SF_COMPANY_ID=myCompanyId
SF_USER_ID=apiuser
SF_PASSWORD=secretPassword
```

All credentials can also be overridden per-request via tool parameters (`data_center`, `auth_user_id`, `auth_password`).

## Authentication Flow

The server uses **Basic Auth** against the SF OData v2 API. The credential resolution logic (`helpers/credentials.py`) works as follows:

1. Reads defaults from `.env` via `python-dotenv`
2. Builds the auth username as `{SF_USER_ID}@{SF_COMPANY_ID}` (e.g., `apiuser@myCompanyId`)
3. If `SF_API_HOST` is a bare hostname (e.g., `api10preview.sapsf.com`), it prepends `https://`
4. If `SF_API_HOST` is a data center code (e.g., `DC4`), it resolves it to the corresponding API URL

### Supported Data Centers

The client (`helpers/sf_client.py`) maps data center codes to API URLs per SAP KBA 2215682:

| Code | URL |
|---|---|
| DC2 | `https://api2.successfactors.eu` |
| DC4 | `https://api4.successfactors.com` |
| DC5 | `https://api5.successfactors.eu` |
| DC8 | `https://api8.successfactors.com` |
| DC10 | `https://api10.successfactors.com` |
| DC12 | `https://api012.successfactors.eu` |
| DC15 | `https://api15.sapsf.cn` |
| DC16 | `https://api16.sapsf.eu` |
| DC17 | `https://api17.sapsf.com` |
| DC18 | `https://api18.sapsf.com` |
| DC19 | `https://api19.sapsf.com` |
| DC22 | `https://api22.sapsf.com` |
| DC23 | `https://api23.sapsf.com` |
| DC42 | `https://api42.sapsf.com` |
| DC44 | `https://api44.sapsf.com` |

Preview and Sales Demo variants are also supported (e.g., `DC4_PREVIEW`, `DC4_SALESDEMO`).

You can also pass a full URL directly instead of a DC code.

## API Endpoints Used

All HTTP calls go through `helpers/sf_client.py`. The three endpoint patterns are:

| Method | URL Pattern | Used By |
|---|---|---|
| `GET` | `{base}/odata/v2/{entity}/$metadata` | `get_entity_metadata`, `validate_rule_fields`, `generate_rule_spec` |
| `GET` | `{base}/odata/v2/$metadata` | `list_entities` (full metadata, can be slow) |
| `GET` | `{base}/odata/v2/{entity}?$format=json&...` | `query_odata`, `get_picklist_values` |

All requests use:
- `httpx.AsyncClient` with `follow_redirects=True`
- Timeout: 60 seconds (90 seconds for full metadata)
- `Accept: application/xml` for metadata, JSON for queries
- Basic Auth header: `Authorization: Basic base64(user@companyId:password)`

## Project Structure

```
.
├── main.py                     # Entry point — creates FastMCP server, registers 8 tools
├── pyproject.toml              # Project config (uv/hatch)
├── .env                        # Credentials (not committed)
├── .mcp.json                   # MCP client config for Claude Code
│
├── helpers/
│   ├── credentials.py          # Credential resolution (.env + per-request overrides)
│   ├── sf_client.py            # Async HTTP client (DC resolution, Basic Auth, OData calls)
│   └── metadata_parser.py      # EDMX/CSDL XML parser → structured dicts
│
├── models/
│   ├── rule_spec.py            # Pydantic models: RuleSpec, RuleCondition, RuleAction, enums
│   └── field_validation.py     # Pydantic models: FieldValidationResult, TestCase, TestMatrix
│
├── tools/
│   ├── discovery.py            # Tools 1-4: get_entity_metadata, list_entities, get_picklist_values, query_odata
│   ├── rule_generation.py      # Tools 5-6: validate_rule_fields, generate_rule_spec
│   └── rule_documentation.py   # Tools 7-8: generate_rule_doc, generate_rule_test
│
├── knowledge/                  # Static JSON files used by generate_rule_spec
│   ├── base_objects.json       # Maps base objects to OData entities
│   ├── rule_scenarios.json     # Standard SF rule scenarios
│   ├── event_types.json        # Event type metadata (onSave, onChange, etc.)
│   └── best_practices.json     # SAP best practices for rule configuration
│
└── tests/
    ├── test_sf_client.py       # HTTP client tests (mocked with respx)
    ├── test_metadata_parser.py # XML parser tests
    └── test_models.py          # Pydantic model tests
```

## Tools Reference

### Discovery Layer (tools that call the SF API)

| # | Tool | Description | Calls SF API? |
|---|---|---|---|
| 1 | `get_entity_metadata` | Get fields, types, and annotations for a specific entity | Yes — `$metadata` |
| 2 | `list_entities` | List all OData entity sets (optionally filtered by prefix) | Yes — full `$metadata` |
| 3 | `get_picklist_values` | Get dropdown options for a picklist field | Yes — OData query |
| 4 | `query_odata` | Flexible OData query with filter/select/expand/top/skip/orderby | Yes — OData query |

### Rule Generation Layer (may call SF API for validation)

| # | Tool | Description | Calls SF API? |
|---|---|---|---|
| 5 | `validate_rule_fields` | Validate fields, entities, and picklist values exist | Yes — `$metadata` + picklist |
| 6 | `generate_rule_spec` | Generate a full rule spec from a natural language requirement | Yes — `$metadata` |
| 7 | `generate_rule_doc` | Produce a step-by-step implementation guide (markdown/json/text, en/es) | No |
| 8 | `generate_rule_test` | Create test case matrix with edge cases and negative tests | No |

### Typical Workflow

```
1. get_entity_metadata("EmpJob")          → understand available fields
2. get_picklist_values("payGroup")         → check valid dropdown values
3. validate_rule_fields([...])             → confirm fields exist before building
4. generate_rule_spec(requirement="...")   → generate complete rule specification
5. generate_rule_doc(rule_spec)            → create implementation guide
6. generate_rule_test(rule_spec)           → create test case matrix
```

## Troubleshooting API Connectivity

### Common Issues

**1. `ValueError: No API host configured`**
- `.env` file is missing or `SF_API_HOST` is empty
- Fix: create `.env` with the correct hostname

**2. `ValueError: SF_USER_ID does not contain '@companyId' and SF_COMPANY_ID is not set`**
- Both `SF_COMPANY_ID` and the `@companyId` suffix in `SF_USER_ID` are missing
- Fix: set `SF_COMPANY_ID` in `.env`

**3. `SFClientError 401` — Authentication failed**
- Wrong username, password, or company ID
- The API expects Basic Auth with username format `user@companyId`
- Verify credentials work by testing directly:
  ```bash
  curl -u "apiuser@myCompanyId:password" \
    "https://api10preview.sapsf.com/odata/v2/User?\$format=json&\$top=1"
  ```

**4. `SFClientError 403` — Forbidden**
- The API user may lack OData API permissions
- Check: Admin Center > Manage Permission Roles > the user's role must have "OData API" permissions for the target entities

**5. `Unknown data center 'XXX'`**
- The `SF_API_HOST` value is not a recognized DC code or a valid URL
- Fix: use a full hostname (e.g., `api4.successfactors.com`) or a valid DC code from the table above

**6. Connection timeout / `httpx.ConnectTimeout`**
- Network issues, firewall blocking, or wrong hostname
- The client uses 60s timeout — if the SF instance is behind a VPN or IP allowlist, ensure your machine has access
- For `list_entities` (full metadata), the timeout is 90s — large instances can be slow

**7. SSL/TLS errors**
- Ensure your Python installation has up-to-date CA certificates
- Corporate proxies may require custom CA bundles

### Debugging Checklist

1. Verify `.env` exists in the project root and has all 4 variables set
2. Test raw API access with `curl` using the same credentials
3. Check the data center URL matches your SF instance (production vs preview vs salesdemo)
4. Ensure the API user has OData API permissions for the entities you are querying
5. Check network connectivity (VPN, firewall, proxy)

## Running Tests

```bash
# Install dev dependencies
uv sync --dev

# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_sf_client.py -v
```

Tests use `pytest` + `pytest-asyncio` for async tests and `respx` for HTTP mocking (no real SF instance needed).

## MCP Client Configuration

To use this server with Claude Code or another MCP client, add to `.mcp.json`:

```json
{
  "mcpServers": {
    "sf-business-rules": {
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/path/to/this/project"
    }
  }
}
```

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastmcp` | >= 3.0.0 | MCP server framework |
| `httpx` | >= 0.27.0 | Async HTTP client for SF API calls |
| `pydantic` | >= 2.0.0 | Data models and validation |
| `python-dotenv` | (transitive) | Load `.env` credentials |

Dev dependencies: `pytest`, `pytest-asyncio`, `respx`
