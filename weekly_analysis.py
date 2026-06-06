"""
Screener.in Weekly Analysis v4
Key fixes:
- Auto NSE symbol lookup via yfinance search (no hardcoded map)
- Vol week vs vol month shown as visual bar chart per stock
- Deep dives for ALL 2+ day stocks
- Robust fallback if yfinance fails for a ticker
"""

import json, os, re, time, statistics, glob
from datetime import datetime, date, timedelta
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import quote

OUTPUT_DIR = "reports"
SCREEN_URL = "https://www.screener.in/screens/3664072/screen1/"

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    print("  ⚠️  pip install yfinance")

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_float(val):
    try: return float(str(val).replace(",","").replace("%","").strip())
    except: return None

def find_col(headers, *kws):
    for kw in kws:
        for i,h in enumerate(headers):
            if kw.lower() in h.lower(): return i
    return None

def get_week_dates():
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)).isoformat() for i in range(5)]

def load_report(d):
    p = os.path.join(OUTPUT_DIR, d, f"{d}_screener.json")
    if not os.path.exists(p): return None
    with open(p) as f: return json.load(f)

def http_get(url, timeout=8):
    try:
        req = Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except: return None

# ── NSE symbol lookup ─────────────────────────────────────────────────────────

_sym_cache = {}

def get_nse_symbol(name):
    """Look up NSE symbol via yfinance search — works on GitHub Actions."""
    if name in _sym_cache:
        return _sym_cache[name]
    if not HAS_YF:
        return None
    # Try direct common variations
    candidates = []
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', name).strip()
    words = clean.upper().split()

    # Build candidate symbols
    candidates.append("".join(words[:2])[:12] + ".NS")
    candidates.append(words[0][:12] + ".NS")
    if len(words) >= 2:
        candidates.append((words[0] + words[1])[:12] + ".NS")

    # Known corrections
    CORRECTIONS = {
        "bliss gvs": "BLISSGVS.NS",
        "modison": "MODISON.NS",
        "guj themis": "GUJTHEM.NS",
        "jk tyre": "JKTYRE.NS",
        "rossell": "ROSSELLTECH.NS",
        "ksh intern": "KSHITIJPOL.NS",
        "vidya wires": "VIDYAWIRES.NS",
        "adani total": "ATGL.NS",
        "exide": "EXIDEIND.NS",
        "psp project": "PSPPROJECT.NS",
        "mercury ev": "MERCURYEV.NS",
        "timex": "TIMEXG.NS",
        "tpl plast": "TPLPLAST.NS",
        "crizac": "CRIZAC.NS",
        "emmvee": "EMMVEE.NS",
        "aditya infotech": "ADITYAINFOTECH.NS",
        "astra micro": "ASTRAMICRO.NS",
        "vintage coffee": "VINTAGEFNB.NS",
        "vikran": "VIKRANENG.NS",
        "skipper": "SKIPPER.NS",
        "ifb ind": "IFBIND.NS",
        "ge vernova": "GETVERNOVA.NS",
        "oracle fin": "OFSS.NS",
        "natl alum": "NATIONALUM.NS",
        "national alum": "NATIONALUM.NS",
        "cummins": "CUMMINSIND.NS",
        "indrapr": "INDRAPRASTHA.NS",
        "suzlon": "SUZLON.NS",
        "apar ind": "APARINDS.NS",
        "hitachi energy": "POWERINDIA.NS",
        "monarch networth": "MONARCH.NS",
        "inox wind": "INOXWIND.NS",
        "waaree": "WAAREEENER.NS",
        "premier energies": "PREMIERENE.NS",
        "bharat heavy": "BHEL.NS",
        "bhel": "BHEL.NS",
    }
    nl = name.lower()
    for k, v in CORRECTIONS.items():
        if k in nl:
            _sym_cache[name] = v
            return v

    # Try each candidate with yfinance
    for sym in candidates:
        try:
            t = yf.Ticker(sym)
            h = t.history(period="5d")
            if not h.empty and len(h) >= 1:
                _sym_cache[name] = sym
                return sym
        except: pass

    _sym_cache[name] = None
    return None

# ── Volume data from yfinance ─────────────────────────────────────────────────

def get_vol_data(name):
    """Get volume week (5d avg), volume month (22d avg), daily vols for bar chart."""
    sym = get_nse_symbol(name)
    if not sym or not HAS_YF:
        return None
    try:
        t    = yf.Ticker(sym)
        hist = t.history(period="3mo")
        if hist.empty or len(hist) < 5:
            return None
        vols   = [v for v in hist["Volume"].tolist() if v > 0]
        closes = hist["Close"].tolist()
        dates  = [str(d.date()) for d in hist.index.tolist()]
        if len(vols) < 5:
            return None

        vol5d  = sum(vols[-5:])  / 5
        vol22d = sum(vols[-22:]) / 22 if len(vols) >= 22 else sum(vols) / len(vols)
        vol63d = sum(vols[-63:]) / 63 if len(vols) >= 63 else vol22d  # ~3 months
        ratio_wk_mo = round(vol5d / vol22d, 2) if vol22d > 0 else None

        # Daily vols for last 10 days (for sparkline)
        last10_vols  = vols[-10:]
        last10_dates = dates[-10:]
        last10_cls   = closes[-10:]

        return {
            "sym":         sym,
            "vol5d":       int(vol5d),
            "vol22d":      int(vol22d),
            "vol63d":      int(vol63d),
            "ratio_wk_mo": ratio_wk_mo,
            "last10_vols": last10_vols,
            "last10_dates": last10_dates,
            "last10_cls":  last10_cls,
            "all_vols":    vols,
            "all_closes":  closes,
            "all_dates":   dates,
        }
    except Exception as e:
        print(f"    ⚠️  vol failed {name}: {e}")
        return None

# ── Technical indicators ──────────────────────────────────────────────────────

