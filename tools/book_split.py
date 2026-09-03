#!/usr/bin/env python3
"""Split stylized-facts.qmd into the question-per-chapter Quarto book in book/.

ONE-SHOT. This script produced the first version of book/*.qmd from the paper.
The human chapters have since been (or will be) hand-edited; re-running it
would overwrite them. It is kept so the claim-to-question mapping is auditable
and so the same procedure can be re-applied deliberately (e.g. to a fresh
directory with --out) if the paper gains a new section.

    python3 tools/book_split.py --out /tmp/book-preview   # safe: writes elsewhere
    python3 tools/book_split.py --force                   # overwrite book/

Mapping
-------
Every level-2 heading in the paper asserts a claim. MAPPING below assigns each
claim a question (the chapter title) and a slug (the filename). Claims that
bundle two topics are split into two chapters, each receiving the part of the
section body that concerns it. Sections the paper has commented out with
`<!-- ... -->` are carried over as chapters marked `status: commented out in
the paper`, with the comment removed so the text is visible to the editor.

Each chapter is written as two files:

    book/<slug>.qmd        human-written; this script writes the first draft
    book/<slug>.llm.qmd    LLM-written literature summary; a stub, included at
                           the end of the human chapter
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
    body lines a split chapter receives: a regex a line must match."""

    slug: str
    question: str
    claim: str
    keep: str | None = None
    see_also: list[str] = field(default_factory=list)
    short_answer: str | None = None  # defaults to the claim


