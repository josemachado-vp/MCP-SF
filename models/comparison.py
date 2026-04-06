"""Pydantic v2 models for instance comparison results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldDifference(BaseModel):
    """A single field-level difference between instances."""

    field: str
    instance_a_value: str = ""
    instance_b_value: str = ""
    difference_type: str = ""  # "missing_in_a", "missing_in_b", "value_mismatch", "type_mismatch"


class EntityComparisonResult(BaseModel):
    """Comparison result for an entity between two instances."""

    entity: str
    instance_a: str
    instance_b: str
    fields_only_in_a: list[str] = Field(default_factory=list)
    fields_only_in_b: list[str] = Field(default_factory=list)
    field_differences: list[FieldDifference] = Field(default_factory=list)
    matching_fields: int = 0
    total_fields_a: int = 0
    total_fields_b: int = 0


class PicklistComparisonResult(BaseModel):
    """Comparison result for a picklist between instances."""

    picklist_id: str
    instance_a: str
    instance_b: str
    values_only_in_a: list[dict] = Field(default_factory=list)
    values_only_in_b: list[dict] = Field(default_factory=list)
    label_differences: list[dict] = Field(default_factory=list)
    matching_values: int = 0


class FOComparisonResult(BaseModel):
    """Comparison result for Foundation Objects between instances."""

    fo_type: str
    instance_a: str
    instance_b: str
    records_only_in_a: list[dict] = Field(default_factory=list)
    records_only_in_b: list[dict] = Field(default_factory=list)
    field_differences: list[dict] = Field(default_factory=list)
    matching_records: int = 0
