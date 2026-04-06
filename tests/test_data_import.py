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
