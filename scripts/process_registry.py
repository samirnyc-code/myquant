"""process_registry.py — the trading day as a chronological list of automated processes.

One entry per automated step: when it runs (CHICAGO time — the exchange clock, not this PC's
Berlin clock), what it does, WHY it exists, what it writes, and what consumes that output.

The "why" and "downstream" fields are the point. A schedule tells you a job ran; it does not
tell you whether the data it produced still feeds anything. Several of these exist only to
capture data whose retention window is short (MenthorQ is today-only for several surfaces,
NT8 has no historical depth at all) — that context is invisible in Task Scheduler and is
exactly what gets forgotten.

Consumed by scripts/launcher.py (Mission Control /timeline).
"""
from __future__ import annotations

# phase -> ordering on the page; each is one tile group
PHASES = [
    ("overnight", "Overnight — archive while the market is shut"),
    ("preopen",   "Pre-open — get the desk armed before 08:30 CT"),
    ("session",   "Session — live, running all day"),
    ("close",     "Close — reconcile and learn"),
]

# ct     : Chicago time the step is meant to run ("cont" = continuous)
# task   : Windows scheduled-task name (None = not scheduled / runs inside NT8)
# health : matching check name in pipeline_health, if any
PROCESSES = [
    # ---------------------------------------------------------------- overnight
    dict(id="mq_mine", phase="overnight", ct="07:30", task="MyQuant MQ Mine",
         title="MenthorQ full-surface mine",
         script="scripts/mq_mine.py",
         what="Archives EVERYTHING MenthorQ exposes for ~25 tickers: levels, matrix, "
              "per-strike, gamma-insights, vol, Q-score, swing.",
         why="MQ's retention is thin — futures ~2yr, and the Matrix / per-strike / levels "
             "surfaces are TODAY-ONLY. Whatever is not captured today is gone permanently. "
             "This is the single most time-critical archive job we run.",
         writes="data/menthorq/mine/raw/…",
         downstream="Every gamma-level study; the ~5yr levels DB; future GEX research that "
                    "does not exist yet — which is the whole point of hoarding it."),

    dict(id="mq_harvest", phase="overnight", ct="15:45", task="MyQuant MQ Harvest",
         title="MenthorQ dashboard harvest",
         script="scripts/mq_harvest.py",
         what="Playwright session replays the MQ dashboard per symbol × page and captures "
              "the rendered data.",
         why="Covers surfaces the direct API does not expose. Uses the saved auth_state.json "
             "from the S66 scraper.",
         writes="data/menthorq/harvest/YYYY-MM-DD/",
         downstream="Cross-check against the API pull; fills gaps the REST endpoints miss."),

    dict(id="quin", phase="overnight", ct="16:00", task="MyQuant QUIN Harvest",
         title="QUIN AI harvest",
         script="scripts/mq_quin_harvest.py",
         what="Asks MenthorQ's in-app AI for a gamma-levels table + top-10 GEX strikes per "
              "symbol and parses the answer into JSON.",
         why="QUIN can answer things no endpoint returns. Quota-limited, so it runs last.",
         writes="data/menthorq/harvest/YYYY-MM-DD/quin_<SYM>.json",
         downstream="Supplementary only — mq_levels_fetch replaced it as the primary source."),

    dict(id="levels_db", phase="overnight", ct="16:15", task="MyQuant Levels DB",
         title="Levels DB + viewer",
         script="scripts/mq_levels_db.py",
         what="Pulls today's full level set for every tracked ticker and rebuilds the "
              "browsable HTML viewer.",
         why="QUIN-free (direct API, no quota). This is the ~5-year levels database that "
             "every level study is built on.",
         writes="data/menthorq/levels_db.csv · levels_db.html",
         downstream="Gamma Levels Command Center; all level-touch and fade research."),

    dict(id="catalog", phase="overnight", ct="20:30", task="MyQuant Data Catalog Scan",
         title="Data catalog scan",
         script="scripts/data_catalog.py scan",
         what="Walks every data family and records size, freshness and health.",
         why="The data/ tree is ~110GB and must never be blind-walked on page load, so the "
             "scan is nightly and the page reads the cached registry.",
         writes="data/_catalog/manifest.json",
         downstream="Data Catalog dashboard (:8620) and the Library page."),

    # ---------------------------------------------------------------- pre-open
    dict(id="watchdog", phase="preopen", ct="07:45", task="MyQuant Desk Watchdog",
         title="Desk watchdog",
         script="scripts/desk_watchdog.py",
         health="Options sim",
         what="Guards the desk: restarts the feed and sampler if they die.",
         why="Built after 7/17, when a midday IB drop killed spot_feed at 12:59 ET, hung the "
             "sim daemon's sampler, and NOTHING noticed for 36 minutes because the health "
             "check only ran once at 08:40.",
         writes="data/_catalog/logs/desk_watchdog.log",
         downstream="Keeps every session-phase process alive."),

    dict(id="gw_login", phase="preopen", ct="08:00", task="MyQuant Gateway Login",
         title="IB Gateway login",
         script="C:/IBC/StartGateway.bat",
         health="IB gateway",
         what="IBC launches IB Gateway and signs in (paper).",
         why="Everything option-priced depends on it.",
         writes="—",
         downstream="Sim daemon, marks, spot feed, dashboard, EOD report."),

    dict(id="watchdog_live", phase="preopen", ct="08:12", task="MyQuant Desk Watchdog Live",
         title="Desk watchdog (daemon)",
         script="scripts/desk_watchdog.py --daemon",
         what="Same guard, now resident for the session.",
         why="The one-shot at 07:45 cannot catch a midday failure.",
         writes="data/_catalog/logs/desk_watchdog.log",
         downstream="Continuous supervision of the desk."),

    dict(id="backtest_levels", phase="preopen", ct="08:15", task="MyQuant Backtest Levels",
         title="Backtest-tile scrape",
         script="gamma_tracker/scrape.py run",
         what="Pulls MenthorQ's Backtest tile values.",
         why="Their published level performance — used to sanity-check our own results "
             "against the vendor's claims.",
         writes="gamma_tracker/…",
         downstream="Level-study validation."),

    dict(id="levels_history", phase="preopen", ct="08:17", task="MyQuant Levels History",
         title="Levels history backfill",
         script="scripts/mq_levels_backfill_batch.py --recent 10",
         what="Batched multi-ticker gamma-levels backfill, up to 5 tickers per request.",
         why="Fills any gap the nightly capture missed, ~5× fewer API calls than one-by-one.",
         writes="data/menthorq/*_mq_levels_history.csv",
         downstream="The levels DB and every historical level study."),

    dict(id="gw_ensure", phase="preopen", ct="08:20", task="MyQuant Gateway Ensure",
         title="Gateway ensure (API port)",
         script="scripts/gateway_ensure.py",
         health="IB gateway",
         what="Verifies the API port 4002 actually answers; relaunches IBC if not.",
         why="**Logged in ≠ API up.** On 7/16 Gateway showed connected while 4002 was dead "
             "and the whole morning chain silently no-oped. Only a socket connect proves it.",
         writes="—",
         downstream="Hard gate for everything that follows."),

    dict(id="dashboard", phase="preopen", ct="08:25", task="MyQuant Dashboard",
         title="Options desk server",
         script="scripts/options_dashboard_live.py",
         what="Serves the live options dashboard on :8600 and keeps it regenerating.",
         why="The desk must be viewable without Claude or a terminal open.",
         writes="data/options_sim/dashboard.html",
         downstream="The desk UI, and the remote read-only viewer."),

    dict(id="spot_feed", phase="preopen", ct="08:26", task="MyQuant Spot Feed",
         title="Spot feed (SPX/ES/VIX)",
         script="scripts/spot_feed.py",
         health="Options sim",
         what="Every ~5s writes SPX, VIX, ES estimate and basis.",
         why="The single live-price source the trigger daemon and dashboard both read. If it "
             "dies, triggers stop firing silently — the 7/17 failure.",
         writes="data/options_sim/live.json",
         downstream="Trigger daemon, dashboard tiles, levels engine."),

    dict(id="marks", phase="preopen", ct="08:26", task="MyQuant Marks Watch",
         title="Position marking",
         script="scripts/options_mark.py --watch 120",
         what="Quotes every leg of every open trade at realtime OPRA and values the position "
              "at mid, every 2 minutes.",
         why="Live P&L, POP and EV on the desk. Verified live: 7/17 produced 202 marks with "
             "151 distinct spots and 0.10–0.15 spreads.",
         writes="data/options_sim/marks.csv · trade_metrics.csv",
         downstream="Desk P&L tiles, EOD report, the trade journal."),

    dict(id="levels_fetch", phase="preopen", ct="08:27", task="MyQuant Levels Fetch",
         title="Today's MQ levels",
         script="scripts/mq_levels_fetch.py",
         what="Direct-API pull of today's gamma levels in the shape the gameplan reads.",
         why="Replaced the dead QUIN harvester as the primary path — same data, no quota.",
         writes="scratchpad/mq_levels_today.json",
         downstream="Gameplan, levels engine, the desk's level rail."),

    dict(id="gameplan", phase="preopen", ct="08:28", task="MyQuant Gameplan",
         title="Premarket gameplan",
         script="scripts/options_gameplan.py",
         what="Turns EOD gamma levels + a pre-open spot snapshot into a committed set of "
              "ARMED TRIGGERS, one per setup/scenario.",
         why="Decisions are committed BEFORE the session so the day cannot be rationalised "
             "afterwards. The postmortem grades reality against this file.",
         writes="data/options_sim/gameplan_YYYYMMDD.json",
         downstream="Trigger daemon executes it; postmortem scores it."),

    dict(id="sim_daemon", phase="preopen", ct="08:28", task="MyQuant Sim Daemon",
         title="OPRA forward-sim daemon",
         script="scripts/options_sim_daemon.py",
         health="Options sim",
         what="Runs the causal 15:59 BPS rule live against real OPRA quotes.",
         why="Mirrors mr_bps_causal_1559.py — the only backtest we consider honest. Forward "
             "testing it live is what turns a backtest into evidence.",
         writes="data/options_sim/decisions.csv",
         downstream="Forward-test record for the BPS rule."),

    dict(id="levels_engine", phase="preopen", ct="08:32", task="MyQuant Levels Engine",
         title="Level-fade engine (ES)",
         script="scripts/levels_live_engine.py",
         what="Arms the three validated first-touch fades (CR / CR0 / PS0) on ES.",
         why="Forward test of the fades from note 0016. Live, unmodified, so the sample is "
             "honest.",
         writes="data/options_sim/levels_engine_log.csv",
         downstream="Fade-suite forward-test record."),

    dict(id="trigger_daemon", phase="preopen", ct="08:33", task="MyQuant Trigger Daemon",
         title="Trigger daemon (to 15:00 CT)",
         script="scripts/options_trigger_daemon.py --until 15:00",
         what="Watches live.json and auto-executes each armed gameplan trigger the instant "
              "its condition is met.",
         why="Removes discretion from execution. Stops at 15:00 CT — the prop flat-by rule.",
         writes="data/options_log/trades.parquet",
         downstream="The trade log, the desk, the postmortem."),

    dict(id="scanner", phase="preopen", ct="08:35", task="MyQuant Gamma Scanner",
         title="Cross-symbol gamma scanner",
         script="scripts/options_gamma_scanner.py",
         what="Net/abs GEX, walls and dominant expiry across a universe of liquid names; "
              "ranks pin vs momentum regimes.",
         why="Our own MenthorQ-style screener — finds where the gamma setup is best today "
             "rather than assuming SPX.",
         writes="data/options_sim/scanner_YYYYMMDD.json",
         downstream="Symbol selection for the desk."),

    dict(id="healthcheck", phase="preopen", ct="08:40", task="MyQuant Health Check",
         title="Morning health check",
         script="scripts/options_healthcheck.py",
         what="Verifies the whole 08:00–08:35 chain actually came up.",
         why="Turn silent failures loud. Its weakness — running ONCE — is what the resident "
             "watchdog and the status light now cover.",
         writes="—",
         downstream="Desktop/email alert."),

    # ---------------------------------------------------------------- session
    dict(id="depth", phase="session", ct="cont", task=None,
         title="L2 depth + tape recorder",
         script="nt8/strategies/MarketDepthRecorder.cs",
         health="L2 depth",
         what="Records every order-book add/update/remove plus the interleaved trade tape, "
              "on one clock, to a daily CSV.",
         why="**The only truly irreplaceable dataset here.** NT8 stores no historical depth "
             "and no vendor sells it cheaply — resting liquidity exists only in the moment. "
             "Every minute not recorded is gone forever.",
         writes="data/depth/ES_depth_YYYY-MM-DD.csv",
         downstream="Iceberg / absorption / DOM-pressure research — and ANY footprint "
                    "timeframe, since the tape is a superset."),

    dict(id="footprint", phase="session", ct="cont", task=None,
         title="Footprint exporter",
         script="nt8/indicators/FootprintExporter.cs",
         health="Footprint",
         what="Reconstructs the bid/ask footprint ladder per bar from ticks.",
         why="Validated EXACT against MzPack (zero error on delta/buy%/POC), which is why we "
             "never bought their €599 suite.",
         writes="data/footprint/ES_<series>_footprint_<stamp>.csv",
         downstream="footprint_metrics.py → POC/VA/imbalance/absorption/CVD."),

    dict(id="tickdb", phase="session", ct="cont", task=None,
         title="NT8 tick recording",
         script="NT8 · Record live data as historical",
         health="NT8 tick DB",
         what="NT8 persists every incoming tick into its own historical database.",
         why="Independent second copy of the tape, and the source for rebuilding footprint "
             "for any past day via Tick Replay.",
         writes="Documents/NinjaTrader 8/db/tick/ES 09-26/",
         downstream="Tick-Replay footprint rebuilds; gap-fill for the parquet tick archive."),

    # ---------------------------------------------------------------- close
    dict(id="postmortem", phase="close", ct="15:15", task="MyQuant Postmortem",
         title="Daily postmortem",
         script="scripts/options_postmortem.py",
         what="Reconciles the morning gameplan against what the day actually did.",
         why="Learn without changing the rules daily. Scenario reconciliation, level-action "
             "taxonomy, over/undertrade and contradiction flags.",
         writes="data/options_sim/postmortem_YYYYMMDD.*",
         downstream="The Postmortem tab; rule changes only after evidence accumulates."),

    dict(id="eod", phase="close", ct="15:20", task="MyQuant EOD Report",
         title="EOD desk report",
         script="scripts/eod_report.py",
         what="Checks every step of the day's autonomous chain and renders the report.",
         why="So the desk can be trusted without Claude open. Exits 0 whenever the REPORT "
             "succeeded — a red desk is news, not a task failure.",
         writes="data/options_sim/eod_report_YYYYMMDD.html",
         downstream="Desk Report tab; optional HTML email."),
]


def by_phase():
    return [(key, label, [p for p in PROCESSES if p["phase"] == key]) for key, label in PHASES]


if __name__ == "__main__":
    for key, label, items in by_phase():
        print(f"\n=== {label}")
        for p in sorted(items, key=lambda x: x["ct"]):
            print(f"  {p['ct']:>5}  {p['title']:<32} {p['script']}")
    print(f"\n{len(PROCESSES)} processes")
