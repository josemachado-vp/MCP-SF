# SF Assistant Frontend — Technical Design

## 1. Overview

A web-based chat interface that lets Veritas Prime SF consultants interact with SAP SuccessFactors instances through natural language, powered by the Gemini API and the existing 53-tool MCP server.

**Key capabilities:**
- Chat with Gemini that orchestrates all 53 MCP tools
- Multi-environment support (T1/DEV/PRD) — switch instances by entering credentials
- Download generated files (Excel workbooks, CSVs, Word docs)
- Visual dashboards (org charts, headcount, compensation)
- Saved environment credentials (encrypted) so consultants don't re-enter them
- Audit logs of all queries per instance

**Users:** Internal Veritas Prime consultants only (`@veritasprime.com`).

---

## 2. Architecture

```
Consultant (browser)
    |
    v
+-------------------------+
|  Firebase Hosting        |  React + Vite (SPA)
|  - Chat UI               |  Firebase Auth (Google, @veritasprime.com)
|  - Dashboards            |  Firestore (client-side reads for history/logs)
|  - File downloads        |
+-----------+-------------+
            | HTTPS (REST API)
            v
+-------------------------+
|  Cloud Run               |  Python backend (FastAPI)
|  - Gemini SDK            |  Receives chat messages
|  - MCP tools (in-proc)   |  Gemini decides which tools to call
|  - SF Client (httpx)     |  Executes tools locally, returns results
|  - File generation       |  Cloud Storage for generated files
+-----------+-------------+
            | HTTPS (OData v2)
            v
+-------------------------+
|  SAP SuccessFactors      |  T1 / DEV / PRD instances
+-------------------------+
```

### 2.1 Key Design Decision: In-Process Tool Execution

Gemini and the MCP tools live in the **same Python process** on Cloud Run. There is no stdio/SSE transport between separate services. The backend:

1. Receives a chat message + environment context from the frontend
2. Passes the message to Gemini with all 53 tools declared as function declarations
3. Gemini returns a function call (e.g., `get_employee_profile(userId="12345")`)
4. The backend calls the Python function directly (same process)
5. Returns the tool result to Gemini for the next step or final response
6. Streams the final response back to the frontend

This eliminates network hops between Gemini and the MCP, reduces latency, and simplifies deployment to a single container.

### 2.2 Multi-Environment Credential Flow

Each consultant can save credentials for multiple SF environments. When they send a chat message, the backend resolves credentials for the selected environment and injects them into the SF client for that request.

```
Frontend: { message: "show org chart", environment_id: "client-x-dev" }
    |
    v
Backend: load credentials for "client-x-dev" from Firestore
    |
    v
Override SF_API_HOST, SF_COMPANY_ID, SF_USER_ID, SF_PASSWORD, IAS_* for this request
    |
    v
Execute tools against that specific SF instance
```

Credentials are encrypted at rest in Firestore using Google Cloud KMS. The backend decrypts them per-request. The frontend never sees raw passwords after initial setup.

---

## 3. Frontend (React + Vite)

### 3.1 Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 18 + Vite |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Components | shadcn/ui (Radix primitives) |
| State | Zustand (lightweight, no boilerplate) |
| Charts | Recharts (org charts, headcount, compensation) |
| Auth | Firebase Auth (Google provider) |
| Database | Firestore (client-side SDK for reads) |
| Hosting | Firebase Hosting |

### 3.2 Pages & Layout

**Shell layout:** Sidebar (environments, conversations) + Main area (chat or dashboard).

| Route | Purpose |
|-------|---------|
| `/` | Redirect to `/chat` |
| `/chat` | Main chat interface with Gemini |
| `/chat/:id` | Specific conversation |
| `/environments` | Manage SF environments (add/edit/delete credentials) |
| `/dashboards` | Visual dashboards (org chart, headcount, compensation) |
| `/logs` | Audit log viewer — queries per environment |
| `/settings` | User preferences |

### 3.3 Chat Interface

- Message input at the bottom, conversation history scrolling up
- Gemini responses render as Markdown (code blocks, tables, lists)
- When Gemini calls a tool, show a subtle "Querying SAP SuccessFactors..." indicator with the tool name
- File attachments (generated Excel/CSV/Word) render as download cards inline in the chat
- Environment selector in the top bar — dropdown showing saved environments with colored badges (DEV=blue, QA=yellow, PRD=red)

### 3.4 Dashboard Views

Dashboards are populated by sending predefined prompts to the backend (reusing the same Gemini+tools pipeline):

