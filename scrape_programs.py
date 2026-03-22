#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ouinfo.ca"
BASE_PROGRAMS = f"{BASE}/programs"
OUTPUT_JSON = "ouinfo_programs.json"


@dataclass(frozen=True)
class CliArgs:
    limit: int | None
    output: str


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}

FALLBACK_LISTING_GROUPS = (
    "a",
    "b",
    "c",
    "d-e",
    "f-g",
    "h",
    "i",
    "j-l",
    "m",
    "n-p",
    "q-s",
    "t-z",
)

DETAIL_SLEEP_SEC = 1.0
LISTING_SLEEP_SEC = 0.3


def get_page(url: str, session: requests.Session) -> str:
    response = session.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def pager_hrefs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[str] = []
    for anchor in soup.select("div.results-meta ul.pagination a[href]"):
        href = anchor.get("href")
        if not href or "programs/search" not in href:
            continue
        absolute = urljoin(BASE, href)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def _program_path_ok(path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[0] != "programs":
        return False
    hub = parts[1]
    if hub in ("search", "all", "category", "universities", "compare"):
        return False
    return True


def program_links_on_page(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[str] = []
    for anchor in soup.select("article.result-program h2.result-heading a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(BASE, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if "ouinfo.ca" not in (parsed.netloc or "").lower():
            continue
        if not _program_path_ok(parsed.path):
            continue
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def gather_listing_pages(session: requests.Session) -> list[str]:
    print("Discovering listing pages (each letter group + pagination)…")
    first_pages = [
        f"{BASE}/programs/search/?search=&group={g}"
        for g in FALLBACK_LISTING_GROUPS
    ]
    seen: set[str] = set()
    out: list[str] = []
    for fp in first_pages:
        time.sleep(LISTING_SLEEP_SEC)
        html = get_page(fp, session)
        for u in [fp, *pager_hrefs(html)]:
            if u not in seen:
                seen.add(u)
                out.append(u)
    print(f"  -> {len(out)} listing page URL(s)")
    return out


def _squish(s: str) -> str:
    return " ".join(s.split())


def _to_na(s: str) -> str:
    t = _squish(s) if s else ""
    return t if t else "n/a"


def ouac_and_grades(soup: BeautifulSoup) -> tuple[str, str]:
    ouac_code = ""
    grade_range = ""
    for h4 in soup.select("h4.tabbed-subsection-heading"):
        if h4.get_text(strip=True) != "Program Summary":
            continue
        dl = h4.find_next("dl")
        if not dl:
            continue
        for dt in dl.find_all("dt", recursive=False):
            label = dt.get_text(strip=True)
            dd = dt.find_next_sibling("dd")
            val = _squish(dd.get_text(" ", strip=True)) if dd else ""
            if label == "OUAC Program Code":
                ouac_code = val
            elif label == "Grade Range":
                grade_range = val
        break
    return ouac_code, grade_range


def prereq_list(soup: BeautifulSoup) -> list[str]:
    for h4 in soup.select("h4.tabbed-subsection-heading"):
        if h4.get_text(strip=True) != "Prerequisites":
            continue
        parent = h4.parent
        if not parent:
            continue
        ul = parent.find("ul", recursive=False)
        if not ul:
            continue
        return [
            _squish(li.get_text(" ", strip=True))
            for li in ul.find_all("li", recursive=False)
        ]
    return []


def guess_supp_app(soup: BeautifulSoup) -> bool:
    article = soup.select_one("main.template-content article")
    if not article:
        return False
    section = article.select_one(".tabbed-section") or article
    for tag in section.select("p, li, dd"):
        t = _squish(tag.get_text(" ", strip=True))
        if not t or len(t) > 700:
            continue
        tl = t.lower()
        if len(t) > 280 and "the following programs require" in tl:
            continue
        if "strongly recommended for admission" in tl and "scholarship" in tl:
            continue
        if re.search(
            r"(supplementary|supplemental)\s+application",
            tl,
        ) and re.search(
            r"\b(required|is required|must complete|must submit|must be submitted)\b",
            tl,
        ):
            return True
        if "admission information form" in tl and re.search(
            r"\b(required|is required)\b", tl
        ):
            return True
        if re.search(r"\baif\b", tl) and re.search(
            r"\b(is required|required)\b", tl
        ):
            return True
        if "portfolio" in tl and re.search(
            r"\b(required|must submit|must be submitted)\b", tl
        ):
            return True
        if "personal profile" in tl and re.search(
            r"\b(required|must complete)\b", tl
        ):
            return True
        if re.search(
            r"(one idea|video essay|audition|interview).{0,80}"
            r"(required|is required|must complete)",
            tl,
        ):
            return True
    return False


def fetch_program(
    session: requests.Session,
    url: str,
) -> tuple[dict[str, str | bool | list[str]], str] | None:
    try:
        html = get_page(url, session)
    except requests.RequestException as e:
        print(f"  [warn] GET failed {url}: {e}", file=sys.stderr)
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.select_one("h1.template-heading")
        program_name = _squish(h1.get_text(" ", strip=True)) if h1 else ""
        uni_a = soup.select_one("h2.template-subheading a")
        university = _squish(uni_a.get_text(" ", strip=True)) if uni_a else ""

        ouac_code, grade_range = ouac_and_grades(soup)
        prerequisites = prereq_list(soup)
        supp = guess_supp_app(soup)

        if not ouac_code:
            parts = urlparse(url).path.strip("/").split("/")
            if len(parts) >= 3:
                ouac_code = parts[-1].upper()

        if not prerequisites:
            prerequisites = ["n/a"]

        record: dict[str, str | bool | list[str]] = {
            "university": _to_na(university),
            "programName": _to_na(program_name),
            "admissionAverage": _to_na(grade_range),
            "prerequisites": prerequisites,
            "suppAppRequired": supp,
            "url": url,
        }
        return record, ouac_code.strip().upper()
    except (AttributeError, TypeError, ValueError) as e:
        print(f"  [warn] parse failed {url}: {e}", file=sys.stderr)
        return None


def harvest_program_urls(session: requests.Session) -> list[str]:
    listing_urls = gather_listing_pages(session)
    print(f"\nListing pages ({len(listing_urls)} total). Collecting program links...")
    master: list[str] = []
    seen: set[str] = set()
    for i, listing_url in enumerate(listing_urls, 1):
        time.sleep(LISTING_SLEEP_SEC)
        html = get_page(listing_url, session)
        found = program_links_on_page(html)
        for u in found:
            if u not in seen:
                seen.add(u)
                master.append(u)
        print(
            f"  [{i}/{len(listing_urls)}] +{len(found)} on page "
            f"(total unique {len(master)})"
        )
    print(f"\nTotal unique program detail URLs: {len(master)}")
    return master


def disambiguate_key(
    ouac_code: str,
    url: str,
    used: set[str],
) -> str:
    base = (ouac_code or "").strip().upper() or "UNKNOWN"
    key = base
    if key not in used:
        return key
    parts = urlparse(url).path.strip("/").split("/")
    slug = parts[-2] if len(parts) >= 3 else "dup"
    key = f"{base}__{slug}"
    n = 2
    while key in used:
        key = f"{base}__{slug}__{n}"
        n += 1
    return key


def scrape_all(limit: int | None) -> dict[str, dict]:
    programs: dict[str, dict] = {}
    key_used: set[str] = set()
    skipped = 0

    with requests.Session() as session:
        print(f"Requesting base directory: {BASE_PROGRAMS}")
        r = session.get(BASE_PROGRAMS, headers=HEADERS, timeout=60)
        r.raise_for_status()
        print(f"  -> {r.status_code} {r.url}\n")

        urls = harvest_program_urls(session)
        if limit is not None:
            urls = urls[:limit]
            print(f"\n--limit {limit}: scraping first {len(urls)} programs only\n")

        total = len(urls)
        print(
            f"Scraping {total} program detail pages "
            f"({DETAIL_SLEEP_SEC}s pause between each)..."
        )
        for i, url in enumerate(urls, 1):
            if i > 1:
                time.sleep(DETAIL_SLEEP_SEC)
            print(f"  Extracting details for program {i}/{total}…")
            print(f"    {url}")
            parsed = fetch_program(session, url)
            if not parsed:
                skipped += 1
                continue
            rec, ouac_code = parsed
            key = disambiguate_key(ouac_code, url, key_used)
            key_used.add(key)
            programs[key] = rec

    print(
        f"\nAssembled {len(programs)} programs into JSON object "
        f"({skipped} detail pages skipped due to errors)."
    )
    return programs


def write_json(data: dict[str, dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_cli(argv: list[str]) -> CliArgs:
    p = argparse.ArgumentParser(description="Scrape OUInfo programs into JSON.")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Scrape at most N programs (after discovery). Default: all.",
    )
    p.add_argument(
        "-o",
        "--output",
        default=OUTPUT_JSON,
        help=f"Output JSON path (default: {OUTPUT_JSON}).",
    )
    ns = p.parse_args(argv)
    return CliArgs(limit=ns.limit, output=ns.output)


def main() -> None:
    args = parse_cli(sys.argv[1:])
    print("OUInfo scraper — Phases 4–5 (assembly, rate limit, JSON output)\n")
    data = scrape_all(args.limit)
    out_path = args.output
    print(f"\nWriting {len(data)} entries to {out_path} …")
    write_json(data, out_path)
    print(f"Successfully saved to {out_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