def ema(prices, p):
    if len(prices) < p: return None
    k = 2/(p+1); e = statistics.mean(prices[:p])
    for x in prices[p:]: e = x*k + e*(1-k)
    return round(e, 2)

def rsi(prices, p=14):
    if len(prices) < p+1: return None
    g = [max(prices[i]-prices[i-1],0) for i in range(1,len(prices))]
    l = [max(prices[i-1]-prices[i],0) for i in range(1,len(prices))]
    ag = statistics.mean(g[-p:]); al = statistics.mean(l[-p:])
    return round(100-(100/(1+ag/al)),2) if al else 100.0

def bollinger(prices, p=20):
    if len(prices) < p: return None, None, None
    r = prices[-p:]; m = statistics.mean(r); s = statistics.stdev(r)
    return round(m-2*s,2), round(m,2), round(m+2*s,2)

def get_technicals(name, vd=None):
    """Compute technical indicators. Uses vol_data if already fetched."""
    if vd is None:
        vd = get_vol_data(name)
    if not vd:
        return None
    try:
        closes = vd["all_closes"]
        vols   = vd["all_vols"]
        cur    = closes[-1]

        r14          = rsi(closes)
        e20          = ema(closes, 20)
        e50          = ema(closes, 50)
        e200         = ema(closes, 200)
        e12          = ema(closes, 12)
        e26          = ema(closes, 26)
        macd_val     = round(e12-e26, 2) if e12 and e26 else None
        bb_lo,bb_mid,bb_hi = bollinger(closes)
        h52  = max(closes[-252:] if len(closes)>=252 else closes)
        l52  = min(closes[-252:] if len(closes)>=252 else closes)
        pfh  = round(((cur-h52)/h52)*100, 1)
        pfl  = round(((cur-l52)/l52)*100, 1)
        p5   = round(((closes[-1]-closes[-6])/closes[-6])*100,2) if len(closes)>=6 else None
        p20  = round(((closes[-1]-closes[-21])/closes[-21])*100,2) if len(closes)>=21 else None

        vr   = vd["ratio_wk_mo"]

        # Upward movement score 0-100
        score = 0; signals = []
        if r14:
            if r14 < 35:   score+=22; signals.append(f"RSI oversold ({r14}) — strong reversal zone 🔥")
            elif r14 < 50: score+=15; signals.append(f"RSI neutral-low ({r14}) — room to run upward")
            elif r14 < 65: score+=10; signals.append(f"RSI healthy ({r14}) — mid-range momentum")
            elif r14 > 75: score-=10; signals.append(f"RSI overbought ({r14}) — caution, may pull back")
        if e20 and e50:
            if cur > e20 > e50:  score+=20; signals.append("Price > EMA20 > EMA50 — bullish stack ✅")
            elif cur > e50:      score+=10; signals.append("Above EMA50 — medium-term bullish")
            elif cur < e50 and e20 > e50: score+=5; signals.append("EMA20 above EMA50 — golden cross intact")
        if e200:
            if cur > e200:       score+=12; signals.append("Above EMA200 — long-term uptrend intact ✅")
            elif cur < e200 and pfh < -30 and vr and vr > 1.5:
                score+=8; signals.append("Below EMA200 but volume surging — possible reversal")
        if macd_val:
            if macd_val > 0:     score+=10; signals.append(f"MACD positive ({macd_val}) — bullish momentum ✅")
            else:                score-=5;  signals.append(f"MACD negative ({macd_val}) — bearish momentum")
        if vr:
            if vr >= 2.0:        score+=18; signals.append(f"Volume 2×+ weekly avg ({vr}×) — strong unusual activity 🔥")
            elif vr >= 1.5:      score+=12; signals.append(f"Volume surge ({vr}×) — institutional activity possible")
            elif vr >= 1.2:      score+=6;  signals.append(f"Volume slightly elevated ({vr}×)")
        if bb_lo and bb_mid and bb_hi:
            if cur < bb_mid and cur > bb_lo:
                score+=8; signals.append("In lower Bollinger band — bounce zone")
            elif cur > bb_hi:
                score-=5; signals.append("Above upper Bollinger — extended, risk of pullback")
        if p5:
            if p5 > 5:           score+=5;  signals.append(f"Strong 5d momentum: +{p5}%")
            elif p5 > 0:         score+=2
        if pfh < -40 and vr and vr > 1.5:
            score+=10; signals.append(f"Down {abs(pfh)}% from 52w high + volume surge — ACCUMULATION PATTERN 🎯")
        elif pfh < -20:
            score+=4;  signals.append(f"Pulling back {abs(pfh)}% from highs — watching for base formation")

        score = max(0, min(100, score))
        if score >= 72:   verdict = "🟢 STRONG UPSIDE SIGNAL"
        elif score >= 52: verdict = "🟡 MODERATE BULLISH"
        elif score >= 32: verdict = "🟠 NEUTRAL / WEAK"
        else:             verdict = "🔴 BEARISH — AVOID"

        return {
            "sym": vd["sym"], "cur": round(cur,2),
            "rsi": r14, "ema20": e20, "ema50": e50, "ema200": e200,
            "macd": macd_val, "bb_lo": bb_lo, "bb_mid": bb_mid, "bb_hi": bb_hi,
            "h52": round(h52,2), "l52": round(l52,2), "pfh": pfh, "pfl": pfl,
            "p5": p5, "p20": p20,
            "score": score, "verdict": verdict, "signals": signals,
        }
    except Exception as e:
        print(f"    ⚠️  TA failed {name}: {e}"); return None

# ── News ──────────────────────────────────────────────────────────────────────

def get_news(name, max_items=5):
    q    = quote(f"{name} NSE stock India")
    url  = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    html = http_get(url)
    if not html: return []
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", html, re.DOTALL):
        block = m.group(1)
        t = re.search(r"<title>(.*?)</title>", block)
        d = re.search(r"<pubDate>(.*?)</pubDate>", block)
        if t:
            title = re.sub(r"<[^>]+>","",t.group(1)).strip()
            pub   = d.group(1).strip()[:16] if d else ""
            if title and "Google News" not in title:
                items.append({"title":title,"date":pub})
        if len(items) >= max_items: break
    return items

