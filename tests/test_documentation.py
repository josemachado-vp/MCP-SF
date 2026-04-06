"""Tests for documentation generation tools."""

import pytest
from tools.documentation import generate_test_script


class TestGenerateTestScript:
    """Tests for test script generation (no API calls needed)."""

    @pytest.mark.asyncio
    async def test_hire_scenario(self):
        result = await generate_test_script(scenario="hire")
        assert result["scenario"] == "hire"
        assert result["total_steps"] > 0
        assert len(result["steps"]) > 0

    @pytest.mark.asyncio
    async def test_terminate_scenario_spanish(self):
        result = await generate_test_script(scenario="terminate", language="es")
        assert "Terminación" in result["title"]
        assert result["total_steps"] > 0

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        result = await generate_test_script(scenario="full_lifecycle")
        assert result["total_steps"] >= 7

    @pytest.mark.asyncio
    async def test_invalid_scenario(self):
        result = await generate_test_script(scenario="nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_hire_with_country(self):
        result = await generate_test_script(scenario="hire", country="COL")
        assert result["country"] == "COL"
        # Should have extra country-specific steps
        assert result["total_steps"] > 7
        assert len(result["country_compliance_notes"]) > 0

    @pytest.mark.asyncio
    async def test_promote_scenario(self):
        result = await generate_test_script(scenario="promote")
        assert result["scenario"] == "promote"

    @pytest.mark.asyncio
    async def test_transfer_scenario(self):
        result = await generate_test_script(scenario="transfer")
        assert result["scenario"] == "transfer"

    @pytest.mark.asyncio
    async def test_rehire_scenario(self):
        result = await generate_test_script(scenario="rehire")
        assert result["scenario"] == "rehire"
