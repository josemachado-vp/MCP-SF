"""Tests for the SF client helper."""

import httpx
import pytest
import respx

from helpers.credentials import resolve_api_host
from helpers.sf_client import PIIPolicyError, SFClient, DATA_CENTERS, allowed_hosts


class TestResolveBaseUrl:
    def setup_method(self):
        self.client = SFClient(None)  # No HTTP client needed for URL resolution

    def test_known_data_center(self):
        assert self.client.resolve_base_url("DC4") == "https://api4.successfactors.com"

    def test_case_insensitive(self):
        assert self.client.resolve_base_url("dc4") == "https://api4.successfactors.com"

    def test_preview_data_center(self):
        assert self.client.resolve_base_url("DC4_PREVIEW") == "https://api4preview.sapsf.com"

    def test_salesdemo_data_center(self):
        url = self.client.resolve_base_url("DC4_SALESDEMO")
        assert url == "https://apisalesdemo4.successfactors.com"

    def test_direct_url_of_known_dc_host(self):
        url = "https://api4.successfactors.com"
        assert self.client.resolve_base_url(url) == url

    def test_direct_url_strips_trailing_slash(self):
        assert (
            self.client.resolve_base_url("https://api4.successfactors.com/")
            == "https://api4.successfactors.com"
        )

    def test_bare_hostname_of_known_dc(self):
        assert self.client.resolve_base_url("api8preview.sapsf.com") == "https://api8preview.sapsf.com"

    def test_unknown_dc_raises(self):
        with pytest.raises(ValueError, match="Unknown data center"):
            self.client.resolve_base_url("DC999")

    def test_all_data_centers_have_https(self):
        for dc, url in DATA_CENTERS.items():
            assert url.startswith("https://"), f"{dc} URL doesn't start with https"


# ---------------------------------------------------------------------------
# P1: data_center override must not send the Bearer token to arbitrary hosts
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_host_env(monkeypatch):
    monkeypatch.delenv("SF_API_HOST", raising=False)
    monkeypatch.delenv("SF_ALLOWED_HOSTS", raising=False)
    return monkeypatch


class TestHostAllowlist:
    def setup_method(self):
        self.client = SFClient(None)

    @pytest.mark.parametrize("value", [
        "https://attacker.example.com",
        "attacker.example.com",
        "https://api4.successfactors.com.attacker.com",
        "http://api4.successfactors.com",
        "https://api4.successfactors.com/evil",
        "https://api4.successfactors.com?x=1",
        "https://user:pw@api4.successfactors.com",
        "https://api4.successfactors.com:8443",
        "https://attacker.example.com#api4.successfactors.com",
        "ftp://api4.successfactors.com",
    ])
    def test_rejects_unlisted_or_malformed(self, clean_host_env, value):
        with pytest.raises(ValueError):
            self.client.resolve_base_url(value)

    def test_configured_sf_api_host_is_allowed(self, clean_host_env):
        clean_host_env.setenv("SF_API_HOST", "custom-tenant.sapsf.com")
        assert self.client.resolve_base_url("https://custom-tenant.sapsf.com") == "https://custom-tenant.sapsf.com"
        assert self.client.resolve_base_url("CUSTOM-TENANT.sapsf.com") == "https://custom-tenant.sapsf.com"

    def test_env_allowlist(self, clean_host_env):
        clean_host_env.setenv("SF_ALLOWED_HOSTS", " qa.sapsf.com , https://prod.sapsf.com/ ")
        assert {"qa.sapsf.com", "prod.sapsf.com"} <= allowed_hosts()
        assert self.client.resolve_base_url("qa.sapsf.com") == "https://qa.sapsf.com"
        assert self.client.resolve_base_url("https://prod.sapsf.com") == "https://prod.sapsf.com"
        with pytest.raises(ValueError, match="not an allowed"):
            self.client.resolve_base_url("dev.sapsf.com")

    def test_resolve_api_host_enforces_allowlist(self, clean_host_env):
        clean_host_env.setenv("SF_API_HOST", "api8preview.sapsf.com")
        assert resolve_api_host() == "https://api8preview.sapsf.com"
        assert resolve_api_host("DC4") == "https://api4.successfactors.com"
        with pytest.raises(ValueError, match="not an allowed"):
            resolve_api_host("https://attacker.example.com")

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_request_sent_to_rejected_host(self, clean_host_env):
        route = respx.get(url__regex=r"https://attacker\.example\.com/.*")
        async with httpx.AsyncClient() as http:
            sf = SFClient(http)
            with pytest.raises(ValueError):
                await sf.query_odata("https://attacker.example.com", "secret-token", "User")
        assert not route.called


