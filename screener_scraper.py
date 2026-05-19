"""
Screener.in Daily Stock Report Scraper v2
Fetches momentum screen results and saves as CSV, HTML, JSON
Columns: Name, CMP, P/E, Mkt Cap, Vol, Vol 1wk avg, Vol 1mo avg,
         Return 1d, Return 1wk, Return 1mo, Return 3mo, Return 6mo, Return 1yr,
         YOY Qtr Profit growth, Profit growth, QoQ Sales, QoQ Profits
"""

import requests
from bs4 import BeautifulSoup
import csv
import json
import os
from datetime import datetime, date

# ── CONFIG ───────────────────────────────────────────────────────────────────
SCREEN_URL = "https://www.screener.in/screens/3664072/screen1/"
OUTPUT_DIR = "reports"

# Columns to KEEP (must match Screener header text exactly, case-insensitive partial match)
KEEP_COLS = [
    "name",
    "cmp",
    "p/e",
    "mar cap",
    "volume",
    "vol 1week",
    "vol 1month",
    "return over 1day",
    "return over 1week",
    "return over 1month",
    "return over 3month",
    "return over 6month",
    "return over 1year",
    "yoy quarterly profit",
    "profit growth",
    "qoq sales",
    "qoq profits",
]
# ─────────────────────────────────────────────────────────────────────────────

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

def col_matches(header_text):
    """Check if a header matches any of our desired columns."""
    h = header_text.lower().strip()
    for k in KEEP_COLS:
        if k in h:
            return True
    return False

def fetch_screen(url):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_table(html):
    """Parse Screener results table, deduplicate headers, filter columns."""
    soup = BeautifulSoup(html, "html.parser")

    # Find the main data table
    table = soup.find("table", class_=lambda c: c and "data-table" in c)
    if not table:
        table = soup.find("table")
    if not table:
        raise ValueError("No data table found in page")

    # ── Headers: use only the FIRST thead row to avoid duplicates ──
    thead = table.find("thead")
    if thead:
        first_header_row = thead.find("tr")
        all_headers = [th.get_text(strip=True) for th in first_header_row.find_all("th")]
    else:
        all_headers = [th.get_text(strip=True) for th in table.find_all("th")]

    # Deduplicate: keep track of seen names
    seen = {}
    unique_headers = []
    for h in all_headers:
        if h not in seen:
            seen[h] = True
            unique_headers.append(h)

    # Find which column indices to keep
    keep_indices = []
    final_headers = []
    for i, h in enumerate(unique_headers):
        if col_matches(h) or h.lower() in ("s.no.", "#", "no."):
            keep_indices.append(i)
            final_headers.append(h)

    # If filtering found nothing, just use all columns
    if len(final_headers) <= 1:
        keep_indices = list(range(len(unique_headers)))
        final_headers = unique_headers

    # ── Rows ──
    rows = []
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            all_cells = tr.find_all("td")
            if not all_cells:
                continue

            cells = []
            for td in all_cells:
                # Get anchor text for company name cells
                a = td.find("a")
                cells.append(a.get_text(strip=True) if a else td.get_text(strip=True))

            # Filter to keep only desired columns
            filtered = []
            for i in keep_indices:
                filtered.append(cells[i] if i < len(cells) else "")
            rows.append(filtered)

    return final_headers, rows

def save_csv(headers, rows, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"✅ CSV → {filepath}")

