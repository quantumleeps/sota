# Site structure

The blueprint for Phase 3. A SotA site has a **fixed spine** of pages that apply to any topic, plus **thematic pages derived from this corpus**. Build `corpus.html` first (everything cites into it), then the thematic pages, then the framing pages (Overview, Synthesis) once you know the final shape.

## Contents
- Page set (spine + thematic)
- Navigation
- Overview page anatomy
- Evidence page anatomy
- Failure/Limitations page
- Synthesis page
- Corpus (bibliography) page
- File & naming rules

## Page set

**Fixed spine (always present):**
| File | Page | Role |
|---|---|---|
| `index.html` | Overview | thesis, "state of the art in N claims", reading convention, map, timeline |
| `evidence.html` | Evidence | ledger of measured effects + honest appraisal |
| `failure-modes.html` | Failure Modes / Limitations | where it breaks; open problems (retitle to suit the topic) |
| `synthesis.html` | Synthesis | wholly your inference: a reference model / your bets |
| `corpus.html` | Corpus | bibliography backbone; every chip resolves here |

**Thematic pages (derive 2–6 from THIS corpus):** group the digests into the natural sub-topics of the field and give each its own page (e.g. for codified-context the themes were Foundations, Codified Context, Architecture, Security, Adoption). Do not transplant another topic's section names — read what the corpus is actually about and name pages accordingly. A small corpus may need only 2–3 thematic pages; a broad one up to ~6.

Aim for ~8–11 pages total. Each idea on a page links to its source via a citation chip.

## Navigation
Identical on every page (copy verbatim), brand + one `<a class="nav">` per page, in reading order: **Overview → [thematic…] → Evidence → Failure Modes → Synthesis → Corpus**. Mark the current page `class="nav active"`. Generate the nav once, then reuse — `verify_site.sh` will catch any page filename that doesn't exist.

## Overview page anatomy (index.html)
1. `kicker` + `h1` + `lede` stating the **central thesis** of the field in plain language.
2. A 3-card **stats strip** (`grid g3` of `card stat`) with 2–3 headline numbers, each chip-sourced.
3. **The reading convention** (see provenance-conventions §6) so the visual language is legible.
4. **"The state of the art in N claims"** — the 4–6 claims that recur across the corpus with enough independent support to count as consensus. Each claim: a short paragraph, multiple citation chips, a claim-type tag, and a link to the page that develops it.
5. **Map of the territory** — `grid g2` of `card cardlink` linking each subsequent page with a one-line description.
6. **Timeline** — corpus documents on a line. If you group them into "eras," flag that grouping as your inference (amber note), since the papers don't claim it.

## Evidence page anatomy (evidence.html — use `wrap wide`)
- A **ledger table**: each row = a measured effect (what was measured, result with `.pos`/`.neg`, method & scale, source chip, and a final **"my confidence"** column). The confidence column is YOUR appraisal — open the page with an amber box defining your scale (e.g. Strong / Moderate / Indicative) and stating it is not from the papers.
- Pull the **strongest single result** into a stat strip with its caveats.
- Close with an honest **appraisal** (amber inference) — where the evidence is consistent vs thin — and a grey **gap box** of "what would raise confidence," drawn from the papers' own future-work.
- Keep secondary-cited figures out of the primary ledger (a survey quoting another paper's number is not that survey's evidence) — note them as such if used.

## Failure / Limitations page
Synthesize the digests' "limitations / open problems" into families (e.g. coordination failures, decay, maintenance, security). Use `risk`/`gap` callouts. End with the cross-cutting tension you see (amber).

## Synthesis page (synthesis.html)
Open with a prominent amber banner: this page is entirely your reasoning across the corpus; chips mark what you reason from, not agreement. Offer a **reference model** that unifies the findings and a set of **bets / design principles**, each grounded in (not claimed by) cited work. Add a grey "where I'd hold back" box for open bets you would not place. This is where opinion lives — keep it out of the other pages.

## Corpus page (corpus.html) — build this first
The provenance backbone. Intro lede explains chips resolve here and link to arXiv. Group entries by role (Anchor → Core → Support → References, or just by relevance for a flat set). Each entry:

```html
<div class="bibentry" id="p-2601-20404">
  <span class="role core">Core</span><span class="bt">Full title</span>
  <div class="meta"><span class="idtag">arXiv:2601.20404</span> · Authors (affil), Year · type · <strong>cite: Author+ '26</strong></div>
  <div class="rel">One-paragraph: what it contributes to the topic.</div>
  <div class="links"><a href="https://arxiv.org/abs/2601.20404" target="_blank" rel="noopener">arXiv abstract ↗</a></div>
</div>
```
- `id="p-<dashed-id>"` is the chip target. The `cite:` label in `.meta` must match the chip label used across the site.
- Role badge classes: `role anchor` / `role core` / `role support` / `role ref`. Include a small legend (`.legend` with `.sw` swatches) up top.
- Link to **arXiv** (`/abs/<id>`). For a published (not local-only) site, do not link local file paths — they 404 on the web.
- `.bibentry` already has `scroll-margin-top` and a `:target` highlight, so chip-jumps land cleanly.

## File & naming rules (hub model)
- The published root is `docs/`. The hub landing is `docs/index.html`; the one shared stylesheet is `docs/styles.css`; topic pages live in `docs/<slug>/*.html`, each with its own `corpus.html`.
- All page files **lowercase** `.html`. Topic pages link the shared stylesheet as **`../styles.css`** and the hub as **`../index.html`** (the "↑ All SotA" up-link) — these two parent links are expected and allowed. No `/absolute` and no other `../` links. `verify_site.sh` enforces this (it recurses topics and verifies chips per-topic).
- `.nojekyll` lives **inside `docs/`** (the served folder), not just the repo root.
- The repo `README.md` (root) documents the hub; content/provenance live in the pages — see the publish runbook.