# ── StockTwits ────────────────────────────────────────────────────────────────

def get_twits(name, max_items=5):
    sym  = get_nse_symbol(name)
    if not sym: return [], None
    sym_clean = sym.replace(".NS","")
    url  = f"https://api.stocktwits.com/api/2/streams/symbol/{sym_clean}.NS.json"
    data = http_get(url)
    if not data: return [], None
    try:
        j = json.loads(data); msgs = j.get("messages",[]); items=[]; b=0; br=0
        for m in msgs[:max_items*2]:
            body = m.get("body","").replace("\n"," ")[:140]
            sent = ((m.get("entities",{}) or {}).get("sentiment",{}) or {}).get("basic","")
            if sent=="Bullish": b+=1
            elif sent=="Bearish": br+=1
            items.append({"text":body,"sent":sent,"date":m.get("created_at","")[:10]})
        tot = b+br
        summary = f"🐂 {b} Bullish / 🐻 {br} Bearish ({round(b/tot*100)}% bull)" if tot else None
        return items[:max_items], summary
    except: return [], None

# ── Reddit ────────────────────────────────────────────────────────────────────

def get_reddit(name):
    sym  = (get_nse_symbol(name) or "").replace(".NS","")
    q    = quote(f"{name} stock NSE")
    url  = f"https://www.reddit.com/search.json?q={q}&sort=new&limit=5&t=week"
    data = http_get(url)
    if not data: return []
    try:
        j = json.loads(data); posts=[]
        for p in j.get("data",{}).get("children",[]):
            d = p.get("data",{})
            posts.append({"title":d.get("title","")[:120],"sub":d.get("subreddit",""),"score":d.get("score",0)})
        return posts[:3]
    except: return []

# ── Core analysis ─────────────────────────────────────────────────────────────

def analyse_week(reports):
    stock_days = defaultdict(list); all_dates=[]
    for rep in reports:
        if not rep: continue
        d = rep["date"]; all_dates.append(d); headers = rep["headers"]
        idx = {k:find_col(headers,*v) for k,v in {
            "name":["name"],"cmp":["cmp","current price"],
            "ret1d":["1day","return over 1day"],"ret1w":["1week","return over 1week"],
            "ret1m":["1month","return over 1month"],"ret3m":["3month"],
            "ret6m":["6month"],"ret1y":["1year"],
            "vol":["volume"],"vol1w":["vol 1week","volume 1week"],
            "mktcap":["mar cap","market cap"],"pe":["p/e"],
            "roce":["roce"],"profit":["profit growth","profit var"],
            "qoqp":["qoq profit"],"qoqs":["qoq sales"],
        }.items()}
        for stock in rep["stocks"]:
            if not isinstance(stock,dict): continue
            def g(k):
                i=idx.get(k); return safe_float(stock.get(headers[i],"")) if i is not None else None
            def gs(k):
                i=idx.get(k); return stock.get(headers[i],"") if i is not None else ""
            name=gs("name")
            if not name: continue
            stock_days[name].append({
                "date":d,"cmp":g("cmp"),"ret1d":g("ret1d"),"ret1w":g("ret1w"),
                "ret1m":g("ret1m"),"ret3m":g("ret3m"),"ret6m":g("ret6m"),"ret1y":g("ret1y"),
                "vol":g("vol"),"vol1w":g("vol1w"),"mktcap":g("mktcap"),
                "pe":g("pe"),"roce":g("roce"),"profit":g("profit"),
                "qoqp":g("qoqp"),"qoqs":g("qoqs"),
            })

    stock_stats={}
    for name,days in stock_days.items():
        ret1ds=[d["ret1d"] for d in days if d["ret1d"] is not None]
        cmps=[d["cmp"] for d in days if d["cmp"] is not None]
        pos_days=sum(1 for r in ret1ds if r>0)
        latest=days[-1]
        stock_stats[name]={
            "appearances":len(days),
            "avg_ret1d":round(statistics.mean(ret1ds),2) if ret1ds else None,
            "pos_days":pos_days,
            "price_change_week":round(((cmps[-1]-cmps[0])/cmps[0])*100,2) if len(cmps)>=2 and cmps[0] else None,
            "latest_cmp":latest["cmp"],"latest_ret1d":latest["ret1d"],
            "latest_ret1w":latest["ret1w"],"latest_ret1m":latest["ret1m"],
            "latest_ret3m":latest["ret3m"],"latest_ret1y":latest["ret1y"],
            "latest_mktcap":latest["mktcap"],"latest_pe":latest["pe"],
            "latest_roce":latest["roce"],"latest_profit":latest["profit"],
            "latest_qoqp":latest["qoqp"],"latest_qoqs":latest["qoqs"],
            "daily_data":days,
        }

    frequency=   {n:len(d) for n,d in stock_days.items()}
    appeared_2p= sorted([n for n,c in frequency.items() if c>=2],key=lambda n:stock_stats[n]["appearances"],reverse=True)
    appeared_all5=[n for n,c in frequency.items() if c==5]
    earnings_cat=sorted([(n,s) for n,s in stock_stats.items() if s["appearances"]>=2 and s.get("latest_qoqp") and s["latest_qoqp"]>20],key=lambda x:x[1]["latest_qoqp"],reverse=True)
    bp_ranked=sorted(stock_stats.items(),key=lambda x:(x[1]["appearances"],x[1].get("avg_ret1d") or 0),reverse=True)
    return {"dates":sorted(all_dates),"total_unique":len(stock_days),"frequency":frequency,
            "appeared_all5":appeared_all5,"appeared_2p":appeared_2p,
            "stock_stats":stock_stats,"earnings_cat":earnings_cat,"bp_ranked":bp_ranked}

