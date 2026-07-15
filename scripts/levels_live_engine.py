"""LIVE forward-test engine for the gamma-level fade suite (S73 — goes live today).

The three validated first-touch fades (note 0016 §4.4 panel), traded on ES:
  SHORT first from-below touch of CR (major)     strategy_id lvlfade_cr_ES
  SHORT first from-below touch of CR-0DTE        strategy_id lvlfade_cr0_ES
  LONG  first from-above touch of PS-0DTE        strategy_id lvlfade_ps0_ES
Dedup: if CR and CR0 are within 5 pts, only the CR (major) rule arms.
Exits: stop 8 / target 10 ES pts, else mark at 15:55 ET close-out.

Price source: es_est from data/options_sim/live.json (parity SPX + measured basis,
written by spot_feed.py every ~5s). Synthetic 1-min closes maintained for the
approach-from-below test. Fill quality flagged fill_model="es_est_sim" — this is a
SIM on estimated ES; ±1pt basis error is part of what live verification measures.

Trades write into the SAME unified log as the options (data/options_log/trades.parquet)
-> they appear in the app/cards/journal automatically.

Run all day (Task Scheduler 9:32 ET or manual):
  .venv/Scripts/python.exe scripts/levels_live_engine.py
"""
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
LIVE = ROOT / "data" / "options_sim" / "live.json"
AUDIT = ROOT / "data" / "options_sim" / "levels_engine_log.csv"
STOP, TGT = 8.0, 10.0
FRICTION_NOTE = 1.25  # pts, recorded for analysis; sim pnl kept gross+flagged
CLOSE_OUT = dt.time(15, 55)


def now():
    return dt.datetime.now(ET)


