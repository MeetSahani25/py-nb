"""
earnings_scanner.py v2
Fetches Screener.in /results/latest/?all= for a given date.
Parses the card-based layout (each company = one card with
Sales / EBIDT / Net Profit / EPS across 3 quarters + YoY%).
No filters are applied for now; all parsed companies are included.
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
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import time

OUTPUT_DIR   = "reports"
EARNINGS_DIR = os.path.join(OUTPUT_DIR, "earnings")
LOGIN_URL    = "https://www.screener.in/login/"
RESULTS_BASE = "https://www.screener.in/results/latest/"

EMAIL    = os.environ.get("SCREENER_EMAIL",    "")
PASSWORD = os.environ.get("SCREENER_PASSWORD", "")

# ── Filters ───────────────────────────────────────────────────────────────────
MIN_MCAP_CR = 500    # Market cap in Crores

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

def build_results_url(target_date, page=1):
    """
    Build Screener's latest-results URL for a specific result date/page.

    Screener's latest-results paginator uses the query parameter `p`, not
    `page`. The first page is simply the base URL; later pages use p=N.
    """
    params = [
        ("all", ""),
        ("result_update_date__day", str(target_date.day)),
        ("result_update_date__month", str(target_date.month)),
        ("result_update_date__year", str(target_date.year)),
    ]

    if page > 1:
        params.append(("p", str(page)))

    return f"{RESULTS_BASE}?{urlencode(params)}"


def pagination_info(html):
    """
    Read Screener's actual paginator.

    Returns:
        (current_page, total_pages, total_results)
    """
    soup = BeautifulSoup(html, "html.parser")

    current_page = 1
    total_pages = None
    total_results = None

    current = soup.select_one("p.paginator .this-page")
    if current:
        try:
            current_page = int(current.get_text(strip=True))
        except (ValueError, TypeError):
            pass

    paginator = soup.select_one("p.paginator")

    if paginator:
        page_numbers = [current_page]

        for a in paginator.find_all("a", href=True):
            query = parse_qs(urlparse(a["href"]).query)

            if "p" not in query:
                continue

            try:
                page_numbers.append(int(query["p"][0]))
            except (ValueError, TypeError):
                continue

        if page_numbers:
            total_pages = max(page_numbers)

        match = re.search(
            r"([\d,]+)\s+results",
            paginator.get_text(" ", strip=True),
            re.IGNORECASE,
        )

        if match:
            total_results = int(match.group(1).replace(",", ""))

    return current_page, total_pages, total_results


def next_page_from_links(html, current_page):
    """
    Find the smallest Screener paginator page > current_page.
    Screener uses query parameter `p`.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    paginator = soup.select_one("p.paginator")

    if not paginator:
        return None

    for a in paginator.find_all("a", href=True):
        query = parse_qs(urlparse(a["href"]).query)

        if "p" not in query:
            continue

        try:
            page_number = int(query["p"][0])
        except (ValueError, TypeError):
            continue

        if page_number > current_page:
            candidates.append(page_number)

    if not candidates:
        return None

    return min(candidates)


def fetch_results_page(session, target_date, page=1):
    """
    Fetch one page of Screener results for a given date.
    Retries a small number of times on HTTP 429.
    """
    url = build_results_url(target_date, page)

    if page > 1:
        time.sleep(1.5)

    print(f"  Fetching page {page}: {url}")

    for attempt in range(3):
        resp = session.get(url, timeout=20)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")

            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = 4.0 * (attempt + 1)

            print(
                f"  ⚠  Screener rate-limited page {page} "
                f"(attempt {attempt + 1}/3). Waiting {delay:.1f}s..."
            )

            if attempt == 2:
                resp.raise_for_status()

            time.sleep(delay)
            continue

        resp.raise_for_status()
        return resp.text

    raise RuntimeError(f"Could not fetch Screener page {page}")