# ── HTML helpers ──────────────────────────────────────────────────────────────

def pct(v,d=2):
    if v is None: return "—"
    c="var(--green)" if v>0 else "var(--red)" if v<0 else "var(--text3)"
    a="▲" if v>0 else "▼" if v<0 else ""
    return f'<span style="color:{c};font-weight:600">{a}&nbsp;{v:.{d}f}%</span>'

def n(v,d=2):
    if v is None: return "—"
    try: return f"{float(v):,.{d}f}"
    except: return str(v)

def freq_bar(count,mx=5):
    return (f'<span style="color:var(--blue);letter-spacing:2px">{"█"*count}</span>'
            f'<span style="color:#ddd;letter-spacing:2px">{"░"*(mx-count)}</span>'
            f' <b>{count}/5</b>')

def score_badge(s):
    c="#1a9e6d" if s>=70 else "#f0a500" if s>=50 else "#d94b4b"
    return f'<span style="font-size:20px;font-weight:700;color:{c}">{s}</span><span style="color:var(--text3);font-size:11px">/100</span>'

def fmt_vol(v):
    if not v: return "—"
    if v >= 1e7: return f"{v/1e7:.2f}Cr"
    if v >= 1e5: return f"{v/1e5:.1f}L"
    if v >= 1e3: return f"{v/1e3:.0f}K"
    return str(int(v))

