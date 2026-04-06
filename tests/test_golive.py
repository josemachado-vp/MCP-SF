"""Tests for go-live tools."""

import pytest


class TestGoLiveImports:
    def test_import_works(self):
        from tools.golive import (
            run_go_live_checks,
            generate_reconciliation_report,
        )
        assert callable(run_go_live_checks)
        assert callable(generate_reconciliation_report)
