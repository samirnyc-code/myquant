"""Daily MenthorQ full-surface miner (S75) — archive EVERYTHING MQ exposes, for the
whole universe, every day, LOSSLESSLY. MQ's retention is thin (futures ~2yr) and the
Matrix / per-strike / levels are TODAY-ONLY — so anything not captured today is gone.

For each ticker × surface it (a) writes the RAW JSON to
`data/menthorq/mine/raw/<surface>/<SYM>_<date>.json` (never lose data), and
(b) appends the key scalars to a flat CSV under `data/menthorq/mine/<surface>.csv`
for easy analysis. Never raises on one ticker/surface — logs and continues.

Run after the EOD sets are computed (indices/stocks 6pm ET, futures 11pm ET) — the
chain calls it ~22:15 CT. Options:
  .venv/Scripts/python.exe scripts/mq_mine.py            # daily pull (all surfaces, all tickers)
  .venv/Scripts/python.exe scripts/mq_mine.py --backfill # also pull 365d history surfaces
  .venv/Scripts/python.exe scripts/mq_mine.py --only SPX,ES1!   # subset
"""
import datetime as dt
import json
import sys
import traceback
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
MINE = ROOT / "data" / "menthorq" / "mine"
RAW = MINE / "raw"
ET = ZoneInfo("America/New_York")

# --- universe (MQ uses `1!` continuous for futures) ---------------------------
UNIVERSE = {
    "mag7": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
    "index": ["SPX", "NDX", "RUT"],
    "eq_futures": ["ES1!", "NQ1!", "RTY1!", "YM1!"],
    "commodity": ["CL1!", "GC1!", "SI1!", "HG1!", "NG1!"],
    "fx": ["6E1!", "6J1!", "6A1!", "6B1!"],
    "rates": ["ZB1!", "ZN1!"],
    # expansion — uncomment to widen:
    # "etf": ["SPY", "QQQ", "IWM"],
}

# --- surfaces: (name, callable(mq, sym), is_history) --------------------------
# is_history=True surfaces already carry ~365d, so a daily pull keeps them fresh
# and a --backfill isn't strictly needed; the today-only ones MUST run daily.
SURFACES = [
    ("levels", lambda mq, s: mq.levels(s), False),
    ("matrix_eod", lambda mq, s: mq.matrix(s, "eod"), False),
    ("matrix_intraday", lambda mq, s: mq.matrix(s, "intraday"), False),
    ("per_strike", lambda mq, s: mq.per_strike(s, "eod"), False),
    ("gamma_insights", lambda mq, s: mq.gamma_insights(s, 365), True),
    ("vol_insights", lambda mq, s: mq.vol_insights(s), True),
    ("qscore", lambda mq, s: mq.metrics(s, 365), True),
    ("swing_levels", lambda mq, s: mq.get(f"swing-levels/{s}"), True),
]


MIN_COVERAGE_PCT = 90.0   # below this the archive is FAILED, not "partial"


def _now():
    return dt.datetime.now(ET)


def save_raw(surface, sym, obj):
    d = RAW / surface
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sym.replace('!', '')}_{_now():%Y%m%d}.json").write_text(
        json.dumps(obj), encoding="utf-8")


def main():
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    syms = [s for group in UNIVERSE.values() for s in group]
    if only:
        syms = [s for s in syms if s in only]

    MINE.mkdir(parents=True, exist_ok=True)
    mq = MQ()
    ok = fail = empty = 0
    log = []
    missing = []          # (sym, surface, why) — what did NOT get archived
    for sym in syms:
        for name, fn, _hist in SURFACES:
            try:
                obj = fn(mq, sym)
                if obj is None or (isinstance(obj, (list, dict)) and not obj):
                    empty += 1
                    missing.append((sym, name, "empty"))
                    log.append(f"  --  {sym:7} {name:18} empty")
                    continue
                save_raw(name, sym, obj)
                n = len(obj) if isinstance(obj, (list, dict)) else 1
                ok += 1
                log.append(f"  OK  {sym:7} {name:18} ({n})")
            except Exception as e:
                fail += 1
                missing.append((sym, name, f"{type(e).__name__}: {str(e)[:50]}"))
                log.append(f"  XX  {sym:7} {name:18} {type(e).__name__}: {str(e)[:60]}")

    stamp = _now().strftime("%Y-%m-%d %H:%M ET")
    manifest = MINE / "mine_log.txt"
    with open(manifest, "a", encoding="utf-8") as f:
        f.write(f"\n=== {stamp} · {len(syms)} tickers × {len(SURFACES)} surfaces "
                f"· {ok} ok / {fail} fail ===\n" + "\n".join(log) + "\n")
    # ---- COMPLETION CHECK (S75V) ----------------------------------------------
    # This used to `return 0 if ok else 1`: ONE success out of 175 exited clean, and
    # "empty" responses counted as neither ok nor fail, so they vanished. A half-empty
    # archive looked identical to a full one — and these surfaces are TODAY-ONLY, so a
    # silent gap is permanent and unbackfillable. Coverage is measured against EXPECTED.
    expected = len(syms) * len(SURFACES)
    coverage = 100.0 * ok / expected if expected else 0.0

    (MINE / "mine_status.json").write_text(json.dumps({
        "ts": stamp, "date": _now().strftime("%Y-%m-%d"),
        "expected": expected, "ok": ok, "fail": fail, "empty": empty,
        "coverage_pct": round(coverage, 1),
        "missing": [{"sym": s, "surface": su, "why": w} for s, su, w in missing][:80],
    }, indent=2), encoding="utf-8")

    print(f"=== MQ mine {stamp} ===")
    print("\n".join(log))
    print(f"\n{ok} ok / {fail} fail / {empty} empty of {expected} expected"
          f"  ·  coverage {coverage:.1f}%")
    print(f"raw -> {RAW}  ·  log -> {manifest}")

    if coverage < MIN_COVERAGE_PCT:
        print(f"\n*** INCOMPLETE ARCHIVE: {coverage:.1f}% < {MIN_COVERAGE_PCT}% required.")
        print("    These surfaces are TODAY-ONLY — the gap cannot be backfilled.")
        for s_, su_, w_ in missing[:12]:
            print(f"      {s_:8} {su_:18} {w_}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
