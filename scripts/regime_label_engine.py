"""regime_label_engine.py — reusable per-5M-bar regime labeler.

A faithful, class-encapsulated port of the tick-driven phase machine v4
(`scratchpad/regime_phase_machine.py`) — the "latest regime engine with the
fast flip and the second-entry bells and whistles" (wick/tick break, immediate
flip, one-candidate pullback promotion). The standalone script is a single-day
module-level program; this wraps the SAME logic (verbatim add_pivot /
start_trend / terminate / tick loop) in a class so it can run over many days and
emit a recordable per-bar regime label.

Self-test (`python scripts/regime_label_engine.py`) replays the two
user-validated teaching days and asserts the known pivot counts
(2022-02-24 → 35, 2022-04-12 → 36). If those match, the port is in lockstep
with the validated standalone.

`label_day(g, tk)` returns a DataFrame indexed by bar number with the regime
active at each bar's CLOSE (`neutral`/`bull`/`bear`) — causal (known at that
bar close) and suitable as an entry filter.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]


class RegimeMachine:
    """One instance per trading day. Drives the phase machine on the day's
    ticks and records the regime mode at every bar close."""

    def __init__(self, g: pd.DataFrame, tk: pd.DataFrame):
        self.g = g.reset_index(drop=True)
        self.O, self.H, self.L, self.C = (
            self.g[c].to_numpy() for c in ["Open", "High", "Low", "Close"])
        self.n = len(self.g)
        tk = tk.sort_values("DateTime")
        self.tbar = np.searchsorted(
            self.g["DateTime"].values, tk["DateTime"].values, side="right") - 1
        self.tP = tk["Price"].to_numpy()

        # ---- machine state (verbatim from the standalone) ----
        self.piv = []
        self.log = []
        self.trend_starts = []
        self.terms = []
        self.transitions = []          # (bar, "start"|"term", side) in firing order
        self.prevH = self.prevL = 0
        self.first_pivot_done = False
        self.mode = "NEUTRAL"
        self.standing = None
        self.run_b = None
        self.run_px = None
        self.cand = None
        self.neu_start = 0
        self.hi_p = None
        self.lo_p = None
        self.lsh = None
        self.lsl = None
        self.has_hl = False
        self.has_lh = False
        self.struct_hl = None
        self.struct_lh = None
        # leg tracking (tick loop locals in the standalone)
        self.d = None
        self.leg_px = None
        self.leg_bar = None
        # per-bar regime at close
        self.bar_mode = ["neutral"] * self.n

    # -------------------------------------------------------------- add_pivot
    def add_pivot(self, bar, side, emit):
        H, L = self.H, self.L
        if side == "H":
            t = "hh" if H[bar] > H[self.prevH] else ("lh" if H[bar] < H[self.prevH] else "dh")
            self.prevH = bar
        else:
            t = "hl" if L[bar] > L[self.prevL] else ("ll" if L[bar] < L[self.prevL] else "dl")
            self.prevL = bar
        disp = side if not self.first_pivot_done else t
        self.first_pivot_done = True
        p = dict(bar=bar, side=side, tag=t, disp=disp, conf=emit,
                 intrabar=(emit == bar), major=None, majlab=None)
        self.piv.append(p)
        if side == "H":
            self.lsh = p
            if self.hi_p is None or H[bar] > H[self.hi_p["bar"]]:
                self.hi_p = p
            if t == "lh" or len(disp) == 1:
                self.has_lh = True
                self.struct_lh = p
        else:
            self.lsl = p
            if self.lo_p is None or L[bar] < L[self.lo_p["bar"]]:
                self.lo_p = p
            if t == "hl" or len(disp) == 1:
                self.has_hl = True
                self.struct_hl = p
        if self.mode == "BULL" and side == "L":
            if self.cand is None or L[bar] < L[self.cand["p"]["bar"]]:
                self.cand = dict(p=p, ref_px=self.run_px)
        elif self.mode == "BEAR" and side == "H":
            if self.cand is None or H[bar] > H[self.cand["p"]["bar"]]:
                self.cand = dict(p=p, ref_px=self.run_px)
        if self.mode == "BULL" and side == "H" and bar == self.run_b:
            p["major"] = emit
            p["majlab"] = "HH"
        elif self.mode == "BEAR" and side == "L" and bar == self.run_b:
            p["major"] = emit
            p["majlab"] = "LL"
        return p

    # ------------------------------------------------------------ start_trend
    def start_trend(self, up, b, px):
        H, L = self.H, self.L
        side = "bull" if up else "bear"
        broken = self.lsh if up else self.lsl
        partner = self.struct_hl if up else self.struct_lh
        opp = self.lo_p if up else self.hi_p
        broken["major"] = b
        broken["majlab"] = "HH" if up else "LL"
        if partner is not None and partner["major"] is None:
            partner["major"] = b
            partner["majlab"] = (partner["disp"] if len(partner["disp"]) == 1
                                 else ("HL" if up else "LH"))
        if opp is not None and opp is not partner and opp["major"] is None:
            opp["major"] = b
            opp["majlab"] = (opp["disp"] if len(opp["disp"]) == 1 else opp["tag"].upper())
        self.trend_starts.append((b, side, broken["bar"]))
        self.transitions.append((b, "start", side))
        self.standing = None
        if partner is not None:
            self.standing = (partner["bar"], L[partner["bar"]] if up else H[partner["bar"]])
        self.run_b, self.run_px = b, px
        self.mode = "BULL" if up else "BEAR"
        self.cand = None
        self.hi_p = self.lo_p = self.lsh = self.lsl = None
        self.has_hl = self.has_lh = False
        self.struct_hl = self.struct_lh = None

    # -------------------------------------------------------------- terminate
    def terminate(self, b, px):
        H, L = self.H, self.L
        was_bull = (self.mode == "BULL")
        self.terms.append((self.standing[0], self.standing[1], b, self.mode.lower()))
        self.transitions.append((b, "term", self.mode.lower()))
        flip_up = ((not was_bull) and self.lsh is not None and px > H[self.lsh["bar"]]
                   and self.has_hl and self.struct_hl is not None
                   and self.struct_hl["bar"] > self.lsh["bar"])
        flip_dn = (was_bull and self.lsl is not None and px < L[self.lsl["bar"]]
                   and self.has_lh and self.struct_lh is not None
                   and self.struct_lh["bar"] > self.lsl["bar"])
        self.mode = "NEUTRAL"
        self.neu_start = b
        self.cand = None
        self.standing = None
        self.run_b = self.run_px = None
        if flip_up or flip_dn:
            self.start_trend(flip_up, b, px)
        else:
            self.hi_p = self.lo_p = self.lsh = self.lsl = None
            self.has_hl = self.has_lh = False
            self.struct_hl = self.struct_lh = None

    # ------------------------------------------------------------------- run
    def run(self):
        H, L, tP, tbar, n = self.H, self.L, self.tP, self.tbar, self.n
        cur_bar = -1
        up_done = dn_done = True
        for _t in range(len(tP)):
            b = int(tbar[_t])
            if b < 1 or b >= n:
                continue
            px = tP[_t]
            if b != cur_bar:
                # the bar we are leaving is fully processed → stamp its close mode
                if cur_bar >= 0:
                    self.bar_mode[cur_bar] = self.mode.lower()
                cur_bar = b
                up_done = dn_done = False
            if self.d == 1 and (self.leg_px is None or px > self.leg_px):
                self.leg_px, self.leg_bar = px, b
            if self.d == -1 and (self.leg_px is None or px < self.leg_px):
                self.leg_px, self.leg_bar = px, b
            if not up_done and px > H[b - 1]:
                up_done = True
                if self.d == -1:
                    self.add_pivot(self.leg_bar, "L", b)
                    self.d = 1
                    self.leg_px, self.leg_bar = px, b
                elif self.d is None:
                    self.d = 1
                    self.leg_px, self.leg_bar = px, b
            if not dn_done and px < L[b - 1]:
                dn_done = True
                if self.d == 1:
                    self.add_pivot(self.leg_bar, "H", b)
                    self.d = -1
                    self.leg_px, self.leg_bar = px, b
                elif self.d is None:
                    self.d = -1
                    self.leg_px, self.leg_bar = px, b
            if self.mode == "NEUTRAL":
                if self.lsh is not None and px > H[self.lsh["bar"]] and self.has_hl:
                    self.start_trend(True, b, px)
                elif self.lsl is not None and px < L[self.lsl["bar"]] and self.has_lh:
                    self.start_trend(False, b, px)
            else:
                if self.cand is not None and self.cand["ref_px"] is not None:
                    hit = (px > self.cand["ref_px"] if self.mode == "BULL"
                           else px < self.cand["ref_px"])
                    if hit:
                        q = self.cand["p"]
                        q["major"] = b
                        q["majlab"] = "HL" if self.mode == "BULL" else "LH"
                        self.standing = (q["bar"],
                                         L[q["bar"]] if self.mode == "BULL" else H[q["bar"]])
                        self.cand = None
                if self.mode == "BULL" and px > self.run_px:
                    self.run_b, self.run_px = b, px
                if self.mode == "BEAR" and px < self.run_px:
                    self.run_b, self.run_px = b, px
                if self.standing is not None:
                    if ((self.mode == "BULL" and px < self.standing[1])
                            or (self.mode == "BEAR" and px > self.standing[1])):
                        self.terminate(b, px)
        # stamp the final bar touched
        if cur_bar >= 0:
            self.bar_mode[cur_bar] = self.mode.lower()
        # forward-fill regime across bars that saw no qualifying tick (state persists)
        last = "neutral"
        for i in range(n):
            if self.bar_mode[i] is None:
                self.bar_mode[i] = last
            else:
                last = self.bar_mode[i]
        return self


def label_day(g: pd.DataFrame, tk: pd.DataFrame) -> pd.DataFrame:
    """Per-bar regime at close for one day. Returns a frame with columns
    ['bar', 'DateTime', 'regime'] (regime in {neutral,bull,bear})."""
    m = RegimeMachine(g, tk).run()
    return pd.DataFrame({
        "bar": np.arange(m.n),
        "DateTime": m.g["DateTime"].to_numpy(),
        "regime": m.bar_mode,
    })


def _selftest():
    import massive
    B = pd.read_parquet(_ROOT / "data" / "bars" / "_continuous.parquet")
    B["Date"] = B["DateTime"].dt.date.astype(str)
    expect = {"2022-02-24": 35, "2022-04-12": 36}
    ok = True
    for day, want in expect.items():
        g = B[B["Date"] == day].sort_values("DateTime").reset_index(drop=True)
        tk = massive.load_continuous_ticks(date.fromisoformat(day))
        m = RegimeMachine(g, tk).run()
        got = len(m.piv)
        starts = [(sb, sd) for sb, sd, _ in m.trend_starts]
        status = "OK" if got == want else "MISMATCH"
        if got != want:
            ok = False
        print(f"{day}: pivots={got} (want {want}) [{status}]  "
              f"trend_starts={[(b+1, s) for b, s in starts]}")
        # regime segment summary
        seg = pd.Series(m.bar_mode)
        counts = seg.value_counts().to_dict()
        print(f"   bar-regime counts: {counts}")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT))
    _selftest()
