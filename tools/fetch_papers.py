#!/usr/bin/env python3
"""Fetch open-access PDFs + extracted text for papers cited in a Quarto post.

For each citekey used in the target .qmd, resolve an open-access PDF through a
fallback chain (direct PDF -> arXiv -> Unpaywall -> OpenAlex -> OpenAlex title
search -> NBER), download it to references/pdf/<key>.pdf, extract plaintext via
pdftotext to references/text/<key>.txt, and record the outcome in
references/manifest.csv.

Sources that are not papers (blogs, etc.) fall back to readable text via the
r.jina.ai reader and are saved as text only.

Every fetched text (PDF-extracted or jina) is validated against the bib entry
(title-token overlap + author surname in the head of the text); candidates
that fail validation are rejected and the resolver chain continues. Use
--revalidate [--delete-bad] to audit files already on disk without fetching.

Status values in the manifest:
  ok            - PDF downloaded + text extracted (validated unless noted)
  text_only     - no PDF, but readable text saved (HTML/jina fallback or seed)
  manual_needed - nothing reachable/validated; download by hand

Requires: requests (pip), pdftotext (brew install poppler).
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_BIB = REPO / "stylized-facts.bib"
DEFAULT_QMD = REPO / "stylized-facts.qmd"
DEFAULT_PDF_DIR = REPO / "references" / "pdf"
DEFAULT_TEXT_DIR = REPO / "references" / "text"
DEFAULT_MANIFEST = REPO / "references" / "manifest.csv"
DEFAULT_EMAIL = "tom.cunningham@metr.org"

# citekey-like tokens that are actually LaTeX macros, not references. The
# paper's PDF header block defines \@title/\@author/\@date and uses the
# sidenotes package, all of which look like pandoc citekeys to the regex.
NON_CITES = {
    "placemarginal", "sidenotes",
    "author", "date", "maketitle", "title",
}

MIN_TEXT_CHARS = 500
MIN_PDF_BYTES = 5000


# --------------------------------------------------------------------------
# Helpers (several adapted from tecunningham.github.io/tools/fetch_bib_texts.py)
# --------------------------------------------------------------------------
def build_jina_url(url: str) -> str:
    if url.startswith("https://r.jina.ai/"):
        return url
    if "//" not in url:
        return url
    scheme, rest = url.split("//", 1)
    return f"https://r.jina.ai/{scheme}//{rest}"


def is_unusable_fulltext(text: str) -> bool:
    lower = text.lower()
    markers = [
        "verifying you are human",
        "needs to review the security of your connection before proceeding",
        "don't have permission to access",
        "errors.edgesuite.net",
        "enable javascript and cookies to continue",
        "just a moment...",
        "access denied",
        "captcha",
        "no papers found",
        "use of this site constitutes acceptance of our terms",  # jstor block page
        "you may not use the site for bulk downloading",         # jstor block page
        "| semantic scholar",                                    # scraped S2 page
        "semanticscholar.org/search",
    ]
    return any(marker in lower for marker in markers)


# --------------------------------------------------------------------------
# Content validation: does fetched text actually match the bib entry?
# --------------------------------------------------------------------------
STOPWORDS = {
    "the", "and", "for", "with", "from", "their", "that", "this", "are",
    "its", "into", "between", "versus", "toward", "towards", "about", "what",
    "does", "implications", "evidence", "analysis", "review", "approach",
}


def _norm_tokens(s: str) -> list[str]:
    s = re.sub(r"[{}\\$]", "", s.lower())
    return [t for t in re.findall(r"[a-z]{3,}", s) if t not in STOPWORDS]


def _author_surnames(fields: dict[str, str]) -> list[str]:
    raw = fields.get("author", "")
    names = []
    for part in re.split(r"\s+and\s+", raw):
        part = part.strip()
        if not part:
            continue
        # "Surname, First" or "First Surname"
        surname = part.split(",")[0] if "," in part else part.split()[-1]
        surname = re.sub(r"[^A-Za-z-]", "", surname)
        if len(surname) >= 3:
            names.append(surname.lower())
    return names


def match_score(text: str, fields: dict[str, str], head_chars: int = 25000) -> tuple[float, bool]:
    """Return (title_bigram_overlap, author_found) computed on the head of the text.

    Bigrams (consecutive distinctive title words) are much more discriminating
    than bag-of-words: a different paper by the same author on a nearby topic
    shares many unigrams but few title bigrams.
    """
    # token-based head: scanned PDFs often extract pages of symbol soup before
    # real text, so a char-based window can miss the title page entirely
    head_norm = " ".join(_norm_tokens(text)[:4000])
    head = text[:head_chars * 8].lower()  # raw window for author surname search
    title_toks = _norm_tokens(fields.get("title", ""))
    if len(title_toks) >= 2:
        bigrams = [f"{a} {b}" for a, b in zip(title_toks, title_toks[1:])]
        overlap = sum(1 for bg in bigrams if bg in head_norm) / len(bigrams)
    elif title_toks:
        overlap = 1.0 if title_toks[0] in head_norm else 0.0
    else:
        overlap = 1.0  # nothing to check against
    authors = _author_surnames(fields)
    author_found = (not authors) or any(a in head for a in authors)
    return overlap, author_found


def validate_match(text: str, fields: dict[str, str]) -> str | None:
    """Return None if text plausibly is the cited work, else a reason string."""
    if is_unusable_fulltext(text):
        return "unusable (captcha/block/search page)"
    overlap, author_found = match_score(text, fields)
    if overlap >= 0.5 and author_found:
        return None
    if overlap >= 0.7:  # title clearly present; tolerate missing author line
        return None
    if not author_found:
        return f"title bigram overlap {overlap:.0%}, no author surname found"
    return f"title bigram overlap only {overlap:.0%}"


def titles_similar(a: str, b: str) -> bool:
    """Loose symmetric token-overlap test for resolver title-search hits."""
    ta, tb = set(_norm_tokens(a)), set(_norm_tokens(b))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.6


def extract_markdown_content(text: str) -> str:
    marker = "Markdown Content:"
    if marker in text:
        text = text.split(marker, 1)[1]
    return text.lstrip("\n")


def sanitize_markdown(text: str) -> str:
    cleaned = []
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^!\[.*\]\(.*\)", s):
            continue
        if re.match(r"^\[!\[Image", s):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def extract_citekeys_from_qmd(qmd_path: Path) -> set[str]:
    text = qmd_path.read_text(encoding="utf-8")
    raw = re.findall(r"@([A-Za-z][A-Za-z0-9:_-]*)", text)
    # pandoc citekeys may contain internal :_- but not trailing punctuation
    keys = {k.rstrip(":_-") for k in raw}
    return {k for k in keys if k not in NON_CITES}


def pdf_to_text(pdf_bytes: bytes) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise RuntimeError("pdftotext not found; run: brew install poppler")
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "doc.pdf"
        txt_path = Path(tmp) / "doc.txt"
        pdf_path.write_bytes(pdf_bytes)
        proc = subprocess.run(
            [pdftotext, str(pdf_path), str(txt_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "pdftotext failed").strip())
        return txt_path.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# Minimal BibTeX parsing (regex; entries are flat key = {...}, comma-delimited)
# --------------------------------------------------------------------------
def parse_bib(bib_text: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"@(\w+)\{([^,]+),", bib_text):
        key = m.group(2).strip()
        nxt = bib_text.find("\n@", m.end())
        block = bib_text[m.start(): nxt if nxt != -1 else len(bib_text)]
        fields: dict[str, str] = {}
        for fm in re.finditer(r"(?im)^\s*([a-z_]+)\s*=\s*[{\"]", block):
            fname = fm.group(1).lower()
            # capture balanced-ish value: read until matching } or " at same depth
            start = fm.end() - 1
            opener = block[start]
            closer = "}" if opener == "{" else '"'
            depth = 0
            i = start
            val_chars = []
            while i < len(block):
                c = block[i]
                if opener == "{":
                    if c == "{":
                        depth += 1
                        if depth > 1:
                            val_chars.append(c)
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            break
                        val_chars.append(c)
                    else:
                        val_chars.append(c)
                else:  # quoted
                    if c == '"' and i != start:
                        break
                    if i != start:
                        val_chars.append(c)
                i += 1
            fields[fname] = "".join(val_chars).strip()
        entries[key] = fields
    return entries


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------
def doi_from_fields(fields: dict[str, str]) -> str | None:
    doi = fields.get("doi")
    if doi:
        return doi.strip().replace("https://doi.org/", "").replace("http://doi.org/", "")
    url = fields.get("url", "")
    m = re.search(r"doi\.org/(10\.\S+)", url)
    if m:
        return m.group(1).rstrip("/")
    return None


def arxiv_id_from_fields(fields: dict[str, str]) -> str | None:
    ep = fields.get("eprint")
    if ep and re.match(r"\d{4}\.\d{4,5}", ep.strip()):
        return ep.strip()
    for v in (fields.get("url", ""), fields.get("text_url", "")):
        m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})", v)
        if m:
            return m.group(1)
    return None


def nber_number(fields: dict[str, str]) -> str | None:
    url = fields.get("url", "")
    m = re.search(r"nber\.org/(?:papers|system/files/working_papers)/(w\d+)", url)
    if m:
        return m.group(1)
    return None


class Fetcher:
    def __init__(self, email: str, timeout: int, sleep: float):
        self.email = email
        self.timeout = timeout
        self.sleep = sleep
        self.s = requests.Session()
        self.s.headers.update(
            {"User-Agent": f"stylized-facts-fetcher (mailto:{email})"}
        )

    def get(self, url: str, **kw) -> requests.Response | None:
        for attempt in range(2):
            try:
                return self.s.get(url, timeout=self.timeout, **kw)
            except Exception:
                if attempt == 1:
                    return None
                time.sleep(1.0)
        return None

    def download_pdf(self, url: str) -> bytes | None:
        resp = self.get(url, allow_redirects=True)
        if resp is None or resp.status_code != 200:
            return None
        content = resp.content
        ctype = resp.headers.get("content-type", "").lower()
        if not (content[:5] == b"%PDF-" or "application/pdf" in ctype):
            return None
        if len(content) < MIN_PDF_BYTES:
            return None
        return content

    # -- OA url resolvers (return an ordered list of candidate PDF urls) --
    def unpaywall_pdfs(self, doi: str) -> list[str]:
        resp = self.get(f"https://api.unpaywall.org/v2/{quote(doi)}?email={self.email}")
        if resp is None or resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []
        out: list[str] = []
        best = data.get("best_oa_location") or {}
        for loc in [best] + (data.get("oa_locations") or []):
            for u in (loc.get("url_for_pdf"), loc.get("url")):
                if u and u not in out:
                    out.append(u)
        return out

    def openalex_pdfs(self, doi: str) -> list[str]:
        resp = self.get(f"https://api.openalex.org/works/doi:{quote(doi)}?mailto={self.email}")
        if resp is None or resp.status_code != 200:
            return []
        try:
            return self._openalex_oa_urls(resp.json())
        except ValueError:
            return []

    def openalex_title_pdfs(self, title: str) -> list[str]:
        if not title:
            return []
        resp = self.get(
            "https://api.openalex.org/works"
            f"?filter=title.search:{quote(title)}&per-page=3&mailto={self.email}"
        )
        if resp is None or resp.status_code != 200:
            return []
        try:
            results = resp.json().get("results", [])
        except ValueError:
            return []
        out: list[str] = []
        for work in results:
            # only trust hits whose title actually matches the bib title
            if titles_similar(work.get("title") or "", title):
                out += [u for u in self._openalex_oa_urls(work) if u not in out]
        return out

    def semanticscholar_pdfs(self, doi: str | None, title: str) -> list[str]:
        out: list[str] = []
        if doi:
            r = self.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi)}"
                "?fields=openAccessPdf"
            )
            if r is not None and r.status_code == 200:
                try:
                    u = (r.json().get("openAccessPdf") or {}).get("url")
                    if u:
                        out.append(u)
                except ValueError:
                    pass
        if not out and title:
            r = self.get(
                "https://api.semanticscholar.org/graph/v1/paper/search"
                f"?query={quote(title)}&fields=openAccessPdf,title&limit=3"
            )
            if r is not None and r.status_code == 200:
                try:
                    for res in r.json().get("data", []) or []:
                        # only trust hits whose title actually matches
                        if not titles_similar(res.get("title") or "", title):
                            continue
                        u = (res.get("openAccessPdf") or {}).get("url")
                        if u:
                            out.append(u)
                            break
                except ValueError:
                    pass
        return out

    @staticmethod
    def _openalex_oa_urls(work: dict) -> list[str]:
        out: list[str] = []
        locs = [work.get("best_oa_location") or {}, work.get("primary_location") or {}]
        locs += work.get("locations") or []
        for loc in locs:
            u = loc.get("pdf_url")
            if u and u not in out:
                out.append(u)
        oa = (work.get("open_access") or {}).get("oa_url")
        if oa and oa not in out:
            out.append(oa)
        return out


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "?"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bib", default=str(DEFAULT_BIB))
    ap.add_argument("--qmd", default=str(DEFAULT_QMD))
    ap.add_argument("--all", action="store_true", help="All bib entries, not just those cited in --qmd.")
    ap.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    ap.add_argument("--text-dir", default=str(DEFAULT_TEXT_DIR))
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--email", default=DEFAULT_EMAIL)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--sleep", type=float, default=0.5, help="Pause between keys (politeness).")
    ap.add_argument("--max", type=int, help="Limit number of keys attempted.")
    ap.add_argument("--skip-existing", action="store_true", help="Skip keys that already have a PDF (or text).")
    ap.add_argument("--seed-from", help="Dir of <key>.txt to use as text fallback (e.g. blog references/text).")
    ap.add_argument("--only", help="Comma-separated subset of citekeys to fetch.")
    ap.add_argument("--reconcile", action="store_true",
                    help="No fetching: rewrite the manifest from what is actually on disk. "
                         "Use after a re-run downgraded rows for files that still exist "
                         "(title-search resolvers are non-deterministic).")
    ap.add_argument("--revalidate", action="store_true",
                    help="No fetching: validate existing references/text files against the bib and report mismatches.")
    ap.add_argument("--delete-bad", action="store_true",
                    help="With --revalidate: delete text (and pdf) files that fail validation.")
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir); pdf_dir.mkdir(parents=True, exist_ok=True)
    text_dir = Path(args.text_dir); text_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest)
    seed_dir = Path(args.seed_from) if args.seed_from else None

    entries = parse_bib(Path(args.bib).read_text(encoding="utf-8"))
    if args.all:
        keys = set(entries.keys())
    else:
        keys = extract_citekeys_from_qmd(Path(args.qmd))
    if args.only:
        keys &= {k.strip() for k in args.only.split(",")}
    keys = sorted(keys)

    if args.reconcile:
        cols = ["key", "doi", "resolver", "pdf_url", "oa_status", "pdf", "pdf_bytes",
                "txt", "txt_chars", "status", "note"]
        existing: dict[str, dict] = {}
        if manifest_path.exists():
            with manifest_path.open(newline="", encoding="utf-8") as f:
                existing = {row["key"]: row for row in csv.DictReader(f)}

        out_rows, changed = [], 0
        for key in keys:
            pdf_path, txt_path = pdf_dir / f"{key}.pdf", text_dir / f"{key}.txt"
            has_pdf = pdf_path.exists() and pdf_path.stat().st_size > MIN_PDF_BYTES
            has_txt = txt_path.exists() and txt_path.stat().st_size > MIN_TEXT_CHARS
            status = "ok" if has_pdf else ("text_only" if has_txt else "manual_needed")

            row = dict(existing.get(key, {}))
            row.setdefault("resolver", "")
            row.setdefault("pdf_url", "")
            row.setdefault("oa_status", "")
            row.setdefault("note", "")
            if row.get("status") != status:
                changed += 1
                print(f"{key}: {row.get('status', '-')} -> {status}")
            row.update(
                key=key,
                doi=doi_from_fields(entries.get(key) or {}) or row.get("doi", ""),
                pdf=pdf_path.name if has_pdf else "",
                pdf_bytes=pdf_path.stat().st_size if has_pdf else 0,
                txt=txt_path.name if has_txt else "",
                txt_chars=txt_path.stat().st_size if has_txt else 0,
                status=status,
            )
            out_rows.append({c: row.get(c, "") for c in cols})

        out_rows.sort(key=lambda r: (r["status"], r["key"]))
        with manifest_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(out_rows)
        from collections import Counter
        summary = Counter(r["status"] for r in out_rows)
        print(f"\nreconciled {len(out_rows)} rows ({changed} corrected): "
              + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
        return 0

    if args.revalidate:
        bad = 0
        for key in keys:
            fields = entries.get(key)
            txt_path = text_dir / f"{key}.txt"
            pdf_path = pdf_dir / f"{key}.pdf"
            if fields is None:
                print(f"{key}: NOT IN BIB")
                bad += 1
                continue
            if not txt_path.exists():
                state = "pdf only (unvalidated)" if pdf_path.exists() else "missing"
                print(f"{key}: {state}")
                continue
            text = txt_path.read_text(encoding="utf-8", errors="replace")
            reason = validate_match(text, fields)
            if reason is None and len(text) < 5000:
                reason = f"suspiciously short ({len(text)} chars)"
            if reason:
                bad += 1
                print(f"{key}: BAD - {reason}")
                if args.delete_bad:
                    try:
                        txt_path.unlink()
                        if pdf_path.exists():
                            pdf_path.unlink()
                        print(f"  deleted {txt_path.name}")
                    except OSError as exc:
                        print(f"  could not delete: {exc}")
            else:
                print(f"{key}: ok ({len(text)} chars)")
        print(f"\n{bad} bad / {len(keys)} keys")
        return 0 if bad == 0 else 1

    fetcher = Fetcher(args.email, args.timeout, args.sleep)
    rows = []
    attempted = 0

    for key in keys:
        if args.max is not None and attempted >= args.max:
            break
        fields = entries.get(key)
        pdf_path = pdf_dir / f"{key}.pdf"
        txt_path = text_dir / f"{key}.txt"

        if args.skip_existing and pdf_path.exists() and pdf_path.stat().st_size > MIN_PDF_BYTES:
            rows.append(dict(key=key, doi=doi_from_fields(fields or {}) or "",
                             resolver="cached", oa_status="", pdf=pdf_path.name,
                             pdf_bytes=pdf_path.stat().st_size,
                             txt=txt_path.name if txt_path.exists() else "",
                             txt_chars=txt_path.stat().st_size if txt_path.exists() else 0,
                             status="ok", note="skip-existing"))
            print(f"{key}: ok (cached)")
            continue

        attempted += 1
        if fields is None:
            rows.append(dict(key=key, doi="", resolver="", oa_status="", pdf="", pdf_bytes=0,
                             txt="", txt_chars=0, status="manual_needed", note="missing from bib"))
            print(f"{key}: MANUAL (missing from bib)")
            continue

        doi = doi_from_fields(fields)
        arxiv = arxiv_id_from_fields(fields)
        url = fields.get("url", "")
        title = fields.get("title", "")

        # ordered list of (resolver_name, pdf_url) candidates
        candidates: list[tuple[str, str]] = []
        if url.lower().endswith(".pdf"):
            candidates.append(("direct", url))
        if arxiv:
            candidates.append(("arxiv", f"https://arxiv.org/pdf/{arxiv}.pdf"))
        nber = nber_number(fields)
        if nber:
            candidates.append(("nber", f"https://www.nber.org/system/files/working_papers/{nber}/{nber}.pdf"))
        if doi:
            candidates += [("unpaywall", u) for u in fetcher.unpaywall_pdfs(doi)]
            candidates += [("openalex", u) for u in fetcher.openalex_pdfs(doi)]
        # title search helps find OA copies (e.g. NBER) the DOI record omits
        candidates += [("openalex-title", u) for u in fetcher.openalex_title_pdfs(title)]
        candidates += [("semanticscholar", u) for u in fetcher.semanticscholar_pdfs(doi, title.strip("{}"))]
        # dedup by url, preserving order
        seen_urls: set[str] = set()
        candidates = [(n, u) for n, u in candidates if not (u in seen_urls or seen_urls.add(u))]

        pdf_bytes = None
        pdf_text = ""
        used_resolver = ""
        used_url = ""
        pdf_note = ""
        rejected: list[str] = []
        for name, cand in candidates:
            got = fetcher.download_pdf(cand)
            if not got:
                continue
            try:
                text = pdf_to_text(got).strip()
            except Exception as exc:
                text = ""
                extract_err = str(exc)
            else:
                extract_err = ""
            if len(text) >= MIN_TEXT_CHARS:
                # validate extracted text against the bib entry; on mismatch,
                # reject this candidate and keep trying the chain
                reason = validate_match(text, fields)
                if reason:
                    rejected.append(f"{name}:{host_of(cand)} rejected ({reason})")
                    print(f"  {key}: rejected {name} candidate {host_of(cand)}: {reason}")
                    continue
                pdf_bytes, pdf_text, used_resolver, used_url = got, text, name, cand
                break
            # no usable text (e.g. scanned pdf): can't validate; accept only as
            # a last resort, flagged unvalidated
            if pdf_bytes is None:
                pdf_bytes, pdf_text, used_resolver, used_url = got, "", name, cand
                pdf_note = f"unvalidated: no extractable text ({extract_err or 'too short'})"
                # keep looping in case a later candidate yields validated text

        if pdf_bytes:
            pdf_path.write_bytes(pdf_bytes)
            note = pdf_note
            if pdf_text:
                txt_path.write_text(pdf_text + "\n", encoding="utf-8")
                txt_chars = len(pdf_text)
            else:
                txt_chars = 0
                note = note or "pdf ok, text too short / unusable"
            if rejected:
                note = (note + "; " if note else "") + " | ".join(rejected)
            rows.append(dict(key=key, doi=doi or "", resolver=used_resolver, pdf_url=used_url, oa_status="oa",
                             pdf=pdf_path.name, pdf_bytes=len(pdf_bytes),
                             txt=txt_path.name if txt_chars else "", txt_chars=txt_chars,
                             status="ok", note=note))
            print(f"{key}: ok (pdf via {used_resolver}, {len(pdf_bytes)//1024}KB, {txt_chars} chars)")
            time.sleep(args.sleep)
            continue

        # ---- no PDF: try readable text via jina reader (good for blogs) ----
        text = ""
        resolver = ""
        jina_note = ""
        target = url
        # search/landing pages can't contain the work itself
        if re.search(r"semanticscholar\.org/(search|paper)|/action/doSearch", target or ""):
            target = ""
            jina_note = "url is a search page, skipped"
        if target:
            resp = fetcher.get(build_jina_url(target))
            if resp is not None and resp.status_code == 200:
                content = sanitize_markdown(extract_markdown_content(resp.text))
                if len(content) >= MIN_TEXT_CHARS:
                    reason = validate_match(content, fields)
                    if reason is None:
                        text = content
                        resolver = "jina"
                    else:
                        jina_note = f"jina text rejected ({reason})"

        # ---- seed fallback (reuse pre-fetched text from another repo) ----
        if not text and seed_dir is not None:
            seed = seed_dir / f"{key}.txt"
            if seed.exists() and seed.stat().st_size > MIN_TEXT_CHARS:
                cand_text = seed.read_text(encoding="utf-8", errors="replace").strip()
                if validate_match(cand_text, fields) is None:
                    text = cand_text
                    resolver = "seed"

        if text:
            txt_path.write_text(text.strip() + "\n", encoding="utf-8")
            rows.append(dict(key=key, doi=doi or "", resolver=resolver, pdf_url=target if resolver == "jina" else "",
                             oa_status="",
                             pdf="", pdf_bytes=0, txt=txt_path.name, txt_chars=len(text),
                             status="text_only", note=f"host={host_of(url)}"))
            print(f"{key}: text_only (via {resolver}, {len(text)} chars)")
        else:
            detail = "; ".join(x for x in [jina_note] + rejected if x)
            note = f"host={host_of(url)} url={url}" + (f"; {detail}" if detail else "")
            rows.append(dict(key=key, doi=doi or "", resolver="", oa_status="",
                             pdf="", pdf_bytes=0, txt="", txt_chars=0,
                             status="manual_needed", note=note))
            print(f"{key}: MANUAL ({host_of(url)}{'; ' + detail if detail else ''})")
        time.sleep(args.sleep)

    # ---- write manifest (merge with existing rows so --only runs don't clobber it) ----
    cols = ["key", "doi", "resolver", "pdf_url", "oa_status", "pdf", "pdf_bytes", "txt", "txt_chars", "status", "note"]
    merged: dict[str, dict] = {}
    if manifest_path.exists():
        with manifest_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                merged[row["key"]] = row
    for r in rows:
        merged[r["key"]] = r
    out_rows = sorted(merged.values(), key=lambda r: (r["status"], r["key"]))
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    from collections import Counter
    summary = Counter(r["status"] for r in rows)
    print("\n=== summary ===")
    for st in ("ok", "text_only", "manual_needed"):
        print(f"  {st:14s} {summary.get(st, 0)}")
    print(f"  total          {len(rows)}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
