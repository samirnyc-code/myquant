"""S115 killer-day study — COMBINED RULE STACKS per book (ic / puts_band / fly / combined).

Input universe = the single rules that survived train/test on their own across
the five family sweeps (credit / gap-prior / vix / event / cluster / breaker).
This script answers: how much do they add TOGETHER, and which are redundant?

Method
------
1. Re-implement every surviving rule inside ONE composable day-level simulator
   (identical logic to test_credit / test_gap-prior / test_vix / test_event /
   test_cluster / test_breaker; same data, same no-lookahead conventions).
2. Per book, compute each candidate's SOLO train/test delta with this engine,
   rank candidates by solo TEST delta (descending) = "test-period robustness".
3. Greedy stacking: walk the ranked list; simulate current stack + candidate;
   ADD the rule iff its marginal TEST delta > 0, else REJECT it
   (rules_rejected_at_stacking). Scanning continues past a rejection so later
   independent rules still get considered — a redundant rule (marginal <= 0)
   is dropped without blinding us to the rest of the list.
3b. Backward prune: after the greedy pass, iteratively remove any rule whose
   leave-one-rule-out marginal TEST contribution in the final stack is
   negative, or whose TEST marginal is 0 while its TRAIN marginal is negative
   (strictly dominated). Worst first, recomputed after every removal. A rule
   added early on solo strength can be fully superseded by later,
   better-overlapping rules; keeping it would mean recommending a rule that
   HURTS the stack. Pruned rules land in stack_steps with action=PRUNED_POST.
4. For the final stack: leave-one-RULE-out marginals (what each accepted rule
   still contributes given all the others), leave-one-YEAR-out totals (drop
   each year from the measurement, refit nothing), maxDD before/after,
   killer-day table (every day with baseline book P&L < -1500: baseline vs
   stacked P&L).

Composition semantics (per day, per book)
-----------------------------------------
- If ANY accepted day-skip rule (static mask or dynamic stand-down) fires:
  the whole book takes 0 that day.
- Else side/component-drop rules subtract their flagged component
  (ic call leg = eodic_c; fly call side = eodfly_c+openfly_c;
  combined call side = eodic_c+openic_c+eodfly_c+openfly_c; skip_flies_* =
  the fly_pnl component of the combined book).
- Then fomc_close_1230_UPPERBOUND clips a FOMC-day loss to 0 (OPTIMISTIC
  BOUND, carried over verbatim from test_event.py — flagged in output).
- The day-level circuit breaker (MID estimate from test_breaker.py, thr=-1000)
  adds its precomputed per-day MID delta, only on days with no skip, no drop
  and no clip (interactions with partial-day rules are not modelable at day
  level; conservative).
- DYNAMIC rules (loss stand-downs / VIX-recede re-entry / 2-loss cluster) see
  the STACKED realized P&L: a day skipped by another rule produces no loss and
  therefore cannot trigger a stand-down. Skipped sessions still burn cooldown.

Honesty notes
-------------
- Greedy acceptance keyed on marginal TEST delta is itself selection pressure
  on the out-of-sample period; the LOYO table is the check on that.
- fly book: baseline is net-losing, so large deltas are partly "trade less of
  a losing book" beta, exactly as flagged in the family sweeps.

Outputs (all in data/options_sim/backtest_full/killerday/):
  stack_steps_20260910.csv        every candidate in greedy order: solo +
                                  marginal train/test, ADDED/REJECTED
  stack_final_20260910.csv        per book: stack size, train/test/total delta,
                                  baseline, maxDD before/after, killer counts
  stack_rules_20260910.csv        accepted rules + leave-one-rule-out marginals
  stack_killer_days_20260910.csv  every baseline killer day: baseline vs stacked
  stack_loyo_20260910.csv         per book x year: year delta + LOYO total
"""
import os
import numpy as np
import pandas as pd

ROOT = r"C:\Users\Admin\myquant"
BF = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUTDIR = os.path.join(BF, "killerday")
os.makedirs(OUTDIR, exist_ok=True)
STAMP = "20260910"

KILLER = -1500.0
TRAIN_END = pd.Timestamp("2024-12-31")

