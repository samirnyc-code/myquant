"""build_hvl_by_session.py — THE single source of truth for HVL. One row per trading session:
the HVL to use for that ENTIRE session = the level computed from the PRIOR session's EOD ORATS
chain (our validated MQ HVL formula). No inline recompute, no inherited tags — everything reads
this file.

Rule (exactly as stated): take the EOD-computed HVL from session D-1, use it as session D's HVL
for the whole session. Causal by construction (D-1 close is known before D opens).

Columns:
  session_date  — the trading session the HVL applies to
  eod_date      — the prior session whose EOD chain produced it
  hvl_spx       — HVL in SPX points (MQ-native, the authoritative value)
  spx_eod       — SPX close on eod_date (for reference)
  basis         — ES - SPX on eod_date (ES premium/discount)
  hvl_es        — hvl_spx + basis = HVL in real-ES price terms (compare your ES price to this)

Regime for session D: price > hvl_es -> positive_gamma ; price < hvl_es -> negative_gamma.

  python scripts/build_hvl_by_session.py
Output: data/regime/hvl_by_session.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv")
    mq["date"] = mq["date"].astype(str)
    mq = mq.sort_values("date").reset_index(drop=True)
    # HVL is computed from that row's OWN EOD chain (same-day tradeDate). To USE it live, it
    # becomes the NEXT session's level. So session_date = the row AFTER; eod_date = this row.
    out = pd.DataFrame({
        "session_date": mq["date"].shift(-1),      # this EOD level applies to the next session
        "eod_date": mq["date"],
        "hvl_spx": mq["hvl"],                       # HVL — gamma flip / regime line
        "cr_spx": mq["cr"],                         # Call Resistance = argmax net(K)
        "ps_spx": mq["ps"],                         # Put Support = argmin net(K), |K/spot-1|<=20%
        "spx_eod": mq["spot"],
    }).dropna(subset=["session_date"]).reset_index(drop=True)

    # real-ES basis on eod_date (unadjusted ES), so hvl_es is in the ES prices you actually see
    up = DATA / "bars" / "_continuous_1m_unadj.parquet"
    if up.exists():
        es = pd.read_parquet(up); es["Date"] = pd.to_datetime(es["DateTime"]).dt.date.astype(str)
        esc = es.groupby("Date")["Close"].last()
        out["es_eod"] = out["eod_date"].map(esc)
        out["basis"] = out["es_eod"] - out["spx_eod"]
        for lv in ("hvl", "cr", "ps"):
            out[f"{lv}_es"] = out[f"{lv}_spx"] + out["basis"]
    else:
        out["basis"] = np.nan
        for lv in ("hvl", "cr", "ps"):
            out[f"{lv}_es"] = np.nan

    out.to_csv(DATA / "regime" / "hvl_by_session.csv", index=False)
    print(f"wrote {len(out)} sessions -> data/regime/hvl_by_session.csv")
    print(f"  span: {out.session_date.min()} -> {out.session_date.max()}")
    print(f"  ES-basis coverage (2021+): {out.hvl_es.notna().sum()} sessions\n")
    print("last 12 sessions (each session uses the PRIOR EOD's levels all day):")
    cols = ["session_date", "eod_date", "hvl_spx", "cr_spx", "ps_spx", "basis", "hvl_es", "cr_es", "ps_es"]
    print(out[cols].tail(12).to_string(index=False))


if __name__ == "__main__":
    main()
