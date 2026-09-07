"""
Screener.in Daily Stock Report Scraper v5
- Logs in fresh every day using email + password (no cookie maintenance)
- Gets your custom columns exactly as you see them on Screener
- Saves CSV, HTML, JSON
"""

import requests
from bs4 import BeautifulSoup
import csv
import json
import os
import time
import re
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, date

# ── CONFIG ───────────────────────────────────────────────────────────────────
SCREEN_URL   = "https://www.screener.in/screens/3664072/screen1/"
LOGIN_URL    = "https://www.screener.in/login/"
OUTPUT_DIR   = "reports"

EMAIL        = os.environ.get("SCREENER_EMAIL", "")
PASSWORD     = os.environ.get("SCREENER_PASSWORD", "")
# ─────────────────────────────────────────────────────────────────────────────

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    })
    return s

def login(session):
    if not EMAIL or not PASSWORD:
        print("  ⚠️  No credentials — fetching as guest (default columns only)")
        return False

    # Step 1: GET login page to grab csrftoken
    resp = session.get(LOGIN_URL, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract CSRF token from the login form
    csrf_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf_input:
        # Fallback: grab from cookie
        csrf_token = session.cookies.get("csrftoken", "")
    else:
        csrf_token = csrf_input["value"]

    if not csrf_token:
        print("  ❌ Could not get CSRF token for login")
        return False

    # Step 2: POST login credentials
    payload = {
        "csrfmiddlewaretoken": csrf_token,
        "username": EMAIL,
        "password": PASSWORD,
    }
    session.headers.update({
        "Referer": LOGIN_URL,
        "Origin": "https://www.screener.in",
    })

    resp = session.post(LOGIN_URL, data=payload, timeout=15)

    # Check if login succeeded — Screener redirects to home on success
    if resp.url == "https://www.screener.in/" or "logout" in resp.text.lower():
        print(f"  ✅ Logged in as {EMAIL}")
        return True
    elif "Invalid" in resp.text or "incorrect" in resp.text.lower():
        print("  ❌ Login failed — check SCREENER_EMAIL and SCREENER_PASSWORD secrets")
        return False
    else:
        # Sometimes Screener redirects to dashboard — check for session cookie
        if session.cookies.get("sessionid"):
            print(f"  ✅ Logged in as {EMAIL} (session cookie confirmed)")
            return True
        print("  ⚠️  Login status unclear — proceeding anyway")
        return True

def fetch_screen(session, url):
    session.headers.update({"Referer": "https://www.screener.in/"})

    for attempt in range(4):
        resp = session.get(url, timeout=20)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")

            if retry_after:
                try:
                    wait = int(retry_after)
                except ValueError:
                    wait = 5
            else:
                wait = 2 ** attempt * 2

            wait = min(wait, 30)

            print(
                f"  ⚠️ Screener rate-limited request "
                f"(429). Waiting {wait}s..."
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.text

    raise RuntimeError(
        f"Screener kept returning HTTP 429 for {url}"
    )
    
def parse_table(html):
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", class_=lambda c: c and "data-table" in c)
    if not table:
        table = soup.find("table")
    if not table:
        raise ValueError("No data table found in page")
    # Screener may repeat the complete header block multiple times.
    # Keep only the first header block.
    thead = table.find("thead")

    if thead:
        row = thead.find("tr")
        if not row:
            raise RuntimeError("No header row found")

        all_headers = [
            th.get_text(" ", strip=True)
            for th in row.find_all("th")
        ]
    else:
        # Some Screener responses don't expose <thead>.
        # Fall back to the first row containing <th>.
        row = table.find("tr")
        if not row:
            raise RuntimeError("No table header row found")

        all_headers = [
            th.get_text(" ", strip=True)
            for th in row.find_all("th")
        ]

    if not all_headers:
        raise RuntimeError("No headers found")

    # "S.No." starts each repeated header block.
    if "S.No." in all_headers:
        first_sno = all_headers.index("S.No.")

        try:
            second_sno = all_headers.index("S.No.", first_sno + 1)
            headers = all_headers[first_sno:second_sno]
        except ValueError:
            headers = all_headers[first_sno:]
    else:
        headers = all_headers

    print(f"  Columns ({len(headers)}): {headers}")

    # Rows — skip repeated header rows Screener injects mid-table
    rows = []
    tbody = table.find("tbody")
    for tr in (tbody if tbody else table).find_all("tr"):
        cells_raw = tr.find_all(["td", "th"])
        if not cells_raw:
            continue
        if all(c.name == "th" for c in cells_raw):
            continue
        cells = [
            (td.find("a").get_text(strip=True) if td.find("a") else td.get_text(strip=True))
            for td in cells_raw
        ]
        if cells[:2] == headers[:2]:
            continue
        if not any(cells):
            continue
        rows.append(cells)

    return headers, rows
def extract_pagination_info(html):
    """
    Extract Screener's pagination information.

    Example:
        76 results found: Showing page 1 of 2
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    match = re.search(
        r"([\d,]+)\s+results found.*?"
        r"Showing page\s+(\d+)\s+of\s+(\d+)",
        text,
        re.IGNORECASE
    )

    if not match:
        return None, None, None

    total_results = int(match.group(1).replace(",", ""))
    current_page = int(match.group(2))
    total_pages = int(match.group(3))

    return total_results, current_page, total_pages


def get_next_page_url(html, current_url):
    """
    Find the next numerical Screener pagination URL.

    We intentionally follow Screener's actual pagination links
    instead of blindly constructing '?page=2', '?page=3', etc.
    """
    soup = BeautifulSoup(html, "html.parser")

    parsed_current = urlparse(current_url)
    current_query = parse_qs(parsed_current.query)

    try:
        current_page = int(current_query.get("page", ["1"])[0])
    except (ValueError, TypeError):
        current_page = 1

    candidates = []

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        if not href:
            continue

        absolute_url = urljoin(current_url, href)

        parsed = urlparse(absolute_url)
        query = parse_qs(parsed.query)

        if "page" not in query:
            continue

        try:
            page_number = int(query["page"][0])
        except (ValueError, TypeError):
            continue

        if page_number > current_page:
            candidates.append(
                (page_number, absolute_url)
            )

    if not candidates:
        return None

    # Select the immediate next page.
    candidates.sort(key=lambda x: x[0])

    return candidates[0][1]


def build_page_url(base_url, page_number):
    """
    Fallback pagination URL builder.

    Used only when Screener reports additional pages but
    does not expose the pagination link in the HTML.
    """
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)

    query["page"] = [str(page_number)]

    return urlunparse(
        parsed._replace(
            query=urlencode(query, doseq=True)
        )
    )

def scrape_all_pages(session):
    """
    Scrape every Screener result page and combine the rows.
    """
    current_url = SCREEN_URL

    all_rows = []
    headers = None

    visited_urls = set()
    seen_stocks = set()

    max_pages = 20

    expected_total = None
    expected_pages = None

    for page_number in range(1, max_pages + 1):

        if current_url in visited_urls:
            print(
                "  ⚠️ Pagination returned an already-visited URL. "
                "Stopping safely."
            )
            break

        visited_urls.add(current_url)

        print(f"\n📄 Fetching Screener page {page_number}")
        print(f"   {current_url}")

        html = fetch_screen(session, current_url)

        page_headers, page_rows = parse_table(html)

        # First page defines the expected column structure.
        if headers is None:
            headers = page_headers

            (
                expected_total,
                detected_current_page,
                expected_pages
            ) = extract_pagination_info(html)

            if expected_total is not None:
                print(
                    f"  📊 Screener reports "
                    f"{expected_total} results across "
                    f"{expected_pages} pages"
                )

        elif page_headers != headers:
            raise RuntimeError(
                "Column headers changed between Screener pages."
            )

        # Find the Name column.
        if "Name" in headers:
            name_index = headers.index("Name")
        else:
            name_index = 1

        new_rows = 0

        for row in page_rows:

            if len(row) <= name_index:
                continue

            stock_name = row[name_index].strip()

            if not stock_name:
                continue

            # Case-insensitive deduplication.
            stock_key = stock_name.casefold()

            if stock_key in seen_stocks:
                continue

            seen_stocks.add(stock_key)
            all_rows.append(row)
            new_rows += 1

        print(
            f"  → Page contained {len(page_rows)} rows"
            f" · {new_rows} new stocks"
        )

        # If we've already collected everything Screener reported,
        # there is no reason to make another request.
        if (
            expected_total is not None
            and len(all_rows) >= expected_total
        ):
            print(
                f"  ✅ Collected all {len(all_rows)} reported stocks"
            )
            break

        # Find Screener's actual next-page URL.
        next_url = get_next_page_url(
            html,
            current_url
        )

        # Safety check: if page returned no new stocks,
        # don't keep hammering Screener.
        if new_rows == 0:
            print(
                "  ⚠️ Page produced no new stocks. "
                "Stopping pagination safely."
            )
            break

        # If Screener didn't expose a next link but told us
        # there are more pages, use the fallback URL builder.
        if not next_url:

            if (
                expected_pages is not None
                and page_number < expected_pages
            ):
                next_url = build_page_url(
                    current_url,
                    page_number + 1
                )
                print(
                    "  ℹ️ No next link found; "
                    "using Screener's reported page number."
                )
            else:
                break

        # Never revisit the same URL.
        if next_url in visited_urls:
            print(
                "  ⚠️ Next page URL was already visited. "
                "Stopping safely."
            )
            break

        current_url = next_url

        # Be gentle with Screener between page requests.
        time.sleep(1.5)

    else:
        print(
            f"  ⚠️ Reached safety limit of {max_pages} pages."
        )

    if headers is None:
        raise RuntimeError(
            "No Screener pages could be parsed."
        )

    # Re-number S.No. because every Screener page starts
    # its serial numbers again from 1.
    if "S.No." in headers:
        sno_index = headers.index("S.No.")

        for index, row in enumerate(all_rows, start=1):
            if len(row) > sno_index:
                row[sno_index] = str(index)

    print(
        f"\n📦 Combined result: "
        f"{len(all_rows)} unique stocks "
        f"from {len(visited_urls)} page(s)"
    )

    return headers, all_rows
    
def save_csv(headers, rows, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([headers] + rows)
    print(f"  ✅ CSV  → {filepath}")

def save_html(headers, rows, filepath, report_date):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    def fmt_cell(val, col):
        col = col.lower()
        is_pct = any(k in col for k in ["return", "growth", "profit", "sales var", "qoq", "yoy", "roce"])
        try:
            num = float(str(val).replace(",", "").replace("%", "").strip())
            if is_pct:
                c = "#1a9e6d" if num > 0 else "#d94b4b"
                a = "▲" if num > 0 else "▼"
                return f'<td style="color:{c};font-weight:600">{a}&nbsp;{val}</td>'
        except:
            pass
        return f"<td>{val}</td>"

    hdr = "".join(f"<th>{h}</th>" for h in headers)
    bdy = "".join(
        "<tr>" + "".join(
            fmt_cell(row[j], headers[j]) if j < len(headers) else "<td></td>"
            for j in range(len(row))
        ) + "</tr>\n"
        for row in rows
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Report — {report_date}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;padding:20px;color:#1a1a1a}}
  .wrap{{max-width:1600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.08);overflow:hidden}}
  .top{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:#fff;padding:22px 28px}}
  .top h1{{font-size:20px;font-weight:700}}
  .top p{{font-size:13px;opacity:.6;margin-top:5px}}
  .meta{{display:flex;gap:24px;padding:12px 28px;background:#f8f9ff;border-bottom:1px solid #e8eaf0;font-size:13px;color:#555;flex-wrap:wrap}}
  .meta a{{color:#4a6cf7;text-decoration:none}}
  .tbl-wrap{{overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  thead th{{background:#1a1a2e;color:#c8d0ff;padding:11px 14px;text-align:right;font-weight:500;font-size:12px;white-space:nowrap;position:sticky;top:0;z-index:2}}
  thead th:nth-child(1){{text-align:center;width:44px}}
  thead th:nth-child(2){{text-align:left;min-width:160px}}
  tbody td{{padding:10px 14px;border-bottom:1px solid #f0f0f0;text-align:right;white-space:nowrap}}
  tbody td:nth-child(1){{text-align:center;color:#aaa;font-size:12px}}
  tbody td:nth-child(2){{text-align:left;font-weight:600;color:#1a1a2e}}
  tbody tr:hover td{{background:#f0f4ff}}
  tbody tr:nth-child(even){{background:#fafbff}}
  .foot{{padding:12px 28px;font-size:11px;color:#bbb;border-top:1px solid #eee}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>📈 Screener Momentum Screen — Daily Report</h1>
    <p>Breakout: Vol &gt; 1.5× avg · 1-day return &gt; 4% · Mkt Cap &gt; ₹500 Cr</p>
  </div>
  <div class="meta">
    <span>📅 <strong>{report_date}</strong></span>
    <span>📊 <strong>{len(rows)} stocks</strong></span>
    <span>🔗 <a href="{SCREEN_URL}" target="_blank">screener.in/screens/3664072/screen1</a></span>
  </div>
  <div class="tbl-wrap">
    <table><thead><tr>{hdr}</tr></thead><tbody>{bdy}</tbody></table>
  </div>
  <div class="foot">Auto-generated via GitHub Actions · Screener.in · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div>
</body></html>""")
    print(f"  ✅ HTML → {filepath}")

def save_json(headers, rows, filepath, report_date):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "date": report_date,
            "screen_url": SCREEN_URL,
            "total_stocks": len(rows),
            "headers": headers,
            "stocks": [dict(zip(headers, row)) for row in rows],
        }, f, indent=2, ensure_ascii=False)
    print(f"  ✅ JSON → {filepath}")

