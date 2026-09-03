from __future__ import annotations

import importlib.util
import re
import sys
from functools import lru_cache
from pathlib import Path

from ..core import TestResult, ValidationContext
from ..util import read_text

# citekey-like tokens that are LaTeX macros or CSS, not references. The
# paper's PDF header block defines \@title/\@author/\@date and uses the
# sidenotes package; the HTML header carries @media / @font-face rules.
NON_CITES = {
    "placemarginal", "sidenotes", "author", "date", "maketitle", "title",
    "media", "font-face", "keyframes", "supports", "import", "charset",
}


def extract_citekeys(text: str) -> set[str]:
    raw = re.findall(r"@([A-Za-z][A-Za-z0-9:_-]*)", text)
    # Pandoc allows :_- inside a citekey but not trailing, so an in-text
    # citation used as a sentence subject ("@key: claim") ends the key at the
    # colon. Mirrors tools/fetch_papers.py.
    keys = {k.rstrip(":_-") for k in raw}
    return {k for k in keys if k not in NON_CITES}


@lru_cache(maxsize=8)
def _load_bib_tests_module(path: Path):
    spec = importlib.util.spec_from_file_location("sf_bib_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {path}.")
    module = importlib.util.module_from_spec(spec)
    # register before exec: @dataclass resolves annotations via sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def bib_keys(bib_path: Path, bib_tests_path: Path) -> set[str]:
    bib_tests = _load_bib_tests_module(bib_tests_path)
    text = read_text(bib_path)
    entries, parse_errors = bib_tests.parse_entries(text.splitlines())
    if parse_errors:
        raise AssertionError(f"bib parse errors: {parse_errors}")
    return {entry.key for entry in entries}


def citekeys_resolve(allow_none: bool = False) -> callable:
    """Every `@key` in the document is an entry in the bibliography.

    A document with no citations at all is suspicious for the paper (the
    check would be vacuous) but normal for a book chapter that is a part page
    or an unwritten stub, hence `allow_none`.
    """

    def _check(ctx: ValidationContext) -> TestResult:
        citekeys = extract_citekeys(ctx.qmd_text)
        name = f"Citekeys resolve in {ctx.bib_path.name}"
        if not citekeys:
            return TestResult(name=name, ok=allow_none, detail="(0/0, no citekeys found)",
                              meta={"missing": [], "citekeys": 0})
        try:
            keys = bib_keys(ctx.bib_path, ctx.bib_tests_path)
        except Exception as exc:
            return TestResult(name=name, ok=False, detail=f"(error: {exc})")
        missing = sorted(citekeys - keys)
        detail = f"({len(citekeys) - len(missing)}/{len(citekeys)})"
        if missing:
            detail += f" missing: {missing[:10]}{' ...' if len(missing) > 10 else ''}"
        return TestResult(
            name=name,
            ok=not missing,
            detail=detail,
            meta={"missing": missing, "citekeys": len(citekeys)},
        )

    return _check


def bib_conventions() -> callable:
    def _check(ctx: ValidationContext) -> TestResult:
        try:
            bib_tests = _load_bib_tests_module(ctx.bib_tests_path)
        except Exception as exc:
            return TestResult(name="Bibliography tests", ok=False, detail=f"(error loading bib tests: {exc})")

        try:
            text = read_text(ctx.bib_path)
            entries, parse_errors = bib_tests.parse_entries(text.splitlines())
            results = bib_tests.run_tests(entries)
            bibclean_result = bib_tests.run_bibclean(ctx.bib_path)
            if bibclean_result is not None:
                results.append(bibclean_result)
            if parse_errors:
                results.insert(
                    0,
                    bib_tests.TestResult(
                        name="BibTeX parse errors",
                        ok=False,
                        detail=f" ({bib_tests.summarize_keys(parse_errors)})",
                    ),
                )

            def advisory(r) -> bool:
                return bool(getattr(r, "advisory", False))

            # Coverage gaps (locators, uncited entries) are reported but do
            # not fail — see the `advisory` note in the bib tests.
            ok = all(bool(getattr(r, "ok", False)) for r in results if not advisory(r))
            passed = sum(1 for r in results if getattr(r, "ok", False))
            failed = [getattr(r, "name", "") for r in results
                      if not getattr(r, "ok", False) and not advisory(r)]
            gaps = []
            for r in results:
                if getattr(r, "ok", False) or not advisory(r):
                    continue
                count = re.match(r"\s*\((\d+/\d+)\)", getattr(r, "detail", "") or "")
                gaps.append(f"{getattr(r, 'name', '')} {count.group(1) if count else ''}".strip())

            detail = f"({passed}/{len(results)})"
            if failed:
                detail += " failing: " + "; ".join(failed)
            if gaps:
                detail += " | coverage: " + "; ".join(gaps)
            return TestResult(
                name="Bibliography tests",
                ok=ok,
                detail=detail,
                meta={
                    "results": [
                        {
                            "name": getattr(r, "name", ""),
                            "ok": bool(getattr(r, "ok", False)),
                            "detail": getattr(r, "detail", ""),
                        }
                        for r in results
                    ]
                },
            )
        except Exception as exc:
            return TestResult(name="Bibliography tests", ok=False, detail=f"(error: {exc})")

    return _check