def vol_bar_chart(vd):
    """Render a mini bar chart of daily volumes for last 10 days + week vs month comparison."""
    if not vd:
        return '<em style="color:var(--text3);font-size:12px">Volume data loading... (yfinance fetching NSE data)</em>'

    v5   = vd["vol5d"]
    v22  = vd["vol22d"]
    v63  = vd["vol63d"]
    ratio= vd["ratio_wk_mo"]
    last10= vd["last10_vols"]
    last10d=vd["last10_dates"]

    # Color for ratio
    rc = "#1a9e6d" if ratio and ratio>1.5 else "#f0a500" if ratio and ratio>1.0 else "#d94b4b"

    # Summary boxes
    summary = f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px">
      <div style="background:var(--green-dim);border:1px solid #c3e6c3;border-radius:6px;padding:8px;text-align:center">
        <div style="font-size:10px;color:var(--text3)">Vol (5d avg)</div>
        <div style="font-weight:700;font-size:13px">{fmt_vol(v5)}</div>
      </div>
      <div style="background:var(--bg4);border:1px solid #d0d8ff;border-radius:6px;padding:8px;text-align:center">
        <div style="font-size:10px;color:var(--text3)">Vol (1mo avg)</div>
        <div style="font-weight:700;font-size:13px">{fmt_vol(v22)}</div>
      </div>
      <div style="background:var(--bg2)8f0;border:1px solid #ffd0a0;border-radius:6px;padding:8px;text-align:center">
        <div style="font-size:10px;color:var(--text3)">Vol (3mo avg)</div>
        <div style="font-weight:700;font-size:13px">{fmt_vol(v63)}</div>
      </div>
      <div style="background:var(--bg4);border:1px solid #c0c8ff;border-radius:6px;padding:8px;text-align:center">
        <div style="font-size:10px;color:var(--text3)">Week/Month Ratio</div>
        <div style="font-weight:700;font-size:15px;color:{rc}">{ratio or '—'}×</div>
      </div>
    </div>"""

    # Visual bar chart of last 10 days
    if not last10: return summary
    max_v = max(last10) if last10 else 1
    bars  = ""
    for i, (v, d) in enumerate(zip(last10, last10d)):
        h   = max(4, int((v / max_v) * 60))
        col = "#1a9e6d" if v > v22 else "#4a6cf7"
        is_recent = i >= len(last10)-5  # last 5 = this week
        bc  = "#ff8c00" if is_recent else col
        bars += f"""
        <div style="display:flex;flex-direction:column;align-items:center;gap:2px">
          <div style="font-size:9px;color:var(--text3)">{fmt_vol(v)}</div>
          <div style="width:18px;height:{h}px;background:{bc};border-radius:2px 2px 0 0" title="{d}: {fmt_vol(v)}"></div>
          <div style="font-size:8px;color:var(--text3);transform:rotate(-45deg);margin-top:2px">{d[-5:]}</div>
        </div>"""

    chart = f"""
    <div style="display:flex;align-items:flex-end;gap:3px;height:90px;padding:0 4px;margin-top:8px;overflow-x:auto">
      {bars}
    </div>
    <div style="font-size:10px;color:var(--text3);margin-top:24px">
      🟠 = This week &nbsp; 🔵 = Prior weeks &nbsp; Green bar = above 1mo avg
    </div>"""

    return summary + chart

def render_ta(ta):
    if not ta:
        return '<div style="background:var(--bg2)8f0;border-radius:6px;padding:10px;font-size:12px;color:var(--text3)">Technical data unavailable — NSE ticker not found in yfinance</div>'
    rsi_c = "#d94b4b" if ta["rsi"] and ta["rsi"]>70 else "#1a9e6d" if ta["rsi"] and ta["rsi"]<40 else "#555"
    m_c   = "#1a9e6d" if ta["macd"] and ta["macd"]>0 else "#d94b4b"
    sigs  = "".join(f'<div style="font-size:11px;padding:2px 0;color:#2d5a27">✓ {s}</div>' for s in ta["signals"]) or '<div style="font-size:11px;color:var(--text3)">No strong signals</div>'
    return f"""
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-bottom:8px;font-size:11px">
      <div style="background:var(--bg4);padding:6px;border-radius:5px"><div style="color:var(--text3);font-size:9px">RSI(14)</div><div style="font-weight:700;color:{rsi_c}">{ta['rsi'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:6px;border-radius:5px"><div style="color:var(--text3);font-size:9px">MACD</div><div style="font-weight:700;color:{m_c}">{ta['macd'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:6px;border-radius:5px"><div style="color:var(--text3);font-size:9px">EMA20/50</div><div style="font-weight:600">{ta['ema20'] or '—'}/{ta['ema50'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:6px;border-radius:5px"><div style="color:var(--text3);font-size:9px">EMA200</div><div style="font-weight:600">{ta['ema200'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:6px;border-radius:5px"><div style="color:var(--text3);font-size:9px">From 52w High</div><div style="font-weight:700;color:{'#d94b4b' if ta['pfh']<-20 else '#555'}">{ta['pfh']}%</div></div>
      <div style="background:var(--bg4);padding:6px;border-radius:5px"><div style="color:var(--text3);font-size:9px">5d / 20d</div><div style="font-weight:600">{pct(ta['p5'],1)}/{pct(ta['p20'],1)}</div></div>
    </div>
    <div style="background:var(--green-dim);border:1px solid #c3e6c3;border-radius:6px;padding:8px">
      <div style="font-size:12px;font-weight:700;margin-bottom:4px">{ta['verdict']}</div>
      {sigs}
    </div>
    <div style="font-size:10px;color:var(--text3);margin-top:4px">BB: {ta['bb_lo']}/{ta['bb_mid']}/{ta['bb_hi']} | 52w: {ta['l52']}–{ta['h52']}</div>"""

def render_news(items):
    if not items: return '<em style="color:var(--text3);font-size:11px">No recent news found</em>'
    return "".join(f'<div style="padding:5px 0;border-bottom:1px solid #f5f5f5"><div style="font-size:10px;color:var(--text3)">{i["date"]}</div><div style="font-size:12px;line-height:1.4">{i["title"]}</div></div>' for i in items)

def render_twits(items, summary):
    if not items: return '<em style="color:var(--text3);font-size:11px">No StockTwits data</em>'
    s = f'<div style="font-size:11px;font-weight:600;margin-bottom:4px;padding:4px 8px;background:var(--bg4);border-radius:4px">{summary}</div>' if summary else ""
    rows = "".join(f'<div style="padding:3px 0;border-bottom:1px solid #f8f8f8;font-size:11px;line-height:1.4"><span style="color:{"#1a9e6d" if i["sent"]=="Bullish" else "#d94b4b" if i["sent"]=="Bearish" else "#888"}">{"🐂" if i["sent"]=="Bullish" else "🐻" if i["sent"]=="Bearish" else "💬"}</span> {i["text"]}</div>' for i in items)
    return s+rows

def render_reddit(posts):
    if not posts: return '<em style="color:var(--text3);font-size:11px">No Reddit mentions this week</em>'
    return "".join(f'<div style="padding:4px 0;border-bottom:1px solid #f8f8f8;font-size:11px"><span style="color:#ff6314;font-size:10px">r/{p["sub"]}</span> ↑{p["score"]} — {p["title"]}</div>' for p in posts)

def deep_dive_card(name, s, vd, ta, news, twits, twit_sent, reddit):
    sym   = (vd["sym"] if vd else None) or get_nse_symbol(name) or "—"
    score = ta["score"] if ta else 0
    sc    = "#1a9e6d" if score>=70 else "#f0a500" if score>=50 else "#d94b4b"

    return f"""
    <div id="stock-{re.sub(r'[^a-z0-9]','',name.lower())}" style="border:1px solid #e0e4f0;border-radius:12px;margin-bottom:28px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.04)">
      <div style="background:linear-gradient(90deg,#0f0c29,#302b63);color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center">
        <div>
          <span style="font-size:16px;font-weight:700">{name}</span>
          <span style="font-size:11px;opacity:.6;margin-left:8px">{sym}</span>
        </div>
        <div style="text-align:right">
          <div style="font-size:18px;font-weight:700">₹{n(s['latest_cmp'],1)}</div>
          <div style="font-size:11px;opacity:.7">{freq_bar(s['appearances'])} &nbsp;|&nbsp; Upside: {score_badge(score)}</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid var(--border);font-size:11px">
        <div style="padding:8px 10px;border-right:1px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">Avg 1d Ret</div>{pct(s['avg_ret1d'])}</div>
        <div style="padding:8px 10px;border-right:1px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">Week Chg</div>{pct(s['price_change_week'])}</div>
        <div style="padding:8px 10px;border-right:1px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">1Mo Return</div>{pct(ta.get("p20") if ta and s.get("latest_ret1m") is None and ta.get("p20") is not None else s.get("latest_ret1m"))}<div style="font-size:8px;color:var(--text3)">{("yf" if ta and s.get("latest_ret1m") is None and ta.get("p20") is not None else "")}</div></div>
        <div style="padding:8px 10px;border-right:1px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">QoQ Profit</div>{pct(s['latest_qoqp'])}</div>
        <div style="padding:8px 10px;border-right:1px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">ROCE%</div>{pct(s['latest_roce'])}</div>
        <div style="padding:8px 10px"><div style="color:var(--text3);font-size:9px">Mkt Cap</div><div style="font-weight:600">₹{n(s['latest_mktcap'],0) if s['latest_mktcap'] else '—'}Cr</div></div>
      </div>
      <!-- Volume chart full width -->
      <div style="padding:12px 16px;background:var(--bg3);border-bottom:1px solid var(--border)">
        <div style="font-size:12px;font-weight:700;color:var(--text);margin-bottom:8px">🔊 Volume Analysis — Week vs Month vs 3-Month</div>
        {vol_bar_chart(vd)}
      </div>
      <!-- 3 columns -->
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr">
        <div style="padding:12px 14px;border-right:1px solid #f0f0f0">
          <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:var(--text)">📊 Chart Analysis</div>
          {render_ta(ta)}
        </div>
        <div style="padding:12px 14px;border-right:1px solid #f0f0f0">
          <div style="font-size:12px;font-weight:700;margin-bottom:6px;color:var(--text)">📰 News</div>
          {render_news(news)}
          <div style="font-size:12px;font-weight:700;margin:10px 0 6px;color:var(--text)">🗣 Reddit</div>
          {render_reddit(reddit)}
        </div>
        <div style="padding:12px 14px">
          <div style="font-size:12px;font-weight:700;margin-bottom:6px;color:var(--text)">💬 StockTwits</div>
          {render_twits(twits, twit_sent)}
        </div>
      </div>
    </div>"""

def build_html(analysis, vol_d, tech_d, news_d, twit_d, reddit_d, week_dates):
    stats = analysis["stock_stats"]
    wl    = f"{week_dates[0]} → {week_dates[-1]}" if week_dates else "This Week"

    all5_badges = "".join(f'<span style="display:inline-block;background:#e8f0ff;color:#1a3a8f;border-radius:20px;padding:3px 12px;margin:3px;font-size:13px;font-weight:500">{n}</span>' for n in analysis["appeared_all5"]) or "<em style='color:var(--text3)'>None this week</em>"

    earn_rows = "".join(f"""<tr>
      <td style="text-align:left;font-weight:500">{nm}</td>
      <td>{pct(s.get('latest_qoqp'))}</td><td>{pct(s.get('latest_qoqs'))}</td>
      <td>{pct(s.get('latest_profit'))}</td><td>{s['appearances']}/5</td><td>₹{n(s.get('latest_cmp'),1)}</td>
    </tr>""" for nm,s in analysis["earnings_cat"][:10])

    bp_rows = "".join(f"""<tr>
      <td style="text-align:left;font-weight:600"><a href="#{re.sub(r'[^a-z0-9]','',nm.lower())}" style="color:inherit;text-decoration:none">{nm} ↓</a></td>
      <td>{freq_bar(s['appearances'])}</td>
      <td>{pct(s.get('avg_ret1d'))}</td>
      <td>{pct(s.get('price_change_week'))}</td>
      <td style="color:{'#1a9e6d' if vol_d.get(nm) and vol_d[nm]['ratio_wk_mo'] and vol_d[nm]['ratio_wk_mo']>1.5 else '#555'};font-weight:600">
        {str(vol_d[nm]['ratio_wk_mo'])+'×' if vol_d.get(nm) and vol_d[nm].get('ratio_wk_mo') else '—'}
      </td>
      <td style="font-size:11px">{fmt_vol(vol_d[nm]['vol5d']) if vol_d.get(nm) else '—'}</td>
      <td style="font-size:11px">{fmt_vol(vol_d[nm]['vol22d']) if vol_d.get(nm) else '—'}</td>
      <td>{pct(s.get('latest_roce'))}</td>
      <td>{score_badge(tech_d[nm]['score']) if tech_d.get(nm) else '—'}</td>
    </tr>""" for nm,s in analysis["bp_ranked"] if s["appearances"]>=2)

    dive_cards = "".join(
        deep_dive_card(
            nm, stats[nm],
            vol_d.get(nm), tech_d.get(nm),
            news_d.get(nm,[]),
            *twit_d.get(nm,([], None)),
            reddit_d.get(nm,[])
        )
        for nm in analysis["appeared_2p"]
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Analysis — {wl}</title>
<style>
/* ── Bloomberg-inspired dark theme ─────────────────────────── */
:root {{
  --bg:        #0d0f14;
  --bg2:       #131620;
  --bg3:       #1a1d2e;
  --bg4:       #1e2235;
  --border:    #252840;
  --border2:   #2e3250;
  --text:      #e2e4f0;
  --text2:     #9198b8;
  --text3:     #545c7a;
  --amber:     #f0a500;
  --amber-dim: #3d2900;
  --green:     #00c875;
  --green-dim: #002e1a;
  --red:       #ff4560;
  --red-dim:   #3d0010;
  --blue:      #4a9eff;
  --blue-dim:  #0a1f3d;
  --mono:      'JetBrains Mono','Fira Code','Courier New',monospace;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}}
/* Header */
.page-header{{background:var(--bg2);border-bottom:2px solid var(--amber);padding:14px 24px;display:flex;justify-content:space-between;align-items:center}}
.page-title{{font-size:16px;font-weight:600;color:var(--amber);letter-spacing:.5px}}
.page-meta{{font-size:11px;color:var(--text3);font-family:var(--mono)}}
/* Stat strip */
.stat-strip{{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 24px;display:flex;gap:32px;flex-wrap:wrap}}
.stat{{display:flex;flex-direction:column;gap:2px}}
.stat-val{{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--amber)}}
.stat-lbl{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}}
/* Sections */
.sec{{border-bottom:1px solid var(--border)}}
.sec-head{{padding:7px 24px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}}
.sec-label{{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--amber)}}
.sec-count{{font-size:10px;color:var(--text3);font-family:var(--mono)}}
/* Tables */
table{{width:100%;border-collapse:collapse}}
thead th{{background:var(--bg3);color:var(--text3);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:8px 14px;text-align:right;border-bottom:1px solid var(--border2);white-space:nowrap}}
thead th:first-child{{text-align:left}}
tbody td{{padding:7px 14px;border-bottom:1px solid var(--border);text-align:right;font-family:var(--mono);font-size:12px;color:var(--text);white-space:nowrap}}
tbody td:first-child{{text-align:left;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-weight:500}}
tbody tr:hover td{{background:var(--bg4)}}
/* Pct colors */
.up{{color:var(--green);font-weight:600}}
.dn{{color:var(--red);font-weight:600}}
.neu{{color:var(--text2)}}
/* Stock card */
.stock-card{{border:1px solid var(--border);border-left:3px solid var(--amber);margin:12px 24px;border-radius:6px;overflow:hidden}}
.card-header{{background:var(--bg3);padding:10px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)}}
.card-name{{font-size:14px;font-weight:600;color:var(--text)}}
.card-sym{{font-size:10px;color:var(--text3);font-family:var(--mono);margin-left:8px}}
.card-price{{font-family:var(--mono);font-size:16px;font-weight:600;color:var(--amber)}}
.card-score-line{{font-size:10px;color:var(--text2);margin-top:2px;text-align:right;font-family:var(--mono)}}
/* Metrics row */
.metrics{{display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid var(--border)}}
.metric{{padding:8px 12px;border-right:1px solid var(--border)}}
.metric:last-child{{border-right:none}}
.metric-lbl{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}}
.metric-val{{font-family:var(--mono);font-size:13px;font-weight:600}}
/* 3-col body */
.card-body{{display:grid;grid-template-columns:1fr 1fr 1fr}}
.col{{padding:12px 14px;border-right:1px solid var(--border)}}
.col:last-child{{border-right:none}}
.col-title{{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--amber);margin-bottom:7px}}
/* TA grid */
.ta-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-bottom:8px}}
.ta-cell{{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:5px 7px}}
.ta-lbl{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.3px}}
.ta-val{{font-family:var(--mono);font-size:12px;font-weight:600;margin-top:1px}}
/* Verdict box */
.verdict-box{{border-left:2px solid;padding:7px 10px;border-radius:3px;margin-top:6px}}
.verdict-box.strong{{background:var(--green-dim);border-color:var(--green)}}
.verdict-box.moderate{{background:var(--amber-dim);border-color:var(--amber)}}
.verdict-box.weak{{background:var(--bg4);border-color:var(--border2)}}
.verdict-box.bearish{{background:var(--red-dim);border-color:var(--red)}}
.verdict-title{{font-size:11px;font-weight:600;margin-bottom:4px}}
.verdict-box.strong .verdict-title{{color:var(--green)}}
.verdict-box.moderate .verdict-title{{color:var(--amber)}}
.verdict-box.weak .verdict-title{{color:var(--text2)}}
.verdict-box.bearish .verdict-title{{color:var(--red)}}
.verdict-sig{{font-size:10px;color:var(--text2);line-height:1.6}}
/* News */
.news-item{{padding:4px 0;border-bottom:1px solid var(--border)}}
.news-item:last-child{{border-bottom:none}}
.news-date{{font-size:9px;color:var(--text3);font-family:var(--mono)}}
.news-title{{font-size:11px;color:var(--text2);line-height:1.4;margin-top:1px}}
/* Twits */
.twit-summary{{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:5px 10px;margin-bottom:6px;font-family:var(--mono);font-size:11px}}
.twit-item{{font-size:10px;padding:3px 0;border-bottom:1px solid var(--border);color:var(--text2);line-height:1.4}}
/* Badges */
.badge{{font-size:9px;padding:2px 7px;border-radius:3px;font-weight:600;letter-spacing:.4px}}
.badge-gold{{background:var(--amber-dim);color:var(--amber)}}
.badge-silver{{background:var(--blue-dim);color:var(--blue)}}
.badge-watch{{background:var(--bg4);color:var(--text3);border:1px solid var(--border2)}}
.badge-fresh{{background:var(--blue-dim);color:var(--blue)}}
.badge-recover{{background:var(--green-dim);color:var(--green)}}
.badge-stage2{{background:var(--green-dim);color:var(--green)}}
.badge-extended{{background:var(--amber-dim);color:var(--amber)}}
.badge-danger{{background:var(--red-dim);color:var(--red)}}
/* OBV warning */
.obv-warn{{background:var(--red-dim);border-left:3px solid var(--red);padding:8px 14px;font-size:11px;color:var(--red);font-weight:600}}
/* Vol bar chart */
.vol-summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:8px}}
.vol-kpi{{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:6px 8px;text-align:center}}
.vol-kpi-val{{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--text)}}
.vol-kpi-lbl{{font-size:9px;color:var(--text3);margin-top:2px;text-transform:uppercase}}
.vol-bars{{display:flex;align-items:flex-end;gap:3px;height:44px;margin:4px 0}}
.vol-bar-wrap{{display:flex;flex-direction:column;align-items:center;flex:1;gap:2px}}
.vol-bar{{width:100%;border-radius:2px 2px 0 0;min-height:2px}}
.vol-bar.week{{background:var(--amber)}}
.vol-bar.prior{{background:var(--blue-dim);border:1px solid var(--blue)}}
.vol-bar-lbl{{font-size:8px;color:var(--text3);font-family:var(--mono)}}
/* Week pattern boxes */
.week-pattern{{display:flex;gap:5px;margin:5px 0}}
.wk-box{{width:24px;height:24px;border-radius:3px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:10px;font-weight:600}}
.wk-box.hit3{{background:var(--amber);color:#000}}
.wk-box.hit2{{background:var(--amber-dim);color:var(--amber);border:1px solid var(--amber)}}
.wk-box.hit1{{background:var(--blue-dim);color:var(--blue);border:1px solid var(--blue)}}
.wk-box.miss{{background:var(--bg4);color:var(--text3);border:1px solid var(--border)}}
/* Score breakdown */
.score-list{{font-size:10px;color:var(--text3);font-family:var(--mono);line-height:1.7}}
/* Stage 1 table */
.stage1-note{{padding:16px 24px;font-size:12px;color:var(--text3);background:var(--bg2);text-align:center}}
/* Footer */
.page-foot{{padding:10px 24px;font-size:10px;color:var(--text3);font-family:var(--mono);background:var(--bg2);border-top:1px solid var(--border);text-align:center}}
/* Legend strip */
.legend{{display:flex;gap:16px;padding:8px 24px;background:var(--bg2);border-bottom:1px solid var(--border);font-size:10px;color:var(--text3);flex-wrap:wrap}}
.legend-item{{display:flex;align-items:center;gap:5px}}
</style></style></head><body>
<div class="wrap">
  <div class="top">
    <h1>📊 Weekly Breakout & Volume Analysis</h1>
    <p>{wl} · {analysis['total_unique']} unique stocks · {len(analysis['dates'])} trading days · {len(analysis['appeared_2p'])} stocks deep-dived (appeared 2+ days)</p>
  </div>
  <div class="meta">
    <span>📅 <strong>{", ".join(analysis['dates'])}</strong></span>
    <span>🔗 <a href="{SCREEN_URL}">screener.in/screens/3664072/screen1</a></span>
  </div>

  <div class="sec"><div class="sh"><h2>📈 Week at a Glance</h2></div><div class="sb"><div class="sg">
    <div class="sb2"><div class="v">{analysis['total_unique']}</div><div class="l">Unique stocks appeared</div></div>
    <div class="sb2"><div class="v">{len(analysis['appeared_all5'])}</div><div class="l">All 5 days</div></div>
    <div class="sb2"><div class="v">{len(analysis['appeared_2p'])}</div><div class="l">2+ days (deep-dived)</div></div>
    <div class="sb2"><div class="v">{len(analysis['earnings_cat'])}</div><div class="l">Earnings catalysts</div></div>
    <div class="sb2"><div class="v">{sum(1 for nm in analysis['appeared_2p'] if tech_d.get(nm) and tech_d[nm]['score']>=70)}</div><div class="l">Strong upside signals</div></div>
  </div></div></div>

  <div class="sec"><div class="sh"><h2>🔁 Appeared All 5 Days</h2><p>Highest conviction</p></div><div class="sb">{all5_badges}</div></div>

  <div class="sec"><div class="sh"><h2>💥 Earnings Catalysts (QoQ Profit > 20% + 2+ days)</h2></div>
  <div style="padding:0 24px 20px"><table>
    <thead><tr><th>Stock</th><th>QoQ Profit%</th><th>QoQ Sales%</th><th>Profit Growth%</th><th>Days</th><th>CMP</th></tr></thead>
    <tbody>{earn_rows}</tbody>
  </table></div></div>

  <div class="sec"><div class="sh"><h2>🎯 All Repeated Stocks — Volume + Score Summary</h2><p>Click stock name to jump to deep dive</p></div>
  <div style="padding:0 24px 20px"><table>
    <thead><tr><th>Stock</th><th>Days</th><th>Avg 1d Ret</th><th>Week Chg</th><th>Wk/Mo Vol Ratio</th><th>Vol 5d avg</th><th>Vol 1mo avg</th><th>ROCE%</th><th>Upside Score</th></tr></thead>
    <tbody>{bp_rows}</tbody>
  </table></div></div>

  <div class="sec"><div class="sh"><h2>⭐ Deep Dives — Every Stock Appearing 2+ Days</h2>
  <p>Volume bars (week vs month vs 3mo) · Chart signals · News · StockTwits · Reddit</p></div>
  <div class="sb">{dive_cards}</div></div>

  <div class="foot">Auto-generated · GitHub Actions · Screener.in · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div></body></html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today      = date.today().isoformat()
    week_dates = get_week_dates()
    print(f"\n🔍 Weekly Analysis v4 — {week_dates[0]} to {week_dates[-1]}")

    reports = []
    for d in week_dates:
        r = load_report(d)
        if r: print(f"  📂 {d} — {r['total_stocks']} stocks"); reports.append(r)
        else: print(f"  ⚠️  No report: {d}")

    if not reports: print("❌ No reports. Exit."); return

    analysis = analyse_week(reports)
    targets  = analysis["appeared_2p"]
    print(f"\n  📊 {analysis['total_unique']} unique · {len(targets)} to deep-dive")
    print(f"  Stocks: {targets}\n")

    vol_d={}; tech_d={}; news_d={}; twit_d={}; reddit_d={}

    if HAS_YF:
        print(f"  📡 Fetching volume + technicals ({len(targets)} stocks)...")
        for nm in targets:
            sym = get_nse_symbol(nm)
            print(f"    → {nm} ({sym})")
            vd = get_vol_data(nm)
            vol_d[nm] = vd
            tech_d[nm] = get_technicals(nm, vd) if vd else None
            time.sleep(0.5)
    else:
        print("  ⚠️  yfinance not installed — skipping vol/TA")

    print(f"\n  📰 Fetching news...")
    for nm in targets: news_d[nm]=get_news(nm); time.sleep(0.4)

    print(f"\n  💬 Fetching StockTwits...")
    for nm in targets: twit_d[nm]=get_twits(nm); time.sleep(0.3)

    print(f"\n  🗣 Fetching Reddit...")
    for nm in targets: reddit_d[nm]=get_reddit(nm); time.sleep(0.3)

    week_dir = os.path.join(OUTPUT_DIR,"weekly")
    os.makedirs(week_dir, exist_ok=True)
    base = os.path.join(week_dir, f"week_{week_dates[0]}")

    html = build_html(analysis, vol_d, tech_d, news_d, twit_d, reddit_d, week_dates)
    with open(base+"_analysis.html","w",encoding="utf-8") as f: f.write(html)
    print(f"\n  ✅ HTML → {base}_analysis.html")

    with open(base+"_analysis.json","w",encoding="utf-8") as f:
        out = {k:v for k,v in analysis.items() if k not in("stock_stats","bp_ranked")}
        out["stock_stats_summary"] = {n:{k:v for k,v in s.items() if k!="daily_data"} for n,s in analysis["stock_stats"].items()}
        out["conviction_picks"] = [(nm,{k:v for k,v in s.items() if k!="daily_data"}) for nm,s in analysis["bp_ranked"] if s["appearances"]>=2]
        json.dump(out,f,indent=2,ensure_ascii=False,default=str)
    print(f"  ✅ JSON → {base}_analysis.json")
    print(f"\n✅ Done — {len(targets)} deep dives complete")

if __name__=="__main__":
    main()
