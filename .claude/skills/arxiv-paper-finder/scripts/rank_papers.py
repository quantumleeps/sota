#!/usr/bin/env python3
"""Score and rank a candidate pool with user-weighted signals.

Signals (each normalized to 0..1 across the pool):
  relevance  - semantic match of title+abstract to the topic. Uses local ONNX
               embeddings (fastembed, keyless) if available; falls back to
               sentence-transformers, then BM25. Blended with S2's rank proxy.
  recency    - exponential decay on age (half-life default 120d; we skew NEW).
  citations  - blend of citation count (log-scaled) and velocity (cites/age).
  code       - has-linked-code (boolean from an author repo URL), or real star
               counts if the fetcher was run with --gh-stars.
  social     - HF upvotes (log-scaled) — an EARLY buzz signal that works on fresh work.

A relevance floor (--min-relevance) drops off-topic papers before ranking.
Deterministic given the same pool + weights, so rankings are reproducible.
"""
import argparse, json, math, re, sys
from datetime import datetime, timezone

WORD = re.compile(r"[a-z0-9]+")


def tok(s):
    return WORD.findall((s or "").lower())


def age_days(published):
    if not published:
        return None
    try:
        d = datetime.fromisoformat(published[:10]).replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)
    except Exception:
        return None


# ---------- relevance ----------
def bm25_scores(topic, docs, k1=1.5, b=0.75):
    corpus = [tok(d) for d in docs]
    N = len(corpus)
    if N == 0:
        return []
    avgdl = sum(len(c) for c in corpus) / N or 1.0
    df = {}
    for c in corpus:
        for t in set(c):
            df[t] = df.get(t, 0) + 1
    q = tok(topic)
    scores = []
    for c in corpus:
        tf = {}
        for t in c:
            tf[t] = tf.get(t, 0) + 1
        dl = len(c) or 1
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def embed_scores(topic, docs):
    """Cosine sim of topic vs each doc using local ONNX embeddings.

    Tries fastembed (keyless, ONNX, no torch) first, then sentence-transformers.
    Returns (scores, method) or (None, None) to signal BM25 fallback.
    """
    # fastembed — preferred (lightweight, keyless). bge is a RETRIEVAL model, so
    # embed the topic as a query (instruction-prefixed) and docs as passages —
    # this sharpens the on/off-topic separation that a symmetric embed mushes.
    try:
        from fastembed import TextEmbedding
        import numpy as np
        model = TextEmbedding("BAAI/bge-small-en-v1.5")
        try:
            qv = list(model.query_embed([topic]))[0]
            dv = list(model.passage_embed(docs))
        except Exception:
            vv = list(model.embed([topic] + docs))
            qv, dv = vv[0], vv[1:]
        q = np.array(qv, dtype="float32"); D = np.array(dv, dtype="float32")
        q /= (np.linalg.norm(q) + 1e-9)
        D /= (np.linalg.norm(D, axis=1, keepdims=True) + 1e-9)
        sims = (D @ q).tolist()
        return sims, "fastembed:bge-small"
    except Exception as e:
        sys.stderr.write(f"[rank] fastembed unavailable ({e!r}); trying sentence-transformers\n")
    # sentence-transformers — secondary
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode([topic] + docs, convert_to_tensor=True, normalize_embeddings=True)
        return util.cos_sim(emb[0:1], emb[1:]).tolist()[0], "sentence-transformers:MiniLM"
    except Exception:
        return None, None