PARTS: list[tuple[str, str | None, list[Q]]] = [
    # (part title, part intro qmd basename or None, chapters)
    ("Overview", None, [
        Q("measure-of-machine-intelligence",
          "Is there a standard measure of machine intelligence?",
          "There is no standard measure of machine intelligence"),
        Q("taxonomy-of-ai-capabilities",
          "Is there a standard taxonomy of AI capabilities?",
          "There is no standard taxonomy of AI capabilities."),
        Q("latent-factor-of-llm-intelligence",
          "Is there a single latent factor of LLM intelligence?",
          "There does appears to be a single latent component of intelligence across LLMs",
          see_also=["correlation-across-benchmarks"],
          short_answer="There does appear to be a single latent component of intelligence across LLMs."),
        Q("llm-vs-human-latent-intelligence",
          "How does latent LLM intelligence differ from latent human intelligence?",
          "Latent LLM intelligence appears to be distinct from latent human intelligence."),
        Q("bottleneck-on-llm-abilities",
          "Is there a bottleneck on LLM abilities?",
          "There is *some* bottleneck on LLM abilities, but disagreement about where"),
        Q("bottleneck-candidates",
          "What are the candidates for the bottleneck?",
          "There are many candidates for the bottleneck"),
        Q("forecasts-of-future-capabilities",
          "What forecasts exist of future AI capabilities?",
          "There are few forecasts of future capabilities"),
    ]),
    ("LLM Performance on Tasks", "part-tasks.qmd", [
        Q("benchmark-saturation",
          "How quickly do benchmarks saturate?",
          "The time between benchmark introduction and saturation has been decreasing"),
        Q("correlation-across-benchmarks",
          "How correlated is LLM performance across benchmarks?",
          "LLM performance is highly correlated across benchmarks",
          see_also=["latent-factor-of-llm-intelligence"]),
        Q("training-compute-and-performance",
          "How well does training compute predict benchmark performance?",
          "The best predictor of benchmark performance is training compute."),
        Q("growth-of-effective-scale",
          "How fast is the effective scale of frontier models growing?",
          "The effective scale of frontier models has been growing at around 15X per year."),
        Q("test-time-scaling",
          "How much does test-time scaling improve performance?",
          "Benchmark performance significantly improves with test-time scaling on some tasks."),
        Q("human-difficulty-vs-llm-difficulty",
          "Are tasks that are hard for humans also hard for LLMs?",
          "Benchmark tasks that are harder for humans are typically harder for LLMs."),
        Q("context-length",
          "How does LLM performance change with context length?",
          "LLM performance degrades significantly with context length."),
        Q("within-task-variability",
          "How variable is LLM performance on repeated attempts at the same task?",
          "LLM performance on benchmarks is highly variable within the same task."),
        Q("sub-task-variability",
          "How variable is LLM performance across related sub-tasks?",
          "LLM Performance on related sub-tasks is highly variable."),
        Q("prompt-sensitivity",
          "How sensitive is LLM performance to prompt wording?",
          "LLM performance is sensitive to prompt wording."),
        Q("task-length-and-llm-difficulty",
          "Are tasks that take humans longer harder for LLMs?",
          "Benchmark tasks that take humans longer are typically harder for LLMs.",
          see_also=["human-time-to-complete"]),
        # Split: one paper section, two chapters.
        Q("llm-math-ability",
          "How good are LLMs at mathematics?",
          "LLMs perform particularly well on math and programming competition problems.",
          keep=r"math|AIME|MATH",
          short_answer="LLMs perform particularly well on math competition problems."),
        Q("llm-programming-ability",
          "How good are LLMs at programming?",
          "LLMs perform particularly well on math and programming competition problems.",
          keep=r"programm|Codeforces",
          short_answer="LLMs perform particularly well on programming competition problems."),
        Q("exam-questions",
          "How well do LLMs do on exam questions?",
          "LLMs do very well on exam questions, especially when the answer is short."),
        Q("autonomous-software-engineering",
          "Can LLMs autonomously complete software engineering tasks?",
          "LLMs show some ability to autonomously complete software engineering tasks."),
        Q("ai-producing-ai-inputs",
          "Can LLMs augment the production of their own inputs?",
          "LLMs show ability in augmenting the production of all three of its key inputs (algorithmic improvements, hardware, and data)."),
        Q("algorithmic-improvement",
          "Can LLMs improve on algorithmic tasks?",
          "LLMs are showing ability to improve on algorithmic tasks."),
        Q("long-form-outputs",
          "How do LLM long-form outputs compare to human ones?",
          "LLMs can produce long-form outputs that are preferred to a large share of human long-form outputs."),
        Q("economically-valuable-tasks",
          "Can LLMs autonomously complete economically valuable real-world tasks?",
          "LLMs are able to autonomously complete real-world tasks with significant economic value."),
        Q("where-humans-outperform",
          "On which benchmarks do humans still outperform LLMs?",
          "There are few benchmarks in which humans significantly outperform computers."),
        Q("benchmarks-beyond-human-ability",
          "Are new benchmarks stretching the limits of human ability?",
          "New benchmarks are being produced that stretch the limits of human ability."),
        Q("real-world-actions",
          "Can LLMs perform actions in the real world?",
          "LLMs show limited ability to perform actions in the real world."),
        Q("llm-ability-to-play-games",
          "How well can LLMs play games?",
          "LLMs show limited ability to play single-player and multiplayer games."),
        Q("hallucination",
          "When do LLMs hallucinate?",
          "LLMs hallucinate with obscure or long-form answers."),
        Q("calibration",
          "Are LLMs calibrated about what they know?",
          "LLMs struggle to give calibrated answers."),
        Q("logically-complex-and-ux-tasks",
          "Do LLMs struggle with logically complex tasks and tasks requiring UX usage?",
          "LLMs struggle with tasks that are logically complex (and costly to verify at scale) and those that require UX usage."),
        Q("human-time-to-complete",
          "Is human time-to-complete the best predictor of LLM success?",
          "The Human Time-to-Complete a task is the best univariate predictor of LLM success rates",
          see_also=["task-length-and-llm-difficulty"]),
        Q("verifiability",
          "Does the verifiability of a task's output predict LLM success?",
          "The ease of verifying the outputs of a task is the most important attribute in leading LLMs to be successful at a task."),
    ]),
    ("LLM Augmentation Studies", "part-augmentation.qmd", [
        Q("augmentation-productivity-effects",
          "How large are the productivity effects of LLM augmentation?",
          "The productivity effects of LLM augmentation varies widely"),
        Q("augmentation-and-worker-skill",
          "Does augmentation help lower-productivity workers more?",
          "There is some evidence of larger effects on lower-productivity workers"),
        Q("augmentation-benchmarks",
          "Are there benchmarks of augmentation?",
          "There are few benchmarks of augmentation"),
        Q("human-ai-teams",
          "Do human plus AI teams outperform the better of the two alone?",
          "Human + AI teams do not reliably outperform the better of human or AI performance individually"),
        Q("misperception-of-llm-abilities",
          "Do humans perceive LLM abilities accurately?",
          "Humans often misperceive the abilities of LLMs."),
        Q("occupational-exposure-indices",
          "How correlated are the different occupational exposure indices?",
          "The correlation between different occupational exposure indices is fairly strong."),
    ]),
    ("Implications for LLM Economic Impact", None, [
        Q("inference-price-decline",
          "How fast is the price of inference falling for a fixed capability?",
          "The price of inference for a fixed level of capability has been falling at 10X/year or faster."),
        Q("frontier-inference-cost",
          "How has the cost of frontier inference changed?",
          "The cost of inference for frontier capabilities has remained roughly stable."),
        Q("inference-vs-training-costs",
          "How do inference costs compare to training costs?",
          "Inference costs of serving a model are now roughly proportional to the initial training costs."),
        Q("llm-vs-human-cost",
          "Are LLMs cheaper than humans?",
          "LLMs are almost always cheaper than humans"),
        Q("economic-impact-so-far",
          "How large has the economic impact of LLMs been so far?",
          "The economic impact of LLMs has been modest so far"),
        Q("directing-technical-change",
          "Can the direction of AI technical change be steered?",
          "We may not be able to direct technical change"),
        Q("univariate-model-of-intelligence",
          "Is a univariate model of machine and human intelligence a good fit?",
          "A univariate model of machine and human intelligence will be a poor fit"),
        Q("wages-and-compute-price",
          "Are wages pinned down by the price of compute?",
          "Wages are unlikely to be pinned down by the price of compute"),
    ]),
]

