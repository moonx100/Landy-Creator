# LANDY Creator — v1 Build Specification

You are building **LANDY Creator**, a contract-review and negotiation-coaching tool for Indonesian content creators, influencers, artists and freelancers. Build exactly what is specified here. Where this document is silent, ask before inventing. Where it says *do not build*, do not build it.

The person directing this project is an Indonesian lawyer and former financial-services regulator. Legal reasoning in this document is deliberate — do not "simplify" legal categories or relax the constraints in §9.

---

## 1. What the product does

A creator uploads a contract they've been sent (usually by a brand or an agency). The system:

1. Extracts the contract's clauses while preserving structure.
2. Flags risks against a fixed taxonomy of clause domains.
3. Explains, per flag, why it matters to the creator and what to ask for instead.
4. Produces two outputs: a **redlined DOCX** with real tracked changes, and a **plain-language email draft** the creator can send to the counterparty.
5. On re-upload of a revised version, diffs it and classifies each change as **material** or **immaterial** by legal significance.

**Launch context:** free, invite-only beta, 10–20 users. Not a public signup product. Build for correctness and auditability, not scale.

---

## 2. Critical design decision: no contract-type routing

Indonesian KOL/creator agreements are **omnibus by practice**. A single "Brand Ambassador Agreement" routinely contains endorsement terms, work-for-hire service terms, an IP licence, and agency/management terms all at once.

Therefore: **do not build a contract-type classifier that routes to type-specific rule sets.** Run the full clause-domain taxonomy (§6) against every document. Detect which domains are *present*, report on those, and note materially absent domains as a gap finding (e.g. "no termination clause found" is itself a finding).

---

## 3. Stack

**Backend:** Python 3.11+ with **FastAPI**. Pydantic models for every request/response — no untyped dicts crossing a boundary.

**Frontend:** **React + Vite + TypeScript**, styled with **Tailwind**. A static SPA that talks to the API over HTTP. Do **not** use Next.js — a static frontend deploys anywhere without a Node server, which matters for §4.

**Database:** **PostgreSQL 15+** with the `pgvector` extension enabled.

**Storage:** S3-compatible object storage via `boto3`, with a **configurable endpoint URL**.

**Queue/async:** simple DB-backed job table plus a background worker process. Do not add Redis, Celery, or a message broker for 20 users.

Rationale for Python: the document-processing path (PDF text extraction, DOCX manipulation, direct OOXML XML editing via `lxml`) is materially better served in Python, and the wider LANDY codebase is Python.

---

## 4. Portability is a hard requirement

The production host is **undecided** — it may be Replit, it may be an Indonesian VPS in Jakarta. Write code that runs unmodified on either.

- **No Replit-proprietary services.** No Replit DB, no Replit Auth, no Replit Object Storage, no Replit Secrets accessed through a Replit-specific SDK.
- **Everything via environment variables.** Read config from the environment with `.env` for local dev. Provide a `.env.example` with every key documented and no real values.
- **Ship a `Dockerfile` and `docker-compose.yml`** that stand up API + Postgres + worker locally.
- Storage config must include `S3_ENDPOINT_URL`, so the same code targets AWS-compatible or Indonesian providers (IDCloudHost IS3, Biznet Gio NEO) by changing one variable.
- Database access via `DATABASE_URL` only.

---

## 5. Data schema

Create this as a proper migration. **Citation slots exist from day one and stay empty in v1** — this is deliberate, so the legal corpus attaches later with no migration.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------- Users & access ----------

CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email           TEXT UNIQUE NOT NULL,
  display_name    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- beta quota
  analyses_used   INT NOT NULL DEFAULT 0,
  analyses_quota  INT NOT NULL DEFAULT 8,
  quota_period_start DATE NOT NULL DEFAULT CURRENT_DATE,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE invites (
  code        TEXT PRIMARY KEY,
  email       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  redeemed_at TIMESTAMPTZ,
  redeemed_by UUID REFERENCES users(id)
);

-- ---------- Documents (CLASS B — personal data) ----------

CREATE TABLE documents (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title         TEXT NOT NULL,
  counterparty  TEXT,                    -- user-supplied label, e.g. "PT Brand XYZ"
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ              -- soft delete; purge job hard-deletes blobs
);

