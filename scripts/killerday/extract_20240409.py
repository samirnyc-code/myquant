"""Killer-day forensics extract: 2024-04-09.

Pulls the morning-context row, all backtest trade rows (IC + fly), SPX OHLC and
VIX OHLC for the surrounding days, and writes one dated CSV bundle under
data/options_sim/backtest_full/killerday/.

Local CSVs only (no ThetaData, per tonight's terminal lock).
"""
import csv
import io
import os

ROOT = r"c:\Users\Admin\myquant"
OUT_DIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
DAY = "2024-04-09"
WINDOW = ["2024-04-04", "2024-04-05", "2024-04-08", "2024-04-09", "2024-04-10", "2024-04-11", "2024-04-12"]


def rows_matching(path, pred):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return [row for row in r if pred(row)]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    bt = os.path.join(ROOT, "data", "options_sim", "backtest_full")

    ctx = rows_matching(os.path.join(bt, "killer_context.csv"), lambda r: r["date"] == DAY)
    ic = rows_matching(os.path.join(bt, "rows.csv"), lambda r: r["date"] == DAY)
    fly = rows_matching(os.path.join(bt, "fly_rows.csv"), lambda r: r["date"] == DAY)
    spx = rows_matching(os.path.join(bt, "spx_daily_ohlc.csv"), lambda r: r["date"] in WINDOW)
    vix = rows_matching(
        os.path.join(ROOT, "data", "VIX_History.csv"),
        lambda r: any(d.split("-")[1] + "/" + d.split("-")[2] + "/" + d.split("-")[0] == list(r.values())[0] for d in WINDOW),
    )

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["section", "payload"])
    for name, rows in [("context", ctx), ("ic_rows", ic), ("fly_rows", fly), ("spx_ohlc", spx), ("vix_ohlc", vix)]:
        for row in rows:
            w.writerow([name, ";".join(f"{k}={v}" for k, v in row.items())])

    out_path = os.path.join(OUT_DIR, f"forensics_{DAY}.csv")
    with open(out_path, "w", newline="") as f:
        f.write(out.getvalue())
    print("wrote", out_path)
    print("sections:", {n: len(x) for n, x in [("context", ctx), ("ic", ic), ("fly", fly), ("spx", spx), ("vix", vix)]})


if __name__ == "__main__":
    main()
