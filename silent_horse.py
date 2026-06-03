"""
silent_horse.py
Runs two rolling windows:
  - 4-week  (monthly)  analysis → reports/monthly/silent_horse_4wk_YYYY-MM-DD.html
  - 3-week  (sprint)   analysis → reports/monthly/silent_horse_3wk_YYYY-MM-DD.html
  - 8-week  Stage 1 slow tracker (Weinstein accumulation fingerprint)

Tiers (same for both windows):
  Gold   — 3+ weeks present, freq >5, escalating or gap-return, price held
  Silver — 2+ weeks present, freq >3 OR single blowout week (4+ days)
  Watch  — 2 weeks present, freq 3-4

Stage context label (applied to every stock):
  "Fresh base"    — down 30%+ from 52w high, 3mo return < 10%  → Stage 1 candidate, best risk/reward
  "Mid-run"       — 3mo return 10-40%, not overextended          → Stage 2, still good entry
  "Extended run"  — 3mo return 40%+ OR within 5% of 52w high    → Stage 3 risk, verify OBV
  "Recovering"    — was down, now up 0-20% from recent lows      → Stage 1 breakout, high conviction

Exhaustion flags (added to score as penalties / warnings):
  -15 pts if 3mo return > 50%   (late entry risk)
  -8  pts if 3mo return 30-50%  (getting extended)
  +8  pts if stock recovering from 30%+ drawdown (fresh base bonus)
  OBV divergence warning if price near 52w high + RSI lower highs
"""

import json, os, re, time, statistics, glob
from datetime import datetime, date, timedelta
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import quote

OUTPUT_DIR  = "reports"
MONTHLY_DIR = os.path.join(OUTPUT_DIR, "monthly")
SCREEN_URL  = "https://www.screener.in/screens/3664072/screen1/"

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    print("  ⚠  pip install yfinance")

# ── Helpers ───────────────────────────────────────────────────────────────────

def sf(v):
    try: return float(str(v).replace(",","").replace("%","").strip())
    except: return None

def fcol(headers, *kws):
    for kw in kws:
        for i,h in enumerate(headers):
            if kw.lower() in h.lower(): return i
    return None

def http_get(url, timeout=8):
    try:
        req = Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except: return None

def load_daily_jsons():
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR,"????-??-??","????-??-??_screener.json")))
    out = []
    for f in files:
        try:
            with open(f) as fh: d = json.load(fh)
            out.append(d)
        except: pass
    return out

# ── Build tracker ─────────────────────────────────────────────────────────────

def build_tracker(daily_reports, weeks=4):
    cutoff = date.today() - timedelta(weeks=weeks)
    week_buckets = defaultdict(list)
    for rep in daily_reports:
        try: d = date.fromisoformat(rep["date"])
        except: continue
        if d < cutoff: continue
        week_buckets[d.isocalendar()[:2]].append(rep)

    all_weeks = sorted(week_buckets.keys())

    stock_data = defaultdict(lambda:{
        "weeks":[],"week_freq":{},"daily_cmps":[],"daily_ret1d":[],
        "all_freq":0,"latest":{},"first_date":None,"latest_date":None,
    })

    for week_key, day_reps in week_buckets.items():
        for rep in day_reps:
            headers = rep.get("headers",[])
            idx = {k:fcol(headers,*v) for k,v in {
                "name":["name"],"cmp":["cmp","current price"],
                "ret1d":["1day","return over 1day"],"ret1w":["1week","return over 1week"],
                "ret1m":["1month","return over 1month"],
                "mktcap":["mar cap","market cap"],"pe":["p/e"],"roce":["roce"],
                "profit":["profit growth","profit var"],"qoqp":["qoq profit"],"qoqs":["qoq sales"],
            }.items()}
            for stock in rep.get("stocks",[]):
                if not isinstance(stock,dict): continue
                def g(k):
                    i=idx.get(k); return sf(stock.get(headers[i],"")) if i is not None else None
                def gs(k):
                    i=idx.get(k); return stock.get(headers[i],"") if i is not None else ""
                name=gs("name")
                if not name: continue
                sd=stock_data[name]
                if week_key not in sd["week_freq"]:
                    sd["weeks"].append(week_key); sd["week_freq"][week_key]=0
                sd["week_freq"][week_key]+=1
                sd["all_freq"]+=1
                d_str=rep.get("date",""); cmp=g("cmp")
                if cmp: sd["daily_cmps"].append((d_str,cmp))
                if g("ret1d") is not None: sd["daily_ret1d"].append((d_str,g("ret1d")))
                if not sd["first_date"] or d_str<sd["first_date"]: sd["first_date"]=d_str
                if not sd["latest_date"] or d_str>sd["latest_date"]:
                    sd["latest_date"]=d_str
                    sd["latest"]={"cmp":cmp,"ret1d":g("ret1d"),"ret1w":g("ret1w"),
                        "ret1m":g("ret1m"),"mktcap":g("mktcap"),"pe":g("pe"),
                        "roce":g("roce"),"profit":g("profit"),"qoqp":g("qoqp"),"qoqs":g("qoqs")}
    return dict(stock_data), all_weeks

# ── Pattern detection ─────────────────────────────────────────────────────────

def detect_pattern(sd, all_weeks):
    weeks=sd["weeks"]; wf=sd["week_freq"]
    if not weeks: return "none",0,"No appearances"
    widx={w:i for i,w in enumerate(all_weeks)}
    pos=sorted([widx[w] for w in weeks if w in widx])
    if not pos: return "unknown",0,"Insufficient data"
    freqs=[wf.get(all_weeks[p],0) for p in pos]
    gaps=[pos[i]-pos[i-1]-1 for i in range(1,len(pos))]
    has_gap=any(g>=1 for g in gaps)
    is_esc=(len(freqs)>=2 and freqs[-1]>=freqs[-2] and freqs[-1]==max(freqs))
    is_blowout=max(freqs)>=4
    if is_esc and has_gap:        return "escalating+return",20,"Gap then return with escalating intensity — VCP signal 🔥"
    elif is_esc:                  return "escalating",15,"Accelerating appearances — accumulation escalating"
    elif has_gap and freqs[-1]>=2: return "gap+return",15,"Disappeared then returned stronger — Darvas box retest"
    elif is_blowout:              return "blowout",12,f"Single-week blowout ({max(freqs)} days) — explosive entry"
    elif len(pos)>=3:             return "consistent",8,"Consistent multi-week presence"
    elif has_gap:                 return "intermittent",4,"Intermittent — early radar"
    else:                         return "flat",3,"Flat frequency — no escalation yet"

