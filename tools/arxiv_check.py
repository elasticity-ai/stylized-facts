#!/usr/bin/env python3
"""Check that each arXiv ID in the bibliography is the paper the entry claims.

An arXiv URL is a precise pointer, which makes a wrong one silently
authoritative: the citation renders, the link resolves, a reader clicks
through to a real paper — just not the one being cited. This repo's
bibliography had entries pointing at unrelated work ("MathVista" -> "Credal
Learning Theory"), so the pointer is worth verifying.

Fetches title and authors from the arXiv API and compares them with the bib
entry, caching the result in references/arxiv-metadata.csv. The cache is
committed, so `--check` runs offline and in CI; refresh it with `--refresh`
when arXiv entries are added or changed.

    python3 tools/arxiv_check.py --refresh   # hit the API, rewrite the cache
    python3 tools/arxiv_check.py --check     # offline, exit 1 on a mismatch
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BIB = REPO_ROOT / "stylized-facts.bib"
CACHE = REPO_ROOT / "references" / "arxiv-metadata.csv"
COLS = ["key", "arxiv_id", "bib_title", "arxiv_title", "arxiv_authors", "overlap", "verdict"]

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})")
BATCH = 20

# Title words too generic to distinguish one paper from another.
STOPWORDS = {
    "the", "and", "for", "with", "from", "their", "that", "this", "are", "its",
    "into", "between", "using", "via", "how", "what", "does", "can", "you",
    "large", "language", "models", "model", "llms", "llm", "ai", "evaluating",
    "evaluation", "benchmark", "benchmarks", "towards", "toward", "study",
}


def norm_tokens(text: str) -> set[str]:
    text = re.sub(r"[{}\\$]", " ", text.lower())
    return {t for t in re.findall(r"[a-z]{3,}", text) if t not in STOPWORDS}


def title_overlap(bib_title: str, arxiv_title: str) -> float:
    a, b = norm_tokens(bib_title), norm_tokens(arxiv_title)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"@(\w+)\{([^,]+),", text):
        key = m.group(2).strip()
        nxt = text.find("\n@", m.end())
        block = text[m.start(): nxt if nxt != -1 else len(text)]
        fields = {}
        for fm in re.finditer(r"(?im)^\s*([a-z_]+)\s*=\s*\{(.*?)\},?\s*$", block):
            fields[fm.group(1).lower()] = fm.group(2)
        entries[key] = fields
    return entries


def arxiv_id_of(fields: dict[str, str]) -> str | None:
    eprint = fields.get("eprint", "")
    m = ARXIV_ID_RE.search(eprint)
    if m:
        return m.group(1)
    # `note` is deliberately not scanned: it is prose, and a note explaining
    # that an id was wrong would otherwise be read as an id to go and check.
    for field in ("url", "journal", "howpublished"):
        value = fields.get(field, "")
        if "arxiv" in value.lower():
            m = ARXIV_ID_RE.search(value)
            if m:
                return m.group(1)
    return None


def fetch_arxiv(ids: list[str]) -> dict[str, tuple[str, list[str]]]:
    """Map arXiv id -> (title, authors). Missing ids are simply absent."""
    out: dict[str, tuple[str, list[str]]] = {}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i: i + BATCH]
        url = (
            "http://export.arxiv.org/api/query?id_list="
            + ",".join(chunk)
            + f"&max_results={len(chunk)}"
        )
        try:
            raw = urllib.request.urlopen(url, timeout=45).read().decode("utf-8", "replace")
        except Exception as exc:  # network problems are reported, not fatal
            print(f"  ! arXiv query failed for {chunk[0]}...: {exc}", file=sys.stderr)
            continue
        for m in re.finditer(r"<entry>(.*?)</entry>", raw, re.S):
            block = m.group(1)
            aid = re.search(r"<id>https?://arxiv\.org/abs/([^<v]+)", block)
            title = re.search(r"<title>(.*?)</title>", block, re.S)
            if not aid or not title:
                continue
            authors = re.findall(r"<name>(.*?)</name>", block)
            out[aid.group(1).strip()] = (" ".join(title.group(1).split()), authors)
        time.sleep(3.0)  # arXiv asks for one query per 3 seconds
    return out


def verdict_for(overlap: float) -> str:
    if overlap >= 0.5:
        return "ok"
    if overlap >= 0.25:
        return "suspect"
    return "MISMATCH"


def refresh(bib_path: Path) -> int:
    entries = parse_bib(bib_path.read_text(encoding="utf-8"))
    targets = {k: aid for k, f in entries.items() if (aid := arxiv_id_of(f))}
    print(f"{len(targets)} entries carry an arXiv id; querying arXiv...")

    meta = fetch_arxiv(sorted(set(targets.values())))
    rows = []
    for key in sorted(targets):
        aid = targets[key]
        bib_title = entries[key].get("title", "")
        if aid not in meta:
            rows.append(dict(key=key, arxiv_id=aid, bib_title=bib_title,
                             arxiv_title="", arxiv_authors="", overlap="",
                             verdict="not_found"))
            continue
        arxiv_title, authors = meta[aid]
        overlap = title_overlap(bib_title, arxiv_title)
        rows.append(dict(key=key, arxiv_id=aid, bib_title=bib_title,
                         arxiv_title=arxiv_title,
                         arxiv_authors="; ".join(authors[:4]),
                         overlap=f"{overlap:.2f}", verdict=verdict_for(overlap)))

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    report(rows)
    print(f"\ncache: {CACHE}")
    return 0


def report(rows: list[dict]) -> int:
    bad = [r for r in rows if r["verdict"] in ("MISMATCH", "suspect")]
    missing = [r for r in rows if r["verdict"] == "not_found"]
    for r in sorted(bad, key=lambda r: r["overlap"]):
        print(f"{r['verdict']:9} {r['key']}  (arXiv {r['arxiv_id']}, overlap {r['overlap']})")
        print(f"          bib says   : {r['bib_title'][:74]}")
        print(f"          arXiv says : {r['arxiv_title'][:74]}")
        if r["arxiv_authors"]:
            print(f"          arXiv authors: {r['arxiv_authors'][:74]}")
    for r in missing:
        print(f"not_found {r['key']}  (arXiv {r['arxiv_id']} returned no entry)")
    ok = len(rows) - len(bad) - len(missing)
    print(f"\n{ok}/{len(rows)} arXiv ids match their bib entry"
          f"{f', {len(bad)} mismatched' if bad else ''}"
          f"{f', {len(missing)} not found' if missing else ''}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bib", default=str(DEFAULT_BIB))
    ap.add_argument("--refresh", action="store_true", help="Query arXiv and rewrite the cache.")
    ap.add_argument("--check", action="store_true", help="Read the cache only; exit 1 on a mismatch.")
    args = ap.parse_args()

    if args.refresh:
        return refresh(Path(args.bib))

    if not CACHE.exists():
        print(f"No cache at {CACHE}. Run: python3 tools/arxiv_check.py --refresh")
        return 1
    with CACHE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return report(rows)


if __name__ == "__main__":
    raise SystemExit(main())
