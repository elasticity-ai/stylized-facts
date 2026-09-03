"""Numeric claims the paper asserts and attributes to a source.

Each entry is (citekey, [strings that must appear in the document], [strings
that must appear in that source's archived fulltext]).

This is the analogue of a recompute-from-CSV check for a document whose
evidence is textual: it pins a number to the source that licenses it, so that
editing one without the other fails. Keys with no local archive are skipped
rather than failed.

Shared by the paper (stylized-facts.qmd) and the book (book/), which carry the
same claims; the book check runs over the concatenation of its chapters.
"""

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
