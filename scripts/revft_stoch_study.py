"""revft_stoch_study.py — winners-vs-losers discovery: RevFT signals vs Stochastic %K/%D.

Source files:
  • RevFT signals  : MyReversals Signal Export txt (DD/MM/YYYY, tab-delimited, comma prices)
  • Stochastic CSV : ES_stoch.csv  (K/D from MyStochasticExporter, PeriodK=8, Smooth=1,
                      PeriodD=1 -> D == K every bar; K/D-cross mode is degenerate)

Join method: causal as-of join (searchsorted right-1) — same math as
  `merge_stoch_overlay()` in bar_analysis.py.  STO_K_next is look-ahead / diagnostic only.

Analysis cuts:
  • STO_K binned in 10-point bands (0-10, 10-20, … 90-100)
  • STO_Zone  (OS < 20 / mid / OB > 80)  × Direction
  • STO_KoverD  (K > D at signal bar)      — degenerate when PeriodD=1, shown for future use
  • STO_KslopeUp  (K rising over last bar)
  • Lead-in slope  (K − K_lag3, quintile split)
  • ZoneSignal hit-rate
  • Signal type  (Sneaky / Trap / IB / OB / BO)  × STO_Zone
  • Year-by-year stability on best zone cuts

Run (MAIN venv):
  c:/Users/Admin/myquant/.venv/Scripts/python.exe scripts/revft_stoch_study.py

Out: docs/living/revft_stoch_study_<date>.md
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_MAIN = Path("c:/Users/Admin/myquant")
sys.path.insert(0, str(_ROOT))

import massive                                                        # noqa: E402
massive._TICKS_CONT_DIR = _MAIN / "data" / "ticks_continuous"         # noqa: E402
from simulation_engine import simulate_trades                         # noqa: E402

# ── paths ──────────────────────────────────────────────────────────────────────
_SIGNALS_TXT = Path(
    r"C:\Users\Admin\Desktop"
    r"\MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_STOCH_CSV = Path(
    r"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\Stoch\ES_stoch.csv"
)
_BARS      = _MAIN / "data" / "bars" / "_continuous.parquet"
_OUT       = _ROOT / "docs" / "living"

OS_LEVEL = 20.0
OB_LEVEL = 80.0

BASE = dict(
    entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
    contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
    ratchet_r=0.0, pb_round="nearest",
    multileg=False, threeleg=False, overrides=None,
)
TARGETS = [1.0, 2.0, 3.0]


def log(m: str) -> None:
    print(f"[stoch_study] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── parse RevFT signals text file ─────────────────────────────────────────────
def parse_signals(path: Path) -> pd.DataFrame:
    """Parse the MyReversals Signal Export text file.

    Format (after 2-line header):
        N  SignalType  Direction  DD/MM/YYYY HH:MM:SS  BarNum  Price  StopPx
    Fields are separated by whitespace / tabs; prices may have comma thousands separators.
    """
    rows = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.rstrip()
            if not line or line.startswith("-") or not line[0].isdigit():
                continue
            # Remove commas inside numbers (thousands separators)
            line = re.sub(r"(\d),(\d)", r"\1\2", line)
            parts = line.split()
            if len(parts) < 8:
                continue
            # parts: [N, Type, Dir, DD/MM/YYYY, HH:MM:SS, BarNum, SignalPx, StopPx]
            try:
                sig_num  = int(parts[0])
                sig_type = parts[1]
                direction = parts[2]
                dt_str   = f"{parts[3]} {parts[4]}"
                dt       = datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
                bar_num  = int(parts[5])
                sig_px   = float(parts[6])
                stop_px  = float(parts[7])
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


# ── load stochastic CSV ────────────────────────────────────────────────────────
def load_stoch(path: Path) -> pd.DataFrame:
    stoch = pd.read_csv(path, parse_dates=["DateTime"])
    stoch = stoch.sort_values("DateTime").reset_index(drop=True)
    return stoch


# ── as-of join (look-ahead-safe) ───────────────────────────────────────────────
def join_stoch(signals: pd.DataFrame, stoch: pd.DataFrame) -> pd.DataFrame:
    """Attach the stochastic reading active at each signal bar (bar T, not T+1)."""
    sto_dt  = stoch["DateTime"].values.astype("datetime64[ns]")
    sig_dt  = signals["DateTime"].values.astype("datetime64[ns]")

    # idx[i] = last stoch bar index whose DateTime <= signal DateTime
    # (side="right" gives first index > sig_dt, minus 1 = last index <= sig_dt)
    idx     = np.searchsorted(sto_dt, sig_dt, side="right") - 1
    valid   = idx >= 0

    k_arr   = stoch["K"].values
    d_arr   = stoch["D"].values
    ks_arr  = stoch["KSignalUp"].values.astype(float)
    kd_arr  = stoch["KSignalDn"].values.astype(float)
    zs_arr  = stoch["ZoneSignal"].values.astype(float)

    n = len(signals)
    sto_k      = np.where(valid, k_arr[np.clip(idx, 0, len(k_arr)-1)], np.nan)
    sto_d      = np.where(valid, d_arr[np.clip(idx, 0, len(d_arr)-1)], np.nan)
    sto_ksup   = np.where(valid, ks_arr[np.clip(idx, 0, len(ks_arr)-1)], np.nan)
    sto_ksdwn  = np.where(valid, kd_arr[np.clip(idx, 0, len(kd_arr)-1)], np.nan)
    sto_zs     = np.where(valid, zs_arr[np.clip(idx, 0, len(zs_arr)-1)], np.nan)

    def lag(arr, shift):
        lagged_idx = np.clip(idx - shift, 0, len(arr)-1)
        return np.where(valid & (idx - shift >= 0), arr[lagged_idx], np.nan)

    def lead(arr, shift):
        ahead_idx = np.clip(idx + shift, 0, len(arr)-1)
        return np.where(valid & (idx + shift < len(arr)), arr[ahead_idx], np.nan)

    out = signals.copy()
    out["STO_K"]        = sto_k
    out["STO_D"]        = sto_d
    out["STO_KSignalUp"] = sto_ksup
    out["STO_KSignalDn"] = sto_ksdwn
    out["STO_ZoneSignal"]= sto_zs
    out["STO_K_lag1"]   = lag(k_arr, 1)
    out["STO_K_lag2"]   = lag(k_arr, 2)
    out["STO_K_lag3"]   = lag(k_arr, 3)
    out["STO_D_lag1"]   = lag(d_arr, 1)
    out["STO_D_lag2"]   = lag(d_arr, 2)
    out["STO_D_lag3"]   = lag(d_arr, 3)
    out["STO_K_next"]   = lead(k_arr, 1)   # (!) LOOK-AHEAD — diagnostic only

    # derived features
    out["STO_Zone"]     = pd.cut(
        out["STO_K"], bins=[-0.001, OS_LEVEL, OB_LEVEL, 100.001],
        labels=["OS", "mid", "OB"], right=True,
    ).astype(str)
    out["STO_KoverD"]   = out["STO_K"] > out["STO_D"]   # degenerate when D==K
    out["STO_KslopeUp"] = out["STO_K"] > out["STO_K_lag1"]
    out["STO_lead_in"]  = out["STO_K"] - out["STO_K_lag3"]  # 3-bar lead-in slope
    return out


# ── stats helper ──────────────────────────────────────────────────────────────
def stats(pnl: np.ndarray, risk: np.ndarray | None = None) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan, rci=np.nan)
    net  = float(pnl.sum())
    gw   = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl   = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf   = gw / gl if gl > 0 else float("inf")
    wr   = float((pnl > 0).sum() / n * 100)
    exp  = net / n
    ci   = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    if risk is not None:
        rmult = pnl / risk
        rr    = rmult[np.isfinite(rmult)]
        expR  = float(rr.mean()) if len(rr) else np.nan
        rci   = float(1.96 * rr.std(ddof=1) / np.sqrt(len(rr))) if len(rr) > 1 else np.nan
    else:
        expR = rci = np.nan
    return dict(n=n, net=net, exp=exp, pf=pf, wr=wr, expR=expR, ci=ci, rci=rci)


HDR = "| group | n | net $ | exp $/trade | exp R | ±R CI | R 95% interval | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|---|"


def row(label: str, pnl: np.ndarray, risk: np.ndarray | None = None) -> str:
    s = stats(pnl, risk)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — | — |"
    pf  = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    er  = "—" if np.isnan(s["expR"])  else f"{s['expR']:+.3f}"
    rci = "—" if np.isnan(s["rci"])   else f"±{s['rci']:.3f}"
    if not np.isnan(s["expR"]) and not np.isnan(s["rci"]):
        lo, hi    = s["expR"] - s["rci"], s["expR"] + s["rci"]
        excl      = "" if (lo > 0 or hi < 0) else "  (∋0)"
        interval  = f"[{lo:+.3f}, {hi:+.3f}]{excl}"
    else:
        interval  = "—"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | "
            f"{er} | {rci} | {interval} | {pf} | {s['wr']:.1f}% |")


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    log("parsing RevFT signals...")
    sig = parse_signals(_SIGNALS_TXT)
    log(f"  {len(sig)} signals  {sig['DateTime'].min():%Y-%m-%d} to {sig['DateTime'].max():%Y-%m-%d}")

    log("loading stochastic CSV...")
    stoch = load_stoch(_STOCH_CSV)
    log(f"  {len(stoch):,} bars  {stoch['DateTime'].min():%Y-%m-%d} -> {stoch['DateTime'].max():%Y-%m-%d}")
    log(f"  (!)  PeriodD=1 -> D==K in every row; STO_KoverD will be always-False (degenerate)")

    log("joining stochastic features (as-of, look-ahead-safe)...")
    tagged = join_stoch(sig, stoch)
    na_k   = tagged["STO_K"].isna().sum()
    if na_k:
        log(f"  {na_k} signals have no prior stoch bar (before stoch series start) — excluded from analysis")

    log("loading bars...")
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    log("loading ticks...")
    dates = sorted(tagged["DateTime"].dt.date.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}
    log(f"  tick data for {len(ticks_by_date)} / {len(dates)} dates")

    md = [
        f"# RevFT × Stochastic discovery study ({datetime.now():%Y-%m-%d})\n",
        "**Source:** `MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt`  \n"
        "**Stochastic:** `ES_stoch.csv`  PeriodK=8, Smooth=1, PeriodD=**1**  \n"
        "**Join:** causal as-of (bar T, not T+1) — `searchsorted(side='right') - 1`  \n"
        "**(!) PeriodD=1:** D == K in every row. K/D-cross rows are all False and should be ignored "
        "until re-exported with PeriodD=3.  \n"
        "**STO_K_next** is look-ahead (bar T+1) — diagnostic/ceiling only, not tradeable.  \n"
        f"Signals: {len(sig):,}   OS < {OS_LEVEL:.0f} / OB > {OB_LEVEL:.0f}  \n",
    ]

    results_by_target: dict = {}

    for tr in TARGETS:
        log(f"simulating at {tr:.0f}R...")
        res = simulate_trades(
            signals=tagged, ticks_by_date=ticks_by_date,
            bars_by_date=bars_by_date, target_r=tr, **BASE,
        ).reset_index(drop=True)

        filled  = res["Filled"].values == True
        f       = tagged.loc[filled].reset_index(drop=True)
        rf      = res.loc[filled].reset_index(drop=True)
        pnl     = rf["NetPnL"].values
        risk    = rf["RiskDollar"].values if "RiskDollar" in rf.columns else None
        isL     = f["Direction"].str.lower().str.startswith("l").values

        results_by_target[tr] = (f, pnl, risk, isL)
        has_stoch = f["STO_K"].notna().values
        pnl_s     = pnl[has_stoch]
        risk_s    = risk[has_stoch] if risk is not None else None
        f_s       = f[has_stoch].reset_index(drop=True)
        isL_s     = isL[has_stoch]

        md.append(f"\n---\n\n# Target {tr:.0f}R  (filled={filled.sum():,}, with-stoch={has_stoch.sum():,})\n")

        # ── 1. K-level bins ────────────────────────────────────────────────────
        md.append("\n## 1. STO_K level (10-point bins)\n")
        md += [HDR, SEP]
        md.append(row("BASELINE (all filled)", pnl, risk))
        md.append(row("with-stoch (baseline)", pnl_s, risk_s))
        edges = list(range(0, 101, 10))
        labels_k = [f"{lo}-{lo+10}" for lo in edges[:-1]]
        k_bin = pd.cut(f_s["STO_K"], bins=edges, labels=labels_k, right=False, include_lowest=True)
        for lab in labels_k:
            m = (k_bin == lab).values
            md.append(row(f"  K={lab}", pnl_s[m], risk_s[m] if risk_s is not None else None))
        md.append("")

        # ── 2. Zone × Direction ───────────────────────────────────────────────
        md.append("\n## 2. STO_Zone × Direction\n")
        md += [HDR, SEP]
        for zone in ["OS", "mid", "OB"]:
            mz = (f_s["STO_Zone"] == zone).values
            md.append(row(f"Zone={zone} (all)", pnl_s[mz], risk_s[mz] if risk_s is not None else None))
            mzL = mz & isL_s
            mzS = mz & ~isL_s
            md.append(row(f"  {zone} Long",  pnl_s[mzL], risk_s[mzL] if risk_s is not None else None))
            md.append(row(f"  {zone} Short", pnl_s[mzS], risk_s[mzS] if risk_s is not None else None))
        md.append("")

        # ── 3. K slope (KslopeUp) ─────────────────────────────────────────────
        md.append("\n## 3. K slope (rising vs falling)\n")
        md += [HDR, SEP]
        slope_up = f_s["STO_KslopeUp"].values
        valid_slope = ~f_s["STO_K_lag1"].isna().values
        md.append(row("K rising  (K > K_lag1)", pnl_s[slope_up & valid_slope],
                       risk_s[slope_up & valid_slope] if risk_s is not None else None))
        md.append(row("K falling (K <= K_lag1)", pnl_s[~slope_up & valid_slope],
                       risk_s[~slope_up & valid_slope] if risk_s is not None else None))
        md.append("")

        # ── 4. Lead-in slope quintiles (K - K_lag3) ───────────────────────────
        md.append("\n## 4. Lead-in slope quintiles (K - K_lag3, 3-bar momentum)\n")
        valid_li = ~f_s["STO_K_lag3"].isna().values
        lead_in  = f_s["STO_lead_in"].values
        if valid_li.sum() > 5:
            li_ser   = pd.Series(lead_in, dtype=float)
            qcuts_s  = pd.qcut(li_ser.where(pd.Series(valid_li)), q=5, duplicates="drop")
            cats     = qcuts_s.cat.categories
            bins     = [-np.inf] + [c.right for c in cats]
            bins[-1] = np.inf
            cut_all  = pd.cut(li_ser, bins=bins, labels=[f"[{c.left:+.1f},{c.right:+.1f}]" for c in cats],
                               include_lowest=True, duplicates="drop")
            md += [HDR, SEP]
            for lab in cut_all.cat.categories:
                m_li = valid_li & (cut_all == lab).values
                md.append(row(f"lead_in {lab}", pnl_s[m_li],
                               risk_s[m_li] if risk_s is not None else None))
        else:
            md.append("_No valid lag-3 data._")
        md.append("")

        # ── 5. ZoneSignal hit-rate ─────────────────────────────────────────────
        md.append("\n## 5. ZoneSignal from exporter (signal bar)\n")
        md += [HDR, SEP]
        zs = f_s["STO_ZoneSignal"].values
        md.append(row("ZoneSignal = 1 (bar)", pnl_s[zs == 1], risk_s[zs == 1] if risk_s is not None else None))
        md.append(row("ZoneSignal = 0",       pnl_s[zs == 0], risk_s[zs == 0] if risk_s is not None else None))
        md.append("")

        # ── 6. Signal type × Zone ─────────────────────────────────────────────
        md.append("\n## 6. Signal type × STO_Zone\n")
        md += [HDR, SEP]
        for stype in ["Sneaky", "Trap", "IB", "OB", "BO"]:
            mt = (f_s["SignalType"] == stype).values
            if mt.sum() == 0:
                continue
            md.append(row(f"{stype} (all zones)", pnl_s[mt], risk_s[mt] if risk_s is not None else None))
            for zone in ["OS", "mid", "OB"]:
                mtz = mt & (f_s["STO_Zone"] == zone).values
                if mtz.sum() >= 10:
                    md.append(row(f"  {stype} + {zone}", pnl_s[mtz],
                                   risk_s[mtz] if risk_s is not None else None))
        md.append("")

        # ── 7. STO_K_next diagnostic (look-ahead ceiling) ─────────────────────
        md.append("\n## 7. STO_K_next direction ((!) look-ahead — ceiling only)\n")
        md += [HDR, SEP]
        kn       = f_s["STO_K_next"].values
        kc       = f_s["STO_K"].values
        valid_kn = ~np.isnan(kn)
        k_next_up = valid_kn & (kn > kc)
        k_next_dn = valid_kn & (kn < kc)
        md.append(row("K_next > K (rising next bar)", pnl_s[k_next_up],
                       risk_s[k_next_up] if risk_s is not None else None))
        md.append(row("K_next < K (falling next bar)", pnl_s[k_next_dn],
                       risk_s[k_next_dn] if risk_s is not None else None))
        md.append(f"\n_If the next-bar split is strong, there is a tradeable K-slope signal — "
                   f"verify with STO_KslopeUp (causal, section 3) to confirm._\n")

    # ── year-by-year for best zone cuts ───────────────────────────────────────
    md.append("\n---\n\n# Year-by-year stability — STO_Zone × Direction\n")
    md.append("_Best zone filter applied at each target; each year must hold up independently._\n")
    for tr in TARGETS:
        f, pnl, risk, isL = results_by_target[tr]
        has_stoch = f["STO_K"].notna().values
        f_s   = f[has_stoch].reset_index(drop=True)
        pnl_s = pnl[has_stoch]
        risk_s = risk[has_stoch] if risk is not None else None
        isL_s = isL[has_stoch]
        yr    = f_s["DateTime"].dt.year.values

        md.append(f"\n### {tr:.0f}R — year-by-year\n")
        for zone in ["OS", "mid", "OB"]:
            mz = (f_s["STO_Zone"] == zone).values
            md.append(f"\n#### Zone={zone}\n")
            md += [HDR, SEP]
            for y in sorted(np.unique(yr)):
                my = mz & (yr == y)
                if my.sum() >= 5:
                    md.append(row(str(y), pnl_s[my], risk_s[my] if risk_s is not None else None))
            md.append("")

    # ── meta / caveats ─────────────────────────────────────────────────────────
    md.append("\n---\n\n# Methodology notes\n")
    md.append(
        "- **In-sample:** all analysis uses the same 5yr set — findings are hypotheses, not out-of-sample results.\n"
        "- **PeriodD=1:** D ≡ K; K/D-cross features are degenerate. Re-export stoch with PeriodD=3 for a real signal line.\n"
        "- **Minimum threshold for a 'finding':** R 95%-interval must exclude zero AND hold year-by-year.\n"
        "- **STO_K_next** is shown as a ceiling for what a future-informed K-slope could achieve.\n"
        "- **Roll sensitivity:** ~PeriodK bars (8 bars = 40 min) around each roll may have a spurious K spike "
        "due to price discontinuity from Panama back-adjustment. Estimated <1% of all bars affected.\n"
    )

    out = _OUT / f"revft_stoch_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
