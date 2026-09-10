"""S115 killer-day study — LIVE-DESK APPLICABILITY AUDIT of every rule claimed
ROBUST in the family sweeps + the test_stack.py candidate universe.

Question audited per rule: could options_gameplan.py (arms premarket) +
options_trigger_daemon.py (fires 08:30 CT, quotes credit BEFORE placing,
60s exit poll with intraday close capability, 14:45 CT time stop) actually
execute it, with every input knowable premarket or at entry?

Verified sources (read 2026-09-10, no ThetaData calls):
  scripts/killer_day_context.py   feature definitions:
      gap_pct   = SPX open vs prior close      -> knowable AT 08:30 fire
      prior_*   = prior-day OHLC               -> knowable premarket
      vix_prior = prior VIX close              -> knowable premarket
      vix_chg   = prior close - close before   -> knowable premarket (NOT same-day)
      cr_eodic_c/p = morning condor fill credits -> knowable AT entry quote
      next_ret  = next-day close               -> LOOKAHEAD (not used by any rule)
  scripts/killerday/test_stack.py  masks: VIX derived features use
      merge_asof(direction="backward", allow_exact_matches=False) -> strictly
      prior-close data; no mask reads same-day close/high/low or next_ret.
      Dynamic rules: end_day() sets cooldown from the day's realized pnl for
      FUTURE days only; LossUntilVixdown re-entry tests vc[i-1] (one-day-stale
      vix_chg = knowable). No lookahead found in any skip path.
  scripts/options_gameplan.py     ENTRY_AT="08:30"; reads data/vix_daily.csv
      (latest_vix); event-aware (gexlog brief, WAIT shifting to 09:05).
  scripts/options_trigger_daemon.py  fire(): 1.QUOTE 2.GATE(broken/thin_credit/
      grade/dedupe) 3.place -> credit knowable BEFORE commitment; manage_open():
      EXIT_POLL=60s, intraday closes (combo/sequential), time_stop 14:45 CT.

Verdict codes
  CONFIRMED  every input knowable in time; executable with at most a small
             config/feature addition to gameplan/daemon
  WEAKENED   rule SHAPE is executable but the TESTED NUMBER is not
             execution-faithful (optimistic bound / fill-assumption dependent)
  (no rule REFUTED: none uses same-day close/high/low/next_ret)

Standing desk policy note (memory: premium-desk-never-block-trades): ALL skip
rules must land advisory-only during fact-finding; this audit rates
executability, not permission to block.

Output: data/options_sim/backtest_full/killerday/live_applicability_20260910.csv
"""
import os
import pandas as pd

ROOT = r"C:\Users\Admin\myquant"
OUTDIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
os.makedirs(OUTDIR, exist_ok=True)
STAMP = "20260910"