# Sections that are not claims and get bespoke treatment.
PREFACE_CLAIM = "We wish to characterize AI capabilities"
OFFCUTS_CLAIM = "Appendix / Offcuts"


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
    # skip YAML header
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
        # update comment state from this line's content
        for tok in re.findall(r"<!--|-->", line):
            in_comment = tok == "<!--"
    return preamble, sections


def uncomment(lines: list[str]) -> list[str]:
    """For a commented-out section: drop the `<!--` that hid it and its `-->`.

    The opener is either on the heading line (already stripped by the heading
    regex) or on a standalone line just before it (handled by the caller, see
    `strip_trailing_opener`). The closer is the first `-->` in the body."""
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
    # drop definitions nothing in this chapter references (they came along
    # with the paper's trailing footnote block)
    keep = []
    for l in body.split("\n"):
        m = FOOTDEF_RE.match(l)
        if m and m.group(1) not in used:
            continue
        keep.append(l)
    return "\n".join(keep)


def tidy(body: str) -> str:
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip("\n") + "\n"


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def citekeys(text: str) -> list[str]:
    raw = re.findall(r"@([A-Za-z][A-Za-z0-9:_-]*)", text)
    keys = sorted({k.rstrip(":_-") for k in raw})
    return [k for k in keys if k not in {"placemarginal", "sidenotes", "author", "date", "maketitle", "title"}]


# ----------------------------------------------------------------- writing --
def chapter_text(q: Q, sec: Section, body: str, defs: dict[str, str]) -> str:
    fm = ["---", f"title: {yaml_str(q.question)}", f"claim: {yaml_str(q.claim)}"]
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
    parts.append(f"**Short answer.** {(q.short_answer or q.claim).rstrip('.')}.")
    parts.append("")
    if q.see_also:
        links = ", ".join(f"[{other_title(s)}]({s}.qmd)" for s in q.see_also)
        parts.append(f"*See also:* {links}.")
        parts.append("")
    parts.append(with_footnotes(tidy(body), defs).rstrip("\n"))
    parts += [
        "",
        "## Literature summary (LLM-written) {.unnumbered}",
        "",
        f"{{{{< include {q.slug}.llm.qmd >}}}}",
        "",
    ]
    return "\n".join(parts)


