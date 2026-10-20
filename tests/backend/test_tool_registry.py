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


def test_annotated_string_param_yields_string_schema():
    """A real tool parameter annotated as Annotated[str, "..."] becomes string schema."""
    registry = get_registry()
    profile = registry.by_name["get_employee_profile"]
    props = profile.parameters_schema["properties"]
    # The user_id-style param on get_employee_profile is a string in tools/employee.py.
    # Pick whichever required string param it has.
    string_params = [v for v in props.values() if v.get("type") == "string"]
    assert string_params, f"Expected at least one string-typed property, got {props!r}"


def test_annotated_bool_param_yields_boolean_schema():
    registry = get_registry()
    upsert = registry.by_name["execute_upsert"]
    props = upsert.parameters_schema["properties"]
    assert props["dry_run"]["type"] == "boolean", f"dry_run schema was {props['dry_run']!r}"


def test_annotated_list_param_yields_array_schema():
    registry = get_registry()
    upsert = registry.by_name["execute_upsert"]
    props = upsert.parameters_schema["properties"]
    assert props["records"]["type"] == "array", f"records schema was {props['records']!r}"


def test_annotated_metadata_becomes_description():
    """Annotated[T, 'desc'] metadata is exposed as description on the property."""
    registry = get_registry()
    upsert = registry.by_name["execute_upsert"]
    props = upsert.parameters_schema["properties"]
    desc = props["dry_run"].get("description")
    assert isinstance(desc, str) and desc.strip(), f"dry_run.description was {desc!r}"


# --- P1: host/credential overrides are hidden from the model ---------------

from backend.tool_registry import HIDDEN_PARAMS, strip_hidden_args


def test_no_tool_schema_exposes_hidden_params():
    registry = get_registry()
    for tool in registry.tools:
        props = tool.parameters_schema["properties"]
        leaked = HIDDEN_PARAMS & set(props)
        assert not leaked, f"{tool.name} exposes {leaked}"
        assert not HIDDEN_PARAMS & set(tool.parameters_schema.get("required", []))


def test_instance_compare_keeps_required_host_params_only():
    props = get_registry().by_name["compare_picklists"].parameters_schema["properties"]
    assert {"instance_a_dc", "instance_b_dc"} <= set(props)
    assert not any(k.endswith(("_user", "_password")) for k in props)


def test_strip_hidden_args():
    args = {"user_id": "u1", "data_center": "https://evil", "auth_password": "x", "instance_a_user": "y"}
    assert strip_hidden_args(args) == {"user_id": "u1"}
