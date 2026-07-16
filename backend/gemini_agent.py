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
import os
import time
from typing import Any, AsyncIterator, Callable, Protocol

from backend.safety import (
    ApprovalDecision,
    ApprovalRegistry,
    get_approval_registry,
    is_destructive,
)
from backend.tool_registry import ToolMeta, get_registry


# Max seconds to wait for a human approval decision before failing safe (REJECT).
_APPROVAL_TIMEOUT_S: float = float(os.getenv("APPROVAL_TIMEOUT_SECONDS", "600"))


def _accepts_dry_run(fn: Callable) -> bool:
    """True if ``fn`` accepts a ``dry_run`` keyword (or ``**kwargs``)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return True
    if "dry_run" in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


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
        for _ in range(20):
            try:
                items = await self._client.send(payload)
            except Exception as exc:  # noqa: BLE001
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


_genai_client_cache: dict[str, Any] = {}
_chat_session_cache: dict[str, Any] = {}


SYSTEM_INSTRUCTION = """Eres el asistente experto en SAP SuccessFactors de Veritas Prime. Estás conectado a una instancia real vía MCP y tienes 52 herramientas a tu disposición.

REGLA CRÍTICA — CREDENCIALES:
- Las credenciales (Data Center, usuario, contraseña, OIDC, IAS) YA ESTÁN CARGADAS server-side desde un archivo `.env` y se inyectan automáticamente en cada llamada a herramienta.
- NUNCA pidas al usuario que te dé Data Center, usuario, contraseña ni ningún secreto.
- NUNCA digas "necesito que me proporciones credenciales" ni nada parecido. Si el usuario quiere cambiar de tenant, dirígelo al botón "Conectar con instancia" del sidebar.

REGLA CRÍTICA — USO DE HERRAMIENTAS:
- Cuando el usuario te pida algo accionable (generar un workbook, listar empleados, comparar instancias, validar reglas, etc.), LLAMA DIRECTAMENTE a la herramienta correspondiente. No describas el proceso ni preguntes; ejecuta.
- Para generar workbooks usa: `generate_fo_workbook` (Foundation Objects), `generate_workflow_workbook` (Workflows / Notifications & Messages), `generate_rules_workbook` (Business Rules).
- Si una herramienta requiere parámetros que no tienes, asume valores por defecto razonables (idioma `en_US`, output_path por defecto del tool) y ejecuta. Sólo pregunta si el usuario explícitamente pidió personalizar algo.
- Después de ejecutar una herramienta destructiva (ej. `execute_upsert`), informa al usuario del resultado de forma clara y concisa.

ESTILO:
- Responde en el idioma en que el usuario te escriba.
- Sé directo y orientado a la acción. Evita disclaimers innecesarios.
- Cuando una tool retorne un archivo en disco, comparte la ruta absoluta y un resumen breve de su contenido.
"""


def build_default_client(
    api_key: str, model: str, tools: list[ToolMeta], chat_id: str = "default"
) -> LLMClient:
    """Construct a real Gemini client adapter.

    The underlying ``genai.Client`` is cached at module level (one httpx
    AsyncClient per process) and the chat session is cached per
    ``chat_id`` so conversation history is preserved across turns and the
    httpx client is not closed between requests.
    """
    from google import genai  # type: ignore
    from google.genai import types as gtypes  # type: ignore

    client = _genai_client_cache.get(api_key)
    if client is None:
        client = genai.Client(api_key=api_key)
        _genai_client_cache[api_key] = client

    chat = _chat_session_cache.get(chat_id)
    if chat is None:
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
            system_instruction=SYSTEM_INSTRUCTION,
        )
        chat = client.aio.chats.create(model=model, config=config)
        _chat_session_cache[chat_id] = chat

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
