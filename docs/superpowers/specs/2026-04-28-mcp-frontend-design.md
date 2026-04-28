# MCP SF Frontend — Design Spec

**Date:** 2026-04-28
**Status:** Approved (brainstorming)
**Owner:** José Machado

## 1. Goal

Build a web frontend that lets a user (SF consultant) chat with **Google Gemini 3 Pro Preview**, which acts as the LLM agent invoking the existing 52 MCP tools (`tools/*.py`) against SAP SuccessFactors tenants.

The existing FastMCP server (`main.py`) keeps working as-is for Claude Desktop. The new frontend stack lives alongside it in the same repo.

## 2. Stack

| Layer | Choice |
|---|---|
| Frontend | Vite + React 18 + TypeScript |
| Styling | Tailwind CSS + shadcn/ui components |
| Backend | FastAPI (Python 3.10+, same `uv` env) |
| Streaming | Server-Sent Events (SSE) via `sse-starlette` |
| LLM SDK | `google-genai` (official Gemini SDK) |
| Model | `gemini-3-pro-preview` |
| Testing (BE) | pytest + pytest-asyncio + respx |
| Testing (FE) | Vitest + React Testing Library |

The frontend is **not** deployed to Vercel — runs locally / on internal infrastructure.

## 3. Visual Design

Corporate Veritas Prime palette (white + navy):

| Token | Hex | Usage |
|---|---|---|
| `navy-primary` | `#1B2D4F` | Primary brand color, headers, primary buttons |
| `navy-dark` | `#0F1B33` | Hover states, active accents |
| `gray-secondary` | `#8A8D8F` | Secondary text, "PRIME" word in logo |
| `bg-white` | `#FFFFFF` | Chat background |
| `bg-soft` | `#F7F8FA` | Sidebar, execution panel background |
| `border` | `#E5E7EB` | Dividers |
| `text-primary` | `#1B2D4F` | Headings |
| `text-body` | `#374151` | Body copy |
| `success` | `#0E8F5E` | Dry-run badges, OK states |
| `danger` | `#B42318` | Destructive modal accents |

- **Font:** Inter (with system fallback).
- **Logo:** copy `C:\Users\JoséMachado\Desktop\OIP.jpg` to `frontend/public/veritas-prime-logo.jpg` and render at ~36px height in the sidebar header.

## 4. Architecture

```
┌────────────────────────┐    HTTP + SSE    ┌─────────────────────────┐
│  Vite + React + TS     │ ───────────────► │   FastAPI (backend/)    │
│  Tailwind + shadcn/ui  │                  │                         │
│  - Chat                │ ◄─────────────── │  POST /api/chat (SSE)   │
│  - Sidebar (15 cats)   │      events      │  POST /api/chat/{id}/   │
│  - Execution panel     │      stream      │       approve           │
│  - Approval modal      │                  │  GET  /api/tools        │
└────────────────────────┘                  │  POST /api/tools/run    │
                                            │  GET  /api/health       │
                                            └────────────┬────────────┘
                                                         │
                                        ┌────────────────┼────────────────┐
                                        ▼                                 ▼
                               ┌──────────────────┐            ┌─────────────────────┐
                               │ google-genai SDK │            │ tools/ (imported)   │
                               │ Gemini 3 Pro Prev│            │ → helpers/sf_client │
                               │ function-calling │            │ → SF tenants (OData)│
                               └──────────────────┘            └─────────────────────┘
```

Key principle: the FastAPI backend **imports the same Python functions** the MCP server registers. No logic duplication.

## 5. Backend Components (`backend/`)

| File | Responsibility |
|---|---|
| `app.py` | FastAPI app factory, CORS for `http://localhost:5173`, mounts routers, lifespan loads tool registry once |
| `tool_registry.py` | Imports the 52 tools from `tools/`, groups them by the 15 categories defined in `CLAUDE.md`, exposes metadata: `{name, category, description, parameters_schema, is_destructive}`. Generates JSON Schema from each function's signature/docstring for Gemini `FunctionDeclaration`s |
| `gemini_agent.py` | Owns the Gemini chat loop: sends user message + tool catalog → receives function calls → executes via registry → feeds results back → emits final text. Yields events for SSE |
| `safety.py` | `DESTRUCTIVE_TOOLS = {"execute_upsert"}`. When a destructive tool is proposed, the agent pauses and waits for an approval decision via an `asyncio.Event` keyed by `chat_id` |
| `routes/chat.py` | `POST /api/chat` — opens SSE stream; emits events: `message_delta`, `tool_call_proposed`, `tool_call_pending_approval`, `tool_call_executed`, `error`, `final`. `POST /api/chat/{id}/approve` — body `{decision: "approve" \| "reject" \| "force_dry_run"}` |
| `routes/tools.py` | `GET /api/tools` returns categorized catalog. `POST /api/tools/run` lets sidebar trigger a tool directly without going through Gemini (for power users) |
| `routes/health.py` | `GET /api/health` validates SF + Gemini credentials at startup; returns 503 if missing |

The 15 categories from `CLAUDE.md`: Discovery, Business Rules, Employee, Organization, Configuration, Data Import, Analytics, Instance Comparison, Audit & Troubleshooting, Documentation, Migration, MDF, Go-Live, Country, Workbook Generator.

## 6. Frontend Components (`frontend/src/`)