# ---------------------------------------------------------------- load context
ctx = pd.read_csv(os.path.join(BF, "killer_context.csv"), parse_dates=["date"])
ctx = ctx.sort_values("date").reset_index(drop=True)
for c in ("ic_pnl", "fly_pnl", "puts_band_pnl"):
    ctx[c] = ctx[c].fillna(0.0)
ctx["combined_pnl"] = ctx["ic_pnl"] + ctx["fly_pnl"] + ctx["puts_band_pnl"]
ctx["event"] = ctx["event"].fillna("")
ctx["is_event"] = ctx["event"].str.strip().ne("")
ctx["is_fomc"] = ctx["event"].str.contains("FOMC")
ctx["is_cpi"] = ctx["event"].str.contains("CPI")
ctx["is_nfp"] = ctx["event"].str.contains("NFP")
ctx["total_cr"] = ctx["cr_eodic_c"] + ctx["cr_eodic_p"]          # NaN-propagating (credit family)
ctx["cr_total_fill"] = ctx["cr_eodic_c"].fillna(0.0) + ctx["cr_eodic_p"].fillna(0.0)  # event family
ctx["cum2"] = ctx["prior_ret"] + ctx["prior2_ret"]

# ------------------------------------------------------------- VIX derivations
vix = pd.read_csv(os.path.join(ROOT, "data", "vix_daily.csv"), parse_dates=["date"])
vix = vix.sort_values("date").reset_index(drop=True)
vix["chg"] = vix["close"].diff()
vix["mean5"] = vix["close"].rolling(5).mean()
vix["mean10"] = vix["close"].rolling(10).mean()
vix["chg_prev"] = vix["chg"].shift(1)
vix["accel2"] = vix["chg"] + vix["chg_prev"]
feat = vix[["date", "close", "chg", "chg_prev", "accel2", "mean5", "mean10"]].copy()
feat = feat.rename(columns={c: "v_" + c for c in feat.columns if c != "date"})
ctx = pd.merge_asof(ctx, feat, on="date", direction="backward", allow_exact_matches=False)
ctx["ratio5"] = ctx["v_close"] / ctx["v_mean5"]
ctx["ratio10"] = ctx["v_close"] / ctx["v_mean10"]
chk = ctx.dropna(subset=["vix_prior", "v_close"])
print(f"[check] max |vix_prior - derived prior VIX close| = "
      f"{(chk['vix_prior'] - chk['v_close']).abs().max():.3f} over {len(chk)} days")

N = len(ctx)
DATES = ctx["date"]
TRAIN = (DATES <= TRAIN_END).values
TEST = ~TRAIN

# ------------------------------------------------- per-leg components (rows)
rows = pd.read_csv(os.path.join(BF, "rows.csv"))
ic252 = rows[(rows["method"] == "vix252")].dropna(subset=["pnl"]).copy()
frows = pd.read_csv(os.path.join(BF, "fly_rows.csv")).dropna(subset=["pnl"]).copy()


def day_sum(df, strats):
    s = df[df["strat"].isin(strats)].groupby("date")["pnl"].sum()
    s.index = pd.to_datetime(s.index)
    return s.reindex(DATES).fillna(0.0).values


COMP = {
    "ic_eodic_c": day_sum(ic252, ["eodic_c"]),                     # credit-family call-leg drop
    "ic_callside": day_sum(ic252, ["eodic_c", "openic_c"]),        # event-family call side
    "fly_callside": day_sum(frows, ["eodfly_c", "openfly_c"]),
    "fly_all": ctx["fly_pnl"].values,                              # skip_flies_* on combined
}
COMP["combined_callside"] = COMP["ic_callside"] + COMP["fly_callside"]
ic_leg_check = np.abs(day_sum(ic252, ["eodic_c", "eodic_p", "openic_c", "openic_p"])
                      - ctx["ic_pnl"].values).max()
print(f"[check] ic vix252 4-leg sum vs ic_pnl day col: max abs diff = {ic_leg_check:.2f}")

