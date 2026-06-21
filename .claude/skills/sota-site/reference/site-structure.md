# Site structure

The blueprint for Phase 3. There is **no fixed page template to force** — the site is *sized to the corpus and the user's ask* (a 1–5 scale, below) and its thematic pages are **wholly derived from this corpus's own sub-topics**. The only constants at every size are the **bibliography with chip-anchors** (the provenance backbone), the **scope line** (this reviews N sources, not the field), and the provenance conventions. Build the bibliography first (everything cites into it), then the body, then the framing once you know the shape.

## Contents
- Size scale (pick first)
- Components (a menu, not a checklist)
- Navigation
- Overview page anatomy
- Evidence page anatomy
- Failure/Limitations page
- Synthesis page
- Corpus (bibliography) page
- File & naming rules

## Size scale (pick first — confirm with the user)

| Size | Shape | Artifacts | When |
|---|---|---|---|
| **1** | single page | 1 | tiny corpus / a quick brief / the user wants one page |
| **2** | brief | 2–3 | small corpus: Overview + Corpus (+ maybe Synthesis) |
| **3** | standard | 4–5 | focused review: Overview + Evidence + Synthesis + Corpus (+1 thematic) |
| **4** | full | 5–7 | Overview + 2–3 corpus-derived thematic pages + Evidence + Failure + Synthesis + Corpus |
| **5** | comprehensive | 6–9 | rich corpus: the full multi-page treatment |

Default to **3–4** unless the user picks a size or the corpus clearly warrants 1 or 5. The driver is the corpus: many papers spanning several distinct sub-themes → larger; a handful on one tight question → smaller. State the chosen size when you confirm scope.

## Components (a menu, not a checklist)

Include components as the size warrants — don't force all of them. Two are **non-negotiable at every size**: the **bibliography** (chip-anchor backbone) and the **scope line**.

- **Overview / thesis** — always. At size 1 it's the head of the single page.
- **Bibliography (corpus)** — always. Inline section at size 1; its own `corpus.html` at size ≥2. Build it first.
- **Thematic pages** — *wholly corpus-derived*: read what THIS corpus is actually about and name pages after its real sub-topics (e.g. codified-context yielded Foundations / Codified Context / Architecture / Security / Adoption — but that was that corpus). 0 at size 1–2, up to ~6 at size 5. Never transplant another topic's section names.
- **Evidence** — ledger of measured effects (size ≥3).
- **Failure / Limitations** — open problems (size ≥4).
- **Synthesis** — your corpus-scoped inference (size ≥3; folded into the single page at size 1).

**Size 1** folds it all into one page: thesis + scope line → key claims → compact evidence → brief amber synthesis → bibliography with `id="p-…"` anchors so chips resolve on-page. **Size 5** is the full flow: Overview → [thematic…] → Evidence → Failure Modes → Synthesis → Corpus. The per-component anatomies below are good defaults *for the components you include* — adapt them to the corpus, don't treat them as mandatory.

## Navigation
(Size 1 has no nav — it's a single page.) At size ≥2, the nav is identical on every page (copy verbatim), brand + one `<a class="nav">` per page that actually exists, in reading order: **Overview → [thematic…] → Evidence → Failure Modes → Synthesis → Corpus** (omit the components your size doesn't include). Mark the current page `class="nav active"`. Generate the nav once, then reuse — `verify_site.sh` will catch any page filename that doesn't exist.

## Overview page anatomy (index.html)
1. `kicker` + `h1` + `lede` stating the **central thesis that emerges across this corpus** (not "the field's" thesis) in plain language.
2. A **scope line** — mandatory, near the top (in the lede or a `.note`): "A review of **N** sources gathered [roughly when]; a reading of *this corpus*, not a complete survey of the field." This is the one-sentence honesty anchor; do not omit it.
3. A 3-card **stats strip** (`grid g3` of `card stat`) with 2–3 headline numbers, each chip-sourced.
4. **The reading convention** (see provenance-conventions §6) so the visual language is legible.
5. **"What recurs across these N papers"** — the 4–6 claims with enough independent support *within this corpus* to count as consensus *here*. Frame them as corpus observations ("across these papers, …"), not field-level verdicts. Each claim: a short paragraph, multiple citation chips, a claim-type tag, and a link to the page that develops it.
6. **Map of the territory** — `grid g2` of `card cardlink` linking each subsequent page with a one-line description.
7. **Timeline** — corpus documents on a line. If you group them into "eras," flag that grouping as your inference (amber note), since the papers don't claim it.

## Evidence page anatomy (evidence.html — use `wrap wide`)
- A **ledger table**: each row = a measured effect (what was measured, result with `.pos`/`.neg`, method & scale, source chip, and a final **"my confidence"** column). The confidence column is YOUR appraisal — open the page with an amber box defining your scale (e.g. Strong / Moderate / Indicative) and stating it is not from the papers.
- Pull the **strongest single result** into a stat strip with its caveats.
- Close with an honest **appraisal** (amber inference) — where the evidence is consistent vs thin — and a grey **gap box** of "what would raise confidence," drawn from the papers' own future-work.
- Keep secondary-cited figures out of the primary ledger (a survey quoting another paper's number is not that survey's evidence) — note them as such if used.

## Failure / Limitations page
Synthesize the digests' "limitations / open problems" into families (e.g. coordination failures, decay, maintenance, security). Use `risk`/`gap` callouts. End with the cross-cutting tension you see (amber).

## Synthesis page (synthesis.html)
Open with a prominent amber banner: this page is entirely your reasoning **across this corpus** — chips mark what you reason from, not agreement, and nothing here is a forecast of where the field is going. Offer a **reference model** that unifies *these papers'* findings and a set of **bets / design principles**, each grounded in (not claimed by) cited work and phrased as "what this corpus suggests," not "where the field is heading." Add a grey "where I'd hold back" box for open bets you would not place. This is where opinion lives — keep it out of the other pages, and keep even the opinion scoped to the corpus.

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
