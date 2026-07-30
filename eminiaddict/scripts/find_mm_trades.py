"""Scan ES daily for COMPLETED traditional measured moves that actually worked:
leg low->high, price pulls back and TAGS the 50% HWB, never breaches the 61.8%
failure, then rallies to the 123.6% target. Prints the candidates.

A valid long (mirror for short):
  L,H = swing low/high, R=H-L
  hwb = L+0.5R   (entry, must be tagged: some low <= hwb after H)
  fail= L+0.382R (must NOT be breached: no low < fail before target)
  tgt = H+0.236R (must be reached: some high >= tgt after the pullback)
"""
import sys
import pandas as pd

PARQUET = "../../data/bars/_db_es_5m_rth.parquet"  # resampled to 15m below
TF = "15min"         # Halsey trades the 50% setup on the 15-minute chart
ZZ_PCT = 0.5         # intraday swing-leg threshold
MAXFWD = 60          # 15m bars after the high to allow pullback+target to complete


def zigzag(highs, lows, pct):
    """Percent ZigZag. One state (dir): dir=1 last pivot was a low -> seeking a
    high; dir=-1 seeking a low. The running extreme only advances in the direction
    being sought (the previous version updated both extremes every bar, which let
    the reference run away and stalled pivot detection)."""
    thr = pct / 100.0
    n = len(highs)
    piv = []
    d = 0
    hi_i, hi = 0, highs[0]
    lo_i, lo = 0, lows[0]
    for i in range(1, n):
        if d == 1:                                   # seeking a high
            if highs[i] > hi:
                hi, hi_i = highs[i], i
            elif lows[i] <= hi * (1 - thr):          # confirmed reversal down
                piv.append((hi_i, hi, 'H')); d = -1; lo, lo_i = lows[i], i
        elif d == -1:                                # seeking a low
            if lows[i] < lo:
                lo, lo_i = lows[i], i
            elif highs[i] >= lo * (1 + thr):         # confirmed reversal up
                piv.append((lo_i, lo, 'L')); d = 1; hi, hi_i = highs[i], i
        else:                                        # undecided: seed direction
            if highs[i] > hi:
                hi, hi_i = highs[i], i
            if lows[i] < lo:
                lo, lo_i = lows[i], i
            if lows[i] <= hi * (1 - thr):
                piv.append((hi_i, hi, 'H')); d = -1; lo, lo_i = lows[i], i
            elif highs[i] >= lo * (1 + thr):
                piv.append((lo_i, lo, 'L')); d = 1; hi, hi_i = highs[i], i
    return piv


def scan(df, debug=False):
    H = df["High"].values; L = df["Low"].values
    piv = zigzag(H, L, ZZ_PCT)
    out = []
    fun = {"legs": 0, "tagged_hwb": 0, "not_breached": 0, "reached_tgt": 0}
    for k in range(len(piv) - 1):
        (i0, p0, k0), (i1, p1, k1) = piv[k], piv[k + 1]
        if k0 == 'L' and k1 == 'H':      # up leg
            lo, hi = p0, p1; up = True
        elif k0 == 'H' and k1 == 'L':    # down leg
            hi, lo = p0, p1; up = False
        else:
            continue
        R = hi - lo
        if R <= 0:
            continue
        if up:
            hwb = lo + 0.5 * R; fail = lo + 0.382 * R; tgt = hi + 0.236 * R
        else:
            hwb = hi - 0.5 * R; fail = hi - 0.382 * R; tgt = lo - 0.236 * R
        fun["legs"] += 1
        j0, j1 = i1 + 1, min(len(df), i1 + 1 + MAXFWD)
        idx_tgt = idx_entry = None
        breached = False
        for j in range(j0, j1):
            if up:
                if idx_entry is None and L[j] <= hwb: idx_entry = j
                if idx_entry is not None and L[j] < fail: breached = True; break
                if idx_entry is not None and H[j] >= tgt: idx_tgt = j; break
            else:
                if idx_entry is None and H[j] >= hwb: idx_entry = j
                if idx_entry is not None and H[j] > fail: breached = True; break
                if idx_entry is not None and L[j] <= tgt: idx_tgt = j; break
        if idx_entry is not None: fun["tagged_hwb"] += 1
        if idx_entry is not None and not breached: fun["not_breached"] += 1
        if idx_tgt is not None and not breached: fun["reached_tgt"] += 1
        if breached or idx_entry is None or idx_tgt is None:
            continue
        out.append({
            "up": up, "i0": i0, "i1": i1, "i_entry": idx_entry, "i_tgt": idx_tgt,
            "L": lo, "H": hi, "R": R, "hwb": hwb, "fail": fail, "tgt": tgt,
            "dL": df.DateTime[i0].date(), "dH": df.DateTime[i1].date(),
            "d_entry": df.DateTime[idx_entry].date(), "d_tgt": df.DateTime[idx_tgt].date(),
            "bars_pull": idx_entry - i1, "bars_tgt": idx_tgt - idx_entry,
        })
    if debug:
        print("funnel:", fun, "\n")
    return out


def load():
    df = pd.read_parquet(PARQUET)
    r = (df.set_index("DateTime").resample(TF)
         .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
         .dropna().reset_index())
    return r


def main():
    df = load()
    print(f"{len(df)} {TF} RTH bars  {df.DateTime.iloc[0].date()}..{df.DateTime.iloc[-1].date()}")
    res = scan(df, debug=True)
    print(f"found {len(res)} completed measured moves (ZZ {ZZ_PCT}%)\n")
    # rank most-recent first (recent = real prices; _db older data is back-adjusted)
    res.sort(key=lambda r: -r["i1"])
    print(f"{'dir':4} {'leg low->high':28} {'entry(HWB)':12} {'target hit':12} {'R':>7} {'pull':>4} {'tgt':>4}")
    for r in res[:25]:
        d = "LONG" if r["up"] else "SHORT"
        print(f"{d:4} {str(r['dL'])+' '+format(r['L'],',.2f'):>13} -> {str(r['dH'])+' '+format(r['H'],',.2f'):>13} "
              f"{r['d_entry']}  {r['d_tgt']}  {r['R']:7.1f} {r['bars_pull']:4d} {r['bars_tgt']:4d}")
    # emit the chosen index for the drawer (arg: rank, default 0)
    rank = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    r = res[rank]
    print("\nCHOSEN[", rank, "]:", {k: (v if not isinstance(v, float) else round(v, 2))
                                    for k, v in r.items() if k in
                                    ("up", "i0", "i1", "i_entry", "i_tgt", "L", "H", "hwb", "fail", "tgt")})


if __name__ == "__main__":
    main()
