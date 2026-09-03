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

The check functions themselves live in tools/qmd_validate/checks/document.py
so the book (tools/qmd_validate/docs/book.py) runs the same ones. The numeric
claims are in tools/qmd_validate/claims.py, shared likewise.

Every check reads only `references/text/`, never `references/pdf/`. The PDFs
are absent in CI, so a check that touched them would pass locally and fail
there. See AGENTS.md.
"""
from __future__ import annotations

from tools.qmd_validate.checks import bib, document, quotes
from tools.qmd_validate.claims import CLAIMS


def doc_checks():
    return [
        bib.citekeys_resolve(),
        bib.bib_conventions(),
        quotes.quotes_verified(),
        document.numeric_claims(CLAIMS),
        document.check_images_exist,
        document.check_image_attribution,
        document.check_no_accidental_citations,
        document.check_no_build_residue,
        document.check_todos_are_hidden,
        document.check_archive_coverage,
    ]


# The framework looks for `post_checks`; keep both names so the plugin works
# whichever the runner asks for.
post_checks = doc_checks
