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
    public class ClaudeTracker : Strategy
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
            public int SessionBar;
            public int SessionLastBar;
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
            public int StartSessionLastBar;
            public int EndSessionBar;
            public int EndSessionLastBar;
            public int BarsHeld;
            public double DurationMins;
            public string ExitType;
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
            public int StopSessionBar;      // -1 = blank (ENTRY row)
            public double RiskPoints;       // EntryPrice - StopPrice (LONG) or StopPrice - EntryPrice (SHORT)

            public int StopEventIndex;      // 0=ENTRY, 1=INITIAL_STOP, 2=ACTUAL_STOP_1 ...

            // ── Phase 2 — left blank by NT, calculated in Sheets ─────────
            // Sheets joins this CSV with the 1M bar export on date + session bar number.
            // All metrics are calculated from EntryTime to session end using 1M OHLC data.

            // SESSION-END EXCURSION METRICS (same value on every row for a given trade)
            // MFEPoints   = MAX of (bar High - EntryPrice) for LONG, (EntryPrice - bar Low) for SHORT
            //               across all 1M bars from EntryTime to session end
            // MAEPoints   = MIN of (bar Low - EntryPrice) for LONG, (EntryPrice - bar High) for SHORT
            //               across all 1M bars from EntryTime to session end
            //               Note: MAE will be negative for adverse moves

            // R-METRICS USING THIS ROW'S RiskPoints AS DENOMINATOR
            // MaxR        = MFEPoints / RiskPoints
            // MAEinR      = MAEPoints / RiskPoints
            // RR          = (SessionClosePrice - EntryPrice) / RiskPoints for LONG
            //               (EntryPrice - SessionClosePrice) / RiskPoints for SHORT
            //               Blank if RiskPoints = 0 (free trade / BE stop)
            // SessionClosePrice = Close of last 1M bar at or before session end time

            // TIME-TO-R METRICS (how many 1M bars / minutes from entry to first touch of each R level)
            // BarsTo1R    = first 1M bar index (from entry) where High >= EntryPrice + RiskPoints (LONG)
            //               or Low <= EntryPrice - RiskPoints (SHORT)
            // BarsTo2R    = same for 2x RiskPoints
            // BarsTo3R    = same for 3x RiskPoints
            // BarsToMaxR  = bar index where running MFE peaked
            // MinsTo1R/2R/3R/MaxR = same as above but in minutes from entry

            // CUMULATIVE AT CHECKPOINT (entry to this stop's StopTime)
            // MFEPoints_AtStop = MAX excursion from entry up to StopTime
            // MAEPoints_AtStop = MIN excursion from entry up to StopTime
            // MaxR_AtStop      = MFEPoints_AtStop / RiskPoints
            // MAEinR_AtStop    = MAEPoints_AtStop / RiskPoints

            // WINDOW METRICS (prior stop event to this stop event)
            // Window start = EntryTime for INITIAL_STOP row, prior StopTime for subsequent rows
            // Window end   = this row's StopTime
            // MFEPoints_Window = MAX excursion within this window (anchored to EntryPrice)
            // MAEPoints_Window = MIN excursion within this window (anchored to EntryPrice)
            // MaxR_Window      = MFEPoints_Window / RiskPoints
            // MAEinR_Window    = MAEPoints_Window / RiskPoints
        }

        private class ActiveTrade
        {
            public string TradeID;
            public string InstrumentName;
            public string Direction;
            public DateTime StartTime;
            public DateTime LastEventTime;
            public int StartSessionBar;
            public int StartSessionLastBar;
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
            public string LastExitType;
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

        // ─── Session study — tracks stop checkpoints only (Phase 1) ────────
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

        #endregion

        #region State

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                   = "ClaudeTracker";
                Calculate              = Calculate.OnEachTick;
                IsOverlay              = true;
                InitialStopLockSeconds = 5;
                ScreenshotDelayMs      = 100;
                DebugMode              = true;
            }
            else if (State == State.Configure)
            {
                outputRoot = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "NinjaTrader 8",
                    "ClaudeTracker");

                if (!Directory.Exists(outputRoot))
                    Directory.CreateDirectory(outputRoot);
            }
            else if (State == State.DataLoaded)
            {
                sessionIterator = new SessionIterator(Bars);

                if (Account != null)
                {
                    Account.OrderUpdate     += OnAccountOrderUpdate;
                    Account.ExecutionUpdate += OnAccountExecutionUpdate;
                }
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
            if (State != State.Realtime)
                return;

            if (CurrentBar < 1)
                return;

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
                if (o == null || o.Instrument == null || Instrument == null)
                    return;
                if (o.Instrument.FullName != Instrument.FullName)
                    return;
                if (activeTrade == null)
                    return;

                if (IsStopOrder(o))
                {
                    double stopPrice = o.StopPrice;
                    if (stopPrice > 0)
                        HandleStopUpdate(stopPrice, o);
                }
                else if (IsTargetOrder(o))
                {
                    double targetPrice = GetTargetPrice(o);
                    if (targetPrice > 0)
                        activeTrade.CurrentTarget = targetPrice;
                }
            }
            catch (Exception ex)
            {
                Print("OnAccountOrderUpdate error: " + ex.Message);
            }
        }

        private void OnAccountExecutionUpdate(object sender, ExecutionEventArgs e)
        {
            try
            {
                Execution ex = e.Execution;
                Order o = ex != null ? ex.Order : null;

                if (ex == null || o == null || o.Instrument == null || Instrument == null)
                    return;
                if (o.Instrument.FullName != Instrument.FullName)
                    return;
                if (IsDuplicateExecution(ex, o))
                    return;

                int signedQty = GetSignedQty(o.OrderAction, ex.Quantity);
                if (signedQty == 0)
                    return;

                HandleExecution(ex, o, signedQty);
            }
            catch (Exception ex2)
            {
                Print("OnAccountExecutionUpdate error: " + ex2.Message);
            }
        }

        #endregion

        #region Execution handling

        private void HandleExecution(Execution ex, Order o, int signedQty)
        {
            int positionBefore = activeTrade != null ? activeTrade.CurrentQty : 0;
            int positionAfter  = positionBefore + signedQty;

            if (positionBefore == 0)
            {
                BeginNewTrade(ex, o, signedQty);
                return;
            }

            if (Math.Sign(positionBefore) == Math.Sign(signedQty))
            {
                HandleAddExecution(ex, o, signedQty, positionBefore, positionAfter);
                return;
            }

            int closeQty     = Math.Min(Math.Abs(positionBefore), Math.Abs(signedQty));
            int remainderQty = Math.Abs(signedQty) - closeQty;

            if (closeQty > 0)
            {
                int afterExit   = positionBefore - Math.Sign(positionBefore) * closeQty;
                string exitType = remainderQty > 0
                    ? "REVERSAL_EXIT"
                    : (Math.Abs(afterExit) == 0 ? "EXIT" : "SCALE_OUT");

                HandleExitExecution(ex, o, closeQty, positionBefore, afterExit, exitType, ex.ExecutionId);
            }

            if (remainderQty > 0)
            {
                int remainderSigned = Math.Sign(signedQty) * remainderQty;
                BeginNewTrade(ex, o, remainderSigned, SafeFillId(ex.ExecutionId) + "_REVERSAL_OPEN");
            }
        }

        private void BeginNewTrade(Execution ex, Order o, int signedQty, string customFillId = null)
        {
            dailyTradeCounter++;

            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string datePart       = ex.Time.ToString("yyyyMMdd", INV);
            string timePart       = ex.Time.ToString("HHmmss", INV);
            string tradeId        = instrumentName + "_" + datePart + "_" + timePart
                                  + "_" + (signedQty > 0 ? "LONG" : "SHORT")
                                  + "_T" + dailyTradeCounter.ToString(INV);

            int sessionBar, sessionLastBar;
            GetBarInfo(ex.Time, out sessionBar, out sessionLastBar);

            activeTrade = new ActiveTrade
            {
                TradeID               = tradeId,
                InstrumentName        = Instrument.FullName,
                Direction             = signedQty > 0 ? "LONG" : "SHORT",
                StartTime             = ex.Time,
                LastEventTime         = ex.Time,
                StartSessionBar       = sessionBar,
                StartSessionLastBar   = sessionLastBar,
                LastEventSessionBar   = sessionBar,
                CurrentQty            = signedQty,
                MaxPositionQty        = Math.Abs(signedQty),
                TotalEntryQty         = Math.Abs(signedQty),
                FirstEntryPrice       = ex.Price,
                WeightedAvgEntryPrice = ex.Price,
                EntryPriceSum         = ex.Price * Math.Abs(signedQty),
                TradeFolder           = string.Empty
            };

            TradeEventRow row = new TradeEventRow
            {
                Sequence            = ++globalSequence,
                TradeID             = activeTrade.TradeID,
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
                SessionBar          = sessionBar,
                SessionLastBar      = sessionLastBar,
                BarsSinceTradeStart = 0,
                BarsSincePrevEvent  = 0,
                MinsSinceTradeStart = 0,
                MinsSincePrevEvent  = 0
            };
            activeTrade.EventRows.Add(row);

            activeStudy = new SessionStudy
            {
                TradeID         = tradeId,
                Direction       = activeTrade.Direction,
                EntryPrice      = ex.Price,
                EntryQty        = Math.Abs(signedQty),
                EntryTime       = ex.Time,
                EntrySessionBar = sessionBar
            };

            EntryStudyRow entryRow = new EntryStudyRow
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
            };
            activeStudy.StopRows.Add(entryRow);

            WriteEntryStudy(activeStudy);

            DebugPrint("ENTRY written for " + tradeId + " at " + F2(ex.Price));
            RequestScreenshot("ENTRY", ex.Time);
        }

        private void HandleAddExecution(Execution ex, Order o, int signedQty, int positionBefore, int positionAfter)
        {
            if (activeTrade == null)
                return;

            double avgBefore = activeTrade.WeightedAvgEntryPrice;
            double price     = ex.Price;
            string eventType = ClassifyAddType(activeTrade.Direction, avgBefore, price);
            int addQty       = Math.Abs(signedQty);

            // If ADD_ON within 500ms of trade open — treat as late initial fill
            bool isLateInitialFill = eventType == "ADD_ON" &&
                (ex.Time - activeTrade.StartTime).TotalMilliseconds <= 500;

            if (isLateInitialFill)
                eventType = "ENTRY_ADD";
            else if (eventType == "SCALE_IN") activeTrade.ScaleInCount++;
            else if (eventType == "ADD_ON")   activeTrade.AddOnCount++;

            if (isLateInitialFill && activeStudy != null)
            {
                activeStudy.EntryQty = activeTrade.TotalEntryQty + addQty;
                foreach (EntryStudyRow r in activeStudy.StopRows)
                    r.EntryQty = activeStudy.EntryQty;
                WriteEntryStudy(activeStudy);
                DebugPrint("ENTRY_ADD detected — EntryQty updated to " + activeStudy.EntryQty.ToString(INV));
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

            TradeEventRow row = new TradeEventRow
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
                SessionBar             = sessionBar,
                SessionLastBar         = sessionLastBar,
                BarsSinceTradeStart    = sessionBar >= 0 && activeTrade.StartSessionBar >= 0 ? sessionBar - activeTrade.StartSessionBar : -1,
                BarsSincePrevEvent     = sessionBar >= 0 && prevSessionBar >= 0 ? sessionBar - prevSessionBar : -1,
                MinsSinceTradeStart    = (ex.Time - activeTrade.StartTime).TotalMinutes,
                MinsSincePrevEvent     = (ex.Time - prevTime).TotalMinutes
            };

            activeTrade.EventRows.Add(row);
            activeTrade.LastEventSessionBar = sessionBar;
            activeTrade.LastEventTime       = ex.Time;

            if (eventType == "SCALE_IN" || eventType == "ADD_ON" || eventType == "ENTRY_ADD")
                RequestScreenshot(eventType, ex.Time);
        }

        private void HandleExitExecution(Execution ex, Order o, int closeQty, int positionBefore, int positionAfter, string exitType, string customFillId = null)
        {
            if (activeTrade == null || closeQty <= 0)
                return;

            double fillPrice = ex.Price;
            double avgEntry  = activeTrade.WeightedAvgEntryPrice;
            double legPoints = activeTrade.Direction == "LONG"
                ? fillPrice - avgEntry
                : avgEntry - fillPrice;

            double legPnLCurrency = legPoints * closeQty * Instrument.MasterInstrument.PointValue;

            activeTrade.RealizedPnLCurrency += legPnLCurrency;
            activeTrade.TotalExitQty        += closeQty;
            activeTrade.ExitPriceSum        += fillPrice * closeQty;
            activeTrade.WeightedAvgExitPrice = activeTrade.TotalExitQty > 0
                ? activeTrade.ExitPriceSum / activeTrade.TotalExitQty : 0;

            if (exitType == "SCALE_OUT") activeTrade.ScaleOutCount++;

            activeTrade.CurrentQty   = positionAfter;
            activeTrade.LastExitType = exitType;

            int sessionBar, sessionLastBar;
            GetBarInfo(ex.Time, out sessionBar, out sessionLastBar);

            int prevSessionBar = activeTrade.LastEventSessionBar;
            DateTime prevTime  = activeTrade.LastEventTime;

            TradeEventRow row = new TradeEventRow
            {
                Sequence               = ++globalSequence,
                TradeID                = activeTrade.TradeID,
                EventID                = NextEventID(activeTrade),
                FillID                 = !string.IsNullOrEmpty(customFillId) ? customFillId : SafeFillId(ex.ExecutionId),
                Time                   = ex.Time,
                EventType              = exitType,
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
                SessionBar             = sessionBar,
                SessionLastBar         = sessionLastBar,
                BarsSinceTradeStart    = sessionBar >= 0 && activeTrade.StartSessionBar >= 0 ? sessionBar - activeTrade.StartSessionBar : -1,
                BarsSincePrevEvent     = sessionBar >= 0 && prevSessionBar >= 0 ? sessionBar - prevSessionBar : -1,
                MinsSinceTradeStart    = (ex.Time - activeTrade.StartTime).TotalMinutes,
                MinsSincePrevEvent     = (ex.Time - prevTime).TotalMinutes
            };

            activeTrade.EventRows.Add(row);
            activeTrade.LastEventSessionBar = sessionBar;
            activeTrade.LastEventTime       = ex.Time;

            if (exitType == "SCALE_OUT" || exitType == "REVERSAL_EXIT")
                RequestScreenshot(exitType + "_" + activeTrade.TotalExitQty.ToString(INV), ex.Time);

            if (positionAfter == 0)
                CloseTrade(ex.Time, sessionBar, sessionLastBar);
        }

        private void CloseTrade(DateTime endTime, int endSessionBar, int endSessionLastBar)
        {
            if (activeTrade == null)
                return;

            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string dateFolder     = Path.Combine(outputRoot, instrumentName,
                activeTrade.StartTime.ToString("yyyy-MM-dd", INV));

            TradeSummaryRow summary = new TradeSummaryRow
            {
                TradeID               = activeTrade.TradeID,
                InstrumentName        = activeTrade.InstrumentName,
                StartTime             = activeTrade.StartTime,
                EndTime               = endTime,
                Direction             = activeTrade.Direction,
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
                StartSessionLastBar   = activeTrade.StartSessionLastBar,
                EndSessionBar         = endSessionBar,
                EndSessionLastBar     = endSessionLastBar,
                BarsHeld              = endSessionBar >= 0 && activeTrade.StartSessionBar >= 0
                                        ? endSessionBar - activeTrade.StartSessionBar : -1,
                DurationMins          = (endTime - activeTrade.StartTime).TotalMinutes,
                ExitType              = activeTrade.LastExitType ?? string.Empty,
                TradeFolder           = dateFolder
            };

            WriteEventRows(activeTrade.EventRows, true, activeTrade.TradeID);
            WriteTradeSummary(summary, true, activeTrade.TradeID);

            DebugPrint("Trade closed: " + activeTrade.TradeID + " PnL=" + F2(activeTrade.RealizedPnLCurrency));
            RequestScreenshot("EXIT", endTime);

            activeTrade = null;
            activeStudy = null;
        }

        #endregion

        #region Stop handling

        private void HandleStopUpdate(double stopPrice, Order o)
        {
            if (activeTrade == null)
                return;

            DateTime now = Core.Globals.Now;

            if (activeTrade.FirstProtectiveStop <= 0)
            {
                activeTrade.FirstProtectiveStop          = stopPrice;
                activeTrade.FirstProtectiveStopLocalTime = now;
                activeTrade.CurrentStop                  = stopPrice;
                if (activeTrade.ATMStop <= 0)
                    activeTrade.ATMStop = stopPrice;
                return;
            }

            if (activeTrade.CurrentStop.ApproxCompare(stopPrice) == 0 && !activeTrade.InitialStopLocked)
                return;

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
                    int actualStopCount = activeStudy != null
                        ? activeStudy.StopRows.Count(r => r.StopEvent.StartsWith("ACTUAL_STOP"))
                        : 1;
                    AppendStopRowToStudy("ACTUAL_STOP_" + (actualStopCount + 1).ToString(INV), stopPrice, now);
                }
            }
        }

        private void AppendStopRowToStudy(string stopEvent, double stopPrice, DateTime stopTime)
        {
            if (activeStudy == null)
                return;

            // Hard 200ms gate — prevents ATM flicker regardless of price
            if (activeStudy.LastStopWrittenTime != default(DateTime) &&
                (stopTime - activeStudy.LastStopWrittenTime).TotalMilliseconds < 200)
            {
                DebugPrint("DEBOUNCE: Stop " + F2(stopPrice) + " within 200ms of last write — skipped");
                return;
            }

            int sessionBar, sessionLastBar;
            GetBarInfo(stopTime, out sessionBar, out sessionLastBar);

            double riskPoints = GetRiskPoints(activeStudy.Direction, activeStudy.EntryPrice, stopPrice);

            EntryStudyRow row = new EntryStudyRow
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
            };

            activeStudy.StopRows.Add(row);
            activeStudy.LastStopWrittenTime = stopTime;

            WriteEntryStudy(activeStudy);
            RequestScreenshot(stopEvent, stopTime);

            DebugPrint(stopEvent + " appended: stop=" + F2(stopPrice) + " risk=" + F2(riskPoints) + " pts");
        }

        private void TryLockInitialStop()
        {
            if (activeTrade == null)
                return;
            if (!activeTrade.InitialStopStarted || activeTrade.InitialStopLocked)
                return;
            if ((Core.Globals.Now - activeTrade.InitialStopWindowStartTime).TotalSeconds < InitialStopLockSeconds)
                return;

            activeTrade.InitialStop       = activeTrade.PendingInitialStopCandidate;
            activeTrade.InitialStopLocked = true;

            AppendStopRowToStudy("INITIAL_STOP", activeTrade.InitialStop, activeTrade.InitialStopTime);

            DebugPrint("InitialStop locked at " + F2(activeTrade.InitialStop));
        }

        #endregion

        #region Trade excursions

        private void UpdateOpenTradeExcursions()
        {
            if (activeTrade == null || CurrentBar < 0)
                return;

            double mfe, mae;
            if (activeTrade.Direction == "LONG")
            {
                mfe = High[0] - activeTrade.FirstEntryPrice;
                mae = Low[0]  - activeTrade.FirstEntryPrice;
            }
            else
            {
                mfe = activeTrade.FirstEntryPrice - Low[0];
                mae = activeTrade.FirstEntryPrice - High[0];
            }

            activeTrade.TradeMFEPoints = Math.Max(activeTrade.TradeMFEPoints, mfe);
            activeTrade.TradeMAEPoints = Math.Min(activeTrade.TradeMAEPoints, mae);
        }

        #endregion

        #region Screenshot

        private void RequestScreenshot(string label, DateTime time)
        {
            if (ChartControl == null)
                return;

            try
            {
                string instrumentName = SanitizeFilePart(Instrument.FullName);
                string dateFolder     = Path.Combine(outputRoot, instrumentName,
                    time.ToString("yyyy-MM-dd", INV));
                if (!Directory.Exists(dateFolder))
                    Directory.CreateDirectory(dateFolder);

                string stem     = activeStudy != null
                    ? TradeFileStem(activeStudy.TradeID, activeStudy.EntryTime)
                    : (activeTrade != null
                        ? TradeFileStem(activeTrade.TradeID, activeTrade.StartTime)
                        : ShortDayDate(time));
                string filePath = Path.Combine(dateFolder, stem + "_" + label + ".png");

                ChartControl.Dispatcher.InvokeAsync(async () =>
                {
                    try
                    {
                        await System.Threading.Tasks.Task.Delay(ScreenshotDelayMs);

                        NinjaTrader.Gui.Chart.Chart chartWindow =
                            System.Windows.Window.GetWindow(ChartControl)
                            as NinjaTrader.Gui.Chart.Chart;

                        if (chartWindow == null)
                        {
                            Print("[ClaudeTracker] Screenshot: could not get chart window");
                            return;
                        }

                        RenderTargetBitmap screenCapture =
                            chartWindow.GetScreenshot(ShareScreenshotType.Chart);

                        if (screenCapture == null)
                        {
                            Print("[ClaudeTracker] Screenshot: GetScreenshot returned null");
                            return;
                        }

                        PngBitmapEncoder png = new PngBitmapEncoder();
                        png.Frames.Add(BitmapFrame.Create(screenCapture));

                        using (Stream stream = File.Create(filePath))
                            png.Save(stream);

                        DebugPrint("Screenshot saved: " + filePath);
                    }
                    catch (Exception ex)
                    {
                        Print("[ClaudeTracker] Screenshot failed: " + ex.Message);
                    }
                });
            }
            catch (Exception ex)
            {
                Print("[ClaudeTracker] Screenshot request failed: " + ex.Message);
            }
        }

        #endregion

        #region CSV writers — EntryStudy

        private string EntryStudyMasterPath(DateTime date)
        {
            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string dateFolder     = Path.Combine(outputRoot, instrumentName, date.ToString("yyyy-MM-dd", INV));
            if (!Directory.Exists(dateFolder))
                Directory.CreateDirectory(dateFolder);
            return Path.Combine(dateFolder,
                string.Format(INV, "{0}_EntryStudy_MASTER.csv", ShortDate(date)));
        }

        private void WriteEntryStudy(SessionStudy study)
        {
            // Master file — preserves rows from other trades
            string masterPath = EntryStudyMasterPath(study.EntryTime);
            WriteEntryStudyMerged(masterPath, study);

            // Per-trade file
            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string dateFolder     = Path.Combine(outputRoot, instrumentName,
                study.EntryTime.ToString("yyyy-MM-dd", INV));
            string tradePath      = Path.Combine(dateFolder,
                string.Format(INV, "{0}_EntryStudy.csv", TradeFileStem(study.TradeID, study.EntryTime)));
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
                        {
                            if (!allLines[i].Contains("\"" + study.TradeID + "\""))
                                existingLines.Add(allLines[i]);
                        }
                    }
                }

                using (StreamWriter sw = new StreamWriter(path, false))
                {
                    sw.WriteLine(string.IsNullOrEmpty(header) ? EntryStudyHeader() : header);

                    foreach (string line in existingLines)
                        sw.WriteLine(line);

                    foreach (EntryStudyRow r in study.StopRows)
                        sw.WriteLine(EntryStudyRowCsv(r));
                }

                DebugPrint("EntryStudy merged: " + study.StopRows.Count + " rows for " + study.TradeID);
            }
            catch (Exception ex)
            {
                Print("CSV ERROR (ENTRY STUDY MERGED): " + ex.Message + " — close the file and hit F5");
            }
        }

        private void WriteEntryStudyFile(string path, SessionStudy study)
        {
            try
            {
                using (StreamWriter sw = new StreamWriter(path, false))
                {
                    sw.WriteLine(EntryStudyHeader());
                    foreach (EntryStudyRow r in study.StopRows)
                        sw.WriteLine(EntryStudyRowCsv(r));
                }
            }
            catch (Exception ex)
            {
                Print("CSV ERROR (ENTRY STUDY): " + ex.Message);
            }
        }

        private string EntryStudyHeader()
        {
            // Phase 1 columns written by NT
            // Phase 2 columns left blank — calculated in Sheets using 1M bar export
            return "TradeID,Instrument,Direction,EntryPrice,EntryQty,EntryTime,EntrySessionBar," +
                   "StopEvent,StopPrice,StopTime,StopSessionBar,RiskPoints," +
                   // Phase 2 — session-end excursion (same value all rows per trade)
                   "MFEPoints,MAEPoints," +
                   // Phase 2 — R-metrics using this row's RiskPoints
                   "MaxR,MAEinR,RR,SessionClosePrice," +
                   // Phase 2 — time to R levels (in 1M bars and minutes from entry)
                   "BarsTo1R,MinsTo1R,BarsTo2R,MinsTo2R,BarsTo3R,MinsTo3R,BarsToMaxR,MinsToMaxR," +
                   // Phase 2 — cumulative excursion from entry to this stop's timestamp
                   "MFEPoints_AtStop,MAEPoints_AtStop,MaxR_AtStop,MAEinR_AtStop," +
                   // Phase 2 — excursion within window between consecutive stop events
                   "MFEPoints_Window,MAEPoints_Window,MaxR_Window,MAEinR_Window";
        }

        private string EntryStudyRowCsv(EntryStudyRow r)
        {
            bool isEntry = r.StopEvent == "ENTRY";

            return string.Join(",",
                // Phase 1 — written by NT
                Csv(r.TradeID),
                Csv(r.InstrumentName),
                Csv(r.Direction),
                Csv(F2(r.EntryPrice)),
                Csv(r.EntryQty.ToString(INV)),
                Csv(r.EntryTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                Csv(r.EntrySessionBar.ToString(INV)),
                Csv(r.StopEvent),
                isEntry ? Csv("") : Csv(F2(r.StopPrice)),
                isEntry || r.StopTime == default(DateTime) ? Csv("") : Csv(r.StopTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                isEntry || r.StopSessionBar < 0 ? Csv("") : Csv(r.StopSessionBar.ToString(INV)),
                isEntry ? Csv("") : Csv(F2(r.RiskPoints)),
                // Phase 2 — all blank, calculated in Sheets
                // MFEPoints, MAEPoints
                Csv(""), Csv(""),
                // MaxR, MAEinR, RR, SessionClosePrice
                Csv(""), Csv(""), Csv(""), Csv(""),
                // BarsTo1R, MinsTo1R, BarsTo2R, MinsTo2R, BarsTo3R, MinsTo3R, BarsToMaxR, MinsToMaxR
                Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""), Csv(""),
                // MFEPoints_AtStop, MAEPoints_AtStop, MaxR_AtStop, MAEinR_AtStop
                Csv(""), Csv(""), Csv(""), Csv(""),
                // MFEPoints_Window, MAEPoints_Window, MaxR_Window, MAEinR_Window
                Csv(""), Csv(""), Csv(""), Csv("")
            );
        }

        #endregion

        #region CSV writers — Events and Trades

        private void WriteEventRows(List<TradeEventRow> rows, bool appendToMaster, string tradeId)
        {
            if (rows == null || rows.Count == 0)
                return;

            string date           = rows[0].Time.ToString("yyyy-MM-dd", INV);
            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string dateFolder     = Path.Combine(outputRoot, instrumentName, date);

            if (!Directory.Exists(dateFolder))
                Directory.CreateDirectory(dateFolder);

            string masterPath = Path.Combine(dateFolder,
                string.Format(INV, "{0}_Events_MASTER.csv", ShortDate(rows[0].Time)));
            string tradePath  = Path.Combine(dateFolder,
                string.Format(INV, "{0}_Events.csv", TradeFileStem(tradeId, rows[0].Time)));

            WriteEventFile(masterPath, rows, appendToMaster);
            WriteEventFile(tradePath,  rows, false);
        }

        private void WriteTradeSummary(TradeSummaryRow row, bool appendToMaster, string tradeId)
        {
            string date           = row.StartTime.ToString("yyyy-MM-dd", INV);
            string instrumentName = SanitizeFilePart(Instrument.FullName);
            string dateFolder     = Path.Combine(outputRoot, instrumentName, date);

            if (!Directory.Exists(dateFolder))
                Directory.CreateDirectory(dateFolder);

            string masterPath = Path.Combine(dateFolder,
                string.Format(INV, "{0}_Trades_MASTER.csv", ShortDate(row.StartTime)));
            string tradePath  = Path.Combine(dateFolder,
                string.Format(INV, "{0}_TradeSummary.csv", TradeFileStem(tradeId, row.StartTime)));

            WriteTradeFile(masterPath, row, appendToMaster);
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
                            "FirstActualStop,CurrentStop,ActualStop,TargetAtEvent,SessionBar,SessionLastBar," +
                            "BarsSinceTradeStart,BarsSincePrevEvent,MinsSinceTradeStart,MinsSincePrevEvent");

                    foreach (TradeEventRow r in rows.OrderBy(x => x.Sequence))
                    {
                        sw.WriteLine(string.Join(",",
                            Csv(r.TradeID),
                            Csv(r.EventID),
                            Csv(r.FillID),
                            Csv(r.Time.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                            Csv(r.EventType),
                            Csv(r.Direction),
                            Csv(r.OrderName),
                            Csv(r.Oco),
                            Csv(r.OrderId.ToString(INV)),
                            Csv(r.ExecQty.ToString(INV)),
                            Csv(r.PositionBefore.ToString(INV)),
                            Csv(r.PositionAfter.ToString(INV)),
                            Csv(F2(r.FillPrice)),
                            Csv(F2(r.AvgEntryBefore)),
                            Csv(F2(r.AvgEntryAfter)),
                            Csv(F2(r.LegPnLCurrency)),
                            Csv(F2(r.CumRealizedPnLCurrency)),
                            Csv(F2(r.ATMStop)),
                            Csv(F2(r.FirstProtectiveStop)),
                            Csv(F2(r.InitialStop)),
                            Csv(F2(r.FirstActualStop)),
                            Csv(F2(r.CurrentStop)),
                            Csv(F2(r.ActualStop)),
                            Csv(F2(r.TargetAtEvent)),
                            Csv(r.SessionBar.ToString(INV)),
                            Csv(r.SessionLastBar.ToString(INV)),
                            Csv(r.BarsSinceTradeStart.ToString(INV)),
                            Csv(r.BarsSincePrevEvent.ToString(INV)),
                            Csv(F2(r.MinsSinceTradeStart)),
                            Csv(F2(r.MinsSincePrevEvent))
                        ));
                    }
                }
            }
            catch (Exception ex)
            {
                Print("CSV ERROR (EVENTS): " + ex.Message);
            }
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
                            "TotalEntryQty,TotalExitQty,MaxPositionQty,FirstEntryPrice," +
                            "WeightedAvgEntryPrice,WeightedAvgExitPrice,ATMStop,FirstProtectiveStop," +
                            "InitialStop,FirstActualStop,CurrentStopAtExit,InitialRiskPoints," +
                            "FirstActualRiskPoints,GrossPnLCurrency,TradeMAEPoints,TradeMFEPoints," +
                            "ScaleInCount,AddOnCount,ScaleOutCount," +
                            "StartSessionBar,StartSessionLastBar,EndSessionBar,EndSessionLastBar," +
                            "BarsHeld,DurationMins,ExitType,TradeFolder");

                    sw.WriteLine(string.Join(",",
                        Csv(r.TradeID),
                        Csv(r.InstrumentName),
                        Csv(r.StartTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                        Csv(r.EndTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
                        Csv(r.Direction),
                        Csv(r.TotalEntryQty.ToString(INV)),
                        Csv(r.TotalExitQty.ToString(INV)),
                        Csv(r.MaxPositionQty.ToString(INV)),
                        Csv(F2(r.FirstEntryPrice)),
                        Csv(F2(r.WeightedAvgEntryPrice)),
                        Csv(F2(r.WeightedAvgExitPrice)),
                        Csv(F2(r.ATMStop)),
                        Csv(F2(r.FirstProtectiveStop)),
                        Csv(F2(r.InitialStop)),
                        Csv(F2(r.FirstActualStop)),
                        Csv(F2(r.CurrentStopAtExit)),
                        Csv(F2(r.InitialRiskPoints)),
                        Csv(F2(r.FirstActualRiskPoints)),
                        Csv(F2(r.GrossPnLCurrency)),
                        Csv(F2(r.TradeMAEPoints)),
                        Csv(F2(r.TradeMFEPoints)),
                        Csv(r.ScaleInCount.ToString(INV)),
                        Csv(r.AddOnCount.ToString(INV)),
                        Csv(r.ScaleOutCount.ToString(INV)),
                        Csv(r.StartSessionBar.ToString(INV)),
                        Csv(r.StartSessionLastBar.ToString(INV)),
                        Csv(r.EndSessionBar.ToString(INV)),
                        Csv(r.EndSessionLastBar.ToString(INV)),
                        Csv(r.BarsHeld.ToString(INV)),
                        Csv(F2(r.DurationMins)),
                        Csv(r.ExitType),
                        Csv(r.TradeFolder)
                    ));
                }
            }
            catch (Exception ex)
            {
                Print("CSV ERROR (TRADES): " + ex.Message);
            }
        }

        #endregion

        #region Helpers

        private void GetBarInfo(DateTime time, out int sessionBar, out int sessionLastBar)
        {
            sessionBar     = -1;
            sessionLastBar = -1;

            if (sessionIterator == null)
                return;

            sessionIterator.GetNextSession(time, false);
            DateTime sessionStart = sessionIterator.ActualSessionBegin;
            DateTime sessionEnd   = sessionIterator.ActualSessionEnd;

            double barMinutes    = BarsPeriod.Value;
            double minsFromStart = (time - sessionStart).TotalMinutes;
            double sessionMins   = (sessionEnd - sessionStart).TotalMinutes;

            if (minsFromStart >= 0 && barMinutes > 0)
                sessionBar = (int)(minsFromStart / barMinutes) + 1;

            if (sessionMins > 0 && barMinutes > 0)
                sessionLastBar = (int)(sessionMins / barMinutes);
        }

        private bool IsDuplicateExecution(Execution ex, Order o)
        {
            string key = string.Join("|",
                ex.ExecutionId ?? string.Empty,
                o.Id.ToString(INV),
                ex.Time.ToString("O", INV),
                ex.Quantity.ToString(INV),
                ex.Price.ToString("F8", INV));

            if (processedExecutions.Contains(key)) return true;
            processedExecutions.Add(key);
            return false;
        }

        private int GetSignedQty(OrderAction action, int qty)
        {
            switch (action)
            {
                case OrderAction.Buy:
                case OrderAction.BuyToCover:  return qty;
                case OrderAction.Sell:
                case OrderAction.SellShort:   return -qty;
                default:                      return 0;
            }
        }

        private bool IsStopOrder(Order o)
        {
            return o.OrderType == OrderType.StopMarket || o.OrderType == OrderType.StopLimit;
        }

        private bool IsTargetOrder(Order o)
        {
            return o.OrderType == OrderType.Limit || o.OrderType == OrderType.MIT;
        }

        private double GetTargetPrice(Order o)
        {
            return o != null && o.LimitPrice > 0 ? o.LimitPrice : 0;
        }

        private string ClassifyAddType(string direction, double avgBefore, double price)
        {
            if (direction == "LONG") return price < avgBefore ? "SCALE_IN" : "ADD_ON";
            return price > avgBefore ? "SCALE_IN" : "ADD_ON";
        }

        private string NextEventID(ActiveTrade trade)
        {
            trade.EventCounter++;
            return trade.TradeID + "_E" + trade.EventCounter.ToString(INV);
        }

        private double GetRiskPoints(string direction, double entryPrice, double stopPrice)
        {
            if (stopPrice <= 0) return 0;
            if (direction == "LONG") return Math.Max(0, entryPrice - stopPrice);
            return Math.Max(0, stopPrice - entryPrice);
        }

        private string SafeFillId(string executionId)
        {
            return string.IsNullOrEmpty(executionId) ? string.Empty : executionId;
        }

        private string ShortDate(DateTime time)
        {
            return time.Day.ToString(INV) + time.ToString("MMM", CultureInfo.InvariantCulture);
        }

        private string ShortDayDate(DateTime time)
        {
            return time.ToString("ddd", CultureInfo.InvariantCulture) + "_" + ShortDate(time);
        }

        private string TradeFileStem(string tradeId, DateTime time)
        {
            string direction = tradeId.Contains("_LONG_") ? "LONG" : "SHORT";
            string tNum      = string.Empty;
            int tIdx         = tradeId.LastIndexOf("_T", StringComparison.Ordinal);
            if (tIdx >= 0) tNum = tradeId.Substring(tIdx + 1);
            return ShortDayDate(time) + "_" + direction + "_" + tNum;
        }

        private string SanitizeFilePart(string value)
        {
            if (string.IsNullOrEmpty(value)) return "NA";
            foreach (char c in Path.GetInvalidFileNameChars())
                value = value.Replace(c, '_');
            return value.Replace(" ", "_");
        }

        private string F2(double value)
        {
            return value.ToString("F2", INV);
        }

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