# ------------------------------------------- circuit-breaker MID delta (thr 1000)
def breaker_mid_delta(trades, thr=1000.0):
    """Per-day MID-scenario delta (mid - baseline), test_breaker.py logic."""
    trades = trades.copy()
    trades["is_stop"] = trades["exit_kind"].astype(str).str.strip() == "stop"
    out = {}
    for date, g in trades.groupby("date"):
        baseline = g["pnl"].sum()
        stops = sorted(g.loc[g["is_stop"], "pnl"].tolist())
        cum, fired = 0.0, False
        for p in stops:
            cum += p
            if cum <= -thr:
                fired = True
                break
        out[date] = (cum - baseline) if fired else 0.0
    s = pd.Series(out)
    s.index = pd.to_datetime(s.index)
    return s.reindex(DATES).fillna(0.0).values


puts_band_trades = ic252[ic252["strat"].isin(["eodic_p", "openic_p"])
                         & (ic252["credit"] >= 0.5) & (ic252["credit"] <= 2.5)]
BRK = {"ic": breaker_mid_delta(ic252), "puts_band": breaker_mid_delta(puts_band_trades)}

# ---------------------------------------------------------------- static masks
def nz(cond):
    return cond.fillna(False).values


c = ctx
MASKS = {
    # credit richness / floors / bands
    "skip_day_if_cr_c>2.0": nz(c["cr_eodic_c"] > 2.0),
    "skip_day_if_cr_c>2.5": nz(c["cr_eodic_c"] > 2.5),
    "skip_day_if_cr_c>3.0": nz(c["cr_eodic_c"] > 3.0),
    "skip_day_if_cr_c>4.0": nz(c["cr_eodic_c"] > 4.0),
    "skip_day_if_cr_p>2.0": nz(c["cr_eodic_p"] > 2.0),
    "skip_day_if_cr_p>2.5": nz(c["cr_eodic_p"] > 2.5),
    "skip_day_if_cr_p>3.0": nz(c["cr_eodic_p"] > 3.0),
    "skip_day_if_cr_p>4.0": nz(c["cr_eodic_p"] > 4.0),
    "skip_day_if_total_cr>3.0": nz(c["total_cr"] > 3.0),
    "skip_day_if_total_cr>4.0": nz(c["total_cr"] > 4.0),
    "skip_day_if_total_cr>5.0": nz(c["total_cr"] > 5.0),
    "skip_day_if_total_cr>6.0": nz(c["total_cr"] > 6.0),
    "band_p_0.5-2.5": nz((c["cr_eodic_p"] < 0.5) | (c["cr_eodic_p"] > 2.5)),
    "band_c_0.5-2.5": nz((c["cr_eodic_c"] < 0.5) | (c["cr_eodic_c"] > 2.5)),
    "skip_day_if_cr_c<0.5": nz(c["cr_eodic_c"] < 0.5),
    "skip_day_if_cr_p<0.5": nz(c["cr_eodic_p"] < 0.5),
    "skip_day_if_total_cr<1.0": nz(c["total_cr"] < 1.0),
    # gap / prior-day
    "|gap|>=0.3": nz(c["gap_pct"].abs() >= 0.3),
    "|gap|>=0.5": nz(c["gap_pct"].abs() >= 0.5),
    "|gap|>=0.75": nz(c["gap_pct"].abs() >= 0.75),
    "|gap|>=1.0": nz(c["gap_pct"].abs() >= 1.0),
    "gap<=-0.5": nz(c["gap_pct"] <= -0.5),
    "gap<=-1.0": nz(c["gap_pct"] <= -1.0),
    "|prior_ret|>=1.0": nz(c["prior_ret"].abs() >= 1.0),
    "|prior_ret|>=1.5": nz(c["prior_ret"].abs() >= 1.5),
    "prior_ret<=-1.0": nz(c["prior_ret"] <= -1.0),
    "prior_ret<=-1.5": nz(c["prior_ret"] <= -1.5),
    "prior_range>=2.0": nz(c["prior_range"] >= 2.0),
    "prior_range>=4.0": nz(c["prior_range"] >= 4.0),
    "|cum2day|>=2.0": nz(c["cum2"].abs() >= 2.0),
    "|cum2day|>=3.0": nz(c["cum2"].abs() >= 3.0),
    "|gap|>=0.5&vixchg>=2": nz((c["gap_pct"].abs() >= 0.5) & (c["vix_chg"] >= 2)),
    "gap<=-0.5&vixchg>=2": nz((c["gap_pct"] <= -0.5) & (c["vix_chg"] >= 2)),
    "prior_range>=3&|gap|>=0.3": nz((c["prior_range"] >= 3) & (c["gap_pct"].abs() >= 0.3)),
    # VIX family
    "skip_vix>25": nz(c["v_close"] > 25),
    "skip_vix>30": nz(c["v_close"] > 30),
    "skip_vixchg>2": nz(c["v_chg"] > 2),
    "skip_vixchg>3": nz(c["v_chg"] > 3),
    "skip_accel2d>3": nz(c["v_accel2"] > 3),
    "skip_accel2d>5": nz(c["v_accel2"] > 5),
    "skip_2day_both_up1": nz((c["v_chg"] > 1) & (c["v_chg_prev"] > 1)),
    "skip_vix/5dma>1.10": nz(c["ratio5"] > 1.10),
    "skip_vix/5dma>1.20": nz(c["ratio5"] > 1.20),
    "skip_vix/10dma>1.15": nz(c["ratio10"] > 1.15),
    "skip_vix/10dma>1.25": nz(c["ratio10"] > 1.25),
    "skip_event&vixchg>2": nz(c["is_event"] & (c["v_chg"] > 2)),
    "skip_event&vix>25": nz(c["is_event"] & (c["v_close"] > 25)),
    "skip_event&vix/5dma>1.10": nz(c["is_event"] & (c["ratio5"] > 1.10)),
    # cluster-family VIX stand-downs (ctx vix_prior variant)
    "vixprior>25_standdown": nz(c["vix_prior"] > 25),
    "vixprior>30_standdown": nz(c["vix_prior"] > 30),
    # event family
    "skip_FOMC": nz(c["is_fomc"]),
    "skip_CPI": nz(c["is_cpi"]),
    "skip_NFP": nz(c["is_nfp"]),
    "skip_ANY_EVENT": nz(c["is_event"]),
}
for T in (2.0, 3.0, 4.0, 5.0, 6.0):
    MASKS[f"skip_event_if_credit_above_{T:g}"] = nz(c["is_event"] & (c["cr_total_fill"] >= T))
    MASKS[f"skip_event_if_credit_below_{T:g}"] = nz(c["is_event"] & (c["cr_total_fill"] < T))

