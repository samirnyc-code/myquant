"""Options Codex — single-page dashboard builder (S73) -> data/options_sim/codex.html.

The Brooks-Codex-style replacement for the Streamlit app: one dark, fully custom
page. Static data (trades, journal, decisions, levels, calibration, marks) is
baked in at build time; the LIVE strip polls /live (see options_codex_serve.py)
every 5s; journal reviews POST to /review. Rebuilt automatically by the server.

Standalone build: .venv/Scripts/python.exe scripts/options_codex_build.py
"""
import datetime as dt
import glob
import json
from pathlib import Path

import pandas as pd

import options_build_cards as obc
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def safe_csv(p, tail=None):
    try:
        df = pd.read_csv(p)
        if tail:
            df = df.tail(tail)
        return json.loads(df.to_json(orient="records"))
    except Exception:
        return []


def build_payload():
    trades = tlog.load()
    marks_f = SIM / "marks.csv"
    last_marks = None
    if marks_f.exists():
        mk = pd.read_csv(marks_f)
        if len(mk):
            last_marks = mk.groupby("trade_id").last()
    spot = obc.latest_spot()
    cards = [obc.trade_payload(r, last_marks, spot) for _, r in trades.iloc[::-1].iterrows()]

    closed = trades[trades.exit_dt.notna()]
    p = closed.pnl.astype(float) if len(closed) else pd.Series(dtype=float)
    pf = round(p[p > 0].sum() / -p[p < 0].sum(), 2) if len(p) and (p < 0).any() else None
    open_tr = trades[trades.exit_dt.isna()]
    unreal = None
    if last_marks is not None:
        m = last_marks[last_marks.index.isin(set(open_tr.trade_id))]
        unreal = round(float(m.unreal_pnl.sum())) if len(m) else None
    acct = safe_csv(SIM / "account.csv", tail=1)
    jf = ROOT / "data" / "options_log" / "journal.json"
    journal = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
    lvl_f = ROOT / "scratchpad" / "mq_levels_today.json"
    levels = json.loads(lvl_f.read_text(encoding="utf-8")) if lvl_f.exists() else {}
    return {
        "built": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "open": int(len(open_tr)), "closed": int(len(closed)),
            "win": round(float((p > 0).mean()) * 100) if len(p) else None,
            "pf": pf, "realized": round(float(p.sum())) if len(p) else None,
            "unreal": unreal,
            "collateral": round(float(open_tr.collateral.astype(float).sum())) if len(open_tr) else 0,
            "ib_margin": acct[0].get("maint_margin") if acct else None,
            "net_liq": acct[0].get("net_liq") if acct else None,
        },
        "cards": cards,
        "journal": journal,
        "decisions": safe_csv(SIM / "decisions.csv", tail=40)[::-1],
        "calib": safe_csv(ROOT / "data" / "menthorq" / "spx_calibration.csv", tail=20)[::-1],
        "levels": levels,
        "vix_hist": safe_csv(ROOT / "data" / "vix_daily.csv", tail=120),
        "marks_tot": (lambda m: [{"ts": k, "v": round(float(v))} for k, v in
                                 pd.DataFrame(m).groupby("ts_et").unreal_pnl.sum().items()])(
            safe_csv(marks_f)) if marks_f.exists() else [],
    }


def main():
    payload = build_payload()
    tpl = (ROOT / "scripts" / "options_codex_tpl.html").read_text(encoding="utf-8")
    out = SIM / "codex.html"
    out.write_text(tpl.replace("__PAYLOAD__", json.dumps(payload)), encoding="utf-8")
    print(f"wrote {out} ({len(payload['cards'])} cards)")
    return out


if __name__ == "__main__":
    main()
