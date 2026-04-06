"""
OData query sanitization utilities.

Provides escaping and validation helpers to prevent OData injection attacks.
"""

from __future__ import annotations

import re


def escape_odata_string(value: str) -> str:
    """Escape a string value for safe inclusion in an OData $filter expression.

    OData v2 uses single-quoted string literals. A single quote inside the
    value must be escaped by doubling it: O'Brien -> O''Brien.

    Usage:
        safe = escape_odata_string(user_input)
        filter_expr = f"userId eq '{safe}'"

    Note: This function is not idempotent — call it exactly once per raw user-supplied value.
    """
    if value is None:
        raise TypeError("escape_odata_string requires a str, got None")
    return value.replace("'", "''")


_FIELD_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,127}$")


def validate_field_name(name: str) -> str:
    """Validate and return an OData field name.

    Allows only alphanumeric characters and underscores, starting with a
    letter or underscore, max 128 characters. Raises ValueError on invalid input.

    Usage:
        safe_field = validate_field_name(user_provided_field)
        select_expr = f"userId,{safe_field}"

    Note: This validates simple field names only. OData navigation paths
    (e.g. 'jobInfoNav/department') are not supported and will raise ValueError.
    """
    if not _FIELD_NAME_RE.match(name):
        raise ValueError(
            f"Invalid OData field name: '{name}'. "
            "Must start with a letter/underscore and contain only alphanumeric characters and underscores (max 128 chars)."
        )
    return name
