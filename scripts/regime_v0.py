"""regime_v0.py — Grimes v0 regime state machine for ES.

Consumes the feature frame from regime_features.py and emits a per-bar regime label:
  no_trade (default) | bull | bear | transition

Faithful to docs/research_notes/grimes_regime/SYNTHESIS_regime_engine_design.md sec.5.
STRICTLY CAUSAL: state at bar t is decided from features known at the close of bar t.
No feature here peeks ahead; the ATR-zigzag inside regime_features already lags by design.

Logic (v0):
  NO_TRADE (default):
    -> BULL  if close beyond UPPER Keltner (kelt_pos==+1) AND MACD new momentum high.
    -> BEAR  if close beyond LOWER Keltner (kelt_pos==-1) AND MACD new momentum low.
    (impulse-out-of-compression is captured because compressed bars precede the impulse.)
  BULL (trend up), kept alive by the health checklist; leaves only on:
    -> TRANSITION  2-STEP RULE: a BREAK EVENT occurred within the last BREAK_WINDOW bars
       AND now a MACD new momentum LOW prints (opposite momentum extreme).
       Break events (bull): buying climax; bearish divergence (new price high, no new MACD
       high); Dow state falling out of +1. Divergence alone never flips (needs step 2).
    -> NO_TRADE  quiet death: dow_state==0 and close back inside bands and no new MACD high
       for FLAT_DEATH bars ("goes flat and dull" pullback failure).
  BEAR: mirror of BULL.
  TRANSITION (remembers prior trend dir):
    -> opposite trend  when the opposite Dow structure completes (dow_state == -prior_dir).
    -> prior trend     if the old trend reasserts (dow_state == prior_dir) — MMO holds /
       complex pullback resolves.
    -> NO_TRADE        default resolution if neither confirms within TRANS_TIMEOUT bars.

Run:
  .venv/Scripts/python.exe scripts/regime_v0.py            # all timeframes (latest features)
Outputs (dated): data/regime/state_<tf>_<YYYYMMDD>.parquet + state_summary_<YYYYMMDD>.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "regime"

# ---- state-machine parameters ---------------------------------------------
BREAK_WINDOW = 5     # bars: the 2-step reversal must complete within this window
FLAT_DEATH = 6       # bars of flat/inside action that quietly ends a trend
TRANS_TIMEOUT = 10   # bars: transition resolves to no_trade if unconfirmed
DIV_LOOKBACK = 20    # price-new-high window for the divergence proxy


def _latest(tf: str, tag: str | None) -> Path:
    if tag:
        return OUT / f"features_{tf}_{tag}.parquet"
    cands = sorted(OUT.glob(f"features_{tf}_*.parquet"))
    if not cands:
        raise FileNotFoundError(f"no features_{tf}_*.parquet in {OUT} — run regime_features.py")
    return cands[-1]


def run_state_machine(f: pd.DataFrame) -> pd.DataFrame:
    n = len(f)
    close = f["Close"].to_numpy()
    kelt_pos = f["kelt_pos"].to_numpy()
    macd_hi = f["macd_new_hi"].to_numpy()
    macd_lo = f["macd_new_lo"].to_numpy()
    dow = f["dow_state"].to_numpy()
    climax = f["climax"].to_numpy()

    # divergence proxies (causal): price new DIV_LOOKBACK-bar high but no new MACD high
    price_hi = (f["Close"] >= f["Close"].rolling(DIV_LOOKBACK, min_periods=5).max()).to_numpy()
    price_lo = (f["Close"] <= f["Close"].rolling(DIV_LOOKBACK, min_periods=5).min()).to_numpy()
    bear_div = price_hi & (macd_hi == 0)
    bull_div = price_lo & (macd_lo == 0)

    state = np.array(["no_trade"] * n, dtype=object)
    prior_dir = np.zeros(n, dtype=np.int8)   # direction transition came from

    cur = "no_trade"
    pdir = 0
    last_break = -10**9      # bar index of most recent break event (sign = bull/bear break)
    last_break_dir = 0
    flat_run = 0
    trans_age = 0

    for i in range(n):
        if cur == "no_trade":
            if kelt_pos[i] == 1 and macd_hi[i] == 1:
                cur = "bull"
            elif kelt_pos[i] == -1 and macd_lo[i] == 1:
                cur = "bear"

        elif cur == "bull":
            # register a bull break event (step 1)
            if climax[i] == 1 or bear_div[i] or dow[i] < 1:
                last_break = i; last_break_dir = +1
            # step 2: opposite momentum extreme within window -> TRANSITION
            if (i - last_break) <= BREAK_WINDOW and last_break_dir == +1 and macd_lo[i] == 1:
                cur = "transition"; pdir = +1; trans_age = 0
            else:
                # quiet death
                inside = kelt_pos[i] == 0
                flat_run = flat_run + 1 if (dow[i] == 0 and inside and macd_hi[i] == 0) else 0
                if flat_run >= FLAT_DEATH:
                    cur = "no_trade"; flat_run = 0

        elif cur == "bear":
            if climax[i] == -1 or bull_div[i] or dow[i] > -1:
                last_break = i; last_break_dir = -1
            if (i - last_break) <= BREAK_WINDOW and last_break_dir == -1 and macd_hi[i] == 1:
                cur = "transition"; pdir = -1; trans_age = 0
            else:
                inside = kelt_pos[i] == 0
                flat_run = flat_run + 1 if (dow[i] == 0 and inside and macd_lo[i] == 0) else 0
                if flat_run >= FLAT_DEATH:
                    cur = "no_trade"; flat_run = 0

        elif cur == "transition":
            trans_age += 1
            if dow[i] == -pdir:              # opposite structure completes
                cur = "bull" if -pdir == 1 else "bear"; flat_run = 0
            elif dow[i] == pdir:             # old trend reasserts
                cur = "bull" if pdir == 1 else "bear"; flat_run = 0
            elif trans_age >= TRANS_TIMEOUT:
                cur = "no_trade"

        state[i] = cur
        prior_dir[i] = pdir if cur == "transition" else 0

    out = f[["DateTime", "Close"]].copy()
    out["state"] = state
    out["trans_from"] = prior_dir
    return out


def summarize(states: pd.DataFrame, tf: str) -> dict:
    s = states["state"]
    # dwell: run lengths per state
    grp = (s != s.shift()).cumsum()
    runs = states.groupby(grp)["state"].agg(["first", "size"])
    dwell = runs.groupby("first")["size"].mean()
    # count entries INTO each state
    entries = runs["first"].value_counts().to_dict()
    d = {"tf": tf, "bars": len(s)}
    for st in ("no_trade", "bull", "bear", "transition"):
        d[f"{st}%"] = round(100 * (s == st).mean(), 1)
        d[f"{st}_dwell"] = round(float(dwell.get(st, 0)), 1)
        d[f"{st}_entries"] = int(entries.get(st, 0))
    return d


def main(tag: str | None = None):
    wtag = pd.Timestamp.now().strftime("%Y%m%d")
    rows = []
    for tf in ("daily", "60m", "30m"):
        fp = _latest(tf, tag)
        f = pd.read_parquet(fp)
        states = run_state_machine(f)
        states.to_parquet(OUT / f"state_{tf}_{wtag}.parquet", index=False)
        rows.append(summarize(states, tf))
    sm = pd.DataFrame(rows)
    sm.to_csv(OUT / f"state_summary_{wtag}.csv", index=False)
    pd.set_option("display.width", 200)
    print(sm.to_string(index=False))
    return sm


if __name__ == "__main__":
    main()
