/**
 * index-headings.ts — deterministic heading-map generator for registered
 * context-dense markdown files (governance apparatus, 2026-08-02).
 *
 * Reads scripts/index-registry.json, and for each registered {source, index}
 * pair, regenerates a heading-map sibling file (H1-H4, GitHub-style anchors,
 * a source_sha256 content hash, and a level tally) — the same shape as the
 * F4TALITY project's *-INDEX.md convention this was adapted from.
 *
 * Registration is a JUDGMENT CALL, not a hard line-count gate: a short but
 * heading-dense file that's read every session (CLAUDE.md) is worth
 * indexing; a long file nobody navigates by section isn't. ~250 lines is a
 * rough "probably worth it" heuristic, not a rule enforced anywhere. Add a
 * `registered_when` note to the registry entry explaining the call.
 *
 * Determinism is required — no timestamps, no Date.now(), no randomness —
 * so `--check` (regenerate in memory, diff against on-disk) is a valid
 * staleness test. Do not add anything non-deterministic to the output.
 *
 * Usage (from scripts/):
 *   pnpm index-headings           # write
 *   pnpm index-headings --check   # verify, exit 1 on drift
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

interface RegistryEntry {
  id: string;
  source: string;
  index: string;
  registered_when: string;
}

interface Heading {
  text: string;
  level: number;
  line: number;
  anchor: string;
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..", "..");

function githubSlug(text: string, seen: Map<string, number>): string {
  // GitHub's heading-anchor algorithm: lowercase, strip characters that
  // aren't word chars/spaces/hyphens, spaces -> hyphens, dedupe with -1/-2.
  let slug = text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
  const count = seen.get(slug) ?? 0;
  seen.set(slug, count + 1);
  return count === 0 ? slug : `${slug}-${count}`;
}

function extractHeadings(content: string): Heading[] {
  const lines = content.split("\n");
  const seen = new Map<string, number>();
  const headings: Heading[] = [];
  // Skip fenced code blocks so a `#` inside a code sample is never parsed
  // as a heading.
  let inFence = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const m = /^(#{1,4})\s+(.+?)\s*$/.exec(line);
    if (!m) continue;
    const level = m[1].length;
    const text = m[2].replace(/\s*#+\s*$/, ""); // strip trailing closing #'s
    headings.push({ text, level, line: i + 1, anchor: githubSlug(text, seen) });
  }
  return headings;
}

function normalizeLineEndings(content: string): string {
  // This repo has core.autocrlf=true, so a `git checkout` on Windows can
  // hand back CRLF line endings for a file that was hashed/generated as LF
  // (or vice versa) — making a naive hash non-deterministic across checkouts
  // even when the actual content hasn't changed. Normalize before doing
  // anything content-sensitive (hashing, line counting, heading extraction).
  return content.replace(/\r\n/g, "\n");
}

function sha256(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex");
}

function buildIndex(entry: RegistryEntry, rawSourceContent: string): string {
  const sourceContent = normalizeLineEndings(rawSourceContent);
  const headings = extractHeadings(sourceContent);
  const lines = sourceContent.split("\n").length;
  const hash = sha256(sourceContent);
  const tally = new Map<number, number>();
  for (const h of headings) tally.set(h.level, (tally.get(h.level) ?? 0) + 1);

  const rows = headings
    .map((h) => {
      const indent = "&nbsp;&nbsp;".repeat(h.level - 1);
      const lvl = `H${h.level}`;
      const jump = `[#${h.anchor}](./${entry.source}#${h.anchor}) · L${h.line}`;
      return `| ${indent}${h.text} | ${lvl} | ${jump} |`;
    })
    .join("\n");

  const tallyRows = [...tally.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([lvl, n]) => `| H${lvl} | ${n} |`)
    .join("\n");

  return `# INDEX — ${entry.id}

> **Generated artifact — do not hand-edit.** Regenerate with
> \`pnpm --dir scripts index-headings\`.
> Registered in \`scripts/index-registry.json\`; validated by
> \`scripts/governance/validate-index-sync.sh\`. Heading map only — open the
> source and grep the heading text to navigate (line numbers drift; the hash
> below is the staleness signal, not the line numbers).

**Source:** [\`${entry.source}\`](./${entry.source})
**source_sha256:** \`${hash}\`
**source_lines:** ${lines}
**headings_indexed:** ${headings.length}
**registered_when:** ${entry.registered_when}

---

## Heading map

| Heading | Lvl | Jump |
|---|---|---|
${rows}

---

## Level tally

| Level | Count |
|---|---|
${tallyRows}
| **Total** | **${headings.length}** |
`;
}

function main() {
  const check = process.argv.includes("--check");
  const registryPath = join(ROOT, "scripts", "index-registry.json");
  const registry: { entries: RegistryEntry[] } = JSON.parse(
    readFileSync(registryPath, "utf8"),
  );

  if (registry.entries.length === 0) {
    console.log("index-headings: registry is empty — nothing to do");
    process.exit(0);
  }

  let drift = false;
  for (const entry of registry.entries) {
    const sourcePath = join(ROOT, entry.source);
    if (!existsSync(sourcePath)) {
      console.error(`index-headings: FAIL — registered source missing: ${entry.source}`);
      drift = true;
      continue;
    }
    const sourceContent = readFileSync(sourcePath, "utf8");
    const generated = buildIndex(entry, sourceContent);
    const indexPath = join(ROOT, entry.index);

    if (check) {
      if (!existsSync(indexPath)) {
        console.error(`index-headings: FAIL — ${entry.index} does not exist (run without --check)`);
        drift = true;
        continue;
      }
      const onDisk = normalizeLineEndings(readFileSync(indexPath, "utf8"));
      if (onDisk !== generated) {
        console.error(`index-headings: FAIL — ${entry.index} is stale vs. ${entry.source}`);
        drift = true;
      } else {
        console.log(`index-headings: PASS — ${entry.index} is in sync`);
      }
    } else {
      writeFileSync(indexPath, generated, "utf8");
      console.log(`index-headings: wrote ${entry.index} (${entry.source} -> ${entry.index})`);
    }
  }

  process.exit(drift ? 1 : 0);
}

main();
