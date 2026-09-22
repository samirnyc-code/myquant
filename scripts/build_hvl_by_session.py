"""build_hvl_by_session.py — THE single source of truth for MQ levels per session (HVL/CR/PS).
One row per trading session: the levels to use for that ENTIRE session = computed from the
PRIOR session's EOD chain (causal). Prefers MQ's ACTUAL PUBLISHED ES levels; falls back to the
SPX-derived approximation only where ES history doesn't exist.

Levels are ES-native STRIKES (5-pt), NOT SPX+basis (that was wrong — validated 34-111pt off MQ).

Sources:
  * ES1! (data/menthorq/ES1!_mq_levels_history.csv): MQ's real published ES cr/ps/hvl,
    2024-07-01 -> present. AUTHORITATIVE for that span.
  * SPX backfill (data/regime/mq_regime_daily_2007_2026_v2.csv): SPX cr/ps/hvl 2007-2026.
    Used ONLY pre-2024-07 as an approximation (flagged source='spx_approx'); ES conversion is
    an estimate and off by tens of pts vs true ES levels — treat as regime-context, not exact.

Rule: level for session D = the value from D-1's EOD chain (fixed all session, causal).

  python scripts/build_hvl_by_session.py
Output: data/regime/hvl_by_session.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def prior_eod(df, cols):
    """df indexed by eod_date (sorted); return rows keyed by NEXT session_date."""
    df = df.sort_values("eod_date").reset_index(drop=True)
    out = pd.DataFrame({"session_date": df["eod_date"].shift(-1), "eod_date": df["eod_date"]})
    for c in cols:
        out[c] = df[c]
    return out.dropna(subset=["session_date"]).reset_index(drop=True)


def main():
    # 1) MQ real ES levels (authoritative, 2024-07+)
    es = pd.read_csv(DATA / "menthorq" / "ES1!_mq_levels_history.csv")
    es["eod_date"] = es["eod_date"].astype(str)
    es = prior_eod(es[["eod_date", "hvl", "cr", "ps"]].rename(columns={"hvl": "hvl", "cr": "cr", "ps": "ps"}),
                   ["hvl", "cr", "ps"])
    es["source"] = "mq_es"

    # 2) SPX-derived approximation (pre-2024-07 fallback only)
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv")
    mq["eod_date"] = mq["date"].astype(str)
    spx = prior_eod(mq[["eod_date", "hvl", "cr", "ps", "spot"]], ["hvl", "cr", "ps", "spot"])
    # crude ES estimate for the fallback period: SPX strike + rough basis from unadj ES
    up = DATA / "bars" / "_continuous_1m_unadj.parquet"
    if up.exists():
        u = pd.read_parquet(up); u["Date"] = pd.to_datetime(u["DateTime"]).dt.date.astype(str)
        esc = u.groupby("Date")["Close"].last()
        spx["basis"] = spx["eod_date"].map(esc) - spx["spot"]
    else:
        spx["basis"] = np.nan
    for c in ("hvl", "cr", "ps"):
        spx[c] = spx[c] + spx["basis"].fillna(0)     # approx ES; flagged below
    spx = spx[["session_date", "eod_date", "hvl", "cr", "ps"]]
    spx["source"] = "spx_approx"

    # 3) combine: MQ-ES wins wherever available; SPX-approx only for earlier sessions
    es_sessions = set(es["session_date"])
    spx_only = spx[~spx["session_date"].isin(es_sessions)]
    out = pd.concat([spx_only, es]).sort_values("session_date").reset_index(drop=True)
    out = out[["session_date", "eod_date", "source", "hvl", "cr", "ps"]]
    out.to_csv(DATA / "regime" / "hvl_by_session.csv", index=False)

    n_mq = (out.source == "mq_es").sum(); n_spx = (out.source == "spx_approx").sum()
    print(f"wrote {len(out)} sessions -> data/regime/hvl_by_session.csv")
    print(f"  mq_es (real ES levels): {n_mq}  | spx_approx (pre-2024 estimate): {n_spx}")
    print(f"  span: {out.session_date.min()} -> {out.session_date.max()}\n")
    print("last 10 sessions (MQ real ES levels, prior EOD applied all day):")
    print(out.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
