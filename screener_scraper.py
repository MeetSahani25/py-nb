"""
Screener.in Daily Stock Report Scraper
Fetches momentum screen results and saves as CSV + HTML
"""

import requests
from bs4 import BeautifulSoup
import csv
import json
import os
from datetime import datetime, date
import time

# ── CONFIG ──────────────────────────────────────────────────────────────────
SCREEN_URL = "https://www.screener.in/screens/3664072/screen1/"
OUTPUT_DIR = "reports"
# ────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

def fetch_screen(url):
    """Fetch a single page from Screener."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_table(html):
    """Parse the results table from Screener HTML."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"class": lambda c: c and "data-table" in c})
    if not table:
        # fallback — find any table with stock data
        table = soup.find("table")
    if not table:
        raise ValueError("Could not find data table in page")

    # Extract headers
    headers = []
    for th in table.find_all("th"):
        headers.append(th.get_text(strip=True))

    # Extract rows
    rows = []
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells:
                # Extract company URL/name from first cell anchor if present
                first_td = tr.find("td")
                if first_td and first_td.find("a"):
                    cells[0] = first_td.find("a").get_text(strip=True)
                rows.append(cells)

    return headers, rows

def save_csv(headers, rows, filepath):
    """Save data to CSV."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"✅ CSV saved: {filepath}")

def save_html(headers, rows, filepath, report_date):
    """Save data as a clean HTML report."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    def color_cell(val, col_name):
        """Color positive/negative values."""
        try:
            num = float(str(val).replace(",", "").replace("%", "").strip())
            if any(k in col_name.lower() for k in ["return", "change", "growth", "profit", "var"]):
                if num > 0:
                    return f'<td style="color:#1a9e6d;font-weight:500">{val}</td>'
                elif num < 0:
                    return f'<td style="color:#d94b4b;font-weight:500">{val}</td>'
        except:
            pass
        return f"<td>{val}</td>"

    header_html = "".join(f"<th>{h}</th>" for h in headers)
    rows_html = ""
    for i, row in enumerate(rows):
        bg = '#fafafa' if i % 2 == 0 else '#ffffff'
        cells = "".join(
            color_cell(cell, headers[j] if j < len(headers) else "")
            for j, cell in enumerate(row)
        )
        rows_html += f'<tr style="background:{bg}">{cells}</tr>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Screener Daily Report — {report_date}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #222; }}
  .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
  .header {{ background: #1a1a2e; color: white; padding: 20px 24px; }}
  .header h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
  .header p {{ margin: 4px 0 0; font-size: 13px; opacity: 0.7; }}
  .meta {{ padding: 12px 24px; background: #f0f4ff; font-size: 13px; color: #555; border-bottom: 1px solid #e0e0e0; }}
  .table-wrap {{ overflow-x: auto; padding: 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #1a1a2e; color: white; padding: 10px 12px; text-align: left; font-weight: 500; font-size: 12px; white-space: nowrap; position: sticky; top: 0; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #f0f0f0; white-space: nowrap; }}
  tr:hover td {{ background: #f0f4ff !important; }}
  .footer {{ padding: 12px 24px; font-size: 11px; color: #999; border-top: 1px solid #eee; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📈 Screener Momentum Screen — Daily Report</h1>
    <p>Breakout stocks: Vol &gt; 1.5× avg · 1-day return &gt; 4% · Mkt Cap &gt; ₹500Cr</p>
  </div>
  <div class="meta">
    📅 Report Date: <strong>{report_date}</strong> &nbsp;|&nbsp;
    🔗 Screen: <a href="{SCREEN_URL}" target="_blank">screener.in/screens/3664072/screen1/</a> &nbsp;|&nbsp;
    📊 Total stocks: <strong>{len(rows)}</strong>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>{header_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="footer">Generated automatically via GitHub Actions · Data source: Screener.in</div>
</div>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML saved: {filepath}")

def save_json(headers, rows, filepath, report_date):
    """Save as JSON for easy parsing by Claude later."""
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
    print(f"✅ JSON saved: {filepath}")

def update_index(report_date, csv_path, html_path):
    """Maintain a simple index.json of all reports."""
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {"reports": []}

    # Remove duplicate for same date
    index["reports"] = [r for r in index["reports"] if r["date"] != report_date]
    index["reports"].append({
        "date": report_date,
        "csv": csv_path,
        "html": html_path,
    })
    index["reports"].sort(key=lambda x: x["date"], reverse=True)
    index["last_updated"] = datetime.utcnow().isoformat()

    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"✅ Index updated: {index_path}")

def main():
    today = date.today().isoformat()
    print(f"\n🚀 Screener Daily Scraper — {today}")
    print(f"📡 Fetching: {SCREEN_URL}")

    try:
        html = fetch_screen(SCREEN_URL)
        headers, rows = parse_table(html)
        print(f"📊 Found {len(rows)} stocks, {len(headers)} columns")

        csv_path  = os.path.join(OUTPUT_DIR, today, f"{today}_screener.csv")
        html_path = os.path.join(OUTPUT_DIR, today, f"{today}_screener.html")
        json_path = os.path.join(OUTPUT_DIR, today, f"{today}_screener.json")

        save_csv(headers, rows, csv_path)
        save_html(headers, rows, html_path, today)
        save_json(headers, rows, json_path, today)
        update_index(today, csv_path, html_path)

        print(f"\n✅ Done! {len(rows)} stocks saved for {today}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

if __name__ == "__main__":
    main()
