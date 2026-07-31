# Rule: AI output is legal information, not legal advice

## What the rule requires

Every user-facing surface — web, mobile, API response metadata, exported DOCX,
generated negotiation email — carries the disclaimer that the content is legal
**information** and negotiation coaching, not legal advice, and not a substitute
for consulting an advocate. Canonical Bahasa Indonesia string:

> Konten ini merupakan informasi hukum, bukan nasihat hukum, dan bukan pengganti
> konsultasi dengan advokat.

Beyond the banner, the **register** of generated text is itself governed. Model
output and UI copy must not:

- instruct the user to sign, refuse to sign, or terminate an agreement;
- assert an outcome ("klausul ini batal demi hukum", "Anda akan menang");
- describe LANDY as the user's lawyer, counsel, or representative;
- promise a legal result from following a `negotiation_ask`.

Permitted register: identify, explain, compare, and propose language the user may
choose to request. "Talk to a lawyer" routes to MV's law firm as a **separately
engaged advocate service** — never presented as bundled into the SaaS.

## Why

Two exposures, one rule. First, UPL: MV is a licensed advocate and the product
carries their professional name through the YesMadameLawyer persona; an AI
product that advises rather than informs puts that licence in the frame. Second,
reliance: a creator who reads "klausul ini tidak sah" as a determination will sign
or refuse on that basis. The disclaimer banner does not cure advisory register in
the body text — a reader takes the specific sentence over the boilerplate every
time. Both halves are required.

Current coverage is partial: `landy-web` (`DisclaimerBanner.tsx`, `ReviewPage`,
`DemoReviewPage`), `landy-api` (`main.py`), `landy-mobile` (`login.tsx` only), and
the DOCX export (first-page comment). The mobile review/diff screens and the
email-draft body are the thin spots.

---

**FAIL condition:** (a) a user-facing page/screen component under
`artifacts/landy-web/src/pages/`, `artifacts/landy-mobile/app/`, or an export
generator under `artifacts/landy-api/landy/export/` that renders analysis output
with no disclaimer string reachable on that surface; or (b) an LLM system prompt
under `artifacts/landy-api/landy/` that lacks an explicit
information-not-advice instruction; or (c) any prompt or template containing
advisory-imperative constructions directing the user to sign, refuse, or
terminate.

**WHERE-checked:** `scripts/governance/validate-legal-advice-framing.sh`
(disclaimer-presence sweep across user-facing surfaces + system-prompt
instruction check + advisory-imperative grep) + `/review-gate` and `/export-gate`
self-audit on generated register.

**Enforcement strength:** `mechanical` (presence sweep) + `self-audit` (register
is a judgment; the grep catches the blatant cases only).
