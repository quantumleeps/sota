#!/usr/bin/env python3
"""make_listen_page.py — build docs/<slug>/listen.html and wire the "Listen" nav link.

Deterministic HTML surgery so the audio page matches the topic site exactly:
it reuses the topic's OWN nav, brand, and footer (read from its index.html), adds
a "🎧 Listen" item to the nav of every page in the topic (idempotent), and renders
the audio page — an embedded player with 1×–2× playback-speed buttons (only if the
MP3 exists) plus the full transcript taken verbatim from the narration script.

    python3 make_listen_page.py docs/<slug> --narration topics-corpora/<slug>/audio/narration.txt \
        [--audio audio/<slug>.mp3] [--title "..."] [--lede "..."]

The transcript is the SAME text the synthesizer speaks, so the page stays a true
transcript. `## heading` lines in the narration become <h2> chapter markers on the
page (they are not spoken). Run with no --audio (or before the MP3 exists) to
publish the transcript now and add the player on a later audio pass.
"""
import argparse
import html
import os
import re
import sys

NAV_ITEM = '<a class="nav" href="listen.html">🎧&nbsp;Listen</a>'

# Playback-speed options for the player (1× up to 2×). Default = 1×.
SPEEDS = [("1", "1×"), ("1.25", "1.25×"), ("1.5", "1.5×"), ("1.75", "1.75×"), ("2", "2×")]

# Scoped to listen.html only — reads the shared palette (var(--…)); never edits styles.css.
SPEED_STYLE = """
<style>
  #sa-audio { width:100%; margin:1.2em 0 .2em; }
  .sa-speed { display:flex; align-items:center; gap:.55em; flex-wrap:wrap; margin:.4em 0 .2em; font-family:var(--sans); }
  .sa-speed > .lbl { font-size:.78rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
  .sa-rates { display:flex; gap:.35em; flex-wrap:wrap; }
  .sa-rates button { font-family:var(--sans); font-size:.85rem; padding:.18em .65em; border:1px solid var(--line);
    border-radius:6px; background:var(--card); color:var(--ink-soft); cursor:pointer; line-height:1.4; }
  .sa-rates button:hover { border-color:var(--accent); color:var(--accent); }
  .sa-rates button[aria-pressed="true"] { background:var(--accent); border-color:var(--accent); color:#fff; }
</style>"""

SPEED_SCRIPT = """
  <script>
  (function () {
    var a = document.getElementById('sa-audio');
    var btns = document.querySelectorAll('.sa-rates button');
    function set(rate, el) {
      a.playbackRate = parseFloat(rate);
      Array.prototype.forEach.call(btns, function (b) {
        b.setAttribute('aria-pressed', b === el ? 'true' : 'false');
      });
    }
    Array.prototype.forEach.call(btns, function (b) {
      b.addEventListener('click', function () { set(b.dataset.rate, b); });
    });
    a.addEventListener('loadedmetadata', function () { a.playbackRate = parseFloat(a.dataset.rate || '1'); });
  })();
  </script>"""
