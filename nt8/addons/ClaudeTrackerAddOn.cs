// ClaudeTrackerAddOn.cs — AddOn port of ClaudeTrackerV2.cs (the Strategy version), built
// 2026-10-23 because the Strategy kept getting disabled by NT8 itself — confirmed in the
// Output log ("Disabling NinjaScript strategy") after an uncaught exception in a Strategy
// callback (see nt8/strategies/ClaudeTrackerV2.cs's RequestScreenshot comment, 2026-10-16,
// and docs/living/claudetracker_incidents.md's 2026-10-22 entry — same mechanism, two
// different trigger paths). An AddOn has NO Strategies-tab enable/disable concept and NT8
// does not auto-disable one on an unhandled exception the way it does a Strategy — the
// SAME reasoning the repo's other recorders (L1TapeRecorderAddOn, MarketDepthRecorderAddOn)
// were already built this way for. Also a natural SINGLE instance (no chart to attach
// multiple times to), which deletes the whole ownership-arbitration class of bugs the
// Strategy version needed (two chart instances on the same instrument double-processing).
//
// WHAT THIS DOES NOT FIX: state lost on an NT8 recompile/reload is a property of ALL
// NinjaScript (Strategies, Indicators, AND AddOns all get torn down and reinstantiated on
// F5) — switching to AddOn does not change that. ReconcileOpenPosition() below is the same
// Position-reconcile fallback the Strategy version used (ported as-is) — a trade open
// across a reload still loses its original entry time/stop history, same limitation as
// before. The more thorough reload-resume rewrite (TryResumeOpenTrade, replaying a trade's
// own Events.csv) that caused the 2026-10-22 live incident was deliberately NOT carried
// over here — starting from the simpler, longer-proven-stable baseline on purpose.
//
// SCREENSHOTS: kept, not dropped. RequestScreenshot() finds the right chart via, in order:
//   1. ClaudeTrackerChartRegistry (nt8/indicators/ClaudeTrackerChartRegistry.cs) — if the
//      user has dropped ClaudeTrackerChartTag.cs on the ONE real execution chart, this is an
//      exact, unambiguous ChartControl, no guessing. The recommended setup.
//   2. Window-title match ("Chart - <Instrument.FullName>", native EnumWindows + Win32
//      GetWindowText) — fallback for an instrument nobody has tagged. Can pick the wrong
//      window if more than one open chart shows that instrument (confirmed live 2026-10-23:
//      got a real screenshot, but from the wrong ES 12-26 window) — that's exactly why #1
//      exists now.
// History: originally used Application.Current.Windows, which 2026-10-23 live testing proved
// is EMPTY (count=0) even while 4 real "Chart - ..." OS windows demonstrably exist — NT8
// creates each chart window on its own dedicated UI thread, and WPF only auto-registers a
// Window there when it's created on the main Application thread. Switched to native hwnds
// instead: HwndSource.FromHwnd(hwnd) (a static lookup, safe from any thread) recovers the WPF
// HwndSource for each one, then hs.Dispatcher.Invoke marshals onto THAT window's own UI
// thread to read state. The Strategy-side crash this file originally cited (2026-10-16) was a
// SINGLE wrong-thread hop — touching a different chart's window from inside another chart's
// own dispatcher without ever jumping to the target's. This never does that: every touch of a
// given window happens only on that window's own dispatcher (first to read state, then
// again to capture — same Chart object, same thread, just re-entering it for the actual
// GetScreenshot() call). Real limitation, not a threading one: no chart open showing the
// tracked instrument = no screenshot that cycle (logged, not fatal) — the Journal app's manual
// "+ Add screenshot" upload is the fallback for exactly that case.
//
// WHAT THIS DOES DROP vs the Strategy version (deliberate, not an oversight):
//   Bar/session-bar tracking (SessionBar, BarsHeld, bar-based MAE/MFE) — a Strategy gets bars
//   for free from its chart; an AddOn has none. MAE/MFE now tracks off live tick prices
//   (MarketData.Last) instead of bar High/Low — arguably more accurate, not less. GetBarInfo()
//   is kept as a stub always returning -1 so the many call sites that already handle "-1 =
//   unknown" (the Strategy version's own graceful-degradation path when sessionIterator wasn't
//   ready) didn't need touching. Multi-chart ownership arbitration is also gone — not dropped
//   functionality, just not applicable: an AddOn loads once, there's no second instance to
//   arbitrate against.
//
// CONFIG (the one manual step per machine, same convention as L1TapeRecorderAddOn's
// contract-roll const): set AccountName below to the live/sim account THIS copy should
// track, and SymbolName to the current front-month contract. One compiled copy == one
// account. Samir and Thomas each run their own NT8 install with their own copy/consts.
//
// ⚠️ UNTESTED until F5 + a real trade cycle (entry, stop move, exit) run against it live.
// Deploy to Custom\AddOns\, F5 when flat, and watch the NinjaScript Output log for
// "[ClaudeTrackerAddOn]" lines on the next trade before trusting it over the Strategy
// version. Recommend running BOTH side by side (this AddOn + the existing Strategy) for at
// least one full session, comparing their output files, before retiring the Strategy.

