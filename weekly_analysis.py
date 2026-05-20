"""
Screener.in Weekly Analysis Report v2
- Institutional/big player footprint detection
- Volume analysis for stocks appearing 2+ days
- Technical indicators: RSI, MACD, EMA, Bollinger Bands
- "Comeback mode" detection
- Google News headlines per conviction stock
- StockTwits sentiment per stock
- Quarterly earnings catalyst detection
"""

import json
import os
import re
import time
import statistics
from datetime import datetime, date, timedelta
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError
import urllib.request

OUTPUT_DIR = "reports"
SCREEN_URL = "https://www.screener.in/screens/3664072/screen1/"

# ── Try importing optional libs (installed in GitHub Actions) ─────────────────
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("  ⚠️  yfinance not available — skipping technical analysis")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_float(val):
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except:
        return None

def find_col(headers, *keywords):
    for kw in keywords:
        for i, h in enumerate(headers):
            if kw.lower() in h.lower():
                return i
    return None

def get_this_week_dates():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)).isoformat() for i in range(5)]

def load_daily_report(report_date):
    path = os.path.join(OUTPUT_DIR, report_date, f"{report_date}_screener.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

def http_get(url, timeout=8):
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/html, */*",
        })
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return None

# ── Core Analysis ─────────────────────────────────────────────────────────────

def analyse_week(daily_reports):
    stock_days = defaultdict(list)
    all_dates  = []

    for report in daily_reports:
        if not report:
            continue
        d       = report["date"]
        all_dates.append(d)
        headers = report["headers"]

        idx = {
            "name":   find_col(headers, "name"),
            "cmp":    find_col(headers, "cmp", "current price"),
            "ret1d":  find_col(headers, "1day", "return over 1day"),
            "ret1w":  find_col(headers, "1week", "return over 1week"),
            "ret1m":  find_col(headers, "1month", "return over 1month"),
            "ret3m":  find_col(headers, "3month"),
            "ret6m":  find_col(headers, "6month"),
            "ret1y":  find_col(headers, "1year"),
            "vol":    find_col(headers, "volume"),
            "vol1w":  find_col(headers, "vol 1week", "volume 1week"),
            "vol1m":  find_col(headers, "vol 1month", "volume 1month"),
            "mktcap": find_col(headers, "mar cap", "market cap"),
            "pe":     find_col(headers, "p/e"),
            "roce":   find_col(headers, "roce"),
            "profit": find_col(headers, "profit growth", "profit var"),
            "qoqp":   find_col(headers, "qoq profit"),
            "qoqs":   find_col(headers, "qoq sales"),
        }

        for stock in report["stocks"]:
            if not isinstance(stock, dict):
                continue
            def g(key):
                i = idx.get(key)
                return safe_float(stock.get(headers[i], "")) if i is not None else None
            def gs(key):
                i = idx.get(key)
                return stock.get(headers[i], "") if i is not None else ""

            name = gs("name")
            if not name:
                continue

            stock_days[name].append({
                "date": d, "cmp": g("cmp"), "ret1d": g("ret1d"),
                "ret1w": g("ret1w"), "ret1m": g("ret1m"),
                "ret3m": g("ret3m"), "ret6m": g("ret6m"), "ret1y": g("ret1y"),
                "vol": g("vol"), "vol1w": g("vol1w"), "vol1m": g("vol1m"),
                "mktcap": g("mktcap"), "pe": g("pe"), "roce": g("roce"),
                "profit": g("profit"), "qoqp": g("qoqp"), "qoqs": g("qoqs"),
            })

    # ── Per-stock stats ──
    stock_stats = {}
    for name, days in stock_days.items():
        ret1ds     = [d["ret1d"]  for d in days if d["ret1d"]  is not None]
        vols       = [d["vol"]    for d in days if d["vol"]    is not None]
        vol1ws     = [d["vol1w"]  for d in days if d["vol1w"]  is not None]
        cmps       = [d["cmp"]    for d in days if d["cmp"]    is not None]

        vol_spikes = []
        for d in days:
            if d["vol"] and d["vol1w"] and d["vol1w"] > 0:
                vol_spikes.append(d["vol"] / d["vol1w"])

        # Big player signal score (0–100)
        # High score = unusual volume + multi-day appearance + positive return
        bp_score = 0
        if vol_spikes:
            avg_spike = statistics.mean(vol_spikes)
            bp_score += min(40, int(avg_spike * 10))   # volume component (max 40)
        bp_score += len(days) * 10                      # frequency component (max 50)
        pos_days = sum(1 for r in ret1ds if r > 0)
        bp_score += pos_days * 2                        # consistency (max 10)
        bp_score = min(100, bp_score)

        latest = days[-1]
        stock_stats[name] = {
            "appearances":   len(days),
            "avg_ret1d":     round(statistics.mean(ret1ds), 2) if ret1ds else None,
            "max_ret1d":     round(max(ret1ds), 2)             if ret1ds else None,
            "avg_vol_spike": round(statistics.mean(vol_spikes), 2) if vol_spikes else None,
            "max_vol_spike": round(max(vol_spikes), 2)         if vol_spikes else None,
            "pos_days":      pos_days,
            "bp_score":      bp_score,
            "price_change_week": round(
                ((cmps[-1] - cmps[0]) / cmps[0]) * 100, 2
            ) if len(cmps) >= 2 and cmps[0] else None,
            "latest_cmp":    latest["cmp"],
            "latest_ret1d":  latest["ret1d"],
            "latest_ret1w":  latest["ret1w"],
            "latest_ret1m":  latest["ret1m"],
            "latest_ret3m":  latest["ret3m"],
            "latest_ret1y":  latest["ret1y"],
            "latest_mktcap": latest["mktcap"],
            "latest_pe":     latest["pe"],
            "latest_roce":   latest["roce"],
            "latest_profit": latest["profit"],
            "latest_qoqp":   latest["qoqp"],
            "latest_qoqs":   latest["qoqs"],
            "daily_data":    days,
        }

    frequency   = {n: len(d) for n, d in stock_days.items()}
    appeared_all5 = [n for n, c in frequency.items() if c == 5]
    appeared_4p   = [n for n, c in frequency.items() if c >= 4]
    appeared_3p   = [n for n, c in frequency.items() if c >= 3]
    appeared_2p   = [n for n, c in frequency.items() if c >= 2]

    conviction = [
        (n, s) for n, s in stock_stats.items()
        if s["appearances"] >= 3
        and s.get("avg_ret1d") and s["avg_ret1d"] > 0
        and s.get("avg_vol_spike") and s["avg_vol_spike"] >= 1.5
    ]
    conviction.sort(key=lambda x: x[1]["bp_score"], reverse=True)

    # Earnings catalyst: strong QoQ profit AND appearing multiple days
    earnings_catalyst = [
        (n, s) for n, s in stock_stats.items()
        if s["appearances"] >= 2
        and s.get("latest_qoqp") and s["latest_qoqp"] > 20
    ]
    earnings_catalyst.sort(key=lambda x: x[1]["latest_qoqp"], reverse=True)

    return {
        "dates": sorted(all_dates),
        "total_unique": len(stock_days),
        "frequency": frequency,
        "appeared_all5": appeared_all5,
        "appeared_4p": appeared_4p,
        "appeared_3p": appeared_3p,
        "appeared_2p": appeared_2p,
        "stock_stats": stock_stats,
        "conviction": conviction,
        "earnings_catalyst": earnings_catalyst,
        "top_bp_score": sorted(stock_stats.items(), key=lambda x: x[1]["bp_score"], reverse=True)[:15],
        "top_vol_spike": sorted(
            [(n, s) for n, s in stock_stats.items() if s.get("avg_vol_spike")],
            key=lambda x: x[1]["avg_vol_spike"], reverse=True
        )[:10],
        "top_weekly_movers": sorted(
            [(n, s) for n, s in stock_stats.items() if s.get("price_change_week") is not None],
            key=lambda x: x[1]["price_change_week"], reverse=True
        )[:10],
    }

# ── Technical Analysis ────────────────────────────────────────────────────────

def compute_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = statistics.mean(gains[-period:])
    avg_loss = statistics.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def compute_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = statistics.mean(prices[:period])
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 2)

def compute_macd(prices):
    ema12 = compute_ema(prices, 12)
    ema26 = compute_ema(prices, 26)
    if ema12 is None or ema26 is None:
        return None, None
    macd = round(ema12 - ema26, 2)
    return macd, round(ema12, 2)

def compute_bollinger(prices, period=20):
    if len(prices) < period:
        return None, None, None
    recent = prices[-period:]
    mid    = statistics.mean(recent)
    std    = statistics.stdev(recent)
    return round(mid - 2*std, 2), round(mid, 2), round(mid + 2*std, 2)

def get_technical_analysis(name, symbol):
    """Fetch 6 months of price data and compute technical indicators."""
    if not HAS_YFINANCE:
        return None
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist   = ticker.history(period="6mo")
        if hist.empty or len(hist) < 30:
            return None

        closes = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        current = closes[-1]

        rsi     = compute_rsi(closes)
        ema20   = compute_ema(closes, 20)
        ema50   = compute_ema(closes, 50)
        ema200  = compute_ema(closes, 200)
        macd, _ = compute_macd(closes)
        bb_low, bb_mid, bb_high = compute_bollinger(closes)

        # 52-week high/low
        high52 = max(closes[-252:] if len(closes) >= 252 else closes)
        low52  = min(closes[-252:] if len(closes) >= 252 else closes)
        pct_from_high = round(((current - high52) / high52) * 100, 1)
        pct_from_low  = round(((current - low52)  / low52)  * 100, 1)

        # Volume trend: recent 5d avg vs 20d avg
        vol_5d  = statistics.mean(volumes[-5:])  if len(volumes) >= 5  else None
        vol_20d = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else None
        vol_ratio = round(vol_5d / vol_20d, 2) if vol_5d and vol_20d and vol_20d > 0 else None

        # Comeback mode signals
        comeback_signals = []
        if rsi and rsi < 40:
            comeback_signals.append(f"RSI oversold ({rsi})")
        if ema20 and ema50 and ema20 > ema50 and closes[-2] < closes[-1]:
            comeback_signals.append("EMA20 crossed above EMA50 (golden cross forming)")
        if bb_low and current < bb_mid and current > bb_low:
            comeback_signals.append("Price in lower Bollinger band — potential reversal zone")
        if pct_from_high < -30 and vol_ratio and vol_ratio > 1.5:
            comeback_signals.append(f"Down {abs(pct_from_high)}% from 52w high with volume surge ({vol_ratio}×)")
        if ema200 and current > ema200 and ema20 and current > ema20:
            comeback_signals.append("Price above EMA200 — long-term uptrend intact")
        if macd and macd > 0:
            comeback_signals.append("MACD positive — bullish momentum")

        # Overall signal
        bullish_count = len(comeback_signals)
        if bullish_count >= 4:
            signal = "🟢 STRONG COMEBACK"
        elif bullish_count >= 2:
            signal = "🟡 POSSIBLE COMEBACK"
        elif rsi and rsi > 70:
            signal = "🔴 OVERBOUGHT"
        else:
            signal = "⚪ NEUTRAL"

        return {
            "symbol":          symbol,
            "current":         round(current, 2),
            "rsi":             rsi,
            "ema20":           ema20,
            "ema50":           ema50,
            "ema200":          ema200,
            "macd":            macd,
            "bb_low":          bb_low,
            "bb_mid":          bb_mid,
            "bb_high":         bb_high,
            "high52":          round(high52, 2),
            "low52":           round(low52, 2),
            "pct_from_high":   pct_from_high,
            "pct_from_low":    pct_from_low,
            "vol_ratio_5_20":  vol_ratio,
            "comeback_signals": comeback_signals,
            "signal":          signal,
        }
    except Exception as e:
        print(f"    ⚠️  Technical analysis failed for {symbol}: {e}")
        return None

# ── News ──────────────────────────────────────────────────────────────────────

def get_google_news(stock_name, max_items=4):
    """Fetch headlines from Google News RSS for a stock."""
    query = quote(f"{stock_name} NSE stock")
    url   = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    html  = http_get(url)
    if not html:
        return []
    items = []
    for match in re.finditer(r"<title><!\[CDATA\[(.*?)\]\]></title>.*?<pubDate>(.*?)</pubDate>",
                             html, re.DOTALL):
        title = match.group(1).strip()
        pub   = match.group(2).strip()[:16]
        if stock_name.lower().split()[0] in title.lower() or "nse" in title.lower():
            items.append({"title": title, "date": pub})
        if len(items) >= max_items:
            break
    # Fallback: grab first N titles
    if not items:
        for match in re.finditer(r"<title><!\[CDATA\[(.*?)\]\]></title>", html):
            t = match.group(1).strip()
            if t and "Google News" not in t:
                items.append({"title": t, "date": ""})
            if len(items) >= max_items:
                break
    return items[:max_items]

# ── StockTwits ────────────────────────────────────────────────────────────────

def get_stocktwits(symbol, max_items=4):
    """Fetch recent messages from StockTwits for an NSE symbol."""
    url  = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.NS.json"
    data = http_get(url)
    if not data:
        return [], None
    try:
        j        = json.loads(data)
        messages = j.get("messages", [])
        items    = []
        bulls, bears = 0, 0
        for m in messages[:max_items*2]:
            body      = m.get("body", "").replace("\n", " ")[:120]
            sentiment = m.get("entities", {}).get("sentiment", {})
            sent_val  = sentiment.get("basic", "") if sentiment else ""
            if sent_val == "Bullish":
                bulls += 1
            elif sent_val == "Bearish":
                bears += 1
            items.append({"text": body, "sentiment": sent_val, "date": m.get("created_at","")[:10]})
        total = bulls + bears
        sent_summary = None
        if total > 0:
            sent_summary = f"🐂 {bulls} Bullish / 🐻 {bears} Bearish ({round(bulls/total*100)}% bull)"
        return items[:max_items], sent_summary
    except:
        return [], None

# ── NSE Symbol Map ────────────────────────────────────────────────────────────

# Partial map — will do best-effort match for unknown names
NSE_SYMBOL_MAP = {
    "infosys": "INFY", "tcs": "TCS", "hdfc bank": "HDFCBANK",
    "reliance": "RELIANCE", "wipro": "WIPRO", "hcl tech": "HCLTECH",
    "icici bank": "ICICIBANK", "axis bank": "AXISBANK", "sbi": "SBIN",
    "bajaj finance": "BAJFINANCE", "kotak": "KOTAKBANK",
    "nazara": "NAZARA", "nazara technologies": "NAZARA",
    "chambal fert": "CHAMBLFERT", "chambal fertilisers": "CHAMBLFERT",
    "crompton": "CROMPTON", "pricol": "PRICOLLTD",
    "td power": "TDPOWERSYS", "kirloskar oil": "KIRLOSENG",
    "mayur uniquoters": "MAYURUNIQ", "pearl global": "PGIL",
    "chalet hotels": "CHALET", "latent view": "LATENTVIEW",
    "triveni turbine": "TRIVENI", "hexaware": "HEXAWARE",
    "balaji amines": "BALAMINES", "carborundum": "CARBORUNIV",
    "medplus": "MEDPLUS", "senores": "SENORES",
    "atul auto": "ATULAUTO", "stove kraft": "STOVEKRAFT",
    "sakar healthcare": "SAKAR", "grm overseas": "GRMOVER",
    "blue cloud": "BLUECLOUDSOF", "sparc": "SPARC",
    "supriya lifesci": "SUPRIYA", "tbo tek": "TBOTEK",
    "ajax engineering": "AJAX", "coforge": "COFORGE",
    "tata technolog": "TATATECH", "seamec": "SEAMEC",
    "hind rectifiers": "HIRECT", "wheels india": "WHEELS",
    "nephrocare": "NEPHROPLUS", "dynacons": "DYNACONS",
    "euro pratik": "EUROPRATIK", "international ge": "INTLGERMN",
    "sumitomo chemi": "SUMICHEM", "saksoft": "SAKSOFT",
    "eppack": "EPACKPEB", "garuda": "GARUDA",
    "shadowfax": "SHADOWFAX",
}

def name_to_symbol(name):
    name_lower = name.lower()
    for k, v in NSE_SYMBOL_MAP.items():
        if k in name_lower:
            return v
    # Fallback: uppercase first word
    return name.upper().split()[0]

# ── HTML Generation ───────────────────────────────────────────────────────────

def pct(val, d=2):
    if val is None: return "—"
    c = "#1a9e6d" if val > 0 else "#d94b4b" if val < 0 else "#888"
    a = "▲" if val > 0 else "▼" if val < 0 else ""
    return f'<span style="color:{c};font-weight:600">{a}&nbsp;{val:.{d}f}%</span>'

def num(val, d=2):
    if val is None: return "—"
    return f"{val:,.{d}f}"

def freq_bar(count, max_count=5):
    return (f'<span style="color:#4a6cf7;letter-spacing:2px">{"█"*count}</span>'
            f'<span style="color:#ddd;letter-spacing:2px">{"░"*(max_count-count)}</span>'
            f' <strong>{count}/5</strong>')

def bp_bar(score):
    filled = int(score / 10)
    color  = "#1a9e6d" if score >= 70 else "#f0a500" if score >= 40 else "#d94b4b"
    return f'<span style="color:{color};font-weight:700">{score}</span><span style="color:#ddd;font-size:11px"> /100</span>'

def news_html(items):
    if not items:
        return '<em style="color:#aaa;font-size:12px">No news found</em>'
    rows = "".join(
        f'<div style="padding:6px 0;border-bottom:1px solid #f5f5f5;font-size:12px">'
        f'<span style="color:#555">{i["date"]}</span> — {i["title"]}</div>'
        for i in items
    )
    return rows

def twits_html(items, sentiment):
    if not items:
        return '<em style="color:#aaa;font-size:12px">No StockTwits data</em>'
    sent_bar = f'<div style="margin-bottom:8px;font-size:12px;font-weight:600">{sentiment}</div>' if sentiment else ""
    rows = "".join(
        f'<div style="padding:5px 0;border-bottom:1px solid #f5f5f5;font-size:12px">'
        f'<span style="color:{"#1a9e6d" if i["sentiment"]=="Bullish" else "#d94b4b" if i["sentiment"]=="Bearish" else "#888"}">'
        f'{"🐂" if i["sentiment"]=="Bullish" else "🐻" if i["sentiment"]=="Bearish" else "💬"}</span> '
        f'{i["text"]}</div>'
        for i in items
    )
    return sent_bar + rows

def tech_html(ta):
    if not ta:
        return '<em style="color:#aaa;font-size:12px">Technical data unavailable</em>'
    signals_html = "".join(
        f'<div style="padding:3px 0;font-size:12px;color:#2d5a27">✓ {s}</div>'
        for s in ta["comeback_signals"]
    ) or '<div style="font-size:12px;color:#aaa">No strong signals detected</div>'

    rsi_color = "#d94b4b" if ta["rsi"] and ta["rsi"] > 70 else "#1a9e6d" if ta["rsi"] and ta["rsi"] < 40 else "#555"

    return f"""
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;font-size:12px">
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888">RSI (14)</div>
        <div style="font-weight:700;color:{rsi_color}">{ta['rsi'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888">MACD</div>
        <div style="font-weight:700;color:{'#1a9e6d' if ta['macd'] and ta['macd']>0 else '#d94b4b'}">{ta['macd'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888">Vol Ratio 5d/20d</div>
        <div style="font-weight:700">{ta['vol_ratio_5_20'] or '—'}×</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888">EMA 20/50</div>
        <div style="font-weight:600">{ta['ema20'] or '—'} / {ta['ema50'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888">52w High/Low</div>
        <div style="font-weight:600">{ta['high52']} / {ta['low52']}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888">From 52w High</div>
        <div style="font-weight:700;color:{'#d94b4b' if ta['pct_from_high']<-20 else '#555'}">{ta['pct_from_high']}%</div></div>
    </div>
    <div style="background:#f0f9f0;border-radius:6px;padding:10px;margin-bottom:8px">
      <div style="font-size:12px;font-weight:700;margin-bottom:6px">{ta['signal']}</div>
      {signals_html}
    </div>"""

def save_weekly_html(analysis, tech_data, news_data, twit_data, filepath, week_dates):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    week_label = f"{week_dates[0]} → {week_dates[-1]}" if week_dates else "This Week"
    stats = analysis["stock_stats"]

    # ── Conviction stock cards ──
    conviction_cards = ""
    for name, s in analysis["conviction"][:8]:
        symbol  = name_to_symbol(name)
        ta      = tech_data.get(name)
        nws     = news_data.get(name, [])
        tw, sent = twit_data.get(name, ([], None))

        conviction_cards += f"""
        <div style="background:#fff;border:1px solid #e8eaf0;border-radius:10px;margin-bottom:20px;overflow:hidden">
          <div style="background:linear-gradient(90deg,#0f0c29,#302b63);color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center">
            <div>
              <span style="font-size:16px;font-weight:700">{name}</span>
              <span style="font-size:12px;opacity:.6;margin-left:10px">{symbol}.NS</span>
            </div>
            <div style="text-align:right">
              <div style="font-size:18px;font-weight:700">₹{num(s['latest_cmp'],1)}</div>
              <div style="font-size:12px;opacity:.7">{freq_bar(s['appearances'])} &nbsp;|&nbsp; BP Score: {bp_bar(s['bp_score'])}</div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-bottom:1px solid #f0f0f0">
            <div style="padding:10px 16px;border-right:1px solid #f0f0f0"><div style="font-size:11px;color:#888">Avg 1d Return</div><div style="font-weight:600">{pct(s['avg_ret1d'])}</div></div>
            <div style="padding:10px 16px;border-right:1px solid #f0f0f0"><div style="font-size:11px;color:#888">Week Change</div><div style="font-weight:600">{pct(s['price_change_week'])}</div></div>
            <div style="padding:10px 16px;border-right:1px solid #f0f0f0"><div style="font-size:11px;color:#888">Avg Vol Spike</div><div style="font-weight:600">{num(s['avg_vol_spike'],1)}×</div></div>
            <div style="padding:10px 16px"><div style="font-size:11px;color:#888">ROCE%</div><div style="font-weight:600">{pct(s['latest_roce'])}</div></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0">
            <div style="padding:14px 16px;border-right:1px solid #f0f0f0">
              <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:#1a1a2e">📊 Technical Analysis</div>
              {tech_html(ta)}
            </div>
            <div style="padding:14px 16px;border-right:1px solid #f0f0f0">
              <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:#1a1a2e">📰 Latest News</div>
              {news_html(nws)}
            </div>
            <div style="padding:14px 16px">
              <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:#1a1a2e">💬 StockTwits</div>
              {twits_html(tw, sent)}
            </div>
          </div>
        </div>"""

    # ── Big Player Radar table ──
    bp_rows = ""
    for name, s in analysis["top_bp_score"]:
        vol_trend = ""
        days = s.get("daily_data", [])
        if len(days) >= 2:
            vols = [d["vol"] for d in days if d["vol"]]
            if len(vols) >= 2:
                trend = "📈" if vols[-1] > vols[0] else "📉"
                vol_trend = trend
        bp_rows += f"""<tr>
          <td style="text-align:left;font-weight:600">{name}</td>
          <td>{freq_bar(s['appearances'])}</td>
          <td>{bp_bar(s['bp_score'])}</td>
          <td>{num(s.get('avg_vol_spike'),1)}× {vol_trend}</td>
          <td>{pct(s.get('avg_ret1d'))}</td>
          <td>{pct(s.get('price_change_week'))}</td>
          <td>{pct(s.get('latest_roce'))}</td>
          <td>{pct(s.get('latest_qoqp'))}</td>
        </tr>"""

    # ── Volume analysis: 2+ appearances ──
    vol_rows = ""
    vol_stocks = [(n, s) for n, s in stats.items() if s["appearances"] >= 2 and s.get("avg_vol_spike")]
    vol_stocks.sort(key=lambda x: x[1]["avg_vol_spike"], reverse=True)
    for name, s in vol_stocks[:15]:
        days = s.get("daily_data", [])
        daily_vols = " → ".join(
            f'{d["vol"]/1e5:.1f}L' if d.get("vol") else "—"
            for d in days
        )
        vol_rows += f"""<tr>
          <td style="text-align:left;font-weight:500">{name}</td>
          <td>{s['appearances']}/5</td>
          <td style="font-weight:700;color:#302b63">{num(s['avg_vol_spike'],1)}×</td>
          <td>{num(s.get('max_vol_spike'),1)}×</td>
          <td style="font-size:11px;color:#666">{daily_vols}</td>
          <td>{pct(s.get('avg_ret1d'))}</td>
          <td>{pct(s.get('latest_qoqp'))}</td>
        </tr>"""

    # ── Earnings Catalyst ──
    earn_rows = ""
    for name, s in analysis["earnings_catalyst"][:10]:
        earn_rows += f"""<tr>
          <td style="text-align:left;font-weight:500">{name}</td>
          <td>{pct(s.get('latest_qoqp'))}</td>
          <td>{pct(s.get('latest_qoqs'))}</td>
          <td>{pct(s.get('latest_profit'))}</td>
          <td>{s['appearances']}/5</td>
          <td>{num(s.get('avg_vol_spike'),1)}×</td>
          <td>₹{num(s.get('latest_cmp'),1)}</td>
        </tr>"""

    # Badges
    badge = lambda n, color="#1a3a8f", bg="#e8f0ff": f'<span style="display:inline-block;background:{bg};color:{color};border-radius:20px;padding:3px 12px;margin:3px;font-size:13px;font-weight:500">{n}</span>'
    all5_html = "".join(badge(n) for n in analysis["appeared_all5"]) or "<em style='color:#aaa'>None this week</em>"
    catalyst_badges = "".join(badge(n, "#3d1a00", "#fff3e0") for n, _ in analysis["earnings_catalyst"][:8]) or "<em style='color:#aaa'>None</em>"

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
  .meta a{{color:#4a6cf7}}
  .section{{background:#fff;border:1px solid #e8eaf0;border-radius:10px;margin:16px 0;overflow:hidden}}
  .sec-head{{padding:16px 24px;border-bottom:1px solid #f0f0f0;background:#fafbff}}
  .sec-head h2{{font-size:15px;font-weight:700;color:#1a1a2e}}
  .sec-head p{{font-size:12px;color:#888;margin-top:3px}}
  .sec-body{{padding:20px 24px}}
  .stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}}
  .stat-box{{background:#f8f9ff;border-radius:8px;padding:14px 18px;border:1px solid #e8eaf0}}
  .stat-box .val{{font-size:24px;font-weight:700;color:#1a1a2e}}
  .stat-box .lbl{{font-size:11px;color:#888;margin-top:4px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  thead th{{background:#1a1a2e;color:#c8d0ff;padding:10px 14px;text-align:right;font-weight:500;font-size:12px;white-space:nowrap}}
  thead th:first-child{{text-align:left}}
  tbody td{{padding:9px 14px;border-bottom:1px solid #f5f5f5;text-align:right;white-space:nowrap}}
  tbody td:first-child{{text-align:left}}
  tbody tr:hover td{{background:#f5f7ff}}
  .foot{{padding:12px;font-size:11px;color:#bbb;text-align:center;margin-top:8px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>📊 Weekly Breakout & Big Player Analysis</h1>
    <p>Screener Momentum Screen · {week_label} · {analysis['total_unique']} unique stocks · {len(analysis['dates'])} trading days</p>
  </div>
  <div class="meta">
    <span>📅 <strong>{", ".join(analysis['dates'])}</strong></span>
    <span>🔗 <a href="{SCREEN_URL}">screener.in/screens/3664072/screen1</a></span>
  </div>

  <!-- Glance -->
  <div class="section">
    <div class="sec-head"><h2>📈 Week at a Glance</h2></div>
    <div class="sec-body">
      <div class="stat-grid">
        <div class="stat-box"><div class="val">{analysis['total_unique']}</div><div class="lbl">Unique stocks</div></div>
        <div class="stat-box"><div class="val">{len(analysis['appeared_all5'])}</div><div class="lbl">Appeared all 5 days</div></div>
        <div class="stat-box"><div class="val">{len(analysis['appeared_2p'])}</div><div class="lbl">Appeared 2+ days</div></div>
        <div class="stat-box"><div class="val">{len(analysis['conviction'])}</div><div class="lbl">Conviction picks</div></div>
        <div class="stat-box"><div class="val">{len(analysis['earnings_catalyst'])}</div><div class="lbl">Earnings catalysts</div></div>
      </div>
    </div>
  </div>

  <!-- All 5 days -->
  <div class="section">
    <div class="sec-head"><h2>🔁 Appeared All 5 Days — Highest Conviction</h2><p>These stocks triggered the breakout screen every single trading day this week</p></div>
    <div class="sec-body">{all5_html}</div>
  </div>

  <!-- Earnings Catalyst -->
  <div class="section">
    <div class="sec-head"><h2>💥 Earnings Catalysts — Brilliant Quarter + Volume</h2><p>Stocks with strong QoQ profit growth appearing multiple days — riding earnings momentum</p></div>
    <div class="sec-body" style="margin-bottom:16px">{catalyst_badges}</div>
    <div style="padding:0 24px 20px">
    <table>
      <thead><tr><th>Stock</th><th>QoQ Profit%</th><th>QoQ Sales%</th><th>Profit Growth%</th><th>Days in Screen</th><th>Avg Vol Spike</th><th>CMP</th></tr></thead>
      <tbody>{earn_rows}</tbody>
    </table></div>
  </div>

  <!-- Big Player Radar -->
  <div class="section">
    <div class="sec-head"><h2>🎯 Big Player Radar — Institutional Footprint Score</h2><p>Unusual volume + multi-day appearance = potential institutional accumulation. Score 0–100.</p></div>
    <div style="padding:0 24px 20px">
    <table>
      <thead><tr><th>Stock</th><th>Frequency</th><th>BP Score</th><th>Avg Vol Spike</th><th>Avg 1d Return</th><th>Week Change</th><th>ROCE%</th><th>QoQ Profits%</th></tr></thead>
      <tbody>{bp_rows}</tbody>
    </table></div>
  </div>

  <!-- Volume Analysis 2+ days -->
  <div class="section">
    <div class="sec-head"><h2>🔊 Volume Analysis — Stocks Appearing 2+ Days</h2><p>Daily volume progression — looking for sustained accumulation vs one-day spikes</p></div>
    <div style="padding:0 24px 20px">
    <table>
      <thead><tr><th>Stock</th><th>Days</th><th>Avg Spike</th><th>Max Spike</th><th>Daily Vol Progression</th><th>Avg 1d Ret</th><th>QoQ Profits%</th></tr></thead>
      <tbody>{vol_rows}</tbody>
    </table></div>
  </div>

  <!-- Conviction Stock Deep Dives -->
  <div class="section">
    <div class="sec-head"><h2>⭐ Conviction Stock Deep Dives</h2><p>Technical analysis + news + social sentiment for top conviction picks</p></div>
    <div class="sec-body">{conviction_cards}</div>
  </div>

  <div class="foot">Auto-generated via GitHub Actions · Screener.in · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div>
</body></html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ Weekly HTML → {filepath}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today      = date.today().isoformat()
    week_dates = get_this_week_dates()
    print(f"\n🔍 Weekly Analysis v2 — {week_dates[0]} to {week_dates[-1]}")

    daily_reports = []
    for d in week_dates:
        r = load_daily_report(d)
        if r:
            print(f"  📂 Loaded {d} — {r['total_stocks']} stocks")
            daily_reports.append(r)
        else:
            print(f"  ⚠️  No report for {d}")

    if not daily_reports:
        print("❌ No daily reports found. Exiting.")
        return

    analysis = analyse_week(daily_reports)
    print(f"\n  📊 {analysis['total_unique']} unique stocks")
    print(f"  🔁 All-5-day: {analysis['appeared_all5']}")
    print(f"  ⭐ Conviction: {len(analysis['conviction'])}")
    print(f"  💥 Earnings catalysts: {len(analysis['earnings_catalyst'])}")

    # ── Fetch technical, news, twits for conviction + 2+ day stocks ──
    targets = list({n for n, _ in analysis["conviction"]} |
                   {n for n in analysis["appeared_2p"]})[:20]  # cap at 20 to avoid rate limits

    tech_data = {}
    news_data = {}
    twit_data = {}

    if HAS_YFINANCE:
        print(f"\n  📡 Fetching technical data for {len(targets)} stocks...")
        for name in targets:
            symbol = name_to_symbol(name)
            print(f"    → {name} ({symbol})")
            ta = get_technical_analysis(name, symbol)
            tech_data[name] = ta
            time.sleep(0.3)

    print(f"\n  📰 Fetching news for {len(targets)} stocks...")
    for name in targets:
        news_data[name] = get_google_news(name)
        time.sleep(0.5)

    print(f"\n  💬 Fetching StockTwits for {len(targets)} stocks...")
    for name in targets:
        symbol = name_to_symbol(name)
        twit_data[name] = get_stocktwits(symbol)
        time.sleep(0.3)

    # ── Save ──
    week_dir = os.path.join(OUTPUT_DIR, "weekly")
    os.makedirs(week_dir, exist_ok=True)
    base = os.path.join(week_dir, f"week_{week_dates[0]}")

    save_weekly_html(analysis, tech_data, news_data, twit_data, base + "_analysis.html", week_dates)

    # Save JSON summary
    with open(base + "_analysis.json", "w") as f:
        out = {k: v for k, v in analysis.items() if k not in ("stock_stats",)}
        out["stock_stats_summary"] = {
            n: {k: v for k, v in s.items() if k != "daily_data"}
            for n, s in analysis["stock_stats"].items()
        }
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"  ✅ JSON → {base}_analysis.json")

    print(f"\n✅ Weekly analysis complete!")

if __name__ == "__main__":
    main()