# ------------------------------------------------------------- dynamic rules
class LossStand:
    def __init__(self, X, Ndays):
        self.X, self.N, self.cooldown = X, Ndays, 0

    def skip_today(self, i):
        return self.cooldown > 0

    def end_day(self, traded, pnl):
        if self.cooldown > 0:
            self.cooldown -= 1
            return
        if traded and pnl < self.X:
            self.cooldown = self.N


class LossUntilVixdown:
    def __init__(self, X, vix_chg, cap=5):
        self.X, self.vc, self.cap = X, vix_chg, cap
        self.standing, self.days_out, self._skipped = False, 0, False

    def skip_today(self, i):
        if self.standing:
            if (i > 0 and self.vc[i - 1] < 0) or self.days_out >= self.cap:
                self.standing = False
                return False
            self._skipped = True
            return True
        return False

    def end_day(self, traded, pnl):
        if self._skipped:
            self.days_out += 1
            self._skipped = False
            return
        if traded and pnl < self.X:
            self.standing = True
            self.days_out = 0


class Cluster2:
    def __init__(self, X=-500.0):
        self.X, self.hist = X, []

    def skip_today(self, i):
        if len(self.hist) >= 2 and self.hist[-1] < self.X and self.hist[-2] < self.X:
            self.hist.clear()
            return True
        return False

    def end_day(self, traded, pnl):
        if traded:
            self.hist.append(pnl)


VC = ctx["vix_chg"].fillna(0.0).values

