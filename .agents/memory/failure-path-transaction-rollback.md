---
name: Failure-path writes roll back with the request transaction
description: get_raw_conn wraps the request in engine.begin(); a record written on a path that then raises (e.g. an audit/rate-limit row) is rolled back with it. Use an independent transaction.
---

# A record written on a raising path is erased by the rollback

`landy/deps/db.py get_raw_conn()` yields a connection inside `engine.begin()`,
which **rolls back on any exception**. So anything written through that
connection on a path that subsequently raises is undone.

LC-4 hit this: `verify_otp()`'s `_fail()` recorded the failed OTP attempt via the
request connection, then raised the 401. The rate limiter counts those rows — but
each one rolled back with the 401, so the count always read zero and lockout
**never triggered**. Three of five rate-limit tests failed only against real
Postgres (first live run of the DB-gated suite). Fixed by writing the failed
attempt in its own `engine.begin()` (`_record_failed_attempt_committed`).

**Rule of thumb:** any audit / security / rate-limit record that must survive a
request that then raises needs its **own** transaction, not the request's.

**Verification lesson:** this was invisible until the suite ran against real
Postgres. Test auth / security-critical PRs against a real DB **before merge** —
it caught this ship-blocker (and the DB-gated tests had never run before, hiding
two more fixture bugs; see local `landy-creator-toolchain`).

Related: `.claude/rules/tenant-isolation.md`, `MEMORY.md`.
