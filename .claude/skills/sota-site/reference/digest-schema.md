# Reading-agent digest schema

Phase 2 reads every paper in full and returns a structured, quote-anchored **digest**. You synthesize the site from these digests — not from raw papers — which keeps context manageable and the writing faithful. Dispatch independent agents in one batch so they run concurrently.

## Granularity
- **Priority papers** (anchor/core, and any the user flagged): one agent each, read in full.
- **Long reference lists**: cluster 2–3 thematically-related papers per agent (still full-text each), to bound the number of agents. A digest-per-paper is still produced inside each agent's output.

Scale the fan-out to the set: a handful of papers → one agent each; dozens → priority papers solo + clustered references. If you cap coverage anywhere (e.g. skim a low-value ref), say so in the site rather than implying full coverage.

## The agent prompt (template)

Give each reading agent this, filling the bracketed parts:

> You are reading academic paper(s) from a local corpus (cwd: `<BUILD>/corpus/papers`) to support a state-of-the-art synthesis on **"<TOPIC>"**. Read the specified file(s) IN FULL.
> - **format=tex** → read the `\documentclass` root, then follow every `\input`/`\include` and `sections/` in order; the bibliography (`.bbl`/`.bib`) lists cited works.
> - **format=pdf** → read it fully with the `pdf` skill or the Read tool's `pages` parameter in chunks until the whole document is covered.
> - **format=html** → it is a self-contained bundle; read it directly.
>
> Files to read: `<paths>`
>
> Return a digest in EXACTLY the format below. Be faithful: never invent authors or numbers; preserve exact figures/percentages/p-values; if something isn't in the source, write "not stated in source." Distinguish the paper's own results from numbers it merely cites. Your entire response is consumed by an orchestrator as source material — return only the digest(s), no preamble.

## The digest format (per paper)

```
## <arXiv id> — <short title>
- **Authors/affiliation/venue/date:** (from source, else "not stated in source")
- **Type:** empirical | survey | system/tool | position/vision | benchmark | framework
- **Core thesis:** 1–2 sentences.
- **Key findings/claims:** numbered list. Each item = the claim + a tag
  [EMPIRICAL] / [THEORETICAL] / [PROPOSAL] / [DEFINITION] + a provenance anchor
  (section name or a short verbatim "quote"). Preserve exact numbers.
- **Definitions/terminology introduced:** terms the paper coins or defines (its own wording).
- **Methodology (if empirical):** dataset/sample size, what was measured, key numbers, significance.
- **Notable verbatim quotes:** 3–5 short quotes (<=25 words) each with a section location — for direct citation on the site.
- **Relation to the thread:** how it connects to <TOPIC> (mechanisms, artifacts, claims it supports/undercuts).
- **Stated limitations / open problems.**
```

## Why this shape
The tags and provenance anchors are what let the site separate empirical findings from proposals and theory, and the verbatim quotes give you safe, attributable text to quote directly. The "relation to the thread" and "limitations" fields feed the thematic pages, the Evidence ledger, and the Failure/Limitations page respectively. Keep digests dense but faithful; they are the entire evidentiary basis for the site.
