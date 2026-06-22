---
name: sota-audio
description: >-
  Produce an audio-native version of a SotA topic — a single continuous narration,
  written for the ear, surfaced as a "Listen" page (player + transcript) on the
  topic site, with the spoken MP3 synthesized on demand via Fish Audio or
  ElevenLabs. Designed to run as the FOLLOW-ON to /sota-site in the SAME session,
  while that topic's paper digests and synthesis are still in context, so the
  narration is authored fresh from that understanding rather than scraped back out
  of the HTML. Use whenever the user wants to "make an audio / listenable / podcast
  version of this review", "narrate this topic", "add a Listen page", "turn the
  sota site into audio", or "TTS this review". Authoring the script needs no API
  key; synthesizing audio is an opt-in step.
---

# SotA Audio — an audio-native version of a published topic

This skill gives a `/sota-site` topic an **ear-first** counterpart: one continuous
narration of the review, published as a **`listen.html`** page (embedded player with
**1×–2× playback-speed** controls + full transcript) on the topic site, with the
spoken **MP3** synthesized on demand.

It is the **second half of one pipeline.** Run it right after `/sota-site`, in the
**same session**, so the corpus digests and the synthesis you just wrote are still
in working memory. The narration is then **authored**, not converted — written as
speech from what you understand about the corpus, never by reading the HTML back
out. (The HTML is the sibling artifact; this is its spoken twin.)

## The governing idea: author for the ear, keep the honesty

Two rules sit above everything else:

1. **Write it as speech, from in-context understanding.** A page read aloud verbatim
   sounds robotic and mispronounces its numbers and citations. Compose a fresh
   narration: spoken sentences, numbers and symbols spelled out, citations turned
   into spoken attributions, structure carried by spoken transition cues and
   pauses. Full authoring rules: **`reference/narration-style.md`** — read it first.
2. **Carry the corpus-scoped honesty into audio.** The narration inherits the site's
   load-bearing rules: it is a reading of *this corpus*, not a verdict on the field
   ("across these N sources," never "the field is…"); the synthesis is **spoken-
   flagged as inference**, never dressed up as a finding; exact numbers and
   attributions are preserved. The amber "my inference" callouts become *verbal*
   hand-offs ("here I'm going beyond what the papers claim —").

## Shape (fixed for this hub): one continuous narration

A single flowing listen for the whole topic, with spoken section cues between parts
(this was the chosen shape — not per-chapter files). One narration script → one
transcript → one MP3 → one Listen page. Typical focused review ≈ a 6–12 minute
listen.

## Inputs to collect first

1. **Topic slug** — which existing topic under `docs/<slug>/` to narrate (the one
   you just built, by default).
2. **Synthesize audio now, or transcript-only?** Default: **author the script and
   publish the transcript page now; synthesize the MP3 on demand** (the chosen
   default — keeps every run key-free and cheap). Only do the audio pass when the
   user asks or keys are present.
3. **Provider & voice** — *only if synthesizing now.* Default **Fish Audio `s2-pro`**;
   alternatively ElevenLabs `eleven_multilingual_v2`. Voice id + key from env/`.env`
   (`FISH_API_KEY`/`FISH_VOICE_ID`, `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID`) or
   `--voice`. See **`reference/tts-providers.md`**.
4. **Publish?** Same gate as sota-site — publishing is public and effectively
   permanent. Confirm before pushing.

## Where things live

```
topics-corpora/<slug>/audio/narration.txt   ← the script (WORKING, gitignored)
docs/<slug>/listen.html                      ← PUBLISHED: player + transcript
docs/<slug>/audio/<slug>.mp3                 ← PUBLISHED: the spoken narration (when synthesized)
```

The narration script is working material (gitignored, like the digests); the
transcript rides published inside `listen.html`; the committed MP3 lives under
`docs/<slug>/audio/`.

## Workflow

### Phase A — Author the narration (in-context)
Compose the single continuous narration **from the digests and synthesis already in
context**, following **`reference/narration-style.md`** to the letter (audio-native
writing + the spoken honesty guardrails + the narration.txt contract). Write it to
`topics-corpora/<slug>/audio/narration.txt` (create the dir). Open with the spoken
**scope line** ("a review of N sources…, this corpus, not the field"); flag the
synthesis section verbally as your own inference.

> **Cold-start fallback** (only if invoked in a *fresh* session with the corpus no
> longer in context): reconstruct understanding from `topics-corpora/<slug>/digest/`
> and `docs/<slug>/*.html` + `corpus/papers/index.json` — read the topic's own files
> only, never another topic's. Authoring from a live `/sota-site` context is
> strongly preferred and produces a better narration.

### Phase B — Build the Listen page & wire it in
```bash
python3 .claude/skills/sota-audio/scripts/make_listen_page.py docs/<slug> \
    --narration topics-corpora/<slug>/audio/narration.txt
```
This reuses the topic's own nav/brand/footer, adds a **🎧 Listen** item to the nav
of every page in the topic (idempotent), and writes `listen.html` with the
transcript (verbatim from the script) plus — *only if the MP3 already exists* — the
player. With no MP3 yet it publishes the transcript and a "audio not yet generated"
note, so the page is valid and verify stays green. Then **add a small `🎧 Listen`
link to this topic's card on the hub** `docs/index.html` (one line; the card prose
is bespoke, so edit it by hand).

### Phase C — Verify
```bash
.claude/skills/sota-site/scripts/verify_site.sh docs
```
The shared gate now resolves the audio `src` too. Fix anything it flags.

### Phase D — Synthesize the audio (OPTIONAL — on demand)
Only when the user opts in / keys are set. First preview with no key or spend:
```bash
python3 .claude/skills/sota-audio/scripts/tts_synthesize.py \
    topics-corpora/<slug>/audio/narration.txt --out docs/<slug>/audio/<slug>.mp3 --dry-run
```
Then synthesize (defaults to Fish `s2-pro`), and **rebuild the Listen page** so the
player appears, and re-verify:
```bash
python3 .claude/skills/sota-audio/scripts/tts_synthesize.py \
    topics-corpora/<slug>/audio/narration.txt --out docs/<slug>/audio/<slug>.mp3 --voice "$FISH_VOICE_ID"
python3 .claude/skills/sota-audio/scripts/make_listen_page.py docs/<slug> \
    --narration topics-corpora/<slug>/audio/narration.txt --audio audio/<slug>.mp3
.claude/skills/sota-site/scripts/verify_site.sh docs
```
First synthesis run: `pip install -r .claude/skills/sota-audio/requirements.txt`
(and `brew install ffmpeg` for clean multi-chunk seams). See
**`reference/tts-providers.md`** for providers, knobs, cost, and chunking/stitching.

### Phase E — Publish (gated)
Confirm public publishing, then reuse the sota-site publisher from the repo root:
```bash
.claude/skills/sota-site/scripts/publish_pages.sh <repo-root> [repo-name]
```
Report the new Listen URL: `https://<user>.github.io/<repo>/<slug>/listen.html`.

## Re-running / editing
Re-running is safe and idempotent: editing `narration.txt` and re-running
`make_listen_page.py` rewrites the page and re-uses the existing nav wiring;
re-synthesizing overwrites the MP3 in place. To change the voice or provider, just
re-run Phase D.

## Dependencies
- **Authoring + page build:** Python 3 stdlib only (`make_listen_page.py`).
- **Audio synthesis:** `pip install -r requirements.txt` (`requests`; optional
  `pydub` + `ffmpeg` for clean stitching) and a provider API key + voice id.
- **Verify/publish:** the bundled `sota-site` scripts (already in this repo).
