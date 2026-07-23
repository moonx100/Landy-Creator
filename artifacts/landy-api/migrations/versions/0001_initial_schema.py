"""Initial schema — full §5 schema from the LANDY Creator specification.

Revision ID: 0001
Revises: (none)
Create Date: 2026-07-23

Implements:
  - Extensions: pgvector, uuid-ossp
  - Tables (in dependency order): users, invites, sessions,
    documents, document_versions, clauses, risk_flags, suggested_edits,
    version_diffs, statutes, statute_provisions, citations,
    analysis_jobs, usage_events
  - Row-level security on 8 tables with policies keyed to
    current_setting('app.current_user_id', true)

Citation slots exist from day one but are deliberately empty in v1 —
the legal corpus attaches later with no migration required.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    # pgvector may not be available in all environments; the column
    # vector(768) on statute_provisions will fail at INSERT time if the
    # extension is absent, but table creation itself tolerates the absence.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ------------------------------------------------------------------
    # Users & access
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE users (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email               TEXT UNIQUE NOT NULL,
            display_name        TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            analyses_used       INT  NOT NULL DEFAULT 0,
            analyses_quota      INT  NOT NULL DEFAULT 8,
            quota_period_start  DATE NOT NULL DEFAULT CURRENT_DATE,
            is_active           BOOLEAN NOT NULL DEFAULT TRUE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE invites (
            code         TEXT PRIMARY KEY,
            email        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            redeemed_at  TIMESTAMPTZ,
            redeemed_by  UUID REFERENCES users(id)
        )
        """
    )

    # sessions — not in §5 spec but required for server-side session auth
    op.execute(
        """
        CREATE TABLE sessions (
            id          TEXT PRIMARY KEY,
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at  TIMESTAMPTZ NOT NULL,
            revoked     BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_sessions_user_id ON sessions (user_id)")
    op.execute(
        "CREATE INDEX idx_sessions_lookup ON sessions (id, revoked, expires_at)"
    )

    # ------------------------------------------------------------------
    # Documents (Class B — personal data)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE documents (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title         TEXT NOT NULL,
            counterparty  TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at    TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX idx_documents_user_id ON documents (user_id)")

    op.execute(
        """
        CREATE TABLE document_versions (
            id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            version_no        INT  NOT NULL,
            source_filename   TEXT NOT NULL,
            source_format     TEXT NOT NULL
                                CHECK (source_format IN ('docx','pdf_text','pdf_image','image')),
            storage_key       TEXT NOT NULL,
            sha256            TEXT NOT NULL,
            extraction_ok     BOOLEAN NOT NULL,
            extraction_note   TEXT,
            detected_language TEXT,
            uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, version_no)
        )
        """
    )

    # ------------------------------------------------------------------
    # Extracted structure
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE clauses (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            version_id    UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            ordinal       INT  NOT NULL,
            heading_path  TEXT,
            text          TEXT NOT NULL,
            char_start    INT,
            char_end      INT,
            UNIQUE (version_id, ordinal)
        )
        """
    )

    # ------------------------------------------------------------------
    # Risk findings
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE risk_flags (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            clause_id        UUID REFERENCES clauses(id) ON DELETE CASCADE,
            version_id       UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            domain           TEXT NOT NULL,
            severity         TEXT NOT NULL
                               CHECK (severity IN ('critical','high','medium','info')),
            finding_type     TEXT NOT NULL
                               CHECK (finding_type IN ('present_risky','absent','ambiguous')),
            summary          TEXT NOT NULL,
            rationale        TEXT NOT NULL,
            negotiation_ask  TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ------------------------------------------------------------------
    # Redline suggestions
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE suggested_edits (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            risk_flag_id   UUID NOT NULL REFERENCES risk_flags(id) ON DELETE CASCADE,
            clause_id      UUID REFERENCES clauses(id) ON DELETE CASCADE,
            original_text  TEXT NOT NULL,
            revised_text   TEXT NOT NULL,
            comment        TEXT,
            accepted       BOOLEAN
        )
        """
    )

    # ------------------------------------------------------------------
    # Version diffing
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE version_diffs (
            id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            from_version        UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            to_version          UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            clause_ref          TEXT,
            change_kind         TEXT NOT NULL
                                  CHECK (change_kind IN ('added','removed','modified')),
            materiality         TEXT NOT NULL
                                  CHECK (materiality IN ('material','immaterial')),
            materiality_reason  TEXT,
            before_text         TEXT,
            after_text          TEXT
        )
        """
    )

    # ------------------------------------------------------------------
    # Legal corpus (EMPTY IN V1 — do not populate)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE statutes (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            short_name    TEXT NOT NULL,
            full_title    TEXT NOT NULL,
            number        TEXT,
            year          INT,
            tier_label    TEXT,
            tier_rank     INT,
            tier_basis    TEXT,
            issuing_body  TEXT,
            source_url    TEXT,
            retrieved_date DATE,
            sha256        TEXT,
            status        TEXT NOT NULL DEFAULT 'unverified'
                           CHECK (status IN ('unverified','in_force','revoked','partially_valid'))
        )
        """
    )

    op.execute(
        """
        CREATE TABLE statute_provisions (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            statute_id  UUID NOT NULL REFERENCES statutes(id) ON DELETE CASCADE,
            bab         TEXT,
            bagian      TEXT,
            pasal       TEXT,
            ayat        TEXT,
            text        TEXT NOT NULL,
            embedding   vector(768)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE citations (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            risk_flag_id   UUID NOT NULL REFERENCES risk_flags(id) ON DELETE CASCADE,
            provision_id   UUID REFERENCES statute_provisions(id),
            citation_text  TEXT,
            basis          TEXT
        )
        """
    )

    # ------------------------------------------------------------------
    # Jobs & metering
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE analysis_jobs (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            version_id     UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            state          TEXT NOT NULL
                            CHECK (state IN ('queued','running','done','failed')),
            stage          TEXT,
            error_message  TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at    TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX idx_analysis_jobs_user_id ON analysis_jobs (user_id)")
    op.execute("CREATE INDEX idx_analysis_jobs_state   ON analysis_jobs (state)")

    op.execute(
        """
        CREATE TABLE usage_events (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id         UUID REFERENCES analysis_jobs(id) ON DELETE SET NULL,
            input_tokens   INT,
            output_tokens  INT,
            model          TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ------------------------------------------------------------------
    # Row-level security
    #
    # RLS policy pattern:
    #   nullif(current_setting('app.current_user_id', true), '')::uuid
    #
    # - current_setting(..., true) returns '' instead of raising an error
    #   when the setting is absent (unauthenticated connections).
    # - nullif(..., '') converts '' to NULL.
    # - NULL::uuid = user_id evaluates to NULL (not TRUE), so unauthenticated
    #   connections see zero rows on all RLS-protected tables.
    # - The app sets: SET LOCAL app.current_user_id = '<uuid>'
    #   inside engine.begin() at the start of every authenticated request.
    # ------------------------------------------------------------------
    rls_tables = [
        "documents",
        "document_versions",
        "clauses",
        "risk_flags",
        "suggested_edits",
        "version_diffs",
        "analysis_jobs",
        "usage_events",
    ]
    for tbl in rls_tables:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")

    # Direct user_id tables
    for tbl in ("documents", "analysis_jobs", "usage_events"):
        op.execute(
            f"""
            CREATE POLICY user_isolation ON {tbl}
                FOR ALL TO PUBLIC
                USING (
                    user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            """
        )

    # document_versions — one join to documents
    op.execute(
        """
        CREATE POLICY user_isolation ON document_versions
            FOR ALL TO PUBLIC
            USING (
                document_id IN (
                    SELECT id FROM documents
                    WHERE user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
        """
    )

    # clauses — two joins: document_versions → documents
    op.execute(
        """
        CREATE POLICY user_isolation ON clauses
            FOR ALL TO PUBLIC
            USING (
                version_id IN (
                    SELECT dv.id
                    FROM   document_versions dv
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
        """
    )

    # risk_flags — via version_id → document_versions → documents
    op.execute(
        """
        CREATE POLICY user_isolation ON risk_flags
            FOR ALL TO PUBLIC
            USING (
                version_id IN (
                    SELECT dv.id
                    FROM   document_versions dv
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
        """
    )

    # suggested_edits — via risk_flags → document_versions → documents
    op.execute(
        """
        CREATE POLICY user_isolation ON suggested_edits
            FOR ALL TO PUBLIC
            USING (
                risk_flag_id IN (
                    SELECT rf.id
                    FROM   risk_flags rf
                    JOIN   document_versions dv ON dv.id = rf.version_id
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
        """
    )

    # version_diffs — keyed on from_version → document_versions → documents
    op.execute(
        """
        CREATE POLICY user_isolation ON version_diffs
            FOR ALL TO PUBLIC
            USING (
                from_version IN (
                    SELECT dv.id
                    FROM   document_versions dv
                    JOIN   documents d ON d.id = dv.document_id
                    WHERE  d.user_id = nullif(
                        current_setting('app.current_user_id', true), ''
                    )::uuid
                )
            )
        """
    )


def downgrade() -> None:
    """Drop everything created in upgrade(), in reverse dependency order."""
    tables = [
        "usage_events", "analysis_jobs",
        "citations", "statute_provisions", "statutes",
        "version_diffs", "suggested_edits", "risk_flags",
        "clauses", "document_versions", "documents",
        "sessions", "invites", "users",
    ]
    for tbl in tables:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
    op.execute("DROP EXTENSION IF EXISTS vector")
