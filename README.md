# SotA — state-of-the-art review hub

A self-contained, topic-agnostic working repo that turns a list of papers on any research topic into a hyperlinked, provenance-cited review and publishes it as one topic in a shared GitHub Pages hub. Each topic absorbs one sealed corpus and writes its own self-contained site.

**Live:** https://quantumleeps.github.io/sota/

## Topics
- **Context Engineering** — `/context-engineering/` — codified context for AI coding agents (AGENTS.md/CLAUDE.md, rules, skills, MCP, sub-agents). **Deep dive**: 10 papers + 23 harvested references.
- **Context Engineering × Agent Memory** — `/agent-memory/` — the convergence of context engineering and agent memory, 2024–2026. **Review**: 16 sources.

## How it works
`cd` here and run Claude Code; the bundled **`sota-site`** skill (`.claude/skills/sota-site/`) fetches the corpus, reads every paper in full via parallel agents, synthesizes a provenance-cited topic site, regenerates the hub, verifies link integrity, and publishes. See `CLAUDE.md` for the workflow, the review-vs-deep-dive option, and the date-cutoff option.

## Layout
- `docs/` — the **published** site (GitHub Pages source: `main` `/docs`): the hub `index.html`, one shared `styles.css`, and `docs/<slug>/` per topic.
- `topics-corpora/` — **gitignored** working material (corpora + digests); not published.
- `.claude/skills/sota-site/` — the skill, versioned with the repo.

## Provenance convention
Every sourced claim carries a citation chip → that topic's Corpus page → arXiv or the publishing lab. Claim-type tags (Empirical / Theory / Proposal / Definition) show source strength. **Amber callouts are author inference**, never a paper's claim. Content derives from public papers and lab writeups; it is not re-hosted.

Run locally: `python3 -m http.server` in `docs/`, then open `http://localhost:8000`. `.nojekyll` (inside `docs/`) disables Jekyll on Pages.
