"""Tests for helpers/pii_filter.py — PII Protection Layer."""

from __future__ import annotations

import os
import pytest

from helpers.pii_filter import (
    PIICheckResult,
    validate_entity_access,
    validate_select_fields,
    validate_query,
    get_safe_select,
    scrub_response,
    check_indirect_pii_combination,
    annotate_template_fields,
    get_pii_warning_for_upsert,
    _load_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _strict_mode_on(monkeypatch):
    """Default: strict mode enabled for all tests."""
    monkeypatch.setenv("PII_STRICT_MODE", "true")


@pytest.fixture
def strict_mode_off(monkeypatch):
    """Switch to non-strict mode."""
    monkeypatch.setenv("PII_STRICT_MODE", "false")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:
    def test_config_loads_successfully(self):
        config = _load_config()
        assert "classification_tiers" in config
        assert "blocked_entities" in config
        assert "blocked_fields" in config

    def test_config_has_four_tiers(self):
        config = _load_config()
        tiers = config["classification_tiers"]
        assert set(tiers.keys()) == {
            "HIGHLY_CONFIDENTIAL", "CONFIDENTIAL", "INTERNAL", "PUBLIC"
        }


# ---------------------------------------------------------------------------
# Entity access validation
# ---------------------------------------------------------------------------

class TestValidateEntityAccess:
    def test_blocked_entity_returns_not_allowed(self):
        result = validate_entity_access("PerNationalId")
        assert not result.allowed
        assert result.tier == "HIGHLY_CONFIDENTIAL"
        assert "PerNationalId" in result.error_message

    def test_blocked_entity_case_insensitive(self):
        result = validate_entity_access("pernationalid")
        assert not result.allowed

    def test_safe_entity_returns_allowed(self):
        result = validate_entity_access("EmpJob")
        assert result.allowed
        assert result.tier is None

    def test_user_entity_allowed(self):
        result = validate_entity_access("User")
        assert result.allowed

    def test_blocked_entity_warns_in_non_strict(self, strict_mode_off):
        result = validate_entity_access("PerNationalId")
        assert result.allowed
        assert result.tier == "HIGHLY_CONFIDENTIAL"
        assert len(result.warnings) > 0
        assert "PII_STRICT_MODE" in result.warnings[0]


# ---------------------------------------------------------------------------
# Select field validation
# ---------------------------------------------------------------------------

class TestValidateSelectFields:
    def test_blocked_field_in_select(self):
        result = validate_select_fields("User", "userId,nationalId,firstName")
        assert not result.allowed
        assert "nationalId" in result.blocked_fields

    def test_multiple_blocked_fields(self):
        result = validate_select_fields("User", "userId,nationalId,bankAccount")
        assert not result.allowed
        assert len(result.blocked_fields) == 2

    def test_safe_select_passes(self):
        result = validate_select_fields("User", "userId,firstName,lastName")
        assert result.allowed
        assert len(result.blocked_fields) == 0

    def test_none_select_passes(self):
        result = validate_select_fields("User", None)
        assert result.allowed

    def test_empty_select_passes(self):
        result = validate_select_fields("User", "")
        assert result.allowed

    def test_blocked_field_warns_in_non_strict(self, strict_mode_off):
        result = validate_select_fields("User", "userId,nationalId")
        assert result.allowed
        assert "nationalId" in result.blocked_fields
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# Combined query validation
# ---------------------------------------------------------------------------

class TestValidateQuery:
    def test_blocked_entity_in_query(self):
        result = validate_query("PerNationalId")
        assert not result.allowed
        assert result.tier == "HIGHLY_CONFIDENTIAL"

    def test_blocked_select_in_query(self):
        result = validate_query("User", select="userId,socialSecurityNumber")
        assert not result.allowed

    def test_blocked_expand(self):
        result = validate_query("EmpJob", expand="perNationalIdNav")
        assert not result.allowed
        assert "pernationalidnav" in result.blocked_fields

    def test_blocked_field_in_filter(self):
        result = validate_query("User", filter_expr="nationalId eq '12345'")
        assert not result.allowed
        assert "nationalid" in result.blocked_fields

    def test_clean_query_passes(self):
        result = validate_query("EmpJob", select="userId,department", expand="companyNav")
        assert result.allowed

    def test_expand_warns_in_non_strict(self, strict_mode_off):
        result = validate_query("EmpJob", expand="perNationalIdNav")
        assert result.allowed
        assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# Safe select defaults
# ---------------------------------------------------------------------------

class TestGetSafeSelect:
    def test_returns_config_value_for_known_entity(self):
        result = get_safe_select("User")
        assert result is not None
        assert "userId" in result
        assert "firstName" in result

    def test_returns_none_for_unknown_entity(self):
        result = get_safe_select("SomeUnknownEntity")
        assert result is None

    def test_empjob_safe_select(self):
        result = get_safe_select("EmpJob")
        assert result is not None
        assert "department" in result
        assert "nationalId" not in result


# ---------------------------------------------------------------------------
# Response scrubbing
# ---------------------------------------------------------------------------

class TestScrubResponse:
    def test_removes_pii_fields(self):
        records = [
            {"userId": "admin", "firstName": "John", "nationalId": "123-45-6789"},
            {"userId": "user2", "firstName": "Jane", "bankAccount": "9876543"},
        ]
        scrubbed, redacted = scrub_response("User", records)
        assert len(scrubbed) == 2
        assert "nationalId" not in scrubbed[0]
        assert "bankAccount" not in scrubbed[1]
        assert "nationalId" in redacted
        assert "bankAccount" in redacted

    def test_preserves_safe_fields(self):
        records = [{"userId": "admin", "firstName": "John", "department": "HR"}]
        scrubbed, redacted = scrub_response("User", records)
        assert scrubbed[0]["userId"] == "admin"
        assert scrubbed[0]["firstName"] == "John"
        assert scrubbed[0]["department"] == "HR"
        assert len(redacted) == 0

    def test_empty_records(self):
        scrubbed, redacted = scrub_response("User", [])
        assert scrubbed == []
        assert redacted == []

    def test_removes_pattern_matched_fields(self):
        records = [{"userId": "admin", "ssn_custom": "999-99-9999"}]
        scrubbed, redacted = scrub_response("User", records)
        assert "ssn_custom" not in scrubbed[0]
        assert "ssn_custom" in redacted


# ---------------------------------------------------------------------------
# Indirect PII combination rule
# ---------------------------------------------------------------------------

class TestIndirectPIICombination:
    def test_3_fields_escalates(self):
        fields = ["dateOfBirth", "gender", "zipCode"]
        result = check_indirect_pii_combination(fields)
        assert not result.allowed
        assert result.tier == "HIGHLY_CONFIDENTIAL"
        assert len(result.blocked_fields) == 3

    def test_2_fields_no_escalation(self):
        fields = ["dateOfBirth", "gender"]
        result = check_indirect_pii_combination(fields)
        assert result.allowed
        assert result.tier == "CONFIDENTIAL"
        assert len(result.warnings) > 0

    def test_1_field_allowed_with_warning(self):
        fields = ["dateOfBirth"]
        result = check_indirect_pii_combination(fields)
        assert result.allowed
        assert result.tier == "CONFIDENTIAL"

    def test_0_indirect_fields_clean(self):
        fields = ["userId", "department"]
        result = check_indirect_pii_combination(fields)
        assert result.allowed
        assert result.tier is None

    def test_3_fields_warns_in_non_strict(self, strict_mode_off):
        fields = ["dateOfBirth", "gender", "zipCode"]
        result = check_indirect_pii_combination(fields)
        assert result.allowed
        assert result.tier == "HIGHLY_CONFIDENTIAL"
        assert len(result.warnings) > 0

    def test_case_insensitive(self):
        fields = ["DateOfBirth", "Gender", "ZipCode"]
        result = check_indirect_pii_combination(fields)
        assert not result.allowed


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------

class TestPatternMatching:
    def test_ssn_custom_matches(self):
        result = validate_select_fields("User", "userId,ssn_custom1")
        assert not result.allowed
        assert "ssn_custom1" in result.blocked_fields

    def test_bank_acct_pattern_matches(self):
        result = validate_select_fields("User", "userId,bank_acct_number")
        assert not result.allowed

    def test_taxid_pattern_matches(self):
        result = validate_select_fields("User", "userId,taxid_local")
        assert not result.allowed

    def test_normal_field_no_match(self):
        result = validate_select_fields("User", "userId,department")
        assert result.allowed


# ---------------------------------------------------------------------------
# Template field annotation
# ---------------------------------------------------------------------------

class TestAnnotateTemplateFields:
    def test_annotates_highly_confidential(self):
        fields = [
            {"name": "userId"},
            {"name": "nationalId"},
            {"name": "department"},
        ]
        result = annotate_template_fields("User", fields)
        assert "pii_tier" not in result[0]
        assert result[1]["pii_tier"] == "HIGHLY_CONFIDENTIAL"
        assert "pii_warning" in result[1]
        assert "pii_tier" not in result[2]

    def test_annotates_confidential(self):
        fields = [{"name": "dateOfBirth"}]
        result = annotate_template_fields("User", fields)
        assert result[0]["pii_tier"] == "CONFIDENTIAL"
        assert "indirect PII" in result[0]["pii_warning"]


# ---------------------------------------------------------------------------
# Upsert PII warning
# ---------------------------------------------------------------------------

class TestUpsertPIIWarning:
    def test_warns_on_pii_fields(self):
        record = {"userId": "admin", "nationalId": "123", "department": "HR"}
        warning = get_pii_warning_for_upsert("User", record)
        assert warning is not None
        assert "nationalId" in warning

    def test_no_warning_for_clean_record(self):
        record = {"userId": "admin", "department": "HR"}
        warning = get_pii_warning_for_upsert("User", record)
        assert warning is None

    def test_warns_on_pattern_matched_field(self):
        record = {"userId": "admin", "ssn_local": "999"}
        warning = get_pii_warning_for_upsert("User", record)
        assert warning is not None
        assert "ssn_local" in warning
