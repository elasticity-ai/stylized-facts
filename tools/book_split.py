#!/usr/bin/env python3
"""Split stylized-facts.qmd into the question-per-chapter Quarto book in book/.

ONE-SHOT. This script produces book/*.qmd from the paper. Once the human
chapters are hand-edited, re-running it would overwrite them; it is kept so
the claim-to-question mapping is auditable and the same procedure can be
re-applied deliberately (e.g. to a fresh directory with --out) if the paper
gains a new section.

    python3 tools/book_split.py --out /tmp/book-preview   # safe: writes elsewhere
    python3 tools/book_split.py --force                   # overwrite book/

Mapping
-------
Every level-2 heading in the paper asserts a claim. QUESTIONS below assigns
each claim a chapter: a noun-phrase title naming the question ("LLM math
ability") and a slug (the filename). The book is a flat list of chapters in
the paper's order; the paper's four parts are not kept. Claims that bundle two
topics are split into two chapters, each receiving the part of the section
body that concerns it. Sections the paper has commented out with `<!-- -->`
are carried over as chapters marked `status: commented out in the paper`,
with the comment removed so the text is visible to the editor.

Chapter format (standardized; see AGENTS.md "The book")
--------------------------------------------------------
    ---
    title: "<noun phrase naming the question>"
    claim: "<the paper's heading, verbatim>"
    ---

    **<short answer: the claim as one bold sentence>**

    <body, as prose / bullets / figures>

    ## Literature summary (LLM-written) {.unnumbered}

    {{< include <slug>.llm.qmd >}}

The paper's definition-list idiom (`Lead sentence.` / `: elaboration`) is
rewritten as a bold lead paragraph followed by the elaboration, so every
chapter uses the same devices: bold lead, paragraph, bullet, figure, quote.
The paper's margin figures (`{.column-margin}`) become body figures.

tikz
----
The paper draws four figures with knitr `{tikz}` chunks. The book has no
executable code: each chunk is written to book/tikz/<name>.tex as a
standalone document and referenced as images/tikz-<name>.svg. `make tikz`
compiles them (pdflatex + pdftocairo). This keeps the book renderable with
plain `quarto render` — no R, no TeX — anywhere the SVGs are checked out.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER = REPO_ROOT / "stylized-facts.qmd"
DEFAULT_OUT = REPO_ROOT / "book"


# ----------------------------------------------------------------- mapping --
@dataclass
class Q:
    """One chapter. `claim` must match the paper's heading text exactly
    (whitespace-normalized, `<!--` stripped). `keep` optionally selects which
    body sentences a split chapter receives: a regex a sentence must match."""

    slug: str
    title: str
    claim: str
    keep: str | None = None
    see_also: list[str] = field(default_factory=list)
    short_answer: str | None = None  # defaults to the claim
    prepend_intro_of: str | None = None  # paper H1 whose intro text opens this chapter


QUESTIONS: list[Q] = [
    # --- from the paper's "Overview" ---
    Q("measure-of-machine-intelligence", "Measures of machine intelligence",
      "There is no standard measure of machine intelligence"),
    Q("taxonomy-of-ai-capabilities", "Taxonomies of AI capabilities",
      "There is no standard taxonomy of AI capabilities."),
    Q("latent-factor-of-llm-intelligence", "The latent factor of LLM intelligence",
      "There does appears to be a single latent component of intelligence across LLMs",
      see_also=["correlation-across-benchmarks"],
      short_answer="There does appear to be a single latent component of intelligence across LLMs."),
    Q("llm-vs-human-latent-intelligence", "Latent LLM intelligence vs latent human intelligence",
      "Latent LLM intelligence appears to be distinct from latent human intelligence."),
    Q("bottleneck-on-llm-abilities", "The bottleneck on LLM abilities",
      "There is *some* bottleneck on LLM abilities, but disagreement about where"),
    Q("bottleneck-candidates", "Candidates for the bottleneck",
      "There are many candidates for the bottleneck"),
    Q("forecasts-of-future-capabilities", "Forecasts of future capabilities",
      "There are few forecasts of future capabilities"),
    # --- from "LLM Performance on Tasks" ---
    Q("benchmark-saturation", "The speed of benchmark saturation",
      "The time between benchmark introduction and saturation has been decreasing"),
    Q("correlation-across-benchmarks", "Correlation of LLM performance across benchmarks",
      "LLM performance is highly correlated across benchmarks",
      see_also=["latent-factor-of-llm-intelligence"]),
    Q("training-compute-and-performance", "Training compute as a predictor of benchmark performance",
      "The best predictor of benchmark performance is training compute."),
    Q("growth-of-effective-scale", "Growth in the effective scale of frontier models",
      "The effective scale of frontier models has been growing at around 15X per year."),
    Q("test-time-scaling", "Test-time scaling",
      "Benchmark performance significantly improves with test-time scaling on some tasks."),
    Q("human-difficulty-vs-llm-difficulty", "Human difficulty vs LLM difficulty",
      "Benchmark tasks that are harder for humans are typically harder for LLMs."),
    Q("context-length", "Performance and context length",
      "LLM performance degrades significantly with context length."),
    Q("within-task-variability", "Variability of LLM performance within a task",
      "LLM performance on benchmarks is highly variable within the same task."),
    Q("sub-task-variability", "Variability of LLM performance across related sub-tasks",
      "LLM Performance on related sub-tasks is highly variable.",
      short_answer="LLM performance on related sub-tasks is highly variable."),
    Q("prompt-sensitivity", "Sensitivity to prompt wording",
      "LLM performance is sensitive to prompt wording."),
    Q("task-length-and-llm-difficulty", "Human task length and LLM difficulty",
      "Benchmark tasks that take humans longer are typically harder for LLMs.",
      see_also=["human-time-to-complete"]),
    # Split: one paper section, two chapters.
    Q("llm-math-ability", "LLM math ability",
      "LLMs perform particularly well on math and programming competition problems.",
      keep=r"math|AIME|MATH",
      short_answer="LLMs perform particularly well on math competition problems."),
    Q("llm-programming-ability", "LLM programming ability",
      "LLMs perform particularly well on math and programming competition problems.",
      keep=r"programm|Codeforces",
      short_answer="LLMs perform particularly well on programming competition problems."),
    Q("exam-questions", "LLM performance on exam questions",
      "LLMs do very well on exam questions, especially when the answer is short."),
    Q("autonomous-software-engineering", "Autonomous software engineering",
      "LLMs show some ability to autonomously complete software engineering tasks."),
    Q("ai-producing-ai-inputs", "LLMs producing their own inputs",
      "LLMs show ability in augmenting the production of all three of its key inputs (algorithmic improvements, hardware, and data)."),
    Q("algorithmic-improvement", "LLM ability to improve algorithms",
      "LLMs are showing ability to improve on algorithmic tasks."),
    Q("long-form-outputs", "LLM long-form outputs",
      "LLMs can produce long-form outputs that are preferred to a large share of human long-form outputs."),
    Q("economically-valuable-tasks", "Autonomous completion of economically valuable tasks",
      "LLMs are able to autonomously complete real-world tasks with significant economic value."),
    Q("where-humans-outperform", "Benchmarks where humans still outperform LLMs",
      "There are few benchmarks in which humans significantly outperform computers."),
    Q("benchmarks-beyond-human-ability", "Benchmarks beyond human ability",
      "New benchmarks are being produced that stretch the limits of human ability."),
    Q("real-world-actions", "LLM ability to act in the real world",
      "LLMs show limited ability to perform actions in the real world."),
    Q("llm-ability-to-play-games", "LLM ability to play games",
      "LLMs show limited ability to play single-player and multiplayer games."),
    Q("hallucination", "Hallucination",
      "LLMs hallucinate with obscure or long-form answers."),
    Q("calibration", "Calibration",
      "LLMs struggle to give calibrated answers."),
    Q("logically-complex-and-ux-tasks", "Logically complex tasks and UX usage",
      "LLMs struggle with tasks that are logically complex (and costly to verify at scale) and those that require UX usage."),
    Q("human-time-to-complete", "Human time-to-complete as a predictor of LLM success",
      "The Human Time-to-Complete a task is the best univariate predictor of LLM success rates",
      see_also=["task-length-and-llm-difficulty"],
      short_answer="The human time-to-complete a task is the best univariate predictor of LLM success rates."),
    Q("verifiability", "Verifiability as a predictor of LLM success",
      "The ease of verifying the outputs of a task is the most important attribute in leading LLMs to be successful at a task."),
    # --- from "LLM Augmentation Studies" ---
    Q("augmentation-productivity-effects", "The productivity effects of LLM augmentation",
      "The productivity effects of LLM augmentation varies widely",
      short_answer="The productivity effects of LLM augmentation vary widely.",
      prepend_intro_of="LLM Augmentation Studies"),
    Q("augmentation-and-worker-skill", "Augmentation effects by worker skill",
      "There is some evidence of larger effects on lower-productivity workers"),
    Q("augmentation-benchmarks", "Benchmarks of augmentation",
      "There are few benchmarks of augmentation"),
    Q("human-ai-teams", "Human + AI teams",
      "Human + AI teams do not reliably outperform the better of human or AI performance individually"),
    Q("misperception-of-llm-abilities", "Human misperception of LLM abilities",
      "Humans often misperceive the abilities of LLMs."),
    Q("occupational-exposure-indices", "Correlation among occupational exposure indices",
      "The correlation between different occupational exposure indices is fairly strong."),
    # --- from "Implications for LLM Economic Impact" ---
    Q("inference-price-decline", "The falling price of inference at fixed capability",
      "The price of inference for a fixed level of capability has been falling at 10X/year or faster."),
    Q("frontier-inference-cost", "The cost of frontier inference",
      "The cost of inference for frontier capabilities has remained roughly stable."),
    Q("inference-vs-training-costs", "Inference costs vs training costs",
      "Inference costs of serving a model are now roughly proportional to the initial training costs."),
    Q("llm-vs-human-cost", "The cost of LLMs vs humans",
      "LLMs are almost always cheaper than humans"),
    Q("economic-impact-so-far", "The economic impact of LLMs so far",
      "The economic impact of LLMs has been modest so far"),
    Q("directing-technical-change", "Directing technical change",
      "We may not be able to direct technical change"),
    Q("univariate-model-of-intelligence", "Univariate models of intelligence",
      "A univariate model of machine and human intelligence will be a poor fit"),
    Q("wages-and-compute-price", "Wages and the price of compute",
      "Wages are unlikely to be pinned down by the price of compute"),
]

# Sections that are not claims and get bespoke treatment.
PREFACE_CLAIM = "We wish to characterize AI capabilities"
OFFCUTS_H1 = "Appendix / Offcuts"

# tikz chunks, in order of appearance within each chapter -> figure name.
TIKZ_NAMES: dict[str, list[str]] = {
    "index": ["agent-task-matrix"],
    "llm-vs-human-latent-intelligence": ["one-dimension", "two-dimensions"],
    "economic-impact-so-far": ["frozen-capabilities"],
}

TIKZ_PREAMBLE = "\\documentclass[tikz,border=4pt]{standalone}\n\\begin{document}\n"
TIKZ_POSTAMBLE = "\\end{document}\n"


# ----------------------------------------------------------------- parsing --
@dataclass
class Section:
    level: int
    heading: str  # normalized heading text
    lines: list[str]  # body lines, heading excluded
    commented: bool
    start: int  # 1-based line of the heading in the paper


HEADING_RE = re.compile(r"^(?:<!--\s*)?(#{1,2})\s+(.*?)\s*(?:\{#[^}]*\})?\s*$")


def norm(s: str) -> str:
    return " ".join(s.split())


def parse_sections(text: str) -> tuple[list[str], list[Section]]:
    """Split the paper body (after the YAML header) into sections.

    Tracks `<!-- -->` state so a heading inside a comment is still a section
    boundary, flagged `commented`. Returns (preamble lines, sections)."""
    lines = text.split("\n")
    assert lines[0].strip() == "---"
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    body = lines[end + 1:]
    offset = end + 2  # 1-based line number of body[0]

    preamble: list[str] = []
    sections: list[Section] = []
    in_comment = False
    for i, line in enumerate(body):
        was_in_comment = in_comment
        m = HEADING_RE.match(line)
        opens_here = line.lstrip().startswith("<!--")
        if m:
            level = len(m.group(1))
            heading = norm(m.group(2))
            commented = was_in_comment or opens_here
            if level == 1 and commented:
                # A commented-out part heading (`<!-- # LLM Benchmarks: Factor
                # Analysis`). Not a chapter; drop the line but keep the comment
                # state so the sections it introduces are marked commented.
                pass
            else:
                sections.append(Section(level, heading, [], commented, offset + i))
        else:
            (sections[-1].lines if sections else preamble).append(line)
        for tok in re.findall(r"<!--|-->", line):
            in_comment = tok == "<!--"
    return preamble, sections


def uncomment(lines: list[str]) -> list[str]:
    """For a commented-out section: drop the `-->` that closed the comment
    hiding it (the opener was on the heading line, or handled by
    `strip_trailing_opener`)."""
    out = list(lines)
    for j, line in enumerate(out):
        if "-->" in line:
            out[j] = line.replace("-->", "", 1).rstrip()
            break
    return out


def strip_trailing_opener(lines: list[str]) -> list[str]:
    """Remove a dangling `<!--` line (plus blanks) at the end of a section; it
    opened the comment hiding the *next* section."""
    out = list(lines)
    while out and out[-1].strip() == "":
        out.pop()
    if out and re.fullmatch(r"<!--\s*", out[-1]):
        out.pop()
    return out


# ------------------------------------------------------------- transforms --
def comment_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"<!--.*?-->", text, flags=re.S)]


def in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


TIKZ_RE = re.compile(r"```\{tikz\}\n(.*?)```", re.S)


def extract_tikz(body: str, names: list[str], tikz_dir: Path) -> str:
    """Replace live `{tikz}` chunks with references to pre-rendered SVGs and
    write each chunk as a standalone .tex source. Chunks inside HTML comments
    are left alone."""
    spans = comment_spans(body)
    idx = 0

    def repl(m: re.Match) -> str:
        nonlocal idx
        if in_spans(m.start(), spans):
            return m.group(0)
        if idx >= len(names):
            sys.exit(f"unmapped tikz chunk (chunk #{idx + 1}); add it to TIKZ_NAMES")
        name = names[idx]
        idx += 1
        chunk = m.group(1)
        opts = dict(re.findall(r"^#\|\s*([\w-]+):\s*(.*)$", chunk, flags=re.M))
        code = "\n".join(l for l in chunk.split("\n") if not l.startswith("#|")).strip("\n")
        tikz_dir.mkdir(parents=True, exist_ok=True)
        (tikz_dir / f"{name}.tex").write_text(
            f"% Source of images/tikz-{name}.svg. Rebuild with `make tikz`.\n"
            + TIKZ_PREAMBLE + code + "\n" + TIKZ_POSTAMBLE, encoding="utf-8")
        cap = opts.get("fig-cap", "").strip().strip('"')
        # The paper puts figures in the margin; the book keeps them in the body.
        return f"![{cap}](images/tikz-{name}.svg)"

    out = TIKZ_RE.sub(repl, body)
    if idx != len(names):
        sys.exit(f"expected {len(names)} tikz chunks, found {idx}")
    return out


DD_RE = re.compile(r"^:(?!::)\s*(.*)$")


def convert_definition_lists(lines: list[str]) -> list[str]:
    """Rewrite pandoc definition lists as bold-lead paragraphs.

        Lead sentence.              **Lead sentence.**
        : Elaboration.        ->
            continued...            Elaboration.
        : More.                     continued...

                                    More.

    The paper uses this idiom as "claim: evidence"; the book renders every
    chapter with the same small set of devices instead, so the two-column
    grid CSS the paper needs for it is not carried over.
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = DD_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        # Find the term: last non-blank output line, separated by blanks only,
        # unless it was itself part of the definition we are converting.
        j = len(out) - 1
        while j >= 0 and out[j].strip() == "":
            j -= 1
        # A term is a sentence-like line: starts with a capital, a citation, a
        # link or a quote mark. This skips comment openers and stray fragments.
        is_term = j >= 0 and re.match(r"^[A-Z@\[*\"“]", out[j].strip() or " ") is not None
        if is_term and not getattr(convert_definition_lists, "_in_dd", False):
            term = out[j].strip()
            del out[j:]
            out.append(f"**{term}**")
            out.append("")
        convert_definition_lists._in_dd = True  # type: ignore[attr-defined]

        # Collect this definition: the `:` line's content plus indented or
        # blank continuation lines (stop at a blank followed by a non-indented
        # line, or at another `:` item).
        block = [m.group(1)]
        i += 1
        while i < n:
            nxt = lines[i]
            if DD_RE.match(nxt):
                break
            if nxt.strip() == "":
                # blank: continue only if a later indented line follows
                k = i + 1
                while k < n and lines[k].strip() == "":
                    k += 1
                if k < n and lines[k].startswith((" ", "\t")) and not DD_RE.match(lines[k]):
                    block.append("")
                    i += 1
                    continue
                break
            if nxt.startswith((" ", "\t")):
                block.append(nxt)
                i += 1
                continue
            break
        cont = [l for l in block[1:] if l.strip()]
        indent = min((len(l) - len(l.lstrip()) for l in cont), default=0)
        body = [block[0].strip()] + [l[indent:] if l.strip() else "" for l in block[1:]]
        out.extend(body)
        out.append("")

        # Does the list continue with another `:` item (possibly after blanks)?
        k = i
        while k < n and lines[k].strip() == "":
            k += 1
        if not (k < n and DD_RE.match(lines[k])):
            convert_definition_lists._in_dd = False  # type: ignore[attr-defined]
        else:
            i = k
    convert_definition_lists._in_dd = False  # type: ignore[attr-defined]
    return out


