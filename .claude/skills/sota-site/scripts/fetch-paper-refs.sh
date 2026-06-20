#!/usr/bin/env bash
# Harvest the arXiv works a paper cites and fetch each one's LaTeX source.
# Usage: fetch-paper-refs.sh <paper-dir-or-bbl/bib/tex-file> [dest-dir]
#   dest defaults to <paper-dir>/refs ; point it at your shared papers/ pool
#   (e.g. fetch-paper-refs.sh papers/2602.20478 papers) to dedupe against
#   papers you already have. Each referenced arXiv paper lands as one flat
#   subdirectory under dest -- no recursion into references-of-references.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
fetch="$here/fetch-arxiv-src.sh"
sleep_s="${ARXIV_SLEEP:-3}"   # be polite to arXiv between downloads

die() { echo "error: $*" >&2; exit 1; }
[ $# -ge 1 ] || die "usage: $0 <paper-dir-or-bibfile> [dest-dir]"
[ -x "$fetch" ] || die "missing $fetch"

src="$1"
if [ -d "$src" ]; then
  dest="${2:-$src/refs}"
  content="$(find "$src" -maxdepth 1 -type f \( -name '*.bbl' -o -name '*.bib' -o -name '*.tex' \) -exec cat {} +)"
elif [ -f "$src" ]; then
  dest="${2:-$(dirname "$src")/refs}"
  content="$(cat "$src")"
else
  die "no such paper dir or file: $src"
fi
[ -n "$content" ] || die "no .bbl/.bib/.tex content found in $src"

# Pull arXiv ids from arXiv:NNNN.NNNNN, abs/NNNN.NNNNN, eprint fields, etc.
ids="$(printf '%s' "$content" \
  | grep -oiE '(arxiv[:/ ]+|abs/|eprint[ ={]+)[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?' \
  | grep -oE '[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?' \
  | sort -u)"

[ -n "$ids" ] || { echo "no arXiv references found in $src"; exit 0; }

n="$(printf '%s\n' "$ids" | wc -l | tr -d ' ')"
echo "found $n arXiv reference(s) in $src -> $dest"
while IFS= read -r id; do
  "$fetch" "$id" "$dest" || echo "[warn] failed: $id"
  sleep "$sleep_s"
done <<< "$ids"
echo "[refs done] $src"
