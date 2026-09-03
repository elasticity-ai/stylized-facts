"""Validation checks for the Quarto book in book/ — one question per chapter.

The book is the paper restructured: every claim in stylized-facts.qmd became a
question, answered by a human-written `<slug>.qmd` with an LLM-written
`<slug>.llm.qmd` literature summary included at its end. It shares the
paper's bibliography and images (book/images -> ../images), so it is exposed
to the same drift the paper's plugin catches, spread over ~100 files.

This is a *collection* plugin: `documents()` names the files, `post_checks()`
run on each file and are merged into one result per check (counts summed,
failures listed with their filename), and `collection_checks()` run once over
the concatenation of every file — for checks that only make sense on the
whole, such as the numeric claims that live in one chapter each.

Every check reads only `references/text/`, never `references/pdf/`. See
AGENTS.md.
"""
from __future__ import annotations

from pathlib import Path

from tools.qmd_validate.checks import bib, document, quotes
from tools.qmd_validate.claims import CLAIMS


def documents(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "book").glob("*.qmd"))


def post_checks():
    """Per file. A chapter with no citation is fine (part pages, stubs)."""
    return [
        bib.citekeys_resolve(allow_none=True),
        quotes.quotes_verified(),
        document.check_images_exist,
        document.check_image_attribution,
        document.check_no_accidental_citations,
        document.check_no_build_residue,
        document.check_todos_are_hidden,
    ]


def collection_checks():
    """Once, over the whole book."""
    return [
        bib.bib_conventions(),
        document.numeric_claims(CLAIMS),
        document.check_archive_coverage,
    ]
