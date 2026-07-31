# Rule: Explicit `WHERE user_id` is the isolation layer; RLS is defence-in-depth

## What the rule requires

Every query in `artifacts/landy-api/landy/routes/` that reads or writes
tenant-owned data — documents, versions, clauses, risk flags, analyses, diffs,
exports, redaction mappings — must carry an **explicit `user_id` predicate**
bound from the authenticated session, or join to a parent row that does.

PostgreSQL Row-Level Security is a **second** layer, not the first, and is
presently **inert**. Reasoning, tests, and code comments must not treat RLS as
the protection. Where the worker legitimately crosses tenants, it does so through
the documented `SET LOCAL app.current_user_id = 'SYSTEM_WORKER'` path, and that
crossing is explicit rather than incidental.

RLS becomes a genuine second layer only once the application connects as a
non-superuser role. Until that deploy change lands, do not weaken any `WHERE`
predicate on the strength of an RLS policy existing.

## Why

The Replit `DATABASE_URL` user is a PostgreSQL superuser with `bypassrls=True`,
confirmed against `pg_roles`. Per the PostgreSQL specification a superuser
bypasses RLS regardless of `FORCE ROW LEVEL SECURITY`, so the policies applied by
migrations `0004`/`0005` **do not restrict anything through the API today**.

This corrects Code Review 001, which recorded RLS as real protection. The danger
is not the inert policy; it is a future reviewer seeing `FORCE ROW LEVEL SECURITY`
in the migrations, concluding the database enforces isolation, and dropping a
`WHERE user_id` predicate as redundant. That single edit would expose every
tenant's contracts to every other tenant. The full finding is
`.agents/memory/rls-superuser-constraint.md`.

A related trap: DB-level RLS tests that connect as the superuser will see all rows
even with FORCE RLS set. That is expected and is **not** evidence the application
is secure.

---

**FAIL condition:** (a) a SQL statement or ORM query in
`artifacts/landy-api/landy/routes/` touching a tenant-owned table with no
`user_id` predicate and no join to a row that carries one; or (b) a code comment,
docstring, or test that asserts RLS as the operative isolation mechanism while
the app role remains superuser; or (c) a migration that drops a `user_id` column
or index relied on by route predicates.

**WHERE-checked:** `scripts/governance/validate-tenant-isolation.sh` (scans route
modules for tenant-table access lacking a `user_id` binding, and greps for
RLS-as-primary-protection assertions) + code review self-audit on every new route.

**Enforcement strength:** `mechanical` (route scan, heuristic) + `self-audit`
(join-path reasoning the grep cannot follow).