FOOTDEF_RE = re.compile(r"^\[\^([^\]]+)\]:")
FOOTREF_RE = re.compile(r"\[\^([^\]]+)\](?!:)")


def footnote_defs(text: str) -> dict[str, str]:
    defs: dict[str, str] = {}
    for line in text.split("\n"):
        m = FOOTDEF_RE.match(line)
        if m:
            defs[m.group(1)] = line
    return defs


def with_footnotes(body: str, defs: dict[str, str]) -> str:
    used = set(FOOTREF_RE.findall(body))
    defined = set(FOOTDEF_RE.match(l).group(1) for l in body.split("\n") if FOOTDEF_RE.match(l))
    missing = [k for k in used - defined if k in defs]
    if missing:
        body = body.rstrip("\n") + "\n\n" + "\n".join(defs[k] for k in sorted(missing)) + "\n"
    keep = []
    for l in body.split("\n"):
        m = FOOTDEF_RE.match(l)
        if m and m.group(1) not in used:
            continue
        keep.append(l)
    return "\n".join(keep)


def tidy(body: str) -> str:
    body = re.sub(r"[ \t]+\n", "\n", body)  # trailing whitespace
    body = re.sub(r"^\\\n", "\n", body, flags=re.M)  # the paper's stray lone backslashes
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip("\n") + "\n"


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def citekeys(text: str) -> list[str]:
    raw = re.findall(r"@([A-Za-z][A-Za-z0-9:_-]*)", text)
    keys = sorted({k.rstrip(":_-") for k in raw})
    return [k for k in keys if k not in {"placemarginal", "sidenotes", "author", "date", "maketitle", "title"}]


