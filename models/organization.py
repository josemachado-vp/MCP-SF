"""Pydantic v2 models for organizational structure data."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FoundationObject(BaseModel):
    """A Foundation Object record (company, department, location, etc.)."""

    external_code: str
    name: str = ""
    description: str = ""
    status: str = ""
    start_date: str = ""
    extra_fields: dict = Field(default_factory=dict)


class OrgUnit(BaseModel):
    """An organizational unit with optional hierarchy info."""

    external_code: str
    name: str = ""
    parent_code: str = ""
    level: str = ""
    headcount: int = 0
    children: list[OrgUnit] = Field(default_factory=list)
    extra_fields: dict = Field(default_factory=dict)


class PositionDetail(BaseModel):
    """Position record from Position Management."""

    code: str
    name: str = ""
    department: str = ""
    division: str = ""
    company: str = ""
    job_code: str = ""
    incumbent_user_id: str = ""
    vacant: bool = False
    effective_status: str = ""
    extra_fields: dict = Field(default_factory=dict)
