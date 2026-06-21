"""regime_overlay_phaseB.py — does level-state beat the CC baseline (real sim)?

Phase A showed: balance edges get touched (magnets real, ~84%), but ACCEPTANCE at
the edge is a coin-flip (~50-54%) and regime-stable across years. So the level alone
carries no edge. This asks the only question that matters: conditioned on a CC signal,
does the level-STATE at signal time shift expectancy vs the unconditioned baseline?

Population: ba_signals_mc.parquet, ER_intra_6 >= 0.30 (the deployed chop filter),
pinned 1.0R single-leg (BASE) — i.e. we test whether level-state ADDS to the current
best config, in real engine dollars.

State at signal time (look-ahead-safe — uses only bars BEFORE the signal timestamp):
  • disc   — prior-day extreme already broken in the signal's direction (discovery),
             against it (counter), or neither (rotation, still inside prior range).
  • eth    — signal price beyond the overnight edge in its direction (eth_break),
             beyond the opposite edge (counter), or inside the ETH range.
  • adr    — developing range / ADR at signal time (how much of the day is spent).
  • room   — distance from entry to the next balance edge in the trade's direction
             (ETH edge / prior extreme), in ADR units — the "room to run".
  • open_loc — day opened inside / above / below prior range (day-level).

Each bucket: n, net$, exp$, win%, PF — plus a 2022-vs-rest split (the chop holdout).
Baseline row (ALL) on top of every table for comparison.

Run: .venv/Scripts/python.exe scripts/regime_overlay_phaseB.py
Out: docs/living/regime_overlay_phaseB_<date>.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
import regime_filter as rf                                          # noqa: E402
from simulation_engine import simulate_trades                       # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_SESS    = _ROOT / "data" / "regime_ladder_sessions.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)
CHOP_MIN = 0.30


def log(m: str) -> None:
    print(f"[overlayB] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── per-signal level state (look-ahead-safe) ──────────────────────────────────

def tag_states(sig: pd.DataFrame, bars: pd.DataFrame, sess: pd.DataFrame) -> pd.DataFrame:
    """Attach disc / eth / adr / room / open_loc state to each signal row."""
    bars = bars.copy()
    bars["Date"] = bars["DateTime"].dt.date
    by_date = {d: g.sort_values("DateTime") for d, g in bars.groupby("Date")}
    lv = sess.set_index("Date")

    out = []
    for r in sig.itertuples():
        d = r.Date if not isinstance(r.Date, pd.Timestamp) else r.Date.date()
        rec = dict(disc="na", eth="na", adr_bkt="na", room_bkt="na", open_loc="na")
        if d in lv.index and d in by_date:
            row = lv.loc[d]
            g = by_date[d]
            pre = g[g["DateTime"] < r.DateTime]            # bars strictly before signal
            if len(pre):
                dev_hi, dev_lo = float(pre["High"].max()), float(pre["Low"].min())
            else:
                dev_hi = dev_lo = float(g["Open"].iloc[0])
            px = float(r.SignalPrice)
            is_long = (r.Direction == "Long")
            hoy, loy = row["HOY"], row["LOY"]
            ethH, ethL, adr = row["ETH_High"], row["ETH_Low"], row["ADR"]

            # discovery state vs signal direction
            broke_up, broke_dn = (dev_hi > hoy), (dev_lo < loy)
            aligned = broke_up if is_long else broke_dn
            counter = broke_dn if is_long else broke_up
            rec["disc"] = "disc_aligned" if aligned else ("disc_counter" if counter else "rotation")

            # eth state vs signal direction
            if is_long:
                rec["eth"] = "eth_break" if px > ethH else ("eth_counter" if px < ethL else "eth_inside")
            else:
                rec["eth"] = "eth_break" if px < ethL else ("eth_counter" if px > ethH else "eth_inside")

            # adr consumed at signal time
            if pd.notna(adr) and adr > 0:
                cons = (dev_hi - dev_lo) / adr
                rec["adr_bkt"] = pd.cut([cons], [0, 0.5, 1.0, 1.5, np.inf],
                                        labels=["<0.5", "0.5-1.0", "1.0-1.5", ">1.5"])[0]
                # room to run: nearest edge above (long) / below (short), in ADR units
                if is_long:
                    edges = [e for e in (ethH, hoy) if pd.notna(e) and e > px]
                    room = (min(edges) - px) / adr if edges else np.nan
                else:
                    edges = [e for e in (ethL, loy) if pd.notna(e) and e < px]
                    room = (px - max(edges)) / adr if edges else np.nan
                if pd.notna(room):
                    rec["room_bkt"] = pd.cut([room], [-np.inf, 0, 0.25, 0.5, np.inf],
                                             labels=["beyond", "<0.25", "0.25-0.5", ">0.5"])[0]
                else:
                    rec["room_bkt"] = "open_air"      # no edge ahead = clear runway
            rec["open_loc"] = row["open_loc"]
        out.append(rec)
    return pd.DataFrame(out, index=sig.index)


# ── bucket stats ──────────────────────────────────────────────────────────────

def stats(pnl: np.ndarray) -> dict:
    if len(pnl) == 0:
        return dict(n=0, net=0, exp=float("nan"), win=float("nan"), pf=float("nan"))
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    return dict(n=len(pnl), net=float(pnl.sum()), exp=float(pnl.mean()),
                win=float((pnl > 0).mean() * 100), pf=(gw / gl if gl > 0 else float("inf")))


def fmt(s: dict) -> str:
    if s["n"] == 0:
        return "0 | — | — | — | —"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return f"{s['n']} | ${s['net']:,.0f} | ${s['exp']:.0f} | {s['win']:.0f}% | {pf}"


def table(title: str, filled: pd.DataFrame, col: str, base: dict) -> list[str]:
    L = [f"### {title}\n",
         "| bucket | n | net | exp | win% | PF | exp 2022 | exp ex-2022 |",
         "|---|---|---|---|---|---|---|---|",
         f"| **ALL (baseline)** | {fmt(base)} | — | — |"]
    order = filled[col].value_counts().index.tolist()
    for b in order:
        m = filled[col] == b
        s = stats(filled.loc[m, "NetPnL"].to_numpy())
        y = filled.loc[m, "_year"]
        e22 = filled.loc[m & (filled["_year"] == 2022), "NetPnL"]
        erest = filled.loc[m & (filled["_year"] != 2022), "NetPnL"]
        e22s = f"${e22.mean():.0f}" if len(e22) else "—"
        ers = f"${erest.mean():.0f}" if len(erest) else "—"
        L.append(f"| {b} | {fmt(s)} | {e22s} ({len(e22)}) | {ers} |")
    return L + [""]


def main() -> int:
    log("loading signals + bars + session levels...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    sess = pd.read_parquet(_SESS)
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    log("ER>=0.30 filter...")
    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float).fillna(0)
    sigf = sig[er >= CHOP_MIN].reset_index(drop=True).copy()   # align to engine's 0..N result index
    log(f"signals after ER>=0.30: {len(sigf)}")

    log("tagging level-state...")
    states = tag_states(sigf, bars, sess)
    sigf = pd.concat([sigf, states], axis=1)

    log("loading ticks...")
    ticks_by_date = {}
    for d in sorted(sigf["Date"].unique()):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t

    log("simulating (pinned 1.0R single-leg)...")
    res = simulate_trades(signals=sigf, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE)
    filled = res[res["Filled"] == True].copy()
    # attach state + year (results keep the signal index)
    for c in ["disc", "eth", "adr_bkt", "room_bkt", "open_loc"]:
        filled[c] = sigf.loc[filled.index, c].values
    filled["_year"] = pd.to_datetime(sigf.loc[filled.index, "DateTime"]).dt.year.values
    log(f"filled trades: {len(filled)}")

    base = stats(filled["NetPnL"].to_numpy())
    head = [f"# Regime Overlay — Phase B (CC × level-state, pinned 1.0R) ({datetime.now():%Y-%m-%d})\n",
            f"Population: ER>=0.30 single-leg, {len(filled)} filled of {len(sigf)} signals. "
            f"Baseline exp **${base['exp']:.0f}**, PF {base['pf']:.2f}, win {base['win']:.0f}%.\n",
            "Columns: 2022 = chop/bear holdout (n in parens). A bucket is real only if it "
            "beats baseline AND survives 2022.\n"]
    md = head
    md += table("Discovery state (prior extreme broken in signal dir?)", filled, "disc", base)
    md += table("ETH edge state (signal price vs overnight range)", filled, "eth", base)
    md += table("ADR consumed at signal time", filled, "adr_bkt", base)
    md += table("Room to run (distance to next edge ahead, ADR units)", filled, "room_bkt", base)
    md += table("Open location (day vs prior range)", filled, "open_loc", base)

    out = _OUT / f"regime_overlay_phaseB_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote -> {out}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
