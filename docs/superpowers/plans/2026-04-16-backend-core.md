# SF Assistant Backend Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI backend on Cloud Run that receives chat messages from the frontend, orchestrates Gemini function calling with all 53 MCP tools, manages per-environment SF credentials encrypted with KMS, and stores conversations/logs in Firestore.

**Architecture:** Single Python process running FastAPI. The Gemini SDK calls tool functions in-process (no stdio/SSE). Each request decrypts credentials for the selected SF environment, creates a fresh SF client, executes Gemini's tool calls, and streams the response back. Firebase Admin SDK validates auth tokens on every request.

**Tech Stack:** FastAPI, google-genai (Gemini SDK), firebase-admin, google-cloud-firestore, google-cloud-kms, google-cloud-storage, uvicorn, Docker.

**Spec:** `docs/superpowers/specs/2026-04-16-sf-assistant-frontend-design.md`

---

## File Structure

```
backend/
├── __init__.py              # Package init
├── api.py                   # FastAPI app, routes, CORS, lifespan
├── auth.py                  # Firebase ID token verification middleware
├── chat.py                  # Gemini chat orchestration (send message, handle tool loop)
├── tool_bridge.py           # Convert 53 MCP tool functions → Gemini FunctionDeclarations
├── credential_manager.py    # KMS encrypt/decrypt + Firestore CRUD for environments
├── file_manager.py          # Cloud Storage upload + signed URL generation
├── logger.py                # Audit log writer (Firestore)
├── config.py                # Environment variables, GCP project config
├── models.py                # Pydantic request/response models
├── Dockerfile               # Container image for Cloud Run
└── requirements.txt         # Backend-specific deps (separate from MCP pyproject.toml)
tests/
└── test_backend/
    ├── __init__.py
    ├── test_tool_bridge.py      # Tool declaration extraction tests
    ├── test_auth.py             # Token verification tests
    ├── test_credential_manager.py # Encrypt/decrypt + CRUD tests
    ├── test_chat.py             # Gemini orchestration tests
    ├── test_file_manager.py     # File upload + signed URL tests
    └── test_api.py              # Integration tests for API endpoints
```

---

### Task 1: Backend Config & Dependencies

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/requirements.txt`

- [ ] **Step 1: Create backend package init**

```python
# backend/__init__.py
```

- [ ] **Step 2: Create config module**

```python
# backend/config.py
"""Backend configuration loaded from environment variables."""

import os

# GCP
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_KMS_KEYRING = os.environ.get("GCP_KMS_KEYRING", "sf-assistant")
GCP_KMS_KEY = os.environ.get("GCP_KMS_KEY", "credentials-key")
GCP_KMS_LOCATION = os.environ.get("GCP_KMS_LOCATION", "us-central1")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "sf-assistant-files")

# Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

# Firebase
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")

# CORS
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173",  # Vite dev server
).split(",")

# Cloud Run port
PORT = int(os.environ.get("PORT", "8080"))
```

- [ ] **Step 3: Create requirements.txt**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
google-genai>=1.0.0
firebase-admin>=6.0.0
google-cloud-firestore>=2.0.0
google-cloud-kms>=3.0.0
google-cloud-storage>=2.0.0
pydantic>=2.0.0
httpx>=0.27.0
python-dotenv>=1.0.0
```

- [ ] **Step 4: Commit**

```bash
git add backend/__init__.py backend/config.py backend/requirements.txt
git commit -m "feat(backend): add config module and dependencies"
```

---

### Task 2: Pydantic Request/Response Models

**Files:**
- Create: `backend/models.py`

- [ ] **Step 1: Create request/response models**

```python
# backend/models.py
"""Pydantic models for API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


# --- Chat ---

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    environment_id: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None


class ToolCallInfo(BaseModel):
    tool_name: str
    tool_args: dict


class FileAttachment(BaseModel):
    name: str
    download_url: str
    size_bytes: int


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "tool_call" | "tool_result"
    content: str
    tool_call: Optional[ToolCallInfo] = None
    files: Optional[list[FileAttachment]] = None
    timestamp: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)


# --- Environments ---

class EnvironmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    env_type: str = Field(..., pattern="^(DEV|QA|PRD|T1)$")
    sf_api_host: str = Field(..., min_length=1)
    sf_company_id: str = Field(..., min_length=1)
    sf_user_id: str = Field(..., min_length=1)
    sf_password: str = Field(..., min_length=1)
    ias_host: str = Field(..., min_length=1)
    oidc_client_id: str = Field(..., min_length=1)
    oidc_client_secret: str = Field(..., min_length=1)
    ias_dependency_name: str = Field(..., min_length=1)


class EnvironmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    env_type: Optional[str] = Field(None, pattern="^(DEV|QA|PRD|T1)$")
    sf_api_host: Optional[str] = None
    sf_company_id: Optional[str] = None
    sf_user_id: Optional[str] = None
    sf_password: Optional[str] = None
    ias_host: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    ias_dependency_name: Optional[str] = None


class EnvironmentResponse(BaseModel):
    id: str
    name: str
    env_type: str
    sf_api_host: str
    sf_company_id: str
    last_tested: Optional[str] = None
    created_at: str


class EnvironmentTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


# --- Conversations ---

class ConversationSummary(BaseModel):
    id: str
    title: str
    environment_id: str
    environment_name: str
    created_at: str
    updated_at: str
    message_count: int


# --- Logs ---

class LogEntry(BaseModel):
    id: str
    environment_id: str
    environment_name: str
    tool_name: str
    tool_args: dict
    success: bool
    latency_ms: int
    timestamp: str


class LogQuery(BaseModel):
    environment_id: Optional[str] = None
    tool_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)
```

- [ ] **Step 2: Commit**

```bash
git add backend/models.py
git commit -m "feat(backend): add Pydantic request/response models"
```

---

### Task 3: Tool Bridge — MCP Tools to Gemini Function Declarations

**Files:**
- Create: `backend/tool_bridge.py`
- Create: `tests/test_backend/__init__.py`
- Create: `tests/test_backend/test_tool_bridge.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backend/__init__.py
```