def detect_price_action(sd):
    cmps=sd["daily_cmps"]
    if len(cmps)<2: return None,"insufficient",0
    fc=cmps[0][1]; lc=cmps[-1][1]
    if not fc or fc==0: return None,"insufficient",0
    pct=round(((lc-fc)/fc)*100,2)
    if pct>=15: return pct,"strong uptrend",15
    elif pct>=5: return pct,"holding gains",12
    elif pct>=0: return pct,"flat hold",7
    elif pct>=-5: return pct,"slight fade",3
    else: return pct,"fading",0

# ── Stage context — THE KEY ADDITION ─────────────────────────────────────────

def get_stage_context(ta, ret3m):
    """
    Classify stock into stage context using technical data + 3-month return.
    Returns: label, badge_color, description, score_adjustment, warning_flag
    """
    if not ta:
        if ret3m and ret3m > 50:
            return "Extended run","#A32D2D","Up 50%+ recently — verify OBV before entering",-15,True
        return "Unknown","#888","Insufficient data for stage assessment",0,False

    pfh    = ta.get("pfh",0) or 0      # % from 52-week high (negative = below high)
    pfl    = ta.get("pfl",0) or 0      # % from 52-week low (positive = above low)
    rsi    = ta.get("rsi") or 50
    e200   = ta.get("ema200")
    cur    = ta.get("cur",0)
    vr     = ta.get("vol_ratio") or 1
    r3m    = ret3m or 0

    # Fresh base: significantly below 52w high, not yet extended
    if pfh < -25 and r3m < 15:
        if e200 and cur < e200:
            return "Fresh base","#185FA5","Down from highs, below EMA200 — Stage 1 candidate. Best risk/reward if OBV rising.",+8,False
        return "Fresh base","#185FA5","Pulling back from highs — Stage 1 candidate. Watch for OBV divergence.",+5,False

    # Recovering: was down, now bouncing
    if pfh < -15 and r3m > 5 and r3m < 30:
        return "Recovering","#3B6D11","Recovering from drawdown — Stage 1→2 transition. High conviction if volume confirms.",+8,False

    # Mid-run: healthy stage 2
    if 5 <= r3m <= 35 and pfh > -20:
        if rsi < 65 and (not e200 or cur > e200):
            return "Stage 2 mid-run","#3B6D11","Healthy uptrend, not overextended — good entry zone still.",0,False
        elif rsi >= 65:
            return "Stage 2 extended","#854F0B","Uptrend but RSI getting high — momentum intact, manage position size.",-5,True

    # Extended run: Stage 3 risk zone
    if r3m > 40 or pfh > -5:
        warning = True
        if rsi > 70 and vr < 1.2:
            return "Stage 3 risk","#A32D2D","Extended run near 52w high + weak volume + overbought RSI — DISTRIBUTION WARNING. Verify OBV.",-15,True
        elif r3m > 50:
            return "Extended run","#A32D2D",f"Up {r3m:.0f}% in 3 months — late entry risk. Check if fundamental story still has runway.",-15,True
        else:
            return "Near highs","#854F0B","Close to 52-week highs — momentum intact but reduced margin of safety.",-8,True

    return "Neutral","#888","No clear stage signal — needs more data.",0,False

# ── Scoring ───────────────────────────────────────────────────────────────────

def score_stock(name, sd, all_weeks, ta=None):
    score=0; breakdown=[]
    nw=len(sd["weeks"])
    if nw>=4: wp=25
    elif nw==3: wp=17
    elif nw==2: wp=10
    else: wp=5
    score+=wp; breakdown.append(f"Week spread ({nw} wks): +{wp}")

    freq=sd["all_freq"]
    fp=20 if freq>=10 else 17 if freq>=7 else 13 if freq>=5 else 9 if freq>=4 else 6 if freq>=3 else 3
    score+=fp; breakdown.append(f"Total freq ({freq}d): +{fp}")

    pname,ppts,pdesc=detect_pattern(sd,all_weeks)
    score+=ppts; breakdown.append(f"Pattern ({pname}): +{ppts}")

    pct,plabel,ppts2=detect_price_action(sd)
    score+=ppts2; breakdown.append(f"Price action ({plabel}): +{ppts2}")

    qoqp=sd["latest"].get("qoqp")
    qp=15 if qoqp and qoqp>50 else 10 if qoqp and qoqp>20 else 5 if qoqp and qoqp>0 else 0
    score+=qp
    if qoqp is not None: breakdown.append(f"QoQ profit ({qoqp:.0f}%): +{qp}")

    mwf=max(sd["week_freq"].values()) if sd["week_freq"] else 0
    if mwf>=4: score+=5; breakdown.append(f"Blowout week ({mwf}d): +5")

    # Stage context penalty/bonus
    ret3m = sd["latest"].get("ret1m")  # using 1mo as proxy if 3mo not in data
    # Try to get actual 3mo from ta
    r3m_actual = None
    if ta and ta.get("p20"): r3m_actual = ta["p20"]  # 20d as rough proxy
    _, _, _, stage_adj, _ = get_stage_context(ta, ret3m)
    if stage_adj != 0:
        score+=stage_adj
        breakdown.append(f"Stage adjustment: {stage_adj:+d}")

    return {
        "score":min(100,max(0,score)),
        "breakdown":breakdown,
        "pattern":pname,"pattern_desc":pdesc,
        "price_pct":pct,"price_label":plabel,
        "n_weeks":nw,"total_freq":freq,"max_week_freq":mwf,
        "week_freq_map":sd["week_freq"],
    }

def assign_tier(scored):
    nw=scored["n_weeks"]; freq=scored["total_freq"]; mwf=scored["max_week_freq"]
    if nw>=3 and freq>5 and scored["score"]>=55: return "gold"
    elif (nw>=2 and freq>3) or mwf>=4: return "silver"
    elif nw>=2 and freq>=3: return "watch"
    return None

# ── 8-week Stage 1 detector ───────────────────────────────────────────────────

def detect_stage1_bases(daily_reports):
    tracker8,all_weeks8=build_tracker(daily_reports,weeks=8)
    out=[]
    for name,sd in tracker8.items():
        nw=len(sd["weeks"]); freq=sd["all_freq"]
        if nw<5: continue
        avg=freq/nw
        if avg>2.5: continue
        widx={w:i for i,w in enumerate(all_weeks8)}
        pos=sorted([widx[w] for w in sd["weeks"] if w in widx])
        if not pos: continue
        maxg=max(pos[i]-pos[i-1]-1 for i in range(1,len(pos))) if len(pos)>1 else 0
        if maxg>3: continue
        pct,_,_=detect_price_action(sd)
        out.append({"name":name,"n_weeks":nw,"total_freq":freq,"avg_per_week":round(avg,1),
                    "max_gap":maxg,"price_pct":pct,"latest_cmp":sd["latest"].get("cmp"),
                    "latest_qoqp":sd["latest"].get("qoqp"),"latest_roce":sd["latest"].get("roce")})
    out.sort(key=lambda x:(x["n_weeks"],-x["avg_per_week"]),reverse=True)
    return out

