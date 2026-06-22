# Writing the narration (audio-native authoring)

This is the heart of the skill. You are **not** converting the HTML — you are
**authoring a fresh narration** from the same in-context understanding you used to
write the site, the moment after `/sota-site` finishes, while the digests and the
synthesis are still in working memory. Write for the **ear**, not the eye. A page
read aloud verbatim sounds robotic and mispronounces everything; a narration
written *as speech* sounds like a person who read the papers explaining them.

The output is **one continuous narration** — a single flowing listen for the whole
topic, with spoken transitions between parts (the user chose this shape). It is
saved as a plain-text script and becomes both the transcript on `listen.html` and
the input to the synthesizer.

## The non-negotiable: carry the honesty guardrails into speech

The narration inherits every honesty rule the site lives by. These are load-bearing
— the value of the artifact is a faithful, corpus-scoped reading, and that must
survive the move to audio.

- **It is a reading of THIS corpus, not a verdict on the field.** Say "across these
  N sources" / "in this corpus," never "the field is moving toward…" or "the state
  of the art is…". Open with the **scope line** spoken aloud (see below).
- **Separate findings from inference, out loud.** When you cross from what the papers
  found into your own synthesis, *mark it in words*: "Here I'm going beyond what the
  papers claim —", "this next part is my own reading, not a finding," "the papers
  don't say this; it's how I'd put it together." The amber callouts on the site
  become spoken hedges. Never let your inference sound like a paper's result.
- **Preserve exact numbers and attributions.** Keep the real figures (spoken as
  words) and attribute them to the right work. Distinguish a paper's own result
  from a number it merely cites. If a source didn't state something, don't invent it.
- **Name strength honestly.** "measured," "argued," "proposed but not yet tested,"
  "a single small study" — the claim-type tags become spoken qualifiers.

## Audio-native writing rules (apply them as you write, not as a cleanup pass)

1. **No markup, no chips, no tables.** Don't write `**bold**`, `#`, bullet
   asterisks, `[1]`, or citation chips. Speak the structure instead.
2. **Spell out numbers, symbols, units.** "ninety-two percent," "minus ninety-two
   percent," "version two point five," "forty-four point one kilohertz,"
   "approximately," "plus or minus," "fifteen dollars per million bytes." The
   engines normalize imperfectly on technical text — you do it at the source. (The
   synthesizer keeps a light safety-net normalizer, but don't lean on it.)
3. **Citations become spoken attributions — and only where they earn it.** "the
   Mem0 paper, Chhikara and colleagues, twenty twenty-five," "Anthropic's context-
   engineering writeup." Don't read every chip; attribute the load-bearing claims
   and let the rest flow. The transcript + the site's Corpus page hold the full
   provenance; the audio names sources the way a person would.
4. **Punctuation is your prosody.** The model infers pacing and intonation from
   punctuation, so it *is* the control surface. End every sentence with a period.
   Use commas for breath in long clauses. Em dashes and colons make natural
   mid-sentence pauses. Keep question marks on rhetorical questions — they change
   the intonation. A blank line (paragraph break) cues a longer pause; use blank
   lines between beats.
5. **Short, spoken sentences beat dense academic ones.** Unpack a packed sentence
   into two or three. Prefer the active voice and concrete subjects. Read a draft
   line in your head — if you run out of breath, split it.
6. **Expressive tags: basically none.** Clean text + good punctuation beats tagging
   for factual narration. At most, an opening tone-setter is acceptable if you want
   it (Fish s2-pro takes inline `[calm]`/`[measured]`; ElevenLabs takes a
   `<break time="1s" />` between major parts) — but the default is clean prose and
   paragraph breaks. Don't pepper the script with tags.

## Shape of the continuous narration

One piece, read start to finish, but with audible structure so a listener can
follow by ear. A good default arc, adapted to *this* corpus (don't force it):

1. **Cold open + scope line.** One or two sentences naming the topic and the
   central thesis that emerged across the corpus, then the spoken scope line:
   *"This is a review of N sources, gathered around [when] — a reading of this
   particular set of papers, not a complete survey of the field."* Then a one-
   sentence "here's how this narration goes."
2. **The recurring claims.** Walk the few positions with enough support across the
   corpus to count as consensus *here*, each as a short spoken beat with its
   attribution and an honest strength qualifier.
3. **The themes**, in the site's reading order. Open each with a **spoken
   transition cue** — "First, the foundations." / "Now, how this plays out in
   practice." / "Next, the evidence — what was actually measured." — then a blank
   line, then the beat. These cues are how the listener navigates without a screen.
4. **Evidence, spoken honestly.** The strongest measured results as plain spoken
   numbers with their method and scale, then where the evidence is thin.
5. **Synthesis, clearly flagged as yours.** Open it with an explicit verbal hand-off
   ("Everything up to here was the papers. Here's my own reading across them —") so
   no one mistakes inference for finding. Keep it corpus-scoped; nothing here is a
   forecast.
6. **Close.** A short wrap that restates the scope ("again, this is N papers, not
   the field") and points the ear back to the site/corpus for provenance.

Length: let the corpus drive it. A focused review is usually a **6–12 minute**
listen (~900–1,800 spoken words ≈ 150 words/minute); a rich corpus can run longer.
Favor a tight, well-paced piece over an exhaustive one — audio has no skimming.

## The narration.txt contract (what the scripts expect)

Write the script to `topics-corpora/<slug>/audio/narration.txt` as **plain text**:

- **Paragraphs** separated by a blank line. Every paragraph is spoken; blank lines
  become longer pauses.
- A line beginning with `## ` is a **transcript-only chapter heading** — it is
  rendered as a heading on `listen.html` for the eye, but is **NOT spoken** (the
  synthesizer strips it). Use a handful to chapter the transcript; your *spoken*
  section cue still lives in the prose (rule 3 of the shape above). Keep the two
  consistent (`## Evidence` above the paragraph that opens "Next, the evidence…").
- No other markup. No chips, no tables, no Markdown emphasis.

The transcript published on the site is taken **verbatim** from this file, so it is
a true transcript of what is (or will be) spoken.
