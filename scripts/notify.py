"""Notifications helper (S73): desktop toast (Windows, no install) + optional email.

Desktop: balloon tip via System.Windows.Forms — works out of the box.
Email: SMTP via scratchpad/email_cfg.json (gitignored) if present:
  {"host":"smtp.gmail.com","port":587,"user":"you@gmail.com",
   "password":"<gmail APP password>","to":"you@gmail.com"}
Both fail silently (never crash the daemon).

Usage: from notify import notify;  notify("BPS FIRED", "short 7450/7400P, credit 1.30")
"""
import datetime as dt
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "scratchpad" / "email_cfg.json"
LOG = ROOT / "data" / "options_log" / "notifications.log"


def _log(title, msg):
    """Append every notification so there's always a record to check."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{stamp}\t{title}\t{msg}\n")
    except Exception:
        pass


def desktop(title, msg):
    ps = (f"Add-Type -AssemblyName System.Windows.Forms;"
          f"$n=New-Object System.Windows.Forms.NotifyIcon;"
          f"$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
          f"$n.ShowBalloonTip(10000,{json.dumps(title)},{json.dumps(msg)},"
          f"[System.Windows.Forms.ToolTipIcon]::Info);Start-Sleep -Seconds 11;$n.Dispose()")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         creationflags=0x08000000)
    except Exception:
        pass


def email(title, msg):
    if not CFG.exists():
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        c = json.loads(CFG.read_text())
        m = MIMEText(msg)
        m["Subject"] = f"[myquant] {title}"
        m["From"] = c["user"]; m["To"] = c["to"]
        s = smtplib.SMTP(c["host"], c.get("port", 587), timeout=15)
        s.starttls(); s.login(c["user"], c["password"])
        s.sendmail(c["user"], [c["to"]], m.as_string()); s.quit()
    except Exception:
        pass


def email_html(title, html, text_fallback=""):
    """Send an HTML email (used by the EOD report). No-op if email_cfg.json absent."""
    if not CFG.exists():
        return False
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        c = json.loads(CFG.read_text())
        m = MIMEMultipart("alternative")
        m["Subject"] = f"[myquant] {title}"
        m["From"] = c["user"]; m["To"] = c["to"]
        m.attach(MIMEText(text_fallback or "See HTML version.", "plain"))
        m.attach(MIMEText(html, "html"))
        s = smtplib.SMTP(c["host"], c.get("port", 587), timeout=15)
        s.starttls(); s.login(c["user"], c["password"])
        s.sendmail(c["user"], [c["to"]], m.as_string()); s.quit()
        return True
    except Exception:
        return False


def notify(title, msg):
    _log(title, msg)
    desktop(title, msg)
    email(title, msg)


if __name__ == "__main__":
    notify("myquant test", "desktop notification working — daemon events will show like this")
    print("sent test notification (+ email if scratchpad/email_cfg.json exists)")
