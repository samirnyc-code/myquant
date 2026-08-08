"""One row per trading day — THE comparison table for the premium-selling forward test.

Joins the day's gameplan (brief fields), trades (per-stream P&L), and evening
verdict into data/options_sim/daily_summary.csv. Idempotent: rebuilds the whole
table from files each run, so schema fixes back-propagate. Runs nightly from
gexlog_evening.py (and standalone).

  .venv/Scripts/python.exe scripts/daily_summary.py
"""
import glob
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
OUT = SIM / "daily_summary.csv"

STREAM_MAP = {
    "eodic_p": "eod", "eodic_c": "eod", "eodfly_p": "eod", "eodfly_c": "eod",
    "openic_p": "open", "openic_c": "open", "openfly_p": "open", "openfly_c": "open",
    "gx_bps": "gexlog", "gx_bcs": "gexlog", "bps_stmr": "stmr",
}


def _norm_gamma(raw):
    """POSITIVE/NEGATIVE -> POS/NEG/? — backfills gamma_regime for pre-08-08 briefs."""
    s = str(raw or "").strip().upper()
    return "POS" if s.startswith("POS") else ("NEG" if s.startswith("NEG") else "?")


def _flip_in(gx):
    """GEX flip inside [emLower, emUpper]? Use the stored field, else recompute from
    fields older gameplans already carry (emLower/emUpper/gex_flip)."""
    if gx.get("in_range_flip") is not None:
        return gx.get("in_range_flip")
    lo, hi, flip = gx.get("emLower"), gx.get("emUpper"), gx.get("gex_flip")
    if lo is not None and hi is not None and flip is not None:
        return bool(lo <= flip <= hi)
    return None


def day_row(gp_path, trades):
    d = json.loads(Path(gp_path).read_text(encoding="utf-8"))
    date = d.get("date")
    gx = d.get("gexlog", {}) or {}
    ev = d.get("gexlog_evening", {}) or {}
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    t = trades[(trades.entry_dt.astype(str).str[:10] == iso)]
    tc = t[t.exit_dt.notna()].copy()
    tc["pnl"] = pd.to_numeric(tc.pnl, errors="coerce")
    tc["stream"] = tc.strategy_id.map(STREAM_MAP)
    per = tc.groupby("stream").pnl.sum().to_dict()
    trig = d.get("triggers", [])
    row = dict(
        date=iso,
        # forecast side (morning brief)
        signal=gx.get("signal_bucket"), day_type=gx.get("day_type"),
        forecast=gx.get("forecast_type"), confidence=gx.get("confidence"),
        risk=gx.get("risk_level"), gap_note=gx.get("gap_note"),
        calendar=gx.get("calendar_note"), playbook_wait=gx.get("playbook_wait"),
        stale_risk=gx.get("stale_risk"), vix=d.get("vix"),
        eod_spot=gx.get("current"), em=d.get("em_halfwidth"),
        em_low=d.get("em_low"), em_high=d.get("em_high"),
        put_wall=gx.get("putWall"), call_wall=gx.get("callWall"),
        gex_flip=gx.get("gex_flip"), net_gex=gx.get("net_gex"),
        # #27 capture (added 2026-08-08) — the #20 gate axes + rotation/RSI context.
        # gamma_regime/event_day/dispersion are forward-only (older briefs lack them);
        # gamma_regime falls back to the raw `regime` string when the norm is absent.
        gamma_regime=gx.get("gamma_regime") or _norm_gamma(gx.get("regime")),
        event_day=gx.get("event_day"), event_titles="; ".join(gx.get("event_titles") or []),
        event_gate=(d.get("event_gate", {}) or {}).get("verdict"),
        in_range_flip=_flip_in(gx), sector_dispersion=gx.get("sector_dispersion"),
        rsi_14=gx.get("rsi_14"),
        # execution side
        open_spot=d.get("open_spot"), open_at=d.get("open_spot_at"),
        n_armed=len(trig), n_fired=sum(1 for x in trig if x.get("status") == "fired"),
        n_stood_down=sum(1 for x in trig if str(x.get("status", "")).startswith("stood_down")),
        # result side
        pnl_total=round(tc.pnl.sum(), 0) if len(tc) else None,
        pnl_eod=round(per.get("eod", 0), 0), pnl_open=round(per.get("open", 0), 0),
        pnl_gexlog=round(per.get("gexlog", 0), 0), pnl_stmr=round(per.get("stmr", 0), 0),
        n_closed=len(tc), n_wins=int((tc.pnl > 0).sum()) if len(tc) else 0,
        # S99 entry integrity: count trades struck late/off a stale feed (entry_valid
        # False). >0 ⇒ the day's A/B tables must filter these out (they're not clean).
        n_entry_invalid=(int((tc["entry_valid"] == False).sum())  # noqa: E712 (NaN-safe)
                         if "entry_valid" in tc.columns else 0),
        credit_total=round(pd.to_numeric(tc.credit, errors="coerce").sum() * 100, 0) if len(tc) else None,
        # realized side (evening report)
        session_type=ev.get("session_type"), forecast_accurate=ev.get("forecast_accurate"),
        em_hit=ev.get("expected_move_hit"), spx_change=ev.get("spx_change"),
        vix_change=ev.get("vix_change"),
    )
    return row


def main():
    trades = (pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
              if (ROOT / "data" / "options_log" / "trades.parquet").exists()
              else pd.DataFrame(columns=["entry_dt", "exit_dt", "pnl", "credit", "strategy_id"]))
    rows = []
    for p in sorted(glob.glob(str(SIM / "gameplan_*.json"))):
        if not re.search(r"gameplan_\d{8}\.json$", p):
            continue
        try:
            rows.append(day_row(p, trades))
        except Exception as e:
            print(f"skip {Path(p).name}: {e}")
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"daily_summary.csv: {len(df)} day(s)")
    if len(df):
        cols = ["date", "signal", "session_type", "em_hit", "open_spot",
                "pnl_total", "pnl_eod", "pnl_open", "pnl_gexlog", "n_closed"]
        print(df[[c for c in cols if c in df.columns]].to_string(index=False))


if __name__ == "__main__":
    main()
