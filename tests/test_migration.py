"""Tests for migration tools."""

import pytest
from tools.migration import generate_migration_sequence


class TestGenerateMigrationSequence:
    """Tests for migration sequence generation (no API calls)."""

    def test_basic_sequence(self):
        result = generate_migration_sequence(
            entities=["FOCompany", "FODepartment", "EmpJob", "User", "EmpEmployment"]
        )
        assert result["total_entities"] == 5
        ordered = result["ordered_sequence"]
        assert len(ordered) == 5

        # FOCompany should come before FODepartment
        fo_comp_order = next(o["order"] for o in ordered if o["entity"] == "FOCompany")
        fo_dept_order = next(o["order"] for o in ordered if o["entity"] == "FODepartment")
        assert fo_comp_order < fo_dept_order

        # User should come before EmpJob
        user_order = next(o["order"] for o in ordered if o["entity"] == "User")
        job_order = next(o["order"] for o in ordered if o["entity"] == "EmpJob")
        assert user_order < job_order

    def test_missing_dependencies_warned(self):
        result = generate_migration_sequence(entities=["EmpJob"])
        ordered = result["ordered_sequence"]
        assert len(ordered) == 1
        # EmpJob depends on User, FOCompany, etc.
        assert len(ordered[0]["missing_dependencies"]) > 0
        assert len(result["warnings"]) > 0

    def test_unrecognized_entities(self):
        result = generate_migration_sequence(entities=["cust_MyObject", "FOCompany"])
        assert "cust_MyObject" in result["unrecognized_entities"]
        assert len(result["ordered_sequence"]) == 1  # Only FOCompany

    def test_empty_input(self):
        result = generate_migration_sequence(entities=[])
        assert result["total_entities"] == 0
        assert len(result["ordered_sequence"]) == 0

    def test_full_migration(self):
        result = generate_migration_sequence(
            entities=["FOCompany", "FODivision", "FODepartment", "FOLocation",
                      "FOJobCode", "User", "EmpEmployment", "PerPersonal",
                      "EmpJob", "EmpCompensation"]
        )
        ordered = result["ordered_sequence"]
        # Verify order integrity
        orders = [o["order"] for o in ordered]
        assert orders == sorted(orders)
