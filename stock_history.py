"""
stock_history.py
Search across all historical reports to find every time
a stock appeared in your system — daily screens, weekly
analysis, silent horse picks, and earnings scanner.

Usage:
  python stock_history.py "Triveni Turbine"
  python stock_history.py "TRIVENI"
  python stock_history.py "triveni"   # case insensitive

Output:
  - Terminal summary
  - reports/history/STOCKNAME_history.html
    Dark-themed timeline showing every appearance with context
"""

import json, os, glob, sys, re
from datetime import date, datetime
from collections import defaultdict

REPORTS_DIR  = "reports"
HISTORY_DIR  = os.path.join(REPORTS_DIR, "history")

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
.summary-strip{background:var(--bg2);border-bottom:1px solid var(--border);
  padding:10px 24px;display:flex;gap:28px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:2px}
.stat-val{font-family:var(--mono);font-size:18px;font-weight:600;color:var(--amber)}
.stat-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.verdict{padding:12px 24px;font-size:13px;font-weight:500;border-bottom:1px solid var(--border)}
.verdict.caught{background:var(--green-dim);color:var(--green);border-left:3px solid var(--green)}
.verdict.missed{background:var(--red-dim);color:var(--red);border-left:3px solid var(--red)}
.verdict.partial{background:var(--amber-dim);color:var(--amber);border-left:3px solid var(--amber)}
/* Timeline */
.timeline{padding:20px 24px;position:relative}
.timeline::before{content:'';position:absolute;left:48px;top:0;bottom:0;
  width:1px;background:var(--border2)}
.tl-item{display:flex;gap:16px;margin-bottom:20px;position:relative}
.tl-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;margin-top:4px;
  border:2px solid;z-index:1}
.tl-dot.daily{background:var(--blue-dim);border-color:var(--blue)}
.tl-dot.weekly{background:var(--amber-dim);border-color:var(--amber)}
.tl-dot.gold{background:var(--amber);border-color:var(--amber)}
.tl-dot.silver{background:var(--blue-dim);border-color:var(--blue)}
.tl-dot.earnings{background:var(--green-dim);border-color:var(--green)}
.tl-content{flex:1;background:var(--bg2);border:1px solid var(--border);
  border-radius:6px;padding:10px 14px}
