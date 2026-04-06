"""Tests for the natural language query parser."""

import pytest
from helpers.nl_query_parser import (
    parse_nl_query,
    build_effective_date_filter,
    resolve_entity_for_query,
    ParsedQuery,
)


class TestParseNlQuery:
    """Tests for parse_nl_query function."""

    def test_simple_name_search(self):
        result = parse_nl_query("John")
        assert result.entity == "User"
        assert any("firstName" in f or "lastName" in f for f in result.filters)
        assert "name contains" in result.interpretation

    def test_full_name_search(self):
        result = parse_nl_query("John Smith")
        assert result.entity == "User"
        assert len(result.filters) >= 2  # One per name part

    def test_department_search(self):
        result = parse_nl_query("department 40000013")
        assert result.entity == "EmpJob"
        assert any("department eq '40000013'" in f for f in result.filters)
        assert "department=40000013" in result.interpretation

    def test_dept_abbreviation(self):
        result = parse_nl_query("dept HR")
        assert any("department eq 'HR'" in f for f in result.filters)

    def test_country_by_code(self):
        result = parse_nl_query("country COL")
        assert result.entity == "EmpJob"
        assert any("countryOfCompany eq 'COL'" in f for f in result.filters)

    def test_country_by_name(self):
        result = parse_nl_query("employees in Colombia")
        assert result.entity == "EmpJob"
        assert any("countryOfCompany eq 'COL'" in f for f in result.filters)

    def test_active_employees(self):
        result = parse_nl_query("active employees")
        assert any("emplStatus eq 'A'" in f for f in result.filters)

    def test_terminated_employees(self):
        result = parse_nl_query("terminated employees")
        assert any("emplStatus eq 'T'" in f for f in result.filters)

    def test_manager_search(self):
        result = parse_nl_query("reports to admin")
        assert any("managerId eq 'admin'" in f for f in result.filters)

    def test_location_search(self):
        result = parse_nl_query("location NYC")
        assert any("location eq 'NYC'" in f for f in result.filters)

    def test_user_id_search(self):
        result = parse_nl_query("user admin")
        assert result.entity == "User"
        assert any("userId eq 'admin'" in f for f in result.filters)

    def test_company_search(self):
        result = parse_nl_query("company 1000")
        assert any("company eq '1000'" in f for f in result.filters)

    def test_combined_query(self):
        result = parse_nl_query("department 40000013 in Colombia")
        assert any("department" in f for f in result.filters)
        assert any("countryOfCompany" in f for f in result.filters)

    def test_max_results(self):
        result = parse_nl_query("John", max_results=5)
        assert result.top == 5

    def test_include_inactive(self):
        result = parse_nl_query("all employees", include_inactive=True)
        assert not any("emplStatus" in f for f in result.filters)

    def test_custom_search_fields(self):
        result = parse_nl_query("John", search_fields=["firstName"])
        assert any("firstName" in f for f in result.filters)
        assert not any("lastName" in f for f in result.filters)

    def test_empty_query(self):
        result = parse_nl_query("")
        assert isinstance(result, ParsedQuery)

    def test_spanish_keywords(self):
        result = parse_nl_query("empleados activos")
        assert any("emplStatus eq 'A'" in f for f in result.filters)

    def test_injection_in_department(self):
        """Single quote in department value must be escaped."""
        result = parse_nl_query("department O'Brien")
        dept_filters = [f for f in result.filters if "department" in f]
        assert dept_filters
        assert "department eq 'O''Brien'" in dept_filters[0]

    def test_injection_in_manager(self):
        """Single quote in manager value must be escaped."""
        result = parse_nl_query("manager admin' or '1'='1")
        mgr_filters = [f for f in result.filters if "managerId" in f]
        assert mgr_filters
        # The regex captures only the first whitespace-delimited token ("admin'").
        # That token must be escaped to a harmless literal — no raw single quote.
        assert "managerId eq 'admin'''" in mgr_filters[0]

    def test_injection_in_name_search(self):
        """Name parts used in substringof must be escaped."""
        result = parse_nl_query("O'Brien")
        name_filters = [f for f in result.filters if "substringof" in f]
        assert name_filters
        assert "O''Brien" in name_filters[0]

    def test_invalid_search_field_name_skipped(self):
        """Invalid search_fields entries (injection attempts) must be skipped silently."""
        result = parse_nl_query("John", search_fields=["firstName;$expand=evil", "firstName"])
        # The invalid field should be skipped; valid field should still produce a filter
        name_filters = [f for f in result.filters if "substringof" in f]
        assert name_filters
        # No injection chars in any filter
        for f in name_filters:
            assert ";" not in f
            assert "$expand" not in f
        # The valid field 'firstName' must still produce a filter
        assert any("firstName" in f for f in name_filters)

    def test_country_name_fallback_escaped(self):
        """Country code from the name-lookup fallback must be escaped."""
        result = parse_nl_query("employees in Colombia")
        country_filters = [f for f in result.filters if "countryOfCompany" in f]
        assert country_filters
        # Code comes from entity_mapping.json — must be embedded safely
        assert "countryOfCompany eq '" in country_filters[0]
        # Should not contain raw unescaped single quotes in the value
        value_part = country_filters[0].split("eq '")[1].rstrip("'")
        assert "'" not in value_part  # no unescaped quotes in the value

    def test_effective_date_filter_rejects_injection(self):
        """build_effective_date_filter must reject non-date strings."""
        import pytest
        with pytest.raises(ValueError, match="Invalid date format"):
            build_effective_date_filter("EmpJob", "2024-01-01' or '1'='1")


class TestBuildEffectiveDateFilter:
    """Tests for build_effective_date_filter function."""

    def test_empjob_date_filter(self):
        result = build_effective_date_filter("EmpJob", "2024-06-15")
        assert "2024-06-15" in result
        assert "startDate" in result
        assert "endDate" in result

    def test_non_effective_dated_entity(self):
        result = build_effective_date_filter("User", "2024-06-15")
        assert result == ""

    def test_empcompensation_date_filter(self):
        result = build_effective_date_filter("EmpCompensation", "2024-01-01")
        assert "2024-01-01" in result


class TestResolveEntity:
    """Tests for resolve_entity_for_query function."""

    def test_job_keyword(self):
        assert resolve_entity_for_query("job") == "EmpJob"

    def test_department_keyword(self):
        # "department" matches EmpJob nl_hints first; use "departments" for FODepartment
        assert resolve_entity_for_query("departments") == "FODepartment"

    def test_company_keyword(self):
        # "company" matches FOCompany via nl_hints
        assert resolve_entity_for_query("companies") == "FOCompany"

    def test_user_keyword(self):
        assert resolve_entity_for_query("employee") == "User"

    def test_unknown_returns_input(self):
        assert resolve_entity_for_query("UnknownEntity") == "UnknownEntity"

    def test_case_insensitive(self):
        assert resolve_entity_for_query("SALARY") == "EmpCompensation"
