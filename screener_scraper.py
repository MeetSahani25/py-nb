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
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text
    
def fetch_all_pages(session, base_url):
    all_rows = []
    headers = None
    page = 1

    while True:
        page_url = base_url if page == 1 else f"{base_url}?page={page}"

        print(f"\n📄 Fetching page {page}: {page_url}")

        html = fetch_screen(session, page_url)

        try:
            page_headers, page_rows = parse_table(html)
        except Exception:
            print(f"  No table found on page {page}")
            break

        print(f"  Rows found: {len(page_rows)}")

        if not page_rows:
            break

        if headers is None:
            headers = page_headers

        all_rows.extend(page_rows)

        next_url = f"{base_url}?page={page + 1}"
        
        next_html = fetch_screen(session, next_url)
        
        try:
            _, next_rows = parse_table(next_html)
        except:
            next_rows = []
        
        if not next_rows:
            break
        
        page += 1
    return headers, all_rows
    
def dedupe_rows(headers, rows):
    try:
        name_idx = headers.index("Name")
    except ValueError:
        return rows

    seen = set()
    unique = []

    for row in rows:
        if len(row) <= name_idx:
            continue

        stock = row[name_idx]

        if stock in seen:
            continue

        seen.add(stock)
        unique.append(row)

    return unique
    
def parse_table(html):
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", class_=lambda c: c and "data-table" in c)
    if not table:
        table = soup.find("table")
    if not table:
        raise ValueError("No data table found in page")

    # Headers from first thead row only
    thead = table.find("thead")
    
    if thead:
        all_headers = [th.get_text(strip=True) for th in thead.find_all("th")]
    
        headers = []
        seen = set()
    
        for h in all_headers:
            if h in seen:
                break
            headers.append(h)
            seen.add(h)
    else:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]

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
    print(f"  Parsed rows: {len(rows)}")
    
    tbody = table.find("tbody")
    if tbody:
        print(f"  Raw TR count: {len(tbody.find_all('tr'))}")
    return headers, rows

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
    headers, rows = fetch_all_pages(session, SCREEN_URL)
    
    rows = dedupe_rows(headers, rows)
    
    print(f"\n📊 Total unique stocks: {len(rows)}")
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
