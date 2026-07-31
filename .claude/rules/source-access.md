# Rule: Verify site access before building any acquisition path — DORMANT

> **DORMANT.** LANDY Creator **does not scrape.** It analyses contracts users
> upload. This rule is armed in advance for the ~6–8 statute mini-corpus build
> and must not be read as evidence that an acquisition path exists. Do not
> scaffold an `ingest/` tree in this repo on the strength of this file.

## What the rule requires

Before writing any acquisition/fetch path against an external legal source,
verify that source's access posture: HTTP status, `robots.txt`, WAF/challenge
behaviour, and any AI-training directive. Record the verification as a note in
`.agents/memory/` before the first line of fetch code.

**Do not target `peraturan.bpk.go.id`** — HTTP 403 behind a Cloudflare JS
challenge, and its `robots.txt` carries `ai-train=no`. Verify current posture for
`peraturan.go.id`, JDIHN, and OJK before relying on any of them; postures drift.

## Why

Scraping a source that forbids it is a legal and reputational exposure for a
product whose entire proposition is that a lawyer built it. Separately, a plain
HTTP client against a WAF produces silent false-empties — see `silent-failure.md`.
Access posture is verified per-source, per-build, never assumed from memory.

---

**FAIL condition:** any code under `artifacts/` that issues a request to a host
listed in `scripts/governance/source-denylist.txt`, OR any new fetch target with
no access-verification note in `.agents/memory/`.

**WHERE-checked:** `scripts/governance/validate-source-access.sh` (denylist grep
across `artifacts/`) + self-audit at the time the mini-corpus work begins.

**Enforcement strength:** `mechanical` (denylist grep) + `self-audit`
(per-source verification note).
