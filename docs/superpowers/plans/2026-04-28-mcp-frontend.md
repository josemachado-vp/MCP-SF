# MCP SF Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web frontend (Vite + React + TS) backed by a FastAPI service that lets a SAP SuccessFactors consultant chat with Google Gemini 3 Pro Preview, which orchestrates the existing 52 MCP tools to query/modify SF tenants.

**Architecture:** Existing FastMCP server (`main.py`) stays untouched for Claude Desktop. A new sibling FastAPI app (`backend/`) imports the same Python tool functions, exposes them to Gemini via function-calling, and streams events to a React SPA (`frontend/`) over SSE. Destructive tools (`execute_upsert`) require a human-approval modal before running.

**Tech Stack:** Python 3.10+, FastAPI, sse-starlette, google-genai SDK, Vite 5, React 18, TypeScript, Tailwind CSS, shadcn/ui, Vitest.

**Spec:** `docs/superpowers/specs/2026-04-28-mcp-frontend-design.md`

---

## File Structure

**Backend (new package `backend/`):**
- `backend/__init__.py` — empty package marker
- `backend/app.py` — FastAPI factory, CORS, lifespan, router mounting
- `backend/tool_registry.py` — imports the 52 tools, builds metadata + JSON Schemas, groups by 15 categories
- `backend/safety.py` — destructive-tool detection + per-chat approval-event registry
- `backend/gemini_agent.py` — Gemini chat loop yielding event dicts for SSE
- `backend/routes/__init__.py`
- `backend/routes/health.py` — `GET /api/health`
- `backend/routes/tools.py` — `GET /api/tools`, `POST /api/tools/run`
- `backend/routes/chat.py` — `POST /api/chat` (SSE), `POST /api/chat/{chat_id}/approve`

**Frontend (new package `frontend/`):**
- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`
- `frontend/tailwind.config.ts`, `frontend/postcss.config.js`
- `frontend/public/veritas-prime-logo.jpg` — copied from `C:\Users\JoséMachado\Desktop\OIP.jpg`
- `frontend/src/main.tsx`, `frontend/src/App.tsx`
- `frontend/src/styles/globals.css` — Tailwind directives + palette CSS vars
- `frontend/src/lib/types.ts` — shared TS interfaces (`ToolMeta`, `ChatEvent`, `ApprovalDecision`)
- `frontend/src/lib/api.ts` — fetch + SSE client (`postChat`, `approveTool`, `listTools`)
- `frontend/src/components/Sidebar.tsx` — logo + 15 collapsible category sections
- `frontend/src/components/Chat.tsx` — message list + input
- `frontend/src/components/ExecutionPanel.tsx` — last-tool-call inspector
- `frontend/src/components/ApprovalModal.tsx` — destructive-tool consent modal

**Tests (new):**
- `tests/backend/__init__.py`
- `tests/backend/test_tool_registry.py`
- `tests/backend/test_safety.py`
- `tests/backend/test_gemini_agent.py`
- `tests/backend/test_routes_chat.py`
- `frontend/src/components/__tests__/Sidebar.test.tsx`
- `frontend/src/components/__tests__/ApprovalModal.test.tsx`

**Modified:**
- `pyproject.toml` — add `[project.optional-dependencies] frontend = [...]`
- `.env.example` — add `GEMINI_API_KEY`, `GEMINI_MODEL`, `FRONTEND_BACKEND_PORT`, `FRONTEND_CORS_ORIGIN`
- `.gitignore` — add `frontend/node_modules`, `frontend/dist`
- `README.md` — append "Web frontend" section with run instructions

---

## Phase 1 — Backend

### Task 1: Add backend dependencies and env scaffolding

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `backend/__init__.py`
- Create: `backend/routes/__init__.py`
- Create: `tests/backend/__init__.py`

- [ ] **Step 1:** Append the optional dependency group to `pyproject.toml` after the existing `gcp` group:

```toml
frontend = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sse-starlette>=2.1",
    "google-genai>=0.3",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2:** Append to `.env.example`:

```
# --- Web frontend (optional) ---
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3-pro-preview
FRONTEND_BACKEND_PORT=8001
FRONTEND_CORS_ORIGIN=http://localhost:5173
```

- [ ] **Step 3:** Append to `.gitignore`:

```
frontend/node_modules/
frontend/dist/
frontend/.vite/
```

- [ ] **Step 4:** Create empty `backend/__init__.py`, `backend/routes/__init__.py`, `tests/backend/__init__.py`.

- [ ] **Step 5:** Install deps: `uv sync --extra frontend --extra dev`. Expected: completes without error.

- [ ] **Step 6:** Commit:

```bash
git add pyproject.toml .env.example .gitignore backend tests/backend uv.lock
git commit -m "chore: scaffold backend package and add frontend deps"
```

---

### Task 2: Tool registry — load and categorize 52 tools

**Files:**
- Create: `backend/tool_registry.py`
- Test: `tests/backend/test_tool_registry.py`

The 15 categories and their tool functions match `main.py`. The registry imports each function, derives a JSON Schema from its signature using `inspect` + type hints, and exposes a flat list and a category-grouped view.

- [ ] **Step 1:** Write the failing test `tests/backend/test_tool_registry.py`:

```python
"""Tests for the backend tool registry."""

from backend.tool_registry import (
    ToolMeta,
    get_registry,
    CATEGORIES,
)


def test_registry_loads_52_tools():
    registry = get_registry()
    assert len(registry.tools) == 52


def test_registry_has_15_categories():
    registry = get_registry()
    assert len(registry.by_category) == 15
    assert set(registry.by_category.keys()) == set(CATEGORIES.keys())


def test_every_tool_has_schema_and_metadata():
    registry = get_registry()
    for tool in registry.tools:
        assert isinstance(tool, ToolMeta)
        assert tool.name
        assert tool.category in CATEGORIES
        assert tool.description  # non-empty docstring summary
        assert isinstance(tool.parameters_schema, dict)
        assert tool.parameters_schema.get("type") == "object"
        assert "properties" in tool.parameters_schema
        assert callable(tool.fn)


def test_execute_upsert_marked_destructive():
    registry = get_registry()
    upsert = registry.by_name["execute_upsert"]
    assert upsert.is_destructive is True


def test_get_employee_profile_not_destructive():
    registry = get_registry()
    profile = registry.by_name["get_employee_profile"]
    assert profile.is_destructive is False


def test_lookup_by_name():
    registry = get_registry()
    assert "search_employees" in registry.by_name
    assert registry.by_name["search_employees"].category == "Employee"
```

- [ ] **Step 2:** Run: `uv run pytest tests/backend/test_tool_registry.py -v`. Expected: ImportError / module not found.

- [ ] **Step 3:** Implement `backend/tool_registry.py`:

