"""tempo_engine.py — EXACT Python port of the v2 NT8 tempo indicators (S116-tempo).

Replicates TempoSpeedometer/TempoStateStripes bar-for-bar on the trove 2000t table
so chart marks and offline analysis speak the same numbers:

  - tempo pctile: rank vs the previous <=480 values (60 sessions x 8) of the SAME
    15-min clock bucket, excluding the current bar; <30 samples -> global
    rolling-200 fallback; <30 there -> 50. Same for amplitude (range). Efficiency
    pctile: global rolling-200 only. Pushes happen AFTER scoring (exclude-current).
  - warm = tempo or range bucket under 30 samples; no CLIMAX while warm.
  - CLIMAX: !warm and tpct >= 95.
  - ABR8: range as % of the mean of the prior 8 bar ranges (continuous, matches indi).
  - 10-bar window (reset each session): eff10 = |close_t - close_{t-10}| / sum(range),
    t10 = mean tpct. States (exact chain): CLIMAX(0) -> EXPAND(1: eff10>=.30 & t10>=50)
    -> CHURN(2: t10>=60 & eff10<=.10) -> GRIND(4: eff10>=.30) -> ACTIVITY(3: tpct>=80 &
    apct<50) -> BALANCE(5: tpct<40 & apct<40) -> MIXED(6).
  - dir: EXPAND/GRIND from sign(net10); otherwise close >= EMA20(close) (pre-update,
    stripes convention). First bar of each day skipped (indicator behavior).

Known, unavoidable delta vs the live chart: the trove is RTH-only, so a chart
running the ETH template feeds overnight bars into its buffers; RTH readings will
differ slightly. Everything else is the same math and parameters.

Output: tempo/outputs/tempo_engine_bars.parquet
    python tempo/scripts/tempo_engine.py
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"

CAP, MINS, ROLL = 480, 30, 200
CLIMAX = 95.0
EFF10_GATE, T10_GATE = 0.30, 50.0
K_EMA = 2.0 / 21.0


class Roll:
    def __init__(self, cap):
        self.cap = cap
        self.v = []

    def pct(self, x):
        if len(self.v) < MINS:
            return None
        below = sum(1 for a in self.v if a <= x)
        return max(1.0, min(99.0, 100.0 * below / (len(self.v) + 1)))

    def push(self, x):
        self.v.append(x)
        if len(self.v) > self.cap:
            self.v.pop(0)


def main():
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["minute"] = pd.to_datetime(df["start"]).dt.hour * 60 + pd.to_datetime(df["start"]).dt.minute
    df["bucket"] = (df["minute"] // 15).astype(int)

    bufT = {}
    bufA = {}
    rollT, rollA, rollE = Roll(ROLL), Roll(ROLL), Roll(ROLL)
    lastRanges = []
    ema_close = None
    ema_init = False

    n = len(df)
    tpct = np.full(n, np.nan); apct = np.full(n, np.nan); epct = np.full(n, np.nan)
    ampabr = np.full(n, np.nan); e10 = np.full(n, np.nan); t10a = np.full(n, np.nan)
    state = np.full(n, -1); dirn = np.zeros(n); climax = np.zeros(n, bool); warm = np.zeros(n, bool)

    cur_date = None
    w10 = []                     # (close, range, tpct)
    for i, r in enumerate(df.itertuples()):
        if r.date != cur_date:
            cur_date = r.date
            w10 = []
            continue             # first bar of session: skipped entirely (indicator)
        if r.ticks != 2000:
            continue
        b = int(r.bucket)
        bt = bufT.setdefault(b, Roll(CAP))
        ba = bufA.setdefault(b, Roll(CAP))
        tempo, rng, eff, close = r.tempo, r.range, r.eff, r.close

        tp = bt.pct(tempo); ap = ba.pct(rng)
        w = tp is None or ap is None
        if tp is None:
            tp = rollT.pct(tempo)
            tp = 50.0 if tp is None else tp
        if ap is None:
            ap = rollA.pct(rng)
            ap = 50.0 if ap is None else ap
        ep = rollE.pct(eff)
        ep = 50.0 if ep is None else ep
        bt.push(tempo); ba.push(rng)
        rollT.push(tempo); rollA.push(rng); rollE.push(eff)

        abr = np.mean(lastRanges) if lastRanges else np.nan
        aabr = 100.0 * rng / abr if abr and abr > 0 else np.nan
        lastRanges.append(rng)
        if len(lastRanges) > 8:
            lastRanges.pop(0)

        if not ema_init:
            ema_close = close; ema_init = True
        bull = close >= ema_close          # stripes convention: pre-update
        ema_close += K_EMA * (close - ema_close)

        w10.append((close, rng, tp))
        if len(w10) > 11:
            w10.pop(0)
        eff10 = t10 = None; net10 = 0.0
        if len(w10) == 11:
            net10 = w10[10][0] - w10[0][0]
            sr = sum(x[1] for x in w10[1:])
            st = sum(x[2] for x in w10[1:])
            if sr > 0:
                eff10 = abs(net10) / sr
            t10 = st / 10.0

        cx = (not w) and tp >= CLIMAX
        trending = eff10 is not None and eff10 >= EFF10_GATE
        if cx:
            s = 0
        elif trending and t10 >= T10_GATE:
            s = 1
        elif eff10 is not None and t10 >= 60 and eff10 <= 0.10:
            s = 2
        elif trending:
            s = 4
        elif tp >= 80 and ap < 50:
            s = 3
        elif tp < 40 and ap < 40:
            s = 5
        else:
            s = 6
        d = (1 if net10 >= 0 else -1) if s in (1, 4) else (1 if bull else -1)

        tpct[i], apct[i], epct[i] = tp, ap, ep
        ampabr[i] = aabr
        e10[i] = np.nan if eff10 is None else eff10
        t10a[i] = np.nan if t10 is None else t10
        state[i], dirn[i], climax[i], warm[i] = s, d, cx, w

    out = df[["date", "bar", "start", "end", "open", "high", "low", "close",
              "vol", "ticks", "duration_s", "tempo", "range", "eff", "session_min"]].copy()
    out["tpct"] = tpct; out["apct"] = apct; out["epct"] = epct
    out["amp_abr8"] = ampabr; out["eff10"] = e10; out["t10"] = t10a
    out["state"] = state; out["dir"] = dirn; out["climax"] = climax; out["warm"] = warm
    out.to_parquet(OUT, index=False)

    done = out[out["state"] >= 0]
    print(f"bars scored: {len(done):,} / {len(out):,}   climax share: {done['climax'].mean():.3f}")
    print("state shares:", {i: round(float((done['state'] == i).mean()), 3) for i in range(7)})
    print(f"saved -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
