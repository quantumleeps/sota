# TTS providers & synthesis (Fish Audio + ElevenLabs)

Reference for the **optional** audio pass. The narration script is the deliverable;
this is how it becomes an MP3. The bundled `scripts/tts_synthesize.py` already
implements everything below behind one interface — you rarely need to hand-roll a
call. Use this doc to choose a provider, set keys/voice, and understand the knobs.
Endpoints/params are current to **June 2026**; confirm against docs.fish.audio /
elevenlabs.io/docs before a large batch.

## The two providers at a glance

|  | Fish Audio (default) | ElevenLabs |
|---|---|---|
| Base / endpoint | `POST https://api.fish.audio/v1/tts` | `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` |
| Auth header | `Authorization: Bearer <KEY>` | `xi-api-key: <KEY>` |
| Model goes in | an HTTP **header** `model: s2-pro` | the JSON body `model_id` |
| Voice goes in | JSON `reference_id` | the URL **path** |
| Narration model | `s2-pro` (top quality; loudness-normalized) | `eleven_multilingual_v2` (~10k chars/req) |
| Billing | UTF-8 **bytes** — $15 / 1M (~12 h audio) | **characters**, per plan |
| Output | MP3 128 kbps / 44.1 kHz | MP3 (format via `?output_format=`) |

The only structural disagreement is *where the model goes and how you authenticate*
— everything else maps cleanly, which is why one adapter per provider behind one
interface is all the script needs. **Default to Fish `s2-pro`**: best quality-to-
cost for narration, pure pay-as-you-go, no plan minimum. Reach for ElevenLabs
`eleven_multilingual_v2` when you want its mature voice library or its
`previous_text`/`next_text` stitching for very long pieces.

## Keys & voice (env or `.env`, never hard-coded)

The script loads these from the environment or the nearest `.env` (same loader as
`arxiv-paper-finder`; a real env var always wins):

```
FISH_API_KEY=…            FISH_VOICE_ID=…           # browse voices at fish.audio, copy the model id
ELEVENLABS_API_KEY=…      ELEVENLABS_VOICE_ID=…     # a voice id from your ElevenLabs library
```

Voice can also be passed with `--voice`. Keep keys out of any logs.

## Running it

```bash
# Preview cost + chunking with NO API call and NO key:
python3 scripts/tts_synthesize.py topics-corpora/<slug>/audio/narration.txt \
    --out docs/<slug>/audio/<slug>.mp3 --dry-run

# Synthesize (Fish s2-pro by default):
python3 scripts/tts_synthesize.py topics-corpora/<slug>/audio/narration.txt \
    --out docs/<slug>/audio/<slug>.mp3 --voice "$FISH_VOICE_ID"

# Or ElevenLabs:
python3 scripts/tts_synthesize.py … --provider elevenlabs --voice "$ELEVENLABS_VOICE_ID"
```

Useful flags: `--stability 0.55` (0–1, higher = steadier; the script maps it to
Fish's inverted `temperature`), `--speed 1.0`, `--max-chars 1800` (chunk ceiling),
`--gap-ms 400` (silence between chunks). For dry, steady research narration, a
slightly higher stability (0.55–0.65) / lower temperature reads best.

## What the script handles for you

- **Chunking** on paragraph → sentence boundaries under `--max-chars` (never
  mid-sentence — a split sentence glitches at the seam). Both engines also sound
  better fed coherent segments than one giant blob.
- **Continuity across chunks.** ElevenLabs gets the tail/head of neighbors as
  `previous_text`/`next_text` (context only, not spoken) so intonation flows; Fish
  keeps `condition_on_previous_chunks` on and a steady low temperature + one voice.
- **Stitching** into one MP3 — via `pydub` (clean PCM joins + real `--gap-ms`
  silence; needs `ffmpeg`), falling back to raw MP3 concatenation if pydub/ffmpeg
  aren't installed (valid file, no gap control).
- **Backoff** on `429`/`5xx`, and a per-provider **cost estimate** (Fish: bytes →
  dollars; ElevenLabs: character count) printed up front and on `--dry-run`.

## Cost & determinism notes

- Plain English ≈ 1 byte/char, so Fish cost ≈ `$15 × chars / 1,000,000`. The
  `--dry-run` prints the exact estimate from the cleaned, chunked text.
- Both engines are nondeterministic; don't expect byte-identical re-runs. ElevenLabs
  accepts a `seed`; Fish leans on a low temperature. Re-synthesizing overwrites the
  MP3 in place, so the listen page picks up the new audio with no other changes.
- MP3 128 kbps is plenty for speech and keeps the committed file small. The single
  narration for a focused review is typically a few MB.
