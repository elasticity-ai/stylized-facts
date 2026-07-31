#!/usr/bin/env python3
"""Apply the mechanical parts of the bibliography conventions to a .bib file.

Only fixes that are unambiguous from the file itself. Anything requiring a
lookup (a missing DOI, a missing year) is left alone and reported by
tools/stylized-facts.bib.tests.py instead.

Fixes applied:
  1. Trailing comma on the last field of every entry. The convention is one
     field per line, each ending in a comma, which is what makes the file
     safely parseable line-by-line.
  2. arXiv entries get the canonical url https://arxiv.org/pdf/<id>.pdf,
     inserted if absent. Requires `eprint` plus `archiveprefix = {arXiv}`.

Idempotent: running twice changes nothing the second time.

    python3 tools/bib_normalize.py            # rewrite stylized-facts.bib
    python3 tools/bib_normalize.py --check    # report, exit 1 if changes needed
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BIB = REPO_ROOT / "stylized-facts.bib"

ENTRY_START_RE = re.compile(r"^\s*@([A-Za-z]+)\s*\{\s*([^,]+)\s*,\s*$")
ENTRY_END_RE = re.compile(r"^\s*}\s*$")
FIELD_LINE_RE = re.compile(r"^(\s*)([A-Za-z][\w-]*)(\s*)=(\s*)(.*?)(,?)\s*$")
ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


def _is_field_line(line: str) -> bool:
    return bool(FIELD_LINE_RE.match(line)) and not line.lstrip().startswith("%")


def add_trailing_commas(lines: list[str]) -> tuple[list[str], int]:
    """Ensure the last field line of each entry ends with a comma."""
    out = list(lines)
    fixed = 0
    in_entry = False
    last_field_idx: int | None = None

    for idx, line in enumerate(lines):
        if not in_entry:
            if ENTRY_START_RE.match(line):
                in_entry = True
                last_field_idx = None
            continue

        if ENTRY_END_RE.match(line):
            if last_field_idx is not None:
                match = FIELD_LINE_RE.match(out[last_field_idx])
                if match and not match.group(6):
                    out[last_field_idx] = out[last_field_idx].rstrip() + ","
                    fixed += 1
            in_entry = False
            last_field_idx = None
            continue

        if _is_field_line(line):
            last_field_idx = idx

    return out, fixed


def _entry_blocks(lines: list[str]):
    """Yield (start_idx, end_idx, citekey) for each entry, end exclusive."""
    start = None
    key = None
    for idx, line in enumerate(lines):
        if start is None:
            match = ENTRY_START_RE.match(line)
            if match:
                start, key = idx, match.group(2).strip()
            continue
        if ENTRY_END_RE.match(line):
            yield start, idx, key
            start, key = None, None


def canonicalize_arxiv_urls(lines: list[str]) -> tuple[list[str], int]:
    """Point arXiv entries at https://arxiv.org/pdf/<id>.pdf.

    Entries are walked back-to-front so that inserting a `url` line into an
    earlier entry cannot shift the indices of one not yet visited.
    """
    out = list(lines)
    fixed = 0

    for start, end, _key in reversed(list(_entry_blocks(lines))):
        fields: dict[str, tuple[int, str]] = {}
        for idx in range(start + 1, end):
            if out[idx].lstrip().startswith("%"):
                continue
            match = FIELD_LINE_RE.match(out[idx])
            if match:
                fields[match.group(2).lower()] = (idx, match.group(5).strip())

        if "eprint" not in fields:
            continue
        if fields.get("archiveprefix", (0, ""))[1].strip('{} "').lower() != "arxiv":
            continue
        eprint = fields["eprint"][1].strip('{} ",')
        if not ARXIV_ID_RE.match(eprint):
            continue

        want = f"https://arxiv.org/pdf/{eprint}.pdf"

        if "url" in fields:
            idx, value = fields["url"]
            if want in value:
                continue
            indent, name, pre, post, _old, comma = FIELD_LINE_RE.match(out[idx]).groups()
            out[idx] = f"{indent}{name}{pre}={post}{{{want}}}{comma or ','}"
        else:
            idx, _ = fields["eprint"]
            indent, name, pre, post, _v, _c = FIELD_LINE_RE.match(out[idx]).groups()
            # keep the entry's `=` column: pad `url` to the width of the
            # field name it is being inserted next to
            pad = " " * max(1, len(name) + len(pre) - len("url"))
            out.insert(idx + 1, f"{indent}url{pad}={post}{{{want}}},")
        fixed += 1

    return out, fixed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bib", default=str(DEFAULT_BIB))
    ap.add_argument("--check", action="store_true", help="Report only; exit 1 if changes are needed.")
    args = ap.parse_args()

    path = Path(args.bib)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()

    lines, commas = add_trailing_commas(lines)
    lines, arxiv = canonicalize_arxiv_urls(lines)

    updated = "\n".join(lines)
    if original.endswith("\n"):
        updated += "\n"

    changed = updated != original
    print(f"trailing commas added: {commas}")
    print(f"arXiv urls canonicalized: {arxiv}")

    if args.check:
        print("CHANGES NEEDED" if changed else "clean")
        return 1 if changed else 0

    if changed:
        path.write_text(updated, encoding="utf-8")
        print(f"wrote {path}")
    else:
        print("no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
