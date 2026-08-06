# LC-25 — Tenant-Isolation Route Sweep

**Scope:** every HTTP route mounted in `artifacts/landy-api/landy/main.py`
(`health`, `auth`, `documents`, `analyses`, `exports`, `diffs`,
`storage_routes`). This is the complete route surface — `landy/admin.py` is a
CLI, not an HTTP router, and is out of scope.

**Why this audit exists:** the Replit `DATABASE_URL` role is a Postgres
superuser with `bypassrls=True` ([rls-superuser-constraint](../../.agents/memory/rls-superuser-constraint.md)),
so `FORCE ROW LEVEL SECURITY` is a no-op through the API. The explicit
`WHERE user_id = :uid` predicate in each handler — or a join to a row that
already carries one — is the only isolation actually running. See
`.claude/rules/tenant-isolation.md`.

**Verdict legend:** `OK` predicate (or verified-parent join) present ·
`MISSING` user-scoped, no predicate · `AMBIGUOUS` scoping unclear, needs a
decision · `N/A` legitimately tenant-agnostic.

## Audit table

| Method + Path | Handler (file:func) | Table(s) touched | Tenant predicate present? | Verdict |
|---|---|---|---|---|
| GET `/api/healthz` | `health.py:health_check` | none | n/a — no DB access | N/A |
| POST `/api/auth/redeem` | `auth.py:redeem_invite` | `invites`, `users`, `sessions` | pre-auth: no tenant exists yet; scoped by unredeemed invite `code` + unique `email` | N/A |
| POST `/api/auth/login` | `auth.py:login` | `users`, `login_tokens` | pre-auth: looked up by `email` to *issue* a challenge; identical 200 response for unknown/inactive users prevents enumeration | N/A |
| POST `/api/auth/verify` | `auth.py:verify_otp` | `login_tokens`, `otp_verify_attempts`, `users`, `sessions` | pre-auth: scoped by `challenge_id` (opaque UUID) + OTP hash comparison; rate-limit counters keyed by `identifier`/`ip_address`, not a tenant row | N/A |
| GET `/api/auth/me` | `auth.py:get_me` | (none — reads the already-authenticated `user` object) | n/a | N/A |
| POST `/api/auth/logout` | `auth.py:logout` | `sessions` | `WHERE id = :token` — the session token itself is the predicate: a 32-byte `secrets.token_urlsafe` value only the owning client ever holds, and revoking it affects only that one session | OK |
| POST `/api/documents` | `documents.py:create_document` | `documents` | `INSERT ... user_id = :uid` bound from `get_current_user` | OK |
| GET `/api/documents` | `documents.py:list_documents` | `documents`, `document_versions`, `analysis_jobs` | `WHERE user_id = :uid`; child queries scoped by `document_id`/`version_id` already drawn from that filtered set | OK |
| GET `/api/documents/{id}` | `documents.py:get_document` | `documents` | `_require_document()` → `WHERE id = :id AND user_id = :uid` | OK |
| DELETE `/api/documents/{id}` | `documents.py:delete_document` | `documents` | `_require_document()` guard, then `UPDATE ... WHERE id = :id AND user_id = :uid` | OK |
| POST `/api/documents/{id}/versions` | `documents.py:upload_version` | `documents`, `document_versions`, `analysis_jobs`, `users` (quota) | `_require_document()` first; version/job inserts bound to verified `document_id` / explicit `uid` | OK |
| GET `/api/documents/{id}/versions` | `documents.py:list_versions` | `document_versions` | `_require_document()` first, then `WHERE document_id = :did` (already ownership-verified) | OK |
| GET `/api/documents/{id}/versions/{vid}/download` | `documents.py:download_version` | `document_versions`, `documents` | `_require_document()` + join predicate `d.user_id = :uid` on the version fetch (double-checked) | OK |
| GET `/api/documents/{doc_id}/versions/{ver_id}/diff` | `diffs.py:get_version_diff` | `document_versions`, `documents`, `version_diffs`, `analysis_jobs` | ownership join `d.user_id = :uid` up front; every later query keyed off IDs already proven owned (`prior_row.id`, `ver_id`) | OK |
| POST `/api/analyses` | `analyses.py:create_analysis` | `document_versions`, `documents`, `analysis_jobs` | explicit `d.user_id = :uid` join before enqueue; insert binds `:uid` | OK |
| GET `/api/analyses/{job_id}` | `analyses.py:get_analysis` | `analysis_jobs` | `WHERE aj.id = :jid AND aj.user_id = :uid` | OK |
| GET `/api/analyses/{job_id}/results` | `analyses.py:get_analysis_results` | `analysis_jobs`, `risk_flags`, `suggested_edits`, `citations`, `document_comments`, `document_versions`, `analysis_domain_runs` | `job_row` fetch is `WHERE aj.id = :jid AND aj.user_id = :uid`; every subsequent query is keyed by `job_id`/`version_id` drawn from that verified row (two queries additionally re-assert `user_id` directly) | OK |
| PATCH `/api/suggested-edits/{edit_id}` | `exports.py:patch_suggested_edit` | `suggested_edits`, `risk_flags`, `document_versions`, `documents` | **was MISSING on the `UPDATE`** — the preceding `SELECT` verified ownership via a join to `d.user_id = :uid`, but the mutating `UPDATE` itself carried only `WHERE id = :eid`, no predicate of its own. Not exploitable as written (the `SELECT` 404s first), but it broke the "every query is scoped" invariant. **Fixed in this PR**: the `UPDATE` now carries its own `WHERE id = :eid AND EXISTS (... d.user_id = :uid ...)`. | MISSING → fixed |
| POST `/api/documents/{doc_id}/versions/{ver_id}/export/docx` | `exports.py:export_docx` | `document_versions`, `documents`, `clauses`, `suggested_edits`, `redaction_mappings`, `analysis_jobs` | `_require_version_ownership()` (`d.user_id = :uid`) then `_fetch_latest_job_id()` (`WHERE version_id = :vid AND user_id = :uid`); clause/edit fetches keyed off the verified `version_id`/`job_id` | OK |
| POST `/api/documents/{doc_id}/versions/{ver_id}/export/email-draft` | `exports.py:export_email_draft` | same as above + `risk_flags` | same pattern as `export_docx` | OK |
| GET `/api/storage/local/{path}` | `storage.py:serve_local_file` | `sessions`, `users` (token check); no per-row DB predicate — object storage key, not a table row | session token validated against `sessions`/`users`, then the storage key's embedded `documents/{user_id}/...` segment is compared to the authenticated `user_id`; mismatch → 403 | OK |