def fetch_all_results(session, target_date):
    """
    Fetch every Screener results page for target_date.

    Uses Screener's reported page count when available, while also checking
    actual pagination links. Stops safely if pages repeat or return no companies.
    """
    all_companies = []
    seen_names = set()
    seen_pages = set()

    page = 1
    reported_total_pages = None
    reported_total_results = None
    max_pages = 500
    last_html = None

    while page <= max_pages:
        if page in seen_pages:
            print(f"  ⚠  Page {page} was already fetched. Stopping.")
            break

        seen_pages.add(page)

        html = fetch_results_page(session, target_date, page)
        last_html = html

        current_page, total_pages, total_results = pagination_info(html)
        if current_page < 1:
            current_page = page

        if total_pages is not None:
            reported_total_pages = total_pages

        if total_results is not None:
            reported_total_results = total_results

        companies = parse_results_cards(html)

        print(
            f"  📊 Page {current_page}: "
            f"{len(companies)} companies parsed"
        )

        new_count = 0

        for company in companies:
            key = company.get("name", "").strip().casefold()
            if not key or key in seen_names:
                continue

            seen_names.add(key)
            all_companies.append(company)
            new_count += 1

        print(f"  → {new_count} new unique companies")

        # If Screener says exactly how many pages exist, use that.
        if reported_total_pages is not None and page >= reported_total_pages:
            break

        # Also inspect actual links. This protects us if the textual page
        # count is missing or changes format.
        linked_next = next_page_from_links(html, current_page)

        if linked_next is not None:
            page = linked_next
        elif reported_total_pages is not None and page < reported_total_pages:
            page += 1
        else:
            break

    if page > max_pages:
        print(f"  ⚠  Reached safety limit of {max_pages} pages.")

    print(
        f"\n  📦 Combined earnings results: "
        f"{len(all_companies)} unique companies from {len(seen_pages)} page(s)"
    )

    if reported_total_results is not None:
        print(
            f"  📋 Screener reported {reported_total_results} total results"
        )

    if reported_total_pages is not None:
        print(
            f"  📄 Screener reported {reported_total_pages} page(s)"
        )

    return all_companies, last_html


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
    Parse Screener's actual latest-results structure.

    Each company is represented by two adjacent blocks:
      1. Header div with the /company/ link and Price/M.Cap/PE.
      2. Following div containing the results table.

    The debug HTML for 2026-08-13 shows 25 result tables and 50 company links
    because every company also has a separate PDF link. We therefore parse
    the company header blocks, then pair each header with its following table.
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # This is the actual company header block observed in Screener HTML.
    headers = soup.select(
        "div.flex-row.flex-space-between.flex-align-center.margin-top-32"
    )

    print(f"  Found {len(headers)} company result blocks")

    for header in headers:
        try:
            name_link = header.find(
                "a",
                href=lambda h: h and "/company/" in h
            )

            if not name_link:
                continue

            name = name_link.get_text(" ", strip=True)

            if not name or name.upper() == "PDF":
                continue

            # The actual results table is the next sibling block.
            table_holder = header.find_next_sibling(
                "div",
                class_=lambda c: c and "responsive-holder" in c
            )

            if table_holder is None:
                continue

            table = table_holder.find("table")

            if table is None:
                continue

            card_text = header.get_text(" ", strip=True)

            price = None
            mcap = None
            pe = None

            p_match = re.search(
                r"\bPrice\s*[₹]?\s*([\d,]+(?:\.\d+)?)",
                card_text,
                re.IGNORECASE,
            )
            m_match = re.search(
                r"\bM\.Cap\s*[₹]?\s*([\d,]+(?:\.\d+)?)",
                card_text,
                re.IGNORECASE,
            )
            pe_match = re.search(
                r"\bPE\s+([\-]?\d+(?:\.\d+)?)",
                card_text,
                re.IGNORECASE,
            )

            if p_match:
                price = safe_float(p_match.group(1))

            if m_match:
                mcap = safe_float(m_match.group(1))

            if pe_match:
                pe = safe_float(pe_match.group(1))

            thead = table.find("thead")
            tbody = table.find("tbody") or table

            quarters = []

            if thead:
                ths = thead.find_all(["th", "td"])
                quarters = [
                    th.get_text(" ", strip=True)
                    for th in ths
                ]

            rows_data = {}

            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td", "th"])

                if len(tds) < 2:
                    continue

                row_name = tds[0].get_text(" ", strip=True).lower()

                if not row_name:
                    continue

                vals = [
                    td.get_text(" ", strip=True)
                    for td in tds[1:]
                ]

                rows_data[row_name] = vals

            def get_yoy(*keys):
                for key in keys:
                    for row_name, vals in rows_data.items():
                        if key in row_name and vals:
                            value = parse_yoy(vals[0])
                            if value is not None:
                                return value
                return None

            def get_qvals(*keys):
                for key in keys:
                    for row_name, vals in rows_data.items():
                        if key in row_name and len(vals) >= 2:
                            out = [
                                safe_float(
                                    re.sub(
                                        r"[%↑↓▲▼,]",
                                        "",
                                        value
                                    ).strip()
                                )
                                for value in vals[1:4]
                            ]

                            while len(out) < 3:
                                out.append(None)

                            return out

                return [None, None, None]

            sales_yoy = get_yoy("sales", "revenue")
            ebidt_yoy = get_yoy("ebidt", "ebitda")
            profit_yoy = get_yoy("net profit", "profit")
            eps_yoy = get_yoy("eps")

            sales_q = get_qvals("sales", "revenue")
            ebidt_q = get_qvals("ebidt", "ebitda")
            profit_q = get_qvals("net profit", "profit")
            eps_q = get_qvals("eps")

            companies.append({
                "name": name,
                "price": price,
                "mcap": mcap,
                "pe": pe,
                "quarters": quarters,
                "sales_yoy": sales_yoy,
                "ebidt_yoy": ebidt_yoy,
                "profit_yoy": profit_yoy,
                "eps_yoy": eps_yoy,
                "sales_q": sales_q,
                "ebidt_q": ebidt_q,
                "profit_q": profit_q,
                "eps_q": eps_q,
                "rows_raw": rows_data,
            })

        except Exception as e:
            print(f"  ⚠  Could not parse company block: {e}")
            continue

    # Deduplicate by company name.
    seen = set()
    unique = []

    for company in companies:
        key = company["name"].strip().casefold()

        if not key or key in seen:
            continue

        seen.add(key)
        unique.append(company)

    print(f"  ✅ Parsed {len(unique)} unique company cards")
    return unique


