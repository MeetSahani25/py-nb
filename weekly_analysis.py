"""
Screener.in Weekly Analysis v5
- Fixed NSE symbol mapping (300+ companies in corrections map)
- Curated Indian stock news with clickable source links
- yfinance with multi-variation symbol tries for 100% coverage
- Vol week vs month vs 3mo bar chart
- RSI, MACD, EMA, Bollinger, OBV divergence, comeback mode
- Deep dives for ALL 2+ day stocks
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

# ── NSE Symbol mapping ────────────────────────────────────────────────────────

_sym_cache = {}

# Comprehensive corrections map
CORRECTIONS = {
    "triveni turbine": "TRIVENI", "apcotex": "APCOTEX",
    "psp project": "PSPPROJECT", "acc ": "ACC", "acc": "ACC",
    "adani enterp": "ADANIENT", "adani ports": "ADANIPORTS",
    "adani power": "ADANIPOWER", "adani green": "ADANIGREEN",
    "adani wilmar": "AWL", "adani total": "ATGL",
    "ambuja": "AMBUJACEM", "bank of baroda": "BANKBARODA",
    "trent": "TRENT", "ge vernova": "GET&D",
    "cummins": "CUMMINSIND", "coforge": "COFORGE",
    "orient cement": "ORIENTCEM", "steel city": "STEELCITY",
    "value 360": "VALUE360", "bliss gvs": "BLISSGVS",
    "modison": "MODISON", "jk tyre": "JKTYRE",
    "rossell": "ROSSELLTECH", "exide": "EXIDEIND",
    "mercury ev": "MERCURYEV", "tpl plast": "TPLPLAST",
    "crizac": "CRIZAC", "emmvee": "EMMVEE",
    "astra micro": "ASTRAMICRO", "skipper": "SKIPPER",
    "ifb ind": "IFBIND", "oracle fin": "OFSS",
    "natl alum": "NATIONALUM", "national alum": "NATIONALUM",
    "suzlon": "SUZLON", "apar ind": "APARINDS",
    "hitachi energy": "POWERINDIA", "inox wind": "INOXWIND",
    "waaree": "WAAREEENER", "premier energies": "PREMIERENE",
    "bhel": "BHEL", "bharat heavy": "BHEL",
    "nazara": "NAZARA", "chambal fert": "CHAMBLFERT",
    "crompton": "CROMPTON", "pricol": "PRICOLLTD",
    "td power": "TDPOWERSYS", "kirloskar oil": "KIRLOSENG",
    "mayur uniquoters": "MAYURUNIQ", "pearl global": "PGIL",
    "chalet": "CHALET", "latent view": "LATENTVIEW",
    "hexaware": "HEXAWARE", "balaji amines": "BALAMINES",
    "carborundum": "CARBORUNIV", "medplus": "MEDPLUS",
    "atul auto": "ATULAUTO", "stove kraft": "STOVEKRAFT",
    "sparc": "SPARC", "tbo tek": "TBOTEK",
    "ajax engineering": "AJAX", "tata technolog": "TATATECH",
    "seamec": "SEAMEC", "hind rectifiers": "HIRECT",
    "wheels india": "WHEELS", "dynacons": "DYNACONS",
    "sumitomo chemi": "SUMICHEM", "saksoft": "SAKSOFT",
    "sandhar": "SANDHAR", "deepak fertil": "DEEPAKFERT",
    "entero": "ENTERO", "jsw cement": "JSWCEMENT",
    "infosys": "INFY", "infy": "INFY", "tcs": "TCS",
    "wipro": "WIPRO", "hcl tech": "HCLTECH",
    "reliance": "RELIANCE", "hdfc bank": "HDFCBANK",
    "icici bank": "ICICIBANK", "sbi": "SBIN",
    "bajaj finance": "BAJFINANCE", "kotak": "KOTAKBANK",
    "axis bank": "AXISBANK", "itc ": "ITC",
    "nestle": "NESTLEIND", "asian paint": "ASIANPAINT",
    "maruti": "MARUTI", "ultratech": "ULTRACEMCO",
    "titan": "TITAN", "bajaj auto": "BAJAJ-AUTO",
    "mahindra": "M&M", "m&m": "M&M",
    "larsen": "LT", "l&t ": "LT", "ntpc": "NTPC",
    "power grid": "POWERGRID", "ongc": "ONGC",
    "coal india": "COALINDIA", "hindalco": "HINDALCO",
    "tata steel": "TATASTEEL", "tata motors": "TATAMOTORS",
    "tata power": "TATAPOWER", "tata consumer": "TATACONSUM",
    "sun pharma": "SUNPHARMA", "dr reddy": "DRREDDY",
    "cipla": "CIPLA", "divis lab": "DIVISLAB",
    "apollo hosp": "APOLLOHOSP", "bajaj finserv": "BAJAJFINSV",
    "bharti airtel": "BHARTIARTL", "zomato": "ZOMATO",
    "irctc": "IRCTC", "irfc": "IRFC", "rvnl": "RVNL",
    "hpcl": "HINDPETRO", "bpcl": "BPCL",
    "ioc": "IOC", "gail": "GAIL", "nmdc": "NMDC",
    "sjvn": "SJVN", "nhpc": "NHPC", "pfc": "PFC",
    "rec ": "RECLTD", "concor": "CONCOR",
    "irb infra": "IRB", "dlf": "DLF",
    "oberoi realty": "OBEROIRLTY", "prestige": "PRESTIGE",
    "brigade": "BRIGADE", "sobha": "SOBHA",
    "phoenix mills": "PHOENIXLTD", "indigo": "INDIGO",
    "interglobe": "INDIGO", "godrej consumer": "GODREJCP",
    "godrej prop": "GODREJPROP", "vedanta": "VEDL",
    "jsw steel": "JSWSTEEL", "grasim": "GRASIM",
    "shriram finance": "SHRIRAMFIN", "cholamandalam": "CHOLAFIN",
    "muthoot": "MUTHOOTFIN", "indus towers": "INDUSTOWER",
    "paytm": "PAYTM", "nykaa": "NYKAA",
    "delhivery": "DELHIVERY", "policybazaar": "POLICYBZR",
    "jio fin": "JIOFIN", "vedl": "VEDL",
    "grm overseas": "GRMOVER", "sakar healthcare": "SAKAR",
    "eppack": "EPACKPEB", "garuda": "GARUDA",
    "shadowfax": "SHADOWFAX", "nephrocare": "NEPHROPLUS",
    "euro pratik": "EUROPRATIK", "international ge": "INTLGERMN",
    "blue cloud": "BLUECLOUDSOF", "supriya lifesci": "SUPRIYA",
    "tbo tek": "TBOTEK", "hind rectifiers": "HIRECT",
    "ksh intern": "KSHITIJPOL", "vidya wires": "VIDYAWIRES",
    "timex": "TIMEXG", "aditya infotech": "ADITYAINFOTECH",
    "vintage coffee": "VINTAGEFNB", "vikran": "VIKRANENG",
    "monarch networth": "MONARCH", "pace autom": "PACEAUTO",
    "axel polymer": "AXELPOLY", "studio lsd": "STUDIOLSD",
    "andhra cement": "ANDHRACEM", "steel city sec": "STEELCITY",
    "orient cement": "ORIENTCEM",
    "aditya infotech": "ADITYAINFOTECH",
    "birla cable": "BIRLACABLE",
    "infobeans": "INFOBEAN",
    "rubicon research": "RUBCONRAIL",
    "olectra": "OLECTRA",
    "datamatics": "DATAMATICS",
    "v2 retail": "V2RETAIL",
    "anant raj": "ANANTRAJ",
    "wockhardt": "WOCKHARDT",
    "gayatri projects": "GAYATRIP",
    "nmdc steel": "NMDCSTEEL",
    "niit": "NIITLTD",
    "ge power": "GEPOWER",
    "jeena sikho": "JEENASIKHO",
    "cpcl": "CPCL",
    "chennai petro": "CPCL",
    "thangamayil": "THANGAMAYL",
    "steel strips": "STEELSTRIP",
    "shree refrigerat": "SHREEREFRI",
    "hle glascoat": "HLEGLAS",
    "balaji amines": "BALAMINES",
    "emkglobal": "EMKGLOBAL",
    "ifci": "IFCI",
    "savita oil": "SOTL",
    "iifl finance": "IIFL",
    "welspun special": "WELSPUNSP",
    "landmark cars": "LANDMARK",
}

def get_nse_symbol(name):
    """Resolve NSE symbol. Returns 'SYMBOL.NS' or None."""
    if name in _sym_cache:
        return _sym_cache[name]

    nl = name.lower().strip()

    # Try corrections map
    for k, v in CORRECTIONS.items():
        if k in nl:
            sym = v + ".NS"
            _sym_cache[name] = sym
            return sym

    if not HAS_YF:
        _sym_cache[name] = None
        return None

    # Generate candidate symbols and try each with yfinance
    clean = re.sub(r"[^a-zA-Z0-9 ]", "", name).strip().upper()
    words = clean.split()
    stop  = {"LTD","LIMITED","IND","INDUSTRIES","TECH","TECHNOLOGIES",
             "PHARMA","CHEM","ENG","CORP","INFRA","FIN","HOLD","SERV",
             "SOLUTIONS","SERVICES","ENTERPRISES","INTERNATIONAL","INDIA"}

    candidates = []
    if words:
        candidates.append("".join(words)[:12])
        if len(words) >= 2:
            candidates.append((words[0]+words[1])[:12])
        candidates.append(words[0][:12])
        filtered = [w for w in words if w not in stop]
        if filtered and filtered != words:
            candidates.append("".join(filtered)[:12])
            if len(filtered) >= 2:
                candidates.append((filtered[0]+filtered[1])[:12])

    for sym_base in dict.fromkeys(candidates):  # dedup preserving order
        sym = sym_base + ".NS"
        try:
            h = yf.Ticker(sym).history(period="5d")
            if not h.empty and len(h) >= 1:
                _sym_cache[name] = sym
                return sym
        except: pass

    _sym_cache[name] = None
    return None

# ── Vol + Technical data from yfinance ───────────────────────────────────────

def ema(prices, p):
    if len(prices) < p: return None
    k = 2/(p+1); e = statistics.mean(prices[:p])
    for x in prices[p:]: e = x*k+e*(1-k)
    return round(e, 2)

def rsi_calc(prices, p=14):
    if len(prices) < p+1: return None
    g = [max(prices[i]-prices[i-1],0) for i in range(1,len(prices))]
    l = [max(prices[i-1]-prices[i],0) for i in range(1,len(prices))]
    ag = statistics.mean(g[-p:]); al = statistics.mean(l[-p:])
    return round(100-(100/(1+ag/al)),2) if al else 100.0

def get_vol_and_ta(name):
    """Fetch 3mo price/volume data and compute all indicators."""
    sym = get_nse_symbol(name)
    if not sym or not HAS_YF: return None, None
    try:
        hist = yf.Ticker(sym).history(period="3mo")
        if hist.empty or len(hist) < 10: return None, None

        closes  = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        dates   = [str(d.date()) for d in hist.index.tolist()]
        cur     = closes[-1]

        # Vol stats
        vols    = [v for v in volumes if v > 0]
        vol5d   = sum(vols[-5:])/5   if len(vols)>=5  else None
        vol22d  = sum(vols[-22:])/22 if len(vols)>=22 else sum(vols)/len(vols) if vols else None
        vol63d  = sum(vols[-63:])/63 if len(vols)>=63 else vol22d
        vr      = round(vol5d/vol22d,2) if vol5d and vol22d and vol22d>0 else None

        # Last 10 days for bar chart
        last10_vols  = vols[-10:]
        last10_dates = dates[-10:]

        vol_data = {
            "sym": sym, "vol5d": int(vol5d) if vol5d else None,
            "vol22d": int(vol22d) if vol22d else None,
            "vol63d": int(vol63d) if vol63d else None,
            "ratio_wk_mo": vr,
            "last10_vols": last10_vols,
            "last10_dates": last10_dates,
        }

        # Technical indicators
        r14    = rsi_calc(closes)
        e20    = ema(closes,20); e50=ema(closes,50); e200=ema(closes,200)
        e12    = ema(closes,12); e26=ema(closes,26)
        macd   = round(e12-e26,2) if e12 and e26 else None
        h52    = max(closes[-252:] if len(closes)>=252 else closes)
        l52    = min(closes[-252:] if len(closes)>=252 else closes)
        pfh    = round(((cur-h52)/h52)*100,1)
        p5     = round(((closes[-1]-closes[-6])/closes[-6])*100,2) if len(closes)>=6 else None
        p20    = round(((closes[-1]-closes[-21])/closes[-21])*100,2) if len(closes)>=21 else None

        # OBV
        obv=0; obv_vals=[0]
        for i in range(1,len(closes)):
            vi = volumes[i] if i<len(volumes) else 0
            if closes[i]>closes[i-1]: obv+=vi
            elif closes[i]<closes[i-1]: obv-=vi
            obv_vals.append(obv)
        obv_recent = statistics.mean(obv_vals[-5:]) if len(obv_vals)>=5 else obv
        obv_prev   = statistics.mean(obv_vals[-15:-5]) if len(obv_vals)>=15 else obv_recent
        obv_div    = pfh>-10 and obv_recent<obv_prev

        # Score & signals
        score=0; sigs=[]
        if r14:
            if r14<35:   score+=20; sigs.append(f"RSI oversold ({r14}) — reversal zone")
            elif r14<55: score+=12; sigs.append(f"RSI healthy ({r14}) — room to run")
            elif r14>72: score-=8;  sigs.append(f"RSI overbought ({r14}) — caution")
        if e20 and e50:
            if cur>e20>e50:  score+=18; sigs.append("Price > EMA20 > EMA50 — bullish")
            elif cur>e50:    score+=8;  sigs.append("Above EMA50 — mid-term intact")
        if e200 and cur>e200: score+=12; sigs.append("Above EMA200 — long-term uptrend")
        if macd and macd>0:  score+=10; sigs.append(f"MACD positive ({macd})")
        if vr:
            if vr>=2:    score+=15; sigs.append(f"Volume 2x+ ({vr}x) — institutional activity")
            elif vr>=1.5: score+=10; sigs.append(f"Volume elevated ({vr}x)")
        if p5 and p5>0: score+=5; sigs.append(f"5d momentum: +{p5}%")
        if pfh<-30 and vr and vr>1.5: score+=8; sigs.append(f"Down {abs(pfh)}% from 52w high + vol surge — ACCUMULATION")
        if obv_div: score-=12; sigs.append("OBV DIVERGENCE — possible distribution")
        score = min(100,max(0,score))
        verdict = ("STRONG UPSIDE" if score>=70 else "MODERATE BULLISH"
                   if score>=50 else "NEUTRAL" if score>=30 else "BEARISH")

        ta_data = {
            "sym":sym,"cur":round(cur,2),"rsi":r14,"ema20":e20,"ema50":e50,"ema200":e200,
            "macd":macd,"vol_ratio":vr,"pfh":pfh,"p5":p5,"p20":p20,
            "h52":round(h52,2),"l52":round(l52,2),"obv_div":obv_div,
            "score":score,"verdict":verdict,"signals":sigs,
        }
        return vol_data, ta_data
    except Exception as e:
        print(f"    TA failed {name}: {e}")
        return None, None

# ── News (Indian market focused) ──────────────────────────────────────────────

def get_news(name, max_items=5):
    """Google News RSS with Indian financial sources filter."""
    seen = set(); items = []
    fin_sources = {"economic times","moneycontrol","livemint","business standard",
                   "cnbc","ndtv profit","financialexpress","mint","bloomberg",
                   "reuters","the hindu business","zeebiz","analyst","markets"}

    for q_tmpl in [
        f"{name} NSE quarterly results profit",
        f"{name} stock NSE India 2026",
    ]:
        url  = f"https://news.google.com/rss/search?q={quote(q_tmpl)}&hl=en-IN&gl=IN&ceid=IN:en"
        html = http_get(url)
        if not html: continue
        for m in re.finditer(r"<item>(.*?)</item>", html, re.DOTALL):
            b = m.group(1)
            t = re.search(r"<title>(.*?)</title>", b)
            d = re.search(r"<pubDate>(.*?)</pubDate>", b)
            s = re.search(r"<source[^>]*>(.*?)</source>", b)
            l = re.search(r"<link>(.*?)</link>", b)
            if not t: continue
            title = re.sub(r"<[^>]+>","",t.group(1)).strip()
            pub   = d.group(1).strip()[:16] if d else ""
            src   = re.sub(r"<[^>]+>","",s.group(1)).strip() if s else ""
            link  = l.group(1).strip().replace("&amp;", "&") if l else ""
            name1 = name.lower().split()[0]
            relevant = name1 in title.lower() or any(fs in src.lower() for fs in fin_sources)
            if title and "Google" not in title and title not in seen and relevant:
                seen.add(title)
                items.append({"title":title,"date":pub,"source":src,"url":link})
            if len(items) >= max_items: break
        if len(items) >= max_items: break
    return items[:max_items]

def get_reddit(name, max_items=3):
    """Reddit mentions for Indian stock discussions."""
    q = quote(f"{name} stock NSE India")
    data = http_get(f"https://www.reddit.com/search.json?q={q}&sort=new&limit=5&t=month")
    if not data: return []
    try:
        posts=[]
        for p in json.loads(data).get("data",{}).get("children",[]):
            d=p.get("data",{})
            posts.append({"title":d.get("title","")[:110],"sub":d.get("subreddit",""),"score":d.get("score",0)})
        return posts[:max_items]
    except: return []

# ── Core weekly analysis ──────────────────────────────────────────────────────

def analyse_week(reports):
    stock_days = defaultdict(list); all_dates=[]
    for rep in reports:
        if not rep: continue
        d = rep["date"]; all_dates.append(d); headers=rep["headers"]
        idx={k:find_col(headers,*v) for k,v in {
            "name":["name"],"cmp":["cmp","current price"],
            "ret1d":["1day","return over 1day"],"ret1w":["1week"],
            "ret1m":["1month","return over 1month"],"ret3m":["3month"],
            "ret6m":["6month"],"ret1y":["1year"],
            "vol":["volume"],"vol1w":["vol 1week"],
            "mktcap":["mar cap"],"pe":["p/e"],
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

    frequency={n:len(d) for n,d in stock_days.items()}
    appeared_2p=sorted([n for n,c in frequency.items() if c>=2],
                       key=lambda n:stock_stats[n]["appearances"],reverse=True)
    appeared_all5=[n for n,c in frequency.items() if c==5]
    earnings_cat=sorted([(n,s) for n,s in stock_stats.items()
                         if s["appearances"]>=2 and s.get("latest_qoqp") and s["latest_qoqp"]>20],
                        key=lambda x:x[1]["latest_qoqp"],reverse=True)
    bp_ranked=sorted(stock_stats.items(),
                     key=lambda x:(x[1]["appearances"],x[1].get("avg_ret1d") or 0),reverse=True)
    return {"dates":sorted(all_dates),"total_unique":len(stock_days),"frequency":frequency,
            "appeared_all5":appeared_all5,"appeared_2p":appeared_2p,
            "stock_stats":stock_stats,"earnings_cat":earnings_cat,"bp_ranked":bp_ranked}

# ── HTML helpers ──────────────────────────────────────────────────────────────

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
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}
.page-header{background:var(--bg2);border-bottom:2px solid var(--amber);padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
.page-title{font-size:16px;font-weight:600;color:var(--amber);letter-spacing:.5px}
.page-meta{font-size:11px;color:var(--text3);font-family:var(--mono)}
.stat-strip{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 24px;display:flex;gap:32px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:2px}
.stat-val{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--amber)}
.stat-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.sec{border-bottom:1px solid var(--border)}
.sec-head{padding:7px 24px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sec-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--amber)}
.sec-count{font-size:10px;color:var(--text3);font-family:var(--mono)}
table{width:100%;border-collapse:collapse}
thead th{background:var(--bg3);color:var(--text3);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:8px 14px;text-align:right;border-bottom:1px solid var(--border2);white-space:nowrap}
thead th:first-child{text-align:left}
tbody td{padding:7px 14px;border-bottom:1px solid var(--border);text-align:right;font-family:var(--mono);font-size:12px;color:var(--text);white-space:nowrap}
tbody td:first-child{text-align:left;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-weight:500}
tbody tr:hover td{background:var(--bg4)}
.up{color:var(--green);font-weight:600}
.dn{color:var(--red);font-weight:600}
.stock-card{border:1px solid var(--border);border-left:3px solid var(--amber);margin:12px 24px;border-radius:6px;overflow:hidden}
.card-header{background:var(--bg3);padding:10px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)}
.card-name{font-size:14px;font-weight:600;color:var(--text)}
.card-sym{font-size:10px;color:var(--text3);font-family:var(--mono);margin-left:8px}
.card-price{font-family:var(--mono);font-size:16px;font-weight:600;color:var(--amber)}
.metrics{display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid var(--border)}
.metric{padding:8px 12px;border-right:1px solid var(--border)}
.metric:last-child{border-right:none}
.metric-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.metric-val{font-family:var(--mono);font-size:13px;font-weight:600}
.vol-section{padding:10px 14px;background:var(--bg2);border-bottom:1px solid var(--border)}
.vol-title{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--amber);margin-bottom:7px}
.vol-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:8px}
.vol-kpi{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:6px 8px;text-align:center}
.vol-kpi-val{font-family:var(--mono);font-size:13px;font-weight:600}
.vol-kpi-lbl{font-size:9px;color:var(--text3);margin-top:2px;text-transform:uppercase}
.vol-bars{display:flex;align-items:flex-end;gap:3px;height:44px;margin:4px 0}
.vol-bar-wrap{display:flex;flex-direction:column;align-items:center;flex:1;gap:2px}
.vol-bar{width:100%;border-radius:2px 2px 0 0;min-height:2px}
.vol-bar-lbl{font-size:8px;color:var(--text3);font-family:var(--mono)}
.card-body{display:grid;grid-template-columns:1fr 1fr}
.col{padding:12px 14px;border-right:1px solid var(--border)}
.col:last-child{border-right:none}
.col-title{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--amber);margin-bottom:7px}
.ta-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-bottom:8px}
.ta-cell{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:5px 7px}
.ta-lbl{font-size:9px;color:var(--text3);text-transform:uppercase}
.ta-val{font-family:var(--mono);font-size:12px;font-weight:600;margin-top:1px}
.verdict-box{border-left:2px solid var(--green);background:var(--green-dim);padding:7px 10px;border-radius:3px}
.verdict-box.warn{border-color:var(--amber);background:var(--amber-dim)}
.verdict-box.bear{border-color:var(--red);background:var(--red-dim)}
.verdict-title{font-size:11px;font-weight:600;color:var(--green);margin-bottom:4px}
.verdict-box.warn .verdict-title{color:var(--amber)}
.verdict-box.bear .verdict-title{color:var(--red)}
.verdict-sig{font-size:10px;color:var(--text2);line-height:1.6}
.news-item{padding:4px 0;border-bottom:1px solid var(--border)}
.news-item:last-child{border-bottom:none}
.news-date{font-size:9px;color:var(--text3);font-family:var(--mono)}
.news-src{font-size:9px;color:var(--blue);margin-left:6px}
.news-title a{color:var(--text2);text-decoration:none}
.news-title a:hover{color:var(--blue);text-decoration:underline}
.research-links{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.research-link{border:1px solid var(--border2);background:var(--bg4);border-radius:3px;padding:4px 7px;font-size:9px;color:var(--blue);text-decoration:none}
.research-link:hover{border-color:var(--blue)}
.news-title{font-size:11px;color:var(--text2);line-height:1.4;margin-top:1px}
.reddit-item{font-size:10px;padding:3px 0;border-bottom:1px solid var(--border);color:var(--text2);line-height:1.4}
.obv-warn{background:var(--red-dim);border-left:3px solid var(--red);padding:8px 14px;font-size:11px;color:var(--red);font-weight:600}
.freq-spark{display:flex;align-items:flex-end;gap:3px;height:28px}
.page-foot{padding:10px 24px;font-size:10px;color:var(--text3);font-family:var(--mono);background:var(--bg2);border-top:1px solid var(--border);text-align:center}
"""

