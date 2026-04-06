"""Pydantic v2 models for employee and profile data."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EmployeeProfile(BaseModel):
    """Complete employee profile assembled from multiple entities."""

    user_id: str
    personal: dict = Field(default_factory=dict, description="PerPersonal data")
    job: dict = Field(default_factory=dict, description="Current EmpJob data")
    compensation: dict = Field(default_factory=dict, description="Current EmpCompensation data")
    employment: dict = Field(default_factory=dict, description="EmpEmployment data")
    emails: list[dict] = Field(default_factory=list, description="PerEmail records")
    phones: list[dict] = Field(default_factory=list, description="PerPhone records")
    user: dict = Field(default_factory=dict, description="User entity data")


class OrgNode(BaseModel):
    """A node in the organizational chart."""

    user_id: str
    name: str = ""
    title: str = ""
    department: str = ""
    position: str = ""
    level: int = 0
    direct_reports: list[OrgNode] = Field(default_factory=list)
    manager: Optional[OrgNode] = None


class EmployeeComparison(BaseModel):
    """Side-by-side comparison of multiple employees."""

    fields_compared: list[str] = Field(default_factory=list)
    employees: list[dict] = Field(default_factory=list)
    differences: list[str] = Field(
        default_factory=list,
        description="Fields that differ between compared employees",
    )


class EmployeeHistoryRecord(BaseModel):
    """A single history record for an employee."""

    entity: str
    start_date: str = ""
    end_date: str = ""
    data: dict = Field(default_factory=dict)