def split_body(lines: list[str], pattern: str) -> list[str]:
    """For a section split into two chapters: keep sentences matching pattern.

    Handles the one case in the paper — a single bullet whose sentences cover
    the two topics in turn — by splitting the bullet into sentences and keeping
    those that match. Non-bullet lines (blank, comments) pass through."""
    rx = re.compile(pattern, re.I)
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(\s*[-*]\s+)(.*)$", line)
        if not m:
            out.append(line)
            continue
        prefix, body = m.groups()
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\[(])", body)
        kept = [s for s in sentences if rx.search(s)]
        if kept:
            out.append(prefix + " ".join(kept))
    return out


# ----------------------------------------------------------------- writing --
_TITLES: dict[str, str] = {q.slug: q.title for q in QUESTIONS}


def short_answer(q: Q) -> str:
    s = (q.short_answer or q.claim).strip().rstrip(".")
    return f"**{s}.**"


def chapter_text(q: Q, sec: Section, body: str, defs: dict[str, str]) -> str:
    fm = ["---", f"title: {yaml_str(q.title)}", f"claim: {yaml_str(q.claim)}"]
    if sec.commented:
        fm.append('status: "commented out in the paper"')
    fm.append("---")
    parts = ["\n".join(fm), ""]
    if sec.commented:
        parts += [
            "::: {.callout-warning}",
            "This section is commented out in `stylized-facts.qmd`; it is carried here so the claim is not lost. Treat as a draft.",
            ":::",
            "",
        ]
    parts.append(short_answer(q))
    parts.append("")
    if q.see_also:
        links = ", ".join(f"[{_TITLES[s]}]({s}.qmd)" for s in q.see_also)
        parts.append(f"*See also:* {links}.")
        parts.append("")
    parts.append(with_footnotes(tidy(body), defs).rstrip("\n"))
    parts += [
        "",
        "::: {.llm-summary .column-page-right}",  # body + margin width: the table needs it
        "## Literature summary (LLM-written) {.unnumbered}",
        "",
        f"{{{{< include {q.slug}.llm.qmd >}}}}",
        ":::",
        "",
    ]
    return "\n".join(parts)


