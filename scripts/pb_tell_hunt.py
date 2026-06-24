"""Tell-hunt: what separates the PB->1R winners from the PB->stop losers?

Restricts to PB-touched signals, defines the resolved binary
    win  = pb_then_1r   (pulled back 50%, then made original 1R)
    loss = pb_then_stop (pulled back 50%, then stopped)
and ranks every cheap pre-trade feature by its win-rate lift. Also breaks the
whole population down by time-of-day, and searches 2-feature combos for any
sub-bucket that clears the ~27% marginal-add bar with usable sample size.

EXPLORATORY / overfitting-prone by construction (we are fishing). Everything
here is a hypothesis to be OOS-validated, not a rule.
"""
from __future__ import annotations
import sys, gc, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
import massive          # noqa: E402
import indicators       # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_AI      = Path(r"C:\Users\Admin\Documents\NinjaTrader 8\MCVolumeExport\AlwaysIn_State.csv")


def log(m): print(f"[tell] {m}", flush=True)


def merge_alwaysin(feat):
    """Attach causal AID features (backward as-of on the flip CSV). Mirrors
    bar_analysis.merge_alwaysin_overlay / alwaysin_flip_test.merge_alwaysin."""
    if not _AI.exists():
        log(f"  AID csv not found at {_AI} — skipping AID")
        return feat
    ai = pd.read_csv(_AI, parse_dates=["BarTime"]).sort_values("BarTime").reset_index(drop=True)
    flip_dt = pd.to_datetime(ai["BarTime"])
    flip_dir = (ai["NewDir"].astype(str).str.upper().str.startswith("L")
                .map({True: 1, False: -1}).to_numpy())
    sig_dt = pd.to_datetime(feat["DateTime"])
    idx = flip_dt.searchsorted(sig_dt, side="right") - 1
    pre = idx < 0
    idx_c = idx.clip(0, len(ai) - 1)
    state = flip_dir[idx_c].astype(float); state[pre] = 0.0
    bars = (sig_dt.to_numpy() - flip_dt.to_numpy()[idx_c]) / np.timedelta64(5, "m")
    bars = np.where(pre, np.nan, np.round(bars))
    feat = feat.copy()
    feat["AID_State"] = state
    feat["AID_BarsSinceFlip"] = bars
    feat["AID_OnFlipBar"] = (bars == 0)
    is_long = feat["is_long"].to_numpy()
    feat["AID_DirMatch"] = ((is_long & (state == 1)) | (~is_long & (state == -1)))
    log(f"  AID merged: {len(ai)} flips, {int((state!=0).sum())} signals with state")
    return feat


def classify(prices, e1, stop_px, is_long):
    if prices.size == 0:
        return "no_ticks"
    R = abs(e1 - stop_px)
    if R <= 0:
        return "bad_R"
    sgn = 1.0 if is_long else -1.0
    pb  = e1 - sgn * 0.5 * R
    tgt = e1 + sgn * 1.0 * R
    stp = e1 - sgn * 1.0 * R
    if is_long:
        pb_hit, tgt_hit, stop_hit = prices <= pb, prices >= tgt, prices <= stp
    else:
        pb_hit, tgt_hit, stop_hit = prices >= pb, prices <= tgt, prices >= stp
    i_pb  = int(np.argmax(pb_hit))  if pb_hit.any()  else None
    i_tgt = int(np.argmax(tgt_hit)) if tgt_hit.any() else None
    if i_tgt is not None and (i_pb is None or i_tgt < i_pb):
        return "clean_win"
    if i_pb is None:
        return "clean_eod"
    j = i_pb + 1
    post_tgt, post_stop = tgt_hit[j:], stop_hit[j:]
    k_t = int(np.argmax(post_tgt))  if post_tgt.any()  else None
    k_s = int(np.argmax(post_stop)) if post_stop.any() else None
    if k_t is not None and (k_s is None or k_t < k_s):
        return "pb_then_1r"
    if k_s is not None and (k_t is None or k_s < k_t):
        return "pb_then_stop"
    return "pb_eod"


