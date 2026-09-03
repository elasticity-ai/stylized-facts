# Style guide for the LLM-written literature summaries

Every chapter of the book (`book/<slug>.qmd`) ends by including
`book/<slug>.llm.qmd`: a literature summary written and maintained by an LLM.
This guide is the specification for those files. The chapter's human-written
half answers the question; the LLM half shows the reader **what the literature
says, paper by paper, in the order it appeared**, so they can judge the answer
for themselves.

The stubs currently in place are placeholders; nothing below has been
assembled yet.

## What the file is for

- **Coverage**, not argument. The human chapter makes the case. The summary
  lists the evidence, including evidence that cuts against the chapter's short
  answer.
- **Traceability.** Every row, number and quote must be checkable against a
  source in `stylized-facts.bib`. The repo's checks run on these files exactly
  as they run on the paper (`make check`).
- **Chronology.** The table is ordered by date so the reader can see how the
  picture changed as models did. A 2023 result about GPT-4 and a 2025 result
  about a reasoning model are different facts, not a disagreement.

## Required structure

The file is plain Quarto markdown, included into a chapter. In order:

1. **One-paragraph orientation** (2–4 sentences). What kind of evidence
   exists for this question, how much of it, and the date range. No verdict.
2. **The table** (see below). This is the body of the file.
3. **Figures**, where the literature has a chart that carries the finding
   (see below). Zero to three.
4. **Gaps** — a short bullet list of what has *not* been measured, or has
   only been measured on obsolete models. This is the most useful section for
   the authors; do not skip it.

Do not add a conclusion or a synthesis paragraph. Do not repeat the chapter's
short answer.

## The table

One row per paper, or per distinct result when a paper has several that
matter here. Chronological by publication (or preprint) date, oldest first.

| Column | Contents |
|---|---|
| **Date** | `YYYY-MM`. Preprint date if that is what is cited. |
| **Source** | The citation, `@citekey`. Nothing else in this cell. |
| **Setting** | What was measured on what: models (named, with version), benchmark or task, sample size, population if human. Terse; this is a table. |
| **Finding** | The result as a number wherever the paper gives one, with its unit and comparison baseline. One or two sentences at most. |
| **Bearing** | One of `supports`, `qualifies`, `contradicts`, `context`, relative to the chapter's short answer. Judge honestly. |

Rules for cells:

- **Numbers come from the source**, quoted as the source states them (same
  units, same rounding). If you convert (e.g. a time saving into a
  throughput gain), show the original and mark the conversion, as the paper's
  augmentation table does: `"55.8% faster" (implies +126% tasks/minute)`.
- **Quote verbatim or not at all.** A quotation must be 8+ words and appear
  word-for-word in the source, because `make check` looks it up in the
  archived text and fails the commit if it is not there. Paraphrase without
  quotation marks when you are not certain of the exact wording.
- **Name the model.** "Frontier models" is not a finding. `GPT-4 (Mar 2023)`,
  `o3`, `Claude 3.7 Sonnet` are.
- **Sample sizes and dates** belong in Setting. A result on 12 models from
  2023 is not the same evidence as one on 591 models from 2024.
- Keep the table wide, not tall: prefer one dense row to three thin ones.

## Figures

Include a figure when the paper's own chart shows the finding better than a
number can — a scaling curve, a distribution of effect sizes, a
model-by-benchmark heatmap. Otherwise do not.

- Save the image to `images/` at the repo root (the book sees it through the
  `book/images` symlink). Name it `<citekey>-<short-description>.png`.
- Caption it with the credit and what it shows:
  `![Effect sizes across 45 studies, from @coupe2025impact](images/coupe2025impact-effect-sizes.png){.column-margin}`
  The `From @citekey` form is what the attribution check reads; the key must
  resolve or the build fails.
- Margin placement (`{.column-margin}`) by default, matching the rest of the
  book. Use the full column only for a figure that is unreadable small.
- Screenshots of a published chart are fine (that is what the paper does).
  Do not redraw or re-plot data unless the paper provides the numbers and no
  chart.

## Citations and the bibliography

- Cite only keys that exist in `stylized-facts.bib`. To add a paper, add an
  entry following the conventions in `AGENTS.md` (one field per line,
  trailing commas, a `url`/`doi`/`eprint` locator, arXiv URLs in
  `https://arxiv.org/pdf/<id>.pdf` form) and run `make bib`.
- Where possible, fetch the paper into the local archive
  (`make fetch`, run on a local machine) so the quote and number checks can
  see it. A source with no archived text is reported as unchecked, not as
  wrong — but the point of the table is that it *can* be checked.
- Prefer the primary source. A blog post summarising a paper is `context` at
  best; cite the paper.
- Grey literature (lab system cards, Epoch and METR reports, leaderboards)
  is in scope and often the only source for frontier-model numbers. Cite it
  with a dated `@online` entry.

## Voice and length

- Neutral, declarative, past tense for results ("found", "estimated",
  "reported"). No evaluative adverbs ("impressively", "only").
- No first person, no hedging boilerplate, no "it is worth noting".
- Target: 150–400 words of prose outside the table; the table can be as long
  as the literature requires. If the table exceeds ~15 rows, consider whether
  the question should be split into two chapters (see `tools/book_split.py`).
- Do not use headings above `###`: the file is included under the chapter's
  `## Literature summary (LLM-written)` heading and must nest beneath it.
- Working notes go in `<!-- -->` comments, never in prose. A visible `TODO`
  fails the build.

## Things the file must not contain

- YAML frontmatter (included files cannot carry it; it renders as text).
- The chapter's short answer, or a restatement of it.
- Numbers, quotes, or model names not present in a cited source.
- Any source not in the bibliography.
- Claims about the human chapter ("the authors argue"): the summary is about
  the literature, not about the chapter.

## Template

```markdown
<!-- <slug>.llm.qmd — LLM-written literature summary for “<chapter title>”.
     Follows book/LLM-STYLE-GUIDE.md. -->

<Orientation paragraph: 2–4 sentences on the shape of the evidence.>

| Date | Source | Setting | Finding | Bearing |
|---|---|---|---|---|
| 2023-03 | @key1 | GPT-4; 12 benchmarks; n = 27 models | ... | supports |
| 2024-05 | @key2 | 77 LLMs, 8 benchmarks | First PC explains 80% of variance | supports |
| 2025-02 | @key3 | o1, o3-mini; ARC-AGI-2 | ... | qualifies |

![<what it shows>, from @key2](images/key2-<description>.png){.column-margin}

### Gaps

- <What has not been measured, or only on obsolete models.>
- <Populations, tasks or model classes with no data.>
```

## Checking your work

Before committing: `python3 tools/qmd_validate.py --qmd book/<slug>.qmd`
checks that chapter (with its included summary) on its own; `make check`
runs everything. Both must pass.
