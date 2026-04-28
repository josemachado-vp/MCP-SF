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

    Each `send` returns a list of either text deltas or function-call
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