| File | Responsibility |
|---|---|
| `App.tsx` | 3-pane layout: sidebar 280px, chat fluid center, execution panel 360px (collapsible) |
| `components/Sidebar.tsx` | Veritas Prime logo + 15 collapsible category sections listing the 52 tools. Click on a tool name inserts `@tool_name` token into the chat input |
| `components/Chat.tsx` | Message history, markdown rendering, JSON/table viewers for tool results, "Gemini is calling `<tool>`..." inline indicator |
| `components/ExecutionPanel.tsx` | Latest tool execution: name, formatted args (JSON), raw response, duration ms, dry-run badge |
| `components/ApprovalModal.tsx` | Shown on `tool_call_pending_approval`. Displays tool name + args (JSON). Three buttons: **Approve** (navy), **Reject** (gray), **Force dry_run** (success green) |
| `lib/api.ts` | SSE client wrapping `EventSource`/`fetch`; TS event types matching backend |
| `lib/types.ts` | Shared TS interfaces: `ToolMeta`, `ChatEvent`, `ApprovalDecision` |
| `lib/theme.ts` | Tailwind config tokens for the palette in §3 |

## 7. Data Flow — Destructive Tool Path

1. User sends *"Upload these employees from CSV X"* → `POST /api/chat` (SSE opens)
2. Backend calls Gemini with the 52-tool catalog
3. Gemini returns `function_call: execute_upsert(args=...)`
4. `safety.py` flags it destructive → backend emits `tool_call_pending_approval` event → frontend shows `ApprovalModal`
5. User clicks **Approve** → `POST /api/chat/{id}/approve {decision: "approve"}`
6. Backend executes the tool, emits `tool_call_executed` (execution panel updates), feeds result back to Gemini
7. Gemini emits final answer → backend streams as `message_delta` events → chat renders

Read-only tools skip steps 4–5: executed immediately.

## 8. Error Handling

| Failure | Behavior |
|---|---|
| Gemini API quota / 5xx | Backend catches, emits `error` event; chat shows red banner with retry button |
| Tool raises exception (SF 401, timeout, validation) | Caught in registry; passed to Gemini as `function_response = {"error": "..."}` so it can reason/retry; also surfaced in execution panel |
| Missing SF or Gemini env vars | `/api/health` returns 503 at startup; frontend shows config error screen with `.env` instructions |
| User rejects destructive call | Gemini receives `function_response = {"error": "user_rejected"}`; explains and offers alternative |
| SSE disconnect | Frontend reconnects with last event id; backend resumes from buffered events for that `chat_id` (in-memory, session-scoped) |

## 9. Configuration

New env vars added to `.env.example`:

```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3-pro-preview
FRONTEND_BACKEND_PORT=8001
FRONTEND_CORS_ORIGIN=http://localhost:5173
```

Existing SF env vars (`SF_API_HOST`, `SF_COMPANY_ID`, etc.) are reused unchanged — the same `helpers/credentials.py` resolves them.

`pyproject.toml`: add an optional dependency group:

```toml
[project.optional-dependencies]
frontend = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sse-starlette>=2.1",
  "google-genai>=0.3",
]
```

Install with `uv sync --extra frontend`.

## 10. Testing Strategy

**Backend (pytest):**
- `test_tool_registry.py` — loads exactly 52 tools across 15 categories; every tool has a JSON Schema
- `test_gemini_agent.py` — mocked Gemini client; verifies function-calling loop, error propagation, destructive-tool pause
- `test_safety.py` — destructive set, approval flow with `asyncio.Event`
- `test_routes_chat.py` — SSE event sequence; approval endpoint
- All Gemini and SF HTTP calls mocked (no live tenant required), consistent with existing `tests/`

**Frontend (Vitest + RTL):**
- `Sidebar.test.tsx` — renders 15 categories, 52 tools; `@tool` insertion
- `ApprovalModal.test.tsx` — three actions emit correct decisions
- `Chat.test.tsx` — SSE event handling with mock EventSource

## 11. Folder Layout (after implementation)

```
MCP SF/
├── main.py                          # existing MCP entry — UNCHANGED
├── tools/                           # existing — UNCHANGED
├── helpers/                         # existing — UNCHANGED
├── backend/                         # NEW
│   ├── __init__.py
│   ├── app.py
│   ├── gemini_agent.py
│   ├── tool_registry.py
│   ├── safety.py
│   └── routes/
│       ├── __init__.py
│       ├── chat.py
│       ├── tools.py
│       └── health.py
├── frontend/                        # NEW
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/
│   │   └── veritas-prime-logo.jpg
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/
│       │   ├── Sidebar.tsx
│       │   ├── Chat.tsx
│       │   ├── ExecutionPanel.tsx
│       │   └── ApprovalModal.tsx
│       ├── lib/
│       │   ├── api.ts
│       │   ├── types.ts
│       │   └── theme.ts
│       └── styles/
│           └── globals.css
└── tests/
    └── backend/                     # NEW
        ├── test_tool_registry.py
        ├── test_gemini_agent.py
        ├── test_safety.py
        └── test_routes_chat.py
```

## 12. Out of Scope (v1)

- Authentication / multi-user (single local user)
- Persistent chat history (sessions are in-memory only)
- Vercel/cloud deployment
- File upload UI (CSV imports keep going through scripts)
- Playwright E2E tests
- Mobile / responsive layout below 1024px

## 13. Open Items

None at design time. Confirm `gemini-3-pro-preview` is the exact model ID used by `google-genai` at implementation time and adjust `GEMINI_MODEL` default if Google's SDK names it differently.