```python
"""Registry of MCP tools exposed to the Gemini agent.

Loads the same 52 tool functions registered in main.py, groups them by
the 15 categories defined in CLAUDE.md, and derives JSON Schemas for
Gemini function-calling.
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

# --- Imports mirror main.py ---
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
    compare_instance_config, compare_picklists,
    compare_business_rules, compare_foundation_objects,
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


CATEGORIES: dict[str, list[Callable]] = {
    "Discovery": [get_entity_metadata, list_entities, get_picklist_values, query_odata],
    "Business Rules": [validate_rule_fields, generate_rule_spec, generate_rule_doc, generate_rule_test],
    "Employee": [search_employees, get_employee_profile, get_org_chart, get_employee_history, compare_employees],
    "Organization": [get_org_structure, get_position_details, list_foundation_objects],
    "Configuration": [list_business_rules, get_permission_roles],
    "Data Import": [validate_import_template, generate_import_template, execute_upsert],
    "Analytics": [get_headcount, get_compensation_analytics, simulate_rule_impact],
    "Instance Comparison": [compare_instance_config, compare_picklists, compare_business_rules, compare_foundation_objects],
    "Audit & Troubleshooting": [audit_employee_data, find_data_anomalies, trace_rule_execution, check_permission_access, validate_effective_dating],
    "Documentation": [generate_functional_spec, generate_cutover_checklist, generate_data_dictionary, generate_test_script],
    "Migration": [validate_migration_file, generate_migration_sequence, reconcile_data, generate_purge_file],
    "MDF": [get_mdf_object_definition, generate_mdf_import_template, list_mdf_objects],
    "Go-Live": [run_go_live_checks, generate_reconciliation_report],
    "Country": [get_country_specific_fields, validate_country_compliance, generate_country_config_guide],
    "Workbook Generator": [generate_fo_workbook, generate_workflow_workbook, generate_rules_workbook],
}

DESTRUCTIVE_TOOL_NAMES: set[str] = {"execute_upsert"}


_PRIMITIVE_MAP = {
    str: "string", int: "integer", float: "number", bool: "boolean",
}


def _python_type_to_schema(annotation: Any) -> dict[str, Any]:
    """Map a python type hint to a minimal JSON Schema fragment."""
    if annotation is inspect._empty or annotation is Any:
        return {"type": "string"}
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[X] / Union[X, None]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_schema(non_none[0])
        return {"type": "string"}

    if origin in (list, typing.List):
        item_schema = _python_type_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    if origin in (dict, typing.Dict):
        return {"type": "object"}

    if annotation in _PRIMITIVE_MAP:
        return {"type": _PRIMITIVE_MAP[annotation]}

    # Pydantic models / dataclasses → object
    return {"type": "object"}


def _build_schema(fn: Callable) -> dict[str, Any]:
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        properties[name] = _python_type_to_schema(param.annotation)
        if param.default is inspect._empty:
            required.append(name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _summary(doc: str | None) -> str:
    if not doc:
        return ""
    first = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
    return first[:500]


@dataclass
class ToolMeta:
    name: str
    category: str
    description: str
    parameters_schema: dict[str, Any]
    is_destructive: bool
    fn: Callable = field(repr=False)


@dataclass
class ToolRegistry:
    tools: list[ToolMeta]
    by_name: dict[str, ToolMeta]
    by_category: dict[str, list[ToolMeta]]


_registry_cache: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    tools: list[ToolMeta] = []
    by_category: dict[str, list[ToolMeta]] = {}

    for category, fns in CATEGORIES.items():
        bucket: list[ToolMeta] = []
        for fn in fns:
            meta = ToolMeta(
                name=fn.__name__,
                category=category,
                description=_summary(fn.__doc__),
                parameters_schema=_build_schema(fn),
                is_destructive=fn.__name__ in DESTRUCTIVE_TOOL_NAMES,
                fn=fn,
            )
            tools.append(meta)
            bucket.append(meta)
        by_category[category] = bucket

    by_name = {t.name: t for t in tools}
    _registry_cache = ToolRegistry(tools=tools, by_name=by_name, by_category=by_category)
    return _registry_cache
```

- [ ] **Step 4:** Run: `uv run pytest tests/backend/test_tool_registry.py -v`. Expected: 5 passed.

- [ ] **Step 5:** Commit:

```bash
git add backend/tool_registry.py tests/backend/test_tool_registry.py
git commit -m "feat(backend): add tool registry with categorized 52 SF tools"
```

---

### Task 3: Safety module — destructive-tool approval gate

**Files:**
- Create: `backend/safety.py`
- Test: `tests/backend/test_safety.py`

`safety.py` keeps an in-memory map of pending approvals keyed by `(chat_id, call_id)`. The agent awaits the future; the approval HTTP endpoint resolves it.

- [ ] **Step 1:** Write the failing test `tests/backend/test_safety.py`:

```python
import asyncio
import pytest

from backend.safety import (
    ApprovalDecision,
    ApprovalRegistry,
    is_destructive,
)


def test_is_destructive_flags_upsert():
    assert is_destructive("execute_upsert") is True
    assert is_destructive("get_employee_profile") is False


@pytest.mark.asyncio
async def test_request_and_resolve_approval():
    reg = ApprovalRegistry()
    fut = reg.request("chat-1", "call-1")
    reg.resolve("chat-1", "call-1", ApprovalDecision.APPROVE)
    decision = await asyncio.wait_for(fut, timeout=1.0)
    assert decision is ApprovalDecision.APPROVE


@pytest.mark.asyncio
async def test_resolve_unknown_call_is_noop():
    reg = ApprovalRegistry()
    # Should not raise
    reg.resolve("nope", "nope", ApprovalDecision.REJECT)


@pytest.mark.asyncio
async def test_request_then_reject():
    reg = ApprovalRegistry()
    fut = reg.request("chat-2", "call-2")
    reg.resolve("chat-2", "call-2", ApprovalDecision.REJECT)
    assert (await fut) is ApprovalDecision.REJECT
```

- [ ] **Step 2:** Run: `uv run pytest tests/backend/test_safety.py -v`. Expected: ImportError.

- [ ] **Step 3:** Implement `backend/safety.py`:

```python
"""Destructive-tool approval gate for the Gemini agent."""

from __future__ import annotations

import asyncio
import enum

from backend.tool_registry import DESTRUCTIVE_TOOL_NAMES


class ApprovalDecision(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    FORCE_DRY_RUN = "force_dry_run"


def is_destructive(tool_name: str) -> bool:
    return tool_name in DESTRUCTIVE_TOOL_NAMES


class ApprovalRegistry:
    """Per-process registry of pending tool-call approvals."""

    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], asyncio.Future[ApprovalDecision]] = {}

    def request(self, chat_id: str, call_id: str) -> asyncio.Future[ApprovalDecision]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._pending[(chat_id, call_id)] = fut
        return fut

    def resolve(self, chat_id: str, call_id: str, decision: ApprovalDecision) -> None:
        fut = self._pending.pop((chat_id, call_id), None)
        if fut is not None and not fut.done():
            fut.set_result(decision)


_registry: ApprovalRegistry | None = None


def get_approval_registry() -> ApprovalRegistry:
    global _registry
    if _registry is None:
        _registry = ApprovalRegistry()
    return _registry
```

