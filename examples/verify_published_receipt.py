"""Verify the published AMW receipt. No API key needed.

Downloads the portable receipt and key snapshot published at
https://www.thisisatest.tech/proof/ and checks the signature offline.
Pass --offline to use the bundled test fixtures instead of the network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

RECEIPT_URL = "https://www.thisisatest.tech/proof/receipt.json"
KEYS_URL = "https://www.thisisatest.tech/proof/trust-keys.json"
EXPECTED_ISSUER = "https://api.thisisatest.tech"

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")


def _download(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_fixture(name: str) -> dict:
    path = os.path.join(FIXTURE_DIR, name)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the published AMW receipt.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the bundled fixtures instead of downloading the published files.",
    )
    args = parser.parse_args(argv)

    from amw_demo.verify import verify_receipt

    if args.offline:
        print("Using bundled fixtures (no network).")
        receipt = _load_fixture("proof_receipt.json")
        keys = _load_fixture("proof_trust_keys.json")
    else:
        print(f"Downloading receipt from {RECEIPT_URL} ...")
        try:
            receipt = _download(RECEIPT_URL)
        except (OSError, ValueError) as exc:
            print(f"Could not download the receipt: {exc}", file=sys.stderr)
            print("Try again with --offline to use the bundled copy.", file=sys.stderr)
            return 2
        print(f"Downloading key snapshot from {KEYS_URL} ...")
        try:
            keys = _download(KEYS_URL)
        except (OSError, ValueError) as exc:
            print(f"Could not download the key snapshot: {exc}", file=sys.stderr)
            print("Try again with --offline to use the bundled copy.", file=sys.stderr)
            return 2

    result = verify_receipt(receipt, keys, expected_issuer=EXPECTED_ISSUER)
    if not result.ok:
        print(f"Could not verify the receipt: {result.reason}", file=sys.stderr)
        return 1

    print()
    print("Verified. The signature matches the published key snapshot.")
    print()
    print("What this shows:")
    print(f"  - Receipt {result.receipt_id} was signed by key {result.kid}.")
    print(f"  - It records a call to tool {result.tool!r} with outcome {result.outcome!r}.")
    print("  - The signature covers the exact signing_input bytes, so any")
    print("    change to those bytes would fail this check. Receipts are")
    print("    tamper-evident: edits are detectable, not impossible.")
    print()
    print("What this does not show:")
    print("  - It does not prove the tool output was correct. The receipt")
    print("    signs hashes of the request and response, not the content.")
    print("  - It does not prove anything about other calls, or about calls")
    print("    that have no receipt. A missing receipt proves nothing.")
    print("  - The key snapshot comes from the same origin being checked,")
    print("    so this does not independently establish who runs that origin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