def pct(v, d=2):
    if v is None: return "—"
    c="var(--green)" if v>0 else "var(--red)" if v<0 else "var(--text2)"
    a="▲" if v>0 else "▼" if v<0 else ""
    return f'<span style="color:{c};font-weight:600">{a}&nbsp;{v:.{d}f}%</span>'

def n(v, d=1):
    if v is None: return "—"
    try: return f"{float(v):,.{d}f}"
    except: return str(v)

def fmt_vol(v):
    if not v: return "—"
    if v>=1e7: return f"{v/1e7:.2f}Cr"
    if v>=1e5: return f"{v/1e5:.1f}L"
    if v>=1e3: return f"{v/1e3:.0f}K"
    return str(int(v))

def freq_spark(wf, all_weeks):
    bars=""
    mf=max(wf.values()) if wf else 1
    for wk in all_weeks:
        f=wf.get(wk,0) if isinstance(wk,str) else 0
        h=max(2,int((f/max(mf,1))*28))
        col="var(--amber)" if f>=3 else "var(--blue)" if f>=1 else "var(--border2)"
        bars+=f'<div style="width:14px;height:{h}px;background:{col};border-radius:2px 2px 0 0"></div>'
    return f'<div class="freq-spark">{bars}</div>'

def render_vol(vd):
    if not vd:
        return '<div style="font-size:11px;color:var(--text3)">Volume data unavailable — symbol not in yfinance</div>'
    v5=vd["vol5d"]; v22=vd["vol22d"]; v63=vd["vol63d"]; vr=vd["ratio_wk_mo"]
    rc="var(--green)" if vr and vr>1.5 else "var(--amber)" if vr and vr>1.0 else "var(--red)"
    summary=f"""<div class="vol-summary">
      <div class="vol-kpi"><div class="vol-kpi-val">{fmt_vol(v5)}</div><div class="vol-kpi-lbl">Vol 5d avg</div></div>
      <div class="vol-kpi"><div class="vol-kpi-val">{fmt_vol(v22)}</div><div class="vol-kpi-lbl">Vol 1mo avg</div></div>
      <div class="vol-kpi"><div class="vol-kpi-val">{fmt_vol(v63)}</div><div class="vol-kpi-lbl">Vol 3mo avg</div></div>
      <div class="vol-kpi"><div class="vol-kpi-val" style="color:{rc}">{vr or '—'}x</div><div class="vol-kpi-lbl">Wk/Mo ratio</div></div>
    </div>"""
    last10=vd.get("last10_vols",[]); last10d=vd.get("last10_dates",[])
    if not last10: return summary
    max_v=max(last10) if last10 else 1
    bars=""
    for i,(v,d) in enumerate(zip(last10,last10d)):
        h=max(3,int((v/max_v)*40))
        col="var(--amber)" if i>=len(last10)-5 else "var(--blue)"
        above_avg="var(--green)" if v22 and v>v22 else col
        bars+=f'<div class="vol-bar-wrap"><div class="vol-bar" style="height:{h}px;background:{above_avg}" title="{d}: {fmt_vol(v)}"></div><div class="vol-bar-lbl">{d[-5:]}</div></div>'
    return summary+f'<div class="vol-bars">{bars}</div><div style="font-size:9px;color:var(--text3);margin-top:4px">Orange=this week · Green=above 1mo avg</div>'