NAV_RE = re.compile(r'(<nav class="topnav">.*?</nav>)', re.S)
BRAND_RE = re.compile(r'<a class="brand"[^>]*>.*?</a>', re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
FOOTER_RE = re.compile(r'<footer class="site">.*?</footer>', re.S)


def inject_nav_item(nav_html):
    """Add the Listen item to a nav block, just before the Corpus link (idempotent)."""
    if 'href="listen.html"' in nav_html:
        return nav_html
    corpus = re.search(r'\s*<a class="nav[^"]*" href="corpus\.html">', nav_html)
    insert = f'\n  {NAV_ITEM}'
    if corpus:
        return nav_html[:corpus.start()] + insert + nav_html[corpus.start():]
    return nav_html.replace("</div></nav>", insert + "\n</div></nav>", 1)


def activate(nav_html, target):
    """Return nav with `target` marked active and every other item de-activated."""
    nav_html = nav_html.replace('class="nav active"', 'class="nav"')
    return re.sub(
        rf'<a class="nav" href="{re.escape(target)}">',
        f'<a class="nav active" href="{target}">',
        nav_html, count=1)


def render_transcript(narration):
    """narration .txt → transcript HTML. `## x` → <h2>; blank-line blocks → <p>."""
    out = []
    for block in re.split(r"\n{2,}", narration.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            out.append(f"  <h2>{html.escape(block[3:].strip())}</h2>")
        else:
            text = html.escape(" ".join(block.split()))
            out.append(f"  <p>{text}</p>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topicdir", help="published topic dir, e.g. docs/<slug>")
    ap.add_argument("--narration", required=True, help="narration .txt script")
    ap.add_argument("--audio", help="relative MP3 path under the topic dir, e.g. audio/<slug>.mp3")
    ap.add_argument("--title", help="page H1 (default: 'Listen — <topic title>')")
    ap.add_argument("--lede", help="standfirst under the H1 (default: a generated one)")
    args = ap.parse_args()

    tdir = args.topicdir.rstrip("/")
    index = os.path.join(tdir, "index.html")
    if not os.path.isfile(index):
        raise SystemExit(f"error: {index} not found — run /sota-site for this topic first.")
    index_html = open(index, encoding="utf-8").read()

    nav_m = NAV_RE.search(index_html)
    brand_m = BRAND_RE.search(index_html)
    if not nav_m or not brand_m:
        raise SystemExit("error: could not locate the .topnav / brand in index.html.")
    base_nav = inject_nav_item(nav_m.group(1))

    title_m = TITLE_RE.search(index_html)
    topic_title = re.sub(r"\s*—.*$", "", html.unescape(title_m.group(1))).strip() if title_m else tdir
    footer_m = FOOTER_RE.search(index_html)
    footer = footer_m.group(0) if footer_m else '<footer class="site">State of the Art</footer>'

    narration = open(args.narration, encoding="utf-8").read()
    spoken = "\n".join(ln for ln in narration.splitlines() if not ln.startswith("## "))
    words = len(spoken.split())
    minutes = max(1, round(words / 150))

    # 1) wire the Listen item into every existing page's nav (idempotent)
    touched = []
    for fn in sorted(os.listdir(tdir)):
        if not fn.endswith(".html") or fn == "listen.html":
            continue
        p = os.path.join(tdir, fn)
        s = open(p, encoding="utf-8").read()
        m = NAV_RE.search(s)
        if not m or 'href="listen.html"' in m.group(1):
            continue
        s = s[:m.start()] + inject_nav_item(m.group(1)) + s[m.end():]
        open(p, "w", encoding="utf-8").write(s)
        touched.append(fn)

    # 2) the player (only when the MP3 is actually present — keeps verify green)
    audio_rel = args.audio
    if not audio_rel:  # autodetect a single mp3 under audio/
        ad = os.path.join(tdir, "audio")
        if os.path.isdir(ad):
            mp3s = sorted(f for f in os.listdir(ad) if f.endswith(".mp3"))
            if mp3s:
                audio_rel = f"audio/{mp3s[0]}"
    have_audio = bool(audio_rel) and os.path.isfile(os.path.join(tdir, audio_rel))
    head_extra = ""
    if have_audio:
        buttons = "\n".join(
            f'      <button type="button" data-rate="{rate}" '
            f'aria-pressed="{"true" if rate == "1" else "false"}">{label}</button>'
            for rate, label in SPEEDS)
        player = (
            f'  <audio id="sa-audio" data-rate="1" controls preload="none" src="{html.escape(audio_rel)}">'
            'Your browser does not support audio playback.</audio>\n'
            '  <div class="sa-speed" role="group" aria-label="Playback speed">\n'
            '    <span class="lbl">Speed</span>\n'
            f'    <div class="sa-rates">\n{buttons}\n    </div>\n'
            '  </div>\n'
            f'  <p class="note">~{minutes} min listen · '
            f'<a href="{html.escape(audio_rel)}" download>download the MP3</a>. '
            f'Single continuous narration; the full transcript is below.</p>'
            f'{SPEED_SCRIPT}')
        head_extra = SPEED_STYLE
    else:
        player = (
            '  <div class="box gap"><p class="box-h">◇ Audio not yet generated</p>'
            f'<p>The ~{minutes}-minute narration script is published below as a transcript. '
            'Run the synthesizer (scripts/tts_synthesize.py) to add the spoken MP3.</p></div>')

    h1 = args.title or f"Listen — {topic_title}"
    lede = args.lede or (
        f"A single continuous, audio-native narration of this review — the same "
        f"corpus-scoped reading as the site, rewritten for the ear. About {minutes} "
        f"minutes. The full transcript follows the player.")

    nav = activate(base_nav, "listen.html")
    transcript = render_transcript(narration)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listen — {html.escape(topic_title)}</title>
<link rel="stylesheet" href="../styles.css">{head_extra}
</head>
<body>
{nav}

<div class="wrap">
  <p class="kicker">🎧 Audio narration</p>
  <h1>{html.escape(h1)}</h1>
  <p class="lede">{html.escape(lede)}</p>

{player}

  <h2>Transcript</h2>
{transcript}

  <div class="pager">
    <a href="index.html">← Overview</a>
    <a href="corpus.html">Corpus →</a>
  </div>
</div>

{footer}
</body>
</html>
"""
    out = os.path.join(tdir, "listen.html")
    open(out, "w", encoding="utf-8").write(page)
    print(f"wrote {out} ({words:,} words, ~{minutes} min, audio={'yes' if have_audio else 'no'})")
    if touched:
        print(f"added 🎧 Listen to nav of: {', '.join(touched)}")
    print("next: run scripts/verify_site.sh docs, then add a 🎧 marker to the hub card if you like.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
