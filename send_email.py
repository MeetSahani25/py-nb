"""
send_email.py

Email contents:
- Every day:
    - Today's Screener CSV
    - Today's Screener HTML

- Friday only:
    - Weekly Analysis HTML
    - Silent Horse 4-week HTML
    - Silent Horse 3-week HTML

No historical daily CSVs are attached.
"""

import os
import smtplib
import glob

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import date


SENDER = os.environ.get("EMAIL_SENDER", "")
PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
RECEIVER = os.environ.get("EMAIL_RECEIVER", "")

REPORTS = "reports"


def latest(pattern):
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


def todays_screener_file(extension):
    """
    Return today's Screener report only.
    """
    today = date.today().isoformat()

    path = os.path.join(
        REPORTS,
        today,
        f"{today}_screener.{extension}"
    )

    return path if os.path.exists(path) else None


def is_friday():
    return date.today().weekday() == 4


def build_body():
    today = date.today().strftime("%d %b %Y")

    lines = [
        f"📊 SCREENER DAILY REPORT — {today}",
        "=" * 45,
        "",
        "Today's Screener report is attached:",
        "  • CSV",
        "  • HTML",
        "",
    ]

    if is_friday():
        lines += [
            "FRIDAY REPORTS",
            "  • Weekly Analysis",
            "  • Silent Horse — 4 Week",
            "  • Silent Horse — 3 Week",
            "",
        ]

    lines += [
        "=" * 45,
        "Open the HTML file in Chrome for the full report.",
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

    part.add_header(
        "Content-Disposition",
        f'attachment; filename="{os.path.basename(path)}"'
    )

    msg.attach(part)

    print(f"  📎 {os.path.basename(path)}")


def main():
    if not SENDER or not PASSWORD or not RECEIVER:
        print("  ❌ Email credentials missing")
        return

    today = date.today().strftime("%d %b %Y")

    if is_friday():
        subject = f"📊 Screener Daily + Weekly + Silent Horse — {today}"
    else:
        subject = f"📊 Screener Daily Report — {today}"

    msg = MIMEMultipart("mixed")
    msg["From"] = SENDER
    msg["To"] = RECEIVER
    msg["Subject"] = subject

    msg.attach(
        MIMEText(build_body(), "plain")
    )

    print(f"\n📧 Sending to {RECEIVER}...")

    # ─────────────────────────────────────────────
    # DAILY: Today's Screener CSV
    # ─────────────────────────────────────────────

    attach(
        msg,
        todays_screener_file("csv")
    )

    # ─────────────────────────────────────────────
    # DAILY: Today's Screener HTML
    # ─────────────────────────────────────────────

    attach(
        msg,
        todays_screener_file("html")
    )

    # ─────────────────────────────────────────────
    # FRIDAY ONLY
    # ─────────────────────────────────────────────

    if is_friday():

        attach(
            msg,
            latest(
                os.path.join(
                    REPORTS,
                    "weekly",
                    "week_*_analysis.html"
                )
            )
        )

        attach(
            msg,
            latest(
                os.path.join(
                    REPORTS,
                    "monthly",
                    "silent_horse_4wk_*.html"
                )
            )
        )

        attach(
            msg,
            latest(
                os.path.join(
                    REPORTS,
                    "monthly",
                    "silent_horse_3wk_*.html"
                )
            )
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(SENDER, PASSWORD)
            s.sendmail(
                SENDER,
                RECEIVER,
                msg.as_string()
            )

        print("  ✅ Email sent!")

    except smtplib.SMTPAuthenticationError:
        print(
            "  ❌ Auth failed — check EMAIL_PASSWORD "
            "(use App Password)"
        )

    except Exception as e:
        print(f"  ❌ Failed: {e}")


if __name__ == "__main__":
    main()
