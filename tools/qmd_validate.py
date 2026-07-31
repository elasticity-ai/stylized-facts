#!/usr/bin/env python3
"""Validate the Quarto documents in this repo against per-document checks.

Each document with a plugin in tools/qmd_validate/docs/ is checked. See
AGENTS.md for what the checks cover and how to add one.

    python3 tools/qmd_validate.py --all
    python3 tools/qmd_validate.py --qmd stylized-facts.qmd
    python3 tools/qmd_validate.py --all --json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # Allow `import tools.qmd_validate...` when executing this file directly.
    sys.path.insert(0, str(REPO_ROOT))

from tools.qmd_validate.core import ValidationContext
from tools.qmd_validate.plugin import load_plugin, plugin_path_for_qmd, run_plugin_checks
from tools.qmd_validate.report import overall_ok, render_json, render_text
from tools.qmd_validate.util import find_repo_root, read_text, to_json


def build_context(repo_root: Path, qmd_path: Path) -> ValidationContext:
    bib_path = repo_root / "stylized-facts.bib"
    bib_tests_path = repo_root / "tools" / "stylized-facts.bib.tests.py"
    qmd_text = read_text(qmd_path)
    return ValidationContext(
        repo_root=repo_root,
        qmd_path=qmd_path,
        bib_path=bib_path,
        bib_tests_path=bib_tests_path,
        qmd_text=qmd_text,
    )


def discover_qmd_paths_from_plugins(repo_root: Path) -> list[Path]:
    plugin_dir = repo_root / "tools/qmd_validate/docs"
    if not plugin_dir.exists():
        return []
    qmds: list[Path] = []
    seen: set[Path] = set()
    for plugin in sorted(plugin_dir.glob("*.qmd.py")):
        qmd_name = plugin.name[: -len(".py")]
        qmd_path = repo_root / qmd_name
        if qmd_path.exists() and qmd_path not in seen:
            qmds.append(qmd_path)
            seen.add(qmd_path)
    return qmds


def run_one(repo_root: Path, qmd_path: Path) -> dict:
    ctx = build_context(repo_root, qmd_path)
    plugin_path = plugin_path_for_qmd(repo_root, qmd_path)
    if not plugin_path.exists():
        raise SystemExit(f"No plugin for {qmd_path.name}. Expected: {plugin_path}")
    plugin = load_plugin(plugin_path)
    results = run_plugin_checks(ctx, plugin)
    return {"qmd": str(qmd_path), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--qmd", help="Path to a single QMD to validate.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate every document that has a plugin in tools/qmd_validate/docs/.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    repo_root = find_repo_root(Path.cwd())

    if args.all:
        qmds = discover_qmd_paths_from_plugins(repo_root)
        docs = []
        any_fail = False
        for qmd_path in qmds:
            doc = run_one(repo_root, qmd_path)
            doc_json = render_json(doc["results"])
            doc_json["qmd"] = doc["qmd"]
            docs.append({"qmd": doc["qmd"], "results": doc["results"], "json": doc_json})
            if not doc_json["overall_ok"]:
                any_fail = True
        if args.json:
            print(to_json({"overall_ok": not any_fail, "docs": [d["json"] for d in docs]}))
        else:
            for d in docs:
                name = Path(d["qmd"]).name
                print(render_text(d["results"], title=f"Validation Checks ({name})"))
                print()
        return 1 if any_fail else 0

    if not args.qmd:
        parser.error("Specify --qmd or --all")

    qmd_path = Path(args.qmd)
    if not qmd_path.is_absolute():
        qmd_path = repo_root / qmd_path

    doc = run_one(repo_root, qmd_path)
    results = doc["results"]
    if args.json:
        print(to_json(render_json(results)))
    else:
        print(render_text(results))
    return 0 if overall_ok(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
