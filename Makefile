# Entry points for this repo. See AGENTS.md for what each check covers.
.PHONY: check bib arxiv arxiv-refresh validate render fetch reconcile revalidate clean help

help:
	@echo "make check       - bib conventions + arXiv ids + document validation (run before committing)"
	@echo "make bib         - normalize stylized-facts.bib, then run its tests"
	@echo "make arxiv       - verify arXiv ids point at the paper each entry claims"
	@echo "make arxiv-refresh - re-query the arXiv API and rewrite the cache (network)"
	@echo "make validate    - run the document checks only"
	@echo "make render      - render the canonical paper to HTML + PDF"
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
