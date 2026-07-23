---
name: Replit DB superuser RLS constraint
description: The Replit DATABASE_URL user is a PostgreSQL superuser with bypassrls=True. FORCE ROW LEVEL SECURITY cannot restrict superusers per Postgres spec.
---

# Replit DB superuser and RLS

## The rule

Do NOT rely on PostgreSQL FORCE ROW LEVEL SECURITY for user isolation through the API. The Replit DATABASE_URL user (`postgres`) is a superuser with `bypassrls=True`, which means it bypasses RLS regardless of `FORCE ROW LEVEL SECURITY`.

## Why

Confirmed by querying `pg_roles`:
- `rolsuper=True`, `rolbypassrls=True`
- FORCE RLS is still set on all 8 tables (migrations applied correctly), but the superuser ignores it per PostgreSQL spec

## How to apply

- **Primary isolation**: explicit `WHERE user_id = :uid` predicates in every API route query. This is the actual security layer.
- **Defense-in-depth**: FORCE RLS policies still protect against non-superuser connections (e.g., a future read-only analytics role).
- **Worker access**: The worker uses `SET LOCAL app.current_user_id = 'SYSTEM_WORKER'` — this is respected by RLS policies for non-superuser connections; the superuser worker bypasses it anyway.
- **Production deploy**: If deployed with a non-superuser DB role, FORCE RLS would add a genuine second layer. Apply `NOINHERIT NOSUPERUSER` to the app user via migration if possible.
- **Test caveat**: DB-level RLS tests that connect as the superuser will see all rows even with FORCE RLS set. This is expected and does not indicate a bug in the application code.
