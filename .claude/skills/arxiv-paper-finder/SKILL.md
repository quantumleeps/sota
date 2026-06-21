---
name: arxiv-paper-finder
description: Find the most recent, best-matching arXiv papers for a topic in AI/ML (especially AI-agents subfields like memory, multi-agent orchestration, tool use, planning, RAG, etc.). Use this skill whenever the user wants to discover, rank, or shortlist papers from arXiv by a natural-language description ("find me the best recent papers on X"), pull together a reading list, or surface trending/most-cited/most-starred work in a subfield. Triggers on phrases like "best papers on", "recent arxiv papers", "reading list", "what's hot in", "find papers about", "literature on". The skill gathers a candidate superset from multiple APIs (arXiv, Semantic Scholar, OpenAlex, Papers with Code, Hugging Face Papers), scores each candidate across user-weightable signals (semantic relevance, recency, citation velocity, code popularity, social buzz), and returns the top N. Always use this rather than answering from memory when the user wants current papers, because paper rankings and what exists go stale.
---

# arXiv Paper Finder

Find the top-N arXiv papers matching a natural-language query by gathering a large candidate pool from several scholarly APIs and ranking it with user-controllable signal weights.

## Core idea

The candidate **superset is intentionally larger than N**. Multiple sources each return papers; we dedupe them into one pool, score every paper on several independent signals, combine those scores with weights the user controls, then return the top N. Because the pool is larger than N, the *weights actually change the answer* — that is the point of the tool.

## Setup (first use)
Install the one optional dependency: `pip install -r requirements.txt` (fastembed — local ONNX relevance embeddings, keyless, no torch). Without it the ranker still runs but falls back to BM25 (weaker, title-mostly) and prints a NOTE saying so. First rank downloads a ~30 MB model. Everything else is Python stdlib; no API keys required (set `S2_API_KEY` only if you have one — put it in a `.env` at the sota repo root, which the fetcher auto-loads, or export it; see `.env.example`).

## When to clarify vs. proceed

If the user gave a clear topic, proceed with sensible defaults and state the assumptions inline. Only ask up front if genuinely ambiguous (e.g., no topic, or "papers" with no domain).

Defaults if unspecified: `N=10`, recency window = last 18 months, balanced weights. Tell the user they can re-rank with different weights without re-fetching.

## Workflow

### 1. Parse the request into a query spec
Extract:
- **topic** — the natural-language description (e.g., "cross-agent context, memories and dreaming").
- **N** — how many papers to return (default 10).
- **recency window** — default 18 months; honor "this year", "since 2024", "all-time".
- **weights** — see the signal table below. If the user named priorities ("I care most about citations", "newest first"), translate them into weights. Otherwise use balanced defaults.

### 2. Build keyword variants
LLM-expand the topic into 4–8 query strings: synonyms, the canonical sub-field term, and adjacent phrasings. Example: "cross-agent context, memories and dreaming" →
`["multi-agent memory sharing", "shared memory LLM agents", "agent memory consolidation", "experience replay language agents", "cross-agent knowledge transfer", "agent self-reflection dreaming", "memory architectures autonomous agents"]`.
Pass these to the fetch script. More variants = broader superset.

### 3. Fetch the candidate superset
Run the fetcher. It queries every available source and writes one deduped JSON pool. It is resilient: if a source is down or rate-limited, it logs and continues.

```bash
cd <skill-dir> && python scripts/fetch_papers.py \
  --queries "multi-agent memory sharing" "agent memory consolidation" "cross-agent knowledge transfer" \
  --since-months 18 \
  --max-per-source 50 \
  --out /tmp/paper_pool.json
  # add --gh-stars to resolve real star counts via your authed `gh` (local-only, opt-in)
```

After merging, the fetcher **backfills thin records** (HF-only entries that arrive title-only) via a batch arXiv `id_list` lookup, so relevance and recency have a real abstract+date for ~every paper — this is the single biggest recall/quality lever. arXiv is queried **both date- and relevance-sorted** so strong-but-not-newest matches aren't crowded out.

Sources (see `references/sources.md` for API details and quirks):
- **arXiv API** — authoritative abstracts/dates/authors; queried date- AND relevance-sorted; also the backfill source for thin records.
- **OpenAlex** — the **primary citation source**: keyless, reliable, indexes even fresh arXiv papers; citation counts are backfilled for the whole pool by arXiv DOI (batch).
- **Semantic Scholar (S2)** — **key-gated**: only runs if `S2_API_KEY` is set (the keyless tier is globally rate-limited to ~0 — instant 429s). When keyed, it adds richer citation counts as a bonus. Requests use exponential backoff (honoring `Retry-After`).
- **Hugging Face Papers** — community upvotes (early social-buzz signal).
- **Code signal** — Papers-with-Code was **retired** (Meta, Jul 2025); there is no keyless star source. We instead detect an **author-linked repo** (github/gitlab URL in the abstract or arXiv comment) → `has_code`. With `--gh-stars`, an authed `gh` resolves the exact repo's real `stargazers_count` (no fuzzy search — the URL is the authors' own).

