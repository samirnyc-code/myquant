"""MenthorQ edge study — S54 (July 4, 2026).

Stage 0: price-space alignment (continuous vs front contract) + causality checks
Stage 1: level validity — touch/bounce/break vs matched control levels (82 days)
Stage 2: pre-registered trade-level tests on the Stack v2 subset (frozen exec)

PRE-REGISTERED TESTS (declared before outcomes were seen):
  T1 headwind/tailwind: opposing major level (Call Res / Gamma Wall 0DTE)
     between entry and 3R target; + ABR-scaled distance tertiles
  T2 gamma regime: gamma_condition Negative vs Positive; HVL-side variant
  T3 scores: volatility_score {<=1, 2-3, >=4}, momentum/option/seasonality coarse
  T4 daily scalars: net GEX sign, IV30 tertiles, exp-move tertiles
  T5 user combo: high-vol (>=3) AND negative gamma vs rest (2x2 shown)

Fixed a-priori Stage-1 params: horizon 6 bars (30 min), bounce/break threshold
3.0 pts, re-touch reset 5 pts, controls seeded RNG(42), 3x oversample.
"""
from __future__ import annotations

import os
import sys
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import massive                                              # noqa: E402
massive._TICKS_CONT_DIR = ROOT / "data" / "ticks_continuous"
from simulation_engine import simulate_trades               # noqa: E402
from stack_filter import compute_stack_columns, _abr20      # noqa: E402

