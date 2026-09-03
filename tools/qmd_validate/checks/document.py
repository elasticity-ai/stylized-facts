"""Checks of a document against itself and the repo, shared by every document.

These were written for the paper and are reused by the book (see
tools/qmd_validate/docs/). They read only `references/text/`, never
`references/pdf/` — the PDFs are absent in CI by design (AGENTS.md).

  internal        figures exist, attributions resolve, no build residue, no
                  TODO in rendered prose
  source-backed   numbers the document attributes to a paper appear in that
                  paper's archived fulltext
"""
from __future__ import annotations

import re

from ..core import TestResult, ValidationContext
from . import bib
from .quotes import strip_noise


# --------------------------------------------------------------- internal --
def check_images_exist(ctx: ValidationContext) -> TestResult:
    """Every referenced image is on disk.

    Paths are resolved the way Quarto resolves them — relative to the document
    — and then, for documents that sit at the repo root, relative to the root.
    """
    refs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", ctx.qmd_text)
    base = ctx.qmd_path if ctx.qmd_path.is_dir() else ctx.qmd_path.parent
    missing = sorted({r for r in refs if not ((base / r).exists() or (ctx.repo_root / r).exists())})
    return TestResult(
        name="Referenced images exist on disk",
        ok=not missing,
        category="internal",
        detail=f"({len(refs) - len(missing)}/{len(refs)})"
        + (f" missing: {missing[:6]}" if missing else ""),
        meta={"missing": missing},
    )


def check_image_attribution(ctx: ValidationContext) -> TestResult:
    """Figure captions crediting a paper cite a key that resolves.

    Most figures are screenshots from a cited paper, captioned
    `![From @key](...)`. A caption naming a key the bibliography does not have
    is a broken credit on someone else's figure, which matters more than an
    ordinary broken citation.
    """
    try:
        keys = bib.bib_keys(ctx.bib_path, ctx.bib_tests_path)
    except Exception as exc:
        return TestResult(name="Figure attributions resolve", ok=False,
                          category="internal", detail=f"(error: {exc})")

    captions = re.findall(r"!\[([^\]]*)\]\(", ctx.qmd_text)
    attributed = 0
    broken: list[str] = []
    for caption in captions:
        found = [k.rstrip(":_-") for k in re.findall(r"@([A-Za-z][A-Za-z0-9:_-]*)", caption)]
        found = [k for k in found if k not in bib.NON_CITES]
        if not found:
            continue
        attributed += 1
        for key in found:
            if key not in keys:
                broken.append(f"@{key} in “{caption[:50]}”")

    uncredited = len(captions) - attributed
    return TestResult(
        name="Figure attributions resolve",
        ok=not broken,
        category="internal",
        detail=f"({attributed - len(broken)}/{attributed} credited figures resolve, "
               f"{uncredited} figures carry no credit)"
        + (" | " + "; ".join(broken[:5]) if broken else ""),
        meta={"broken": broken, "attributed": attributed, "uncredited": uncredited},
    )


