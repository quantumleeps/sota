#!/usr/bin/env bash
# publish_pages.sh <repo-root> [repo-name]
# Publish a multi-topic SotA HUB repo to GitHub Pages (public), serving from /docs.
# The repo root holds the working project (the skill, CLAUDE.md, gitignored
# topics-corpora/) and the published site under docs/. GitHub Pages serves the
# docs/ folder, so the repo can carry the skill + working files without exposing
# them. Re-runnable:
#   - first run:  inits git (if needed), creates a PUBLIC repo, pushes, enables Pages from main/docs
#   - later runs: commits + pushes; ensures Pages source is main/docs
# Requires: gh (authenticated), git, curl. Runs under bash 3.2.
#
# NOTE: this creates a WORLD-READABLE site. The caller (skill) must confirm
# public publishing with the user before invoking this.
set -u

ROOT="${1:?usage: publish_pages.sh <repo-root> [repo-name]}"
[ -d "$ROOT" ] || { echo "error: not a dir: $ROOT" >&2; exit 2; }
[ -f "$ROOT/docs/index.html" ] || { echo "error: $ROOT/docs/index.html (hub) missing" >&2; exit 2; }
REPO="${2:-$(basename "$(cd "$ROOT" && pwd)")}"; REPO="${REPO##*/}"

command -v gh >/dev/null || { echo "error: gh not installed" >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { echo "error: gh not authenticated — run 'gh auth login'" >&2; exit 2; }
OWNER="$(gh api user --jq .login)"; [ -n "$OWNER" ] || { echo "error: cannot resolve gh user" >&2; exit 2; }
echo "owner=$OWNER repo=$REPO root=$ROOT (serving /docs)"

# Pages hygiene: disable Jekyll on the served folder (docs/), not just repo root.
[ -f "$ROOT/docs/.nojekyll" ] || touch "$ROOT/docs/.nojekyll"

ensure_id() {
  git -C "$ROOT" config --get user.name  >/dev/null 2>&1 || git -C "$ROOT" config user.name  "$OWNER"
  git -C "$ROOT" config --get user.email >/dev/null 2>&1 || git -C "$ROOT" config user.email "$OWNER@users.noreply.github.com"
}

if [ -d "$ROOT/.git" ] && git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
  echo "[update] existing repo; committing + pushing"
  ensure_id
  git -C "$ROOT" add -A
  if git -C "$ROOT" diff --cached --quiet; then echo "[update] no changes to push"; else
    git -C "$ROOT" commit -q -m "Update site"
    git -C "$ROOT" push -q
    echo "[update] pushed"
  fi
else
  echo "[create] first publish: init + create PUBLIC repo $OWNER/$REPO + push"
  [ -d "$ROOT/.git" ] || git -C "$ROOT" init -b main -q
  ensure_id
  git -C "$ROOT" add -A
  git -C "$ROOT" diff --cached --quiet || git -C "$ROOT" commit -q -m "Publish SotA hub"
  gh repo create "$OWNER/$REPO" --public --source="$ROOT" --remote=origin --push \
    --description "State-of-the-art review hub (built by the sota-site skill)"
fi

# Ensure Pages is enabled and serving from main/docs (idempotent).
if gh api "repos/$OWNER/$REPO/pages" >/dev/null 2>&1; then
  echo "[pages] ensuring source = main /docs"
  gh api --method PUT "repos/$OWNER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 \
    || echo "[pages] (PUT returned non-2xx — source may already be /docs; continuing)"
else
  echo "[pages] enabling Pages from main /docs"
  echo '{"source":{"branch":"main","path":"/docs"}}' \
    | gh api --method POST "repos/$OWNER/$REPO/pages" --input - >/dev/null 2>&1 \
    || echo "[pages] (POST returned non-2xx — may already be enabled; continuing)"
fi

URL="https://$OWNER.github.io/$REPO"
echo "[verify] polling $URL/ until it serves (first build / source change ~1-2 min)"
code="$(curl -sS -o /dev/null -w '%{http_code}' \
  --retry 24 --retry-delay 10 --retry-all-errors --retry-max-time 260 "$URL/")"
echo
echo "live hub  : $URL/   (HTTP $code)"
echo "repo      : https://github.com/$OWNER/$REPO"
[ "$code" = "200" ] || echo "note: not 200 yet — Pages can take another minute after a source change; re-check shortly."
