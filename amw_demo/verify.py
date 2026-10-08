"""Offline verifier for AMW portable receipts.

Checks an Ed25519 signature over the exact ``signing_input`` bytes, plus an
optional payload hash binding and issuer check. No network calls.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass


@dataclass
class VerificationResult:
    ok: bool
    reason: str
    receipt_id: str | None = None
    kid: str | None = None
    issuer: str | None = None
    tool: str | None = None
    outcome: str | None = None


def _b64decode(value: str) -> bytes:
    text = value.strip()
    padding = "=" * (-len(text) % 4)
    return base64.b64decode(text + padding)


def _find_key(trust_keys: dict, kid: str) -> dict:
    keys = trust_keys.get("keys", [])
    if not isinstance(keys, list):
        raise TypeError("trust-keys document has no 'keys' list")
    for entry in keys:
        if isinstance(entry, dict) and entry.get("kid") == kid:
            return entry
    raise LookupError(f"no key with kid {kid!r} in trust-keys document")


def _public_bytes(entry: dict) -> bytes:
    raw = entry.get("public_key_b64")
    if not raw:
        jwk = entry.get("jwk", {})
        raw = jwk.get("x", "") if isinstance(jwk, dict) else ""
    if not raw:
        raise ValueError("key entry has no public_key_b64 or jwk.x")
    return _b64decode(raw)


def verify_receipt(
    receipt: dict,
    trust_keys: dict,
    expected_issuer: str | None = None,
) -> VerificationResult:
    """Verify one portable receipt bundle against a trust-keys document."""
    try:
        signing_input = receipt["signing_input"]
        signature_b64 = receipt["signature"]
        kid = receipt["kid"]
    except KeyError as exc:
        return VerificationResult(
            ok=False, reason=f"receipt is missing field: {exc}"
        )
    receipt_id = receipt.get("receipt_id")
    issuer = receipt.get("issuer")

    try:
        key_entry = _find_key(trust_keys, kid)
    except LookupError:
        return VerificationResult(
            ok=False,
            reason=f"unknown kid {kid!r}: not in trust-keys document",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )
    if key_entry.get("status") == "disabled":
        return VerificationResult(
            ok=False,
            reason=f"key {kid!r} is disabled, refusing to verify",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )

    try:
        public_bytes = _public_bytes(key_entry)
    except ValueError as exc:
        return VerificationResult(
            ok=False,
            reason=f"cannot load public key for {kid!r}: {exc}",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(_b64decode(signature_b64), signing_input.encode("utf-8"))
    except ImportError:
        return VerificationResult(
            ok=False,
            reason="cannot determine: the 'cryptography' package is not installed",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )
    except (InvalidSignature, ValueError, TypeError):
        return VerificationResult(
            ok=False,
            reason="signature invalid: bytes do not match the signing_input",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )

    try:
        claims = json.loads(signing_input)
    except ValueError:
        return VerificationResult(
            ok=False,
            reason="signature valid but signing_input is not JSON",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )

    payload_hash = claims.get("payload_hash")
    if payload_hash is not None:
        rest = {k: v for k, v in claims.items() if k != "payload_hash"}
        canonical = json.dumps(rest, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if digest != payload_hash:
            return VerificationResult(
                ok=False,
                reason="payload_hash mismatch: signing_input does not match its hash",
                receipt_id=receipt_id,
                kid=kid,
                issuer=issuer,
            )

    if expected_issuer is not None and issuer != expected_issuer:
        return VerificationResult(
            ok=False,
            reason=f"issuer mismatch: got {issuer!r}, expected {expected_issuer!r}",
            receipt_id=receipt_id,
            kid=kid,
            issuer=issuer,
        )

    return VerificationResult(
        ok=True,
        reason="signature valid",
        receipt_id=receipt_id or claims.get("receipt_id"),
        kid=kid,
        issuer=issuer,
        tool=claims.get("tool"),
        outcome=claims.get("outcome"),
    )
