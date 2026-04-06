"""Tests for Pydantic models."""

from models.rule_spec import (
    RuleSpec, RuleCondition, ConditionExpression, RuleAction,
    ActionType, ConditionOperator, EventType, ExecutionNotes,
)
from models.field_validation import (
    FieldValidationResult, ValidationReport, TestCase, TestMatrix,
)


class TestRuleSpec:
    def test_create_minimal_spec(self):
        spec = RuleSpec(
            rule_name="BR_Test",
            scenario="Rules for Employee Central",
            base_object="JobInformationModel",
            event_type=EventType.ON_SAVE,
            description="Test rule",
        )
        assert spec.rule_name == "BR_Test"
        assert spec.event_type == EventType.ON_SAVE
        assert spec.conditions == []

    def test_serialize_to_dict(self):
        spec = RuleSpec(
            rule_name="BR_Test",
            scenario="Rules for Employee Central",
            base_object="JobInformationModel",
            event_type=EventType.ON_SAVE,
            description="Test rule",
        )
        data = spec.model_dump()
        assert data["rule_name"] == "BR_Test"
        assert data["event_type"] == "onSave"

    def test_spec_with_conditions(self):
        spec = RuleSpec(
            rule_name="BR_DerivePayGroup",
            scenario="Rules for Employee Central",
            base_object="JobInformationModel",
            event_type=EventType.ON_SAVE,
            description="Derive pay group",
            conditions=[
                RuleCondition(
                    sequence=1,
                    type="IF",
                    expression=ConditionExpression(
                        field="countryOfCompany",
                        entity="EmpJob",
                        operator=ConditionOperator.EQUALS,
                        value="PE",
                    ),
                    action=RuleAction(
                        type=ActionType.SET_FIELD,
                        target_field="payGroup",
                        value="PG_PE_FT",
                    ),
                )
            ],
        )
        assert len(spec.conditions) == 1
        assert spec.conditions[0].expression.field == "countryOfCompany"
        assert spec.conditions[0].action.value == "PG_PE_FT"


class TestValidationReport:
    def test_valid_report(self):
        report = ValidationReport(
            valid=True,
            field_validations=[
                FieldValidationResult(
                    field="payGroup",
                    entity="EmpJob",
                    exists=True,
                    type="Edm.String",
                    editable=True,
                )
            ],
        )
        assert report.valid is True
        assert len(report.field_validations) == 1

    def test_invalid_report(self):
        report = ValidationReport(
            valid=False,
            errors=["Field 'xyz' not found on 'EmpJob'"],
        )
        assert report.valid is False
        assert len(report.errors) == 1


class TestTestMatrix:
    def test_create_matrix(self):
        matrix = TestMatrix(
            rule_name="BR_Test",
            test_cases=[
                TestCase(
                    id="TC001",
                    description="Test case 1",
                    preconditions={"country": "PE"},
                    action="Save Job Information",
                    expected_result={"payGroup": "PG_PE_FT"},
                )
            ],
            total_paths=2,
            covered_paths=1,
            coverage_percentage="50%",
        )
        assert matrix.rule_name == "BR_Test"
        assert len(matrix.test_cases) == 1
        assert matrix.coverage_percentage == "50%"