def run_paths(sig):
    buckets = np.empty(len(sig), dtype=object)
    idx_by_date = {d: g.index.to_numpy() for d, g in sig.groupby("Date")}
    days = sorted(idx_by_date)
    for di, d in enumerate(days):
        try:
            t = massive.load_continuous_ticks(pd.to_datetime(d).date())
        except Exception:
            continue
        if t is None or t.empty:
            continue
        t = t.sort_values("DateTime")
        tt = t["DateTime"].to_numpy(); tp = t["Price"].to_numpy(dtype=float)
        for i in idx_by_date[d]:
            s = sig.loc[i]
            st = np.searchsorted(tt, np.datetime64(s["DateTime"]), side="right")
            buckets[sig.index.get_loc(i)] = classify(
                tp[st:], float(s["SignalPrice"]), float(s["StopPrice"]), bool(s["is_long"]))
        del t, tt, tp; gc.collect()
        if (di + 1) % 250 == 0:
            log(f"  paths {di+1}/{len(days)}")
    return buckets


def winrate_table(df, col, bins=None, labels=None, min_n=40):
    """Win-rate of pb_then_1r vs pb_then_stop within each bucket of `col`."""
    d = df.copy()
    if bins is not None:
        d["_b"] = pd.cut(d[col], bins=bins, labels=labels)
    else:
        d["_b"] = d[col].astype(str)
    rows = []
    for b, g in d.groupby("_b", observed=True):
        n = len(g)
        if n < min_n:
            continue
        wr = g["win"].mean() * 100
        rows.append((str(b), n, wr))
    if not rows:
        return None
    out = pd.DataFrame(rows, columns=["bucket", "N", "win%"]).sort_values("win%", ascending=False)
    return out