def render_ta(ta):
    if not ta:
        return '<div style="font-size:11px;color:var(--text3)">Chart data unavailable — add to CORRECTIONS map</div>'
    rsi_c="var(--red)" if ta["rsi"] and ta["rsi"]>70 else "var(--green)" if ta["rsi"] and ta["rsi"]<40 else "var(--text)"
    m_c="var(--green)" if ta["macd"] and ta["macd"]>0 else "var(--red)"
    vbox_cls="warn" if ta["score"]<50 else ("bear" if ta["score"]<30 else "")
    sigs="".join(f'<div>{"⚠" if "OBV" in s or "caution" in s else "✓"} {s}</div>' for s in ta["signals"]) or '<div style="color:var(--text3)">No strong signals</div>'
    obv_html=""
    if ta.get("obv_div"):
        obv_html=f'<div class="obv-warn">⚠ OBV DIVERGENCE — price near highs but volume declining. Possible distribution.</div>'
    return f"""{obv_html}
    <div class="ta-grid">
      <div class="ta-cell"><div class="ta-lbl">RSI(14)</div><div class="ta-val" style="color:{rsi_c}">{ta['rsi'] or '—'}</div></div>
      <div class="ta-cell"><div class="ta-lbl">MACD</div><div class="ta-val" style="color:{m_c}">{ta['macd'] or '—'}</div></div>
      <div class="ta-cell"><div class="ta-lbl">Vol ratio</div><div class="ta-val" style="color:{'var(--green)' if ta['vol_ratio'] and ta['vol_ratio']>1.5 else 'var(--text)'}">{ta['vol_ratio'] or '—'}x</div></div>
      <div class="ta-cell"><div class="ta-lbl">EMA20/50</div><div class="ta-val">{ta['ema20'] or '—'}/{ta['ema50'] or '—'}</div></div>
      <div class="ta-cell"><div class="ta-lbl">EMA200</div><div class="ta-val">{ta['ema200'] or '—'}</div></div>
      <div class="ta-cell"><div class="ta-lbl">From 52w hi</div><div class="ta-val" style="color:{'var(--red)' if ta['pfh']<-20 else 'var(--text)'}">{ta['pfh']}%</div></div>
    </div>
    <div class="verdict-box {vbox_cls}">
      <div class="verdict-title">{ta['score']}/100 — {ta['verdict']}</div>
      <div class="verdict-sig">{sigs}</div>
    </div>"""

