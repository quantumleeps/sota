# State of the Art — provenance-cited reviews

A hub of hyperlinked, provenance-cited literature reviews on how AI coding agents are steered by their **context** and **memory**. Each review absorbs one sealed corpus and writes its own self-contained site.

**Live:** https://quantumleeps.github.io/sota/

## Topics
- **Context Engineering** — `/context-engineering/` — codified context for AI coding agents (AGENTS.md/CLAUDE.md, rules, skills, MCP, sub-agents); 33-document corpus.
- **Context Engineering × Agent Memory** — `/context-engineering-memory/` — the convergence of context engineering and agent memory, 2024–2026; 16 sources.

## Layout
This repo is the published (site-only) artifact. One shared `styles.css` lives at the top level; each topic's pages sit in its own directory and link `../styles.css`. The `index.html` here is the hub; each topic page links back via "↑ All SotA" (`../index.html`).

The unpublished reading material (corpora, digests) lives outside this repo, grouped per topic as `<topic>/{corpus,digests,site}`; the `site/` dirs are the source for the pages assembled here.

## Provenance convention
Every sourced claim carries a citation chip → that topic's Corpus page → arXiv or the publishing lab. Claim-type tags (Empirical / Theory / Proposal / Definition) show source strength. **Amber callouts are author inference**, never a paper's claim. Content derives from public papers and lab writeups; it is not re-hosted.

Run locally: `python3 -m http.server` from this directory, then open `http://localhost:8000`.
`.nojekyll` disables Jekyll on GitHub Pages.
