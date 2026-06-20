#!/usr/bin/env bash
# Download one arXiv paper's LaTeX source and extract it into <dest>/<id>/.
# Usage: fetch-arxiv-src.sh <arxiv-id-or-url> [dest-dir]   (dest defaults to ./papers)
#
# Handles the three things arXiv's /src/ endpoint can return:
#   - gzipped tar (multi-file source, the common case)
#   - gzip of a single .tex (older single-file submissions)
#   - a bare PDF (PDF-only submissions: no TeX exists -> saved + warned)
# Re-running is a no-op for papers already fetched.
set -euo pipefail

UA="arxiv-src-fetch/1.0 (mailto:dan.leeper@gmail.com)"

die() { echo "error: $*" >&2; exit 1; }
[ $# -ge 1 ] || die "usage: $0 <arxiv-id-or-url> [dest-dir]"

# Fallback when no TeX source exists: prefer a self-contained HTML render
# (LaTeXML/ar5iv) over PDF, since HTML is far easier to read/parse. A genuine
# PDF-only submission has no TeX, hence no HTML either -- then we keep the PDF.
# Args: $1 = path to the already-downloaded PDF (kept only if HTML is absent).
fallback_html_or_pdf() {
  local pdf="$1"
  local url="https://arxiv.org/html/$id"
  if [ "$(curl -so /dev/null -w '%{http_code}' -A "$UA" "$url")" = "200" ]; then
    echo "[info] $id: no TeX; bundling HTML instead"
    if command -v monolith >/dev/null 2>&1; then
      monolith -a -e -s -o "$outdir/$id.html" "$url" && return 0
    fi
    curl -fsSL -A "$UA" -o "$outdir/$id.html" "$url" && return 0
  fi
  if [ -n "$pdf" ] && [ -f "$pdf" ]; then
    mv "$pdf" "$outdir/$id.pdf"
    echo "[warn] $id: no TeX or HTML available, kept PDF"
  else
    echo "[warn] $id: no TeX, HTML, or PDF available"
  fi
}

raw="$1"; dest="${2:-papers}"

# Normalize to a bare arXiv id (keeps a vN suffix if present).
id="${raw%%\?*}"   # drop ?query
id="${id%/}"       # drop trailing slash
id="${id##*/}"     # keep last path segment (handles abs/ src/ pdf/ html/ forms)
[[ "$id" =~ ^[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?$ ]] || die "not an arXiv id: '$raw' -> '$id'"

# Optional HARD DATE CUTOFF (programmatic, from the id's YYMM — no network needed).
# Set SOTA_AFTER and/or SOTA_BEFORE to YYYY or YYYY-MM to skip papers outside the
# window. Applies to harvested references too (they fetch through this script).
_pdate="20${id%%.*}"                                  # 2602.20478 -> 202602
_norm() { local c="${1//-/}"; [ ${#c} -eq 4 ] && c="${c}$2"; printf '%s' "$c"; }
if [ -n "${SOTA_AFTER:-}" ] && [ "$_pdate" -lt "$(_norm "$SOTA_AFTER" 01)" ]; then
  echo "[date-skip] $id (20${id%%.*} before SOTA_AFTER=$SOTA_AFTER)"; exit 0
fi
if [ -n "${SOTA_BEFORE:-}" ] && [ "$_pdate" -gt "$(_norm "$SOTA_BEFORE" 12)" ]; then
  echo "[date-skip] $id (20${id%%.*} after SOTA_BEFORE=$SOTA_BEFORE)"; exit 0
fi

outdir="$dest/$id"
if [ -d "$outdir" ] && [ -n "$(ls -A "$outdir" 2>/dev/null)" ]; then
  echo "[skip] $id (already at $outdir)"; exit 0
fi
mkdir -p "$outdir"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

echo "[fetch] $id"
curl -fsSL --retry 3 --retry-delay 2 -A "$UA" -o "$tmp/src" \
  "https://arxiv.org/src/$id" || die "download failed for $id"

mime="$(file -b --mime-type "$tmp/src")"
case "$mime" in
  application/gzip|application/x-gzip)
    gunzip -c "$tmp/src" > "$tmp/inner"
    if file -b "$tmp/inner" | grep -qi 'tar archive'; then
      tar -xf "$tmp/inner" -C "$outdir"
    else
      mv "$tmp/inner" "$outdir/$id.tex"   # single-file gzipped source
    fi ;;
  application/x-tar)
    tar -xf "$tmp/src" -C "$outdir" ;;
  application/pdf)
    fallback_html_or_pdf "$tmp/src" ;;
  *)
    if tar -xf "$tmp/src" -C "$outdir" 2>/dev/null; then :; else
      fallback_html_or_pdf "$tmp/src"
    fi ;;
esac

# Flatten a single top-level subdirectory so each paper is one flat dir.
shopt -s dotglob nullglob
entries=("$outdir"/*)
if [ ${#entries[@]} -eq 1 ] && [ -d "${entries[0]}" ]; then
  mv "${entries[0]}"/* "$outdir"/ && rmdir "${entries[0]}"
fi
shopt -u dotglob nullglob

echo "[done] $id -> $outdir ($(ls -1A "$outdir" | wc -l | tr -d ' ') files)"
