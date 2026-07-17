#!/usr/bin/env python3
"""
discord_scrape.py — export a Discord channel via DiscordChatExporter, then parse
the JSON into a flat JSONL/CSV the myquant pipeline can consume.

Two modes:
  backfill     full history export (one time)
  incremental  export only messages after the last saved timestamp

Config lives in data/discord/config.json (gitignored). Example:
{
  "dce_exe": "C:/tools/DiscordChatExporter/DiscordChatExporter.Cli.exe",
  "token": "YOUR_USER_TOKEN",
  "channels": {
    "levels":    "123456789012345678",
    "chat":      "234567890123456789"
  }
}

NOTE: using a personal USER token to export is against Discord's ToS and carries
a small account-ban risk. Keep cadence modest. Only export channels you can
legitimately read.

Usage:
  python scripts/discord_scrape.py backfill               # all channels, full history
  python scripts/discord_scrape.py backfill --channel levels
  python scripts/discord_scrape.py incremental            # all channels, since last run
  python scripts/discord_scrape.py incremental --channel levels
"""
from __future__ import annotations
import argparse, json, subprocess, sys, csv
from datetime import datetime, timezone
from pathlib import Path

# Windows: run the DCE child with no console window so launcher-spawned
# (pythonw) scrapes don't flash black boxes on the desktop.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

ROOT = Path(__file__).resolve().parents[1]
DISCORD_DIR = ROOT / "data" / "discord"
RAW_DIR = DISCORD_DIR / "raw"
PARSED_DIR = DISCORD_DIR / "parsed"
CONFIG = DISCORD_DIR / "config.json"
STATE = DISCORD_DIR / "state.json"


def load_config() -> dict:
    if not CONFIG.exists():
        sys.exit(f"[discord_scrape] missing config: {CONFIG}\n"
                 f"Create it with your token + channel ids (see script header).")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def utcstamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def export_channel(cfg: dict, name: str, chan_id: str, after: str | None) -> Path | None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = RAW_DIR / f"{name}_{ts}.json"
    cmd = [
        cfg["dce_exe"], "export",
        "-t", cfg["token"],
        "-c", chan_id,
        "-f", "Json",
        "-o", str(out),
    ]
    if after:
        cmd += ["--after", after]
    print(f"[discord_scrape] exporting '{name}' ({chan_id})"
          + (f" after {after}" if after else " (full history)"))
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        print(f"[discord_scrape] export FAILED for '{name}'", file=sys.stderr)
        return None
    if not out.exists():
        print(f"[discord_scrape] no new messages for '{name}'")
        return None
    print(f"[discord_scrape] wrote {out.name}")
    return out


def parse_export(raw_path: Path, name: str) -> tuple[int, str | None]:
    """Flatten a DCE JSON export into parsed/<name>.jsonl and .csv (append).
    Returns (message_count, last_timestamp)."""
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    msgs = data.get("messages", [])
    if not msgs:
        return 0, None
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    jsonl = PARSED_DIR / f"{name}.jsonl"
    csvp = PARSED_DIR / f"{name}.csv"
    rows = []
    for m in msgs:
        rows.append({
            "id": m.get("id"),
            "timestamp": m.get("timestamp"),
            "author": (m.get("author") or {}).get("name"),
            "author_id": (m.get("author") or {}).get("id"),
            "content": (m.get("content") or "").replace("\n", " ").strip(),
            "attachments": "|".join(a.get("url", "") for a in m.get("attachments", [])),
            "embeds": len(m.get("embeds", [])),
            "reactions": "|".join(
                f"{(r.get('emoji') or {}).get('name','')}:{r.get('count',0)}"
                for r in m.get("reactions", [])
            ),
        })
    with jsonl.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_header = not csvp.exists()
    with csvp.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if write_header:
            w.writeheader()
        w.writerows(rows)
    last_ts = msgs[-1].get("timestamp")
    print(f"[discord_scrape] parsed {len(rows)} msgs -> {jsonl.name} / {csvp.name}")
    return len(rows), last_ts


def run(mode: str, only: str | None, after_date: str | None = None):
    cfg = load_config()
    state = load_state()
    channels = cfg.get("channels", {})
    if only:
        if only not in channels:
            sys.exit(f"[discord_scrape] unknown channel '{only}'. "
                     f"Known: {', '.join(channels)}")
        channels = {only: channels[only]}
    if not channels:
        sys.exit("[discord_scrape] no channels configured.")

    for name, chan_id in channels.items():
        after = None
        if mode == "incremental":
            after = state.get(name, {}).get("last_timestamp")
            if not after:
                # a date floor makes a first pull fast (recent history only)
                after = after_date
                print(f"[discord_scrape] no prior state for '{name}', "
                      + (f"pulling since {after_date}." if after_date else "doing full history."))
        elif mode == "backfill":
            # backfill honors --after too, so we can grab only recent history
            after = after_date
        raw = export_channel(cfg, name, chan_id, after)
        if raw is None:
            continue
        count, last_ts = parse_export(raw, name)
        if last_ts:
            state.setdefault(name, {})
            state[name]["last_timestamp"] = last_ts
            state[name]["last_run"] = utcstamp()
            state[name]["last_count"] = count
            save_state(state)


def main():
    ap = argparse.ArgumentParser(description="Scrape a Discord channel via DiscordChatExporter.")
    ap.add_argument("mode", choices=["backfill", "incremental"])
    ap.add_argument("--channel", help="only this named channel (default: all)")
    ap.add_argument("--after", dest="after_date",
                    help="only messages after this date, e.g. 2026-04-01 "
                         "(makes a first pull fast — skips years of old chat)")
    args = ap.parse_args()
    run(args.mode, args.channel, args.after_date)


if __name__ == "__main__":
    main()
