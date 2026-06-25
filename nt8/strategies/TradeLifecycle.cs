#region Using declarations
using System;
using Microsoft.CSharp;
using System.IO;
using System.Collections.Generic;
using System.Collections;
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
using System.Globalization;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using System.Windows;
using System.Windows.Media.Imaging;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
	public class TradeLifecycle : Strategy
	{
		#region Nested classes

		private class TradeEventRow
		{
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

			public int AbsBar;
			public int SessionBar;
			public int SessionLastBar;

			public int BarsSinceTradeStart;
			public int BarsSincePrevEvent;
			public double SecondsSinceTradeStart;
			public double SecondsSincePrevEvent;

			public string ScreenshotFile;
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
			public double MAEPoints;
			public double MFEPoints;

			public int ScaleInCount;
			public int AddOnCount;
			public int ScaleOutCount;

			public int StartAbsBar;
			public int StartSessionBar;
			public int StartSessionLastBar;
			public int EndAbsBar;
			public int EndSessionBar;
			public int EndSessionLastBar;

			public int BarsHeld;
			public double DurationSec;

			public string ExitType;
			public string TradeFolder;
		}

		private class EntryStudyRow
		{
			public string TradeID;
			public string InstrumentName;
			public DateTime EntryTime;
			public double EntryPrice;
			public int EntryQty;
			public string Direction;

			public DateTime SessionEndTime;
			public bool Written;

			public int EntryAbsBar;
			public int EntrySessionBar;
			public int EntrySessionLastBar;

			public double FirstProtectiveStop;
			public DateTime FirstProtectiveStopTime;

			public double InitialStop;
			public DateTime InitialStopTime;
			public bool InitialStopLocked;

			public double FirstActualStop;
			public DateTime FirstActualStopTime;
			public bool FirstActualCaptured;

			public double MFEPoints;
			public double MAEPoints;

			public double MaxRInitial;
			public int BarsToMaxRInitial = -1;
			public double DurationToMaxRInitialSec = -1;

			public double MaxRActual;
			public int BarsToMaxRActual = -1;
			public double DurationToMaxRActualSec = -1;

			public int BarsTo1RInitial = -1;
			public int BarsTo2RInitial = -1;
			public int BarsTo3RInitial = -1;

			public double DurationTo1RInitialSec = -1;
			public double DurationTo2RInitialSec = -1;
			public double DurationTo3RInitialSec = -1;

			public int BarsTo1RActual = -1;
			public int BarsTo2RActual = -1;
			public int BarsTo3RActual = -1;

			public double DurationTo1RActualSec = -1;
			public double DurationTo2RActualSec = -1;
			public double DurationTo3RActualSec = -1;

			public double MFEBeforeFirstActualPoints;
			public double MaxRBeforeFirstActualInitial;
			public int BarsToMaxRBeforeFirstActual = -1;
			public double DurationToMaxRBeforeFirstActualSec = -1;

			public double SessionClosePrice;
			public int ExitAbsBar;
			public int ExitSessionBar;
			public int ExitSessionLastBar;
			public int BarsFromEntryToSessionClose;
			public double DurationToSessionCloseSec;
		}

		private class ActiveTrade
		{
			public string TradeID;
			public string InstrumentName;
			public string Direction;

			public DateTime StartTime;
			public DateTime LastEventTime;

			public int StartAbsBar;
			public int StartSessionBar;
			public int StartSessionLastBar;
			public int StartBarIndex;
			public int LastEventBarIndex;

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
			public double MAEPoints;
			public double MFEPoints;

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
			public double FirstActualStop;
			public DateTime FirstActualStopTime;
			public bool FirstActualCaptured;
			public double CurrentStop;
			public double CurrentTarget;

			public int EventCounter;
			public List<TradeEventRow> EventRows = new List<TradeEventRow>();
			public string TradeFolder;
		}

		#endregion

		#region Fields
// ===== DEBUG HELPER =====
private void DebugPrint(string msg)
{
	try
	{
		Print("[TradeLifecycle] " + msg);
	}
	catch {}
}
		private static readonly CultureInfo INV = CultureInfo.InvariantCulture;

		private SessionIterator sessionIterator;
		private ActiveTrade activeTrade;
		private EntryStudyRow activeEntryStudy;

		private string outputRoot;
		private int dailyTradeCounter = 0;

		private string lastProcessedExecutionKey = string.Empty;
		private bool sessionEndScreenshotTakenForCurrentSession = false;

		#endregion

		#region User parameters

		[NinjaScriptProperty]
		[Display(Name = "Initial Stop Lock Seconds", Order = 1, GroupName = "Parameters")]
		public int InitialStopLockSeconds { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Enable Screenshots", Order = 2, GroupName = "Parameters")]
		public bool EnableScreenshots { get; set; }

		#endregion

		#region State

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "TradeLifecycle";
				Calculate = Calculate.OnEachTick;
				IsOverlay = true;

				InitialStopLockSeconds = 5;
				EnableScreenshots = true;
			}
			else if (State == State.Configure)
			{
				outputRoot = Path.Combine(
					Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
					"NinjaTrader 8",
					"TradeLifecycle");

				if (!Directory.Exists(outputRoot))
					Directory.CreateDirectory(outputRoot);
			}
			else if (State == State.DataLoaded)
			{
				sessionIterator = new SessionIterator(Bars);

				if (Account != null)
				{
					Account.OrderUpdate += OnAccountOrderUpdate;
					Account.ExecutionUpdate += OnAccountExecutionUpdate;
				}
			}
			else if (State == State.Terminated)
			{
				if (Account != null)
				{
					Account.OrderUpdate -= OnAccountOrderUpdate;
					Account.ExecutionUpdate -= OnAccountExecutionUpdate;
				}
			}
		}

		#endregion

		#region Core bar loop

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 1 || State != State.Realtime)
				return;

			UpdateOpenTradeExcursions();
			UpdateEntryStudyExcursions();
			TryLockInitialStop();
			CheckSessionBoundaryForStudyAndScreenshot();
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

				if (!IsStopOrder(o))
					return;

				double stopPrice = o.StopPrice;
				if (stopPrice <= 0)
					return;

				HandleStopUpdate(stopPrice, o);
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

				string executionKey = (ex.ExecutionId ?? string.Empty) + "|" + o.Id + "|" + ex.Time.ToString("O") + "|" + ex.Quantity;
				if (executionKey == lastProcessedExecutionKey)
					return;

				lastProcessedExecutionKey = executionKey;

				int signedQty = GetSignedQty(o.OrderAction, ex.Quantity);
				if (signedQty == 0)
					return;

				DebugPrint("EXECUTION: " + o.OrderAction + " " + ex.Quantity + " @ " + ex.Price);