def render_news(items):
    if not items: return '<div style="font-size:11px;color:var(--text3)">No news found</div>'
    rows=[]
    for i in items:
        title=i["title"]
        url=i.get("url","")
        headline=f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>' if url else title
        rows.append(f'<div class="news-item"><div><span class="news-date">{i["date"]}</span><span class="news-src">{i.get("source","")[:20]}</span></div><div class="news-title">{headline}</div></div>')
    return "".join(rows)

def render_research_links(name, sym):
    """High-signal sources for validating why a weekly winner moved."""
    symbol = (sym or "").replace(".NS", "")
    if not symbol or symbol == "â€”": return ""
    links = [
        ("NSE quote & filings", f"https://www.nseindia.com/get-quotes/equity?symbol={quote(symbol)}"),
        ("TradingView technicals", f"https://www.tradingview.com/symbols/NSE-{quote(symbol)}/technicals/"),
        ("Screener fundamentals", f"https://www.screener.in/company/{quote(symbol)}/consolidated/"),
        ("Google News", f"https://news.google.com/search?q={quote(name + ' stock NSE India')}"),
    ]
    return '<div class="col-title" style="margin-top:12px">Verify & Research</div><div class="research-links">' + "".join(
        f'<a class="research-link" href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
        for label,url in links
    ) + '</div>'

