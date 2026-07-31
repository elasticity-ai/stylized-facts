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
| `stylized-facts-slides-BATES.qmd` | Live (variant) | Beamer deck, variant of the above for a specific talk. |
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

## Local paper archive (`references/`)

*Not yet built — see the plan below.*

Local copies of every cited paper, keyed by citekey, so claims and quotes can be
checked against sources offline:

- `references/pdf/<citekey>.pdf` — the PDF
- `references/text/<citekey>.txt` — plaintext (`pdftotext`), the grep target
- `references/manifest.csv` — one row per key with fetch status

**Design constraint:** every validation check must run from `references/text/`
alone. The PDFs may be absent (git-lfs not pulled, or a CI checkout), so nothing
in the test suite may depend on them.

## Tests

*Not yet built — see the plan below.*

```sh
python3 tools/stylized-facts.bib.tests.py   # bib conventions; updates the block in the .bib
python3 tools/qmd_validate.py --all         # document checks
python3 tools/qmd_validate.py --all --json  # same, machine-readable
```

Run both before finalizing any edit to the paper or the bibliography.

## Planned work (agent-maintainability)

Ported from the patterns in `~/tecunningham.github.io` (`tools/fetch_papers.py`,
`tools/ai.bib.tests.py`, `tools/qmd_validate/`).

- [ ] **Phase 0 — hygiene.** Restore a real `.gitignore` (the repo currently has a
      `.gitignore.html` containing `*.html`, apparently a rename accident, and so
      tracks 79 `tikz*.log` files plus caches and `.DS_Store`). Resolve the
      committed merge conflict in `stylized-facts.html`. Delete stale copies.
      Write this file. ← in progress
- [ ] **Phase 1 — `references/`.** Port `fetch_papers.py`; resolve and archive all
      115 cited papers. Run locally, not in the cloud (see below).
- [ ] **Phase 2 — bib tests.** Port `ai.bib.tests.py`.
- [ ] **Phase 3 — document validator.** Port `qmd_validate/`; write a plugin for
      `stylized-facts.qmd` covering quote verification against the local archive,
      image provenance, and a claims registry.
- [ ] **Phase 4 — wire up.** `make check`, pre-commit hook, CI.

### Where to run what

Phase 1 (fetching papers) should be run **locally**. Publisher sites rate-limit
and captcha datacenter IP ranges much more aggressively than residential ones,
roughly a quarter of the bibliography will need hand-downloading through a
browser, and `pdftotext` and Quarto are already installed on the local machine.

Phases 2–4 are pure code with no network dependency and can be written anywhere.

## Open questions

These are undocumented and should be resolved by whoever knows:

- What is `frontier.md`? Is it live input to the paper, or an archive?
- Are `stylized-facts.pdf` / `stylized-facts-slides.pdf` meant to stay committed?
  They are the bulk of the 42 MB `.git`.
- `stylized-facts-slides-BATES.qmd` — which talk, and is it still needed?
