# Entry points for this repo. See AGENTS.md for what each check covers.
.PHONY: check bib arxiv arxiv-refresh validate status render render-book tikz fetch reconcile revalidate clean help

help:
	@echo "make check       - bib conventions + arXiv ids + document validation (run before committing)"
	@echo "make bib         - normalize stylized-facts.bib, then run its tests"
	@echo "make arxiv       - verify arXiv ids point at the paper each entry claims"
	@echo "make arxiv-refresh - re-query the arXiv API and rewrite the cache (network)"
	@echo "make validate    - run the document checks only"
	@echo "make status      - regenerate the check-status table in README.md"
	@echo "make render      - render the canonical paper to HTML + PDF"
	@echo "make render-book - render the question-per-chapter book (book/) to book/_book/"
	@echo "make tikz        - rebuild the book's tikz figures (book/tikz/*.tex -> images/tikz-*.svg)"
	@echo "make fetch       - fetch missing papers into references/ (network; run locally)"
	@echo "make reconcile   - rewrite references/manifest.csv from what is on disk"
	@echo "make revalidate  - re-check archived texts against the bibliography"
	@echo "make clean       - remove Quarto and LaTeX build output"

# The gate. Fails on correctness problems (bad citekeys, a citation pointing at
# the wrong paper, a quote that is not in its source); bibliography coverage
# gaps are reported but do not fail.
#
# Every check runs even when an earlier one fails, so one problem does not hide
# the rest; the exit code is non-zero if any failed.
check:
	@fail=0; \
	$(MAKE) --no-print-directory bib      || fail=1; \
	echo; $(MAKE) --no-print-directory arxiv    || fail=1; \
	echo; $(MAKE) --no-print-directory validate || fail=1; \
	echo; python3 tools/status_table.py --check || fail=1; \
	echo; \
	if [ $$fail -eq 0 ]; then echo "all checks passed"; \
	else echo "checks FAILED - see above (coverage INFO lines are not failures)"; fi; \
	exit $$fail

bib:
	python3 tools/bib_normalize.py
	python3 "tools/stylized-facts.bib.tests.py"

# Offline: reads references/arxiv-metadata.csv, which is committed.
arxiv:
	python3 tools/arxiv_check.py --check

arxiv-refresh:
	python3 tools/arxiv_check.py --refresh

validate:
	python3 tools/qmd_validate.py --all

# Regenerates the table in README.md from the checks. `make check` verifies it
# is current rather than rewriting it, so CI cannot silently paper over drift.
status:
	python3 tools/status_table.py

render:
	quarto render stylized-facts.qmd

# HTML only. No engine, no R, no TeX needed: the tikz figures are pre-rendered
# SVGs (see `tikz`).
render-book:
	quarto render book

# The book's tikz figures. Sources in book/tikz/<name>.tex (standalone
# documents), output images/tikz-<name>.svg, committed so `quarto render`
# needs no TeX. Needs pdflatex (texlive-pictures) and pdftocairo (poppler).
tikz:
	@set -e; tmp=$$(mktemp -d); \
	for src in book/tikz/*.tex; do \
	  name=$$(basename $$src .tex); \
	  pdflatex -interaction=batchmode -halt-on-error -output-directory $$tmp $$src >/dev/null \
	    || { echo "pdflatex failed on $$src; see $$tmp/$$name.log"; exit 1; }; \
	  pdftocairo -svg $$tmp/$$name.pdf images/tikz-$$name.svg; \
	  echo "images/tikz-$$name.svg"; \
	done; rm -rf $$tmp

# Network-bound; see AGENTS.md for why this belongs on a local machine.
# --skip-existing matters: title-search resolvers are non-deterministic, so a
# bare re-run can fail for a paper already on disk.
fetch:
	python3 tools/fetch_papers.py --all --skip-existing

reconcile:
	python3 tools/fetch_papers.py --all --reconcile

revalidate:
	python3 tools/fetch_papers.py --all --revalidate

clean:
	git clean -Xfd
