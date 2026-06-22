#!/usr/bin/env bash
# verify_site.sh <docs-dir>
# Hub-aware integrity gate for a multi-topic SotA site before publishing.
# Expects the published-root layout:
#   <docs>/index.html        the hub
#   <docs>/styles.css        the one shared stylesheet
#   <docs>/<slug>/*.html     one topic per dir; each has its own corpus.html
# Checks:
#   1. every  corpus.html#p-XXXX  chip resolves to an id in its OWN topic's corpus.html
#   2. every internal *.html link resolves (hub topic links + intra-topic links)
#   3. the two allowed up-links (../styles.css, ../index.html) resolve to the hub
#   4. html filenames are lowercase (GitHub Pages is case-sensitive)
#   5. every page links styles.css and has a .topnav
#   6. no other root-absolute ("/...") or unexpected parent ("../...") links
# Exit 0 = clean; 1 = problems (printed). Needs python3 (already a skill dep).
set -u
SITE="${1:?usage: verify_site.sh <docs-dir>}"
[ -d "$SITE" ] || { echo "error: not a dir: $SITE" >&2; exit 2; }
[ -f "$SITE/index.html" ] || { echo "error: $SITE/index.html (hub) missing" >&2; exit 2; }

python3 - "$SITE" <<'PY'
import os, re, sys, glob
SITE = os.path.abspath(sys.argv[1])
href_re = re.compile(r'(?:href|src)="([^"]+)"')
fail = 0
def err(m):
    global fail; fail += 1; print("  [FAIL]", m)

print(f"== verifying {SITE} ==")

topics = sorted(d for d in os.listdir(SITE)
                if os.path.isdir(os.path.join(SITE, d))
                and os.path.isfile(os.path.join(SITE, d, "index.html")))
if not topics:
    err("no topic dirs (subdirs with an index.html) found under the docs root")
print(f"[..]   topics: {', '.join(topics) or '(none)'}")

if not os.path.isfile(os.path.join(SITE, "styles.css")):
    err("shared styles.css missing at docs root")

def hrefs(path): return href_re.findall(open(path, encoding="utf-8").read())
def is_external(h): return h.startswith(("http://", "https://", "mailto:", "#", "data:"))

for f in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True):
    b = os.path.basename(f)
    if b != b.lower():
        err(f"uppercase in filename (Pages is case-sensitive): {os.path.relpath(f, SITE)}")

# --- hub (index.html at docs root) ---
hub = os.path.join(SITE, "index.html")
hs = open(hub, encoding="utf-8").read()
if "styles.css" not in hs: err("hub index.html: no stylesheet link")
if 'class="topnav"' not in hs: err("hub index.html: no .topnav")
for h in hrefs(hub):
    if is_external(h) or h == "styles.css":
        continue
    m = re.fullmatch(r'([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+\.html)(#[A-Za-z0-9-]+)?', h)
    if m:
        if not os.path.isfile(os.path.join(SITE, m.group(1), m.group(2))):
            err(f"hub: link to missing topic page -> {h}")
    elif re.fullmatch(r'[A-Za-z0-9._-]+\.html(#[A-Za-z0-9-]+)?', h):
        if not os.path.isfile(os.path.join(SITE, h.split('#')[0])):
            err(f"hub: link to missing file -> {h}")
    else:
        err(f"hub: unexpected link (absolute/parent?) -> {h}")

# --- each topic ---
for t in topics:
    tdir = os.path.join(SITE, t)
    pages = sorted(glob.glob(os.path.join(tdir, "*.html")))
    # bibliography anchors live in corpus.html (size >=2) or inline in index.html (size 1)
    bib = os.path.join(tdir, "corpus.html")
    if not os.path.isfile(bib):
        bib = os.path.join(tdir, "index.html")
    anchors = set(re.findall(r'id="(p-[A-Za-z0-9-]+)"', open(bib, encoding="utf-8").read()))
    chips = set()
    for p in pages:
        b = os.path.basename(p)
        s = open(p, encoding="utf-8").read()
        if "styles.css" not in s: err(f"{t}/{b}: no stylesheet link")
        if 'class="topnav"' not in s: err(f"{t}/{b}: no .topnav")
        for h in hrefs(p):
            if h.startswith("#p-"):                          # same-page chip (size-1 inline bib)
                frag = h[1:]; chips.add(frag)
                if frag not in anchors:
                    err(f"{t}/{b}: chip {h} has no anchor in {t}")
                continue
            if is_external(h):
                continue
            if h in ("../styles.css", "../index.html"):
                if not os.path.isfile(os.path.join(SITE, h[3:])):
                    err(f"{t}/{b}: up-link {h} does not resolve")
            elif h.startswith("corpus.html#"):
                frag = h.split("#", 1)[1]; chips.add(frag)
                if frag not in anchors:
                    err(f"{t}/{b}: chip corpus.html#{frag} has no anchor in {t}/corpus.html")
            elif re.fullmatch(r'[A-Za-z0-9._-]+\.html(#[A-Za-z0-9-]+)?', h):
                if not os.path.isfile(os.path.join(tdir, h.split('#')[0])):
                    err(f"{t}/{b}: internal link missing -> {h}")
            elif re.fullmatch(r'[A-Za-z0-9._/-]+\.(mp3|m4a|ogg|oga|wav|png|jpe?g|gif|svg|webp|vtt)', h):
                if not os.path.isfile(os.path.join(tdir, h)):                 # e.g. audio/<slug>.mp3
                    err(f"{t}/{b}: media file missing -> {h}")
            else:
                err(f"{t}/{b}: unexpected link (absolute/parent?) -> {h}")
    print(f"[ok]   {t}: {len(pages)} page(s), {len(anchors)} bib anchors, {len(chips)} chip targets resolve")

print()
print("RESULT: PASS — site is publish-ready" if fail == 0 else f"RESULT: FAIL — {fail} issue(s) above")
sys.exit(1 if fail else 0)
PY
