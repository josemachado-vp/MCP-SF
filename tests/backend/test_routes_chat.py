"""End-to-end test of the chat SSE route using a fake Gemini client."""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.gemini_agent import GeminiAgent


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
    monkeypatch.setenv("SF_API_HOST", "x")
    monkeypatch.setenv("SF_COMPANY_ID", "x")
    monkeypatch.setenv("SF_USER_ID", "x")
    monkeypatch.setenv("SF_PASSWORD", "x")
    monkeypatch.setenv("IAS_HOST", "x")
    monkeypatch.setenv("OIDC_CLIENT_ID", "x")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("IAS_DEPENDENCY_NAME", "x")
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
