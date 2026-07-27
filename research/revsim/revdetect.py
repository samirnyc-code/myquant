"""Faithful Python port of MyReversals detection (Trap/BO/OB/IB + Follow-Through).

Runs on the CONTINUOUS RTH 5M series (cross-day lookbacks intact, like NT). Every
detection parameter is exposed so they can be swept. Emits the SAME tradeable signal
the indicator exports:  signal = FT[i] AND rev[i-1] (Trap/BO/OB/IB), entry = Close[i],
stop = MIN(Low,2)[i-1].  Validated signal-for-signal against the NT export.

Bar indexing: arrays are the continuous series; for bar i, [0]->i, [1]->i-1, ...
bsd[i] = Bars.BarsSinceNewTradingDay (0 at each session's first bar).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant")
TICK = 0.25

DEFAULTS = dict(
    Trap_IBS=50, Trap_UL=100, Trap_Body=0, Trap_Tail=1, Trap_MinSize=1, Trap_ABR=0.33,
    Trap_Prior_OppClose=False, Trap_BodyCheck=False,
    BO_IBS=50, BO_UL=1, BO_Body=10, BO_CloseBeyond=False, BO_ABR=0.5, BO_Prior_OppClose=False,
    OB_IBS=50, OB_UL=1, OB_Body=5, OB_CloseBeyond=False, OB_CloseBeyondIB=False, OB_ABR=0.50,
    OB_Strict=False, OB_Prior_OppClose=False, OB_BodyCheck=True,
    IB_IBS=50, IB_Body=0, IB_BodyCheck=False, IB_Prior_Tail=50, IB_Prior_OppClose=False,
    FT_IBS=50, FT_UL=5, FT_Body=5, FT_CloseBeyond=True, FT_ABR=0.24, FT_NoDojiIB=True,
    ShowTrap=True, ShowBO=True, ShowOB=True, ShowIB=True,
)


def _prep(df5):
    d = df5.sort_values("DateTime").reset_index(drop=True)
    O, H, L, C = d.Open.values, d.High.values, d.Low.values, d.Close.values
    rng = H - L
    body = np.abs(O - C)
    with np.errstate(divide="ignore", invalid="ignore"):
        ibs = np.where(rng != 0, (C - L) / rng * 100.0, 0.0)
    uptail = H - np.maximum(O, C)
    lotail = np.minimum(O, C) - L
    avg = pd.Series(rng).rolling(8).mean().values
    bsd = d["bar"].values
    n = len(d)
    bardir = np.zeros(n, dtype=int)
    for i in range(n):
        prev = bardir[i - 1] if i > 0 else 0
        c, o, s = C[i], O[i], ibs[i]
        if c > o and s >= 50: bardir[i] = 1
        elif c < o and s <= 50: bardir[i] = -1
        elif c == o and s > 50: bardir[i] = 1
        elif c == o and s < 50: bardir[i] = -1
        elif c == o and s == 50: bardir[i] = prev
        elif c < o and s > 50: bardir[i] = 1
        elif c > o and s < 50: bardir[i] = -1
        else: bardir[i] = prev
    return dict(O=O, H=H, L=L, C=C, rng=rng, body=body, ibs=ibs, up=uptail, lo=lotail,
                avg=avg, bsd=bsd, dir=bardir, n=n, dt=d.DateTime.values, date=d.Date.values,
                bar=d["bar"].values)


def detect(df5, p=None):
    """Return DataFrame of tradeable signals (FT-confirmed reversals)."""
    P = dict(DEFAULTS);
    if p: P.update(p)
    A = _prep(df5)
    O, H, L, C = A["O"], A["H"], A["L"], A["C"]
    rng, body, ibs, up, lo = A["rng"], A["body"], A["ibs"], A["up"], A["lo"]
    avg, bsd, D, n = A["avg"], A["bsd"], A["dir"], A["n"]
    revL = np.zeros(n, bool); revS = np.zeros(n, bool)
    revtypeL = np.array([""] * n, dtype=object); revtypeS = np.array([""] * n, dtype=object)
    ftL = np.zeros(n, bool); ftS = np.zeros(n, bool)

    def abr_ok(k, mult):
        return (avg[k] * mult <= rng[k]) or (1 > mult and min(avg[k] * mult, avg[k] - TICK) <= rng[k])

    for i in range(6, n):
        if np.isnan(avg[i]) or np.isnan(avg[i - 1]):
            continue
        first = bsd[i] < 1
        # --- Trap ---
        if P["ShowTrap"]:
            if ((D[i-1] == -1 or (first and L[i-1] > H[i])) and abr_ok(i, P["Trap_ABR"]) and
                D[i] == 1 and H[i-1] >= H[i] and ibs[i] >= P["Trap_IBS"] and
                (O[i] < C[i] or not P["Trap_BodyCheck"]) and
                (L[i-1] - rng[i]*(P["Trap_UL"]/100) <= L[i] or first) and
                rng[i]*(P["Trap_Body"]/100) <= body[i] and
                (O[i-1] > C[i-1] or not P["Trap_Prior_OppClose"]) and
                (rng[i]*(P["Trap_Tail"]/100) <= lo[i] or first) and
                L[i-1] - P["Trap_MinSize"]*TICK >= L[i]):
                revL[i] = True; revtypeL[i] = "Trap"
            if ((D[i-1] == 1 or (first and H[i-1] < L[i])) and abr_ok(i, P["Trap_ABR"]) and
                D[i] == -1 and L[i-1] <= L[i] and ibs[i] <= (100-P["Trap_IBS"]) and
                (O[i] > C[i] or not P["Trap_BodyCheck"]) and
                (H[i-1] + rng[i]*(P["Trap_UL"]/100) >= H[i] or first) and
                rng[i]*(P["Trap_Body"]/100) <= body[i] and
                (O[i-1] < C[i-1] or not P["Trap_Prior_OppClose"]) and
                (rng[i]*(P["Trap_Tail"]/100) <= up[i] or first) and
                H[i-1] + P["Trap_MinSize"]*TICK <= H[i]):
                revS[i] = True; revtypeS[i] = "Trap"
        # --- BO ---
        if P["ShowBO"]:
            if (D[i-1] == -1 and abr_ok(i, P["BO_ABR"]) and D[i] == 1 and O[i] < C[i] and
                L[i-1] < L[i] and ibs[i] >= P["BO_IBS"] and
                H[i-1] + rng[i]*(P["BO_UL"]/100) <= H[i] and
                rng[i]*(P["BO_Body"]/100) <= body[i] and
                (O[i-1] > C[i-1] or not P["BO_Prior_OppClose"]) and
                (H[i-1] < C[i] or (H[i-1] < H[i] and not P["BO_CloseBeyond"]))):
                if not revL[i]: revL[i] = True; revtypeL[i] = "BO"
            if (D[i-1] == 1 and abr_ok(i, P["BO_ABR"]) and D[i] == -1 and O[i] > C[i] and
                H[i-1] > H[i] and ibs[i] <= (100-P["BO_IBS"]) and
                L[i-1] - rng[i]*(P["BO_UL"]/100) >= L[i] and
                rng[i]*(P["BO_Body"]/100) <= body[i] and
                (O[i-1] < C[i-1] or not P["BO_Prior_OppClose"]) and
                (L[i-1] > C[i] or (L[i-1] > L[i] and not P["BO_CloseBeyond"]))):
                if not revS[i]: revS[i] = True; revtypeS[i] = "BO"
        # --- OB ---
        if P["ShowOB"]:
            out0 = H[i-1] < H[i] and L[i-1] > L[i]
            ins1 = (H[i-1] >= H[i-2] and L[i-1] <= L[i-2])
            if (D[i-1] == -1 and abr_ok(i, P["OB_ABR"]) and
                (out0 or (not P["OB_Strict"] and L[i-1] == L[i] and H[i-1] < H[i])) and
                D[i] == 1 and ibs[i] >= P["OB_IBS"] and (O[i] < C[i] or not P["OB_BodyCheck"]) and
                H[i-1] + rng[i]*(P["OB_UL"]/100) <= H[i] and
                rng[i]*(P["OB_Body"]/100) <= body[i] and
                (O[i-1] > C[i-1] or not P["OB_Prior_OppClose"]) and
                not (ins1 and H[i-1] >= C[i] and P["OB_CloseBeyondIB"]) and
                (H[i-1] < C[i] or not P["OB_CloseBeyond"])):
                if not revL[i]: revL[i] = True; revtypeL[i] = "OB"
            if (D[i-1] == 1 and abr_ok(i, P["OB_ABR"]) and
                (out0 or (not P["OB_Strict"] and H[i-1] == H[i] and L[i-1] > L[i])) and
                D[i] == -1 and ibs[i] <= (100-P["OB_IBS"]) and (O[i] > C[i] or not P["OB_BodyCheck"]) and
                L[i-1] - rng[i]*(P["OB_UL"]/100) >= L[i] and
                rng[i]*(P["OB_Body"]/100) <= body[i] and
                (O[i-1] < C[i-1] or not P["OB_Prior_OppClose"]) and
                not (ins1 and L[i-1] <= C[i] and P["OB_CloseBeyondIB"]) and
                (L[i-1] > C[i] or not P["OB_CloseBeyond"])):
                if not revS[i]: revS[i] = True; revtypeS[i] = "OB"
        # --- IB ---
        if P["ShowIB"]:
            if (not revL[i] and D[i-1] == -1 and D[i] == 1 and
                (O[i] < C[i] or not P["IB_BodyCheck"]) and
                H[i-1] >= H[i] and L[i-1] <= L[i] and rng[i-1] >= rng[i] and ibs[i] >= P["IB_IBS"] and
                rng[i]*(P["IB_Body"]/100) <= body[i] and
                rng[i-1]*(P["IB_Prior_Tail"]/100) >= lo[i-1] and
                (O[i-1] > C[i-1] or not P["IB_Prior_OppClose"])):
                revL[i] = True; revtypeL[i] = "IB"
            if (not revS[i] and D[i-1] == 1 and D[i] == -1 and
                (O[i] > C[i] or not P["IB_BodyCheck"]) and
                L[i-1] <= L[i] and H[i-1] >= H[i] and rng[i-1] >= rng[i] and ibs[i] <= (100-P["IB_IBS"]) and
                rng[i]*(P["IB_Body"]/100) <= body[i] and
                rng[i-1]*(P["IB_Prior_Tail"]/100) >= up[i-1] and
                (O[i-1] < C[i-1] or not P["IB_Prior_OppClose"])):
                revS[i] = True; revtypeS[i] = "IB"

    # --- Follow Through (needs rev on prior bar) ---
    for i in range(6, n):
        if np.isnan(avg[i]): continue
        ins1 = (H[i-2] >= H[i-1] and L[i-2] <= L[i-1])
        if (revL[i-1] and abr_ok(i, P["FT_ABR"]) and L[i-1] <= L[i] and ibs[i] >= P["FT_IBS"] and
            H[i-1] + rng[i]*(P["FT_UL"]/100) <= H[i] and rng[i]*(P["FT_Body"]/100) <= body[i] and
            not (D[i] == -1 and rng[i]/3 > body[i]) and
            (H[i-1] < C[i] or (H[i-1] < H[i] and O[i-1] < C[i] and not P["FT_CloseBeyond"])) and
            not (ins1 and rng[i-2]/20 > body[i-2] and H[i-2] >= C[i] and P["FT_NoDojiIB"]) and
            not (L[i-2] == L[i-1] and L[i-1] == L[i])):
            ftL[i] = True
        if (revS[i-1] and abr_ok(i, P["FT_ABR"]) and H[i-1] >= H[i] and ibs[i] <= (100-P["FT_IBS"]) and
            L[i-1] - rng[i]*(P["FT_UL"]/100) >= L[i] and rng[i]*(P["FT_Body"]/100) <= body[i] and
            not (D[i] == 1 and rng[i]/3 > body[i]) and
            (L[i-1] > C[i] or (L[i-1] > L[i] and O[i-1] > C[i] and not P["FT_CloseBeyond"])) and
            not (ins1 and rng[i-2]/20 > body[i-2] and L[i-2] <= C[i] and P["FT_NoDojiIB"]) and
            not (H[i-2] == H[i-1] and H[i-1] == H[i])):
            ftS[i] = True

    FIVE = pd.Timedelta("5min")  # df5 DateTime is OPEN-labelled; NT export uses CLOSE time
    sigs = []
    for i in range(6, n):
        if ftL[i]:
            sigs.append(dict(rev=revtypeL[i-1], side=1, Date=str(A["date"][i]),
                             time=pd.Timestamp(A["dt"][i]) + FIVE, bar=int(A["bar"][i]),
                             entry=C[i], stop=min(L[i-1], L[i-2])))
        if ftS[i]:
            sigs.append(dict(rev=revtypeS[i-1], side=-1, Date=str(A["date"][i]),
                             time=pd.Timestamp(A["dt"][i]) + FIVE, bar=int(A["bar"][i]),
                             entry=C[i], stop=max(H[i-1], H[i-2])))
    return pd.DataFrame(sigs)


if __name__ == "__main__":
    df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
    df5["DateTime"] = pd.to_datetime(df5["DateTime"])
    sg = detect(df5)
    print(f"PORT produced {len(sg)} signals  {sg.Date.min()}..{sg.Date.max()}")
    print(sg.rev.value_counts().to_string())
    sg.to_parquet(ROOT / "research" / "revsim" / "signals_port_default.parquet")
