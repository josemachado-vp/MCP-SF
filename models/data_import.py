"""Pydantic v2 models for data import/upsert operations."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    UNKNOWN = "unknown"


class ImportFieldValidation(BaseModel):
    """Validation result for a single import field/header."""

    header: str
    mapped_field: str = ""
    status: FieldStatus = FieldStatus.UNKNOWN
    entity: str = ""
    field_type: str = ""
    is_key: bool = False
    is_required: bool = False
    notes: str = ""


class ImportValidationReport(BaseModel):
    """Complete validation report for an import template."""

    entity: str
    valid: bool
    total_headers: int = 0
    valid_headers: int = 0
    invalid_headers: int = 0
    field_validations: list[ImportFieldValidation] = Field(default_factory=list)
    row_errors: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class UpsertRecord(BaseModel):
    """Result of a single upsert operation."""

    index: int
    status: str = ""
    key: str = ""
    message: str = ""
    data: dict = Field(default_factory=dict)


class UpsertResult(BaseModel):
    """Complete result of an upsert batch operation."""

    entity: str
    dry_run: bool = True
    total_records: int = 0
    successful: int = 0
    failed: int = 0
    records: list[UpsertRecord] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