def main():
    log("Load signals + bars...")
    sig = pd.read_parquet(_SIGNALS)
    sig["DateTime"] = pd.to_datetime(sig["DateTime"])
    sig["is_long"] = sig["Direction"].astype(str).str.upper().str.startswith("L")
    sig = sig.sort_values("DateTime").reset_index(drop=True)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")

    log("Classify paths (day-by-day ticks)...")
    sig["bucket"] = run_paths(sig)

    log("Tag causal features...")
    feat = indicators.tag_signals(sig, bars)
    feat = feat.sort_values("DateTime").reset_index(drop=True)
    feat = merge_alwaysin(feat)

    # ── engineered features ────────────────────────────────────────────────
    dt = feat["DateTime"]
    feat["hour"] = dt.dt.hour
    # Canonical CT session phases (bar_analysis._SESSION_PHASES):
    # Open 08:30-11:30 · Mid 11:30-13:00 · Late 13:00-14:45 · Close 14:45-15:15
    _PHASES = [("Open", 510, 690), ("Mid", 690, 780),
               ("Late", 780, 885), ("Close", 885, 915)]
    def _phase(ts):
        m = ts.hour * 60 + ts.minute
        for nm, lo, hi in _PHASES:
            if lo <= m < hi:
                return nm
        return "Other"
    feat["tod"] = pd.Categorical(dt.apply(_phase),
                                 categories=["Open","Mid","Late","Close","Other"], ordered=True)
    feat["dow"] = dt.dt.dayofweek
    feat["R_pts"] = (feat["SignalPrice"] - feat["StopPrice"]).abs()
    sgn = np.where(feat["is_long"], 1.0, -1.0)
    # entry extension: + = entering EXTENDED in trade direction (chasing); - = pullback-side entry
    feat["ext_ema"]  = sgn * (feat["SignalPrice"] - feat["EMA_20"])
    feat["ext_vwap"] = sgn * feat["VWAP_dev"]            # signed sigma in trade direction
    # with structural trend?
    if "structural_trend" in feat:
        st = feat["structural_trend"].astype(str)
        feat["with_trend"] = ((feat["is_long"] & st.str.contains("up", case=False)) |
                              (~feat["is_long"] & st.str.contains("down", case=False)))
    # consecutive same-direction streak (global sequence, position incl. self)
    d = feat["Direction"].astype(str).to_numpy()
    streak = np.ones(len(d), dtype=int)
    for i in range(1, len(d)):
        streak[i] = streak[i-1] + 1 if d[i] == d[i-1] else 1
    feat["dir_streak"] = streak
    # session VA location relptr to direction
    if "session_loc" in feat:
        feat["va_loc"] = feat["session_loc"]
    # AID derived buckets
    if "AID_BarsSinceFlip" in feat:
        feat["AID_bars_b"] = pd.cut(feat["AID_BarsSinceFlip"],
                                    bins=[-1, 0, 3, 10, 1e9],
                                    labels=["on-flip", "1-3", "4-10", "11+"])

    # ── binary among resolved PB-touched ───────────────────────────────────
    pbres = feat[feat["bucket"].isin(["pb_then_1r", "pb_then_stop"])].copy()
    pbres["win"] = (pbres["bucket"] == "pb_then_1r").astype(int)
    base = pbres["win"].mean() * 100
    n_all_pb = feat["bucket"].isin(["pb_then_1r","pb_then_stop","pb_eod"]).sum()
    log(f"PB-touched resolved N={len(pbres)}  base win%={base:.1f}  "
        f"(all-PB incl eod={n_all_pb})\n")

    print("=" * 78)
    print(f"TELL HUNT — PB->1R vs PB->stop  (base win-rate = {base:.1f}%, N={len(pbres)})")
    print("bar to beat for the add: ~27% (leg-2 marginal breakeven)")
    print("=" * 78)

    # ── TOD breakdown of the WHOLE population first ─────────────────────────
    print("\n## Whole population by TOD (pb_then_1r share of ALL signals)")
    for b, g in feat.groupby("tod", observed=True):
        n = len(g)
        p1 = (g["bucket"] == "pb_then_1r").mean() * 100
        pbt = g["bucket"].isin(["pb_then_1r","pb_then_stop","pb_eod"]).mean() * 100
        cw = (g["bucket"] == "clean_win").mean() * 100
        print(f"   {str(b):<14} N={n:>5}  clean_win={cw:>4.1f}%  PB-touch={pbt:>4.1f}%  PB->1R={p1:>4.1f}%")

    # ── ranked feature buckets (resolved binary) ────────────────────────────
    specs = [
        ("tod", None, None),
        ("dow", None, None),
        ("SignalType", None, None),
        ("is_long", None, None),
        ("with_trend", None, None) if "with_trend" in feat else None,
        ("is_deep_pullback", None, None) if "is_deep_pullback" in feat else None,
        ("balance_state", None, None),
        ("prior_inside_day", None, None),
        ("prior_adr_ext", None, None),
        ("va_loc", None, None) if "va_loc" in feat else None,
        ("dir_streak", [0,1,2,3,99], ["1","2","3","4+"]),
        ("ext_ema", [-1e9,-2,-0.5,0.5,2,1e9], ["<<below","below","≈EMA","above",">>above"]),
        ("ext_vwap", [-1e9,-1,0,1,1e9], ["<-1σ","-1..0","0..1σ",">1σ"]),
        ("R_pts", [0,1.5,2.5,3.5,1e9], ["≤1.5","1.5-2.5","2.5-3.5","3.5+"]),
        ("ER_intra_6", [0,0.2,0.35,0.5,1.01], ["≤.2",".2-.35",".35-.5",".5+"]) if "ER_intra_6" in feat else None,
        ("ER_intra_12", [0,0.2,0.35,0.5,1.01], ["≤.2",".2-.35",".35-.5",".5+"]) if "ER_intra_12" in feat else None,
        ("prior_ER", [0,0.2,0.35,0.5,1.01], ["≤.2",".2-.35",".35-.5",".5+"]),
        ("hour", None, None),
        ("AID_State", None, None) if "AID_State" in feat else None,
        ("AID_DirMatch", None, None) if "AID_DirMatch" in feat else None,
        ("AID_OnFlipBar", None, None) if "AID_OnFlipBar" in feat else None,
        ("AID_bars_b", None, None) if "AID_bars_b" in feat else None,
    ]
    print("\n## Feature buckets ranked by win-rate (min N=40)")
    for spec in specs:
        if spec is None:
            continue
        col, bins, labels = spec
        if col not in pbres.columns:
            continue
        tab = winrate_table(pbres, col, bins, labels, min_n=40)
        if tab is None:
            continue
        print(f"\n-- {col} (base {base:.1f}%) --")
        for _, r in tab.iterrows():
            flag = "  <<<" if r["win%"] >= base + 6 else ("  (low)" if r["win%"] <= base - 6 else "")
            print(f"     {r['bucket']:<14} N={int(r['N']):>5}  win={r['win%']:>5.1f}%{flag}")

    # ── 2-feature combo search for buckets clearing ~30% ────────────────────
    print("\n## Best 2-feature combos clearing 30% win-rate (N>=60)")
    cat_cols = [c for c in ["tod","SignalType","balance_state","AID_DirMatch",
                            "AID_bars_b","prior_inside_day","va_loc"] if c in pbres.columns]
    found = []
    for i in range(len(cat_cols)):
        for j in range(i+1, len(cat_cols)):
            a, b = cat_cols[i], cat_cols[j]
            g = pbres.groupby([a, b], observed=True)["win"].agg(["mean","count"])
            for idx, row in g.iterrows():
                if row["count"] >= 60 and row["mean"]*100 >= 30:
                    found.append((f"{a}={idx[0]} & {b}={idx[1]}", int(row["count"]), row["mean"]*100))
    for name, n, wr in sorted(found, key=lambda x: -x[2])[:15]:
        print(f"   {name:<48} N={n:>4}  win={wr:>5.1f}%")
    if not found:
        print("   (none cleared 30% with N>=60)")

    # ── quick tree feature importance (if sklearn available) ────────────────
    try:
        from sklearn.tree import DecisionTreeClassifier
        from sklearn.preprocessing import OrdinalEncoder
        Xcols = ["hour","dow","R_pts","ext_ema","ext_vwap","dir_streak"]
        Xcols += [c for c in ["ER_intra_6","ER_intra_12","prior_ER","VWAP_dev"] if c in pbres]
        X = pbres[Xcols].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy()
        y = pbres["win"].to_numpy()
        clf = DecisionTreeClassifier(max_depth=4, min_samples_leaf=60, random_state=0)
        clf.fit(X, y)
        imp = sorted(zip(Xcols, clf.feature_importances_), key=lambda x: -x[1])
        print("\n## Decision-tree feature importance (depth4, leaf>=60)")
        for c, v in imp:
            if v > 0:
                print(f"   {c:<14} {v:.3f}")
    except Exception as e:
        print(f"\n(tree skipped: {e})")

    # ── Open+Mid combined + by-year validation of the phase gradient ────────
    pbres["year"] = pd.to_datetime(pbres["DateTime"]).dt.year
    pbres["phase2"] = np.where(pbres["tod"].isin(["Open", "Mid"]), "Open+Mid",
                       np.where(pbres["tod"].isin(["Late", "Close"]), "Late+Close", "Other"))
    feat["year"] = pd.to_datetime(feat["DateTime"]).dt.year
    feat["phase2"] = np.where(feat["tod"].isin(["Open", "Mid"]), "Open+Mid",
                      np.where(feat["tod"].isin(["Late", "Close"]), "Late+Close", "Other"))

    print("\n" + "=" * 78)
    print("PHASE GRADIENT — Open+Mid combined + per-year validation")
    print("=" * 78)
    print(f"\n## Resolved win-rate (base {base:.1f}%) — combined buckets")
    for grp, g in pbres.groupby("phase2"):
        if grp == "Other":
            continue
        wr = g["win"].mean() * 100; n = len(g)
        se = (wr*(100-wr)/n) ** 0.5
        print(f"   {grp:<12} N={n:>5}  win={wr:>5.1f}%  (±{1.96*se:.1f})")

    print("\n## Whole-population PB->1R share by year × phase2")
    yrs = sorted(feat["year"].unique())
    hdr = "   year   " + "".join(f"{g:>14}" for g in ["Open+Mid", "Late+Close"])
    print(hdr)
    for y in yrs:
        line = f"   {y:<6}"
        for grp in ["Open+Mid", "Late+Close"]:
            gg = feat[(feat["year"] == y) & (feat["phase2"] == grp)]
            n = len(gg); p1 = (gg["bucket"] == "pb_then_1r").mean()*100 if n else 0
            line += f"  {p1:>4.1f}% (N={n:>4})"
        print(line)

    print("\n## Resolved win-rate by year × phase2  (the overfit test)")
    print("   year      Open+Mid            Late+Close")
    for y in yrs:
        line = f"   {y:<6}"
        for grp in ["Open+Mid", "Late+Close"]:
            gg = pbres[(pbres["year"] == y) & (pbres["phase2"] == grp)]
            n = len(gg); wr = gg["win"].mean()*100 if n else 0
            line += f"  {wr:>5.1f}% (N={n:>4})  "
        print(line)

    print("\n## Per-year, per-phase (Open/Mid/Late) resolved win-rate")
    print("   year     Open               Mid                Late")
    for y in yrs:
        line = f"   {y:<6}"
        for ph in ["Open", "Mid", "Late"]:
            gg = pbres[(pbres["year"] == y) & (pbres["tod"] == ph)]
            n = len(gg); wr = gg["win"].mean()*100 if n else 0
            line += f"  {wr:>5.1f}% (N={n:>4}) "
        print(line)

    feat.to_parquet(_ROOT / "docs" / "living" / "pb_tell_features.parquet")
    log("Saved features parquet.")


if __name__ == "__main__":
    main()