DYN_FACTORY = {
    "loss<-1000_stand2d": lambda: LossStand(-1000.0, 2),
    "loss<-1500_stand2d": lambda: LossStand(-1500.0, 2),
    "loss<-2000_stand1d": lambda: LossStand(-2000.0, 1),
    "loss<-2000_stand2d": lambda: LossStand(-2000.0, 2),
    "loss<-1000_until_vixdown": lambda: LossUntilVixdown(-1000.0, VC),
    "loss<-1500_until_vixdown": lambda: LossUntilVixdown(-1500.0, VC),
    "loss<-2000_until_vixdown": lambda: LossUntilVixdown(-2000.0, VC),
    "cluster_2x_loss<-500": lambda: Cluster2(-500.0),
}

# drop-rule component per book: rule -> {book: component key}
DROPS = {
    "ic_drop_call_leg_if_cr_c>2.0": (MASKS["skip_day_if_cr_c>2.0"], {"ic": "ic_eodic_c"}),
    "ic_drop_call_leg_if_cr_c>2.5": (MASKS["skip_day_if_cr_c>2.5"], {"ic": "ic_eodic_c"}),
    "ic_drop_call_leg_if_cr_c>3.0": (MASKS["skip_day_if_cr_c>3.0"], {"ic": "ic_eodic_c"}),
    "skip_callside_CPI": (nz(c["is_cpi"]), {"fly": "fly_callside",
                                            "combined": "combined_callside"}),
    "skip_flies_FOMC": (nz(c["is_fomc"]), {"combined": "fly_all"}),
    "skip_flies_CPI": (nz(c["is_cpi"]), {"combined": "fly_all"}),
    "skip_flies_NFP": (nz(c["is_nfp"]), {"combined": "fly_all"}),
    "skip_flies_ANY_EVENT": (nz(c["is_event"]), {"combined": "fly_all"}),
}

BOOKS = {"ic": "ic_pnl", "fly": "fly_pnl", "puts_band": "puts_band_pnl",
         "combined": "combined_pnl"}
IS_FOMC = nz(c["is_fomc"])

