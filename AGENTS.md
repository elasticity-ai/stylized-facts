# AGENTS.md

**This file is the master reference for this repository.** `README.md` points here;
`CLAUDE.md` is a symlink to this file. Keep it current — if you change the build,
the file layout, or the bibliography conventions, update this file in the same commit.

Audience: both humans and coding agents.

## What this repo is

A paper — *Stylized Facts about AI & Human Capabilities* (Tom Cunningham & Ali
Merali) — plus slide decks derived from it. The paper is a list of ~50 claims
about AI capabilities, each backed by cited papers, quotes, and figures.

## Canonical files

| File | Status | What it is |
|---|---|---|
| `stylized-facts.qmd` | **CANONICAL** | The paper. This is the source of truth for all content. Edits go here. |
| `stylized-facts.bib` | **CANONICAL** | The single bibliography. Shared by every document below. |
| `stylized-facts-slides.qmd` | Live | Beamer deck derived from the paper. |
| `stylized-facts-slides-BATES.qmd` | **NOT LIVE** | Beamer deck for a past talk. Kept for reference; do not update it when the paper changes. |
| `stylized-facts-matrices.qmd` | Live (separate) | "Model-Task Matrices" — a standalone companion document. |
| `Copy of stylized-facts.qmd` | **STALE — do not edit** | An old snapshot (776 lines vs the canonical 1039), last touched 2026-01-05. Slated for deletion. |
| `frontier.md` | Unclear | 75 KB of notes; provenance not documented. See "Open questions". |

Rules for agents:

- Content changes go in `stylized-facts.qmd`. Never edit `Copy of stylized-facts.qmd`.
- The slide decks and the matrices document are *derived* views. If a claim changes
  in the paper, check whether the decks repeat it.
- There is exactly one bibliography. Do not create a second `.bib`.

## Building

```sh
quarto render stylized-facts.qmd            # HTML + PDF
quarto render stylized-facts-slides.qmd     # Beamer PDF
```

Requires Quarto (1.8.25 known good) and a TeX distribution with `tikz`,
`sidenotes`, `sectsty`, `xcolor`, `enumitem`, `xy`, `morewrites`.

Rendering writes a lot of intermediate junk (`tikz*.log`, `*_cache/`, `*_files/`,
`latex_output/`). That is build output, not source — it belongs in `.gitignore`.

## Bibliography conventions (`stylized-facts.bib`)

- One field per line, with a trailing comma. This is what makes the file
  machine-parseable; the tests enforce it.
- Every entry needs a source locator: `url`, `doi`, or `eprint`.
- arXiv entries: use `https://arxiv.org/pdf/<id>.pdf` as the `url`, with
  `eprint` and `archiveprefix = {arXiv}`.
- URL preference order: full-text PDF > abstract page > journal landing page.
- Every entry should be cited by at least one document in the repo.
- Run the bibliography tests after editing (see below); they write a
  machine-generated PASS/FAIL block into the top of the `.bib` itself, so the
  current state is visible in the file you are already reading.


Fix the mechanical parts automatically rather than by hand:

```bash
python3 tools/bib_normalize.py
```

It adds the trailing commas and canonicalizes arXiv URLs, and is idempotent.
`--check` reports without writing.

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

```bash
make check          # the gate: bib conventions + arXiv ids + document checks
make bib            # normalize the .bib, then test it
make arxiv          # verify arXiv ids point at the paper each entry claims
make validate       # document checks only
make render         # quarto render stylized-facts.qmd
```

Run `make check` before finalizing any edit to the paper or the bibliography.
A pre-commit hook runs the same thing:

```bash
ln -sf ../../tools/pre-commit .git/hooks/pre-commit
```

CI runs it too (`.github/workflows/check.yml`), with no network and no PDFs.

### What the checks cover

`tools/qmd_validate.py` runs per-document plugins from
`tools/qmd_validate/docs/<document>.qmd.py`. The plugin for the paper checks:

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
`tools/qmd_validate/docs/stylized-facts.qmd.py`, and list it in `doc_checks()`.
To validate a new document, create
`tools/qmd_validate/docs/<name>.qmd.py` — the runner discovers it.

## Known gaps

Current, and reported by the tooling rather than hidden. `make check` passes;
what is left below is coverage, not correctness.

- **`jahani2024earning` is unidentified.** Its arXiv id was malformed and no
  arXiv record matches its title or author, so the fabricated locator has been
  removed and the entry carries a note saying so. Identify the intended work or
  delete it.
- **18 bibliography entries have no locator** and 19 are cited by no document.
  Advisory; see the `INFO` lines from `make bib`.
- **37 of 115 works could not be fetched automatically** — mostly paywalled
  economics journals and vendor pricing pages. Listed in
  `references/manifest.csv` with `status = manual_needed`.
- **One quote is a non-failing "partial" (L190, `morris2023levels`).** It is
  quoted verbatim from a table, and `pdftotext` interleaves table cells, so it
  is genuinely not contiguous in the extracted text. Not an error.

### Resolved

Kept as a record of what the checks caught, since the same failure modes will
recur:

- Six entries pointed at the wrong arXiv paper, two at entirely unrelated work
  (`liu2024mathvista` -> "Credal Learning Theory"; `qiu2023videomme` -> a paper
  on covalent inhibitors). All shared a signature — individually plausible
  author/title/id triples that were each wrong, with `and others` author lists
  — which is what unverified generated citations look like. Corrected against
  the arXiv API; five were uncited and were also renamed so the citekey no
  longer misnames the authors.
- Two quotes did not match their source. `brynjolfsson2023callcenter` was
  quoted as "14% on average" where the paper says 15%, with a "34% improvement
  for novice and low-skilled workers" clause that appears nowhere in it.
  `zhang2025trainbeforetest` was quoted with a "0.61 for direct evaluation
  (5-shot)" clause describing an experiment the paper never ran — it evaluates
  zero-shot only. Both replaced with verbatim quotes making the same point.

## Where to run what

Fetching papers (`make fetch`) belongs on a **local machine**. Publishers
rate-limit and captcha datacenter IP ranges far more aggressively than
residential ones, a good fraction of the bibliography needs hand-downloading
through a logged-in browser, and `pdftotext` and Quarto are already installed
locally. Everything else is pure Python with no network and runs anywhere.

## Open questions

Undocumented; resolve with whoever knows:

- What is `frontier.md`? Live input to the paper, or an archive?
