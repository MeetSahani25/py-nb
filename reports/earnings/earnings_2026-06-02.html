"""
earnings_scanner.py v2
Fetches Screener.in /results/latest/?all= for a given date.
Parses the card-based layout (each company = one card with
Sales / EBIDT / Net Profit / EPS across 3 quarters + YoY%).
Filters: Mkt Cap > 500 Cr AND Net Profit YoY > 50%.
Outputs a dark-themed HTML report showing only the filtered cards,
styled exactly like the Screener mobile card layout.

Usage:
  python earnings_scanner.py              # yesterday's results
  python earnings_scanner.py 2026-06-02   # specific date
"""

import requests
from bs4 import BeautifulSoup
import json, os, re, sys
from datetime import datetime, date, timedelta

OUTPUT_DIR   = "reports"
EARNINGS_DIR = os.path.join(OUTPUT_DIR, "earnings")
LOGIN_URL    = "https://www.screener.in/login/"
RESULTS_BASE = "https://www.screener.in/results/latest/"

EMAIL    = os.environ.get("SCREENER_EMAIL",    "")
PASSWORD = os.environ.get("SCREENER_PASSWORD", "")

# ── Filters ───────────────────────────────────────────────────────────────────
MIN_MCAP_CR       = 500    # Market cap in Crores
MIN_PROFIT_YOY_PC = 50     # Net profit YoY growth %

# ── Dark CSS ──────────────────────────────────────────────────────────────────
DARK_CSS = """
:root{
  --bg:#0d0f14;--bg2:#131620;--bg3:#1a1d2e;--bg4:#1e2235;
  --border:#252840;--border2:#2e3250;
  --text:#e2e4f0;--text2:#9198b8;--text3:#545c7a;
  --amber:#f0a500;--amber-dim:#3d2900;
  --green:#00c875;--green-dim:#002e1a;
  --red:#ff4560;--red-dim:#3d0010;
  --blue:#4a9eff;--blue-dim:#0a1f3d;
  --mono:'JetBrains Mono','Fira Code','Courier New',monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}
.page-header{background:var(--bg2);border-bottom:2px solid var(--amber);
  padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
.page-title{font-size:16px;font-weight:600;color:var(--amber);letter-spacing:.5px}
.page-meta{font-size:11px;color:var(--text3);font-family:var(--mono)}
.stat-strip{background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 24px;display:flex;gap:32px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:2px}
.stat-val{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--amber)}
.stat-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.filter-bar{background:var(--bg3);border-bottom:1px solid var(--border);
  padding:8px 24px;font-size:11px;color:var(--text2);display:flex;gap:20px}
.filter-tag{background:var(--amber-dim);color:var(--amber);padding:2px 10px;
  border-radius:3px;font-weight:600;font-family:var(--mono);font-size:10px}
.cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
  gap:16px;padding:16px 24px}
/* ── Company card ── */
.card{background:var(--bg2);border:1px solid var(--border);
  border-radius:8px;overflow:hidden}
.card-header{background:var(--bg3);padding:12px 16px;
  border-bottom:1px solid var(--border)}
.card-name{font-size:14px;font-weight:600;color:var(--text);margin-bottom:4px}
.card-meta{display:flex;gap:16px;font-family:var(--mono);font-size:11px;color:var(--text2)}
.card-meta span strong{color:var(--amber)}
/* ── Result table ── */
.result-table{width:100%;border-collapse:collapse;font-size:12px}
.result-table th{padding:7px 12px;text-align:right;font-size:9px;font-weight:600;
  text-transform:uppercase;letter-spacing:.4px;color:var(--text3);
  background:var(--bg4);border-bottom:1px solid var(--border2);white-space:nowrap}
.result-table th:first-child{text-align:left}
.result-table td{padding:8px 12px;text-align:right;border-bottom:1px solid var(--border);
  font-family:var(--mono);font-size:12px;white-space:nowrap}
.result-table td:first-child{text-align:left;font-family:-apple-system,
  BlinkMacSystemFont,'Segoe UI',sans-serif;color:var(--text2);font-size:11px}
.result-table tr:last-child td{border-bottom:none}
.result-table tr:hover td{background:var(--bg4)}
/* ── YoY badge ── */
.yoy{display:inline-block;font-family:var(--mono);font-size:11px;font-weight:600}
.yoy.up{color:var(--green)}
.yoy.dn{color:var(--red)}
.yoy.neu{color:var(--text3)}
/* ── Profit highlight ── */
.profit-highlight{background:var(--green-dim);border-top:1px solid var(--green)}
.profit-highlight td:first-child{color:var(--green) !important;font-weight:600}
/* ── Empty state ── */
.empty{padding:40px 24px;text-align:center;color:var(--text3);font-size:13px}
.page-foot{padding:10px 24px;font-size:10px;color:var(--text3);font-family:var(--mono);
  background:var(--bg2);border-top:1px solid var(--border);text-align:center}
"""