## Notes / things found but out of scope for this sweep

- `exports.py:export_docx` calls `storage.generate_presigned_url(export_key, expires_in=600)` **without** a `bearer_token` in local-storage mode, so it always falls into the `except` fallback and returns a base64 data URL rather than a link through `storage.py:serve_local_file`. Not a tenant-isolation gap (the bytes still only reach the already-ownership-verified caller, in the same response), and `serve_local_file`'s `documents/`-prefix check would in fact reject an `exports/...` key if it were ever reached — this is a storage-routing quirk, not an access-control bug. Flagging for awareness, not fixing here (would be a refactor beyond this job's scope).

## Summary

- **21 routes enumerated**, all in `artifacts/landy-api`.
- **16 OK** as found.
- **1 MISSING → fixed** (`PATCH /api/suggested-edits/{edit_id}`, see above).
- **0 AMBIGUOUS** — no route required an MV scoping decision; there is no
  admin/staff surface, shared-resource read, or cross-tenant join anywhere in
  the current route set.
- **4 N/A**, justified individually above (`/healthz` and the three pre-auth
  `auth` bootstrap routes).

## Fix applied

`artifacts/landy-api/landy/routes/exports.py` — `patch_suggested_edit`'s
`UPDATE suggested_edits` now carries its own ownership predicate (`EXISTS`
subquery joining `risk_flags → document_versions → documents`, matching
`d.user_id = :uid`), instead of relying solely on the preceding `SELECT`.
Regression test: `artifacts/landy-api/tests/test_suggested_edit_isolation.py`
(DB-gated — asserts a foreign `user_id` cannot flip `accepted` on another
tenant's row via that exact `UPDATE`; requires `DATABASE_URL` against a real
Postgres, so it runs on Replit, not locally — there is no local Postgres in
this dev environment, same as the other DB-gated tests in this suite).