# ── External data ─────────────────────────────────────────────────────────────

_sc={}
CORR={"bliss gvs":"BLISSGVS","modison":"MODISON","guj themis":"GUJTHEM","jk tyre":"JKTYRE",
      "rossell":"ROSSELLTECH","adani total":"ATGL","exide":"EXIDEIND","psp project":"PSPPROJECT",
      "mercury ev":"MERCURYEV","timex":"TIMEXG","tpl plast":"TPLPLAST","crizac":"CRIZAC",
      "emmvee":"EMMVEE","astra micro":"ASTRAMICRO","skipper":"SKIPPER","ifb ind":"IFBIND",
      "ge vernova":"GETVERNOVA","oracle fin":"OFSS","natl alum":"NATIONALUM",
      "national alum":"NATIONALUM","cummins":"CUMMINSIND","suzlon":"SUZLON",
      "apar ind":"APARINDS","hitachi energy":"POWERINDIA","monarch networth":"MONARCH",
      "nazara":"NAZARA","chambal fert":"CHAMBLFERT","crompton":"CROMPTON","pricol":"PRICOLLTD",
      "td power":"TDPOWERSYS","kirloskar oil":"KIRLOSENG","mayur uniquoters":"MAYURUNIQ",
      "pearl global":"PGIL","chalet":"CHALET","latent view":"LATENTVIEW",
      "triveni turbine":"TRIVENI","hexaware":"HEXAWARE","balaji amines":"BALAMINES",
      "carborundum":"CARBORUNIV","medplus":"MEDPLUS","atul auto":"ATULAUTO",
      "stove kraft":"STOVEKRAFT","sparc":"SPARC","tbo tek":"TBOTEK",
      "ajax engineering":"AJAX","coforge":"COFORGE","tata technolog":"TATATECH",
      "seamec":"SEAMEC","hind rectifiers":"HIRECT","wheels india":"WHEELS",
      "dynacons":"DYNACONS","sumitomo chemi":"SUMICHEM","saksoft":"SAKSOFT",
      "sandhar":"SANDHAR","mtar":"MTAR","deepak fertil":"DEEPAKFERT","entero":"ENTERO",
      "inox wind":"INOXWIND","waaree":"WAAREEENER","premier energies":"PREMIERENE",
      "bhel":"BHEL","jsw cement":"JSWCEMENT"}

def gsym(name):
    if name in _sc: return _sc[name]
    nl=name.lower()
    for k,v in CORR.items():
        if k in nl: _sc[name]=v+".NS"; return _sc[name]
    _sc[name]=re.sub(r'[^A-Z0-9]','',name.upper())[:12]+".NS"
    return _sc[name]

