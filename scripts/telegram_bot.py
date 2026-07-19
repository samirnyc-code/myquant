"""telegram_bot.py — two-way control: send commands to the desk from your phone.

Long-polls Telegram (this PC has no public URL, so no webhook) and answers commands.
LOCKED to the stored chat_id: a message from any other chat is ignored, so someone who
finds the bot cannot drive your machine.

Commands (send to the bot):
  /status /health   full pipeline health
  /depth            live book% + MB + data rate
  /next             what runs next on the timeline
  /trades           today's sim trades
  /tasks            scheduled-task results
  /pause <name>     pause a process (partial name ok, e.g. /pause quin)
  /resume <name>    resume it
  /mc               Mission Control URLs
  /help

DELIBERATELY read-only except pause/resume. No arbitrary shell — a chat bot that can run
commands is a remote shell the moment the token leaks. Pause/resume only toggles a
scheduled task's enabled state, which is reversible and low-blast-radius.

Runs as a resident loop (single instance). Launched at startup alongside the status light.
    python scripts/telegram_bot.py
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
NOWIN = 0x08000000
API = "https://api.telegram.org/bot{token}/{method}"


def _cfg():
    import notify_telegram as tg
    return tg._load()


def _api(token, method, **params):
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=70) as r:
        return json.loads(r.read().decode())


def _single_instance() -> bool:
    global _LOCK
    try:
        _LOCK = socket.socket()
        _LOCK.bind(("127.0.0.1", 49732))
        _LOCK.listen(1)
        return True
    except OSError:
        return False


# ----------------------------------------------------------------- command handlers
def cmd_health(_arg):
    import pipeline_health as ph
    h = ph.health()
    icon = {"ok": "🟢", "warn": "🟠", "bad": "🔴", "idle": "⚪"}
    lines = [f"{h['overall'].upper()} · market {h['market']} · {h['chicago']} CT", ""]
    for c in h["checks"]:
        lines.append(f"{icon.get(c['state'],'·')} {c['name']}: {c['detail']}")
    return "\n".join(lines)


def cmd_depth(_arg):
    import pipeline_health as ph
    c = ph.check_depth()
    b, t = c.get("book"), c.get("tape")
    extra = f" · {b} book / {t} tape in tail" if b is not None else ""
    return f"L2 depth: {c['detail']}{extra}"


def cmd_next(_arg):
    import pipeline_health as ph
    sess = ph.session_info()
    try:
        import process_registry as reg
        best = None
        for _, _, items in reg.by_phase():
            for pr in items:
                if pr["ct"] == "cont":
                    continue
                e = ph.next_process_epoch(pr["ct"])
                if best is None or e < best[0]:
                    best = (e, pr)
        if best:
            mins = (best[0] - sess["chicago_epoch"]) / 60
            return f"NEXT UP: {best[1]['title']} at {best[1]['ct']} CT (in {mins:.0f} min)\n{best[1]['what']}"
    except Exception:
        pass
    return "timeline unavailable"


def cmd_trades(_arg):
    import pandas as pd
    import datetime as dt
    f = ROOT / "data" / "options_log" / "trades.parquet"
    if not f.exists():
        return "no trade log"
    d = pd.read_parquet(f)
    today = dt.date.today().isoformat()
    td = d[d.entry_dt.astype(str).str.startswith(today)]
    op = d[d.exit_dt.astype(str).isin(["", "nan", "None", "NaT"])]
    if not len(td) and not len(op):
        return "no trades today · 0 open"
    out = [f"today: {len(td)} entered · {len(op)} open"]
    for _, r in td.tail(8).iterrows():
        pnl = r.get("pnl")
        p = f" {pnl:+,.0f}" if pnl == pnl else ""
        out.append(f"· {r.get('structure','?')} {r.get('close_reason','open')}{p}")
    return "\n".join(out)


def cmd_tasks(_arg):
    import pipeline_health as ph
    ts = ph.task_status()
    bad = [n for n, v in ts.items()
           if v.get("result") not in (0, 267009, 267011, 267014) and v.get("day") not in (0, 6)]
    paused = [n for n, v in ts.items() if str(v.get("tstate", "")).lower() == "disabled"]
    out = [f"{len(ts)} tasks · {len(bad)} failing · {len(paused)} paused"]
    for n in bad:
        out.append(f"🟠 {n[8:]}: result {ts[n]['result']}")
    for n in paused:
        out.append(f"⏸ {n[8:]} (paused)")
    return "\n".join(out) if len(out) > 1 else out[0] + " — all clean"


def _find_task(part):
    import pipeline_health as ph
    part = part.strip().lower()
    for n in ph.task_status():
        if part in n.lower():
            return n
    return None


def cmd_pause(arg, pause=True):
    if not arg:
        return "usage: /pause <name>  e.g. /pause quin"
    name = _find_task(arg)
    if not name:
        return f"no task matching '{arg}'"
    verb = "Disable" if pause else "Enable"
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-Command", f"{verb}-ScheduledTask -TaskName '{name}'"],
                       capture_output=True, timeout=30, creationflags=NOWIN)
        return f"{'⏸ paused' if pause else '▶ resumed'}: {name[8:]}"
    except Exception as e:
        return f"failed: {e}"


def cmd_mc(_arg):
    return ("Mission Control: http://localhost:8590\n"
            "Timeline: http://localhost:8590/timeline\n"
            "Health: http://localhost:8590/health")


def cmd_help(_arg):
    return ("/status /health · /depth · /next · /trades · /tasks\n"
            "/pause <name> · /resume <name> · /mc · /help")


HANDLERS = {
    "/status": cmd_health, "/health": cmd_health, "/depth": cmd_depth,
    "/next": cmd_next, "/trades": cmd_trades, "/tasks": cmd_tasks,
    "/pause": lambda a: cmd_pause(a, True), "/resume": lambda a: cmd_pause(a, False),
    "/mc": cmd_mc, "/help": cmd_help, "/start": cmd_help,
}


def handle(text):
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]        # strip @botname if present
    arg = parts[1] if len(parts) > 1 else ""
    fn = HANDLERS.get(cmd)
    if not fn:
        return f"unknown: {cmd}\n{cmd_help('')}"
    try:
        return fn(arg)
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


def main() -> int:
    cfg = _cfg()
    if not cfg.get("token"):
        print("telegram not configured — run notify_telegram.py --setup first")
        return 2
    if not _single_instance():
        print("telegram_bot already running")
        return 0
    token, my_chat = cfg["token"], int(cfg["chat_id"])
    print(f"telegram bot listening (chat {my_chat} only)")
    offset = None
    while True:
        try:
            params = {"timeout": 60}
            if offset is not None:
                params["offset"] = offset
            upd = _api(token, "getUpdates", **params)
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if not msg or "text" not in msg:
                    continue
                if int(msg["chat"]["id"]) != my_chat:      # LOCK: only the owner
                    continue
                reply = handle(msg["text"])
                _api(token, "sendMessage", chat_id=my_chat, text=reply[:3900])
        except Exception as e:
            print(f"poll error: {type(e).__name__}: {e}")
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