# External NT8 export — not committed to the repo. Override with MC_SIGNAL_TXT,
# else drop the file under data/signals/ with the default name below.
SIG_TXT = Path(os.environ.get(
    "MC_SIGNAL_TXT",
    ROOT / "data" / "signals" /
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"))
MQ_CSV  = ROOT / "data" / "menthorq" / "menthorq_levels.csv"
BARS_PQ = ROOT / "data" / "bars" / "_continuous.parquet"
OUT_MD  = ROOT / "docs" / "living" / "menthorq_edge_study_20260704_tables.md"
SIM_PQ  = ROOT / "data" / "menthorq" / "_study_sim_results.parquet"

WIN_START = pd.Timestamp("2026-03-06")
WIN_END   = pd.Timestamp("2026-07-02")

H_BARS   = 6      # stage-1 outcome horizon (bars)
THRESH   = 3.0    # pts: bounce / break threshold
RETOUCH  = 5.0    # pts: price must leave by this much before a new touch counts
RNG      = np.random.default_rng(42)

CONTRACT_FILE = {"ESH2026": "ESH6", "ESM2026": "ESM6", "ESU2026": "ESU6"}

L = []  # markdown lines
def emit(s=""):
    print(s, flush=True)
    L.append(s)


def log(m):
    print(f"[mq] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── loaders ──────────────────────────────────────────────────────────────────

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
                rows.append(dict(
                    SignalNum=int(parts[0]), SignalType=parts[1], Direction=parts[2],
                    DateTime=datetime.strptime(f"{parts[3]} {parts[4]}", "%d/%m/%Y %H:%M:%S"),
                    BarNum=int(parts[5]), SignalPrice=float(parts[6]), StopPrice=float(parts[7]),
                ))
            except (ValueError, IndexError):
                continue
    df = pd.DataFrame(rows)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df["Date"] = df["DateTime"].dt.date
    return df.sort_values("DateTime").reset_index(drop=True)


def load_mq() -> pd.DataFrame:
    df = pd.read_csv(MQ_CSV, parse_dates=["date"])
    for c in df.columns:
        if c in ("date", "contract", "gamma_condition"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            s = (df[c].astype(str).str.replace("%", "", regex=False)
                 .str.replace("M", "e6").str.replace("B", "e9"))
            df[c] = pd.to_numeric(s, errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)
    # Row d is generated at EOD of day d (verified: 1d-band centered on close(d),
    # distance_to_hvl uses close(d)); its tradeable session is the NEXT day.
    # MQ_APPLY_NEXT_DAY=1 re-dates each row to the next trading day (correct,
    # causal join). Unset = as-archived same-day join (lookahead for levels).
    import os
    if os.environ.get("MQ_APPLY_NEXT_DAY") == "1":
        df["date"] = df["date"].shift(-1)
        df = df.dropna(subset=["date"]).reset_index(drop=True)
    return df


# ── stage 0 ──────────────────────────────────────────────────────────────────

def stage0(mq: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    emit("## Stage 0 — alignment & causality checks\n")
    day = bars["DateTime"].dt.normalize()
    cont_by_day = bars.groupby(day).agg(
        c_high=("High", "max"), c_low=("Low", "min"),
        c_open=("Open", "first"), c_close=("Close", "last"))

    # per-day offset continuous - front contract, from per-contract bar files
    offsets, rows = {}, []
    cache = {}
    for _, r in mq.iterrows():
        d = r["date"]
        code = CONTRACT_FILE.get(str(r["contract"]))
        if code is None:
            continue
        if code not in cache:
            p = ROOT / "data" / "bars" / f"{code}.parquet"
            cache[code] = pd.read_parquet(p) if p.exists() else None
        cb = cache[code]
        if cb is None:
            continue
        dt_col = "DateTime" if "DateTime" in cb.columns else cb.columns[0]
        cd = cb[cb[dt_col].dt.normalize() == d]
        bd = bars[day == d]
        if cd.empty or bd.empty:
            continue
        m = bd.merge(cd[[dt_col, "Close"]].rename(columns={dt_col: "DateTime", "Close": "ct_close"}),
                     on="DateTime", how="inner")
        if m.empty:
            continue
        off = float((m["Close"] - m["ct_close"]).median())
        offsets[d] = off
        rows.append(dict(date=d, contract=code, offset=off,
                         ct_high=cd["High"].max(), ct_low=cd["Low"].min(),
                         ct_close=cd["Close"].iloc[-1]))
    odf = pd.DataFrame(rows).set_index("date")
    emit(f"- Offset (continuous − contract), per contract period: "
         + ", ".join(f"{c}: median {g['offset'].median():+.2f} (spread {g['offset'].max()-g['offset'].min():.2f}, n={len(g)})"
                     for c, g in odf.groupby("contract")))

    # 1d_max / 1d_min semantics: same-day realized vs prior-day vs expected band
    chk = mq.set_index("date").join(odf.rename(columns={"contract": "ct_code"}), how="inner")
    same_hi = (chk["ct_high"] - chk["1d_max"]).abs().median()
    same_lo = (chk["ct_low"] - chk["1d_min"]).abs().median()
    prior_hi = (chk["ct_high"].shift(1) - chk["1d_max"]).abs().median()
    band = (chk["1d_max"] - chk["1d_min"])
    exp_band = 2 * chk["exp_move_1d_pct"] / 100.0 * chk["ct_close"].shift(1)
    emit(f"- `1d_max/min` vs SAME-day realized H/L: median |diff| {same_hi:.2f} / {same_lo:.2f} pts; "
         f"vs PRIOR-day high: {prior_hi:.2f} pts; band width vs 2x expected move: "
         f"median ratio {(band/exp_band).median():.2f}")
    inside = ((chk["ct_high"] <= chk["1d_max"]) & (chk["ct_low"] >= chk["1d_min"])).mean()
    emit(f"- Day's realized range fully inside [1d_min, 1d_max]: {inside*100:.0f}% of days "
         f"(expected-move band ⇒ ~70-85%; realized copy ⇒ 100% with 0 diff)")

    # distance_to_hvl basis: prior close vs same-day close
    d_prior = ((chk["ct_close"].shift(1) - chk["high_vol_level"]).abs()
               / chk["ct_close"].shift(1) * 100)
    d_same = ((chk["ct_close"] - chk["high_vol_level"]).abs() / chk["ct_close"] * 100)
    e_prior = (d_prior - chk["distance_to_hvl_%"]).abs().median()
    e_same = (d_same - chk["distance_to_hvl_%"]).abs().median()
    emit(f"- `distance_to_hvl_%` matches PRIOR close (median err {e_prior:.3f}pp) vs "
         f"SAME-day close ({e_same:.3f}pp) → snapshot basis = "
         f"{'prior close (causal)' if e_prior < e_same else 'SAME-DAY close (EOD/lookahead!)'}")
    emit("")
    return odf


# ── stage 1 ──────────────────────────────────────────────────────────────────

KEY_COLS = ["call_resistance", "call_resistance_0dte", "put_support",
            "put_support_0dte", "high_vol_level", "hvl_0dte", "gamma_wall_0dte"]
GEX_COLS = [f"gex_{i}" for i in range(1, 11)]
BL_COLS = [f"bl_{i}" for i in range(1, 11)]


def touches_for_levels(day_bars: pd.DataFrame, levels: list[float]) -> list[dict]:
    hi = day_bars["High"].to_numpy(); lo = day_bars["Low"].to_numpy()
    cl = day_bars["Close"].to_numpy()
    out = []
    for lev in levels:
        armed, prev_close = True, None
        for i in range(len(day_bars)):
            if prev_close is not None and armed and lo[i] <= lev <= hi[i]:
                appr = 1.0 if prev_close < lev else -1.0  # +1 approaching from below
                j = min(i + H_BARS, len(day_bars) - 1)
                if j > i:
                    fh = hi[i + 1:j + 1].max(); fl = lo[i + 1:j + 1].min()
                    pen = (fh - lev) if appr > 0 else (lev - fl)      # continue thru
                    bnc = (lev - fl) if appr > 0 else (fh - lev)      # reject
                    drift = (cl[j] - lev) * appr
                    out.append(dict(level=lev, bounce=bnc >= THRESH and pen < THRESH,
                                    breakthru=pen >= THRESH, drift=drift))
                armed = False
            if not armed and abs(cl[i] - lev) > RETOUCH:
                armed = True
            prev_close = cl[i]
    return out


def stage1(mq: pd.DataFrame, bars: pd.DataFrame, odf: pd.DataFrame):
    emit("## Stage 1 — do MenthorQ levels act as S/R? (touch outcomes vs controls)\n")
    emit(f"Params (fixed a priori): horizon {H_BARS} bars, threshold {THRESH} pts, "
         f"re-touch reset {RETOUCH} pts. Controls: GEX/strike-type → other 25-pt strikes "
         "in range; continuous-type → uniform random prices in day range (3x, seed 42), "
         "both excluding ±5 pts of any real level.\n")
    day = bars["DateTime"].dt.normalize()
    groups = {"KEY (CallRes/PutSup/HVL/GW)": KEY_COLS, "GEX strikes": GEX_COLS,
              "BL (blind spots)": BL_COLS}
    res = {g: {"real": [], "ctrl": []} for g in groups}
    for _, r in mq.iterrows():
        d = r["date"]
        if d not in odf.index:
            continue
        off = odf.loc[d, "offset"]
        db = bars[day == d].reset_index(drop=True)
        if len(db) < 20:
            continue
        dlo, dhi = db["Low"].min(), db["High"].max()
        all_real = [r[c] + off for cols in groups.values() for c in cols
                    if pd.notna(r.get(c))]
        for gname, cols in groups.items():
            levs = [r[c] + off for c in cols if pd.notna(r.get(c))]
            levs = [l for l in levs if dlo - 15 <= l <= dhi + 15]
            if not levs:
                continue
            res[gname]["real"] += touches_for_levels(db, levs)
            if "GEX" in gname:
                grid = np.arange(np.floor((dlo - 15) / 25) * 25, dhi + 15 + 25, 25) + (off % 25)
                cand = [g for g in grid if all(abs(g - rl) >= 5 for rl in all_real)]
                ctrl = list(RNG.choice(cand, size=min(len(cand), 3 * len(levs)),
                                       replace=False)) if cand else []
            else:
                ctrl, tries = [], 0
                while len(ctrl) < 3 * len(levs) and tries < 200:
                    x = RNG.uniform(dlo, dhi)
                    tries += 1
                    if all(abs(x - rl) >= 5 for rl in all_real):
                        ctrl.append(x)
            res[gname]["ctrl"] += touches_for_levels(db, ctrl)

    emit("| level group | touches | bounce% | break% | drift (pts) | ctrl n | ctrl bounce% | ctrl break% | ctrl drift |")
    emit("|---|---|---|---|---|---|---|---|---|")
    for gname in groups:
        rr, cc = pd.DataFrame(res[gname]["real"]), pd.DataFrame(res[gname]["ctrl"])
        if rr.empty or cc.empty:
            emit(f"| {gname} | insufficient |")
            continue
        # bootstrap CI on bounce-rate difference
        diffs = [rr["bounce"].sample(len(rr), replace=True).mean()
                 - cc["bounce"].sample(len(cc), replace=True).mean() for _ in range(1000)]
        lo_, hi_ = np.percentile(diffs, [2.5, 97.5])
        sig = " **⇐**" if lo_ > 0 or hi_ < 0 else ""
        emit(f"| {gname} | {len(rr)} | {rr['bounce'].mean()*100:.1f}% | {rr['breakthru'].mean()*100:.1f}% "
             f"| {rr['drift'].mean():+.2f} | {len(cc)} | {cc['bounce'].mean()*100:.1f}% "
             f"| {cc['breakthru'].mean()*100:.1f}% | {cc['drift'].mean():+.2f} |")
        emit(f"| ↳ bounce-rate diff 95% CI | [{lo_*100:+.1f}pp, {hi_*100:+.1f}pp]{sig} | | | | | | | |")
    emit("")


# ── stage 2 ──────────────────────────────────────────────────────────────────

def rstats(g: pd.DataFrame) -> str:
    n = len(g)
    if n == 0:
        return "| — | 0 | — | — | — | — |"
    r = g["Rmult"].to_numpy()
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    pnl = g["PnL"].to_numpy()
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    wr = (pnl > 0).mean() * 100
    lo_, hi_ = r.mean() - ci, r.mean() + ci
    mark = " ✅" if lo_ > 0 else (" ❌" if hi_ < 0 else "")
    return (f"{n} | {r.mean():+.3f} ±{ci:.3f}{mark} | [{lo_:+.3f},{hi_:+.3f}] "
            f"| {pf:.2f} | {wr:.0f}% | ${pnl.sum():,.0f}")


def trow(label, g):
    return f"| {label} | {rstats(g)} |"


def stage2(mq: pd.DataFrame, bars: pd.DataFrame, odf: pd.DataFrame):
    emit("## Stage 2 — pre-registered tests on Stack v2 trades (Mar 6 – Jul 2, 2026)\n")
    sig = parse_signals(SIG_TXT)
    win = sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
    log(f"signals: {len(sig)} total, {len(win)} in window")

    sc = compute_stack_columns(win, bars)
    win = win.join(sc)

    if SIM_PQ.exists():
        res = pd.read_parquet(SIM_PQ)
        log(f"sim results loaded from cache ({len(res)})")
    else:
        dates = sorted(win["Date"].unique())
        ticks = {d: massive.load_continuous_ticks(d) for d in dates}
        ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
        log(f"ticks for {len(ticks)}/{len(dates)} dates")
        day = bars["DateTime"].dt.normalize()
        bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}
        res = simulate_trades(
            signals=win, ticks_by_date=ticks, target_r=3.0,
            entry_slip=1, exit_slip=1, stop_offset=1, tick_value=12.5,
            contracts=1, commission=4.36, bars_by_date=bbd,
            ratchet_r=1.0, ratchet_dest="BE",
        )
        log(f"sim: {len(res)} rows, cols: {list(res.columns)}")
        res.to_parquet(SIM_PQ)

    # attach stack cols / features by SignalNum
    keep = [c for c in ("SignalNum", "stack_pass", "stack_skip", "stack_tier") if c in win.columns]
    res = res.merge(win[keep], on="SignalNum", how="left", suffixes=("", "_w"))
    filled = res[res["Filled"].astype(bool)].copy()
    filled["PnL"] = filled["NetPnL"].astype(float)
    filled["Rmult"] = filled["PnL"] / filled["RiskDollar"].replace(0, np.nan)
    filled["DateD"] = pd.to_datetime(filled["Date"]).dt.normalize()

    # daily features in continuous space
    mqd = mq.set_index(mq["date"]).join(odf[["offset"]], how="inner")
    abr = _abr20(bars)

    f = filled
    f = f.merge(mqd.reset_index(drop=True).assign(DateD=mqd.index), on="DateD", how="left")
    off = f["offset"]
    s = np.where(f["Direction"].astype(str).str.upper().str.startswith("L"), 1.0, -1.0)
    entry = f["SignalPrice"].astype(float)
    riskp = (f["SignalPrice"] - f["StopPrice"]).abs()
    target = entry + s * 3 * riskp
    f["abr"] = f["DateD"].map(abr)

    # T1 headwind: opposing major (CallRes / CallRes0DTE / GammaWall0DTE for Longs;
    # PutSup / PutSup0DTE / GammaWall0DTE for Shorts) between entry and 3R target
    opp_long = f[["call_resistance", "call_resistance_0dte", "gamma_wall_0dte"]].add(off, axis=0)
    opp_short = f[["put_support", "put_support_0dte", "gamma_wall_0dte"]].add(off, axis=0)
    def nearest_opp(row_i):
        i = row_i
        levs = (opp_long.iloc[i] if s[i] > 0 else opp_short.iloc[i]).dropna()
        ahead = levs[(levs - entry.iloc[i]) * s[i] > 0]
        return (ahead - entry.iloc[i]).abs().min() if len(ahead) else np.nan
    f["opp_dist"] = [nearest_opp(i) for i in range(len(f))]
    f["hw_cross"] = f["opp_dist"] <= (3 * riskp)
    f["opp_abr"] = f["opp_dist"] / f["abr"]

    # T2 regime — as-published AND causal (prior-day) variants: Stage 0 showed the
    # archive row is EOD-stamped (distance_to_hvl uses same-day close), so
    # gamma_condition/scores may embed same-day information.
    prev = mq.set_index("date").shift(1)  # prior trading day's row
    for c in ("gamma_condition", "volatility_score", "momentum_score",
              "option_score", "seasonality_score", "net_gex"):
        f[c + "_prev"] = f["DateD"].map(prev[c])
    f["neg_gamma"] = f["gamma_condition"].astype(str).str.lower().eq("negative")
    f["neg_gamma_prev"] = f["gamma_condition_prev"].astype(str).str.lower().eq("negative")
    f["hv_ng_prev"] = (pd.to_numeric(f["volatility_score_prev"], errors="coerce") >= 3) & f["neg_gamma_prev"]
    hvl_c = f["high_vol_level"] + off
    f["above_hvl"] = entry > hvl_c
    # T3/T5 scores
    f["vol_bin"] = pd.cut(f["volatility_score"], [-1, 1.5, 3.5, 9], labels=["low(≤1)", "mid(2-3)", "high(≥4)"])
    f["hv_ng"] = (f["volatility_score"] >= 3) & f["neg_gamma"]
    # T4 scalars
    f["gex_neg"] = f["net_gex"] < 0
    for c, b in (("implied_vol_30d", "iv_bin"), ("exp_move_1d_pct", "em_bin")):
        try:
            f[b] = pd.qcut(f[c], 3, labels=["low", "mid", "high"])
        except ValueError:
            f[b] = np.nan

    hdr = "| cut | n | ExpR ±CI | 95% interval | PF | WR | net$ |"
    sep = "|---|---|---|---|---|---|---|"

    for scope, sub in (("ALL MC signals in window", f),
                       ("STACK v2 subset", f[f["stack_pass"] == True])):  # noqa: E712
        emit(f"### {scope}\n")
        emit(hdr); emit(sep)
        emit(trow("baseline", sub))
        emit(trow("T1 headwind (major level inside 3R path)", sub[sub["hw_cross"] == True]))   # noqa: E712
        emit(trow("T1 clear air (no major inside 3R path)", sub[sub["hw_cross"] == False]))    # noqa: E712
        q = sub["opp_abr"].dropna()
        if len(q) > 20:
            t1, t2_ = q.quantile([1/3, 2/3])
            emit(trow(f"T1 opp-dist tertile near (<{t1:.1f} ABR)", sub[sub["opp_abr"] < t1]))
            emit(trow("T1 opp-dist tertile mid", sub[(sub["opp_abr"] >= t1) & (sub["opp_abr"] < t2_)]))
            emit(trow(f"T1 opp-dist tertile far (≥{t2_:.1f} ABR)", sub[sub["opp_abr"] >= t2_]))
        emit(trow("T2 NEGATIVE gamma", sub[sub["neg_gamma"] == True]))     # noqa: E712
        emit(trow("T2 positive gamma", sub[sub["neg_gamma"] == False]))    # noqa: E712
        emit(trow("T2 NEG gamma (CAUSAL prev-day)", sub[sub["neg_gamma_prev"] == True]))   # noqa: E712
        emit(trow("T2 pos gamma (CAUSAL prev-day)", sub[sub["neg_gamma_prev"] == False]))  # noqa: E712
        emit(trow("T2 above HVL", sub[sub["above_hvl"] == True]))          # noqa: E712
        emit(trow("T2 below HVL", sub[sub["above_hvl"] == False]))         # noqa: E712
        for lab in ["low(≤1)", "mid(2-3)", "high(≥4)"]:
            emit(trow(f"T3 vol_score {lab}", sub[sub["vol_bin"] == lab]))
        for c in ("momentum_score", "option_score", "seasonality_score"):
            emit(trow(f"T3 {c} ≤1", sub[sub[c] <= 1]))
            emit(trow(f"T3 {c} ≥2", sub[sub[c] >= 2]))
        emit(trow("T5 HIGH-VOL(≥3) ∧ NEG-GAMMA", sub[sub["hv_ng"] == True]))    # noqa: E712
        emit(trow("T5 rest", sub[sub["hv_ng"] == False]))                       # noqa: E712
        emit(trow("T5 HV∧NG (CAUSAL prev-day)", sub[sub["hv_ng_prev"] == True]))   # noqa: E712
        emit(trow("T5 rest (CAUSAL prev-day)", sub[sub["hv_ng_prev"] == False]))   # noqa: E712
        emit(trow("T5 hi-vol ∧ pos-gamma", sub[(sub["volatility_score"] >= 3) & (~sub["neg_gamma"])]))
        emit(trow("T5 lo-vol ∧ neg-gamma", sub[(sub["volatility_score"] < 3) & (sub["neg_gamma"])]))
        emit(trow("T4 net GEX < 0", sub[sub["gex_neg"] == True]))    # noqa: E712
        emit(trow("T4 net GEX ≥ 0", sub[sub["gex_neg"] == False]))   # noqa: E712
        for b, lab in (("iv_bin", "IV30"), ("em_bin", "exp-move")):
            for v in ("low", "mid", "high"):
                emit(trow(f"T4 {lab} {v}", sub[sub[b] == v]))
        emit("")
    return f


def main():
    emit(f"# MenthorQ edge study — run {datetime.now():%Y-%m-%d %H:%M}\n")
    bars = pd.read_parquet(BARS_PQ)
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    log(f"bars {bars['DateTime'].min()} → {bars['DateTime'].max()}")
    mq = load_mq()
    mq["date"] = mq["date"].dt.normalize()
    mq = mq[(mq["date"] >= WIN_START) & (mq["date"] <= WIN_END)].reset_index(drop=True)
    log(f"menthorq rows in window: {len(mq)}")
    odf = stage0(mq, bars)
    stage1(mq, bars, odf)
    stage2(mq, bars, odf)
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    log(f"written {OUT_MD}")


if __name__ == "__main__":
    main()