# ── Login ─────────────────────────────────────────────────────────────────────

def login():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer":    "https://www.screener.in/",
    })
    if not EMAIL or not PASSWORD:
        print("  ⚠  No credentials — will fetch as guest (limited data)")
        return s, False

    resp = s.get(LOGIN_URL, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    csrf_inp = soup.find("input", {"name": "csrfmiddlewaretoken"})
    csrf = csrf_inp["value"] if csrf_inp else s.cookies.get("csrftoken", "")

    s.headers.update({"Referer": LOGIN_URL, "Origin": "https://www.screener.in"})
    r = s.post(LOGIN_URL, data={
        "csrfmiddlewaretoken": csrf,
        "username": EMAIL,
        "password": PASSWORD,
    }, timeout=15)

    ok = bool(s.cookies.get("sessionid")) or "logout" in r.text.lower()
    print(f"  {'✅ Logged in' if ok else '⚠  Login uncertain'} as {EMAIL}")
    return s, ok

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_results_page(session, target_date):
    """Fetch all results for a given date using ?all= param."""
    url = (f"{RESULTS_BASE}?all="
           f"&result_update_date__day={target_date.day}"
           f"&result_update_date__month={target_date.month}"
           f"&result_update_date__year={target_date.year}")
    print(f"  Fetching: {url}")
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    html = resp.text

    # Debug: print page structure to logs
    from bs4 import BeautifulSoup as _BS
    _soup = _BS(html, "html.parser")

    # Print all div/section class names to understand structure
    print("\n  [DEBUG] Top-level containers found:")
    for tag in _soup.find_all(["div","section","article","li"], limit=200):
        cls = " ".join(tag.get("class", []))
        if cls and any(k in cls.lower() for k in ["result","company","card","item","row","entry"]):
            txt = tag.get_text(strip=True)[:60]
            print(f"    <{tag.name} class='{cls}'> → {txt}")

    # Print all company links
    print("\n  [DEBUG] Company links (/company/ hrefs):")
    for a in _soup.find_all("a", href=lambda h: h and "/company/" in h)[:10]:
        print(f"    {a.get('href','')} → '{a.get_text(strip=True)[:40]}'")
        # Print parent chain
        p = a.parent
        for _ in range(4):
            if p:
                print(f"      parent: <{p.name} class='{' '.join(p.get('class',[]))}'>")
                p = p.parent

    print()
    return html

# ── Parse cards ───────────────────────────────────────────────────────────────

def safe_float(v):
    if v is None: return None
    s = str(v).replace(",","").replace("%","").replace("₹","").replace("Cr","").strip()
    if s in ("","—","-","N/A","na","NA","--"): return None
    try: return float(s)
    except: return None

def parse_yoy(text):
    """Parse YoY % from text like '11%↑' or '-97%↓' or '11%'."""
    if not text: return None
    text = text.strip()
    # Remove arrow characters
    text = text.replace("↑","").replace("↓","").replace("▲","").replace("▼","").strip()
    return safe_float(text)

def parse_results_cards(html):
    """
    Parse the card-based results page.
    Each company card contains:
      - Company name, Price, M.Cap, PE
      - A table with rows: Sales, EBIDT, Net profit, EPS
        and columns: YoY%, [Latest Quarter], [Prev Quarter], [Year Ago Quarter]
    Returns list of company dicts.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Screener wraps each company result in a div with class "result-card" or similar
    # Try multiple selectors based on Screener's HTML structure
    cards = (soup.find_all("div", class_=re.compile(r"result", re.I)) or
             soup.find_all("section", class_=re.compile(r"result", re.I)) or
             soup.find_all("div", class_=re.compile(r"company", re.I)))

    # Fallback: find by structure — look for divs containing both a company link and a table
    if not cards:
        # Try finding all tables on the page — each company has one
        all_tables = soup.find_all("table")
        print(f"  Found {len(all_tables)} tables on page")
        
        for tbl in all_tables:
            # Find parent that contains company info
            parent = tbl.parent
            for _ in range(5):  # walk up max 5 levels
                if parent is None: break
                name_el = parent.find(["h2","h3","h4","a"], class_=re.compile(r"name|company|title", re.I))
                if not name_el:
                    name_el = parent.find("a", href=re.compile(r"/company/"))
                if name_el:
                    company = parse_single_card(parent, name_el, tbl)
                    if company:
                        companies.append(company)
                    break
                parent = parent.parent
    else:
        print(f"  Found {len(cards)} result cards")
        for card in cards:
            name_el = (card.find("a", href=re.compile(r"/company/")) or
                      card.find(["h2","h3","h4"]))
            tbl = card.find("table")
            if name_el and tbl:
                company = parse_single_card(card, name_el, tbl)
                if company:
                    companies.append(company)

    # Deduplicate by name
    seen = set()
    unique = []
    for c in companies:
        if c["name"] and c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)

    return unique

def parse_single_card(card_el, name_el, table_el):
    """Parse one company card into a dict."""
    try:
        name = name_el.get_text(strip=True)
        if not name or len(name) < 2: return None

        # Extract Price, M.Cap, PE from card header text
        card_text = card_el.get_text(" ", strip=True)
        
        price  = None
        mcap   = None
        pe     = None

        # Try to find price/mcap/pe spans or text patterns
        price_el = (card_el.find(string=re.compile(r"Price|CMP|₹\s*[\d.]+", re.I)) or
                   card_el.find(class_=re.compile(r"price|cmp", re.I)))
        
        # Parse from text using regex
        p_match = re.search(r"Price\s*[₹:]?\s*([\d,]+\.?\d*)", card_text)
        m_match = re.search(r"M\.?Cap\s*[₹:]?\s*([\d,]+\.?\d*)", card_text)
        pe_match= re.search(r"PE\s*[:]?\s*([\d.]+)", card_text)
        
        if p_match:  price = safe_float(p_match.group(1))
        if m_match:  mcap  = safe_float(m_match.group(1))
        if pe_match: pe    = safe_float(pe_match.group(1))

        # Parse the result table
        rows_data = {}
        quarters  = []

        thead = table_el.find("thead")
        tbody = table_el.find("tbody")

        # Get quarter labels from header
        if thead:
            header_cells = thead.find_all(["th","td"])
            quarters = [c.get_text(strip=True) for c in header_cells[1:]]  # skip first col

        # Get data rows
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = tr.find_all(["td","th"])
                if not cells: continue
                row_name = cells[0].get_text(strip=True)
                if not row_name: continue
                
                row_values = []
                for cell in cells[1:]:
                    # Each cell may have YoY% and actual value
                    cell_text = cell.get_text(" ", strip=True)
                    row_values.append(cell_text)
                
                rows_data[row_name.lower()] = row_values

        # Extract YoY% for key metrics
        # Column 0 of data is typically YoY%, cols 1-3 are quarterly values
        def get_yoy(row_key):
            for k in rows_data:
                if row_key in k:
                    vals = rows_data[k]
                    if vals:
                        return parse_yoy(vals[0])  # first col = YoY
            return None

        def get_quarterly_values(row_key):
            """Get [latest_q, prev_q, year_ago_q] values."""
            for k in rows_data:
                if row_key in k:
                    vals = rows_data[k]
                    # Skip YoY col (index 0), return next 3
                    result = []
                    for v in vals[1:4]:
                        result.append(safe_float(re.sub(r'[%↑↓▲▼]','',v).strip()))
                    return result
            return [None, None, None]

        sales_yoy   = get_yoy("sales") or get_yoy("revenue") or get_yoy("turnover")
        ebidt_yoy   = get_yoy("ebidt") or get_yoy("ebitda") or get_yoy("operating")
        profit_yoy  = get_yoy("net profit") or get_yoy("profit") or get_yoy("pat")
        eps_yoy     = get_yoy("eps") or get_yoy("earning")

        sales_q     = get_quarterly_values("sales") or get_quarterly_values("revenue")
        ebidt_q     = get_quarterly_values("ebidt") or get_quarterly_values("ebitda")
        profit_q    = get_quarterly_values("net profit") or get_quarterly_values("profit")
        eps_q       = get_quarterly_values("eps")

        return {
            "name":       name,
            "price":      price,
            "mcap":       mcap,
            "pe":         pe,
            "quarters":   quarters,
            "sales_yoy":  sales_yoy,
            "ebidt_yoy":  ebidt_yoy,
            "profit_yoy": profit_yoy,
            "eps_yoy":    eps_yoy,
            "sales_q":    sales_q,
            "ebidt_q":    ebidt_q,
            "profit_q":   profit_q,
            "eps_q":      eps_q,
            "rows_raw":   rows_data,
        }
    except Exception as e:
        return None

# ── Filter ────────────────────────────────────────────────────────────────────

def apply_filters(companies):
    """Filter: Mkt Cap > 500 Cr AND Net Profit YoY > 50%."""
    filtered = []
    for c in companies:
        mcap = c.get("mcap")
        pyoy = c.get("profit_yoy")
        
        # Skip if missing key data
        if mcap is None and pyoy is None:
            continue
        
        # Apply filters
        mcap_ok   = mcap  is None or mcap  >= MIN_MCAP_CR        # include if mcap unknown
        profit_ok = pyoy is not None and pyoy >= MIN_PROFIT_YOY_PC
        
        if profit_ok and mcap_ok:
            filtered.append(c)
    
    # Sort by profit YoY descending
    filtered.sort(key=lambda x: x.get("profit_yoy") or 0, reverse=True)
    return filtered

# ── HTML ──────────────────────────────────────────────────────────────────────

def fmt_num(v, d=2):
    if v is None: return "—"
    try: return f"{float(v):,.{d}f}"
    except: return str(v)

def fmt_yoy(v):
    if v is None: return '<span class="yoy neu">—</span>'
    cls = "up" if v > 0 else "dn" if v < 0 else "neu"
    arrow = "↑" if v > 0 else "↓" if v < 0 else ""
    return f'<span class="yoy {cls}">{arrow}{abs(v):.0f}%</span>'

def company_card_html(c):
    q = c.get("quarters", [])
    # Quarter labels for header
    q_labels = q[1:4] if len(q) >= 4 else (q[1:] if len(q) > 1 else ["Q1","Q2","Q3"])
    while len(q_labels) < 3: q_labels.append("—")

    profit_yoy_val = c.get("profit_yoy")
    profit_color   = "var(--green)" if profit_yoy_val and profit_yoy_val >= 50 else "var(--amber)"

    rows_html = ""
    metrics = [
        ("Sales",       c["sales_yoy"],  c["sales_q"]),
        ("EBIDT",       c["ebidt_yoy"],  c["ebidt_q"]),
        ("Net Profit",  c["profit_yoy"], c["profit_q"]),
        ("EPS",         c["eps_yoy"],    c["eps_q"]),
    ]
    for label, yoy, qvals in metrics:
        qvals = qvals or [None, None, None]
        while len(qvals) < 3: qvals.append(None)
        is_profit = "profit" in label.lower()
        row_style = f'style="background:var(--green-dim)"' if is_profit else ""
        label_style = f'style="color:var(--green);font-weight:600"' if is_profit else ""
        rows_html += f"""<tr {row_style}>
          <td {label_style}>{label}</td>
          <td>{fmt_yoy(yoy)}</td>
          <td>{fmt_num(qvals[0])}</td>
          <td>{fmt_num(qvals[1])}</td>
          <td>{fmt_num(qvals[2])}</td>
        </tr>"""

    return f"""
    <div class="card">
      <div class="card-header">
        <div class="card-name">{c['name']}</div>
        <div class="card-meta">
          <span>Price <strong>₹{fmt_num(c['price'], 2)}</strong></span>
          <span>M.Cap <strong>₹{fmt_num(c['mcap'], 0)} Cr</strong></span>
          <span>PE <strong>{fmt_num(c['pe'], 1)}</strong></span>
          <span style="color:{profit_color};font-weight:600;font-family:var(--mono)">
            Profit YoY {fmt_yoy(profit_yoy_val)}
          </span>
        </div>
      </div>
      <table class="result-table">
        <thead>
          <tr>
            <th></th>
            <th>YoY</th>
            <th>{q_labels[0]}</th>
            <th>{q_labels[1]}</th>
            <th>{q_labels[2]}</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""

def build_html(filtered, total_fetched, report_date):
    cards_html = "".join(company_card_html(c) for c in filtered)
    if not cards_html:
        cards_html = '<div class="empty">No companies matched the filters today.<br>Try lowering the profit growth threshold or check if results were filed.</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Earnings Scanner — {report_date}</title>
<style>{DARK_CSS}</style>
</head><body>

<div class="page-header">
  <div class="page-title">⚡ EARNINGS SCANNER — {report_date}</div>
  <div class="page-meta">QUARTERLY RESULTS · {total_fetched} COMPANIES REPORTED · {len(filtered)} PASSED FILTERS</div>
</div>

<div class="stat-strip">
  <div class="stat">
    <div class="stat-val">{total_fetched}</div>
    <div class="stat-lbl">Results filed</div>
  </div>
  <div class="stat">
    <div class="stat-val" style="color:var(--green)">{len(filtered)}</div>
    <div class="stat-lbl">Passed filters</div>
  </div>
  <div class="stat">
    <div class="stat-val" style="color:var(--text3)">{total_fetched - len(filtered)}</div>
    <div class="stat-lbl">Filtered out</div>
  </div>
</div>

<div class="filter-bar">
  <span>Active filters:</span>
  <span class="filter-tag">M.Cap &gt; ₹{MIN_MCAP_CR} Cr</span>
  <span class="filter-tag">Net Profit YoY &gt; {MIN_PROFIT_YOY_PC}%</span>
  <span>Sorted by highest profit growth</span>
</div>

<div class="cards-grid">{cards_html}</div>

<div class="page-foot">
  Earnings Scanner v2 · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC · Source: Screener.in/results/latest/
</div>
</body></html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main(target_date=None):
    today = date.today()

    if target_date is None:
        # Default: yesterday (results filed after market close previous day)
        target_date = today - timedelta(days=1)
        # Skip weekends
        if target_date.weekday() == 6: target_date -= timedelta(days=2)
        if target_date.weekday() == 5: target_date -= timedelta(days=1)

    print(f"\n⚡ Earnings Scanner v2 — results for {target_date}")

    session, logged_in = login()

    try:
        html = fetch_results_page(session, target_date)
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return

    companies = parse_results_cards(html)
    print(f"  📊 {len(companies)} companies parsed")

    if not companies:
        print("  ⚠  No company cards found — page structure may have changed or no results today")
        # Save debug HTML
        os.makedirs(EARNINGS_DIR, exist_ok=True)
        with open(os.path.join(EARNINGS_DIR, f"debug_{target_date}.html"), "w") as f:
            f.write(html)
        print(f"  💾 Raw HTML saved to earnings/debug_{target_date}.html for inspection")
        return

    filtered = apply_filters(companies)
    print(f"  ✅ {len(filtered)} companies passed filters (MCap>{MIN_MCAP_CR}Cr, ProfitYoY>{MIN_PROFIT_YOY_PC}%)")

    # Save outputs
    os.makedirs(EARNINGS_DIR, exist_ok=True)
    date_str  = target_date.isoformat()
    html_path = os.path.join(EARNINGS_DIR, f"earnings_{date_str}.html")
    json_path = os.path.join(EARNINGS_DIR, f"earnings_{date_str}.json")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(filtered, len(companies), date_str))
    print(f"  ✅ HTML → {html_path}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "date":           date_str,
            "total_fetched":  len(companies),
            "total_filtered": len(filtered),
            "filters": {
                "min_mcap_cr":       MIN_MCAP_CR,
                "min_profit_yoy_pc": MIN_PROFIT_YOY_PC,
            },
            "companies": [{
                "name":       c["name"],
                "price":      c["price"],
                "mcap":       c["mcap"],
                "pe":         c["pe"],
                "sales_yoy":  c["sales_yoy"],
                "ebidt_yoy":  c["ebidt_yoy"],
                "profit_yoy": c["profit_yoy"],
                "eps_yoy":    c["eps_yoy"],
            } for c in filtered]
        }, f, indent=2, ensure_ascii=False)
    print(f"  ✅ JSON → {json_path}")

    if filtered:
        print(f"\n  Top picks:")
        for c in filtered[:5]:
            print(f"    {c['name']:30s} Profit YoY: {c.get('profit_yoy','?')}%  MCap: ₹{c.get('mcap','?')}Cr")

def run_recent(days_back=3):
    """Run scanner for last N trading days to avoid missing any results."""
    today = date.today()
    ran = []
    d = today - timedelta(days=1)  # start from yesterday
    attempts = 0
    while len(ran) < days_back and attempts < 10:
        attempts += 1
        if d.weekday() < 5:  # Mon-Fri only
            print(f"\n{'='*50}")
            main(d)
            ran.append(d)
        d -= timedelta(days=1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            # Specific date: python earnings_scanner.py 2026-06-02
            main(date.fromisoformat(sys.argv[1]))
        except ValueError:
            print(f"Invalid date: {sys.argv[1]} — use YYYY-MM-DD")
    else:
        # Default: scan last 3 trading days
        run_recent(days_back=3)
