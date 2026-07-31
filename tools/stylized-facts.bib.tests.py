#!/usr/bin/env python3
"""Validate stylized-facts.bib formatting and metadata conventions.

Defaults to updating the machine-generated test block in the bib file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
import json
from dataclasses import dataclass
from pathlib import Path

BEGIN_MARKER = "% BEGIN BIB TESTS (machine-generated)"
END_MARKER = "% END BIB TESTS"
MAX_ABSTRACT_WORDS = 500
REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_ARCHIVE_DIR = REPO_ROOT / "references" / "text"

# Every document that cites from stylized-facts.bib. Used by the
# "entry is cited somewhere" test; an entry cited by none of these is dead
# weight and should be removed or the citation restored.
CITING_DOCS = [
    "stylized-facts.qmd",
    "stylized-facts-slides.qmd",
    "stylized-facts-slides-BATES.qmd",
    "stylized-facts-matrices.qmd",
]

# citekey-like tokens in the documents that are LaTeX macros, not references
NON_CITES = {
    "placemarginal", "sidenotes", "author", "date", "maketitle", "title",
    "media", "font-face", "keyframes", "supports",
}

FIELD_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*=\s*(\{.*\}|\".*\"|[^,]+)\s*,\s*$")
ENTRY_START_RE = re.compile(r"^\s*@([A-Za-z]+)\s*\{\s*([^,]+)\s*,\s*$")
ENTRY_END_RE = re.compile(r"^\s*}\s*$")


@dataclass
class Entry:
    key: str
    fields: dict[str, str]
    format_errors: list[tuple[int, str]]


@dataclass
class TestResult:
    name: str
    ok: bool
    detail: str = ""
    # Advisory results describe *coverage* of the bibliography rather than its
    # correctness: how many entries carry a locator, how many are still cited.
    # They are real gaps worth seeing, but they close by doing research, not by
    # fixing a bug — so they must not gate a commit. A check that is always red
    # stops being read.
    advisory: bool = False


def parse_entries(lines: list[str]) -> tuple[list[Entry], list[str]]:
    entries: list[Entry] = []
    errors: list[str] = []
    current: Entry | None = None

    for idx, line in enumerate(lines, start=1):
        if current is None:
            match = ENTRY_START_RE.match(line)
            if match:
                key = match.group(2).strip()
                current = Entry(key=key, fields={}, format_errors=[])
            continue

        if ENTRY_END_RE.match(line):
            entries.append(current)
            current = None
            continue

        if not line.strip() or line.lstrip().startswith("%"):
            continue

        field_match = FIELD_RE.match(line)
        if not field_match:
            current.format_errors.append((idx, line.rstrip("\n")))
            continue

        field_name = field_match.group(1).lower()
        raw_value = field_match.group(2)
        if raw_value.startswith("{") and raw_value.endswith("}"):
            value = raw_value[1:-1]
        elif raw_value.startswith('"') and raw_value.endswith('"'):
            value = raw_value[1:-1]
        else:
            value = raw_value
        current.fields[field_name] = value

    if current is not None:
        errors.append(f"Unclosed entry for citekey '{current.key}'.")

    return entries, errors


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def summarize_keys(keys: list[str], limit: int = 6) -> str:
    if not keys:
        return ""
    shown = ", ".join(keys[:limit])
    if len(keys) > limit:
        shown += f", +{len(keys) - limit} more"
    return shown


def run_tests(entries: list[Entry]) -> list[TestResult]:
    results: list[TestResult] = []

    keys = [entry.key for entry in entries]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    results.append(
        TestResult(
            name="Duplicate citekeys",
            ok=not duplicates,
            detail=f" ({len(keys) - len(duplicates)}/{len(keys)})"
            + (f" {summarize_keys(duplicates)}" if duplicates else ""),
        )
    )

    formatting_errors: list[str] = []
    for entry in entries:
        for line_no, line in entry.format_errors:
            formatting_errors.append(f"L{line_no}:{entry.key}")
    bad_entries = len({entry.key for entry in entries if entry.format_errors})
    results.append(
        TestResult(
            name="One field per line + trailing comma",
            ok=not formatting_errors,
            detail=f" ({len(entries) - bad_entries}/{len(entries)})"
            + (f" {summarize_keys(formatting_errors)}" if formatting_errors else ""),
        )
    )

    # A `howpublished = {\\url{...}}` is how @misc entries (pricing pages,
    # blog posts) carry their locator, so it counts as one.
    def has_locator(entry: Entry) -> bool:
        if any(field in entry.fields for field in ("url", "doi", "eprint")):
            return True
        return "http" in entry.fields.get("howpublished", "")

    missing_locator = sorted(entry.key for entry in entries if not has_locator(entry))
    locator_total = len(entries)
    locator_pass = locator_total - len(missing_locator)
    results.append(
        TestResult(
            name="Source locator present (url/doi/eprint)",
            advisory=True,
            ok=not missing_locator,
            detail=(
                f" ({locator_pass}/{locator_total})"
                + (f" {summarize_keys(missing_locator)}" if missing_locator else "")
            ),
        )
    )

    abstract_too_long: list[str] = []
    abstract_checked = 0
    for entry in entries:
        abstract = entry.fields.get("abstract", "").strip()
        if not abstract or abstract.lower().startswith("abstract unavailable"):
            continue
        abstract_checked += 1
        if word_count(abstract) > MAX_ABSTRACT_WORDS:
            abstract_too_long.append(entry.key)
    abstract_pass = abstract_checked - len(abstract_too_long)
    results.append(
        TestResult(
            name=f"Abstract length <= {MAX_ABSTRACT_WORDS} words",
            ok=not abstract_too_long,
            detail=(
                f" ({abstract_pass}/{abstract_checked})"
                + (f" {summarize_keys(abstract_too_long)}" if abstract_too_long else "")
            ),
        )
    )

    abstract_source_mismatch: list[str] = []
    abstract_source_total = 0
    for entry in entries:
        abstract = entry.fields.get("abstract", "").strip()
        abstract_source = entry.fields.get("abstract_source", "").strip()
        if abstract_source:
            abstract_source_total += 1
        if abstract_source and (not abstract or abstract.lower().startswith("abstract unavailable")):
            abstract_source_mismatch.append(entry.key)
    abstract_source_pass = abstract_source_total - len(abstract_source_mismatch)
    results.append(
        TestResult(
            name="abstract_source only when abstract is present",
            ok=not abstract_source_mismatch,
            detail=(
                f" ({abstract_source_pass}/{abstract_source_total})"
                + (f" {summarize_keys(abstract_source_mismatch)}" if abstract_source_mismatch else "")
            ),
        )
    )

    arxiv_mismatches: list[str] = []
    arxiv_total = 0
    for entry in entries:
        eprint = entry.fields.get("eprint", "").strip()
        archiveprefix = entry.fields.get("archiveprefix", "").strip().lower()
        if not eprint or archiveprefix != "arxiv":
            continue
        arxiv_total += 1
        url = entry.fields.get("url", "")
        expected = f"arxiv.org/pdf/{eprint}.pdf"
        if expected not in url:
            arxiv_mismatches.append(entry.key)
    arxiv_pass = arxiv_total - len(arxiv_mismatches)
    results.append(
        TestResult(
            name="arXiv eprints use arxiv.org/pdf/<id>.pdf URLs",
            ok=not arxiv_mismatches,
            detail=(
                f" ({arxiv_pass}/{arxiv_total})"
                + (f" {summarize_keys(arxiv_mismatches)}" if arxiv_mismatches else "")
            ),
        )
    )

    text_missing: list[str] = []
    text_total = 0
    for entry in entries:
        text_url = entry.fields.get("text_url", "").strip()
        if not text_url:
            continue
        text_total += 1
        text_path = TEXT_ARCHIVE_DIR / f"{entry.key}.txt"
        if not text_path.exists():
            text_missing.append(entry.key)
            continue
        try:
            content = text_path.read_text(encoding="utf-8")
        except Exception:
            text_missing.append(entry.key)
            continue
        if len(content.strip()) < 200:
            text_missing.append(entry.key)

    text_pass = text_total - len(text_missing)
    results.append(
        TestResult(
            name="text_url has local text archive",
            ok=not text_missing,
            detail=(
                f" ({text_pass}/{text_total})"
                + (f" {summarize_keys(text_missing)}" if text_missing else "")
            ),
        )
    )

    missing_year = sorted(entry.key for entry in entries if not entry.fields.get("year", "").strip())
    year_total = len(entries)
    year_pass = year_total - len(missing_year)
    results.append(
        TestResult(
            name="Year present",
            ok=not missing_year,
            detail=(
                f" ({year_pass}/{year_total})"
                + (f" {summarize_keys(missing_year)}" if missing_year else "")
            ),
        )
    )

    cited = cited_citekeys()
    uncited = sorted(entry.key for entry in entries if entry.key not in cited)
    cited_total = len(entries)
    cited_pass = cited_total - len(uncited)
    results.append(
        TestResult(
            name="Entry is cited by some document",
            advisory=True,
            ok=not uncited,
            detail=(
                f" ({cited_pass}/{cited_total})"
                + (f" {summarize_keys(uncited)}" if uncited else "")
            ),
        )
    )

    return results


def cited_citekeys() -> set[str]:
    """Every citekey referenced by any document listed in CITING_DOCS."""
    keys: set[str] = set()
    for name in CITING_DOCS:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        raw = re.findall(r"@([A-Za-z][A-Za-z0-9:_-]*)", text)
        keys |= {k.rstrip(":_-") for k in raw}
    return keys - NON_CITES


def run_bibclean(bib_path: Path) -> TestResult | None:
    """Lint with bibclean, when a compatible bibclean is available.

    Returns None (skip) rather than a failure when the tool is missing or too
    old to accept our flags. Which switches bibclean supports varies by build
    — Ubuntu's rejects -no-fix-braces, which is how this check spent three CI
    runs reporting a tool incompatibility as though the bibliography were
    broken. A linter we cannot run is a skip; only what it actually says about
    the file is a result.
    """
    bibclean = shutil.which("bibclean")
    if not bibclean:
        return None

    # These switches suppress bibclean's cosmetic reformatting suggestions so
    # that only real problems surface. Which switches a build accepts varies:
    # Ubuntu's rejects -no-fix-braces. Running it *without* them would report
    # the very noise they exist to suppress, so an incompatible build is a
    # skip, not a pass and not a failure — we cannot interpret its output.
    flags = [
        "-no-prettyprint", "-max-width", "0", "-no-align-equals",
        "-no-fix-braces", "-no-fix-font-changes", "-no-fix-names",
        "-no-fix-initials",
    ]
    proc = subprocess.run([bibclean, *flags, str(bib_path)], capture_output=True, text=True)
    stderr = (proc.stderr or "").strip()

    if "Unrecognized option switch" in stderr:
        return None

    if proc.returncode != 0:
        detail = f" (exit {proc.returncode})"
        if stderr:
            detail += f" {stderr.splitlines()[0]}"
        return TestResult(name="bibclean lint", ok=False, detail=detail)
    if stderr:
        return TestResult(name="bibclean lint", ok=False, detail=f" ({stderr.splitlines()[0]})")
    return TestResult(name="bibclean lint", ok=True)


def format_block(results: list[TestResult], timestamp: str) -> str:
    all_ok = all(r.ok for r in results if not getattr(r, "advisory", False))
    lines = [
        BEGIN_MARKER,
        f"% Last run: {timestamp}",
        f"% Status: {'PASS' if all_ok else 'FAIL'}",
    ]
    for result in results:
        if result.ok:
            status = "PASS"
        else:
            status = "INFO" if getattr(result, "advisory", False) else "FAIL"
        detail = result.detail or ""
        counts = ""
        if detail.startswith(" (") and "/" in detail:
            counts = detail.split(")", 1)[0].strip(" (")
            detail = detail.split(")", 1)[1].strip()
        prefix = f"[{status} {counts}]".strip() if counts else f"[{status}]"
        suffix = f" {detail}" if detail else ""
        lines.append(f"% - {prefix} {result.name}{suffix}")
    lines.append(END_MARKER)
    return "\n".join(lines)


def update_block(text: str, block: str) -> str:
    if BEGIN_MARKER in text and END_MARKER in text:
        pattern = re.compile(
            re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
            re.DOTALL,
        )
        return pattern.sub(block, text)

    lines = text.splitlines()
    insert_at = 0
    for idx, line in enumerate(lines):
        if line.startswith("%") or not line.strip():
            insert_at = idx + 1
        else:
            break
    block_lines = block.splitlines()
    new_lines = lines[:insert_at] + block_lines + [""] + lines[insert_at:]
    return "\n".join(new_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bib",
        default=str(REPO_ROOT / "stylized-facts.bib"),
        help="Path to ai.bib",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write the machine-generated block; exit non-zero on failure.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output with test results.",
    )
    args = parser.parse_args()

    bib_path = Path(args.bib)
    text = bib_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    entries, parse_errors = parse_entries(lines)
    results = run_tests(entries)
    bibclean_result = run_bibclean(bib_path)
    if bibclean_result is not None:
        results.append(bibclean_result)

    if parse_errors:
        results.insert(
            0,
            TestResult(
                name="BibTeX parse errors",
                ok=False,
                detail=f" ({summarize_keys(parse_errors)})",
            ),
        )

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = format_block(results, timestamp)

    if not args.check:
        updated = update_block(text, block)
        if updated != text:
            bib_path.write_text(updated, encoding="utf-8")

    if args.json:
        payload = {
            "timestamp": timestamp,
            "results": [
                {
                    "name": result.name,
                    "ok": result.ok,
                    "detail": result.detail,
                    "advisory": bool(getattr(result, "advisory", False)),
                }
                for result in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            if result.ok:
                status = "PASS"
            else:
                status = "INFO" if getattr(result, "advisory", False) else "FAIL"
            print(f"{status}: {result.name}{result.detail}")

    return 0 if all(r.ok for r in results if not getattr(r, "advisory", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
