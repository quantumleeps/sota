# Publish runbook (GitHub Pages)

Phase 5. `scripts/publish_pages.sh <site-dir> <repo-name>` automates this; this doc explains what it does, the manual fallback, and the gotchas.

## Before you publish — the gate
Publishing is **outward-facing and effectively permanent** (search engines index and cache; deletion doesn't fully retract). **Confirm with the user** that a world-readable site is intended, and confirm the repo name (`<slug>-sota[-vN]`). Also confirm `gh auth status` is green; if not, stop and have them run `gh auth login`.

**Visibility reality to state plainly:** on non-Enterprise plans a Pages site is public **even if the repo is private** — repo visibility only hides source, not the rendered site. So "make the repo private" does not make the site private. For these sites the content is public-arXiv-derived, so a public repo is the normal choice.

## What the script does
1. Resolves your GitHub login via `gh api user`.
2. Ensures `.nojekyll` exists (the site is hand-written HTML; Jekyll would needlessly process it and can hide files).
3. Sets a privacy-preserving local git identity if none is configured (`<owner>@users.noreply.github.com`) so a personal email isn't baked into public history.
4. **First run:** `git init` in the site dir → commit → `gh repo create <owner>/<repo> --public --source=<site> --push` → enable Pages via `POST repos/<owner>/<repo>/pages` with `{"source":{"branch":"main","path":"/"}}`.
5. **Re-run (updates):** detects an existing repo+remote and just commits + pushes; Pages auto-rebuilds.
6. Polls `https://<owner>.github.io/<repo>/` with curl retries until it serves (first build is ~1–2 min).

Because the site dir is published as the repo root, URLs are clean (`…github.io/<repo>/foundations.html`) and there is no corpus/papers material in it (site-only).

## Manual fallback (if the script can't run)
```bash
cd <site-dir>
touch .nojekyll
git init -b main && git add -A && git commit -m "Publish SotA review microsite"
gh repo create <owner>/<slug>-sota --public --source=. --remote=origin --push
echo '{"source":{"branch":"main","path":"/"}}' | gh api --method POST repos/<owner>/<slug>-sota/pages --input -
# then open https://<owner>.github.io/<slug>-sota/
```

## README.md to include in the site
A short README at the site root helps anyone who lands on the repo:
- one-line description + the live URL (fill in after first publish),
- the page list,
- the provenance convention (chips → bibliography → arXiv; amber = author inference),
- a note that content derives from public arXiv papers (not re-hosted) and how to run locally (`python3 -m http.server`),
- mention `.nojekyll`.
Also add a `.gitignore` with `.DS_Store`, `*.log`, `Thumbs.db`.

## Updating later
Edit files in the site dir, then re-run `publish_pages.sh <site-dir> <repo>` (it commits + pushes), or `git push` directly. Pages rebuilds in ~30–60 s. The site dir is the canonical source for the published site.

## Gotchas (all caught by verify_site.sh except where noted)
- **Case sensitivity:** Pages runs on Linux; `Foundations.html` ≠ `foundations.html`. Keep filenames lowercase and links case-matched.
- **Relative links only:** project Pages serve under `…/<repo>/`, so `/absolute` and `../parent` links break. All links must be page-relative.
- **`.nojekyll`:** include it; otherwise Jekyll processes the site and ignores any `_`-prefixed paths.
- **HTTPS:** `*.github.io` certs are automatic and enforced — nothing to do.
- **First build latency:** the URL 404s until the first build finishes; the script's retry loop handles this. If it reports non-200, wait a minute and re-check.

## Optional follow-ups to offer the user
- **Custom domain:** add a `CNAME` file (the bare domain) + a DNS record; GitHub provisions the cert.
- **Discourage indexing** (site stays public, just less discoverable): add `<meta name="robots" content="noindex">` to each page's `<head>`.
- **Retire any local preview server** once the Pages URL is live.
