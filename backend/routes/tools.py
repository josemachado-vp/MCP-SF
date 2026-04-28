"""Tool catalog and direct-execution endpoints."""

from __future__ import annotations

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
