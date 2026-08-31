"""
Screener.in Monthly Stock Report

- Logs into Screener using SCREENER_EMAIL / SCREENER_PASSWORD
- Scrapes the complete monthly screen, including all pagination pages
- Deduplicates stocks by Name
- Saves CSV, HTML and JSON
- Output:
    reports/monthly_screener/YYYY-MM/
        YYYY-MM_monthly_screener.csv
        YYYY-MM_monthly_screener.html
        YYYY-MM_monthly_screener.json
"""

import csv
import json
import os
import re
import time
from datetime import date, datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup


# ── CONFIG ───────────────────────────────────────────────────────────────────

SCREEN_URL = "https://www.screener.in/screens/1019281/monthly-exert/"
LOGIN_URL = "https://www.screener.in/login/"

OUTPUT_DIR = "reports/monthly_screener"

EMAIL = os.environ.get("SCREENER_EMAIL", "")
PASSWORD = os.environ.get("SCREENER_PASSWORD", "")

PAGE_SIZE = 50

# Be polite to Screener. This is a monthly report, so there is no reason
# to hammer the site.
REQUEST_DELAY_SECONDS = 1.5

# ─────────────────────────────────────────────────────────────────────────────


def make_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Connection": "keep-alive",
    })

    return session


def login(session):
    if not EMAIL or not PASSWORD:
        raise RuntimeError(
            "SCREENER_EMAIL / SCREENER_PASSWORD are missing"
        )

    print("  🔐 Logging into Screener...")

    response = session.get(LOGIN_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    csrf_input = soup.find(
        "input",
        {"name": "csrfmiddlewaretoken"}
    )

    csrf_token = (
        csrf_input.get("value", "")
        if csrf_input
        else session.cookies.get("csrftoken", "")
    )

    if not csrf_token:
        raise RuntimeError("Could not obtain Screener CSRF token")

    payload = {
        "csrfmiddlewaretoken": csrf_token,
        "username": EMAIL,
        "password": PASSWORD,
    }

    session.headers.update({
        "Referer": LOGIN_URL,
        "Origin": "https://www.screener.in",
    })

    response = session.post(
        LOGIN_URL,
        data=payload,
        timeout=20,
        allow_redirects=True,
    )

    response.raise_for_status()

    if session.cookies.get("sessionid"):
        print(f"  ✅ Logged in as {EMAIL}")
        return

    if "logout" in response.text.lower():
        print(f"  ✅ Logged in as {EMAIL}")
        return

    raise RuntimeError(
        "Screener login could not be confirmed"
    )


def page_url(base_url, page):
    """
    Return the Screener URL for the requested page.

    page 1:
        /monthly-exert/

    page 2:
        /monthly-exert/?page=2
    """

    if page == 1:
        return base_url

    parts = urlparse(base_url)

    query = parse_qs(parts.query)
    query["page"] = [str(page)]

    new_query = urlencode(query, doseq=True)

    return urlunparse((
        parts.scheme,
        parts.netloc,
        parts.path,
        parts.params,
        new_query,
        parts.fragment,
    ))


def fetch_page(session, url, page):
    if page > 1:
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\n📄 Fetching page {page}")
    print(f"   {url}")

    response = session.get(url, timeout=20)

    # Do not blindly retry forever.
    if response.status_code == 429:
        raise RuntimeError(
            f"Screener rate-limited us on page {page} (HTTP 429). "
            "Increase REQUEST_DELAY_SECONDS."
        )

    response.raise_for_status()

    return response.text


def extract_headers(table):
    thead = table.find("thead")

    if not thead:
        return [
            th.get_text(" ", strip=True)
            for th in table.find_all("th")
        ]

    # Screener can repeat the header block in the same <tr>.
    all_headers = [
        th.get_text(" ", strip=True)
        for th in thead.find_all("th")
    ]

    headers = []

    for header in all_headers:
        if header in headers:
            # We have reached the repeated header block.
            break

        headers.append(header)

    return headers


def extract_rows(table, headers):
    rows = []

    tbody = table.find("tbody")

    if not tbody:
        return rows

    header_pair = headers[:2]

    for tr in tbody.find_all("tr"):
        cells_raw = tr.find_all("td")

        if not cells_raw:
            continue

        cells = []

        for cell in cells_raw:
            link = cell.find("a")

            if link:
                value = link.get_text(" ", strip=True)
            else:
                value = cell.get_text(" ", strip=True)

            cells.append(value)

        if not any(cells):
            continue

        # Ignore repeated header rows.
        if cells[:2] == header_pair:
            continue

        # Screener should have exactly len(headers) values.
        # Ignore malformed rows rather than corrupting the CSV.
        if len(cells) != len(headers):
            print(
                f"  ⚠️ Skipping malformed row: "
                f"{len(cells)} cells vs {len(headers)} headers"
            )
            continue

        rows.append(cells)

    return rows


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find(
        "table",
        class_=lambda c: c and "data-table" in c
    )

    if not table:
        table = soup.find("table")

    if not table:
        raise RuntimeError("No Screener data table found")

    headers = extract_headers(table)
    rows = extract_rows(table, headers)

    return headers, rows


def dedupe_rows(headers, rows):
    try:
        name_index = headers.index("Name")
    except ValueError:
        # Fall back to first/second column if Screener changes the header.
        name_index = 1 if len(headers) > 1 else 0

    unique_rows = []
    seen = set()

    for row in rows:
        if len(row) <= name_index:
            continue

        name = row[name_index].strip()

        if not name:
            continue

        if name in seen:
            continue

        seen.add(name)
        unique_rows.append(row)

    return unique_rows


def scrape_all_pages(session):
    all_rows = []
    headers = None
    page = 1
    seen_page_signatures = set()

    while True:
        url = page_url(SCREEN_URL, page)
        html = fetch_page(session, url, page)

        page_headers, page_rows = parse_page(html)

        if headers is None:
            headers = page_headers
        elif page_headers != headers:
            raise RuntimeError(
                f"Header mismatch on page {page}"
            )

        print(
            f"   ✅ Page {page}: {len(page_rows)} stocks"
        )

        if not page_rows:
            print("   ℹ️ No rows — stopping pagination")
            break

        # Safety check:
        # If ?page=N keeps returning the same page, do not loop forever.
        signature = tuple(
            row[1] if len(row) > 1 else row[0]
            for row in page_rows
        )

        if signature in seen_page_signatures:
            print(
                f"   ⚠️ Page {page} repeated an earlier page — "
                "stopping pagination"
            )
            break

        seen_page_signatures.add(signature)

        all_rows.extend(page_rows)

        # If fewer than 50 rows are returned, this is the final page.
        if len(page_rows) < PAGE_SIZE:
            break

        page += 1

    all_rows = dedupe_rows(headers, all_rows)

    print(
        f"\n📊 Total unique stocks scraped: {len(all_rows)}"
    )

    return headers, all_rows


def save_csv(headers, rows, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(
        filepath,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"  ✅ CSV  → {filepath}")


def html_escape(value):
    value = str(value)
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def save_html(headers, rows, filepath, report_month):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    header_html = "".join(
        f"<th>{html_escape(header)}</th>"
        for header in headers
    )

    body_parts = []

    for row in rows:
        cells = "".join(
            f"<td>{html_escape(value)}</td>"
            for value in row
        )

        body_parts.append(
            f"<tr>{cells}</tr>"
        )

    body_html = "\n".join(body_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<title>Monthly Screener Report — {report_month}</title>

<style>
* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

body {{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    background: #f0f2f5;
    padding: 20px;
    color: #1a1a1a;
}}

.wrap {{
    max-width: 1800px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,.08);
}}

.top {{
    background:
        linear-gradient(
            135deg,
            #0f0c29,
            #302b63,
            #24243e
        );
    color: white;
    padding: 24px 28px;
}}

.top h1 {{
    font-size: 22px;
}}

.top p {{
    margin-top: 6px;
    font-size: 13px;
    opacity: .65;
}}

.meta {{
    display: flex;
    gap: 25px;
    flex-wrap: wrap;
    padding: 13px 28px;
    background: #f8f9ff;
    border-bottom: 1px solid #e8eaf0;
    font-size: 13px;
    color: #555;
}}

.meta a {{
    color: #4a6cf7;
    text-decoration: none;
}}

.tbl-wrap {{
    overflow-x: auto;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}

thead th {{
    background: #1a1a2e;
    color: #c8d0ff;
    padding: 11px 14px;
    text-align: right;
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
    position: sticky;
    top: 0;
}}

thead th:first-child {{
    text-align: center;
}}

thead th:nth-child(2) {{
    text-align: left;
    min-width: 180px;
}}

tbody td {{
    padding: 9px 14px;
    border-bottom: 1px solid #f0f0f0;
    text-align: right;
    white-space: nowrap;
}}

tbody td:first-child {{
    text-align: center;
    color: #999;
}}

tbody td:nth-child(2) {{
    text-align: left;
    font-weight: 600;
}}

tbody tr:nth-child(even) {{
    background: #fafbff;
}}

tbody tr:hover {{
    background: #f0f4ff;
}}

.foot {{
    padding: 12px 28px;
    font-size: 11px;
    color: #aaa;
    border-top: 1px solid #eee;
}}
</style>
</head>

<body>

<div class="wrap">

<div class="top">
<h1>📊 Screener Monthly Report</h1>
<p>
Monthly screen: Monthly Exert —
complete paginated result set
</p>
</div>

<div class="meta">
<span>
📅 <strong>{html_escape(report_month)}</strong>
</span>

<span>
📊 <strong>{len(rows)} stocks</strong>
</span>

<span>
🔗
<a
    href="{SCREEN_URL}"
    target="_blank"
>
Screener monthly-exert
</a>
</span>
</div>

<div class="tbl-wrap">

<table>

<thead>
<tr>
{header_html}
</tr>
</thead>

<tbody>
{body_html}
</tbody>

</table>

</div>

<div class="foot">
Generated via GitHub Actions ·
Screener.in ·
{datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC
</div>

</div>

</body>
</html>
"""

    with open(
        filepath,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(html)

    print(f"  ✅ HTML → {filepath}")


def save_json(headers, rows, filepath, report_month):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    payload = {
        "report_month": report_month,
        "screen_url": SCREEN_URL,
        "generated_at_utc": datetime.utcnow().isoformat(),
        "total_stocks": len(rows),
        "headers": headers,
        "stocks": [
            dict(zip(headers, row))
            for row in rows
        ],
    }

    with open(
        filepath,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(f"  ✅ JSON → {filepath}")


def main():
    today = date.today()
    report_month = today.strftime("%Y-%m")

    print("\n" + "=" * 60)
    print("📊 SCREENER MONTHLY REPORT")
    print("=" * 60)

    print(f"Month: {report_month}")
    print(f"Screen: {SCREEN_URL}")

    session = make_session()

    login(session)

    headers, rows = scrape_all_pages(session)

    if not rows:
        raise RuntimeError(
            "No stocks were scraped. Refusing to create empty report."
        )

    month_dir = os.path.join(
        OUTPUT_DIR,
        report_month,
    )

    base = os.path.join(
        month_dir,
        f"{report_month}_monthly_screener",
    )

    save_csv(
        headers,
        rows,
        base + ".csv",
    )

    save_html(
        headers,
        rows,
        base + ".html",
        report_month,
    )

    save_json(
        headers,
        rows,
        base + ".json",
        report_month,
    )

    print("\n" + "=" * 60)
    print(
        f"✅ DONE — {len(rows)} unique stocks"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