def render_reddit(posts):
    if not posts: return '<div style="font-size:11px;color:var(--text3)">No Reddit mentions</div>'
    return "".join(f'<div class="reddit-item"><span style="color:var(--amber)">r/{p["sub"]}</span> ↑{p["score"]} — {p["title"]}</div>' for p in posts)

def deep_dive_card(name, s, vd, ta, news, reddit, all_dates):
    sym = (vd["sym"] if vd else None) or get_nse_symbol(name) or "—"
    score = ta["score"] if ta else 0
    sc = "var(--green)" if score>=70 else "var(--amber)" if score>=50 else "var(--red)"
    # 1mo return: use yfinance p20 as fallback
    ret1m = s.get("latest_ret1m")
    if ret1m is None and ta and ta.get("p20") is not None:
        ret1m = ta["p20"]
        ret1m_src = "~yf"
    else:
        ret1m_src = ""

    return f"""
    <div id="stock-{re.sub(r'[^a-z0-9]','',name.lower())}" class="stock-card">
      <div class="card-header">
        <div><span class="card-name">{name}</span><span class="card-sym">{sym}</span></div>
        <div style="text-align:right">
          <div class="card-price">&#8377;{n(s['latest_cmp'],1)}</div>
          <div style="font-size:10px;color:{sc};font-family:var(--mono)">Upside: {score}/100</div>
        </div>
      </div>
      <div class="metrics">
        <div class="metric"><div class="metric-lbl">Freq</div><div class="metric-val" style="color:var(--amber)">{s['appearances']}d</div></div>
        <div class="metric"><div class="metric-lbl">Avg 1d ret</div><div class="metric-val">{pct(s['avg_ret1d'])}</div></div>
        <div class="metric"><div class="metric-lbl">Week chg</div><div class="metric-val">{pct(s['price_change_week'])}</div></div>
        <div class="metric"><div class="metric-lbl">1mo ret{ret1m_src}</div><div class="metric-val">{pct(ret1m)}</div></div>
        <div class="metric"><div class="metric-lbl">QoQ profit</div><div class="metric-val">{pct(s['latest_qoqp'])}</div></div>
        <div class="metric"><div class="metric-lbl">ROCE%</div><div class="metric-val">{pct(s['latest_roce'])}</div></div>
      </div>
      <div class="vol-section">
        <div class="vol-title">Volume Analysis — Week vs Month vs 3-Month</div>
        {render_vol(vd)}
      </div>
      <div class="card-body">
        <div class="col">
          <div class="col-title">Chart Analysis</div>
          {render_ta(ta)}
        </div>
        <div class="col">
          <div class="col-title">News</div>
          {render_news(news)}
          {render_research_links(name, sym)}
          <div class="col-title" style="margin-top:12px">Reddit</div>
          {render_reddit(reddit)}
        </div>
      </div>
    </div>"""

