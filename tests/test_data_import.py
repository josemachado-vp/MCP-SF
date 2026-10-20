"""Tests for data import tools and template parser."""

import pytest
from helpers.template_parser import (
    parse_csv_template,
    validate_template_against_metadata,
)


class TestParseCsvTemplate:
    """Tests for CSV template parsing."""

    def test_basic_csv(self):
        csv_content = "userId,firstName,lastName\nadmin,John,Smith\nuser2,Jane,Doe"
        result = parse_csv_template(csv_content)
        assert result["headers"] == ["userId", "firstName", "lastName"]
        assert result["row_count"] == 2
        assert result["rows"][0]["userId"] == "admin"

    def test_empty_csv(self):
        result = parse_csv_template("")
        assert result["headers"] == []
        assert result["row_count"] == 0

    def test_headers_only(self):
        result = parse_csv_template("userId,firstName,lastName\n")
        assert result["headers"] == ["userId", "firstName", "lastName"]
        assert result["row_count"] == 0

    def test_csv_with_commas_in_quotes(self):
        csv_content = 'name,address\n"Smith, John","123 Main St"'
        result = parse_csv_template(csv_content)
        assert result["row_count"] == 1
        assert result["rows"][0]["name"] == "Smith, John"


class TestValidateTemplateAgainstMetadata:
    """Tests for template validation against metadata."""

    def test_all_valid_headers(self):
        headers = ["userId", "firstName"]
        metadata = {
            "keys": ["userId"],
            "properties": {
                "userId": {"type": "Edm.String", "required": True},
                "firstName": {"type": "Edm.String", "required": False},
            },
        }
        result = validate_template_against_metadata(headers, metadata)
        assert result["valid"] is True
        assert result["valid_headers"] == 2
        assert result["invalid_headers"] == 0

    def test_invalid_header(self):
        headers = ["userId", "nonExistentField"]
        metadata = {
            "keys": ["userId"],
            "properties": {
                "userId": {"type": "Edm.String", "required": True},
            },
        }
        result = validate_template_against_metadata(headers, metadata)
        assert result["valid"] is False
        assert result["invalid_headers"] == 1

    def test_missing_key_field(self):
        headers = ["firstName"]
        metadata = {
            "keys": ["userId"],
            "properties": {
                "userId": {"type": "Edm.String", "required": True},
                "firstName": {"type": "Edm.String", "required": False},
            },
        }
        result = validate_template_against_metadata(headers, metadata)
        assert result["valid"] is False
        assert "userId" in result["missing_key_fields"]

    def test_key_field_flagged(self):
        headers = ["userId"]
        metadata = {
            "keys": ["userId"],
            "properties": {
                "userId": {"type": "Edm.String", "required": True},
            },
        }
        result = validate_template_against_metadata(headers, metadata)
        assert result["field_results"][0]["is_key"] is True

    def test_empty_headers(self):
        result = validate_template_against_metadata(
            [],
            {"keys": ["userId"], "properties": {"userId": {"type": "Edm.String"}}},
        )
        assert result["total_headers"] == 0
        assert result["missing_key_fields"] == ["userId"]


# --- generate_import_template (regression: PII annotation crashed with AttributeError) ---

import httpx
import respx
from unittest.mock import patch

from tools.data_import import generate_import_template

_ENV_VARS = {
    "SF_API_HOST": "https://api8preview.sapsf.com",
    "IAS_HOST": "test.accounts.ondemand.com",
    "SF_USER_ID": "testuser",
    "SF_PASSWORD": "testpass",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "IAS_DEPENDENCY_NAME": "sfdep",
}

_PER_PERSONAL_METADATA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0"
    xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SFOData"
      xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
      xmlns:sap="http://www.sap.com/Protocols/SAPData">
      <EntityType Name="PerPersonal">
        <Key><PropertyRef Name="personIdExternal"/></Key>
        <Property Name="personIdExternal" Type="Edm.String" Nullable="false"
          sap:label="Person ID" sap:creatable="true" sap:updatable="false"/>
        <Property Name="firstName" Type="Edm.String" Nullable="true"
          sap:label="First Name" sap:creatable="true" sap:updatable="true"/>
        <Property Name="nationalId" Type="Edm.String" Nullable="true"
          sap:label="National ID" sap:creatable="true" sap:updatable="true"/>
      </EntityType>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


@pytest.fixture
def _reset_token_cache():
    from helpers.credentials import _token_cache
    _token_cache.clear()


class TestGenerateImportTemplate:
    @respx.mock
    @pytest.mark.asyncio
    async def test_annotates_pii_fields_without_crashing(self, _reset_token_cache):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json={"id_token": "mock-id-token"}),
                httpx.Response(200, json={"access_token": "mock-sf-token", "expires_in": 3600}),
            ]
        )
        respx.get(url__regex=r".*/odata/v2/PerPersonal/\$metadata.*").mock(
            return_value=httpx.Response(200, text=_PER_PERSONAL_METADATA)
        )

        with patch.dict("os.environ", _ENV_VARS):
            result = await generate_import_template(entity_name="PerPersonal")

        fields = {f["name"]: f for f in result["fields"]}
        assert result["total_fields"] == 3
        assert fields["nationalId"]["pii_tier"] == "HIGHLY_CONFIDENTIAL"
        assert "pii_warning" in fields["nationalId"]
        assert "pii_tier" not in fields["firstName"]
        assert "pii_notice" in result
