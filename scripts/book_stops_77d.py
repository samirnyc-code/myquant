"""book_stops_77d.py — 77-day desk-stop effect for the ENTIRE options book.

Reuses wall_pnl_stops.py's desk-rule machinery (identical stop logic: short-strike
acceptance >=10 min + 14:45 stop, mid combo-fill, parity spot) but runs it on EVERY
structure the live book arms, not just the gx walls:

  eodic_p/c   EM condor, short strikes at prior_close -/+ EM
  openic_p/c  EM condor, short strikes at OPEN -/+ EM
  eodfly_p/c  ATM fly, short strikes at prior_close
  openfly_p/c ATM fly, short strikes at OPEN
  gx_bps/bcs  wall condor, short strikes at gexlog put/call wall

Strikes from the gexlog morning brief (current/expectedMove/putWall/callWall). OPEN spot
= parity @ 09:31 at the prior-close strike. Each leg: stopped (desk rule) vs hold-to-settle.

VALIDATION: for AUGUST (where the live book actually traded these), compare the model's
per-structure stop-effect to the ANCHORED actual (live realized vs held-to-settle from
trades.parquet). Same self-check as gx_stop_vs_hold_actual: non-stopped live trades'
realized must equal the held computation.

Out: data/options_sim/book_stops_77d.csv    (needs the Theta Terminal up)
"""
from __future__ import annotations
import glob
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import wall_pnl_stops as W   # opt_path, stopped_side, _settle_side, _mid, _at_or_before, ENTRY_HM, STEP, WING
W.FILL, W.INTERVAL = "mid", "1m"

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
RAW = ROOT / "data" / "gexlog" / "raw"
WALL3 = SIM / "wall_pnl_3way.csv"
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
OUT = SIM / "book_stops_77d.csv"
STEP = W.STEP


def rnd(x):
    return round(x / STEP) * STEP if x is not None else None


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def brief(date):
    fp = RAW / f"{date}_morning.json"
    if not fp.exists():
        return None
    d = json.load(open(fp, encoding="utf-8")).get("levels", {}) or {}
    return {"pc": fnum(d.get("current")), "em": fnum(d.get("expectedMove")),
            "pw": fnum(d.get("putWall")), "cw": fnum(d.get("callWall"))}


def open_spot(date, pc):
    """parity spot @ 09:31 at the prior-close strike (rnd)."""
    k = rnd(pc)
    cp = W.opt_path(date, k, "call")
    pp = W.opt_path(date, k, "put")
    c = W._mid(W._at_or_before(cp, W.ENTRY_HM))
    p = W._mid(W._at_or_before(pp, W.ENTRY_HM))
    return (k + c - p) if (c is not None and p is not None) else None


def structures(date, b, op):
    """[(name, short_k, right)] for the whole book on this day."""
    pc, em, pw, cw = b["pc"], b["em"], b["pw"], b["cw"]
    S = []
    if pc and em:
        S += [("eodic_p", rnd(pc - em), "P"), ("eodic_c", rnd(pc + em), "C"),
              ("eodfly_p", rnd(pc), "P"), ("eodfly_c", rnd(pc), "C")]
    if op and em:
        S += [("openic_p", rnd(op - em), "P"), ("openic_c", rnd(op + em), "C"),
              ("openfly_p", rnd(op), "P"), ("openfly_c", rnd(op), "C")]
    if pw:
        S += [("gx_bps", rnd(pw), "P")]
    if cw:
        S += [("gx_bcs", rnd(cw), "C")]
    return S


def run_leg(job):
    date, sc, name, k, right = job
    r = W.stopped_side(date, k, right, 10)
    if r is None:
        return None
    settle = W._settle_side(r["credit"], k, right, sc)
    return {"date": date, "structure": name, "right": right, "K": k,
            "stopped_pnl": round(r["pnl"], 2), "settle_pnl": round(settle, 2),
            "reason": r["reason"]}