| Dashboard | Underlying tools | Visualization |
|-----------|-----------------|---------------|
| Org Chart | `get_org_chart` | Tree/hierarchy component |
| Headcount | `get_headcount` | Bar/pie charts by department, location, etc. |
| Compensation | `get_compensation_analytics` | Box plots, histograms, comparison tables |

The backend returns structured JSON; the frontend renders it visually. Dashboards are essentially "saved prompts with visual rendering."

### 3.5 File Downloads

When a tool generates a file (workbook, CSV, import template):
1. Backend uploads the file to Cloud Storage with a signed URL (1h expiry)
2. Returns the signed URL in the chat response
3. Frontend renders a download card with filename, size, and download button

---

## 4. Backend (Cloud Run — Python)

### 4.1 Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI |
| AI SDK | `google-genai` (Gemini Python SDK) |
| SF Client | Existing `helpers/sf_client.py` (httpx async) |
| MCP tools | Existing `tools/*.py` (imported directly) |
| Auth validation | `firebase-admin` SDK (verify ID tokens) |
| Database | `google-cloud-firestore` |
| File storage | `google-cloud-storage` |
| Encryption | `google-cloud-kms` (credential encryption) |
| Container | Docker → Cloud Run |

### 4.2 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/chat` | Send message, get Gemini response (streaming SSE) |
| GET | `/api/conversations` | List conversations for current user |
| GET | `/api/conversations/:id` | Get conversation history |
| DELETE | `/api/conversations/:id` | Delete a conversation |
| POST | `/api/environments` | Create SF environment (encrypt + store credentials) |
| GET | `/api/environments` | List environments for current user |
| PUT | `/api/environments/:id` | Update environment credentials |
| DELETE | `/api/environments/:id` | Delete environment |
| POST | `/api/environments/:id/test` | Test connection to SF instance |
| GET | `/api/logs` | Query audit logs (filtered by environment, date, tool) |
| GET | `/api/files/:id` | Get signed download URL for a generated file |

### 4.3 Chat Flow (POST `/api/chat`)

```python
# Pseudocode for the chat endpoint
async def chat(request: ChatRequest, user: FirebaseUser):
    # 1. Load credentials for selected environment
    env = await firestore.get(f"users/{user.uid}/environments/{request.environment_id}")
    sf_creds = decrypt_credentials(env.encrypted_credentials)

    # 2. Load conversation history (or start new)
    history = await load_conversation(request.conversation_id)

    # 3. Build Gemini request with all 53 tools as function declarations
    model = genai.GenerativeModel("gemini-2.5-pro")
    chat_session = model.start_chat(history=history)

    # 4. Send message — Gemini may call tools in a loop
    response = await chat_session.send_message(
        request.message,
        tools=MCP_TOOL_DECLARATIONS,
    )

    # 5. Handle function calls
    while response.candidates[0].content.parts[-1].function_call:
        fc = response.candidates[0].content.parts[-1].function_call
        tool_result = await execute_tool(fc.name, fc.args, sf_creds)

        # Log the tool call
        await log_tool_call(user.uid, request.environment_id, fc.name, fc.args)

        # Return result to Gemini
        response = await chat_session.send_message(
            genai.types.Content(parts=[genai.types.Part(function_response=...)])
        )

    # 6. Save conversation, return response
    await save_conversation(request.conversation_id, chat_session.history)
    return StreamingResponse(response.text)
```

### 4.4 Tool Declaration Bridge

The 53 MCP tools need to be declared as Gemini function declarations. A bridge module inspects each tool's signature and docstring to generate the `genai.types.FunctionDeclaration` list at startup:

```python
# backend/tool_bridge.py
def build_tool_declarations() -> list[FunctionDeclaration]:
    """Convert MCP tool functions to Gemini function declarations."""
    declarations = []
    for tool_fn, metadata in ALL_TOOLS:
        declarations.append(FunctionDeclaration(
            name=metadata["name"],
            description=metadata["description"],
            parameters=metadata["input_schema"],
        ))
    return declarations
```

### 4.5 Credential Isolation

Each request creates a fresh `SFClient` instance with the decrypted credentials for that specific environment. No shared state between requests — this ensures tenant isolation when multiple consultants query different SF instances concurrently.

```python
async def execute_tool(tool_name: str, args: dict, sf_creds: SFCredentials):
    """Execute a tool with environment-specific credentials."""
    # Override the credential resolution for this request
    with credential_context(sf_creds):
        tool_fn = TOOL_REGISTRY[tool_name]
        return await tool_fn(**args)
```

### 4.6 PII Protection

