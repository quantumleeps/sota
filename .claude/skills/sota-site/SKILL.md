---
name: sota-site
description: >-
  Build and publish a hyperlinked "state of the art" (SotA) review microsite to
  GitHub Pages from a list of papers on a topic, as a new topic in a persistent
  multi-topic hub repo. Use this whenever the user hands you a set of papers
  (arXiv IDs, arXiv URLs, or a papers.txt) and wants a published, provenance-cited
  review — phrasings like "make a sota site for these papers", "add a topic to the
  sota hub", "publish a state-of-the-art review of this corpus", "turn these
  papers into a hosted review", or "do an agent-memory-v2 with this newer set".
  Each invocation absorbs exactly ONE paper set (one sealed corpus) for ONE topic
  and reads it in isolation; do not mix papers across topics unless explicitly
  told to compare or merge.
---

# SotA Site — paper set → published state-of-the-art review (hub model)

This skill turns a list of papers into a hyperlinked, provenance-cited **state of the art** review and publishes it as **one topic in a persistent hub** on **GitHub Pages**. The hub repo (e.g. `sota`) accumulates topics over time; each run adds or refreshes one topic. The pipeline per topic: fetch the corpus → read every paper in full via parallel agents → synthesize a multi-page topic site with strict provenance → regenerate the hub landing → verify link integrity → publish.

## The one rule that governs everything: corpus isolation per topic

A single run absorbs **one topic = one paper set = one sealed corpus, read in isolation**. The *repo* is a shared hub that holds many topics, but the *reading* of each topic is sealed.

- **Never read or ingest another topic's papers or digests** into this topic's context. Do not glob across sibling topic corpora; do not let one topic's conclusions leak into another. Each topic absorbs its own set and writes its own pages — as a human reviewer would sit down with one stack of papers at a time.
- A new **version** (`agent-memory-v2`) is a **separate topic** with its own corpus, read fresh — not "v1 plus new papers."
- The **only** exception is if the user explicitly asks you to compare or merge topics. Otherwise, one set in, one topic site out.

Why this matters: the value of these reviews is a faithful, self-consistent reading of a specific body of work. Bleed-through between topics produces claims no single corpus supports and quietly breaks provenance.

## Inputs to collect first

