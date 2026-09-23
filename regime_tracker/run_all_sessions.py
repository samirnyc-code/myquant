#!/usr/bin/env python3
"""Re-run the regime tracker over every reference session and rebuild its chart.

    python run_all_sessions.py                 # all sessions
    python run_all_sessions.py 2026-05-18 ...  # just these
    python run_all_sessions.py --no-charts     # JSON only

Writes regime_data_es_<slug>.json + ms_chart_<slug>.png next to this script and
prints one summary line per session, so a rule change can be diffed by eye.
"""
import argparse, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
PARQUET = HERE.parent / "data" / "bars" / "_continuous_1m.parquet"

SESSIONS = ["2025-12-26", "2026-01-13", "2026-02-13", "2026-04-06",
            "2026-05-06", "2026-05-12",
            "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22",
            "2026-06-12", "2026-06-25", "2026-06-29"]


def run(date, charts=True):
    slug = date.replace("-", "")
    js = HERE / f"regime_data_es_{slug}.json"
    png = HERE / f"ms_chart_{slug}.png"
    subprocess.run([sys.executable, str(HERE / "run_regime_parquet.py"), str(PARQUET),
                    "--date", date, "--out", str(js)],
                   check=True, capture_output=True)
    if charts:
        subprocess.run([sys.executable, str(HERE / "plot_regime.py"), str(js),
                        "--out", str(png)], check=True, capture_output=True)
    return js


def summarise(js):
    d = json.load(open(js))
    bars, n = d["bars"], len(d["bars"])
    ml = sum(p["major"] for p in d["pivot_lows"]) + sum(p["major"] for p in d["pivot_highs"])
    mn = len(d["pivot_lows"]) + len(d["pivot_highs"]) - ml
    ev = d["events"]
    held = {"Bull": 0, "Bear": 0, "Range": 0}
    segs = d["segments"]
    for k, g in enumerate(segs):
        z = segs[k + 1]["start"] if k + 1 < len(segs) else n
        held[g["regime"]] += z - g["start"]
    return dict(
        n=n, maj=ml, minr=mn,
        bos=sum(e["kind"] == "BOS" for e in ev), choch=sum(e["kind"] == "ChoCh" for e in ev),
        held=held,
        shape=" ".join(f"{g['regime'][:2]}{g['start'] + 1}" for g in segs),
        o=bars[0]["o"], h=max(b["h"] for b in bars),
        l=min(b["l"] for b in bars), c=bars[-1]["c"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*", default=None)
    ap.add_argument("--no-charts", action="store_true")
    a = ap.parse_args()
    dates = a.dates or SESSIONS
    if not PARQUET.exists():
        sys.exit(f"parquet not found: {PARQUET}")

    print(f"{'session':<12} {'bars':>4} {'maj':>4} {'min':>4} {'BOS':>4} {'ChoCh':>6} "
          f"{'Bull':>5} {'Bear':>5} {'Rng':>5}  shape")
    for date in dates:
        s = summarise(run(date, charts=not a.no_charts))
        print(f"{date:<12} {s['n']:>4} {s['maj']:>4} {s['minr']:>4} {s['bos']:>4} "
              f"{s['choch']:>6} {s['held']['Bull']:>5} {s['held']['Bear']:>5} "
              f"{s['held']['Range']:>5}  {s['shape']}")
    print(f"\n{len(dates)} sessions -> {HERE}")


if __name__ == "__main__":
    main()