# ------------------------------------------------- candidate lists (survivors)
CANDIDATES = {
    "ic": [
        "skip_day_if_cr_c>2.0", "skip_day_if_cr_c>2.5", "skip_day_if_cr_c>3.0",
        "skip_day_if_total_cr>3.0", "band_p_0.5-2.5", "skip_day_if_cr_p<0.5",
        "skip_day_if_total_cr<1.0",
        "ic_drop_call_leg_if_cr_c>2.0", "ic_drop_call_leg_if_cr_c>2.5",
        "ic_drop_call_leg_if_cr_c>3.0",
        "|gap|>=1.0", "|gap|>=0.75", "gap<=-1.0",
        "skip_vix>25", "skip_vix>30", "skip_vixchg>2", "skip_accel2d>3",
        "skip_accel2d>5", "skip_vix/5dma>1.10", "skip_vix/5dma>1.20",
        "skip_vix/10dma>1.15", "skip_vix/10dma>1.25", "skip_event&vix>25",
        "skip_FOMC", "skip_NFP", "skip_ANY_EVENT", "fomc_close_1230_UPPERBOUND",
        "skip_event_if_credit_above_2", "skip_event_if_credit_above_3",
        "skip_event_if_credit_above_4", "skip_event_if_credit_below_6",
        "skip_event_if_credit_above_6",
        "loss<-2000_stand2d", "vixprior>25_standdown", "vixprior>30_standdown",
        "loss<-1500_until_vixdown", "loss<-2000_until_vixdown",
        "breaker_-1000_MID",
    ],
    "fly": [
        "skip_day_if_cr_c>2.0", "skip_day_if_cr_p>2.0", "skip_day_if_cr_c>2.5",
        "skip_day_if_cr_p>2.5", "skip_day_if_cr_c>3.0", "skip_day_if_cr_p>3.0",
        "skip_day_if_cr_c>4.0", "skip_day_if_cr_p>4.0",
        "skip_day_if_total_cr>3.0", "skip_day_if_total_cr>4.0",
        "skip_day_if_total_cr>5.0", "skip_day_if_total_cr>6.0",
        "band_p_0.5-2.5", "band_c_0.5-2.5",
        "skip_day_if_cr_c<0.5", "skip_day_if_cr_p<0.5", "skip_day_if_total_cr<1.0",
        "|gap|>=0.3", "|prior_ret|>=1.0", "prior_ret<=-1.0",
        "skip_vix>25", "skip_vix>30", "skip_vixchg>2", "skip_vixchg>3",
        "skip_accel2d>3", "skip_accel2d>5", "skip_2day_both_up1",
        "skip_vix/5dma>1.10", "skip_vix/5dma>1.20", "skip_vix/10dma>1.15",
        "skip_vix/10dma>1.25", "skip_event&vixchg>2", "skip_event&vix>25",
        "skip_event&vix/5dma>1.10",
        "skip_FOMC", "skip_CPI", "skip_NFP", "skip_ANY_EVENT",
        "skip_callside_CPI", "fomc_close_1230_UPPERBOUND",
        "skip_event_if_credit_above_2", "skip_event_if_credit_below_2",
        "skip_event_if_credit_above_3", "skip_event_if_credit_below_4",
        "skip_event_if_credit_above_4", "skip_event_if_credit_below_5",
        "skip_event_if_credit_above_5", "skip_event_if_credit_below_6",
        "skip_event_if_credit_above_6",
        "loss<-1000_stand2d", "loss<-1500_stand2d", "loss<-2000_stand1d",
        "loss<-2000_stand2d", "vixprior>25_standdown", "vixprior>30_standdown",
        "loss<-1000_until_vixdown",
    ],
    "puts_band": [
        "skip_day_if_cr_c>4.0", "skip_day_if_cr_p<0.5", "skip_day_if_total_cr<1.0",
        "prior_range>=4.0", "fomc_close_1230_UPPERBOUND", "breaker_-1000_MID",
    ],
    "combined": [
        "skip_day_if_total_cr>3.0", "skip_day_if_total_cr>4.0",
        "skip_day_if_total_cr>5.0", "skip_day_if_total_cr>6.0",
        "|gap|>=0.5", "|gap|>=0.75", "|gap|>=1.0", "gap<=-0.5",
        "prior_ret<=-1.5", "|prior_ret|>=1.5", "prior_range>=2.0",
        "prior_range>=4.0", "|cum2day|>=2.0", "|cum2day|>=3.0",
        "|gap|>=0.5&vixchg>=2", "gap<=-0.5&vixchg>=2", "prior_range>=3&|gap|>=0.3",
        "skip_vix>25", "skip_vix>30", "skip_vixchg>2", "skip_vixchg>3",
        "skip_accel2d>3", "skip_accel2d>5", "skip_2day_both_up1",
        "skip_vix/5dma>1.10", "skip_vix/5dma>1.20", "skip_vix/10dma>1.15",
        "skip_vix/10dma>1.25", "skip_event&vixchg>2", "skip_event&vix>25",
        "skip_event&vix/5dma>1.10",
        "skip_FOMC", "skip_NFP", "skip_ANY_EVENT", "skip_callside_CPI",
        "skip_flies_FOMC", "skip_flies_CPI", "skip_flies_NFP",
        "skip_flies_ANY_EVENT", "fomc_close_1230_UPPERBOUND",
        "skip_event_if_credit_above_2", "skip_event_if_credit_above_3",
        "skip_event_if_credit_above_4", "skip_event_if_credit_below_5",
        "skip_event_if_credit_above_5", "skip_event_if_credit_below_6",
        "skip_event_if_credit_above_6",
        "loss<-1000_stand2d", "loss<-2000_stand2d", "vixprior>25_standdown",
        "vixprior>30_standdown", "loss<-1500_until_vixdown", "cluster_2x_loss<-500",
    ],
}

