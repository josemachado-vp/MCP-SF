"""Tests for go-live tools."""

import pytest


class TestGoLiveImports:
    def test_import_works(self):
        from tools.golive import (
            run_go_live_checks,
            generate_reconciliation_report,
        )
        assert callable(run_go_live_checks)
        assert callable(generate_reconciliation_report)


# --- run_go_live_checks behavior ---

import httpx
import respx
from unittest.mock import patch

from tools.golive import run_go_live_checks

_ENV_VARS = {
    "SF_API_HOST": "https://api8preview.sapsf.com",
    "IAS_HOST": "test.accounts.ondemand.com",
    "SF_USER_ID": "testuser",
    "SF_PASSWORD": "testpass",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "IAS_DEPENDENCY_NAME": "sfdep",
}


@pytest.fixture(autouse=True)
def reset_token_cache():
    from helpers.credentials import _token_cache
    _token_cache.clear()


def _mock_token():
    respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
        side_effect=[
            httpx.Response(200, json={"id_token": "mock-id-token"}),
            httpx.Response(200, json={"access_token": "mock-sf-token", "expires_in": 3600}),
        ]
    )


def _odata(records):
    return httpx.Response(200, json={"d": {"results": records}})


def _paged(records, page_size=1000):
    """Return a respx side effect that serves records honoring $top/$skip."""
    def handler(request):
        skip = int(request.url.params.get("$skip", "0"))
        top = min(int(request.url.params.get("$top", str(page_size))), page_size)
        return _odata(records[skip:skip + top])
    return handler


def _mock_job(user_ids):
    respx.get(url__regex=r".*/odata/v2/EmpJob\?.*").mock(
        side_effect=_paged([{"userId": u, "managerId": "boss"} for u in user_ids])
    )


def _check(result, check_id):
    return next(c for c in result["checks"] if c["check_id"] == check_id)


class TestRunGoLiveChecks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_gl001_paginates_past_first_page(self):
        _mock_token()
        _mock_job(["u0"])
        # 1001 employments: a single request would only see SF's first 1000.
        employments = [{"userId": f"u{i}"} for i in range(1001)]
        emp_route = respx.get(url__regex=r".*/odata/v2/EmpEmployment\?.*").mock(
            side_effect=_paged(employments)
        )

        with patch.dict("os.environ", _ENV_VARS):
            result = await run_go_live_checks(checklist_type="critical")

        gl001 = _check(result, "GL001")
        assert emp_route.call_count == 2
        assert gl001["affected_count"] == 1000
        assert gl001["status"] == "fail"

    @respx.mock
    @pytest.mark.asyncio
    async def test_gl020_paginates_past_first_page(self):
        _mock_token()
        users = [f"u{i}" for i in range(1001)]
        _mock_job(users)
        respx.get(url__regex=r".*/odata/v2/FODepartment\?.*").mock(return_value=_odata([]))
        respx.get(url__regex=r".*/odata/v2/EmpCompensation\?.*").mock(
            side_effect=_paged([{"userId": u} for u in users])
        )
        email_route = respx.get(url__regex=r".*/odata/v2/PerEmail\?.*").mock(
            side_effect=_paged([{"personIdExternal": u} for u in users])
        )

        with patch.dict("os.environ", _ENV_VARS):
            result = await run_go_live_checks(checklist_type="recommended")

        gl020 = _check(result, "GL020")
        assert email_route.call_count == 2
        assert gl020["affected_count"] == 0
        assert gl020["status"] == "pass"

    @respx.mock
    @pytest.mark.asyncio
    async def test_errored_check_blocks_readiness(self):
        _mock_token()
        _mock_job(["u0"])
        respx.get(url__regex=r".*/odata/v2/EmpEmployment\?.*").mock(
            return_value=httpx.Response(500, text="boom")
        )

        with patch.dict("os.environ", _ENV_VARS):
            result = await run_go_live_checks(checklist_type="critical")

        assert _check(result, "GL001")["status"] == "error"
        assert result["failed"] == 0
        assert result["errors"] == 1
        assert result["ready_for_golive"] is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_ready_when_all_checks_pass(self):
        _mock_token()
        _mock_job(["u0"])
        respx.get(url__regex=r".*/odata/v2/EmpEmployment\?.*").mock(
            side_effect=_paged([{"userId": "u0"}])
        )

        with patch.dict("os.environ", _ENV_VARS):
            result = await run_go_live_checks(checklist_type="critical")

        assert result["errors"] == 0
        assert result["failed"] == 0
        assert result["ready_for_golive"] is True
