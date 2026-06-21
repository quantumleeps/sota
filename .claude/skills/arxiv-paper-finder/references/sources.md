# Source APIs — details and quirks

All endpoints are public and keyless (S2 optionally takes a key). Read this when
debugging fetches, adding a source, or explaining coverage gaps to the user.

## arXiv API
- Endpoint: `http://export.arxiv.org/api/query`
- Returns Atom XML. We parse with ElementTree (namespace `http://www.w3.org/2005/Atom`).
- Sort by `submittedDate desc` to bias toward recent.
- Etiquette: ~3 seconds between requests (the fetcher sleeps 3s). Don't parallelize hard.
- Best source for: authoritative abstracts, exact submission dates, author lists.
- Categories worth targeting in queries: cs.AI, cs.CL, cs.LG, cs.MA, cs.NE.

## Semantic Scholar (S2) Graph API — KEY-GATED
- Endpoint: `GET /graph/v1/paper/search` (Academic Graph). Fields: title, abstract, citationCount, influentialCitationCount, externalIds, publicationDate, year, authors, url.
- **The keyless tier is now effectively dead** — the shared global pool returns instant `429 Too Many Requests` (verified; no `Retry-After`), so backoff/spacing can't recover it. The fetcher therefore **skips S2 unless `S2_API_KEY` is set**.
- With a key it's a *bonus* citation source (counts run higher/faster than OpenAlex). Requests use exponential backoff honoring `Retry-After` (a condition of the S2 key terms).
- We no longer need its relevance-rank proxy — local embeddings (fastembed) replaced it.

## OpenAlex — primary (keyless) citation source
- Search endpoint: `https://api.openalex.org/works?search=...` (always pass `mailto=` for the polite pool).
- **Citation backfill (the main use):** look up the whole pool by arXiv DOI — `works?filter=doi:10.48550/arxiv.<id>|<id2>|…` (batch ≤50, `select=doi,cited_by_count,publication_date`). Keyless, reliable, and indexes even fresh papers; restores citation coverage to ~94% where keyless S2 gave ~2%.
- Counts run lower/laggier than S2 (conservative on preprint→preprint edges) — fine at a low citation weight.

## Papers with Code — RETIRED (do not use)
- Meta sunset Papers with Code on ~2025-07-24; `paperswithcode.com` now redirects to HF Trending Papers and the API serves redirects/5xx, not JSON. The `paperswithcode/paperswithcode-data` GitHub archive is frozen at mid-2025 (useless for new papers).
- There is **no keyless paper→GitHub-stars source** anymore. The code signal was reworked (below).

## Code signal (replaces Papers with Code)
- **`has_code` (keyless, default):** scan each paper's **abstract + arXiv `<comment>`** for a `github.com`/`gitlab.com` repo URL (regex). Authors routinely write "Code: https://github.com/…" there. Sets `has_code=True` and `code_url`. This recovers the *linkage* PwC used to provide, from the authors' own text.
- **Real stars (`--gh-stars`, opt-in, local-only):** for papers with a `code_url`, resolve `owner/repo` and call `gh api repos/{owner}/{repo} --jq .stargazers_count`. No fuzzy search (the URL is authoritative), so no wrong-repo risk. Needs an authed `gh`; not portable to CI/containers — hence opt-in.
- For a recency-skewed search, stars are ~0 for the freshest papers, so the boolean usually carries more signal than the count.

## arXiv backfill (recall) + dual-sort
- After merging, thin records (esp. HF-only, which arrive title-only) are backfilled in batch via `http://export.arxiv.org/api/query?id_list=id1,id2,…` (≤100 ids/call, 3s between). Fills abstract/date/authors/comment so relevance+recency work for ~every paper, and lets code detection run on the fetched abstract. Biggest quality lever.
- arXiv is queried twice per query (`sortBy=submittedDate` and `sortBy=relevance`) so relevant-but-not-newest papers aren't crowded out of the date-sorted window.

## Hugging Face Papers
- Search: `https://huggingface.co/api/papers/search?q=...`
- Daily list (alt): `https://huggingface.co/api/daily_papers`
- Gives: community `upvotes` keyed to arXiv ids.
- Best source for: social-buzz signal. Coverage skews to LLM/agent/vision trending work.
- Response shape varies; the fetcher tolerates both list and `{papers:[...]}` forms.

## Dedup strategy
- Primary key: arXiv id (parsed via regex `\d{4}.\d{4,5}`).
- Fallback key: normalized title (lowercased, alphanumerics only).
- On merge, scalar signals take the max across sources; first non-empty wins for text fields.

## Adding a new source
1. Write `fetch_<name>(queries, max_per_source) -> {key: record}` returning `blank()` records.
2. Populate whatever signals it provides; leave others None.
3. Register it in the `fns` dict and the `--sources` default in `fetch_papers.py`.
4. If it introduces a new signal, add a column in `rank_papers.py` and a `--w-<signal>` flag.
