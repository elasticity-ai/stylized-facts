"""Shared validation framework for the Quarto documents in this repo.

Provides:
- A small, stable result model (`TestResult`)
- Reusable checks (citekeys, bibliography conventions, quote verification)
- Report rendering (text / JSON)
- Per-document plugin loading. Plugins live in `tools/qmd_validate/docs/` and
  are named after the source QMD, with an added `.py` suffix:

    stylized-facts.qmd  ->  tools/qmd_validate/docs/stylized-facts.qmd.py

Ported from tecunningham.github.io/tools/qmd_validate/, adapted for a repo
whose documents sit at the root rather than under posts/.
"""