def is_stub(path: Path) -> bool:
    return not path.exists() or "**Stub.**" in path.read_text(encoding="utf-8")


def llm_stub(q: Q, body: str) -> str:
    keys = citekeys(body)
    lines = [
        f"<!-- {q.slug}.llm.qmd — LLM-written literature summary for “{q.title}”.",
        "     Written and maintained by an LLM pass following book/LLM-STYLE-GUIDE.md,",
        "     and included at the end of the human-written chapter. No YAML frontmatter",
        "     here: included files cannot carry their own metadata. -->",
        "",
        "::: {.callout-note}",
        "**Stub.** The literature summary for this question has not been written yet.",
        ":::",
        "",
    ]
    if keys:
        lines.append("Sources already cited in the human-written chapter:")
        lines.append("")
        lines += [f"- @{k}" for k in keys]
        lines.append("")
    return "\n".join(lines)


def quarto_yml(chapters: list[str]) -> str:
    chapter_lines = "\n".join(f"    - {c}" for c in chapters)
    return f"""# Quarto book built from stylized-facts.qmd: a flat list of chapters, one
# per question. See AGENTS.md ("The book") and tools/book_split.py for the
# claim→question mapping and the chapter format.
project:
  type: book
  output-dir: _book

book:
  title: "Stylized Facts about AI & Human Capabilities"
  author: "Tom Cunningham & Ali Merali"
  date: today
  repo-url: https://github.com/elasticity-ai/stylized-facts
  repo-subdir: book
  repo-actions: [edit, issue]
  sidebar:
    style: floating
    search: true
  chapters:
{chapter_lines}

# Shared with the paper: exactly one bibliography and one image directory
# (book/images is a symlink to ../images). The tikz figures are pre-rendered
# SVGs, sources in book/tikz/, rebuilt with `make tikz`; so there is no
# executable code and no engine here.
bibliography: ../stylized-facts.bib

number-sections: false
lightbox: auto

format:
  html:
    theme: cosmo
    css: book.css   # tints the LLM-written section, sizes body figures
    toc: false   # chapters are short; the sidebar is the table of contents
    include-in-header:
      - text: |
          <script>window.MathJax = {{
                   tex: {{ macros: {{
                      bm: ["\\\\boldsymbol{{#1}}", 1],
                      ut: ["\\\\underbrace{{#1}}_{{\\\\text{{#2}}}}", 2],
                      utt: ["\\\\underbrace{{#1}}_{{\\\\substack{{\\\\text{{#2}}\\\\\\\\\\\\text{{#3}}}}}}", 3]
                   }} }} }};
          </script>
"""


