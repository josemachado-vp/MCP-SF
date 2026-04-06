"""Tests for the SF client helper."""

import pytest

from helpers.sf_client import SFClient, DATA_CENTERS


class TestResolveBaseUrl:
    def setup_method(self):
        self.client = SFClient(None)  # No HTTP client needed for URL resolution

    def test_known_data_center(self):
        assert self.client.resolve_base_url("DC4") == "https://api4.successfactors.com"

    def test_case_insensitive(self):
        assert self.client.resolve_base_url("dc4") == "https://api4.successfactors.com"

    def test_preview_data_center(self):
        assert self.client.resolve_base_url("DC4_PREVIEW") == "https://api4preview.sapsf.com"

    def test_salesdemo_data_center(self):
        url = self.client.resolve_base_url("DC4_SALESDEMO")
        assert url == "https://apisalesdemo4.successfactors.com"

    def test_direct_url(self):
        url = "https://api99.custom.sapsf.com"
        assert self.client.resolve_base_url(url) == url

    def test_direct_url_strips_trailing_slash(self):
        assert self.client.resolve_base_url("https://api4.sapsf.com/") == "https://api4.sapsf.com"

    def test_unknown_dc_raises(self):
        with pytest.raises(ValueError, match="Unknown data center"):
            self.client.resolve_base_url("DC999")

    def test_all_data_centers_have_https(self):
        for dc, url in DATA_CENTERS.items():
            assert url.startswith("https://"), f"{dc} URL doesn't start with https"
