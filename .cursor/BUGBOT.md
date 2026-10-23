# Bugbot review focus

Review security first: authorization, permit scope, signing, receipt verification, and injection paths. Check that API keys and private keys cannot enter commits, logs, errors, or output. Require meaningful tests for behavior changes, including failure cases.

Enforce the repository house rules: no em dashes, en dashes, or spaced hyphens in copy; real data only, with no synthetic data; no force push; no admin merge; never touch `agent-middleware-api`; one branch per issue; commits use `git commit -s`; never commit `.env` or keys.

QA must post PASS naming the exact head SHA. AMW PR Merger merges only after CI is green and all review threads are resolved.