# ---------------------------------------------------------------------------
# P1: PII policy enforced centrally in SFClient.query_odata
# ---------------------------------------------------------------------------

BASE = "https://api4.successfactors.com"


class TestCentralPIIEnforcement:
    @pytest.fixture(autouse=True)
    def _strict(self, monkeypatch):
        monkeypatch.setenv("PII_STRICT_MODE", "true")

    @respx.mock
    @pytest.mark.asyncio
    @pytest.mark.parametrize("entity,params", [
        ("PerNationalId", {}),
        ("User", {"$select": "userId,ssn"}),
        ("User", {"$select": "personNav/nationalId"}),
        ("EmpJob", {"$expand": "personNav/perNationalIdNav"}),
        ("User", {"$filter": "homeAddress eq 'x'"}),
        ("User('admin')", {}),
        ("User/../PerNationalId", {}),
    ])
    async def test_blocked_query_never_hits_network(self, entity, params):
        route = respx.get(url__regex=r".*")
        async with httpx.AsyncClient() as http:
            sf = SFClient(http)
            with pytest.raises(PIIPolicyError) as exc_info:
                await sf.query_odata("DC4", "tok", entity, params)
        assert exc_info.value.status_code == 403
        assert not route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_response_scrubbed_recursively(self):
        respx.get(f"{BASE}/odata/v2/EmpJob").mock(return_value=httpx.Response(200, json={
            "d": {"results": [{
                "userId": "u1",
                "ssn": "123-45-6789",
                "userNav": {
                    "firstName": "Ana",
                    "homeAddress": "Calle 1",
                    "empInfo": {"results": [
                        {"bankAccount": "ES00", "personIdExternal": "p1"},
                    ]},
                    "perNationalIdNav": {"results": [{"countryCode": "COL"}]},
                },
            }]},
        }))
        async with httpx.AsyncClient() as http:
            data = await SFClient(http).query_odata("DC4", "tok", "EmpJob", {"$expand": "userNav"})

        rec = data["d"]["results"][0]
        assert rec["userId"] == "u1"
        assert "ssn" not in rec
        assert rec["userNav"]["firstName"] == "Ana"
        assert "homeAddress" not in rec["userNav"]
        assert "perNationalIdNav" not in rec["userNav"]
        assert rec["userNav"]["empInfo"]["results"][0] == {"personIdExternal": "p1"}
        assert data["pii_redacted_fields"] == [
            "bankAccount", "homeAddress", "perNationalIdNav", "ssn",
        ]

    @respx.mock
    @pytest.mark.asyncio
    async def test_clean_response_unchanged(self):
        payload = {"d": {"results": [{"userId": "u1", "firstName": "Ana"}]}}
        respx.get(f"{BASE}/odata/v2/User").mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as http:
            data = await SFClient(http).query_odata("DC4", "tok", "User")
        assert data == payload

    @pytest.mark.asyncio
    async def test_get_metadata_rejects_path_in_entity(self):
        with pytest.raises(ValueError, match="Invalid OData entity name"):
            await SFClient(None).get_metadata("DC4", "tok", entity="User/../x")
