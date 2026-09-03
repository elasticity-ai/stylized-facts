# Style guide for the LLM-written literature summaries

Every chapter of the book (`book/<slug>.qmd`) ends by including
`book/<slug>.llm.qmd`: a literature summary written and maintained by an LLM.
This guide is the specification for those files. The chapter's human-written
half answers the question; the LLM half shows the reader **what the literature
says, paper by paper, in the order it appeared**, so they can judge the answer
for themselves.

`book/latent-factor-of-llm-intelligence.llm.qmd` is the worked example. The
other files are stubs until written.

## What the file is for

- **Coverage**, not argument. The human chapter makes the case. The summary
  lists the evidence, including evidence that cuts against the chapter's short
  answer.
- **Traceability.** Every number and quote must be checkable against a
  source in `stylized-facts.bib`. The repo's checks run on these files exactly
  as they run on the paper (`make check`).
- **Chronology.** The table is ordered by date so the reader can see how the
  picture changed as models did. A 2023 result about GPT-4 and a 2025 result
  about a reasoning model are different facts, not a disagreement.

## Required structure

The file is plain Quarto markdown, included into a chapter. In order:

1. **One-paragraph orientation** (2–4 sentences). What kind of evidence
   exists for this question, how much of it, and the date range. No verdict.
2. **The table** (see below). This is the body of the file. Figures go
   *inside* the table, in the row of the paper they come from — never
   outside it.
3. **Gaps** — a short bullet list of what has *not* been measured, or has
   only been measured on obsolete models. This is the most useful section for
   the authors; do not skip it.

Do not add a conclusion or a synthesis paragraph. Do not repeat the chapter's
short answer.

## The table

One row per paper. Chronological by publication (or preprint) date, oldest
first. Five columns:

| Column | Contents |
|---|---|
| **Date** | `YYYY-MM`. Preprint date if that is what is cited. |
| **Paper** | The paper's title in italics, then the citation on its own line: `*Title*<br>@citekey`. |
| **Setting** | What was measured on what: models (named, with version), benchmark or task, sample size, population if human. Terse. |
| **Findings** | Each finding relevant to the question as **one bold sentence**, typically one per paper, several when the paper has several. Below each bold sentence, at most one or two plain sentences of supporting detail: the numbers, the comparison baseline, a verbatim quote. |
| **Figure** | The paper's own figure that carries the finding, as an inline image with a caption crediting the source: `![PC1 explains ~80% of variance, from @key](images/key-scree.png)`. Empty when the paper has no such figure. |

Separate a row's multiple findings and their detail with `<br>`; pipe tables
cannot hold paragraphs. Set the column widths with the separator line, e.g.
`|:--|:-----|:----|:--------------|:----------|`, so the Findings column gets the
room.

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
- **The bold sentence is the finding, not the topic.** "PC1 explains nearly
  80% of variance across 77 models." Not "Analyses variance structure."
- No column for the paper's bearing on the chapter's answer. Let the bold
  findings speak; the reader judges.

## Figures

Include a figure when the paper's own chart shows the finding better than a
number can — a scaling curve, a distribution of effect sizes, a
model-by-benchmark heatmap. Otherwise leave the cell empty.

- Save the image to `images/` at the repo root (the book sees it through the
  `book/images` symlink). Name it `<citekey>-<short-description>.png`.
- Caption it with what it shows and the credit: `![..., from @citekey](...)`.
  The `from @citekey` form is what the attribution check reads; the key must
  resolve or the build fails.
- Figures go in the table cell, in the body of the page. Nothing in the book
  goes in the margin; do not use `{.column-margin}`.
- Screenshots of a published chart are fine (that is what the paper does).
  Do not redraw or re-plot data unless the paper provides the numbers and no
  chart.

## Citations and the bibliography

- Cite only keys that exist in `stylized-facts.bib`. To add a paper, add an
  entry following the conventions in `AGENTS.md` (one field per line,
  trailing commas, a `url`/`doi`/`eprint` locator, arXiv URLs in
  `https://arxiv.org/pdf/<id>.pdf` form) and run `make bib`. A new arXiv
  entry also needs `make arxiv-refresh` run once from a machine that can
  reach arXiv.
- Where possible, fetch the paper into the local archive
  (`make fetch`, run on a local machine) so the quote and number checks can
  see it. A source with no archived text is reported as unchecked, not as
  wrong — but the point of the table is that it *can* be checked.
- Prefer the primary source. A blog post summarising a paper is context at
  best; cite the paper.
- Grey literature (lab system cards, Epoch and METR reports, leaderboards)
  is in scope and often the only source for frontier-model numbers. Cite it
  with a dated `@online` entry.

## Voice and length

- Neutral, declarative, past tense for results ("found", "estimated",
  "reported"). No evaluative adverbs ("impressively", "only").
- No first person, no hedging boilerplate, no "it is worth noting".
- Target: 100–300 words of prose outside the table; the table can be as long
  as the literature requires. If the table exceeds ~20 rows, consider whether
  the question should be split into two chapters (see `tools/book_split.py`).
- Do not use headings above `###`: the file is included under the chapter's
  `## Literature summary (LLM-written)` heading and must nest beneath it.
- Working notes go in `<!-- -->` comments, never in prose. A visible `TODO`
  fails the build.

## Things the file must not contain

- YAML frontmatter (included files cannot carry it; it renders as text).
- The chapter's short answer, or a restatement of it.
- The literal `**Stub.**` marker — that is how `tools/book_split.py` tells
  an unwritten stub from a written summary it must preserve.
- Numbers, quotes, or model names not present in a cited source.
- Any source not in the bibliography.
- Claims about the human chapter ("the authors argue"): the summary is about
  the literature, not about the chapter.

## Template

```markdown
<!-- <slug>.llm.qmd — LLM-written literature summary for “<chapter title>”.
     Follows book/LLM-STYLE-GUIDE.md. -->

<Orientation paragraph: 2–4 sentences on the shape of the evidence.>

| Date | Paper | Setting | Findings | Figure |
|:--|:-----|:----|:--------------|:----------|
| 2023-06 | *<Title>*<br>@key1 | 29 LLMs on 27 HELM tasks | **<One-sentence finding.>**<br>Detail with numbers. "A verbatim quote of eight or more words." | ![<what it shows>, from @key1](images/key1-<description>.png) |
| 2024-05 | *<Title>*<br>@key2 | 77 models, 8 benchmarks | **<Finding one.>**<br>Detail.<br>**<Finding two.>**<br>Detail. | |

### Gaps

- <What has not been measured, or only on obsolete models.>
- <Populations, tasks or model classes with no data.>
```

## Checking your work

Before committing: `python3 tools/qmd_validate.py --qmd book/<slug>.qmd`
checks that chapter (with its included summary) on its own; `make check`
runs everything. Both must pass. Render with `make render-book` and look at
the table: a pipe table with a very long cell can render badly, and the fix
is more `<br>`, not fewer words.
