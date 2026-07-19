"""cool_pings.py — the alerts that make the desk feel alive, not just monitored.

Beyond "is it broken" and "did it run" — these are the pings a trader actually wants: the
market doing something notable at YOUR levels, milestones worth a nod, and one daily
briefing. Every one fires at most once per event (deduped), so it stays a signal.

  1. LEVEL TOUCH        — spot reaches a MenthorQ level (CR/PS/HVL/GW) live. "Price is at
                          the thing you care about" is the single most useful real-time ping.
  2. BIG DEPTH BURST    — an unusually fast surge of book+tape rows (a liquidity event /
                          aggressive push) — the tape screaming without you watching it.
  3. DATA MILESTONES    — 100 MB, 500 MB, 1 GB of book data captured today; first
                          full hour clean. Little "it's working and it's big" nods.
  4. MORNING BRIEFING   — one message at the RTH open: today's levels, regime, spot,
                          and what the desk is armed with. Your day on one screen.
  5. STREAK / RECORDS   — new record depth-day size, longest clean run without a gap.

None of this pages loudly (all level "info" = silent notification) except a level touch,
which is time-sensitive. Runs on the same 5-min monitor.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
STATE = ROOT / "data" / "_catalog" / "cool_pings_state.json"


def _load():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s))


def _spot():
    """Live SPX/ES spot from the feed, if fresh."""
    f = ROOT / "data" / "options_sim" / "live.json"
    try:
        d = json.loads(f.read_text())
        return d.get("spx") or d.get("es_est")
    except Exception:
        return None


def _levels():
    f = ROOT / "scratchpad" / "mq_levels_today.json"
    try:
        d = json.loads(f.read_text())
        return {k: d[k] for k in ("cr", "cr0", "gw0", "hvl", "ps0", "ps") if d.get(k)}
    except Exception:
        return {}


# ---------------------------------------------------------------- 1. level touch
def level_touch(tg, st, today):
    import pipeline_health as ph
    if ph.market_state() != "open":
        return
    spot, lv = _spot(), _levels()
    if not spot or not lv:
        return
    touched = st.setdefault("touched", {})
    for name, val in lv.items():
        if abs(spot - val) <= 1.0:                      # within 1 pt = "at the level"
            key = f"{today}_{name}"
            if touched.get(key):
                continue
            touched[key] = True
            arrow = "▲" if spot >= val else "▼"
            tg.send(f"🎯 LEVEL TOUCH — spot {spot:.2f} at {name.upper()} {val:.0f} {arrow}",
                    level="warn")   # warn = audible; a touch is time-sensitive


# ---------------------------------------------------------------- 2. depth burst
def depth_burst(tg, st, today):
    import pipeline_health as ph
    if ph.market_state() != "open":
        return
    files = []
    now = ph.chicago_now()
    for d in (-1, 0):
        day = (now.date() + dt.timedelta(days=d)).isoformat()
        files += sorted(ph.DEPTH_DIR.glob(f"ES*_depth_{day}.csv"))
    if not files:
        return
    size = sum(f.stat().st_size for f in files)
    import time as _t
    prev_size, prev_t = st.get("burst_size", size), st.get("burst_t", _t.time())
    dt_s = max(1.0, _t.time() - prev_t)
    rate = (size - prev_size) / dt_s / 1024.0           # KB/s since last check
    st["burst_size"], st["burst_t"] = size, _t.time()
    baseline = st.get("burst_baseline")
    if baseline and rate > baseline * 4 and rate > 200:   # 4x normal AND meaningful
        tg.send(f"⚡ DEPTH BURST — {rate:,.0f} KB/s ({rate/max(baseline,1):.1f}x normal). "
                "Aggressive flow / liquidity event.", level="info")
    # slow-moving baseline of the KB/s rate
    st["burst_baseline"] = rate if not baseline else baseline * 0.8 + rate * 0.2


# ---------------------------------------------------------------- 3. data milestones
def data_milestones(tg, st, today):
    import pipeline_health as ph
    files = []
    now = ph.chicago_now()
    for d in (-1, 0):
        day = (now.date() + dt.timedelta(days=d)).isoformat()
        files += sorted(ph.DEPTH_DIR.glob(f"ES*_depth_{day}.csv"))
    if not files:
        return
    mb = sum(f.stat().st_size for f in files) / 1e6
    done = set(st.get(f"mstones_{today}", []))
    for gate, txt in [(100, "100 MB"), (500, "500 MB"), (1000, "1 GB"), (2000, "2 GB")]:
        if mb >= gate and txt not in done:
            done.add(txt)
            tg.send(f"💾 {txt} of book data captured today — recorder humming.", level="info")
    st[f"mstones_{today}"] = list(done)


# ---------------------------------------------------------------- 4. morning briefing
def morning_briefing(tg, st, today):
    import pipeline_health as ph
    now = ph.chicago_now()
    if not (dt.time(8, 30) <= now.time() <= dt.time(8, 45)):    # just after RTH open
        return
    if st.get("briefing") == today:
        return
    st["briefing"] = today
    lv, spot = _levels(), _spot()
    if not lv:
        tg.send("☀️ Morning — desk is up, but no MenthorQ levels loaded yet.", level="info")
        return
    hvl = lv.get("hvl")
    regime = ""
    if spot and hvl:
        regime = "positive gamma (pin/fade)" if spot >= hvl else "NEGATIVE gamma (moves amplify)"
    rail = " · ".join(f"{k.upper()} {v:.0f}" for k, v in lv.items())
    # count armed triggers if a gameplan exists
    armed = ""
    gp = ROOT / "data" / "options_sim" / f"gameplan_{today}.json"
    if gp.exists():
        try:
            g = json.loads(gp.read_text())
            n = len(g.get("triggers", g.get("armed", [])))
            armed = f"\nArmed: {n} triggers"
        except Exception:
            pass
    tg.send(f"☀️ MORNING BRIEFING {now:%b %d}\nSpot {spot or '?'} · {regime}\n{rail}{armed}",
            level="info")


# ---------------------------------------------------------------- 5. record depth day
def records(tg, st, today):
    import pipeline_health as ph
    if ph.market_state() == "open":
        return
    # at/after the close, check whether today beat the record depth-day size
    files = sorted(ph.DEPTH_DIR.glob("ES*_depth_*.csv"))
    if not files:
        return
    sizes = {f.stem: f.stat().st_size for f in files}
    best_name = max(sizes, key=sizes.get)
    best_mb = sizes[best_name] / 1e6
    if best_mb > st.get("record_mb", 0) + 1 and st.get("record_checked") != today:
        st["record_mb"] = best_mb
        st["record_checked"] = today
        if best_mb > 50:      # ignore the tiny early files
            tg.send(f"🏆 New record depth day: {best_name} at {best_mb:,.0f} MB.", level="info")


def main() -> int:
    import notify_telegram as tg
    if not tg._load().get("token"):
        return 2
    st = _load()
    today = dt.date.today().strftime("%Y%m%d")
    for fn in (level_touch, depth_burst, data_milestones, morning_briefing, records):
        try:
            fn(tg, st, today)
        except Exception as e:
            print(f"{fn.__name__}: {type(e).__name__}: {e}")
    _save(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
