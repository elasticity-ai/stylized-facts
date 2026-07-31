# references/

Local copies of the works cited in `stylized-facts.bib`, keyed by citekey, so
claims and quotes in the paper can be checked against their sources offline.
Built by `tools/fetch_papers.py`. See AGENTS.md for how this fits the rest.

## Layout

| Path | Committed? | What it is |
|---|---|---|
| `text/<citekey>.txt` | **yes** | Plaintext from `pdftotext`, or from an HTML reader for non-paper sources. The grep target. |
| `manifest.csv` | **yes** | One row per citekey: `key, doi, resolver, pdf_url, oa_status, pdf, pdf_bytes, txt, txt_chars, status, note` |
| `pdf/<citekey>.pdf` | **yes** | The PDF itself. ~200 MB total, committed as plain git objects (immutable once fetched, so no git-lfs). |

**Every check in the validation suite reads `text/` only, never `pdf/`.** That
is a hard rule, not a convention: CI checks out without the PDFs, so a check
that touched them would pass locally and fail there.

`status` is one of:

- `ok` — PDF downloaded and text extracted
- `text_only` — no open-access PDF, but readable text was saved (HTML reader,
  or seeded from another repo). Fine for quote-checking; no figures or layout.
- `manual_needed` — nothing reachable automatically; download by hand

## Regenerating

```sh
make fetch        # python3 tools/fetch_papers.py --all --skip-existing
```

`--skip-existing` is not optional in practice. Two of the resolvers work by
title search against OpenAlex and Semantic Scholar, and those are
non-deterministic and rate-limited: a bare re-run can fail to find a paper it
found an hour earlier and downgrade a perfectly good manifest row. If that
happens, `make reconcile` rewrites the manifest from what is actually on disk.

Resolution order per key: direct PDF → arXiv → NBER → Unpaywall → OpenAlex
(DOI, then title) → Semantic Scholar → HTML reader (r.jina.ai) → seed dir.

Every fetched text is validated against its bib entry (title-bigram overlap
plus an author surname near the head of the text) before being saved, so a
resolver returning the wrong paper is rejected and the chain continues rather
than quietly archiving an impostor. Audit what is already on disk with
`make revalidate` (add `--delete-bad` to remove mismatches).

Run it from a local machine, not a cloud box: publishers rate-limit and
captcha datacenter IP ranges far more aggressively, and the manual-download
step below needs a browser anyway.

## Filling a gap by hand

For anything marked `manual_needed`: fetch the PDF in a browser, save it as
`references/pdf/<citekey>.pdf`, then

```sh
python3 tools/fetch_papers.py --all --skip-existing
```

which will extract, validate, and record it. The remaining gaps are mostly
paywalled economics journals, SSRN preprints, and vendor pricing pages that
have no stable document behind them.

## Caveats for quote-checking

These are why the quote checker matches on a squashed letter-only string
rather than raw substrings — see `tools/qmd_validate/checks/quotes.py`.

- **`pdftotext` disagrees with the source about every separator.**
  "sample-\\nefficient" comes out as `sampleefficient`; "BIG-Bench" as
  `BIGBench`. Exact substring matching fails on correct quotes constantly.
- **Footnote and superscript markers land inline** as bare digits, so
  "low levels³ of automation" extracts as "low levels 3 of automation".
- **Multi-column tables are flattened by interleaving cells.** A quote lifted
  verbatim from a table cell may genuinely not be contiguous in the extracted
  text. This is why the quote checker has a non-failing "partial" tier.
- **`%` vs "percent"** — the paper writes `14%` where a source writes
  "14 percent".
- Some PDFs are scans with no text layer; those get no `text/` entry and need
  OCR or manual reading.
