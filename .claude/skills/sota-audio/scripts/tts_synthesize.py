#!/usr/bin/env python3
"""tts_synthesize.py — render a narration script to one MP3 via Fish Audio or ElevenLabs.

On-demand audio for the sota-audio skill. Reads a plain-text narration script
(the audio-native body authored in Phase A), chunks it on sentence/paragraph
boundaries, synthesizes each chunk through a provider behind a single interface,
and stitches the chunks into ONE continuous MP3.

    pip install -r requirements.txt          # requests (+ optional pydub for clean seams)
    python3 tts_synthesize.py narration.txt --out docs/<slug>/audio/<slug>.mp3 \
        --provider fish --voice <voice_id>

Keys + default voices come from the environment or a nearby .env (never override
a real env var):
    FISH_API_KEY / FISH_AUDIO_API_KEY     FISH_VOICE_ID
    ELEVENLABS_API_KEY                    ELEVENLABS_VOICE_ID

--dry-run does the cleaning + chunking + cost estimate but makes NO API call and
needs no key — use it to preview spend and chunk count before committing.

Endpoints/params follow the provider docs as of June 2026 (docs.fish.audio,
elevenlabs.io/docs); confirm against the live docs before a big batch.
"""
import argparse
import os
import re
import sys
import time


# ----------------------------------------------------------------------------- env
def load_dotenv():
    """Load KEY=value pairs from the nearest .env into os.environ (stdlib-only).

    Walks up from both the cwd and this script's dir so a .env at the sota repo
    root is found wherever the script is invoked. Never overrides a real env var.
    """
    seen = set()
    for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        d = start
        for _ in range(8):
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


# ------------------------------------------------------------------------- prepare
SECTION_HEADING = re.compile(r"^\s*##\s+")
# Safety-net symbol expansion. The author should already write audio-native text
# (see reference/narration-style.md); these only catch stragglers.
_SYMBOLS = {
    "%": " percent", "~": "approximately ", "&": " and ",
    "±": " plus or minus ", "≈": " approximately ", "×": " times ",
    "→": " to ", "—": ", ", "–": ", ",
}


def prepare_for_tts(text):
    """Drop transcript-only `## headings`, normalize stray symbols, tidy whitespace.

    `## ...` lines are visual chapter markers for the transcript ONLY — they are
    not spoken, so they are stripped here. Paragraph breaks (blank lines) are
    preserved: the engines read them as a longer pause.
    """
    lines = [ln for ln in text.splitlines() if not SECTION_HEADING.match(ln)]
    text = "\n".join(lines)
    text = re.sub(r"\[\d+\]", "", text)            # stray bracket citations
    text = re.sub(r"https?://\S+", "", text)       # bare URLs
    for k, v in _SYMBOLS.items():
        text = text.replace(k, v)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_SENT = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text, max_chars=1800):
    """Split into <= max_chars chunks on paragraph, then sentence, boundaries.

    Never splits mid-sentence (an audible glitch at the seam). Paragraphs are the
    primary unit; an over-long paragraph is divided on sentence boundaries.
    """
    chunks, buf = [], ""
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 2 <= max_chars:
            buf = f"{buf}\n\n{para}" if buf else para
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(para) <= max_chars:
            buf = para
            continue
        # paragraph itself too long: pack sentences
        for sent in _SENT.split(para):
            sent = sent.strip()
            if not sent:
                continue
            if len(buf) + len(sent) + 1 <= max_chars:
                buf = f"{buf} {sent}" if buf else sent
            else:
                if buf:
                    chunks.append(buf)
                buf = sent
    if buf:
        chunks.append(buf)
    return chunks


# ------------------------------------------------------------------------ providers
class FishProvider:
    """Fish Audio /v1/tts — model in an HTTP header, voice as reference_id."""
    name = "fish"
    base = "https://api.fish.audio/v1/tts"

    def __init__(self, api_key, voice_id, model="s2-pro", speed=1.0, stability=0.55):
        self.api_key, self.voice_id, self.model = api_key, voice_id, model
        self.speed, self.stability = speed, stability

    def synthesize(self, requests, text, prev=None, nxt=None):
        body = {
            "text": text,
            "reference_id": self.voice_id,
            "format": "mp3",
            "mp3_bitrate": 128,
            "normalize": True,
            # ElevenLabs `stability` ↑ = steadier; Fish `temperature` ↓ = steadier.
            "temperature": max(0.0, min(1.0, 1.0 - self.stability + 0.1)),
            "prosody": {"speed": self.speed, "normalize_loudness": True},
            "condition_on_previous_chunks": True,
        }
        r = requests.post(
            self.base,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "model": self.model,
            },
            json=body, timeout=300,
        )
        r.raise_for_status()
        return r.content

    @staticmethod
    def cost_note(total_chars, total_bytes):
        usd = total_bytes / 1_000_000 * 15.0
        return f"~{total_bytes:,} UTF-8 bytes → ~${usd:.3f} (Fish: $15 / 1M bytes)"


class ElevenLabsProvider:
    """ElevenLabs /v1/text-to-speech/{voice} — model in body, voice in the path."""
    name = "elevenlabs"

    def __init__(self, api_key, voice_id, model="eleven_multilingual_v2", speed=1.0, stability=0.55):
        self.api_key, self.voice_id, self.model = api_key, voice_id, model
        self.speed, self.stability = speed, stability

    def synthesize(self, requests, text, prev=None, nxt=None):
        body = {
            "text": text,
            "model_id": self.model,
            "language_code": "en",
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": self.speed,
            },
        }
        if prev:
            body["previous_text"] = prev      # context only — keeps prosody flowing
        if nxt:
            body["next_text"] = nxt
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json=body, timeout=300,
        )
        r.raise_for_status()
        return r.content

    @staticmethod
    def cost_note(total_chars, total_bytes):
        return f"~{total_chars:,} characters (ElevenLabs bills per character, per plan)"


