"""Health endpoint — reports backend readiness.

Verifies that the env vars required for SF and Gemini are present.
Does not call the remote APIs; that happens lazily on first use.
"""

from __future__ import annotations

import os
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])

_REQUIRED_SF = [
    "SF_API_HOST", "SF_COMPANY_ID", "SF_USER_ID", "SF_PASSWORD",
    "IAS_HOST", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "IAS_DEPENDENCY_NAME",
]
_REQUIRED_GEMINI = ["GEMINI_API_KEY"]


@router.get("/health")
def health() -> dict:
    missing_sf = [k for k in _REQUIRED_SF if not os.getenv(k)]
    missing_gemini = [k for k in _REQUIRED_GEMINI if not os.getenv(k)]
    ok = not missing_sf and not missing_gemini
    return {
        "ok": ok,
        "missing_sf": missing_sf,
        "missing_gemini": missing_gemini,
        "model": os.getenv("GEMINI_MODEL", "gemini-3-pro-preview"),
    }
