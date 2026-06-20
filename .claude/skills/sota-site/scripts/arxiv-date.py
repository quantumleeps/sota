#!/usr/bin/env python3
"""Filter / inspect arXiv IDs by submission date (encoded in the ID's YYMM).

The date check is purely programmatic — an arXiv ID NNNN.NNNNN starts with YYMM
(year-month of first submission), so 2602.20478 -> 2026-02. No network needed.

Usage:
    arxiv-date.py [--after YYYY[-MM]] [--before YYYY[-MM]] [--report] [IDS...]
    cat papers.txt | arxiv-date.py --after 2026          # keep only 2026+ ids

Reads IDs from positional args or stdin (one token per line; '#' comments and
extra words are ignored — the first arXiv-id-looking token on a line is used).
Prints KEPT ids to stdout (one per line). With --report, prints every id with its
date and KEEP/DROP verdict to stderr. Lines with no arXiv id are ignored.

Cutoffs are inclusive: --after 2026 keeps 2026-01 onward; --before 2026 keeps
through 2026-12. A YYYY-MM value pins the month.
"""
import sys, re, argparse

ID_RE = re.compile(r'\b(\d{4})\.(\d{4,5})(?:v\d+)?\b')


def to_yyyymm(four: str) -> int:
    """YYMM (e.g. '2602') -> 202602."""
    return int("20" + four)


def norm_cutoff(val: str, default_mm: str) -> int:
    c = val.replace("-", "")
    if len(c) == 4:        # year only -> pin to default month
        c = c + default_mm
    return int(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", help="keep ids on/after this YYYY or YYYY-MM")
    ap.add_argument("--before", help="keep ids on/before this YYYY or YYYY-MM")
    ap.add_argument("--report", action="store_true", help="print per-id verdicts to stderr")
    ap.add_argument("ids", nargs="*", help="arXiv ids (else read stdin)")
    a = ap.parse_args()

    lo = norm_cutoff(a.after, "01") if a.after else None
    hi = norm_cutoff(a.before, "12") if a.before else None

    lines = a.ids if a.ids else sys.stdin.read().splitlines()
    kept = dropped = 0
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = ID_RE.search(s)
        if not m:
            continue
        ident = f"{m.group(1)}.{m.group(2)}"
        d = to_yyyymm(m.group(1))
        keep = (lo is None or d >= lo) and (hi is None or d <= hi)
        ymd = f"{str(d)[:4]}-{str(d)[4:]}"
        if keep:
            print(ident); kept += 1
            if a.report: print(f"  KEEP {ident}  ({ymd})", file=sys.stderr)
        else:
            dropped += 1
            if a.report: print(f"  DROP {ident}  ({ymd})", file=sys.stderr)
    win = f"{a.after or '..'} .. {a.before or '..'}"
    print(f"[arxiv-date] window {win}: kept {kept}, dropped {dropped}", file=sys.stderr)


if __name__ == "__main__":
    main()
