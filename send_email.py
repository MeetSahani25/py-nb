"""
send_email.py
Sends weekly analysis + silent horse reports via Gmail SMTP.
Runs every Friday evening and Saturday 10am IST.
"""

import os, smtplib, json, glob
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import date, timedelta

SENDER   = os.environ.get("EMAIL_SENDER", "")
PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
RECEIVER = os.environ.get("EMAIL_RECEIVER", "")
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

def build_body():
    # Try to read weekly JSON for summary
    wj = latest(os.path.join(REPORTS, "weekly", "week_*_analysis.json"))
    mj_4wk = latest(os.path.join(REPORTS, "monthly", "silent_horse_4wk_*.json"))
    mj_3wk = latest(os.path.join(REPORTS, "monthly", "silent_horse_3wk_*.json"))

    lines = [f"📊 SCREENER WEEKLY + SILENT HORSE REPORT — {date.today().strftime('%d %b %Y')}",
             "="*55, ""]

    if wj and os.path.exists(wj):
        try:
            d = json.load(open(wj))
            lines += [
                "WEEKLY BREAKOUT SUMMARY",
                f"  Days tracked    : {len(d.get('dates',[]))}",
                f"  Unique stocks   : {d.get('total_unique',0)}",
                f"  All-5-day stocks: {len(d.get('appeared_all5',[]))} — {', '.join(d.get('appeared_all5',[])[:5])}",
                f"  2+ day stocks   : {len(d.get('appeared_2p',[]))}",
                "",
            ]
        except: pass

    for label, jpath in [("4-WEEK SILENT HORSE", mj_4wk), ("3-WEEK SILENT HORSE", mj_3wk)]:
        if jpath and os.path.exists(jpath):
            try:
                d = json.load(open(jpath))
                gold   = d.get("gold", [])
                silver = d.get("silver", [])
                watch  = d.get("watch", [])
                stage1 = d.get("stage1_bases", [])
                lines += [
                    label,
                    f"  🥇 Gold  ({len(gold)}): {', '.join(n for n,_ in gold[:5])}",
                    f"  🥈 Silver({len(silver)}): {', '.join(n for n,_ in silver[:5])}",
                    f"  👁  Watch ({len(watch)}): {', '.join(n for n,_ in watch[:5])}",
                    f"  🔍 Stage 1 bases (8wk): {len(stage1)}",
                    "",
                ]
            except: pass

    lines += [
        "="*55,
        "Attachments: weekly HTML · silent horse 3wk + 4wk HTML · daily CSVs",
        "Open HTML files in Chrome for best experience.",
        "",
        "Screen: https://www.screener.in/screens/3664072/screen1/",
    ]
    return "\n".join(lines)

def attach(msg, path):
    if not path or not os.path.exists(path):
        return
    with open(path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        msg.attach(part)
    print(f"  📎 {os.path.basename(path)}")

def main():
    if not SENDER or not PASSWORD or not RECEIVER:
        print("  ❌ Email credentials missing"); return

    today   = date.today().strftime("%d %b %Y")
    subject = f"📊 Weekly + Earnings + Silent Horse — {today}"

    msg = MIMEMultipart("mixed")
    msg["From"] = SENDER; msg["To"] = RECEIVER; msg["Subject"] = subject
    msg.attach(MIMEText(build_body(), "plain"))

    print(f"\n📧 Sending to {RECEIVER}...")

    # Attach latest earnings report if exists
    import glob as _glob
    earnings_latest = sorted(_glob.glob(os.path.join("reports","earnings","earnings_*.html")), reverse=True)
    if earnings_latest:
        attach(msg, earnings_latest[0])

    # Attach weekly HTML
    attach(msg, latest(os.path.join(REPORTS, "weekly", "week_*_analysis.html")))
    # Attach silent horse reports
    attach(msg, latest(os.path.join(REPORTS, "monthly", "silent_horse_4wk_*.html")))
    attach(msg, latest(os.path.join(REPORTS, "monthly", "silent_horse_3wk_*.html")))
    # Attach daily CSVs
    for csv in this_week_csvs(): attach(msg, csv)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(SENDER, PASSWORD)
            s.sendmail(SENDER, RECEIVER, msg.as_string())
        print(f"  ✅ Email sent!")
    except smtplib.SMTPAuthenticationError:
        print("  ❌ Auth failed — check EMAIL_PASSWORD (use App Password, not Gmail password)")
    except Exception as e:
        print(f"  ❌ Failed: {e}")

if __name__ == "__main__":
    main()
