"""er10_tp_control.py — is the +4pt take-profit ER10-SPECIFIC, or just generically good?

The phantom-block sweep found a tight +4pt take-profit (applied at EB close to the
ER10-decayed "flagged" trades) clawed back ~$30k. Before believing the ER10 flag
adds anything, control for the obvious confound: maybe a +4pt scalp helps EVERY
trade on this set (it would just be a better exit, nothing to do with ER10).

Test: apply the SAME EB-close +4pt take-profit overlay to the ENTIRE causal book,
compute each trade's delta (overlay_net − baseline_net), and split by group:
  • flagged   (ER10 decayed < gate by EB close)  — the "bad" trades
  • unflagged (ER10 still >= gate at EB close)    — the "good" trades
  • random    (a size-matched random subset of the whole book)
If flagged trades benefit MUCH more than unflagged/random → the flag selects trades
the TP helps (real). If deltas are similar → it's a generic exit tweak (not ER10).

Reuses the overlay engine from er10_block_exit_sweep (no divergence). k = +2/+4/+6.
Out: docs/living/er10_tp_control_<date>.md
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # for sibling import

import massive                                                        # noqa: E402
from simulation_engine import simulate_trades                         # noqa: E402
from data_loader import bar_num_from_dt                               # noqa: E402
from er_lookahead_tab import _er10_both_modes                         # noqa: E402
from er10_block_exit_sweep import (_overlay_gross_pts, _net,          # noqa: E402
                                   GATE, SIM_KW, N_CHUNKS)

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"
K_TEST   = [2, 4, 6]
SEED     = 42


def log(m): print(f"[ctl] {datetime.now():%H:%M:%S} {m}", flush=True)


def main() -> int:
    log("load + tag ...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    tagged = _er10_both_modes(sig, bars)
    causal_pass = tagged["ER10_causal"] >= GATE
    cur_pass    = tagged["ER10_current"] >= GATE
    flag = causal_pass & ~cur_pass
    g = tagged.loc[causal_pass].copy()
    g["FilterStatus"] = "ok"
    g["flagged"] = flag.loc[g.index].to_numpy()
    g["_date"] = pd.to_datetime(g["DateTime"]).dt.date

    rows = []
    dates = sorted(g["_date"].unique())
    for ci, chunk in enumerate(np.array_split(np.array(dates, object), N_CHUNKS)):
        cset = set(chunk.tolist())
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        sub = g[g["_date"].isin(cset)].drop(columns="_date").reset_index(drop=True)
        res = simulate_trades(sub, ticks_by_date=tbd, bars_by_date=bbd, **SIM_KW)
        filled = res[res["Filled"] == True].copy()
        for r in filled.itertuples(index=False):
            t = tbd.get(r.Date)
            rec = {"flag": bool(r.flagged), "net_base": _net(r.GrossPnLPts)}
            for k in K_TEST:
                gp = r.GrossPnLPts if (t is None or t.empty) else _overlay_gross_pts(r, t, k)
                rec[f"net_k{k}"] = _net(gp)
            rows.append(rec)
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/{N_CHUNKS} done")

    df = pd.DataFrame(rows)
    rng = np.random.default_rng(SEED)
    n_flag = int(df["flag"].sum())
    rand_idx = rng.choice(len(df), size=n_flag, replace=False)
    df["rand"] = False
    df.iloc[rand_idx, df.columns.get_loc("rand")] = True
    df.to_parquet(_OUT / "er10_tp_control_pertrade.parquet")   # per-trade net by k + groups

    groups = {"FLAGGED (ER10 decayed)": df["flag"],
              "UNFLAGGED (ER10 held)":  ~df["flag"],
              "RANDOM (size-matched)":  df["rand"],
              "ALL causal trades":      pd.Series(True, index=df.index)}

    md = [f"# ER10 +Npt take-profit — control test ({datetime.now():%Y-%m-%d})\n",
          "Applies the EB-close take-profit overlay to the WHOLE causal book and splits "
          "the per-trade delta (overlay − baseline) by group. If FLAGGED ≈ UNFLAGGED ≈ "
          "RANDOM, the TP is a generic exit tweak, not an ER10 effect.\n",
          f"**Set:** `ba_signals_mc.parquet`  **Gate:** {GATE:.2f}  "
          f"**n:** flagged {n_flag:,}, unflagged {int((~df['flag']).sum()):,}, "
          f"all {len(df):,}.\n"]
    for k in K_TEST:
        md += [f"## Take-profit @ entry+{k}pt — per-trade delta by group\n",
               "| group | n | baseline net $ | baseline exp $ | overlay net $ | overlay exp $ "
               "| mean Δ $/trade | total Δ $ |",
               "|---|---|---|---|---|---|---|---|"]
        for name, mask in groups.items():
            d = df[mask]
            bn, on = d["net_base"].sum(), d[f"net_k{k}"].sum()
            be, oe = d["net_base"].mean(), d[f"net_k{k}"].mean()
            md.append(f"| {name} | {len(d):,} | ${bn:,.0f} | ${be:,.2f} | ${on:,.0f} | "
                      f"${oe:,.2f} | ${oe-be:,.2f} | ${on-bn:,.0f} |")
        md.append("")

    # headline: +4 flagged vs unflagged vs random mean delta
    k = 4
    fd = (df.loc[df["flag"], f"net_k{k}"].mean() - df.loc[df["flag"], "net_base"].mean())
    ud = (df.loc[~df["flag"], f"net_k{k}"].mean() - df.loc[~df["flag"], "net_base"].mean())
    rd = (df.loc[df["rand"], f"net_k{k}"].mean() - df.loc[df["rand"], "net_base"].mean())
    md += [f"## Verdict (+{k}pt)\n",
           f"- mean Δ/trade: FLAGGED **${fd:,.2f}**, UNFLAGGED **${ud:,.2f}**, RANDOM **${rd:,.2f}**.",
           f"- If FLAGGED Δ ≫ UNFLAGGED/RANDOM Δ → the ER10 decay flag genuinely selects trades "
           "the take-profit rescues. If they're comparable → the +4pt TP is generic (helps any "
           "trade), and ER10 adds nothing.\n"]
    out = _OUT / f"er10_tp_control_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    log(f"+{k}pt mean Δ/trade — FLAGGED ${fd:.2f} | UNFLAGGED ${ud:.2f} | RANDOM ${rd:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