- [ ] **Step 4:** Run: `uv run pytest tests/backend/test_safety.py -v`. Expected: 4 passed.

- [ ] **Step 5:** Commit:

```bash
git add backend/safety.py tests/backend/test_safety.py
git commit -m "feat(backend): add destructive-tool approval registry"
```

---

### Task 4: Gemini agent — chat loop with function calling

**Files:**
- Create: `backend/gemini_agent.py`
- Test: `tests/backend/test_gemini_agent.py`

The agent is an async generator that yields event dicts. It accepts an injectable Gemini client (so tests use a fake). Real client construction is encapsulated in a tiny factory used by routes.

The event types yielded:
- `{"type": "message_delta", "text": "..."}`
- `{"type": "tool_call_proposed", "call_id": ..., "name": ..., "args": {...}}`
- `{"type": "tool_call_pending_approval", "call_id": ..., "name": ..., "args": {...}}`
- `{"type": "tool_call_executed", "call_id": ..., "name": ..., "args": {...}, "result": ..., "duration_ms": ..., "dry_run_forced": bool}`
- `{"type": "error", "message": "..."}`
- `{"type": "final"}`

- [ ] **Step 1:** Write the failing test `tests/backend/test_gemini_agent.py`:

```python
"""Tests for the Gemini agent chat loop using a fake LLM client."""

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

import pytest

from backend.gemini_agent import GeminiAgent
from backend.safety import ApprovalDecision, ApprovalRegistry


@dataclass
class _FakeCall:
    name: str
    args: dict[str, Any]
    id: str = "call-1"


class _FakeClient:
    """Mimics the slice of google-genai we use.

    Each `send_message` returns a list of either text deltas or function-call
    requests. The test scripts these turns in advance.
    """

    def __init__(self, scripted_turns: list[list[Any]]):
        self._turns = scripted_turns
        self._turn_idx = 0

    async def send(self, _user_or_tool_payload):
        idx = self._turn_idx
        self._turn_idx += 1
        return self._turns[idx]


@pytest.mark.asyncio
async def test_text_only_turn_streams_message_and_final():
    client = _FakeClient([[{"text": "Hello world"}]])
    agent = GeminiAgent(client=client, registry_overrides={})
    events = [e async for e in agent.run(chat_id="c1", user_message="hi")]
    types = [e["type"] for e in events]
    assert types == ["message_delta", "final"]
    assert events[0]["text"] == "Hello world"


@pytest.mark.asyncio
async def test_read_only_tool_call_executes_immediately():
    def fake_tool(name: str) -> dict:
        return {"echo": name}

    client = _FakeClient([
        [{"function_call": _FakeCall(name="fake_tool", args={"name": "Ada"})}],
        [{"text": "Done"}],
    ])
    agent = GeminiAgent(
        client=client,
        registry_overrides={"fake_tool": (fake_tool, False)},
    )
    events = [e async for e in agent.run(chat_id="c2", user_message="run it")]
    types = [e["type"] for e in events]
    assert "tool_call_proposed" in types
    assert "tool_call_executed" in types
    executed = next(e for e in events if e["type"] == "tool_call_executed")
    assert executed["result"] == {"echo": "Ada"}
    assert executed["dry_run_forced"] is False


@pytest.mark.asyncio
async def test_destructive_tool_waits_for_approval_then_runs():
    captured = {}

    def fake_upsert(records: list, dry_run: bool = True) -> dict:
        captured["dry_run"] = dry_run
        return {"ok": True, "dry_run": dry_run}

    approvals = ApprovalRegistry()
    client = _FakeClient([
        [{"function_call": _FakeCall(name="fake_upsert", args={"records": [], "dry_run": False})}],
        [{"text": "Upsert complete"}],
    ])
    agent = GeminiAgent(
        client=client,
        registry_overrides={"fake_upsert": (fake_upsert, True)},
        approvals=approvals,
    )

    async def consume():
        return [e async for e in agent.run(chat_id="c3", user_message="upsert")]

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    approvals.resolve("c3", "call-1", ApprovalDecision.APPROVE)
    events = await task

    types = [e["type"] for e in events]
    assert "tool_call_pending_approval" in types
    assert "tool_call_executed" in types
    assert captured["dry_run"] is False


@pytest.mark.asyncio
async def test_destructive_tool_rejected_returns_error_to_model():
    def fake_upsert(records: list, dry_run: bool = True):  # pragma: no cover - not called
        raise AssertionError("must not run when rejected")

    approvals = ApprovalRegistry()
    client = _FakeClient([
        [{"function_call": _FakeCall(name="fake_upsert", args={"records": []})}],
        [{"text": "Cancelled by user"}],
    ])
    agent = GeminiAgent(
        client=client,
        registry_overrides={"fake_upsert": (fake_upsert, True)},
        approvals=approvals,
    )

    async def consume():
        return [e async for e in agent.run(chat_id="c4", user_message="upsert")]

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    approvals.resolve("c4", "call-1", ApprovalDecision.REJECT)
    events = await task

    types = [e["type"] for e in events]
    assert "tool_call_executed" not in types
    # The agent should still complete with a final event.
    assert types[-1] == "final"


@pytest.mark.asyncio
async def test_force_dry_run_overrides_args():
    captured = {}

    def fake_upsert(records: list, dry_run: bool = True) -> dict:
        captured["dry_run"] = dry_run
        return {"ok": True}

    approvals = ApprovalRegistry()
    client = _FakeClient([
        [{"function_call": _FakeCall(name="fake_upsert", args={"records": [], "dry_run": False})}],
        [{"text": "ok"}],
    ])
    agent = GeminiAgent(
        client=client,
        registry_overrides={"fake_upsert": (fake_upsert, True)},
        approvals=approvals,
    )

    async def consume():
        return [e async for e in agent.run(chat_id="c5", user_message="upsert")]

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    approvals.resolve("c5", "call-1", ApprovalDecision.FORCE_DRY_RUN)
    events = await task

    assert captured["dry_run"] is True
    executed = next(e for e in events if e["type"] == "tool_call_executed")
    assert executed["dry_run_forced"] is True
```

- [ ] **Step 2:** Run: `uv run pytest tests/backend/test_gemini_agent.py -v`. Expected: ImportError.

