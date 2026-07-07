"""QuantSystems Breakouts — setup detection (headless, sweepable).

Faithful reproduction of Ali Moin-Afshari's **PaintBar `AMA_Breakouts_PB` Ver 5
(Feb 3, 2023)** EasyLanguage source — the authoritative latest. See note 0006
(blueprint/decode) and note 0007 (build/test mechanism).

The indicator emits ONE signal per bar via a sequential pipeline (each stage may
overwrite the prior), then range/IBS filters can zero it. Signal codes mirror the
TS source:  1/-1 = BO (bull/bear),  2/-2 = CX,  3/-3 = OB,  4 = doji OB.
FT bars carry FTflag and are still coded +-1.

Two presets capture the two real use-modes:
  * QSConfig()            -> Ver 5 PAINT defaults: BO only, range filter ON @8
                            (incl. current bar), NO follow-through, NO IBS filter.
                            This is what Ali actually ships/trades.
  * QSConfig.research()  -> whitepaper BO+FT tradeable subset (~5/day, the SQN
                            setup): adds FT (close-beyond) + IBS 69/31 + the
                            time / no-3rd-consecutive execution filters.
  * QSConfig.paintbar_raw() -> everything painted (range filter OFF, all signals).

`detect()` emits the project-standard signal schema consumed by
`simulation_engine.simulate_trades` and the bar-viewer chart:
    SignalNum, SignalType, Direction, DateTime, BarNum, SignalPrice, StopPrice,
    Date, FilterStatus
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

RTH_START = "08:35"   # S60 close labels: first RTH bar is labelled 08:35
RTH_END   = "15:15"   # last bar's close label
SESSION_OPEN_MIN = 8 * 60 + 30


@dataclass
class QSConfig:
    # ── which primitives to emit (Ver 5 input defaults) ──
    use_bo: bool = True            # _ShowBLBO / _ShowBRBO
    use_ob: bool = False           # _ShowOutsideBarsBO
    use_cx: bool = False           # _ShowCX

    # ── PaintBar params ──
    strict_ob: bool = False        # _StrictOB
    cx_factor: float = 1.8         # _CXfactor

    # ── range filter (Ver 5: default ON, lookback 8, AvgRange INCLUDES current) ──
    range_filter_on: bool = True   # _RangeFilter
    range_lookback: int = 8        # _RangeLookBack

    # ── WP detector ABR (detect_wp): prior-N bars, excludes current (page 8) ──
    abr_period: int = 10
    abr_include_current: bool = False

    # ── follow-through (Ver 5: _PaintFTBar default OFF) ──
    require_ft: bool = False        # _PaintFTBar
    ft_must_close_beyond: bool = True   # _FTbarMustCloseBeyond
    ft_must_bo: bool = True         # _FTbarMustBO  (used when close-beyond off)
    ft_bar_not_range_limited: bool = False  # _FTbarNotRangeLimited
    ignore_open_gap: bool = True    # _IgnoreOpenGap (no FT before session open)

    # ── IBS filters (Ver 5: default OFF = -1). Cutoffs applied to the painted bar. ──
    signal_ibs_bull: float = -1.0   # _BLsignalIBS : keep bull BO only if IBS>=this
    signal_ibs_bear: float = -1.0   # _BRsignalIBS : keep bear BO only if IBS<=this
    ft_ibs_bull: float = -1.0       # _BLFTbarIBS
    ft_ibs_bear: float = -1.0       # _BRFTbarIBS
    do_not_ibs_filter_ob: bool = True   # _DoNotIBSfilterOB

    # ── WHITEPAPER (page 8-9) detector cutoffs (used by detect_wp) ──
    bull_bo_ibs: float = 69.0       # breakout bar strong IBS (item 1c / 2b)
    bear_bo_ibs: float = 31.0
    bull_rev_ibs: float = 69.0      # reversal signal bar strong IBS (item 3c; text=69, Fig11=51)
    bear_rev_ibs: float = 31.0

    # ── classification / sizing ──
    big_bar_mult: float = 2.0       # tag a BO as BigBO when range > this*AvgRange
    tag_big_bo: bool = True
    tick_size: float = 0.25

    # ── iStop / R geometry (note §4.2; A5) ──
    stop_basis: str = "signal_range"     # "signal_range" | "combined_range"
    stop_dist_mult: float = 1.0
    small_bar_mult: float = 1.0
    small_bar_stop_mult: float = 2.0
    twobar_stop_mult: float = 2.0
    big_bar_stop_buffer_ticks: int = 2
    use_paper_istop_variants: bool = True

    # ── target ──
    target_r: float = 1.0

    # ── execution filters (note §4.4) ──
    no_third_consecutive: bool = False
    time_filter_on: bool = False
    entry_start_ct: str = "09:10"        # 10:10 ET == 09:10 CT
    sess_open_ct: str = "08:30"
    skip_large_bars: bool = False
    large_bar_pts: float = 20.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def research(cls, **kw) -> "QSConfig":
        """Whitepaper BO+FT tradeable subset (the SQN setup)."""
        base = dict(require_ft=True, ft_must_close_beyond=True,
                    signal_ibs_bull=69.0, signal_ibs_bear=31.0,
                    ft_ibs_bull=69.0, ft_ibs_bear=31.0,
                    time_filter_on=True, no_third_consecutive=True)
        base.update(kw)
        return cls(**base)

    @classmethod
    def paintbar_raw(cls, **kw) -> "QSConfig":
        """Everything painted: range filter OFF, all three signal types on."""
        base = dict(range_filter_on=False, require_ft=False,
                    use_bo=True, use_ob=True, use_cx=True)
        base.update(kw)
        return cls(**base)

    @classmethod
    def wp(cls, **kw) -> "QSConfig":
        """Whitepaper page 8-9 RESEARCH-scope definitions (for detect_wp).
        ABR lookback 10, big bar = 2x ABR(10), IBS 69/31 on BO & Rev signal bars,
        2-bar iStop = 2x combined, the page-16 filters (no-3rd-consecutive, 10:10 ET)."""
        # iStop = 1x the signal-bar range (Ali's worksheet "a.Risk Dist" averaged
        # ~4.74 pt in 2020 low-vol ES = ~1 bar range, NOT the 2x-combined rule).
        base = dict(abr_period=10, abr_include_current=False, big_bar_mult=2.0,
                    bull_bo_ibs=69.0, bear_bo_ibs=31.0,
                    bull_rev_ibs=69.0, bear_rev_ibs=31.0,
                    stop_basis="signal_range", stop_dist_mult=1.0,
                    use_paper_istop_variants=False,
                    time_filter_on=True, no_third_consecutive=True)
        base.update(kw)
        return cls(**base)

    @classmethod
    def paper(cls, **kw) -> "QSConfig":
        """Whitepaper SQN-study detection config (matched to the paper's stated
        frequencies: ~20 signals/day, BO-family ~12% of bars). All three signal
        types ON + IBS 69/31 on the signal bar + ABR(10) range gate + 2-bar FT
        (same-direction, not close-beyond) + 10:10 ET + no-3rd-consecutive.
        (legs-3/4 filter still a placeholder — not yet applied.)"""
        base = dict(
            use_bo=True, use_ob=True, use_cx=True,
            range_filter_on=True, range_lookback=10,
            require_ft=True, ft_must_bo=True, ft_must_close_beyond=False,
            signal_ibs_bull=69.0, signal_ibs_bear=31.0,
            ft_ibs_bull=69.0, ft_ibs_bear=31.0,
            big_bar_mult=1.8,
            time_filter_on=True, no_third_consecutive=True,
        )
        base.update(kw)
        return cls(**base)


# ─────────────────────────── building blocks (note §2) ───────────────────────

def _ibs(h, l, c) -> np.ndarray:
    rng = (h - l).astype(float)
    return np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1.0) * 100.0, 50.0)


def _bardir(o, h, l, c, ibs) -> np.ndarray:
    n = len(c); bd = np.empty(n, dtype=np.int8); prev = 1
    for i in range(n):
        ci, oi, si = c[i], o[i], ibs[i]
        if   ci >  oi and si >= 50: d = 1
        elif ci <  oi and si <= 50: d = -1
        elif ci == oi and si >  50: d = 1
        elif ci == oi and si <  50: d = -1
        elif ci == oi and si == 50: d = prev
        elif ci <  oi and si >  50: d = 1
        elif ci >  oi and si <  50: d = -1
        elif si == 50:              d = prev
        else:                        d = prev
        bd[i] = d; prev = d
    return bd


def _avg_range(rng: np.ndarray, lookback: int) -> np.ndarray:
    """TS Average(BarRange, lookback): simple MA INCLUDING the current bar."""
    return pd.Series(rng, dtype=float).rolling(lookback, min_periods=lookback).mean().to_numpy()


def _outside_bar(h, l, strict: bool) -> np.ndarray:
    Hp, Lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    full = (h > Hp) & (l < Lp)
    if strict:
        return full
    return full | ((h > Hp) & (l == Lp)) | ((h == Hp) & (l < Lp))


def _inside_bar(h, l) -> np.ndarray:
    Hp, Lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    return ((h < Hp) & (l > Lp)) | ((h < Hp) & (l == Lp)) | ((h == Hp) & (l > Lp))


def _prep_session(g: pd.DataFrame, cfg: QSConfig) -> pd.DataFrame:
    g = g.sort_values("DateTime").reset_index(drop=True)
    o = g["Open"].to_numpy(float); h = g["High"].to_numpy(float)
    l = g["Low"].to_numpy(float);  c = g["Close"].to_numpy(float)
    g["Range"]    = h - l
    g["IBS"]      = _ibs(h, l, c)
    g["BarDir"]   = _bardir(o, h, l, c, g["IBS"].to_numpy())
    g["AvgRange"] = _avg_range(g["Range"].to_numpy(), cfg.range_lookback)
    g["OB"]       = _outside_bar(h, l, cfg.strict_ob)
    g["IB"]       = _inside_bar(h, l)
    # S60 close labels: label minutes are +5 vs the old open labels
    mins = g["DateTime"].dt.hour * 60 + g["DateTime"].dt.minute - SESSION_OPEN_MIN
    g["BarNum"] = (mins // 5).astype(int) - 1
    return g


def _stop_price(cfg, direction, entry, rng_sig, rng_bar1, avg, n_bars) -> float:
    base = (rng_sig + rng_bar1) if cfg.stop_basis == "combined_range" else rng_sig
    dist = base * cfg.stop_dist_mult
    if cfg.use_paper_istop_variants:
        if avg and rng_sig > cfg.big_bar_mult * avg:
            dist = rng_sig + cfg.big_bar_stop_buffer_ticks * cfg.tick_size
        elif n_bars == 2:
            dist = cfg.twobar_stop_mult * (rng_sig + rng_bar1)
        elif avg and rng_sig < cfg.small_bar_mult * avg:
            dist = cfg.small_bar_stop_mult * rng_sig
    return entry - dist if direction == 1 else entry + dist


# ─────────────────────────────── detection ───────────────────────────────────

def detect(bars: pd.DataFrame, cfg: QSConfig | None = None) -> pd.DataFrame:
    cfg = cfg or QSConfig()
    df = bars.copy()
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    t = df["DateTime"].dt.strftime("%H:%M")
    df = df[(t >= RTH_START) & (t <= RTH_END)].copy()
    df["Date"] = df["DateTime"].dt.date
    open_min = _hhmm_to_min(cfg.sess_open_ct)
    rows: list[dict] = []

    for date, g in df.groupby("Date", sort=True):
        g = _prep_session(g, cfg)
        H = g["High"].to_numpy(float); L = g["Low"].to_numpy(float)
        O = g["Open"].to_numpy(float); C = g["Close"].to_numpy(float)
        RNG = g["Range"].to_numpy(float); IBS = g["IBS"].to_numpy(float)
        BD = g["BarDir"].to_numpy(); AVG = g["AvgRange"].to_numpy(float)
        OB = g["OB"].to_numpy(bool); IB = g["IB"].to_numpy(bool)
        DT = g["DateTime"].to_numpy(); BN = g["BarNum"].to_numpy(); n = len(g)

        prev_sig = 0       # Signal[1] = prior bar's FINAL signal (post-filter)
        bar1_idx = -1      # index of the BO bar that a FT would follow

        for i in range(1, n):
            sig = 0
            # ── BO (Ver 5: >= / <= and OB-gated) ──
            if cfg.use_bo and not OB[i]:
                if H[i] > H[i-1] and L[i] >= L[i-1]:
                    sig = 1
                elif H[i] <= H[i-1] and L[i] < L[i-1]:
                    sig = -1
            bo_dir = sig

            # ── CX (overwrites; reverts to BO on filter-fail) ──
            if cfg.use_cx:
                boup = H[i] - H[i-1] if H[i] > H[i-1] else 0.0
                bodn = L[i-1] - L[i] if L[i] < L[i-1] else 0.0
                hh = ll = 0.0
                if boup > 0 and bodn == 0:        # BL BO
                    hh, ll = H[i] - H[i-1], L[i] - L[i-1]
                elif boup == 0 and bodn > 0:      # BR BO
                    ll, hh = L[i-1] - L[i], H[i-1] - H[i]
                if hh > ll * cfg.cx_factor:
                    sig = 2
                elif ll > hh * cfg.cx_factor:
                    sig = -2
                if abs(sig) == 2:
                    if IB[i-1] or OB[i] or BD[i] != BD[i-1]:
                        sig = bo_dir
                    elif sig == 2 and C[i] <= H[i-1]:
                        sig = bo_dir
                    elif sig == -2 and C[i] >= L[i-1]:
                        sig = bo_dir

            # ── OB (overwrites) ──
            if cfg.use_ob and OB[i]:
                hh, ll = H[i] - H[i-1], L[i-1] - L[i]
                if hh > ll:   sig = 3
                elif hh < ll: sig = -3
                else:
                    sig = 4 if (C[i] == O[i] and IBS[i] == 50) else (3 if BD[i] == 1 else -3)

            # ── Follow-through (optional) ──
            ftflag = 0
            ft_allowed = (not cfg.ignore_open_gap) or _tod_min(DT[i]) > open_min
            if cfg.require_ft and ft_allowed:
                if cfg.ft_must_close_beyond:
                    if prev_sig > 0 and C[i] > H[i-1]:
                        sig, ftflag = 1, 1
                    elif prev_sig < 0 and C[i] < L[i-1]:
                        sig, ftflag = -1, -1
                    elif BD[i] == prev_sig:
                        if OB[i] and cfg.use_ob:
                            ftflag = 0
                        else:
                            sig, ftflag = 0, 0
                    elif prev_sig > 0 and bo_dir == 1 and C[i] < H[i-1]:
                        sig, ftflag = 0, 0
                    elif prev_sig < 0 and bo_dir == -1 and C[i] > L[i-1]:
                        sig, ftflag = 0, 0
                else:  # ft_must_bo only
                    if prev_sig > 0 and bo_dir == 1:
                        sig, ftflag = 1, 1
                    elif prev_sig < 0 and bo_dir == -1:
                        sig, ftflag = -1, -1
                    elif BD[i] == prev_sig:
                        if OB[i] and cfg.use_ob:
                            ftflag = 0
                        else:
                            sig, ftflag = 0, 0

            # ── Range filter (Ver 5: default ON, applied to this bar) ──
            if cfg.range_filter_on and sig != 0:
                exempt = (cfg.ft_bar_not_range_limited and prev_sig != 0 and BD[i] == prev_sig)
                if not exempt:
                    if not np.isfinite(AVG[i]) or RNG[i] < AVG[i]:
                        sig = 0; ftflag = 0

            # ── IBS filters (optional) ──
            if sig != 0 and not (cfg.do_not_ibs_filter_ob and abs(sig) == 3):
                if cfg.signal_ibs_bull > -1 and sig > 0 and ftflag == 0 and IBS[i] < cfg.signal_ibs_bull:
                    sig = 0
                elif cfg.signal_ibs_bear > -1 and sig < 0 and ftflag == 0 and IBS[i] > cfg.signal_ibs_bear:
                    sig = 0
                elif cfg.ft_ibs_bull > -1 and sig > 0 and ftflag == 1 and IBS[i] < cfg.ft_ibs_bull:
                    sig = 0
                elif cfg.ft_ibs_bear > -1 and sig < 0 and ftflag == -1 and IBS[i] > cfg.ft_ibs_bear:
                    sig = 0

            # ── emit ──
            if sig != 0 and sig != 4:   # skip doji-OB (no tradeable direction)
                direction = 1 if sig > 0 else -1
                stype = _signal_type(sig, ftflag, RNG[i], AVG[i], cfg)
                if ftflag != 0 and bar1_idx >= 0:
                    n_bars, rng_bar1 = 2, RNG[bar1_idx]
                else:
                    n_bars, rng_bar1 = 1, 0.0
                _emit(rows, cfg, stype, direction, i, H, L, C, RNG, AVG, BN, DT,
                      date, n_bars, rng_bar1)

            # carry state
            if bo_dir != 0 and ftflag == 0:
                bar1_idx = i           # this bar is a fresh BO that a FT can follow
            prev_sig = sig

    sig_df = pd.DataFrame(rows)
    if sig_df.empty:
        return _empty_schema()
    sig_df = sig_df.sort_values("DateTime").reset_index(drop=True)
    sig_df = _apply_exec_filters(sig_df, cfg)
    sig_df.insert(0, "SignalNum", range(1, len(sig_df) + 1))
    return sig_df


def _signal_type(sig, ftflag, rng, avg, cfg) -> str:
    if abs(sig) == 3:
        return "OB"
    if abs(sig) == 2:
        return "CX"
    # BO family
    if cfg.tag_big_bo and np.isfinite(avg) and avg > 0 and rng > cfg.big_bar_mult * avg:
        return "BigBO"
    return "BO+FT" if ftflag != 0 else "BO"


def _emit(rows, cfg, stype, direction, i, H, L, C, RNG, AVG, BN, DT, date,
          n_bars, rng_bar1):
    entry = C[i]
    avg = AVG[i] if np.isfinite(AVG[i]) else 0.0
    stop = _stop_price(cfg, direction, entry, RNG[i], rng_bar1, avg, n_bars)
    rows.append({
        "SignalType": stype,
        "Direction": "Long" if direction == 1 else "Short",
        # S60 close labels: the bar label IS the close time — emit it directly
        # (the tick engine fills strictly after it; no look-ahead).
        "DateTime": pd.Timestamp(DT[i]),
        "BarNum": int(BN[i]) + 1,
        "SignalPrice": float(entry),
        "StopPrice": float(stop),
        "Date": date,
        "_dir": direction,
        "_range": float(RNG[i]),
    })


def _apply_exec_filters(sig: pd.DataFrame, cfg: QSConfig) -> pd.DataFrame:
    status = np.array(["ok"] * len(sig), dtype=object)
    if cfg.time_filter_on:
        start_min = _hhmm_to_min(cfg.entry_start_ct)
        close_min = (sig["DateTime"].dt.hour * 60 + sig["DateTime"].dt.minute).to_numpy()  # already close time
        status[close_min < start_min] = "time"
    if cfg.skip_large_bars:
        big = sig["_range"].to_numpy() >= cfg.large_bar_pts
        status[(status == "ok") & big] = "large_bar"
    if cfg.no_third_consecutive:
        pos = {idx: p for p, idx in enumerate(sig.index)}
        for _, idx in sig.groupby("Date").groups.items():
            run = 0; last = 0
            for j in idx:
                d = sig.loc[j, "_dir"]
                run = run + 1 if d == last else 1
                last = d
                if run >= 3 and status[pos[j]] == "ok":
                    status[pos[j]] = "consec3"
    sig = sig.copy()
    sig["FilterStatus"] = status
    return sig.drop(columns=["_dir", "_range"])


def _tod_min(dt64) -> int:
    ts = pd.Timestamp(dt64)
    return ts.hour * 60 + ts.minute


def _hhmm_to_min(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)


def _empty_schema() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "SignalNum", "SignalType", "Direction", "DateTime", "BarNum",
        "SignalPrice", "StopPrice", "Date", "FilterStatus"])


# ════════════════════════════════════════════════════════════════════════════
# WHITEPAPER detector — Ali's page 8-9 "Scope of Research" definitions.
# Distinct from the PaintBar-code detect() above. Produces the three WP-defined
# setups (the paper gives NO mechanical rules for OB/CX — those stay in detect()).
#   1. BO+FT  : breakout bar (1 tick beyond prior bar) + same-direction FT bar;
#               >=1 of the two bars > ABR(10); breakout-bar IBS >=69/<=31.   (item 1)
#   2. BigBO  : a big breakout bar > 2x ABR(10), strong IBS.                  (item 2)
#   3. Rev+FT : 2 bars >= ABR(10) but < 2x (not "breakout-bar big"); bar 2
#               CLOSES beyond bar 1; reversal bar (turns the prior bar's dir),
#               signal IBS >=69/<=31.                                          (item 3)
# Entry = bar-2 CLOSE (BTC). DateTime emitted as the CLOSE time (look-ahead-safe).
# ════════════════════════════════════════════════════════════════════════════

def detect_wp(bars: pd.DataFrame, cfg: QSConfig | None = None) -> pd.DataFrame:
    cfg = cfg or QSConfig.wp()
    df = bars.copy()
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    t = df["DateTime"].dt.strftime("%H:%M")
    df = df[(t >= RTH_START) & (t <= RTH_END)].copy()
    df["Date"] = df["DateTime"].dt.date
    tick = cfg.tick_size
    bbm = cfg.big_bar_mult
    rows: list[dict] = []

    for date, g in df.groupby("Date", sort=True):
        g = g.sort_values("DateTime").reset_index(drop=True)
        O = g["Open"].to_numpy(float); H = g["High"].to_numpy(float)
        L = g["Low"].to_numpy(float);  C = g["Close"].to_numpy(float)
        RNG = H - L
        IBS = _ibs(H, L, C)
        BD = _bardir(O, H, L, C, IBS)
        # ABR(N) over the N bars PRIOR to each bar (causal, excludes current)
        ABR = pd.Series(RNG).shift(1).rolling(cfg.abr_period, min_periods=cfg.abr_period).mean().to_numpy()
        mins = g["DateTime"].dt.hour * 60 + g["DateTime"].dt.minute - SESSION_OPEN_MIN
        BN = (mins // 5).to_numpy() - 1   # S60 close labels: +5m vs open labels
        DT = g["DateTime"].to_numpy()
        n = len(g)

        for i in range(2, n):
            ref = ABR[i - 1]                      # ABR(10) measured before bar 1
            if not np.isfinite(ref) or ref <= 0:
                continue
            r1, r2 = RNG[i - 1], RNG[i]           # bar1 = i-1 (breakout), bar2 = i (FT)

            # ── 2. Big Breakout (1-bar): the signal bar itself is a big breakout ──
            if RNG[i] > bbm * ref:
                if H[i] > H[i - 1] + tick and BD[i] == 1 and IBS[i] >= cfg.bull_bo_ibs:
                    _emit(rows, cfg, "BigBO", 1, i, H, L, C, RNG, ABR, BN, DT, date, 1, 0.0)
                elif L[i] < L[i - 1] - tick and BD[i] == -1 and IBS[i] <= cfg.bear_bo_ibs:
                    _emit(rows, cfg, "BigBO", -1, i, H, L, C, RNG, ABR, BN, DT, date, 1, 0.0)

            # ── 1. Breakout + Follow-Through (2-bar, neither bar "big") ──
            big_either = (r1 > bbm * ref) or (r2 > bbm * ref)
            size_ok = max(r1, r2) > ref
            if not big_either and size_ok:
                # bull: bar1 broke 1 tick above bar0 high, strong, bar2 same dir
                if (H[i - 1] > H[i - 2] + tick and BD[i - 1] == 1
                        and IBS[i - 1] >= cfg.bull_bo_ibs and BD[i] == 1):
                    _emit(rows, cfg, "BO+FT", 1, i, H, L, C, RNG, ABR, BN, DT, date, 2, r1)
                elif (L[i - 1] < L[i - 2] - tick and BD[i - 1] == -1
                      and IBS[i - 1] <= cfg.bear_bo_ibs and BD[i] == -1):
                    _emit(rows, cfg, "BO+FT", -1, i, H, L, C, RNG, ABR, BN, DT, date, 2, r1)

            # ── 3. Reversal + Follow-Through (2-bar; bar2 closes beyond bar1) ──
            # WP item 3 is ambiguous ("≥ABR but not breakout-big"); relaxed to match
            # the paper's count (~6.6/day): ≥1 bar ≥ ABR, reversal context = prior bar
            # opposite OR bar1 poked beyond the prior bar's extreme, FT closes beyond.
            if max(r1, r2) >= ref:
                bull_ctx = (BD[i - 2] == -1) or (L[i - 1] < L[i - 2])
                bear_ctx = (BD[i - 2] == 1) or (H[i - 1] > H[i - 2])
                if (bull_ctx and BD[i - 1] == 1 and IBS[i - 1] >= cfg.bull_rev_ibs
                        and C[i] > H[i - 1]):
                    _emit(rows, cfg, "Rev+FT", 1, i, H, L, C, RNG, ABR, BN, DT, date, 2, r1)
                elif (bear_ctx and BD[i - 1] == -1 and IBS[i - 1] <= cfg.bear_rev_ibs
                      and C[i] < L[i - 1]):
                    _emit(rows, cfg, "Rev+FT", -1, i, H, L, C, RNG, ABR, BN, DT, date, 2, r1)

    sig_df = pd.DataFrame(rows)
    if sig_df.empty:
        return _empty_schema()
    sig_df = sig_df.sort_values("DateTime").reset_index(drop=True)
    sig_df = _apply_exec_filters(sig_df, cfg)
    sig_df.insert(0, "SignalNum", range(1, len(sig_df) + 1))
    return sig_df