```python
# tests/test_backend/test_tool_bridge.py
"""Tests for MCP tool → Gemini function declaration bridge."""

import pytest
from backend.tool_bridge import (
    build_tool_declarations,
    get_tool_registry,
    extract_function_schema,
)
from typing import Annotated, Optional


# --- extract_function_schema ---

async def _sample_tool(
    entity: Annotated[str, "The entity name"],
    top: Annotated[int, "Max results"] = 10,
    filter: Annotated[Optional[str], "OData filter"] = None,
) -> dict:
    """Sample tool for testing.

    This is the extended description.
    """
    return {}


def test_extract_schema_name():
    schema = extract_function_schema(_sample_tool)
    assert schema["name"] == "_sample_tool"


def test_extract_schema_description():
    schema = extract_function_schema(_sample_tool)
    assert schema["description"] == "Sample tool for testing."


def test_extract_schema_required_params():
    schema = extract_function_schema(_sample_tool)
    props = schema["parameters"]["properties"]
    assert "entity" in props
    assert props["entity"]["type"] == "string"
    assert props["entity"]["description"] == "The entity name"


def test_extract_schema_optional_params():
    schema = extract_function_schema(_sample_tool)
    props = schema["parameters"]["properties"]
    assert "top" in props
    assert props["top"]["type"] == "integer"
    assert "filter" in props
    assert props["filter"]["type"] == "string"


def test_extract_schema_required_list():
    schema = extract_function_schema(_sample_tool)
    assert schema["parameters"]["required"] == ["entity"]


def test_extract_schema_excludes_credential_params():
    """Credential override params (data_center, auth_user_id, auth_password)
    should be excluded from Gemini declarations — the backend injects them."""

    async def tool_with_creds(
        entity: Annotated[str, "Entity"],
        data_center: Annotated[Optional[str], "API host override"] = None,
        auth_user_id: Annotated[Optional[str], "User override"] = None,
        auth_password: Annotated[Optional[str], "Password override"] = None,
    ) -> dict:
        """Tool with credential params."""
        return {}

    schema = extract_function_schema(tool_with_creds)
    props = schema["parameters"]["properties"]
    assert "entity" in props
    assert "data_center" not in props
    assert "auth_user_id" not in props
    assert "auth_password" not in props


# --- build_tool_declarations ---

def test_build_declarations_returns_list():
    declarations = build_tool_declarations()
    assert isinstance(declarations, list)
    assert len(declarations) == 53


def test_build_declarations_have_names():
    declarations = build_tool_declarations()
    names = [d.name for d in declarations]
    assert "query_odata" in names
    assert "search_employees" in names
    assert "get_employee_profile" in names


# --- get_tool_registry ---

def test_registry_maps_name_to_function():
    registry = get_tool_registry()
    assert callable(registry["query_odata"])
    assert callable(registry["search_employees"])


def test_registry_has_53_tools():
    registry = get_tool_registry()
    assert len(registry) == 53
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_tool_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.tool_bridge'`

- [ ] **Step 3: Implement tool bridge**

```python
# backend/tool_bridge.py
"""Bridge between MCP tool functions and Gemini function declarations.

Inspects each tool's type hints (Annotated[Type, "description"]) to build
Gemini FunctionDeclaration objects. Credential params (data_center,
auth_user_id, auth_password) are excluded — the backend injects those.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Optional, get_args, get_origin

from google.genai import types

# Credential params that the backend injects — never exposed to Gemini
_CREDENTIAL_PARAMS = {"data_center", "auth_user_id", "auth_password"}

# Python type → JSON Schema type
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _get_all_tools() -> list[tuple[str, callable]]:
    """Import all 53 tool functions and return (name, fn) pairs."""
    from tools.discovery import (
        get_entity_metadata, list_entities, get_picklist_values, query_odata,
    )
    from tools.rule_generation import validate_rule_fields, generate_rule_spec
    from tools.rule_documentation import generate_rule_doc, generate_rule_test
    from tools.employee import (
        search_employees, get_employee_profile, get_org_chart,
        get_employee_history, compare_employees,
    )
    from tools.organization import (
        get_org_structure, get_position_details, list_foundation_objects,
    )
    from tools.configuration import list_business_rules, get_permission_roles
    from tools.data_import import (
        validate_import_template, generate_import_template, execute_upsert,
    )
    from tools.analytics import (
        get_headcount, get_compensation_analytics, simulate_rule_impact,
    )
    from tools.instance_compare import (
        compare_instance_config, compare_picklists, compare_business_rules,
        compare_foundation_objects,
    )
    from tools.audit import (
        audit_employee_data, find_data_anomalies, trace_rule_execution,
        check_permission_access, validate_effective_dating,
    )
    from tools.documentation import (
        generate_functional_spec, generate_cutover_checklist,
        generate_data_dictionary, generate_test_script,
    )
    from tools.migration import (
        validate_migration_file, generate_migration_sequence,
        reconcile_data, generate_purge_file,
    )
    from tools.mdf import (
        get_mdf_object_definition, generate_mdf_import_template, list_mdf_objects,
    )
    from tools.golive import run_go_live_checks, generate_reconciliation_report
    from tools.country import (
        get_country_specific_fields, validate_country_compliance,
        generate_country_config_guide,
    )
    from tools.workbook_generator import (
        generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook,
    )

    all_fns = [
        get_entity_metadata, list_entities, get_picklist_values, query_odata,
        validate_rule_fields, generate_rule_spec,
        generate_rule_doc, generate_rule_test,
        search_employees, get_employee_profile, get_org_chart,
        get_employee_history, compare_employees,
        get_org_structure, get_position_details, list_foundation_objects,
        list_business_rules, get_permission_roles,
        validate_import_template, generate_import_template, execute_upsert,
        get_headcount, get_compensation_analytics, simulate_rule_impact,
        compare_instance_config, compare_picklists, compare_business_rules,
        compare_foundation_objects,
        audit_employee_data, find_data_anomalies, trace_rule_execution,
        check_permission_access, validate_effective_dating,
        generate_functional_spec, generate_cutover_checklist,
        generate_data_dictionary, generate_test_script,
        validate_migration_file, generate_migration_sequence,
        reconcile_data, generate_purge_file,
        get_mdf_object_definition, generate_mdf_import_template, list_mdf_objects,
        run_go_live_checks, generate_reconciliation_report,
        get_country_specific_fields, validate_country_compliance,
        generate_country_config_guide,
        generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook,
    ]
    return [(fn.__name__, fn) for fn in all_fns]


def _resolve_type(annotation) -> str:
    """Resolve a Python type annotation to a JSON Schema type string."""
    origin = get_origin(annotation)

    # Optional[X] → unwrap to X
    if origin is Optional:
        args = get_args(annotation)
        return _resolve_type(args[0]) if args else "string"

    # Union (e.g., str | None) → take first non-None
    import types as builtin_types
    if origin is builtin_types.UnionType or (origin is not None and hasattr(origin, "__origin__")):
        args = get_args(annotation)
        for arg in args:
            if arg is not type(None):
                return _resolve_type(arg)

    # Annotated[X, desc] → unwrap to X
    if origin is Annotated:
        args = get_args(annotation)
        return _resolve_type(args[0]) if args else "string"

    return _TYPE_MAP.get(annotation, "string")


def _get_description(annotation) -> str:
    """Extract description string from Annotated[Type, 'description']."""
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        for arg in args[1:]:
            if isinstance(arg, str):
                return arg
    return ""


def extract_function_schema(fn: callable) -> dict:
    """Extract a JSON-schema-like dict from a function's type hints.

    Returns:
        {
            "name": "function_name",
            "description": "First line of docstring.",
            "parameters": {
                "type": "object",
                "properties": { ... },
                "required": [ ... ],
            }
        }
    """
    sig = inspect.signature(fn)
    hints = inspect.get_annotations(fn, eval_str=True) if hasattr(inspect, "get_annotations") else fn.__annotations__

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in _CREDENTIAL_PARAMS:
            continue
        if param_name == "return":
            continue

        annotation = hints.get(param_name, str)
        json_type = _resolve_type(annotation)
        description = _get_description(annotation)

        properties[param_name] = {"type": json_type}
        if description:
            properties[param_name]["description"] = description

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    # First line of docstring as description
    doc = inspect.getdoc(fn) or ""
    first_line = doc.split("\n")[0].strip() if doc else fn.__name__

    return {
        "name": fn.__name__,
        "description": first_line,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def build_tool_declarations() -> list[types.FunctionDeclaration]:
    """Build Gemini FunctionDeclaration list from all 53 MCP tools."""
    declarations = []
    for name, fn in _get_all_tools():
        schema = extract_function_schema(fn)
        declarations.append(types.FunctionDeclaration(
            name=schema["name"],
            description=schema["description"],
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    k: types.Schema(
                        type=v["type"].upper(),
                        description=v.get("description", ""),
                    )
                    for k, v in schema["parameters"]["properties"].items()
                },
                required=schema["parameters"]["required"],
            ),
        ))
    return declarations


def get_tool_registry() -> dict[str, callable]:
    """Return a dict mapping tool name → async function for execution."""
    return {name: fn for name, fn in _get_all_tools()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_tool_bridge.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tool_bridge.py tests/test_backend/
git commit -m "feat(backend): tool bridge — MCP tools to Gemini function declarations"
```

