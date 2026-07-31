# Rule: Nothing secret, and no user data, ever enters git

## What the rule requires

The `Landy-Creator` repository is **public**. Every commit is published the
moment it is pushed. Therefore:

- `.env` and every variant (`.env.local`, `.env.production`, `*.env`) is
  gitignored and never committed. `.env.example` — names only, no values — is the
  single committed environment file.
- No credential, key, token, connection string, or password appears in tracked
  source, config, test fixture, migration, or documentation.
- No real contract, no uploaded document, no screenshot showing a real contract,
  and no file containing a creator's or counterparty's personal data is
  committed. This includes `attached_assets/`.
- Local upload storage stays outside the working tree. It currently does —
  `storage.py` sets `_LOCAL_ROOT = ~/.landy-dev-storage`. That placement is a
  deliberate safety property; do not relocate it into the repo.

If a secret is pushed, **rotate the key**. Removing the commit does not help:
it is in the fork network, in clones, and in GitHub's cache.

## Why

Two different exposures share one mechanism.

**Credentials.** `.env` carries `LLM_API_KEY`, `S3_SECRET_KEY`, `SESSION_SECRET`,
`ADMIN_SECRET`, and `DATABASE_URL`. On a public repo, a leaked `LLM_API_KEY` is
someone else's inference bill, and a leaked `ADMIN_SECRET` is invite-code
issuance. Automated scrapers find public-repo keys within minutes of a push —
this is not a theoretical risk.

**Personal data.** A committed contract, or a screenshot of one, is a permanent,
public, worldwide disclosure of a counterparty's personal data. Under UU PDP that
is a breach with no remediation path — the data cannot be recalled. A single
`git add -A` run at the wrong moment is all it takes, which is exactly why this
is enforced by `.gitignore` and a validator rather than by remembering.

The repository's `.gitignore` is generic Nx/Angular boilerplate. It covers
`node_modules` and build output. **It does not mention `.env` at all.** Until
that is fixed, the only thing standing between a real `.env` and a public commit
is that nobody has created one locally yet.

---

**FAIL condition:** (a) any `.env`-pattern file tracked by git other than
`.env.example`; or (b) `.gitignore` missing an `.env` rule; or (c) a
high-entropy credential literal (API key, secret, token, password, connection
string with credentials) in tracked source outside `.env.example`; or (d) a
document/image file committed under a path used for user uploads.

**WHERE-checked:** `scripts/governance/validate-secrets-hygiene.sh` (asserts the
`.gitignore` rules exist, lists tracked `.env` files, and greps tracked source
for credential-shaped literals) — run by `validate-all.sh` and before every push.

**Enforcement strength:** `mechanical` (tracked-file + gitignore + entropy grep)
+ `self-audit` (whether a committed asset contains personal data is a judgment
the grep cannot make — look at the file).
