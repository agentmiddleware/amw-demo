"""Command line interface for the AMW demo package."""

from __future__ import annotations

import argparse
import json
import sys


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} does not contain a JSON object")
    return data


def cmd_verify(args: argparse.Namespace) -> int:
    from amw_demo.verify import verify_receipt

    try:
        receipt = _load_json(args.receipt)
    except (OSError, ValueError) as exc:
        print(f"Cannot read receipt file: {exc}", file=sys.stderr)
        return 2
    try:
        keys = _load_json(args.keys)
    except (OSError, ValueError) as exc:
        print(f"Cannot read trust-keys file: {exc}", file=sys.stderr)
        return 2
    result = verify_receipt(receipt, keys, expected_issuer=args.issuer)
    if result.ok:
        print(
            f"Verified receipt {result.receipt_id} "
            f"(tool {result.tool}, outcome {result.outcome}, kid {result.kid})."
        )
        return 0
    print(f"Verification failed: {result.reason}", file=sys.stderr)
    if result.reason.startswith("cannot determine") or "Cannot read" in result.reason:
        return 2
    if result.reason.startswith("unknown kid") or "missing field" in result.reason:
        return 2
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amw-demo", description="AMW demo tools")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Verify a portable receipt offline")
    verify.add_argument("receipt", help="Path to a portable receipt JSON file")
    verify.add_argument("--keys", required=True, help="Path to a trust-keys JSON file")
    verify.add_argument("--issuer", default=None, help="Expected issuer URL")
    verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
