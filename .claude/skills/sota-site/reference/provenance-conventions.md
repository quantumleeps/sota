# Provenance conventions

These are what make the site trustworthy: a reader can trace any claim to its source, and can always tell a paper's finding from your synthesis. `assets/styles.css` already implements every class below — never restyle; just use the classes.

## 1. Citation chips — every sourced claim carries one

Inline, immediately after the claim, linking to the bibliography entry in `corpus.html`:

```html
<a class="cite" href="corpus.html#p-2601-20404">Lulla+&nbsp;'26</a>
```

- **Anchor id rule:** arXiv id with dots → dashes, prefixed `p-`. `2601.20404` → `#p-2601-20404`. (Dots are legal in ids but dashes keep CSS/anchor handling painless — be consistent.)
- **Label:** `FirstAuthor+ 'YY` (e.g. `Mei+ '25`). Pick one label per paper and use it everywhere. Use `&nbsp;` so the chip never line-wraps.
- A claim drawn from several papers gets several chips in a row.
- The chip points at `corpus.html#p-…`; the corpus entry is what links onward to **arXiv**. So the chain is always: claim → chip → bibliography → arXiv.

## 2. Claim-type tags — show how strong a claim is in its source

```html
<span class="tag emp">Empirical</span>   <!-- measured result -->
<span class="tag thy">Theory</span>      <!-- theoretical/analytical argument -->
<span class="tag prop">Proposal</span>   <!-- proposed design/method, not yet validated -->
<span class="tag def">Definition</span>  <!-- a definition/taxonomy the paper introduces -->
```
Tag a claim with what the digest marked it. This lets a reader weight a controlled result differently from a position-paper proposal at a glance.

## 3. The finding-vs-inference line — the core rule

**Paper findings** are stated in normal prose with a citation chip, or in a blue callout. **Your own synthesis/extrapolation/opinion** goes in an amber callout, explicitly labeled, and is *never* written as though a paper claimed it.

```html
<!-- a finding from the corpus (blue) -->
<div class="box finding"><p class="box-h">▦ A finding from the papers</p>
  <p>…cited claim… <a class="cite" href="corpus.html#p-XXXX">Author+&nbsp;'YY</a></p></div>

<!-- YOUR inference — not from the papers (amber) -->
<div class="box inference"><p class="box-h">⟡ My inference — not from the papers</p>
  <p>…your synthesis. Chips here mark what you reason FROM, not a source that agrees.…</p></div>
```

Two more callouts for honesty:
```html
<div class="box gap"><p class="box-h">◇ Open problem / caveat</p><p>…</p></div>   <!-- grey -->
<div class="box risk"><p class="box-h">⚠ Risk</p><p>…</p></div>                      <!-- rose -->
```

The dedicated **Synthesis** page is entirely amber-style inference (give it a banner saying so). Everywhere else, inference is the fenced exception inside a field of cited findings. If you ever can't back a sentence with a chip and it isn't in an inference box, it doesn't belong.

## 4. Verbatim quotes from papers

For direct, attributable quotation (use the digests' "notable quotes"):

```html
<blockquote class="q">…exact words…
  <span class="src">— Title <a class="cite" href="corpus.html#p-XXXX">Author+&nbsp;'YY</a>, §Section</span>
</blockquote>
```
Keep quotes short and exact. Quotes are the safest way to convey a paper's strong wording without paraphrase risk.

## 5. Supporting components (all in styles.css)

- **Stat card:** `<div class="card stat"><div class="big green">−28.6%</div><div class="lbl">… <a class="cite" …>chip</a></div></div>` — `.big` accent, `.big.green` positive, `.big.amber` for inference/uncertain.
- **Tables:** `<div class="tbl-wrap"><table>…</table></div>`; cells `td.num` for figures, `.pos`/`.neg` for good/bad deltas. Put chips in headers/cells to source each row.
- **Cards / grid:** `<div class="grid g2|g3"><div class="card">…</div></div>`; make a card a link with `<a class="card cardlink" href="…">`.
- **Timeline:** `<div class="timeline"><div class="tl-item"><div class="when">…</div><div class="what">…</div></div></div>`.
- **Legend / pills:** `<div class="legend"><span><span class="sw" style="background:…"></span> label</span>…</div>`.
- **Pager** (bottom of every page) and **footer.site** — see `assets/page-template.html`.
- Helpers: `.note` (muted italic), `.mono`, `ul.clean` (arrow bullets), `.kicker` (overline), `.lede` (standfirst), `wrap wide` for wide pages.

## 6. Reading-convention block (put on the Overview page)
Tell the reader the rules above in two lines so the visual language is legible:
> Citation chips like [chip] follow every sourced claim and link to the bibliography → arXiv. Amber blocks are my inference; blue blocks are paper findings; teal quotes are verbatim.