def get_news(name,n=4):
    q=quote(f"{name} NSE stock India")
    html=http_get(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en")
    if not html: return []
    items=[]
    for m in re.finditer(r"<item>(.*?)</item>",html,re.DOTALL):
        b=m.group(1); t=re.search(r"<title>(.*?)</title>",b); d=re.search(r"<pubDate>(.*?)</pubDate>",b)
        if t:
            title=re.sub(r"<[^>]+>","",t.group(1)).strip()
            pub=d.group(1).strip()[:16] if d else ""
            if title and "Google News" not in title: items.append({"title":title,"date":pub})
        if len(items)>=n: break
    return items

def get_twits(name,n=4):
    sym=gsym(name).replace(".NS","")
    data=http_get(f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.NS.json")
    if not data: return [],None
    try:
        j=json.loads(data); items=[]; b=0; br=0
        for m in j.get("messages",[])[:n*2]:
            body=m.get("body","").replace("\n"," ")[:130]
            sv=((m.get("entities",{}) or {}).get("sentiment",{}) or {}).get("basic","")
            if sv=="Bullish": b+=1
            elif sv=="Bearish": br+=1
            items.append({"text":body,"sent":sv,"date":m.get("created_at","")[:10]})
        tot=b+br; sm=f"🐂 {b} Bullish / 🐻 {br} Bearish ({round(b/tot*100)}% bull)" if tot else None
        return items[:n],sm
    except: return [],None

def get_reddit(name,n=3):
    q=quote(f"{name} stock NSE")
    data=http_get(f"https://www.reddit.com/search.json?q={q}&sort=new&limit=5&t=month")
    if not data: return []
    try:
        posts=[]
        for p in json.loads(data).get("data",{}).get("children",[]):
            d=p.get("data",{})
            posts.append({"title":d.get("title","")[:110],"sub":d.get("subreddit",""),"score":d.get("score",0)})
        return posts[:n]
    except: return []

def ema(p,n):
    if len(p)<n: return None
    k=2/(n+1); e=statistics.mean(p[:n])
    for x in p[n:]: e=x*k+e*(1-k)
    return round(e,2)

def rsi_calc(p,n=14):
    if len(p)<n+1: return None
    g=[max(p[i]-p[i-1],0) for i in range(1,len(p))]
    l=[max(p[i-1]-p[i],0) for i in range(1,len(p))]
    ag=statistics.mean(g[-n:]); al=statistics.mean(l[-n:])
    return round(100-(100/(1+ag/al)),2) if al else 100.0

def get_ta(name):
    if not HAS_YF: return None
    sym=gsym(name)
    try:
        hist=yf.Ticker(sym).history(period="6mo")
        if hist.empty or len(hist)<20: return None
        closes=hist["Close"].tolist(); vols=hist["Volume"].tolist(); cur=closes[-1]
        r14=rsi_calc(closes); e20=ema(closes,20); e50=ema(closes,50); e200=ema(closes,200)
        e12=ema(closes,12); e26=ema(closes,26)
        macd=round(e12-e26,2) if e12 and e26 else None
        v5=statistics.mean([v for v in vols[-5:] if v>0]) if len(vols)>=5 else None
        v20=statistics.mean([v for v in vols[-20:] if v>0]) if len(vols)>=20 else None
        vr=round(v5/v20,2) if v5 and v20 and v20>0 else None
        h52=max(closes[-252:] if len(closes)>=252 else closes)
        l52=min(closes[-252:] if len(closes)>=252 else closes)
        pfh=round(((cur-h52)/h52)*100,1); pfl=round(((cur-l52)/l52)*100,1)
        p5=round(((closes[-1]-closes[-6])/closes[-6])*100,2) if len(closes)>=6 else None
        p20=round(((closes[-1]-closes[-21])/closes[-21])*100,2) if len(closes)>=21 else None

        # OBV calculation
        obv=0; obv_vals=[0]
        for i in range(1,len(closes)):
            vol_i=vols[i] if i<len(vols) else 0
            if closes[i]>closes[i-1]: obv+=vol_i
            elif closes[i]<closes[i-1]: obv-=vol_i
            obv_vals.append(obv)
        # OBV trend: compare last 5 vs previous 5
        obv_recent=statistics.mean(obv_vals[-5:]) if len(obv_vals)>=5 else obv
        obv_prev=statistics.mean(obv_vals[-15:-5]) if len(obv_vals)>=15 else obv_recent
        obv_divergence=(pfh>-10 and obv_recent<obv_prev)  # near highs but OBV falling

        score=0; sigs=[]
        if r14:
            if r14<35:   score+=20; sigs.append(f"RSI oversold ({r14}) — reversal zone 🔥")
            elif r14<55: score+=12; sigs.append(f"RSI healthy ({r14}) — room to run")
            elif r14>72: score-=8;  sigs.append(f"RSI overbought ({r14}) — caution ⚠")
        if e20 and e50:
            if cur>e20>e50:  score+=18; sigs.append("Price > EMA20 > EMA50 — bullish stack ✅")
            elif cur>e50:    score+=8;  sigs.append("Above EMA50 — mid-term intact")
        if e200 and cur>e200: score+=12; sigs.append("Above EMA200 — long-term uptrend ✅")
        if macd and macd>0:  score+=10; sigs.append(f"MACD positive ({macd})")
        if vr:
            if vr>=2:    score+=15; sigs.append(f"Volume 2×+ ({vr}×) — institutional activity 🔥")
            elif vr>=1.5: score+=10; sigs.append(f"Volume elevated ({vr}×)")
        if p5 and p5>0: score+=5; sigs.append(f"5d momentum: +{p5}%")
        if pfh<-30 and vr and vr>1.5: score+=8; sigs.append(f"Down {abs(pfh)}% from 52w high + vol surge — ACCUMULATION 🎯")
        if obv_divergence:
            score-=12; sigs.append("⚠ OBV DIVERGENCE — price near highs but volume declining. Possible distribution.")

        score=min(100,max(0,score))
        verdict=("🟢 STRONG UPSIDE" if score>=70 else "🟡 MODERATE BULLISH"
                 if score>=50 else "🟠 NEUTRAL" if score>=30 else "🔴 BEARISH")

        return {"sym":sym,"cur":round(cur,2),"rsi":r14,"ema20":e20,"ema50":e50,"ema200":e200,
                "macd":macd,"vol_ratio":vr,"pfh":pfh,"pfl":pfl,"p5":p5,"p20":p20,
                "h52":round(h52,2),"l52":round(l52,2),"obv_divergence":obv_divergence,
                "score":score,"verdict":verdict,"signals":sigs}
    except Exception as e: print(f"    ⚠ TA failed {name}: {e}"); return None

# ── HTML helpers ──────────────────────────────────────────────────────────────

def pc(v,d=2):
    if v is None: return "—"
    c="var(--green)" if v>0 else "var(--red)" if v<0 else "var(--text3)"
    a="▲" if v>0 else "▼" if v<0 else ""
    return f'<span style="color:{c};font-weight:600">{a}&nbsp;{v:.{d}f}%</span>'

def nm(v,d=1):
    if v is None: return "—"
    try: return f"{float(v):,.{d}f}"
    except: return str(v)

def freq_spark(wf,all_weeks):
    bars=""
    mf=max(wf.values()) if wf else 1
    for wk in all_weeks:
        f=wf.get(wk,0); h=max(2,int((f/max(mf,1))*28))
        col="#4a6cf7" if f>=3 else "#93b4f7" if f>=1 else "#e8e8e8"
        wlabel=f"W{wk[1]}" if isinstance(wk,tuple) else str(wk)
        bars+=f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px"><div style="width:18px;height:{h}px;background:{col};border-radius:2px 2px 0 0" title="{wlabel}:{f}d"></div><div style="font-size:9px;color:var(--text3)">{f}</div></div>'
    return f'<div style="display:flex;align-items:flex-end;gap:3px;height:38px">{bars}</div>'

def render_news(items):
    if not items: return '<em style="font-size:11px;color:var(--text3)">No news found</em>'
    return "".join(f'<div style="padding:4px 0;border-bottom:1px solid var(--border)"><div style="font-size:10px;color:var(--text3)">{i["date"]}</div><div style="font-size:11px;line-height:1.4">{i["title"]}</div></div>' for i in items)

def render_twits(items,sm):
    if not items: return '<em style="font-size:11px;color:var(--text3)">No StockTwits data</em>'
    s=f'<div style="font-size:11px;font-weight:500;margin-bottom:4px;background:var(--bg4);padding:2px 8px;border-radius:4px">{sm}</div>' if sm else ""
    return s+"".join(f'<div style="font-size:10px;padding:2px 0;border-bottom:0.5px solid #f8f8f8"><span style="color:{"#1a9e6d" if i["sent"]=="Bullish" else "#d94b4b" if i["sent"]=="Bearish" else "#888"}">{"🐂" if i["sent"]=="Bullish" else "🐻" if i["sent"]=="Bearish" else "💬"}</span> {i["text"]}</div>' for i in items)

def render_reddit(posts):
    if not posts: return '<em style="font-size:11px;color:var(--text3)">No Reddit mentions</em>'
    return "".join(f'<div style="font-size:10px;padding:2px 0;border-bottom:0.5px solid #f8f8f8"><span style="color:#ff6314">r/{p["sub"]}</span> ↑{p["score"]} — {p["title"]}</div>' for p in posts)

def render_ta(ta):
    if not ta: return '<em style="font-size:11px;color:var(--text3)">Technical data unavailable</em>'
    rc="#d94b4b" if ta["rsi"] and ta["rsi"]>70 else "#1a9e6d" if ta["rsi"] and ta["rsi"]<40 else "#555"
    sigs="".join(f'<div style="font-size:11px;padding:2px 0;color:{"#A32D2D" if "⚠" in s else "#2d5a27"}">{"⚠" if "⚠" in s else "✓"} {s}</div>' for s in ta["signals"]) or '<div style="font-size:11px;color:var(--text3)">No strong signals</div>'
    obv_warn=f'<div style="background:var(--red-dim);border:0.5px solid #A32D2D;border-radius:4px;padding:5px 8px;margin-bottom:6px;font-size:11px;color:#A32D2D;font-weight:500">⚠ OBV DIVERGENCE DETECTED — possible distribution top</div>' if ta.get("obv_divergence") else ""
    return f"""{obv_warn}<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-bottom:7px">
      <div style="background:var(--bg4);padding:5px;border-radius:5px"><div style="font-size:9px;color:var(--text3)">RSI(14)</div><div style="font-weight:500;font-size:12px;color:{rc}">{ta['rsi'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:5px;border-radius:5px"><div style="font-size:9px;color:var(--text3)">MACD</div><div style="font-weight:500;font-size:12px;color:{'#1a9e6d' if ta['macd'] and ta['macd']>0 else '#d94b4b'}">{ta['macd'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:5px;border-radius:5px"><div style="font-size:9px;color:var(--text3)">Vol ratio</div><div style="font-weight:500;font-size:12px">{ta['vol_ratio'] or '—'}×</div></div>
      <div style="background:var(--bg4);padding:5px;border-radius:5px"><div style="font-size:9px;color:var(--text3)">EMA20/50</div><div style="font-size:11px">{ta['ema20'] or '—'}/{ta['ema50'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:5px;border-radius:5px"><div style="font-size:9px;color:var(--text3)">EMA200</div><div style="font-size:11px">{ta['ema200'] or '—'}</div></div>
      <div style="background:var(--bg4);padding:5px;border-radius:5px"><div style="font-size:9px;color:var(--text3)">From 52w high</div><div style="font-size:11px;font-weight:500;color:{'#d94b4b' if ta['pfh']<-20 else '#555'}">{ta['pfh']}%</div></div>
    </div>
    <div style="background:var(--green-dim);border:0.5px solid #c3e6c3;border-radius:6px;padding:7px">
      <div style="font-size:11px;font-weight:500;margin-bottom:3px">{ta['verdict']}</div>{sigs}
    </div>"""

def gold_card(name,sd,scored,ta,news,twits,twit_sent,reddit,all_weeks):
    lx=sd["latest"]; sc=scored["score"]
    ret3m=lx.get("ret1m")
    stage_label,stage_col,stage_desc,_,warn=get_stage_context(ta,ret3m)
    sym=gsym(name)

    wf_disp=""
    for wk in all_weeks:
        f=scored["week_freq_map"].get(wk,0)
        bg="#4a6cf7" if f>=3 else "#93b4f7" if f>=2 else "#d0d8ff" if f>=1 else "#f0f0f0"
        wlabel=f"W{wk[1]}" if isinstance(wk,tuple) else str(wk)
        wf_disp+=f'<div style="text-align:center;font-size:10px"><div style="width:22px;height:22px;border-radius:4px;background:{bg};color:{"#fff" if f>0 else "#ccc"};display:flex;align-items:center;justify-content:center;font-weight:500;margin:0 auto">{f}</div><div style="color:var(--text3);margin-top:1px">{wlabel}</div></div>'

    obv_banner=""
    if warn and ta and ta.get("obv_divergence"):
        obv_banner=f'<div style="background:var(--red-dim);border-bottom:0.5px solid #A32D2D;padding:8px 16px;font-size:12px;color:#A32D2D;font-weight:500">⚠ DISTRIBUTION WARNING — Price near highs but OBV declining. Institutions may be exiting. Verify before entering.</div>'
    elif warn:
        obv_banner=f'<div style="background:var(--amber-dim);border-bottom:0.5px solid #854F0B;padding:8px 16px;font-size:12px;color:#854F0B;font-weight:500">⚠ STAGE 3 RISK — {stage_desc}</div>'

    bdown="".join(f'<div style="font-size:10px;color:var(--text3);padding:1px 0">→ {b}</div>' for b in scored["breakdown"])

    return f"""
<div style="border:0.5px solid #e0e4f0;border-radius:12px;margin-bottom:22px;overflow:hidden">
  <div style="background:var(--bg3);color:#fff;padding:13px 18px;display:flex;justify-content:space-between;align-items:center">
    <div>
      <span style="font-size:15px;font-weight:500">{name}</span>
      <span style="font-size:10px;opacity:.5;margin-left:8px">{sym}</span>
      <span style="background:#f0c040;color:#2d2000;font-size:10px;font-weight:500;padding:2px 8px;border-radius:20px;margin-left:8px">GOLD</span>
      <span style="background:{stage_col};color:#fff;font-size:10px;padding:2px 8px;border-radius:20px;margin-left:6px">{stage_label}</span>
    </div>
    <div style="text-align:right">
      <div style="font-size:16px;font-weight:500">₹{nm(lx.get('cmp'),1)}</div>
      <div style="font-size:10px;opacity:.6">{sc}/100 silent horse score</div>
    </div>
  </div>
  {obv_banner}
  <div style="display:grid;grid-template-columns:repeat(6,1fr);border-bottom:0.5px solid #f0f0f0;font-size:10px">
    <div style="padding:7px 10px;border-right:0.5px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">Weeks</div><div style="font-weight:500">{scored['n_weeks']}/{len(all_weeks)}</div></div>
    <div style="padding:7px 10px;border-right:0.5px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">Total freq</div><div style="font-weight:500">{scored['total_freq']}d</div></div>
    <div style="padding:7px 10px;border-right:0.5px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">Price Δ</div>{pc(scored['price_pct'],1)}</div>
    <div style="padding:7px 10px;border-right:0.5px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">QoQ profit</div>{pc(lx.get('qoqp'),1)}</div>
    <div style="padding:7px 10px;border-right:0.5px solid #f0f0f0"><div style="color:var(--text3);font-size:9px">1mo return</div>{pc(ta.get("p20") if ta and lx.get("ret1m") is None and ta.get("p20") is not None else lx.get("ret1m"),1)}<div style="font-size:8px;color:var(--text3)">{("yf~" if ta and lx.get("ret1m") is None and ta.get("p20") is not None else "")}</div></div>
    <div style="padding:7px 10px"><div style="color:var(--text3);font-size:9px">Pattern</div><div style="font-size:10px;font-weight:500">{scored['pattern']}</div></div>
  </div>
  <div style="padding:10px 16px;background:var(--bg3);border-bottom:0.5px solid #f0f0f0;display:flex;justify-content:space-between;align-items:center">
    <div><div style="font-size:11px;font-weight:500;color:var(--text);margin-bottom:5px">Weekly pattern</div>
      <div style="display:flex;gap:8px">{wf_disp}</div>
      <div style="font-size:10px;color:var(--text3);margin-top:3px">{scored['pattern_desc']}</div></div>
    <div style="text-align:right"><div style="font-size:10px;font-weight:500;color:var(--text);margin-bottom:3px">Score breakdown</div>{bdown}</div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr">
    <div style="padding:11px 13px;border-right:0.5px solid #f0f0f0">
      <div style="font-size:11px;font-weight:500;margin-bottom:6px;color:var(--text)">📊 Chart + Stage Analysis</div>
      {render_ta(ta)}
    </div>
    <div style="padding:11px 13px;border-right:0.5px solid #f0f0f0">
      <div style="font-size:11px;font-weight:500;margin-bottom:5px;color:var(--text)">📰 News</div>
      {render_news(news)}
      <div style="font-size:11px;font-weight:500;margin:9px 0 5px;color:var(--text)">🗣 Reddit</div>
      {render_reddit(reddit)}
    </div>
    <div style="padding:11px 13px">
      <div style="font-size:11px;font-weight:500;margin-bottom:5px;color:var(--text)">💬 StockTwits</div>
      {render_twits(twits,twit_sent)}
    </div>
  </div>
</div>"""

def build_html(gold,silver,watch,stage1,all_weeks,window_weeks,report_date,ta_d,news_d,twit_d,reddit_d,tracker):
    wrange=f"last {window_weeks} weeks ending {report_date}"
    title_suffix="3-Week Sprint" if window_weeks==3 else "Monthly (4-Week)"

    silver_rows="".join(f"""<tr>
      <td style="text-align:left;font-weight:500">{nm_}</td>
      <td>{sc['n_weeks']}/{len(all_weeks)}</td>
      <td style="color:#185FA5;font-weight:500">{sc['total_freq']}d</td>
      <td>{freq_spark(sc['week_freq_map'],all_weeks)}</td>
      <td>{pc(sc['price_pct'],1)}</td>
      <td>{pc(tracker[nm_]['latest'].get('qoqp'),1)}</td>
      <td>{pc(tracker[nm_]['latest'].get('ret1m'),1)}</td>
      <td style="font-size:11px">{sc['pattern']}</td>
      <td style="font-weight:500;color:{'#1a9e6d' if sc['score']>=60 else '#f0a500' if sc['score']>=45 else '#888'}">{sc['score']}</td>
    </tr>""" for nm_,sc in silver)

    watch_rows="".join(f"""<tr>
      <td style="text-align:left;font-weight:500">{nm_}</td>
      <td>{sc['n_weeks']}/4</td>
      <td>{sc['total_freq']}d</td>
      <td>{freq_spark(sc['week_freq_map'],all_weeks)}</td>
      <td>{pc(sc['price_pct'],1)}</td>
      <td style="font-size:10px;color:var(--text3)">{sc['pattern']}</td>
    </tr>""" for nm_,sc in watch)

    stage1_rows="".join(f"""<tr>
      <td style="text-align:left;font-weight:500">{s['name']}</td>
      <td>{s['n_weeks']}w</td>
      <td>{s['avg_per_week']}/wk</td>
      <td>{s['max_gap']}w</td>
      <td>{pc(s['price_pct'],1)}</td>
      <td>{pc(s['latest_qoqp'],1)}</td>
      <td>₹{nm(s['latest_cmp'],1)}</td>
    </tr>""" for s in stage1[:10])

    gold_html="".join(gold_card(nm_,tracker[nm_],sc,ta_d.get(nm_),news_d.get(nm_,[]),*twit_d.get(nm_,([],None)),reddit_d.get(nm_,[]),all_weeks) for nm_,sc in gold)
    if not gold_html: gold_html='<em style="color:var(--text3);font-size:13px">No Gold horses yet — need more data weeks.</em>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Silent Horse {title_suffix} — {report_date}</title>
<style>
/* ── Bloomberg-inspired dark theme ─────────────────────────── */
:root {
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
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}
/* Header */
.page-header{background:var(--bg2);border-bottom:2px solid var(--amber);padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
.page-title{font-size:16px;font-weight:600;color:var(--amber);letter-spacing:.5px}
.page-meta{font-size:11px;color:var(--text3);font-family:var(--mono)}
/* Stat strip */
.stat-strip{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 24px;display:flex;gap:32px;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:2px}
.stat-val{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--amber)}
.stat-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
/* Sections */
.sec{border-bottom:1px solid var(--border)}
.sec-head{padding:7px 24px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sec-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--amber)}
.sec-count{font-size:10px;color:var(--text3);font-family:var(--mono)}
/* Tables */
table{width:100%;border-collapse:collapse}
thead th{background:var(--bg3);color:var(--text3);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:8px 14px;text-align:right;border-bottom:1px solid var(--border2);white-space:nowrap}
thead th:first-child{text-align:left}
tbody td{padding:7px 14px;border-bottom:1px solid var(--border);text-align:right;font-family:var(--mono);font-size:12px;color:var(--text);white-space:nowrap}
tbody td:first-child{text-align:left;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-weight:500}
tbody tr:hover td{background:var(--bg4)}
/* Pct colors */
.up{color:var(--green);font-weight:600}
.dn{color:var(--red);font-weight:600}
.neu{color:var(--text2)}
/* Stock card */
.stock-card{border:1px solid var(--border);border-left:3px solid var(--amber);margin:12px 24px;border-radius:6px;overflow:hidden}
.card-header{background:var(--bg3);padding:10px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border)}
.card-name{font-size:14px;font-weight:600;color:var(--text)}
.card-sym{font-size:10px;color:var(--text3);font-family:var(--mono);margin-left:8px}
.card-price{font-family:var(--mono);font-size:16px;font-weight:600;color:var(--amber)}
.card-score-line{font-size:10px;color:var(--text2);margin-top:2px;text-align:right;font-family:var(--mono)}
/* Metrics row */
.metrics{display:grid;grid-template-columns:repeat(6,1fr);border-bottom:1px solid var(--border)}
.metric{padding:8px 12px;border-right:1px solid var(--border)}
.metric:last-child{border-right:none}
.metric-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.metric-val{font-family:var(--mono);font-size:13px;font-weight:600}
/* 3-col body */
.card-body{display:grid;grid-template-columns:1fr 1fr 1fr}
.col{padding:12px 14px;border-right:1px solid var(--border)}
.col:last-child{border-right:none}
.col-title{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--amber);margin-bottom:7px}
/* TA grid */
.ta-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-bottom:8px}
.ta-cell{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:5px 7px}
.ta-lbl{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.3px}
.ta-val{font-family:var(--mono);font-size:12px;font-weight:600;margin-top:1px}
/* Verdict box */
.verdict-box{border-left:2px solid;padding:7px 10px;border-radius:3px;margin-top:6px}
.verdict-box.strong{background:var(--green-dim);border-color:var(--green)}
.verdict-box.moderate{background:var(--amber-dim);border-color:var(--amber)}
.verdict-box.weak{background:var(--bg4);border-color:var(--border2)}
.verdict-box.bearish{background:var(--red-dim);border-color:var(--red)}
.verdict-title{font-size:11px;font-weight:600;margin-bottom:4px}
.verdict-box.strong .verdict-title{color:var(--green)}
.verdict-box.moderate .verdict-title{color:var(--amber)}
.verdict-box.weak .verdict-title{color:var(--text2)}
.verdict-box.bearish .verdict-title{color:var(--red)}
.verdict-sig{font-size:10px;color:var(--text2);line-height:1.6}
/* News */
.news-item{padding:4px 0;border-bottom:1px solid var(--border)}
.news-item:last-child{border-bottom:none}
.news-date{font-size:9px;color:var(--text3);font-family:var(--mono)}
.news-title{font-size:11px;color:var(--text2);line-height:1.4;margin-top:1px}
/* Twits */
.twit-summary{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:5px 10px;margin-bottom:6px;font-family:var(--mono);font-size:11px}
.twit-item{font-size:10px;padding:3px 0;border-bottom:1px solid var(--border);color:var(--text2);line-height:1.4}
/* Badges */
.badge{font-size:9px;padding:2px 7px;border-radius:3px;font-weight:600;letter-spacing:.4px}
.badge-gold{background:var(--amber-dim);color:var(--amber)}
.badge-silver{background:var(--blue-dim);color:var(--blue)}
.badge-watch{background:var(--bg4);color:var(--text3);border:1px solid var(--border2)}
.badge-fresh{background:var(--blue-dim);color:var(--blue)}
.badge-recover{background:var(--green-dim);color:var(--green)}
.badge-stage2{background:var(--green-dim);color:var(--green)}
.badge-extended{background:var(--amber-dim);color:var(--amber)}
.badge-danger{background:var(--red-dim);color:var(--red)}
/* OBV warning */
.obv-warn{background:var(--red-dim);border-left:3px solid var(--red);padding:8px 14px;font-size:11px;color:var(--red);font-weight:600}
/* Vol bar chart */
.vol-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:8px}
.vol-kpi{background:var(--bg4);border:1px solid var(--border);border-radius:4px;padding:6px 8px;text-align:center}
.vol-kpi-val{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--text)}
.vol-kpi-lbl{font-size:9px;color:var(--text3);margin-top:2px;text-transform:uppercase}
.vol-bars{display:flex;align-items:flex-end;gap:3px;height:44px;margin:4px 0}
.vol-bar-wrap{display:flex;flex-direction:column;align-items:center;flex:1;gap:2px}
.vol-bar{width:100%;border-radius:2px 2px 0 0;min-height:2px}
.vol-bar.week{background:var(--amber)}
.vol-bar.prior{background:var(--blue-dim);border:1px solid var(--blue)}
.vol-bar-lbl{font-size:8px;color:var(--text3);font-family:var(--mono)}
/* Week pattern boxes */
.week-pattern{display:flex;gap:5px;margin:5px 0}
.wk-box{width:24px;height:24px;border-radius:3px;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:10px;font-weight:600}
.wk-box.hit3{background:var(--amber);color:#000}
.wk-box.hit2{background:var(--amber-dim);color:var(--amber);border:1px solid var(--amber)}
.wk-box.hit1{background:var(--blue-dim);color:var(--blue);border:1px solid var(--blue)}
.wk-box.miss{background:var(--bg4);color:var(--text3);border:1px solid var(--border)}
/* Score breakdown */
.score-list{font-size:10px;color:var(--text3);font-family:var(--mono);line-height:1.7}
/* Stage 1 table */
.stage1-note{padding:16px 24px;font-size:12px;color:var(--text3);background:var(--bg2);text-align:center}
/* Footer */
.page-foot{padding:10px 24px;font-size:10px;color:var(--text3);font-family:var(--mono);background:var(--bg2);border-top:1px solid var(--border);text-align:center}
/* Legend strip */
.legend{display:flex;gap:16px;padding:8px 24px;background:var(--bg2);border-bottom:1px solid var(--border);font-size:10px;color:var(--text3);flex-wrap:wrap}
.legend-item{display:flex;align-items:center;gap:5px}
</style></head><body>
<div class="wrap">
  <div class="top">
    <h1>🐎 Silent Horse — {title_suffix}</h1>
    <p>Rolling {window_weeks}-week window · {wrange} · Stage 1 vs Stage 3 detection active</p>
  </div>
  <div class="meta">
    <span>📅 {report_date}</span>
    <span>🥇 Gold: <strong>{len(gold)}</strong></span>
    <span>🥈 Silver: <strong>{len(silver)}</strong></span>
    <span>👁 Watch: <strong>{len(watch)}</strong></span>
    {'<span>🔍 Stage 1 (8wk): <strong>'+str(len(stage1))+'</strong></span>' if stage1 else ''}
  </div>

  <div class="sec"><div class="sh"><h2>Stage context legend</h2></div><div class="sb">
    <div class="stage-key">
      <span class="sk" style="background:#185FA5">Fresh base</span> <span style="color:var(--color-text-secondary)">Down 25%+ from 52w high, low 3mo return — Stage 1 candidate, best risk/reward</span>
    </div>
    <div class="stage-key">
      <span class="sk" style="background:#3B6D11">Recovering</span> <span style="color:var(--color-text-secondary)">Was down, now bouncing — Stage 1→2 transition, high conviction</span>
    </div>
    <div class="stage-key">
      <span class="sk" style="background:#3B6D11">Stage 2 mid-run</span> <span style="color:var(--color-text-secondary)">Healthy uptrend, not overextended — still good entry</span>
    </div>
    <div class="stage-key">
      <span class="sk" style="background:#854F0B">Stage 2 extended / Near highs</span> <span style="color:var(--color-text-secondary)">Momentum intact but reduced margin of safety — manage position size</span>
    </div>
    <div class="stage-key">
      <span class="sk" style="background:#A32D2D">Extended run / Stage 3 risk</span> <span style="color:var(--color-text-secondary)">Up 50%+ or near 52w high with weakening volume — VERIFY OBV before entering</span>
    </div>
  </div></div>

  <div class="sec"><div class="sh"><h2>📊 Summary</h2></div><div class="sb"><div class="sg">
    <div class="sb2"><div class="v">{len(gold)}</div><div class="l">Gold — deep dive</div></div>
    <div class="sb2"><div class="v">{len(silver)}</div><div class="l">Silver — watchlist</div></div>
    <div class="sb2"><div class="v">{len(watch)}</div><div class="l">Watch — seeding</div></div>
    <div class="sb2"><div class="v">{sum(1 for _,sc in gold if ta_d.get(_) and not ta_d[_].get('obv_divergence'))}</div><div class="l">Gold with clean OBV</div></div>
    <div class="sb2"><div class="v">{sum(1 for _,sc in gold if ta_d.get(_) and ta_d[_].get('obv_divergence'))}</div><div class="l">Gold with OBV warning</div></div>
  </div></div></div>

  <div class="sec"><div class="sh"><h2>🥇 Gold Horses — Full Deep Dive</h2>
  <p>{len(gold)} stocks · 3+ weeks · freq &gt;5 · Stage context label + OBV divergence check on every card</p></div>
  <div class="sb">{gold_html}</div></div>

  <div class="sec"><div class="sh"><h2>🥈 Silver Horses — Watchlist</h2>
  <p>{len(silver)} stocks · 2+ weeks, freq &gt;3 OR blowout week</p></div>
  <div style="padding:0 20px 16px"><table>
    <thead><tr><th>Stock</th><th>Weeks</th><th>Freq</th><th>Pattern</th><th>Price Δ</th><th>QoQ profit</th><th>1mo return</th><th>Signal</th><th>Score</th></tr></thead>
    <tbody>{silver_rows or '<tr><td colspan="9" style="text-align:center;color:var(--text3);padding:14px">No Silver horses yet</td></tr>'}</tbody>
  </table></div></div>

  <div class="sec"><div class="sh"><h2>👁 Watch List</h2>
  <p>{len(watch)} stocks · 2 weeks, freq 3-4 · track for 3rd week reappearance</p></div>
  <div style="padding:0 20px 16px"><table>
    <thead><tr><th>Stock</th><th>Weeks</th><th>Freq</th><th>Pattern</th><th>Price Δ</th><th>Signal</th></tr></thead>
    <tbody>{watch_rows or '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:14px">No Watch stocks yet</td></tr>'}</tbody>
  </table></div></div>

  {'<div class="sec"><div class="sh"><h2>🔍 Stage 1 Bases — 8-Week Slow Tracker</h2><p>Appearing quietly 1-2×/week for 6+ weeks — Weinstein accumulation fingerprint</p></div><div style="padding:0 20px 16px"><table><thead><tr><th>Stock</th><th>Weeks</th><th>Avg/wk</th><th>Max gap</th><th>Price Δ</th><th>QoQ profit</th><th>CMP</th></tr></thead><tbody>'+stage1_rows+'</tbody></table></div></div>' if stage1 else ''}

  <div class="foot">Silent Horse Report · {title_suffix} · {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</div>
</div></body></html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def run_analysis(daily_reports, window_weeks, today, stage1_list=None):
    print(f"\n  ── {window_weeks}-week window ──")
    tracker, all_weeks = build_tracker(daily_reports, weeks=window_weeks)
    print(f"  {len(tracker)} stocks · {len(all_weeks)} weeks: {[f'{y}-W{w:02d}' for y,w in all_weeks]}")

    gold=[]; silver=[]; watch=[]
    for name,sd in tracker.items():
        if sd["all_freq"]<2: continue
        scored=score_stock(name,sd,all_weeks)
        tier=assign_tier(scored)
        if tier=="gold":    gold.append((name,scored))
        elif tier=="silver": silver.append((name,scored))
        elif tier=="watch":  watch.append((name,scored))

    gold.sort(key=lambda x:x[1]["score"],reverse=True)
    silver.sort(key=lambda x:x[1]["score"],reverse=True)
    watch.sort(key=lambda x:(x[1]["n_weeks"],x[1]["total_freq"]),reverse=True)
    print(f"  🥇 Gold:{len(gold)} 🥈 Silver:{len(silver)} 👁 Watch:{len(watch)}")

    # Deep dives for Gold
    gold_names=[nm_ for nm_,_ in gold[:8]]
    ta_d={}; news_d={}; twit_d={}; reddit_d={}

    if gold_names:
        if HAS_YF:
            print(f"  📡 TA for {len(gold_names)} Gold stocks...")
            for nm_ in gold_names:
                print(f"    → {nm_}"); ta_d[nm_]=get_ta(nm_); time.sleep(0.5)
        print(f"  📰 News..."); [news_d.update({nm_:get_news(nm_)}) or time.sleep(0.3) for nm_ in gold_names]
        print(f"  💬 Twits..."); [twit_d.update({nm_:get_twits(nm_)}) or time.sleep(0.3) for nm_ in gold_names]
        print(f"  🗣 Reddit..."); [reddit_d.update({nm_:get_reddit(nm_)}) or time.sleep(0.3) for nm_ in gold_names]

    html=build_html(gold,silver,watch,stage1_list or [],all_weeks,window_weeks,today,ta_d,news_d,twit_d,reddit_d,tracker)
    suffix=f"{window_weeks}wk"
    path=os.path.join(MONTHLY_DIR,f"silent_horse_{suffix}_{today}.html")
    with open(path,"w",encoding="utf-8") as f: f.write(html)
    print(f"  ✅ HTML → {path}")

    def clean_scored(s):
        """Convert tuple keys in week_freq_map to strings for JSON serialization."""
        out = {k: v for k, v in s.items() if k != "breakdown"}
        if "week_freq_map" in out:
            out["week_freq_map"] = {f"{y}-W{w:02d}": v for (y, w), v in out["week_freq_map"].items()}
        return out

    jpath=os.path.join(MONTHLY_DIR,f"silent_horse_{suffix}_{today}.json")
    with open(jpath,"w",encoding="utf-8") as f:
        json.dump({"date":today,"window_weeks":window_weeks,
            "gold":[(n, clean_scored(s)) for n,s in gold],
            "silver":[(n, clean_scored(s)) for n,s in silver],
            "watch":[(n, clean_scored(s)) for n,s in watch],
            "stage1_bases":stage1_list or []},
        f,indent=2,ensure_ascii=False,default=str)
    print(f"  ✅ JSON → {jpath}")
    return len(gold),len(silver),len(watch)

def main():
    today=date.today().isoformat()
    print(f"\n🐎 Silent Horse Analysis — {today}")
    daily=load_daily_jsons()
    print(f"  📂 {len(daily)} daily reports found")
    if not daily: print("❌ No daily reports. Run screener_scraper.py first."); return

    os.makedirs(MONTHLY_DIR,exist_ok=True)

    # 8-week Stage 1 tracker
    print("\n  Building 8-week Stage 1 tracker...")
    stage1=detect_stage1_bases(daily)
    print(f"  🔍 Stage 1 bases: {len(stage1)}")

    # Run both windows
    g4,s4,w4=run_analysis(daily,4,today,stage1)
    g3,s3,w3=run_analysis(daily,3,today)

    print(f"\n🐎 Done!")
    print(f"  4-week: Gold {g4} · Silver {s4} · Watch {w4}")
    print(f"  3-week: Gold {g3} · Silver {s3} · Watch {w3}")
    print(f"  Stage 1 (8wk): {len(stage1)}")

if __name__=="__main__":
    main()