HandleExecution(ex, o, signedQty);
			}
			catch (Exception ex)
			{
				Print("OnAccountExecutionUpdate error: " + ex.Message);
			}
		}

		#endregion

		#region Execution handling

		private void HandleExecution(Execution ex, Order o, int signedQty)
		{
			int positionBefore = activeTrade != null ? activeTrade.CurrentQty : 0;
			int positionAfter = positionBefore + signedQty;

			// New trade from flat
			if (positionBefore == 0)
			{
				BeginNewTrade(ex, o, signedQty);
				return;
			}

			// Same direction add
			if (Math.Sign(positionBefore) == Math.Sign(signedQty))
			{
				HandleAddExecution(ex, o, signedQty, positionBefore, positionAfter);
				return;
			}

			// Opposite direction: reduce, exit, or reverse
			int closeQty = Math.Min(Math.Abs(positionBefore), Math.Abs(signedQty));
			int remainderQty = Math.Abs(signedQty) - closeQty;

			if (closeQty > 0)
			{
				HandleExitExecution(ex, o, closeQty, positionBefore, positionBefore - Math.Sign(positionBefore) * closeQty, remainderQty > 0 ? "REVERSAL_EXIT" : (Math.Abs(positionAfter) == 0 ? "EXIT" : "SCALE_OUT"), ex.ExecutionId);
			}

			if (remainderQty > 0)
			{
				int remainderSigned = Math.Sign(signedQty) * remainderQty;
				BeginNewTrade(ex, o, remainderSigned, ex.ExecutionId + "_OPEN");
			}
		}

		private void BeginNewTrade(Execution ex, Order o, int signedQty, string customFillId = null)
		{
			dailyTradeCounter++;

			string tradeDate = ex.Time.ToString("yyyy-MM-dd");
			string instrumentName = SanitizeFilePart(Instrument.FullName);
			string tradeId = instrumentName + "_" + tradeDate + "_T" + dailyTradeCounter.ToString(INV);

			int absBar, sessionBar, sessionLastBar;
			GetBarInfo(ex.Time, out absBar, out sessionBar, out sessionLastBar);

			activeTrade = new ActiveTrade
			{
				TradeID = tradeId,
				InstrumentName = Instrument.FullName,
				Direction = signedQty > 0 ? "LONG" : "SHORT",
				StartTime = ex.Time,
				LastEventTime = ex.Time,
				StartAbsBar = absBar,
				StartSessionBar = sessionBar,
				StartSessionLastBar = sessionLastBar,
				StartBarIndex = absBar,
				LastEventBarIndex = absBar,
				CurrentQty = signedQty,
				MaxPositionQty = Math.Abs(signedQty),
				TotalEntryQty = Math.Abs(signedQty),
				FirstEntryPrice = ex.Price,
				WeightedAvgEntryPrice = ex.Price,
				EntryPriceSum = ex.Price * Math.Abs(signedQty),
				MAEPoints = 0,
				MFEPoints = 0,
				TradeFolder = EnsureTradeFolder(tradeId, ex.Time)
			};

			string eventId = NextEventID(activeTrade);
			string fillId = !string.IsNullOrEmpty(customFillId) ? customFillId : SafeFillId(ex.ExecutionId);
			string shot = CaptureScreenshotSafe(activeTrade.TradeID, eventId, "OPEN", ex.Time, activeTrade.TradeFolder);

			TradeEventRow row = new TradeEventRow
			{
				TradeID = activeTrade.TradeID,
				EventID = eventId,
				FillID = fillId,
				Time = ex.Time,
				EventType = "OPEN",
				Direction = activeTrade.Direction,
				OrderName = o.Name ?? string.Empty,
				Oco = o.Oco ?? string.Empty,
				OrderId = o.Id,
				ExecQty = Math.Abs(signedQty),
				PositionBefore = 0,
				PositionAfter = signedQty,
				FillPrice = ex.Price,
				AvgEntryBefore = 0,
				AvgEntryAfter = activeTrade.WeightedAvgEntryPrice,
				LegPnLCurrency = 0,
				CumRealizedPnLCurrency = activeTrade.RealizedPnLCurrency,
				ATMStop = activeTrade.ATMStop,
				FirstProtectiveStop = activeTrade.FirstProtectiveStop,
				InitialStop = activeTrade.InitialStop,
				FirstActualStop = activeTrade.FirstActualStop,
				CurrentStop = activeTrade.CurrentStop,
				ActualStop = activeTrade.CurrentStop,
				TargetAtEvent = activeTrade.CurrentTarget,
				AbsBar = absBar,
				SessionBar = sessionBar,
				SessionLastBar = sessionLastBar,
				BarsSinceTradeStart = 0,
				BarsSincePrevEvent = 0,
				SecondsSinceTradeStart = 0,
				SecondsSincePrevEvent = 0,
				ScreenshotFile = shot
			};

			activeTrade.EventRows.Add(row);

			activeEntryStudy = new EntryStudyRow
			{
				TradeID = activeTrade.TradeID,
				InstrumentName = Instrument.FullName,
				EntryTime = ex.Time,
				EntryPrice = ex.Price,
				EntryQty = Math.Abs(signedQty),
				Direction = activeTrade.Direction,
				EntryAbsBar = absBar,
				EntrySessionBar = sessionBar,
				EntrySessionLastBar = sessionLastBar,
				MAEPoints = 0,
				MFEPoints = 0
			};

			SetStudySessionEnd(ex.Time);
		}

		private void HandleAddExecution(Execution ex, Order o, int signedQty, int positionBefore, int positionAfter)
		{
			if (activeTrade == null)
				return;

			double avgBefore = activeTrade.WeightedAvgEntryPrice;
			double price = ex.Price;
			string eventType = ClassifyAddType(activeTrade.Direction, avgBefore, price);

			int addQty = Math.Abs(signedQty);

			if (eventType == "SCALE_IN")
				activeTrade.ScaleInCount++;
			else if (eventType == "ADD_ON")
				activeTrade.AddOnCount++;

			activeTrade.EntryPriceSum += price * addQty;
			activeTrade.TotalEntryQty += addQty;
			activeTrade.CurrentQty = positionAfter;
			activeTrade.MaxPositionQty = Math.Max(activeTrade.MaxPositionQty, Math.Abs(positionAfter));
			activeTrade.WeightedAvgEntryPrice = activeTrade.TotalEntryQty > 0
				? activeTrade.EntryPriceSum / activeTrade.TotalEntryQty
				: 0;

			int absBar, sessionBar, sessionLastBar;
			GetBarInfo(ex.Time, out absBar, out sessionBar, out sessionLastBar);

			int prevBar = activeTrade.LastEventBarIndex;
			DateTime prevTime = activeTrade.LastEventTime;

			string eventId = NextEventID(activeTrade);
			string shot = CaptureScreenshotSafe(activeTrade.TradeID, eventId, eventType, ex.Time, activeTrade.TradeFolder);

			TradeEventRow row = new TradeEventRow
			{
				TradeID = activeTrade.TradeID,
				EventID = eventId,
				FillID = SafeFillId(ex.ExecutionId),
				Time = ex.Time,
				EventType = eventType,
				Direction = activeTrade.Direction,
				OrderName = o.Name ?? string.Empty,
				Oco = o.Oco ?? string.Empty,
				OrderId = o.Id,
				ExecQty = addQty,
				PositionBefore = positionBefore,
				PositionAfter = positionAfter,
				FillPrice = price,
				AvgEntryBefore = avgBefore,
				AvgEntryAfter = activeTrade.WeightedAvgEntryPrice,
				LegPnLCurrency = 0,
				CumRealizedPnLCurrency = activeTrade.RealizedPnLCurrency,
				ATMStop = activeTrade.ATMStop,
				FirstProtectiveStop = activeTrade.FirstProtectiveStop,
				InitialStop = activeTrade.InitialStop,
				FirstActualStop = activeTrade.FirstActualStop,
				CurrentStop = activeTrade.CurrentStop,
				ActualStop = activeTrade.CurrentStop,
				TargetAtEvent = activeTrade.CurrentTarget,
				AbsBar = absBar,
				SessionBar = sessionBar,
				SessionLastBar = sessionLastBar,
				BarsSinceTradeStart = absBar >= 0 && activeTrade.StartBarIndex >= 0 ? absBar - activeTrade.StartBarIndex : -1,
				BarsSincePrevEvent = absBar >= 0 && prevBar >= 0 ? absBar - prevBar : -1,
				SecondsSinceTradeStart = (ex.Time - activeTrade.StartTime).TotalSeconds,
				SecondsSincePrevEvent = (ex.Time - prevTime).TotalSeconds,
				ScreenshotFile = shot
			};

			activeTrade.EventRows.Add(row);
			activeTrade.LastEventBarIndex = absBar;
			activeTrade.LastEventTime = ex.Time;
		}

		private void HandleExitExecution(Execution ex, Order o, int closeQty, int positionBefore, int positionAfter, string exitType, string customFillId = null)
		{
			if (activeTrade == null || closeQty <= 0)
				return;

			double fillPrice = ex.Price;
			double avgEntry = activeTrade.WeightedAvgEntryPrice;
			double legPoints = activeTrade.Direction == "LONG"
				? fillPrice - avgEntry
				: avgEntry - fillPrice;

			double legPnLCurrency = legPoints * closeQty * Instrument.MasterInstrument.PointValue;

			activeTrade.RealizedPnLCurrency += legPnLCurrency;
			activeTrade.TotalExitQty += closeQty;
			activeTrade.ExitPriceSum += fillPrice * closeQty;
			activeTrade.WeightedAvgExitPrice = activeTrade.TotalExitQty > 0
				? activeTrade.ExitPriceSum / activeTrade.TotalExitQty
				: 0;

			if (exitType == "SCALE_OUT")
				activeTrade.ScaleOutCount++;

			activeTrade.CurrentQty = positionAfter;
			activeTrade.LastExitType = exitType;

			int absBar, sessionBar, sessionLastBar;
			GetBarInfo(ex.Time, out absBar, out sessionBar, out sessionLastBar);

			int prevBar = activeTrade.LastEventBarIndex;
			DateTime prevTime = activeTrade.LastEventTime;

			string eventId = NextEventID(activeTrade);
			string shot = CaptureScreenshotSafe(activeTrade.TradeID, eventId, exitType, ex.Time, activeTrade.TradeFolder);

			TradeEventRow row = new TradeEventRow
			{
				TradeID = activeTrade.TradeID,
				EventID = eventId,
				FillID = !string.IsNullOrEmpty(customFillId) ? customFillId : SafeFillId(ex.ExecutionId),
				Time = ex.Time,
				EventType = exitType,
				Direction = activeTrade.Direction,
				OrderName = o.Name ?? string.Empty,
				Oco = o.Oco ?? string.Empty,
				OrderId = o.Id,
				ExecQty = closeQty,
				PositionBefore = positionBefore,
				PositionAfter = positionAfter,
				FillPrice = fillPrice,
				AvgEntryBefore = avgEntry,
				AvgEntryAfter = activeTrade.WeightedAvgEntryPrice,
				LegPnLCurrency = legPnLCurrency,
				CumRealizedPnLCurrency = activeTrade.RealizedPnLCurrency,
				ATMStop = activeTrade.ATMStop,
				FirstProtectiveStop = activeTrade.FirstProtectiveStop,
				InitialStop = activeTrade.InitialStop,
				FirstActualStop = activeTrade.FirstActualStop,
				CurrentStop = activeTrade.CurrentStop,
				ActualStop = activeTrade.CurrentStop,
				TargetAtEvent = activeTrade.CurrentTarget,
				AbsBar = absBar,
				SessionBar = sessionBar,
				SessionLastBar = sessionLastBar,
				BarsSinceTradeStart = absBar >= 0 && activeTrade.StartBarIndex >= 0 ? absBar - activeTrade.StartBarIndex : -1,
				BarsSincePrevEvent = absBar >= 0 && prevBar >= 0 ? absBar - prevBar : -1,
				SecondsSinceTradeStart = (ex.Time - activeTrade.StartTime).TotalSeconds,
				SecondsSincePrevEvent = (ex.Time - prevTime).TotalSeconds,
				ScreenshotFile = shot
			};

			activeTrade.EventRows.Add(row);
			activeTrade.LastEventBarIndex = absBar;
			activeTrade.LastEventTime = ex.Time;

			if (positionAfter == 0)
				CloseTrade(ex.Time, absBar, sessionBar, sessionLastBar);
		}

		private void CloseTrade(DateTime endTime, int endAbsBar, int endSessionBar, int endSessionLastBar)
		{
			if (activeTrade == null)
				return;

			TradeSummaryRow summary = new TradeSummaryRow
			{
				TradeID = activeTrade.TradeID,
				InstrumentName = activeTrade.InstrumentName,
				StartTime = activeTrade.StartTime,
				EndTime = endTime,
				Direction = activeTrade.Direction,
				TotalEntryQty = activeTrade.TotalEntryQty,
				TotalExitQty = activeTrade.TotalExitQty,
				MaxPositionQty = activeTrade.MaxPositionQty,
				FirstEntryPrice = activeTrade.FirstEntryPrice,
				WeightedAvgEntryPrice = activeTrade.WeightedAvgEntryPrice,
				WeightedAvgExitPrice = activeTrade.WeightedAvgExitPrice,
				ATMStop = activeTrade.ATMStop,
				FirstProtectiveStop = activeTrade.FirstProtectiveStop,
				InitialStop = activeTrade.InitialStop,
				FirstActualStop = activeTrade.FirstActualStop,
				CurrentStopAtExit = activeTrade.CurrentStop,
				InitialRiskPoints = GetRiskPoints(activeTrade.Direction, activeTrade.FirstEntryPrice, activeTrade.InitialStop),
				FirstActualRiskPoints = GetRiskPoints(activeTrade.Direction, activeTrade.FirstEntryPrice, activeTrade.FirstActualStop),
				GrossPnLCurrency = activeTrade.RealizedPnLCurrency,
				MAEPoints = activeTrade.MAEPoints,
				MFEPoints = activeTrade.MFEPoints,
				ScaleInCount = activeTrade.ScaleInCount,
				AddOnCount = activeTrade.AddOnCount,
				ScaleOutCount = activeTrade.ScaleOutCount,
				StartAbsBar = activeTrade.StartAbsBar,
				StartSessionBar = activeTrade.StartSessionBar,
				StartSessionLastBar = activeTrade.StartSessionLastBar,
				EndAbsBar = endAbsBar,
				EndSessionBar = endSessionBar,
				EndSessionLastBar = endSessionLastBar,
				BarsHeld = endAbsBar >= 0 && activeTrade.StartBarIndex >= 0 ? endAbsBar - activeTrade.StartBarIndex : -1,
				DurationSec = (endTime - activeTrade.StartTime).TotalSeconds,
				ExitType = activeTrade.LastExitType ?? string.Empty,
				TradeFolder = activeTrade.TradeFolder
			};

			WriteEventRows(activeTrade.EventRows, true, activeTrade.TradeFolder, activeTrade.TradeID);
			WriteTradeSummary(summary, true, activeTrade.TradeFolder, activeTrade.TradeID);

			activeTrade = null;
		}

		#endregion

		#region Stop handling

		private void HandleStopUpdate(double stopPrice, Order o)
		{
			if (activeTrade == null)
				return;

			if (activeTrade.FirstProtectiveStop <= 0)
			{
				activeTrade.FirstProtectiveStop = stopPrice;
				activeTrade.FirstProtectiveStopLocalTime = DateTime.Now;
				activeTrade.PendingInitialStopCandidate = stopPrice;
				activeTrade.CurrentStop = stopPrice;

				if (activeTrade.ATMStop <= 0)
					activeTrade.ATMStop = stopPrice;

				if (activeEntryStudy != null)
				{
					activeEntryStudy.FirstProtectiveStop = stopPrice;
					activeEntryStudy.FirstProtectiveStopTime = DateTime.Now;
				}

				CaptureScreenshotSafe(activeTrade.TradeID, NextNonFillEventTag(activeTrade), "FIRST_PROTECTIVE_STOP", DateTime.Now, activeTrade.TradeFolder);
				return;
			}

			// Before initial stop is locked: keep updating candidate inside first 5 seconds
			if (!activeTrade.InitialStopLocked)
			{
				activeTrade.PendingInitialStopCandidate = stopPrice;
				activeTrade.CurrentStop = stopPrice;
				CaptureScreenshotSafe(activeTrade.TradeID, NextNonFillEventTag(activeTrade), "STOP_ADJUST_PRELOCK", DateTime.Now, activeTrade.TradeFolder);
				return;
			}

			// After initial lock -> first new stop becomes first actual stop
			if (activeTrade.CurrentStop.ApproxCompare(stopPrice) != 0)
			{
				activeTrade.CurrentStop = stopPrice;

				if (!activeTrade.FirstActualCaptured)
				{
					activeTrade.FirstActualCaptured = true;
					activeTrade.FirstActualStop = stopPrice;
					activeTrade.FirstActualStopTime = DateTime.Now;

					if (activeEntryStudy != null && !activeEntryStudy.FirstActualCaptured)
					{
						activeEntryStudy.FirstActualCaptured = true;
						activeEntryStudy.FirstActualStop = stopPrice;
						activeEntryStudy.FirstActualStopTime = DateTime.Now;
					}

					CaptureScreenshotSafe(activeTrade.TradeID, NextNonFillEventTag(activeTrade), "FIRST_ACTUAL_STOP", DateTime.Now, activeTrade.TradeFolder);
				}
				else
				{
					CaptureScreenshotSafe(activeTrade.TradeID, NextNonFillEventTag(activeTrade), "STOP_UPDATE", DateTime.Now, activeTrade.TradeFolder);
				}
			}
		}

		private void TryLockInitialStop()
		{
			if (activeTrade == null)
				return;

			if (activeTrade.FirstProtectiveStop <= 0 || activeTrade.InitialStopLocked)
				return;

			if ((DateTime.Now - activeTrade.FirstProtectiveStopLocalTime).TotalSeconds < InitialStopLockSeconds)
				return;

			activeTrade.InitialStop = activeTrade.PendingInitialStopCandidate;
			activeTrade.InitialStopTime = DateTime.Now;
			activeTrade.InitialStopLocked = true;
			activeTrade.CurrentStop = activeTrade.PendingInitialStopCandidate;

			if (activeEntryStudy != null && !activeEntryStudy.InitialStopLocked)
			{
				activeEntryStudy.InitialStop = activeTrade.InitialStop;
				activeEntryStudy.InitialStopTime = activeTrade.InitialStopTime;
				activeEntryStudy.InitialStopLocked = true;
			}

			CaptureScreenshotSafe(activeTrade.TradeID, NextNonFillEventTag(activeTrade), "INITIAL_STOP_LOCK", DateTime.Now, activeTrade.TradeFolder);
		}

		#endregion

		#region Excursions and study

		private void UpdateOpenTradeExcursions()
		{
			if (activeTrade == null || CurrentBar < 0)
				return;

			double mfe, mae;
			ComputeExcursionFromEntry(activeTrade.Direction, activeTrade.FirstEntryPrice, out mfe, out mae);

			activeTrade.MFEPoints = Math.Max(activeTrade.MFEPoints, mfe);
			activeTrade.MAEPoints = Math.Min(activeTrade.MAEPoints, mae);
		}

		private void UpdateEntryStudyExcursions()
		{
			if (activeEntryStudy == null || activeEntryStudy.Written || CurrentBar < 0)
				return;

			double mfe, mae;
			ComputeExcursionFromEntry(activeEntryStudy.Direction, activeEntryStudy.EntryPrice, out mfe, out mae);

			activeEntryStudy.MFEPoints = Math.Max(activeEntryStudy.MFEPoints, mfe);
			activeEntryStudy.MAEPoints = Math.Min(activeEntryStudy.MAEPoints, mae);

			int barsSinceEntry = activeEntryStudy.EntryAbsBar >= 0 ? Math.Max(0, CurrentBar - activeEntryStudy.EntryAbsBar) : -1;
			double secsSinceEntry = (Time[0] - activeEntryStudy.EntryTime).TotalSeconds;

			if (!activeEntryStudy.FirstActualCaptured)
			{
				if (mfe > activeEntryStudy.MFEBeforeFirstActualPoints)
				{
					activeEntryStudy.MFEBeforeFirstActualPoints = mfe;

					double initialRiskNow = GetRiskPoints(activeEntryStudy.Direction, activeEntryStudy.EntryPrice, activeEntryStudy.InitialStop);
					if (initialRiskNow > 0)
					{
						double rBefore = mfe / initialRiskNow;
						if (rBefore > activeEntryStudy.MaxRBeforeFirstActualInitial)
						{
							activeEntryStudy.MaxRBeforeFirstActualInitial = rBefore;
							activeEntryStudy.BarsToMaxRBeforeFirstActual = barsSinceEntry;
							activeEntryStudy.DurationToMaxRBeforeFirstActualSec = secsSinceEntry;
						}
					}
				}
			}

			UpdateStudyRMetricsInitial(barsSinceEntry, secsSinceEntry);
			UpdateStudyRMetricsActual(barsSinceEntry, secsSinceEntry);
		}

		private void UpdateStudyRMetricsInitial(int barsSinceEntry, double secsSinceEntry)
		{
			if (activeEntryStudy == null || !activeEntryStudy.InitialStopLocked)
				return;

			double risk = GetRiskPoints(activeEntryStudy.Direction, activeEntryStudy.EntryPrice, activeEntryStudy.InitialStop);
			if (risk <= 0)
				return;

			double currentR = activeEntryStudy.MFEPoints / risk;
			if (currentR > activeEntryStudy.MaxRInitial)
			{
				activeEntryStudy.MaxRInitial = currentR;
				activeEntryStudy.BarsToMaxRInitial = barsSinceEntry;
				activeEntryStudy.DurationToMaxRInitialSec = secsSinceEntry;
			}

			if (activeEntryStudy.BarsTo1RInitial < 0 && activeEntryStudy.MFEPoints >= 1.0 * risk)
			{
				activeEntryStudy.BarsTo1RInitial = barsSinceEntry;
				activeEntryStudy.DurationTo1RInitialSec = secsSinceEntry;
			}

			if (activeEntryStudy.BarsTo2RInitial < 0 && activeEntryStudy.MFEPoints >= 2.0 * risk)
			{
				activeEntryStudy.BarsTo2RInitial = barsSinceEntry;
				activeEntryStudy.DurationTo2RInitialSec = secsSinceEntry;
			}

			if (activeEntryStudy.BarsTo3RInitial < 0 && activeEntryStudy.MFEPoints >= 3.0 * risk)
			{
				activeEntryStudy.BarsTo3RInitial = barsSinceEntry;
				activeEntryStudy.DurationTo3RInitialSec = secsSinceEntry;
			}
		}

		private void UpdateStudyRMetricsActual(int barsSinceEntry, double secsSinceEntry)
		{
			if (activeEntryStudy == null || !activeEntryStudy.FirstActualCaptured)
				return;

			double risk = GetRiskPoints(activeEntryStudy.Direction, activeEntryStudy.EntryPrice, activeEntryStudy.FirstActualStop);
			if (risk <= 0)
				return;

			double currentR = activeEntryStudy.MFEPoints / risk;
			if (currentR > activeEntryStudy.MaxRActual)
			{
				activeEntryStudy.MaxRActual = currentR;
				activeEntryStudy.BarsToMaxRActual = barsSinceEntry;
				activeEntryStudy.DurationToMaxRActualSec = secsSinceEntry;
			}

			if (activeEntryStudy.BarsTo1RActual < 0 && activeEntryStudy.MFEPoints >= 1.0 * risk)
			{
				activeEntryStudy.BarsTo1RActual = barsSinceEntry;
				activeEntryStudy.DurationTo1RActualSec = secsSinceEntry;
			}

			if (activeEntryStudy.BarsTo2RActual < 0 && activeEntryStudy.MFEPoints >= 2.0 * risk)
			{
				activeEntryStudy.BarsTo2RActual = barsSinceEntry;
				activeEntryStudy.DurationTo2RActualSec = secsSinceEntry;
			}

			if (activeEntryStudy.BarsTo3RActual < 0 && activeEntryStudy.MFEPoints >= 3.0 * risk)
			{
				activeEntryStudy.BarsTo3RActual = barsSinceEntry;
				activeEntryStudy.DurationTo3RActualSec = secsSinceEntry;
			}
		}

		private void SetStudySessionEnd(DateTime tradeTime)
		{
			if (activeEntryStudy == null || sessionIterator == null)
				return;

			sessionIterator.GetNextSession(tradeTime, true);
			activeEntryStudy.SessionEndTime = sessionIterator.ActualSessionEnd;
		}

		private void CheckSessionBoundaryForStudyAndScreenshot()
		{
			// Session-end screenshot: taken on first bar of the next session
			if (Bars.IsFirstBarOfSession)
			{
				if (!sessionEndScreenshotTakenForCurrentSession && CurrentBar > 0)
				{
					string folder = activeTrade != null
						? activeTrade.TradeFolder
						: EnsureSessionFolder(Time[1]);

					CaptureScreenshotSafe(
						activeTrade != null ? activeTrade.TradeID : "NO_ACTIVE_TRADE",
						"SESSION",
						"SESSION_END",
						Time[1],
						folder);

					sessionEndScreenshotTakenForCurrentSession = true;
				}
			}
			else
			{
				sessionEndScreenshotTakenForCurrentSession = false;
			}

			// Entry study write on first bar after session end
			if (activeEntryStudy == null || activeEntryStudy.Written)
				return;

			if (Bars.IsFirstBarOfSession && CurrentBar > 0 && Time[0] > activeEntryStudy.SessionEndTime)
			{
				FinalizeEntryStudy(Time[1], Close[1]);
			}
		}

		private void FinalizeEntryStudy(DateTime sessionCloseBarTime, double sessionClosePrice)
		{
			if (activeEntryStudy == null || activeEntryStudy.Written)
				return;

			int absBar, sessionBar, sessionLastBar;
			GetBarInfo(sessionCloseBarTime, out absBar, out sessionBar, out sessionLastBar);

			activeEntryStudy.SessionClosePrice = sessionClosePrice;
			activeEntryStudy.ExitAbsBar = absBar;
			activeEntryStudy.ExitSessionBar = sessionBar;
			activeEntryStudy.ExitSessionLastBar = sessionLastBar;
			activeEntryStudy.BarsFromEntryToSessionClose =
				(activeEntryStudy.EntryAbsBar >= 0 && absBar >= 0) ? absBar - activeEntryStudy.EntryAbsBar : -1;
			activeEntryStudy.DurationToSessionCloseSec = (sessionCloseBarTime - activeEntryStudy.EntryTime).TotalSeconds;
			activeEntryStudy.Written = true;

			string folder = activeTrade != null ? activeTrade.TradeFolder : EnsureTradeFolder(activeEntryStudy.TradeID, activeEntryStudy.EntryTime);
			WriteEntryStudy(activeEntryStudy, true, folder, activeEntryStudy.TradeID);
		}

		#endregion

		#region Helpers

		private int GetSignedQty(OrderAction action, int qty)
		{
			switch (action)
			{
				case OrderAction.Buy:
				case OrderAction.BuyToCover:
					return qty;

				case OrderAction.Sell:
				case OrderAction.SellShort:
					return -qty;

				default:
					return 0;
			}
		}

		private bool IsStopOrder(Order o)
		{
			return o.OrderType == OrderType.StopMarket || o.OrderType == OrderType.StopLimit;
		}

		private string ClassifyAddType(string direction, double avgBefore, double price)
		{
			if (direction == "LONG")
				return price <= avgBefore ? "SCALE_IN" : "ADD_ON";

			return price >= avgBefore ? "SCALE_IN" : "ADD_ON";
		}

		private string NextEventID(ActiveTrade trade)
		{
			trade.EventCounter++;
			return trade.TradeID + "_E" + trade.EventCounter.ToString(INV);
		}

		private string NextNonFillEventTag(ActiveTrade trade)
		{
			trade.EventCounter++;
			return trade.TradeID + "_E" + trade.EventCounter.ToString(INV);
		}

		private void ComputeExcursionFromEntry(string direction, double entryPrice, out double mfePoints, out double maePoints)
		{
			if (direction == "LONG")
			{
				mfePoints = High[0] - entryPrice;
				maePoints = Low[0] - entryPrice;
			}
			else
			{
				mfePoints = entryPrice - Low[0];
				maePoints = entryPrice - High[0];
			}
		}

		private double GetRiskPoints(string direction, double entryPrice, double stopPrice)
		{
			if (stopPrice <= 0)
				return 0;

			if (direction == "LONG")
				return Math.Max(0, entryPrice - stopPrice);

			return Math.Max(0, stopPrice - entryPrice);
		}

		private void GetBarInfo(DateTime time, out int absBar, out int sessionBar, out int sessionLastBar)
		{
			absBar = -1;
			sessionBar = -1;
			sessionLastBar = -1;

			if (Bars == null || CurrentBar < 0 || sessionIterator == null)
				return;

			absBar = Bars.GetBar(time);
			if (absBar < 0)
				return;

			sessionIterator.GetNextSession(time, false);

			DateTime sessionStart = sessionIterator.ActualSessionBegin;
			DateTime sessionEnd = sessionIterator.ActualSessionEnd;

			int startBar = Bars.GetBar(sessionStart);
			int endBar = Bars.GetBar(sessionEnd);

			if (startBar >= 0)
				sessionBar = absBar - startBar + 1;

			if (startBar >= 0 && endBar >= 0)
				sessionLastBar = endBar - startBar + 1;
		}

		private string SafeFillId(string executionId)
		{
			return string.IsNullOrEmpty(executionId) ? string.Empty : executionId;
		}

		private string EnsureTradeFolder(string tradeId, DateTime time)
		{
			string instrumentName = SanitizeFilePart(Instrument.FullName);
			string date = time.ToString("yyyy-MM-dd");
			string folder = Path.Combine(outputRoot, instrumentName, date, tradeId);

			if (!Directory.Exists(folder))
				Directory.CreateDirectory(folder);

			return folder;
		}

		private string EnsureSessionFolder(DateTime time)
		{
			string instrumentName = SanitizeFilePart(Instrument.FullName);
			string date = time.ToString("yyyy-MM-dd");
			string folder = Path.Combine(outputRoot, instrumentName, date, "_SESSION");

			if (!Directory.Exists(folder))
				Directory.CreateDirectory(folder);

			return folder;
		}

		private string SanitizeFilePart(string value)
		{
			if (string.IsNullOrEmpty(value))
				return "NA";

			foreach (char c in Path.GetInvalidFileNameChars())
				value = value.Replace(c, '_');

			return value.Replace(" ", "_");
		}

		private string CaptureScreenshotSafe(string tradeId, string eventId, string eventType, DateTime time, string folder)
		{
			if (!EnableScreenshots)
				return string.Empty;

			try
			{
				if (ChartControl == null || ChartControl.Dispatcher == null)
					return string.Empty;

				string instrumentName = SanitizeFilePart(Instrument.FullName);
				string date = time.ToString("yyyy-MM-dd");
				string fileName = string.Format(
					INV,
					"{0}_{1}_{2}_{3}_{4}.png",
					date,
					instrumentName,
					SanitizeFilePart(tradeId),
					SanitizeFilePart(eventId),
					SanitizeFilePart(eventType));

				string fullPath = Path.Combine(folder, fileName);

				ChartControl.Dispatcher.InvokeAsync(() =>
				{
					try
					{
						double width = ChartControl.ActualWidth;
						double height = ChartControl.ActualHeight;

						if (width <= 0 || height <= 0)
							return;

						RenderTargetBitmap rtb = new RenderTargetBitmap(
							(int)Math.Round(width),
							(int)Math.Round(height),
							96d,
							96d,
							PixelFormats.Pbgra32);

						rtb.Render(ChartControl);

						PngBitmapEncoder encoder = new PngBitmapEncoder();
						encoder.Frames.Add(BitmapFrame.Create(rtb));

						using (FileStream fs = new FileStream(fullPath, FileMode.Create, FileAccess.Write))
							encoder.Save(fs);
					}
					catch (Exception ex)
					{
						Print("Screenshot error: " + ex.Message);
					}
				});

				return fullPath;
			}
			catch (Exception ex)
			{
				Print("CaptureScreenshotSafe error: " + ex.Message);
				return string.Empty;
			}
		}

		#endregion

		#region CSV writers

		private void WriteEventRows(List<TradeEventRow> rows, bool appendToMaster, string tradeFolder, string tradeId)
		{
			if (rows == null || rows.Count == 0)
				return;

			string date = rows[0].Time.ToString("yyyy-MM-dd");
			string instrumentName = SanitizeFilePart(Instrument.FullName);

			string masterPath = Path.Combine(outputRoot, instrumentName, string.Format(INV, "Events_{0}.csv", date));
			string tradePath = Path.Combine(tradeFolder, string.Format(INV, "{0}_Events.csv", tradeId));

			WriteEventFile(masterPath, rows, appendToMaster);
			WriteEventFile(tradePath, rows, false);
		}

		private void WriteTradeSummary(TradeSummaryRow row, bool appendToMaster, string tradeFolder, string tradeId)
		{
			string date = row.StartTime.ToString("yyyy-MM-dd");
			string instrumentName = SanitizeFilePart(Instrument.FullName);

			string masterPath = Path.Combine(outputRoot, instrumentName, string.Format(INV, "Trades_{0}.csv", date));
			string tradePath = Path.Combine(tradeFolder, string.Format(INV, "{0}_TradeSummary.csv", tradeId));

			WriteTradeFile(masterPath, row, appendToMaster);
			WriteTradeFile(tradePath, row, false);
		}

		private void WriteEntryStudy(EntryStudyRow row, bool appendToMaster, string tradeFolder, string tradeId)
		{
			string date = row.EntryTime.ToString("yyyy-MM-dd");
			string instrumentName = SanitizeFilePart(Instrument.FullName);

			string masterPath = Path.Combine(outputRoot, instrumentName, string.Format(INV, "EntryStudy_{0}.csv", date));
			string tradePath = Path.Combine(tradeFolder, string.Format(INV, "{0}_EntryStudy.csv", tradeId));

			WriteEntryStudyFile(masterPath, row, appendToMaster);
			WriteEntryStudyFile(tradePath, row, false);
		}

		private void WriteEventFile(string path, List<TradeEventRow> rows, bool append)
{
	try
	{
		bool exists = File.Exists(path);

		using (StreamWriter sw = new StreamWriter(path, append))
		{
			if (!exists || !append)
			{
				sw.WriteLine("TradeID,EventID,FillID,Time,EventType,Direction,OrderName,Oco,OrderId,ExecQty,PositionBefore,PositionAfter,FillPrice,AvgEntryBefore,AvgEntryAfter,LegPnLCurrency,CumRealizedPnLCurrency,ATMStop,FirstProtectiveStop,InitialStop,FirstActualStop,CurrentStop,ActualStop,TargetAtEvent,AbsBar,SessionBar,SessionLastBar,BarsSinceTradeStart,BarsSincePrevEvent,SecondsSinceTradeStart,SecondsSincePrevEvent,ScreenshotFile");
			}

			foreach (TradeEventRow r in rows.OrderBy(x => x.Time))
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
					Csv(r.FillPrice.ToString(INV)),
					Csv(r.AvgEntryBefore.ToString(INV)),
					Csv(r.AvgEntryAfter.ToString(INV)),
					Csv(r.LegPnLCurrency.ToString(INV)),
					Csv(r.CumRealizedPnLCurrency.ToString(INV)),
					Csv(r.ATMStop.ToString(INV)),
					Csv(r.FirstProtectiveStop.ToString(INV)),
					Csv(r.InitialStop.ToString(INV)),
					Csv(r.FirstActualStop.ToString(INV)),
					Csv(r.CurrentStop.ToString(INV)),
					Csv(r.ActualStop.ToString(INV)),
					Csv(r.TargetAtEvent.ToString(INV)),
					Csv(r.AbsBar.ToString(INV)),
					Csv(r.SessionBar.ToString(INV)),
					Csv(r.SessionLastBar.ToString(INV)),
					Csv(r.BarsSinceTradeStart.ToString(INV)),
					Csv(r.BarsSincePrevEvent.ToString(INV)),
					Csv(r.SecondsSinceTradeStart.ToString(INV)),
					Csv(r.SecondsSincePrevEvent.ToString(INV)),
					Csv(r.ScreenshotFile)
				));
			}
		}

		DebugPrint("CSV WRITE (EVENTS): " + path);
	}
	catch (Exception ex)
	{
		DebugPrint("CSV ERROR (EVENTS): " + ex.Message);
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
			{
				sw.WriteLine("TradeID,Instrument,StartTime,EndTime,Direction,TotalEntryQty,TotalExitQty,MaxPositionQty,FirstEntryPrice,WeightedAvgEntryPrice,WeightedAvgExitPrice,ATMStop,FirstProtectiveStop,InitialStop,FirstActualStop,CurrentStopAtExit,InitialRiskPoints,FirstActualRiskPoints,GrossPnLCurrency,MAEPoints,MFEPoints,ScaleInCount,AddOnCount,ScaleOutCount,StartAbsBar,StartSessionBar,StartSessionLastBar,EndAbsBar,EndSessionBar,EndSessionLastBar,BarsHeld,DurationSec,ExitType,TradeFolder");
			}

			sw.WriteLine(string.Join(",",
				Csv(r.TradeID),
				Csv(r.InstrumentName),
				Csv(r.StartTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.EndTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.Direction),
				Csv(r.TotalEntryQty.ToString(INV)),
				Csv(r.TotalExitQty.ToString(INV)),
				Csv(r.MaxPositionQty.ToString(INV)),
				Csv(r.FirstEntryPrice.ToString(INV)),
				Csv(r.WeightedAvgEntryPrice.ToString(INV)),
				Csv(r.WeightedAvgExitPrice.ToString(INV)),
				Csv(r.ATMStop.ToString(INV)),
				Csv(r.FirstProtectiveStop.ToString(INV)),
				Csv(r.InitialStop.ToString(INV)),
				Csv(r.FirstActualStop.ToString(INV)),
				Csv(r.CurrentStopAtExit.ToString(INV)),
				Csv(r.InitialRiskPoints.ToString(INV)),
				Csv(r.FirstActualRiskPoints.ToString(INV)),
				Csv(r.GrossPnLCurrency.ToString(INV)),
				Csv(r.MAEPoints.ToString(INV)),
				Csv(r.MFEPoints.ToString(INV)),
				Csv(r.ScaleInCount.ToString(INV)),
				Csv(r.AddOnCount.ToString(INV)),
				Csv(r.ScaleOutCount.ToString(INV)),
				Csv(r.StartAbsBar.ToString(INV)),
				Csv(r.StartSessionBar.ToString(INV)),
				Csv(r.StartSessionLastBar.ToString(INV)),
				Csv(r.EndAbsBar.ToString(INV)),
				Csv(r.EndSessionBar.ToString(INV)),
				Csv(r.EndSessionLastBar.ToString(INV)),
				Csv(r.BarsHeld.ToString(INV)),
				Csv(r.DurationSec.ToString(INV)),
				Csv(r.ExitType),
				Csv(r.TradeFolder)
			));
		}

		DebugPrint("CSV WRITE (TRADES): " + path);
	}
	catch (Exception ex)
	{
		DebugPrint("CSV ERROR (TRADES): " + ex.Message);
	}
}

		private void WriteEntryStudyFile(string path, EntryStudyRow r, bool append)
{
	try
	{
		bool exists = File.Exists(path);

		using (StreamWriter sw = new StreamWriter(path, append))
		{
			if (!exists || !append)
			{
				sw.WriteLine("TradeID,Instrument,EntryTime,EntryPrice,EntryQty,Direction,SessionEndTime,EntryAbsBar,EntrySessionBar,EntrySessionLastBar,FirstProtectiveStop,FirstProtectiveStopTime,InitialStop,InitialStopTime,FirstActualStop,FirstActualStopTime,MFEPoints,MAEPoints,MaxRInitial,BarsToMaxRInitial,DurationToMaxRInitialSec,MaxRActual,BarsToMaxRActual,DurationToMaxRActualSec,BarsTo1RInitial,DurationTo1RInitialSec,BarsTo2RInitial,DurationTo2RInitialSec,BarsTo3RInitial,DurationTo3RInitialSec,BarsTo1RActual,DurationTo1RActualSec,BarsTo2RActual,DurationTo2RActualSec,BarsTo3RActual,DurationTo3RActualSec,MFEBeforeFirstActualPoints,MaxRBeforeFirstActualInitial,BarsToMaxRBeforeFirstActual,DurationToMaxRBeforeFirstActualSec,EfficiencyAtInitialStop,SessionClosePrice,ExitAbsBar,ExitSessionBar,ExitSessionLastBar,BarsFromEntryToSessionClose,DurationToSessionCloseSec");
			}

			double initialRisk = GetRiskPoints(r.Direction, r.EntryPrice, r.InitialStop);
			double efficiencyAtInitialStop = initialRisk > 0 ? r.MFEBeforeFirstActualPoints / initialRisk : 0;

			sw.WriteLine(string.Join(",",
				Csv(r.TradeID),
				Csv(r.InstrumentName),
				Csv(r.EntryTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.EntryPrice.ToString(INV)),
				Csv(r.EntryQty.ToString(INV)),
				Csv(r.Direction),
				Csv(r.SessionEndTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.EntryAbsBar.ToString(INV)),
				Csv(r.EntrySessionBar.ToString(INV)),
				Csv(r.EntrySessionLastBar.ToString(INV)),
				Csv(r.FirstProtectiveStop.ToString(INV)),
				Csv(r.FirstProtectiveStopTime == default(DateTime) ? string.Empty : r.FirstProtectiveStopTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.InitialStop.ToString(INV)),
				Csv(r.InitialStopTime == default(DateTime) ? string.Empty : r.InitialStopTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.FirstActualStop.ToString(INV)),
				Csv(r.FirstActualStopTime == default(DateTime) ? string.Empty : r.FirstActualStopTime.ToString("yyyy-MM-dd HH:mm:ss.fff", INV)),
				Csv(r.MFEPoints.ToString(INV)),
				Csv(r.MAEPoints.ToString(INV)),
				Csv(r.MaxRInitial.ToString(INV)),
				Csv(r.BarsToMaxRInitial.ToString(INV)),
				Csv(r.DurationToMaxRInitialSec.ToString(INV)),
				Csv(r.MaxRActual.ToString(INV)),
				Csv(r.BarsToMaxRActual.ToString(INV)),
				Csv(r.DurationToMaxRActualSec.ToString(INV)),
				Csv(r.BarsTo1RInitial.ToString(INV)),
				Csv(r.DurationTo1RInitialSec.ToString(INV)),
				Csv(r.BarsTo2RInitial.ToString(INV)),
				Csv(r.DurationTo2RInitialSec.ToString(INV)),
				Csv(r.BarsTo3RInitial.ToString(INV)),
				Csv(r.DurationTo3RInitialSec.ToString(INV)),
				Csv(r.BarsTo1RActual.ToString(INV)),
				Csv(r.DurationTo1RActualSec.ToString(INV)),
				Csv(r.BarsTo2RActual.ToString(INV)),
				Csv(r.DurationTo2RActualSec.ToString(INV)),
				Csv(r.BarsTo3RActual.ToString(INV)),
				Csv(r.DurationTo3RActualSec.ToString(INV)),
				Csv(r.MFEBeforeFirstActualPoints.ToString(INV)),
				Csv(r.MaxRBeforeFirstActualInitial.ToString(INV)),
				Csv(r.BarsToMaxRBeforeFirstActual.ToString(INV)),
				Csv(r.DurationToMaxRBeforeFirstActualSec.ToString(INV)),
				Csv(efficiencyAtInitialStop.ToString(INV)),
				Csv(r.SessionClosePrice.ToString(INV)),
				Csv(r.ExitAbsBar.ToString(INV)),
				Csv(r.ExitSessionBar.ToString(INV)),
				Csv(r.ExitSessionLastBar.ToString(INV)),
				Csv(r.BarsFromEntryToSessionClose.ToString(INV)),
				Csv(r.DurationToSessionCloseSec.ToString(INV))
			));
		}

		DebugPrint("CSV WRITE (ENTRY): " + path);
	}
	catch (Exception ex)
	{
		DebugPrint("CSV ERROR (ENTRY): " + ex.Message);
	}
}

		private string Csv(string s)
		{
			if (s == null)
				s = string.Empty;

			return "\"" + s.Replace("\"", "\"\"") + "\"";
		}

		#endregion
	}

	internal static class ApproxExtensions
	{
		public static int ApproxCompare(this double a, double b, double eps = 1e-10)
		{
			if (Math.Abs(a - b) <= eps)
				return 0;

			return a < b ? -1 : 1;
		}
	}
}