"""Tests for helpers/credentials.py — token cache isolation and concurrency."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
import respx

from helpers import credentials
from helpers.credentials import get_bearer_token

TOKEN_URL = "https://test.accounts.ondemand.com/oauth2/token"

ENV_VARS = {
    "SF_API_HOST": "https://api8preview.sapsf.com",
    "IAS_HOST": "test.accounts.ondemand.com",
    "SF_USER_ID": "envuser",
    "SF_PASSWORD": "envpass",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "IAS_DEPENDENCY_NAME": "sfdep",
}


@pytest.fixture(autouse=True)
def _reset_cache():
    credentials._token_cache.clear()
    credentials._token_locks.clear()
    with patch.dict("os.environ", ENV_VARS):
        yield
    credentials._token_cache.clear()
    credentials._token_locks.clear()


def _mock_ias(expires_in: object = 3600):
    """IAS mock that mints a token embedding the username of the step-1 call."""
    state = {"user": None, "step2_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        if form["grant_type"] == "password":
            state["user"] = form["username"]
            return httpx.Response(200, json={"id_token": f"id-{form['username']}"})
        state["step2_calls"] += 1
        user = form["assertion"].removeprefix("id-")
        return httpx.Response(
            200, json={"access_token": f"tok-{user}-{state['step2_calls']}", "expires_in": expires_in},
        )

    route = respx.post(TOKEN_URL).mock(side_effect=handler)
    return route, state


@respx.mock
@pytest.mark.asyncio
async def test_default_credentials_cached():
    route, _ = _mock_ias()
    async with httpx.AsyncClient() as http:
        t1 = await get_bearer_token(http)
        t2 = await get_bearer_token(http)
    assert t1 == t2 == "tok-envuser-1"
    assert route.call_count == 2  # one 2-step flow only


@respx.mock
@pytest.mark.asyncio
async def test_override_user_does_not_receive_cached_default_token():
    _mock_ias()
    async with httpx.AsyncClient() as http:
        default_token = await get_bearer_token(http)
        other_token = await get_bearer_token(http, "alice", "alicepw")
    assert default_token.startswith("tok-envuser")
    assert other_token.startswith("tok-alice")


@respx.mock
@pytest.mark.asyncio
async def test_wrong_password_for_same_user_is_not_served_from_cache():
    route, _ = _mock_ias()
    async with httpx.AsyncClient() as http:
        await get_bearer_token(http, "alice", "right")
        calls_before = route.call_count
        await get_bearer_token(http, "alice", "guess")
    assert route.call_count > calls_before  # had to authenticate again


@respx.mock
@pytest.mark.asyncio
async def test_cache_keyed_by_api_host():
    route, _ = _mock_ias()
    async with httpx.AsyncClient() as http:
        t_a = await get_bearer_token(http, api_host="DC4")
        t_b = await get_bearer_token(http, api_host="DC8")
        t_a2 = await get_bearer_token(http, api_host="https://api4.successfactors.com")
    assert t_a != t_b
    assert t_a == t_a2  # same effective host → same cache entry
    assert route.call_count == 4


@pytest.mark.asyncio
async def test_disallowed_api_host_rejected_before_auth():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(TOKEN_URL)
        async with httpx.AsyncClient() as http:
            with pytest.raises(ValueError, match="not an allowed"):
                await get_bearer_token(http, api_host="https://attacker.example.com")
        assert not route.called


@respx.mock
@pytest.mark.asyncio
async def test_concurrent_callers_share_single_fetch():
    route, state = _mock_ias()
    async with httpx.AsyncClient() as http:
        tokens = await asyncio.gather(*(get_bearer_token(http) for _ in range(10)))
    assert len(set(tokens)) == 1
    assert state["step2_calls"] == 1
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_string_expires_in_is_coerced():
    _mock_ias(expires_in="3600")
    async with httpx.AsyncClient() as http:
        await get_bearer_token(http)
    (entry,) = credentials._token_cache.values()
    assert isinstance(entry["expires_at"], float)


@respx.mock
@pytest.mark.asyncio
async def test_invalid_expires_in_falls_back_to_default():
    _mock_ias(expires_in="soon")
    async with httpx.AsyncClient() as http:
        token = await get_bearer_token(http)
        assert await get_bearer_token(http) == token  # usable cache entry


@respx.mock
@pytest.mark.asyncio
async def test_instance_compare_uses_distinct_tokens_per_instance():
    """Instance A and B with different users must never share a token."""
    from tools.instance_compare import _get_client_and_token

    _mock_ias()
    async with httpx.AsyncClient() as http:
        _, token_a, host_a = await _get_client_and_token(http, "DC4", "userA", "pwA")
        _, token_b, host_b = await _get_client_and_token(http, "DC4", "userB", "pwB")
    assert token_a.startswith("tok-userA")
    assert token_b.startswith("tok-userB")
    assert host_a == host_b == "https://api4.successfactors.com"