- [ ] **Step 3:** Implement `backend/gemini_agent.py`:

```python
"""Gemini chat loop adapter.

Drives a turn-based conversation between a user and Gemini, executing
local Python tools when Gemini requests them. Yields event dicts so the
SSE route can stream them to the frontend.

The real Gemini client is constructed in `build_default_client()` from
the `google-genai` SDK; tests inject a fake client conforming to the
duck-typed interface used by `_send_to_model`.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, AsyncIterator, Callable, Protocol

from backend.safety import (
    ApprovalDecision,
    ApprovalRegistry,
    get_approval_registry,
    is_destructive,
)
from backend.tool_registry import ToolMeta, get_registry


class LLMClient(Protocol):
    async def send(self, payload: Any) -> list[Any]: ...


class GeminiAgent:
    """Conversational loop between Gemini and the local tool registry.

    Parameters
    ----------
    client:
        Object exposing `async send(payload)` returning a list of items
        where each item is either ``{"text": str}`` or
        ``{"function_call": obj_with_name_args_id}``.
    registry_overrides:
        Optional ``{name: (callable, is_destructive)}`` map for tests.
        When provided, only these tools are exposed to the agent.
    approvals:
        Approval registry; defaults to the process-wide singleton.
    """

    def __init__(
        self,
        client: LLMClient,
        registry_overrides: dict[str, tuple[Callable, bool]] | None = None,
        approvals: ApprovalRegistry | None = None,
    ) -> None:
        self._client = client
        self._approvals = approvals or get_approval_registry()
        if registry_overrides is not None:
            self._tools = {
                name: ToolMeta(
                    name=name, category="test", description="",
                    parameters_schema={"type": "object", "properties": {}},
                    is_destructive=destructive, fn=fn,
                )
                for name, (fn, destructive) in registry_overrides.items()
            }
        else:
            self._tools = get_registry().by_name

    async def run(self, chat_id: str, user_message: str) -> AsyncIterator[dict]:
        payload: Any = {"user_message": user_message}
        # Soft cap on tool-call iterations to prevent runaway loops.
        for _ in range(20):
            try:
                items = await self._client.send(payload)
            except Exception as exc:  # noqa: BLE001 — surface to UI
                yield {"type": "error", "message": str(exc)}
                yield {"type": "final"}
                return

            tool_responses: list[dict] = []
            had_function_call = False

            for item in items:
                if "text" in item:
                    yield {"type": "message_delta", "text": item["text"]}
                    continue
                if "function_call" in item:
                    had_function_call = True
                    call = item["function_call"]
                    name = call.name
                    args = dict(call.args)
                    call_id = getattr(call, "id", name)

                    yield {
                        "type": "tool_call_proposed",
                        "call_id": call_id,
                        "name": name,
                        "args": args,
                    }

                    tool = self._tools.get(name)
                    if tool is None:
                        tool_responses.append({
                            "name": name, "id": call_id,
                            "response": {"error": f"unknown tool: {name}"},
                        })
                        continue

                    decision: ApprovalDecision | None = None
                    if tool.is_destructive or is_destructive(name):
                        yield {
                            "type": "tool_call_pending_approval",
                            "call_id": call_id, "name": name, "args": args,
                        }
                        fut = self._approvals.request(chat_id, call_id)
                        decision = await fut

                        if decision is ApprovalDecision.REJECT:
                            tool_responses.append({
                                "name": name, "id": call_id,
                                "response": {"error": "user_rejected"},
                            })
                            continue
                        if decision is ApprovalDecision.FORCE_DRY_RUN:
                            args["dry_run"] = True

                    started = time.perf_counter()
                    try:
                        result = tool.fn(**args)
                        if inspect.isawaitable(result):
                            result = await result
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": str(exc)}
                    duration_ms = int((time.perf_counter() - started) * 1000)

                    yield {
                        "type": "tool_call_executed",
                        "call_id": call_id,
                        "name": name,
                        "args": args,
                        "result": result,
                        "duration_ms": duration_ms,
                        "dry_run_forced": decision is ApprovalDecision.FORCE_DRY_RUN,
                    }
                    tool_responses.append({
                        "name": name, "id": call_id, "response": result,
                    })

            if not had_function_call:
                yield {"type": "final"}
                return

            payload = {"tool_responses": tool_responses}

        yield {"type": "error", "message": "agent loop exceeded max iterations"}
        yield {"type": "final"}


def build_default_client(api_key: str, model: str, tools: list[ToolMeta]) -> LLMClient:
    """Construct a real Gemini client adapter.

    Implementation detail: wraps `google.genai.Client` so its `send_message`
    surface matches the duck-typed `LLMClient` protocol used above. The
    exact SDK call shape is finalized at implementation time against the
    installed `google-genai` version (see spec §13).
    """
    from google import genai  # type: ignore
    from google.genai import types as gtypes  # type: ignore

    function_declarations = [
        gtypes.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters=t.parameters_schema,
        )
        for t in tools
    ]
    config = gtypes.GenerateContentConfig(
        tools=[gtypes.Tool(function_declarations=function_declarations)],
    )
    client = genai.Client(api_key=api_key)
    chat = client.aio.chats.create(model=model, config=config)

    class _Adapter:
        async def send(self, payload: Any) -> list[Any]:
            if "user_message" in payload:
                response = await chat.send_message(payload["user_message"])
            else:
                parts = [
                    gtypes.Part.from_function_response(
                        name=tr["name"], response=tr["response"]
                    )
                    for tr in payload["tool_responses"]
                ]
                response = await chat.send_message(parts)
            items: list[Any] = []
            for cand in response.candidates or []:
                for part in cand.content.parts or []:
                    if getattr(part, "text", None):
                        items.append({"text": part.text})
                    if getattr(part, "function_call", None):
                        items.append({"function_call": part.function_call})
            return items

    return _Adapter()
```

- [ ] **Step 4:** Run: `uv run pytest tests/backend/test_gemini_agent.py -v`. Expected: 5 passed.

- [ ] **Step 5:** Commit:

```bash
git add backend/gemini_agent.py tests/backend/test_gemini_agent.py
git commit -m "feat(backend): add Gemini chat loop with approval gating"
```

---

### Task 5: Health route

**Files:**
- Create: `backend/routes/health.py`

- [ ] **Step 1:** Write `backend/routes/health.py`:

