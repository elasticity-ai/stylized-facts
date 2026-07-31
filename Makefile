# Entry points for this repo. See AGENTS.md for what each check covers.
.PHONY: check bib validate render fetch reconcile revalidate clean help

help:
	@echo "make check       - bib conventions + document validation (run before committing)"
	@echo "make bib         - normalize stylized-facts.bib, then run its tests"
	@echo "make validate    - run the document checks only"
	@echo "make render      - render the canonical paper to HTML + PDF"
	@echo "make fetch       - fetch missing papers into references/ (network; run locally)"
	@echo "make reconcile   - rewrite references/manifest.csv from what is on disk"
	@echo "make revalidate  - re-check archived texts against the bibliography"
	@echo "make clean       - remove Quarto and LaTeX build output"

# The gate. Fails on correctness problems (bad citekeys, a quote that is not in
# its source); bibliography coverage gaps are reported but do not fail.
check: bib validate

bib:
	python3 tools/bib_normalize.py
	python3 "tools/stylized-facts.bib.tests.py"

validate:
	python3 tools/qmd_validate.py --all

render:
	quarto render stylized-facts.qmd

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
