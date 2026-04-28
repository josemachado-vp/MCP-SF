"""Tests for the backend tool registry."""

from backend.tool_registry import (
    ToolMeta,
    get_registry,
    CATEGORIES,
)


def test_registry_loads_52_tools():
    registry = get_registry()
    assert len(registry.tools) == 52


def test_registry_has_15_categories():
    registry = get_registry()
    assert len(registry.by_category) == 15
    assert set(registry.by_category.keys()) == set(CATEGORIES.keys())


def test_every_tool_has_schema_and_metadata():
    registry = get_registry()
    for tool in registry.tools:
        assert isinstance(tool, ToolMeta)
        assert tool.name
        assert tool.category in CATEGORIES
        assert tool.description  # non-empty docstring summary
        assert isinstance(tool.parameters_schema, dict)
        assert tool.parameters_schema.get("type") == "object"
        assert "properties" in tool.parameters_schema
        assert callable(tool.fn)


def test_execute_upsert_marked_destructive():
    registry = get_registry()
    upsert = registry.by_name["execute_upsert"]
    assert upsert.is_destructive is True


def test_get_employee_profile_not_destructive():
    registry = get_registry()
    profile = registry.by_name["get_employee_profile"]
    assert profile.is_destructive is False


def test_lookup_by_name():
    registry = get_registry()
    assert "search_employees" in registry.by_name
    assert registry.by_name["search_employees"].category == "Employee"