The existing PII protection layer (`helpers/pii_filter.py`) runs inside the same process — all tool calls pass through `validate_query()` and `scrub_response()` automatically. No changes needed.

---

## 5. Data Model (Firestore)

```
users/{uid}/
    profile: { email, displayName, photoURL, createdAt }
    environments/{envId}/
        name: "Client X - DEV"
        type: "DEV" | "QA" | "PRD"
        sf_api_host: "https://api8preview.sapsf.com"
        sf_company_id: "CLIENTX_DEV"
        encrypted_credentials: <KMS-encrypted blob>
        last_tested: timestamp
        created_at: timestamp
    conversations/{convId}/
        title: "Org chart for Client X"
        environment_id: "env-abc123"
        created_at: timestamp
        updated_at: timestamp
        messages/{msgId}/
            role: "user" | "assistant" | "tool_call" | "tool_result"
            content: string
            tool_name?: string
            tool_args?: map
            files?: [{ name, storage_path, signed_url, expires_at }]
            timestamp: timestamp
    logs/{logId}/
        environment_id: string
        tool_name: string
        tool_args: map (scrubbed — no credentials)
        success: boolean
        latency_ms: number
        timestamp: timestamp
```

---

## 6. Security

| Concern | Solution |
|---------|----------|
| Authentication | Firebase Auth — Google Sign-In restricted to `@veritasprime.com` domain |
| API authorization | Every Cloud Run request validates Firebase ID token (`Authorization: Bearer <token>`) |
| SF credentials at rest | Encrypted with Google Cloud KMS before storing in Firestore |
| SF credentials in transit | HTTPS only (Cloud Run enforces TLS) |
| PII in responses | Existing `pii_filter.py` scrubs sensitive fields before Gemini sees them |
| CORS | Cloud Run allows only the Firebase Hosting domain |
| Audit trail | Every tool call logged to Firestore with user, environment, tool, timestamp |
| Rate limiting | Cloud Run concurrency limits + per-user rate limiting in middleware |

---

## 7. Infrastructure & Deployment

### 7.1 GCP Services

| Service | Purpose | Estimated Cost |
|---------|---------|---------------|
| Firebase Hosting | Serve React SPA | Free tier (sufficient) |
| Firebase Auth | Google Sign-In | Free tier (< 50 users) |
| Cloud Firestore | Conversations, environments, logs | Free tier initially |
| Cloud Run | Python backend | Pay-per-request, scales to zero |
| Cloud Storage | Generated files (Excel, CSV, Word) | Minimal (files expire after 24h) |
| Cloud KMS | Credential encryption | ~$0.06/10K operations |
| Gemini API | AI responses + function calling | Pay-per-token (gemini-2.5-pro) |

### 7.2 Deployment Pipeline

```
GitHub repo
    |
    v  (push to main)
Cloud Build trigger
    |
    +---> Build React app → Deploy to Firebase Hosting
    |
    +---> Build Docker image → Deploy to Cloud Run
```

### 7.3 Docker Image (Cloud Run)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --extra gcp
COPY . .
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 8. Project Structure

```
sf-assistant-mcp/
├── frontend/                    # React + Vite SPA
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/            # ChatWindow, MessageBubble, ToolCallIndicator
│   │   │   ├── dashboard/       # OrgChart, HeadcountChart, CompensationChart
│   │   │   ├── environments/    # EnvironmentForm, EnvironmentList, EnvironmentBadge
│   │   │   ├── logs/            # LogTable, LogFilters
│   │   │   └── layout/          # Sidebar, TopBar, Shell
│   │   ├── hooks/               # useChat, useEnvironments, useAuth
│   │   ├── lib/                 # firebase.ts, api.ts (Cloud Run client)
│   │   ├── pages/               # ChatPage, DashboardPage, EnvironmentsPage, LogsPage
│   │   ├── store/               # Zustand stores (chat, environments, auth)
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── backend/                     # FastAPI backend for Cloud Run
│   ├── api.py                   # FastAPI app, routes
│   ├── auth.py                  # Firebase token verification
│   ├── chat.py                  # Gemini chat orchestration
│   ├── tool_bridge.py           # MCP tools → Gemini function declarations
│   ├── credential_manager.py    # KMS encrypt/decrypt, Firestore CRUD
│   ├── file_manager.py          # Cloud Storage upload, signed URLs
│   ├── logger.py                # Audit log writer
│   └── Dockerfile
├── helpers/                     # Existing MCP helpers (unchanged)
├── tools/                       # Existing 53 MCP tools (unchanged)
├── knowledge/                   # Existing knowledge base (unchanged)
├── models/                      # Existing Pydantic models (unchanged)
├── tests/                       # Existing + new tests
├── main.py                      # Existing MCP entry point (unchanged)
├── firebase.json                # Firebase Hosting config
├── .firebaserc                  # Firebase project binding
└── pyproject.toml               # Updated with new backend deps
```

