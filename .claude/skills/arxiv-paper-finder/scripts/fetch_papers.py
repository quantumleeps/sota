#!/usr/bin/env python3
"""Fetch a candidate superset of papers from multiple scholarly APIs.

Queries arXiv (date- AND relevance-sorted), Semantic Scholar, OpenAlex, and
Hugging Face Papers, deduplicates by arXiv id / normalized title, merges signals,
backfills thin records via an arXiv id_list lookup, and writes one JSON pool.
Resilient: a failing source is logged and skipped. No API keys required.

Code signal: Papers-with-Code was sunset (Meta, Jul 2025), so there is no keyless
star source anymore. Instead we detect an author-linked repo (github/gitlab URL in
the abstract or arXiv comment) -> `has_code`/`code_url`. With --gh-stars, an authed
`gh` resolves the real star count for that exact repo (local-only, opt-in).
"""
import argparse, json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

UA = "arxiv-paper-finder/1.0 (mailto:research@example.com)"
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
CODE_URL_RE = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", re.I)
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def log(m):
    """Progress to stderr, flushed so it streams during long runs (non-tty)."""
    sys.stderr.write(m + "\n"); sys.stderr.flush()


def _get(url, headers=None, timeout=30, retries=4, backoff=2.0):
    headers = headers or {}
    headers.setdefault("User-Agent", UA)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 or 500 <= e.code < 600:
                # EXPONENTIAL backoff, honoring Retry-After when the server sends it
                ra = e.headers.get("Retry-After") if e.headers else None
                delay = float(ra) if (ra and str(ra).isdigit()) else backoff * (2 ** attempt)
                time.sleep(min(delay, 60)); continue
            raise
        except Exception as e:  # noqa
            last = e
            time.sleep(backoff * (2 ** attempt))
    raise last


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def extract_arxiv_id(s):
    if not s:
        return None
    m = ARXIV_ID_RE.search(s)
    return m.group(1) if m else None


def detect_code(*texts):
    """Return the first github/gitlab repo URL found in any of the texts, else None."""
    for t in texts:
        if not t:
            continue
        m = CODE_URL_RE.search(t)
        if m:
            return m.group(0).rstrip(").,;")
    return None


def blank(arxiv_id=None, title=None):
    return {
        "arxiv_id": arxiv_id, "title": title, "abstract": None, "authors": [],
        "published": None, "url": None, "comment": None,
        "citations": None, "influential_citations": None, "s2_relevance": None,
        "has_code": None, "code_url": None, "code_stars": None,
        "hf_upvotes": None, "sources": [],
    }


def _set_code(rec, *texts):
    url = detect_code(*texts)
    if url:
        rec["has_code"] = True
        rec["code_url"] = rec["code_url"] or url


# ---------------- arXiv (date- and relevance-sorted) ----------------
def fetch_arxiv(queries, max_per_source):
    out = {}
    total = len(queries) * 2
    i = 0
    log(f"[arxiv] {total} calls ({len(queries)} queries × date+relevance, ~3s each)")
    for q in queries:
        for sort_by in ("submittedDate", "relevance"):   # recency AND relevance recall
            i += 1
            url = ("http://export.arxiv.org/api/query?"
                   + urllib.parse.urlencode({
                       "search_query": f"all:{q}", "start": 0, "max_results": max_per_source,
                       "sortBy": sort_by, "sortOrder": "descending"}))
            try:
                root = ET.fromstring(_get(url))
            except Exception:
                log(f"  [arxiv {i}/{total}] '{q[:36]}' [{sort_by[:4]}] FAILED"); time.sleep(3); continue
            n0 = len(out)
            for e in root.findall("a:entry", NS):
                aid = extract_arxiv_id(e.findtext("a:id", "", NS) or "")
                if not aid:
                    continue
                rec = out.get(aid) or blank(arxiv_id=aid)
                rec["title"] = " ".join((e.findtext("a:title", "", NS) or "").split())
                rec["abstract"] = " ".join((e.findtext("a:summary", "", NS) or "").split())
                rec["published"] = (e.findtext("a:published", "", NS) or "")[:10] or None
                rec["url"] = f"https://arxiv.org/abs/{aid}"
                rec["comment"] = (e.findtext("arxiv:comment", "", NS) or "").strip() or None
                rec["authors"] = [a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)]
                _set_code(rec, rec["abstract"], rec["comment"])
                if "arxiv" not in rec["sources"]:
                    rec["sources"].append("arxiv")
                out[aid] = rec
            log(f"  [arxiv {i}/{total}] '{q[:36]}' [{sort_by[:4]}] +{len(out)-n0} new (pool {len(out)})")
            time.sleep(3)
    return out