Confirm these before doing any work (ask only for what's missing):

1. **The paper set** — arXiv IDs and/or URLs (a list or a `papers.txt`), plus optionally non-arXiv lab writeups (fetched as HTML/clean text). Optional per-paper hints: a role (`anchor` / `core` / `support`), a short title, a relevance note.
2. **Topic slug** — kebab-case (e.g. `agent-memory`). Becomes the topic dir under `docs/<slug>/` and `topics-corpora/<slug>/`, and the published path `…github.io/<repo>/<slug>/`.
3. **Hub repo** — the existing hub (default `sota`) you're adding the topic to, or — for a brand-new hub — its name. Confirm whether to create a new hub or extend an existing one.
4. **Visibility** — GitHub Pages serves a **world-readable** site (public even from a private repo on non-Enterprise plans). Content is normally derived from public papers, so public is the default — but confirm, because publishing is outward-facing and hard to fully retract (indexed/cached).
5. **Depth / breadth** — default is "thorough": read every paper in full. For very large sets, cluster low-priority references into grouped reading agents (still full-text), but say so.
6. **Deep dive? (default: NO)** — whether to also harvest the next level of *cited references* (an anchor paper's bibliography) into the corpus. Off = a standard **review** of the given set. On = a **deep dive** that ingests references too; the result is labelled a deep dive and states how many references it added (see Phase 1b). Ask before turning this on — it multiplies the corpus and the reading cost.
7. **Date cutoff? (default: none)** — an optional hard date window (e.g. "nothing before 2026"). Applied **programmatically** from each arXiv id's YYMM, so it also filters harvested references. Set `SOTA_AFTER` / `SOTA_BEFORE` (YYYY or YYYY-MM) — see Phase 1.

## Repo layout (the hub)

The hub repo is a self-contained working project. The published site lives under `docs/` (GitHub Pages source = `main` `/docs`); the unpublished working material is gitignored.

```
<hub-repo>/                         ← the working repo; `cd` here & run claude
├── .claude/skills/sota-site/       ← this skill (travels with the repo)
├── CLAUDE.md  README.md  .gitignore
├── docs/                           ← PUBLISHED (Pages source: main /docs)
│   ├── index.html                  ← the hub landing (topic cards + nav)
│   ├── styles.css  .nojekyll        ← ONE shared stylesheet at the docs root
│   └── <slug>/*.html               ← one topic per dir; each has its own corpus.html
└── topics-corpora/                 ← WORKING material. GITIGNORED. never published.
    └── <slug>/
        ├── corpus/ {papers/<id>/…, papers/index.json, papers.txt, meta.json}
        └── digest/                 ← (optional) saved digests for this topic
```

Topic pages link the shared stylesheet as `../styles.css` and the hub as `../index.html` ("↑ All SotA" up-link). Reading agents are pointed **only** at this topic's `topics-corpora/<slug>/corpus/papers/`.

## The workflow

### Phase 0 — Setup
If extending an existing hub: create `topics-corpora/<slug>/corpus/papers/` and `docs/<slug>/`. If creating a new hub: also scaffold `docs/` (copy `assets/styles.css` → `docs/styles.css` verbatim — never hand-roll CSS), `docs/.nojekyll`, a `.gitignore` that ignores `/topics-corpora/`, and a starter `docs/index.html` hub. Write the input paper list to `topics-corpora/<slug>/corpus/papers.txt`, and curated per-paper metadata to `corpus/meta.json` (titles/roles/relevance; an `anchor` id if you'll harvest its refs).

### Phase 1a — Fetch the main paper set
For each arXiv paper, run the bundled fetcher into the topic's corpus:
```bash
scripts/fetch-arxiv-src.sh <id-or-url> topics-corpora/<slug>/corpus/papers
```
TeX → HTML (self-contained via `monolith`) → PDF fallback; idempotent. For non-arXiv lab writeups, fetch a self-contained HTML bundle (`monolith`) and produce a `clean.txt` text extraction in the source's dir.

**Date cutoff (optional).** To enforce a hard date window, export `SOTA_AFTER` and/or `SOTA_BEFORE` (YYYY or YYYY-MM) before fetching — the fetcher reads each id's YYMM and `[date-skip]`s anything outside the window (no download). Preview/explain a filter first with `scripts/arxiv-date.py --after 2026 --report < papers.txt`. Because the cutoff lives in the fetcher, it also applies to deep-dive references.

### Phase 1b — Deep dive (OPTIONAL — default OFF)
Only if the user opted in (input #6). Harvest the cited references of an anchor paper into the shared corpus pool (one flat dir per ref, deduped against papers you already have):
```bash
scripts/fetch-paper-refs.sh topics-corpora/<slug>/corpus/papers/<anchor-id> topics-corpora/<slug>/corpus/papers
```
Set the anchor id in `corpus/meta.json` and `"mode": "deep-dive"`. A deep dive must be **clearly labelled** as one and state how many references it added (Phase 3). A standard review keeps `"mode": "review"` and harvests nothing. Respect the date cutoff here too (it applies automatically via the fetcher).

### Phase 1c — Generate the manifest
```bash
scripts/build-index.py topics-corpora/<slug>/corpus
```
Detects each source's entrypoint (the `read` field), merges curated `meta.json`, handles non-arXiv `web` sources, parses the anchor's `.bbl` for reference titles, and stamps `mode` (review/deep-dive) → writes `corpus/papers/index.json`. Read `index.json` first when ingesting — do not glob.

### Phase 2 — Read every paper in full (parallel agents)
Dispatch reading subagents — one per paper for the priority set, small thematic clusters for large reference lists — each returning a structured, quote-anchored **digest**. Use the exact format and prompt in **`reference/digest-schema.md`**. Collect digests (the distilled material), not raw papers. Send independent agents in one batch so they run concurrently. Stay within the topic: every agent reads only files under this topic's `corpus/papers/`.

### Phase 3 — Synthesize the topic site
Write the multi-page topic site into `docs/<slug>/`, following **`reference/site-structure.md`** and **`reference/provenance-conventions.md`**. Use **`assets/page-template.html`** as the per-page skeleton.

Non-negotiables, because they are what make the artifact trustworthy:
- **Build `docs/<slug>/corpus.html` first.** Every citation chip in the topic resolves to an anchor there; the bibliography is the provenance backbone. Each entry links to the paper on **arXiv** (or its canonical URL for lab writeups).
- **Every sourced claim carries a citation chip** → `corpus.html#p-<dashed-id>` (e.g. `2601.20404` → `#p-2601-20404`). Non-arXiv sources get stable letter-slug anchors (e.g. `#p-anthropic-ctx`).
- **Separate findings from inference.** Paper findings are cited and tagged (Empirical / Theory / Proposal / Definition); your own synthesis goes in amber "inference" callouts, never dressed up as a paper's claim.
- **Adapt the thematic pages to *this* corpus's themes** — don't force another topic's section names.
- **Link the shared stylesheet as `../styles.css`** and add the `../index.html` "↑ All SotA" up-link in the nav.
- **Label a deep dive as one.** If `mode == "deep-dive"`, make it visible: a "Deep dive" kicker/badge on the Overview, a **References** role group in `corpus.html` (the harvested refs as `role ref` entries), an explicit count ("includes N harvested references"), and a "Deep dive" marker on the hub card. A `mode == "review"` topic shows only its main sources and is labelled a review.

Then **regenerate the hub** `docs/index.html`: add/refresh this topic's card and nav link so the landing reflects every topic present under `docs/`.

### Phase 4 — Verify before publishing
Run the hub-aware checker against the published root:
```bash
scripts/verify_site.sh docs
```
It recurses every `docs/<slug>/`, confirms each topic's chips resolve to its own `corpus.html`, that internal links and the `../styles.css` / `../index.html` up-links resolve, that the hub's topic links exist, filenames are lowercase, and every page links the stylesheet + has a nav. Fix anything it flags. A dead citation chip defeats the entire point.

### Phase 5 — Publish to GitHub Pages
**Gate:** confirm public publishing with the user (outward-facing and effectively permanent once indexed). Confirm the hub repo name.

Run the bundled publisher from the **repo root** (it commits + pushes the repo, creates it on first run, and ensures Pages serves `main` `/docs`):
```bash
scripts/publish_pages.sh <hub-repo-root> [repo-name]
```
See **`reference/publish-runbook.md`** for the step-by-step, the manual fallback, and the Pages gotchas (`.nojekyll` inside `docs/`, `/docs` source, relative links, public exposure). Report the live hub URL and the new topic URL `https://<user>.github.io/<repo>/<slug>/`.

## Versioning (`-v2`, `-v3`)
A new version is a **new topic slug** in the same hub (e.g. `agent-memory-v2`): new corpus, read fresh, new `docs/<slug>/`, added to the hub landing. Do **not** import the previous version's papers, digests, or text. Cross-references between versions are added only if the user asks.

## Dependencies & environment
- **Required:** `git`, `gh` (authenticated — check `gh auth status`), `curl`, `tar`, `python3`, and a `bash`/`zsh` shell. Scripts run under macOS's bash 3.2.
- **Optional:** `monolith` (`brew install monolith`) — for the HTML fallback / fetching lab writeups. PDF-only papers are read with the `pdf` skill or the Read tool's `pages` parameter.
- If `gh` is not authenticated, stop before Phase 5 and tell the user to run `gh auth login`. Deleting/retiring repos needs the `delete_repo` scope (`gh auth refresh -h github.com -s delete_repo`).

## Honesty guardrails (carry these into the writing)
- Preserve exact numbers, effect sizes, and p-values from the digests; never invent figures or authors. If a source did not state something (a venue, a date), say so.
- Distinguish a paper's **primary** results from numbers it merely **cites** from other work — the latter are not that paper's evidence.
- Where evidence is thin (small-N, single-repo, observational, unvalidated position paper), say so plainly. An honest "indicative, not strong" reads better than false confidence and is the whole reason a reader trusts the site.