CREATE TABLE document_versions (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_no      INT NOT NULL,
  source_filename TEXT NOT NULL,
  source_format   TEXT NOT NULL CHECK (source_format IN ('docx','pdf_text','pdf_image','image')),
  storage_key     TEXT NOT NULL,         -- object storage key, never a public URL
  sha256          TEXT NOT NULL,
  extraction_ok   BOOLEAN NOT NULL,      -- FALSE surfaces to the user; never silent
  extraction_note TEXT,
  detected_language TEXT,                -- 'id', 'en', 'mixed'
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_no)
);

-- ---------- Extracted structure ----------

CREATE TABLE clauses (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  version_id        UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  ordinal           INT NOT NULL,        -- reading order within the document
  heading_path      TEXT,                -- e.g. "Pasal 5 > Ayat (2)" or "5.2"
  text              TEXT NOT NULL,
  char_start        INT,                 -- offset into the extracted plain text
  char_end          INT,
  UNIQUE (version_id, ordinal)
);

-- ---------- Risk findings ----------

CREATE TABLE risk_flags (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  clause_id     UUID REFERENCES clauses(id) ON DELETE CASCADE,  -- NULL = document-level / absence finding
  version_id    UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  domain        TEXT NOT NULL,           -- from the §6 taxonomy
  severity      TEXT NOT NULL CHECK (severity IN ('critical','high','medium','info')),
  finding_type  TEXT NOT NULL CHECK (finding_type IN ('present_risky','absent','ambiguous')),
  summary       TEXT NOT NULL,           -- one line, plain Bahasa
  rationale     TEXT NOT NULL,           -- why this matters to the creator
  negotiation_ask TEXT,                  -- what to ask for instead
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Redline suggestions ----------

CREATE TABLE suggested_edits (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  risk_flag_id  UUID NOT NULL REFERENCES risk_flags(id) ON DELETE CASCADE,
  clause_id     UUID REFERENCES clauses(id) ON DELETE CASCADE,
  original_text TEXT NOT NULL,
  revised_text  TEXT NOT NULL,
  comment       TEXT,                    -- becomes a Word comment alongside the change
  accepted      BOOLEAN                  -- user's choice before export; NULL = undecided
);

-- ---------- Version diffing ----------

CREATE TABLE version_diffs (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  from_version   UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  to_version     UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  clause_ref     TEXT,
  change_kind    TEXT NOT NULL CHECK (change_kind IN ('added','removed','modified')),
  materiality    TEXT NOT NULL CHECK (materiality IN ('material','immaterial')),
  materiality_reason TEXT,
  before_text    TEXT,
  after_text     TEXT
);

-- ---------- Legal corpus (EMPTY IN V1 — do not populate) ----------

CREATE TABLE statutes (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  short_name     TEXT NOT NULL,          -- 'UU Hak Cipta'
  full_title     TEXT NOT NULL,
  number         TEXT,
  year           INT,
  tier_label     TEXT,                   -- 'Undang-Undang'
  tier_rank      INT,                    -- NULLABLE. Never guess.
  tier_basis     TEXT,                   -- 'statutory: Pasal 7 UU 12/2011' | 'doctrinal: ...'
  issuing_body   TEXT,
  source_url     TEXT,
  retrieved_date DATE,
  sha256         TEXT,
  status         TEXT NOT NULL DEFAULT 'unverified'
                 CHECK (status IN ('unverified','in_force','revoked','partially_valid'))
);

CREATE TABLE statute_provisions (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  statute_id   UUID NOT NULL REFERENCES statutes(id) ON DELETE CASCADE,
  bab          TEXT,
  bagian       TEXT,
  pasal        TEXT,
  ayat         TEXT,
  text         TEXT NOT NULL,
  embedding    vector(768)
);

CREATE TABLE citations (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  risk_flag_id  UUID NOT NULL REFERENCES risk_flags(id) ON DELETE CASCADE,
  provision_id  UUID REFERENCES statute_provisions(id),
  citation_text TEXT,                    -- human-readable fallback
  basis         TEXT                     -- 'statutory' | 'doctrinal'
);

-- ---------- Jobs & metering ----------

CREATE TABLE analysis_jobs (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  version_id    UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  state         TEXT NOT NULL CHECK (state IN ('queued','running','done','failed')),
  stage         TEXT,                    -- human-readable progress
  error_message TEXT,                    -- populated on failure. NEVER swallow errors.
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ
);

CREATE TABLE usage_events (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id        UUID REFERENCES analysis_jobs(id) ON DELETE SET NULL,
  input_tokens  INT,
  output_tokens INT,
  model         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Row-level security is mandatory and means actual Postgres policies.** Enable RLS on `documents`, `document_versions`, `clauses`, `risk_flags`, `suggested_edits`, `version_diffs`, `analysis_jobs` and `usage_events`, with policies keyed to the session user. A `WHERE user_id = ...` convention in application code is **not** row-level security — one forgotten clause leaks another creator's contract.

---

## 6. Risk taxonomy — clause domains

Run all of these against every document. Store the domain key verbatim in `risk_flags.domain`.

| Key | Domain | Representative risks |
|---|---|---|
| `scope_deliverables` | Scope of work & deliverables | Vague deliverables, unlimited revisions, unbounded reshoots |
| `exclusivity` | Exclusivity & category restriction | Overbroad category, no territory limit, term exceeding campaign |
| `ip_ownership` | IP ownership & assignment | Full assignment where a licence suffices; work-for-hire over the creator's whole catalogue |
| `moral_rights` | Moral rights (*hak moral*) | Purported waiver of attribution/integrity — inalienable under Indonesian copyright law |
| `usage_rights` | Usage rights, media & whitelisting | Paid-media/whitelisting rights beyond organic; perpetual usage window; unlimited repurposing |
| `payment_terms` | Fee, schedule & tax | Payment on undefined "approval"; no late-payment remedy; who bears PPh/PPN; gross vs net ambiguity |
| `term_termination` | Term & termination | Termination for convenience by brand only; no notice period; post-term obligations unclear |
| `morality_clause` | Morality / reputation clause | Subjective triggers, unilateral determination, clawback of paid fees |
| `content_approval` | Approval & takedown rights | Unlimited takedown discretion; approval delays that block posting without extending deadlines |
| `confidentiality` | Confidentiality | Perpetual scope, no carve-out for public information |
| `personal_data_likeness` | Personal data & likeness | Image/likeness use beyond the campaign; personal-data handling; UU PDP exposure |
| `liability_indemnity` | Liability & indemnity | Uncapped indemnity, one-way indemnity, liability for brand's own product claims |
| `non_compete` | Post-term restriction | Post-term non-compete with no consideration or unreasonable duration |
| `dispute_forum` | Dispute resolution & governing law | Foreign forum/foreign law making enforcement impractical for an individual creator |
| `governing_language` | **Governing language** | Indonesian-language requirement for agreements involving Indonesian parties (UU 24/2009). **Always evaluated. Substantive finding, not a translation note.** |
| `agency_commission` | Agency & management terms | Commission rate/basis, post-term commission tail, scope of any power of attorney, lock-in duration |
| `disclosure_compliance` | Advertising disclosure | Endorsement disclosure obligations; who bears regulatory risk for product claims |
| `execution_validity` | Execution & validity | E-signature provider status, *meterai* treatment, signatory authority |

`governing_language` and `execution_validity` are **evaluated on every contract regardless of whether a matching clause exists** — absence is itself the finding.

---

## 7. Processing pipeline

```
Upload → validate → store blob → extract text → segment clauses
   → redact → LLM analysis (per clause-domain batch) → persist flags
   → generate suggested edits → done
```

**Input handling.** DOCX and text-layer PDF are first-class. Image-only PDF and images are accepted as an **ungated fallback** — process them, but attach a visible accuracy warning to the result and set `source_format` accordingly. Never silently reject; never silently degrade.

**Redaction before the model call.** The LLM API call is the material cross-border transfer of personal data, so minimise what leaves. Before sending text to the model, replace identifiers with stable placeholder tokens (`[NIK_1]`, `[NPWP_1]`, `[BANK_1]`, `[ADDR_1]`, `[PHONE_1]`, `[EMAIL_1]`) and keep the mapping **in memory / in the local DB only** so the redline can be re-expanded on export. Keep party role labels and company names — those are needed for coherent analysis. This also cuts token cost.

**Analysis calls.** Send only the relevant clause text plus a compact document summary — never the entire document per domain. Use zero-data-retention on the provider API.

**Async pattern.** `POST /api/analyses` returns `{ "job_id": ..., "state": "queued" }` immediately. The frontend polls `GET /api/analyses/{job_id}` every ~3 seconds and renders `stage` as progress. Never hold an HTTP request open for the duration of the analysis.

**Failures surface.** If extraction fails, if a model call errors, if a clause can't be parsed — write it to `analysis_jobs.error_message` and show it. A pipeline that returns empty results without surfacing the failure condition is a bug, not a graceful degradation.

---

## 8. Outputs

### 8a. Redlined DOCX — real tracked changes only

**Non-negotiable:** produce genuine OOXML tracked changes — `<w:ins>` and `<w:del>` elements with `w:id`, `w:author`, `w:date`, wrapping the affected runs (deleted text uses `<w:delText>`). Attach the `comment` as a real Word comment anchored to the change.

**Explicitly forbidden:** rendering insertions as blue/bold and deletions as red/strikethrough text. That is formatting, not markup. A reviewer cannot accept or reject it, and the recipient here is frequently brand-side counsel who will notice immediately.

Implement with `python-docx` for document handling plus direct XML manipulation via `lxml` for the tracked-change elements. Verify by opening the output in Word and confirming each change can be individually accepted and rejected. If a proposed edit cannot be expressed as a clean tracked change, surface it as a comment instead — never fall back to fake formatting.

### 8b. Email draft

Plain-language Bahasa Indonesia message the creator can send to the counterparty, covering the material asks in a professional, non-adversarial register. Copy-to-clipboard. **No in-platform editor and no email sending** — the creator uses their own email client.

---

## 9. Non-negotiable constraints

1. **`statutes.status` is operator-assigned only.** Defaults to `unverified`. No code path — script, LLM, or import — may set it automatically. Any such path is a bug.
2. **Silent failures are bugs.** Every pipeline stage logs and surfaces its failure state.
3. **Statutory vs. doctrinal, always labelled.** When citations arrive, `citations.basis` must state which. Never present inference as codified law.
4. **`tier_rank` may be NULL and must stay NULL unless grounded.** Do not assign integer ranks to instruments whose relative rank is not codified.
5. **Class A / Class B separation.** User-uploaded contracts (Class B) and the statute corpus (Class A) never share buckets, stores, or access policies.
6. **Disclaimer on every output surface**, including the exported DOCX and the email draft: this is legal *information* and negotiation coaching, **not legal advice**, and not a substitute for engaging an advokat.
7. **No "vibe coding."** Typed models at every boundary, explicit error handling, migrations for schema changes. This project's discipline is audit-trail engineering.

---

## 10. Guardrails for the beta

- **Invite-only.** No public signup. Redeem an invite code to create an account.
- **Per-user quota** on analyses (default 8/month, per-user overridable). Enforce server-side before dispatching a job. Prefer a monthly quota over a cooling-off timer between uploads — a lockout punishes normal working rhythm.
- **Hard spend cap** configured at the LLM provider dashboard, outside the app. Track `usage_events` in-app for visibility.
- **Private bucket, always.** Downloads go through short-lived (~10 minute) presigned URLs generated on authenticated request. Server-side encryption on upload.
- **Short retention.** Soft-delete immediately on user request; a scheduled job hard-deletes blobs after a configurable window (default 30 days).
- **Onboarding notice** instructing users to remove unnecessary personal data before uploading, plus a short privacy notice covering the cross-border inference transfer.

---

## 11. Language

UI in **Bahasa Indonesia**. Code, schema, comments and internal docs in English.

Contracts arrive in Indonesian, English, or bilingual form — detect and record in `document_versions.detected_language`, and analyse in the source language. Findings are always written in Bahasa Indonesia.

---

## 12. Do NOT build

- Contract-type classification or type-specific rule routing (see §2)
- An in-platform document editor
- Email sending, calendar integration, or n8n
- Any lawyer-matching, booking, or consultation feature — that is a separate engagement handled outside this product
- Payment or subscription flows — the beta is free
- OCR infrastructure beyond a basic fallback path
- Any population of the `statutes` / `statute_provisions` tables

---

## 13. Build order

1. Scaffold: FastAPI + React/Vite + Postgres via docker-compose. `.env.example`. Health check endpoint.
2. Migrations for the full §5 schema, including RLS policies.
3. Auth: invite redemption, session, quota enforcement.
4. Upload → object storage → text extraction (DOCX + text PDF first) → clause segmentation. Show extraction failures.
5. Redaction layer with reversible placeholder mapping.
6. Job queue + worker + polling endpoint.
7. LLM analysis producing `risk_flags` across the §6 taxonomy.
8. Review UI: clause list, flags grouped by severity, per-flag rationale and negotiation ask.
9. Suggested edits + **real tracked-changes DOCX export**. Verify accept/reject works in Word.
10. Email draft generation.
11. Version diffing with materiality classification.

Stop after step 3 and confirm the schema and auth model before proceeding.