# ---------------- Semantic Scholar ----------------
def fetch_s2(queries, max_per_source):
    out = {}
    headers = {"x-api-key": os.environ["S2_API_KEY"]} if os.environ.get("S2_API_KEY") else {}
    fields = "title,abstract,year,publicationDate,citationCount,influentialCitationCount,externalIds,authors,url"
    for q in queries:
        url = ("https://api.semanticscholar.org/graph/v1/paper/search?"
               + urllib.parse.urlencode({"query": q, "limit": max_per_source, "fields": fields}))
        try:
            data = json.loads(_get(url, headers=headers))
        except Exception:
            time.sleep(2); continue
        papers = data.get("data", []) or []
        n = len(papers)
        for rank, p in enumerate(papers):
            aid = extract_arxiv_id((p.get("externalIds") or {}).get("ArXiv") or "")
            key = aid or ("s2:" + norm_title(p.get("title")))
            rec = out.get(key) or blank(arxiv_id=aid, title=p.get("title"))
            rec["title"] = rec["title"] or p.get("title")
            rec["abstract"] = rec["abstract"] or p.get("abstract")
            rec["published"] = rec["published"] or p.get("publicationDate") or (
                f"{p.get('year')}-01-01" if p.get("year") else None)
            rec["citations"] = p.get("citationCount")
            rec["influential_citations"] = p.get("influentialCitationCount")
            rel = 1.0 - (rank / max(1, n - 1)) if n > 1 else 1.0
            rec["s2_relevance"] = max(rec["s2_relevance"] or 0, rel)
            if not rec["authors"]:
                rec["authors"] = [a.get("name") for a in (p.get("authors") or [])]
            if aid and not rec["url"]:
                rec["url"] = f"https://arxiv.org/abs/{aid}"
            elif p.get("url") and not rec["url"]:
                rec["url"] = p.get("url")
            _set_code(rec, p.get("abstract"))
            if "semantic_scholar" not in rec["sources"]:
                rec["sources"].append("semantic_scholar")
            out[key] = rec
        time.sleep(1.2)
    return out


# ---------------- OpenAlex (citation fallback) ----------------
def fetch_openalex(queries, max_per_source):
    out = {}
    for q in queries:
        url = ("https://api.openalex.org/works?"
               + urllib.parse.urlencode({"search": q, "per-page": min(max_per_source, 50),
                                         "mailto": "research@example.com"}))
        try:
            data = json.loads(_get(url))
        except Exception:
            continue
        for w in data.get("results", []) or []:
            loc = (w.get("primary_location") or {})
            aid = extract_arxiv_id(loc.get("landing_page_url") or "") or extract_arxiv_id(w.get("doi") or "")
            title = w.get("display_name") or w.get("title")
            key = aid or ("oa:" + norm_title(title))
            rec = out.get(key) or blank(arxiv_id=aid, title=title)
            rec["title"] = rec["title"] or title
            rec["citations"] = rec["citations"] if rec["citations"] is not None else w.get("cited_by_count")
            rec["published"] = rec["published"] or w.get("publication_date")
            if aid and not rec["url"]:
                rec["url"] = f"https://arxiv.org/abs/{aid}"
            if "openalex" not in rec["sources"]:
                rec["sources"].append("openalex")
            out[key] = rec
        time.sleep(0.5)
    return out


# ---------------- Hugging Face Papers (social) ----------------
def fetch_hf(queries, max_per_source):
    out = {}
    for q in queries:
        url = "https://huggingface.co/api/papers/search?" + urllib.parse.urlencode({"q": q})
        try:
            data = json.loads(_get(url))
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("papers", [])
        for it in items[:max_per_source]:
            p = it.get("paper", it)
            aid = extract_arxiv_id(p.get("id") or p.get("arxivId") or "")
            title = p.get("title")
            key = aid or ("hf:" + norm_title(title))
            rec = out.get(key) or blank(arxiv_id=aid, title=title)
            rec["title"] = rec["title"] or title
            rec["hf_upvotes"] = p.get("upvotes") if p.get("upvotes") is not None else rec["hf_upvotes"]
            if aid and not rec["url"]:
                rec["url"] = f"https://arxiv.org/abs/{aid}"
            if "hf_papers" not in rec["sources"]:
                rec["sources"].append("hf_papers")
            out[key] = rec
        time.sleep(0.4)
    return out


