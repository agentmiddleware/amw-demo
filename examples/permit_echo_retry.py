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

    from amw_demo.client import AmwClient, extract_receipt_id
    from amw_demo.verify import verify_receipt

    client = AmwClient()
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15)
    ).isoformat()

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
    first_id = extract_receipt_id(first)
    print(f"   Echoed result: {first.get('structuredContent', first.get('content'))}")
    print(f"   Receipt id: {first_id}")

    print("3. Retrying with the SAME key and SAME arguments ...")
    second = client.invoke(
        TOOL, arguments, wallet_id, permit_id, idempotency_key,
        service_id=SERVICE_ID,
    )
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
    result = verify_receipt(portable, keys)
    if not result.ok:
        print(f"   Receipt verification failed: {result.reason}", file=sys.stderr)
        return 1
    print(f"   Verified receipt {result.receipt_id} offline (kid {result.kid}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