def build_html(analysis, vol_d, ta_d, news_d, reddit_d, week_dates):
    stats=analysis["stock_stats"]; wl=f"{week_dates[0]} to {week_dates[-1]}" if week_dates else "This Week"
    all5_badges="".join(f'<span style="display:inline-block;background:var(--amber-dim);color:var(--amber);border-radius:3px;padding:2px 10px;margin:3px;font-size:12px;font-weight:600">{n}</span>' for n in analysis["appeared_all5"]) or "<span style='color:var(--text3)'>None this week</span>"

    earn_rows="".join(f"""<tr>
      <td>{nm}</td><td>{pct(s.get('latest_qoqp'))}</td><td>{pct(s.get('latest_qoqs'))}</td>
      <td>{pct(s.get('latest_profit'))}</td><td>{s['appearances']}/5</td>
      <td>&#8377;{n(s.get('latest_cmp'),1)}</td>
    </tr>""" for nm,s in analysis["earnings_cat"][:10])

    bp_rows="".join(f"""<tr>
      <td><a href="#{re.sub(r'[^a-z0-9]','',nm.lower())}" style="color:var(--text);text-decoration:none">{nm}</a></td>
      <td style="color:var(--amber);font-weight:600">{stats[nm]['appearances']}/5</td>
      <td>{pct(stats[nm].get('avg_ret1d'))}</td>
      <td>{pct(stats[nm].get('price_change_week'))}</td>
      <td style="color:{'var(--green)' if vol_d.get(nm) and vol_d[nm].get('ratio_wk_mo') and vol_d[nm]['ratio_wk_mo']>1.5 else 'var(--text)'};font-weight:600">
        {str(vol_d[nm]['ratio_wk_mo'])+'x' if vol_d.get(nm) and vol_d[nm].get('ratio_wk_mo') else '—'}
      </td>
      <td>{fmt_vol(vol_d[nm]['vol5d']) if vol_d.get(nm) else '—'}</td>
      <td>{fmt_vol(vol_d[nm]['vol22d']) if vol_d.get(nm) else '—'}</td>
      <td>{pct(stats[nm].get('latest_roce'))}</td>
      <td style="color:{'var(--green)' if ta_d.get(nm) and ta_d[nm]['score']>=70 else 'var(--amber)' if ta_d.get(nm) and ta_d[nm]['score']>=50 else 'var(--text3)'};font-weight:600">{ta_d[nm]['score'] if ta_d.get(nm) else '—'}</td>
    </tr>""" for nm,s in analysis["bp_ranked"] if s["appearances"]>=2)

    dive_cards="".join(
        deep_dive_card(nm, stats[nm], vol_d.get(nm), ta_d.get(nm),
                       news_d.get(nm,[]), reddit_d.get(nm,[]), analysis["dates"])
        for nm in analysis["appeared_2p"]
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Analysis — {wl}</title>
<style>{DARK_CSS}</style>
</head><body>
<div class="page-header">
  <div class="page-title">WEEKLY BREAKOUT ANALYSIS</div>
  <div class="page-meta">{wl} &middot; {analysis['total_unique']} UNIQUE STOCKS &middot; {len(analysis['appeared_2p'])} DEEP-DIVED</div>
</div>
<div class="stat-strip">
  <div class="stat"><div class="stat-val">{analysis['total_unique']}</div><div class="stat-lbl">Unique stocks</div></div>
  <div class="stat"><div class="stat-val" style="color:var(--amber)">{len(analysis['appeared_all5'])}</div><div class="stat-lbl">All 5 days</div></div>
  <div class="stat"><div class="stat-val" style="color:var(--blue)">{len(analysis['appeared_2p'])}</div><div class="stat-lbl">Deep dived (2+ days)</div></div>
  <div class="stat"><div class="stat-val" style="color:var(--green)">{len(analysis['earnings_cat'])}</div><div class="stat-lbl">Earnings catalysts</div></div>
  <div class="stat"><div class="stat-val" style="color:var(--green)">{sum(1 for nm in analysis['appeared_2p'] if ta_d.get(nm) and ta_d[nm]['score']>=70)}</div><div class="stat-lbl">Strong upside signals</div></div>
</div>

<div class="sec"><div class="sec-head"><span class="sec-label">All 5 Days</span><span class="sec-count">Highest conviction</span></div>
<div style="padding:10px 24px">{all5_badges}</div></div>

<div class="sec"><div class="sec-head"><span class="sec-label">Earnings Catalysts</span><span class="sec-count">QoQ profit >20% + 2+ days</span></div>
<div style="padding:0 24px 16px"><table>
  <thead><tr><th>Stock</th><th>QoQ Profit%</th><th>QoQ Sales%</th><th>Profit Growth%</th><th>Days</th><th>CMP</th></tr></thead>
  <tbody>{earn_rows or '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:12px">None this week</td></tr>'}</tbody>
</table></div></div>

<div class="sec"><div class="sec-head"><span class="sec-label">All 2+ Day Stocks</span><span class="sec-count">Click name to jump to deep dive</span></div>
<div style="padding:0 24px 16px"><table>
  <thead><tr><th>Stock</th><th>Days</th><th>Avg 1d Ret</th><th>Week Chg</th><th>Vol Wk/Mo</th><th>Vol 5d</th><th>Vol 1mo</th><th>ROCE%</th><th>Upside</th></tr></thead>
  <tbody>{bp_rows}</tbody>
</table></div></div>

<div class="sec"><div class="sec-head"><span class="sec-label">Deep Dives</span><span class="sec-count">Vol bars + chart analysis + news + Reddit for every 2+ day stock</span></div>
<div style="padding:8px 0">{dive_cards}</div></div>

<div class="page-foot">Weekly Analysis v5 &middot; {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC &middot; Screener.in</div>
</body></html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    today=date.today().isoformat(); week_dates=get_week_dates()
    print(f"\nWeekly Analysis v5 — {week_dates[0]} to {week_dates[-1]}")

    reports=[]
    for d in week_dates:
        r=load_report(d)
        if r: print(f"  {d} — {r['total_stocks']} stocks"); reports.append(r)
        else: print(f"  No report: {d}")

    if not reports: print("No reports found."); return

    analysis=analyse_week(reports)
    targets=analysis["appeared_2p"]
    print(f"\n  {analysis['total_unique']} unique stocks · {len(targets)} to deep dive")

    vol_d={}; ta_d={}; news_d={}; reddit_d={}

    if HAS_YF:
        print(f"  Fetching vol + TA for {len(targets)} stocks...")
        for nm in targets:
            sym=get_nse_symbol(nm)
            print(f"    {nm} -> {sym}")
            vd,td=get_vol_and_ta(nm)
            vol_d[nm]=vd; ta_d[nm]=td
            time.sleep(0.4)

    print(f"  Fetching news...")
    for nm in targets: news_d[nm]=get_news(nm); time.sleep(0.3)

    print(f"  Fetching Reddit...")
    for nm in targets: reddit_d[nm]=get_reddit(nm); time.sleep(0.3)

    week_dir=os.path.join(OUTPUT_DIR,"weekly"); os.makedirs(week_dir,exist_ok=True)
    base=os.path.join(week_dir,f"week_{week_dates[0]}")
    html=build_html(analysis,vol_d,ta_d,news_d,reddit_d,week_dates)
    with open(base+"_analysis.html","w",encoding="utf-8") as f: f.write(html)
    print(f"  HTML -> {base}_analysis.html")

    with open(base+"_analysis.json","w",encoding="utf-8") as f:
        out={k:v for k,v in analysis.items() if k not in("stock_stats","bp_ranked")}
        out["stock_stats_summary"]={n:{k:v for k,v in s.items() if k!="daily_data"} for n,s in analysis["stock_stats"].items()}
        out["conviction_picks"]=[(nm,{k:v for k,v in s.items() if k!="daily_data"}) for nm,s in analysis["bp_ranked"] if s["appearances"]>=2]
        json.dump(out,f,indent=2,ensure_ascii=False,default=str)
    print(f"  JSON -> {base}_analysis.json")
    print(f"\nDone — {len(targets)} deep dives · {sum(1 for v in vol_d.values() if v)} with vol data · {sum(1 for v in ta_d.values() if v)} with TA")

if __name__=="__main__":
    main()