```python
"""Health endpoint — reports backend readiness.

Verifies that the env vars required for SF and Gemini are present.
Does not call the remote APIs; that happens lazily on first use.
"""

from __future__ import annotations

import os
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])

_REQUIRED_SF = [
    "SF_API_HOST", "SF_COMPANY_ID", "SF_USER_ID", "SF_PASSWORD",
    "IAS_HOST", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "IAS_DEPENDENCY_NAME",
]
_REQUIRED_GEMINI = ["GEMINI_API_KEY"]


@router.get("/health")
def health() -> dict:
    missing_sf = [k for k in _REQUIRED_SF if not os.getenv(k)]
    missing_gemini = [k for k in _REQUIRED_GEMINI if not os.getenv(k)]
    ok = not missing_sf and not missing_gemini
    return {
        "ok": ok,
        "missing_sf": missing_sf,
        "missing_gemini": missing_gemini,
        "model": os.getenv("GEMINI_MODEL", "gemini-3-pro-preview"),
    }
```

- [ ] **Step 2:** Commit:

```bash
git add backend/routes/health.py
git commit -m "feat(backend): add /api/health route"
```

---

### Task 6: Tools route — catalog and direct execution

**Files:**
- Create: `backend/routes/tools.py`

- [ ] **Step 1:** Write `backend/routes/tools.py`:

```python
"""Tool catalog and direct-execution endpoints."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.tool_registry import get_registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolRunRequest(BaseModel):
    name: str
    args: dict[str, Any] = {}


@router.get("")
def list_tools() -> dict:
    reg = get_registry()
    return {
        "categories": [
            {
                "name": cat,
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "is_destructive": t.is_destructive,
                        "parameters_schema": t.parameters_schema,
                    }
                    for t in tools
                ],
            }
            for cat, tools in reg.by_category.items()
        ]
    }


@router.post("/run")
async def run_tool(req: ToolRunRequest) -> dict:
    reg = get_registry()
    tool = reg.by_name.get(req.name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"unknown tool: {req.name}")
    if tool.is_destructive:
        # Direct sidebar execution forces dry_run for safety.
        req.args["dry_run"] = True
    try:
        result = tool.fn(**req.args)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": req.name, "result": result}
```

- [ ] **Step 2:** Commit:

```bash
git add backend/routes/tools.py
git commit -m "feat(backend): add /api/tools listing and direct-run endpoints"
```

---

### Task 7: Chat route — SSE stream + approval endpoint

**Files:**
- Create: `backend/routes/chat.py`
- Test: `tests/backend/test_routes_chat.py`

- [ ] **Step 1:** Write the failing test `tests/backend/test_routes_chat.py`:

```python
"""End-to-end test of the chat SSE route using a fake Gemini client."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.gemini_agent import GeminiAgent
from backend.safety import get_approval_registry


class _StaticClient:
    def __init__(self, turns):
        self._turns = turns
        self._i = 0

    async def send(self, _payload):
        out = self._turns[self._i]
        self._i += 1
        return out


@pytest.fixture
def app_with_fake_agent(monkeypatch):
    def fake_factory(_chat_id):
        client = _StaticClient([[{"text": "Hi there"}]])
        return GeminiAgent(client=client, registry_overrides={})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("SF_API_HOST", "x"); monkeypatch.setenv("SF_COMPANY_ID", "x")
    monkeypatch.setenv("SF_USER_ID", "x"); monkeypatch.setenv("SF_PASSWORD", "x")
    monkeypatch.setenv("IAS_HOST", "x"); monkeypatch.setenv("OIDC_CLIENT_ID", "x")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "x"); monkeypatch.setenv("IAS_DEPENDENCY_NAME", "x")
    app = create_app(agent_factory=fake_factory)
    return app


def test_chat_streams_message_and_final(app_with_fake_agent):
    client = TestClient(app_with_fake_agent)
    with client.stream("POST", "/api/chat", json={"chat_id": "c1", "message": "hi"}) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    assert "message_delta" in body
    assert "Hi there" in body
    assert "final" in body


def test_approve_endpoint_resolves_pending(app_with_fake_agent):
    client = TestClient(app_with_fake_agent)
    # No pending approval — endpoint still returns 200 (idempotent).
    r = client.post("/api/chat/c1/approve", json={"call_id": "x", "decision": "approve"})
    assert r.status_code == 200
```

- [ ] **Step 2:** Run: `uv run pytest tests/backend/test_routes_chat.py -v`. Expected: ImportError on `backend.app`.

- [ ] **Step 3:** Write `backend/routes/chat.py`:

```python
"""Chat SSE stream + approval endpoint."""

from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.gemini_agent import GeminiAgent
from backend.safety import ApprovalDecision, get_approval_registry

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    chat_id: str
    message: str


class ApprovalRequest(BaseModel):
    call_id: str
    decision: ApprovalDecision


def build_router(agent_factory: Callable[[str], GeminiAgent]) -> APIRouter:
    @router.post("")
    async def chat(req: ChatRequest, request: Request):
        agent = agent_factory(req.chat_id)

        async def event_source():
            async for event in agent.run(chat_id=req.chat_id, user_message=req.message):
                if await request.is_disconnected():
                    break
                yield {"event": event["type"], "data": json.dumps(event)}
        return EventSourceResponse(event_source())

    @router.post("/{chat_id}/approve")
    async def approve(chat_id: str, body: ApprovalRequest) -> dict:
        get_approval_registry().resolve(chat_id, body.call_id, body.decision)
        return {"ok": True}

    return router
```

- [ ] **Step 4:** (skip — implemented in Task 8 below; the test will pass after Task 8 wires `create_app`.)

---

### Task 8: FastAPI app factory

**Files:**
- Create: `backend/app.py`

- [ ] **Step 1:** Write `backend/app.py`:

```python
"""FastAPI application factory for the SF MCP web frontend."""

from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.gemini_agent import GeminiAgent, build_default_client
from backend.routes import chat as chat_routes
from backend.routes.health import router as health_router
from backend.routes.tools import router as tools_router
from backend.tool_registry import get_registry


def _default_agent_factory(_chat_id: str) -> GeminiAgent:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    registry = get_registry()
    client = build_default_client(api_key=api_key, model=model, tools=registry.tools)
    return GeminiAgent(client=client)


def create_app(agent_factory: Callable[[str], GeminiAgent] | None = None) -> FastAPI:
    load_dotenv()
    app = FastAPI(title="SF MCP Frontend")
    cors_origin = os.getenv("FRONTEND_CORS_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cors_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(tools_router)
    app.include_router(chat_routes.build_router(agent_factory or _default_agent_factory))
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FRONTEND_BACKEND_PORT", "8001"))
    uvicorn.run("backend.app:app", host="127.0.0.1", port=port, reload=True)
```

- [ ] **Step 2:** Run: `uv run pytest tests/backend/test_routes_chat.py -v`. Expected: 2 passed.

- [ ] **Step 3:** Run the full backend suite: `uv run pytest tests/backend/ -v`. Expected: all green.

