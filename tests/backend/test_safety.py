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