---

## 9. Use Cases & Feature Map

### 9.1 User Roles

| Role | Description | Access |
|------|------------|--------|
| SF Consultant | Veritas Prime consultant implementing/supporting SF instances | Full access to all features |
| Senior Consultant / Lead | Reviews configurations, approves migrations, validates go-live | Full access + audit log visibility across team |

### 9.2 Use Cases

#### UC-1: Employee Data Exploration
**Goal:** Quickly find and understand employee data across SF instances.
**Chat examples:**
- "Show me active employees in Colombia"
- "Get the full profile for user admin123"
- "Compare employee Jose Machado between DEV and PRD"
- "Show the org chart for department 40000013"
- "What's the employment history for user 12345?"

**Tools involved:** `search_employees`, `get_employee_profile`, `compare_employees`, `get_org_chart`, `get_employee_history`

#### UC-2: Configuration Analysis
**Goal:** Understand and document how an SF instance is configured.
**Chat examples:**
- "List all business rules in this instance"
- "What fields does the EmpJob entity have?"
- "Show picklist values for ecEmployeeStatus"
- "What permission roles are configured?"
- "List all MDF objects"

**Tools involved:** `list_business_rules`, `get_entity_metadata`, `list_entities`, `get_picklist_values`, `get_permission_roles`, `list_mdf_objects`, `get_mdf_object_definition`

#### UC-3: Business Rule Development
**Goal:** Design, validate, and document business rules from natural language descriptions.
**Chat examples:**
- "Create a rule that sets the cost center based on department"
- "Validate that fields firstName and lastName exist on PerPersonal"
- "Generate test cases for the new hire rule"
- "Generate implementation documentation for this rule"

**Tools involved:** `validate_rule_fields`, `generate_rule_spec`, `generate_rule_doc`, `generate_rule_test`

#### UC-4: Data Import & Migration
**Goal:** Prepare, validate, and execute data loads into SF.
**Chat examples:**
- "Generate an import template for EmpJob"
- "Validate this CSV template for PerPersonal"
- "Dry-run upsert these 5 records to EmpCompensation"
- "Generate the migration load sequence for go-live"
- "Validate this migration file"

**Tools involved:** `generate_import_template`, `validate_import_template`, `execute_upsert`, `generate_migration_sequence`, `validate_migration_file`, `generate_mdf_import_template`

#### UC-5: Instance Comparison (DEV vs QA vs PRD)
**Goal:** Compare configurations across environments to catch drift.
**Chat examples:**
- "Compare EmpJob metadata between DEV and PRD"
- "Are picklist values for gender the same in QA and PRD?"
- "Compare business rules between T1 and PRD"
- "Compare Foundation Objects between environments"

**Tools involved:** `compare_instance_config`, `compare_picklists`, `compare_business_rules`, `compare_foundation_objects`

**Frontend flow:** Consultant selects two saved environments from dropdowns, types the comparison query, backend executes tools against both instances in parallel.

#### UC-6: Analytics & Reporting
**Goal:** Get headcount, compensation stats, and organizational insights.
**Chat examples:**
- "Show headcount by department"
- "What's the average salary by country?"
- "Simulate the impact of changing the bonus rule threshold"

**Tools involved:** `get_headcount`, `get_compensation_analytics`, `simulate_rule_impact`

**Dashboard integration:** Results render as interactive charts (bar, pie, box plots) on the Dashboards page.

#### UC-7: Audit & Troubleshooting
**Goal:** Investigate data quality issues, permission gaps, and rule behavior.
**Chat examples:**
- "Audit employee data for missing required fields"
- "Find data anomalies in compensation records"
- "Trace why this rule fired for employee 12345"
- "Does role HR_ADMIN have access to edit EmpJob?"
- "Validate effective dating for this employee's job history"

**Tools involved:** `audit_employee_data`, `find_data_anomalies`, `trace_rule_execution`, `check_permission_access`, `validate_effective_dating`

#### UC-8: Documentation Generation
**Goal:** Auto-generate project deliverables and configuration docs.
**Chat examples:**
- "Generate a functional spec for the new hire workflow"
- "Create a cutover checklist for go-live"
- "Generate a data dictionary for Employee Central"
- "Create test scripts for the compensation review process"

