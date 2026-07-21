"""revft_stoch_study.py — RevFT signals × Stochastic discovery (v2).

Analysis axes:
  A. Filter mode x target matrix   (Off / MeanRev / Momentum / ZoneSignal / LocationEdge)
  B. HOD/LOD location               (where in day's range signal fires, Long vs Short)
  C. Time of day                    (Opening / Mid / Lunch / Afternoon)
  D. K slope x Direction            (rising/falling K split within Longs vs Shorts)
  E. Year x Direction               (2021 / 2022 / 2023 separately)
  F. Location + Zone combos         (near-extreme + OS/OB zone intersection)
  G. Standard stoch cuts            (K bins, zone x dir, ZoneSignal)
  H. Year stability for best combos

Causal join: stoch bar T attached to signal at bar T (searchsorted right-1).
Price basis: verified stop < entry for Longs, all ticks back-adjusted.

Run:
  C:/Users/Thomas-Code/Projects/myquant/.venv/Scripts/python.exe scripts/revft_stoch_study.py
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_MAIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import massive                                                         # noqa: E402
massive._TICKS_CONT_DIR = _MAIN / "data" / "ticks_continuous"          # noqa: E402
from simulation_engine import simulate_trades                          # noqa: E402

# ── paths ──────────────────────────────────────────────────────────────────────
_SIGNALS_TXT = Path(
    r"C:\Users\Admin\Desktop"
    r"\MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_STOCH_CSV = Path(
    r"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\Stoch\ES_stoch.csv"
)
_BARS = _MAIN / "data" / "bars" / "_continuous.parquet"
_OUT  = _ROOT / "docs" / "living"

OS_LEVEL = 20.0
OB_LEVEL = 80.0
DATE_CAP = "2024-01-01"   # 2021-2023 only (tick cache fully clean for this range)

BASE = dict(
    entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
    contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
    ratchet_r=0.0, pb_round="nearest",
    multileg=False, threeleg=False, overrides=None,
)
TARGETS = [0.5, 1.0, 1.5, 2.0, 3.0]


def log(m: str) -> None:
    print(f"[stoch_study] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── parse RevFT signals ────────────────────────────────────────────────────────
def parse_signals(path: Path) -> pd.DataFrame:
    rows = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.rstrip()
            if not line or line.startswith("-") or not line[0].isdigit():
                continue
            line = re.sub(r"(\d),(\d)", r"\1\2", line)
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                sig_num   = int(parts[0])
                sig_type  = parts[1]
                direction = parts[2]
                dt        = datetime.strptime(f"{parts[3]} {parts[4]}", "%d/%m/%Y %H:%M:%S")
                bar_num   = int(parts[5])
                sig_px    = float(parts[6])
                stop_px   = float(parts[7])
            except (ValueError, IndexError):
                continue
            rows.append(dict(
                SignalNum=sig_num, SignalType=sig_type, Direction=direction,
                DateTime=dt, BarNum=bar_num,
                SignalPrice=sig_px, StopPrice=stop_px,
            ))
    df = pd.DataFrame(rows)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df["Date"]     = df["DateTime"].dt.date
    return df.sort_values("DateTime").reset_index(drop=True)


# ── load / join stoch ──────────────────────────────────────────────────────────
def load_stoch(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["DateTime"]).sort_values("DateTime").reset_index(drop=True)


def join_stoch(signals: pd.DataFrame, stoch: pd.DataFrame) -> pd.DataFrame:
    sto_dt = stoch["DateTime"].values.astype("datetime64[ns]")
    sig_dt = signals["DateTime"].values.astype("datetime64[ns]")
    idx    = np.searchsorted(sto_dt, sig_dt, side="right") - 1
    valid  = idx >= 0

    def _col(col, shift=0):
        i = np.clip(idx + shift, 0, len(stoch) - 1)
        ok = valid & (idx + shift >= 0) & (idx + shift < len(stoch))
        return np.where(ok, stoch[col].values[i], np.nan)

    out = signals.copy()
    out["STO_K"]         = _col("K")
    out["STO_D"]         = _col("D")
    out["STO_KSignalUp"] = _col("KSignalUp")
    out["STO_KSignalDn"] = _col("KSignalDn")
    out["STO_ZoneSignal"]= _col("ZoneSignal")
    for lag in (1, 2, 3):
        out[f"STO_K_lag{lag}"] = _col("K", -lag)
    out["STO_K_next"] = _col("K", 1)   # look-ahead — diagnostic only

    k = out["STO_K"]
    out["STO_Zone"]     = np.where(k >= OB_LEVEL, "OB", np.where(k <= OS_LEVEL, "OS", "mid"))
    out.loc[k.isna(), "STO_Zone"] = np.nan
    out["STO_KoverD"]   = out["STO_K"] > out["STO_D"]
    out["STO_KslopeUp"] = out["STO_K"] > out["STO_K_lag1"]
    out["STO_lead_in"]  = out["STO_K"] - out["STO_K_lag3"]
    return out


# ── location features (HOD/LOD proximity) ─────────────────────────────────────
def add_location_features(signals: pd.DataFrame, bars_by_date: dict) -> pd.DataFrame:
    """Add DayPctRange (0=at LOD, 1=at HOD) and TimeOfDay bucket to each signal.

    DayPctRange: (signal_price - session_low_so_far) / (session_high_so_far - session_low_so_far)
    Uses bars with close time <= signal close time on the same RTH session.
    """
    pct  = np.full(len(signals), np.nan)
    tod  = [""] * len(signals)

    for i, (_, row) in enumerate(signals.iterrows()):
        d = row["DateTime"].date()
        t = row["DateTime"]

        # Time of day bucket (bar CLOSE time is CT)
        hm = t.hour * 60 + t.minute
        if hm <= 570:        # <= 09:30
            tod[i] = "Opening (08:35-09:30)"
        elif hm <= 660:      # <= 11:00
            tod[i] = "Mid-morning (09:35-11:00)"
        elif hm <= 780:      # <= 13:00
            tod[i] = "Lunch (11:05-13:00)"
        else:
            tod[i] = "Afternoon (13:05-15:15)"

        # HOD/LOD position
        if d not in bars_by_date:
            continue
        day_bars = bars_by_date[d]
        prior = day_bars[day_bars["DateTime"] <= t]
        if prior.empty:
            continue
        h   = prior["High"].max()
        l   = prior["Low"].min()
        rng = h - l
        if rng < 0.25:
            pct[i] = 0.5
            continue
        pct[i] = float(np.clip((row["SignalPrice"] - l) / rng, 0.0, 1.0))

    out = signals.copy()
    out["DayPctRange"] = pct
    out["TimeOfDay"]   = tod
    return out


# ── stats / table helpers ──────────────────────────────────────────────────────
def stats(pnl: np.ndarray, risk: np.ndarray | None = None) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan, rci=np.nan)
    net = float(pnl.sum())
    gw  = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl  = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf  = gw / gl if gl > 0 else float("inf")
    wr  = float((pnl > 0).mean() * 100)
    exp = net / n
    ci  = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    if risk is not None:
        rm   = pnl / risk
        rr   = rm[np.isfinite(rm)]
        expR = float(rr.mean()) if len(rr) else np.nan
        rci  = float(1.96 * rr.std(ddof=1) / np.sqrt(len(rr))) if len(rr) > 1 else np.nan
    else:
        expR = rci = np.nan
    return dict(n=n, net=net, exp=exp, pf=pf, wr=wr, expR=expR, ci=ci, rci=rci)


HDR = "| group | n | net $ | exp R | ±CI | 95% interval | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|"


def row(label: str, pnl: np.ndarray, risk: np.ndarray | None = None) -> str:
    s = stats(pnl, risk)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    pf  = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    er  = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    rci = "—" if np.isnan(s["rci"])  else f"±{s['rci']:.3f}"
    if not np.isnan(s["expR"]) and not np.isnan(s["rci"]):
        lo, hi   = s["expR"] - s["rci"], s["expR"] + s["rci"]
        excl     = "" if (lo > 0 or hi < 0) else "  (∋0)"
        interval = f"[{lo:+.3f}, {hi:+.3f}]{excl}"
    else:
        interval = "—"
    return (f"| {label} | {s['n']:,} | ${s['net']:,.0f} | {er} | {rci} | {interval} | {pf} | {s['wr']:.1f}% |")


def row_short(label: str, pnl: np.ndarray, risk: np.ndarray | None = None) -> str:
    """One-liner for the mode×target matrix: n, expR±CI only."""
    s = stats(pnl, risk)
    if s["n"] == 0:
        return f"| {label} | — |"
    er  = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    rci = "—" if np.isnan(s["rci"])  else f"±{s['rci']:.3f}"
    sig = "" if np.isnan(s["expR"]) or np.isnan(s["rci"]) else (
        " *" if abs(s["expR"]) > s["rci"] else ""
    )
    return f"{er}{rci}{sig} (n={s['n']:,})"


# ── filter mode masks ──────────────────────────────────────────────────────────
def mode_mask(name: str, f: pd.DataFrame) -> np.ndarray:
    """Boolean mask over filled signals for each filter mode."""
    isL = f["Direction"].str.upper().str.startswith("L").values
    k   = f["STO_K"].values
    zs  = f["STO_ZoneSignal"].values
    pct = f["DayPctRange"].values if "DayPctRange" in f.columns else np.full(len(f), np.nan)

    if name == "Off":
        return np.ones(len(f), bool)
    if name == "MeanRev":          # Long when OS, Short when OB
        return ((isL & (k <= OS_LEVEL)) | (~isL & (k >= OB_LEVEL)))
    if name == "Momentum":         # Long when OB, Short when OS
        return ((isL & (k >= OB_LEVEL)) | (~isL & (k <= OS_LEVEL)))
    if name == "ZoneSignal":       # ZS=-1=OS zone (pairs w/ Long reversal); ZS=+1=OB zone (pairs w/ Short)
        return ((isL & (zs == -1)) | (~isL & (zs == 1)))
    if name == "LocationEdge":     # Long in bottom 33% of day's range, Short in top 33%
        return ((isL & (pct <= 0.33)) | (~isL & (pct >= 0.67)))
    return np.ones(len(f), bool)


MODES = ["Off", "MeanRev", "Momentum", "ZoneSignal", "LocationEdge"]
MODE_LABELS = {
    "Off":          "Off (baseline)",
    "MeanRev":      "MeanRev (Long OS / Short OB)",
    "Momentum":     "Momentum (Long OB / Short OS)",
    "ZoneSignal":   "ZoneSignal (reversal bar flag)",
    "LocationEdge": "LocationEdge (Long near LOD / Short near HOD)",
}


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    log("parsing RevFT signals...")
    sig = parse_signals(_SIGNALS_TXT)
    log(f"  {len(sig)} signals  {sig['DateTime'].min():%Y-%m-%d} to {sig['DateTime'].max():%Y-%m-%d}")

    log("loading stochastic CSV...")
    stoch = load_stoch(_STOCH_CSV)
    log(f"  {len(stoch):,} bars  {stoch['DateTime'].min():%Y-%m-%d} -> {stoch['DateTime'].max():%Y-%m-%d}")

    sig = sig[sig["DateTime"] < DATE_CAP].reset_index(drop=True)
    log(f"  date-capped to {DATE_CAP}: {len(sig)} signals")

    log("joining stochastic features...")
    tagged = join_stoch(sig, stoch)

    log("loading bars & computing location features...")
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged = add_location_features(tagged, bars_by_date)

    log("loading ticks...")
    dates = sorted(tagged["DateTime"].dt.date.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}
    log(f"  tick data for {len(ticks_by_date)} / {len(dates)} dates")

    # ── simulate once per target ───────────────────────────────────────────────
    sim_results: dict[float, tuple] = {}
    for tr in TARGETS:
        log(f"simulating {tr}R...")
        res     = simulate_trades(
            signals=tagged, ticks_by_date=ticks_by_date,
            bars_by_date=bars_by_date, target_r=tr, **BASE,
        ).reset_index(drop=True)
        filled  = res["Filled"].values == True
        f       = tagged.loc[filled].reset_index(drop=True)
        rf      = res.loc[filled].reset_index(drop=True)
        pnl     = rf["NetPnL"].values
        risk    = rf["RiskDollar"].values if "RiskDollar" in rf.columns else None
        sim_results[tr] = (f, pnl, risk)

    md = [
        f"# RevFT x Stochastic study v2 — {datetime.now():%Y-%m-%d}  (2021–2023)\n",
        "**Signals:** 2021-2023 only (tick cache verified clean — 0/20 inverted Long stops)  \n"
        "**Stoch:** PeriodK=8 Smooth=1 PeriodD=1 (D==K; K/D-cross mode degenerate)  \n"
        "**Targets:** 0.5R / 1R / 1.5R / 2R / 3R  \n"
        "**`*`** = 95% CI excludes zero (statistically significant)  \n\n",
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # A. FILTER MODE × TARGET MATRIX
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("---\n\n# A. Filter Mode × Target (exp R ± CI)\n")
    md.append(
        "| Mode | 0.5R | 1R | 1.5R | 2R | 3R |\n"
        "|---|---|---|---|---|---|\n"
    )
    for mode in MODES:
        cols = [f"**{MODE_LABELS[mode]}**"]
        for tr in TARGETS:
            f, pnl, risk = sim_results[tr]
            m = mode_mask(mode, f)
            cols.append(row_short(mode, pnl[m], risk[m] if risk is not None else None))
        md.append("| " + " | ".join(cols) + " |")
    md.append("\n_\\* = CI excludes zero. LocationEdge = Long in bottom third of day's range / Short in top third._\n")

    # ═══════════════════════════════════════════════════════════════════════════
    # B. HOD/LOD LOCATION
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# B. HOD/LOD Location (where in day's range signal fires)\n")
    md.append("_DayPctRange: 0 = at session LOD so far, 1 = at session HOD so far. "
              "Favorable = Long near LOD (pct < 0.33) or Short near HOD (pct > 0.67)._\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL  = f["Direction"].str.upper().str.startswith("L").values
        pct  = f["DayPctRange"].values
        valid_pct = ~np.isnan(pct)
        md.append(f"\n## Location at {tr:.0f}R\n")
        md += [HDR, SEP]
        md.append(row("ALL signals", pnl, risk))
        md.append(row("  Long (all)", pnl[isL], risk[isL] if risk is not None else None))
        md.append(row("  Short (all)", pnl[~isL], risk[~isL] if risk is not None else None))
        md.append("")

        # Quartile breakdown × direction
        bins = [(0.00, 0.25, "Bottom Q (near LOD)"),
                (0.25, 0.50, "Lower mid"),
                (0.50, 0.75, "Upper mid"),
                (0.75, 1.01, "Top Q (near HOD)")]
        for lo, hi, label in bins:
            m = valid_pct & (pct >= lo) & (pct < hi)
            md.append(row(f"{label}",        pnl[m],          risk[m] if risk is not None else None))
            md.append(row(f"  {label} Long", pnl[m & isL],    risk[m & isL] if risk is not None else None))
            md.append(row(f"  {label} Short",pnl[m & ~isL],   risk[m & ~isL] if risk is not None else None))
        md.append("")

        # Favorable vs unfavorable location
        fav   = valid_pct & ((isL & (pct <= 0.33)) | (~isL & (pct >= 0.67)))
        unfav = valid_pct & ((isL & (pct >= 0.67)) | (~isL & (pct <= 0.33)))
        mid_loc = valid_pct & ~fav & ~unfav
        md.append(row("Favorable location (Long near LOD / Short near HOD)", pnl[fav],    risk[fav] if risk is not None else None))
        md.append(row("  Favorable Long",  pnl[fav & isL],   risk[fav & isL] if risk is not None else None))
        md.append(row("  Favorable Short", pnl[fav & ~isL],  risk[fav & ~isL] if risk is not None else None))
        md.append(row("Neutral location",  pnl[mid_loc],     risk[mid_loc] if risk is not None else None))
        md.append(row("Unfavorable location",pnl[unfav],     risk[unfav] if risk is not None else None))
        md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # C. TIME OF DAY
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# C. Time of Day\n")
    tod_order = ["Opening (08:35-09:30)", "Mid-morning (09:35-11:00)",
                 "Lunch (11:05-13:00)",   "Afternoon (13:05-15:15)"]

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL  = f["Direction"].str.upper().str.startswith("L").values
        tod  = f["TimeOfDay"].values
        md.append(f"\n## Time of Day at {tr:.0f}R\n")
        md += [HDR, SEP]
        for bucket in tod_order:
            m = tod == bucket
            md.append(row(bucket, pnl[m], risk[m] if risk is not None else None))
            md.append(row(f"  {bucket[:10]}... Long",  pnl[m & isL],  risk[m & isL] if risk is not None else None))
            md.append(row(f"  {bucket[:10]}... Short", pnl[m & ~isL], risk[m & ~isL] if risk is not None else None))
        md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # D. K SLOPE × DIRECTION
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# D. K Slope x Direction\n")
    md.append("_Key cross-cut: K slope (momentum) split within direction._\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL    = f["Direction"].str.upper().str.startswith("L").values
        up     = f["STO_KslopeUp"].values
        valid  = ~f["STO_K_lag1"].isna().values
        k      = f["STO_K"].values

        md.append(f"\n## K Slope x Direction at {tr:.0f}R\n")
        md += [HDR, SEP]
        for is_long, dir_label in [(True, "Long"), (False, "Short")]:
            dm = (isL if is_long else ~isL) & valid
            md.append(row(f"{dir_label} — K rising",  pnl[dm & up],  risk[dm & up] if risk is not None else None))
            md.append(row(f"{dir_label} — K falling", pnl[dm & ~up], risk[dm & ~up] if risk is not None else None))
            # Also OB/OS within slope
            for zone in ["OS", "mid", "OB"]:
                zm = dm & (f["STO_Zone"].values == zone)
                if zm.sum() >= 15:
                    md.append(row(f"  {dir_label} K-rising + {zone}",  pnl[zm & up],  risk[zm & up] if risk is not None else None))
                    md.append(row(f"  {dir_label} K-falling + {zone}", pnl[zm & ~up], risk[zm & ~up] if risk is not None else None))
        md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # E. YEAR × DIRECTION
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# E. Year x Direction\n")
    md.append("_2022 was a bear market — Longs and Shorts behave differently by year._\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL = f["Direction"].str.upper().str.startswith("L").values
        yr  = f["DateTime"].dt.year.values
        md.append(f"\n## Year x Direction at {tr:.0f}R\n")
        md += [HDR, SEP]
        for y in sorted(np.unique(yr)):
            my = yr == y
            md.append(row(f"{y} (all)",  pnl[my],          risk[my] if risk is not None else None))
            md.append(row(f"  {y} Long", pnl[my & isL],    risk[my & isL] if risk is not None else None))
            md.append(row(f"  {y} Short",pnl[my & ~isL],   risk[my & ~isL] if risk is not None else None))
        md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # F. LOCATION + ZONE COMBOS (key intersections)
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# F. Location + Zone Combinations\n")
    md.append("_Near-extreme location AND stoch zone alignment — the most selective filter._\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL  = f["Direction"].str.upper().str.startswith("L").values
        pct  = f["DayPctRange"].values
        k    = f["STO_K"].values
        zone = f["STO_Zone"].values
        valid_pct = ~np.isnan(pct)

        fav_L  = valid_pct & isL  & (pct <= 0.33)     # Long near LOD
        fav_S  = valid_pct & ~isL & (pct >= 0.67)     # Short near HOD
        unfav_L= valid_pct & isL  & (pct >= 0.67)     # Long near HOD (bad)
        unfav_S= valid_pct & ~isL & (pct <= 0.33)     # Short near LOD (bad)

        md.append(f"\n## Location + Zone at {tr:.0f}R\n")
        md += [HDR, SEP]

        # Favorable Longs (near LOD) by zone
        md.append(row("Favorable Long (near LOD) — all zones", pnl[fav_L], risk[fav_L] if risk is not None else None))
        for z in ["OS", "mid", "OB"]:
            m = fav_L & (zone == z)
            if m.sum() >= 10:
                md.append(row(f"  Fav Long + {z}", pnl[m], risk[m] if risk is not None else None))

        # Favorable Shorts (near HOD) by zone
        md.append(row("Favorable Short (near HOD) — all zones", pnl[fav_S], risk[fav_S] if risk is not None else None))
        for z in ["OS", "mid", "OB"]:
            m = fav_S & (zone == z)
            if m.sum() >= 10:
                md.append(row(f"  Fav Short + {z}", pnl[m], risk[m] if risk is not None else None))

        # Unfavorable (contra-location) for contrast
        md.append(row("Unfavorable Long (near HOD)", pnl[unfav_L], risk[unfav_L] if risk is not None else None))
        md.append(row("Unfavorable Short (near LOD)", pnl[unfav_S], risk[unfav_S] if risk is not None else None))
        md.append("")

        # Triple filter: favorable location + zone + K slope
        up   = f["STO_KslopeUp"].values
        valid_slope = ~f["STO_K_lag1"].isna().values
        md.append(row("Fav Long + K rising",           pnl[fav_L & up & valid_slope],
                      risk[fav_L & up & valid_slope] if risk is not None else None))
        md.append(row("Fav Long + OS + K rising",      pnl[fav_L & (zone=="OS") & up & valid_slope],
                      risk[fav_L & (zone=="OS") & up & valid_slope] if risk is not None else None))
        md.append(row("Fav Short + K falling",         pnl[fav_S & ~up & valid_slope],
                      risk[fav_S & ~up & valid_slope] if risk is not None else None))
        md.append(row("Fav Short + OB + K falling",    pnl[fav_S & (zone=="OB") & ~up & valid_slope],
                      risk[fav_S & (zone=="OB") & ~up & valid_slope] if risk is not None else None))
        md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # G. STANDARD STOCH CUTS (K bins, zone × dir, ZoneSignal)
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# G. Standard Stoch Cuts\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL  = f["Direction"].str.upper().str.startswith("L").values
        k    = f["STO_K"].values
        zone = f["STO_Zone"].values
        zs   = f["STO_ZoneSignal"].values
        has_k = ~np.isnan(k)

        pnl_k  = pnl[has_k];   risk_k = risk[has_k] if risk is not None else None
        f_k    = f[has_k].reset_index(drop=True)
        isL_k  = isL[has_k]; k_k = k[has_k]; zone_k = zone[has_k]; zs_k = zs[has_k]

        md.append(f"\n## G1. K bins at {tr:.0f}R\n")
        md += [HDR, SEP]
        md.append(row("BASELINE", pnl, risk))
        edges = list(range(0, 101, 10))
        labels_k = [f"{lo}-{lo+10}" for lo in edges[:-1]]
        k_bin = pd.cut(pd.Series(k_k), bins=edges, labels=labels_k, right=False, include_lowest=True)
        for lab in labels_k:
            m = (k_bin == lab).values
            md.append(row(f"  K={lab}", pnl_k[m], risk_k[m] if risk_k is not None else None))
        md.append("")

        md.append(f"\n## G2. Zone x Direction at {tr:.0f}R\n")
        md += [HDR, SEP]
        for z in ["OS", "mid", "OB"]:
            mz = zone_k == z
            md.append(row(f"Zone={z} (all)", pnl_k[mz], risk_k[mz] if risk_k is not None else None))
            md.append(row(f"  {z} Long",  pnl_k[mz & isL_k], risk_k[mz & isL_k] if risk_k is not None else None))
            md.append(row(f"  {z} Short", pnl_k[mz & ~isL_k], risk_k[mz & ~isL_k] if risk_k is not None else None))
        md.append("")

        md.append(f"\n## G3. ZoneSignal at {tr:.0f}R\n")
        md += [HDR, SEP]
        md.append(row("ZoneSignal=-1 Long (OS zone reversal)",  pnl_k[isL_k  & (zs_k==-1)], risk_k[isL_k  & (zs_k==-1)] if risk_k is not None else None))
        md.append(row("ZoneSignal=+1 Short (OB zone reversal)", pnl_k[~isL_k & (zs_k==1)],  risk_k[~isL_k & (zs_k==1)]  if risk_k is not None else None))
        md.append(row("ZoneSignal=0 (no flag)",                 pnl_k[zs_k==0],              risk_k[zs_k==0]              if risk_k is not None else None))
        md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # H. YEAR STABILITY FOR BEST COMBOS
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# H. Year Stability — Best Combos\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL  = f["Direction"].str.upper().str.startswith("L").values
        pct  = f["DayPctRange"].values
        k    = f["STO_K"].values
        zone = f["STO_Zone"].values
        up   = f["STO_KslopeUp"].values
        yr   = f["DateTime"].dt.year.values
        valid_pct   = ~np.isnan(pct)
        valid_slope = ~f["STO_K_lag1"].isna().values

        fav_L = valid_pct & isL  & (pct <= 0.33)
        fav_S = valid_pct & ~isL & (pct >= 0.67)

        md.append(f"\n## H. Year stability at {tr:.0f}R\n")
        combos = [
            ("Fav Long (near LOD)",          fav_L),
            ("Fav Short (near HOD)",         fav_S),
            ("MeanRev (Long OS / Short OB)", mode_mask("MeanRev", f)),
            ("Momentum (Long OB / Short OS)",mode_mask("Momentum", f)),
        ]
        for label, mask in combos:
            md += [f"\n### {label}\n", HDR, SEP]
            for y in sorted(np.unique(yr)):
                my = mask & (yr == y)
                if my.sum() >= 5:
                    md.append(row(str(y), pnl[my], risk[my] if risk is not None else None))
            md.append("")

    # ═══════════════════════════════════════════════════════════════════════════
    # I. SIGNAL TYPE BREAKDOWN (Trap / Sneaky / IB / OB / BO)
    # ═══════════════════════════════════════════════════════════════════════════
    md.append("\n---\n\n# I. Signal Type Breakdown\n")
    md.append("_Each signal type × direction, with ZoneSignal sub-cut (corrected polarity)._\n")

    for tr in [1.0, 2.0]:
        f, pnl, risk = sim_results[tr]
        isL  = f["Direction"].str.upper().str.startswith("L").values
        zs   = f["STO_ZoneSignal"].values
        stype = f["SignalType"].values

        md.append(f"\n## I. Signal Types at {tr:.0f}R\n")
        md += [HDR, SEP]
        md.append(row("ALL", pnl, risk))

        for st in ["Trap", "Sneaky", "IB", "OB", "BO"]:
            ms = stype == st
            if ms.sum() < 5:
                continue
            md.append(row(f"{st} (all)", pnl[ms], risk[ms] if risk is not None else None))
            # Direction split
            for is_long, dl in [(True, "Long"), (False, "Short")]:
                dm = ms & (isL if is_long else ~isL)
                if dm.sum() < 5:
                    continue
                md.append(row(f"  {st} {dl}", pnl[dm], risk[dm] if risk is not None else None))
                # ZoneSignal sub-cut (correct polarity: Long=ZS-1, Short=ZS+1)
                zs_match = (zs == -1) if is_long else (zs == 1)
                zm = dm & zs_match
                if zm.sum() >= 5:
                    md.append(row(f"    {st} {dl} + ZoneSignal", pnl[zm], risk[zm] if risk is not None else None))
        md.append("")

    md.append("\n---\n\n# Notes\n")
    md.append(
        "- In-sample 2021-2023 only; all findings are hypotheses.\n"
        "- PeriodD=1: D==K always; K/D cross is degenerate until re-exported with PeriodD>=3.\n"
        "- LocationEdge / DayPctRange uses bars up to and including the signal bar.\n"
        "- `*` in matrix = 95% CI excludes zero.\n"
        "- Roll sensitivity: ~8 bars around each roll may have spurious K spikes.\n"
    )

    out = _OUT / f"revft_stoch_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