# ------------------------------------------------------------------ simulator
def simulate(book, rule_ids):
    """Return the stacked per-day P&L array for `book` under `rule_ids`."""
    base = ctx[BOOKS[book]].values
    static = np.zeros(N, dtype=bool)
    drops, dynamics = [], []
    has_clip = has_brk = False
    for rid in rule_ids:
        if rid in MASKS:
            static |= MASKS[rid]
        elif rid in DROPS:
            mask, comp_by_book = DROPS[rid]
            drops.append((mask, COMP[comp_by_book[book]]))
        elif rid == "fomc_close_1230_UPPERBOUND":
            has_clip = True
        elif rid == "breaker_-1000_MID":
            has_brk = True
        elif rid in DYN_FACTORY:
            dynamics.append(DYN_FACTORY[rid]())
        else:
            raise KeyError(f"unknown rule id: {rid}")
    brk = BRK.get(book) if has_brk else None
    out = np.zeros(N)
    for i in range(N):
        dyn_fire = [d.skip_today(i) for d in dynamics]  # evaluated every day (state)
        skipped = static[i] or any(dyn_fire)
        if skipped:
            out[i] = 0.0
        else:
            p = base[i]
            touched = False
            for mask, compv in drops:
                if mask[i]:
                    p -= compv[i]
                    touched = True
            if has_clip and IS_FOMC[i] and p < 0:
                p = 0.0
                touched = True
            if brk is not None and not touched:
                p += brk[i]
            out[i] = p
        for d in dynamics:
            d.end_day(not skipped, out[i])
    return out


def deltas(book, stacked):
    d = stacked - ctx[BOOKS[book]].values
    return float(d[TRAIN].sum()), float(d[TEST].sum())


def max_drawdown(pnl):
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    return float((peak - eq).max())


# --------------------------------------------------------------- greedy stack
steps_rows, final_rows, rules_rows, killer_rows, loyo_rows = [], [], [], [], []
YEARS = sorted(DATES.dt.year.unique())