---

### Task 4: Firebase Auth Middleware

**Files:**
- Create: `backend/auth.py`
- Create: `tests/test_backend/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backend/test_auth.py
"""Tests for Firebase auth middleware."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from backend.auth import get_current_user, FirebaseUser


app = FastAPI()


@app.get("/test")
async def test_endpoint(user: FirebaseUser = Depends(get_current_user)):
    return {"uid": user.uid, "email": user.email}


client = TestClient(app)


def test_missing_auth_header_returns_401():
    resp = client.get("/test")
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"]


def test_invalid_token_returns_401():
    with patch("backend.auth._verify_token", side_effect=ValueError("Invalid token")):
        resp = client.get("/test", headers={"Authorization": "Bearer bad-token"})
        assert resp.status_code == 401


def test_non_veritasprime_email_returns_403():
    mock_decoded = {"uid": "123", "email": "hacker@gmail.com", "name": "Hacker"}
    with patch("backend.auth._verify_token", return_value=mock_decoded):
        resp = client.get("/test", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 403
        assert "veritasprime.com" in resp.json()["detail"]


def test_valid_veritasprime_token_returns_user():
    mock_decoded = {"uid": "abc123", "email": "jose@veritasprime.com", "name": "Jose"}
    with patch("backend.auth._verify_token", return_value=mock_decoded):
        resp = client.get("/test", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 200
        assert resp.json()["uid"] == "abc123"
        assert resp.json()["email"] == "jose@veritasprime.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.auth'`

- [ ] **Step 3: Implement auth module**

```python
# backend/auth.py
"""Firebase ID token verification for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException

import firebase_admin
from firebase_admin import auth as fb_auth

# Initialize Firebase Admin SDK (uses GOOGLE_APPLICATION_CREDENTIALS env var)
if not firebase_admin._apps:
    firebase_admin.initialize_app()

ALLOWED_DOMAIN = "veritasprime.com"


@dataclass
class FirebaseUser:
    uid: str
    email: str
    name: str


def _verify_token(token: str) -> dict:
    """Verify Firebase ID token. Raises ValueError on failure."""
    try:
        return fb_auth.verify_id_token(token)
    except Exception as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


async def get_current_user(
    authorization: str = Header(None),
) -> FirebaseUser:
    """FastAPI dependency that extracts and validates the Firebase user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        decoded = _verify_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = decoded.get("email", "")
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        raise HTTPException(
            status_code=403,
            detail=f"Access restricted to @{ALLOWED_DOMAIN} accounts",
        )

    return FirebaseUser(
        uid=decoded["uid"],
        email=email,
        name=decoded.get("name", ""),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_auth.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_backend/test_auth.py
git commit -m "feat(backend): Firebase auth middleware with domain restriction"
```

---

### Task 5: Credential Manager — KMS Encrypt/Decrypt + Firestore CRUD

