"""Validation checks for stylized-facts.qmd, the canonical paper.

The document is a list of ~50 stylized facts, each asserted as a section
heading and backed by cited papers, quotes, and figures lifted from those
papers. So the drift this plugin is built to catch is a claim, quote, or
figure attribution separating from the source that supports it — the citekey
keeps resolving and the prose keeps reading well while the evidence moves.

Check categories:

  source-backed   text in the document is matched against the archived
                  fulltext of the paper it is attributed to
                  (references/text/, built by tools/fetch_papers.py)
  internal        the document is checked against itself and the repo:
                  figures exist, attributions resolve, no build residue
  programmatic    shared bibliography checks

Every check reads only `references/text/`, never `references/pdf/`. The PDFs
are git-ignored, so a check that touched them would pass locally and fail in
CI. See AGENTS.md.
"""
from __future__ import annotations

import re

from tools.qmd_validate.checks import bib, quotes
from tools.qmd_validate.core import TestResult, ValidationContext
from tools.qmd_validate.checks.quotes import strip_noise, tokens, find_run


# --------------------------------------------------------------- internal --
def check_images_exist(ctx: ValidationContext) -> TestResult:
    """Every referenced image is on disk."""
    refs = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", ctx.qmd_text)
    missing = sorted({r for r in refs if not (ctx.repo_root / r).exists()})
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

    Most figures in this document are screenshots from a cited paper, captioned
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

    The document carries research notes and TODO lists in `<!-- -->` blocks.
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


# ----------------------------------------------------------- source-backed --
# Numeric claims the document asserts and attributes to a source. Each entry
# is (citekey, [strings that must appear in the document], [strings that must
# appear in that source's archived fulltext]).
#
# This is the analogue of a recompute-from-CSV check for a document whose
# evidence is textual: it pins a number to the source that licenses it, so
# that editing one without the other fails. Keys with no local archive are
# skipped rather than failed — see the module docstring.
CLAIMS = [
    (
        "ruan2024observational",
        ["80% of the variation"],
        ["80%"],
    ),
    (
        "kipnis2025metabench",
        ["0.93"],
        ["0.93"],
    ),
    (
        "owen2024predictable",
        ["6 percentage points"],
        ["6 percentage points"],
    ),
    (
        "hoffmann2022computeoptimal",
        ["chinchilla"],
        ["Chinchilla"],
    ),
]


def check_numeric_claims(ctx: ValidationContext) -> TestResult:
    """Numbers the document attributes to a paper appear in that paper."""
    archive = ctx.repo_root / "references" / "text"
    doc = " ".join(strip_noise(ctx.qmd_text).split())

    problems: list[str] = []
    skipped: list[str] = []
    checked = 0

    for key, in_doc, in_source in CLAIMS:
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
        detail=f"({checked}/{len(CLAIMS)} claims source-checked"
        + (f", {len(skipped)} not archived: {skipped}" if skipped else "")
        + ")"
        + (" | " + "; ".join(problems[:5]) if problems else ""),
        meta={"problems": problems, "skipped": skipped},
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


def doc_checks():
    return [
        bib.citekeys_resolve(),
        bib.bib_conventions(),
        quotes.quotes_verified(),
        check_numeric_claims,
        check_images_exist,
        check_image_attribution,
        check_no_build_residue,
        check_todos_are_hidden,
        check_archive_coverage,
    ]


# The framework looks for `post_checks`; keep both names so the plugin works
# whichever the runner asks for.
post_checks = doc_checks
