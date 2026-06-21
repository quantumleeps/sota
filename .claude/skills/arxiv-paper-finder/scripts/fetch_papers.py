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
import argparse, json, os, random, re, shutil, subprocess, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

UA = "arxiv-paper-finder/1.0 (mailto:research@example.com)"
# YYMM.NNNNN — require a valid month (01-12) so DOIs/years like ".../2025.24135"
# (month "25") don't get mis-extracted as arXiv ids and poison dedup/handoff.
ARXIV_ID_RE = re.compile(r"(\d{2}(?:0[1-9]|1[0-2])\.\d{4,5})(v\d+)?")
CODE_URL_RE = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", re.I)
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# arXiv ToU (info.arxiv.org/help/api/tou.html): max 1 request / 3s, single connection
# at a time, and the budget is shared across ALL machines on your egress IP. A 429/503
# OR a silent read-timeout (connection accepted, no body) is a throttle signal — back
# off, and STOP probing: continued probing into the penalty box prolongs it. We pace
# arXiv calls and circuit-break the whole source for the run once it throttles.
ARXIV_MIN_SPACING = 4.0   # seconds between arXiv requests (3s ToU floor + margin)
_ARXIV_THROTTLED = False


class Throttled(Exception):
    """A source rate-limited us past our retries; the caller should stop hitting it."""


def log(m):
    """Progress to stderr, flushed so it streams during long runs (non-tty)."""
    sys.stderr.write(m + "\n"); sys.stderr.flush()


def load_dotenv():
    """Load KEY=value pairs from the nearest .env into os.environ (stdlib-only).

    Walks up from both the cwd and this script's directory so a .env at the
    sota repo root is picked up no matter where the fetcher is invoked from.
    Never overrides a variable already set in the real environment, and quietly
    does nothing if no .env exists — so S2_API_KEY can live in .env OR be
    exported, whichever the user prefers.
    """
    seen = set()
    for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        d = start
        for _ in range(8):  # walk up a bounded number of levels to the repo root
            path = os.path.join(d, ".env")
            if path not in seen and os.path.isfile(path):
                seen.add(path)
                try:
                    with open(path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            if line.startswith("export "):
                                line = line[len("export "):]
                            key, _, val = line.partition("=")
                            key, val = key.strip(), val.strip().strip('"').strip("'")
                            if key and key not in os.environ:
                                os.environ[key] = val
                except OSError:
                    pass
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent


def _get(url, headers=None, timeout=30, retries=5, base=5.0, cap=120.0):
    """Polite GET with full-jitter exponential backoff, per arXiv's rate-limit ToU.

    - 429 / 5xx: honor Retry-After when present (capped at 300s); otherwise sleep
      random.uniform(0, min(cap, base * 2**attempt)). Full jitter avoids synchronized
      retries — important on a shared egress IP where the budget is contended.
    - Read-timeouts / connection errors are treated as throttle signals too: a hung
      arXiv read IS the limiter, not a transient blip, so we back off rather than hammer.
    - After `retries` are exhausted on a retryable failure we raise Throttled so the
      caller can circuit-break the whole source instead of probing into the penalty box.
      A non-retryable HTTP error (e.g. 400/404) raises immediately.
    """
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
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra and str(ra).strip().isdigit():
                    delay = min(float(ra), 300.0)            # honor server's ask
                else:
                    delay = random.uniform(0, min(cap, base * (2 ** attempt)))
                time.sleep(delay); continue
            raise                                            # 4xx (not 429): not retryable
        except Exception as e:  # timeout, URLError, conn reset -> throttle signal
            last = e
            time.sleep(random.uniform(0, min(cap, base * (2 ** attempt))))
    raise Throttled(repr(last) if last else "rate limited")


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
    global _ARXIV_THROTTLED
    out = {}
    total = len(queries) * 2
    i = 0
    consec = 0
    log(f"[arxiv] {total} calls ({len(queries)} queries × date+relevance, {ARXIV_MIN_SPACING:.0f}s spacing)")
    for q in queries:
        for sort_by in ("submittedDate", "relevance"):   # recency AND relevance recall
            i += 1
            url = ("https://export.arxiv.org/api/query?"   # https direct: skip the http->https 301 hop
                   + urllib.parse.urlencode({
                       "search_query": f"all:{q}", "start": 0, "max_results": max_per_source,
                       "sortBy": sort_by, "sortOrder": "descending"}))
            try:
                root = ET.fromstring(_get(url))
            except Throttled as e:
                log(f"  [arxiv {i}/{total}] THROTTLED ({e}) — stopping arXiv for this run")
                _ARXIV_THROTTLED = True
                return out
            except Exception:
                consec += 1
                log(f"  [arxiv {i}/{total}] '{q[:36]}' [{sort_by[:4]}] FAILED ({consec} in a row)")
                if consec >= 3:                            # repeated non-throttle failures ~ throttle too
                    log("  [arxiv] 3 consecutive failures — treating as throttle, stopping arXiv")
                    _ARXIV_THROTTLED = True
                    return out
                time.sleep(ARXIV_MIN_SPACING); continue
            consec = 0
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
            time.sleep(ARXIV_MIN_SPACING)
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


def _oa_abstract(inv):
    """Rebuild plain text from OpenAlex's abstract_inverted_index ({word: [positions]}).

    OpenAlex returns abstracts only in this inverted form. Reconstructing it means the
    pool has real abstract text for relevance ranking even when arXiv (the usual abstract
    source) is throttled — the difference between a strong semantic rank and a title-only one.
    """
    if not inv:
        return None
    pos = sorted((i, w) for w, idxs in inv.items() for i in idxs)
    return " ".join(w for _, w in pos) or None


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
            rec["abstract"] = rec["abstract"] or _oa_abstract(w.get("abstract_inverted_index"))
            rec["citations"] = rec["citations"] if rec["citations"] is not None else w.get("cited_by_count")
            rec["published"] = rec["published"] or w.get("publication_date")
            if not rec["authors"]:
                rec["authors"] = [a.get("author", {}).get("display_name")
                                  for a in (w.get("authorships") or [])] or rec["authors"]
            _set_code(rec, rec["abstract"])
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
    global _ARXIV_THROTTLED
    if _ARXIV_THROTTLED:
        log("[enrich] arXiv was throttled earlier this run — skipping id_list backfill "
            "(OpenAlex abstracts already cover most records)")
        return 0
    need = [r for r in records if r.get("arxiv_id") and (not r.get("abstract") or not r.get("published"))]
    if not need:
        return 0
    by_id = {r["arxiv_id"]: r for r in need}
    ids = list(by_id)
    nb = (len(ids) + 99) // 100
    log(f"[enrich] arXiv backfill: {len(ids)} thin records in {nb} batch(es) ({ARXIV_MIN_SPACING:.0f}s spacing)")
    filled = 0
    for bi, i in enumerate(range(0, len(ids), 100), 1):
        chunk = ids[i:i + 100]
        url = ("https://export.arxiv.org/api/query?"
               + urllib.parse.urlencode({"id_list": ",".join(chunk), "max_results": len(chunk)}))
        try:
            root = ET.fromstring(_get(url))
        except Throttled as e:
            log(f"  [enrich {bi}/{nb}] THROTTLED ({e}) — stopping backfill")
            _ARXIV_THROTTLED = True; break
        except Exception:
            log(f"  [enrich {bi}/{nb}] batch failed"); time.sleep(ARXIV_MIN_SPACING); continue
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
        time.sleep(ARXIV_MIN_SPACING)
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
    load_dotenv()  # pick up S2_API_KEY (etc.) from a .env if present

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
