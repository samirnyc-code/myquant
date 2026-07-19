"""notify_telegram.py — push alerts to the user's phone via a Telegram bot.

Only the alerts that matter overnight go here — depth died, NT8 disconnected, disk
critical. Wire it to everything and it becomes noise you mute, and then you mute the one
that mattered too.

SETUP (once):
  1. Telegram -> @BotFather -> /newbot -> copy the bot TOKEN.
  2. Send your new bot any message.
  3. python scripts/notify_telegram.py --setup <TOKEN>
     (auto-detects your chat id from that message and stores both, encrypted-at-rest
      outside the repo).

USE:
  python scripts/notify_telegram.py "test message"
  from notify_telegram import send; send("depth is TAPE ONLY", level="alert")

The token is a secret: stored in %LOCALAPPDATA%\myquant\telegram.json, which is NOT in
the repo. De-duplication (data/_catalog/telegram_sent.json) stops the same condition
paging you every poll — you get told once when it breaks and once when it recovers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "myquant" / "telegram.json"
SENT = ROOT / "data" / "_catalog" / "telegram_sent.json"
API = "https://api.telegram.org/bot{token}/{method}"


def _load() -> dict:
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _api(token: str, method: str, **params):
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=15) as r:
        return json.loads(r.read().decode())


def setup(token: str) -> int:
    """Find the chat id from the most recent message to the bot, then store both."""
    token = token.strip()
    try:
        upd = _api(token, "getUpdates")
    except Exception as e:
        print(f"cannot reach Telegram: {e}")
        return 1
    if not upd.get("ok"):
        print(f"bad token? response: {upd}")
        return 1
    results = upd.get("result", [])
    if not results:
        print("no messages found — send your bot any message first, then re-run --setup")
        return 1
    chat = results[-1]["message"]["chat"]
    chat_id, name = chat["id"], chat.get("first_name", "?")
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({"token": token, "chat_id": chat_id}), encoding="utf-8")
    print(f"stored: chat_id {chat_id} ({name}) -> {CFG}")
    send("✅ MyQuant alerts connected. You'll get pings for depth/NT8/disk problems only.")
    print("sent a confirmation message — check your phone.")
    return 0


def send(text: str, level: str = "info", dedup_key: str | None = None,
         cooldown_s: int = 3600) -> bool:
    """Send a message. Returns True if it went out.

    dedup_key: if given, the SAME key will not resend within cooldown_s — so a condition
    that is true on every 30s poll pings you once, not 120 times an hour.
    """
    cfg = _load()
    if not cfg.get("token"):
        return False

    if dedup_key:
        try:
            sent = json.loads(SENT.read_text()) if SENT.exists() else {}
        except Exception:
            sent = {}
        last = sent.get(dedup_key, 0)
        if time.time() - last < cooldown_s:
            return False
        sent[dedup_key] = time.time()
        SENT.parent.mkdir(parents=True, exist_ok=True)
        SENT.write_text(json.dumps(sent))

    icon = {"alert": "🔴", "warn": "🟠", "ok": "🟢", "info": "ℹ️"}.get(level, "")
    try:
        r = _api(cfg["token"], "sendMessage",
                 chat_id=cfg["chat_id"], text=f"{icon} {text}".strip(),
                 disable_notification=(level == "info"))
        return bool(r.get("ok"))
    except Exception:
        return False


def clear_dedup(key: str) -> None:
    """Forget a dedup key so its RECOVERY message can fire immediately."""
    try:
        sent = json.loads(SENT.read_text()) if SENT.exists() else {}
        sent.pop(key, None)
        SENT.write_text(json.dumps(sent))
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", metavar="TOKEN", help="store token + auto-detect chat id")
    ap.add_argument("msg", nargs="?", help="send this message")
    a = ap.parse_args()
    if a.setup:
        return setup(a.setup)
    if a.msg:
        ok = send(a.msg, level="info")
        print("sent" if ok else "NOT sent — run --setup first")
        return 0 if ok else 1
    if not _load().get("token"):
        print("not configured — run: python scripts/notify_telegram.py --setup <TOKEN>")
        return 1
    print(f"configured: chat {_load().get('chat_id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