**Files:**
- Create: `backend/credential_manager.py`
- Create: `tests/test_backend/test_credential_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backend/test_credential_manager.py
"""Tests for credential manager (KMS + Firestore)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.credential_manager import (
    CredentialManager,
    SFCredentials,
)


@pytest.fixture
def mock_firestore():
    return MagicMock()


@pytest.fixture
def mock_kms():
    mock = MagicMock()
    # encrypt returns a mock with ciphertext
    mock.encrypt.return_value = MagicMock(ciphertext=b"encrypted-data")
    mock.decrypt.return_value = MagicMock(plaintext=b'{"sf_user_id":"admin","sf_password":"pass123","oidc_client_id":"cid","oidc_client_secret":"csec"}')
    return mock


@pytest.fixture
def manager(mock_firestore, mock_kms):
    return CredentialManager(
        firestore_client=mock_firestore,
        kms_client=mock_kms,
        kms_key_name="projects/p/locations/l/keyRings/kr/cryptoKeys/k",
    )


def test_sf_credentials_dataclass():
    creds = SFCredentials(
        sf_api_host="https://api.sapsf.com",
        sf_company_id="ACME",
        sf_user_id="admin",
        sf_password="secret",
        ias_host="ias.ondemand.com",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        ias_dependency_name="SF_DEP",
    )
    assert creds.sf_api_host == "https://api.sapsf.com"
    assert creds.sf_company_id == "ACME"


def test_encrypt_credentials(manager, mock_kms):
    sensitive = {"sf_user_id": "admin", "sf_password": "pass123"}
    result = manager.encrypt_credentials(sensitive)
    mock_kms.encrypt.assert_called_once()
    assert isinstance(result, bytes)


def test_decrypt_credentials(manager, mock_kms):
    result = manager.decrypt_credentials(b"encrypted-data")
    mock_kms.decrypt.assert_called_once()
    assert result["sf_user_id"] == "admin"
    assert result["sf_password"] == "pass123"


@pytest.mark.asyncio
async def test_create_environment(manager, mock_firestore):
    env_ref = MagicMock()
    env_ref.id = "env-123"
    mock_collection = MagicMock()
    mock_collection.document.return_value = env_ref
    mock_firestore.collection.return_value = mock_collection

    env_id = await manager.create_environment(
        user_uid="user-1",
        name="Client DEV",
        env_type="DEV",
        sf_api_host="https://api.sapsf.com",
        sf_company_id="ACME_DEV",
        sf_user_id="admin",
        sf_password="pass",
        ias_host="ias.ondemand.com",
        oidc_client_id="cid",
        oidc_client_secret="csec",
        ias_dependency_name="SF_DEP",
    )
    assert env_id == "env-123"
    env_ref.set.assert_called_once()


@pytest.mark.asyncio
async def test_get_credentials_decrypts(manager, mock_firestore, mock_kms):
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {
        "name": "Client DEV",
        "env_type": "DEV",
        "sf_api_host": "https://api.sapsf.com",
        "sf_company_id": "ACME",
        "ias_host": "ias.ondemand.com",
        "ias_dependency_name": "SF_DEP",
        "encrypted_credentials": b"encrypted-data",
    }
    mock_firestore.collection.return_value.document.return_value.get.return_value = doc_mock

    creds = await manager.get_credentials("user-1", "env-123")
    assert isinstance(creds, SFCredentials)
    assert creds.sf_api_host == "https://api.sapsf.com"
    assert creds.sf_user_id == "admin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_credential_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.credential_manager'`

- [ ] **Step 3: Implement credential manager**

```python
# backend/credential_manager.py
"""SF environment credential management with KMS encryption and Firestore storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from google.cloud import firestore, kms


@dataclass
class SFCredentials:
    """Decrypted SF credentials for a specific environment."""
    sf_api_host: str
    sf_company_id: str
    sf_user_id: str
    sf_password: str
    ias_host: str
    oidc_client_id: str
    oidc_client_secret: str
    ias_dependency_name: str


class CredentialManager:
    """Manages SF environment credentials: KMS encryption + Firestore CRUD."""

    def __init__(
        self,
        firestore_client: firestore.Client,
        kms_client: kms.KeyManagementServiceClient,
        kms_key_name: str,
    ):
        self._db = firestore_client
        self._kms = kms_client
        self._kms_key_name = kms_key_name

    def encrypt_credentials(self, sensitive: dict) -> bytes:
        """Encrypt a dict of sensitive fields with KMS."""
        plaintext = json.dumps(sensitive).encode("utf-8")
        response = self._kms.encrypt(
            request={"name": self._kms_key_name, "plaintext": plaintext}
        )
        return response.ciphertext

    def decrypt_credentials(self, ciphertext: bytes) -> dict:
        """Decrypt KMS-encrypted credentials back to a dict."""
        response = self._kms.decrypt(
            request={"name": self._kms_key_name, "ciphertext": ciphertext}
        )
        return json.loads(response.plaintext.decode("utf-8"))

    def _env_collection(self, user_uid: str):
        return self._db.collection("users").document(user_uid).collection("environments")

    async def create_environment(
        self,
        user_uid: str,
        name: str,
        env_type: str,
        sf_api_host: str,
        sf_company_id: str,
        sf_user_id: str,
        sf_password: str,
        ias_host: str,
        oidc_client_id: str,
        oidc_client_secret: str,
        ias_dependency_name: str,
    ) -> str:
        """Create a new SF environment with encrypted credentials. Returns env ID."""
        encrypted = self.encrypt_credentials({
            "sf_user_id": sf_user_id,
            "sf_password": sf_password,
            "oidc_client_id": oidc_client_id,
            "oidc_client_secret": oidc_client_secret,
        })

        now = datetime.now(timezone.utc).isoformat()
        doc_ref = self._env_collection(user_uid).document()
        doc_ref.set({
            "name": name,
            "env_type": env_type,
            "sf_api_host": sf_api_host,
            "sf_company_id": sf_company_id,
            "ias_host": ias_host,
            "ias_dependency_name": ias_dependency_name,
            "encrypted_credentials": encrypted,
            "last_tested": None,
            "created_at": now,
        })
        return doc_ref.id

    async def list_environments(self, user_uid: str) -> list[dict]:
        """List all environments for a user (without decrypted credentials)."""
        docs = self._env_collection(user_uid).stream()
        envs = []
        for doc in docs:
            data = doc.to_dict()
            envs.append({
                "id": doc.id,
                "name": data["name"],
                "env_type": data["env_type"],
                "sf_api_host": data["sf_api_host"],
                "sf_company_id": data["sf_company_id"],
                "last_tested": data.get("last_tested"),
                "created_at": data["created_at"],
            })
        return envs

    async def get_credentials(self, user_uid: str, env_id: str) -> SFCredentials:
        """Load and decrypt credentials for a specific environment."""
        doc = self._env_collection(user_uid).document(env_id).get()
        if not doc.exists:
            raise ValueError(f"Environment '{env_id}' not found")

        data = doc.to_dict()
        decrypted = self.decrypt_credentials(data["encrypted_credentials"])

        return SFCredentials(
            sf_api_host=data["sf_api_host"],
            sf_company_id=data["sf_company_id"],
            sf_user_id=decrypted["sf_user_id"],
            sf_password=decrypted["sf_password"],
            ias_host=data["ias_host"],
            oidc_client_id=decrypted["oidc_client_id"],
            oidc_client_secret=decrypted["oidc_client_secret"],
            ias_dependency_name=data["ias_dependency_name"],
        )

    async def update_environment(
        self, user_uid: str, env_id: str, updates: dict
    ) -> None:
        """Update environment fields. Re-encrypts if credential fields change."""
        doc_ref = self._env_collection(user_uid).document(env_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise ValueError(f"Environment '{env_id}' not found")

        data = doc.to_dict()
        cred_fields = {"sf_user_id", "sf_password", "oidc_client_id", "oidc_client_secret"}
        has_cred_update = any(k in updates for k in cred_fields)

        firestore_updates = {}
        for k, v in updates.items():
            if v is not None and k not in cred_fields:
                firestore_updates[k] = v

        if has_cred_update:
            current_creds = self.decrypt_credentials(data["encrypted_credentials"])
            for k in cred_fields:
                if k in updates and updates[k] is not None:
                    current_creds[k] = updates[k]
            firestore_updates["encrypted_credentials"] = self.encrypt_credentials(current_creds)

        if firestore_updates:
            doc_ref.update(firestore_updates)

    async def delete_environment(self, user_uid: str, env_id: str) -> None:
        """Delete an environment."""
        self._env_collection(user_uid).document(env_id).delete()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_credential_manager.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/credential_manager.py tests/test_backend/test_credential_manager.py
git commit -m "feat(backend): credential manager with KMS encryption and Firestore CRUD"
```