def llm_stub(q: Q, body: str) -> str:
    keys = citekeys(body)
    lines = [
        f"<!-- {q.slug}.llm.qmd — LLM-written literature summary for the question",
        f"     “{q.question}”. This file is generated/maintained by an LLM pass and",
        "     included at the end of the human-written chapter. Do not put YAML",
        "     frontmatter here: included files cannot carry their own metadata. -->",
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


_TITLES: dict[str, str] = {}


def other_title(slug: str) -> str:
    return _TITLES[slug]


def quarto_yml(index_and_parts: list[str]) -> str:
    return f"""# Quarto book built from stylized-facts.qmd, one question per chapter.
# See AGENTS.md ("The book") and tools/book_split.py for the claim→question mapping.
project:
  type: book
  output-dir: _book

book:
  title: "Stylized Facts about AI & Human Capabilities"
  author: "Tom Cunningham & Ali Merali"
  date: today
  repo-url: https://github.com/elasticity-ai/stylized-facts
  chapters:
{index_and_parts}

# Shared with the paper: exactly one bibliography and one image directory
# (book/images is a symlink to ../images).
bibliography: ../stylized-facts.bib

engine: knitr
execute:
  echo: false
  warning: false
  error: false
  cache: true

number-sections: true
toc-depth: 2
lightbox: auto

format:
  html:
    theme: cosmo
    grid:
      margin-width: 400px
    include-in-header:
      - text: |
          <script>window.MathJax = {{
                   tex: {{ macros: {{
                      bm: ["\\\\boldsymbol{{#1}}", 1],
                      ut: ["\\\\underbrace{{#1}}_{{\\\\text{{#2}}}}", 2],
                      utt: ["\\\\underbrace{{#1}}_{{\\\\substack{{\\\\text{{#2}}\\\\\\\\\\\\text{{#3}}}}}}", 3]
                   }} }} }};
          </script>
          <style>
             dl {{ display: grid; grid-template-columns: 10em auto; }}
             dt {{ grid-column-start: 1; font-weight: bold; margin-right: 10px; }}
             dd {{ grid-column-start: 2; }}
          </style>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true", help="Overwrite existing chapter files.")
    args = ap.parse_args()
    out: Path = args.out

    text = PAPER.read_text(encoding="utf-8")
    defs = footnote_defs(text)
    preamble, sections = parse_sections(text)

    # strip dangling comment openers that belong to the following section
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

    for _, _, qs in PARTS:
        for q in qs:
            _TITLES[q.slug] = q.question

    existing = [p for p in out.glob("*.qmd")] if out.exists() else []
    if existing and not args.force:
        sys.exit(f"{out} already has .qmd files; pass --force to overwrite (this is a one-shot script, see docstring)")
    out.mkdir(parents=True, exist_ok=True)

    used: set[str] = set()
    chapter_yaml: list[str] = ["    - index.qmd"]
    for part_title, part_file, qs in PARTS:
        if part_file:
            intro = h1_intro[part_title]
            (out / part_file).write_text(
                f"# {part_title}\n\n" + tidy("\n".join(intro.lines)), encoding="utf-8")
            chapter_yaml.append(f"    - part: {part_file}")
        else:
            chapter_yaml.append(f"    - part: {yaml_str(part_title)}")
        chapter_yaml.append("      chapters:")
        for q in qs:
            sec = by_claim.get(q.claim)
            if sec is None:
                sys.exit(f"claim not found in paper: {q.claim!r}")
            used.add(q.claim)
            body_lines = sec.lines
            if q.keep:
                # split section: keep only sentences matching the pattern
                body_lines = split_body(body_lines, q.keep)
            body = "\n".join(body_lines)
            (out / f"{q.slug}.qmd").write_text(chapter_text(q, sec, body, defs), encoding="utf-8")
            (out / f"{q.slug}.llm.qmd").write_text(llm_stub(q, body), encoding="utf-8")
            chapter_yaml.append(f"        - {q.slug}.qmd")

    # preface
    pre = by_claim[PREFACE_CLAIM]
    used.add(PREFACE_CLAIM)
    header_yaml = text.split("\n---\n")[0]
    abstract = re.search(r"^abstract:\s*(.*)$", header_yaml, re.M).group(1).strip()
    # The preamble holds the paper's working notes (comments) and the thanks
    # margin note. Keep the note visible; keep the working notes as a comment.
    notes = "\n".join(re.findall(r"<!--.*?-->", "\n".join(preamble), flags=re.S))
    thanks = re.sub(r"<!--.*?-->", "", "\n".join(preamble), flags=re.S).strip()
    index = "\n".join([
        "# Introduction {.unnumbered}",
        "",
        abstract,
        "",
        "This book is a restructuring of the paper *Stylized Facts about AI & Human Capabilities* "
        "(`stylized-facts.qmd`). The paper is a list of claims; here each claim is posed as a "
        "*question*, one chapter per question. Each chapter has a human-written answer, drawn from "
        "the paper, followed by an LLM-written summary of the relevant literature.",
        "",
        thanks,
        "",
        f"## {PREFACE_CLAIM}",
        "",
        with_footnotes(tidy("\n".join(pre.lines)), defs).rstrip("\n"),
        "",
        notes,
        "",
    ])
    (out / "index.qmd").write_text(index, encoding="utf-8")

    # offcuts
    off = h1_intro[OFFCUTS_CLAIM]
    (out / "offcuts.qmd").write_text(
        "# Offcuts {.unnumbered}\n\nMaterial from the paper's appendix that is not (yet) attached to a question.\n\n"
        + with_footnotes(tidy("\n".join(off.lines)), defs).rstrip("\n") + "\n",
        encoding="utf-8")
    chapter_yaml += ["    - offcuts.qmd", "    - references.qmd"]
    (out / "references.qmd").write_text("# References {.unnumbered}\n\n::: {#refs}\n:::\n", encoding="utf-8")

    (out / "_quarto.yml").write_text(quarto_yml("\n".join(chapter_yaml)), encoding="utf-8")

    unused = [h for h, s in by_claim.items() if h not in used and s.heading != "References"]
    if unused:
        print("WARNING: paper sections not mapped to any chapter:", file=sys.stderr)
        for h in unused:
            print(f"  - {h}", file=sys.stderr)
    n = sum(len(qs) for _, _, qs in PARTS)
    print(f"wrote {n} chapters (+ index, offcuts, references) to {out}")
    return 1 if unused else 0


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


if __name__ == "__main__":
    raise SystemExit(main())