# ── Filter ────────────────────────────────────────────────────────────────────

def apply_filters(companies):
    """Keep only companies with market cap > 500 Cr."""
    filtered = [
        c for c in companies
        if c.get("mcap") is not None and c.get("mcap") > MIN_MCAP_CR
    ]
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
        cards_html = '<div class="empty">No companies were parsed today.<br>Check if results were filed or if Screener changed its page structure.</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Earnings Scanner — {report_date}</title>
<style>{DARK_CSS}</style>
</head><body>

<div class="page-header">
  <div class="page-title">⚡ EARNINGS SCANNER — {report_date}</div>
  <div class="page-meta">QUARTERLY RESULTS · {total_fetched} COMPANIES REPORTED</div>
</div>

<div class="stat-strip">
  <div class="stat">
    <div class="stat-val">{total_fetched}</div>
    <div class="stat-lbl">Results filed</div>
  </div>
</div>

<div class="filter-bar">
  <span>Active filter:</span>
  <span class="filter-tag">M.Cap &gt; ₹{MIN_MCAP_CR} Cr</span>
  <span>Showing companies above market-cap threshold</span>
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
        companies, last_html = fetch_all_results(session, target_date)
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return

    print(f"  📊 {len(companies)} companies parsed")

    if not companies:
        print(
            "  ⚠  No company cards found — page structure may have changed "
            "or no results today"
        )

        os.makedirs(EARNINGS_DIR, exist_ok=True)

        debug_path = os.path.join(
            EARNINGS_DIR,
            f"debug_{target_date}.html"
        )

        if last_html:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(last_html)

            print(f"  💾 Raw HTML saved to {debug_path}")
        else:
            print("  ⚠  No HTML available for debug output.")

        return

    filtered = apply_filters(companies)
    print(f"  ✅ {len(filtered)} companies passed market-cap filter (MCap>{MIN_MCAP_CR}Cr)")

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
            "filters": {"min_mcap_cr": MIN_MCAP_CR},
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
        print(f"\n  First 5 companies:")
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
