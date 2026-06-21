"""fade_by_state.py — fade analysis bucketed by the level-states.

Two questions, both in real engine dollars (ER>=0.30, pinned 1.0R single-leg):

  Q1 (ex-ante, tradeable): is any STATE bucket negative enough on its own that
     fading every signal in it (flip direction, pay costs twice) is net positive?
  Q2 (diagnostic): of the trades that LOSE, which states reverse best when faded?
     This points the Phase-3 RevFT / fade setup at the richest regime.

Fade = same entry price, opposite direction, symmetric R (engine derives stop/target
from Direction + stop_offset, so flipping Direction gives the mirror trade).

Run: .venv/Scripts/python.exe scripts/fade_by_state.py
Out: docs/living/fade_by_state_<date>.md
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
from scripts.regime_overlay_phaseB import (BASE, CHOP_MIN, tag_states,  # noqa: E402
                                           stats, _SIGNALS, _BARS, _SESS)

_OUT = _ROOT / "docs" / "living"
STATE_COLS = ["disc", "eth", "adr_bkt", "open_loc", "balance_lbl"]


def log(m): print(f"[fade] {datetime.now():%H:%M:%S} {m}", flush=True)


def row(label: str, orig: np.ndarray, fade: np.ndarray) -> str:
    fade = fade[~np.isnan(fade)]                    # keep only filled fades
    o, f = stats(orig), stats(fade)
    if o["n"] == 0:
        return f"| {label} | 0 | — | — | — | — |"
    opf = "∞" if o["pf"] == float("inf") else f"{o['pf']:.2f}"
    fexp = f"${f['exp']:.0f}" if f["n"] else "—"
    fwin = f"{f['win']:.0f}%" if f["n"] else "—"
    return f"| {label} | {o['n']} | ${o['exp']:.0f} | {opf} | {f['n']} | {fexp} | {fwin} |"


def main() -> int:
    log("load + ER>=0.30 + tag states...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    sess = pd.read_parquet(_SESS)
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float).fillna(0)
    sigf = sig[er >= CHOP_MIN].reset_index(drop=True).copy()
    st = tag_states(sigf, bars, sess)
    sigf = pd.concat([sigf, st], axis=1)
    sigf["balance_lbl"] = np.where((sigf["open_loc"] == "inside") & (sigf["disc"] == "rotation"),
                                   "balance", "non-balance")

    log("ticks + simulate original...")
    tk = {d: massive.load_continuous_ticks(d) for d in sorted(sigf["Date"].unique())}
    tk = {d: t for d, t in tk.items() if not t.empty}
    orig = simulate_trades(signals=sigf, ticks_by_date=tk, bars_by_date=bars_by_date, **BASE)
    of = orig[orig["Filled"] == True].copy()
    for c in STATE_COLS:
        of[c] = sigf.loc[of.index, c].values

    # fade every filled signal (flip direction) — gives the mirror trade for ALL,
    # so we can read both "fade the whole bucket" and "fade only the losers".
    sig_flip = sigf.loc[of.index].copy()
    sig_flip["Direction"] = sig_flip["Direction"].map({"Long": "Short", "Short": "Long"})
    # MIRROR the stop across the entry — flipping Direction alone leaves the stop on
    # the wrong side (in profit), so faded trades never stop out (rode to EOD → fake
    # 100% win). new_stop = 2*entry - orig_stop keeps risk symmetric on the right side.
    sig_flip["StopPrice"] = 2.0 * sig_flip["SignalPrice"] - sig_flip["StopPrice"]
    log("simulate faded (all, flipped + mirrored stop)...")
    # engine returns rows in input order with a reset 0..N index, so align POSITIONALLY
    # to `of` (same row order) — reindex on of.index would misalign (was giving NaN).
    fad = simulate_trades(signals=sig_flip, ticks_by_date=tk, bars_by_date=bars_by_date, **BASE)
    of["fade_pnl"] = np.where((fad["Filled"] == True).values, fad["NetPnL"].values, np.nan)
    of["fade_filled"] = (fad["Filled"] == True).values
    of["is_loser"] = of["NetPnL"] < 0

    md = [f"# Fade by state ({datetime.now():%Y-%m-%d})\n",
          f"ER>=0.30 pinned 1.0R. {len(of)} filled. 'orig' = as-traded; 'fade' = mirror trade.\n"]

    # ── Q1 — fade the WHOLE bucket (ex-ante) ─────────────────────────────────
    md += ["## Q1 — fade the whole bucket? (orig exp vs fading every signal in it)\n",
           "Only worth fading if orig exp is clearly negative AND fade exp clearly positive.\n",
           "| bucket | orig n | orig exp | orig PF | fade n | fade exp | fade win% |",
           "|---|---|---|---|---|---|---|",
           row("ALL", of["NetPnL"].to_numpy(), of["fade_pnl"].to_numpy())]
    for col in STATE_COLS:
        for b in of[col].value_counts().index:
            m = of[col] == b
            md.append(row(f"{col}={b}", of.loc[m, "NetPnL"].to_numpy(), of.loc[m, "fade_pnl"].to_numpy()))
    md += [""]

    # ── Q2 — fade only the LOSERS, by bucket (diagnostic / RevFT seed) ────────
    losers = of[of["is_loser"]]
    lf = losers["fade_pnl"].dropna()
    md += ["## Q2 — of the LOSING trades, do they reverse? (faded losers by state)\n",
           f"All losers: {len(losers)} trades, orig ${losers['NetPnL'].sum():,.0f}; "
           f"faded fills {len(lf)}, net ${lf.sum():,.0f} (exp ${lf.mean():.0f}, "
           f"win {(lf>0).mean()*100:.0f}%).\n",
           "| bucket | n losers | orig loss | faded net | fade exp | fade win% |",
           "|---|---|---|---|---|---|"]
    for col in STATE_COLS:
        for b in losers[col].value_counts().index:
            m = losers[col] == b
            sub = losers[m]
            fp = sub["fade_pnl"].dropna().to_numpy()
            fe = f"${fp.mean():.0f}" if len(fp) else "—"
            fw = f"{(fp>0).mean()*100:.0f}%" if len(fp) else "—"
            md.append(f"| {col}={b} | {len(sub)} | ${sub['NetPnL'].sum():,.0f} | ${fp.sum():,.0f} "
                      f"| {fe} | {fw} |")
    md += [""]

    out = _OUT / f"fade_by_state_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote -> {out}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
