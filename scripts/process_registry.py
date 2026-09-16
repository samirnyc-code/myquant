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

# phase -> ordering on the page; each is one tile group. Ordered to follow the trading
# day CHRONOLOGICALLY so the "market-shut" phases (close -> halt -> overnight) sit
# together and flow logically, instead of overnight-first / halt-last with a gap between
# them (2026-07-20 fix). The overnight block ends at the 07:30 mine, looping back to
# pre-open at the top — a natural daily cycle.
PHASES = [
    ("preopen",   "① Pre-open  08:00–08:35 CT — get the desk armed before the 08:30 open"),
    ("session",   "② Session  08:30–15:00 CT — live, running all day"),
    ("close",     "③ Close  15:00–15:30 CT — reconcile and learn"),
    ("halt",      "④ Daily halt  16:00–17:00 CT — compress + back up; the only hour a restart costs nothing"),
    ("overnight", "⑤ Overnight  17:00–07:30 CT — record ETH + archive while the market is shut"),
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
         title="L2 depth + tape recorder — RETIRED (superseded by L1 tape)",
         script="nt8/addons/MarketDepthRecorderAddOn.cs.disabled",
         health=None,
         what="[RETIRED S120] Recorded the full L2 order book + interleaved tape. The AddOn is "
              "disabled in the Custom folder; the desk moved to L1 capture (tape + best "
              "bid/ask) — lighter disk, footprint/delta-complete — see the 'l1_tape' entry.",
         why="Kept in the timeline for provenance: this is where the irreplaceable L2 DOM "
             "history came from (through 2026-09-04). Re-enable only if full-depth capture "
             "is wanted again; for now L1 is the live recorder.",
         writes="data/depth/addon_test/ES_<contract>_depth_YYYY-MM-DD.csv (through 2026-09-04)",
         downstream="Historical L2/absorption/DOM research on the archived parquet."),

    dict(id="tickdb", phase="session", ct="cont", task=None,
         title="NT8 tick recording",
         script="NT8 · Record live data as historical",
         health="NT8 tick DB",
         what="NT8 persists every incoming tick into its own historical database.",
         why="Independent second copy of the tape, and the source for rebuilding footprint "
             "for any past day via Tick Replay.",
         writes="Documents/NinjaTrader 8/db/tick/ES 09-26/",
         downstream="Tick-Replay footprint rebuilds; gap-fill for the parquet tick archive."),

    dict(id="l1_tape", phase="session", ct="cont", task=None,
         title="L1 tape + best bid/ask recorder",
         script="nt8/addons/L1TapeRecorderAddOn.cs",
         health="L1 tape",
         what="Records every trade print (price/size/aggressor) plus every best-bid and "
              "best-ask change, on one clock, to a daily CSV. L1 only — NO full depth book.",
         why="The Wyckoff-2.0 order-flow DB (S120). The tick troves store TRADES ONLY with no "
             "bid/ask, so footprint/delta and absorption cannot be reconstructed from them. "
             "This adds the missing quote to the tape at a fraction of L2 DOM's disk. AddOn = "
             "auto-runs on NT startup, survives restarts, no enable step. L1 gaps are "
             "unrecoverable (Databento MBP-10 is the paid backfill safety-net).",
         writes="data/l1_tape/ES_<contract>_l1_YYYY-MM-DD.csv",
         downstream="Footprint/CVD/absorption on the OF trigger lane; the Wyckoff-2.0 "
                    "backtest/journal DB. Nightly -> parquet via l1_rollover.py."),


    # ---------------------------------------------------------------- daily halt
    dict(id="rollover", phase="halt", ct="16:05", task="MyQuant Depth Rollover",
         title="L2 market depth -> parquet (compress session)",
         script="scripts/depth_rollover.py",
         what="The session just ended at 16:00: every finished L2/tape CSV (book events + "
              "trades) is converted to zstd parquet (~20x smaller) and the CSV deleted "
              "ONLY after the parquet is re-read and its row count matches.",
         why="Raw CSV is right for LIVE capture (appendable, crash-safe) and wrong for the "
             "archive: ES book events run to hundreds of MB a day and disk is what limits "
             "how long we can record. Measured 20.2x on the first real file. Files carry "
             "the TRADE DATE (session template), so the file that just closed converts "
             "the same afternoon. A file still held open by the recorder is never touched.",
         writes="data/depth/ES_<contract>_depth_YYYY-MM-DD.parquet",
         downstream="Every order-flow study reads the parquet; ~50MB/day instead of ~1GB."),

    dict(id="nt8_restart", phase="halt", ct="16:15", task="MyQuant NT8 Restart",
         title="NT8 restart + re-arm",
         script="scripts/nt8_maintenance.py",
         health="NinjaTrader",
         what="Closes NT8 cleanly, restarts it via the scripted login, then watches the "
              "depth file to prove rows are arriving again.",
         why="NT8 leaks memory over multi-day runs, and a two-week unattended recording "
             "needs a scheduled restart - the halt is the only hour where it costs no data. "
             "It verifies AFTERWARDS because a restart or recompile DISABLES enabled "
             "strategies: that happened twice on 7/19 with the Control Center looking "
             "perfectly healthy while nothing was being recorded.",
         writes="—",
         downstream="Keeps the depth/tape capture alive across a two-week run."),

    dict(id="preopen_verify", phase="halt", ct="16:45", task="MyQuant Pre-Open Verify",
         title="Pre-open armed check",
         script="scripts/nt8_maintenance.py --verify-only",
         health="L2 depth",
         what="Fifteen minutes before the 17:00 CT open, confirms NT8 is up and the depth "
              "file is growing.",
         why="Last gate before an unattended overnight session. Catches a restart that came "
             "back without the recorder enabled while there is still time to fix it.",
         writes="—",
         downstream="The difference between finding out at 16:45 and finding out at 08:00."),

    dict(id="archive", phase="halt", ct="16:06", task="MyQuant Depth Rollover",
         title="L2 depth backup -> GitHub (myquantdata)",
         script="scripts/depth_rollover.py -> ~/myquant-data",
         health="Data archive",
         what="Copies each verified depth parquet into the PRIVATE myquantdata git repo and "
              "pushes it to GitHub.",
         why="A parquet on this one drive is not a backup - lose the drive, lose the only "
             "copy of data no vendor sells back. This puts the irreplaceable L2 history "
             "off-machine the same halt hour it is made. Runs inside the rollover job.",
         writes="~/myquant-data/depth/*.parquet (GitHub: samirnyc-code/myquantdata, PRIVATE)",
         downstream="Disaster recovery for the one dataset that cannot be re-collected."),

    dict(id="l1_rollover", phase="halt", ct="16:05", task="MyQuant L1 Rollover",
         title="L1 tape -> parquet + backup",
         script="scripts/l1_rollover.py",
         health="L1 tape",
         what="Converts each finished L1 tape CSV (trades + best bid/ask) to zstd parquet and "
              "deletes the CSV ONLY after the parquet is re-read and its row count matches, "
              "then mirrors the parquet to the private ~/myquant-data archive repo.",
         why="Raw CSV is right for LIVE capture, wrong for the archive. Parquet is ~10x "
             "smaller and column-selective. Files carry the TRADE DATE, so the file that just "
             "closed converts the same afternoon; a file still held open is never touched. "
             "Scheduled task 'MyQuant L1 Rollover' created S120 (run_at_ct --at 16:05, "
             "DST-safe two-trigger pattern).",
         writes="data/l1_tape/*.parquet + ~/myquant-data/l1_tape/*.parquet",
         downstream="The Wyckoff-2.0 order-flow DB in its archive format; off-machine backup."),

    dict(id="l1_watchdog", phase="session", ct="every 10m", task="MyQuant L1 Recorder Watchdog",
         title="L1 recorder watchdog",
         script="scripts/l1_recorder_watchdog.py",
         health="L1 tape",
         what="Every 10 min while the market is open: checks the L1 tape freshness/quote mix "
              "(via check_l1_tape) and Telegram-pages if it stalls or goes tape-only.",
         why="PAGE-ONLY by design — never closes/restarts NT (that pops the un-answerable "
             "'Save workspace?' dialog). The AddOn self-heals silent stalls on its own; this "
             "just alerts a human if recording is genuinely down. Task created S120.",
         writes="Telegram alert (deduped) on stall/not-started; nothing on disk",
         downstream="Human intervention only when the AddOn's self-heal can't recover it."),

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
