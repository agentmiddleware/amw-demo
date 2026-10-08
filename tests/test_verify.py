"""Offline tests for the receipt verifier."""

import copy
import json
import os

import pytest

from amw_demo.verify import verify_receipt

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture()
def receipt():
    return _load("proof_receipt.json")


@pytest.fixture()
def keys():
    return _load("proof_trust_keys.json")


def test_fixture_receipt_verifies(receipt, keys):
    result = verify_receipt(
        receipt, keys, expected_issuer="https://api.thisisatest.tech"
    )
    assert result.ok, result.reason
    assert result.receipt_id == "rcpt-9daf745e477d45ab"
    assert result.tool == "partner.echo"


def test_tampered_signing_input_fails(receipt, keys):
    bad = copy.deepcopy(receipt)
    claims = json.loads(bad["signing_input"])
    claims["credits_charged"] = "999"
    bad["signing_input"] = json.dumps(claims, sort_keys=True, separators=(",", ":"))
    result = verify_receipt(bad, keys)
    assert not result.ok


def test_flipped_signature_byte_fails(receipt, keys):
    import base64

    bad = copy.deepcopy(receipt)
    raw = bytearray(base64.b64decode(bad["signature"]))
    raw[0] ^= 1
    bad["signature"] = base64.b64encode(bytes(raw)).decode("ascii")
    result = verify_receipt(bad, keys)
    assert not result.ok


def test_wrong_kid_is_undetermined(receipt, keys):
    bad = copy.deepcopy(receipt)
    bad["kid"] = "no-such-key"
    result = verify_receipt(bad, keys)
    assert not result.ok
    assert "unknown kid" in result.reason


def test_disabled_key_refused(receipt, keys):
    bad_keys = copy.deepcopy(keys)
    for entry in bad_keys["keys"]:
        if entry.get("kid") == receipt["kid"]:
            entry["status"] = "disabled"
    result = verify_receipt(receipt, bad_keys)
    assert not result.ok
    assert "disabled" in result.reason


def test_payload_hash_mismatch_detected():
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    # Build a receipt whose signature is valid but whose payload_hash is
    # wrong, so a failure below can only come from the payload_hash check.
    private_key = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(
        private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    claims = {"receipt_id": "rcpt-test", "tool": "partner.echo"}
    claims["payload_hash"] = "0" * 64
    signing_input = json.dumps(claims, sort_keys=True, separators=(",", ":"))
    forged = {
        "receipt_id": "rcpt-test",
        "issuer": "https://api.thisisatest.tech",
        "kid": "fresh-test-key",
        "signing_input": signing_input,
        "signature": base64.b64encode(
            private_key.sign(signing_input.encode("utf-8"))
        ).decode("ascii"),
    }
    forged_keys = {
        "keys": [
            {"kid": "fresh-test-key", "status": "active", "public_key_b64": public_b64}
        ]
    }
    result = verify_receipt(forged, forged_keys)
    assert not result.ok
    assert "payload_hash" in result.reason


def test_issuer_mismatch(receipt, keys):
    result = verify_receipt(
        receipt, keys, expected_issuer="https://someone-else.example"
    )
    assert not result.ok
    assert "issuer" in result.reason
