"""Verify that quotes in a document appear in the cited source.

This is the check the local paper archive exists to support. A quote drifting
from its source across edits is the failure mode a bibliography cannot catch:
the citekey still resolves, the sentence still reads well, and the words are
no longer the author's.

Method
------
Extract every quoted passage, attribute it to the nearest preceding citekey,
and look for it in references/text/<citekey>.txt.

Matching is token-based rather than substring-based, because `pdftotext`
output cannot be matched literally:

  - it hard-wraps lines, so a quote spanning a line break has newlines in it
  - it hyphenates across those breaks ("perfor-\\nmance")
  - footnote and superscript markers land inline as bare digits
    ("for low levels\\u00b3 of automation" extracts as "low levels 3 of automation")

So both sides are reduced to lowercase alphabetic tokens with pure-digit
tokens dropped, and the quote must appear as a contiguous token run in the
source. Typographic quotes, dashes, and ligatures are folded first.

Severity
--------
Only a quote that is *checkable and absent* fails: the citekey resolves, the
source text is on disk, and the words are not in it. Quotes with no local
archive, or with no attributable citekey, are reported but do not fail — the
archive is incomplete by nature (paywalled sources) and a document may quote
someone who is not a cited paper.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..core import TestResult, ValidationContext
from .bib import NON_CITES

# A quote shorter than this is too likely to collide by chance to be worth
# checking, and too likely to be a scare-quote rather than a quotation.
MIN_QUOTE_WORDS = 8

# How far back to look for the citekey a quote belongs to. Quotes in this
# document sit in the same paragraph as their attribution.
ATTRIBUTION_WINDOW = 600


@dataclass(frozen=True)
class Quote:
    text: str
    citekey: str | None
    form: str
    line: int


# ------------------------------------------------------------------ cleaning
def strip_noise(text: str) -> str:
    """Remove regions that contain quote-like punctuation but no prose.

    Replaces each region with an equal number of newlines so that line
    numbers reported to the user still line up with the source file.
    """

    def blank(match: re.Match) -> str:
        return "\n" * match.group(0).count("\n")

    # YAML frontmatter (contains the abstract, LaTeX macros, CSS)
    text = re.sub(r"\A---\n.*?\n---\n", blank, text, flags=re.DOTALL)
    # HTML comments (research notes, TODO lists) must go BEFORE code fences.
    # This document comments out a whole tikz block:
    #     <!-- ```{tikz}
    #     ...
    #     ``` -->
    # Strip fences first and the trailing "``` -->" reads as an *opening*
    # fence, which then pairs with the next real one and blanks everything
    # between — 600 lines of this document, silently.
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.DOTALL)
    # fenced code blocks
    text = re.sub(r"^```.*?^```", blank, text, flags=re.DOTALL | re.MULTILINE)
    # inline code and display math
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\$\$.*?\$\$", blank, text, flags=re.DOTALL)
    # Inline math inside a quote is content that cannot be token-matched
    # against pdftotext output ($n = 10^l$ extracts as "n = 10l"). Leave an
    # ellipsis so it acts as a fragment boundary rather than silently
    # deleting a word and breaking the surrounding run.
    text = re.sub(r"\$[^$\n]*\$", " … ", text)
    return text


def fold(text: str) -> str:
    """Normalize typography so quotes and sources compare on equal terms."""
    text = unicodedata.normalize("NFKC", text)
    for a, b in [
        ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
        ("–", "-"), ("—", "-"), ("−", "-"), ("‐", "-"),
        ("ﬁ", "fi"), ("ﬂ", "fl"), (" ", " "),
        # A document writing "14%" quotes a paper writing "14 percent".
        # Digits are dropped downstream, so without this the symbol form
        # loses a word the prose form keeps, and the run breaks there.
        ("%", " percent "),
    ]:
        text = text.replace(a, b)
    return text


def squash(text: str) -> str:
    """Reduce text to a bare lowercase letter string.

    Every separator is discarded, which is what makes matching survive
    `pdftotext`. Its output disagrees with the source document about all of
    them, and inconsistently within a single file:

        source "sample-\\nefficient"  extracts as  "sampleefficient"
        source "BIG-Bench"            extracts as  "BIGBench"
        document                      writes       "sample-efficient"

    Squashing maps all three to `sampleefficient`, so hyphenation, line
    wrapping, and lost spaces stop mattering. Digits go too, which disposes of
    footnote and superscript markers landing inline ("low levels\\u00b3 of"
    extracts as "low levels 3 of"). Numbers inside quotes are therefore not
    verified here — that is what the numeric-claims check is for.
    """
    text = fold(text)
    return "".join(c for c in text.lower() if c.isalpha())


def tokens(text: str) -> str:
    """Alias kept for callers that read this as "the comparable form"."""
    return squash(text)


# ---------------------------------------------------------------- extraction
def _citekey_before(text: str, pos: int) -> str | None:
    """The citekey a quote at `pos` belongs to, or None if unclear.

    A quote is only attributed to a citekey when nothing closer claims it.
    This document routinely quotes sources that are *links* rather than bib
    entries — a blog post, a shared Google Doc — and those quotes sit a few
    words after some other paper's citekey:

        @mirzadeh2024gsm find that ... However [Andrew Mayne (2024)](url)
        shows that this penalty disappears when the prompt included "..."

    Attributing that quote to @mirzadeh2024gsm and then failing to find it in
    Mirzadeh's paper is a false alarm about a correctly-sourced quote. So an
    intervening markdown link disqualifies the citekey.
    """
    window = text[max(0, pos - ATTRIBUTION_WINDOW): pos]
    matches = list(re.finditer(r"@([A-Za-z][A-Za-z0-9:_-]*)", window))
    for m in reversed(matches):
        key = m.group(1).rstrip(":_-")
        if key in NON_CITES:
            continue
        if re.search(r"\]\(\s*(?:https?:|www\.)", window[m.end():]):
            return None  # a nearer, non-bibliographic source claims it
        return key
    return None


def _paired_spans(line: str, offset: int) -> list[tuple[str, int]]:
    """Quoted spans in a line, paired left-to-right.

    Pairing matters: a regex with a minimum length silently mis-pairs. In

        proposed five "levels of AGI", based on ... a *"wide range of ..."*

    a `"..{30,}.."` pattern skips the short first quote and then matches from
    its *closing* mark to the next opening one, capturing the unquoted prose
    between two real quotes. Taking marks in consecutive pairs cannot do that.
    An odd trailing mark (an unbalanced quote) is ignored.
    """
    marks = [i for i, ch in enumerate(line) if ch == '"']
    out = []
    for a, b in zip(marks[::2], marks[1::2]):
        # A quoted markdown link label — ["useful benchmarks ..."](url) — is
        # the title of the thing being linked, not a quotation from the paper
        # cited nearby. Checking it against that paper is a false alarm.
        if line[b + 1: b + 3] == "](" or line[max(0, a - 1): a] == "[":
            continue
        out.append((line[a + 1: b], offset + a))
    return out


def extract_quotes(qmd_text: str) -> list[Quote]:
    text = strip_noise(qmd_text)
    folded = fold(text)
    seen: set[str] = set()
    quotes: list[Quote] = []

    def add(body: str, start: int, form: str) -> None:
        body = body.strip()
        if len(body.split()) < MIN_QUOTE_WORDS:
            return
        norm = " ".join(tokens(body))
        if not norm or norm in seen:
            return
        seen.add(norm)
        quotes.append(
            Quote(
                text=" ".join(body.split()),
                citekey=_citekey_before(folded, start),
                form=form,
                line=folded.count("\n", 0, start) + 1,
            )
        )

    # 1. double-quoted passages, paired per line (typographic quotes folded)
    offset = 0
    for line in folded.splitlines(keepends=True):
        if not line.lstrip().startswith(">"):
            for body, pos in _paired_spans(line, offset):
                add(body, pos, "quoted")
        offset += len(line)

    # 2. blockquotes: contiguous runs of `>` lines
    for m in re.finditer(r"(?:^[ \t]*>[^\n]*\n?)+", folded, flags=re.MULTILINE):
        body = re.sub(r"^[ \t]*>[ \t]?", "", m.group(0), flags=re.MULTILINE)
        add(body.strip().strip('"'), m.start(), "blockquote")

    # 3. footnote bodies that are themselves a quotation
    for m in re.finditer(r"\^\[([^\]]{30,})\]", folded, flags=re.DOTALL):
        body = m.group(1).strip()
        if body.startswith('"') and body.rstrip(".").endswith('"'):
            add(body.strip('"'), m.start(), "footnote")

    return quotes


# --------------------------------------------------------------- verification
def find_run(needle: str, haystack: str) -> float:
    """Fraction of `needle` present in `haystack` as a contiguous run.

    1.0 means the fragment appears verbatim. Otherwise the longest prefix of
    the fragment that does appear is found by binary search, so a partial
    result reports how far the quote tracked the source before diverging.
    """
    if not needle:
        return 0.0
    if needle in haystack:
        return 1.0
    lo, hi = 0, len(needle)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if needle[:mid] in haystack:
            lo = mid
        else:
            hi = mid - 1
    return lo / len(needle)


# Scholarly quotes are not contiguous runs of the source. Two conventions
# interrupt the run, and both are *boundaries*, not deletions:
#
#   "focus on X ... humans retain the power"    elision of intervening text
#   "deploying [human-level AI] can lead"       editorial insertion
#
# The insertion case is why deletion is wrong: the source reads "deploying
# HLAI can lead", so dropping the bracket leaves "deploying can lead", which
# matches nothing. Splitting there matches both sides.
BOUNDARY_RE = re.compile(r"\s*(?:\.\s*\.\s*\.|…|\[[^\]]*\])\s*")

# A fragment shorter than this (in letters) carries too little signal to
# demand a match — roughly four short words.
MIN_FRAGMENT_CHARS = 20


def quote_coverage(quote: str, source: str) -> float:
    """How much of `quote` is present in `source`, honouring elisions.

    The quote is split at elisions and editorial insertions, each fragment is
    matched independently, and the score is the length-weighted mean over
    fragments long enough to be meaningful. An uninterrupted quote is a
    single fragment, so this reduces to `find_run`.
    """
    fragments = [squash(f) for f in BOUNDARY_RE.split(quote)]
    fragments = [f for f in fragments if len(f) >= MIN_FRAGMENT_CHARS]
    if not fragments:
        # nothing substantial left; fall back to the whole quote
        whole = squash(BOUNDARY_RE.sub(" ", quote))
        return find_run(whole, source) if whole else 0.0
    total = sum(len(f) for f in fragments)
    return sum(find_run(f, source) * len(f) for f in fragments) / total


# Coverage at or above this counts as verbatim.
VERIFIED = 0.9
# Between PARTIAL and VERIFIED the quote is mostly present but broken up.
# `pdftotext` flattens multi-column tables by interleaving cells, so a quote
# lifted from a table cell can be genuinely verbatim yet not contiguous in
# the extracted text. Partials are always listed but do not fail the check;
# below PARTIAL the quote is effectively absent and does fail.
PARTIAL = 0.5


def quotes_verified(text_dir: str = "references/text") -> callable:
    """Every quote attributed to a locally-archived source appears in it."""

    def _check(ctx: ValidationContext) -> TestResult:
        archive = ctx.repo_root / text_dir
        quotes = extract_quotes(ctx.qmd_text)

        verified = 0
        partials: list[str] = []
        failures: list[str] = []
        no_archive: set[str] = set()
        unattributed = 0
        cache: dict[str, list[str]] = {}

        for q in quotes:
            if q.citekey is None:
                unattributed += 1
                continue
            path = archive / f"{q.citekey}.txt"
            if not path.exists():
                no_archive.add(q.citekey)
                continue
            if q.citekey not in cache:
                cache[q.citekey] = tokens(path.read_text(encoding="utf-8", errors="replace"))
            coverage = quote_coverage(q.text, cache[q.citekey])
            snippet = q.text[:70] + ("..." if len(q.text) > 70 else "")
            entry = f"L{q.line} @{q.citekey} [{coverage:.0%}] “{snippet}”"
            if coverage >= VERIFIED:
                verified += 1
            elif coverage >= PARTIAL:
                partials.append(entry)
            else:
                failures.append(entry)

        checked = verified + len(partials) + len(failures)
        detail = f"({verified}/{checked} verbatim"
        if partials:
            detail += f", {len(partials)} partial"
        if no_archive:
            detail += f", {len(no_archive)} keys not archived"
        if unattributed:
            detail += f", {unattributed} unattributed"
        detail += ")"
        for label, items in (("ABSENT", failures), ("partial", partials)):
            if items:
                detail += f" | {label}: " + " ; ".join(items[:4])
                if len(items) > 4:
                    detail += f" ; +{len(items) - 4} more"

        return TestResult(
            name="Quotes appear in the cited source",
            ok=not failures,
            category="source-backed",
            detail=detail,
            meta={
                "absent": failures,
                "partial": partials,
                "verified": verified,
                "checked": checked,
                "total_quotes": len(quotes),
                "keys_not_archived": sorted(no_archive),
                "unattributed": unattributed,
            },
        )

    return _check
