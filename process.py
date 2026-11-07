#!/usr/bin/env python3
"""
Kindlogger Process — enriches your library with Open Library data
and merges in your highlights. One command does everything.

Usage:
    python3 process.py kindlogger-export.json [kindlogger-highlights.json]

Highlights file is optional — if omitted, you just get enriched library data.

Outputs: kindlogger-complete.json in the same directory as the export.
"""
import json
import sys
import time
import urllib.request
import urllib.parse
import os
import re

RATE_LIMIT_DELAY = 0.35
USER_AGENT = "Kindlogger/1.0 (https://github.com/maxtattonbrown/kindlogger)"


def fetch_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def search_open_library(title, author):
    clean_title = title.split(":")[0].strip()
    clean_title = re.sub(r"\s*\([^)]*\)\s*$", "", clean_title)
    params = urllib.parse.urlencode({
        "title": clean_title,
        "author": author,
        "limit": 1,
        "fields": "key,title,author_name,first_publish_year,subject,number_of_pages_median"
    })
    url = "https://openlibrary.org/search.json?" + params
    return fetch_json(url)


def get_work_details(work_key):
    url = "https://openlibrary.org" + work_key + ".json"
    return fetch_json(url)


SKIP_SUBJECTS = {
    "fiction", "in library", "accessible book", "protected daisy",
    "lending library", "large type books", "english language",
    "english fiction", "open library staff picks", "literature",
    "general", "fiction, general", "reading level-grade 11",
    "reading level-grade 12", "children's fiction"
}


def clean_subjects(subjects):
    filtered = []
    for s in subjects:
        low = s.lower()
        if low in SKIP_SUBJECTS:
            continue
        if re.match(r"nyt:", low):
            continue
        if re.match(r"fiction,\s", low):
            continue
        if len(s) < 3 or len(s) > 50:
            continue
        filtered.append(s)
    return filtered[:5]


def enrich_book(book):
    title = book.get("title", "")
    author = book.get("author", "")
    if not title:
        return book

    data = search_open_library(title, author)
    time.sleep(RATE_LIMIT_DELAY)
    if not data or data.get("numFound", 0) == 0:
        return book

    result = data["docs"][0]
    enriched = dict(book)

    subjects = result.get("subject", [])
    if subjects:
        genres = clean_subjects(subjects)
        if genres:
            enriched["genres"] = genres

    pages = result.get("number_of_pages_median")
    if pages:
        enriched["pages"] = pages

    year = result.get("first_publish_year")
    if year:
        enriched["published"] = year

    work_key = result.get("key")
    if work_key:
        work = get_work_details(work_key)
        time.sleep(RATE_LIMIT_DELAY)
        if work:
            desc = work.get("description")
            if isinstance(desc, dict):
                desc = desc.get("value", "")
            if isinstance(desc, str) and len(desc) > 10:
                if len(desc) > 500:
                    desc = desc[:497] + "..."
                enriched["description"] = desc

    return enriched


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process.py <export.json> [highlights.json]")
        print()
        print("  export.json      — from kindlogger.js (required)")
        print("  highlights.json  — from kindlogger-highlights.js (optional)")
        sys.exit(1)

    export_path = sys.argv[1]
    highlights_path = sys.argv[2] if len(sys.argv) > 2 else None

    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    books = data.get("books", [])
    total = len(books)

    # Step 1: Enrich with Open Library
    print("Step 1/2: Enriching {} books from Open Library...".format(total))
    print("Estimated time: {:.0f} minutes".format(total * 0.7 / 60))
    print()

    enriched_count = 0
    for i, book in enumerate(books):
        books[i] = enrich_book(book)
        has_new = any(k in books[i] for k in ("genres", "pages", "published", "description"))
        if has_new:
            enriched_count += 1
        if (i + 1) % 25 == 0 or i == total - 1:
            pct = ((i + 1) / total) * 100
            print("  {}/{} ({:.0f}%) — {} enriched so far".format(
                i + 1, total, pct, enriched_count))

    print()
    print("Enrichment done: {}/{} books matched".format(enriched_count, total))

    # Step 2: Merge highlights
    books_with_highlights = 0
    total_highlights = 0

    if highlights_path:
        print()
        print("Step 2/2: Merging highlights...")

        with open(highlights_path, "r", encoding="utf-8") as f:
            hl_data = json.load(f)

        hl_by_asin = {}
        hl_by_title = {}
        for hl_book in hl_data.get("books", []):
            asin = hl_book.get("asin", "")
            title = hl_book.get("title", "").lower()
            highlights = hl_book.get("highlights", [])
            if asin and asin.startswith("B"):
                hl_by_asin[asin] = highlights
            if title:
                hl_by_title[title] = highlights

        for book in books:
            asin = book.get("asin", "")
            title = book.get("title", "").lower()
            highlights = hl_by_asin.get(asin) or hl_by_title.get(title)
            if highlights:
                book["highlights"] = highlights
                books_with_highlights += 1
                total_highlights += len(highlights)

        print("  {} books with highlights ({} total)".format(
            books_with_highlights, total_highlights))
    else:
        print()
        print("Step 2/2: No highlights file provided, skipping.")

    # Build final output
    meta = data.get("kindlogger", {})
    meta["enriched"] = True
    meta["enriched_count"] = enriched_count
    meta["enrichment_source"] = "Open Library (openlibrary.org)"
    if highlights_path:
        meta["books_with_highlights"] = books_with_highlights
        meta["total_highlights"] = total_highlights

    output = {"kindlogger": meta, "books": books}

    output_dir = os.path.dirname(export_path) or "."
    output_path = os.path.join(output_dir, "kindlogger-complete.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 50)
    print("DONE: {}".format(output_path))
    print("  {} books total".format(total))
    print("  {} enriched with genres/pages/year".format(enriched_count))
    if highlights_path:
        print("  {} with highlights ({} highlights)".format(
            books_with_highlights, total_highlights))
    print("=" * 50)


if __name__ == "__main__":
    main()
