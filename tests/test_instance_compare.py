"""Tests for instance comparison tools."""

import pytest


class TestCompareInstanceConfig:
    """Basic validation tests for instance comparison."""

    def test_import_works(self):
        from tools.instance_compare import (
            compare_instance_config,
            compare_picklists,
            compare_business_rules,
            compare_foundation_objects,
        )
        assert callable(compare_instance_config)
        assert callable(compare_picklists)
        assert callable(compare_business_rules)
        assert callable(compare_foundation_objects)