.tl-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.tl-date{font-family:var(--mono);font-size:11px;color:var(--text3)}
.tl-source{font-size:10px;font-weight:600;padding:2px 8px;border-radius:3px;letter-spacing:.4px}
.tl-source.daily{background:var(--blue-dim);color:var(--blue)}
.tl-source.weekly{background:var(--amber-dim);color:var(--amber)}
.tl-source.gold{background:var(--amber);color:#000}
.tl-source.silver{background:var(--blue-dim);color:var(--blue)}
.tl-source.earnings{background:var(--green-dim);color:var(--green)}
.tl-metrics{display:flex;gap:14px;flex-wrap:wrap;font-family:var(--mono);font-size:11px}
.tl-metric{color:var(--text2)}
.tl-metric span{color:var(--text)}
.up{color:var(--green);font-weight:600}
.dn{color:var(--red);font-weight:600}
/* Price chart */
.price-chart{padding:16px 24px;border-bottom:1px solid var(--border)}
.chart-title{font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.8px;color:var(--amber);margin-bottom:10px}
.chart-bars{display:flex;align-items:flex-end;gap:4px;height:60px}
.chart-bar{flex:1;border-radius:2px 2px 0 0;min-height:3px;position:relative;cursor:default}
.chart-bar:hover::after{content:attr(title);position:absolute;bottom:100%;left:50%;
  transform:translateX(-50%);background:var(--bg4);border:1px solid var(--border2);
  padding:3px 7px;border-radius:3px;font-size:10px;white-space:nowrap;z-index:10;
  font-family:var(--mono);color:var(--text)}
.chart-dates{display:flex;justify-content:space-between;
  font-size:9px;color:var(--text3);font-family:var(--mono);margin-top:4px}
/* Source legend */
.legend{display:flex;gap:16px;padding:8px 24px;background:var(--bg3);
  border-bottom:1px solid var(--border);font-size:10px;flex-wrap:wrap}
.legend-item{display:flex;align-items:center;gap:5px;color:var(--text2)}
.legend-dot{width:8px;height:8px;border-radius:50%}
.page-foot{padding:10px 24px;font-size:10px;color:var(--text3);font-family:var(--mono);
  background:var(--bg2);border-top:1px solid var(--border);text-align:center}
.empty{padding:40px 24px;text-align:center;color:var(--text3);font-size:13px}
.section-head{padding:8px 24px;background:var(--bg3);border-bottom:1px solid var(--border);
  border-top:1px solid var(--border);font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:1px;color:var(--amber);display:flex;justify-content:space-between}
"""

# ── Data loaders ──────────────────────────────────────────────────────────────

def name_matches(stock_name, query):
    """Fuzzy case-insensitive name match."""
    sn = stock_name.lower().strip()
    q  = query.lower().strip()
    # Exact or partial match
    if q in sn or sn in q:
        return True
    # Match first word
    if sn.split()[0] == q.split()[0]:
        return True
    # Match without common suffixes
    clean = re.sub(r'\s*(ltd|limited|technologies|tech|industries|ind|pharma|chemicals|energy|finance|services|solutions|infra|infrastructure)\s*$', '', sn, flags=re.I).strip()
    if q in clean or clean in q:
        return True
    return False

def load_daily_appearances(query):
    """Search all daily screener JSONs for the stock."""
    results = []
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "????-??-??", "????-??-??_screener.json")))
    
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            report_date = data.get("date", "")
            headers = data.get("headers", [])
            
            for stock in data.get("stocks", []):
                if not isinstance(stock, dict): continue
                
                # Find name
                name_idx = next((i for i,h in enumerate(headers) if "name" in h.lower()), 0)
                name = stock.get(headers[name_idx], "") if headers else ""
                
                if not name_matches(name, query): continue
                
                # Extract key metrics
                def gv(*kws):
                    for kw in kws:
                        for h in headers:
                            if kw.lower() in h.lower():
                                v = stock.get(h)
                                if v:
                                    try: return float(str(v).replace(",","").replace("%","").strip())
                                    except: pass
                    return None
                
                results.append({
                    "source":    "daily",
                    "date":      report_date,
                    "name":      name,
                    "cmp":       gv("cmp","current price"),
                    "ret1d":     gv("1day","return over 1day"),
                    "ret1w":     gv("1week","return over 1week"),
                    "ret1m":     gv("1month","return over 1month"),
                    "mktcap":    gv("mar cap","market cap"),
                    "vol":       gv("volume"),
                    "qoqp":      gv("qoq profit"),
                    "roce":      gv("roce"),
                })
        except Exception as e:
            continue
    
    return results

def load_weekly_appearances(query):
    """Search weekly analysis JSONs."""
    results = []
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "weekly", "week_*_analysis.json")))
    
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            
            week_dates = data.get("dates", [])
            week_start = week_dates[0] if week_dates else ""
            stats = data.get("stock_stats_summary", {})
            appeared_2p = data.get("appeared_2p", [])
            
            for name, s in stats.items():
                if not name_matches(name, query): continue
                
                results.append({
                    "source":      "weekly",
                    "date":        week_start,
                    "week_dates":  week_dates,
                    "name":        name,
                    "appearances": s.get("appearances", 0),
                    "avg_ret1d":   s.get("avg_ret1d"),
                    "price_change_week": s.get("price_change_week"),
                    "latest_cmp":  s.get("latest_cmp"),
                    "latest_ret1m": s.get("latest_ret1m"),
                    "latest_qoqp": s.get("latest_qoqp"),
                    "in_deep_dive": name in appeared_2p,
                })
        except: continue
    
    return results

def load_silent_horse_appearances(query):
    """Search silent horse JSONs for Gold/Silver/Watch appearances."""
    results = []
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "monthly", "silent_horse_*.json")))
    
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            
            report_date   = data.get("date", "")
            window_weeks  = data.get("window_weeks", 4)
            
            for tier in ["gold", "silver", "watch"]:
                for item in data.get(tier, []):
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        name, scored = item[0], item[1]
                    elif isinstance(item, dict):
                        name = item.get("name",""); scored = item
                    else: continue
                    
                    if not name_matches(name, query): continue
                    
                    results.append({
                        "source":       "silent_horse",
                        "tier":         tier,
                        "date":         report_date,
                        "window_weeks": window_weeks,
                        "name":         name,
                        "score":        scored.get("score") if isinstance(scored,dict) else None,
                        "n_weeks":      scored.get("n_weeks") if isinstance(scored,dict) else None,
                        "total_freq":   scored.get("total_freq") if isinstance(scored,dict) else None,
                        "pattern":      scored.get("pattern") if isinstance(scored,dict) else None,
                        "price_pct":    scored.get("price_pct") if isinstance(scored,dict) else None,
                    })
        except: continue
    
    return results

def load_earnings_appearances(query):
    """Search earnings scanner JSONs."""
    results = []
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "earnings", "earnings_*.json")))
    
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            
            report_date = data.get("date","")
            
            for c in data.get("companies", []):
                if not name_matches(c.get("name",""), query): continue
                results.append({
                    "source":      "earnings",
                    "date":        report_date,
                    "name":        c.get("name",""),
                    "profit_yoy":  c.get("profit_yoy"),
                    "sales_yoy":   c.get("sales_yoy"),
                    "ebidt_yoy":   c.get("ebidt_yoy"),
                    "eps_yoy":     c.get("eps_yoy"),
                    "mcap":        c.get("mcap"),
                    "price":       c.get("price"),
                    "pe":          c.get("pe"),
                })
        except: continue
    
    return results

# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse_history(daily, weekly, silent_horse, earnings, query):
    """Build a complete picture of the stock's journey through the system."""
    
    all_dates = (
        [d["date"] for d in daily] +
        [w["date"] for w in weekly] +
        [s["date"] for s in silent_horse] +
        [e["date"] for e in earnings]
    )
    all_dates = sorted(set(d for d in all_dates if d))
    
    first_seen = all_dates[0] if all_dates else None
    last_seen  = all_dates[-1] if all_dates else None
    
    # Price journey from daily reports
    price_journey = [(d["date"], d["cmp"]) for d in daily if d.get("cmp")]
    price_journey.sort(key=lambda x: x[0])
    
    first_price = price_journey[0][1]  if price_journey else None
    last_price  = price_journey[-1][1] if price_journey else None
    price_return = round(((last_price - first_price) / first_price) * 100, 1) if first_price and last_price else None
    
    # Best silent horse tier achieved
    tier_rank = {"gold": 3, "silver": 2, "watch": 1}
    best_tier = None
    if silent_horse:
        best_tier = max(silent_horse, key=lambda x: tier_rank.get(x.get("tier",""), 0))
    
    # Verdict
    if not all_dates:
        verdict = "never_seen"
        verdict_text = f"'{query}' was NEVER detected in any report. Either the name doesn't match or it didn't trigger the momentum screen."
        verdict_cls = "missed"
    elif best_tier and best_tier.get("tier") == "gold":
        verdict = "gold"
        verdict_text = f"✅ CAUGHT — Reached GOLD tier in silent horse on {best_tier['date']}. First seen {first_seen}. System had high conviction."
        verdict_cls = "caught"
    elif best_tier and best_tier.get("tier") == "silver":
        verdict = "silver"
        verdict_text = f"🟡 PARTIALLY CAUGHT — Reached SILVER in silent horse on {best_tier['date']}. First seen in daily screen {first_seen}."
        verdict_cls = "partial"
    elif daily:
        verdict = "daily_only"
        verdict_text = f"⚠ RADAR ONLY — Appeared in daily screen {len(daily)}× (first: {first_seen}) but never reached Silver/Gold. Didn't meet multi-week frequency threshold."
        verdict_cls = "partial"
    else:
        verdict = "missed"
        verdict_text = f"❌ MISSED — Not in daily screens. Either below MCap/volume filters or didn't have a 4%+ day during this period."
        verdict_cls = "missed"
    
    return {
        "first_seen":    first_seen,
        "last_seen":     last_seen,
        "total_days":    len(daily),
        "total_weeks":   len(weekly),
        "silent_picks":  len(silent_horse),
        "earnings_hits": len(earnings),
        "best_tier":     best_tier,
        "price_journey": price_journey,
        "first_price":   first_price,
        "last_price":    last_price,
        "price_return":  price_return,
        "verdict":       verdict,
        "verdict_text":  verdict_text,
        "verdict_cls":   verdict_cls,
    }

# ── HTML builder ──────────────────────────────────────────────────────────────

def pct_html(v):
    if v is None: return '<span style="color:var(--text3)">—</span>'
    c = "up" if v > 0 else "dn" if v < 0 else ""
    a = "▲" if v > 0 else "▼" if v < 0 else ""
    return f'<span class="{c}">{a}{abs(v):.1f}%</span>'

def num_html(v, d=2, prefix=""):
    if v is None: return '<span style="color:var(--text3)">—</span>'
    return f'<span style="font-family:var(--mono)">{prefix}{v:,.{d}f}</span>'

def build_timeline(daily, weekly, silent_horse, earnings):
    """Merge all appearances into a single chronological timeline."""
    events = []
    
    for d in daily:
        events.append({
            "date":   d["date"],
            "type":   "daily",
            "label":  "Daily Screen",
            "detail": f"CMP ₹{d.get('cmp','—')} · 1d {pct_html(d.get('ret1d'))} · 1mo {pct_html(d.get('ret1m'))} · QoQ profit {pct_html(d.get('qoqp'))}",
        })
    
    for w in weekly:
        events.append({
            "date":   w["date"],
            "type":   "weekly",
            "label":  f"Weekly Analysis ({w.get('appearances',0)} days that week)",
            "detail": f"Avg 1d ret {pct_html(w.get('avg_ret1d'))} · Week chg {pct_html(w.get('price_change_week'))} · 1mo {pct_html(w.get('latest_ret1m'))}",
        })
    
    for s in silent_horse:
        t = s.get("tier","watch")
        events.append({
            "date":   s["date"],
            "type":   t,
            "label":  f"Silent Horse — {t.upper()} ({s.get('window_weeks',4)}-week window)",
            "detail": f"Score {s.get('score','—')}/100 · {s.get('n_weeks','—')} weeks · freq {s.get('total_freq','—')}d · pattern: {s.get('pattern','—')} · price Δ {pct_html(s.get('price_pct'))}",
        })
    
    for e in earnings:
        events.append({
            "date":   e["date"],
            "type":   "earnings",
            "label":  "Earnings Scanner",
            "detail": f"Profit YoY {pct_html(e.get('profit_yoy'))} · Sales YoY {pct_html(e.get('sales_yoy'))} · MCap ₹{e.get('mcap','—')}Cr · PE {e.get('pe','—')}",
        })
    
    events.sort(key=lambda x: x["date"])
    return events

def build_price_chart(price_journey):
    if not price_journey or len(price_journey) < 2:
        return ""
    
    prices = [p for _, p in price_journey if p]
    dates  = [d for d, p in price_journey if p]
    if not prices: return ""
    
    min_p = min(prices); max_p = max(prices)
    rng   = max_p - min_p or 1
    
    bars = ""
    for i, (d, p) in enumerate(zip(dates, prices)):
        h   = max(3, int(((p - min_p) / rng) * 54) + 3)
        col = "var(--green)" if i > 0 and p >= prices[i-1] else "var(--red)"
        bars += f'<div class="chart-bar" style="height:{h}px;background:{col}" title="{d}: ₹{p:,.0f}"></div>'
    
    # Show first/last dates
    n = len(dates)
    date_labels = ""
    if n >= 2:
        date_labels = f'<div class="chart-dates"><span>{dates[0]}</span><span>{dates[n//2]}</span><span>{dates[-1]}</span></div>'
    
    first_p = prices[0]; last_p = prices[-1]
    pct_chg = round(((last_p - first_p) / first_p) * 100, 1)
    col = "var(--green)" if pct_chg >= 0 else "var(--red)"
    
    return f"""
    <div class="price-chart">
      <div class="chart-title">Price journey in system — ₹{first_p:,.0f} → ₹{last_p:,.0f}
        <span style="color:{col};font-family:var(--mono);margin-left:10px">
          {'▲' if pct_chg>=0 else '▼'}{abs(pct_chg)}% since first detected
        </span>
      </div>
      <div class="chart-bars">{bars}</div>
      {date_labels}
    </div>"""

def build_html(query, analysis, events, price_chart_html, stock_name):
    tl_html = ""
    for ev in events:
        tl_html += f"""
        <div class="tl-item">
          <div class="tl-dot {ev['type']}"></div>
          <div class="tl-content">
            <div class="tl-header">
              <span class="tl-date">{ev['date']}</span>
              <span class="tl-source {ev['type']}">{ev['label']}</span>
            </div>
            <div class="tl-metrics">{ev['detail']}</div>
          </div>
        </div>"""
    
    if not tl_html:
        tl_html = '<div class="empty">No appearances found in any report for this stock.</div>'
    
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock History — {stock_name}</title>
<style>{DARK_CSS}</style>
</head><body>

<div class="page-header">
  <div class="page-title">🔍 STOCK HISTORY — {stock_name.upper()}</div>
  <div class="page-meta">QUERY: "{query}" · GENERATED: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div>

<div class="verdict {analysis['verdict_cls']}">{analysis['verdict_text']}</div>

<div class="summary-strip">
  <div class="stat">
    <div class="stat-val">{analysis['total_days']}</div>
    <div class="stat-lbl">Daily appearances</div>
  </div>
  <div class="stat">
    <div class="stat-val">{analysis['total_weeks']}</div>
    <div class="stat-lbl">Weekly reports</div>
  </div>
  <div class="stat">
    <div class="stat-val">{analysis['silent_picks']}</div>
    <div class="stat-lbl">Silent horse picks</div>
  </div>
  <div class="stat">
    <div class="stat-val">{analysis['earnings_hits']}</div>
    <div class="stat-lbl">Earnings hits</div>
  </div>
  <div class="stat">
    <div class="stat-val" style="color:{'var(--green)' if analysis['price_return'] and analysis['price_return']>0 else 'var(--red)'}">
      {'▲' if analysis['price_return'] and analysis['price_return']>0 else '▼'}{abs(analysis['price_return']) if analysis['price_return'] else '—'}%
    </div>
    <div class="stat-lbl">Price Δ in system</div>
  </div>
  <div class="stat">
    <div class="stat-val" style="color:var(--text2)">{analysis['first_seen'] or '—'}</div>
    <div class="stat-lbl">First detected</div>
  </div>
</div>

<div class="legend">
  <div class="legend-item"><div class="legend-dot" style="background:var(--blue)"></div>Daily screen</div>
  <div class="legend-item"><div class="legend-dot" style="background:var(--amber)"></div>Weekly analysis</div>
  <div class="legend-item"><div class="legend-dot" style="background:var(--amber);border:2px solid #000"></div>Gold pick</div>
  <div class="legend-item"><div class="legend-dot" style="background:var(--blue-dim);border:1px solid var(--blue)"></div>Silver pick</div>
  <div class="legend-item"><div class="legend-dot" style="background:var(--green)"></div>Earnings scanner</div>
</div>

{price_chart_html}

<div class="section-head">
  <span>📅 Full Timeline — {len(events)} events</span>
  <span style="color:var(--text3)">{analysis['first_seen']} → {analysis['last_seen']}</span>
</div>
<div class="timeline">{tl_html}</div>

<div class="page-foot">
  Stock History Tool · py-nb · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
</div>
</body></html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main(query):
    print(f"\n🔍 Searching history for: '{query}'")
    print(f"   Reports dir: {os.path.abspath(REPORTS_DIR)}\n")

    # Load from all sources
    print("  📂 Scanning daily reports...")
    daily = load_daily_appearances(query)
    print(f"     → {len(daily)} daily appearances")

    print("  📂 Scanning weekly reports...")
    weekly = load_weekly_appearances(query)
    print(f"     → {len(weekly)} weekly appearances")

    print("  📂 Scanning silent horse reports...")
    sh = load_silent_horse_appearances(query)
    print(f"     → {len(sh)} silent horse picks")

    print("  📂 Scanning earnings reports...")
    earn = load_earnings_appearances(query)
    print(f"     → {len(earn)} earnings appearances")

    if not any([daily, weekly, sh, earn]):
        print(f"\n  ❌ '{query}' not found in ANY report.")
        print("     Try a shorter search term, e.g. 'Triveni' instead of 'Triveni Turbine'")
        return

    # Get stock name from first result
    stock_name = (daily or weekly or sh or earn)[0].get("name", query)

    # Analyse
    analysis = analyse_history(daily, weekly, sh, earn, query)

    print(f"\n  📊 Result:")
    print(f"     First seen:   {analysis['first_seen']}")
    print(f"     Last seen:    {analysis['last_seen']}")
    print(f"     Daily hits:   {analysis['total_days']}")
    print(f"     Best tier:    {analysis['best_tier']['tier'].upper() if analysis['best_tier'] else 'None'}")
    print(f"     Price return: {analysis['price_return']}%")
    print(f"\n  ⚡ Verdict: {analysis['verdict_text']}")

    # Build timeline
    events        = build_timeline(daily, weekly, sh, earn)
    price_chart   = build_price_chart(analysis["price_journey"])

    # Save HTML
    os.makedirs(HISTORY_DIR, exist_ok=True)
    safe_name = re.sub(r'[^a-z0-9]', '_', query.lower()).strip('_')
    html_path = os.path.join(HISTORY_DIR, f"{safe_name}_history.html")

    html = build_html(query, analysis, events, price_chart, stock_name)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  ✅ Report → {html_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stock_history.py 'Stock Name'")
        print("Examples:")
        print("  python stock_history.py 'Triveni Turbine'")
        print("  python stock_history.py 'SUZLON'")
        print("  python stock_history.py 'triveni'")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    main(query)
