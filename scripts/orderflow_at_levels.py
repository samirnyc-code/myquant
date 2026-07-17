"""Order flow at MenthorQ gamma levels — touch/signature/outcome study (S75).

For every touch of an MQ level by ES price, tag the order-flow signature computed
ONLY from data up to the touch bar's close, then measure forward outcomes starting
at the NEXT bar. Pre-registered parameters (S75H, set before seeing any results):

  TOUCH_TICKS = 4      a bar touches a level if |high/low - level| <= 4 ticks (1 pt)
  RESET_PTS   = 3      a new episode requires price to leave a 3-pt buffer first
  RESET_MIN   = 30     ... or 30 minutes to pass since the last touch of that level
  APPROACH_N  = 10     signature approach window = 10 bars before the touch bar
  HOLD_PTS    = 3      "level held" = price stays >= 3 pts on the fade side ...
  HOLD_MIN    = 15     ... for the next 15 minutes without trading through

Hypotheses under test (docs/living/orderflow_edge_backlog.md — #1, #2, #5 only):
  #1 naked/session VPOC within 6 pts below PS/GW0 -> price gravitates to it
  #2 session HVN coinciding (±2 pts) with HVL -> first touch mean-reverts
  #5 absorption into HVL (aggressive delta, no price progress) -> level holds

Inputs : data/footprint/ES_footprint.csv (ladder, deduped on load)
         data/footprint/ES_bars.csv      (tick-order fields; defines valid bars)
         data/menthorq/ES1!_mq_levels_history.csv (levels in ES points — no basis)
Outputs: data/footprint/level_touches.csv (one row per touch episode)
         inline summary tables

  .venv/Scripts/python.exe scripts/orderflow_at_levels.py [YYYY-MM-DD ...]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
FP = ROOT / "data" / "footprint"

TICK = 0.25
TOUCH_TICKS = 4
TOUCH_PTS = TOUCH_TICKS * TICK
RESET_PTS = 3.0
RESET_MIN = 30
APPROACH_N = 10
HOLD_PTS = 3.0
HOLD_MIN = 15
FWD_MIN = [5, 15, 30, 60]

LEVEL_COLS = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0",
              "d1_min", "d1_max"] + [f"gex_{i}" for i in range(1, 11)]


def load_ladder():
    d = pd.read_csv(FP / "ES_footprint.csv")
    d = d[~d.duplicated(subset=["BarIdx", "BarTime", "Price"], keep="last")]
    return d


def load_bars():
    """Join exporter bar fields with recreated ladder metrics; per-session CVD."""
    b = pd.read_csv(FP / "ES_bars.csv")
    m = pd.read_csv(FP / "ES_metrics.csv")
    m = m.drop(columns=[c for c in ("high", "low", "High", "Low") if c in m.columns])
    bars = b.merge(m, on=["BarIdx", "BarTime"], how="inner", suffixes=("", "_m"))
    bars["ts"] = pd.to_datetime(bars.BarTime)
    bars["day"] = bars.BarTime.str[:10]
    bars = bars.sort_values("BarIdx").reset_index(drop=True)
    bars["cvd"] = bars.groupby("day").delta.cumsum()  # reset CVD per session
    return bars


def session_profile(ladder_day, upto_baridx):
    """Per-price volume for one session, using bars STRICTLY BEFORE upto_baridx."""
    g = ladder_day[ladder_day.BarIdx < upto_baridx]
    if g.empty:
        return None
    vol = g.groupby("Price")[["BidVol", "AskVol"]].sum().sum(axis=1)
    return vol  # index=price, values=volume


def profile_features(vol):
    """POC / HVNs (>=2x mean) / LVNs (<=0.25x mean) from a per-price volume series."""
    if vol is None or vol.empty:
        return None
    mean_v = vol.mean()
    return dict(
        poc=float(vol.idxmax()),
        hvns=[float(p) for p, v in vol.items() if v >= 2 * mean_v],
        lvns=[float(p) for p, v in vol.items() if 0 < v <= 0.25 * mean_v],
    )


def swing_confirmed_divergence(w, side):
    """Delta divergence into the touch, using only the approach window w (closed bars).
    side='up' approach: price high rising while CVD high not rising (bear div)."""
    if len(w) < 4:
        return False
    half = len(w) // 2
    a, b = w.iloc[:half], w.iloc[half:]
    if side == "up":
        return b.High.max() > a.High.max() and b.cvd.max() <= a.cvd.max()
    return b.Low.min() < a.Low.min() and b.cvd.min() >= a.cvd.min()


def touch_episodes(bars_day, level, ltype):
    """Yield first-touch episodes of one level for one session.

    New episode on band re-entry if price left the 3-pt reset buffer in between,
    OR was out of the band for >= RESET_MIN minutes (the doc'd rules are OR — the
    v1 code required both AND only reset the clock on recorded touches, silently
    swallowing genuine re-tests; found on the 7/16 chart audit)."""
    eps = []
    last_near_ts = None   # last bar whose band overlapped the level
    prev_near = False
    armed = False         # price has been beyond the reset buffer since last touch
    for _, r in bars_day.iterrows():
        near = (r.Low - TOUCH_PTS) <= level <= (r.High + TOUCH_PTS)
        if near:
            if not prev_near and (
                last_near_ts is None or armed
                or (r.ts - last_near_ts).total_seconds() >= RESET_MIN * 60
            ):
                eps.append(r)
            last_near_ts = r.ts
            armed = False
        elif not (r.Low <= level <= r.High) \
                and min(abs(r.High - level), abs(r.Low - level)) > RESET_PTS:
            armed = True
        prev_near = near
    return eps


def signature(bars_day, ladder_day, touch, level):
    """Order-flow signature from approach window + touch bar ONLY (no lookahead)."""
    i = bars_day.index.get_loc(touch.name)
    w = bars_day.iloc[max(0, i - APPROACH_N):i]  # closed bars before the touch
    mid = (touch.High + touch.Low) / 2
    side = "up" if (len(w) and mid > w.Close.iloc[0]) or level >= mid else None
    # approach direction: where price came FROM relative to the level
    approach = "from_below" if (len(w) and w.Close.mean() < level) else "from_above"
    appr_delta = int(w.delta.sum()) if len(w) else 0
    appr_range = float(w.Close.iloc[-1] - w.Close.iloc[0]) if len(w) > 1 else 0.0
    # absorption: heavy aggressive delta pushed TOWARD the level (sign must match the
    # approach direction) with little net price progress. Threshold revised S75H after
    # the first run showed the v1 rule could never fire on 2000-lot volume bars.
    toward = appr_delta > 0 if approach == "from_below" else appr_delta < 0
    absorbing = toward and abs(appr_delta) >= 500 and abs(appr_range) <= 2.0
    div = swing_confirmed_divergence(
        pd.concat([w, touch.to_frame().T]).infer_objects(),
        "up" if approach == "from_below" else "down")
    prof = profile_features(session_profile(ladder_day, touch.BarIdx))
    hvn_near = prof and any(abs(h - level) <= 2.0 for h in prof["hvns"])
    poc_below = prof and (level - 6.0) <= prof["poc"] < level
    return dict(
        approach=approach, appr_delta=appr_delta, appr_range=appr_range,
        absorbing=bool(absorbing), divergence=bool(div),
        imb_with=int(touch.buy_imb if approach == "from_below" else touch.sell_imb),
        imb_against=int(touch.sell_imb if approach == "from_below" else touch.buy_imb),
        touch_delta=int(touch.delta), touch_min_delta=int(touch.MinDelta),
        touch_max_delta=int(touch.MaxDelta), delta_rate=float(touch.DeltaRate),
        unf_auction=bool(touch.UnfHigh or touch.UnfLow),
        sess_poc=(prof or {}).get("poc"), hvn_at_level=bool(hvn_near),
        poc_just_below=bool(poc_below),
    )


def outcomes(bars_day, touch, level, approach):
    """Forward outcomes starting at the NEXT bar after the touch bar."""
    i = bars_day.index.get_loc(touch.name)
    fwd = bars_day.iloc[i + 1:]
    if fwd.empty:
        return None
    t0 = touch.ts
    px0 = float(touch.Close)
    out = {}
    for mins in FWD_MIN:
        seg = fwd[fwd.ts <= t0 + pd.Timedelta(minutes=mins)]
        out[f"ret_{mins}m"] = round(float(seg.Close.iloc[-1]) - px0, 2) if len(seg) else np.nan
    # MFE/MAE in the fade direction (fade = away from the level, back where price came from)
    fade_sign = -1.0 if approach == "from_below" else 1.0  # from_below -> fade is short? no:
    # fade means the level HOLDS: from_below -> price rejected DOWN (short the touch)
    hold_seg = fwd[fwd.ts <= t0 + pd.Timedelta(minutes=HOLD_MIN)]
    if approach == "from_below":
        mfe = px0 - float(hold_seg.Low.min()) if len(hold_seg) else np.nan
        mae = float(hold_seg.High.max()) - px0 if len(hold_seg) else np.nan
        held = len(hold_seg) > 0 and hold_seg.High.max() < level + HOLD_PTS \
            and (px0 - hold_seg.Close.iloc[-1]) > 0
    else:
        mfe = float(hold_seg.High.max()) - px0 if len(hold_seg) else np.nan
        mae = px0 - float(hold_seg.Low.min()) if len(hold_seg) else np.nan
        held = len(hold_seg) > 0 and hold_seg.Low.min() > level - HOLD_PTS \
            and (hold_seg.Close.iloc[-1] - px0) > 0
    out.update(mfe_fade=round(mfe, 2), mae_fade=round(mae, 2), held=bool(held))
    return out


def main():
    days = sys.argv[1:] or None
    bars = load_bars()
    ladder = load_ladder()
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "ES1!_mq_levels_history.csv")
    if days:
        bars = bars[bars.day.isin(days)]
    rows = []
    for day, bd in bars.groupby("day"):
        lrow = lv[lv.session_date == day]
        if lrow.empty:
            print(f"!! no MQ levels for {day} — skipped")
            continue
        lrow = lrow.iloc[0]
        ld = ladder[ladder.BarTime.str.startswith(day)]
        # dedupe levels sharing one price (e.g. cr0==gw0) so a touch isn't double-counted
        by_price = {}
        for ltype in LEVEL_COLS:
            level = lrow.get(ltype)
            if pd.isna(level):
                continue
            by_price.setdefault(float(level), []).append(ltype)
        for level, ltypes in by_price.items():
            if not (bd.Low.min() - 10 <= level <= bd.High.max() + 10):
                continue  # level never in play this session
            for touch in touch_episodes(bd, level, ltypes[0]):
                sig = signature(bd, ld, touch, level)
                out = outcomes(bd, touch, level, sig["approach"])
                if out is None:
                    continue
                rows.append(dict(day=day, level_type="+".join(ltypes), level=level,
                                 gex=lrow.get(f"{ltypes[0]}_gex"),
                                 bar_time=touch.BarTime, touch_px=float(touch.Close),
                                 **sig, **out))
    t = pd.DataFrame(rows)
    if t.empty:
        raise SystemExit("no touches found")
    out_csv = FP / "level_touches.csv"
    t.to_csv(out_csv, index=False)

    print(f"=== {len(t)} touch episodes, {t.day.nunique()} sessions -> {out_csv} ===\n")
    print("-- touches by level type --")
    print(t.groupby("level_type").agg(n=("held", "size"), held_rate=("held", "mean"),
                                      ret15=("ret_15m", "mean")).round(3).to_string())
    print("\n-- H2: HVN at level vs not (first touch holds?) --")
    print(t.groupby("hvn_at_level").agg(n=("held", "size"), held_rate=("held", "mean"),
                                        mfe=("mfe_fade", "mean"), mae=("mae_fade", "mean")
                                        ).round(3).to_string())
    print("\n-- H5: absorption on approach vs not --")
    print(t.groupby("absorbing").agg(n=("held", "size"), held_rate=("held", "mean"),
                                     ret15=("ret_15m", "mean")).round(3).to_string())
    print("\n-- H1: session POC just below PS/GW0 (magnet: fwd return toward POC?) --")
    h1 = t[t.level_type.str.contains(r"\b(?:ps|ps0|gw0)\b")]
    print(h1.groupby("poc_just_below").agg(n=("held", "size"), ret5=("ret_5m", "mean"),
                                           ret15=("ret_15m", "mean"),
                                           ret30=("ret_30m", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