- [ ] **Step 4:** Smoke-start the server: `uv run python -m backend.app` — visit `http://127.0.0.1:8001/api/health`. Expected: JSON with `"ok": true` (assuming `.env` is filled). Stop with Ctrl+C.

- [ ] **Step 5:** Commit:

```bash
git add backend/app.py backend/routes/chat.py tests/backend/test_routes_chat.py
git commit -m "feat(backend): wire FastAPI app factory and chat SSE route"
```

---

## Phase 2 — Frontend

### Task 9: Scaffold Vite + React + TS + Tailwind + shadcn/ui

**Files:**
- Create: `frontend/` (npm scaffold)

- [ ] **Step 1:** From repo root: `npm create vite@latest frontend -- --template react-ts`. Confirm prompts.

- [ ] **Step 2:** `cd frontend && npm install`.

- [ ] **Step 3:** Install Tailwind: `npm install -D tailwindcss@latest postcss@latest autoprefixer@latest && npx tailwindcss init -p`.

- [ ] **Step 4:** Replace `frontend/tailwind.config.js` (rename to `.ts` if preferred) content with:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#1B2D4F",
          dark: "#0F1B33",
        },
        "gray-secondary": "#8A8D8F",
        "bg-soft": "#F7F8FA",
        success: "#0E8F5E",
        danger: "#B42318",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 5:** Replace `frontend/src/index.css` (or rename to `frontend/src/styles/globals.css` and import from `main.tsx`) with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root { height: 100%; }
body {
  font-family: 'Inter', system-ui, sans-serif;
  color: #1B2D4F;
  background: #FFFFFF;
}
```

- [ ] **Step 6:** Install runtime deps: `npm install @microsoft/fetch-event-source clsx`.

- [ ] **Step 7:** Install test deps: `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`.

- [ ] **Step 8:** Add to `frontend/package.json` scripts:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run"
}
```

- [ ] **Step 9:** Add `frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true, setupFiles: "./src/test-setup.ts" },
});
```

- [ ] **Step 10:** Create `frontend/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 11:** Verify build: `npm run build`. Expected: completes without errors.

- [ ] **Step 12:** Copy logo:

```bash
cp "C:/Users/JoséMachado/Desktop/OIP.jpg" frontend/public/veritas-prime-logo.jpg
```

- [ ] **Step 13:** Commit:

```bash
git add frontend
git commit -m "chore(frontend): scaffold Vite + React + Tailwind + Vitest"
```

---

### Task 10: Shared types and SSE API client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1:** Write `frontend/src/lib/types.ts`:

```ts
export type ApprovalDecision = "approve" | "reject" | "force_dry_run";

export interface ToolMeta {
  name: string;
  description: string;
  is_destructive: boolean;
  parameters_schema: Record<string, unknown>;
}

export interface ToolCategory {
  name: string;
  tools: ToolMeta[];
}

