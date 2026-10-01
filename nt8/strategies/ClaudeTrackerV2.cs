#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Globalization;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class ClaudeTrackerV2 : Strategy
    {
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

        private class ActiveTrade
        {
            public string TradeID;
            public string InstrumentName;
            public string Direction;
            public string EntryType;        // ATM_<name> | Market | Limit
            public string EntryOrderName;   // raw order name from NT for ATM template extraction
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
            public int EventCounter;
            public List<TradeEventRow> EventRows = new List<TradeEventRow>();
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
        private SessionIterator sessionIterator;
        private ActiveTrade activeTrade;
        private SessionStudy activeStudy;
        private string outputRoot;
        private int dailyTradeCounter = 0;
        private readonly HashSet<string> processedExecutions = new HashSet<string>();
        private long globalSequence = 0;

        #endregion

        #region User parameters

        [NinjaScriptProperty]
        [Display(Name = "Initial Stop Lock Seconds", Order = 1, GroupName = "Parameters")]
        public int InitialStopLockSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Screenshot Delay (ms)", Order = 2, GroupName = "Parameters")]
        public int ScreenshotDelayMs { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Debug Mode", Order = 3, GroupName = "Parameters")]
        public bool DebugMode { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export Root Folder", Order = 4, GroupName = "Parameters",
            Description = "Base folder for CSV/screenshot export. An ES or MES subfolder is created under it automatically.")]
        public string ExportRootFolder { get; set; }

        #endregion

        #region State

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                   = "ClaudeTrackerV2";
                Calculate              = Calculate.OnEachTick;
                IsOverlay              = true;
                InitialStopLockSeconds = 5;
                ScreenshotDelayMs      = 100;
                DebugMode              = true;
                ExportRootFolder       = @"G:\My Drive\!NT Tracker Export";
                RealtimeErrorHandling  = RealtimeErrorHandling.IgnoreAllErrors;
                StartBehavior          = StartBehavior.AdoptAccountPosition;
            }
            else if (State == State.Configure)
            {
                string instrumentFolder = Instrument.FullName.Contains("MES") ? "MES" : "ES";
                string root = string.IsNullOrWhiteSpace(ExportRootFolder)
                    ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "NinjaTrader 8", "ClaudeTracker")
                    : ExportRootFolder;
                outputRoot = Path.Combine(root, instrumentFolder);
                if (!Directory.Exists(outputRoot))
                    Directory.CreateDirectory(outputRoot);
            }
            else if (State == State.DataLoaded)
{
    sessionIterator      = new SessionIterator(Bars);
    dailyTradeCounter    = CountTodaysTrades();
    if (Account != null)
    {
        Account.OrderUpdate     += OnAccountOrderUpdate;
        Account.ExecutionUpdate += OnAccountExecutionUpdate;
    }
    DebugPrint("Loaded. Resuming from trade #" + dailyTradeCounter.ToString(INV));
}
            else if (State == State.Terminated)
            {
                if (Account != null)
                {
                    Account.OrderUpdate     -= OnAccountOrderUpdate;
                    Account.ExecutionUpdate -= OnAccountExecutionUpdate;
                }
            }
        }

        #endregion

        #region Core bar loop

        protected override void OnBarUpdate()
        {
            if (State != State.Realtime) return;
            if (CurrentBar < 1) return;
            UpdateOpenTradeExcursions();
            TryLockInitialStop();
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
                else if (IsTargetOrder(o)) { double tp = GetTargetPrice(o); if (tp > 0) activeTrade.CurrentTarget = tp; }
            }
            catch (Exception ex) { Print("OnAccountOrderUpdate error: " + ex.Message); }
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
            catch (Exception ex2) { Print("OnAccountExecutionUpdate error: " + ex2.Message); }
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
                                  + "_T" + dailyTradeCounter.ToString(INV);

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
            RequestScreenshot("ENTRY", ex.Time, tradeId, ex.Time, ex.Price);
        }

        private void HandleAddExecution(Execution ex, Order o, int signedQty, int positionBefore, int positionAfter)
        {
            if (activeTrade == null) return;

            double avgBefore = activeTrade.WeightedAvgEntryPrice;
            double price     = ex.Price;
            string eventType = ClassifyAddType(activeTrade.Direction, avgBefore, price);
            int addQty       = Math.Abs(signedQty);

            bool isLateInitialFill = eventType == "ADD_ON" &&
                (ex.Time - activeTrade.StartTime).TotalMilliseconds <= 500;

            if (isLateInitialFill) eventType = "ENTRY_ADD";
            else if (eventType == "SCALE_IN") activeTrade.ScaleInCount++;
            else if (eventType == "ADD_ON")   activeTrade.AddOnCount++;

            if (isLateInitialFill && activeStudy != null)
{
    activeStudy.EntryQty = activeTrade.TotalEntryQty + addQty;
    foreach (EntryStudyRow r in activeStudy.StopRows) r.EntryQty = activeStudy.EntryQty;
    WriteEntryStudy(activeStudy);
    DebugPrint("ENTRY_ADD — EntryQty updated to " + activeStudy.EntryQty.ToString(INV));
}
else if (eventType == "SCALE_IN" && activeStudy != null)
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

            if (eventType == "SCALE_IN" || eventType == "ADD_ON" || eventType == "ENTRY_ADD")
                RequestScreenshot(eventType, ex.Time, activeTrade.TradeID, activeTrade.StartTime, price);
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

            if (eventType == "SCALE_OUT" || eventType == "REVERSAL_EXIT")
                RequestScreenshot(exitLabel + "_" + activeTrade.TotalExitQty.ToString(INV),
                    ex.Time, activeTrade.TradeID, activeTrade.StartTime, fillPrice);

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

            WriteEventRows(activeTrade.EventRows, activeTrade.TradeID);
            WriteTradeSummary(summary, activeTrade.TradeID);

            DebugPrint("Trade closed: " + activeTrade.TradeID
                + " [" + summary.ExitMechanism + "/" + summary.ExitLabel + "]"
                + " PnL=" + F2(activeTrade.RealizedPnLCurrency));
            RequestScreenshot("EXIT", endTime, activeTrade.TradeID, activeTrade.StartTime, activeTrade.WeightedAvgExitPrice);

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
            RequestScreenshot(stopEvent, stopTime, activeStudy.TradeID, activeStudy.EntryTime, stopPrice);

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

        #region Trade excursions

        private void UpdateOpenTradeExcursions()
        {
            if (activeTrade == null || CurrentBar < 0) return;
            double mfe, mae;
            if (activeTrade.Direction == "LONG")
            { mfe = High[0] - activeTrade.FirstEntryPrice; mae = Low[0] - activeTrade.FirstEntryPrice; }
            else
            { mfe = activeTrade.FirstEntryPrice - Low[0]; mae = activeTrade.FirstEntryPrice - High[0]; }
            activeTrade.TradeMFEPoints = Math.Max(activeTrade.TradeMFEPoints, mfe);
            activeTrade.TradeMAEPoints = Math.Min(activeTrade.TradeMAEPoints, mae);
        }

        #endregion

        #region Screenshot

        private void RequestScreenshot(string label, DateTime time, string tradeId, DateTime tradeTime, double price = 0)
        {
            if (ChartControl == null) return;
            try
            {
                string fileName  = TradeFileStem(tradeId, tradeTime) + "_" + label + ".png";
                string tradeDir  = EnsureTradeFolder(tradeId, tradeTime);
                string masterDir = EnsureMasterScreenshotsFolder(tradeTime);
                string tradePath = Path.Combine(tradeDir,  fileName);
                string masterPath= Path.Combine(masterDir, fileName);

                ChartControl.Dispatcher.InvokeAsync(async () =>
                {
                    try
                    {
                        // Our own marker — NT8 removes an order's chart line the instant it's
                        // filled/cancelled, so a screenshot taken after that (any delay) shows
                        // no stop/target line at all. Drawing our own dot+label at the exact
                        // event price fixes this regardless of ATM/order-line timing.
                        if (price > 0)
                        {
                            string tag = "CT_" + SanitizeLabel(tradeId) + "_" + SanitizeLabel(label);
                            Draw.Dot(this, tag, false, 0, price, Brushes.Yellow);
                            Draw.Text(this, tag + "_TXT", label + " " + F2(price), 0, price, Brushes.Yellow);
                        }
                        await System.Threading.Tasks.Task.Delay(ScreenshotDelayMs);
                        NinjaTrader.Gui.Chart.Chart chartWindow =
                            System.Windows.Window.GetWindow(ChartControl) as NinjaTrader.Gui.Chart.Chart;
                        if (chartWindow == null) { Print("[ClaudeTracker] Screenshot: no chart window"); return; }

                        RenderTargetBitmap sc = chartWindow.GetScreenshot(ShareScreenshotType.Chart);
                        if (sc == null) { Print("[ClaudeTracker] Screenshot: null capture"); return; }

                        PngBitmapEncoder e1 = new PngBitmapEncoder();
                        e1.Frames.Add(BitmapFrame.Create(sc));
                        using (Stream s = File.Create(tradePath)) e1.Save(s);

                        PngBitmapEncoder e2 = new PngBitmapEncoder();
                        e2.Frames.Add(BitmapFrame.Create(sc));
                        using (Stream s = File.Create(masterPath)) e2.Save(s);

                        DebugPrint("Screenshot saved: " + fileName);
                    }
                    catch (Exception ex) { Print("[ClaudeTracker] Screenshot failed: " + ex.Message); }
                });
            }
            catch (Exception ex) { Print("[ClaudeTracker] Screenshot request failed: " + ex.Message); }
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
            catch (Exception ex) { Print("CSV ERROR (ENTRY STUDY MERGED): " + ex.Message + " — close the file and hit F5"); }
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
            catch (Exception ex) { Print("CSV ERROR (ENTRY STUDY): " + ex.Message); }
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

        private void WriteEventRows(List<TradeEventRow> rows, string tradeId)
        {
            if (rows == null || rows.Count == 0) return;
            string masterPath = Path.Combine(MastersFolder(rows[0].Time), "Events_MASTER.csv");
            string tradePath  = Path.Combine(EnsureTradeFolder(tradeId, rows[0].Time),
                TradeFileStem(tradeId, rows[0].Time) + "_Events.csv");
            WriteEventFile(masterPath, rows, true);
            WriteEventFile(tradePath,  rows, false);
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
            catch (Exception ex) { Print("CSV ERROR (EVENTS): " + ex.Message); }
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
            catch (Exception ex) { Print("CSV ERROR (TRADES): " + ex.Message); }
        }

        #endregion

        #region Helpers
		
		private int CountTodaysTrades()
{
    try
    {
        string today      = DateTime.Now.ToString("yyyy-MM", INV);
        string instrument = SanitizeFilePart(Instrument.FullName);
        string masterPath = Path.Combine(outputRoot, instrument, today, "Masters", "Events_MASTER.csv");

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

        private void GetBarInfo(DateTime time, out int sessionBar, out int sessionLastBar)
        {
            sessionBar = -1; sessionLastBar = -1;
            if (sessionIterator == null) return;
            sessionIterator.GetNextSession(time, false);
            DateTime sessionStart = sessionIterator.ActualSessionBegin;
            DateTime sessionEnd   = sessionIterator.ActualSessionEnd;
            double barMinutes     = BarsPeriod.Value;
            double minsFromStart  = (time - sessionStart).TotalMinutes;
            double sessionMins    = (sessionEnd - sessionStart).TotalMinutes;
            if (minsFromStart >= 0 && barMinutes > 0) sessionBar     = (int)(minsFromStart / barMinutes) + 1;
            if (sessionMins   >  0 && barMinutes > 0) sessionLastBar = (int)(sessionMins   / barMinutes);
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

        private void DebugPrint(string message)
        {
            if (DebugMode)
                Print("[ClaudeTracker] " + DateTime.Now.ToString("HH:mm:ss.fff", INV) + " " + message);
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