def anchored_august():
    """Live per-structure stop-effect (Aug), anchored + self-checked. Returns (df, ok, offset)."""
    spx = pd.read_csv(SIM / "spx_daily_yahoo.csv")
    close = dict(zip(spx["Date"].astype(str).str[:10], pd.to_numeric(spx["Close"], errors="coerce")))
    t = pd.read_parquet(TRADES)
    names = ["eodic_p", "eodic_c", "openic_p", "openic_c", "eodfly_p", "eodfly_c",
             "openfly_p", "openfly_c", "gx_bps", "gx_bcs"]
    g = t[t["strategy_id"].isin(names) & t["exit_dt"].notna()].copy()
    g["date"] = g["entry_dt"].astype(str).str[:10]
    rows = []
    for _, r in g.iterrows():
        legs = r["legs"] if isinstance(r["legs"], list) else json.loads(r["legs"])
        sh = next((l for l in legs if l.get("side") == "sell"), None)
        sc = close.get(r["date"])
        if not sh or sc is None or pd.isna(r.get("credit")):
            continue
        K, right = float(sh["strike"]), (sh.get("right") or "").upper()
        liab = min(W.WING, max(0.0, (K - sc) if right == "P" else (sc - K)))
        rows.append({"structure": r["strategy_id"], "realized": float(r["pnl"]),
                     "settle_gross": (float(r["credit"]) - liab) * 100.0,
                     "stopped": "ACCEPT" in str(r.get("close_reason", "")).upper()})
    d = pd.DataFrame(rows)
    held = d[~d["stopped"]]
    off = (held["realized"] - held["settle_gross"]).mean() if len(held) else 0.0
    ok = bool(len(held) and (held["realized"] - held["settle_gross"]).std() < 30)
    d["settle_net"] = d["settle_gross"] + off
    d["stop_effect"] = d["realized"] - d["settle_net"]
    return d, ok, off


def main() -> int:
    dates = sorted(r["date"] for r in csv_rows(WALL3))
    sc_map = {r["date"]: fnum(r.get("spx_close")) for r in csv_rows(WALL3)}
    print(f"days={len(dates)}  (Theta Terminal @ {W.BASE})\n")

    jobs = []
    for date in dates:
        b = brief(date)
        sc = sc_map.get(date)
        if not b or sc is None:
            continue
        op = open_spot(date, b["pc"]) if b["pc"] else None
        for name, k, right in structures(date, b, op):
            if k is not None:
                jobs.append((date, sc, name, k, right))

    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(run_leg, jobs):
            if res:
                out.append(res)
    m = pd.DataFrame(out)
    m.to_csv(OUT, index=False)

    order = ["eodic_p", "eodic_c", "openic_p", "openic_c", "eodfly_p", "eodfly_c",
             "openfly_p", "openfly_c", "gx_bps", "gx_bcs"]
    print("=== 77-DAY MODEL: stop-effect (stopped - hold) per structure ===")
    print(f"{'structure':12}{'n':>4}{'hold $':>10}{'stopped $':>11}{'stop-effect':>13}{'acc%':>7}")
    tot_h = tot_s = 0.0
    for name in order:
        s = m[m["structure"] == name]
        if not len(s):
            continue
        h, st = s["settle_pnl"].sum(), s["stopped_pnl"].sum()
        acc = 100 * (s["reason"] == "acceptance").mean()
        tot_h += h; tot_s += st
        print(f"{name:12}{len(s):>4}{h:>10,.0f}{st:>11,.0f}{st-h:>13,.0f}{acc:>7.0f}")
    print(f"{'BOOK TOTAL':12}{len(m):>4}{tot_h:>10,.0f}{tot_s:>11,.0f}{tot_s-tot_h:>13,.0f}")

    # ---- August validation vs anchored actual ----
    av, ok, off = anchored_august()
    print(f"\n=== AUGUST VALIDATION (model vs anchored-actual stop-effect) ===")
    print(f"self-check (non-stopped realized == held): {'PASS' if ok else 'FAIL — actual VOID'}  (fee offset {off:+.1f})")
    maug = m[m["date"] >= "2026-08-01"]
    print(f"{'structure':12}{'model Aug':>11}{'actual Aug':>12}")
    ma_tot = aa_tot = 0.0
    for name in order:
        ms = maug[maug["structure"] == name]
        mod = ms["stopped_pnl"].sum() - ms["settle_pnl"].sum() if len(ms) else 0.0
        act = av[av["structure"] == name]["stop_effect"].sum()
        ma_tot += mod; aa_tot += act
        if len(ms) or abs(act) > 0:
            print(f"{name:12}{mod:>11,.0f}{act:>12,.0f}")
    print(f"{'TOTAL':12}{ma_tot:>11,.0f}{aa_tot:>12,.0f}")
    print(f"\nsaved -> {OUT.relative_to(ROOT)}")
    return 0


def csv_rows(fp):
    import csv
    return list(csv.DictReader(open(fp, encoding="utf-8")))


if __name__ == "__main__":
    raise SystemExit(main())
