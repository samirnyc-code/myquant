"""Notifications helper (S73): desktop toast (Windows, no install) + optional email.

Desktop: balloon tip via System.Windows.Forms — works out of the box.
Email: SMTP via scratchpad/email_cfg.json (gitignored) if present:
  {"host":"smtp.gmail.com","port":587,"user":"you@gmail.com",
   "password":"<gmail APP password>","to":"you@gmail.com"}
Both fail silently (never crash the daemon).

Usage: from notify import notify;  notify("BPS FIRED", "short 7450/7400P, credit 1.30")
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "scratchpad" / "email_cfg.json"


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


def notify(title, msg):
    desktop(title, msg)
    email(title, msg)


if __name__ == "__main__":
    notify("myquant test", "desktop notification working — daemon events will show like this")
    print("sent test notification (+ email if scratchpad/email_cfg.json exists)")
