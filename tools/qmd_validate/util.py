from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def find_repo_root(start: Path) -> Path:
    """Best-effort repo root detection for Quarto execution contexts."""
    for candidate in [start, *start.parents]:
        if (candidate / "tools").is_dir() and (candidate / "stylized-facts.bib").exists():
            return candidate
    return start


def normalize_ws(text: str) -> str:
    """Collapse all whitespace runs to single spaces.

    Essential before matching quotes against pdftotext output, which
    hard-wraps lines: a quote spanning a line break will not substring-match
    the source otherwise.
    """
    return " ".join(text.split())


def to_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=False)
