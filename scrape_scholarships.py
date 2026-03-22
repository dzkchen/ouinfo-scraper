#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ouinfo.ca"
BASE_SCHOLARSHIPS = f"{BASE}/scholarships"
OUTPUT_JSON = "ouinfo_scholarships.json"

LETTER_GROUPS = ("a-g", "h-o", "p-t", "u-w", "x-z")

_SUBMIT_SCHOLARSHIPS = "Search Scholarships"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}

GRADE_RANGE_REQUIRED_LABELS: dict[str, str] = {
    "1": "below 75%",
    "2": "75-80%",
    "3": "80-85%",
    "4": "85-90%",
    "5": "90-95%",
    "6": "95-100%",
    "7": "other criteria",
}

DETAIL_SLEEP_SEC = 1.0
LISTING_SLEEP_SEC = 0.3


def _hub_adv(**over: str) -> str:
    p = {
        "search": "",
        "advanced": "1",
        "a_indigenous": "",
        "a_equityseeking": "",
        "a_range": "0",
        "a_location": "0",
        "a_appreq": "",
        "a_avg": "0",
        "a_renewable": "",
        "submit": _SUBMIT_SCHOLARSHIPS,
    }
    p.update(over)
    return f"{BASE_SCHOLARSHIPS}?{urlencode(p)}"


def _group_adv(group: str, **over: str) -> str:
    p = {
        "search": "",
        "advanced": "1",
        "a_range": "0",
        "a_location": "0",
        "a_appreq": "",
        "a_avg": "0",
        "a_renewable": "",
        "a_indigenous": "",
        "a_equityseeking": "",
        "group": group,
    }
    p.update(over)
    return f"{BASE}/scholarships/?{urlencode(p)}"


def advanced_first_pages_default_letter_groups(pred: dict[str, str]) -> list[str]:
    return [
        _hub_adv(**pred),
        _group_adv("h-o", **pred),
        _group_adv("p-t", **pred),
        _group_adv("u-w", **pred),
        _group_adv("x-z", **pred),
    ]


def _grade_first_pages() -> dict[int, list[str]]:
    d: dict[int, list[str]] = {}
    for n in range(1, 7):
        d[n] = [_hub_adv(a_avg=str(n), a_appreq="", a_renewable="")]
    d[7] = [
        _hub_adv(a_avg="7", a_appreq="", a_renewable=""),
        _group_adv("n-o", a_avg="7", a_appreq="", a_renewable=""),
        _group_adv("p-t", a_avg="7", a_appreq="", a_renewable=""),
        _group_adv("u-z", a_avg="7", a_appreq="", a_renewable=""),
    ]
    return d


GRADE_FIRST_PAGES = _grade_first_pages()

APP_REQ_YES_FIRST_PAGES = [
    _hub_adv(a_appreq="yes", a_avg="0", a_renewable=""),
    _group_adv("h-o", a_appreq="yes", a_avg="0", a_renewable=""),
    _group_adv("p-w", a_appreq="yes", a_avg="0", a_renewable=""),
    _group_adv("x-z", a_appreq="yes", a_avg="0", a_renewable=""),
]
APP_REQ_NO_FIRST_PAGES = [
    _hub_adv(a_appreq="no", a_avg="0", a_renewable=""),
    _group_adv("i-o", a_appreq="no", a_avg="0", a_renewable=""),
    _group_adv("p-z", a_appreq="no", a_avg="0", a_renewable=""),
]

RENEW_NO_FIRST_PAGES = [
    _hub_adv(a_appreq="", a_avg="0", a_renewable="no"),
    _group_adv("i-o", a_appreq="", a_avg="0", a_renewable="no"),
    _group_adv("p-w", a_appreq="", a_avg="0", a_renewable="no"),
    _group_adv("x-z", a_appreq="", a_avg="0", a_renewable="no"),
]
RENEW_YES_FIRST_PAGES = [
    _hub_adv(a_appreq="", a_avg="0", a_renewable="yes"),
    _group_adv("h-q", a_appreq="", a_avg="0", a_renewable="yes"),
    _group_adv("r-w", a_appreq="", a_avg="0", a_renewable="yes"),
    _group_adv("x-z", a_appreq="", a_avg="0", a_renewable="yes"),
]