def save_html(headers, rows, filepath, report_date):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    def fmt_cell(val, col_name):
        col = col_name.lower()
        is_pct = any(k in col for k in ["return", "growth", "profit", "sales", "qoq", "yoy"])
        try:
            num = float(str(val).replace(",", "").replace("%", "").strip())
            if is_pct:
                color = "#1a9e6d" if num > 0 else "#d94b4b"
                arrow = "▲" if num > 0 else "▼"
                return f'<td style="color:{color};font-weight:600">{arrow} {val}</td>'
        except:
            pass
        return f"<td>{val}</td>"

    col_widths = {
        "name": "160px",
        "cmp": "80px",
        "p/e": "60px",
        "mar cap": "100px",
    }

    header_html = ""
    for h in headers:
        w = ""
        for k, v in col_widths.items():
            if k in h.lower():
                w = f' style="min-width:{v}"'
                break
        header_html += f"<th{w}>{h}</th>"

    rows_html = ""
    for i, row in enumerate(rows):
        cells = "".join(fmt_cell(row[j], headers[j]) if j < len(headers) else "<td></td>" for j in range(len(row)))
        rows_html += f"<tr>{cells}</tr>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Report — {report_date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; color: #1a1a1a; }}
  .wrap {{ max-width: 1400px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
  .top {{ background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); color: white; padding: 22px 28px; }}
  .top h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }}
  .top p {{ font-size: 13px; opacity: 0.65; margin-top: 4px; }}
  .meta {{ display: flex; gap: 24px; padding: 12px 28px; background: #f8f9ff; border-bottom: 1px solid #e8eaf0; font-size: 13px; color: #555; flex-wrap: wrap; }}
  .meta strong {{ color: #222; }}
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{ background: #1a1a2e; color: #e0e0ff; padding: 11px 14px; text-align: right; font-weight: 500; font-size: 12px; white-space: nowrap; position: sticky; top: 0; z-index: 1; }}
  thead th:nth-child(1) {{ text-align: center; width: 44px; }}
  thead th:nth-child(2) {{ text-align: left; }}
  tbody td {{ padding: 10px 14px; border-bottom: 1px solid #f0f0f0; text-align: right; white-space: nowrap; }}
  tbody td:nth-child(1) {{ text-align: center; color: #999; font-size: 12px; }}
  tbody td:nth-child(2) {{ text-align: left; font-weight: 500; color: #1a1a2e; }}
  tbody tr:hover td {{ background: #f5f7ff; }}
  tbody tr:nth-child(even) {{ background: #fafbff; }}
  .foot {{ padding: 12px 28px; font-size: 11px; color: #aaa; border-top: 1px solid #eee; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>📈 Screener Momentum Screen — Daily Report</h1>
    <p>Breakout filter: Volume &gt; 1.5× avg · 1-day return &gt; 4% · Market Cap &gt; ₹500 Cr</p>
  </div>
  <div class="meta">
    <span>📅 Date: <strong>{report_date}</strong></span>
    <span>📊 Stocks: <strong>{len(rows)}</strong></span>
    <span>🔗 <a href="{SCREEN_URL}" target="_blank" style="color:#4a6cf7">screener.in/screens/3664072/screen1</a></span>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>{header_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="foot">Auto-generated via GitHub Actions · Source: Screener.in · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML → {filepath}")

def save_json(headers, rows, filepath, report_date):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "date": report_date,
        "screen_url": SCREEN_URL,
        "total_stocks": len(rows),
        "headers": headers,
        "stocks": [dict(zip(headers, row)) for row in rows],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON → {filepath}")

def update_index(report_date, csv_path, html_path, json_path, total):
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    index = {"reports": []}
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    index["reports"] = [r for r in index["reports"] if r["date"] != report_date]
    index["reports"].append({
        "date": report_date,
        "total_stocks": total,
        "csv": csv_path,
        "html": html_path,
        "json": json_path,
    })
    index["reports"].sort(key=lambda x: x["date"], reverse=True)
    index["last_updated"] = datetime.utcnow().isoformat()
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"✅ Index → {index_path}")

def main():
    today = date.today().isoformat()
    print(f"\n🚀 Screener Daily Scraper v2 — {today}")
    print(f"📡 Fetching: {SCREEN_URL}\n")

    html = fetch_screen(SCREEN_URL)
    headers, rows = parse_table(html)
    print(f"📊 {len(rows)} stocks · {len(headers)} columns: {headers}\n")

    base = os.path.join(OUTPUT_DIR, today, today)
    save_csv(headers, rows, base + "_screener.csv")
    save_html(headers, rows, base + "_screener.html", today)
    save_json(headers, rows, base + "_screener.json", today)
    update_index(today, base + "_screener.csv", base + "_screener.html", base + "_screener.json", len(rows))

    print(f"\n✅ All done — {len(rows)} stocks saved for {today}")

if __name__ == "__main__":
    main()
