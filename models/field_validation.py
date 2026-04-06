"""Pydantic v2 models for field validation and test case generation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldValidationResult(BaseModel):
    """Validation result for a single field."""

    field: str
    entity: str
    exists: bool = False
    type: str = ""
    label: str = ""
    editable: bool = False
    required: bool = False
    is_picklist: bool = False
    values_valid: bool = True
    invalid_values: list[str] = Field(default_factory=list)
    notes: str = ""


class ValidationReport(BaseModel):
    """Complete validation report for a rule specification."""

    valid: bool
    field_validations: list[FieldValidationResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    """A single test case for a business rule."""

    id: str
    description: str
    preconditions: dict[str, str] = Field(default_factory=dict)
    action: str
    expected_result: dict[str, str] = Field(default_factory=dict)
    sample_employee: str = ""
    is_edge_case: bool = False


class TestMatrix(BaseModel):
    """Complete test matrix for a business rule."""

    rule_name: str
    test_cases: list[TestCase] = Field(default_factory=list)
    total_paths: int = 0
    covered_paths: int = 0
    coverage_percentage: str = "0%"
