"""
send_email.py
Sends Friday reports via Gmail SMTP.
- Weekly HTML + Silent Horse (always on Fridays)
- Today's earnings HTML only (not all past files)
- Stock history HTML if stock_lookup input was provided
- Daily CSVs for the week
"""

import os, smtplib, json, glob, re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import date, timedelta

SENDER   = os.environ.get("EMAIL_SENDER",   "")
PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
RECEIVER = os.environ.get("EMAIL_RECEIVER", "")
STOCK_LOOKUP = os.environ.get("STOCK_LOOKUP", "")  # passed from workflow
REPORTS  = "reports"

def latest(pattern):
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None

def this_week_csvs():
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    out = []
    for i in range(5):
        d = (monday + timedelta(days=i)).isoformat()
        p = os.path.join(REPORTS, d, f"{d}_screener.csv")
        if os.path.exists(p): out.append(p)
    return out

def todays_earnings_html():
    """Return today's earnings HTML path only — not yesterday's or older."""
    today = date.today().isoformat()
    path  = os.path.join(REPORTS, "earnings", f"earnings_{today}.html")
    return path if os.path.exists(path) else None

def stock_history_html(query):
    """Return the history HTML for a given stock name query."""
    if not query: return None
    safe_name = re.sub(r'[^a-z0-9]', '_', query.lower()).strip('_')
    path = os.path.join(REPORTS, "history", f"{safe_name}_history.html")
    return path if os.path.exists(path) else None

def build_body():
    wj   = latest(os.path.join(REPORTS, "weekly",  "week_*_analysis.json"))
    mj4  = latest(os.path.join(REPORTS, "monthly", "silent_horse_4wk_*.json"))
    mj3  = latest(os.path.join(REPORTS, "monthly", "silent_horse_3wk_*.json"))
    ej   = os.path.join(REPORTS, "earnings", f"earnings_{date.today().isoformat()}.json")

    lines = [
        f"📊 SCREENER WEEKLY + EARNINGS + SILENT HORSE — {date.today().strftime('%d %b %Y')}",
        "=" * 55, ""
    ]

    # Weekly summary
    if wj and os.path.exists(wj):
        try:
            d = json.load(open(wj))
            lines += [
                "WEEKLY BREAKOUT SUMMARY",
                f"  Days tracked    : {len(d.get('dates',[]))}",
                f"  Unique stocks   : {d.get('total_unique',0)}",
                f"  All-5-day stocks: {len(d.get('appeared_all5',[]))} "
                f"— {', '.join(d.get('appeared_all5',[])[:5])}",
                f"  2+ day stocks   : {len(d.get('appeared_2p',[]))}",
                "",
            ]
        except: pass

    # Silent horse
    for label, jpath in [("4-WEEK SILENT HORSE", mj4), ("3-WEEK SILENT HORSE", mj3)]:
        if jpath and os.path.exists(jpath):
            try:
                d = json.load(open(jpath))
                gold   = d.get("gold",   [])
                silver = d.get("silver", [])
                watch  = d.get("watch",  [])
                lines += [
                    label,
                    f"  🥇 Gold  ({len(gold)}):   {', '.join(n for n,_ in gold[:5])}",
                    f"  🥈 Silver({len(silver)}): {', '.join(n for n,_ in silver[:5])}",
                    f"  👁  Watch ({len(watch)}):  {', '.join(n for n,_ in watch[:5])}",
                    "",
                ]
            except: pass

    # Today's earnings
    if os.path.exists(ej):
        try:
            d = json.load(open(ej))
            total    = d.get("total_fetched", 0)
            filtered = d.get("total_filtered", 0)
            top5     = d.get("companies", [])[:5]
            lines += [
                f"TODAY'S EARNINGS ({date.today().strftime('%d %b %Y')})",
                f"  Companies reported : {total}",
                f"  MCap > 500Cr       : {filtered}",
                "  Top by profit YoY  :",
            ]
            for c in top5:
                pyoy = c.get("profit_yoy")
                pyoy_str = f"+{pyoy:.0f}%" if pyoy and pyoy > 0 else (f"{pyoy:.0f}%" if pyoy else "—")
                lines.append(f"    • {c['name']:30s} Profit YoY: {pyoy_str}  MCap: ₹{c.get('mcap','—')}Cr")
            lines.append("")
        except: pass
    else:
        lines += ["TODAY'S EARNINGS", "  No earnings report generated for today.", ""]

    # Stock history lookup
    if STOCK_LOOKUP:
        lines += [
            f"STOCK HISTORY LOOKUP: '{STOCK_LOOKUP}'",
            "  See attached HTML for full timeline.",
            "",
        ]

    lines += [
        "=" * 55,
        "Attachments: weekly HTML · silent horse 3wk + 4wk · today's earnings · daily CSVs",
        "Open HTML files in Chrome for best experience.",
        "",
        "Screen: https://www.screener.in/screens/3664072/screen1/",
    ]
    return "\n".join(lines)

def attach(msg, path):
    if not path or not os.path.exists(path): return
    with open(path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f'attachment; filename="{os.path.basename(path)}"')
        msg.attach(part)
    print(f"  📎 {os.path.basename(path)}")

def main():
    if not SENDER or not PASSWORD or not RECEIVER:
        print("  ❌ Email credentials missing"); return

    today   = date.today().strftime("%d %b %Y")
    subject = f"📊 Weekly + Earnings + Silent Horse — {today}"
    if STOCK_LOOKUP:
        subject += f" · History: {STOCK_LOOKUP}"

    msg = MIMEMultipart("mixed")
    msg["From"] = SENDER; msg["To"] = RECEIVER; msg["Subject"] = subject
    msg.attach(MIMEText(build_body(), "plain"))

    print(f"\n📧 Sending to {RECEIVER}...")

    # Weekly HTML
    attach(msg, latest(os.path.join(REPORTS, "weekly", "week_*_analysis.html")))

    # Silent horse reports
    attach(msg, latest(os.path.join(REPORTS, "monthly", "silent_horse_4wk_*.html")))
    attach(msg, latest(os.path.join(REPORTS, "monthly", "silent_horse_3wk_*.html")))

    # TODAY's earnings only
    attach(msg, todays_earnings_html())

    # Stock history if lookup was provided
    if STOCK_LOOKUP:
        h = stock_history_html(STOCK_LOOKUP)
        if h:
            attach(msg, h)
        else:
            print(f"  ⚠  No history file found for '{STOCK_LOOKUP}'")

    # Daily CSVs for this week
    for csv in this_week_csvs():
        attach(msg, csv)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(SENDER, PASSWORD)
            s.sendmail(SENDER, RECEIVER, msg.as_string())
        print("  ✅ Email sent!")
    except smtplib.SMTPAuthenticationError:
        print("  ❌ Auth failed — check EMAIL_PASSWORD (use App Password)")
    except Exception as e:
        print(f"  ❌ Failed: {e}")

if __name__ == "__main__":
    main()