# family -> (rules, inputs, when_knowable, verdict, infra_needed)
FAM = [
    ("credit_day_skip",
     ["skip_day_if_cr_c>2.0", "skip_day_if_cr_c>2.5", "skip_day_if_cr_c>3.0",
      "skip_day_if_cr_c>4.0", "skip_day_if_cr_p>2.0", "skip_day_if_cr_p>2.5",
      "skip_day_if_cr_p>3.0", "skip_day_if_cr_p>4.0",
      "skip_day_if_total_cr>3.0", "skip_day_if_total_cr>4.0",
      "skip_day_if_total_cr>5.0", "skip_day_if_total_cr>6.0",
      "skip_day_if_cr_c<0.5", "skip_day_if_cr_p<0.5", "skip_day_if_total_cr<1.0",
      "band_p_0.5-2.5", "band_c_0.5-2.5"],
     "own eodic condor credits (quote at fire)",
     "08:30 entry (daemon already quotes before placing)",
     "CONFIRMED",
     "day-level pre-fire gate stage: quote BOTH condor sides (and for whole-day "
     "skips gate ALL triggers incl. flies/open streams) BEFORE placing any order; "
     "today the quote happens per-trigger inside fire(). Basis note: backtest "
     "credits are ThetaData marks, live gate uses IB quotes - thresholds "
     "transfer approximately."),
    ("credit_leg_drop",
     ["ic_drop_call_leg_if_cr_c>2.0", "ic_drop_call_leg_if_cr_c>2.5",
      "ic_drop_call_leg_if_cr_c>3.0"],
     "own call-spread credit (quote at fire)",
     "08:30 entry",
     "CONFIRMED",
     "trivial: add threshold check in existing gate() for the eodic_c trigger "
     "only - per-trigger quote already exists."),
    ("gap_prior_day",
     ["|gap|>=0.3", "|gap|>=0.5", "|gap|>=0.75", "|gap|>=1.0",
      "gap<=-0.5", "gap<=-1.0", "|prior_ret|>=1.0", "|prior_ret|>=1.5",
      "prior_ret<=-1.0", "prior_ret<=-1.5", "prior_range>=2.0",
      "prior_range>=4.0", "|cum2day|>=2.0", "|cum2day|>=3.0",
      "|gap|>=0.5&vixchg>=2", "gap<=-0.5&vixchg>=2", "prior_range>=3&|gap|>=0.3"],
     "SPX open vs prior close; prior-day OHLC; prior VIX chg",
     "prior-day stats premarket; gap at 08:30 fire (daemon has live spot)",
     "CONFIRMED",
     "daemon needs gap computation at fire: live spot vs stored prior SPX close "
     "(neither is wired today). Minor basis: official SPX open print vs feed "
     "spot at 08:30:00 can differ slightly."),
    ("vix_state",
     ["skip_vix>25", "skip_vix>30", "skip_vixchg>2", "skip_vixchg>3",
      "skip_accel2d>3", "skip_accel2d>5", "skip_2day_both_up1",
      "skip_vix/5dma>1.10", "skip_vix/5dma>1.20", "skip_vix/10dma>1.15",
      "skip_vix/10dma>1.25", "vixprior>25_standdown", "vixprior>30_standdown"],
     "prior VIX closes only (close, chg, 2d accel, 5/10dma ratios)",
     "premarket (gameplan already reads data/vix_daily.csv for EM)",
     "CONFIRMED",
     "gameplan feature block: derive chg/accel2/5dma/10dma from vix_daily.csv "
     "and stamp skip flags into the plan - no new data source. Dependency: "
     "vix_daily.csv must be current each morning (already the EM input)."),
    ("event_calendar",
     ["skip_FOMC", "skip_CPI", "skip_NFP", "skip_ANY_EVENT",
      "skip_callside_CPI", "skip_flies_FOMC", "skip_flies_CPI",
      "skip_flies_NFP", "skip_flies_ANY_EVENT",
      "skip_event&vixchg>2", "skip_event&vix>25", "skip_event&vix/5dma>1.10"],
     "econ calendar (data/econ_calendar_2022_2026.csv) + prior VIX closes",
     "premarket (calendar known days/weeks ahead)",
     "CONFIRMED",
     "gameplan reads the calendar file (today event info comes via gexlog "
     "brief, advisory event_gate); component skips = simply do not arm those "
     "triggers. Maintenance: calendar file ends 2026 - needs yearly refresh."),
    ("event_x_credit",
     ["skip_event_if_credit_above_2", "skip_event_if_credit_above_3",
      "skip_event_if_credit_above_4", "skip_event_if_credit_above_5",
      "skip_event_if_credit_above_6", "skip_event_if_credit_below_2",
      "skip_event_if_credit_below_4", "skip_event_if_credit_below_5",
      "skip_event_if_credit_below_6"],
     "econ calendar premarket + total condor credit at entry",
     "08:30 entry",
     "CONFIRMED",
     "same both-sides pre-fire quote stage as credit_day_skip. Sim detail: "
     "cr_total_fill uses fillna(0), so a day with NO condor fill counts as "
     "'below' - live equivalent (quote failure) is no-trade anyway; define "
     "explicitly when building."),
    ("loss_standdown",
     ["loss<-1000_stand2d", "loss<-1500_stand2d", "loss<-2000_stand1d",
      "loss<-2000_stand2d", "cluster_2x_loss<-500"],
     "PRIOR days' realized book P&L (trade log / daily_summary)",
     "premarket (yesterday's P&L is settled by evening)",
     "CONFIRMED",
     "gameplan needs: read prior-day realized P&L per book + persist a cooldown "
     "state file across days (none exists). Calibration caveat: thresholds were "
     "fit on backtest P&L basis (sim fills+fees), live basis differs - map "
     "before arming. Book defs must match (ic=vix252 4 streams; puts_band= "
     "put legs with own credit 0.5-2.5, computable at entry)."),
    ("loss_standdown_vix_reentry",
     ["loss<-1000_until_vixdown", "loss<-1500_until_vixdown",
      "loss<-2000_until_vixdown"],
     "prior realized P&L + prior VIX chg (sim tests vc[i-1] = one-day-stale)",
     "premarket",
     "CONFIRMED",
     "same state-file build as loss_standdown; replicate the sim's exact "
     "staleness (vc[i-1], 5-day cap) or re-test - the live-obvious 'yesterday's "
     "vix_chg' is one day FRESHER than what was backtested."),
    ("fomc_1230_close",
     ["fomc_close_1230_UPPERBOUND"],
     "FOMC date premarket + a 12:30 CT clock",
     "12:30 CT intraday",
     "WEAKENED",
     "mechanically buildable today (daemon time_stop pattern + intraday close "
     "infra exist - set FOMC-day time_stop 12:30). BUT the tested number is an "
     "admitted OPTIMISTIC BOUND: it clips every FOMC-day loss to exactly $0, "
     "i.e. assumes a breakeven exit wherever the market is at 12:30. Real "
     "12:30-mark repricing was never computed. Do NOT adopt on this number; "
     "run the 12:30 reprice study first (needs ThetaData - not tonight)."),
    ("day_pnl_breaker",
     ["breaker_-1000_MID",
      "flatten at day P&L <= -1000 (MID est; OPT +38987/+30702, PESS -16435/-6380)",
      "flatten at day P&L <= -1000 (MID; OPT +6799/+7685, PESS -47/0)"],
     "live aggregated day P&L across open positions (marks every poll)",
     "intraday, continuous",
     "WEAKENED",
     "needs NEW infra: daemon aggregates all open-position marks each EXIT_POLL "
     "and flattens everything at <= -1000 (close capability exists; the "
     "aggregation/breaker logic does not). Tested value is NOT execution-"
     "faithful: MID realizes stops WORST-FIRST (not chronological) and the "
     "PESS bound is NEGATIVE for ic (-16435/-6380) - edge sign depends on fill "
     "assumption. puts_band PESS ~0 (-47/0) is safer but small. Re-sim "
     "chronologically at tick level before trusting the delta."),
]

rows = []
for fam, rules, inputs, when, verdict, infra in FAM:
    for r in sorted(set(rules)):
        rows.append(dict(family=fam, rule=r, inputs=inputs,
                         knowable_when=when, verdict=verdict,
                         lookahead="NONE" if verdict == "CONFIRMED"
                         else "modeled-payoff not execution-faithful",
                         infra_needed=infra))

df = pd.DataFrame(rows)
out = os.path.join(OUTDIR, f"live_applicability_{STAMP}.csv")
df.to_csv(out, index=False)
print(f"saved {out} ({len(df)} rules audited)")
print(df.groupby(["verdict", "family"])["rule"].count().to_string())
