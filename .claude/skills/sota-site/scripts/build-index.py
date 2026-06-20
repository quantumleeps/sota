#!/usr/bin/env python3
"""Build <corpus>/papers/index.json: a ready-to-ingest manifest of a corpus.

Topic-agnostic. Detects each paper's true entrypoint (the .tex with
\\documentclass, else HTML/clean-text, else PDF) from the filesystem, and reads
an optional per-corpus <corpus>/meta.json for curated titles/roles/relevance and
the anchor id. If an anchor is set, parses its .bbl so a fresh session can triage
references by title without opening each one. Handles non-arXiv "web" sources
(lab writeups fetched as HTML/clean text). Idempotent.

Usage:
    build-index.py [corpus-dir]      # default: current dir; must contain papers/

meta.json shape (all fields optional):
{
  "topic": "context-engineering",
  "anchor": "2602.20478",                      # arXiv id whose refs/ were harvested, or null
  "papers": { "<arxiv-id>": {"title": "..", "role": "anchor|core|support|ref", "relevance": ".."} },
  "web":    { "<slug>":     {"title": "..", "role": "..", "relevance": "..", "url": "https://.."} }
}
"""
import json, re, sys
from pathlib import Path

CORPUS = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
PAPERS = CORPUS / "papers"
if not PAPERS.is_dir():
    sys.exit(f"error: no papers/ dir under {CORPUS}")

META = {}
_mp = CORPUS / "meta.json"
if _mp.is_file():
    META = json.loads(_mp.read_text())
PAPER_META = META.get("papers", {})
WEB_META = META.get("web", {})
ANCHOR = META.get("anchor")
TOPIC = META.get("topic", CORPUS.parent.name)

ARXIV_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")
DOCCLASS = re.compile(r"\\documentclass")


def rel(p: Path) -> str:
    return p.relative_to(CORPUS).as_posix()


def detect_entry(pdir: Path):
    """Return (format, entrypoint_relpath) for a paper/source directory."""
    texs = sorted(pdir.rglob("*.tex"))
    for t in texs:
        try:
            if DOCCLASS.search(t.read_text(errors="ignore")):
                return "tex", rel(t)
        except OSError:
            pass
    if texs:  # tex present but no \documentclass (e.g. \input-only); use first
        return "tex", rel(texs[0])
    # non-tex: prefer a cleaned-text extraction, then html bundle, then pdf
    for name, fmt in (("clean.txt", "text"),):
        hit = pdir / name
        if hit.is_file():
            return fmt, rel(hit)
    for ext, fmt in ((".html", "html"), (".pdf", "pdf"), (".txt", "text")):
        hits = sorted(pdir.glob(f"*{ext}"))
        if hits:
            return fmt, rel(hits[0])
    return "unknown", ""


def first(pdir: Path, pattern: str):
    hits = sorted(pdir.glob(pattern))
    return rel(hits[0]) if hits else None


def _braced(block: str, start: int) -> str:
    """Extract a brace-balanced group beginning at the '{' index `start`."""
    depth, buf, i = 1, [], start + 1
    while i < len(block) and depth:
        c = block[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        buf.append(c)
        i += 1
    return re.sub(r"\s+", " ", "".join(buf)).strip()


TITLE_MACROS = (r"\showarticletitle{", r"\bibinfo{title}{", r"\bibinfo{booktitle}{")


def parse_bbl_titles(bbl: Path):
    """Map arXiv id -> title by walking each \\bibitem block in a .bbl."""
    text = bbl.read_text(errors="ignore")
    out = {}
    for block in text.split("\\bibitem")[1:]:
        m = (re.search(r"arXiv:([0-9]{4}\.[0-9]{4,5})", block)
             or re.search(r"\\showeprint(?:\[[^\]]*\])?\{([0-9]{4}\.[0-9]{4,5})", block))
        if not m:
            continue
        title = None
        for macro in TITLE_MACROS:
            pos = block.find(macro)
            if pos != -1:
                title = _braced(block, pos + len(macro) - 1).replace("{", "").replace("}", "")
                break
        out[m.group(1)] = title
    return out


def build():
    papers, web = [], []
    for pdir in sorted(p for p in PAPERS.iterdir() if p.is_dir()):
        pid = pdir.name
        fmt, entry = detect_entry(pdir)
        if ARXIV_RE.match(pid):
            m = PAPER_META.get(pid, {})
            refs_dir = pdir / "refs"
            papers.append({
                "id": pid,
                "title": m.get("title"),
                "role": m.get("role", "ref"),
                "format": fmt,
                "read": entry,                       # <- exact insertion point
                "bib": first(pdir, "*.bbl"),
                "refs_dir": rel(refs_dir) if refs_dir.is_dir() else None,
                "abs": f"https://arxiv.org/abs/{pid}",
                "relevance": m.get("relevance"),
            })
        else:
            m = WEB_META.get(pid, {})
            web.append({
                "id": pid,
                "title": m.get("title"),
                "role": m.get("role", "support"),
                "format": fmt,                       # 'text' (clean.txt) or 'html'
                "read": entry,
                "url": m.get("url"),
                "relevance": m.get("relevance"),
            })

    references = None
    if ANCHOR:
        anchor = PAPERS / ANCHOR
        bbl = first(anchor, "*.bbl")
        titles = parse_bbl_titles(CORPUS / bbl) if bbl else {}
        rdir = anchor / "refs"
        items, main_ids = [], set(PAPER_META)
        if rdir.is_dir():
            for d in sorted(p for p in rdir.iterdir() if p.is_dir()):
                fmt, entry = detect_entry(d)
                items.append({
                    "id": d.name,
                    "title": titles.get(d.name),
                    "format": fmt,
                    "read": entry,
                    "also_in_main_corpus": d.name in main_ids,
                })
        references = {"source_paper": ANCHOR, "downloaded_to": f"papers/{ANCHOR}/refs", "items": items}

    # mode: a "deep-dive" included the next level of cited references; a "review"
    # is the main paper set only. Explicit in meta.json, else inferred from refs.
    mode = META.get("mode") or ("deep-dive" if (references and references["items"]) else "review")

    out = {
        "topic": TOPIC,
        "mode": mode,
        "purpose": "Pre-resolved insertion points for ingesting this corpus. Each entry's "
                   "'read' field is the exact file to open first — do not glob or explore.",
        "reading_protocol": [
            "Ingest papers in role order: anchor -> core -> support.",
            "format=tex: read 'read' (the \\documentclass file); follow \\input/\\include and sections/ in order; cited works are in 'bib'.",
            "format=pdf: use the pdf skill to extract text (no TeX/HTML exists for these on arXiv).",
            "format=html: the file is a self-contained monolith bundle; read it directly.",
            "format=text: a cleaned-text extraction of a web source (lab writeup); read it directly; 'url' is the canonical source.",
            "References of the anchor (if any) are under references[].read; triage by title and open only high-value ones.",
        ],
        "counts": {
            "papers": len(papers),
            "web_sources": len(web),
            "with_tex": sum(p["format"] == "tex" for p in papers),
            "pdf_only": sum(p["format"] == "pdf" for p in papers),
            "anchor_refs_downloaded": len(references["items"]) if references else 0,
        },
        "papers": papers,
    }
    if web:
        out["web_sources"] = web
    if references:
        out["references"] = references
    return out


if __name__ == "__main__":
    idx = build()
    out = PAPERS / "index.json"
    out.write_text(json.dumps(idx, indent=2) + "\n")
    print(f"wrote {out}: {idx['counts']}")
