"""Tests for organization tools."""

import pytest
import respx
import httpx
from unittest.mock import patch

from tools.organization import (
    get_org_structure,
    get_position_details,
    list_foundation_objects,
)


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
    from helpers.credentials import _token_cache
    _token_cache.clear()


ENV_VARS = {
    "SF_API_HOST": "https://api8preview.sapsf.com",
    "IAS_HOST": "test.accounts.ondemand.com",
    "SF_USER_ID": "testuser",
    "SF_PASSWORD": "testpass",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "IAS_DEPENDENCY_NAME": "sfdep",
}


class TestGetOrgStructure:
    """Tests for get_org_structure tool."""

    @pytest.mark.asyncio
    async def test_invalid_level(self):
        result = await get_org_structure(level="invalid_level")
        assert "error" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_company_level(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/FOCompany.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"externalCode": "1000", "name": "Acme Corp", "status": "A"},
            ]))
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await get_org_structure(level="company")

        assert result["entity"] == "FOCompany"
        assert result["count"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_department_with_parent(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/FODepartment.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"externalCode": "IT", "name": "IT Dept", "parent": "1000"},
            ]))
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await get_org_structure(level="department", parent_code="1000")

        assert result["count"] == 1


class TestGetPositionDetails:
    """Tests for get_position_details tool."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_positions(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/Position.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"code": "POS001", "vacant": True, "department": "IT"},
            ]))
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await get_position_details(department="IT", vacant_only=True)

        assert result["count"] == 1
        assert result["filters"]["vacant_only"] is True


class TestListFoundationObjects:
    """Tests for list_foundation_objects tool."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_locations(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/FOLocation.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"externalCode": "NYC", "name": "New York Office", "status": "A"},
                {"externalCode": "LON", "name": "London Office", "status": "A"},
            ]))
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await list_foundation_objects(fo_type="location")

        assert result["entity"] == "FOLocation"
        assert result["count"] == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_direct_entity_name(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/FOJobCode.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([]))
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await list_foundation_objects(fo_type="FOJobCode")

        assert result["entity"] == "FOJobCode"


class TestCentralPIIEnforcement:
    """organization.py has no PII code of its own; SFClient must enforce it."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_pii_select_blocked_before_request(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        odata = respx.get(url__regex=r".*/odata/v2/FOJobCode.*")

        from helpers.sf_client import PIIPolicyError

        with patch.dict("os.environ", {**ENV_VARS, "PII_STRICT_MODE": "true"}):
            with pytest.raises(PIIPolicyError):
                await list_foundation_objects(fo_type="FOJobCode", select="externalCode,ssn")
        assert not odata.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_pii_in_response_scrubbed(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/FOJobCode.*").mock(
            return_value=httpx.Response(200, json=_mock_odata_response([
                {"externalCode": "J1", "ownerNav": {"name": "Ana", "homeAddress": "Calle 1"}},
            ]))
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await list_foundation_objects(fo_type="FOJobCode")

        assert result["data"] == [{"externalCode": "J1", "ownerNav": {"name": "Ana"}}]