def normalize(xs):
    vals = [x for x in xs if x is not None]
    if not vals:
        return [0.0 for _ in xs]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return [0.5 if x is not None else 0.0 for x in xs]
    return [((x - lo) / (hi - lo)) if x is not None else 0.0 for x in xs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--n", type=int, default=10)
    # recency-leaning defaults: a fast field rewards NEW + on-topic over well-cited.
    # Citations are deliberately light — new papers on new topics have few by
    # construction, so a low count is expected, not a quality signal.
    ap.add_argument("--w-relevance", type=float, default=0.40)
    ap.add_argument("--w-recency", type=float, default=0.35)
    ap.add_argument("--w-citations", type=float, default=0.05)
    ap.add_argument("--w-code", type=float, default=0.05)
    ap.add_argument("--w-social", type=float, default=0.15)
    ap.add_argument("--half-life-days", type=float, default=120.0,
                    help="recency decay half-life (shorter = newer-skewed)")
    ap.add_argument("--min-relevance", type=float, default=0.0,
                    help="drop this BOTTOM FRACTION by relevance before ranking "
                         "(e.g. 0.10 = least-relevant 10%%). A fraction, not a cosine "
                         "cutoff: embedding spaces compress similarity, so a fixed "
                         "threshold can't cleanly separate borderline off-topic. "
                         "BM25 always also drops zero-overlap papers. 0 = off.")
    ap.add_argument("--out", default="/tmp/ranked.json")
    ap.add_argument("--emit-list", default=None,
                    help="also write the top-N as a sota-site-ready papers.txt "
                         "(one `<arxiv-id>  # <title>` per line)")
    args = ap.parse_args()

    pool = json.load(open(args.pool))
    papers = pool.get("papers", [])
    if not papers:
        json.dump({"topic": args.topic, "results": [], "note": "empty pool"},
                  open(args.out, "w"), indent=2)
        print("Empty pool — nothing to rank.")
        return

    docs = [f"{p.get('title','')}. {p.get('abstract','')}" for p in papers]

    # --- relevance: local embeddings (fastembed) else BM25 ---
    sys.stderr.write(f"[rank] scoring relevance for {len(docs)} papers "
                     f"(first run downloads a ~30MB model)...\n"); sys.stderr.flush()
    local_raw, method = embed_scores(args.topic, docs)
    if local_raw is None:
        local_raw, method = bm25_scores(args.topic, docs), "bm25"
    sys.stderr.write(f"[rank] relevance via {method}\n")
    if method == "bm25":
        sys.stderr.write("[rank] NOTE: BM25 fallback (title-mostly). `pip install -r "
                         "requirements.txt` (fastembed) for embedding-quality relevance.\n")

    # --- relevance floor: drop off-topic before ranking ---
    # Embedding spaces compress similarity (even unrelated docs score high), so a
    # fixed cosine cutoff can't separate borderline off-topic — we use a PERCENTILE
    # floor (drop the least-relevant fraction) plus BM25's free zero-overlap drop.
    # The main off-topic defense is the embedding ranking itself.
    dropped = 0
    keep = list(range(len(papers)))
    if method == "bm25":
        keep = [i for i in keep if local_raw[i] > 0]            # no term overlap = off-topic
    if args.min_relevance > 0:
        order = sorted(keep, key=lambda i: local_raw[i])       # ascending relevance
        drop = set(order[: int(len(order) * args.min_relevance)])
        keep = [i for i in keep if i not in drop]
    if len(keep) != len(papers):
        dropped = len(papers) - len(keep)
        papers = [papers[i] for i in keep]
        local_raw = [local_raw[i] for i in keep]
        docs = [docs[i] for i in keep]
    if not papers:
        print(f"All {dropped} candidates fell below --min-relevance {args.min_relevance}; nothing to rank.")
        json.dump({"topic": args.topic, "results": [], "note": "all below floor"},
                  open(args.out, "w"), indent=2)
        return

    local_n = normalize(local_raw)
    s2_n = normalize([p.get("s2_relevance") for p in papers])
    relevance = [0.7 * a + 0.3 * b for a, b in zip(local_n, s2_n)]

    # recency: exponential decay; undated -> neutral 0.5
    rec = []
    for p in papers:
        a = age_days(p.get("published"))
        rec.append(0.5 if a is None else 0.5 ** (a / args.half_life_days))

    # citations: blend log-count and velocity
    cites_log = [math.log1p(p.get("citations") or 0) for p in papers]
    vel = []
    for p in papers:
        a = age_days(p.get("published"))
        c = p.get("citations") or 0
        vel.append((c / (a / 30.0)) if (a and a > 0) else 0.0)
    cit = [0.6 * a + 0.4 * b for a, b in zip(normalize(cites_log), normalize(vel))]

    # code: real star counts if the fetcher resolved any (--gh-stars), else the
    # keyless has-linked-code boolean (1 if an author repo URL was found, else 0).
    any_stars = any(p.get("code_stars") for p in papers)
    if any_stars:
        code = normalize([math.log1p(p.get("code_stars") or 0) for p in papers])
        code_mode = "stars"
    else:
        code = [1.0 if p.get("has_code") else 0.0 for p in papers]
        code_mode = "has-code"

    # social: log upvotes
    social = normalize([math.log1p(p.get("hf_upvotes") or 0) for p in papers])

    W = {"relevance": args.w_relevance, "recency": args.w_recency,
         "citations": args.w_citations, "code": args.w_code, "social": args.w_social}
    wsum = sum(abs(v) for v in W.values()) or 1.0
    Wn = {k: v / wsum for k, v in W.items()}

    scored = []
    for i, p in enumerate(papers):
        comp = {"relevance": relevance[i], "recency": rec[i], "citations": cit[i],
                "code": code[i], "social": social[i]}
        total = sum(Wn[k] * comp[k] for k in Wn)
        scored.append({
            "title": p.get("title"), "arxiv_id": p.get("arxiv_id"), "url": p.get("url"),
            "published": p.get("published"), "authors": p.get("authors") or [],
            "citations": p.get("citations"), "influential_citations": p.get("influential_citations"),
            "has_code": p.get("has_code"), "code_url": p.get("code_url"), "code_stars": p.get("code_stars"),
            "hf_upvotes": p.get("hf_upvotes"), "sources": p.get("sources"),
            "score": round(total, 4), "components": {k: round(v, 3) for k, v in comp.items()},
        })

    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:args.n]
    json.dump({"topic": args.topic, "weights": Wn, "relevance_method": method,
               "code_mode": code_mode, "pool_size": len(papers), "dropped_below_floor": dropped,
               "returned": len(top), "results": top}, open(args.out, "w"), indent=2)

    # handoff artifact: a sota-site-ready papers.txt of the shortlist
    if args.emit_list:
        with open(args.emit_list, "w") as f:
            f.write(f"# top {len(top)} for '{args.topic}' — feed to /sota-site (trim/curate first)\n")
            for r in top:
                if r.get("arxiv_id"):
                    f.write(f"{r['arxiv_id']}  # {r.get('title','')}\n")
        n_ids = sum(1 for r in top if r.get("arxiv_id"))
        sys.stderr.write(f"[rank] wrote {n_ids} ids -> {args.emit_list}  (papers.txt for /sota-site)\n")

    print(f"\nTopic: {args.topic}")
    print(f"Pool: {len(papers)} candidates"
          + (f" ({dropped} dropped below floor {args.min_relevance})" if dropped else "")
          + f" -> top {len(top)}")
    print(f"Relevance: {method} · code: {code_mode} · half-life {args.half_life_days:.0f}d")
    print("Weights: " + ", ".join(f"{k} {v:.2f}" for k, v in Wn.items()) + "\n")
    for rank, r in enumerate(top, 1):
        au = ", ".join(r["authors"][:3]) + (" et al." if len(r["authors"]) > 3 else "")
        c = r["components"]
        if r.get("code_stars"):
            codestr = f"★{r['code_stars']}"
        elif r.get("has_code"):
            codestr = "code✓"
        else:
            codestr = "code-"
        line2 = (f"   rel {c['relevance']:.2f} · rec {c['recency']:.2f} · "
                 f"cite {r['citations'] if r['citations'] is not None else '?'} ({c['citations']:.2f}) · "
                 f"{codestr} · HF▲ {r['hf_upvotes'] if r['hf_upvotes'] is not None else '-'}  [score {r['score']:.3f}]")
        date = (r["published"] or "n/a")[:7]
        print(f"{rank}. {r['title']}  ({r['arxiv_id'] or 'no-id'}, {date})")
        if au:
            print(f"   {au}")
        print(line2)
        if r["url"]:
            print(f"   {r['url']}")
        print()


if __name__ == "__main__":
    main()
