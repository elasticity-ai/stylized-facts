# AGENTS.md

**The working reference for this repository** — bibliography conventions, what
each check covers, how to add one, and where to run what.

[README.md](README.md) is the front door: what the paper is, which files are
canonical, how to build, and the live status of every check. This file does not
repeat it — start there for orientation, come here to change something.

`CLAUDE.md` symlinks to this file. Keep it current: if you change the build, the
layout, or the bibliography conventions, update this file in the same commit.

## Bibliography conventions (`stylized-facts.bib`)

- One field per line, with a trailing comma. This is what makes the file
  machine-parseable; the tests enforce it.
- Every entry needs a source locator: `url`, `doi`, or `eprint`.
- arXiv entries: use `https://arxiv.org/pdf/<id>.pdf` as the `url`, with
  `eprint` and `archiveprefix = {arXiv}`. `make arxiv` only reads the
  committed cache, so a new arXiv entry is unverified until someone runs
  `make arxiv-refresh` on a machine that can reach arXiv; do that when you
  add one.
- URL preference order: full-text PDF > abstract page > journal landing page.
- Every entry should be cited by at least one document in the repo (the
  paper, the decks, the matrices document, or a book chapter — see
  `CITING_DOCS` in the bib tests).
- Run the bibliography tests after editing (see below); they write a
  machine-generated PASS/FAIL block into the top of the `.bib` itself, so the
  current state is visible in the file you are already reading.


Fix the mechanical parts automatically rather than by hand:

```bash
python3 tools/bib_normalize.py
```

It adds the trailing commas and canonicalizes arXiv URLs, and is idempotent.
`--check` reports without writing.

## The book (`book/`)

