---
name: Bug-class registry — recurring failure shapes
description: Catalog of failure CLASSES (not one-off bugs, not feature ideas) so the next instance is cheap to spot and promote to a rule.
---

# Bug-class registry

A **class** is a failure *shape* that has appeared, or is likely to reappear, at
more than one site. Cataloguing the shape — not just the instance — is what let
LC-41 fix six sites with one pattern. When a new instance of a known class
appears, cite the class; when a genuinely new shape appears, add a class here and
consider whether it warrants a `.claude/rules/` promotion with a validator.

This is **evidence, not law** (Rule Promotion Boundary). Nothing here binds a
future session by itself. A class earns a binding rule only when it is promoted.

Feature/tooling ideas are **not** bugs — those go in
[[claude-code-advancements.md]], never here.

---

## Class 1 — Silent fallback (failed result written as a benign valid value)

**Shape:** a classification or parse step, on failure, writes a plausible
in-vocabulary value instead of an honest "unknown" — `materiality→immaterial`,
`finding_type→none`, `severity→info`, `has_changes=False`, `comments→[]`,
`summary→raw slice`. Indistinguishable from success at every layer above; on the
money-path it terminates in a creator signing an unreviewed contract.

**Detection:** a failure/except branch that assigns a substantive domain value
with no surfaced status on the same path; a `lookup[x] ?? BENIGN_DEFAULT` in TS.

**Promoted:** `.claude/rules/silent-failure.md` + `.claude/rules/unknown-state.md`;
gates `validate-silent-failure.sh`, `validate-silent-failure-web.sh`; semantics
locked by `artifacts/landy-api/tests/test_unknown_state.py`. Six sites fixed in
LC-41 (2026-08-02). Full record: [[unknown-state-pattern.md]].

**Where it will try to return:** any new classification field, any new parse
step, any new render mapping. The `??`-into-a-config-entry shortcut is the
tempting reintroduction.

## Class 2 — Evidence drift (a memory/doc claim outlives the code it describes)

**Shape:** an `.agents/memory` note (or any doc) states "Status: OPEN" / cites
line numbers, but the underlying code was fixed or moved since. A future session
reads the stale claim as current truth and either re-does settled work or trusts
a "gap" that no longer exists.

**Instances:** `redaction-diff-path-gap.md` said OPEN while the fix was live at
HEAD; `materiality-default-gap.md` cited lines ~104/109/211 when the real sites
had shifted to ~125/236 (both caught 2026-08-02 only because an Explore agent
re-read the code). **Second occurrence, same day:** when those two files were
marked RESOLVED, a `---\n## RESOLVED` section was appended but the *original*
`## Status` block above it was left saying "OPEN as of 31 Jul 2026" <!-- memory-sync-ok: quoting the pattern as a worked example, not asserting this file's own status --> —
`extraction-coverage-gap.md` had the identical problem (MEMORY.md called it
resolved; the file body still said OPEN). All three caught by the first run of
`validate-memory-sync.sh` (piece C, this session) — the guard found the exact
drift it was built to catch, on its first execution, in files this very PR had
just edited.

**Detection:** a memory file naming a `validate-*.sh` that now exits 0 while the
file still claims OPEN; hard-coded line numbers in prose.

**Mitigation:** `validate-memory-sync.sh` (stale-claim heuristic); the
session-close reconciliation ritual (`/wrap-session`) re-checks touched claims.
Standing habit: prefer heading/symbol anchors over line numbers in prose.

## Class 3 — Toolchain side-effect committed by accident

**Shape:** a routine local command mutates a tracked file as a side effect, and
the mutation rides along in the next `git add -A`. Instance (2026-08-02): a
non-frozen `pnpm install` rewrote `pnpm-lock.yaml`, stripping Replit's esbuild
overrides (1864→412 lines); caught only by reading the commit diff.

**Detection:** review `git status` / the staged diff before committing; watch for
lockfiles, generated indexes, and config files you did not intend to touch.

**Mitigation:** use `pnpm install --frozen-lockfile` for read-only installs;
never `git add -A` without scanning the file list. Recorded in
[[landy-creator-toolchain]] (personal memory).

---

Related: [[MEMORY.md]], `.claude/rules/silent-failure.md`, `.claude/rules/unknown-state.md`,
[[claude-code-advancements.md]].
