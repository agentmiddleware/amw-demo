"""Tiny AMW client built on the Python standard library.

Only speaks the public API described by the live OpenAPI document at
https://api.thisisatest.tech/openapi.json. Authentication uses an
operator-issued key read from the AMW_API_KEY environment variable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.thisisatest.tech"

_GETTING_KEY_HINT = (
    "AMW has no public self-serve key. See KEY_PATH_PROPOSAL.md and "
    'the "Getting a key" section of the README for how to request one.'
)


class AmwError(Exception):
    """An AMW request failed. Carries the HTTP status and server detail."""

    def __init__(self, message: str, status: int | None = None, detail=None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _auth_headers(api_key: str | None) -> dict:
    if not api_key:
        return {}
    return {"X-API-Key": api_key}


def _read_json_response(response) -> dict | list:
    raw = response.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


def _friendly_message(status: int, detail, url: str) -> str:
    if status == 401:
        return (
            f"AMW returned 401 for {url}: an operator-issued API key is "
            f"required. Set AMW_API_KEY and retry. {_GETTING_KEY_HINT} "
            f"Server detail: {detail}"
        )
    return f"AMW request to {url} failed with status {status}: {detail}"


class AmwClient:
    """Minimal client for the AMW public API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        base = base_url or os.environ.get("AMW_BASE_URL", DEFAULT_BASE_URL)
        self.base_url = base.rstrip("/")
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("AMW_API_KEY")

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        extra_headers: dict | None = None,
    ):
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        headers.update(_auth_headers(self.api_key))
        if extra_headers:
            headers.update(extra_headers)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return _read_json_response(response)
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
                payload = json.loads(raw.decode("utf-8")) if raw else None
            except (ValueError, UnicodeDecodeError):
                payload = None
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
            raise AmwError(
                _friendly_message(exc.code, detail, url),
                status=exc.code,
                detail=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise AmwError(f"Could not reach {url}: {exc.reason}") from exc

    def health(self) -> dict:
        """Return the public liveness payload. No key needed."""
        return self._request("GET", "/health")

    def trust_keys(self) -> dict:
        """Return the public signing-key set. No key needed."""
        return self._request("GET", "/.well-known/trust-keys.json")

    def create_permit(
        self,
        issuer_wallet_id: str,
        subject_wallet_id: str,
        max_credits: str,
        expires_at: str,
        allowed_tools: list | None = None,
        scopes: list | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Create a scoped permit. Requires an operator-issued key."""
        body = {
            "issuer_wallet_id": issuer_wallet_id,
            "subject_wallet_id": subject_wallet_id,
            "max_credits": max_credits,
            "expires_at": expires_at,
        }
        if allowed_tools is not None:
            body["allowed_tools"] = allowed_tools
        if scopes is not None:
            body["scopes"] = scopes
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._request("POST", "/v1/permits", body=body, extra_headers=headers)

    def invoke(
        self,
        tool: str,
        arguments: dict,
        wallet_id: str,
        permit_id: str,
        idempotency_key: str,
        service_id: str | None = None,
    ) -> dict:
        """Call a tool through the gateway. Requires an operator-issued key."""
        target = service_id or tool
        body = {
            "name": tool,
            "arguments": arguments,
            "mcp_context": {
                "wallet_id": wallet_id,
                "permit_id": permit_id,
                "idempotency_key": idempotency_key,
            },
        }
        path = f"/mcp/tools/{target}/invoke"
        return self._request("POST", path, body=body)

    def portable_receipt(self, receipt_id: str) -> dict:
        """Fetch the portable receipt bundle. Requires an operator-issued key."""
        return self._request("GET", f"/v1/receipts/{receipt_id}/portable")


def extract_receipt_id(invoke_response: dict) -> str:
    """Find the receipt id in an invoke response.

    Looks in the places the API may put it and fails clearly if absent.
    """
    if not isinstance(invoke_response, dict):
        raise AmwError(f"Invoke response has no receipt id: {invoke_response!r}")
    receipt = invoke_response.get("receipt")
    candidates = []
    if isinstance(receipt, dict):
        candidates.extend([receipt.get("receipt_id"), receipt.get("id")])
    structured = invoke_response.get("structuredContent")
    if isinstance(structured, dict):
        candidates.extend([structured.get("receipt_id"), structured.get("id")])
        inner = structured.get("receipt")
        if isinstance(inner, dict):
            candidates.extend([inner.get("receipt_id"), inner.get("id")])
    candidates.extend(
        [invoke_response.get("receipt_id"), invoke_response.get("receiptId")]
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    raise AmwError(
        "Invoke response contained no receipt id "
        "(looked in receipt.receipt_id, receipt.id, "
        "structuredContent.receipt_id, and top-level receipt_id)."
    )
