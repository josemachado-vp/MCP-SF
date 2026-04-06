"""Tests for employee tools."""

import pytest
import respx
import httpx
from unittest.mock import AsyncMock, patch

from tools.employee import (
    search_employees,
    get_employee_profile,
    get_org_chart,
    get_employee_history,
    compare_employees,
)


# Mock token response
MOCK_TOKEN_RESPONSE_1 = {
    "id_token": "mock-id-token",
    "access_token": "mock-access-token-step1",
}
MOCK_TOKEN_RESPONSE_2 = {
    "access_token": "mock-sf-token",
    "expires_in": 3600,
}


def _mock_odata_response(records: list[dict]) -> dict:
    return {"d": {"results": records}}


@pytest.fixture(autouse=True)
def reset_token_cache():
    """Reset token cache between tests."""
    from helpers.credentials import _token_cache
    _token_cache.clear()


class TestSearchEmployees:
    """Tests for search_employees tool."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_by_name(self):
        # Mock IAS token endpoints
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )

        # Mock OData query
        respx.get(url__regex=r".*/odata/v2/User.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"userId": "jsmith", "firstName": "John", "lastName": "Smith"},
            ]))
        )

        with patch.dict("os.environ", {
            "SF_API_HOST": "https://api8preview.sapsf.com",
            "IAS_HOST": "test.accounts.ondemand.com",
            "SF_USER_ID": "testuser",
            "SF_PASSWORD": "testpass",
            "OIDC_CLIENT_ID": "client-id",
            "OIDC_CLIENT_SECRET": "client-secret",
            "IAS_DEPENDENCY_NAME": "sfdep",
        }):
            result = await search_employees(query="John Smith")

        assert result["count"] == 1
        assert result["data"][0]["firstName"] == "John"
        assert "interpretation" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_by_department(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/EmpJob.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"userId": "emp1", "department": "40000013"},
            ]))
        )

        with patch.dict("os.environ", {
            "SF_API_HOST": "https://api8preview.sapsf.com",
            "IAS_HOST": "test.accounts.ondemand.com",
            "SF_USER_ID": "testuser",
            "SF_PASSWORD": "testpass",
            "OIDC_CLIENT_ID": "client-id",
            "OIDC_CLIENT_SECRET": "client-secret",
            "IAS_DEPENDENCY_NAME": "sfdep",
        }):
            result = await search_employees(query="department 40000013")

        assert result["count"] == 1
        assert "department=40000013" in result["interpretation"]


class TestGetEmployeeHistory:
    """Tests for get_employee_history tool."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_job_history(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/EmpJob.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"userId": "admin", "startDate": "2024-01-01", "department": "IT"},
                {"userId": "admin", "startDate": "2023-01-01", "department": "HR"},
            ]))
        )

        with patch.dict("os.environ", {
            "SF_API_HOST": "https://api8preview.sapsf.com",
            "IAS_HOST": "test.accounts.ondemand.com",
            "SF_USER_ID": "testuser",
            "SF_PASSWORD": "testpass",
            "OIDC_CLIENT_ID": "client-id",
            "OIDC_CLIENT_SECRET": "client-secret",
            "IAS_DEPENDENCY_NAME": "sfdep",
        }):
            result = await get_employee_history(user_id="admin", history_type="job")

        assert result["count"] == 2
        assert result["entity"] == "EmpJob"

    @pytest.mark.asyncio
    async def test_invalid_history_type(self):
        result = await get_employee_history(user_id="admin", history_type="invalid")
        assert "error" in result


class TestCompareEmployees:
    """Tests for compare_employees tool."""

    @pytest.mark.asyncio
    async def test_too_few_employees(self):
        result = await compare_employees(user_ids=["only_one"])
        assert "error" in result
        assert "at least 2" in result["error"]

    @pytest.mark.asyncio
    async def test_too_many_employees(self):
        result = await compare_employees(user_ids=["a", "b", "c", "d", "e", "f"])
        assert "error" in result
        assert "Maximum 5" in result["error"]