---

### Task 6: Audit Logger

**Files:**
- Create: `backend/logger.py`
- Create: `tests/test_backend/test_logger.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_backend/test_logger.py
"""Tests for audit logger."""

import pytest
from unittest.mock import MagicMock
from backend.logger import AuditLogger


@pytest.fixture
def mock_firestore():
    return MagicMock()


@pytest.fixture
def audit_logger(mock_firestore):
    return AuditLogger(firestore_client=mock_firestore)


@pytest.mark.asyncio
async def test_log_tool_call(audit_logger, mock_firestore):
    await audit_logger.log_tool_call(
        user_uid="user-1",
        environment_id="env-1",
        tool_name="query_odata",
        tool_args={"entity": "User", "top": 10},
        success=True,
        latency_ms=245,
    )
    mock_firestore.collection.assert_called_once_with("users")


@pytest.mark.asyncio
async def test_log_scrubs_credential_args(audit_logger, mock_firestore):
    """Credential params should never appear in logs."""
    doc_ref = MagicMock()
    mock_firestore.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    await audit_logger.log_tool_call(
        user_uid="user-1",
        environment_id="env-1",
        tool_name="query_odata",
        tool_args={
            "entity": "User",
            "auth_user_id": "secret-user",
            "auth_password": "secret-pass",
            "data_center": "https://api.sapsf.com",
        },
        success=True,
        latency_ms=100,
    )
    call_args = doc_ref.set.call_args[0][0]
    assert "auth_user_id" not in call_args["tool_args"]
    assert "auth_password" not in call_args["tool_args"]
    assert "data_center" not in call_args["tool_args"]
    assert call_args["tool_args"]["entity"] == "User"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_logger.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement audit logger**

```python
# backend/logger.py
"""Audit logger — writes tool call records to Firestore."""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud import firestore

_SCRUB_KEYS = {"data_center", "auth_user_id", "auth_password"}


