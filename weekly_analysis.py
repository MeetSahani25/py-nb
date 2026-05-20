"""
Screener.in Weekly Analysis Report
Runs every Friday at 6pm IST via GitHub Actions
- Reads Mon–Fri daily JSON reports
- Analyses stock appearance frequency
- Tracks price momentum, volume trends, return consistency
- Identifies strongest breakout candidates of the week
"""

import json
import os
from datetime import datetime, date, timedelta
from collections import defaultdict
import statistics

OUTPUT_DIR = "reports"
SCREEN_URL = "https://www.screener.in/screens/3664072/screen1/"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_this_week_dates():
    """Return Mon–Fri dates for the current week (or last 5 trading days)."""
    today = date.today()
    # Go back to find Monday
    days_back = today.weekday()  # 0=Mon, 4=Fri
    monday = today - timedelta(days=days_back)
    return [(monday + timedelta(days=i)).isoformat() for i in range(5)]

def load_daily_report(report_date):
    """Load a daily JSON report by date."""
    path = os.path.join(OUTPUT_DIR, report_date, f"{report_date}_screener.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

def safe_float(val):
    """Safely convert a string value to float."""
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except:
        return None

def find_col(headers, *keywords):
    """Find a column index by keyword match."""
    for kw in keywords:
        for i, h in enumerate(headers):
            if kw.lower() in h.lower():
                return i
    return None

# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse_week(daily_reports):
    """
    Core weekly analysis.
    Returns a dict of all computed insights.
    """
    # Map: stock name → list of daily data dicts
    stock_days = defaultdict(list)
    all_dates = []

    for report in daily_reports:
        if not report:
            continue
        d = report["date"]
        all_dates.append(d)
        headers = report["headers"]

        # Column indices
        idx_name   = find_col(headers, "name")
        idx_cmp    = find_col(headers, "cmp", "current price")
        idx_ret1d  = find_col(headers, "1day", "return over 1day")
        idx_ret1w  = find_col(headers, "1week", "return over 1week")
        idx_ret1m  = find_col(headers, "1month", "return over 1month")
        idx_vol    = find_col(headers, "volume")
        idx_vol1w  = find_col(headers, "vol 1week", "volume 1week")
        idx_vol1m  = find_col(headers, "vol 1month", "volume 1month")
        idx_mktcap = find_col(headers, "mar cap", "market cap")
        idx_pe     = find_col(headers, "p/e")
        idx_roce   = find_col(headers, "roce")
        idx_profit = find_col(headers, "profit growth", "profit var")
        idx_qoqp   = find_col(headers, "qoq profit")
        idx_qoqs   = find_col(headers, "qoq sales")
        idx_ret3m  = find_col(headers, "3month")
        idx_ret6m  = find_col(headers, "6month")
        idx_ret1y  = find_col(headers, "1year")

        for stock in report["stocks"]:
            row = list(stock.values()) if isinstance(stock, dict) else stock
            if isinstance(stock, dict):
                # Use dict values directly
                name    = stock.get(headers[idx_name], "") if idx_name is not None else ""
                cmp     = safe_float(stock.get(headers[idx_cmp], "")) if idx_cmp is not None else None
                ret1d   = safe_float(stock.get(headers[idx_ret1d], "")) if idx_ret1d is not None else None
                ret1w   = safe_float(stock.get(headers[idx_ret1w], "")) if idx_ret1w is not None else None
                ret1m   = safe_float(stock.get(headers[idx_ret1m], "")) if idx_ret1m is not None else None
                vol     = safe_float(stock.get(headers[idx_vol], "")) if idx_vol is not None else None
                vol1w   = safe_float(stock.get(headers[idx_vol1w], "")) if idx_vol1w is not None else None
                vol1m   = safe_float(stock.get(headers[idx_vol1m], "")) if idx_vol1m is not None else None
                mktcap  = safe_float(stock.get(headers[idx_mktcap], "")) if idx_mktcap is not None else None
                pe      = safe_float(stock.get(headers[idx_pe], "")) if idx_pe is not None else None
                roce    = safe_float(stock.get(headers[idx_roce], "")) if idx_roce is not None else None
                profit  = safe_float(stock.get(headers[idx_profit], "")) if idx_profit is not None else None
                qoqp    = safe_float(stock.get(headers[idx_qoqp], "")) if idx_qoqp is not None else None
                qoqs    = safe_float(stock.get(headers[idx_qoqs], "")) if idx_qoqs is not None else None
                ret3m   = safe_float(stock.get(headers[idx_ret3m], "")) if idx_ret3m is not None else None
                ret6m   = safe_float(stock.get(headers[idx_ret6m], "")) if idx_ret6m is not None else None
                ret1y   = safe_float(stock.get(headers[idx_ret1y], "")) if idx_ret1y is not None else None
            else:
                name = ""
                cmp = ret1d = ret1w = ret1m = vol = vol1w = vol1m = None
                mktcap = pe = roce = profit = qoqp = qoqs = None
                ret3m = ret6m = ret1y = None

            if not name:
                continue

            stock_days[name].append({
                "date": d,
                "cmp": cmp,
                "ret1d": ret1d,
                "ret1w": ret1w,
                "ret1m": ret1m,
                "vol": vol,
                "vol1w": vol1w,
                "vol1m": vol1m,
                "mktcap": mktcap,
                "pe": pe,
                "roce": roce,
                "profit": profit,
                "qoqp": qoqp,
                "qoqs": qoqs,
                "ret3m": ret3m,
                "ret6m": ret6m,
                "ret1y": ret1y,
            })

    # ── Frequency ──
    frequency = {name: len(days) for name, days in stock_days.items()}
    appeared_all_5  = [n for n, c in frequency.items() if c == 5]
    appeared_4plus  = [n for n, c in frequency.items() if c >= 4]
    appeared_3plus  = [n for n, c in frequency.items() if c >= 3]

    # ── Per-stock aggregates ──
    stock_stats = {}
    for name, days in stock_days.items():
        ret1ds  = [d["ret1d"]  for d in days if d["ret1d"]  is not None]
        ret1ws  = [d["ret1w"]  for d in days if d["ret1w"]  is not None]
        vols    = [d["vol"]    for d in days if d["vol"]    is not None]
        vol1ws  = [d["vol1w"]  for d in days if d["vol1w"]  is not None]
        vol1ms  = [d["vol1m"]  for d in days if d["vol1m"]  is not None]
        cmps    = [d["cmp"]    for d in days if d["cmp"]    is not None]

        # Volume spike ratio: today's vol vs 1wk avg
        vol_spikes = []
        for d in days:
            if d["vol"] and d["vol1w"] and d["vol1w"] > 0:
                vol_spikes.append(d["vol"] / d["vol1w"])

        # Momentum consistency: how many days had positive 1d return
        pos_days = sum(1 for r in ret1ds if r > 0)

        latest = days[-1]
        stock_stats[name] = {
            "appearances":    len(days),
            "avg_ret1d":      round(statistics.mean(ret1ds), 2)  if ret1ds  else None,
            "max_ret1d":      round(max(ret1ds), 2)              if ret1ds  else None,
            "avg_ret1w":      round(statistics.mean(ret1ws), 2)  if ret1ws  else None,
            "avg_vol_spike":  round(statistics.mean(vol_spikes), 2) if vol_spikes else None,
            "max_vol_spike":  round(max(vol_spikes), 2)          if vol_spikes else None,
            "pos_days":       pos_days,
            "latest_cmp":     latest["cmp"],
            "latest_ret1d":   latest["ret1d"],
            "latest_ret1w":   latest["ret1w"],
            "latest_ret1m":   latest["ret1m"],
            "latest_ret3m":   latest["ret3m"],
            "latest_ret1y":   latest["ret1y"],
            "latest_mktcap":  latest["mktcap"],
            "latest_pe":      latest["pe"],
            "latest_roce":    latest["roce"],
            "latest_profit":  latest["profit"],
            "latest_qoqp":    latest["qoqp"],
            "latest_qoqs":    latest["qoqs"],
            "price_change_week": round(
                ((cmps[-1] - cmps[0]) / cmps[0]) * 100, 2
            ) if len(cmps) >= 2 and cmps[0] else None,
        }

    # ── Rankings ──
    def rank(key, reverse=True, min_appearances=1):
        return sorted(
            [(n, s) for n, s in stock_stats.items() if s.get(key) is not None and s["appearances"] >= min_appearances],
            key=lambda x: x[1][key],
            reverse=reverse
        )

    top_frequency       = sorted(frequency.items(), key=lambda x: x[1], reverse=True)[:10]
    top_avg_ret1d       = rank("avg_ret1d")[:10]
    top_vol_spike       = rank("avg_vol_spike")[:10]
    top_price_chg_week  = rank("price_change_week")[:10]
    top_consistency     = rank("pos_days")[:10]
    top_roce            = rank("latest_roce")[:10]
    top_profit          = rank("latest_profit")[:10]

    # ── Strong conviction picks: appeared 3+ days AND strong avg return ──
    conviction = [
        (n, s) for n, s in stock_stats.items()
        if s["appearances"] >= 3
        and s["avg_ret1d"] is not None and s["avg_ret1d"] > 0
        and s["avg_vol_spike"] is not None and s["avg_vol_spike"] >= 1.5
    ]
    conviction.sort(key=lambda x: (x[1]["appearances"], x[1]["avg_vol_spike"]), reverse=True)

    return {
        "dates": sorted(all_dates),
        "total_unique_stocks": len(stock_days),
        "frequency": frequency,
        "appeared_all_5": appeared_all_5,
        "appeared_4plus": appeared_4plus,
        "appeared_3plus": appeared_3plus,
        "stock_stats": stock_stats,
        "top_frequency": top_frequency,
        "top_avg_ret1d": top_avg_ret1d,
        "top_vol_spike": top_vol_spike,
        "top_price_chg_week": top_price_chg_week,
        "top_consistency": top_consistency,
        "top_roce": top_roce,
        "top_profit": top_profit,
        "conviction_picks": conviction,
    }

# ── HTML Report ───────────────────────────────────────────────────────────────

def pct(val, decimals=2):
    if val is None: return "—"
    color = "#1a9e6d" if val > 0 else "#d94b4b" if val < 0 else "#888"
    arrow = "▲" if val > 0 else "▼" if val < 0 else ""
    return f'<span style="color:{color};font-weight:600">{arrow}&nbsp;{val:.{decimals}f}%</span>'

def num(val, decimals=2):
    if val is None: return "—"
    return f"{val:.{decimals}f}"

def freq_bar(count, max_count=5):
    filled = "█" * count
    empty  = "░" * (max_count - count)
    return f'<span style="color:#4a6cf7;letter-spacing:2px">{filled}</span><span style="color:#e0e0e0;letter-spacing:2px">{empty}</span>'

def save_weekly_html(analysis, filepath, week_dates):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    stats = analysis["stock_stats"]
    week_label = f"{week_dates[0]} → {week_dates[-1]}" if week_dates else "This Week"

    # ── Section: Conviction Picks ──
    conviction_rows = ""
    for name, s in analysis["conviction_picks"][:10]:
        conviction_rows += f"""
        <tr>
          <td style="text-align:left;font-weight:600;color:#1a1a2e">{name}</td>
          <td>{freq_bar(s['appearances'])} {s['appearances']}/5</td>
          <td>{pct(s['avg_ret1d'])}</td>
          <td>{num(s['avg_vol_spike'])}×</td>
          <td>{pct(s['price_change_week'])}</td>
          <td>{pct(s['latest_ret1m'])}</td>
          <td>{pct(s['latest_roce'])}</td>
          <td>₹{num(s['latest_cmp'], 1) if s['latest_cmp'] else '—'}</td>
        </tr>"""

    # ── Section: Frequency Table ──
    freq_rows = ""
    for name, count in analysis["top_frequency"]:
        s = stats.get(name, {})
        freq_rows += f"""
        <tr>
          <td style="text-align:left;font-weight:500">{name}</td>
          <td>{freq_bar(count)} {count}/5</td>
          <td>{pct(s.get('avg_ret1d'))}</td>
          <td>{pct(s.get('price_change_week'))}</td>
          <td>{num(s.get('avg_vol_spike'))}×</td>
          <td>{s.get('pos_days','—')}/5</td>
        </tr>"""

    # ── Section: Top Volume Spikes ──
    vol_rows = ""
    for name, s in analysis["top_vol_spike"]:
        vol_rows += f"""
        <tr>
          <td style="text-align:left;font-weight:500">{name}</td>
          <td>{num(s['avg_vol_spike'])}×</td>
          <td>{num(s['max_vol_spike'])}×</td>
          <td>{s['appearances']}/5</td>
          <td>{pct(s.get('avg_ret1d'))}</td>
          <td>₹{num(s['latest_cmp'], 1) if s['latest_cmp'] else '—'}</td>
        </tr>"""

    # ── Section: Weekly Price Movers ──
    mover_rows = ""
    for name, s in analysis["top_price_chg_week"]:
        mover_rows += f"""
        <tr>
          <td style="text-align:left;font-weight:500">{name}</td>
          <td>{pct(s['price_change_week'])}</td>
          <td>{pct(s.get('latest_ret1m'))}</td>
          <td>{pct(s.get('latest_ret3m'))}</td>
          <td>{pct(s.get('latest_ret1y'))}</td>
          <td>{s['appearances']}/5</td>
        </tr>"""

    # ── Section: Fundamentals ──
    fund_rows = ""
    for name, s in analysis["top_roce"]:
        fund_rows += f"""
        <tr>
          <td style="text-align:left;font-weight:500">{name}</td>
          <td>{pct(s.get('latest_roce'))}</td>
          <td>{num(s.get('latest_pe'))}</td>
          <td>{pct(s.get('latest_profit'))}</td>
          <td>{pct(s.get('latest_qoqp'))}</td>
          <td>{pct(s.get('latest_qoqs'))}</td>
          <td>{s['appearances']}/5</td>
        </tr>"""

    # Badges for always-present stocks
    badge = lambda n: f'<span style="display:inline-block;background:#e8f0ff;color:#1a3a8f;border-radius:20px;padding:3px 12px;margin:3px;font-size:13px;font-weight:500">{n}</span>'
    all5_badges  = "".join(badge(n) for n in analysis["appeared_all_5"])  or "<em style='color:#aaa'>None this week</em>"
    plus4_badges = "".join(badge(n) for n in analysis["appeared_4plus"] if n not in analysis["appeared_all_5"]) or "<em style='color:#aaa'>None</em>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Analysis — {week_label}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;padding:20px;color:#1a1a1a}}
  .wrap{{max-width:1400px;margin:0 auto}}
  .top{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:#fff;padding:28px 32px;border-radius:12px 12px 0 0}}
  .top h1{{font-size:22px;font-weight:700}}
  .top p{{font-size:14px;opacity:.6;margin-top:6px}}
  .meta{{display:flex;gap:20px;padding:14px 32px;background:#f8f9ff;border:1px solid #e8eaf0;border-top:none;font-size:13px;color:#555;flex-wrap:wrap}}
  .card{{background:#fff;border-radius:0 0 12px 12px;border:1px solid #e8eaf0;border-top:none;margin-bottom:24px;overflow:hidden}}
  .section{{padding:24px 28px;border-bottom:1px solid #f0f0f0}}
  .section:last-child{{border-bottom:none}}
  .section-title{{font-size:15px;font-weight:700;color:#1a1a2e;margin-bottom:4px;display:flex;align-items:center;gap:8px}}
  .section-sub{{font-size:12px;color:#888;margin-bottom:16px}}
  .badge-wrap{{margin-top:10px;line-height:2.2}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
  thead th{{background:#1a1a2e;color:#c8d0ff;padding:10px 14px;text-align:right;font-weight:500;font-size:12px;white-space:nowrap}}
  thead th:first-child{{text-align:left}}
  tbody td{{padding:9px 14px;border-bottom:1px solid #f5f5f5;text-align:right;white-space:nowrap}}
  tbody td:first-child{{text-align:left}}
  tbody tr:hover td{{background:#f5f7ff}}
  tbody tr:nth-child(even){{background:#fafbff}}
  .conviction{{background:linear-gradient(135deg,#fef9e7,#fff8e1);border:1px solid #f0c040}}
  .foot{{padding:12px 28px;font-size:11px;color:#bbb;text-align:center;margin-top:8px}}
  .stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-top:12px}}
  .stat-box{{background:#f8f9ff;border-radius:8px;padding:14px 18px;border:1px solid #e8eaf0}}
  .stat-box .val{{font-size:22px;font-weight:700;color:#1a1a2e}}
  .stat-box .lbl{{font-size:11px;color:#888;margin-top:4px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>📊 Weekly Breakout Analysis</h1>
    <p>Screener Momentum Screen · {week_label} · {analysis['total_unique_stocks']} unique stocks across {len(analysis['dates'])} trading days</p>
  </div>
  <div class="meta">
    <span>📅 Days tracked: <strong>{", ".join(analysis['dates'])}</strong></span>
    <span>🔗 <a href="{SCREEN_URL}" target="_blank" style="color:#4a6cf7">screener.in/screens/3664072/screen1</a></span>
  </div>

  <div class="card">

    <!-- Summary Stats -->
    <div class="section">
      <div class="section-title">📈 Week at a Glance</div>
      <div class="section-sub">High-level numbers for the week</div>
      <div class="stat-grid">
        <div class="stat-box"><div class="val">{analysis['total_unique_stocks']}</div><div class="lbl">Unique stocks appeared</div></div>
        <div class="stat-box"><div class="val">{len(analysis['appeared_all_5'])}</div><div class="lbl">Appeared all 5 days</div></div>
        <div class="stat-box"><div class="val">{len(analysis['appeared_4plus'])}</div><div class="lbl">Appeared 4+ days</div></div>
        <div class="stat-box"><div class="val">{len(analysis['appeared_3plus'])}</div><div class="lbl">Appeared 3+ days</div></div>
        <div class="stat-box"><div class="val">{len(analysis['conviction_picks'])}</div><div class="lbl">Conviction picks</div></div>
      </div>
    </div>

    <!-- Stocks appeared all 5 days -->
    <div class="section">
      <div class="section-title">🔁 Appeared All 5 Days</div>
      <div class="section-sub">These stocks triggered the breakout screen every single day this week — highest conviction signals</div>
      <div class="badge-wrap">{all5_badges}</div>
    </div>

    <div class="section">
      <div class="section-title">4-Day Appearances</div>
      <div class="section-sub">Strong repeat breakouts — appeared 4 out of 5 days</div>
      <div class="badge-wrap">{plus4_badges}</div>
    </div>

    <!-- Conviction Picks -->
    <div class="section conviction">
      <div class="section-title">⭐ Conviction Picks of the Week</div>
      <div class="section-sub">Appeared 3+ days · Avg 1-day return > 0% · Avg volume spike ≥ 1.5× — the strongest signals of the week</div>
      <table>
        <thead><tr>
          <th>Stock</th><th>Frequency</th><th>Avg 1d Return</th><th>Avg Vol Spike</th>
          <th>Week Price Chg</th><th>1Mo Return</th><th>ROCE%</th><th>CMP</th>
        </tr></thead>
        <tbody>{conviction_rows}</tbody>
      </table>
    </div>

    <!-- Frequency Table -->
    <div class="section">
      <div class="section-title">📅 Appearance Frequency</div>
      <div class="section-sub">How many days each stock appeared in the breakout screen this week</div>
      <table>
        <thead><tr>
          <th>Stock</th><th>Days</th><th>Avg 1d Return</th><th>Week Chg</th><th>Avg Vol Spike</th><th>Positive Days</th>
        </tr></thead>
        <tbody>{freq_rows}</tbody>
      </table>
    </div>

    <!-- Volume Spikes -->
    <div class="section">
      <div class="section-title">🔊 Top Volume Spikes</div>
      <div class="section-sub">Stocks with the highest volume relative to their weekly average — unusual activity signals</div>
      <table>
        <thead><tr>
          <th>Stock</th><th>Avg Vol Spike</th><th>Max Vol Spike</th><th>Days</th><th>Avg 1d Return</th><th>CMP</th>
        </tr></thead>
        <tbody>{vol_rows}</tbody>
      </table>
    </div>

    <!-- Weekly Price Movers -->
    <div class="section">
      <div class="section-title">🚀 Top Weekly Price Movers</div>
      <div class="section-sub">Stocks with highest price gain from Monday open to Friday close this week</div>
      <table>
        <thead><tr>
          <th>Stock</th><th>Week Chg</th><th>1Mo Return</th><th>3Mo Return</th><th>1Yr Return</th><th>Days in Screen</th>
        </tr></thead>
        <tbody>{mover_rows}</tbody>
      </table>
    </div>

    <!-- Fundamentals -->
    <div class="section">
      <div class="section-title">🏦 Fundamentals of Breakout Stocks</div>
      <div class="section-sub">Top ROCE stocks among this week's breakouts — quality filter on momentum</div>
      <table>
        <thead><tr>
          <th>Stock</th><th>ROCE%</th><th>P/E</th><th>Profit Growth%</th><th>QoQ Profits%</th><th>QoQ Sales%</th><th>Days</th>
        </tr></thead>
        <tbody>{fund_rows}</tbody>
      </table>
    </div>

  </div>
  <div class="foot">Auto-generated via GitHub Actions · Screener.in · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div>
</body></html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ Weekly HTML → {filepath}")

def save_weekly_json(analysis, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # Make serialisable
    out = {k: v for k, v in analysis.items() if k != "stock_stats"}
    out["stock_stats"] = analysis["stock_stats"]
    out["conviction_picks"] = [(n, s) for n, s in analysis["conviction_picks"]]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"  ✅ Weekly JSON → {filepath}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today = date.today().isoformat()
    week_dates = get_this_week_dates()
    print(f"\n🔍 Weekly Analysis — week of {week_dates[0]} to {week_dates[-1]}")

    # Load all daily reports for the week
    daily_reports = []
    for d in week_dates:
        r = load_daily_report(d)
        if r:
            print(f"  📂 Loaded {d} — {r['total_stocks']} stocks")
            daily_reports.append(r)
        else:
            print(f"  ⚠️  No report found for {d} (market closed or not yet generated)")

    if not daily_reports:
        print("❌ No daily reports found for this week. Exiting.")
        return

    print(f"\n📊 Analysing {len(daily_reports)} day(s) of data...\n")
    analysis = analyse_week(daily_reports)

    # Save weekly report
    week_dir  = os.path.join(OUTPUT_DIR, "weekly")
    os.makedirs(week_dir, exist_ok=True)
    base = os.path.join(week_dir, f"week_{week_dates[0]}")

    save_weekly_html(analysis, base + "_analysis.html", week_dates)
    save_weekly_json(analysis, base + "_analysis.json")

    print(f"\n✅ Weekly analysis complete!")
    print(f"   📅 Days analysed: {len(daily_reports)}")
    print(f"   📊 Unique stocks: {analysis['total_unique_stocks']}")
    print(f"   🔁 Appeared all 5 days: {analysis['appeared_all_5']}")
    print(f"   ⭐ Conviction picks: {len(analysis['conviction_picks'])}")

if __name__ == "__main__":
    main()
