"""Plugin loading and execution.

Two kinds of plugin live in tools/qmd_validate/docs/:

  <name>.qmd.py   checks one document, `<name>.qmd` at the repo root. Defines
                  `post_checks()` returning check functions.

  <name>.py       checks a *collection* of documents. Defines
                  `documents(repo_root)` naming the files, `post_checks()`
                  run on each file and merged into one result per check, and
                  optionally `collection_checks()` run once over the
                  concatenation of every file.

A check is any callable taking a ValidationContext and returning a TestResult.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .core import CheckFn, TestResult, ValidationContext


@dataclass(frozen=True)
class PostPlugin:
    path: Path
    module: object

    def post_checks(self) -> list[CheckFn]:
        fn = getattr(self.module, "post_checks", None)
        if fn is None:
            return []
        return list(fn())  # type: ignore[misc]

    def collection_checks(self) -> list[CheckFn]:
        fn = getattr(self.module, "collection_checks", None)
        if fn is None:
            return []
        return list(fn())  # type: ignore[misc]

    def is_collection(self) -> bool:
        return hasattr(self.module, "documents")

    def documents(self, repo_root: Path) -> list[Path]:
        return [Path(p) for p in self.module.documents(repo_root)]  # type: ignore[attr-defined]

    @property
    def label(self) -> str:
        """What the report calls this target: the qmd name, or the plugin name
        for a collection (`book`)."""
        name = self.path.name[: -len(".py")]
        return name


def plugin_path_for_qmd(repo_root: Path, qmd_path: Path) -> Path:
    """Single-document plugins are named after the QMD file, plus `.py`.

    Example:
      stylized-facts.qmd
      -> tools/qmd_validate/docs/stylized-facts.qmd.py
    """
    return repo_root / "tools/qmd_validate/docs" / f"{qmd_path.name}.py"


def load_plugin(path: Path) -> PostPlugin:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load plugin module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return PostPlugin(path=path, module=module)


def run_checks(ctx: ValidationContext, checks: list[CheckFn]) -> list[TestResult]:
    results: list[TestResult] = []
    for check in checks:
        try:
            results.append(check(ctx))
        except Exception as exc:
            results.append(
                TestResult(
                    name=getattr(check, "__name__", "plugin check"),
                    ok=False,
                    category="programmatic",
                    detail=f"(exception: {exc})",
                )
            )
    return results


def run_plugin_checks(ctx: ValidationContext, plugin: PostPlugin) -> list[TestResult]:
    return run_checks(ctx, plugin.post_checks())


# ---------------------------------------------------------------- merging --
_COUNT_RE = re.compile(r"^\((\d+)\s*/\s*(\d+)")


def merge_results(per_file: list[tuple[str, TestResult]]) -> TestResult:
    """Fold one check's results across files into one TestResult.

    The merged detail keeps the `(n/d ...)` shape the status table parses,
    summing both sides, and lists the files that failed. Metadata lists are
    unioned and integers summed, so notes such as "3 partial" or
    "2 sources not archived" still read correctly for the whole.
    """
    first = per_file[0][1]
    oks = [r.ok for _, r in per_file]
    ok: bool | None = False if any(o is False for o in oks) else (None if any(o is None for o in oks) else True)

    nums = [_COUNT_RE.match(r.detail or "") for _, r in per_file]
    if all(nums):
        n = sum(int(m.group(1)) for m in nums)
        d = sum(int(m.group(2)) for m in nums)
        detail = f"({n}/{d} across {len(per_file)} files)"
    else:
        detail = f"({len(per_file)} files)"
    failing = [f"{name}: {r.detail}" for name, r in per_file if r.ok is False]
    if failing:
        detail += " | " + "; ".join(failing[:5]) + (" ..." if len(failing) > 5 else "")

    meta: dict[str, Any] = {}
    for _, r in per_file:
        for k, v in (r.meta or {}).items():
            if isinstance(v, list):
                seen = meta.setdefault(k, [])
                seen.extend(x for x in v if x not in seen)
            elif isinstance(v, bool):
                meta[k] = meta.get(k, False) or v
            elif isinstance(v, (int, float)):
                meta[k] = meta.get(k, 0) + v
            else:
                meta.setdefault(k, v)
    meta["files_failing"] = [name for name, r in per_file if r.ok is False]

    return TestResult(name=first.name, ok=ok, category=first.category, detail=detail, meta=meta)


def run_collection(
    plugin: PostPlugin,
    repo_root: Path,
    build_context: Callable[[Path], ValidationContext],
    only: list[Path] | None = None,
) -> tuple[list[TestResult], list[Path]]:
    """Run a collection plugin. `only` restricts the per-file checks to those
    files (for `--qmd book/<chapter>.qmd`); collection checks still see the
    whole collection."""
    files = plugin.documents(repo_root)
    targets = [f for f in files if only is None or f in only]

    per_check: dict[str, list[tuple[str, TestResult]]] = {}
    order: list[str] = []
    for f in targets:
        ctx = build_context(f)
        for r in run_checks(ctx, plugin.post_checks()):
            if r.name not in per_check:
                order.append(r.name)
            per_check.setdefault(r.name, []).append((str(f.relative_to(repo_root)), r))
    results = [merge_results(per_check[name]) for name in order]

    if plugin.collection_checks() and files:
        whole = build_context(files[0])
        text = "\n\n".join(build_context(f).qmd_text for f in files)
        whole_ctx = ValidationContext(
            repo_root=whole.repo_root,
            qmd_path=files[0].parent,
            bib_path=whole.bib_path,
            bib_tests_path=whole.bib_tests_path,
            qmd_text=text,
        )
        results += run_checks(whole_ctx, plugin.collection_checks())
    return results, targets
