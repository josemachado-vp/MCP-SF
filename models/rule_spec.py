"""Pydantic v2 models for Business Rule specifications."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    ON_SAVE = "onSave"
    ON_CHANGE = "onChange"
    ON_INIT = "onInit"
    VALIDATE = "validate"


class RuleScenario(str, Enum):
    EC_JOB_RULES = "Rules for Employee Central"
    EC_COMPENSATION = "Rules for Compensation"
    EC_TIME_OFF = "Rules for Time Off"
    EC_POSITION = "Rules for Position Management"
    EC_GLOBAL_ASSIGNMENT = "Rules for Global Assignment"
    EC_WORKFLOWS = "Workflow Rules"
    EC_EVENT_REASON = "Event Reason Derivation"
    EC_CUSTOM = "Custom MDF Rules"


class ActionType(str, Enum):
    SET_FIELD = "SET_FIELD"
    RAISE_MESSAGE = "RAISE_MESSAGE"
    SET_FIELD_PROPERTY = "SET_FIELD_PROPERTY"
    TRIGGER_WORKFLOW = "TRIGGER_WORKFLOW"


class ConditionOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "notEquals"
    IN = "in"
    NOT_IN = "notIn"
    GREATER_THAN = "greaterThan"
    LESS_THAN = "lessThan"
    IS_EMPTY = "isEmpty"
    IS_NOT_EMPTY = "isNotEmpty"
    CONTAINS = "contains"
    CHANGED = "changed"


class RuleAction(BaseModel):
    """An action to execute when conditions are met."""

    type: ActionType
    target_field: str = Field(description="Field to set or property to change")
    target_entity: str = Field(default="", description="Entity of the target field")
    value: str = Field(description="Value to set or message text")
    value_label: str = Field(default="", description="Human-readable label for the value")


class ConditionExpression(BaseModel):
    """A single condition expression (field operator value)."""

    field: str
    entity: str = Field(default="", description="Source entity for the field")
    operator: ConditionOperator
    value: str = Field(default="", description="Value to compare against")
    value_label: str = Field(default="", description="Human-readable label for the value")


class RuleCondition(BaseModel):
    """A condition block with optional nesting."""

    sequence: int
    type: str = Field(description="IF, ELSE_IF, AND_IF, OR_IF")
    expression: ConditionExpression
    action: Optional[RuleAction] = None
    nested_conditions: list[RuleCondition] = Field(default_factory=list)


class ExecutionNotes(BaseModel):
    """Notes about rule execution context."""

    order_recommendation: str = ""
    dependencies: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)


class RuleSpec(BaseModel):
    """Complete Business Rule specification."""

    rule_name: str
    rule_id: str = ""
    scenario: str
    base_object: str
    event_type: EventType
    hris_element_assignment: str = ""
    description: str
    country_scope: list[str] = Field(default_factory=list)
    conditions: list[RuleCondition] = Field(default_factory=list)
    execution_notes: ExecutionNotes = Field(default_factory=ExecutionNotes)