def merge(pools):
    merged = {}
    for pool in pools:
        for _, rec in pool.items():
            key = rec["arxiv_id"] or ("t:" + norm_title(rec["title"]))
            if not key.strip(":"):
                continue
            if key not in merged:
                merged[key] = rec
                continue
            cur = merged[key]
            for f, v in rec.items():
                if f == "sources":
                    for s in v:
                        if s not in cur["sources"]:
                            cur["sources"].append(s)
                elif f == "authors":
                    if not cur.get("authors") and v:
                        cur["authors"] = v
                elif f in ("citations", "code_stars", "hf_upvotes",
                           "influential_citations", "s2_relevance") and v is not None:
                    cur[f] = max(cur.get(f) or 0, v)
                elif v is not None and (cur.get(f) is None or cur.get(f) == ""):
                    cur[f] = v
    return merged


def enrich_arxiv(records):
    """RECALL FIX: many records (esp. HF-only) arrive title-only — no abstract/date.
    Backfill them in batch via the arXiv id_list endpoint so relevance and recency
    have something to work with, and detect code links from the fetched abstract."""
    need = [r for r in records if r.get("arxiv_id") and (not r.get("abstract") or not r.get("published"))]
    if not need:
        return 0
    by_id = {r["arxiv_id"]: r for r in need}
    ids = list(by_id)
    nb = (len(ids) + 99) // 100
    log(f"[enrich] arXiv backfill: {len(ids)} thin records in {nb} batch(es) (~3s each)")
    filled = 0
    for bi, i in enumerate(range(0, len(ids), 100), 1):
        chunk = ids[i:i + 100]
        url = ("http://export.arxiv.org/api/query?"
               + urllib.parse.urlencode({"id_list": ",".join(chunk), "max_results": len(chunk)}))
        try:
            root = ET.fromstring(_get(url))
        except Exception:
            log(f"  [enrich {bi}/{nb}] batch failed"); time.sleep(3); continue
        for e in root.findall("a:entry", NS):
            aid = extract_arxiv_id(e.findtext("a:id", "", NS) or "")
            r = by_id.get(aid)
            if not r:
                continue
            r["title"] = r["title"] or " ".join((e.findtext("a:title", "", NS) or "").split())
            r["abstract"] = r["abstract"] or " ".join((e.findtext("a:summary", "", NS) or "").split()) or None
            r["published"] = r["published"] or (e.findtext("a:published", "", NS) or "")[:10] or None
            r["comment"] = r["comment"] or (e.findtext("arxiv:comment", "", NS) or "").strip() or None
            if not r["authors"]:
                r["authors"] = [a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)]
            if not r.get("url"):
                r["url"] = f"https://arxiv.org/abs/{aid}"
            _set_code(r, r["abstract"], r["comment"])
            filled += 1
        log(f"  [enrich {bi}/{nb}] filled {filled}/{len(ids)}")
        time.sleep(3)
    return filled


def enrich_openalex_citations(records):
    """CITATIONS, keyless: look up cited_by_count by arXiv DOI in OpenAlex batches.
    OpenAlex is reliable and indexes even fresh arXiv papers, unlike the rate-limited
    keyless S2 — so this is the dependable citation source. Counts run lower/laggier
    than S2 (conservative on preprint->preprint edges), which is fine at a low weight."""
    need = [r for r in records if r.get("arxiv_id") and r.get("citations") is None]
    if not need:
        return 0
    by_doi = {f"10.48550/arxiv.{r['arxiv_id'].lower()}": r for r in need}
    dois = list(by_doi)
    nb = (len(dois) + 49) // 50
    log(f"[citations] OpenAlex backfill: {len(dois)} ids in {nb} batch(es)")
    filled = 0
    for bi, i in enumerate(range(0, len(dois), 50), 1):     # OpenAlex OR-filter, 50/call
        chunk = dois[i:i + 50]
        url = ("https://api.openalex.org/works?"
               + urllib.parse.urlencode({
                   "filter": "doi:" + "|".join(chunk), "per-page": 200,
                   "select": "doi,cited_by_count,publication_date",
                   "mailto": "research@example.com"}))
        try:
            data = json.loads(_get(url))
        except Exception:
            log(f"  [citations {bi}/{nb}] batch failed"); continue
        for w in data.get("results", []) or []:
            doi = (w.get("doi") or "").lower().replace("https://doi.org/", "")
            r = by_doi.get(doi)
            if r is None:
                continue
            r["citations"] = w.get("cited_by_count")
            r["published"] = r["published"] or w.get("publication_date")
            filled += 1
        log(f"  [citations {bi}/{nb}] filled {filled}/{len(dois)}")
        time.sleep(0.3)
    return filled


