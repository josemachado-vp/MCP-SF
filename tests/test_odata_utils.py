"""Unit tests for OData sanitization utilities."""
import pytest
from helpers.odata_utils import escape_odata_string, validate_field_name


class TestEscapeOdataString:
    def test_plain_value_unchanged(self):
        assert escape_odata_string("admin") == "admin"

    def test_single_quote_escaped(self):
        assert escape_odata_string("O'Brien") == "O''Brien"

    def test_multiple_quotes_escaped(self):
        assert escape_odata_string("it's O'Brien") == "it''s O''Brien"

    def test_empty_string(self):
        assert escape_odata_string("") == ""

    def test_injection_attempt(self):
        result = escape_odata_string("admin' or '1'='1")
        assert result == "admin'' or ''1''=''1"
        # When placed in filter: userId eq 'admin'' or ''1''=''1'
        # The injection becomes a harmless literal string, not an OData operator

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            escape_odata_string(None)


class TestValidateFieldName:
    def test_valid_camel_case(self):
        assert validate_field_name("firstName") == "firstName"

    def test_valid_with_underscore(self):
        assert validate_field_name("custom_field") == "custom_field"

    def test_valid_uppercase(self):
        assert validate_field_name("UserId") == "UserId"

    def test_valid_single_char(self):
        assert validate_field_name("a") == "a"

    def test_invalid_with_space(self):
        with pytest.raises(ValueError, match="Invalid OData field name"):
            validate_field_name("first name")

    def test_invalid_injection(self):
        with pytest.raises(ValueError, match="Invalid OData field name"):
            validate_field_name("firstName;$expand=companyNav")

    def test_invalid_starts_with_digit(self):
        with pytest.raises(ValueError, match="Invalid OData field name"):
            validate_field_name("1field")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid OData field name"):
            validate_field_name("")

    def test_invalid_too_long(self):
        with pytest.raises(ValueError, match="Invalid OData field name"):
            validate_field_name("a" * 129)