def update_index(report_date, csv_path, html_path, json_path, total):
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    index = {"reports": []}
    if os.path.exists(index_path):
        with open(index_path) as f:
            try: index = json.load(f)
            except: pass
    index["reports"] = [r for r in index["reports"] if r["date"] != report_date]
    index["reports"].append({"date": report_date, "total_stocks": total,
                              "csv": csv_path, "html": html_path, "json": json_path})
    index["reports"].sort(key=lambda x: x["date"], reverse=True)
    index["last_updated"] = datetime.utcnow().isoformat()
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"  ✅ Index updated")

def main():
    today = date.today().isoformat()
    print(f"\n🚀 Screener Daily Scraper v5 — {today}")
    print(f"📡 {SCREEN_URL}\n")
    
    session = make_session()
    login(session)
    
    headers, rows = scrape_all_pages(session)
    
    print(f"\n📊 {len(rows)} stocks · {len(headers)} columns\n")

    base = os.path.join(OUTPUT_DIR, today, today)
    os.makedirs(os.path.join(OUTPUT_DIR, today), exist_ok=True)
    save_csv(headers, rows, base + "_screener.csv")
    save_html(headers, rows, base + "_screener.html", today)
    save_json(headers, rows, base + "_screener.json", today)
    update_index(today, base + "_screener.csv", base + "_screener.html",
                 base + "_screener.json", len(rows))

    print(f"\n✅ Done — {len(rows)} stocks, {len(headers)} columns for {today}")

if __name__ == "__main__":
    main()
