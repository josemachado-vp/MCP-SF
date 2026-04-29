"""FastAPI application factory for the SF MCP web frontend."""

from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.gemini_agent import GeminiAgent, build_default_client
from backend.routes import chat as chat_routes
from backend.routes.config import router as config_router
from backend.routes.health import router as health_router
from backend.routes.tools import router as tools_router
from backend.tool_registry import get_registry


def _default_agent_factory(chat_id: str) -> GeminiAgent:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    registry = get_registry()
    client = build_default_client(
        api_key=api_key, model=model, tools=registry.tools, chat_id=chat_id
    )
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
    app.include_router(config_router)
    app.include_router(tools_router)
    app.include_router(chat_routes.build_router(agent_factory or _default_agent_factory))
    return app


# Module-level `app` is intentionally NOT instantiated here, because importing
# this module should not require GEMINI_API_KEY to be set (e.g. for tests).
# Use `uvicorn backend.app:create_app --factory` to run, or the __main__ block below.

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("FRONTEND_BACKEND_PORT", "8001"))
    uvicorn.run("backend.app:create_app", host="127.0.0.1", port=port, reload=False, factory=True)