def add_gh_stars(records):
    """OPT-IN: for papers with a detected author repo, resolve the exact repo's star
    count via an authed `gh`. No fuzzy search — we use the authors' own URL."""
    if not shutil.which("gh"):
        sys.stderr.write("[gh-stars] 'gh' not on PATH; skipping star enrichment\n")
        return 0
    n = 0
    for r in records:
        m = re.search(r"github\.com/([^/]+)/([^/#?]+)", r.get("code_url") or "")
        if not m:
            continue
        owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2))
        try:
            out = subprocess.run(["gh", "api", f"repos/{owner}/{repo}", "--jq", ".stargazers_count"],
                                 capture_output=True, text=True, timeout=20)
            if out.returncode == 0 and out.stdout.strip().isdigit():
                r["code_stars"] = int(out.stdout.strip()); n += 1
        except Exception:
            pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--since-months", type=int, default=18)
    ap.add_argument("--max-per-source", type=int, default=50)
    ap.add_argument("--out", default="/tmp/paper_pool.json")
    ap.add_argument("--sources", nargs="+", default=["arxiv", "s2", "openalex", "hf"],
                    help="subset of: arxiv s2 openalex hf  (Papers-with-Code retired)")
    ap.add_argument("--no-enrich", action="store_true", help="skip the arXiv id_list backfill")
    ap.add_argument("--gh-stars", action="store_true",
                    help="resolve real star counts for linked repos via authed `gh` (local-only)")
    args = ap.parse_args()

    fns = {"arxiv": fetch_arxiv, "s2": fetch_s2, "openalex": fetch_openalex, "hf": fetch_hf}
    pools, errors, counts = [], {}, {}
    active = [s for s in args.sources if s in fns]
    log(f"[fetch] {len(active)} sources × {len(args.queries)} queries: {', '.join(active)}")
    for n, name in enumerate(args.sources, 1):
        fn = fns.get(name)
        if not fn:
            continue
        if name == "s2" and not os.environ.get("S2_API_KEY"):
            counts[name] = "skipped"
            log(f"[fetch {n}/{len(args.sources)}] s2 skipped (no S2_API_KEY; keyless tier is rate-limited — citations come from OpenAlex)")
            continue
        try:
            log(f"[fetch {n}/{len(args.sources)}] {name} ...")
            pool = fn(args.queries, args.max_per_source)
            pools.append(pool); counts[name] = len(pool)
            log(f"[fetch {n}/{len(args.sources)}] {name}: {len(pool)} papers")
        except Exception as e:  # noqa
            errors[name] = repr(e); counts[name] = 0
            log(f"[fetch {n}/{len(args.sources)}] {name} FAILED: {e!r}")
    # surface silently-degraded sources (returned nothing without raising an error)
    for name, c in counts.items():
        if c == 0 and name not in errors:
            errors[name] = "returned 0 results (rate-limited or no matches)"
            log(f"[fetch] WARNING: {name} contributed 0 papers")

    merged = merge(pools)
    records = list(merged.values())
    log(f"[merge] {len(records)} unique papers after dedup")

    if not args.no_enrich:
        enrich_arxiv(records)                 # logs its own batch progress
        enrich_openalex_citations(records)    # logs its own batch progress

    if args.gh_stars:
        log("[gh-stars] resolving repo stars via gh ...")
        ns = add_gh_stars(records)
        log(f"[gh-stars] starred {ns} linked repos")

    # recency window (keep undated; they get neutral recency at rank time)
    if args.since_months > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - args.since_months * 30 * 86400
        kept = []
        for r in records:
            d = r.get("published")
            if not d:
                kept.append(r); continue
            try:
                ts = datetime.fromisoformat(d[:10]).replace(tzinfo=timezone.utc).timestamp()
                if ts >= cutoff:
                    kept.append(r)
            except Exception:
                kept.append(r)
        records = kept

    have_code = sum(1 for r in records if r.get("has_code"))
    after_cites = sum(1 for r in records if r.get("citations") is not None)
    result = {
        "query": args.queries, "since_months": args.since_months,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records), "with_linked_code": have_code,
        "_source_counts": counts, "_source_errors": errors, "papers": records,
    }
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    log(f"[done] pool size={len(records)} ({have_code} with linked code, "
        f"{after_cites}/{len(records)} with citations) -> {args.out}")
    if errors:
        log(f"[done] source notes: {errors}")


if __name__ == "__main__":
    main()
