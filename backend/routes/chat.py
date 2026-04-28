"""Chat SSE stream + approval endpoint."""

from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.gemini_agent import GeminiAgent
from backend.safety import ApprovalDecision, get_approval_registry


class ChatRequest(BaseModel):
    chat_id: str
    message: str


class ApprovalRequest(BaseModel):
    call_id: str
    decision: ApprovalDecision


def build_router(agent_factory: Callable[[str], GeminiAgent]) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

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