#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using System.Globalization;
using NinjaTrader.NinjaScript;
using NinjaTrader.Gui.Chart;
using System.Windows;
using System.Windows.Media.Imaging;
using System.Windows.Interop;
using System.Runtime.InteropServices;
using System.Diagnostics;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public class ClaudeTrackerAddOn : AddOnBase
    {
        // -------- config (edit per machine — see header) --------
        private const string AccountName = "Sim101";
        private const string SymbolName  = "ES 12-26";
        private const string TraderTag   = "Samir"; // just for the health file / log lines

        private Instrument instrument;
        private Account account;
        private MarketData marketData;
        private bool accountHooked;
        private bool marketSubscribed;
        private readonly object subLock = new object();
        private System.Timers.Timer settleTimer;

        #region Nested classes

        private class TradeEventRow
        {
            public long Sequence;
            public string TradeID;
            public string EventID;
            public string FillID;
            public DateTime Time;
            public string EventType;
            public string Direction;
            public string OrderName;
            public string Oco;
            public long OrderId;
            public int ExecQty;
            public int PositionBefore;
            public int PositionAfter;
            public double FillPrice;
            public double AvgEntryBefore;
            public double AvgEntryAfter;
            public double LegPnLCurrency;
            public double CumRealizedPnLCurrency;
            public double ATMStop;
            public double FirstProtectiveStop;
            public double InitialStop;
            public double FirstActualStop;
            public double CurrentStop;
            public double ActualStop;
            public double TargetAtEvent;
            // Cumulative MAE/MFE (from entry to THIS event's instant) — lets the
            // journal show per-leg excursion, not just a trade-level final total.
            public double MAEPointsAtEvent;
            public double MFEPointsAtEvent;
            public int SessionBar;
            // SessionLastBar removed — static value, no analytical value per event
            public int BarsSinceTradeStart;
            public int BarsSincePrevEvent;
            public double MinsSinceTradeStart;
            public double MinsSincePrevEvent;
        }

        private class TradeSummaryRow
        {
            public string TradeID;
            public string InstrumentName;
            public DateTime StartTime;
            public DateTime EndTime;
            public string Direction;
            // Entry/Exit classification — moved up front after Direction
            public string EntryType;        // ATM_<TemplateName> | Market | Limit
            public string ExitMechanism;    // Stop | Target | Market | Reversal
            public string ExitLabel;        // T1 | T2 | T3 | Stop_Initial | Stop_Actual_1 | Stop_Actual_2 | Market
            public int TotalEntryQty;
            public int TotalExitQty;
            public int MaxPositionQty;
            public double FirstEntryPrice;
            public double WeightedAvgEntryPrice;
            public double WeightedAvgExitPrice;
            public double ATMStop;
            public double FirstProtectiveStop;
            public double InitialStop;
            public double FirstActualStop;
            public double CurrentStopAtExit;
            public double InitialRiskPoints;
            public double FirstActualRiskPoints;
            public double GrossPnLCurrency;
            public double TradeMAEPoints;
            public double TradeMFEPoints;
            public int ScaleInCount;
            public int AddOnCount;
            public int ScaleOutCount;
            public int StartSessionBar;
            // StartSessionLastBar removed — static, no per-trade value
            public int EndSessionBar;
            // EndSessionLastBar removed — static, no per-trade value
            public int BarsHeld;
            public double DurationMins;
            public string TradeFolder;
        }

        // ─── EntryStudy row — Phase 1 written by NT, Phase 2 calculated in Sheets ──
        private class EntryStudyRow
        {
            // ── Phase 1 — written immediately by NT ───────────────────────
            public string TradeID;
            public string InstrumentName;
            public string Direction;
            public double EntryPrice;
            public int EntryQty;
            public DateTime EntryTime;
            public int EntrySessionBar;

            public string StopEvent;        // ENTRY | INITIAL_STOP | ACTUAL_STOP_1 ...
            public double StopPrice;        // 0 = blank (ENTRY row)
            public DateTime StopTime;       // default = blank (ENTRY row)
            public int StopSessionBar;      // kept — used to join with 1M bars in Sheets for window metrics
            public double RiskPoints;
            public int StopEventIndex;

            // ── Phase 2 — left blank by NT, calculated in Sheets ─────────
            // Sheets joins this CSV with the 1M bar export on date + session bar number.
            // All metrics are calculated from EntryTime to session end using 1M OHLC data.

            // SESSION-END EXCURSION METRICS (same value on every row for a given trade)
            // MFEPoints   = MAX of (bar High - EntryPrice) for LONG, (EntryPrice - bar Low) for SHORT
            //               across all 1M bars from EntryTime to session end
            // MAEPoints   = MIN of (bar Low - EntryPrice) for LONG, (EntryPrice - bar High) for SHORT
            //               Note: MAE will be negative for adverse moves

            // R-METRICS USING THIS ROW'S RiskPoints AS DENOMINATOR
            // MaxR        = MFEPoints / RiskPoints
            // MAEinR      = MAEPoints / RiskPoints
            // RR          = (SessionClosePrice - EntryPrice) / RiskPoints for LONG
            //               (EntryPrice - SessionClosePrice) / RiskPoints for SHORT
            //               Blank if RiskPoints = 0 (free trade / BE stop)
            // SessionClosePrice = Close of last 1M bar at or before session end time

            // TIME-TO-R METRICS (1M bars and minutes from entry to first touch)
            // BarsTo1R    = first 1M bar where High >= EntryPrice + RiskPoints (LONG)
            //               or Low <= EntryPrice - RiskPoints (SHORT)
            // BarsTo2R/3R = same for 2x/3x RiskPoints
            // BarsToMaxR  = bar where running MFE peaked
            // MinsTo1R/2R/3R/MaxR = same in minutes

            // CUMULATIVE AT CHECKPOINT (entry to this stop's StopTime)
            // MFEPoints_AtStop = MAX excursion from entry up to StopTime
            // MAEPoints_AtStop = MIN excursion from entry up to StopTime
            // MaxR_AtStop      = MFEPoints_AtStop / RiskPoints
            // MAEinR_AtStop    = MAEPoints_AtStop / RiskPoints

            // WINDOW METRICS (prior stop event to this stop event)
            // Window start = EntryTime for INITIAL_STOP, prior StopTime for subsequent rows
            // Window end   = this row's StopTime
            // MFEPoints_Window = MAX excursion within window (anchored to EntryPrice)
            // MAEPoints_Window = MIN excursion within window
            // MaxR_Window      = MFEPoints_Window / RiskPoints
            // MAEinR_Window    = MAEPoints_Window / RiskPoints
        }

        // Per-named-target-order settle/move tracking (Target1, Target2, Target3, ...),
        // mirroring the InitialStop settle-window pattern on ActiveTrade but keyed per
        // order since there can be more than one live target at once.
        private class TargetTrackState
        {
            public bool Started;
            public bool Locked;
            public DateTime WindowStartTime;
            public double PendingCandidate;
            public double LockedPrice;
            public int MoveCount;
        }

        private class ActiveTrade
        {
            public string TradeID;
            public string InstrumentName;
            public string Direction;
            public string EntryType;        // ATM_<name> | Market | Limit
            public string EntryOrderName;   // raw order name from NT for ATM template extraction
            public long EntryOrderId;       // o.Id of the entry fill's order — a single multi-lot
                                             // market order that fills as separate Execution events
                                             // (one per matched price level) shares this Id across all
                                             // of them, which is how HandleAddExecution tells "this is
                                             // still the same entry order finishing its fill" apart from
                                             // a genuine, later add-on placed as a NEW order.
            public DateTime StartTime;
            public DateTime LastEventTime;
            public int StartSessionBar;
            public int CurrentQty;
            public int MaxPositionQty;
            public int TotalEntryQty;
            public int TotalExitQty;
            public double EntryPriceSum;
            public double ExitPriceSum;
            public double FirstEntryPrice;
            public double WeightedAvgEntryPrice;
            public double WeightedAvgExitPrice;
            public double RealizedPnLCurrency;
            public double TradeMAEPoints;
            public double TradeMFEPoints;
            public int ScaleInCount;
            public int AddOnCount;
            public int ScaleOutCount;
            public string LastExitMechanism; // Stop | Target | Market | Reversal
            public string LastExitLabel;     // T1 | T2 | T3 | Stop_Initial | Stop_Actual_N | Market
            public string LastExitOrderName; // raw order name from NT for label extraction
            public double ATMStop;
            public double FirstProtectiveStop;
            public DateTime FirstProtectiveStopLocalTime;
            public double PendingInitialStopCandidate;
            public double InitialStop;
            public DateTime InitialStopTime;
            public bool InitialStopLocked;
            public bool InitialStopStarted;
            public DateTime InitialStopWindowStartTime;
            public double FirstActualStop;
            public DateTime FirstActualStopTime;
            public bool FirstActualCaptured;
            public double CurrentStop;
            public double CurrentTarget;
            // Keyed by sanitized order name (e.g. "TARGET1") — tracks each target
            // order's own settle window + subsequent moves independently.
            public Dictionary<string, TargetTrackState> Targets = new Dictionary<string, TargetTrackState>();
            public int EventCounter;
            public List<TradeEventRow> EventRows = new List<TradeEventRow>();
            public int EventRowsFlushedCount; // how many of EventRows are already on disk — see FlushEventsIncremental
            public string TradeFolder;
            public int LastEventSessionBar;
        }

        private class SessionStudy
        {
            public string TradeID;
            public string Direction;
            public double EntryPrice;
            public int EntryQty;
            public DateTime EntryTime;
            public int EntrySessionBar;
            public List<EntryStudyRow> StopRows = new List<EntryStudyRow>();
            public DateTime LastStopWrittenTime;
        }

        #endregion

        #region Fields

        private static readonly CultureInfo INV = CultureInfo.InvariantCulture;
        private ActiveTrade activeTrade;
        private SessionStudy activeStudy;
        private string outputRoot;
        private int dailyTradeCounter = 0;
        private DateTime instanceStartedAt = DateTime.MinValue; // when THIS instance last (re)loaded
        private readonly HashSet<string> processedExecutions = new HashSet<string>();
        private long globalSequence = 0;
        private DateTime lastHealthCheckTime = DateTime.MinValue;
        private static readonly TimeSpan HealthCheckInterval = TimeSpan.FromSeconds(30);

        // No ownership arbitration needed here (unlike the Strategy version) — an AddOn
        // loads exactly once, there is no "drop the same script on a second chart" to
        // collide with.

        // User-parameters-as-consts (AddOns have no Strategies-tab settings dialog to edit
        // these through — same convention as the repo's other AddOns: hardcode, document,
        // edit per machine if a value needs to differ).
        private const int InitialStopLockSeconds = 5;
        private const bool DebugMode = true;
        // Deliberately a DIFFERENT folder than ClaudeTrackerV2.cs's ExportRootFolder (same
        // base, "_AddOnTest" suffix) — running both at once (as directed, for a side-by-side
        // comparison) against the SAME folder would have them overwrite each other's CSVs.
        // WriteEntryStudyMerged in particular reads the whole file, filters, and rewrites it —
        // two processes doing that concurrently on the same file is a real corruption risk,
        // not just a theoretical one. Compare the two trees once the test session is over;
        // do NOT point journal_uploader.py at this folder while the Strategy is also running
        // against its own — that would upload the same real trades twice into the live Journal.
        private const string ExportRootFolder = @"G:\My Drive\!NT Tracker Export_AddOnTest";
        // A same-order or same-tiny-window fill is still the SAME entry, not a deliberate
        // add — see MergeIntoEntry(). Ported from the entry-merge-window fix that was
        // reverted out of the Strategy version on 2026-10-22 (not because it was implicated
        // in that incident — explicitly noted as safe — just bundled into a full revert).
        private const int EntryMergeWindowMs = 1500;
        private const int ScreenshotDelayMs = 100;
        // Appended to every TradeID this instance generates. Running this AddOn alongside
        // ClaudeTrackerV2.cs on the SAME account means both independently generate a TradeID
        // for the SAME real fill from the same {instrument,entry-second,direction,counter}
        // formula — without something to tell them apart, the second one uploaded to the
        // Journal (Trade.id is the primary key) would silently overwrite the first instead of
        // producing two separate, comparable rows. User's own call (2026-10-23): upload both,
        // on purpose, specifically to compare them side by side in the live Journal.
        private const string TradeIdSourceTag = "_ADDON";

        // A Strategy gets Instrument/Account/Position for free from whatever chart it's on;
        // an AddOn has none of that built in. These three stand in for them, backed by our
        // own resolved fields — named to match on purpose so every other method below (all
        // ported from the Strategy version) reads `Instrument.FullName`, `Account.Name`,
        // `Position.MarketPosition` etc. completely unchanged. (A property sharing its own
        // type's name like this is unusual to read but legal C#, and is literally what NT8's
        // own Strategy base class does for these same three names — not a new pattern here.)
        private Instrument Instrument { get { return instrument; } }
        private Account Account { get; set; }
        private Position Position
        {
            get
            {
                if (Account == null || instrument == null) return null;
                return Account.Positions.FirstOrDefault(p => p.Instrument != null && p.Instrument.FullName == instrument.FullName);
            }
        }

        #endregion

        #region State

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "ClaudeTrackerAddOn";
                Description = "Trade-playbook journal recorder (AddOn port of ClaudeTrackerV2) — tracks " + AccountName + " / " + SymbolName + ". No enable step, survives what used to disable the Strategy version.";

                string instrumentFolder = SymbolName.Contains("MES") ? "MES" : "ES";
                string root = string.IsNullOrWhiteSpace(ExportRootFolder)
                    ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "NinjaTrader 8", "ClaudeTracker")
                    : ExportRootFolder;
                outputRoot = Path.Combine(root, instrumentFolder);
                if (!Directory.Exists(outputRoot))
                    Directory.CreateDirectory(outputRoot);

                dailyTradeCounter = CountTodaysTrades();
                instanceStartedAt = Core.Globals.Now;

                Connection.ConnectionStatusUpdate += OnConnectionStatusUpdate;

                // Settles account/instrument resolution + ties stop/target settle-windows and
                // the health heartbeat to wall-clock time instead of OnBarUpdate (an AddOn has
                // no bars). 1s is plenty — nothing here needs tick-rate polling.
                settleTimer = new System.Timers.Timer(1000);
                settleTimer.Elapsed += (s, e) => SettleTick();
                settleTimer.Start();

                Log("[ClaudeTrackerAddOn] loaded for " + AccountName + " / " + SymbolName
                    + ". Resuming from trade #" + dailyTradeCounter.ToString(INV), LogLevel.Information);
            }
            else if (State == State.Terminated)
            {
                if (settleTimer != null) { try { settleTimer.Stop(); settleTimer.Dispose(); } catch { } settleTimer = null; }
                try { Connection.ConnectionStatusUpdate -= OnConnectionStatusUpdate; } catch { }
                if (Account != null)
                {
                    Account.OrderUpdate     -= OnAccountOrderUpdate;
                    Account.ExecutionUpdate -= OnAccountExecutionUpdate;
                }
                UnsubscribeMarketData();
            }
        }

        // Account lookup doesn't need a live price connection (Account.All is populated as
        // soon as NT8 has loaded its configured accounts) — tried on every settle tick until
        // it succeeds, rather than assumed ready the instant SetDefaults fires. Hooking the
        // execution events and reconciling any already-open position both happen the moment
        // it resolves, whichever tick that is.
        // Fill/stop/target tracking must NOT depend on the price feed being connected —
        // orders and executions can land (and matter) before the feed is up or during a
        // brief hiccup. Resolved independently of SubscribeMarketData below, which is the
        // one piece that genuinely does need a live connection (tick-based MAE/MFE only).
        // lock(subLock) here is load-bearing, not defensive boilerplate: settleTimer is a
        // System.Timers.Timer, which is reentrant — if an Elapsed tick runs long (or several
        // queue up under startup load, confirmed in the 2026-10-27 log: 4 near-simultaneous
        // "instrument resolved"/"account resolved" lines from ONE AddOn instance within the
        // same millisecond), multiple threads can each pass the `if (x != null) return` guard
        // before the first one's assignment is visible. For TryResolveAccount specifically,
        // that meant `Account.ExecutionUpdate += OnAccountExecutionUpdate` ran more than once
        // — every real execution after that fired the handler once per duplicate subscription,
        // each one independently incrementing dailyTradeCounter and writing its own trade
        // record (the "_T1_ADDON" / "_T2_ADDON" duplicate-journal-entry, one with screenshots
        // one without, from a single fill). The lock makes check-then-set atomic.
        private void TryResolveInstrument()
        {
            if (instrument != null) return;
            lock (subLock)
            {
                if (instrument != null) return;
                try
                {
                    Instrument found = NinjaTrader.Cbi.Instrument.GetInstrument(SymbolName);
                    if (found == null) return;
                    instrument = found;
                    Log("[ClaudeTrackerAddOn] instrument resolved: " + instrument.FullName, LogLevel.Information);
                }
                catch (Exception ex) { Log("[ClaudeTrackerAddOn] TryResolveInstrument error: " + ex.Message, LogLevel.Error); }
            }
        }

        private void TryResolveAccount()
        {
            if (Account != null) return;
            lock (subLock)
            {
                if (Account != null) return;
                try
                {
                    Account found = NinjaTrader.Cbi.Account.All.FirstOrDefault(a => a.Name == AccountName);
                    if (found == null) return;
                    Account = found;
                    Account.OrderUpdate     += OnAccountOrderUpdate;
                    Account.ExecutionUpdate += OnAccountExecutionUpdate;
                    Log("[ClaudeTrackerAddOn] account resolved: " + Account.Name, LogLevel.Information);
                    ReconcileOpenPosition();
                }
                catch (Exception ex) { Log("[ClaudeTrackerAddOn] TryResolveAccount error: " + ex.Message, LogLevel.Error); }
            }
        }

        // Market data (for tick-based MAE/MFE — see OnMarketData) DOES need a live price
        // connection, same as L1TapeRecorderAddOn/MarketDepthRecorderAddOn in this repo.
        private void OnConnectionStatusUpdate(object sender, ConnectionStatusEventArgs e)
        {
            try
            {
                if (e.PriceStatus == ConnectionStatus.Connected)
                {
                    lock (subLock)
                    {
                        if (marketSubscribed) return;
                        marketSubscribed = true;
                    }
                    SubscribeMarketData();
                }
                else if (e.PriceStatus == ConnectionStatus.Disconnected || e.PriceStatus == ConnectionStatus.ConnectionLost)
                {
                    UnsubscribeMarketData();
                }
            }
            catch (Exception ex) { Log("[ClaudeTrackerAddOn] connection status error: " + ex.Message, LogLevel.Error); }
        }

        private void SubscribeMarketData()
        {
            try
            {
                TryResolveInstrument();
                if (instrument == null)
                {
                    Log("[ClaudeTrackerAddOn] instrument not found: " + SymbolName, LogLevel.Error);
                    marketSubscribed = false;
                    return;
                }
                instrument.Dispatcher.InvokeAsync(() =>
                {
                    try
                    {
                        marketData = new MarketData(instrument);
                        marketData.Update += OnMarketData;
                        Log("[ClaudeTrackerAddOn] market data connected: " + SymbolName, LogLevel.Information);
                    }
                    catch (Exception ex) { marketSubscribed = false; Log("[ClaudeTrackerAddOn] market subscribe error: " + ex.Message, LogLevel.Error); }
                });
            }
            catch (Exception ex) { marketSubscribed = false; Log("[ClaudeTrackerAddOn] SubscribeMarketData error: " + ex.Message, LogLevel.Error); }
        }

        private void UnsubscribeMarketData()
        {
            try
            {
                var inst = instrument; var mdata = marketData;
                if (inst != null && mdata != null)
                    inst.Dispatcher.InvokeAsync(() => { try { mdata.Update -= OnMarketData; } catch { } });
            }
            catch { }
            marketSubscribed = false;
        }

        // Live tick prices drive MAE/MFE instead of bar High/Low (an AddOn has no bars) —
        // same running-max/min logic as the Strategy version's UpdateOpenTradeExcursions,
        // just fed per-tick instead of per-bar.
        private void OnMarketData(object sender, MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last) return;
            UpdateOpenTradeExcursions(e.Price);
        }

        // Replaces OnBarUpdate's 4 calls (minus excursion tracking, which moved to
        // OnMarketData above since it needs tick prices, not a wall-clock tick).
        private void SettleTick()
        {
            try
            {
                if (instrument == null) TryResolveInstrument();
                if (Account == null) { TryResolveAccount(); return; }
                TryLockInitialStop();
                TryLockTargets();
                RunHealthCheck();
            }
            catch (Exception ex) { Log("[ClaudeTrackerAddOn] SettleTick error: " + ex.Message, LogLevel.Error); }
        }

        #endregion

        #region Account event handlers

        private void OnAccountOrderUpdate(object sender, OrderEventArgs e)
        {
            try
            {
                Order o = e.Order;
                if (o == null || o.Instrument == null || Instrument == null) return;
                if (o.Instrument.FullName != Instrument.FullName) return;
                if (activeTrade == null) return;
                if (IsStopOrder(o)) { double sp = o.StopPrice; if (sp > 0) HandleStopUpdate(sp, o); }
                else if (IsTargetOrder(o) && (o.Name ?? string.Empty).Trim().ToUpperInvariant().StartsWith("TARGET"))
                {
                    // Name-gated: IsTargetOrder() is true for ANY limit order (incl. a
                    // limit scale-in ENTRY), but only ATM-generated "Target1/2/3" orders
                    // are actual exit targets — gating on the name avoids logging a fake
                    // target move/screenshot every time a limit entry order is placed.
                    double tp = GetTargetPrice(o);
                    if (tp > 0) HandleTargetUpdate(tp, o);
                }
            }
            catch (Exception ex) { Log("[ClaudeTrackerAddOn] OnAccountOrderUpdate error: " + ex.Message, LogLevel.Error); }
        }

        private void OnAccountExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            try
            {
                Execution ex = e.Execution;
                Order o = ex != null ? ex.Order : null;
                if (ex == null || o == null || o.Instrument == null || Instrument == null) return;
                if (o.Instrument.FullName != Instrument.FullName) return;
                if (IsDuplicateExecution(ex, o)) return;
                int signedQty = GetSignedQty(o.OrderAction, ex.Quantity);
                if (signedQty == 0) return;
                HandleExecution(ex, o, signedQty);
            }
            catch (Exception ex2) { Log("OnAccountExecutionUpdate error: " + ex2.Message, LogLevel.Error); }
        }

        #endregion

        #region Execution handling

        private void HandleExecution(Execution ex, Order o, int signedQty)
        {
            int positionBefore = activeTrade != null ? activeTrade.CurrentQty : 0;
            int positionAfter  = positionBefore + signedQty;

            if (positionBefore == 0) { BeginNewTrade(ex, o, signedQty); return; }

            if (Math.Sign(positionBefore) == Math.Sign(signedQty))
            { HandleAddExecution(ex, o, signedQty, positionBefore, positionAfter); return; }

            int closeQty     = Math.Min(Math.Abs(positionBefore), Math.Abs(signedQty));
            int remainderQty = Math.Abs(signedQty) - closeQty;

            if (closeQty > 0)
            {
                int afterExit   = positionBefore - Math.Sign(positionBefore) * closeQty;
                string exitMech = remainderQty > 0 ? "Reversal"
                    : ClassifyExitMechanism(o);
                string exitLabel = remainderQty > 0 ? "Reversal"
                    : ClassifyExitLabel(o, activeTrade);
                HandleExitExecution(ex, o, closeQty, positionBefore, afterExit,
                    exitMech, exitLabel, ex.ExecutionId);
            }
            if (remainderQty > 0)
                BeginNewTrade(ex, o, Math.Sign(signedQty) * remainderQty,
                    SafeFillId(ex.ExecutionId) + "_REVERSAL_OPEN");
        }

        private void BeginNewTrade(Execution ex, Order o, int signedQty, string customFillId = null)
        {
            dailyTradeCounter++;
            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string tradeId        = instrumentName
                                  + "_" + ex.Time.ToString("yyyyMMdd", INV)
                                  + "_" + ex.Time.ToString("HHmmss", INV)
                                  + "_" + (signedQty > 0 ? "LONG" : "SHORT")
                                  + "_T" + dailyTradeCounter.ToString(INV)
                                  + TradeIdSourceTag;

            int sessionBar, sessionLastBar;
            GetBarInfo(ex.Time, out sessionBar, out sessionLastBar);

            string entryType = ClassifyEntryType(o);

            activeTrade = new ActiveTrade
            {
                TradeID               = tradeId,
                InstrumentName        = Instrument.FullName,
                Direction             = signedQty > 0 ? "LONG" : "SHORT",
                EntryType             = entryType,
                EntryOrderName        = o.Name ?? string.Empty,
                EntryOrderId          = o.Id,
                StartTime             = ex.Time,
                LastEventTime         = ex.Time,
                StartSessionBar       = sessionBar,
                LastEventSessionBar   = sessionBar,
                CurrentQty            = signedQty,
                MaxPositionQty        = Math.Abs(signedQty),
                TotalEntryQty         = Math.Abs(signedQty),
                FirstEntryPrice       = ex.Price,
                WeightedAvgEntryPrice = ex.Price,
                EntryPriceSum         = ex.Price * Math.Abs(signedQty),
                TradeFolder           = EnsureTradeFolder(tradeId, ex.Time)
            };

            activeTrade.EventRows.Add(new TradeEventRow
            {
                Sequence            = ++globalSequence,
                TradeID             = tradeId,
                EventID             = NextEventID(activeTrade),
                FillID              = !string.IsNullOrEmpty(customFillId) ? customFillId : SafeFillId(ex.ExecutionId),
                Time                = ex.Time,
                EventType           = "OPEN",
                Direction           = activeTrade.Direction,
                OrderName           = o.Name ?? string.Empty,
                Oco                 = o.Oco ?? string.Empty,
                OrderId             = o.Id,
                ExecQty             = Math.Abs(signedQty),
                PositionBefore      = 0,
                PositionAfter       = signedQty,
                FillPrice           = ex.Price,
                AvgEntryBefore      = 0,
                AvgEntryAfter       = activeTrade.WeightedAvgEntryPrice,
                MAEPointsAtEvent    = 0,
                MFEPointsAtEvent    = 0,
                SessionBar          = sessionBar
            });

            FlushEventsIncremental();

            activeStudy = new SessionStudy
            {
                TradeID         = tradeId,
                Direction       = activeTrade.Direction,
                EntryPrice      = ex.Price,
                EntryQty        = Math.Abs(signedQty),
                EntryTime       = ex.Time,
                EntrySessionBar = sessionBar
            };

            activeStudy.StopRows.Add(new EntryStudyRow
            {
                TradeID         = tradeId,
                InstrumentName  = Instrument.FullName,
                Direction       = activeTrade.Direction,
                EntryPrice      = ex.Price,
                EntryQty        = Math.Abs(signedQty),
                EntryTime       = ex.Time,
                EntrySessionBar = sessionBar,
                StopEvent       = "ENTRY",
                StopEventIndex  = 0,
                StopPrice       = 0,
                StopSessionBar  = -1,
                RiskPoints      = 0
            });

            WriteEntryStudy(activeStudy);
            DebugPrint("ENTRY written for " + tradeId + " [" + entryType + "] at " + F2(ex.Price));
            RequestScreenshot("ENTRY", ex.Time, tradeId, ex.Time);

            lastHealthCheckTime = Core.Globals.Now;
        }

        // Synthesizes a minimal activeTrade/activeStudy from the broker's own
        // position when we come up live and find one with nothing tracking it.
        // Same shape as BeginNewTrade's setup, but sourced from Position instead
        // of an Execution — there's no fill to key off, the original entry
        // already happened before this instance existed. Original StartTime,
        // true entry fill count, and any stop/risk history from before the
        // reload are permanently gone; this buys correctness (the trade WILL
        // close) over completeness (it won't look identical to a normally-
        // tracked trade). TradeID and EntryType are both tagged "RECOVERED" /
        // "Recovered" so this is never mistaken for a normal trade downstream.
        private void ReconcileOpenPosition()
        {
            if (activeTrade != null) return;
            if (Position == null || Position.MarketPosition == MarketPosition.Flat) return;

            DateTime now = Core.Globals.Now;
            int signedQty = Position.MarketPosition == MarketPosition.Long ? Position.Quantity : -Position.Quantity;

            dailyTradeCounter++;
            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string tradeId = instrumentName
                + "_" + now.ToString("yyyyMMdd", INV)
                + "_" + now.ToString("HHmmss", INV)
                + "_" + (signedQty > 0 ? "LONG" : "SHORT")
                + "_RECOVERED_T" + dailyTradeCounter.ToString(INV)
                + TradeIdSourceTag;

            int sessionBar, sessionLastBar;
            GetBarInfo(now, out sessionBar, out sessionLastBar);

            activeTrade = new ActiveTrade
            {
                TradeID               = tradeId,
                InstrumentName        = Instrument.FullName,
                Direction             = signedQty > 0 ? "LONG" : "SHORT",
                EntryType             = "Recovered",
                EntryOrderName        = string.Empty,
                StartTime             = now,
                LastEventTime         = now,
                StartSessionBar       = sessionBar,
                LastEventSessionBar   = sessionBar,
                CurrentQty            = signedQty,
                MaxPositionQty        = Math.Abs(signedQty),
                TotalEntryQty         = Math.Abs(signedQty),
                FirstEntryPrice       = Position.AveragePrice,
                WeightedAvgEntryPrice = Position.AveragePrice,
                EntryPriceSum         = Position.AveragePrice * Math.Abs(signedQty),
                TradeFolder           = EnsureTradeFolder(tradeId, now)
            };

            activeStudy = new SessionStudy
            {
                TradeID         = tradeId,
                Direction       = activeTrade.Direction,
                EntryPrice      = Position.AveragePrice,
                EntryQty        = Math.Abs(signedQty),
                EntryTime       = now,
                EntrySessionBar = sessionBar
            };

            activeStudy.StopRows.Add(new EntryStudyRow
            {
                TradeID         = tradeId,
                InstrumentName  = Instrument.FullName,
                Direction       = activeTrade.Direction,
                EntryPrice      = Position.AveragePrice,
                EntryQty        = Math.Abs(signedQty),
                EntryTime       = now,
                EntrySessionBar = sessionBar,
                StopEvent       = "ENTRY_RECOVERED",
                StopEventIndex  = 0,
                StopPrice       = 0,
                StopSessionBar  = -1,
                RiskPoints      = 0
            });

            WriteEntryStudy(activeStudy);
            Log("[ClaudeTrackerAddOn] WARNING: found an open " + activeTrade.Direction + " position ("
                + Math.Abs(signedQty) + " @ " + F2(Position.AveragePrice) + ") on startup with nothing "
                + "tracking it — a prior reload lost it. Recovering as " + tradeId
                + " (original entry time and any stop/risk history before the reload are unrecoverable).", LogLevel.Warning);
        }


        #region Health check

        // Runs every ~30s of wall time (throttled off OnBarUpdate, which fires far more
        // often than that under Calculate.OnEachTick — no need to check this on every tick).
        // Two things, every cycle:
        //   1. Does activeTrade (what we think) still match Position (what the broker
        //      knows)? Catches the SAME class of bug ReconcileOpenPosition fixes at
        //      startup, but for drift that happens WITHOUT a full reload — some other
        //      exception swallowed mid-session, not just "Loaded. Resuming from trade #0".
        //   2. Write a heartbeat file regardless of outcome — pipeline_health.py reads
        //      its freshness as proof this code is still running at all (a frozen/crashed
        //      strategy with ErrorHandling=IgnoreAllErrors can sit there doing nothing and
        //      never tell anyone — a stale heartbeat is itself the alarm).
        // 2026-10-16: removed the drift check entirely (not just the auto-close action) —
        // user call. It compared activeTrade against Position every cycle and either
        // reconciled or (until the same session) auto-closed on a mismatch; proved twice
        // live that a mismatch can fire on a perfectly healthy trade when ownership
        // arbitration between chart instances doesn't hold, and even alert-only it was
        // noise the user didn't want. This function is now ONLY a heartbeat — proof the
        // strategy loop is alive — plus the raw execution-log snapshot. No comparison, no
        // reconciliation, no alerting. A genuinely stuck-open trade (the original 10/15
        // failure mode) now relies solely on ReconcileOpenPosition at startup/ownership
        // takeover, not a periodic check.
        private void RunHealthCheck()
        {
            DateTime now = Core.Globals.Now;
            if (now - lastHealthCheckTime < HealthCheckInterval) return;
            lastHealthCheckTime = now;

            string detail = activeTrade != null
                ? "tracking " + activeTrade.TradeID + " (" + activeTrade.Direction + " " + activeTrade.CurrentQty + ")"
                : "flat, nothing tracked";

            WriteHealthFile("running", detail);
            WriteExecutionLog();
        }

        // No chart/bar-period concept for an AddOn (unlike the Strategy version, which could
        // have multiple chart instances to disambiguate between) — just identifies which
        // trader/account this running copy is tracking.
        private string ChartLabel()
        {
            return "AddOn [" + TraderTag + " / " + AccountName + "]";
        }

        private void WriteHealthFile(string status, string detail)
        {
            try
            {
                DateTime now = Core.Globals.Now;
                string path = Path.Combine(MastersFolder(now), "ClaudeTracker_Health.json");
                string json = "{"
                    + "\"status\":" + JsonStr(status) + ","
                    + "\"detail\":" + JsonStr(detail) + ","
                    + "\"instrument\":" + JsonStr(Instrument.FullName) + ","
                    + "\"checkedAt\":\"" + now.ToString("yyyy-MM-dd HH:mm:ss", INV) + "\","
                    + "\"brokerPosition\":" + (Position != null ? Position.Quantity * (Position.MarketPosition == MarketPosition.Short ? -1 : 1) : 0) + ","
                    + "\"ownerChart\":" + JsonStr(ChartLabel()) + ","
                    + "\"ownerStartedAt\":\"" + instanceStartedAt.ToString("yyyy-MM-dd HH:mm:ss", INV) + "\""
                    + "}";
                File.WriteAllText(path, json);
            }
            catch (Exception ex) { Log("[ClaudeTracker] health file write failed: " + ex.Message, LogLevel.Error); }
        }

        // Full-snapshot rewrite of today's raw fills for this account+instrument, straight
        // from the broker's own Execution records — not ClaudeTracker's derived trade state.
        // This is the ground truth the 2026-10-15 recovery relied on (manually pasted from
        // NT8's UI); keeping it on file automatically means next time that reconstruction
        // takes a script run, not a trading session's worth of screenshots and guesswork.
        private void WriteExecutionLog()
        {
            try
            {
                if (Account == null) return;
                DateTime now = Core.Globals.Now;
                var todays = Account.Executions
                    .Where(e => e.Instrument != null && e.Instrument.FullName == Instrument.FullName
                        && e.Time.Date == now.Date)
                    .OrderBy(e => e.Time)
                    .ToList();
                if (todays.Count == 0) return;

                string path = Path.Combine(MastersFolder(now), "ExecutionLog_" + now.ToString("yyyy-MM-dd", INV) + ".csv");
                using (StreamWriter sw = new StreamWriter(path, false))
                {
                    sw.WriteLine("Instrument,Action,Quantity,Price,Time,OrderName,OrderId,ExecutionId,MarketPosition,Account");
                    foreach (Execution e in todays)
                    {
                        Order o = e.Order;
                        sw.WriteLine(string.Join(",",
                            Csv(e.Instrument.FullName),
                            Csv(o != null ? o.OrderAction.ToString() : ""),
                            Csv(e.Quantity.ToString(INV)),
                            Csv(F2(e.Price)),
                            Csv(e.Time.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                            Csv(o != null ? (o.Name ?? "") : ""),
                            Csv(o != null ? o.Id.ToString(INV) : ""),
                            Csv(e.ExecutionId ?? ""),
                            Csv(e.MarketPosition.ToString()),
                            Csv(Account.Name ?? "")));
                    }
                }
            }
            catch (Exception ex) { Log("[ClaudeTracker] execution log write failed: " + ex.Message, LogLevel.Error); }
        }

        #endregion

        private void HandleAddExecution(Execution ex, Order o, int signedQty, int positionBefore, int positionAfter)
        {
            if (activeTrade == null) return;

            double avgBefore = activeTrade.WeightedAvgEntryPrice;
            double price     = ex.Price;
            int addQty       = Math.Abs(signedQty);

            // Same order finishing its fill (a multi-lot market order that fills across
            // more than one price level generates one Execution per leg, all sharing the
            // entry order's Id) OR arriving within the merge window of the trade's FIRST
            // fill — either way this is still THE SAME ENTRY, not a deliberate add, even
            // though the price is slightly different per leg. Blend it straight into the
            // OPEN row's own price/qty (avg price) instead of logging a second event, so
            // the journal shows one entry fill — matching what actually happened at the
            // exchange — rather than a spurious ADD_ON/SCALE_IN a few hundred ms later.
            bool isEntryMergeFill = o.Id == activeTrade.EntryOrderId
                || (ex.Time - activeTrade.StartTime).TotalMilliseconds <= EntryMergeWindowMs;

            if (isEntryMergeFill)
            {
                MergeIntoEntry(ex, price, addQty, positionAfter);
                return;
            }

            string eventType = ClassifyAddType(activeTrade.Direction, avgBefore, price);
            if (eventType == "SCALE_IN") activeTrade.ScaleInCount++;
            else if (eventType == "ADD_ON")   activeTrade.AddOnCount++;

            if (eventType == "SCALE_IN" && activeStudy != null)
{
    // Blended entry after this scale-in
    double newBlendedEntry = (activeTrade.EntryPriceSum + price * addQty)
                             / (activeTrade.TotalEntryQty + addQty);
    int scaleInSessionBar, scaleInSessionLastBar;
    GetBarInfo(ex.Time, out scaleInSessionBar, out scaleInSessionLastBar);

    // Add a SCALE_IN entry row — RiskPoints relative to blended entry at this moment
    // Stop rows written AFTER this will use the updated activeStudy.EntryPrice (blended)
    activeStudy.StopRows.Add(new EntryStudyRow
    {
        TradeID         = activeStudy.TradeID,
        InstrumentName  = Instrument.FullName,
        Direction       = activeStudy.Direction,
        EntryPrice      = newBlendedEntry,
        EntryQty        = activeTrade.TotalEntryQty + addQty,
        EntryTime       = ex.Time,
        EntrySessionBar = scaleInSessionBar,
        StopEvent       = "SCALE_IN",
        StopEventIndex  = activeStudy.StopRows.Count,
        StopPrice       = 0,
        StopSessionBar  = -1,
        RiskPoints      = 0
    });

    // Update activeStudy so all subsequent stop rows use blended entry
    activeStudy.EntryPrice  = newBlendedEntry;
    activeStudy.EntryQty    = activeTrade.TotalEntryQty + addQty;

    WriteEntryStudy(activeStudy);
    DebugPrint("SCALE_IN row added to EntryStudy: blendedEntry=" + F2(newBlendedEntry)
        + " qty=" + activeStudy.EntryQty.ToString(INV));
}

            activeTrade.EntryPriceSum        += price * addQty;
            activeTrade.TotalEntryQty        += addQty;
            activeTrade.CurrentQty            = positionAfter;
            activeTrade.MaxPositionQty        = Math.Max(activeTrade.MaxPositionQty, Math.Abs(positionAfter));
            activeTrade.WeightedAvgEntryPrice = activeTrade.TotalEntryQty > 0
                ? activeTrade.EntryPriceSum / activeTrade.TotalEntryQty : 0;

            int sessionBar, sessionLastBar;
            GetBarInfo(ex.Time, out sessionBar, out sessionLastBar);
            int prevSessionBar = activeTrade.LastEventSessionBar;
            DateTime prevTime  = activeTrade.LastEventTime;

            activeTrade.EventRows.Add(new TradeEventRow
            {
                Sequence               = ++globalSequence,
                TradeID                = activeTrade.TradeID,
                EventID                = NextEventID(activeTrade),
                FillID                 = SafeFillId(ex.ExecutionId),
                Time                   = ex.Time,
                EventType              = eventType,
                Direction              = activeTrade.Direction,
                OrderName              = o.Name ?? string.Empty,
                Oco                    = o.Oco ?? string.Empty,
                OrderId                = o.Id,
                ExecQty                = addQty,
                PositionBefore         = positionBefore,
                PositionAfter          = positionAfter,
                FillPrice              = price,
                AvgEntryBefore         = avgBefore,
                AvgEntryAfter          = activeTrade.WeightedAvgEntryPrice,
                LegPnLCurrency         = 0,
                CumRealizedPnLCurrency = activeTrade.RealizedPnLCurrency,
                ATMStop                = activeTrade.ATMStop,
                FirstProtectiveStop    = activeTrade.FirstProtectiveStop,
                InitialStop            = activeTrade.InitialStop,
                FirstActualStop        = activeTrade.FirstActualStop,
                CurrentStop            = activeTrade.CurrentStop,
                ActualStop             = activeTrade.CurrentStop,
                TargetAtEvent          = activeTrade.CurrentTarget,
                MAEPointsAtEvent       = activeTrade.TradeMAEPoints,
                MFEPointsAtEvent       = activeTrade.TradeMFEPoints,
                SessionBar             = sessionBar,
                BarsSinceTradeStart    = sessionBar >= 0 && activeTrade.StartSessionBar >= 0 ? sessionBar - activeTrade.StartSessionBar : -1,
                BarsSincePrevEvent     = sessionBar >= 0 && prevSessionBar >= 0 ? sessionBar - prevSessionBar : -1,
                MinsSinceTradeStart    = (ex.Time - activeTrade.StartTime).TotalMinutes,
                MinsSincePrevEvent     = (ex.Time - prevTime).TotalMinutes
            });

            activeTrade.LastEventSessionBar = sessionBar;
            activeTrade.LastEventTime       = ex.Time;

            FlushEventsIncremental();

            if (eventType == "SCALE_IN" || eventType == "ADD_ON")
                RequestScreenshot(eventType, ex.Time, activeTrade.TradeID, activeTrade.StartTime);
        }

        // Folds a merge-eligible fill directly into the trade's OPEN event row and
        // entry-side aggregates — no new Events.csv row, no ScaleIn/AddOn count bump,
        // just a wider averaged entry price/qty. See the merge-condition comment in
        // HandleAddExecution for why a fill qualifies.
        private void MergeIntoEntry(Execution ex, double price, int addQty, int positionAfter)
        {
            activeTrade.EntryPriceSum        += price * addQty;
            activeTrade.TotalEntryQty        += addQty;
            activeTrade.CurrentQty            = positionAfter;
            activeTrade.MaxPositionQty        = Math.Max(activeTrade.MaxPositionQty, Math.Abs(positionAfter));
            activeTrade.WeightedAvgEntryPrice = activeTrade.TotalEntryQty > 0
                ? activeTrade.EntryPriceSum / activeTrade.TotalEntryQty : 0;

            TradeEventRow openRow = activeTrade.EventRows.Count > 0 ? activeTrade.EventRows[0] : null;
            if (openRow != null && openRow.EventType == "OPEN")
            {
                openRow.ExecQty      += addQty;
                openRow.FillPrice     = activeTrade.WeightedAvgEntryPrice;
                openRow.PositionAfter = positionAfter;
                openRow.AvgEntryAfter = activeTrade.WeightedAvgEntryPrice;
            }

            if (activeStudy != null && activeStudy.StopRows.Count > 0)
            {
                activeStudy.EntryPrice = activeTrade.WeightedAvgEntryPrice;
                activeStudy.EntryQty   = activeTrade.TotalEntryQty;
                foreach (EntryStudyRow r in activeStudy.StopRows)
                {
                    r.EntryPrice = activeStudy.EntryPrice;
                    r.EntryQty   = activeStudy.EntryQty;
                }
                WriteEntryStudy(activeStudy);
            }

            activeTrade.LastEventSessionBar = -1;
            activeTrade.LastEventTime       = ex.Time;

            DebugPrint("Entry fill merged (same order/window) — qty now " + activeTrade.TotalEntryQty.ToString(INV)
                + " @ " + F2(activeTrade.WeightedAvgEntryPrice));
        }

        private void HandleExitExecution(Execution ex, Order o, int closeQty, int positionBefore, int positionAfter,
            string exitMechanism, string exitLabel, string customFillId = null)
        {
            if (activeTrade == null || closeQty <= 0) return;

            double fillPrice      = ex.Price;
            double avgEntry       = activeTrade.WeightedAvgEntryPrice;
            double legPoints      = activeTrade.Direction == "LONG" ? fillPrice - avgEntry : avgEntry - fillPrice;
            double legPnLCurrency = legPoints * closeQty * Instrument.MasterInstrument.PointValue;

            activeTrade.RealizedPnLCurrency += legPnLCurrency;
            activeTrade.TotalExitQty        += closeQty;
            activeTrade.ExitPriceSum        += fillPrice * closeQty;
            activeTrade.WeightedAvgExitPrice = activeTrade.TotalExitQty > 0
                ? activeTrade.ExitPriceSum / activeTrade.TotalExitQty : 0;

            if (exitMechanism == "Target") activeTrade.ScaleOutCount++;
            activeTrade.CurrentQty        = positionAfter;
            activeTrade.LastExitMechanism = exitMechanism;
            activeTrade.LastExitLabel     = exitLabel;
            activeTrade.LastExitOrderName = o.Name ?? string.Empty;

            int sessionBar, sessionLastBar;
            GetBarInfo(ex.Time, out sessionBar, out sessionLastBar);
            int prevSessionBar = activeTrade.LastEventSessionBar;
            DateTime prevTime  = activeTrade.LastEventTime;

            // EventType for the event row — preserve SCALE_OUT/EXIT/REVERSAL_EXIT classification
            string eventType = exitMechanism == "Reversal" ? "REVERSAL_EXIT"
                : positionAfter == 0 && activeTrade.TotalExitQty == activeTrade.TotalEntryQty ? "EXIT"
                : "SCALE_OUT";

            activeTrade.EventRows.Add(new TradeEventRow
            {
                Sequence               = ++globalSequence,
                TradeID                = activeTrade.TradeID,
                EventID                = NextEventID(activeTrade),
                FillID                 = !string.IsNullOrEmpty(customFillId) ? customFillId : SafeFillId(ex.ExecutionId),
                Time                   = ex.Time,
                EventType              = eventType,
                Direction              = activeTrade.Direction,
                OrderName              = o.Name ?? string.Empty,
                Oco                    = o.Oco ?? string.Empty,
                OrderId                = o.Id,
                ExecQty                = closeQty,
                PositionBefore         = positionBefore,
                PositionAfter          = positionAfter,
                FillPrice              = fillPrice,
                AvgEntryBefore         = avgEntry,
                AvgEntryAfter          = activeTrade.WeightedAvgEntryPrice,
                LegPnLCurrency         = legPnLCurrency,
                CumRealizedPnLCurrency = activeTrade.RealizedPnLCurrency,
                ATMStop                = activeTrade.ATMStop,
                FirstProtectiveStop    = activeTrade.FirstProtectiveStop,
                InitialStop            = activeTrade.InitialStop,
                FirstActualStop        = activeTrade.FirstActualStop,
                CurrentStop            = activeTrade.CurrentStop,
                ActualStop             = activeTrade.CurrentStop,
                TargetAtEvent          = activeTrade.CurrentTarget,
                MAEPointsAtEvent       = activeTrade.TradeMAEPoints,
                MFEPointsAtEvent       = activeTrade.TradeMFEPoints,
                SessionBar             = sessionBar,
                BarsSinceTradeStart    = sessionBar >= 0 && activeTrade.StartSessionBar >= 0 ? sessionBar - activeTrade.StartSessionBar : -1,
                BarsSincePrevEvent     = sessionBar >= 0 && prevSessionBar >= 0 ? sessionBar - prevSessionBar : -1,
                MinsSinceTradeStart    = (ex.Time - activeTrade.StartTime).TotalMinutes,
                MinsSincePrevEvent     = (ex.Time - prevTime).TotalMinutes
            });

            activeTrade.LastEventSessionBar = sessionBar;
            activeTrade.LastEventTime       = ex.Time;

            FlushEventsIncremental();

            if (eventType == "SCALE_OUT" || eventType == "REVERSAL_EXIT")
                RequestScreenshot(exitLabel + "_" + activeTrade.TotalExitQty.ToString(INV),
                    ex.Time, activeTrade.TradeID, activeTrade.StartTime);

            if (positionAfter == 0)
                CloseTrade(ex.Time, sessionBar);
        }

        private void CloseTrade(DateTime endTime, int endSessionBar)
        {
            if (activeTrade == null) return;

            TradeSummaryRow summary = new TradeSummaryRow
            {
                TradeID               = activeTrade.TradeID,
                InstrumentName        = activeTrade.InstrumentName,
                StartTime             = activeTrade.StartTime,
                EndTime               = endTime,
                Direction             = activeTrade.Direction,
                EntryType             = activeTrade.EntryType,
                ExitMechanism         = activeTrade.LastExitMechanism ?? string.Empty,
                ExitLabel             = activeTrade.LastExitLabel ?? string.Empty,
                TotalEntryQty         = activeTrade.TotalEntryQty,
                TotalExitQty          = activeTrade.TotalExitQty,
                MaxPositionQty        = activeTrade.MaxPositionQty,
                FirstEntryPrice       = activeTrade.FirstEntryPrice,
                WeightedAvgEntryPrice = activeTrade.WeightedAvgEntryPrice,
                WeightedAvgExitPrice  = activeTrade.WeightedAvgExitPrice,
                ATMStop               = activeTrade.ATMStop,
                FirstProtectiveStop   = activeTrade.FirstProtectiveStop,
                InitialStop           = activeTrade.InitialStop,
                FirstActualStop       = activeTrade.FirstActualStop,
                CurrentStopAtExit     = activeTrade.CurrentStop,
                InitialRiskPoints     = GetRiskPoints(activeTrade.Direction, activeTrade.FirstEntryPrice, activeTrade.InitialStop),
                FirstActualRiskPoints = GetRiskPoints(activeTrade.Direction, activeTrade.FirstEntryPrice, activeTrade.FirstActualStop),
                GrossPnLCurrency      = activeTrade.RealizedPnLCurrency,
                TradeMAEPoints        = activeTrade.TradeMAEPoints,
                TradeMFEPoints        = activeTrade.TradeMFEPoints,
                ScaleInCount          = activeTrade.ScaleInCount,
                AddOnCount            = activeTrade.AddOnCount,
                ScaleOutCount         = activeTrade.ScaleOutCount,
                StartSessionBar       = activeTrade.StartSessionBar,
                EndSessionBar         = endSessionBar,
                BarsHeld              = endSessionBar >= 0 && activeTrade.StartSessionBar >= 0
                                        ? endSessionBar - activeTrade.StartSessionBar : -1,
                DurationMins          = (endTime - activeTrade.StartTime).TotalMinutes,
                TradeFolder           = activeTrade.TradeFolder
            };

            FlushEventsIncremental();
            WriteTradeSummary(summary, activeTrade.TradeID);

            DebugPrint("Trade closed: " + activeTrade.TradeID
                + " [" + summary.ExitMechanism + "/" + summary.ExitLabel + "]"
                + " PnL=" + F2(activeTrade.RealizedPnLCurrency));
            RequestScreenshot("EXIT", endTime, activeTrade.TradeID, activeTrade.StartTime);

            activeTrade = null;
            activeStudy = null;
        }

        #endregion

        #region Entry/Exit classification

        private string ClassifyEntryType(Order o)
        {
            if (o == null) return "Market";
           string name = (o.Name ?? string.Empty).Trim().ToUpperInvariant();

            // ATM orders typically have a name set to the template name
            // Market orders placed manually via Chart Trader have empty or generic names
          if (name.StartsWith("LONGPB33") || name.StartsWith("SHORTPB33")) return "PB33";
if (name.StartsWith("LONGPB50") || name.StartsWith("SHORTPB50")) return "PB50";
if (name.StartsWith("LONGPB66") || name.StartsWith("SHORTPB66")) return "PB66";
if (name.StartsWith("LONGBBSA") || name.StartsWith("SHORTBBSA")) return "BBSA";
if (name.StartsWith("LONGBO")   || name.StartsWith("SHORTBO"))   return "BO";

if (o.OrderType == OrderType.Market && string.IsNullOrEmpty(name))
    return "Market";

            if (o.OrderType == OrderType.Limit)
                return "Limit";

            // If there's a non-empty name it's likely an ATM template
            if (!string.IsNullOrEmpty(name))
                return "ATM_" + SanitizeLabel(name);

            return "Market";
        }

        private string ClassifyExitMechanism(Order o)
        {
            if (o == null) return "Market";
            if (IsStopOrder(o))   return "Stop";
            if (IsTargetOrder(o)) return "Target";
            return "Market";
        }

        private string ClassifyExitLabel(Order o, ActiveTrade trade)
        {
            if (o == null || trade == null) return "Market";
            string name = (o.Name ?? string.Empty).Trim().ToUpperInvariant();

            // MCScaleInStrategy signal names
if (name.StartsWith("LONGPB33") || name.StartsWith("SHORTPB33")) return "PB33";
if (name.StartsWith("LONGPB50") || name.StartsWith("SHORTPB50")) return "PB50";
if (name.StartsWith("LONGPB66") || name.StartsWith("SHORTPB66")) return "PB66";
if (name.StartsWith("LONGBBSA") || name.StartsWith("SHORTBBSA")) return "BBSA";
if (name.StartsWith("LONGBO")   || name.StartsWith("SHORTBO"))   return "BO";

// Target orders: "Target1", "Target2", "Target3" etc → T1, T2, T3
if (name.StartsWith("TARGET"))
            {
                string num = name.Replace("TARGET", "").Trim();
                return "T" + num;
            }

            // Stop orders
            if (IsStopOrder(o))
            {
                if (!trade.InitialStopLocked)
                    return "Stop_Initial";

                // Count actual stops fired so far
                int actualCount = activeStudy != null
                    ? activeStudy.StopRows.Count(r => r.StopEvent.StartsWith("ACTUAL_STOP"))
                    : 0;

                if (actualCount == 0) return "Stop_Initial";
                return "Stop_Actual_" + actualCount.ToString(INV);
            }

            // Market close
            if (o.OrderType == OrderType.Market)
                return "Market";

            return name;
        }

        private string SanitizeLabel(string value)
        {
            if (string.IsNullOrEmpty(value)) return string.Empty;
            // Remove spaces and special characters, keep alphanumeric and underscores
            System.Text.StringBuilder sb = new System.Text.StringBuilder();
            foreach (char c in value)
            {
                if (char.IsLetterOrDigit(c) || c == '_') sb.Append(c);
                else if (c == ' ') sb.Append('_');
            }
            return sb.ToString();
        }

        #endregion

        #region Stop handling

        private void HandleStopUpdate(double stopPrice, Order o)
        {
            if (activeTrade == null) return;
            DateTime now = Core.Globals.Now;

            if (activeTrade.FirstProtectiveStop <= 0)
            {
                activeTrade.FirstProtectiveStop          = stopPrice;
                activeTrade.FirstProtectiveStopLocalTime = now;
                activeTrade.CurrentStop                  = stopPrice;
                if (activeTrade.ATMStop <= 0) activeTrade.ATMStop = stopPrice;
                return;
            }

            if (activeTrade.CurrentStop.ApproxCompare(stopPrice) == 0 && !activeTrade.InitialStopLocked) return;

            if (!activeTrade.InitialStopStarted)
            {
                activeTrade.InitialStopStarted          = true;
                activeTrade.InitialStopWindowStartTime  = now;
                activeTrade.PendingInitialStopCandidate = stopPrice;
                activeTrade.InitialStop                 = stopPrice;
                activeTrade.InitialStopTime             = now;
                activeTrade.CurrentStop                 = stopPrice;
                return;
            }

            if (!activeTrade.InitialStopLocked)
            {
                if ((now - activeTrade.InitialStopWindowStartTime).TotalSeconds <= InitialStopLockSeconds)
                {
                    activeTrade.PendingInitialStopCandidate = stopPrice;
                    activeTrade.InitialStop                 = stopPrice;
                    activeTrade.InitialStopTime             = now;
                    activeTrade.CurrentStop                 = stopPrice;
                    return;
                }
                activeTrade.InitialStop       = activeTrade.PendingInitialStopCandidate;
                activeTrade.InitialStopLocked = true;
                AppendStopRowToStudy("INITIAL_STOP", activeTrade.InitialStop, now);
                if (stopPrice.ApproxCompare(activeTrade.InitialStop) != 0)
                {
                    activeTrade.CurrentStop = stopPrice;
                    if (!activeTrade.FirstActualCaptured)
                    {
                        activeTrade.FirstActualCaptured = true;
                        activeTrade.FirstActualStop     = stopPrice;
                        activeTrade.FirstActualStopTime = now;
                        AppendStopRowToStudy("ACTUAL_STOP_1", stopPrice, now);
                    }
                }
                return;
            }

            if (activeTrade.CurrentStop.ApproxCompare(stopPrice) != 0)
            {
                activeTrade.CurrentStop = stopPrice;
                if (!activeTrade.FirstActualCaptured)
                {
                    activeTrade.FirstActualCaptured = true;
                    activeTrade.FirstActualStop     = stopPrice;
                    activeTrade.FirstActualStopTime = now;
                    AppendStopRowToStudy("ACTUAL_STOP_1", stopPrice, now);
                }
                else
                {
                    int n = activeStudy != null
                        ? activeStudy.StopRows.Count(r => r.StopEvent.StartsWith("ACTUAL_STOP")) : 1;
                    AppendStopRowToStudy("ACTUAL_STOP_" + (n + 1).ToString(INV), stopPrice, now);
                }
            }
        }

        private void AppendStopRowToStudy(string stopEvent, double stopPrice, DateTime stopTime)
        {
            if (activeStudy == null) return;

            if (activeStudy.LastStopWrittenTime != default(DateTime) &&
                (stopTime - activeStudy.LastStopWrittenTime).TotalMilliseconds < 200)
            {
                DebugPrint("DEBOUNCE: Stop " + F2(stopPrice) + " within 200ms — skipped");
                return;
            }

            int sessionBar, sessionLastBar;
            GetBarInfo(stopTime, out sessionBar, out sessionLastBar);
            double riskPoints = GetRiskPoints(activeStudy.Direction, activeStudy.EntryPrice, stopPrice);

            activeStudy.StopRows.Add(new EntryStudyRow
            {
                TradeID         = activeStudy.TradeID,
                InstrumentName  = Instrument.FullName,
                Direction       = activeStudy.Direction,
                EntryPrice      = activeStudy.EntryPrice,
                EntryQty        = activeStudy.EntryQty,
                EntryTime       = activeStudy.EntryTime,
                EntrySessionBar = activeStudy.EntrySessionBar,
                StopEvent       = stopEvent,
                StopEventIndex  = activeStudy.StopRows.Count,
                StopPrice       = stopPrice,
                StopTime        = stopTime,
                StopSessionBar  = sessionBar,
                RiskPoints      = riskPoints
            });

            activeStudy.LastStopWrittenTime = stopTime;
            WriteEntryStudy(activeStudy);
            RequestScreenshot(stopEvent, stopTime, activeStudy.TradeID, activeStudy.EntryTime);

            DebugPrint(stopEvent + " appended: stop=" + F2(stopPrice) + " risk=" + F2(riskPoints) + " pts");
        }

        private void TryLockInitialStop()
        {
            if (activeTrade == null) return;
            if (!activeTrade.InitialStopStarted || activeTrade.InitialStopLocked) return;
            if ((Core.Globals.Now - activeTrade.InitialStopWindowStartTime).TotalSeconds < InitialStopLockSeconds) return;
            activeTrade.InitialStop       = activeTrade.PendingInitialStopCandidate;
            activeTrade.InitialStopLocked = true;
            AppendStopRowToStudy("INITIAL_STOP", activeTrade.InitialStop, activeTrade.InitialStopTime);
            DebugPrint("InitialStop locked at " + F2(activeTrade.InitialStop));
        }

        #endregion

        #region Target handling

        // Same settle-then-track-moves shape as HandleStopUpdate/TryLockInitialStop,
        // generalized per order name since there can be multiple live targets (T1/T2/T3).
        private void HandleTargetUpdate(double targetPrice, Order o)
        {
            if (activeTrade == null) return;
            DateTime now = Core.Globals.Now;
            string orderKey = SanitizeLabel((o.Name ?? "TARGET").Trim().ToUpperInvariant());
            if (string.IsNullOrEmpty(orderKey)) orderKey = "TARGET";

            activeTrade.CurrentTarget = targetPrice;

            TargetTrackState st;
            if (!activeTrade.Targets.TryGetValue(orderKey, out st))
            {
                st = new TargetTrackState();
                activeTrade.Targets[orderKey] = st;
            }

            if (!st.Started)
            {
                st.Started          = true;
                st.WindowStartTime  = now;
                st.PendingCandidate = targetPrice;
                return;
            }

            if (!st.Locked)
            {
                if ((now - st.WindowStartTime).TotalSeconds <= InitialStopLockSeconds)
                {
                    st.PendingCandidate = targetPrice;
                    return;
                }
                st.Locked      = true;
                st.LockedPrice = st.PendingCandidate;
                AppendTargetRowToStudy(orderKey + "_INITIAL", st.LockedPrice, now);
                if (targetPrice.ApproxCompare(st.LockedPrice) == 0) return;
                st.LockedPrice = targetPrice;
                st.MoveCount++;
                AppendTargetRowToStudy(orderKey + "_MOVED_" + st.MoveCount.ToString(INV), targetPrice, now);
                return;
            }

            if (st.LockedPrice.ApproxCompare(targetPrice) != 0)
            {
                st.LockedPrice = targetPrice;
                st.MoveCount++;
                AppendTargetRowToStudy(orderKey + "_MOVED_" + st.MoveCount.ToString(INV), targetPrice, now);
            }
        }

        private void AppendTargetRowToStudy(string targetEvent, double targetPrice, DateTime targetTime)
        {
            if (activeStudy == null) return;

            if (activeStudy.LastStopWrittenTime != default(DateTime) &&
                (targetTime - activeStudy.LastStopWrittenTime).TotalMilliseconds < 200)
            {
                DebugPrint("DEBOUNCE: Target " + F2(targetPrice) + " within 200ms — skipped");
                return;
            }

            int sessionBar, sessionLastBar;
            GetBarInfo(targetTime, out sessionBar, out sessionLastBar);
            // RiskEvent.riskPoints is generically "distance from entry at this
            // checkpoint" (both STOP and TARGET kinds) — not direction-clamped
            // like GetRiskPoints, since a target is always on the favorable side.
            double distPoints = Math.Abs(targetPrice - activeStudy.EntryPrice);

            activeStudy.StopRows.Add(new EntryStudyRow
            {
                TradeID         = activeStudy.TradeID,
                InstrumentName  = Instrument.FullName,
                Direction       = activeStudy.Direction,
                EntryPrice      = activeStudy.EntryPrice,
                EntryQty        = activeStudy.EntryQty,
                EntryTime       = activeStudy.EntryTime,
                EntrySessionBar = activeStudy.EntrySessionBar,
                StopEvent       = targetEvent,
                StopEventIndex  = activeStudy.StopRows.Count,
                StopPrice       = targetPrice,
                StopTime        = targetTime,
                StopSessionBar  = sessionBar,
                RiskPoints      = distPoints
            });

            activeStudy.LastStopWrittenTime = targetTime;
            WriteEntryStudy(activeStudy);
            RequestScreenshot(targetEvent, targetTime, activeStudy.TradeID, activeStudy.EntryTime);

            DebugPrint(targetEvent + " appended: target=" + F2(targetPrice) + " dist=" + F2(distPoints) + " pts");
        }

        // Fallback for the same reason TryLockInitialStop exists: if a target's price
        // never changes again after its first settle, no further OrderUpdate fires to
        // trigger the lock — called every bar to lock once the settle window elapses.
        private void TryLockTargets()
        {
            if (activeTrade == null) return;
            foreach (KeyValuePair<string, TargetTrackState> kv in activeTrade.Targets)
            {
                TargetTrackState st = kv.Value;
                if (!st.Started || st.Locked) continue;
                if ((Core.Globals.Now - st.WindowStartTime).TotalSeconds < InitialStopLockSeconds) continue;
                st.Locked      = true;
                st.LockedPrice = st.PendingCandidate;
                AppendTargetRowToStudy(kv.Key + "_INITIAL", st.LockedPrice, Core.Globals.Now);
            }
        }

        #endregion

        #region Trade excursions

        // Fed from live tick prices (OnMarketData) instead of bar High/Low — an AddOn has no
        // bars. Tick-level is at least as accurate as bar-level, arguably more so.
        private void UpdateOpenTradeExcursions(double price)
        {
            if (activeTrade == null) return;
            double mfe, mae;
            if (activeTrade.Direction == "LONG")
            { mfe = price - activeTrade.FirstEntryPrice; mae = price - activeTrade.FirstEntryPrice; }
            else
            { mfe = activeTrade.FirstEntryPrice - price; mae = activeTrade.FirstEntryPrice - price; }
            activeTrade.TradeMFEPoints = Math.Max(activeTrade.TradeMFEPoints, mfe);
            activeTrade.TradeMAEPoints = Math.Min(activeTrade.TradeMAEPoints, mae);
        }

        #endregion

        #region Screenshot

        // Native window P/Invoke — see header comment. Application.Current.Windows is empty
        // (confirmed live, 2026-10-23, commit eaf8d47c's diagnostic dump: count=0 on every
        // single miss) because NT8 chart windows run on their own dedicated UI thread and WPF
        // only auto-registers a Window there when it's created on the main Application thread.
        // Walking native hwnds via EnumWindows sidesteps that collection entirely.
        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll")]
        private static extern int GetWindowTextLength(IntPtr hWnd);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

        private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        private static List<IntPtr> GetTopLevelWindowsForCurrentProcess()
        {
            List<IntPtr> result = new List<IntPtr>();
            uint pid = (uint)Process.GetCurrentProcess().Id;
            EnumWindows((hWnd, lParam) =>
            {
                uint windowPid;
                GetWindowThreadProcessId(hWnd, out windowPid);
                if (windowPid == pid) result.Add(hWnd);
                return true;
            }, IntPtr.Zero);
            return result;
        }

        private static string GetWindowTitle(IntPtr hWnd)
        {
            int len = GetWindowTextLength(hWnd);
            if (len <= 0) return string.Empty;
            System.Text.StringBuilder sb = new System.Text.StringBuilder(len + 1);
            GetWindowText(hWnd, sb, sb.Capacity);
            return sb.ToString();
        }

        // An AddOn has no ChartControl of its own (unlike a Strategy, which gets one for free
        // from whatever chart it's dropped on) — this finds one. MATCH STRATEGY (rewritten
        // 2026-10-23, twice same day): v1 used Application.Current.Windows — always empty
        // (chart windows live on their own UI thread, never auto-registered there). v2
        // switched to native EnumWindows + Chart.ActiveChartControl/MainTabControl — found
        // the real windows, but every one came back active=(none)/tabs=null when probed that
        // way; that WPF introspection just doesn't reflect live state here. v3 (this version)
        // dropped that introspection for window TITLE matching ("Chart - <FullName>", confirmed
        // live via raw Win32 GetWindowText) — got a REAL screenshot, but from the WRONG window:
        // title only identifies the instrument, not which specific chart/tab is the trading
        // one, so when more than one open chart has the same instrument active, title matching
        // picks an arbitrary one. v4 (current): a tiny marker indicator the user drops on the
        // ONE real execution chart (ClaudeTrackerChartTag.cs) registers that exact ChartControl
        // into ClaudeTrackerChartRegistry, keyed by instrument full name — checked FIRST here,
        // unambiguous because only the tagged chart is in it. Title matching stays as a
        // fallback for instruments nobody has tagged yet. targetChart.Dispatcher is still
        // needed for the ACTUAL screenshot call either way (GetScreenshot only works on the
        // window's own thread) — that hop is unavoidable and unchanged.
        private void RequestScreenshot(string label, DateTime time, string tradeId, DateTime tradeTime)
        {
            if (instrument == null) return;
            try
            {
                string fileName   = TradeFileStem(tradeId, tradeTime) + "_" + label + ".png";
                string tradeDir   = EnsureTradeFolder(tradeId, tradeTime);
                string masterDir  = EnsureMasterScreenshotsFolder(tradeTime);
                string tradePath  = Path.Combine(tradeDir, fileName);
                string masterPath = Path.Combine(masterDir, fileName);
                string wantFullName = instrument.FullName;
                string wantTitlePrefix = "Chart - " + wantFullName;

                NinjaTrader.Gui.Chart.ChartControl taggedCC = ClaudeTrackerChartRegistry.Get(wantFullName);
                if (taggedCC != null)
                {
                    taggedCC.Dispatcher.InvokeAsync(async () =>
                    {
                        try
                        {
                            Chart targetChart = Window.GetWindow(taggedCC.Parent) as Chart;
                            if (targetChart == null)
                            {
                                Log("[ClaudeTrackerAddOn] Screenshot: tagged chart's ChartControl has no parent Chart window"
                                    + " — falling back to title match next time", LogLevel.Warning);
                                return;
                            }

                            await System.Threading.Tasks.Task.Delay(ScreenshotDelayMs);

                            RenderTargetBitmap sc = targetChart.GetScreenshot(ShareScreenshotType.Chart);
                            if (sc == null) { Log("[ClaudeTrackerAddOn] Screenshot: null capture (tagged chart)", LogLevel.Warning); return; }

                            PngBitmapEncoder e1 = new PngBitmapEncoder();
                            e1.Frames.Add(BitmapFrame.Create(sc));
                            using (Stream s = File.Create(tradePath)) e1.Save(s);

                            PngBitmapEncoder e2 = new PngBitmapEncoder();
                            e2.Frames.Add(BitmapFrame.Create(sc));
                            using (Stream s = File.Create(masterPath)) e2.Save(s);

                            DebugPrint("Screenshot saved (tagged chart): " + fileName);
                        }
                        catch (Exception ex) { Log("[ClaudeTrackerAddOn] Screenshot capture failed (tagged chart): " + ex.Message, LogLevel.Error); }
                    });
                    return;
                }

                Log("[ClaudeTrackerAddOn] Screenshot: tagged-chart registry has no entry for \"" + wantFullName
                    + "\" — using ambiguous title-match fallback (picks arbitrarily if >1 chart shows this instrument)."
                    + " Re-add ClaudeTracker Chart Tag on the real execution chart to restore exact targeting.", LogLevel.Warning);

                System.Threading.Tasks.Task.Run(() =>
                {
                    try
                    {
                        List<IntPtr> hwnds = GetTopLevelWindowsForCurrentProcess();
                        List<KeyValuePair<IntPtr, string>> titled = new List<KeyValuePair<IntPtr, string>>();

                        foreach (IntPtr hwnd in hwnds)
                        {
                            string title = GetWindowTitle(hwnd);
                            if (!string.IsNullOrEmpty(title)) titled.Add(new KeyValuePair<IntPtr, string>(hwnd, title));
                        }

                        // StartsWith (not Contains) deliberately: "Chart - MES 12-26" contains
                        // "ES 12-26" as a substring, which Contains would wrongly match against
                        // instrument "ES 12-26" — StartsWith requires the characters right after
                        // "Chart - " to match exactly, so MES vs ES can't collide.
                        List<KeyValuePair<IntPtr, string>> candidates = new List<KeyValuePair<IntPtr, string>>();
                        foreach (KeyValuePair<IntPtr, string> kv in titled)
                        {
                            if (kv.Value.StartsWith(wantTitlePrefix, StringComparison.Ordinal)) candidates.Add(kv);
                        }

                        IntPtr matchHwnd = candidates.Count > 0 ? candidates[0].Key : IntPtr.Zero;

                        if (candidates.Count > 1)
                        {
                            Log("[ClaudeTrackerAddOn] Screenshot: " + candidates.Count + " windows titled \""
                                + wantTitlePrefix + "...\" — picked the first by enumeration order, not necessarily"
                                + " the trading chart:", LogLevel.Warning);
                            foreach (KeyValuePair<IntPtr, string> kv in candidates)
                                Log("[ClaudeTrackerAddOn]   hwnd=" + kv.Key + " title=\"" + kv.Value + "\""
                                    + (kv.Key == matchHwnd ? "  <-- chosen" : ""), LogLevel.Warning);
                        }

                        if (matchHwnd == IntPtr.Zero)
                        {
                            Log("[ClaudeTrackerAddOn] Screenshot: no window titled \"" + wantTitlePrefix
                                + "...\" across " + titled.Count + " titled windows (" + hwnds.Count + " total process windows):",
                                LogLevel.Warning);
                            foreach (KeyValuePair<IntPtr, string> kv in titled)
                                Log("[ClaudeTrackerAddOn]   hwnd=" + kv.Key + " title=\"" + kv.Value + "\"", LogLevel.Warning);
                            return;
                        }

                        HwndSource hs = HwndSource.FromHwnd(matchHwnd);
                        if (hs == null)
                        {
                            Log("[ClaudeTrackerAddOn] Screenshot: matched window has no HwndSource — cannot capture", LogLevel.Warning);
                            return;
                        }

                        hs.Dispatcher.InvokeAsync(async () =>
                        {
                            try
                            {
                                Chart targetChart = hs.RootVisual as Chart;
                                if (targetChart == null)
                                {
                                    Log("[ClaudeTrackerAddOn] Screenshot: matched window's RootVisual is not a Chart (type="
                                        + (hs.RootVisual == null ? "null" : hs.RootVisual.GetType().FullName) + ")", LogLevel.Warning);
                                    return;
                                }

                                await System.Threading.Tasks.Task.Delay(ScreenshotDelayMs);

                                RenderTargetBitmap sc = targetChart.GetScreenshot(ShareScreenshotType.Chart);
                                if (sc == null) { Log("[ClaudeTrackerAddOn] Screenshot: null capture", LogLevel.Warning); return; }

                                PngBitmapEncoder e1 = new PngBitmapEncoder();
                                e1.Frames.Add(BitmapFrame.Create(sc));
                                using (Stream s = File.Create(tradePath)) e1.Save(s);

                                PngBitmapEncoder e2 = new PngBitmapEncoder();
                                e2.Frames.Add(BitmapFrame.Create(sc));
                                using (Stream s = File.Create(masterPath)) e2.Save(s);

                                DebugPrint("Screenshot saved: " + fileName);
                            }
                            catch (Exception ex) { Log("[ClaudeTrackerAddOn] Screenshot capture failed: " + ex.Message, LogLevel.Error); }
                        });
                    }
                    catch (Exception ex) { Log("[ClaudeTrackerAddOn] Screenshot window-lookup failed: " + ex.Message, LogLevel.Error); }
                });
            }
            catch (Exception ex) { Log("[ClaudeTrackerAddOn] Screenshot request failed: " + ex.Message, LogLevel.Error); }
        }

        #endregion

        #region Folder helpers

        // ─── Folder structure ──────────────────────────────────────────────
        // ClaudeTracker/ES_06-26/2026-03/Masters/Trades_MASTER.csv
        //                                        Events_MASTER.csv
        //                                        EntryStudy_MASTER.csv
        //                                        Screenshots_MASTER/
        //                                03-26/03-26_Thu_T1_LONG_0935/
        //                                      03-26_Thu_T1_LONG_0935_TradeSummary.csv
        //                                      03-26_Thu_T1_LONG_0935_Events.csv
        //                                      03-26_Thu_T1_LONG_0935_EntryStudy.csv
        //                                      03-26_Thu_T1_LONG_0935_ENTRY.png

      private string MonthRoot(DateTime time)
{
    return Path.Combine(outputRoot, time.ToString("yyyy-MM-dd", INV));
}

        private string MastersFolder(DateTime time)
{
    string path = MonthRoot(time);
    if (!Directory.Exists(path)) Directory.CreateDirectory(path);
    return path;
}

        private string EnsureMasterScreenshotsFolder(DateTime time)
        {
            string path = Path.Combine(MastersFolder(time), "Screenshots_MASTER");
            if (!Directory.Exists(path)) Directory.CreateDirectory(path);
            return path;
        }

       private string EnsureTradeFolder(string tradeId, DateTime time)
{
    string stem = TradeFileStem(tradeId, time);
    string path = Path.Combine(MonthRoot(time), stem);
    if (!Directory.Exists(path)) Directory.CreateDirectory(path);
    return path;
}

        #endregion

        #region CSV writers — EntryStudy

        private string EntryStudyMasterPath(DateTime date)
        {
            return Path.Combine(MastersFolder(date), "EntryStudy_MASTER.csv");
        }

        private void WriteEntryStudy(SessionStudy study)
        {
            WriteEntryStudyMerged(EntryStudyMasterPath(study.EntryTime), study);
            string tradePath = Path.Combine(EnsureTradeFolder(study.TradeID, study.EntryTime),
                TradeFileStem(study.TradeID, study.EntryTime) + "_EntryStudy.csv");
            WriteEntryStudyFile(tradePath, study);
        }

        private void WriteEntryStudyMerged(string path, SessionStudy study)
        {
            try
            {
                List<string> existingLines = new List<string>();
                string header = string.Empty;
                if (File.Exists(path))
                {
                    string[] allLines = File.ReadAllLines(path);
                    if (allLines.Length > 0)
                    {
                        header = allLines[0];
                        for (int i = 1; i < allLines.Length; i++)
                            if (!allLines[i].Contains("\"" + study.TradeID + "\""))
                                existingLines.Add(allLines[i]);
                    }
                }
                using (StreamWriter sw = new StreamWriter(path, false))
                {
                    sw.WriteLine(string.IsNullOrEmpty(header) ? EntryStudyHeader() : header);
                    foreach (string line in existingLines) sw.WriteLine(line);
                    foreach (EntryStudyRow r in study.StopRows) sw.WriteLine(EntryStudyRowCsv(r));
                }
                DebugPrint("EntryStudy merged: " + study.StopRows.Count + " rows for " + study.TradeID);
            }
            catch (Exception ex) { Log("CSV ERROR (ENTRY STUDY MERGED): " + ex.Message + " — close the file and hit F5", LogLevel.Error); }
        }

        private void WriteEntryStudyFile(string path, SessionStudy study)
        {
            try
            {
                using (StreamWriter sw = new StreamWriter(path, false))
                {
                    sw.WriteLine(EntryStudyHeader());
                    foreach (EntryStudyRow r in study.StopRows) sw.WriteLine(EntryStudyRowCsv(r));
                }
            }
            catch (Exception ex) { Log("CSV ERROR (ENTRY STUDY): " + ex.Message, LogLevel.Error); }
        }

        private string EntryStudyHeader()
        {
            return "TradeID,Instrument,Direction,EntryPrice,EntryQty,EntryTime,EntrySessionBar," +
                   "StopEvent,StopPrice,StopTime,StopSessionBar,RiskPoints," +
                   "MFEPoints,MAEPoints," +
                   "MaxR,MAEinR,RR,SessionClosePrice," +
                   "BarsTo1R,MinsTo1R,BarsTo2R,MinsTo2R,BarsTo3R,MinsTo3R,BarsToMaxR,MinsToMaxR," +
                   "MFEPoints_AtStop,MAEPoints_AtStop,MaxR_AtStop,MAEinR_AtStop," +
                   "MFEPoints_Window,MAEPoints_Window,MaxR_Window,MAEinR_Window";
        }

        private string EntryStudyRowCsv(EntryStudyRow r)
        {
            bool isEntry = r.StopEvent == "ENTRY" || r.StopEvent == "SCALE_IN";
            return string.Join(",",
                Csv(r.TradeID), Csv(r.InstrumentName), Csv(r.Direction),
                Csv(F2(r.EntryPrice)), Csv(r.EntryQty.ToString(INV)),
                Csv(r.EntryTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                Csv(r.EntrySessionBar.ToString(INV)),
                Csv(r.StopEvent),
                isEntry ? Csv("") : Csv(F2(r.StopPrice)),
                isEntry || r.StopTime == default(DateTime) ? Csv("") : Csv(r.StopTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                isEntry || r.StopSessionBar < 0 ? Csv("") : Csv(r.StopSessionBar.ToString(INV)),
                isEntry ? Csv("") : Csv(F2(r.RiskPoints)),
                // Phase 2 — blank, calculated in Sheets
                Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""),
                Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""),
                Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv("")
            );
        }

        #endregion

        #region CSV writers — Events and Trades

        // Writes activeTrade.EventRows to disk NOW instead of waiting for CloseTrade.
        // Found 2026-10-28: Events.csv/TradeSummary.csv were write-on-close only, so any
        // fill recorded in memory before the trade fully flattened (e.g. a profitable partial
        // target) was permanently lost from the journal if the AddOn reloaded mid-trade —
        // no file ever existed for it, nothing to recover. TradeSummary.csv stays write-on-
        // close (it marks a trade "done" for journal_uploader.py — an interim one would read
        // as a premature close). The per-trade Events.csv is always rewritten whole (cheap,
        // idempotent). The master Events_MASTER.csv is append-only, so only rows not yet
        // flushed are appended, tracked by EventRowsFlushedCount, to avoid re-appending the
        // same rows on every call.
        private void FlushEventsIncremental()
        {
            if (activeTrade == null || activeTrade.EventRows.Count == 0) return;
            List<TradeEventRow> rows = activeTrade.EventRows;

            string tradePath = Path.Combine(EnsureTradeFolder(activeTrade.TradeID, rows[0].Time),
                TradeFileStem(activeTrade.TradeID, rows[0].Time) + "_Events.csv");
            WriteEventFile(tradePath, rows, false);

            if (activeTrade.EventRowsFlushedCount < rows.Count)
            {
                List<TradeEventRow> newRows = rows.GetRange(activeTrade.EventRowsFlushedCount,
                    rows.Count - activeTrade.EventRowsFlushedCount);
                string masterPath = Path.Combine(MastersFolder(rows[0].Time), "Events_MASTER.csv");
                WriteEventFile(masterPath, newRows, true);
                activeTrade.EventRowsFlushedCount = rows.Count;
            }
        }

        private void WriteTradeSummary(TradeSummaryRow row, string tradeId)
        {
            string masterPath = Path.Combine(MastersFolder(row.StartTime), "Trades_MASTER.csv");
            string tradePath  = Path.Combine(EnsureTradeFolder(tradeId, row.StartTime),
                TradeFileStem(tradeId, row.StartTime) + "_TradeSummary.csv");
            WriteTradeFile(masterPath, row, true);
            WriteTradeFile(tradePath,  row, false);
        }

        private void WriteEventFile(string path, List<TradeEventRow> rows, bool append)
        {
            try
            {
                bool exists = File.Exists(path);
                using (StreamWriter sw = new StreamWriter(path, append))
                {
                    if (!exists || !append)
                        sw.WriteLine("TradeID,EventID,FillID,Time,EventType,Direction,OrderName,Oco,OrderId," +
                            "ExecQty,PositionBefore,PositionAfter,FillPrice,AvgEntryBefore,AvgEntryAfter," +
                            "LegPnLCurrency,CumRealizedPnLCurrency,ATMStop,FirstProtectiveStop,InitialStop," +
                            "FirstActualStop,CurrentStop,ActualStop,TargetAtEvent,MAEPointsAtEvent,MFEPointsAtEvent,SessionBar," +
                            "BarsSinceTradeStart,BarsSincePrevEvent,MinsSinceTradeStart,MinsSincePrevEvent");

                    foreach (TradeEventRow r in rows.OrderBy(x => x.Sequence))
                        sw.WriteLine(string.Join(",",
                            Csv(r.TradeID), Csv(r.EventID), Csv(r.FillID),
                            Csv(r.Time.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                            Csv(r.EventType), Csv(r.Direction), Csv(r.OrderName), Csv(r.Oco),
                            Csv(r.OrderId.ToString(INV)), Csv(r.ExecQty.ToString(INV)),
                            Csv(r.PositionBefore.ToString(INV)), Csv(r.PositionAfter.ToString(INV)),
                            Csv(F2(r.FillPrice)), Csv(F2(r.AvgEntryBefore)), Csv(F2(r.AvgEntryAfter)),
                            Csv(F2(r.LegPnLCurrency)), Csv(F2(r.CumRealizedPnLCurrency)),
                            Csv(F2(r.ATMStop)), Csv(F2(r.FirstProtectiveStop)), Csv(F2(r.InitialStop)),
                            Csv(F2(r.FirstActualStop)), Csv(F2(r.CurrentStop)), Csv(F2(r.ActualStop)),
                            Csv(F2(r.TargetAtEvent)), Csv(F2(r.MAEPointsAtEvent)), Csv(F2(r.MFEPointsAtEvent)),
                            Csv(r.SessionBar.ToString(INV)),
                            Csv(r.BarsSinceTradeStart.ToString(INV)),
                            Csv(r.BarsSincePrevEvent.ToString(INV)),
                            Csv(F2(r.MinsSinceTradeStart)), Csv(F2(r.MinsSincePrevEvent))));
                }
            }
            catch (Exception ex) { Log("CSV ERROR (EVENTS): " + ex.Message, LogLevel.Error); }
        }

        private void WriteTradeFile(string path, TradeSummaryRow r, bool append)
        {
            try
            {
                bool exists = File.Exists(path);
                using (StreamWriter sw = new StreamWriter(path, append))
                {
                    if (!exists || !append)
                        sw.WriteLine("TradeID,Instrument,StartTime,EndTime,Direction," +
                            "EntryType,ExitMechanism,ExitLabel," +
                            "TotalEntryQty,TotalExitQty,MaxPositionQty,FirstEntryPrice," +
                            "WeightedAvgEntryPrice,WeightedAvgExitPrice,ATMStop,FirstProtectiveStop," +
                            "InitialStop,FirstActualStop,CurrentStopAtExit,InitialRiskPoints," +
                            "FirstActualRiskPoints,GrossPnLCurrency,TradeMAEPoints,TradeMFEPoints," +
                            "ScaleInCount,AddOnCount,ScaleOutCount," +
                            "StartSessionBar,EndSessionBar," +
                            "BarsHeld,DurationMins,TradeFolder");

                    sw.WriteLine(string.Join(",",
                        Csv(r.TradeID), Csv(r.InstrumentName),
                        Csv(r.StartTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                        Csv(r.EndTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                        Csv(r.Direction),
                        Csv(r.EntryType), Csv(r.ExitMechanism), Csv(r.ExitLabel),
                        Csv(r.TotalEntryQty.ToString(INV)), Csv(r.TotalExitQty.ToString(INV)),
                        Csv(r.MaxPositionQty.ToString(INV)), Csv(F2(r.FirstEntryPrice)),
                        Csv(F2(r.WeightedAvgEntryPrice)), Csv(F2(r.WeightedAvgExitPrice)),
                        Csv(F2(r.ATMStop)), Csv(F2(r.FirstProtectiveStop)),
                        Csv(F2(r.InitialStop)), Csv(F2(r.FirstActualStop)),
                        Csv(F2(r.CurrentStopAtExit)), Csv(F2(r.InitialRiskPoints)),
                        Csv(F2(r.FirstActualRiskPoints)), Csv(F2(r.GrossPnLCurrency)),
                        Csv(F2(r.TradeMAEPoints)), Csv(F2(r.TradeMFEPoints)),
                        Csv(r.ScaleInCount.ToString(INV)), Csv(r.AddOnCount.ToString(INV)),
                        Csv(r.ScaleOutCount.ToString(INV)),
                        Csv(r.StartSessionBar.ToString(INV)), Csv(r.EndSessionBar.ToString(INV)),
                        Csv(r.BarsHeld.ToString(INV)), Csv(F2(r.DurationMins)),
                        Csv(r.TradeFolder)));
                }
            }
            catch (Exception ex) { Log("CSV ERROR (TRADES): " + ex.Message, LogLevel.Error); }
        }

        #endregion

        #region Helpers
		
		private int CountTodaysTrades()
{
    try
    {
        string today        = DateTime.Now.ToString("yyyy-MM", INV);
        string instrumentDir = SanitizeFilePart(SymbolName); // called from SetDefaults, before `instrument` resolves
        string masterPath   = Path.Combine(outputRoot, instrumentDir, today, "Masters", "Events_MASTER.csv");

        if (!File.Exists(masterPath)) return 0;

        string todayDate = DateTime.Now.ToString("yyyy-MM-dd", INV);
        int maxT = 0;

        foreach (string line in File.ReadAllLines(masterPath))
        {
            // TradeID format: ES_06-26_20260415_093000_LONG_T3
            // Look for lines containing today's date and extract T number
            if (!line.Contains(todayDate)) continue;
            int tIdx = line.LastIndexOf("_T", StringComparison.Ordinal);
            if (tIdx < 0) continue;
            // Extract number after _T up to next quote or comma
            int start = tIdx + 2;
            int end   = start;
            while (end < line.Length && char.IsDigit(line[end])) end++;
            if (end > start)
            {
                int n;
                if (int.TryParse(line.Substring(start, end - start), out n))
                    if (n > maxT) maxT = n;
            }
        }
        return maxT;
    }
    catch { return 0; }
}

        // No bars to derive a session-bar number from (an AddOn has none) — always -1,
        // which every call site already treats as "unknown" (the Strategy version's own
        // graceful-degradation path for when sessionIterator wasn't ready yet), so nothing
        // downstream needed to change. DurationMins/MinsSinceTradeStart (real elapsed wall
        // time, tracked separately) cover what SessionBar/BarsHeld used to approximate.
        private void GetBarInfo(DateTime time, out int sessionBar, out int sessionLastBar)
        {
            sessionBar = -1; sessionLastBar = -1;
        }

        private bool IsDuplicateExecution(Execution ex, Order o)
        {
            string key = string.Join("|", ex.ExecutionId ?? string.Empty, o.Id.ToString(INV),
                ex.Time.ToString("O", INV), ex.Quantity.ToString(INV), ex.Price.ToString("F8", INV));
            if (processedExecutions.Contains(key)) return true;
            processedExecutions.Add(key);
            return false;
        }

        private int GetSignedQty(OrderAction action, int qty)
        {
            switch (action)
            {
                case OrderAction.Buy:
                case OrderAction.BuyToCover: return qty;
                case OrderAction.Sell:
                case OrderAction.SellShort:  return -qty;
                default:                     return 0;
            }
        }

        private bool IsStopOrder(Order o)
        { return o.OrderType == OrderType.StopMarket || o.OrderType == OrderType.StopLimit; }

        private bool IsTargetOrder(Order o)
        { return o.OrderType == OrderType.Limit || o.OrderType == OrderType.MIT; }

        private double GetTargetPrice(Order o)
        { return o != null && o.LimitPrice > 0 ? o.LimitPrice : 0; }

        private string ClassifyAddType(string direction, double avgBefore, double price)
        {
            if (direction == "LONG") return price < avgBefore ? "SCALE_IN" : "ADD_ON";
            return price > avgBefore ? "SCALE_IN" : "ADD_ON";
        }

        private string NextEventID(ActiveTrade trade)
        { trade.EventCounter++; return trade.TradeID + "_E" + trade.EventCounter.ToString(INV); }

        private double GetRiskPoints(string direction, double entryPrice, double stopPrice)
        {
            if (stopPrice <= 0) return 0;
            if (direction == "LONG") return Math.Max(0, entryPrice - stopPrice);
            return Math.Max(0, stopPrice - entryPrice);
        }

        private string SafeFillId(string executionId)
        { return string.IsNullOrEmpty(executionId) ? string.Empty : executionId; }

        private string TradeFileStem(string tradeId, DateTime time)
        {
            // Format: 03-26_Thu_T1_LONG_0935
            string direction = tradeId.Contains("_LONG_") ? "LONG" : "SHORT";
            string tNum      = string.Empty;
            int tIdx         = tradeId.LastIndexOf("_T", StringComparison.Ordinal);
            if (tIdx >= 0) tNum = tradeId.Substring(tIdx + 1);
            return time.ToString("MM-dd", INV) + "_"
                 + time.ToString("ddd", CultureInfo.InvariantCulture) + "_"
                 + tNum + "_" + direction + "_"
                 + time.ToString("HHmm", INV);
        }

        private string SanitizeFilePart(string value)
        {
            if (string.IsNullOrEmpty(value)) return "NA";
            foreach (char c in Path.GetInvalidFileNameChars()) value = value.Replace(c, '_');
            return value.Replace(" ", "_");
        }

        private string F2(double value) { return value.ToString("F2", INV); }

        private string Csv(string s)
        {
            if (s == null) s = string.Empty;
            return "\"" + s.Replace("\"", "\"\"") + "\"";
        }

        // ClaudeTracker_Health.json is the only JSON this file writes — everything else is
        // CSV, which is why there's no general JSON library dependency here, just this one
        // minimal escaper (backslash and quote, the two that break a JSON string literal).
        private string JsonStr(string s)
        {
            if (s == null) s = string.Empty;
            return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        }

        private void DebugPrint(string message)
        {
            if (DebugMode)
                Log("[ClaudeTrackerAddOn] " + DateTime.Now.ToString("HH:mm:ss.fff", INV) + " " + message, LogLevel.Information);
        }

        #endregion
    }

    internal static class ApproxExtensions
    {
        public static int ApproxCompare(this double a, double b, double eps = 1e-10)
        {
            if (Math.Abs(a - b) <= eps) return 0;
            return a < b ? -1 : 1;
        }
    }
}