export type ChatEvent =
  | { type: "message_delta"; text: string }
  | { type: "tool_call_proposed"; call_id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_call_pending_approval"; call_id: string; name: string; args: Record<string, unknown> }
  | {
      type: "tool_call_executed";
      call_id: string;
      name: string;
      args: Record<string, unknown>;
      result: unknown;
      duration_ms: number;
      dry_run_forced: boolean;
    }
  | { type: "error"; message: string }
  | { type: "final" };
```

- [ ] **Step 2:** Write `frontend/src/lib/api.ts`:

```ts
import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { ApprovalDecision, ChatEvent, ToolCategory } from "./types";

const BASE = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8001";

export async function listTools(): Promise<{ categories: ToolCategory[] }> {
  const r = await fetch(`${BASE}/api/tools`);
  if (!r.ok) throw new Error(`listTools failed: ${r.status}`);
  return r.json();
}

export async function approveTool(
  chatId: string,
  callId: string,
  decision: ApprovalDecision,
): Promise<void> {
  const r = await fetch(`${BASE}/api/chat/${chatId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ call_id: callId, decision }),
  });
  if (!r.ok) throw new Error(`approve failed: ${r.status}`);
}

export async function streamChat(
  chatId: string,
  message: string,
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  await fetchEventSource(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, message }),
    signal,
    onmessage(ev) {
      if (!ev.data) return;
      try {
        onEvent(JSON.parse(ev.data) as ChatEvent);
      } catch {
        /* ignore malformed */
      }
    },
    onerror(err) {
      throw err;
    },
  });
}
```

- [ ] **Step 3:** Commit:

```bash
git add frontend/src/lib
git commit -m "feat(frontend): shared types and SSE API client"
```

---

### Task 11: Sidebar component (logo + 15 categories, 52 tools)

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Test: `frontend/src/components/__tests__/Sidebar.test.tsx`

- [ ] **Step 1:** Write the failing test:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Sidebar } from "../Sidebar";

const fakeCats = [
  { name: "Discovery", tools: [
    { name: "list_entities", description: "List entities", is_destructive: false, parameters_schema: {} },
  ]},
  { name: "Data Import", tools: [
    { name: "execute_upsert", description: "Upsert", is_destructive: true, parameters_schema: {} },
  ]},
];

describe("Sidebar", () => {
  it("renders categories and tools", () => {
    render(<Sidebar categories={fakeCats} onPickTool={() => {}} />);
    expect(screen.getByText("Discovery")).toBeInTheDocument();
    expect(screen.getByText("Data Import")).toBeInTheDocument();
  });

  it("invokes onPickTool with the tool name", () => {
    const onPick = vi.fn();
    render(<Sidebar categories={fakeCats} onPickTool={onPick} />);
    fireEvent.click(screen.getByText("Discovery"));
    fireEvent.click(screen.getByText("list_entities"));
    expect(onPick).toHaveBeenCalledWith("list_entities");
  });
});
```

- [ ] **Step 2:** Run: `cd frontend && npm test`. Expected: fail, missing module.

- [ ] **Step 3:** Implement `frontend/src/components/Sidebar.tsx`:

```tsx
import { useState } from "react";
import type { ToolCategory } from "../lib/types";

interface Props {
  categories: ToolCategory[];
  onPickTool: (name: string) => void;
}

export function Sidebar({ categories, onPickTool }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (name: string) =>
    setOpen((s) => ({ ...s, [name]: !s[name] }));

  return (
    <aside className="w-[280px] h-full bg-bg-soft border-r border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-200 flex items-center gap-3">
        <img
          src="/veritas-prime-logo.jpg"
          alt="Veritas Prime"
          className="h-9 w-auto"
        />
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {categories.map((cat) => (
          <div key={cat.name}>
            <button
              type="button"
              onClick={() => toggle(cat.name)}
              className="w-full text-left px-4 py-2 text-sm font-semibold text-navy hover:bg-white"
            >
              {cat.name}
              <span className="float-right text-gray-secondary">
                {open[cat.name] ? "−" : "+"}
              </span>
            </button>
            {open[cat.name] && (
              <ul className="pb-1">
                {cat.tools.map((t) => (
                  <li key={t.name}>
                    <button
                      type="button"
                      onClick={() => onPickTool(t.name)}
                      className="w-full text-left px-6 py-1.5 text-xs font-mono text-gray-700 hover:text-navy hover:bg-white flex items-center gap-2"
                      title={t.description}
                    >
                      <span className="truncate">{t.name}</span>
                      {t.is_destructive && (
                        <span className="text-[10px] uppercase tracking-wide text-danger">
                          ⚠
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 4:** Run: `npm test`. Expected: 2 passed.

- [ ] **Step 5:** Commit:

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/components/__tests__/Sidebar.test.tsx
git commit -m "feat(frontend): sidebar with logo + 15 collapsible categories"
```

---

### Task 12: ApprovalModal component

**Files:**
- Create: `frontend/src/components/ApprovalModal.tsx`
- Test: `frontend/src/components/__tests__/ApprovalModal.test.tsx`

- [ ] **Step 1:** Write the failing test:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ApprovalModal } from "../ApprovalModal";

describe("ApprovalModal", () => {
  it("renders the tool name and args", () => {
    render(
      <ApprovalModal
        toolName="execute_upsert"
        args={{ records: [{ id: 1 }], dry_run: false }}
        onDecision={() => {}}
      />,
    );
    expect(screen.getByText(/execute_upsert/)).toBeInTheDocument();
    expect(screen.getByText(/dry_run/)).toBeInTheDocument();
  });

  it("emits the right decision", () => {
    const cb = vi.fn();
    render(<ApprovalModal toolName="execute_upsert" args={{}} onDecision={cb} />);
    fireEvent.click(screen.getByText(/Approve/));
    fireEvent.click(screen.getByText(/Reject/));
    fireEvent.click(screen.getByText(/Force dry/i));
    expect(cb.mock.calls.map((c) => c[0])).toEqual([
      "approve", "reject", "force_dry_run",
    ]);
  });
});
```

- [ ] **Step 2:** Run: `npm test`. Expected: fail.

- [ ] **Step 3:** Implement `frontend/src/components/ApprovalModal.tsx`:

```tsx
import type { ApprovalDecision } from "../lib/types";

interface Props {
  toolName: string;
  args: Record<string, unknown>;
  onDecision: (d: ApprovalDecision) => void;
}

export function ApprovalModal({ toolName, args, onDecision }: Props) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-xl w-[560px] max-w-[90vw] border border-gray-200">
        <header className="px-5 py-4 border-b border-gray-200">
          <h2 className="text-navy font-semibold">
            Confirm destructive tool
          </h2>
          <p className="text-xs text-gray-secondary mt-1">
            Gemini wants to execute <code className="font-mono">{toolName}</code>
          </p>
        </header>
        <div className="px-5 py-4">
          <pre className="text-xs bg-bg-soft rounded p-3 max-h-[260px] overflow-auto border border-gray-200">
{JSON.stringify(args, null, 2)}
          </pre>
        </div>
        <footer className="px-5 py-3 border-t border-gray-200 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => onDecision("reject")}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-bg-soft"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => onDecision("force_dry_run")}
            className="px-3 py-1.5 text-sm bg-success text-white rounded hover:opacity-90"
          >
            Force dry_run
          </button>
          <button
            type="button"
            onClick={() => onDecision("approve")}
            className="px-3 py-1.5 text-sm bg-navy text-white rounded hover:bg-navy-dark"
          >
            Approve
          </button>
        </footer>
      </div>
    </div>
  );
}
```

- [ ] **Step 4:** Run: `npm test`. Expected: all green.

- [ ] **Step 5:** Commit:

```bash
git add frontend/src/components/ApprovalModal.tsx frontend/src/components/__tests__/ApprovalModal.test.tsx
git commit -m "feat(frontend): destructive-tool approval modal"
```

---

### Task 13: ExecutionPanel component

**Files:**
- Create: `frontend/src/components/ExecutionPanel.tsx`

- [ ] **Step 1:** Write `frontend/src/components/ExecutionPanel.tsx`:

```tsx
interface Execution {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  duration_ms: number;
  dry_run_forced: boolean;
}

interface Props {
  last: Execution | null;
}

export function ExecutionPanel({ last }: Props) {
  if (!last) {
    return (
      <aside className="w-[360px] h-full border-l border-gray-200 bg-bg-soft p-4 text-sm text-gray-secondary">
        No tool calls yet.
      </aside>
    );
  }
  return (
    <aside className="w-[360px] h-full border-l border-gray-200 bg-bg-soft flex flex-col">
      <header className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-navy font-semibold text-sm">Last execution</h3>
        <div className="mt-1 flex items-center gap-2 text-xs">
          <code className="font-mono text-navy">{last.name}</code>
          <span className="text-gray-secondary">{last.duration_ms} ms</span>
          {last.dry_run_forced && (
            <span className="text-success uppercase tracking-wide">dry-run</span>
          )}
        </div>
      </header>
      <section className="px-4 py-3 border-b border-gray-200">
        <h4 className="text-xs uppercase tracking-wide text-gray-secondary mb-1">Args</h4>
        <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-auto max-h-[180px]">
{JSON.stringify(last.args, null, 2)}
        </pre>
      </section>
      <section className="px-4 py-3 flex-1 overflow-auto">
        <h4 className="text-xs uppercase tracking-wide text-gray-secondary mb-1">Result</h4>
        <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-auto">
{JSON.stringify(last.result, null, 2)}
        </pre>
      </section>
    </aside>
  );
}
```

- [ ] **Step 2:** Commit:

```bash
git add frontend/src/components/ExecutionPanel.tsx
git commit -m "feat(frontend): execution panel for last tool call"
```

---

### Task 14: Chat component

**Files:**
- Create: `frontend/src/components/Chat.tsx`

- [ ] **Step 1:** Write `frontend/src/components/Chat.tsx`:

```tsx
import { useRef } from "react";

export interface ChatMessage {
  role: "user" | "assistant" | "tool";
  text: string;
}

interface Props {
  messages: ChatMessage[];
  pendingToolName: string | null;
  onSend: (text: string) => void;
}

export function Chat({ messages, pendingToolName, onSend }: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const v = inputRef.current?.value.trim();
    if (!v) return;
    onSend(v);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <main className="flex-1 h-full flex flex-col bg-white">
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "max-w-[80%] ml-auto bg-navy text-white rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
                : m.role === "tool"
                ? "max-w-[80%] bg-bg-soft border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono whitespace-pre-wrap"
                : "max-w-[80%] bg-bg-soft border border-gray-200 rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
            }
          >
            {m.text}
          </div>
        ))}
        {pendingToolName && (
          <div className="text-xs text-gray-secondary italic">
            Gemini is calling <code className="font-mono">{pendingToolName}</code>…
          </div>
        )}
      </div>
      <div className="border-t border-gray-200 p-3 flex gap-2">
        <textarea
          ref={inputRef}
          rows={2}
          placeholder="Ask Gemini something about your SF tenant…"
          className="flex-1 resize-none border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-navy"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          onClick={submit}
          className="px-4 py-2 bg-navy text-white rounded text-sm hover:bg-navy-dark"
        >
          Send
        </button>
      </div>
    </main>
  );
}
```

- [ ] **Step 2:** Commit:

```bash
git add frontend/src/components/Chat.tsx
git commit -m "feat(frontend): chat panel with input and message list"
```

---

### Task 15: App.tsx — assemble the layout and event loop

**Files:**
- Create/Replace: `frontend/src/App.tsx`
- Create/Replace: `frontend/src/main.tsx`

- [ ] **Step 1:** Replace `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 2:** Replace `frontend/src/App.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { Chat, type ChatMessage } from "./components/Chat";
import { ExecutionPanel } from "./components/ExecutionPanel";
import { ApprovalModal } from "./components/ApprovalModal";
import { approveTool, listTools, streamChat } from "./lib/api";
import type { ChatEvent, ToolCategory } from "./lib/types";

interface PendingApproval {
  callId: string;
  name: string;
  args: Record<string, unknown>;
}
interface Execution {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  duration_ms: number;
  dry_run_forced: boolean;
}

export default function App() {
  const [categories, setCategories] = useState<ToolCategory[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [lastExec, setLastExec] = useState<Execution | null>(null);
  const [pendingTool, setPendingTool] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const chatIdRef = useRef<string>(crypto.randomUUID());
  const inputAppendRef = useRef<((s: string) => void) | null>(null);

  useEffect(() => {
    listTools().then((r) => setCategories(r.categories)).catch((e) => {
      setMessages((m) => [...m, { role: "assistant", text: `Backend unreachable: ${e.message}` }]);
    });
  }, []);

  const handleSend = async (text: string) => {
    setMessages((m) => [...m, { role: "user", text }]);
    const ctrl = new AbortController();
    let assistantBuffer = "";
    try {
      await streamChat(chatIdRef.current, text, (ev: ChatEvent) => {
        switch (ev.type) {
          case "message_delta":
            assistantBuffer += ev.text;
            setMessages((m) => {
              const copy = [...m];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") {
                copy[copy.length - 1] = { role: "assistant", text: assistantBuffer };
              } else {
                copy.push({ role: "assistant", text: assistantBuffer });
              }
              return copy;
            });
            break;
          case "tool_call_proposed":
            setPendingTool(ev.name);
            break;
          case "tool_call_pending_approval":
            setPendingApproval({ callId: ev.call_id, name: ev.name, args: ev.args });
            break;
          case "tool_call_executed":
            setPendingTool(null);
            setLastExec({
              name: ev.name, args: ev.args, result: ev.result,
              duration_ms: ev.duration_ms, dry_run_forced: ev.dry_run_forced,
            });
            setMessages((m) => [...m, {
              role: "tool",
              text: `${ev.name} → ${JSON.stringify(ev.result).slice(0, 240)}…`,
            }]);
            break;
          case "error":
            setMessages((m) => [...m, { role: "assistant", text: `⚠ ${ev.message}` }]);
            break;
          case "final":
            assistantBuffer = "";
            setPendingTool(null);
            break;
        }
      }, ctrl.signal);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((m) => [...m, { role: "assistant", text: `Stream error: ${msg}` }]);
    }
  };

  const handleApprove = async (decision: "approve" | "reject" | "force_dry_run") => {
    if (!pendingApproval) return;
    await approveTool(chatIdRef.current, pendingApproval.callId, decision);
    setPendingApproval(null);
  };

  return (
    <div className="h-screen flex">
      <Sidebar
        categories={categories}
        onPickTool={(name) => inputAppendRef.current?.(`@${name} `)}
      />
      <Chat messages={messages} pendingToolName={pendingTool} onSend={handleSend} />
      <ExecutionPanel last={lastExec} />
      {pendingApproval && (
        <ApprovalModal
          toolName={pendingApproval.name}
          args={pendingApproval.args}
          onDecision={handleApprove}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3:** Run dev servers in two terminals:
  - Backend: `uv run python -m backend.app`
  - Frontend: `cd frontend && npm run dev`

  Open the printed Vite URL. Expected: layout renders with sidebar + chat + empty execution panel; sidebar populated with 15 categories.

- [ ] **Step 4:** Manual smoke test in browser:
  1. Click a Discovery category → expand, see tool names.
  2. Type *"List the first 5 entities"* → press Enter.
  3. Watch a `query_odata` or `list_entities` call appear in the execution panel; the chat shows Gemini's reply.
  4. Type *"Upsert this dummy record …"* (or similar) — confirm the `ApprovalModal` appears for `execute_upsert`.

  If any step fails, fix the corresponding component before committing.

- [ ] **Step 5:** Commit:

```bash
git add frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat(frontend): assemble app layout and SSE event loop"
```

---

## Phase 3 — Documentation

### Task 16: Update README with run instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Append a new section to `README.md`:

````markdown
## Web frontend (optional)

A local web UI lets you chat with Gemini, which orchestrates the 52 MCP tools.

### Install

```bash
uv sync --extra frontend
cd frontend && npm install
```

### Configure

Add to `.env`:

```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3-pro-preview
FRONTEND_BACKEND_PORT=8001
FRONTEND_CORS_ORIGIN=http://localhost:5173
```

### Run

In two terminals:

```bash
# 1. Backend (FastAPI + SSE)
uv run python -m backend.app

# 2. Frontend (Vite)
cd frontend && npm run dev
```

Open the Vite URL printed in the second terminal.

### Safety

`execute_upsert` always pops a confirmation modal before running. Choose
**Approve**, **Reject**, or **Force dry_run**. Direct sidebar execution of
`execute_upsert` is forced to `dry_run=true`.
````

- [ ] **Step 2:** Commit:

```bash
git add README.md
git commit -m "docs: document web frontend setup"
```

---

## Final Verification

- [ ] `uv run pytest tests/backend/ -v` — all green
- [ ] `cd frontend && npm test` — all green
- [ ] `cd frontend && npm run build` — succeeds
- [ ] Both servers start cleanly; `/api/health` returns `ok: true`
- [ ] Manual chat smoke test: a read-only tool call (e.g., `list_entities`) succeeds end-to-end
- [ ] Manual destructive smoke test: `execute_upsert` triggers the modal, all 3 decisions behave correctly