**Tools involved:** `generate_functional_spec`, `generate_cutover_checklist`, `generate_data_dictionary`, `generate_test_script`

**File download:** Generated Word/Excel documents appear as download cards in the chat.

#### UC-9: Workbook Generation
**Goal:** Generate configuration workbooks for client documentation.
**Chat examples:**
- "Generate the Foundation Objects workbook"
- "Generate the Workflow Notifications workbook"
- "Generate the EC Rules workbook"

**Tools involved:** `generate_fo_workbook`, `generate_workflow_workbook`, `generate_rules_workbook`

**File download:** Excel workbooks appear as download cards with environment badge.

#### UC-10: Go-Live Readiness
**Goal:** Validate that an instance is ready for production cutover.
**Chat examples:**
- "Run go-live checks on PRD"
- "Generate a reconciliation report comparing DEV data vs PRD"
- "Generate purge file for test data cleanup"

**Tools involved:** `run_go_live_checks`, `generate_reconciliation_report`, `reconcile_data`, `generate_purge_file`

#### UC-11: Multi-Country Support
**Goal:** Manage country-specific configurations and compliance.
**Chat examples:**
- "What country-specific fields exist for Colombia?"
- "Validate compliance for the Mexico configuration"
- "Generate a country configuration guide for Brazil"

**Tools involved:** `get_country_specific_fields`, `validate_country_compliance`, `generate_country_config_guide`

### 9.3 Feature-to-Tool Matrix

| Feature Area | Tools (count) | Frontend Component |
|-------------|--------------|-------------------|
| Employee Data | `search_employees`, `get_employee_profile`, `get_org_chart`, `get_employee_history`, `compare_employees` (5) | Chat + Org Chart Dashboard |
| Configuration | `get_entity_metadata`, `list_entities`, `get_picklist_values`, `query_odata`, `list_business_rules`, `get_permission_roles` (6) | Chat |
| Business Rules | `validate_rule_fields`, `generate_rule_spec`, `generate_rule_doc`, `generate_rule_test` (4) | Chat + File Downloads |
| Data Import | `generate_import_template`, `validate_import_template`, `execute_upsert` (3) | Chat + File Downloads |
| Organization | `get_org_structure`, `get_position_details`, `list_foundation_objects` (3) | Chat + Org Chart Dashboard |
| Analytics | `get_headcount`, `get_compensation_analytics`, `simulate_rule_impact` (3) | Chat + Charts Dashboard |
| Instance Compare | `compare_instance_config`, `compare_picklists`, `compare_business_rules`, `compare_foundation_objects` (4) | Chat (dual-environment selector) |
| Audit | `audit_employee_data`, `find_data_anomalies`, `trace_rule_execution`, `check_permission_access`, `validate_effective_dating` (5) | Chat + Logs Page |
| Documentation | `generate_functional_spec`, `generate_cutover_checklist`, `generate_data_dictionary`, `generate_test_script` (4) | Chat + File Downloads |
| Migration | `validate_migration_file`, `generate_migration_sequence`, `reconcile_data`, `generate_purge_file` (4) | Chat + File Downloads |
| MDF | `get_mdf_object_definition`, `generate_mdf_import_template`, `list_mdf_objects` (3) | Chat + File Downloads |
| Go-Live | `run_go_live_checks`, `generate_reconciliation_report` (2) | Chat + File Downloads |
| Country | `get_country_specific_fields`, `validate_country_compliance`, `generate_country_config_guide` (3) | Chat + File Downloads |
| Workbooks | `generate_fo_workbook`, `generate_workflow_workbook`, `generate_rules_workbook` (3) | Chat + File Downloads |

**Total: 53 tools across 14 feature areas.**

---

## 10. Implementation Phases

### Phase 1: Backend Core (Cloud Run)

- FastAPI app with auth middleware
- Gemini chat endpoint with tool bridge
- Credential manager (KMS + Firestore)
- Environment CRUD endpoints
- Docker image + Cloud Run deployment

### Phase 2: Frontend Core (Firebase Hosting)
- React + Vite scaffold with Tailwind + shadcn/ui
- Firebase Auth (Google Sign-In, domain restriction)
- Chat interface (messages, streaming, Markdown rendering)
- Environment management page
- Firebase Hosting deployment

### Phase 3: File Downloads + Dashboards
- Cloud Storage integration for generated files
- Download cards in chat
- Dashboard page with org chart, headcount, compensation charts

### Phase 4: Audit Logs + Polish
- Log viewer with filters
- Tool call indicators in chat
- Error handling, loading states, edge cases
- Cloud Build CI/CD pipeline