MARGIN_IMG_RE = re.compile(r"(!\[[^\]]*\]\([^)\s]+\))\{\.column-margin\}")


def unmargin_images(body: str) -> str:
    """Figures live in the body in the book, not in the margin."""
    return MARGIN_IMG_RE.sub(r"\1", body)


def render_body(slug: str, lines: list[str], out: Path) -> str:
    """The shared pipeline from paper section lines to chapter body text."""
    lines = convert_definition_lists(lines)
    body = "\n".join(lines)
    body = extract_tikz(body, TIKZ_NAMES.get(slug, []), out / "tikz")
    body = unmargin_images(body)
    return body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true", help="Overwrite existing chapter files.")
    args = ap.parse_args()
    out: Path = args.out

    text = PAPER.read_text(encoding="utf-8")
    defs = footnote_defs(text)
    preamble, sections = parse_sections(text)

    for s in sections:
        s.lines = strip_trailing_opener(s.lines)
    for s in sections:
        if s.commented:
            s.lines = uncomment(s.lines)

    by_claim: dict[str, Section] = {}
    for s in sections:
        if s.level == 2:
            if s.heading in by_claim:
                sys.exit(f"duplicate heading in paper: {s.heading!r}")
            by_claim[s.heading] = s
    h1_intro = {s.heading: s for s in sections if s.level == 1}

    existing = [p for p in out.glob("*.qmd")] if out.exists() else []
    if existing and not args.force:
        sys.exit(f"{out} already has .qmd files; pass --force to overwrite (this is a one-shot script, see docstring)")
    out.mkdir(parents=True, exist_ok=True)
    for stale in existing:
        if stale.name.endswith(".llm.qmd") and not is_stub(stale):
            continue  # written summaries survive a regeneration
        stale.unlink()

    used: set[str] = set()
    kept: list[str] = []
    chapters: list[str] = ["index.qmd"]
    for q in QUESTIONS:
        sec = by_claim.get(q.claim)
        if sec is None:
            sys.exit(f"claim not found in paper: {q.claim!r}")
        used.add(q.claim)
        body_lines = list(sec.lines)
        if q.keep:
            body_lines = split_body(body_lines, q.keep)
        if q.prepend_intro_of:
            body_lines = [l for l in h1_intro[q.prepend_intro_of].lines if l.strip()] + [""] + body_lines
        body = render_body(q.slug, body_lines, out)
        (out / f"{q.slug}.qmd").write_text(chapter_text(q, sec, body, defs), encoding="utf-8")
        # A written literature summary is never overwritten with a stub.
        llm_path = out / f"{q.slug}.llm.qmd"
        if is_stub(llm_path):
            llm_path.write_text(llm_stub(q, body), encoding="utf-8")
        else:
            kept.append(llm_path.name)
        chapters.append(f"{q.slug}.qmd")

    # index: the paper's abstract, thanks, and its own introduction section
    pre = by_claim[PREFACE_CLAIM]
    used.add(PREFACE_CLAIM)
    header_yaml = text.split("\n---\n")[0]
    abstract = re.search(r"^abstract:\s*(.*)$", header_yaml, re.M).group(1).strip()
    notes = "\n".join(re.findall(r"<!--.*?-->", "\n".join(preamble), flags=re.S))
    thanks = re.sub(r"<!--.*?-->", "", "\n".join(preamble), flags=re.S).strip()
    index = "\n".join([
        "# Introduction {.unnumbered}",
        "",
        abstract,
        "",
        "This book is a restructuring of the paper *Stylized Facts about AI & Human Capabilities* "
        "(`stylized-facts.qmd`). The paper is a list of claims; here each claim is a chapter, "
        "titled by the question it answers. Every chapter opens with the claim as a one-sentence "
        "**short answer** in bold, followed by the evidence from the paper, and closes with an "
        "LLM-written summary of the relevant literature.",
        "",
        thanks,
        "",
        f"## {PREFACE_CLAIM}",
        "",
        with_footnotes(tidy(render_body("index", pre.lines, out)), defs).rstrip("\n"),
        "",
        notes,
        "",
    ])
    (out / "index.qmd").write_text(index, encoding="utf-8")

    off = h1_intro[OFFCUTS_H1]
    (out / "offcuts.qmd").write_text(
        "# Offcuts {.unnumbered}\n\nMaterial from the paper's appendix that is not (yet) attached to a question.\n\n"
        + with_footnotes(tidy("\n".join(off.lines)), defs).rstrip("\n") + "\n",
        encoding="utf-8")
    chapters += ["offcuts.qmd", "references.qmd"]
    (out / "references.qmd").write_text("# References {.unnumbered}\n\n::: {#refs}\n:::\n", encoding="utf-8")
    (out / "_quarto.yml").write_text(quarto_yml(chapters), encoding="utf-8")

    unused = [h for h, s in by_claim.items() if h not in used and s.heading != "References"]
    if unused:
        print("WARNING: paper sections not mapped to any chapter:", file=sys.stderr)
        for h in unused:
            print(f"  - {h}", file=sys.stderr)
    print(f"wrote {len(QUESTIONS)} chapters (+ index, offcuts, references) to {out}")
    if kept:
        print(f"kept {len(kept)} written literature summaries: {', '.join(kept)}")
    return 1 if unused else 0


if __name__ == "__main__":
    raise SystemExit(main())