class AuditLogger:
    """Writes tool call audit logs to Firestore."""

    def __init__(self, firestore_client: firestore.Client):
        self._db = firestore_client

    async def log_tool_call(
        self,
        user_uid: str,
        environment_id: str,
        tool_name: str,
        tool_args: dict,
        success: bool,
        latency_ms: int,
    ) -> str:
        """Log a tool call. Returns log document ID."""
        scrubbed_args = {k: v for k, v in tool_args.items() if k not in _SCRUB_KEYS}

        doc_ref = (
            self._db.collection("users")
            .document(user_uid)
            .collection("logs")
            .document()
        )
        doc_ref.set({
            "environment_id": environment_id,
            "tool_name": tool_name,
            "tool_args": scrubbed_args,
            "success": success,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return doc_ref.id

    async def query_logs(
        self,
        user_uid: str,
        environment_id: str | None = None,
        tool_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query audit logs with optional filters."""
        query = self._db.collection("users").document(user_uid).collection("logs")

        if environment_id:
            query = query.where("environment_id", "==", environment_id)
        if tool_name:
            query = query.where("tool_name", "==", tool_name)

        query = query.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)

        return [{"id": doc.id, **doc.to_dict()} for doc in query.stream()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_logger.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/logger.py tests/test_backend/test_logger.py
git commit -m "feat(backend): audit logger with credential scrubbing"
```

---

### Task 7: File Manager — Cloud Storage Upload + Signed URLs

**Files:**
- Create: `backend/file_manager.py`
- Create: `tests/test_backend/test_file_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backend/test_file_manager.py
"""Tests for file manager (Cloud Storage)."""

import pytest
from unittest.mock import MagicMock, patch
from backend.file_manager import FileManager


@pytest.fixture
def mock_storage():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    return mock_client, mock_bucket


@pytest.fixture
def manager(mock_storage):
    client, _ = mock_storage
    return FileManager(storage_client=client, bucket_name="test-bucket")


def test_upload_file(manager, mock_storage):
    _, mock_bucket = mock_storage
    mock_blob = MagicMock()
    mock_blob.name = "user-1/abc123/workbook.xlsx"
    mock_blob.size = 1024
    mock_bucket.blob.return_value = mock_blob

    result = manager.upload_file(
        user_uid="user-1",
        conversation_id="abc123",
        filename="workbook.xlsx",
        content=b"file-content",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    mock_blob.upload_from_string.assert_called_once_with(
        b"file-content",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert result["name"] == "workbook.xlsx"
    assert result["storage_path"] == "user-1/abc123/workbook.xlsx"


def test_get_signed_url(manager, mock_storage):
    _, mock_bucket = mock_storage
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed-url"
    mock_bucket.blob.return_value = mock_blob

    url = manager.get_signed_url("user-1/abc123/workbook.xlsx")
    assert url == "https://storage.googleapis.com/signed-url"
    mock_blob.generate_signed_url.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_file_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement file manager**

```python
# backend/file_manager.py
"""File manager — upload generated files to Cloud Storage and create signed URLs."""

from __future__ import annotations

from datetime import timedelta

from google.cloud import storage


class FileManager:
    """Manages file uploads to Cloud Storage with signed URL generation."""

    def __init__(self, storage_client: storage.Client, bucket_name: str):
        self._client = storage_client
        self._bucket = self._client.bucket(bucket_name)

    def upload_file(
        self,
        user_uid: str,
        conversation_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """Upload a file to Cloud Storage. Returns metadata dict."""
        storage_path = f"{user_uid}/{conversation_id}/{filename}"
        blob = self._bucket.blob(storage_path)
        blob.upload_from_string(content, content_type=content_type)

        return {
            "name": filename,
            "storage_path": storage_path,
            "size_bytes": blob.size or len(content),
        }

    def get_signed_url(self, storage_path: str, expiration_hours: int = 1) -> str:
        """Generate a signed download URL for a file."""
        blob = self._bucket.blob(storage_path)
        return blob.generate_signed_url(
            expiration=timedelta(hours=expiration_hours),
            method="GET",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_file_manager.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/file_manager.py tests/test_backend/test_file_manager.py
git commit -m "feat(backend): file manager with Cloud Storage upload and signed URLs"
```

---

### Task 8: Gemini Chat Orchestration

**Files:**
- Create: `backend/chat.py`
- Create: `tests/test_backend/test_chat.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backend/test_chat.py
"""Tests for Gemini chat orchestration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.chat import ChatOrchestrator
from backend.credential_manager import SFCredentials


@pytest.fixture
def mock_creds():
    return SFCredentials(
        sf_api_host="https://api.sapsf.com",
        sf_company_id="ACME",
        sf_user_id="admin",
        sf_password="pass",
        ias_host="ias.ondemand.com",
        oidc_client_id="cid",
        oidc_client_secret="csec",
        ias_dependency_name="SF_DEP",
    )


def test_inject_credentials_into_tool_args(mock_creds):
    orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
    args = {"entity": "User", "top": 10}
    injected = orchestrator._inject_credentials(args, mock_creds)
    assert injected["entity"] == "User"
    assert injected["top"] == 10
    assert injected["data_center"] == "https://api.sapsf.com"
    assert injected["auth_user_id"] == "admin"
    assert injected["auth_password"] == "pass"


def test_inject_credentials_preserves_existing_args(mock_creds):
    orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
    args = {"entity": "User", "filter": "userId eq 'admin'"}
    injected = orchestrator._inject_credentials(args, mock_creds)
    assert injected["filter"] == "userId eq 'admin'"
    assert injected["data_center"] == "https://api.sapsf.com"


def test_system_prompt_contains_company_id(mock_creds):
    orchestrator = ChatOrchestrator.__new__(ChatOrchestrator)
    prompt = orchestrator._build_system_prompt(mock_creds)
    assert "ACME" in prompt
    assert "api.sapsf.com" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_chat.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement chat orchestrator**

```python
# backend/chat.py
"""Gemini chat orchestration — message handling with MCP tool execution."""

from __future__ import annotations

import json
import time
from typing import Optional

from google import genai
from google.genai import types

from backend.config import GEMINI_API_KEY, GEMINI_MODEL
from backend.credential_manager import SFCredentials
from backend.tool_bridge import build_tool_declarations, get_tool_registry
from backend.logger import AuditLogger


class ChatOrchestrator:
    """Orchestrates Gemini chat sessions with MCP tool execution."""

    def __init__(self, audit_logger: AuditLogger):
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._tool_declarations = build_tool_declarations()
        self._tool_registry = get_tool_registry()
        self._audit_logger = audit_logger

    def _build_system_prompt(self, creds: SFCredentials) -> str:
        """Build a system prompt with environment context."""
        return (
            "You are SF Assistant, an expert SAP SuccessFactors consultant AI. "
            "You have access to tools that query a live SF instance.\n\n"
            f"Connected to: {creds.sf_api_host} (Company: {creds.sf_company_id})\n\n"
            "Guidelines:\n"
            "- Use the available tools to answer questions about the SF instance.\n"
            "- When you need employee data, search first, then get profiles.\n"
            "- For configuration questions, use discovery tools.\n"
            "- Always explain what you found in clear, professional language.\n"
            "- If a tool returns an error, explain it to the user and suggest alternatives.\n"
            "- Never expose raw credentials or tokens in your responses.\n"
        )

    def _inject_credentials(self, args: dict, creds: SFCredentials) -> dict:
        """Inject environment credentials into tool arguments."""
        injected = dict(args)
        injected["data_center"] = creds.sf_api_host
        injected["auth_user_id"] = creds.sf_user_id
        injected["auth_password"] = creds.sf_password
        return injected

    async def send_message(
        self,
        user_uid: str,
        environment_id: str,
        message: str,
        creds: SFCredentials,
        history: Optional[list[types.Content]] = None,
    ) -> dict:
        """Send a message to Gemini, execute tool calls, return final response.

        Returns:
            {
                "response": "Gemini's final text response",
                "tool_calls": [{"tool_name": ..., "tool_args": ...}, ...],
                "history": [...updated conversation history...],
                "files": [{"name": ..., "storage_path": ..., "size_bytes": ...}, ...],
            }
        """
        system_prompt = self._build_system_prompt(creds)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[types.Tool(function_declarations=self._tool_declarations)],
        )

        chat_history = history or []
        tool_calls_made = []
        files_generated = []

        # Add user message to history
        chat_history.append(types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ))

        # Gemini tool-calling loop
        max_iterations = 10
        for _ in range(max_iterations):
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=chat_history,
                config=config,
            )

            # Check if response contains a function call
            candidate = response.candidates[0]
            parts = candidate.content.parts

            function_call_part = None
            for part in parts:
                if part.function_call:
                    function_call_part = part
                    break

            if not function_call_part:
                # No more tool calls — extract final text
                chat_history.append(candidate.content)
                final_text = "".join(p.text for p in parts if p.text)
                return {
                    "response": final_text,
                    "tool_calls": tool_calls_made,
                    "history": chat_history,
                    "files": files_generated,
                }

            # Execute the tool call
            fc = function_call_part.function_call
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}

            # Add assistant's function call to history
            chat_history.append(candidate.content)

            # Inject credentials and execute
            injected_args = self._inject_credentials(tool_args, creds)
            tool_fn = self._tool_registry.get(tool_name)

            start_time = time.monotonic()
            success = True
            try:
                if tool_fn is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                    success = False
                else:
                    result = await tool_fn(**injected_args)
            except Exception as exc:
                result = {"error": str(exc)}
                success = False

            latency_ms = int((time.monotonic() - start_time) * 1000)

            # Log the tool call
            await self._audit_logger.log_tool_call(
                user_uid=user_uid,
                environment_id=environment_id,
                tool_name=tool_name,
                tool_args=tool_args,
                success=success,
                latency_ms=latency_ms,
            )

            tool_calls_made.append({"tool_name": tool_name, "tool_args": tool_args})

            # Add function response to history
            chat_history.append(types.Content(
                role="user",
                parts=[types.Part(function_response=types.FunctionResponse(
                    name=tool_name,
                    response={"result": result},
                ))],
            ))

        # Max iterations reached
        return {
            "response": "I reached the maximum number of tool calls. Please try a more specific question.",
            "tool_calls": tool_calls_made,
            "history": chat_history,
            "files": files_generated,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_chat.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/chat.py tests/test_backend/test_chat.py
git commit -m "feat(backend): Gemini chat orchestration with tool-calling loop"
```

---

### Task 9: FastAPI App & Routes

**Files:**
- Create: `backend/api.py`
- Create: `tests/test_backend/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backend/test_api.py
"""Integration tests for FastAPI endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# Mock Firebase Admin before importing api module
with patch("firebase_admin.initialize_app"), \
     patch("firebase_admin._apps", {"[DEFAULT]": MagicMock()}):
    from backend.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def mock_auth():
    """Mock auth for all tests — return a valid Veritas Prime user."""
    with patch("backend.api.get_current_user") as mock:
        from backend.auth import FirebaseUser
        mock.return_value = FirebaseUser(
            uid="test-user-1",
            email="jose@veritasprime.com",
            name="Jose",
        )
        yield mock


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_list_environments_empty(client, auth_headers):
    with patch("backend.api._get_credential_manager") as mock_cm:
        mock_cm.return_value.list_environments = AsyncMock(return_value=[])
        resp = client.get("/api/environments", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []


def test_create_environment(client, auth_headers):
    with patch("backend.api._get_credential_manager") as mock_cm:
        mock_cm.return_value.create_environment = AsyncMock(return_value="env-new-123")
        resp = client.post("/api/environments", headers=auth_headers, json={
            "name": "Client DEV",
            "env_type": "DEV",
            "sf_api_host": "https://api.sapsf.com",
            "sf_company_id": "ACME",
            "sf_user_id": "admin",
            "sf_password": "pass",
            "ias_host": "ias.ondemand.com",
            "oidc_client_id": "cid",
            "oidc_client_secret": "csec",
            "ias_dependency_name": "SF_DEP",
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "env-new-123"


def test_delete_environment(client, auth_headers):
    with patch("backend.api._get_credential_manager") as mock_cm:
        mock_cm.return_value.delete_environment = AsyncMock()
        resp = client.delete("/api/environments/env-123", headers=auth_headers)
        assert resp.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backend/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement FastAPI app**

```python
# backend/api.py
"""FastAPI application — routes and middleware for SF Assistant backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from google.cloud import firestore, kms, storage

from backend.auth import FirebaseUser, get_current_user
from backend.chat import ChatOrchestrator
from backend.config import (
    ALLOWED_ORIGINS,
    GCP_KMS_KEY,
    GCP_KMS_KEYRING,
    GCP_KMS_LOCATION,
    GCP_PROJECT_ID,
    GCS_BUCKET,
)
from backend.credential_manager import CredentialManager
from backend.file_manager import FileManager
from backend.logger import AuditLogger
from backend.models import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ConversationSummary,
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentTestResult,
    EnvironmentUpdate,
    LogEntry,
    LogQuery,
    ToolCallInfo,
)


# --- Singletons (created once at startup) ---

_firestore_client: Optional[firestore.Client] = None
_credential_manager: Optional[CredentialManager] = None
_audit_logger: Optional[AuditLogger] = None
_file_manager: Optional[FileManager] = None
_chat_orchestrator: Optional[ChatOrchestrator] = None


def _get_firestore() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    return _firestore_client


def _get_credential_manager() -> CredentialManager:
    global _credential_manager
    if _credential_manager is None:
        kms_client = kms.KeyManagementServiceClient()
        key_name = kms_client.crypto_key_path(
            GCP_PROJECT_ID, GCP_KMS_LOCATION, GCP_KMS_KEYRING, GCP_KMS_KEY,
        )
        _credential_manager = CredentialManager(
            firestore_client=_get_firestore(),
            kms_client=kms_client,
            kms_key_name=key_name,
        )
    return _credential_manager


def _get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(firestore_client=_get_firestore())
    return _audit_logger


def _get_file_manager() -> FileManager:
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager(
            storage_client=storage.Client(project=GCP_PROJECT_ID),
            bucket_name=GCS_BUCKET,
        )
    return _file_manager


def _get_chat_orchestrator() -> ChatOrchestrator:
    global _chat_orchestrator
    if _chat_orchestrator is None:
        _chat_orchestrator = ChatOrchestrator(audit_logger=_get_audit_logger())
    return _chat_orchestrator


# --- App ---

app = FastAPI(title="SF Assistant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health ---

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# --- Chat ---

@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: FirebaseUser = Depends(get_current_user),
):
    cm = _get_credential_manager()
    try:
        creds = await cm.get_credentials(user.uid, request.environment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    orchestrator = _get_chat_orchestrator()

    # TODO: Load conversation history from Firestore if conversation_id provided
    history = None

    result = await orchestrator.send_message(
        user_uid=user.uid,
        environment_id=request.environment_id,
        message=request.message,
        creds=creds,
        history=history,
    )

    # TODO: Save conversation to Firestore

    conversation_id = request.conversation_id or "new-conv"

    return ChatResponse(
        conversation_id=conversation_id,
        message=ChatMessage(
            role="assistant",
            content=result["response"],
            timestamp="",
        ),
        tool_calls=[
            ToolCallInfo(tool_name=tc["tool_name"], tool_args=tc["tool_args"])
            for tc in result["tool_calls"]
        ],
    )


# --- Environments ---

@app.get("/api/environments", response_model=list[EnvironmentResponse])
async def list_environments(user: FirebaseUser = Depends(get_current_user)):
    cm = _get_credential_manager()
    envs = await cm.list_environments(user.uid)
    return [EnvironmentResponse(**e) for e in envs]


@app.post("/api/environments", status_code=201)
async def create_environment(
    env: EnvironmentCreate,
    user: FirebaseUser = Depends(get_current_user),
):
    cm = _get_credential_manager()
    env_id = await cm.create_environment(
        user_uid=user.uid,
        name=env.name,
        env_type=env.env_type,
        sf_api_host=env.sf_api_host,
        sf_company_id=env.sf_company_id,
        sf_user_id=env.sf_user_id,
        sf_password=env.sf_password,
        ias_host=env.ias_host,
        oidc_client_id=env.oidc_client_id,
        oidc_client_secret=env.oidc_client_secret,
        ias_dependency_name=env.ias_dependency_name,
    )
    return {"id": env_id}


@app.put("/api/environments/{env_id}")
async def update_environment(
    env_id: str,
    env: EnvironmentUpdate,
    user: FirebaseUser = Depends(get_current_user),
):
    cm = _get_credential_manager()
    try:
        await cm.update_environment(user.uid, env_id, env.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "updated"}


@app.delete("/api/environments/{env_id}", status_code=204)
async def delete_environment(
    env_id: str,
    user: FirebaseUser = Depends(get_current_user),
):
    cm = _get_credential_manager()
    await cm.delete_environment(user.uid, env_id)


@app.post("/api/environments/{env_id}/test", response_model=EnvironmentTestResult)
async def test_environment(
    env_id: str,
    user: FirebaseUser = Depends(get_current_user),
):
    """Test connectivity to an SF instance by fetching $metadata."""
    import httpx
    import time
    from helpers.credentials import get_bearer_token, resolve_api_host

    cm = _get_credential_manager()
    try:
        creds = await cm.get_credentials(user.uid, env_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
            api_host = resolve_api_host(creds.sf_api_host)
            token = await get_bearer_token(
                http,
                auth_user_id=creds.sf_user_id,
                auth_password=creds.sf_password,
            )
            resp = await http.get(
                f"{api_host}/odata/v2/$metadata",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()

        latency = int((time.monotonic() - start) * 1000)
        return EnvironmentTestResult(
            success=True,
            message=f"Connected to {creds.sf_company_id} successfully",
            latency_ms=latency,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return EnvironmentTestResult(
            success=False,
            message=f"Connection failed: {exc}",
            latency_ms=latency,
        )


# --- Conversations ---

@app.get("/api/conversations", response_model=list[ConversationSummary])
async def list_conversations(user: FirebaseUser = Depends(get_current_user)):
    db = _get_firestore()
    docs = (
        db.collection("users")
        .document(user.uid)
        .collection("conversations")
        .order_by("updated_at", direction=firestore.Query.DESCENDING)
        .limit(50)
        .stream()
    )
    return [
        ConversationSummary(id=doc.id, **doc.to_dict())
        for doc in docs
    ]


@app.delete("/api/conversations/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: str,
    user: FirebaseUser = Depends(get_current_user),
):
    db = _get_firestore()
    db.collection("users").document(user.uid).collection("conversations").document(conv_id).delete()


# --- Logs ---

@app.get("/api/logs", response_model=list[LogEntry])
async def get_logs(
    environment_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    limit: int = 50,
    user: FirebaseUser = Depends(get_current_user),
):
    logger = _get_audit_logger()
    return await logger.query_logs(
        user_uid=user.uid,
        environment_id=environment_id,
        tool_name=tool_name,
        limit=min(limit, 500),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backend/test_api.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api.py tests/test_backend/test_api.py
git commit -m "feat(backend): FastAPI app with chat, environments, conversations, and logs endpoints"
```

---

### Task 10: Dockerfile & Cloud Run Configuration

**Files:**
- Create: `backend/Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./
COPY backend/requirements.txt backend/requirements.txt

# Install main project deps + backend deps
RUN uv sync --extra gcp --no-dev && \
    uv pip install -r backend/requirements.txt

# Copy source code
COPY helpers/ helpers/
COPY models/ models/
COPY tools/ tools/
COPY knowledge/ knowledge/
COPY backend/ backend/

# Cloud Run uses PORT env var
ENV PORT=8080

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Create .dockerignore**

```
# .dockerignore
.git
.env
__pycache__
*.pyc
.pytest_cache
tests/
docs/
exports/
scripts/
templates/
frontend/
node_modules/
.claude/
*.md
```

- [ ] **Step 3: Verify Docker build works**

Run: `docker build -f backend/Dockerfile -t sf-assistant-backend .`
Expected: Image builds without errors

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile .dockerignore
git commit -m "feat(backend): Dockerfile for Cloud Run deployment"
```

---

### Task 11: Run Full Test Suite

- [ ] **Step 1: Run all backend tests**

Run: `uv run pytest tests/test_backend/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run existing MCP tests to confirm no regressions**

Run: `uv run pytest -v`
Expected: All 186+ tests PASS (existing + new backend tests)

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(backend): SF Assistant Backend Core — Phase 1 complete

- FastAPI app with CORS, health check, and all API endpoints
- Gemini chat orchestration with 53-tool function calling loop
- Tool bridge: MCP tools → Gemini FunctionDeclarations (auto-extracted)
- Firebase Auth middleware restricted to @veritasprime.com
- Credential manager: KMS encryption + Firestore CRUD
- File manager: Cloud Storage upload + signed URLs
- Audit logger with credential scrubbing
- Docker image for Cloud Run deployment
- Full test coverage for all backend modules"
```
