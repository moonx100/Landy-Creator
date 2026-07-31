# Rule: `statutes.status` is operator-assigned only

## What the rule requires

A statute's `status` (`unverified` / `in_force` / `revoked` / `partially_valid`)
must **never** be scraped, inferred, LLM-derived, or auto-populated. Schema
default is `unverified`. It changes only through an explicit operator action MV
runs and reviews. Any code path that writes a verified `status` outside a
sanctioned operator entrypoint is a bug.

## Why

Legal in-force status is a judgment a licensed advocate makes, not a fact a
parser can read. An auto-set status launders an inference into apparent ground
truth. In Creator this becomes load-bearing the moment the citation layer lights
up: a risk flag citing a **revoked** provision as authority is a wrong legal
claim delivered with full confidence.

The schema is already compliant (`0001_initial_schema.py`: `status TEXT NOT NULL
DEFAULT 'unverified'` with a `CHECK` constraint). This rule is therefore a
**regression guard**, not a fix — it exists so the mini-corpus ingestion work
cannot quietly relax it.

---

**FAIL condition:** any assignment setting `status` to `in_force`, `revoked`, or
`partially_valid` under `artifacts/landy-api/` outside a file listed in
`scripts/governance/status-integrity-allowlist.txt` — in Python
(`status = '...'`, `"status": "in_force"`, an `UPDATE ... SET status`) or as a
schema/migration default. Also fails if the `statutes` DDL loses its
`DEFAULT 'unverified'` or its `CHECK (status IN ...)` constraint.

**WHERE-checked:** `scripts/governance/validate-status-integrity.sh` (grep gate,
allowlist-aware) + `scripts/governance/validate-provenance-schema.sh` (schema
default + CHECK) — both run by `validate-all.sh` and in CI.

**Enforcement strength:** `mechanical`.