# -------------------------------------------------------------------------- stitch
def stitch(chunks, out_path, gap_ms=400):
    """Concatenate MP3 chunks into one file, with a short silence at each seam.

    Prefers pydub (clean PCM joins + real silence; needs ffmpeg). Falls back to
    raw MP3 byte concatenation — acceptable for spoken MP3, no inter-chunk gap.
    """
    try:
        from io import BytesIO
        from pydub import AudioSegment
        silence = AudioSegment.silent(duration=gap_ms)
        out = AudioSegment.empty()
        for i, c in enumerate(chunks):
            seg = AudioSegment.from_file(BytesIO(c), format="mp3")
            out += seg if i == 0 else (silence + seg)
        out.export(out_path, format="mp3", bitrate="128k")
        return "pydub"
    except Exception as e:  # pydub or ffmpeg missing → naive concat
        with open(out_path, "wb") as f:
            for c in chunks:
                f.write(c)
        print(f"  note: pydub/ffmpeg unavailable ({e}); wrote raw-concatenated MP3 "
              f"(no inter-chunk silence). `brew install ffmpeg` + `pip install pydub` for clean seams.",
              file=sys.stderr)
        return "concat"


# ---------------------------------------------------------------------------- main
def build_provider(name, args):
    if name == "fish":
        key = os.environ.get("FISH_API_KEY") or os.environ.get("FISH_AUDIO_API_KEY")
        voice = args.voice or os.environ.get("FISH_VOICE_ID")
        model = args.model or "s2-pro"
        return FishProvider, key, voice, model, "FISH_API_KEY", "FISH_VOICE_ID"
    if name == "elevenlabs":
        key = os.environ.get("ELEVENLABS_API_KEY")
        voice = args.voice or os.environ.get("ELEVENLABS_VOICE_ID")
        model = args.model or "eleven_multilingual_v2"
        return ElevenLabsProvider, key, voice, model, "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"
    raise SystemExit(f"unknown provider: {name}")


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Render a narration script to one MP3.")
    ap.add_argument("narration", help="path to the narration .txt script")
    ap.add_argument("--out", required=True, help="output MP3 path (e.g. docs/<slug>/audio/<slug>.mp3)")
    ap.add_argument("--provider", choices=["fish", "elevenlabs"], default="fish")
    ap.add_argument("--voice", help="voice id (else FISH_VOICE_ID / ELEVENLABS_VOICE_ID)")
    ap.add_argument("--model", help="override model (fish: s2-pro/s1 · el: eleven_multilingual_v2/eleven_v3)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--stability", type=float, default=0.55,
                    help="0–1, higher = steadier (mapped to Fish temperature)")
    ap.add_argument("--max-chars", type=int, default=1800, help="chunk size ceiling")
    ap.add_argument("--gap-ms", type=int, default=400, help="silence between chunks (pydub only)")
    ap.add_argument("--dry-run", action="store_true", help="clean+chunk+estimate; no API call, no key needed")
    args = ap.parse_args()

    raw = open(args.narration, encoding="utf-8").read()
    text = prepare_for_tts(raw)
    chunks = chunk_text(text, args.max_chars)
    total_chars = sum(len(c) for c in chunks)
    total_bytes = sum(len(c.encode("utf-8")) for c in chunks)

    ProviderCls, key, voice, model, key_env, voice_env = build_provider(args.provider, args)
    words = len(text.split())
    print(f"provider={args.provider} model={model} voice={voice or '(unset)'}")
    print(f"{words:,} words · {total_chars:,} chars · {len(chunks)} chunk(s) "
          f"· ~{words/150:.1f} min at 150 wpm")
    print("  " + ProviderCls.cost_note(total_chars, total_bytes))

    if args.dry_run:
        for i, c in enumerate(chunks):
            print(f"  chunk {i+1}: {len(c)} chars — {c[:70].replace(chr(10), ' ')}…")
        print("dry run: no audio synthesized.")
        return 0

    missing = []
    if not key:
        missing.append(key_env)
    if not voice:
        missing.append(f"--voice or {voice_env}")
    if missing:
        raise SystemExit(f"error: missing {', '.join(missing)} — set it (env or .env) or pass --voice.")

    try:
        import requests
    except ImportError:
        raise SystemExit("error: `pip install -r requirements.txt` (needs `requests`).")

    provider = ProviderCls(key, voice, model=model, speed=args.speed, stability=args.stability)
    audio_chunks = []
    for i, c in enumerate(chunks):
        prev = chunks[i - 1][-300:] if i > 0 else None
        nxt = chunks[i + 1][:300] if i + 1 < len(chunks) else None
        for attempt in range(5):
            try:
                print(f"  synth chunk {i+1}/{len(chunks)} ({len(c)} chars)…")
                audio_chunks.append(provider.synthesize(requests, c, prev, nxt))
                break
            except requests.HTTPError as e:                      # backoff on 429/5xx
                code = e.response.status_code if e.response is not None else 0
                if code in (429, 500, 502, 503, 504) and attempt < 4:
                    wait = min(60.0, 5.0 * (2 ** attempt))
                    print(f"    {code} — retrying in {wait:.0f}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                body = e.response.text[:300] if e.response is not None else str(e)
                raise SystemExit(f"error: provider returned {code}: {body}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    how = stitch(audio_chunks, args.out, args.gap_ms)
    size = os.path.getsize(args.out)
    print(f"wrote {args.out} ({size/1024:.0f} KB, {len(audio_chunks)} chunk(s), stitch={how})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
