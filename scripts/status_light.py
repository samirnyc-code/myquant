"""status_light.py — always-on-top traffic light for the recording pipeline.

A small draggable strip (default: bottom-LEFT, above the taskbar) showing whether the
things that cannot be re-collected are actually being collected right now.

    GREEN  recording, rows arriving
    AMBER  market open but nothing for a while / market in the daily halt
    RED    market open and the file is NOT growing  -> data is being lost
    GREY   market closed (nothing expected)

The light is driven by DATA, not by process state: "NinjaTrader.exe is running" would
have shown green through every failure we hit today (login prompt, disabled strategy,
missing depth subscription). Only row growth proves the pipeline works.

    python scripts/status_light.py
    python scripts/status_light.py --corner br      # bottom-right instead
    python scripts/status_light.py --once           # print status and exit (for scripts)

Drag it anywhere; the position is remembered. Right-click for the menu.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))   # so pipeline_health imports
DEPTH_DIR = ROOT / "data" / "depth"
FOOTPRINT_DIR = ROOT / "data" / "footprint"
STATE_FILE = ROOT / "data" / "_catalog" / "status_light.json"
MISSION_CONTROL = "http://localhost:8590"

STALE_SEC = 180          # market open + no new bytes this long = RED
SYMBOL = "ES"

GREEN, AMBER, RED, GREY = "#22c55e", "#f59e0b", "#ef4444", "#6b7280"


# --------------------------------------------------------------------------- clock
def chicago_now() -> dt.datetime:
    """NT8 and every timestamp in the data run on Chicago time; this PC runs Berlin.
    Every check here MUST be Chicago-anchored or the market-hours logic is 7h wrong."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago"))
    except Exception:
        return dt.datetime.utcnow() - dt.timedelta(hours=5)


def market_state(now: dt.datetime | None = None) -> str:
    """'open' | 'halt' | 'closed' for CME equity index futures (Globex).
    Sun 17:00 -> Fri 16:00 CT, with a daily 16:00-17:00 CT maintenance halt."""
    now = now or chicago_now()
    wd, t = now.weekday(), now.time()          # Mon=0 .. Sun=6
    if wd == 5:                                 # Saturday
        return "closed"
    if wd == 6:                                 # Sunday: opens 17:00
        return "open" if t >= dt.time(17, 0) else "closed"
    if wd == 4 and t >= dt.time(16, 0):         # Friday close
        return "closed"
    if dt.time(16, 0) <= t < dt.time(17, 0):    # daily halt
        return "halt"
    return "open"


# --------------------------------------------------------------------------- probe
def _depth_files(now: dt.datetime):
    """An ETH session straddles Chicago midnight -> today's data can be in two files."""
    out = []
    for delta in (-1, 0):
        d = (now.date() + dt.timedelta(days=delta)).isoformat()
        p = DEPTH_DIR / f"{SYMBOL}_depth_{d}.csv"
        if p.exists():
            out.append(p)
    return out


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(s: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(s))
    except Exception:
        pass


def probe() -> dict:
    """Return {color, short, detail} for the widget.

    Delegates the actual checks to pipeline_health so the light, Mission Control and the
    console all report from ONE source of truth. Falls back to the depth-only probe below
    if that import fails, so the light never goes dark just because a check has a bug.
    """
    try:
        import pipeline_health as ph
    except Exception:
        return _probe_depth_only()

    h = ph.health()
    sev = {ph.OK: GREEN, ph.IDLE: GREY, ph.WARN: AMBER, ph.BAD: RED}
    by = {c["name"]: c for c in h["checks"]}

    depth = by.get("L2 depth", {})
    contract = by.get("Contract", {})
    mb = depth.get("mb", 0)

    # the label must answer "recording WHAT?" - a healthy-looking file on a dead contract
    # is the failure this is here to catch
    tag = f"ES {contract.get('active', '??')}"
    if contract.get("state") == ph.BAD:
        tag = f"!! {tag}"
    short = f"{tag} · {mb:,.0f}MB" if mb else f"{tag} · {h['market']}"

    bad = [c for c in h["checks"] if c["state"] in (ph.BAD, ph.WARN)]
    lines = [f"{c['name']}: {c['detail']}" for c in h["checks"]]
    detail = (f"overall {h['overall'].upper()}   market {h['market']}   {h['chicago']} CT\n"
              + "-" * 44 + "\n" + "\n".join(lines))
    if bad:
        detail += f"\n\n{len(bad)} item(s) need attention"
    return dict(color=sev.get(h["overall"], GREY), short=short, detail=detail)


