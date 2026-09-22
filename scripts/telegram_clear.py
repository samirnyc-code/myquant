"""telegram_clear.py — delete recent messages from the MyQuant alert chat.

Telegram's Bot API has NO "clear chat" / bulk-delete method. deleteMessage works
one id at a time, and ONLY on messages < 48h old (bot's own + the user's, in a
private chat). We never stored the sent ids, but message_id is sequential per chat,
so: send a probe to learn the current max id, then walk downward calling
deleteMessage until we hit a long run of failures (the 48h boundary / already-gone).

  python scripts/telegram_clear.py            # delete downward from newest
  python scripts/telegram_clear.py --max 3000 # scan-depth backstop (default 3000)
  python scripts/telegram_clear.py --stop 60  # consecutive-fail cutoff (default 60)

Only touches the one chat_id in %LOCALAPPDATA%/myquant/telegram.json. Irreversible.
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

CFG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "myquant" / "telegram.json"
API = "https://api.telegram.org/bot{token}/{method}"


def _api(token: str, method: str, **params):
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=15) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=3000, help="max ids to scan downward")
    ap.add_argument("--stop", type=int, default=60, help="stop after this many consecutive failures")
    a = ap.parse_args()

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    token, chat_id = cfg["token"], cfg["chat_id"]

    # Probe: send a throwaway to learn the current max message_id, then delete it.
    probe = _api(token, "sendMessage", chat_id=chat_id, text="🧹 clearing…",
                 disable_notification=True)
    if not probe.get("ok"):
        print(f"probe failed: {probe}")
        return 1
    top = probe["result"]["message_id"]
    _api(token, "deleteMessage", chat_id=chat_id, message_id=top)

    deleted = 0
    consecutive_fail = 0
    mid = top - 1
    scanned = 0
    while scanned < a.max and mid > 0 and consecutive_fail < a.stop:
        try:
            r = _api(token, "deleteMessage", chat_id=chat_id, message_id=mid)
            ok = bool(r.get("ok"))
        except Exception:
            ok = False
        if ok:
            deleted += 1
            consecutive_fail = 0
        else:
            consecutive_fail += 1
        mid -= 1
        scanned += 1
        time.sleep(0.04)  # stay under Telegram's per-chat rate limit

    print(f"deleted {deleted} messages "
          f"(scanned {scanned} ids from {top} down to {mid + 1}; "
          f"stopped on {'fail-run' if consecutive_fail >= a.stop else 'scan-limit'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
