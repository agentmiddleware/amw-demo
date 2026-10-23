# Agent instructions for amw-demo

## Scope and verified commands

This repository contains the public AMW demo client and offline receipt verifier. Work only in this repository. Never touch `agent-middleware-api`.

The project requires Python 3.10 or newer. The CI matrix uses Python 3.11 and 3.12.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m build
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python examples/verify_published_receipt.py --offline
```

Use `python -m pytest` because the `pytest` launcher breaks when the path contains a space. If the package index is unreachable, `pip install --no-index --no-build-isolation -e '.[dev]'` works offline against a venv created with `--system-site-packages`.

Verified on Python 3.12.2: ruff clean, full suite 31 passed, build OK, offline receipt verification OK. Four tests bind a loopback socket, so sandboxes that block local sockets will fail them.

## House rules

1. Do not use em dashes, en dashes, or spaced hyphens in copy.
2. Use real data only. Do not add synthetic data.
3. Never force push or merge as an admin.
4. Use one branch per issue.
5. Commit with `git commit -s`.
6. Never commit `.env`, API keys, private keys, or other credentials.
7. Never touch `agent-middleware-api`.

## Merge flow

QA posts PASS naming the exact head SHA. After CI is green and all review threads are resolved, AMW PR Merger merges the pull request.