for book in ("ic", "puts_band", "fly", "combined"):
    base = ctx[BOOKS[book]].values
    # 1. solo deltas with this engine, rank by solo test delta
    solo = {}
    for rid in CANDIDATES[book]:
        tr, te = deltas(book, simulate(book, [rid]))
        solo[rid] = (tr, te)
    ranked = sorted(CANDIDATES[book], key=lambda r: -solo[r][1])

    # 2. greedy pass
    selected = []
    cur = base.copy()
    cur_tr = cur_te = 0.0
    for rank, rid in enumerate(ranked, 1):
        trial = simulate(book, selected + [rid])
        t_tr, t_te = deltas(book, trial)
        m_tr, m_te = t_tr - cur_tr, t_te - cur_te
        added = m_te > 0
        if added:
            selected.append(rid)
            cur, cur_tr, cur_te = trial, t_tr, t_te
        steps_rows.append(dict(
            book=book, rank=rank, rule=rid,
            solo_train=round(solo[rid][0]), solo_test=round(solo[rid][1]),
            marginal_train=round(m_tr), marginal_test=round(m_te),
            action="ADDED" if added else "REJECTED",
            cum_train=round(cur_tr), cum_test=round(cur_te),
            reject_reason="" if added else "marginal_test<=0 (redundant with stack)"))

    stacked = cur
    tr_delta, te_delta = cur_tr, cur_te

    # 2b. backward prune: drop rules whose leave-one-rule-out TEST marginal is
    # negative in the current stack (worst first, recomputed each removal).
    n_pruned = 0
    while selected:
        loro = []
        for rid in selected:
            rest = [r for r in selected if r != rid]
            r_tr, r_te = deltas(book, simulate(book, rest))
            loro.append((tr_delta - r_tr, te_delta - r_te, rid))
        neg = [x for x in loro if x[1] < 0 or (x[1] <= 0 and x[0] < 0)]
        if not neg:
            break
        m_tr, m_te, worst = min(neg, key=lambda x: (x[1], x[0]))
        selected.remove(worst)
        n_pruned += 1
        stacked = simulate(book, selected)
        tr_delta, te_delta = deltas(book, stacked)
        steps_rows.append(dict(
            book=book, rank=len(ranked) + n_pruned, rule=worst,
            solo_train=round(solo[worst][0]), solo_test=round(solo[worst][1]),
            marginal_train=round(m_tr), marginal_test=round(m_te),
            action="PRUNED_POST",
            cum_train=round(tr_delta), cum_test=round(te_delta),
            reject_reason="negative leave-one-rule-out test marginal in final stack"))

    # 3. leave-one-rule-out marginals on the FINAL (pruned) stack
    for rid in selected:
        rest = [r for r in selected if r != rid]
        r_tr, r_te = deltas(book, simulate(book, rest))
        rules_rows.append(dict(
            book=book, rule=rid,
            solo_train=round(solo[rid][0]), solo_test=round(solo[rid][1]),
            loro_marginal_train=round(tr_delta - r_tr),
            loro_marginal_test=round(te_delta - r_te)))

    # 4. LOYO (measure only, no refit)
    ymask = DATES.dt.year
    d_all = stacked - base
    for y in YEARS:
        my = (ymask == y).values
        y_delta = float(d_all[my].sum())
        loyo_rows.append(dict(
            book=book, year=y,
            year_delta=round(y_delta),
            loyo_total_delta=round(float(d_all.sum()) - y_delta),
            year_baseline=round(float(base[my].sum())),
            year_stacked=round(float(stacked[my].sum()))))

    # 5. killer-day table
    kmask = base < KILLER
    for i in np.flatnonzero(kmask):
        killer_rows.append(dict(
            book=book, date=DATES.iloc[i].date(),
            baseline_pnl=round(float(base[i])), stacked_pnl=round(float(stacked[i])),
            saved=round(float(stacked[i] - base[i])),
            avoided=bool(stacked[i] >= KILLER)))

    final_rows.append(dict(
        book=book, n_rules=len(selected),
        rules=" | ".join(selected),
        baseline_train=round(float(base[TRAIN].sum())),
        baseline_test=round(float(base[TEST].sum())),
        baseline_total=round(float(base.sum())),
        stack_train_delta=round(tr_delta), stack_test_delta=round(te_delta),
        stack_total_delta=round(tr_delta + te_delta),
        stacked_train=round(float(stacked[TRAIN].sum())),
        stacked_test=round(float(stacked[TEST].sum())),
        stacked_total=round(float(stacked.sum())),
        maxDD_baseline=round(max_drawdown(base)),
        maxDD_stacked=round(max_drawdown(stacked)),
        killers_baseline=int((base < KILLER).sum()),
        killers_stacked=int((stacked < KILLER).sum()),
        winners_lost=int(((base > 0) & (stacked <= 0)).sum()),
        days_zeroed=int(((base != 0) & (stacked == 0)).sum()),
        n_rejected_at_greedy=len(ranked) - len(selected) - n_pruned,
        n_pruned_post=n_pruned))

# ------------------------------------------------------------------- outputs
steps = pd.DataFrame(steps_rows)
final = pd.DataFrame(final_rows)
rules = pd.DataFrame(rules_rows)
killers = pd.DataFrame(killer_rows)
loyo = pd.DataFrame(loyo_rows)

paths = {}
for name, df_out in [("stack_steps", steps), ("stack_final", final),
                     ("stack_rules", rules), ("stack_killer_days", killers),
                     ("stack_loyo", loyo)]:
    p = os.path.join(OUTDIR, f"{name}_{STAMP}.csv")
    df_out.to_csv(p, index=False)
    paths[name] = p
    print(f"saved {p} ({len(df_out)} rows)")

pd.set_option("display.width", 260)
print("\n================= FINAL STACKS =================")
print(final.drop(columns=["rules"]).to_string(index=False))
for _, r in final.iterrows():
    print(f"\n{r['book']} stack ({r['n_rules']} rules): {r['rules']}")
print("\n================= LOYO =================")
print(loyo.to_string(index=False))
print("\n================= ACCEPTED RULES (leave-one-rule-out) =================")
print(rules.to_string(index=False))
print("\n================= KILLER DAYS (baseline < -1500) =================")
for book in BOOKS:
    kb = killers[killers["book"] == book]
    if len(kb):
        print(f"\n--- {book}: {len(kb)} killers, {int(kb['avoided'].sum())} avoided ---")
        print(kb.to_string(index=False))
