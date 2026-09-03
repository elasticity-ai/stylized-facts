# stylized-facts

**Stylized Facts about AI & Human Capabilities** — Tom Cunningham & Ali Merali.

A paper surveying what is known about the capabilities of recent AI models and
how they compare to human capabilities. It argues that there is a common latent
factor of capability across LLMs, that this factor differs from the structure of
human capabilities, and it weighs the candidates for the "missing capability"
that would unlock greater economic impact.

The paper is a list of ~50 claims, each backed by cited papers, quotes, and
figures lifted from those papers. Because the evidence is the point, the repo
carries a local copy of every source it could get and checks the paper against
them automatically — see [Checks](#checks) below.

## Files

| File | Status | What it is |
|---|---|---|
| `stylized-facts.qmd` | **canonical** | The paper. All content edits go here. |
| `stylized-facts.bib` | **canonical** | The single bibliography, shared by every document below. |
| `book/` | live | The paper restructured as a Quarto book, one *question* per chapter, published to GitHub Pages. Each question is a human-written `<slug>.qmd` plus an LLM-written `<slug>.llm.qmd` literature summary (one written, the rest stubs). See [The book](#the-book). |
| `stylized-facts-slides.qmd` | live | Beamer deck derived from the paper. |
| `stylized-facts-matrices.qmd` | live | "Model-Task Matrices", a standalone companion document. |
| `stylized-facts-slides-BATES.qmd` | not live | Deck for a past talk. Kept for reference; not updated when the paper changes. |
| `references/` | generated | Local archive of the cited papers. See [references/README.md](references/README.md). |
| `frontier.md` | unclear | 75 KB of notes; provenance undocumented. |

There is exactly one bibliography. Slides and the matrices document are
*derived* views — if a claim changes in the paper, check whether the decks
repeat it.

## Getting started

```bash
git clone https://github.com/elasticity-ai/stylized-facts.git
cd stylized-facts
ln -sf ../../tools/pre-commit .git/hooks/pre-commit   # run checks before each commit
make check
```

The clone is ~200 MB, most of it the PDF archive. To skip the PDFs:

```bash
git clone --filter=blob:none --sparse https://github.com/elasticity-ai/stylized-facts.git
cd stylized-facts && git sparse-checkout set tools images book references/text
```

Building needs Quarto (1.8.25 known good) and a TeX distribution with `tikz`,
`sidenotes`, `sectsty`, `xcolor`, `enumitem`, `xy`, `morewrites`:

```bash
make render      # quarto render stylized-facts.qmd
make render-book # quarto render book   (HTML, to book/_book/)
```

## The book

`book/` is a Quarto book that turns the paper's claims into a flat list of
questions. Every level-2 heading in `stylized-facts.qmd` ("LLMs struggle to
give calibrated answers.") became a chapter named for the question it answers
("Calibration"). Published at
**<https://elasticity-ai.github.io/stylized-facts/>** by
`.github/workflows/book.yml` on every push to `main`.

Every chapter has the same shape:

```markdown
---
title: "The productivity effects of LLM augmentation"    # names the question
claim: "The productivity effects of LLM augmentation varies widely"  # the paper's heading
---

**The productivity effects of LLM augmentation vary widely.**    # short answer, bold

<the evidence: bold lead sentences, paragraphs, bullets, figures, quotes>

## Literature summary (LLM-written) {.unnumbered}
{{< include <slug>.llm.qmd >}}
```

| File | Written by | Contents |
|---|---|---|
| `book/<slug>.qmd` | humans | The answer, as above. First drafts were extracted from the paper. |
| `book/<slug>.llm.qmd` | an LLM | Literature summary for the question: a chronological table, one row per paper, with the paper's title, its setting, its relevant findings each as one bold sentence, and its figure in the row. Specified by [book/LLM-STYLE-GUIDE.md](book/LLM-STYLE-GUIDE.md); one written so far, the rest stubs. |
| `book/tikz/<name>.tex` | humans | Sources of the four tikz figures, pre-rendered to `images/tikz-<name>.svg` by `make tikz` so the book renders with Quarto alone. |

`tools/book_split.py` produced the first version of every human chapter and
holds the claim-to-question mapping. One claim was split into two chapters
(math and programming), and sections the paper has commented out are carried
as chapters marked `status: "commented out in the paper"`. The book shares the
paper's bibliography and images (`book/images` is a symlink), so there is
still one of each, and its chapters run through the same checks as the paper.

## Checks

`make check` verifies the paper and the book against their sources: that citekeys resolve,
that arXiv ids point at the paper they claim, that quoted passages actually
appear in the cited work, and that figures exist and are credited to real
entries. It runs on every push and, if you install the hook above, before every
commit.

Failures are tiered, because a check that is always red stops being read:

- **Correctness** blocks a commit — a broken citekey, a citation pointing at the
  wrong paper, a quote absent from its source.
- **Coverage and informational** results are reported but never block. They
  close by doing research, not by fixing a bug.

Current status, regenerated by `make status` and verified fresh in CI:

<!-- BEGIN CHECK STATUS (generated by tools/status_table.py) -->

| | Check | Status | Count | Notes |
|---|---|:---:|---:|---|
| **Bibliography** | Duplicate citekeys | ✅ | 124 / 124 |  |
|  | One field per line + trailing comma | ✅ | 124 / 124 |  |
|  | Source locator present (url/doi/eprint) | ℹ️ | 106 / 124 | coverage, advisory |
|  | Abstract length <= 500 words | ✅ | 1 / 1 |  |
|  | abstract_source only when abstract is present | ✅ | 0 / 0 |  |
|  | arXiv eprints use arxiv.org/pdf/<id>.pdf URLs | ✅ | 29 / 29 |  |
|  | text_url has local text archive | ✅ | 0 / 0 |  |
|  | Year present | ✅ | 124 / 124 |  |
|  | Entry is cited by some document | ℹ️ | 105 / 124 | coverage, advisory |
| **Citations** | arXiv ids match their bib entry | ✅ | 64 / 64 |  |
| **Paper** | Citekeys resolve in stylized-facts.bib | ✅ | 90 / 90 |  |
|  | Quotes appear in the cited source | ✅ | 23 / 24 | 1 partial, 8 sources not archived |
|  | Numeric claims traced to their cited source | ✅ | 3 / 4 | 1 source not archived, skipped |
|  | Referenced images exist on disk | ✅ | 27 / 27 |  |
|  | Figure attributions resolve | ✅ | 15 / 15 |  |
|  | No accidental @citations in prose | ✅ | — |  |
|  | No merge-conflict markers in source | ✅ | — |  |
|  | No TODO markers in rendered prose | ✅ | — |  |
|  | Local archive coverage of cited works | ℹ️ | 66 / 90 | informational |
| **Book** | Citekeys resolve in stylized-facts.bib | ✅ | 233 / 233 |  |
|  | Quotes appear in the cited source | ✅ | 29 / 30 | 1 partial, 8 sources not archived |
|  | Referenced images exist on disk | ✅ | 34 / 34 |  |
|  | Figure attributions resolve | ✅ | 18 / 18 |  |
|  | No accidental @citations in prose | ✅ | — |  |
|  | No merge-conflict markers in source | ✅ | — |  |
|  | No TODO markers in rendered prose | ✅ | — |  |
|  | Numeric claims traced to their cited source | ✅ | 3 / 4 | 1 source not archived, skipped |
|  | Local archive coverage of cited works | ℹ️ | 66 / 99 | informational |
| **Archive** | Cited works with a local PDF | ℹ️ | 59 / 115 | informational |
|  | Cited works with local fulltext | ℹ️ | 78 / 115 | what the quote checks read |
|  | Works needing manual download | ℹ️ | 37 / 115 | paywalled; see references/manifest.csv |

✅ passing &nbsp; ❌ failing &nbsp; ℹ️ informational or advisory (reported, does not block a commit)

<!-- END CHECK STATUS -->

### Commands

| Command | What it does |
|---|---|
| `make check` | The gate: bibliography, arXiv ids, and document checks |
| `make bib` | Normalize `stylized-facts.bib`, then test it |
| `make arxiv` | Verify arXiv ids point at the paper each entry claims (offline) |
| `make validate` | Document checks only |
| `make status` | Regenerate the table above |
| `make render` | Render the paper to HTML + PDF |
| `make render-book` | Render the book to HTML in `book/_book/` (Quarto only, no TeX) |
| `make tikz` | Rebuild the book's tikz figures from `book/tikz/*.tex` (needs pdflatex, pdftocairo) |
| `make fetch` | Fetch missing papers into `references/` (network; run locally) |
| `make reconcile` | Rewrite `references/manifest.csv` from what is on disk |

## Known gaps

Reported by the tooling rather than hidden. `make check` passes; what is left is
coverage, not correctness.

- `jahani2024earning` is unidentified — its arXiv id was malformed and no arXiv
  record matches its title or author. The fabricated locator has been removed
  and the entry says so. Identify the intended work or delete it.
- 18 bibliography entries have no locator, and 19 are cited by no document.
- 37 of 115 works could not be fetched automatically (paywalled economics
  journals, SSRN, vendor pricing pages). Listed in `references/manifest.csv`
  with `status = manual_needed`; drop a PDF in `references/pdf/<citekey>.pdf`
  and re-run `make fetch` to add one.
- One quote is a non-failing "partial" (L190, `morris2023levels`) — quoted
  verbatim from a table, which `pdftotext` flattens by interleaving cells, so it
  is genuinely not contiguous in the extracted text. Not an error.

## Contributing

**[AGENTS.md](AGENTS.md) is the working reference** — bibliography conventions,
what each check covers, how to add one, and where to run what. Read it before
editing the bibliography or the tooling. `CLAUDE.md` symlinks to it, so coding
agents pick it up automatically.
