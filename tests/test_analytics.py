"""Tests for analytics tools."""

import pytest
from tools.analytics import get_headcount


class TestGetHeadcount:
    """Tests for get_headcount tool."""

    @pytest.mark.asyncio
    async def test_invalid_group_by(self):
        result = await get_headcount(group_by="invalidField")
        assert "error" in result
        assert "Invalid group_by" in result["error"]
