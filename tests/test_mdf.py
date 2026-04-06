"""Tests for MDF tools."""

import pytest


class TestMdfImports:
    def test_import_works(self):
        from tools.mdf import (
            get_mdf_object_definition,
            generate_mdf_import_template,
            list_mdf_objects,
        )
        assert callable(get_mdf_object_definition)
        assert callable(generate_mdf_import_template)
        assert callable(list_mdf_objects)
