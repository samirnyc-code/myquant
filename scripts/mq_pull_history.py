"""Pull the 365-day history endpoints for SPX + ES1! into tidy CSVs (S73).
Direct API (no QUIN). Run nightly to keep them fresh + extend the archive.

Writes:
  data/menthorq/gex_insights_<SYM>.csv    date, gex, gex_pct_1y
  data/menthorq/skew_<SYM>.csv            date, skew_0dte, skew_1m, skew_3m
  data/menthorq/qscore_<SYM>.csv          date, momentum, seasonality, volatility, option
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menthorq"
SYMS = sys.argv[sys.argv.index("--symbols") + 1].split(",") if "--symbols" in sys.argv else ["SPX", "ES1!"]


def merge_csv(path, rows, key="date"):
    """Upsert rows (list of dicts) into a CSV keyed by `key`, sorted."""
    existing = {}
    if path.exists():
        with open(path) as fh:
            for r in csv.DictReader(fh):
                existing[r[key]] = r
    for r in rows:
        existing[r[key]] = {k: r.get(k) for k in rows[0]}
    cols = list(rows[0].keys())
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for k in sorted(existing):
            w.writerow(existing[k])
    return len(existing)


def main():
    mq = MQ()
    for sym in SYMS:
        s = sym.replace("!", "")
        try:
            gi = mq.gamma_insights(sym, 365)
            rows = [{"date": d["report_date"], "gex": d["gex"],
                     "gex_pct_1y": d.get("gex_percentile_1y")} for d in gi]
            n = merge_csv(OUT / f"gex_insights_{s}.csv", rows)
            print(f"{sym} gex_insights: {len(gi)} pulled, {n} total rows")
        except Exception as e:
            print(f"{sym} gex_insights FAIL: {e}")
        try:
            vi = mq.vol_insights(sym)
            hist = vi.get("skew", {}).get("history", [])
            cur = vi.get("skew", {})
            allrows = hist + [{k: cur.get(k) for k in ("report_date", "skew_0dte", "skew_1m", "skew_3m")}]
            rows = [{"date": d["report_date"], "skew_0dte": d.get("skew_0dte"),
                     "skew_1m": d.get("skew_1m"), "skew_3m": d.get("skew_3m")}
                    for d in allrows if d.get("report_date")]
            if rows:
                n = merge_csv(OUT / f"skew_{s}.csv", rows)
                print(f"{sym} skew: {len(rows)} pulled, {n} total rows")
        except Exception as e:
            print(f"{sym} skew FAIL: {e}")
        try:
            m = mq.metrics(sym, 365)
            rows = [{"date": d["date"], **{k: d["metrics"].get(k) for k in
                     ("momentum", "seasonality", "volatility", "option")}} for d in m]
            n = merge_csv(OUT / f"qscore_{s}.csv", rows)
            print(f"{sym} qscore: {len(m)} pulled, {n} total rows")
        except Exception as e:
            print(f"{sym} qscore FAIL: {e}")


if __name__ == "__main__":
    main()
