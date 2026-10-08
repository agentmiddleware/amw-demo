"""Full AMW loop: permit, echo call, same-key retry, offline verification.

Needs AMW_API_KEY and AMW_WALLET_ID in the environment (see .env.example).
Optional: AMW_ISSUER_WALLET_ID (defaults to AMW_WALLET_ID) and AMW_BASE_URL.

Makes at most 2 invoke calls per run.
"""

from __future__ import annotations

import datetime
import os
import sys
import uuid

TOOL = "partner.echo"
SERVICE_ID = "partner.echo"


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value and value.strip() else None


def _invoke_outcome(response: dict) -> str | None:
    """Find the receipt outcome in an invoke response, if present."""
    receipt = response.get("receipt")
    if isinstance(receipt, dict) and receipt.get("outcome") is not None:
        return receipt.get("outcome")
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        inner = structured.get("receipt")
        if isinstance(inner, dict) and inner.get("outcome") is not None:
            return inner.get("outcome")
        if structured.get("outcome") is not None:
            return structured.get("outcome")
    if response.get("outcome") is not None:
        return response.get("outcome")
    return None


def _invoke_reason(response: dict) -> str | None:
    """Find a human readable reason in an invoke response, if present."""
    receipt = response.get("receipt")
    if isinstance(receipt, dict):
        for key in ("reason", "reason_code", "detail"):
            if receipt.get(key) is not None:
                return str(receipt.get(key))
    structured = response.get("structuredContent")
    if isinstance(structured, dict):
        inner = structured.get("receipt")
        if isinstance(inner, dict):
            for key in ("reason", "reason_code", "detail"):
                if inner.get(key) is not None:
                    return str(inner.get(key))
    if response.get("detail") is not None:
        return str(response.get("detail"))
    return None


def _check_tool_response(response: dict, label: str) -> int | None:
    """Return 1 after printing a message if the tool call failed, else None."""
    if response.get("isError") is True:
        outcome = _invoke_outcome(response) or "unknown"
        reason = _invoke_reason(response) or "no reason given"
        print(
            f"   {label} reported isError true "
            f"(outcome {outcome}, reason: {reason}).",
            file=sys.stderr,
        )
        return 1
    outcome = _invoke_outcome(response)
    if outcome is not None and outcome != "success":
        reason = _invoke_reason(response) or "no reason given"
        print(
            f"   {label} ended with outcome {outcome!r} "
            f"(reason: {reason}). Expected outcome 'success'.",
            file=sys.stderr,
        )
        return 1
    return None


def _api_error_exit(exc) -> int:
    """Print a short message for an AmwError (no traceback) and pick a code."""
    status = getattr(exc, "status", None)
    if status in (401, 403):
        print(
            f"AMW rejected the request (HTTP {status}). The demo key is "
            "missing, expired, or not allowed for this call. See the "
            '"Getting a key" section of the README for how to request one.',
            file=sys.stderr,
        )
        return 2
    print(f"AMW request failed: {exc}", file=sys.stderr)
    return 1


def main() -> int:
    api_key = _env("AMW_API_KEY")
    wallet_id = _env("AMW_WALLET_ID")
    if not api_key or not wallet_id:
        print("This example needs an operator-issued API key and a wallet id.")
        print("There is no self-serve key today. To get one, see KEY_PATH_PROPOSAL.md")
        print("and the 'Getting a key' section of the README, then set:")
        print("  export AMW_API_KEY='<your key>'")
        print("  export AMW_WALLET_ID='<your wallet id>'")
        return 2
    issuer_wallet_id = _env("AMW_ISSUER_WALLET_ID") or wallet_id

    from amw_demo.client import AmwClient, AmwError, extract_receipt_id
    from amw_demo.verify import verify_receipt

    client = AmwClient()
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15)
    ).isoformat()

    try:
        print(f"1. Creating a short-lived permit scoped to {TOOL} with a small budget ...")
        permit = client.create_permit(
            issuer_wallet_id=issuer_wallet_id,
            subject_wallet_id=wallet_id,
            max_credits="5",
            expires_at=expires_at,
            allowed_tools=[TOOL],
            scopes=[f"tool:{TOOL}:invoke", "billing:charge"],
            idempotency_key=str(uuid.uuid4()),
        )
        permit_id = permit.get("permit_id")
        if not permit_id:
            print(f"Permit creation returned no permit_id: {permit}", file=sys.stderr)
            return 1
        print(f"   Permit {permit_id} issued, expires {expires_at}.")

        idempotency_key = str(uuid.uuid4())
        arguments = {"message": "hello from the AMW demo"}
        print(
            f"2. Calling {TOOL} through the gateway "
            f"with idempotency key {idempotency_key} ..."
        )
        first = client.invoke(
            TOOL, arguments, wallet_id, permit_id, idempotency_key,
            service_id=SERVICE_ID,
        )
        failed = _check_tool_response(first, "First call")
        if failed is not None:
            return failed
        first_id = extract_receipt_id(first)
        print(f"   Echoed result: {first.get('structuredContent', first.get('content'))}")
        print(f"   Receipt id: {first_id}")

        print("3. Retrying with the SAME key and SAME arguments ...")
        second = client.invoke(
            TOOL, arguments, wallet_id, permit_id, idempotency_key,
            service_id=SERVICE_ID,
        )
        failed = _check_tool_response(second, "Retry call")
        if failed is not None:
            return failed
        second_id = extract_receipt_id(second)
        print(f"   Receipt id: {second_id}")
        if second_id != first_id:
            print(
                "   MISMATCH: the retry returned a different receipt id. "
                "Expected the original receipt back.",
                file=sys.stderr,
            )
            return 1
        print(
            "   Identical receipt id. A retry with the same idempotency key "
            "and the same request returns the original signed receipt. "
            "The tool is not called again and the wallet is not charged again. "
            "A new key would be a new call."
        )

        print("4. Fetching the portable receipt and verifying it offline ...")
        portable = client.portable_receipt(first_id)
        keys = client.trust_keys()
        result = verify_receipt(portable, keys, expected_issuer=client.base_url)
        if not result.ok:
            print(f"   Receipt verification failed: {result.reason}", file=sys.stderr)
            return 1
        print(f"   Verified receipt {result.receipt_id} offline (kid {result.kid}).")
        return 0
    except AmwError as exc:
        return _api_error_exit(exc)


if __name__ == "__main__":
    raise SystemExit(main())