EQUITY_YES_FIRST_PAGES = [_hub_adv(a_equityseeking="yes", a_appreq="", a_avg="0", a_renewable="")]
INDIGENOUS_YES_FIRST_PAGES = [_hub_adv(a_indigenous="yes", a_appreq="", a_avg="0", a_renewable="")]


def fetch_html(url: str, session: requests.Session) -> str:
    response = session.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def discover_listing_page_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[str] = []
    for anchor in soup.select("div.results-meta ul.pagination a[href]"):
        href = anchor.get("href")
        if not href or "/scholarships" not in href:
            continue
        absolute = urljoin(BASE, href)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def _is_scholarship_detail_path(path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    return len(parts) >= 3 and parts[0] == "scholarships"


def extract_scholarship_detail_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[str] = []
    for anchor in soup.select("article.result-scholarship h2.result-heading a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(BASE, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if "ouinfo.ca" not in (parsed.netloc or "").lower():
            continue
        if not _is_scholarship_detail_path(parsed.path):
            continue
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def canonical_first_page_url(letter_group: str) -> str:
    if letter_group == "a-g":
        return BASE_SCHOLARSHIPS
    return f"{BASE}/scholarships/?search=&group={letter_group}"


def collect_listing_page_urls(session: requests.Session) -> list[str]:
    print("Discovering listing URLs (all letter groups)…")
    seen: set[str] = set()
    out: list[str] = []
    for g in LETTER_GROUPS:
        first = canonical_first_page_url(g)
        time.sleep(LISTING_SLEEP_SEC)
        html = fetch_html(first, session)
        for u in [first, *discover_listing_page_urls(html)]:
            if u not in seen:
                seen.add(u)
                out.append(u)
    print(f"  -> {len(out)} listing page URL(s)")
    return out


def collect_scholarship_urls_from_first_pages(
    session: requests.Session,
    first_pages: list[str],
) -> set[str]:
    out: set[str] = set()
    for fp in first_pages:
        time.sleep(LISTING_SLEEP_SEC)
        html = fetch_html(fp, session)
        page_urls: list[str] = []
        seen_page: set[str] = set()
        for u in [fp, *discover_listing_page_urls(html)]:
            if u not in seen_page:
                seen_page.add(u)
                page_urls.append(u)
        for i, pu in enumerate(page_urls):
            if i > 0:
                time.sleep(LISTING_SLEEP_SEC)
            h = html if pu == fp else fetch_html(pu, session)
            out.update(extract_scholarship_detail_urls(h))
    return out


def build_yes_no_search_index(
    session: requests.Session,
    yes_first_pages: list[str],
    no_first_pages: list[str],
    label: str,
) -> dict[str, str]:
    yes_set = collect_scholarship_urls_from_first_pages(session, yes_first_pages)
    no_set = collect_scholarship_urls_from_first_pages(session, no_first_pages)
    print(f"  {label}: yes {len(yes_set)} URLs, no {len(no_set)} URLs")
    m: dict[str, str] = {}
    for u in yes_set:
        m[u] = "yes"
    for u in no_set:
        if u not in m:
            m[u] = "no"
    return m


def build_grade_range_index(session: requests.Session) -> dict[str, str]:
    url_to_avg: dict[str, int] = {}
    for avg_id in range(1, 8):
        key = str(avg_id)
        first_pages = GRADE_FIRST_PAGES[avg_id]
        found = collect_scholarship_urls_from_first_pages(session, first_pages)
        for url in found:
            prev = url_to_avg.get(url)
            if prev is not None and prev != avg_id:
                print(
                    f"  [warn] grade range conflict for {url}: "
                    f"a_avg {prev} vs {avg_id}; keeping min",
                    file=sys.stderr,
                )
            url_to_avg[url] = (
                min(prev, avg_id) if prev is not None else avg_id
            )
        print(
            f"  Grade bucket a_avg={key} ({GRADE_RANGE_REQUIRED_LABELS[key]}): "
            f"{len(found)} scholarships (this pass)"
        )
    return {
        u: GRADE_RANGE_REQUIRED_LABELS[str(k)] for u, k in url_to_avg.items()
    }


def build_equity_seeking_index(session: requests.Session) -> dict[str, str]:
    return build_yes_no_search_index(
        session,
        EQUITY_YES_FIRST_PAGES,
        advanced_first_pages_default_letter_groups({"a_equityseeking": "no"}),
        "Equity seeking",
    )


def build_indigenous_search_index(session: requests.Session) -> dict[str, str]:
    return build_yes_no_search_index(
        session,
        INDIGENOUS_YES_FIRST_PAGES,
        advanced_first_pages_default_letter_groups({"a_indigenous": "no"}),
        "Indigenous applicants only",
    )


def build_application_required_search_index(session: requests.Session) -> dict[str, str]:
    return build_yes_no_search_index(
        session,
        APP_REQ_YES_FIRST_PAGES,
        APP_REQ_NO_FIRST_PAGES,
        "Application required",
    )


def build_renewable_search_index(session: requests.Session) -> dict[str, str]:
    return build_yes_no_search_index(
        session,
        RENEW_YES_FIRST_PAGES,
        RENEW_NO_FIRST_PAGES,
        "Renewable",
    )


def merge_yes_no_from_search(
    index: dict[str, str], url: str, detail_val: str
) -> str:
    if url in index:
        return index[url]
    return detail_val


def _norm_space(s: str) -> str:
    return " ".join(s.split())


def _na_str(raw: str | None) -> str:
    if raw is None:
        return "n/a"
    t = _norm_space(str(raw))
    return t if t else "n/a"


def _yes_no_na(summary: dict[str, str], key: str) -> str:
    if key not in summary:
        return "n/a"
    raw = summary[key]
    if not str(raw).strip():
        return "n/a"
    tl = str(raw).strip().lower()
    if tl in ("yes", "y", "true", "1"):
        return "yes"
    if tl in ("no", "n", "false", "0"):
        return "no"
    return "n/a"


def parse_scholarship_summary_table(soup: BeautifulSoup) -> dict[str, str]:
    data: dict[str, str] = {}
    for h4 in soup.select("h4.tabbed-subsection-heading"):
        if h4.get_text(strip=True) != "Scholarship Summary":
            continue
        table = h4.find_next("table")
        if not table:
            break
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr", recursive=False):
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 2:
                continue
            key = _norm_space(tds[0].get_text(" ", strip=True))
            val = _norm_space(tds[1].get_text(" ", strip=True))
            if key:
                data[key] = val
        break
    return data


def scrape_scholarship_detail(
    session: requests.Session,
    url: str,
) -> tuple[dict[str, str], str] | None:
    try:
        html = fetch_html(url, session)
    except requests.RequestException as e:
        print(f"  [warn] GET failed {url}: {e}", file=sys.stderr)
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.select_one("h1.template-heading")
        name = _norm_space(h1.get_text(" ", strip=True)) if h1 else ""
        uni_a = soup.select_one("h2.template-subheading a")
        university = _norm_space(uni_a.get_text(" ", strip=True)) if uni_a else ""

        summary = parse_scholarship_summary_table(soup)
        deadline = _na_str(summary.get("Deadline"))
        value = _na_str(summary.get("Value"))
        renewable = _yes_no_na(summary, "Renewable?")
        application_required = _yes_no_na(summary, "Application Required")
        indigenous_only = _yes_no_na(summary, "For Indigenous Applicants Only")

        record: dict[str, str] = {
            "name": _na_str(name),
            "url": url,
            "deadline": deadline,
            "value": value,
            "renewable": renewable,
            "applicationRequired": application_required,
            "forIndigenousApplicantsOnly": indigenous_only,
        }
        return record, _na_str(university)
    except (AttributeError, TypeError, ValueError) as e:
        print(f"  [warn] parse failed {url}: {e}", file=sys.stderr)
        return None


def collect_all_scholarship_urls(
    session: requests.Session,
    listing_urls: list[str],
) -> list[str]:
    print(f"\nListing pages ({len(listing_urls)}). Collecting scholarship links...")
    master: list[str] = []
    seen: set[str] = set()
    for i, listing_url in enumerate(listing_urls, 1):
        time.sleep(LISTING_SLEEP_SEC)
        html = fetch_html(listing_url, session)
        found = extract_scholarship_detail_urls(html)
        for u in found:
            if u not in seen:
                seen.add(u)
                master.append(u)
        print(
            f"  [{i}/{len(listing_urls)}] +{len(found)} on page "
            f"(total unique {len(master)})"
        )
    print(f"\nTotal unique scholarship URLs: {len(master)}")
    return master


def run_scrape(limit: int | None) -> dict[str, list[dict[str, str]]]:
    by_univ: dict[str, list[dict[str, str]]] = defaultdict(list)
    skipped = 0

    with requests.Session() as session:
        print(f"Requesting scholarships hub: {BASE_SCHOLARSHIPS}")
        r = session.get(BASE_SCHOLARSHIPS, headers=HEADERS, timeout=60)
        r.raise_for_status()
        print(f"  -> {r.status_code} {r.url}\n")

        listing_urls = collect_listing_page_urls(session)
        urls = collect_all_scholarship_urls(session, listing_urls)

        print(
            "\nBuilding search indices "
            "(grade range, equity, Indigenous, application required, renewable)…"
        )
        grade_index = build_grade_range_index(session)
        equity_index = build_equity_seeking_index(session)
        indigenous_index = build_indigenous_search_index(session)
        app_index = build_application_required_search_index(session)
        renew_index = build_renewable_search_index(session)

        if limit is not None:
            urls = urls[:limit]
            print(f"\n--limit {limit}: scraping first {len(urls)} only\n")

        total = len(urls)
        print(
            f"Scraping {total} scholarship pages ({DETAIL_SLEEP_SEC}s between)..."
        )
        for i, url in enumerate(urls, 1):
            if i > 1:
                time.sleep(DETAIL_SLEEP_SEC)
            print(f"  [{i}/{total}] {url}")
            parsed = scrape_scholarship_detail(session, url)
            if not parsed:
                skipped += 1
                continue
            rec, uni = parsed
            rec["gradeRangeRequired"] = grade_index.get(url, "n/a")
            rec["forEquitySeekingApplicantsOnly"] = equity_index.get(url, "n/a")
            rec["forIndigenousApplicantsOnly"] = merge_yes_no_from_search(
                indigenous_index, url, rec["forIndigenousApplicantsOnly"]
            )
            rec["applicationRequired"] = merge_yes_no_from_search(
                app_index, url, rec["applicationRequired"]
            )
            rec["renewable"] = merge_yes_no_from_search(
                renew_index, url, rec["renewable"]
            )
            by_univ[uni].append(rec)

    print(
        f"\nFinished: {sum(len(v) for v in by_univ.values())} records, "
        f"{len(by_univ)} universities, {skipped} skipped."
    )
    ordered = {k: by_univ[k] for k in sorted(by_univ.keys())}
    return ordered


def write_output(
    data: dict[str, list[dict[str, str]]], path: str
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OUInfo scholarships scraper",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Scrape at most N scholarships after discovery.",
    )
    p.add_argument(
        "-o",
        "--output",
        default=OUTPUT_JSON,
        help=f"Output path (default: {OUTPUT_JSON}).",
    )
    return p.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    print("OUInfo scholarships scraper\n")
    data = run_scrape(args.limit)
    print(f"\nWriting to {args.output} …")
    write_output(data, args.output)
    print(f"Saved {len(data)} university keys to {args.output}")
    print("Done.")


if __name__ == "__main__":
    main()