def check_no_accidental_citations(ctx: ValidationContext) -> TestResult:
    """No stray `@token` that pandoc will try to resolve as a citation.

    The citekey check only looks at keys starting with a letter, because that
    is what a real citekey looks like. Pandoc is less fussy, so prose like

        | Long context | Needle | 50% @ 128K | 99.7% @1M |

    makes it hunt for a reference called `1M` and emit
    "Citeproc: citation 1M not found" — a warning buried in render output that
    nothing was watching. The neighbouring cell writes "@ 128K" with a space
    and is fine, which is the fix.
    """
    text = strip_noise(ctx.qmd_text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", text)  # drop link targets (emails, urls)
    hits = []
    for m in re.finditer(r"(?<![\w@/.])@(\d[\w:-]*)", text):
        line = text.count("\n", 0, m.start()) + 1
        hits.append(f"L{line}: @{m.group(1)}")
    return TestResult(
        name="No accidental @citations in prose",
        ok=not hits,
        category="internal",
        detail="; ".join(hits[:6]) or "(clean)",
        meta={"hits": hits},
    )


def check_no_build_residue(ctx: ValidationContext) -> TestResult:
    """No merge-conflict markers or stray rendering artifacts in the source.

    The repo shipped a committed file with conflict markers in it once; this
    is the cheap guard against a repeat.
    """
    problems: list[str] = []
    for pattern, label in [
        (r"^<{7} ", "merge conflict marker (<<<<<<<)"),
        (r"^>{7} ", "merge conflict marker (>>>>>>>)"),
        (r"^={7}$", "merge conflict marker (=======)"),
    ]:
        for m in re.finditer(pattern, ctx.qmd_text, flags=re.MULTILINE):
            line = ctx.qmd_text.count("\n", 0, m.start()) + 1
            problems.append(f"L{line}: {label}")
    return TestResult(
        name="No merge-conflict markers in source",
        ok=not problems,
        category="internal",
        detail="; ".join(problems[:5]) or "(clean)",
        meta={"problems": problems},
    )


def check_todos_are_hidden(ctx: ValidationContext) -> TestResult:
    """Working notes stay inside HTML comments, out of the rendered output.

    The documents carry research notes and TODO lists in `<!-- -->` blocks.
    That is fine — they are invisible to readers. A TODO that has escaped into
    live prose is not, and will render into the circulated PDF.
    """
    visible = strip_noise(ctx.qmd_text)
    hits: list[str] = []
    for m in re.finditer(r"\b(TODO|FIXME|XXX|TK)\b", visible):
        line = visible.count("\n", 0, m.start()) + 1
        context = visible.splitlines()[line - 1].strip()[:70] if line - 1 < len(visible.splitlines()) else ""
        hits.append(f"L{line}: {context}")
    hidden = len(re.findall(r"\b(TODO|FIXME|XXX)\b", ctx.qmd_text)) - len(hits)
    return TestResult(
        name="No TODO markers in rendered prose",
        ok=not hits,
        category="internal",
        detail=(f"({hidden} in comments, fine)" if not hits else "; ".join(hits[:5])),
        meta={"visible": hits, "hidden": hidden},
    )


def check_archive_coverage(ctx: ValidationContext) -> TestResult:
    """Report how much of the bibliography is locally archived.

    Informational: coverage is limited by what is open-access, so this never
    fails. It exists so the number is visible in the same report as the checks
    that depend on it — a quote check reading "3 keys not archived" means
    something different at 90% coverage than at 40%.
    """
    archive = ctx.repo_root / "references" / "text"
    cited = bib.extract_citekeys(ctx.qmd_text)
    have = {p.stem for p in archive.glob("*.txt")} if archive.exists() else set()
    covered = cited & have
    pct = (100 * len(covered) // len(cited)) if cited else 0
    return TestResult(
        name="Local archive coverage of cited works",
        ok=True,
        category="internal",
        detail=f"({len(covered)}/{len(cited)} cited keys have fulltext, {pct}%)",
        meta={"missing": sorted(cited - have)},
    )


# ----------------------------------------------------------- source-backed --
def numeric_claims(claims: list[tuple[str, list[str], list[str]]]):
    """Numbers the document attributes to a paper appear in that paper.

    `claims` is a list of (citekey, needles in document, needles in source);
    see tools/qmd_validate/claims.py.
    """

    def _check(ctx: ValidationContext) -> TestResult:
        archive = ctx.repo_root / "references" / "text"
        doc = " ".join(strip_noise(ctx.qmd_text).split())

        problems: list[str] = []
        skipped: list[str] = []
        checked = 0

        for key, in_doc, in_source in claims:
            for needle in in_doc:
                if needle.lower() not in doc.lower():
                    problems.append(f"@{key}: document no longer says “{needle}”")

            path = archive / f"{key}.txt"
            if not path.exists():
                skipped.append(key)
                continue
            source = " ".join(path.read_text(encoding="utf-8", errors="replace").split())
            checked += 1
            for needle in in_source:
                if needle.lower() not in source.lower():
                    problems.append(f"@{key}: “{needle}” not found in the archived source")

        return TestResult(
            name="Numeric claims traced to their cited source",
            ok=not problems,
            category="source-backed",
            detail=f"({checked}/{len(claims)} claims source-checked"
            + (f", {len(skipped)} not archived: {skipped}" if skipped else "")
            + ")"
            + (" | " + "; ".join(problems[:5]) if problems else ""),
            meta={"problems": problems, "skipped": skipped},
        )

    _check.__name__ = "check_numeric_claims"
    return _check
