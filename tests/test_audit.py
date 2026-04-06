"""Tests for audit and troubleshooting tools."""

import pytest
import respx
import httpx
from unittest.mock import patch

from tools.audit import (
    audit_employee_data,
    find_data_anomalies,
    trace_rule_execution,
    check_permission_access,
    validate_effective_dating,
)


MOCK_TOKEN_RESPONSE_1 = {"id_token": "mock-id-token", "access_token": "mock-access-token-step1"}
MOCK_TOKEN_RESPONSE_2 = {"access_token": "mock-sf-token", "expires_in": 3600}

ENV_VARS = {
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


class TestFindDataAnomalies:
    @pytest.mark.asyncio
    async def test_invalid_anomaly_type(self):
        with patch.dict("os.environ", ENV_VARS):
            result = await find_data_anomalies(
                entity="EmpJob", field="department", anomaly_type="unknown_type"
            )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_orphan_unsupported_field(self):
        with patch.dict("os.environ", ENV_VARS):
            result = await find_data_anomalies(
                entity="EmpJob", field="unsupported_field", anomaly_type="orphan"
            )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_field_name_rejected(self):
        """Field names with injection characters must be rejected."""
        with patch.dict("os.environ", ENV_VARS):
            result = await find_data_anomalies(
                entity="EmpJob",
                field="department;$expand=evil",
                anomaly_type="empty",
            )
        assert "error" in result
        assert "field name" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_field_name_with_space_rejected(self):
        """Field names with spaces must be rejected."""
        with patch.dict("os.environ", ENV_VARS):
            result = await find_data_anomalies(
                entity="EmpJob",
                field="bad field",
                anomaly_type="empty",
            )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_scope_filter_length_limit(self):
        """scope_filter longer than 2000 chars must be rejected."""
        with patch.dict("os.environ", ENV_VARS):
            result = await find_data_anomalies(
                entity="EmpJob",
                field="department",
                anomaly_type="empty",
                scope_filter="a" * 2001,
            )
        assert "error" in result
        assert "scope_filter" in result["error"].lower()


class TestAuditEmployeeData:
    @respx.mock
    @pytest.mark.asyncio
    async def test_audit_missing_data(self):
        respx.post("https://test.accounts.ondemand.com/oauth2/token").mock(
            side_effect=[
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_1),
                httpx.Response(200, json=MOCK_TOKEN_RESPONSE_2),
            ]
        )
        # Mock all queries to return empty
        respx.get(url__regex=r".*/odata/v2/.*").mock(
            return_value=httpx.Response(200, json={"d": {"results": []}})
        )

        with patch.dict("os.environ", ENV_VARS):
            result = await audit_employee_data(
                user_id="test_user",
                checks=["employment", "email"],
            )

        assert result["user_id"] == "test_user"
        assert result["total_findings"] > 0
        assert result["critical_count"] >= 1  # Missing employment is critical

    @pytest.mark.asyncio
    async def test_user_id_with_quote_is_escaped(self):
        """user_id escaping: verify escape_odata_string works for injection input."""
        from helpers.odata_utils import escape_odata_string
        user_id = "admin' or '1'='1"
        escaped = escape_odata_string(user_id)
        assert escaped == "admin'' or ''1''=''1"
        # When placed in a filter, the injection becomes a harmless literal
        filter_expr = f"userId eq '{escaped}'"
        assert "or '1'='1" not in filter_expr


class TestTraceRuleExecution:
    @pytest.mark.asyncio
    async def test_invalid_base_object(self):
        with patch.dict("os.environ", ENV_VARS):
            result = await trace_rule_execution(
                user_id="admin", event_type="onSave", base_object="NonExistentModel"
            )
        assert "error" in result
