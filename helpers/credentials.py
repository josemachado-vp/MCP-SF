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
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


# --- Token cache (keyed by tenant_id for multi-tenant support) ---
_token_cache: dict[str, dict[str, str | float]] = {}


def _get_tenant_cache(tenant_id: str = "default") -> dict[str, str | float]:
    """Get or create token cache entry for a tenant."""
    if tenant_id not in _token_cache:
        _token_cache[tenant_id] = {"access_token": "", "expires_at": 0.0}
    return _token_cache[tenant_id]


def resolve_api_host(data_center: str | None = None) -> str:
    """Resolve the SF API base URL from params or env vars."""
    if data_center:
        api_host = data_center
    else:
        api_host = os.environ.get("SF_API_HOST", "")
        if not api_host:
            raise ValueError(
                "No API host configured. Set SF_API_HOST in .env "
                "or pass data_center parameter."
            )

    if api_host and not api_host.startswith("https://") and "." in api_host:
        api_host = f"https://{api_host}"

    return api_host


async def get_bearer_token(
    http: httpx.AsyncClient,
    auth_user_id: str | None = None,
    auth_password: str | None = None,
    tenant_id: str = "default",
) -> str:
    """Get a valid SF Bearer token via OIDC 2-step flow.

    Returns a cached token if still valid, otherwise performs
    the full IAS authentication flow. Supports multi-tenant caching
    via tenant_id.
    """
    cache = _get_tenant_cache(tenant_id)

    # Return cached token if still valid (with 60s buffer)
    if (
        cache["access_token"]
        and time.time() < float(cache["expires_at"]) - 60
    ):
        return str(cache["access_token"])

    # Resolve IAS credentials
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
    expires_in = step2_data.get("expires_in", 3600)

    # Cache token
    cache["access_token"] = access_token
    cache["expires_at"] = time.time() + expires_in

    return access_token
