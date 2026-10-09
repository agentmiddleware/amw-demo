"""Offline tests for the client: request shapes, headers, receipt-id lookup."""

import io
import json
import urllib.error

import pytest

from amw_demo import client as client_module
from amw_demo.client import AmwClient, AmwError, extract_receipt_id


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture()
def captured(monkeypatch):
    calls = []

    def fake_urlopen(request, *args, **kwargs):
        calls.append(request)
        handler = getattr(fake_urlopen, "handler", None)
        if handler is not None:
            return handler(request)
        return FakeResponse({})

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    return calls


def _request_json(call):
    return json.loads(call.data.decode("utf-8")) if call.data else None


def test_health_needs_no_key(monkeypatch):
    seen = {}

    def fake_urlopen(request, *args, **kwargs):
        seen["headers"] = dict(request.header_items())
        return FakeResponse({"status": "healthy"})

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    client = AmwClient(base_url="https://x.example", api_key="")
    assert client.health() == {"status": "healthy"}
    assert "X-Api-Key" not in seen["headers"]


def test_create_permit_request_shape(captured):
    client = AmwClient(base_url="https://x.example", api_key="k123")

    def handler(request):
        assert request.full_url == "https://x.example/v1/permits"
        assert request.get_method() == "POST"
        assert request.get_header("Idempotency-key") == "idem-1"
        assert request.get_header("X-api-key") == "k123"
        body = _request_json(request)
        assert body["issuer_wallet_id"] == "w-issuer"
        assert body["subject_wallet_id"] == "w-subject"
        assert body["max_credits"] == "5"
        assert body["allowed_tools"] == ["partner.echo"]
        assert body["scopes"] == ["tool:partner.echo:invoke", "billing:charge"]
        return FakeResponse({"permit_id": "permit-1"})

    client_module.urllib.request.urlopen.handler = handler
    try:
        out = client.create_permit(
            issuer_wallet_id="w-issuer",
            subject_wallet_id="w-subject",
            max_credits="5",
            expires_at="2026-01-01T00:15:00+00:00",
            allowed_tools=["partner.echo"],
            scopes=["tool:partner.echo:invoke", "billing:charge"],
            idempotency_key="idem-1",
        )
    finally:
        del client_module.urllib.request.urlopen.handler
    assert out == {"permit_id": "permit-1"}
    assert len(captured) == 1


def test_invoke_request_shape(captured):
    client = AmwClient(base_url="https://x.example", api_key="k123")

    def handler(request):
        assert request.full_url == "https://x.example/mcp/tools/partner.echo/invoke"
        assert request.get_method() == "POST"
        body = _request_json(request)
        assert body["name"] == "partner.echo"
        assert body["arguments"] == {"message": "hi"}
        assert body["mcp_context"] == {
            "wallet_id": "w-1",
            "permit_id": "permit-1",
            "idempotency_key": "key-1",
        }
        return FakeResponse({"receipt": {"receipt_id": "rcpt-1"}, "content": []})

    client_module.urllib.request.urlopen.handler = handler
    try:
        out = client.invoke(
            "partner.echo", {"message": "hi"}, "w-1", "permit-1", "key-1"
        )
    finally:
        del client_module.urllib.request.urlopen.handler
    assert extract_receipt_id(out) == "rcpt-1"


def test_401_message_points_to_key_docs(monkeypatch):
    def fake_urlopen(request, *args, **kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"detail": "missing credentials"}'),
        )

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    client = AmwClient(base_url="https://x.example", api_key="bad")
    with pytest.raises(AmwError) as excinfo:
        client.health()
    assert excinfo.value.status == 401
    assert "KEY_PATH_PROPOSAL.md" in str(excinfo.value)
    assert "bad" not in str(excinfo.value)


def test_error_shows_server_detail(monkeypatch):
    def fake_urlopen(request, *args, **kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(b'{"detail": "insufficient_scope"}'),
        )

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    client = AmwClient(base_url="https://x.example", api_key="k")
    with pytest.raises(AmwError) as excinfo:
        client.health()
    assert excinfo.value.status == 403
    assert excinfo.value.detail == "insufficient_scope"


@pytest.mark.parametrize(
    "response,expected",
    [
        ({"receipt": {"receipt_id": "r1"}}, "r1"),
        ({"receipt": {"id": "r2"}}, "r2"),
        ({"structuredContent": {"receipt_id": "r3"}}, "r3"),
        ({"receipt_id": "r4"}, "r4"),
    ],
)
def test_extract_receipt_id_variants(response, expected):
    assert extract_receipt_id(response) == expected


def test_extract_receipt_id_missing():
    with pytest.raises(AmwError):
        extract_receipt_id({"content": []})
