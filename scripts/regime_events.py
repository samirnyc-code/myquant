"""regime_events.py — Replicate Grimes's three futures EVENT studies on ES vs nulls.

The v0 occupancy gate failed (see RESULTS_v0_validation.md): state-occupancy is the wrong
unit. This tests what Grimes actually validates — discrete EVENTS, scored as excess forward
return vs the all-bars baseline, against synthetic nulls.

Events (exact specs, workbook Ch.14/16 page cites in the synthesis doc):
  1. COMPRESSION BREAKOUT (wb p.596-598, Table 16.13 — his strongest futures signal):
     setup: prior bar ATR(5)/ATR(40) < 0.5
     trigger: this bar's true range >= prior bar's ATR(5)
     filter: close in top 50% of bar's range AND close > prior close  -> LONG
     (mirrored for shorts). He reports futures: +128bp** d4, 73% up d5. ~1-in-500 days.
  2. KELTNER PULLBACK TO 20-EMA (wb p.599-601, Table 16.14):
     armed LONG after a close above upper Keltner (20-EMA + 2.25*ATR20); the first
     subsequent bar whose LOW touches the PRIOR bar's EMA is the event; one event per
     excursion (re-arm requires a new close outside). Mirrored for shorts (his tested
     side: shorts stronger, -59bp** d1). NOTE: we score from the EVENT bar's close, not
     the intrabar touch price — small conservative deviation, documented.
  3. DONCHIAN CHANNEL BREAKOUT (wb p.584-589): close >= N-bar max close (long) /
     <= N-bar min close (short), entry on close, >=5 bars between same-direction entries.
     N=100 and 260 daily (futures momentum: +73bp**/+102bp** at d20).

Scoring: forward return from event-bar close at h in {1,3,5,10,20}; mean/median (bp), %up,
t, excess vs all-bars baseline. Events with N<20 reported as X-of-Y counts, not stats.

NULLS: same detectors + scoring run on synthetic series (shuffled real returns and iid-normal
random walk), NREPS replications aggregated, so rare events accumulate a real null sample.
The gate: a real event effect must exceed the null's aggregated mean effect meaningfully
(and Grimes floor: >=10bp, mean/median same sign).

Run:  .venv/Scripts/python.exe scripts/regime_events.py
Out:  data/regime/events_real_<tag>.csv, events_nulls_<tag>.csv, events_gate_<tag>.csv,
      regime_events_<tag>.png (opened in VSCode).
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import regime_features as rf
import regime_validate as rvd

OUT = ROOT / "data" / "regime"
HORIZONS = [1, 3, 5, 10, 20]
NREPS = {"shuffle": 20, "rw": 20}
SEED = 20260723
COOLDOWN = 5   # Donchian: min bars between same-direction entries


# ---------------------------------------------------------------- detectors
def ev_compression_breakout(b: pd.DataFrame) -> pd.DataFrame:
    tr = rf.true_range(b)
    atr5 = tr.rolling(5).mean()
    atr40 = tr.rolling(40).mean()
    compressed_prev = (atr5 / atr40).shift(1) < 0.5
    trig = tr >= atr5.shift(1)
    rng = (b["High"] - b["Low"]).replace(0, np.nan)
    pos = (b["Close"] - b["Low"]) / rng
    long_ = compressed_prev & trig & (pos >= 0.5) & (b["Close"] > b["Close"].shift(1))
    short = compressed_prev & trig & (pos <= 0.5) & (b["Close"] < b["Close"].shift(1))
    return pd.DataFrame({"long": long_.fillna(False), "short": short.fillna(False)})


def ev_keltner_pullback(b: pd.DataFrame) -> pd.DataFrame:
    c = b["Close"]
    ema = c.ewm(span=20, adjust=False).mean()
    atr20 = rf.true_range(b).rolling(20).mean()
    up_band = ema + 2.25 * atr20
    dn_band = ema - 2.25 * atr20
    closed_above = (c > up_band).to_numpy()
    closed_below = (c < dn_band).to_numpy()
    lo = b["Low"].to_numpy(); hi = b["High"].to_numpy()
    ema_prev = ema.shift(1).to_numpy()
    n = len(b)
    long_ = np.zeros(n, bool); short = np.zeros(n, bool)
    armed = 0  # +1 long-armed, -1 short-armed, 0 idle
    for i in range(1, n):
        if closed_above[i]:
            armed = +1
        elif closed_below[i]:
            armed = -1
        elif armed == +1 and not np.isnan(ema_prev[i]) and lo[i] <= ema_prev[i]:
            long_[i] = True; armed = 0
        elif armed == -1 and not np.isnan(ema_prev[i]) and hi[i] >= ema_prev[i]:
            short[i] = True; armed = 0
    return pd.DataFrame({"long": long_, "short": short})


def ev_donchian(b: pd.DataFrame, n: int) -> pd.DataFrame:
    c = b["Close"]
    hi_ch = c.rolling(n, min_periods=n).max()
    lo_ch = c.rolling(n, min_periods=n).min()
    raw_l = (c >= hi_ch).to_numpy(); raw_s = (c <= lo_ch).to_numpy()
    long_ = np.zeros(len(b), bool); short = np.zeros(len(b), bool)
    last_l = last_s = -10**9
    for i in range(len(b)):
        if raw_l[i] and i - last_l >= COOLDOWN:
            long_[i] = True; last_l = i
        if raw_s[i] and i - last_s >= COOLDOWN:
            short[i] = True; last_s = i
    return pd.DataFrame({"long": long_, "short": short})


EVENTS = {
    "compress_bo": ev_compression_breakout,
    "kelt_pull": ev_keltner_pullback,
    "donch100": lambda b: ev_donchian(b, 100),
    "donch260": lambda b: ev_donchian(b, 260),
}


# ---------------------------------------------------------------- scoring
def score_events(b: pd.DataFrame, sig: pd.DataFrame, side: str) -> list[dict]:
    c = b["Close"]
    mask = sig[side].to_numpy()
    rows = []
    for h in HORIZONS:
        fwd = c.shift(-h) / c - 1
        if side == "short":
            fwd = -fwd                       # short P&L convention
        base = fwd.dropna()
        r = fwd[mask & fwd.notna().to_numpy()]
        d = {"side": side, "h": h, "N": int(len(r)), "N_base": int(len(base))}
        if len(r) >= 2:
            sd = r.std(ddof=1)
            d.update({
                "mean_bp": round(1e4 * r.mean(), 1),
                "median_bp": round(1e4 * r.median(), 1),
                "up%": round(100 * (r > 0).mean(), 1),
                "t": round(float(r.mean() / (sd / np.sqrt(len(r)))), 2) if sd > 0 else np.nan,
                # fwd was sign-flipped for shorts above, so base.mean() is already the
                # baseline return of the SAME side — excess is a plain difference.
                "excess_bp": round(1e4 * (r.mean() - base.mean()), 1),
            })
        else:
            d.update({"mean_bp": np.nan, "median_bp": np.nan, "up%": np.nan,
                      "t": np.nan, "excess_bp": np.nan})
        rows.append(d)
    return rows


def run_all(bars_by_tf: dict[str, pd.DataFrame], label: str) -> pd.DataFrame:
    rows = []
    for tf, b in bars_by_tf.items():
        for ev, fn in EVENTS.items():
            if ev in ("donch100", "donch260") and tf != "daily":
                continue                     # his spec is daily channels
            sig = fn(b)
            for side in ("long", "short"):
                for d in score_events(b, sig, side):
                    d.update({"src": label, "tf": tf, "event": ev})
                    rows.append(d)
    return pd.DataFrame(rows)


def main():
    tag = pd.Timestamp.now().strftime("%Y%m%d")
    m1 = rf._load_1m()
    bars = {tf: rf.resample_bars(m1, tf) for tf in ("daily", "60m", "30m")}

    real = run_all(bars, "real")
    real.to_csv(OUT / f"events_real_{tag}.csv", index=False)

    # nulls: replicate detectors on synthetic daily + 60m series, aggregate reps
    rng = np.random.default_rng(SEED)
    null_rows = []
    for kind, reps in NREPS.items():
        for rep in range(reps):
            for tf in ("daily", "60m"):
                nb = rvd.make_null(kind, bars[tf], rng)
                t = run_all({tf: nb}, f"null_{kind}")
                t["rep"] = rep
                null_rows.append(t)
    nulls = pd.concat(null_rows, ignore_index=True)
    nulls.to_csv(OUT / f"events_nulls_{tag}.csv", index=False)

    # aggregate null: N-weighted mean effect per (event, tf, side, h)
    def agg_null(g):
        w = g["N"].to_numpy(); m = g["mean_bp"].to_numpy()
        ok = (w > 0) & ~np.isnan(m)
        return pd.Series({
            "null_N": int(w[ok].sum()),
            "null_mean_bp": round(float((m[ok] * w[ok]).sum() / w[ok].sum()), 1) if w[ok].sum() else np.nan,
        })
    na = (nulls.groupby(["event", "tf", "side", "h"])
                .apply(agg_null, include_groups=False).reset_index())

    gate = real.merge(na, on=["event", "tf", "side", "h"], how="left")
    gate["edge_vs_null_bp"] = (gate["mean_bp"] - gate["null_mean_bp"]).round(1)
    gate.to_csv(OUT / f"events_gate_{tag}.csv", index=False)

    show = gate[gate["h"].isin([1, 5, 20])][
        ["event", "tf", "side", "h", "N", "mean_bp", "median_bp", "up%", "t",
         "null_N", "null_mean_bp", "edge_vs_null_bp"]]
    pd.set_option("display.width", 250)
    for ev in EVENTS:
        sub = show[show["event"] == ev]
        if len(sub):
            print(f"\n=== {ev} ===")
            print(sub.to_string(index=False))

    _plot(gate, tag)
    return gate


def _plot(gate: pd.DataFrame, tag: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    evs = list(EVENTS.keys())
    fig, axes = plt.subplots(1, len(evs), figsize=(4.4 * len(evs), 4.4))
    for ax, ev in zip(np.atleast_1d(axes), evs):
        sub = gate[(gate["event"] == ev) & (gate["tf"] == "daily")]
        for side, col in (("long", "#2e7d4f"), ("short", "#b0453a")):
            s = sub[sub["side"] == side].sort_values("h")
            ax.plot(s["h"], s["mean_bp"], "-o", color=col, label=f"{side} (N={int(s['N'].max())})")
            ax.plot(s["h"], s["null_mean_bp"], "--", color=col, alpha=0.45, label=f"{side} null")
        ax.axhline(0, color="#444", lw=0.8)
        ax.set_title(f"{ev} — daily"); ax.set_xlabel("horizon (bars)")
        ax.grid(alpha=0.2); ax.legend(fontsize=7)
    np.atleast_1d(axes)[0].set_ylabel("mean event return (bp, short = short P&L)")
    fig.suptitle(f"Grimes event studies on ES vs aggregated nulls — {tag}", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    png = OUT / f"regime_events_{tag}.png"
    fig.savefig(png, dpi=130)
    plt.close(fig)
    print(f"\nchart -> {png}")
    try:
        subprocess.run(["code", str(png)], shell=True, check=False)
    except Exception:
        pass


if __name__ == "__main__":
    main()
