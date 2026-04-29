"""Config endpoints — expose current .env values (secrets masked) and
verify Gemini connectivity. Allows the frontend to display which tenant
and which Gemini key are in use, and to reload .env on demand."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import APIRouter

router = APIRouter(prefix="/api/config", tags=["config"])


def _mask(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * (len(value) - keep * 2)}{value[-keep:]}"


def _snapshot() -> dict:
    return {
        "sf": {
            "api_host": os.getenv("SF_API_HOST", ""),
            "company_id": os.getenv("SF_COMPANY_ID", ""),
            "user_id": os.getenv("SF_USER_ID", ""),
            "password_masked": _mask(os.getenv("SF_PASSWORD")),
            "ias_host": os.getenv("IAS_HOST", ""),
            "oidc_client_id": os.getenv("OIDC_CLIENT_ID", ""),
            "oidc_client_secret_masked": _mask(os.getenv("OIDC_CLIENT_SECRET")),
            "ias_dependency_name": os.getenv("IAS_DEPENDENCY_NAME", ""),
        },
        "gemini": {
            "api_key_masked": _mask(os.getenv("GEMINI_API_KEY")),
            "model": os.getenv("GEMINI_MODEL", "gemini-3-pro-preview"),
        },
    }


@router.get("")
def get_config() -> dict:
    return _snapshot()


@router.post("/reload")
def reload_env() -> dict:
    """Re-read .env from disk so credential edits take effect without
    restarting the server. Also resets the cached genai client + chat
    sessions so the new key/model are picked up on the next request."""
    load_dotenv(override=True)
    from backend import gemini_agent
    gemini_agent._genai_client_cache.clear()
    gemini_agent._chat_session_cache.clear()
    return {"ok": True, **_snapshot()}


@router.post("/test-gemini")
async def test_gemini() -> dict:
    """Live ping to Gemini using the current API key + model.
    Returns ok=True if the model responds to a trivial prompt."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY not set"}
    model = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=model, contents="Say OK"
        )
        return {"ok": True, "model": model, "reply": (response.text or "").strip()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "model": model}
