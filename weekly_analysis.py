"""
Screener.in Weekly Analysis v3
- Deep dives for ALL stocks appearing 2+ days (not just conviction picks)
- Vol spike computed from yfinance (not Screener columns — those are often missing)
- Technical: RSI, MACD, EMA20/50/200, Bollinger, 52w high/low, comeback mode
- News: Google News RSS per stock
- Social: StockTwits sentiment per stock
- Chart signal: upward movement likelihood score
"""

import json, os, re, time, statistics, glob
from datetime import datetime, date, timedelta
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError

OUTPUT_DIR = "reports"
SCREEN_URL = "https://www.screener.in/screens/3664072/screen1/"

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    print("  ⚠️  yfinance not installed — pip install yfinance")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_float(val):
    try:
        return float(str(val).replace(",","").replace("%","").strip())
    except:
        return None

def find_col(headers, *keywords):
    for kw in keywords:
        for i,h in enumerate(headers):
            if kw.lower() in h.lower():
                return i
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

# ── Core analysis ─────────────────────────────────────────────────────────────

def analyse_week(reports):
    stock_days = defaultdict(list)
    all_dates  = []

    for rep in reports:
        if not rep: continue
        d       = rep["date"]
        all_dates.append(d)
        headers = rep["headers"]
        idx = {
            k: find_col(headers, *v) for k,v in {
                "name":   ["name"],
                "cmp":    ["cmp","current price"],
                "ret1d":  ["1day","return over 1day"],
                "ret1w":  ["1week","return over 1week"],
                "ret1m":  ["1month","return over 1month"],
                "ret3m":  ["3month"],
                "ret6m":  ["6month"],
                "ret1y":  ["1year"],
                "vol":    ["volume"],
                "vol1w":  ["vol 1week","volume 1week"],
                "vol1m":  ["vol 1month","volume 1month"],
                "mktcap": ["mar cap","market cap"],
                "pe":     ["p/e"],
                "roce":   ["roce"],
                "profit": ["profit growth","profit var"],
                "qoqp":   ["qoq profit"],
                "qoqs":   ["qoq sales"],
            }.items()
        }
        for stock in rep["stocks"]:
            if not isinstance(stock, dict): continue
            def g(k):
                i = idx.get(k)
                return safe_float(stock.get(headers[i],"")) if i is not None else None
            def gs(k):
                i = idx.get(k)
                return stock.get(headers[i],"") if i is not None else ""
            name = gs("name")
            if not name: continue
            stock_days[name].append({
                "date":d,"cmp":g("cmp"),"ret1d":g("ret1d"),"ret1w":g("ret1w"),
                "ret1m":g("ret1m"),"ret3m":g("ret3m"),"ret6m":g("ret6m"),"ret1y":g("ret1y"),
                "vol":g("vol"),"vol1w":g("vol1w"),"mktcap":g("mktcap"),
                "pe":g("pe"),"roce":g("roce"),"profit":g("profit"),
                "qoqp":g("qoqp"),"qoqs":g("qoqs"),
            })

    stock_stats = {}
    for name, days in stock_days.items():
        ret1ds = [d["ret1d"] for d in days if d["ret1d"] is not None]
        cmps   = [d["cmp"]   for d in days if d["cmp"]   is not None]
        # Screener vol spike (may be None if columns missing)
        scr_spikes = []
        for d in days:
            if d["vol"] and d["vol1w"] and d["vol1w"]>0:
                scr_spikes.append(d["vol"]/d["vol1w"])
        pos_days = sum(1 for r in ret1ds if r>0)
        latest   = days[-1]
        stock_stats[name] = {
            "appearances":   len(days),
            "avg_ret1d":     round(statistics.mean(ret1ds),2) if ret1ds else None,
            "max_ret1d":     round(max(ret1ds),2)             if ret1ds else None,
            "pos_days":      pos_days,
            "scr_vol_spike": round(statistics.mean(scr_spikes),2) if scr_spikes else None,
            "price_change_week": round(((cmps[-1]-cmps[0])/cmps[0])*100,2) if len(cmps)>=2 and cmps[0] else None,
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

    frequency = {n:len(d) for n,d in stock_days.items()}
    appeared_2p = sorted([n for n,c in frequency.items() if c>=2],
                         key=lambda n: stock_stats[n]["appearances"], reverse=True)
    appeared_all5 = [n for n,c in frequency.items() if c==5]

    earnings_cat = sorted(
        [(n,s) for n,s in stock_stats.items()
         if s["appearances"]>=2 and s.get("latest_qoqp") and s["latest_qoqp"]>20],
        key=lambda x: x[1]["latest_qoqp"], reverse=True
    )

    bp_ranked = sorted(
        stock_stats.items(),
        key=lambda x: (x[1]["appearances"], x[1].get("avg_ret1d") or 0),
        reverse=True
    )

    return {
        "dates": sorted(all_dates),
        "total_unique": len(stock_days),
        "frequency": frequency,
        "appeared_all5": appeared_all5,
        "appeared_2p": appeared_2p,
        "stock_stats": stock_stats,
        "earnings_cat": earnings_cat,
        "bp_ranked": bp_ranked,
    }

# ── yfinance: vol spike + technical ──────────────────────────────────────────

NSE_MAP = {
    "infosys":"INFY","tcs":"TCS","wipro":"WIPRO","hcl tech":"HCLTECH",
    "nazara":"NAZARA","chambal fert":"CHAMBLFERT","crompton":"CROMPTON",
    "pricol":"PRICOLLTD","td power":"TDPOWERSYS","kirloskar oil":"KIRLOSENG",
    "mayur uniquoters":"MAYURUNIQ","pearl global":"PGIL","chalet":"CHALET",
    "latent view":"LATENTVIEW","triveni turbine":"TRIVENI","hexaware":"HEXAWARE",
    "balaji amines":"BALAMINES","carborundum":"CARBORUNIV","medplus":"MEDPLUS",
    "atul auto":"ATULAUTO","stove kraft":"STOVEKRAFT","sparc":"SPARC",
    "supriya lifesci":"SUPRIYA","tbo tek":"TBOTEK","ajax engineering":"AJAX",
    "coforge":"COFORGE","tata technolog":"TATATECH","seamec":"SEAMEC",
    "hind rectifiers":"HIRECT","wheels india":"WHEELS","dynacons":"DYNACONS",
    "international ge":"INTLGERMN","sumitomo chemi":"SUMICHEM","saksoft":"SAKSOFT",
    "deepak fertilis":"DEEPAKFERT","deepak fertilisers":"DEEPAKFERT",
    "dredging corpn":"DREDGECORP","dredging corporation":"DREDGECORP",
    "jay bharat":"JAYBHARAT","mtar technolog":"MTAR","mtar":"MTAR",
    "apollo micro":"APOLLOMICRO","entero healthcare":"ENTERO","entero":"ENTERO",
    "dec.gold":"DECCAN","utssav cz":"UTSSAV","sbc exports":"SBC",
    "s p i c":"SPIC","e2e networks":"E2ENETWORKS","jsw cement":"JSWCEMENT",
    "sandhar tech":"SANDHAR",
}

def name_to_symbol(name):
    nl = name.lower()
    for k,v in NSE_MAP.items():
        if k in nl: return v
    return name.upper().replace(" ","").replace(".","")[:12]

def ema(prices, p):
    if len(prices)<p: return None
    k = 2/(p+1); e = statistics.mean(prices[:p])
    for x in prices[p:]: e = x*k + e*(1-k)
    return round(e,2)

def rsi(prices, p=14):
    if len(prices)<p+1: return None
    g=[max(prices[i]-prices[i-1],0) for i in range(1,len(prices))]
    l=[max(prices[i-1]-prices[i],0) for i in range(1,len(prices))]
    ag=statistics.mean(g[-p:]); al=statistics.mean(l[-p:])
    return round(100-(100/(1+ag/al)),2) if al else 100.0

def bollinger(prices, p=20):
    if len(prices)<p: return None,None,None
    r=prices[-p:]; m=statistics.mean(r); s=statistics.stdev(r)
    return round(m-2*s,2), round(m,2), round(m+2*s,2)

def get_technicals(name):
    if not HAS_YF: return None
    sym = name_to_symbol(name)
    try:
        t    = yf.Ticker(f"{sym}.NS")
        hist = t.history(period="1y")
        if hist.empty or len(hist)<30: return None
        closes  = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        cur     = closes[-1]
        # indicators
        r14      = rsi(closes)
        e20      = ema(closes,20)
        e50      = ema(closes,50)
        e200     = ema(closes,200)
        macd_val = None
        e12=ema(closes,12); e26=ema(closes,26)
        if e12 and e26: macd_val=round(e12-e26,2)
        bb_lo,bb_mid,bb_hi = bollinger(closes)
        h52=max(closes[-252:] if len(closes)>=252 else closes)
        l52=min(closes[-252:] if len(closes)>=252 else closes)
        pfh=round(((cur-h52)/h52)*100,1)
        pfl=round(((cur-l52)/l52)*100,1)
        # vol spike from yfinance: recent 5d avg / 20d avg
        vol5  = statistics.mean(volumes[-5:])  if len(volumes)>=5  else None
        vol20 = statistics.mean(volumes[-20:]) if len(volumes)>=20 else None
        vr    = round(vol5/vol20,2) if vol5 and vol20 and vol20>0 else None
        # price momentum: 5d change
        p5  = round(((closes[-1]-closes[-6])/closes[-6])*100,2) if len(closes)>=6 else None
        p20 = round(((closes[-1]-closes[-21])/closes[-21])*100,2) if len(closes)>=21 else None
        # Upward movement score (0–100)
        score = 0; signals = []
        # RSI signals
        if r14:
            if 40<=r14<=60:   score+=15; signals.append(f"RSI neutral ({r14}) — room to run")
            elif r14<40:      score+=20; signals.append(f"RSI oversold ({r14}) — reversal zone")
            elif r14>70:      score-=10; signals.append(f"RSI overbought ({r14}) — caution")
        # EMA signals
        if e20 and e50:
            if cur>e20>e50:   score+=20; signals.append("Price > EMA20 > EMA50 — bullish alignment")
            elif e20>e50 and cur>e50: score+=10; signals.append("Above EMA50, approaching EMA20")
        if e200 and cur>e200: score+=15; signals.append("Above EMA200 — long-term uptrend intact")
        # MACD
        if macd_val and macd_val>0: score+=10; signals.append(f"MACD positive ({macd_val}) — bullish momentum")
        # Volume
        if vr and vr>1.5:     score+=15; signals.append(f"Volume surge ({vr}×) — unusual activity")
        elif vr and vr>1.2:   score+=8;  signals.append(f"Volume slightly elevated ({vr}×)")
        # Bollinger
        if bb_lo and bb_mid:
            if cur<bb_mid and cur>bb_lo: score+=10; signals.append("In lower Bollinger band — potential bounce")
            elif cur>bb_hi:              score-=5;  signals.append("Above upper Bollinger — extended")
        # Price momentum
        if p5 and p5>0:  score+=5; signals.append(f"5-day price momentum: +{p5}%")
        if p20 and p20>0: score+=5
        # From 52w high
        if pfh<-30 and vr and vr>1.3: score+=10; signals.append(f"Down {abs(pfh)}% from 52w high with vol pickup — possible accumulation")
        score = max(0, min(100, score))
        if score>=70:   verdict="🟢 STRONG BUY SIGNAL"
        elif score>=50: verdict="🟡 MODERATE BULLISH"
        elif score>=30: verdict="🟠 WEAK / NEUTRAL"
        else:           verdict="🔴 BEARISH / AVOID"
        return {
            "symbol":sym, "cur":round(cur,2), "rsi":r14,
            "ema20":e20, "ema50":e50, "ema200":e200, "macd":macd_val,
            "bb_lo":bb_lo, "bb_mid":bb_mid, "bb_hi":bb_hi,
            "h52":round(h52,2), "l52":round(l52,2),
            "pfh":pfh, "pfl":pfl,
            "vol_ratio":vr, "p5":p5, "p20":p20,
            "score":score, "verdict":verdict, "signals":signals,
        }
    except Exception as e:
        print(f"    ⚠️  TA failed {name}: {e}"); return None

# ── News ──────────────────────────────────────────────────────────────────────

def get_news(name, max_items=5):
    q   = quote(f"{name} NSE stock India")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    html = http_get(url)
    if not html: return []
    items=[]; n1=name.lower().split()[0]
    for m in re.finditer(r"<item>(.*?)</item>", html, re.DOTALL):
        block = m.group(1)
        t = re.search(r"<title>(.*?)</title>",block)
        d = re.search(r"<pubDate>(.*?)</pubDate>",block)
        if t:
            title = re.sub(r"<[^>]+>","",t.group(1)).strip()
            pub   = d.group(1).strip()[:16] if d else ""
            if title and "Google News" not in title:
                items.append({"title":title,"date":pub})
        if len(items)>=max_items: break
    return items

# ── StockTwits ────────────────────────────────────────────────────────────────

def get_twits(name, max_items=5):
    sym  = name_to_symbol(name)
    url  = f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.NS.json"
    data = http_get(url)
    if not data: return [], None
    try:
        j=json.loads(data); msgs=j.get("messages",[]); items=[]; b=0; br=0
        for m in msgs[:max_items*2]:
            body = m.get("body","").replace("\n"," ")[:140]
            sent = (m.get("entities",{}) or {}).get("sentiment",{}) or {}
            sv   = sent.get("basic","")
            if sv=="Bullish": b+=1
            elif sv=="Bearish": br+=1
            items.append({"text":body,"sent":sv,"date":m.get("created_at","")[:10]})
        tot=b+br
        summary=f"🐂 {b} Bullish / 🐻 {br} Bearish ({round(b/tot*100)}% bull)" if tot else None
        return items[:max_items], summary
    except: return [], None

# ── Reddit ────────────────────────────────────────────────────────────────────

def get_reddit(name):
    sym = name_to_symbol(name)
    url = f"https://www.reddit.com/search.json?q={quote(name+' NSE OR '+sym)}&sort=new&limit=5&t=week"
    data = http_get(url)
    if not data: return []
    try:
        j=json.loads(data); posts=[]
        for p in j.get("data",{}).get("children",[]):
            d=p.get("data",{})
            posts.append({
                "title": d.get("title","")[:120],
                "sub":   d.get("subreddit",""),
                "score": d.get("score",0),
                "url":   f"https://reddit.com{d.get('permalink','')}",
            })
        return posts[:3]
    except: return []

# ── HTML ──────────────────────────────────────────────────────────────────────

def pct(v,d=2):
    if v is None: return "—"
    c="#1a9e6d" if v>0 else "#d94b4b" if v<0 else "#888"
    a="▲" if v>0 else "▼" if v<0 else ""
    return f'<span style="color:{c};font-weight:600">{a}&nbsp;{v:.{d}f}%</span>'

def n(v,d=2):
    if v is None: return "—"
    return f"{v:,.{d}f}"

def freq_bar(count,mx=5):
    return (f'<span style="color:#4a6cf7;letter-spacing:2px">{"█"*count}</span>'
            f'<span style="color:#ddd;letter-spacing:2px">{"░"*(mx-count)}</span>'
            f' <b>{count}/5</b>')

def score_badge(s):
    c="#1a9e6d" if s>=70 else "#f0a500" if s>=50 else "#d94b4b"
    return f'<span style="font-size:20px;font-weight:700;color:{c}">{s}</span><span style="color:#aaa;font-size:11px">/100</span>'

def render_ta(ta):
    if not ta:
        return '<em style="color:#aaa;font-size:12px">Technical data not available (yfinance may not have this ticker)</em>'
    rsi_c="#d94b4b" if ta["rsi"] and ta["rsi"]>70 else "#1a9e6d" if ta["rsi"] and ta["rsi"]<40 else "#555"
    m_c="#1a9e6d" if ta["macd"] and ta["macd"]>0 else "#d94b4b"
    v_c="#1a9e6d" if ta["vol_ratio"] and ta["vol_ratio"]>1.5 else "#555"
    sigs="".join(f'<div style="font-size:12px;padding:3px 0;color:#2d5a27">✓ {s}</div>' for s in ta["signals"]) or '<div style="font-size:12px;color:#aaa">No strong signals</div>'
    return f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px;font-size:12px">
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">RSI(14)</div><div style="font-weight:700;color:{rsi_c}">{ta['rsi'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">MACD</div><div style="font-weight:700;color:{m_c}">{ta['macd'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">Vol Ratio</div><div style="font-weight:700;color:{v_c}">{ta['vol_ratio'] or '—'}×</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">5d / 20d chg</div><div style="font-weight:600">{pct(ta['p5'],1)} / {pct(ta['p20'],1)}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">EMA 20</div><div style="font-weight:600">{ta['ema20'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">EMA 50</div><div style="font-weight:600">{ta['ema50'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">EMA 200</div><div style="font-weight:600">{ta['ema200'] or '—'}</div></div>
      <div style="background:#f8f9ff;padding:8px;border-radius:6px"><div style="color:#888;font-size:10px">From 52w High</div><div style="font-weight:700;color:{'#d94b4b' if ta['pfh']<-20 else '#555'}">{ta['pfh']}%</div></div>
    </div>
    <div style="background:#f0faf0;border:1px solid #c3e6c3;border-radius:6px;padding:10px;margin-bottom:6px">
      <div style="font-size:13px;font-weight:700;margin-bottom:6px">{ta['verdict']}</div>
      {sigs}
    </div>
    <div style="font-size:11px;color:#aaa">BB: {ta['bb_lo']} / {ta['bb_mid']} / {ta['bb_hi']} &nbsp;|&nbsp; 52w: {ta['l52']} – {ta['h52']}</div>"""

def render_news(items):
    if not items: return '<em style="color:#aaa;font-size:12px">No news found</em>'
    return "".join(f'<div style="padding:5px 0;border-bottom:1px solid #f5f5f5;font-size:12px"><span style="color:#999;font-size:10px">{i["date"]}</span><br>{i["title"]}</div>' for i in items)

def render_twits(items, summary):
    if not items: return '<em style="color:#aaa;font-size:12px">No StockTwits data</em>'
    s = f'<div style="font-size:12px;font-weight:600;margin-bottom:6px">{summary}</div>' if summary else ""
    rows="".join(f'<div style="padding:4px 0;border-bottom:1px solid #f5f5f5;font-size:11px"><span style="color:{"#1a9e6d" if i["sent"]=="Bullish" else "#d94b4b" if i["sent"]=="Bearish" else "#888"}">{"🐂" if i["sent"]=="Bullish" else "🐻" if i["sent"]=="Bearish" else "💬"}</span> {i["text"]}</div>' for i in items)
    return s+rows

def render_reddit(posts):
    if not posts: return '<em style="color:#aaa;font-size:12px">No Reddit mentions this week</em>'
    return "".join(f'<div style="padding:5px 0;border-bottom:1px solid #f5f5f5;font-size:11px"><span style="color:#ff6314">r/{p["sub"]}</span> · ↑{p["score"]}<br>{p["title"]}</div>' for p in posts)

def deep_dive_card(name, s, ta, news, twits, twit_sent, reddit):
    sym = name_to_symbol(name)
    score = ta["score"] if ta else 0
    sc="#1a9e6d" if score>=70 else "#f0a500" if score>=50 else "#d94b4b"
    # Daily vol progression
    vol_prog=""
    for d in s["daily_data"]:
        v=d.get("vol")
        v1w=d.get("vol1w")
        if v:
            vstr=f"{v/1e5:.1f}L"
            spike=f" ({v/v1w:.1f}×)" if v1w and v1w>0 else ""
            vol_prog+=f'<span style="background:#f0f4ff;border-radius:4px;padding:2px 6px;margin:2px;font-size:11px">{d["date"][-5:]}: {vstr}{spike}</span>'
    if not vol_prog:
        vol_prog='<span style="font-size:11px;color:#aaa">Vol data not in Screener columns — see yfinance Vol Ratio above</span>'

    return f"""
    <div style="border:1px solid #e8eaf0;border-radius:10px;margin-bottom:24px;overflow:hidden">
      <!-- Header -->
      <div style="background:linear-gradient(90deg,#0f0c29,#302b63);color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center">
        <div>
          <span style="font-size:16px;font-weight:700">{name}</span>
          <span style="font-size:12px;opacity:.6;margin-left:8px">{sym}.NS</span>
        </div>
        <div style="text-align:right">
          <div style="font-size:18px;font-weight:700">₹{n(s['latest_cmp'],1)}</div>
          <div style="font-size:11px;opacity:.7">{freq_bar(s['appearances'])} &nbsp;|&nbsp; Upside Score: {score_badge(score)}</div>
        </div>
      </div>
      <!-- Key metrics row -->
      <div style="display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid #f0f0f0;font-size:12px">
        <div style="padding:8px 12px;border-right:1px solid #f0f0f0"><div style="color:#888;font-size:10px">Avg 1d Ret</div><div style="font-weight:600">{pct(s['avg_ret1d'])}</div></div>
        <div style="padding:8px 12px;border-right:1px solid #f0f0f0"><div style="color:#888;font-size:10px">Week Chg</div><div style="font-weight:600">{pct(s['price_change_week'])}</div></div>
        <div style="padding:8px 12px;border-right:1px solid #f0f0f0"><div style="color:#888;font-size:10px">1Mo Return</div><div style="font-weight:600">{pct(s['latest_ret1m'])}</div></div>
        <div style="padding:8px 12px;border-right:1px solid #f0f0f0"><div style="color:#888;font-size:10px">QoQ Profit</div><div style="font-weight:600">{pct(s['latest_qoqp'])}</div></div>
        <div style="padding:8px 12px;border-right:1px solid #f0f0f0"><div style="color:#888;font-size:10px">ROCE%</div><div style="font-weight:600">{pct(s['latest_roce'])}</div></div>
        <div style="padding:8px 12px"><div style="color:#888;font-size:10px">Mkt Cap</div><div style="font-weight:600">₹{n(s['latest_mktcap'],0) if s['latest_mktcap'] else '—'}Cr</div></div>
      </div>
      <!-- Vol progression -->
      <div style="padding:10px 16px;background:#fafbff;border-bottom:1px solid #f0f0f0">
        <div style="font-size:11px;font-weight:600;color:#1a1a2e;margin-bottom:4px">🔊 Volume Progression This Week</div>
        {vol_prog}
      </div>
      <!-- 3 columns: Technical / News / Social -->
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr">
        <div style="padding:14px 16px;border-right:1px solid #f0f0f0">
          <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:#1a1a2e">📊 Chart Analysis & Upside Score</div>
          {render_ta(ta)}
        </div>
        <div style="padding:14px 16px;border-right:1px solid #f0f0f0">
          <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:#1a1a2e">📰 Latest News</div>
          {render_news(news)}
          <div style="font-size:12px;font-weight:700;margin:12px 0 8px;color:#1a1a2e">🗣 Reddit Mentions</div>
          {render_reddit(reddit)}
        </div>
        <div style="padding:14px 16px">
          <div style="font-size:12px;font-weight:700;margin-bottom:8px;color:#1a1a2e">💬 StockTwits Sentiment</div>
          {render_twits(twits, twit_sent)}
        </div>
      </div>
    </div>"""

def build_html(analysis, tech, news_d, twit_d, reddit_d, week_dates):
    stats   = analysis["stock_stats"]
    wl      = f"{week_dates[0]} → {week_dates[-1]}" if week_dates else "This Week"

    # Summary stats
    all5_badges="".join(f'<span style="display:inline-block;background:#e8f0ff;color:#1a3a8f;border-radius:20px;padding:3px 12px;margin:3px;font-size:13px;font-weight:500">{n}</span>' for n in analysis["appeared_all5"]) or "<em style='color:#aaa'>None this week</em>"

    # Earnings catalyst table
    earn_rows="".join(f"""<tr>
      <td style="text-align:left;font-weight:500">{nm}</td>
      <td>{pct(s.get('latest_qoqp'))}</td><td>{pct(s.get('latest_qoqs'))}</td>
      <td>{pct(s.get('latest_profit'))}</td><td>{s['appearances']}/5</td>
      <td>₹{n(s.get('latest_cmp'),1)}</td>
    </tr>""" for nm,s in analysis["earnings_cat"][:10])

    # BP radar table (all 2+ day stocks)
    bp_rows="".join(f"""<tr>
      <td style="text-align:left;font-weight:600">{nm}</td>
      <td>{freq_bar(s['appearances'])}</td>
      <td>{pct(s.get('avg_ret1d'))}</td>
      <td>{pct(s.get('price_change_week'))}</td>
      <td>{n(s.get('scr_vol_spike'),1) if s.get('scr_vol_spike') else (tech.get(nm,{}) or {}).get('vol_ratio') or '—'}×</td>
      <td>{pct(s.get('latest_roce'))}</td>
      <td>{pct(s.get('latest_qoqp'))}</td>
      <td>{score_badge(tech[nm]['score']) if tech.get(nm) else '—'}</td>
    </tr>""" for nm,s in analysis["bp_ranked"] if s["appearances"]>=2)

    # Deep dive cards for ALL 2+ day stocks
    dive_cards=""
    for nm in analysis["appeared_2p"]:
        s = stats[nm]
        ta= tech.get(nm)
        nws=news_d.get(nm,[])
        tw,tws=twit_d.get(nm,([], None))
        rd=reddit_d.get(nm,[])
        dive_cards += deep_dive_card(nm, s, ta, nws, tw, tws, rd)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Analysis — {wl}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;padding:20px;color:#1a1a1a}}
  .wrap{{max-width:1500px;margin:0 auto}}
  .top{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:#fff;padding:28px 32px;border-radius:12px 12px 0 0}}
  .top h1{{font-size:22px;font-weight:700}}.top p{{font-size:13px;opacity:.6;margin-top:6px}}
  .meta{{display:flex;gap:20px;padding:12px 32px;background:#f8f9ff;border:1px solid #e8eaf0;border-top:none;font-size:13px;color:#555;flex-wrap:wrap}}
  .meta a{{color:#4a6cf7}}
  .sec{{background:#fff;border:1px solid #e8eaf0;border-radius:10px;margin:16px 0;overflow:hidden}}
  .sh{{padding:14px 24px;border-bottom:1px solid #f0f0f0;background:#fafbff}}
  .sh h2{{font-size:14px;font-weight:700;color:#1a1a2e}}.sh p{{font-size:11px;color:#888;margin-top:3px}}
  .sb{{padding:18px 24px}}
  .sg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}}
  .sb2{{background:#f8f9ff;border-radius:8px;padding:12px 16px;border:1px solid #e8eaf0}}
  .sb2 .v{{font-size:22px;font-weight:700;color:#1a1a2e}}.sb2 .l{{font-size:11px;color:#888;margin-top:3px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  thead th{{background:#1a1a2e;color:#c8d0ff;padding:10px 14px;text-align:right;font-weight:500;font-size:12px;white-space:nowrap}}
  thead th:first-child{{text-align:left}}
  tbody td{{padding:9px 14px;border-bottom:1px solid #f5f5f5;text-align:right;white-space:nowrap}}
  tbody td:first-child{{text-align:left}}
  tbody tr:hover td{{background:#f5f7ff}}
  .foot{{padding:12px;font-size:11px;color:#bbb;text-align:center;margin-top:8px}}
</style></head><body>
<div class="wrap">
  <div class="top">
    <h1>📊 Weekly Breakout & Big Player Analysis</h1>
    <p>Screener Momentum Screen · {wl} · {analysis['total_unique']} unique stocks · {len(analysis['dates'])} trading days · {len(analysis['appeared_2p'])} stocks appeared 2+ days</p>
  </div>
  <div class="meta">
    <span>📅 <strong>{", ".join(analysis['dates'])}</strong></span>
    <span>🔗 <a href="{SCREEN_URL}">screener.in/screens/3664072/screen1</a></span>
  </div>

  <div class="sec"><div class="sh"><h2>📈 Week at a Glance</h2></div><div class="sb">
    <div class="sg">
      <div class="sb2"><div class="v">{analysis['total_unique']}</div><div class="l">Unique stocks</div></div>
      <div class="sb2"><div class="v">{len(analysis['appeared_all5'])}</div><div class="l">Appeared all 5 days</div></div>
      <div class="sb2"><div class="v">{len(analysis['appeared_2p'])}</div><div class="l">Appeared 2+ days</div></div>
      <div class="sb2"><div class="v">{len(analysis['earnings_cat'])}</div><div class="l">Earnings catalysts</div></div>
    </div>
  </div></div>

  <div class="sec"><div class="sh"><h2>🔁 Appeared All 5 Days</h2><p>Highest conviction — triggered every day this week</p></div>
  <div class="sb">{all5_badges}</div></div>

  <div class="sec"><div class="sh"><h2>💥 Earnings Catalysts</h2><p>Strong QoQ profit + appearing 2+ days</p></div>
  <div style="padding:0 24px 20px"><table>
    <thead><tr><th>Stock</th><th>QoQ Profit%</th><th>QoQ Sales%</th><th>Profit Growth%</th><th>Days</th><th>CMP</th></tr></thead>
    <tbody>{earn_rows}</tbody>
  </table></div></div>

  <div class="sec"><div class="sh"><h2>🎯 Repeated Breakout Stocks — Summary</h2><p>All stocks appearing 2+ days with upside score from technical analysis</p></div>
  <div style="padding:0 24px 20px"><table>
    <thead><tr><th>Stock</th><th>Frequency</th><th>Avg 1d Ret</th><th>Week Chg</th><th>Vol Spike</th><th>ROCE%</th><th>QoQ Profit%</th><th>Upside Score</th></tr></thead>
    <tbody>{bp_rows}</tbody>
  </table></div></div>

  <div class="sec"><div class="sh"><h2>⭐ Deep Dives — All Stocks Appearing 2+ Days</h2>
  <p>Chart analysis · Upside score · Volume progression · News · StockTwits · Reddit — for every stock that showed up more than once</p></div>
  <div class="sb">{dive_cards}</div></div>

  <div class="foot">Auto-generated · GitHub Actions · Screener.in · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div></body></html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today      = date.today().isoformat()
    week_dates = get_week_dates()
    print(f"\n🔍 Weekly Analysis v3 — {week_dates[0]} to {week_dates[-1]}")

    reports = []
    for d in week_dates:
        r = load_report(d)
        if r:
            print(f"  📂 {d} — {r['total_stocks']} stocks")
            reports.append(r)
        else:
            print(f"  ⚠️  No report: {d}")

    if not reports:
        print("❌ No reports found. Exiting."); return

    analysis = analyse_week(reports)
    targets  = analysis["appeared_2p"]
    print(f"\n  📊 {analysis['total_unique']} unique stocks")
    print(f"  🎯 {len(targets)} stocks to deep-dive: {targets}\n")

    tech_d={};  news_d={}; twit_d={}; reddit_d={}

    if HAS_YF:
        print(f"  📡 Fetching technicals for {len(targets)} stocks...")
        for nm in targets:
            print(f"    → {nm}")
            tech_d[nm] = get_technicals(nm)
            time.sleep(0.4)

    print(f"\n  📰 Fetching news...")
    for nm in targets:
        news_d[nm] = get_news(nm)
        time.sleep(0.4)

    print(f"\n  💬 Fetching StockTwits...")
    for nm in targets:
        twit_d[nm] = get_twits(nm)
        time.sleep(0.3)

    print(f"\n  🗣 Fetching Reddit...")
    for nm in targets:
        reddit_d[nm] = get_reddit(nm)
        time.sleep(0.3)

    week_dir = os.path.join(OUTPUT_DIR, "weekly")
    os.makedirs(week_dir, exist_ok=True)
    base = os.path.join(week_dir, f"week_{week_dates[0]}")

    html = build_html(analysis, tech_d, news_d, twit_d, reddit_d, week_dates)
    with open(base+"_analysis.html","w",encoding="utf-8") as f:
        f.write(html)
    print(f"\n  ✅ HTML → {base}_analysis.html")

    with open(base+"_analysis.json","w",encoding="utf-8") as f:
        out={k:v for k,v in analysis.items() if k not in("stock_stats","bp_ranked")}
        out["stock_stats_summary"]={n:{k:v for k,v in s.items() if k!="daily_data"} for n,s in analysis["stock_stats"].items()}
        out["conviction_picks"]=[(n,{k:v for k,v in s.items() if k!="daily_data"}) for n,s in analysis["bp_ranked"] if s["appearances"]>=2]
        json.dump(out,f,indent=2,ensure_ascii=False,default=str)
    print(f"  ✅ JSON → {base}_analysis.json")
    print(f"\n✅ Done! {len(targets)} stocks deep-dived.")

if __name__=="__main__":
    main()
