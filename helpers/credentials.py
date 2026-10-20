"""
Centralized credential resolution for SF API calls.

Uses OIDC 2-step flow via IAS (Identity Authentication Service):
  Step 1: Password grant to IAS → id_token
  Step 2: jwt-bearer exchange on IAS → SF access_token

Env vars:
    SF_API_HOST          - API hostname (e.g., api8preview.sapsf.com)
    SF_COMPANY_ID        - Company ID
    SF_USER_ID           - IAS username
    SF_PASSWORD          - IAS password
    IAS_HOST             - IAS tenant host (e.g., xxx.accounts.ondemand.com)
    OIDC_CLIENT_ID       - OIDC Client ID from IAS
    OIDC_CLIENT_SECRET   - OIDC Client Secret from IAS
    IAS_DEPENDENCY_NAME  - SF dependency name in IAS
    SF_ALLOWED_HOSTS     - Optional comma-separated extra API hosts accepted
                           as data_center overrides (see helpers.sf_client)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from helpers.sf_client import resolve_sf_base_url

# Load .env from project root
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


# --- Token cache ---
# Keyed by the *effective* identity: (ias_host, client_id, user_id,
# password fingerprint, api_host). Keying by a fixed label (the old
# "default") let a request with overridden credentials or host receive a
# token minted for a different user. The password fingerprint ensures a
# per-request auth_user_id override without the right password can never
# be served another caller's cached token.
_CacheKey = tuple[str, str, str, str, str]
_token_cache: dict[_CacheKey, dict[str, str | float]] = {}
_token_locks: dict[_CacheKey, asyncio.Lock] = {}

_DEFAULT_EXPIRES_IN = 3600


def resolve_api_host(data_center: str | None = None) -> str:
    """Resolve the SF API base URL from params or env vars.

    The result is always an allowlisted https base URL (see
    helpers.sf_client.resolve_sf_base_url); unknown hosts raise ValueError.
    """
    api_host = data_center or os.environ.get("SF_API_HOST", "")
    if not api_host:
        raise ValueError(
            "No API host configured. Set SF_API_HOST in .env "
            "or pass data_center parameter."
        )
    return resolve_sf_base_url(api_host)


def _cached_token(key: _CacheKey) -> str | None:
    """Return the cached token for key if still valid (60s buffer)."""
    entry = _token_cache.get(key)
    if entry and entry["access_token"] and time.time() < float(entry["expires_at"]) - 60:
        return str(entry["access_token"])
    return None


def _parse_expires_in(value: object) -> int:
    """Coerce IAS expires_in (int or numeric string) to int seconds."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _DEFAULT_EXPIRES_IN


async def get_bearer_token(
    http: httpx.AsyncClient,
    auth_user_id: str | None = None,
    auth_password: str | None = None,
    api_host: str | None = None,
) -> str:
    """Get a valid SF Bearer token via OIDC 2-step flow.

    Effective credentials (overrides on top of .env) are resolved first and
    used as the cache key, so different users/hosts never share a token.
    Concurrent callers for the same key wait on a per-key lock and reuse
    the token fetched by the first one.
    """
    # Resolve effective IAS credentials
    user_id = auth_user_id or os.environ.get("SF_USER_ID", "")
    password = auth_password or os.environ.get("SF_PASSWORD", "")
    ias_host = os.environ.get("IAS_HOST", "")
    client_id = os.environ.get("OIDC_CLIENT_ID", "")
    client_secret = os.environ.get("OIDC_CLIENT_SECRET", "")
    dependency_name = os.environ.get("IAS_DEPENDENCY_NAME", "")

    if not all([user_id, password, ias_host, client_id, client_secret, dependency_name]):
        missing = []
        if not user_id:
            missing.append("SF_USER_ID")
        if not password:
            missing.append("SF_PASSWORD")
        if not ias_host:
            missing.append("IAS_HOST")
        if not client_id:
            missing.append("OIDC_CLIENT_ID")
        if not client_secret:
            missing.append("OIDC_CLIENT_SECRET")
        if not dependency_name:
            missing.append("IAS_DEPENDENCY_NAME")
        raise ValueError(f"Missing OIDC config: {', '.join(missing)}")

    effective_host = (
        resolve_api_host(api_host)
        if api_host or os.environ.get("SF_API_HOST")
        else ""
    )
    password_fp = hashlib.sha256(password.encode("utf-8")).hexdigest()
    key: _CacheKey = (ias_host, client_id, user_id, password_fp, effective_host)

    token = _cached_token(key)
    if token:
        return token

    lock = _token_locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Double-check: another coroutine may have fetched it while we waited
        token = _cached_token(key)
        if token:
            return token

        token_url = f"https://{ias_host}/oauth2/token"

        # Step 1: Password grant → id_token
        step1_resp = await http.post(
            token_url,
            data={
                "grant_type": "password",
                "username": user_id,
                "password": password,
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "openid",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        if step1_resp.status_code != 200:
            raise ValueError(
                f"OIDC Step 1 failed ({step1_resp.status_code}): {step1_resp.text[:300]}"
            )

        id_token = step1_resp.json().get("id_token")
        if not id_token:
            raise ValueError("OIDC Step 1: No id_token in response")

        # Step 2: jwt-bearer exchange → SF access_token
        step2_resp = await http.post(
            token_url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": id_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "resource": f"urn:sap:identity:application:provider:name:{dependency_name}",
                "scope": "openid",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        if step2_resp.status_code != 200:
            raise ValueError(
                f"OIDC Step 2 failed ({step2_resp.status_code}): {step2_resp.text[:300]}"
            )

        step2_data = step2_resp.json()
        access_token = step2_data["access_token"]
        expires_in = _parse_expires_in(step2_data.get("expires_in"))

        _token_cache[key] = {
            "access_token": access_token,
            "expires_at": time.time() + expires_in,
        }
        return access_token