The paper restructured as a Quarto book: a flat list of chapters, one per
*question*, where each question was a claim (a level-2 heading) in
`stylized-facts.qmd`. Published to GitHub Pages
(<https://elasticity-ai.github.io/stylized-facts/>) by
`.github/workflows/book.yml` on push to `main`. One-time setting for that to
work: repository Settings → Pages → Source: "GitHub Actions".

- `book/_quarto.yml` — the chapter list, in the paper's order, no parts.
  `bibliography: ../stylized-facts.bib`; there is still exactly one
  bibliography. `book/images` is a symlink to `../images`, likewise. No
  engine: the book has no executable code.
- `book/<slug>.qmd` — **human-written**. Standard format, in this order:
  frontmatter with `title:` (a noun phrase naming the question, e.g. "LLM math
  ability") and `claim:` (the paper's heading verbatim, so the mapping back to
  the paper survives edits); the short answer as **one bold sentence**; the
  evidence, using only bold lead sentences, paragraphs, bullets, margin
  figures and block quotes; a closing `## Literature summary (LLM-written)
  {.unnumbered}` that includes the LLM file. The paper's definition-list
  idiom (`Lead.` / `: detail`) is not used in the book — it becomes a bold
  lead paragraph.
- `book/<slug>.llm.qmd` — **LLM-written** literature summary, pulled in with
  `{{< include >}}` inside a `::: {.llm-summary}` div that `book/book.css`
  tints, so a reader can always tell which half a human wrote. Specified by
  `book/LLM-STYLE-GUIDE.md` (chronological table of results, figures where
  the literature has them, gaps). No YAML frontmatter: included files cannot
  carry any. Unwritten ones are stubs: a callout containing `**Stub.**` and
  the citekeys the chapter already cites. That marker is what
  `tools/book_split.py` keys on — a `.llm.qmd` without it is a written
  summary and is never overwritten by a regeneration.
- `book/tikz/<name>.tex` — standalone sources of the four figures the paper
  draws with knitr `{tikz}` chunks. `make tikz` compiles them to
  `images/tikz-<name>.svg` (pdflatex + pdftocairo), which are committed, so
  rendering the book needs Quarto and nothing else. Edit the `.tex`, run
  `make tikz`, commit both. `.gitignore` un-ignores these two paths from its
  blanket `tikz*` rule for the paper's build residue.
- `index.qmd` is the paper's own introduction; `offcuts.qmd` and
  `references.qmd` close the book.
- Chapters marked `status: "commented out in the paper"` correspond to
  sections the paper hides inside `<!-- -->`. They are shown with a warning
  callout so the claims are not lost; delete the chapter or the callout when
  you decide.

`tools/book_split.py` produced every chapter and holds the claim→question
mapping (`QUESTIONS`) plus the transformations (definition lists, tikz
extraction, footnote distribution). It is **one-shot** for the human
chapters: once they are hand-edited, re-running it would clobber them
(written `.llm.qmd` summaries are preserved, see above). It refuses to
write into a non-empty `book/` without `--force`; use `--out <dir>` to
preview. If the paper gains a section, add a `Q(...)` to the mapping and
either run with `--out` and copy the one new chapter across, or write the
chapter by hand following the format above.

Rendering: `make render-book` (HTML, to `book/_book/`, git-ignored). Verified
with Quarto 1.8.25: no warnings, no citeproc misses. A render is not part of
`make check` because Quarto is not installed everywhere this repo is edited;
the Pages workflow is the render check.

## Local paper archive (`references/`)

Local copies of the cited works, keyed by citekey, so quotes and claims can be
checked against sources offline. Built by `tools/fetch_papers.py`.

- `references/text/<citekey>.txt` — plaintext, **committed**, the grep target
- `references/manifest.csv` — per-key fetch status, **committed**
- `references/arxiv-metadata.csv` — cached arXiv titles, **committed**, so
  `make arxiv` runs offline. Refresh with `make arxiv-refresh`.
- `references/pdf/<citekey>.pdf` — the PDFs themselves, **committed** (~200 MB)

Committed as ordinary git objects rather than via git-lfs: they are immutable
once fetched, so git stores each exactly once and lfs would add a dependency
and a bandwidth quota for no benefit.

**Hard rule: checks read `references/text/` only, never `references/pdf/`.**
CI checks out without them (`git clone --filter` / a sparse checkout is a
supported way to work here), so a check touching the PDFs would pass locally
and fail there.

See [references/README.md](references/README.md) for coverage, how to fill a gap
by hand, and the `pdftotext` caveats that shape how quote matching works.

## Tests

Run `make check` before finalizing any edit to the paper or the bibliography.
The full command list and the current pass/fail counts are in
[README.md](README.md#checks); CI runs the same checks with no network and no
PDFs (`.github/workflows/check.yml`).

The status table in README is generated by `tools/status_table.py` from the
checks themselves, and CI fails if it is stale. After a change that moves any
count, run `make status` and commit the result.

The table deliberately omits the `bibclean lint` row. bibclean does now run
both locally and in CI, but it is not guaranteed to be installed on every
contributor's machine, and someone without it would regenerate a table missing
that row and fail CI. Only repo-determined results belong in a table CI
verifies.

On bibclean itself: every switch passed to it must exist in **version 2.11.4
(1998)**, which is what Ubuntu still ships and therefore what CI has.
`-no-fix-braces` postdates it; including it made CI skip the lint silently for
several runs. Both 2.11.4 and Homebrew's 3.07 accept the current flag set and
agree on the current bibliography (verified in an ubuntu:24.04 container). If
you add a switch, check it against 2.11.4.

### What the checks cover

`tools/qmd_validate.py` runs the plugins in `tools/qmd_validate/docs/`. There
are two kinds:

- `<document>.qmd.py` checks the single root-level `<document>.qmd`
  (`stylized-facts.qmd.py` is the paper).
- `<name>.py` checks a **collection** it lists itself via
  `documents(repo_root)` (`book.py` is every `book/*.qmd`). Its
  `post_checks()` run per file and are merged into one row per check, counts
  summed and failures named by file; its `collection_checks()` run once over
  the concatenation, for checks that only make sense on the whole (the
  numeric claims, which live in one chapter each).

The check functions are shared, in `tools/qmd_validate/checks/document.py`,
and the numeric claims list in `tools/qmd_validate/claims.py`, so the paper
and the book are held to the same standard. Together they check:

| Check | Catches |
|---|---|
| Citekeys resolve | A citation with no bibliography entry |
| **arXiv ids match their entry** | A citation pointing at a different paper than it names |
| Bibliography tests | Duplicate keys, malformed fields, missing years, arXiv URL form |
| **Quotes appear in the cited source** | A quote that has drifted from what the paper actually says |
| Numeric claims traced to source | A figure edited in the prose but not in the source, or vice versa |
| Images exist / attributions resolve | A missing figure, or a figure credited to a citekey that does not exist |
| No merge-conflict markers | Build residue committed into the source |
| No TODO in rendered prose | A working note escaping its `<!-- -->` into the circulated PDF |
| Archive coverage | Informational: how much of the bibliography is checkable at all |

### Two tiers of failure

Not every red result should block a commit, and a check that is always red
stops being read. So:

- **Correctness** failures block: a broken citekey, a quote absent from its
  source, a missing image.
- **Coverage** gaps report but do not block, shown as `INFO`: how many entries
  carry a locator, how many are still cited by some document. These close by
  doing research, not by fixing a bug.

### Adding a check

Add a function taking a `ValidationContext` and returning a `TestResult` to
`tools/qmd_validate/checks/document.py`, and list it in the paper plugin's
`doc_checks()` and the book plugin's `post_checks()` (or `collection_checks()`
if it needs the whole book at once). A check that runs per book chapter
should put its counts at the front of `detail` as `(n/d ...)` so the merge
can sum them. To validate a new root-level document, create
`tools/qmd_validate/docs/<name>.qmd.py` — the runner discovers it. To check
one chapter while editing: `python3 tools/qmd_validate.py --qmd book/<slug>.qmd`.

## Where to run what

Fetching papers (`make fetch`) belongs on a **local machine**. Publishers
rate-limit and captcha datacenter IP ranges far more aggressively than
residential ones, a good fraction of the bibliography needs hand-downloading
through a logged-in browser, and `pdftotext` and Quarto are already installed
locally. Everything else is pure Python with no network and runs anywhere.

## Open questions

Undocumented; resolve with whoever knows:

- What is `frontier.md`? Live input to the paper, or an archive?