def _probe_depth_only() -> dict:
    """Fallback: depth file only (used if pipeline_health cannot be imported)."""
    now = chicago_now()
    mkt = market_state(now)
    files = _depth_files(now)

    size = sum(f.stat().st_size for f in files)
    newest = max((f.stat().st_mtime for f in files), default=0)

    prev = _load_state()
    prev_size, prev_ts = prev.get("size", 0), prev.get("ts", 0)
    wall = dt.datetime.now().timestamp()

    grew = size > prev_size
    if grew:
        prev["last_growth"] = wall
    last_growth = prev.get("last_growth", 0)
    rate = 0.0
    if grew and prev_ts:
        dtsec = max(1e-6, wall - prev_ts)
        rate = (size - prev_size) / dtsec / 1024.0          # KB/s
    _save_state({"size": size, "ts": wall, "last_growth": prev.get("last_growth", 0)})

    stale = wall - last_growth if last_growth else 1e9
    mb = size / 1e6

    if not files:
        if mkt == "open":
            return dict(color=RED, short="NO FILE",
                        detail=f"market OPEN but no depth file for {now.date()}\nrecorder is not running")
        return dict(color=GREY, short="closed", detail=f"market {mkt} - no file yet")

    fp = sorted(FOOTPRINT_DIR.glob("*_footprint_*.csv"))
    fp_txt = f"\nfootprint: {fp[-1].name}" if fp else "\nfootprint: (none)"

    base = (f"depth {mb:,.1f} MB\n"
            f"files: {', '.join(f.name for f in files)}\n"
            f"market: {mkt} ({now:%H:%M} CT){fp_txt}")

    if mkt == "closed":
        return dict(color=GREY, short=f"{mb:,.0f}MB", detail=f"market closed - nothing expected\n{base}")
    if mkt == "halt":
        return dict(color=AMBER, short="halt", detail=f"daily maintenance halt 16:00-17:00 CT\n{base}")
    if grew or stale < STALE_SEC:
        return dict(color=GREEN, short=f"{mb:,.0f}MB {rate:,.0f}KB/s" if rate else f"{mb:,.0f}MB",
                    detail=f"RECORDING\n{base}")
    return dict(color=RED, short="STALLED",
                detail=f"market OPEN but no new data for {stale/60:,.1f} min\nDATA IS BEING LOST\n{base}")


# --------------------------------------------------------------------------- ui
def _single_instance() -> bool:
    """One widget only. Five copies were running at once on 2026-07-19 (relaunch without a
    working kill), each polling every 10s - that is what made console windows strobe.
    A bound socket is the cheapest cross-process lock and dies with the process."""
    global _LOCK
    try:
        _LOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _LOCK.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        _LOCK.bind(("127.0.0.1", 49731))
        _LOCK.listen(1)
        return True
    except OSError:
        return False


def run_widget(corner: str) -> None:
    import tkinter as tk

    if not _single_instance():
        print("status_light already running - exiting")
        return

    st = _load_state()
    root = tk.Tk()
    root.overrideredirect(True)              # borderless
    root.attributes("-topmost", True)
    root.configure(bg="#0f172a")
    W, H = 250, 26

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    pos = st.get("pos")
    if pos:
        x, y = pos
    else:
        # bottom-LEFT, sitting just above a standard taskbar
        x, y = (12, sh - H - 56) if corner == "bl" else (sw - W - 12, sh - H - 56)
    root.geometry(f"{W}x{H}+{int(x)}+{int(y)}")

    cv = tk.Canvas(root, width=16, height=H, bg="#0f172a", highlightthickness=0)
    cv.pack(side="left", padx=(7, 4))
    dot = cv.create_oval(3, H // 2 - 5, 13, H // 2 + 5, fill=GREY, outline="")
    lbl = tk.Label(root, text="starting", fg="#e2e8f0", bg="#0f172a",
                   font=("Segoe UI", 8), anchor="w")
    lbl.pack(side="left", fill="x", expand=True)

    tip = {"win": None}

    def show_tip(_=None):
        if tip["win"] or not hasattr(root, "_detail"):
            return
        t = tk.Toplevel(root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        tk.Label(t, text=root._detail, justify="left", bg="#1e293b", fg="#e2e8f0",
                 font=("Consolas", 8), padx=8, pady=6).pack()
        t.update_idletasks()
        t.geometry(f"+{root.winfo_x()}+{root.winfo_y() - t.winfo_height() - 4}")
        tip["win"] = t

    def hide_tip(_=None):
        if tip["win"]:
            tip["win"].destroy()
            tip["win"] = None

    drag = {}

    def press(e):
        drag["x"], drag["y"] = e.x_root - root.winfo_x(), e.y_root - root.winfo_y()

    def move(e):
        root.geometry(f"+{e.x_root - drag.get('x', 0)}+{e.y_root - drag.get('y', 0)}")

    def release(_):
        s = _load_state(); s["pos"] = [root.winfo_x(), root.winfo_y()]; _save_state(s)

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Open Mission Control", command=lambda: webbrowser.open(MISSION_CONTROL))
    menu.add_command(label="Refresh now", command=lambda: tick(force=True))
    menu.add_separator()
    menu.add_command(label="Quit", command=root.destroy)

    for w in (root, lbl, cv):
        w.bind("<Button-1>", press)
        w.bind("<B1-Motion>", move)
        w.bind("<ButtonRelease-1>", release)
        w.bind("<Enter>", show_tip)
        w.bind("<Leave>", hide_tip)
        w.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        w.bind("<Double-Button-1>", lambda e: webbrowser.open(MISSION_CONTROL))

    def tick(force=False):
        try:
            s = probe()
            cv.itemconfig(dot, fill=s["color"])
            lbl.config(text=s["short"])
            root._detail = s["detail"]
            if tip["win"]:
                hide_tip(); show_tip()
        except Exception as e:
            lbl.config(text="err")
            root._detail = f"status_light error:\n{e}"
        root.after(30_000, tick)

    tick()
    root.mainloop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="bl", choices=["bl", "br"], help="bl=bottom-left (default)")
    ap.add_argument("--once", action="store_true", help="print status and exit")
    a = ap.parse_args()
    if a.once:
        s = probe()
        print(f"[{ {GREEN:'GREEN', AMBER:'AMBER', RED:'RED', GREY:'GREY'}[s['color']] }] {s['short']}")
        print(s["detail"])
        sys.exit(0 if s["color"] in (GREEN, GREY) else 1)
    run_widget(a.corner)


if __name__ == "__main__":
    main()
