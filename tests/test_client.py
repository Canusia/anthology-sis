"""Tests for the OData client: auth header construction and nextLink paging.

Uses a fake requests.Session so nothing touches the network.
"""

import pytest

from anthology_sis.client import ODataClient
from anthology_sis.config import Config


def make_config(**overrides) -> Config:
    base = dict(
        root_uri="https://example.test/",
        auth_mode="apikey",
        api_key="ABC123",
        api_key_scheme="ApplicationKey",
        username="",
        password="",
        sections_path="ds/odata/ClassSectionTerms",
        terms_path="ds/odata/Terms",
        timeout=30,
    )
    base.update(overrides)
    return Config(**base)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class FakeSession:
    """Returns queued responses in order; records requests for assertions."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.headers = {}
        self.auth = None

    def mount(self, *a, **k):
        pass

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return self._responses.pop(0)


class TestAuthHeader:
    def test_apikey_adds_scheme(self):
        cfg = make_config(api_key="ABC123")
        assert cfg.authorization_header == "ApplicationKey ABC123"

    def test_apikey_passthrough_if_already_has_scheme(self):
        cfg = make_config(api_key="ApplicationKey XYZ")
        assert cfg.authorization_header == "ApplicationKey XYZ"

    def test_apikey_missing_raises(self):
        cfg = make_config(api_key="")
        with pytest.raises(RuntimeError):
            _ = cfg.authorization_header

    def test_basic_mode_no_header(self):
        cfg = make_config(auth_mode="basic")
        assert cfg.authorization_header is None


class TestPaging:
    def test_follows_nextlink(self):
        page1 = FakeResponse({
            "value": [{"Id": 1}, {"Id": 2}],
            "@odata.nextLink": "https://example.test/next-page",
        })
        page2 = FakeResponse({"value": [{"Id": 3}]})
        session = FakeSession([page1, page2])
        client = ODataClient(make_config(), session=session)

        rows = list(client.iter_collection("ds/odata/Terms"))
        assert [r["Id"] for r in rows] == [1, 2, 3]
        # First call carries params; the nextLink call must not re-send them.
        assert session.calls[1]["params"] is None
        assert session.calls[1]["url"] == "https://example.test/next-page"

    def test_single_page(self):
        session = FakeSession([FakeResponse({"value": [{"Id": 1}]})])
        client = ODataClient(make_config(), session=session)
        assert len(list(client.iter_collection("ds/odata/Terms"))) == 1


class TestErrorMapping:
    def test_401_raises_permission(self):
        session = FakeSession([FakeResponse({}, status_code=401)])
        client = ODataClient(make_config(), session=session)
        with pytest.raises(PermissionError):
            list(client.iter_collection("ds/odata/Terms"))

    def test_403_raises_permission(self):
        session = FakeSession([FakeResponse({}, status_code=403)])
        client = ODataClient(make_config(), session=session)
        with pytest.raises(PermissionError):
            list(client.iter_collection("ds/odata/Terms"))