def audit(msg, **kv):
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    new = not AUDIT.exists()
    with open(AUDIT, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts_et", "msg", "detail"])
        w.writerow([now().strftime("%Y-%m-%d %H:%M:%S"), msg, json.dumps(kv)])
    print(f"[{now():%H:%M:%S}] {msg} {kv}", flush=True)


def todays_levels():
    """ES levels for today via the direct MQ API (computed prior EOD -> causal)."""
    from mq_api import MQ
    mq = MQ()
    lv = mq.get("gamma-levels/ES1!/eod")
    out = {"cr": lv.get("call_resistance"), "cr0": lv.get("call_resistance_0dte"),
           "ps0": lv.get("put_support_0dte"), "ps": lv.get("put_support"),
           "hvl": lv.get("hvl")}
    return out, lv


def spot():
    try:
        d = json.loads(LIVE.read_text(encoding="utf-8"))
        if d.get("state") == "live" and d.get("es_est"):
            return float(d["es_est"])
    except Exception:
        pass
    return None


class Rule:
    def __init__(self, name, level, kind):
        self.name, self.level, self.kind = name, level, kind
        self.state = "armed"          # armed -> in_trade -> done
        self.entry_time = None
        self.trade_id = None

    def from_ok(self, closes):
        ref = closes[-3:]
        if len(ref) < 2:
            return False
        if self.kind == "res":
            return max(ref) < self.level - 0.5
        return min(ref) > self.level + 0.5


def main():
    levels, raw = todays_levels()
    if not levels.get("cr0"):
        audit("no levels — abort", raw=str(raw)[:200])
        return
    audit("levels loaded", **{k: v for k, v in levels.items()})
    rules = []
    dedup = (levels["cr"] and levels["cr0"] and abs(levels["cr"] - levels["cr0"]) <= 5)
    if levels["cr"]:
        rules.append(Rule("lvlfade_cr_ES", levels["cr"], "res"))
    if levels["cr0"] and not dedup:
        rules.append(Rule("lvlfade_cr0_ES", levels["cr0"], "res"))
    if dedup:
        audit("dedup: CR and CR0 within 5pts — CR(major) only", cr=levels["cr"], cr0=levels["cr0"])
    if levels["ps0"]:
        rules.append(Rule("lvlfade_ps0_ES", levels["ps0"], "long"))
    # normalize kind naming
    for r in rules:
        if r.kind == "long":
            r.kind = "sup"

    closes = []          # synthetic 1-min closes
    last_min = None
    day = now().strftime("%Y-%m-%d")
    audit("engine armed", rules=[(r.name, r.level) for r in rules])

    while now().time() < dt.time(16, 0):
        s = spot()
        t = now()
        if s is None:
            time.sleep(5)
            continue
        minute = t.strftime("%H:%M")
        if minute != last_min:
            closes.append(s)
            closes = closes[-10:]
            last_min = minute
        # side-lock: max ONE live short-side and ONE live long-side trade at a time
        # (CR and CR0 are the SAME strike 37% of days; correlated risk otherwise)
        res_busy = any(r.state == "in_trade" and r.kind == "res" for r in rules)
        sup_busy = any(r.state == "in_trade" and r.kind == "sup" for r in rules)
        for r in rules:
            if r.state == "armed" and (
                    (r.kind == "res" and res_busy) or (r.kind == "sup" and sup_busy)):
                continue
            if r.state == "armed" and r.from_ok(closes[:-1]) and (
                    (r.kind == "res" and s >= r.level - 1.0) or
                    (r.kind == "sup" and s <= r.level + 1.0)):
                res_busy = res_busy or r.kind == "res"
                sup_busy = sup_busy or r.kind == "sup"
                r.state = "in_trade"
                r.entry_time = t
                r.trade_id = f"{r.name}_{t:%Y%m%d}"
                side = "sell" if r.kind == "res" else "buy"
                tlog.append_entry({
                    "trade_id": r.trade_id, "strategy_id": r.name, "source": "sim",
                    "symbol": "ES", "entry_dt": t.strftime("%Y-%m-%d %H:%M"),
                    "dte": 0, "structure": f"futures {'short' if side=='sell' else 'long'} "
                                           f"@ level {r.level:.0f} (stop {STOP:.0f}/tgt {TGT:.0f})",
                    "fill_model": "es_est_sim",
                    "legs": [{"side": side, "right": "F", "strike": float(r.level),
                              "expiry": t.strftime("%Y%m%d"), "qty": 1}],
                    "credit": 0.0, "collateral": STOP * 50,
                    "max_gain": TGT * 50, "max_loss": -STOP * 50,
                    "commentary": f"LIVE forward-test of note 0016 panel rule: first "
                                  f"{'from-below' if r.kind=='res' else 'from-above'} touch of "
                                  f"{r.name.split('_')[1].upper()} at {r.level:.0f}. Entry on "
                                  f"es_est {s:.2f}. Backtest ref: +$123-344/trade.",
                    "grade": "B", "dow": t.strftime("%a"),
                })
                audit("ENTRY", rule=r.name, level=r.level, es_est=s)
        for r in rules:
            if r.state != "in_trade":
                continue
            if r.kind == "res":
                hit_stop, hit_tgt = s >= r.level + STOP, s <= r.level - TGT
            else:
                hit_stop, hit_tgt = s <= r.level - STOP, s >= r.level + TGT
            force = t.time() >= CLOSE_OUT
            if hit_stop or hit_tgt or force:
                pts = (-STOP if hit_stop else TGT if hit_tgt else
                       ((r.level - s) if r.kind == "res" else (s - r.level)))
                r.state = "done"
                # exit_cost bookkeeping: pnl = (credit - exit_cost)*100 - fees
                # futures: use exit_cost = -pts*0.5 so pnl = pts*50 (log stores $/100 units)
                tlog.update_exit(r.trade_id, t.strftime("%Y-%m-%d %H:%M"),
                                 -pts * 0.5, FRICTION_NOTE * 50,
                                 fill_model="es_est_sim")
                audit("EXIT", rule=r.name, reason="stop" if hit_stop else
                      "target" if hit_tgt else "closeout", pts=round(pts, 2), es_est=s)
        if all(r.state == "done" for r in rules):
            break
        time.sleep(5)
    audit("engine done", states={r.name: r.state for r in rules})


if __name__ == "__main__":
    main()
