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

    def resolve(self, chat_id: str, call_id: str, decision: ApprovalDecision) -> bool:
        """Resolve a pending approval. Returns True iff one was actually pending."""
        fut = self._pending.pop((chat_id, call_id), None)
        if fut is not None and not fut.done():
            fut.set_result(decision)
            return True
        return False

    def cancel(self, chat_id: str, call_id: str) -> None:
        """Drop a pending approval (timeout / client disconnect) so it can't leak."""
        fut = self._pending.pop((chat_id, call_id), None)
        if fut is not None and not fut.done():
            fut.cancel()


_registry: ApprovalRegistry | None = None


def get_approval_registry() -> ApprovalRegistry:
    global _registry
    if _registry is None:
        _registry = ApprovalRegistry()
    return _registry
