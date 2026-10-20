"""
PII Protection Layer for SF Assistant MCP.

Defense-in-depth: validates queries before execution AND scrubs responses
after retrieval. Driven by knowledge/pii_classification.json.

Environment variables:
    PII_STRICT_MODE  - "true" (default) blocks all HIGHLY_CONFIDENTIAL access.
                       "false" allows with warnings (for authorized admin use).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PIICheckResult:
    """Result of a PII validation check."""

    allowed: bool
    tier: Optional[str] = None
    blocked_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    redacted_fields: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Config loading (cached at module level)
# ---------------------------------------------------------------------------

_config: Optional[dict] = None
_all_blocked_fields: Optional[set[str]] = None
_indirect_pii_fields: Optional[set[str]] = None

_CONFIG_PATH = Path(__file__).parent.parent / "knowledge" / "pii_classification.json"


def _load_config() -> dict:
    """Load and cache the PII classification config."""
    global _config
    if _config is None:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _config = json.load(f)
    return _config


def _get_all_blocked_fields() -> set[str]:
    """Flatten all HIGHLY_CONFIDENTIAL blocked field names into a set."""
    global _all_blocked_fields
    if _all_blocked_fields is None:
        config = _load_config()
        hc = config["blocked_fields"].get("HIGHLY_CONFIDENTIAL", {})
        fields: set[str] = set()
        for category_fields in hc.values():
            fields.update(f.lower() for f in category_fields)
        _all_blocked_fields = fields
    return _all_blocked_fields


def _get_indirect_pii_fields() -> set[str]:
    """Get all CONFIDENTIAL indirect PII field names as a set."""
    global _indirect_pii_fields
    if _indirect_pii_fields is None:
        config = _load_config()
        conf = config["blocked_fields"].get("CONFIDENTIAL", {})
        _indirect_pii_fields = {
            f.lower() for f in conf.get("indirect_pii", [])
        }
    return _indirect_pii_fields


def _is_strict_mode() -> bool:
    """Check if PII strict mode is enabled (default: true)."""
    return os.environ.get("PII_STRICT_MODE", "true").lower() == "true"


def _field_matches_pattern(field_name: str) -> bool:
    """Check if a field name matches any pattern in the blocklist."""
    config = _load_config()
    patterns = config.get("field_pattern_blocklist", [])
    lower = field_name.lower()
    return any(fnmatch.fnmatch(lower, p.lower()) for p in patterns)


def _is_blocked_field(field_name: str) -> bool:
    """Check if a field is in the HIGHLY_CONFIDENTIAL blocklist or matches a pattern."""
    return field_name.lower() in _get_all_blocked_fields() or _field_matches_pattern(field_name)


def _get_expand_blocklist() -> set[str]:
    """Navigation properties that lead to HIGHLY_CONFIDENTIAL entities."""
    return {e.lower() for e in _load_config().get("expand_blocklist", [])}


def _path_segments(expr: Optional[str]) -> list[str]:
    """Split a comma-separated $select/$expand into every '/' path segment."""
    if not expr:
        return []
    return [
        seg.strip()
        for part in expr.split(",")
        for seg in part.split("/")
        if seg.strip()
    ]


_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _filter_identifiers(filter_expr: str) -> list[str]:
    """Identifiers referenced in a $filter, ignoring quoted string literals."""
    return _IDENTIFIER_RE.findall(_STRING_LITERAL_RE.sub("''", filter_expr))


_ENTITY_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_entity_name(entity: str) -> str:
    """Return entity if it is a plain OData entity set name, else raise ValueError.

    Rejects key predicates, sub-paths and anything else that could smuggle
    a different resource into the request URL (e.g. "User('x')/empInfo").
    """
    if not isinstance(entity, str) or not _ENTITY_NAME_RE.match(entity):
        raise ValueError(
            f"Invalid OData entity name: {entity!r}. "
            "Must match ^[A-Za-z_][A-Za-z0-9_]*$."
        )
    return entity


def _classify_field(field_name: str) -> Optional[str]:
    """Return the PII tier for a field, or None if not classified."""
    if _is_blocked_field(field_name):
        return "HIGHLY_CONFIDENTIAL"
    if field_name.lower() in _get_indirect_pii_fields():
        return "CONFIDENTIAL"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_entity_access(entity: str) -> PIICheckResult:
    """Check if an entity is blocked entirely (e.g. PerNationalId).

    Called BEFORE any query is built.
    """
    config = _load_config()
    for blocked in config.get("blocked_entities", []):
        if blocked["entity"].lower() == entity.lower():
            if _is_strict_mode():
                return PIICheckResult(
                    allowed=False,
                    tier=blocked["tier"],
                    error_message=(
                        f"Entity '{entity}' is blocked. {blocked['reason']}. "
                        f"Classification: {blocked['tier']}."
                    ),
                )
            else:
                return PIICheckResult(
                    allowed=True,
                    tier=blocked["tier"],
                    warnings=[
                        f"WARNING: Entity '{entity}' contains {blocked['tier']} data. "
                        f"{blocked['reason']}. PII_STRICT_MODE is disabled."
                    ],
                )
    return PIICheckResult(allowed=True)


def validate_select_fields(entity: str, select: Optional[str]) -> PIICheckResult:
    """Validate $select fields against the PII blocklist.

    Returns which fields are blocked and suggests a safe alternative.
    Called BEFORE query execution.
    """
    if not select:
        return PIICheckResult(allowed=True)

    # Every '/' segment counts: "personNav/nationalId" must not slip through.
    fields = _path_segments(select)
    expand_blocklist = _get_expand_blocklist()
    blocked: list[str] = []

    for f in fields:
        if _is_blocked_field(f) or f.lower() in expand_blocklist:
            blocked.append(f)

    if blocked:
        if _is_strict_mode():
            config = _load_config()
            tier_info = config["classification_tiers"]["HIGHLY_CONFIDENTIAL"]
            return PIICheckResult(
                allowed=False,
                tier="HIGHLY_CONFIDENTIAL",
                blocked_fields=blocked,
                error_message=(
                    f"Blocked fields in $select: {', '.join(blocked)}. "
                    f"{tier_info['message']}"
                ),
            )
        else:
            return PIICheckResult(
                allowed=True,
                tier="HIGHLY_CONFIDENTIAL",
                blocked_fields=blocked,
                warnings=[
                    f"WARNING: $select contains HIGHLY_CONFIDENTIAL fields: "
                    f"{', '.join(blocked)}. PII_STRICT_MODE is disabled."
                ],
            )

    # Check indirect PII combination rule
    combo_check = check_indirect_pii_combination(fields)
    if not combo_check.allowed:
        return combo_check

    return PIICheckResult(allowed=True, warnings=combo_check.warnings)


def validate_query(
    entity: str,
    select: Optional[str] = None,
    filter_expr: Optional[str] = None,
    expand: Optional[str] = None,
) -> PIICheckResult:
    """Combined pre-query validation: entity + fields + filter + expand.

    This is the main entry point for pre-query checks.
    """
    # 0. Entity must be a plain entity set name (no key predicates / paths)
    try:
        validate_entity_name(entity)
    except ValueError as exc:
        return PIICheckResult(allowed=False, error_message=str(exc))

    # 1. Check entity
    entity_check = validate_entity_access(entity)
    if not entity_check.allowed:
        return entity_check

    all_warnings = list(entity_check.warnings)

    # 2. Check $select fields
    select_check = validate_select_fields(entity, select)
    if not select_check.allowed:
        return select_check
    all_warnings.extend(select_check.warnings)

    # 3. Check $expand for blocked navigation properties
    #    Every '/' segment of a multi-level expand is checked.
    if expand:
        expand_blocklist = _get_expand_blocklist()
        blocked_expands = [
            seg.lower() for seg in _path_segments(expand)
            if seg.lower() in expand_blocklist or _is_blocked_field(seg)
        ]

        if blocked_expands:
            if _is_strict_mode():
                return PIICheckResult(
                    allowed=False,
                    tier="HIGHLY_CONFIDENTIAL",
                    blocked_fields=blocked_expands,
                    error_message=(
                        f"Blocked navigation properties in $expand: {', '.join(blocked_expands)}. "
                        "These expand to entities containing HIGHLY CONFIDENTIAL data."
                    ),
                )
            else:
                all_warnings.append(
                    f"WARNING: $expand contains restricted navigations: {', '.join(blocked_expands)}."
                )

    # 4. Check $filter for references to blocked fields
    #    Identifiers are matched exactly (string literals ignored), so a
    #    value like 'pin' or a field like 'shipping' is not a false positive.
    if filter_expr:
        blocked_in_filter = sorted({
            ident.lower() for ident in _filter_identifiers(filter_expr)
            if _is_blocked_field(ident)
        })

        if blocked_in_filter:
            if _is_strict_mode():
                return PIICheckResult(
                    allowed=False,
                    tier="HIGHLY_CONFIDENTIAL",
                    blocked_fields=blocked_in_filter,
                    error_message=(
                        f"$filter references HIGHLY CONFIDENTIAL fields: "
                        f"{', '.join(blocked_in_filter)}. Filtering on PII data is not allowed."
                    ),
                )
            else:
                all_warnings.append(
                    f"WARNING: $filter references HIGHLY CONFIDENTIAL fields: "
                    f"{', '.join(blocked_in_filter)}."
                )

    return PIICheckResult(allowed=True, warnings=all_warnings)


def get_safe_select(entity: str) -> Optional[str]:
    """Return the safe $select for an entity from config, or None if not mapped."""
    config = _load_config()
    return config.get("safe_select_defaults", {}).get(entity)


def scrub_response(
    entity: str, records: list[dict]
) -> tuple[list[dict], list[str]]:
    """Remove PII fields from API response records.

    Returns (scrubbed_records, list_of_redacted_field_names).
    Called AFTER query execution, as second line of defense.
    """
    if not records:
        return records, []

    redacted: set[str] = set()
    for record in records:
        redacted |= scrub_payload(record)

    return records, sorted(redacted)


def scrub_payload(payload: object) -> set[str]:
    """Recursively remove PII keys from an OData JSON payload, in place.

    Walks nested dicts (expanded navigations) and lists (including OData v2
    "results" arrays) at any depth. Removes HIGHLY_CONFIDENTIAL fields,
    pattern-blocklisted fields and blocked navigation properties.
    Returns the set of removed key names.
    """
    redacted: set[str] = set()
    expand_blocklist = _get_expand_blocklist()
    stack: list[object] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key in list(node.keys()):
                if _is_blocked_field(key) or key.lower() in expand_blocklist:
                    del node[key]
                    redacted.add(key)
                elif isinstance(node[key], (dict, list)):
                    stack.append(node[key])
        elif isinstance(node, list):
            stack.extend(item for item in node if isinstance(item, (dict, list)))
    return redacted


def check_indirect_pii_combination(fields: list[str]) -> PIICheckResult:
    """Check if 3+ indirect PII fields together escalate to HIGHLY_CONFIDENTIAL.

    Implements the VP data classification combination rule.
    """
    config = _load_config()
    threshold = (
        config["classification_tiers"]
        .get("CONFIDENTIAL", {})
        .get("indirect_combination_threshold", 3)
    )
    indirect_fields = _get_indirect_pii_fields()
    matched = [f for f in fields if f.lower() in indirect_fields]

    if len(matched) >= threshold:
        if _is_strict_mode():
            return PIICheckResult(
                allowed=False,
                tier="HIGHLY_CONFIDENTIAL",
                blocked_fields=matched,
                error_message=(
                    f"Combining {len(matched)} indirect PII fields "
                    f"({', '.join(matched)}) escalates classification to "
                    f"HIGHLY CONFIDENTIAL (threshold: {threshold}). "
                    "Reduce the number of indirect PII fields in your query."
                ),
            )
        else:
            return PIICheckResult(
                allowed=True,
                tier="HIGHLY_CONFIDENTIAL",
                blocked_fields=matched,
                warnings=[
                    f"WARNING: {len(matched)} indirect PII fields combined "
                    f"({', '.join(matched)}) — escalates to HIGHLY CONFIDENTIAL. "
                    f"PII_STRICT_MODE is disabled."
                ],
            )

    if matched:
        return PIICheckResult(
            allowed=True,
            tier="CONFIDENTIAL",
            warnings=[
                f"Query includes {len(matched)} indirect PII field(s): "
                f"{', '.join(matched)}. Adding more may trigger escalation."
            ],
        )

    return PIICheckResult(allowed=True)


def annotate_template_fields(
    entity: str, fields: list[dict]
) -> list[dict]:
    """Add pii_tier and pii_warning to template field definitions.

    Used by generate_import_template to flag sensitive fields.
    """
    for field_def in fields:
        name = field_def.get("name", field_def.get("field", ""))
        tier = _classify_field(name)
        if tier:
            field_def["pii_tier"] = tier
            if tier == "HIGHLY_CONFIDENTIAL":
                field_def["pii_warning"] = (
                    f"HIGHLY CONFIDENTIAL: Field '{name}' contains sensitive PII. "
                    "Handle with extreme care."
                )
            elif tier == "CONFIDENTIAL":
                field_def["pii_warning"] = (
                    f"CONFIDENTIAL: Field '{name}' is indirect PII. "
                    "Combining 3+ indirect PII fields escalates to HIGHLY CONFIDENTIAL."
                )
    return fields


def get_pii_warning_for_upsert(entity: str, record: dict) -> Optional[str]:
    """Check if an upsert record contains PII fields and return a warning.

    Used by execute_upsert to alert about sensitive data in payloads.
    """
    blocked = _get_all_blocked_fields()
    pii_fields = []

    for key in record:
        if key.lower() in blocked or _field_matches_pattern(key):
            pii_fields.append(key)

    if pii_fields:
        return (
            f"Record contains HIGHLY CONFIDENTIAL fields: {', '.join(pii_fields)}. "
            "Ensure you have authorization to import this data."
        )
    return None