### 4. Score and rank
Run the ranker with the chosen weights. It normalizes each signal to 0–1 across the pool, applies weights, and sorts.

```bash
python scripts/rank_papers.py \
  --pool /tmp/paper_pool.json \
  --topic "cross-agent context, memories and dreaming" \
  --n 10 \
  --out /tmp/ranked.json
  # defaults already skew NEW: rel .40 rec .35 social .15 cite .05 code .05, half-life 120d.
  # override any --w-* to taste; add --min-relevance 0.1 to trim the least-relevant tail.
```

Relevance uses **local ONNX embeddings** (fastembed, `BAAI/bge-small-en-v1.5`, keyless) over title+abstract, embedding the topic as a query and docs as passages; it falls back to sentence-transformers then BM25 if fastembed isn't installed. `--min-relevance F` drops the least-relevant **fraction** before ranking (embedding spaces compress similarity, so a percentile is more reliable than a fixed cosine cutoff; the embedding *ranking* is the main off-topic defense). Defaults skew toward new on purpose — in a fast field a few-months-old paper is already behind.

### 5. Present results
Show a ranked, numbered list. For each paper give: **title** (linked to the arXiv abs page), authors (et al. after 3), date, a one-line why-it-matched, and a compact signal readout so the user sees *why* it ranked where it did:

```
1. Title of Paper  (arXiv:2406.12345, 2024-06)
   Authors A, B, C et al.
   Match: shared episodic memory across agents with periodic consolidation ("dreaming").
   Signals — relevance 0.91 · recency 0.88 · citations 142 (vel 0.6) · stars 1.2k · HF▲ 73
```

Then offer re-ranking: "Want me to re-rank with citations weighted higher, or newest-first? I can do that without re-fetching." Re-ranking just re-runs step 4 on the same pool — cheap and instant.

### 6. (Optional) hand off to a published review
If the user wants to turn the shortlist into a hosted SotA review, re-run the ranker with `--emit-list /tmp/picked.txt` to write a **sota-site-ready `papers.txt`** (`<arxiv-id>  # <title>` per line). Curate/trim it with the user, then invoke **`/sota-site`** with that list as the corpus for a new topic. See the repo `CLAUDE.md` ("discover → review → publish") for the full flow, including the `-v2` slug convention when the topic already exists.

## Signal reference

| Signal | Flag | What it measures | Source |
|---|---|---|---|
| relevance | `--w-relevance` | semantic match of title+abstract to the topic | local ONNX embeddings (fastembed) + S2 rank |
| recency | `--w-recency` | how new the paper is (exponential decay, half-life 120d) | arXiv date |
| citations | `--w-citations` | citation count + velocity (cites/age) | OpenAlex by arXiv DOI (keyless, ~94% coverage); + S2 if keyed |
| code | `--w-code` | author-linked repo (`has_code`); real stars only with `--gh-stars` | abstract/comment URL scan; `gh` |
| social | `--w-social` | community upvotes (early buzz) | HF Papers |

Weights need not sum to 1; the ranker normalizes them. Setting a weight to 0 removes that signal. The **default** (rel .40 rec .35 social .15 cite .05 code .05) skews new — citations are kept light on purpose (new papers have few by construction). Other presets:
- **Established** (`relevance .40 citations .35 recency .15 social .05 code .05`) — proven, well-cited (needs S2 citation coverage; sparser than relevance/recency).
- **Ships-code** (`relevance .40 recency .25 code .15 social .15 citations .05`) — favors work that released a repo. `has_code` is a one-bit signal, so don't over-weight it; pair with `--gh-stars` if you want it to carry more.
- **Newest-first** (`recency .55 relevance .35 social .10`) — pure frontier, lightly relevance-gated.

## Repeatability notes
- The two scripts are deterministic given the same pool and weights, so a saved `paper_pool.json` + a weights string fully reproduces a ranking.
- To refresh, re-run the fetcher; to explore weightings, only re-run the ranker.
- All network access is read-only public APIs; no keys required (S2 works keyless at lower rate limits — set `S2_API_KEY` env var if the user has one).

## Failure handling
- If a source errors, the fetcher records it under `_source_errors` in the pool JSON; mention any that failed so the user knows coverage was partial.
- If the pool is small (< N after dedupe), broaden: add more query variants or widen the recency window, then re-fetch.
- If nothing relevant comes back, say so plainly rather than padding with weak matches.
