"""Tests for country-specific tools."""

import pytest
from tools.country import (
    get_country_specific_fields,
    generate_country_config_guide,
)


class TestGetCountrySpecificFields:
    @pytest.mark.asyncio
    async def test_colombia(self):
        result = await get_country_specific_fields(country_code="COL")
        assert result["country_code"] == "COL"
        assert result["entity"] == "PerGlobalInfoCOL"
        assert len(result["required_fields"]) > 0
        assert "EPS" in str(result["required_fields"])
        assert "AFP" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_mexico(self):
        result = await get_country_specific_fields(country_code="MEX")
        assert result["country_code"] == "MEX"
        assert result["entity"] == "PerGlobalInfoMEX"
        assert "CURP" in str(result["required_fields"])
        assert "RFC" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_peru(self):
        result = await get_country_specific_fields(country_code="PER")
        assert result["entity"] == "PerGlobalInfoPER"
        assert "AFP" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_chile(self):
        result = await get_country_specific_fields(country_code="CHL")
        assert result["entity"] == "PerGlobalInfoCHL"
        assert "RUT" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_argentina(self):
        result = await get_country_specific_fields(country_code="ARG")
        assert "CUIL" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_brazil(self):
        result = await get_country_specific_fields(country_code="BRA")
        assert "CPF" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_usa(self):
        result = await get_country_specific_fields(country_code="USA")
        assert "SSN" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_spain(self):
        result = await get_country_specific_fields(country_code="ESP")
        assert "NIF" in str(result["required_fields"])

    @pytest.mark.asyncio
    async def test_unsupported_country(self):
        result = await get_country_specific_fields(country_code="XYZ")
        assert "error" in result
        assert "supported_countries" in result


class TestGenerateCountryConfigGuide:
    def test_colombia_guide_spanish(self):
        result = generate_country_config_guide(country_code="COL", language="es")
        assert "Colombia" in result["title"]
        assert result["entity"] == "PerGlobalInfoCOL"
        assert result["total_sections"] >= 5

    def test_mexico_guide_english(self):
        result = generate_country_config_guide(country_code="MEX", language="en")
        assert "Mexico" in result["title"]
        assert result["total_sections"] >= 5

    def test_all_countries_have_guides(self):
        for code in ["COL", "MEX", "PER", "CHL", "ARG", "BRA", "USA", "ESP"]:
            result = generate_country_config_guide(country_code=code)
            assert "error" not in result, f"Failed for {code}"
            assert result["total_sections"] >= 5, f"Incomplete guide for {code}"

    def test_unsupported_country(self):
        result = generate_country_config_guide(country_code="XYZ")
        assert "error" in result
