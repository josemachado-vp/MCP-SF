"""Pydantic v2 models for audit, troubleshooting, and go-live checks."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AuditFinding(BaseModel):
    """A single audit finding."""

    check_id: str = ""
    severity: Severity = Severity.INFO
    title: str
    description: str = ""
    entity: str = ""
    affected_records: list[str] = Field(default_factory=list)
    affected_count: int = 0
    recommendation: str = ""


class AuditReport(BaseModel):
    """Complete audit report for an employee or data set."""

    subject: str
    findings: list[AuditFinding] = Field(default_factory=list)
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    passed_checks: int = 0
    total_checks: int = 0


class GoLiveCheckResult(BaseModel):
    """Result of a single go-live check."""

    check_id: str
    name: str
    severity: str = ""
    status: str = ""  # "pass", "fail", "warning", "skipped"
    details: str = ""
    affected_count: int = 0
    sample_records: list[dict] = Field(default_factory=list)


class GoLiveReport(BaseModel):
    """Complete go-live readiness report."""

    checklist_type: str
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    checks: list[GoLiveCheckResult] = Field(default_factory=list)
    ready_for_golive: bool = False


class ReconciliationEntry(BaseModel):
    """A single reconciliation line item."""

    entity: str
    expected_count: int = 0
    actual_count: int = 0
    difference: int = 0
    status: str = ""  # "match", "over", "under"
    details: str = ""
