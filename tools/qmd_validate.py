#!/usr/bin/env python3
"""Validate the Quarto documents in this repo against per-document checks.

Each plugin in tools/qmd_validate/docs/ names what it checks: `<name>.qmd.py`
checks the root-level `<name>.qmd`; a plain `<name>.py` checks a collection
of files it lists itself (the book). See AGENTS.md for what the checks cover
and how to add one.

    python3 tools/qmd_validate.py --all
    python3 tools/qmd_validate.py --qmd stylized-facts.qmd
    python3 tools/qmd_validate.py --qmd book/hallucination.qmd   # one chapter
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
from tools.qmd_validate.plugin import (
    PostPlugin,
    load_plugin,
    plugin_path_for_qmd,
    run_collection,
    run_plugin_checks,
)
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


def discover_plugins(repo_root: Path) -> list[PostPlugin]:
    plugin_dir = repo_root / "tools/qmd_validate/docs"
    if not plugin_dir.exists():
        return []
    singles: list[PostPlugin] = []
    collections: list[PostPlugin] = []
    for path in sorted(plugin_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        plugin = load_plugin(path)
        if plugin.is_collection():
            collections.append(plugin)
        else:
            qmd_path = repo_root / path.name[: -len(".py")]
            if qmd_path.exists():
                singles.append(plugin)
    # Canonical documents first, derived collections (the book) after, so the
    # report and the README table read top-down from the source of truth.
    return singles + collections


def run_plugin(repo_root: Path, plugin: PostPlugin, only: list[Path] | None = None) -> dict:
    """Run one plugin. Returns {"qmd": label, "results": [...]}. For a
    collection the label names the plugin and the file count."""
    if plugin.is_collection():
        results, files = run_collection(
            plugin, repo_root, lambda p: build_context(repo_root, p), only=only
        )
        label = f"{plugin.label}/ ({len(files)} files)"
        return {"qmd": label, "results": results}
    qmd_path = repo_root / plugin.label
    ctx = build_context(repo_root, qmd_path)
    return {"qmd": str(qmd_path), "results": run_plugin_checks(ctx, plugin)}


def run_one(repo_root: Path, qmd_path: Path) -> dict:
    """`--qmd path`: a root document with its own plugin, or one file of a
    collection (then only that file's per-file checks run)."""
    plugin_path = plugin_path_for_qmd(repo_root, qmd_path)
    if plugin_path.exists():
        plugin = load_plugin(plugin_path)
        ctx = build_context(repo_root, qmd_path)
        return {"qmd": str(qmd_path), "results": run_plugin_checks(ctx, plugin)}
    for plugin in discover_plugins(repo_root):
        if plugin.is_collection() and qmd_path in plugin.documents(repo_root):
            return run_plugin(repo_root, plugin, only=[qmd_path])
    raise SystemExit(f"No plugin for {qmd_path}. Expected {plugin_path}, or a collection plugin listing it.")


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
        docs = []
        any_fail = False
        for plugin in discover_plugins(repo_root):
            doc = run_plugin(repo_root, plugin)
            doc_json = render_json(doc["results"])
            doc_json["qmd"] = doc["qmd"]
            docs.append({"qmd": doc["qmd"], "results": doc["results"], "json": doc_json})
            if not doc_json["overall_ok"]:
                any_fail = True
        if args.json:
            print(to_json({"overall_ok": not any_fail, "docs": [d["json"] for d in docs]}))
        else:
            for d in docs:
                name = Path(d["qmd"]).name if "/" not in d["qmd"] or d["qmd"].startswith("/") else d["qmd"]
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
        print(render_text(results, title=f"Validation Checks ({doc['qmd']})"))
    return 0 if overall_ok(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
