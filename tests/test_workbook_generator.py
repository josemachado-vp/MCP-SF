"""Tests for workbook_generator pure helper functions."""
import pytest


class TestResolveNestedField:
    def test_simple_field(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": "LE001"}, "externalCode") == "LE001"

    def test_two_level_nested(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"currency": {"code": "USD"}}, "currency.code") == "USD"

    def test_three_level_nested(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"address": {"city": "Lima"}}, "address.city") == "Lima"

    def test_missing_top_level_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": "X"}, "nonexistent") == ""

    def test_missing_nested_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"currency": {}}, "currency.code") == ""

    def test_none_value_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": None}, "externalCode") == ""

    def test_empty_field_path_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({"externalCode": "X"}, "") == ""

    def test_empty_record_returns_empty(self):
        from tools.workbook_generator import _resolve_nested_field
        assert _resolve_nested_field({}, "externalCode") == ""


class TestMapRecordToRow:
    def test_basic_mapping(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "D001", "name": {"en_US": "Finance"}, "effectiveStartDate": "2020-01-01"}
        fields = ["externalCode", "name.en_US", "effectiveStartDate"]
        assert _map_record_to_row(record, fields) == ["D001", "Finance", "2020-01-01"]

    def test_operator_column_becomes_empty(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "D001"}
        assert _map_record_to_row(record, ["externalCode", "[OPERATOR]"]) == ["D001", ""]

    def test_blank_column_header_becomes_empty(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "D001"}
        assert _map_record_to_row(record, ["externalCode", ""]) == ["D001", ""]

    def test_field_alias_applied(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"startDate": "2020-01-01"}
        aliases = {"start-date": "startDate"}
        assert _map_record_to_row(record, ["start-date"], aliases) == ["2020-01-01"]

    def test_missing_field_returns_empty_string(self):
        from tools.workbook_generator import _map_record_to_row
        record = {"externalCode": "X"}
        assert _map_record_to_row(record, ["nonexistent"]) == [""]


class TestWorkbookGeneratorImport:
    def test_tools_importable(self):
        from tools.workbook_generator import (
            generate_fo_workbook,
            generate_workflow_workbook,
            generate_rules_workbook,
        )
        assert callable(generate_fo_workbook)
        assert callable(generate_workflow_workbook)
        assert callable(generate_rules_workbook)
