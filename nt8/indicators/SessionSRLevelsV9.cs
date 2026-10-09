// SessionSRLevelsV9 — RTH + ETH session S/R levels, drawn from NT8's OWN CME trading-hours
// templates (not hardcoded clock times), so the lines land at the right spot on holidays
// and half-days too.
//
// LEVELS (12 total, independently stylable): for BOTH the RTH session and the ETH
// (overnight/non-RTH) session —
//   HOY/LOY/COY = High/Low/Close of the prior completed session (NOT "of year" despite
//                 the name — "Of Yesterday" in the Globex-sense of "the last one").
//   OoD/OoW/OoM = Open of Day / Week / Month for that session.
//   EXCEPTION: EHOY/ELOY (properties still named *HOY*/*LOY* for template/persistence
//              compatibility, but relabeled "H ETH"/"L ETH") track the CURRENT, still
//              in-progress ETH-only session's running high/low, not the prior completed
//              one — live-updating reference, requested instead of the prior-day version.
//
// SESSION SOURCE (why this gets the timing right):
//   RTH window   = read from the NT8 Trading Hours template named by RthTemplateName
//                  (default "CME US Index Futures RTH": Mon-Fri 08:30-15:15 Central,
//                  with NT's own Holidays + PartialHolidays calendar baked in — half-day
//                  early closes on July 3, day-after-Thanksgiving, Christmas Eve, etc.
//                  are already correct in that template file and get picked up for free
//                  via Data.SessionIterator; nothing here reimplements the CME calendar).
//   Full/ETH day = the CHART's own Bars.TradingHours (expected to be the 23h Globex
//                  template, e.g. "CME US Index Futures ETH", so both sessions actually
//                  exist in the loaded bars). A bar is "ETH" simply when it falls inside
//                  the full day but OUTSIDE that day's resolved RTH window.
//
// Two Chart Trader buttons (RTH / ETH) toggle each session's levels on/off — same mount
// pattern as BreakoutBoysDashboardV1.cs (chartTrader.Content -> button Grid).
//
// PLANNED (not built yet): a manual-levels section, deliberately left out of scope now.
//
// ⚠ Session-boundary correctness on a real half-day should be eyeballed once on F5 (scroll
// to the most recent Thanksgiving Friday / Christmas Eve) — OnRender/SessionIterator
// behavior isn't covered by nt8_compile_check.ps1.
// RULE (CLAUDE.md): lives in nt8/ committed. Deploy to Documents\...\Custom\Indicators\ then F5.

#region Using declarations
using System;
using System.Collections.Generic;
using System.IO;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
// Color/Brush/SolidColorBrush exist in BOTH System.Windows.Media (WPF, used by button/property
// colors) and SharpDX/SharpDX.Direct2D1 (used by OnRender) — alias both sides to kill the
// ambiguous-reference compile errors instead of fully qualifying every single use.
using WMColor = System.Windows.Media.Color;
using WMBrush = System.Windows.Media.Brush;
using WMSolidColorBrush = System.Windows.Media.SolidColorBrush;
using D2DSolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript
{
	// Defined in the PARENT namespace (NinjaTrader.NinjaScript), NOT in .Indicators — same
	// reason as ETHSessionDefinition in ETHLevelsExporter.cs: NT8 regenerates the wrapper
	// code in the sibling .MarketAnalyzerColumns and .Strategies namespaces on every
	// compile using the unqualified enum name, so the enum must live where all three
	// child namespaces can see it by walking up to this common parent.
	public enum LevelLineStyle { Solid, Dash, Dot, DashDot }
}

namespace NinjaTrader.NinjaScript.Indicators
{
	public class SessionSRLevelsV9 : Indicator
	{
		// ── session plumbing ───────────────────────────────────────────────
		private SessionIterator _dayIter;      // Bars-bound: full trading-day/week/month boundaries
		private TradingHours    _rthHours;     // resolved RTH-only template
		private SessionIterator _rthIter;      // TradingHours-bound: RTH sub-session begin/end (holiday/half-day aware)
		private bool            _rthOk;         // false if RTH template name didn't resolve
		private TimeZoneInfo    _displayTz;
		private DateTime        _rthSessBegin = Core.Globals.MinDate;
		private DateTime        _rthSessEnd   = Core.Globals.MinDate;

		// ── per-trading-day accumulators ──────────────────────────────────
		private DateTime _curTradingDay = Core.Globals.MinDate;
		private DateTime _curWeekStart  = Core.Globals.MinDate;
		private int      _curMonthKey   = -1;
		private bool     _haveRth, _haveEth;
		private double   _rthHigh, _rthLow, _rthCloseLast;
		private double   _ethHigh, _ethLow, _ethCloseLast;
		private bool     _rthOpenCapturedToday;
		private bool     _weekAwaitingRthOpen, _monthAwaitingRthOpen;

		// bar index of the running RTH/ETH high/low PRINT (updated only when a new
		// extreme is actually made) + the most recent bar processed in that session —
		// these become the "prior" start-bars below once the session flushes.
		private int _rthHighBar = -1, _rthLowBar = -1, _rthLastBar = -1;
		private int _ethHighBar = -1, _ethLowBar = -1, _ethLastBar = -1;

		// ── values actually drawn (prior completed session + opens) ──────
		private double _priorRthHigh = double.NaN, _priorRthLow = double.NaN, _priorRthClose = double.NaN;
		private double _priorEthHigh = double.NaN, _priorEthLow = double.NaN, _priorEthClose = double.NaN;
		private double _rthOpenToday = double.NaN, _rthOpenThisWeek = double.NaN, _rthOpenThisMonth = double.NaN;
		private double _ethOpenToday = double.NaN, _ethOpenThisWeek = double.NaN, _ethOpenThisMonth = double.NaN;

		// ── bar index each level's line should START drawing from — the bar where
		// that EXACT price actually printed (the high/low/close tick itself), NOT an
		// administrative marker like the day-roll bar. Lines are rays from here to the
		// current bar, never full chart-width spans.
		private int _priorRthHighStartBar = -1, _priorRthLowStartBar = -1, _priorRthCloseStartBar = -1;
		private int _priorEthHighStartBar = -1, _priorEthLowStartBar = -1, _priorEthCloseStartBar = -1;
		private int _rthOpenStartBar  = -1, _ethOpenStartBar  = -1;
		private int _rthWeekStartBar  = -1, _ethWeekStartBar  = -1;
		private int _rthMonthStartBar = -1, _ethMonthStartBar = -1;

		// ── ETH from a dedicated hidden ETH-hours series (BarsArray[1]) so ETH levels
		// work on ANY chart — incl. an RTH-only chart whose own bars never fall in ETH
		// hours. This series has its own session timeline, tracked separately from RTH.
		private SessionIterator _ethDayIter;
		private SessionIterator _rthMembershipIter;   // separate RTH iterator used to lock the overnight H/L at RTH open
		private bool     _ethSeriesAdded;
		private bool     _ethLocked;                  // true once RTH has opened for the current ETH session
		private DateTime _ethCurTradingDay = Core.Globals.MinDate;
		private DateTime _ethCurWeekStart  = Core.Globals.MinDate;
		private int      _ethCurMonthKey   = -1;

		// Primary chart's current-session open bars = first bar of the current trading day /
		// week / month on THIS chart (RTH open on an RTH chart, ETH/Globex 17:00 open on an
		// ETH chart). ETH lines start here on intraday charts so they begin at the session
		// open the user is looking at. (On daily charts these stay -1 — the primary loop that
		// sets them is skipped — and rendering falls back to the calendar-date walk.)
		private int      _primaryDayOpenBar   = -1;
		private int      _primaryWeekOpenBar  = -1;
		private int      _primaryMonthOpenBar = -1;

		// Current-day running High/Low, tracked from the ACTUAL bars (not the visible window)
		// so it stays locked when you scroll/zoom. Intraday only; on daily OnBarUpdate is
		// skipped and the current-day H/L is just the latest daily bar's own High/Low.
		private double   _curDayHigh = double.NaN, _curDayLow = double.NaN;
		private int      _curDayStartBar = -1;

		// Expected-move 1-day bands — two methods compared side by side:
		//   VIX  = prior RTH close ± close*(VIX/100)/sqrt(252)*sigma   (matches options_gameplan.em_halfwidth)
		//   GEX  = emUpper/emLower read straight from the gexlog morning (or prior-evening) brief
		// Both read repo files on a throttle; manual VIX override available.
		private double   _emvMax = double.NaN, _emvMin = double.NaN;   // VIX-formula band
		private double   _emgMax = double.NaN, _emgMin = double.NaN;   // gexlog published band
		private double   _vixUsed = double.NaN;
		private DateTime _emLastRead = DateTime.MinValue;
		private const double SQRT252 = 15.874507866387544;

		// ── Chart Trader toggle buttons ───────────────────────────────────
		private Grid   ctButtonsGrid;
		private bool   ctPanelActive;
		private int    ctBaseRowCount;
		private Button btnRth, btnEth, btnLabels, btnPrice;
		private bool   _rthVisible = true, _ethVisible = true, _labelsVisible = true;
		private bool   _priceVisibleSet = false; private bool _priceVisible = true;  // CT price toggle; seeded from ShowPriceInLabel on first render
		private WMColor ColorOn  = WMColor.FromRgb(0, 140, 0);
		private WMColor ColorOff = WMColor.FromRgb(80, 80, 80);

		private struct LevelDef
		{
			public bool enabled; public string label; public double price;
			public WMColor color; public int opacity; public LevelLineStyle style; public int thickness;
			public int col; public int startBarIdx; public int endBarIdx;   // endBarIdx -1 = extend to current+ExtendBarsRight
		}

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name                     = "SessionSRLevelsV9";
				Description              = "RTH + ETH session S/R levels (HOY/LOY/COY/OoD/OoW/OoM) from NT8's own CME trading-hours templates.";
				Calculate                = Calculate.OnBarClose;
				IsOverlay                = true;
				IsChartOnly              = true;
				DisplayInDataBox         = false;
				PaintPriceMarkers        = false;
				BarsRequiredToPlot       = 0;

				RthTemplateName     = "CME US Index Futures RTH";
				FullTemplateNameHint = "CME US Index Futures ETH";
				LabelFontSize       = 11;
				ShowPriceInLabel    = true;
				ExtendBarsRight     = 10;

				// Current-day running High/Low (computed from the chart's own bars for today).
				CDH_Enabled = true; CDH_Label = "HoD"; CDH_Color = Brushes.DarkCyan; CDH_Opacity = 100; CDH_Style = LevelLineStyle.Solid; CDH_Thickness = 1;
				CDL_Enabled = true; CDL_Label = "LoD"; CDL_Color = Brushes.DarkCyan; CDL_Opacity = 100; CDL_Style = LevelLineStyle.Solid; CDL_Thickness = 1;

				// Expected-move bands (two methods, for comparison).
				VixCsvPath   = @"C:\Users\Admin\myquant\data\vix_daily.csv";
				GexlogRawDir = @"C:\Users\Admin\myquant\data\gexlog\raw";
				EmManualVix  = 0;     // 0 = auto (read last close from VixCsvPath)
				EmSigma      = 1.0;
				EMV_Max_Enabled = true; EMV_Max_Label = "1D Max VIX"; EMV_Max_Color = Brushes.Plum;     EMV_Max_Opacity = 90; EMV_Max_Style = LevelLineStyle.Dot; EMV_Max_Thickness = 1;
				EMV_Min_Enabled = true; EMV_Min_Label = "1D Min VIX"; EMV_Min_Color = Brushes.Plum;     EMV_Min_Opacity = 90; EMV_Min_Style = LevelLineStyle.Dot; EMV_Min_Thickness = 1;
				EMG_Max_Enabled = true; EMG_Max_Label = "1D Max GEX"; EMG_Max_Color = Brushes.Khaki;    EMG_Max_Opacity = 90; EMG_Max_Style = LevelLineStyle.Dot; EMG_Max_Thickness = 1;
				EMG_Min_Enabled = true; EMG_Min_Label = "1D Min GEX"; EMG_Min_Color = Brushes.Khaki;    EMG_Min_Opacity = 90; EMG_Min_Style = LevelLineStyle.Dot; EMG_Min_Thickness = 1;

				// RTH defaults: solid, saturated, thickness 2. Label = "{metric} RTH".
				RHOY_Enabled = true;  RHOY_Label = "HOY RTH"; RHOY_Color = Brushes.IndianRed;      RHOY_Opacity = 100; RHOY_Style = LevelLineStyle.Solid; RHOY_Thickness = 2;
				RLOY_Enabled = true;  RLOY_Label = "LOY RTH"; RLOY_Color = Brushes.RoyalBlue;      RLOY_Opacity = 100; RLOY_Style = LevelLineStyle.Solid; RLOY_Thickness = 2;
				RCOY_Enabled = true;  RCOY_Label = "COY RTH"; RCOY_Color = Brushes.Goldenrod;      RCOY_Opacity = 100; RCOY_Style = LevelLineStyle.Solid; RCOY_Thickness = 2;
				ROoD_Enabled = true;  ROoD_Label = "OoD RTH"; ROoD_Color = Brushes.MediumSeaGreen; ROoD_Opacity = 100; ROoD_Style = LevelLineStyle.Solid; ROoD_Thickness = 2;
				ROoW_Enabled = true;  ROoW_Label = "OoW RTH"; ROoW_Color = Brushes.DarkOrange;     ROoW_Opacity = 100; ROoW_Style = LevelLineStyle.Solid; ROoW_Thickness = 2;
				ROoM_Enabled = true;  ROoM_Label = "OoM RTH"; ROoM_Color = Brushes.MediumPurple;   ROoM_Opacity = 100; ROoM_Style = LevelLineStyle.Solid; ROoM_Thickness = 2;
				ROoM_ManualPrice = 0; ROoM_ManualMonth = Core.Globals.MinDate;

				// ETH defaults: same hue family, dashed, thickness 1, lower default opacity. Label = "{metric} ETH".
				EHOY_Enabled = true;  EHOY_Label = "H ETH";   EHOY_Color = Brushes.IndianRed;      EHOY_Opacity = 70; EHOY_Style = LevelLineStyle.Dash; EHOY_Thickness = 1;
				ELOY_Enabled = true;  ELOY_Label = "L ETH";   ELOY_Color = Brushes.RoyalBlue;      ELOY_Opacity = 70; ELOY_Style = LevelLineStyle.Dash; ELOY_Thickness = 1;
				ECOY_Enabled = true;  ECOY_Label = "COY ETH"; ECOY_Color = Brushes.Goldenrod;      ECOY_Opacity = 70; ECOY_Style = LevelLineStyle.Dash; ECOY_Thickness = 1;
				EOoD_Enabled = true;  EOoD_Label = "OoD ETH"; EOoD_Color = Brushes.MediumSeaGreen; EOoD_Opacity = 70; EOoD_Style = LevelLineStyle.Dash; EOoD_Thickness = 1;
				EOoW_Enabled = true;  EOoW_Label = "OoW ETH"; EOoW_Color = Brushes.DarkOrange;     EOoW_Opacity = 70; EOoW_Style = LevelLineStyle.Dash; EOoW_Thickness = 1;
				EOoM_Enabled = true;  EOoM_Label = "OoM ETH"; EOoM_Color = Brushes.MediumPurple;   EOoM_Opacity = 70; EOoM_Style = LevelLineStyle.Dash; EOoM_Thickness = 1;
				EOoM_ManualPrice = 0; EOoM_ManualMonth = Core.Globals.MinDate;

				// Custom/manual levels: off and price=0 by default (nothing drawn until you
				// type a price in and tick Enabled). StartDate defaults to the MinDate
				// sentinel (= "not set" -> leftmost visible bar); pick a date via the
				// calendar dropdown to anchor the ray there instead. Neutral gray/solid so
				// they read as user-placed, not computed.
				// C1/C2 restored from the "SR Daily" template saved under the old V5 name
				// (templates\Indicator\SessionSRLevelsV5\SR Daily.xml) — these were real
				// configured levels, wiped when the V5->V6 rename orphaned that template.
				C1_Enabled = true;  C1_Label = "MM ATH";      C1_Price = 7946.75; C1_StartDate = Core.Globals.MinDate; C1_Color = Brushes.DeepPink; C1_Opacity = 100; C1_Style = LevelLineStyle.Solid; C1_Thickness = 2;
				C2_Enabled = true;  C2_Label = "ATH 8/13/26"; C2_Price = 7906.25; C2_StartDate = Core.Globals.MinDate; C2_Color = Brushes.Magenta;  C2_Opacity = 100; C2_Style = LevelLineStyle.Dash;  C2_Thickness = 2;
				C3_Enabled = false; C3_Label = "Custom 3"; C3_Price = 0; C3_StartDate = Core.Globals.MinDate; C3_Color = Brushes.Silver; C3_Opacity = 100; C3_Style = LevelLineStyle.Solid; C3_Thickness = 2;
				C4_Enabled = false; C4_Label = "Custom 4"; C4_Price = 0; C4_StartDate = Core.Globals.MinDate; C4_Color = Brushes.Silver; C4_Opacity = 100; C4_Style = LevelLineStyle.Solid; C4_Thickness = 2;
				C5_Enabled = false; C5_Label = "Custom 5"; C5_Price = 0; C5_StartDate = Core.Globals.MinDate; C5_Color = Brushes.Silver; C5_Opacity = 100; C5_Style = LevelLineStyle.Solid; C5_Thickness = 2;
				C6_Enabled = false; C6_Label = "Custom 6"; C6_Price = 0; C6_StartDate = Core.Globals.MinDate; C6_Color = Brushes.Silver; C6_Opacity = 100; C6_Style = LevelLineStyle.Solid; C6_Thickness = 2;
				C7_Enabled = false; C7_Label = "Custom 7"; C7_Price = 0; C7_StartDate = Core.Globals.MinDate; C7_Color = Brushes.Silver; C7_Opacity = 100; C7_Style = LevelLineStyle.Solid; C7_Thickness = 2;
				C8_Enabled = false; C8_Label = "Custom 8"; C8_Price = 0; C8_StartDate = Core.Globals.MinDate; C8_Color = Brushes.Silver; C8_Opacity = 100; C8_Style = LevelLineStyle.Solid; C8_Thickness = 2;
			}
			else if (State == State.Configure)
			{
				// Hidden ETH-hours series: feeds ALL ETH levels so they work regardless of
				// the chart's own Trading Hours template (incl. RTH-only charts).
				_ethSeriesAdded = false;
				if (!string.IsNullOrEmpty(FullTemplateNameHint))
				{
					try
					{
						AddDataSeries(Instrument.FullName,
							new BarsPeriod { BarsPeriodType = BarsPeriodType.Minute, Value = 1 },
							FullTemplateNameHint);
						_ethSeriesAdded = true;
					}
					catch (Exception ex) { Print("SessionSRLevelsV9: could not add ETH data series '" + FullTemplateNameHint + "': " + ex.Message); }
				}
				_ethDayIter = null; _rthMembershipIter = null; _ethLocked = false;
				_ethCurTradingDay = Core.Globals.MinDate; _ethCurWeekStart = Core.Globals.MinDate; _ethCurMonthKey = -1;
				_primaryDayOpenBar = _primaryWeekOpenBar = _primaryMonthOpenBar = -1;
				_curDayHigh = _curDayLow = double.NaN; _curDayStartBar = -1;

				_dayIter = null; _rthHours = null; _rthIter = null; _rthOk = false;
				_curTradingDay = Core.Globals.MinDate; _curWeekStart = Core.Globals.MinDate; _curMonthKey = -1;
				_haveRth = _haveEth = false;
				_rthOpenCapturedToday = false; _weekAwaitingRthOpen = false; _monthAwaitingRthOpen = false;
				_priorRthHigh = _priorRthLow = _priorRthClose = double.NaN;
				_priorEthHigh = _priorEthLow = _priorEthClose = double.NaN;
				_rthOpenToday = _rthOpenThisWeek = _rthOpenThisMonth = double.NaN;
				_ethOpenToday = _ethOpenThisWeek = _ethOpenThisMonth = double.NaN;
				_rthHighBar = _rthLowBar = _rthLastBar = -1;
				_ethHighBar = _ethLowBar = _ethLastBar = -1;
				_priorRthHighStartBar = _priorRthLowStartBar = _priorRthCloseStartBar = -1;
				_priorEthHighStartBar = _priorEthLowStartBar = _priorEthCloseStartBar = -1;
				_rthOpenStartBar  = _ethOpenStartBar  = -1;
				_rthWeekStartBar  = _ethWeekStartBar  = -1;
				_rthMonthStartBar = _ethMonthStartBar = -1;
			}
			else if (State == State.DataLoaded)
			{
				_displayTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
				_dayIter   = new SessionIterator(Bars);

				if (_ethSeriesAdded && BarsArray.Length > 1)
					_ethDayIter = new SessionIterator(BarsArray[1]);

				try
				{
					_rthHours = TradingHours.Get(RthTemplateName);
					if (_rthHours == null) throw new Exception("template not found");
					_rthIter = new SessionIterator(_rthHours);
					_rthMembershipIter = new SessionIterator(_rthHours);
					_rthOk   = true;
				}
				catch (Exception ex)
				{
					Print("SessionSRLevelsV9: WARNING - RTH template '" + RthTemplateName + "' did not resolve (" + ex.Message + "). RTH/ETH split disabled; every bar will be treated as ETH.");
					_rthOk = false;
				}

				if (Bars.TradingHours != null && !string.IsNullOrEmpty(FullTemplateNameHint)
					&& Bars.TradingHours.Name != FullTemplateNameHint)
					Print("SessionSRLevelsV9: NOTE - chart Trading Hours template is '" + Bars.TradingHours.Name
						+ "', expected '" + FullTemplateNameHint + "' (the 23h Globex template). If this chart"
						+ " is RTH-only, ETH levels will have nothing to draw.");
			}
			else if (State == State.Historical)
			{
				if (ChartControl != null && !ctPanelActive)
					ChartControl.Dispatcher.InvokeAsync((Action)CreateWPFControls);
			}
			else if (State == State.Terminated)
			{
				if (ChartControl != null)
					ChartControl.Dispatcher.InvokeAsync((Action)DisposeWPFControls);
			}
		}

		protected override void OnBarUpdate()
		{
			if (BarsInProgress == 1) { HandleEthSeries(); return; }
			if (BarsInProgress != 0) return;
			if (CurrentBar < 0 || !Bars.BarsType.IsIntraday) return;

			DateTime barTime    = Time[0];
			DateTime tradingDay = _dayIter.GetTradingDay(barTime);

			if (tradingDay != _curTradingDay)
			{
				if (_haveRth)
				{
					_priorRthHigh = _rthHigh; _priorRthHighStartBar = _rthHighBar;
					_priorRthLow  = _rthLow;  _priorRthLowStartBar  = _rthLowBar;
					_priorRthClose = _rthCloseLast; _priorRthCloseStartBar = _rthLastBar;
				}

				_curTradingDay        = tradingDay;
				_haveRth              = false;
				_rthOpenCapturedToday = false;
				_primaryDayOpenBar    = CurrentBar;   // first bar of this chart's trading day = its session open
				_curDayHigh = High[0]; _curDayLow = Low[0]; _curDayStartBar = CurrentBar;   // reset current-day H/L

				DateTime wkStart = MondayOf(tradingDay);
				if (wkStart != _curWeekStart)
				{
					_curWeekStart         = wkStart;
					_weekAwaitingRthOpen  = true;
					_primaryWeekOpenBar   = CurrentBar;   // first bar of this chart's week = its week's session open
				}
				int monthKey = tradingDay.Year * 12 + tradingDay.Month;
				if (monthKey != _curMonthKey)
				{
					_curMonthKey           = monthKey;
					_monthAwaitingRthOpen  = true;
					_primaryMonthOpenBar   = CurrentBar;  // first bar of this chart's month
				}

				if (_rthOk)
				{
					DateTime tRth = ConvertToRthTz(barTime);
					if (_rthIter.IsNewSession(tRth, true))
						_rthIter.GetNextSession(tRth, true);
					_rthSessBegin = _rthIter.ActualSessionBegin;
					_rthSessEnd   = _rthIter.ActualSessionEnd;
				}
			}

			// Current-day H/L across every bar of the trading day (independent of RTH/ETH).
			if (!double.IsNaN(_curDayHigh) && High[0] > _curDayHigh) _curDayHigh = High[0];
			if (!double.IsNaN(_curDayLow)  && Low[0]  < _curDayLow)  _curDayLow  = Low[0];

			bool isRth = false;
			if (_rthOk && _rthSessBegin != Core.Globals.MinDate)
			{
				DateTime tRth = ConvertToRthTz(barTime);
				isRth = tRth >= _rthSessBegin && tRth <= _rthSessEnd;
			}

			if (isRth)
			{
				if (!_haveRth) { _rthHigh = High[0]; _rthHighBar = CurrentBar; _rthLow = Low[0]; _rthLowBar = CurrentBar; _haveRth = true; }
				else
				{
					if (High[0] > _rthHigh) { _rthHigh = High[0]; _rthHighBar = CurrentBar; }
					if (Low[0]  < _rthLow)  { _rthLow  = Low[0];  _rthLowBar  = CurrentBar; }
				}
				_rthCloseLast = Close[0];
				_rthLastBar   = CurrentBar;

				if (!_rthOpenCapturedToday)
				{
					_rthOpenToday         = Open[0];
					_rthOpenStartBar      = CurrentBar;
					_rthOpenCapturedToday = true;
					if (_weekAwaitingRthOpen)  { _rthOpenThisWeek  = Open[0]; _rthWeekStartBar  = CurrentBar; _weekAwaitingRthOpen  = false; }
					if (_monthAwaitingRthOpen) { _rthOpenThisMonth = Open[0]; _rthMonthStartBar = CurrentBar; _monthAwaitingRthOpen = false; }
				}
			}
		}

		// ETH levels come from the hidden ETH-hours series (BarsArray[1]) — so they work
		// on any chart, including RTH-only. The ETH template is 23h (17:00->16:00), which
		// INCLUDES RTH — so the ETH H/L is the OVERNIGHT range only: it accumulates from the
		// session open up to the RTH open, then LOCKS (stays frozen through RTH and the
		// post-RTH tail until the next overnight session begins). ETH lines render full
		// visible width since an overnight extreme has no corresponding primary (RTH) bar.
		private void HandleEthSeries()
		{
			if (!_ethSeriesAdded || _ethDayIter == null || CurrentBars[1] < 0) return;

			DateTime et  = Times[1][0];
			DateTime etd = _ethDayIter.GetTradingDay(et);

			if (etd != _ethCurTradingDay)
			{
				if (_haveEth)
				{
					_priorEthHigh  = _ethHigh;
					_priorEthLow   = _ethLow;
					_priorEthClose = _ethCloseLast;
				}
				_ethCurTradingDay = etd;
				_haveEth          = false;
				_ethLocked        = false;   // new overnight session — accumulate again until RTH open
				_ethOpenToday     = Opens[1][0];

				DateTime wk = MondayOf(etd);
				if (wk != _ethCurWeekStart) { _ethCurWeekStart = wk; _ethOpenThisWeek = Opens[1][0]; }
				int mk = etd.Year * 12 + etd.Month;
				if (mk != _ethCurMonthKey)  { _ethCurMonthKey = mk; _ethOpenThisMonth = Opens[1][0]; }
			}

			// Once this ETH bar is inside the RTH window, lock the overnight H/L for the rest
			// of the ETH session (stays locked through RTH + the 15:15-16:00 post-close tail).
			if (!_ethLocked && _rthOk && _rthMembershipIter != null)
			{
				DateTime tRth = ConvertToRthTz(et);
				if (_rthMembershipIter.IsNewSession(tRth, true))
					_rthMembershipIter.GetNextSession(tRth, true);
				if (tRth >= _rthMembershipIter.ActualSessionBegin && tRth <= _rthMembershipIter.ActualSessionEnd)
					_ethLocked = true;
			}

			if (!_ethLocked)
			{
				if (!_haveEth) { _ethHigh = Highs[1][0]; _ethLow = Lows[1][0]; _haveEth = true; }
				else
				{
					if (Highs[1][0] > _ethHigh) _ethHigh = Highs[1][0];
					if (Lows[1][0]  < _ethLow)  _ethLow  = Lows[1][0];
				}
			}
			_ethCloseLast = Closes[1][0];
		}

		private DateTime ConvertToRthTz(DateTime t)
		{
			if (_rthHours == null) return t;
			TimeZoneInfo rthTz = _rthHours.TimeZoneInfo;
			return rthTz.Equals(_displayTz) ? t : TimeZoneInfo.ConvertTime(t, _displayTz, rthTz);
		}

		private static DateTime MondayOf(DateTime d)
		{
			int diff = (7 + (d.DayOfWeek - DayOfWeek.Monday)) % 7;
			return d.Date.AddDays(-diff);
		}

		// year*12+month key for a manual-OoM month; <=MinDate (unset) returns a non-matching -1.
		private static int MonthKeyOf(DateTime d)
		{
			return d <= Core.Globals.MinDate ? -1 : d.Year * 12 + d.Month;
		}

		// First VISIBLE primary bar of the current day(0)/week(1)/month(2), resolved straight
		// from the chart bars' calendar dates — NO SessionIterator (which is unreliable here
		// because the primary OnBarUpdate loop, which normally advances it, is skipped on a
		// daily chart). Scans the visible bars forward from the left edge and returns the
		// first one whose date falls in the same period as the last visible bar. Works on
		// any chart period: intraday RTH -> that day's session-open bar (RTH charts have no
		// overnight bars, so the day's first bar IS the RTH open); daily -> the period's
		// first daily bar.
		private int FirstBarOfCurrentPeriod(int period)
		{
			if (ChartBars == null) return 0;
			var bars = ChartBars.Bars;
			int from = Math.Max(0, ChartBars.FromIndex);
			int to   = ChartBars.ToIndex;
			if (bars == null || to < from) return from;

			DateTime refD = bars.GetTime(to).Date;
			for (int i = from; i <= to; i++)
			{
				DateTime d = bars.GetTime(i).Date;
				bool same = period == 2 ? (d.Year == refD.Year && d.Month == refD.Month)
						  : period == 1 ? (MondayOf(d) == MondayOf(refD))
						  :               (d == refD);
				if (same) return i;
			}
			return to;
		}

		// Current day's High/Low from the ACTUAL bars (not the visible window) so it stays
		// locked when you scroll/zoom. Intraday: the values tracked per-bar in OnBarUpdate.
		// Daily (OnBarUpdate skipped): the latest daily bar's own High/Low (one bar = one day).
		private void CurrentDayHighLow(out double hi, out double lo, out int startBar)
		{
			hi = double.NaN; lo = double.NaN; startBar = -1;
			if (BarsArray == null || BarsArray.Length == 0) return;
			var b = BarsArray[0];

			if (b.BarsType.IsIntraday)
			{
				hi = _curDayHigh; lo = _curDayLow; startBar = _curDayStartBar;
				return;
			}
			int last = b.Count - 1;
			if (last < 0) return;
			hi = b.GetHigh(last); lo = b.GetLow(last); startBar = last;
		}

		// ══════════════════════ Expected-move bands ══════════════════════
		// Throttled (≤ once/5s) re-read of the repo files + recompute of both bands.
		private void ReloadEm()
		{
			DateTime now = DateTime.UtcNow;
			if ((now - _emLastRead).TotalSeconds < 5) return;
			_emLastRead = now;

			// ---- VIX-formula band: prior RTH close ± close*(VIX/100)/sqrt(252)*sigma ----
			double vix = EmManualVix > 0 ? EmManualVix : ReadLastVixClose();
			_vixUsed = vix;
			double rf = _priorRthClose;
			if (!double.IsNaN(rf) && rf > 0 && !double.IsNaN(vix) && vix > 0)
			{
				double hw = rf * (vix / 100.0) / SQRT252 * Math.Max(0.0, EmSigma);
				_emvMax = rf + hw; _emvMin = rf - hw;
			}
			else { _emvMax = _emvMin = double.NaN; }

			// ---- gexlog published band (emUpper/emLower from today's morning / prior evening brief) ----
			double up, lo2;
			if (ReadGexlogBand(out up, out lo2)) { _emgMax = up; _emgMin = lo2; }
			else { _emgMax = _emgMin = double.NaN; }
		}

		private double ReadLastVixClose()
		{
			try
			{
				if (!File.Exists(VixCsvPath)) return double.NaN;
				string[] lines = File.ReadAllLines(VixCsvPath);
				for (int i = lines.Length - 1; i >= 1; i--)   // skip header (row 0)
				{
					string ln = lines[i];
					if (string.IsNullOrWhiteSpace(ln)) continue;
					string[] p = ln.Split(',');
					double v;
					if (p.Length >= 1 && double.TryParse(p[p.Length - 1].Trim(),
							System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out v))
						return v;
				}
			}
			catch { }
			return double.NaN;
		}

		private bool ReadGexlogBand(out double up, out double lo)
		{
			up = double.NaN; lo = double.NaN;
			try
			{
				if (string.IsNullOrWhiteSpace(GexlogRawDir) || !Directory.Exists(GexlogRawDir)) return false;

				// Resolve the brief for the current trading day: {date}_morning, else {date-1}_evening,
				// else the newest brief file in the dir.
				DateTime refDate = _curTradingDay > Core.Globals.MinDate ? _curTradingDay : DateTime.Today;
				string path = Path.Combine(GexlogRawDir, refDate.ToString("yyyy-MM-dd") + "_morning.json");
				if (!File.Exists(path))
					path = Path.Combine(GexlogRawDir, refDate.AddDays(-1).ToString("yyyy-MM-dd") + "_evening.json");
				if (!File.Exists(path))
				{
					string newest = null; DateTime newestT = DateTime.MinValue;
					foreach (string f in Directory.GetFiles(GexlogRawDir, "*.json"))
					{
						DateTime t = File.GetLastWriteTimeUtc(f);
						if (t > newestT) { newestT = t; newest = f; }
					}
					path = newest;
				}
				if (path == null || !File.Exists(path)) return false;

				string json = File.ReadAllText(path);
				up = JsonNum(json, "emUpper");
				lo = JsonNum(json, "emLower");
				return !double.IsNaN(up) && !double.IsNaN(lo);
			}
			catch { return false; }
		}

		// Minimal JSON number extractor for a unique key (emUpper/emLower are unique in the brief).
		private static double JsonNum(string json, string key)
		{
			int i = json.IndexOf("\"" + key + "\"");
			if (i < 0) return double.NaN;
			i = json.IndexOf(':', i);
			if (i < 0) return double.NaN;
			i++;
			while (i < json.Length && char.IsWhiteSpace(json[i])) i++;
			int j = i;
			while (j < json.Length)
			{
				char c = json[j];
				if (char.IsDigit(c) || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E') j++;
				else break;
			}
			double v;
			if (j > i && double.TryParse(json.Substring(i, j - i),
					System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out v))
				return v;
			return double.NaN;
		}

		// ══════════════════════════ Rendering ════════════════════════════
		// Lines are RAYS: they start at the bar where that level's value was actually
		// established and run right to the current bar — never the full panel width,
		// never past "now" (same idea as PADayTradingSR). Labels sit just past that
		// right end, not pinned to the chart's physical right edge.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;

			ReloadEm();

			var defs = BuildLevelDefs();
			if (defs.Count == 0) return;

			float panelLeft = (float)ChartPanel.X;
			int lastIdx = ChartBars.ToIndex;
			if (lastIdx < 0) return;
			float lineEndX = chartControl.GetXByBarIndex(ChartBars, lastIdx + ExtendBarsRight);

			var labels = new List<LabelInfo>();
			foreach (LevelDef d in defs)
			{
				if (!d.enabled || double.IsNaN(d.price) || d.startBarIdx < 0) continue;

				int startIdx = Math.Max(d.startBarIdx, ChartBars.FromIndex);
				float xStart = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, startIdx));

				// Optional per-level right cap (e.g. OoD RTH stops at its RTH session end
				// instead of spilling into the following ETH session). The cap still honors
				// ExtendBarsRight — the line runs ExtendBarsRight bars past the session end,
				// never beyond the global right edge (lineEndX).
				float xEnd = lineEndX;
				if (d.endBarIdx >= 0)
				{
					float xe = chartControl.GetXByBarIndex(ChartBars, d.endBarIdx + ExtendBarsRight);
					if (xe < xEnd) xEnd = xe;
				}
				if (xStart >= xEnd) continue;

				float a = Math.Max(0f, Math.Min(1f, d.opacity / 100f));
				var sdxBrush = new D2DSolidColorBrush(RenderTarget,
					new Color4(d.color.R / 255f, d.color.G / 255f, d.color.B / 255f, a));

				float y = chartScale.GetYByValue(d.price);
				DrawStyledLine(xStart, xEnd, y, sdxBrush, d.thickness, d.style);

				string text = (_priceVisibleSet ? _priceVisible : ShowPriceInLabel) ? d.label + " " + F(d.price) : d.label;
				bool capped = xEnd < lineEndX - 0.5f;   // line stops before the right edge -> label sits at the cap
				labels.Add(new LabelInfo { y = y, trueY = y, text = text, brush = sdxBrush, col = d.col, inline = capped, xInline = xEnd + 6f });
			}

			if (_labelsVisible) DrawLabels(labels, lineEndX + 6f);

			foreach (LabelInfo li in labels) li.brush.Dispose();
		}

		private List<LevelDef> BuildLevelDefs()
		{
			var list = new List<LevelDef>(12);

			// Current-day running High/Low — from the chart's own bars, works on any period.
			// Independent of the RTH/ETH toggles; gated only by their own Enabled.
			if (CDH_Enabled || CDL_Enabled)
			{
				double cdHi, cdLo; int cdStart;
				CurrentDayHighLow(out cdHi, out cdLo, out cdStart);
				Add(list, CDH_Enabled, CDH_Label, cdHi, CDH_Color, CDH_Opacity, CDH_Style, CDH_Thickness, 0, cdStart);
				Add(list, CDL_Enabled, CDL_Label, cdLo, CDL_Color, CDL_Opacity, CDL_Style, CDL_Thickness, 0, cdStart);
			}

			// Expected-move 1-day bands (two methods, anchored at the current day's open bar).
			{
				int fb = ChartBars != null ? ChartBars.FromIndex : 0;
				int emStart;
				if (BarsArray != null && BarsArray.Length > 0 && BarsArray[0].BarsType.IsIntraday)
					emStart = _primaryDayOpenBar >= 0 ? _primaryDayOpenBar : fb;
				else
					emStart = FirstBarOfCurrentPeriod(0);
				Add(list, EMV_Max_Enabled, EMV_Max_Label, _emvMax, EMV_Max_Color, EMV_Max_Opacity, EMV_Max_Style, EMV_Max_Thickness, 0, emStart);
				Add(list, EMV_Min_Enabled, EMV_Min_Label, _emvMin, EMV_Min_Color, EMV_Min_Opacity, EMV_Min_Style, EMV_Min_Thickness, 0, emStart);
				Add(list, EMG_Max_Enabled, EMG_Max_Label, _emgMax, EMG_Max_Color, EMG_Max_Opacity, EMG_Max_Style, EMG_Max_Thickness, 0, emStart);
				Add(list, EMG_Min_Enabled, EMG_Min_Label, _emgMin, EMG_Min_Color, EMG_Min_Opacity, EMG_Min_Style, EMG_Min_Thickness, 0, emStart);
			}

			if (_rthVisible)
			{
				Add(list, RHOY_Enabled, RHOY_Label, _priorRthHigh,    RHOY_Color, RHOY_Opacity, RHOY_Style, RHOY_Thickness, 0, _priorRthHighStartBar);
				Add(list, RLOY_Enabled, RLOY_Label, _priorRthLow,     RLOY_Color, RLOY_Opacity, RLOY_Style, RLOY_Thickness, 0, _priorRthLowStartBar);
				Add(list, RCOY_Enabled, RCOY_Label, _priorRthClose,   RCOY_Color, RCOY_Opacity, RCOY_Style, RCOY_Thickness, 0, _priorRthCloseStartBar);
				// OoD RTH stops at the end of its RTH session (_rthLastBar) — doesn't spill into the following ETH session.
				Add(list, ROoD_Enabled, ROoD_Label, _rthOpenToday,    ROoD_Color, ROoD_Opacity, ROoD_Style, ROoD_Thickness, 0, _rthOpenStartBar, _rthLastBar);
				Add(list, ROoW_Enabled, ROoW_Label, _rthOpenThisWeek, ROoW_Color, ROoW_Opacity, ROoW_Style, ROoW_Thickness, 0, _rthWeekStartBar);
				// RTH OoM: manual override wins when a price is set and its month == the current month
				double rOoM = _rthOpenThisMonth; int rOoMBar = _rthMonthStartBar;
				if (ROoM_ManualPrice != 0 && MonthKeyOf(ROoM_ManualMonth) == _curMonthKey)
				{ rOoM = ROoM_ManualPrice; rOoMBar = ChartBars.FromIndex; }
				Add(list, ROoM_Enabled, ROoM_Label, rOoM, ROoM_Color, ROoM_Opacity, ROoM_Style, ROoM_Thickness, 0, rOoMBar);
			}
			if (_ethVisible)
			{
				// ETH start bars: on an INTRADAY chart use the primary chart's own session-open
				// bars (RTH open on an RTH chart, ETH/Globex 17:00 open on an ETH chart) tracked
				// in OnBarUpdate — so ETH lines begin at the session open, not calendar midnight.
				// On a DAILY chart that primary loop is skipped, so fall back to the calendar
				// date walk (the day/week/month's first daily bar).
				int ethDayStart, ethWeekStart, ethMonthStart;
				if (BarsArray != null && BarsArray.Length > 0 && BarsArray[0].BarsType.IsIntraday)
				{
					int fb = ChartBars != null ? ChartBars.FromIndex : 0;
					ethDayStart   = _primaryDayOpenBar   >= 0 ? _primaryDayOpenBar   : fb;
					ethWeekStart  = _primaryWeekOpenBar  >= 0 ? _primaryWeekOpenBar  : fb;
					ethMonthStart = _primaryMonthOpenBar >= 0 ? _primaryMonthOpenBar : fb;
				}
				else
				{
					ethDayStart   = FirstBarOfCurrentPeriod(0);
					ethWeekStart  = FirstBarOfCurrentPeriod(1);
					ethMonthStart = FirstBarOfCurrentPeriod(2);
				}
				// col 0 = same label column as the RTH levels (de-collision merges them).
				Add(list, EHOY_Enabled, EHOY_Label, _ethHigh,          EHOY_Color, EHOY_Opacity, EHOY_Style, EHOY_Thickness, 0, ethDayStart);
				Add(list, ELOY_Enabled, ELOY_Label, _ethLow,           ELOY_Color, ELOY_Opacity, ELOY_Style, ELOY_Thickness, 0, ethDayStart);
				Add(list, ECOY_Enabled, ECOY_Label, _priorEthClose,    ECOY_Color, ECOY_Opacity, ECOY_Style, ECOY_Thickness, 0, ethDayStart);
				Add(list, EOoD_Enabled, EOoD_Label, _ethOpenToday,     EOoD_Color, EOoD_Opacity, EOoD_Style, EOoD_Thickness, 0, ethDayStart);
				Add(list, EOoW_Enabled, EOoW_Label, _ethOpenThisWeek,  EOoW_Color, EOoW_Opacity, EOoW_Style, EOoW_Thickness, 0, ethWeekStart);
				// ETH OoM: manual override wins when a price is set and its month == the current ETH month
				double eOoM = _ethOpenThisMonth;
				if (EOoM_ManualPrice != 0 && MonthKeyOf(EOoM_ManualMonth) == _ethCurMonthKey)
					eOoM = EOoM_ManualPrice;
				Add(list, EOoM_Enabled, EOoM_Label, eOoM, EOoM_Color, EOoM_Opacity, EOoM_Style, EOoM_Thickness, 0, ethMonthStart);
			}

			// Custom/manual levels: no "session" origin bar to anchor to, so the start date
			// is a user-picked calendar date (StartDate property -> a calendar dropdown in
			// the Properties grid). Left unset (Core.Globals.MinDate sentinel) -> falls back
			// to the leftmost visible bar, same as before.
			Add(list, C1_Enabled && C1_Price != 0, C1_Label, C1_Price, C1_Color, C1_Opacity, C1_Style, C1_Thickness, 0, ResolveCustomStartBar(C1_StartDate));
			Add(list, C2_Enabled && C2_Price != 0, C2_Label, C2_Price, C2_Color, C2_Opacity, C2_Style, C2_Thickness, 0, ResolveCustomStartBar(C2_StartDate));
			Add(list, C3_Enabled && C3_Price != 0, C3_Label, C3_Price, C3_Color, C3_Opacity, C3_Style, C3_Thickness, 0, ResolveCustomStartBar(C3_StartDate));
			Add(list, C4_Enabled && C4_Price != 0, C4_Label, C4_Price, C4_Color, C4_Opacity, C4_Style, C4_Thickness, 0, ResolveCustomStartBar(C4_StartDate));
			Add(list, C5_Enabled && C5_Price != 0, C5_Label, C5_Price, C5_Color, C5_Opacity, C5_Style, C5_Thickness, 0, ResolveCustomStartBar(C5_StartDate));
			Add(list, C6_Enabled && C6_Price != 0, C6_Label, C6_Price, C6_Color, C6_Opacity, C6_Style, C6_Thickness, 0, ResolveCustomStartBar(C6_StartDate));
			Add(list, C7_Enabled && C7_Price != 0, C7_Label, C7_Price, C7_Color, C7_Opacity, C7_Style, C7_Thickness, 0, ResolveCustomStartBar(C7_StartDate));
			Add(list, C8_Enabled && C8_Price != 0, C8_Label, C8_Price, C8_Color, C8_Opacity, C8_Style, C8_Thickness, 0, ResolveCustomStartBar(C8_StartDate));

			return list;
		}

		// StartDate unset (still the MinDate sentinel) -> leftmost visible bar (old
		// behavior). Otherwise resolve to the bar index at/after that calendar date;
		// Bars.GetBar(-1) (date before all loaded history, or not found) -> also falls
		// back to leftmost visible rather than hiding the level entirely.
		private int ResolveCustomStartBar(DateTime startDate)
		{
			if (startDate <= Core.Globals.MinDate) return ChartBars.FromIndex;
			int idx = Bars.GetBar(startDate);
			return idx >= 0 ? idx : ChartBars.FromIndex;
		}

		private static void Add(List<LevelDef> list, bool enabled, string label, double price,
			WMBrush brush, int opacity, LevelLineStyle style, int thickness, int col, int startBarIdx, int endBarIdx = -1)
		{
			var scb = brush as WMSolidColorBrush;
			list.Add(new LevelDef
			{
				enabled = enabled, label = label, price = price,
				color = scb != null ? scb.Color : Colors.Gray,
				opacity = opacity, style = style, thickness = thickness, col = col, startBarIdx = startBarIdx, endBarIdx = endBarIdx
			});
		}

		// Dependency-free dashing (no Direct2D1 StrokeStyle/Factory needed) — segments the
		// line into on/off chunks left-to-right across the panel.
		private void DrawStyledLine(float xL, float xR, float y, SharpDX.Direct2D1.Brush br, float thickness, LevelLineStyle style)
		{
			if (style == LevelLineStyle.Solid)
			{
				RenderTarget.DrawLine(new Vector2(xL, y), new Vector2(xR, y), br, thickness);
				return;
			}
			float[] pattern = style == LevelLineStyle.Dot      ? new float[] { 2f, 4f }
							: style == LevelLineStyle.DashDot   ? new float[] { 8f, 4f, 2f, 4f }
							:                                      new float[] { 8f, 5f };   // Dash
			float x = xL;
			int pi = 0;
			while (x < xR)
			{
				float seg = Math.Min(pattern[pi % pattern.Length], xR - x);
				if (pi % 2 == 0) RenderTarget.DrawLine(new Vector2(x, y), new Vector2(x + seg, y), br, thickness);
				x += seg;
				pi++;
			}
		}

		private class LabelInfo { public float y; public float trueY; public string text; public D2DSolidColorBrush brush; public int col; public bool inline; public float xInline; }

		// Two columns (RTH / ETH), anchored just past where the lines end (the current
		// bar), de-collided top-to-bottom with leader lines when a label had to be
		// nudged off its true price — same pattern as WyckoffVPLevels.
		private void DrawLabels(List<LabelInfo> labels, float baseX)
		{
			if (labels.Count == 0) return;
			float colW = LabelFontSize * 6.5f;
			float gap  = LabelFontSize + 4f;
			float textH = LabelFontSize + 6f;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);

			// Inline labels (capped lines, e.g. OoD RTH) sit at the line's end, centered on it.
			foreach (LabelInfo li in labels)
				if (li.inline)
					RenderTarget.DrawText(li.text, tf, new RectangleF(li.xInline, li.trueY - textH / 2f, colW, textH), li.brush);

			for (int c = 0; c <= 2; c++)   // 0=RTH, 1=ETH, 2=Custom (right-edge columns)
			{
				var col = new List<LabelInfo>();
				foreach (LabelInfo li in labels) if (!li.inline && li.col == c) col.Add(li);
				if (col.Count == 0) continue;
				col.Sort(delegate (LabelInfo a, LabelInfo b) { return a.y.CompareTo(b.y); });
				for (int i = 1; i < col.Count; i++)
					if (col[i].y < col[i - 1].y + gap) col[i].y = col[i - 1].y + gap;
				float x = baseX + c * colW;
				foreach (LabelInfo li in col)
				{
					if (Math.Abs(li.y - li.trueY) > 1.5f)
						RenderTarget.DrawLine(new Vector2(x - 6f, li.trueY), new Vector2(x - 1f, li.y), li.brush, 0.6f);
					// Vertically CENTER the text on the line's y, not top-aligned below it.
					RenderTarget.DrawText(li.text, tf, new RectangleF(x, li.y - textH / 2f, colW, textH), li.brush);
				}
			}
			tf.Dispose();
		}

		private static string F(double p) { return p.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture); }

		// ══════════════════════ Chart Trader panel ══════════════════════
		private void CreateWPFControls()
		{
			if (ctPanelActive) return;
			try
			{
				var win = Window.GetWindow(ChartControl.Parent) as NinjaTrader.Gui.Chart.Chart;
				if (win == null) { Print("SessionSRLevelsV9: chart window not found"); return; }
				var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
				if (chartTrader == null) { Print("SessionSRLevelsV9: ChartTrader not found (is Chart Trader shown?)"); return; }
				var outerGrid = chartTrader.Content as Grid;
				if (outerGrid == null) return;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { ctButtonsGrid = g; break; }
				}
				if (ctButtonsGrid == null) { Print("SessionSRLevelsV9: button grid not found"); return; }

				ctBaseRowCount = ctButtonsGrid.RowDefinitions.Count;
				Style s = Application.Current.TryFindResource("Button") as Style;

				btnRth = MakeBtn(s, "RTH LEVELS", "Toggle RTH session levels", _rthVisible ? ColorOn : ColorOff);
				btnRth.Click += (o, e) => { _rthVisible = !_rthVisible; SetBtn(btnRth, _rthVisible ? ColorOn : ColorOff); ChartControl.InvalidateVisual(); };

				btnEth = MakeBtn(s, "ETH LEVELS", "Toggle ETH session levels", _ethVisible ? ColorOn : ColorOff);
				btnEth.Click += (o, e) => { _ethVisible = !_ethVisible; SetBtn(btnEth, _ethVisible ? ColorOn : ColorOff); ChartControl.InvalidateVisual(); };

				AddHalfRow(ctButtonsGrid, ctBaseRowCount, btnRth, btnEth);

				btnLabels = MakeBtn(s, "LABELS", "Toggle level labels on/off", _labelsVisible ? ColorOn : ColorOff);
				btnLabels.Click += (o, e) => { _labelsVisible = !_labelsVisible; SetBtn(btnLabels, _labelsVisible ? ColorOn : ColorOff); ChartControl.InvalidateVisual(); };

				if (!_priceVisibleSet) { _priceVisible = ShowPriceInLabel; _priceVisibleSet = true; }
				btnPrice = MakeBtn(s, "PRICE", "Toggle the price value in the labels", _priceVisible ? ColorOn : ColorOff);
				btnPrice.Click += (o, e) => { _priceVisible = !_priceVisible; SetBtn(btnPrice, _priceVisible ? ColorOn : ColorOff); ChartControl.InvalidateVisual(); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + 1, btnLabels, btnPrice);

				ctPanelActive = true;
			}
			catch (Exception ex) { Print("SessionSRLevelsV9 CreateWPFControls: " + ex.Message); }
		}

		private void DisposeWPFControls()
		{
			try
			{
				if (!ctPanelActive || ctButtonsGrid == null) return;
				int baseRows = Math.Max(0, ctBaseRowCount);
				while (ctButtonsGrid.Children.Count > baseRows)
					ctButtonsGrid.Children.RemoveAt(ctButtonsGrid.Children.Count - 1);
				while (ctButtonsGrid.RowDefinitions.Count > baseRows)
					ctButtonsGrid.RowDefinitions.RemoveAt(ctButtonsGrid.RowDefinitions.Count - 1);
				btnRth = btnEth = btnLabels = btnPrice = null;
				ctPanelActive = false;
			}
			catch (Exception ex) { Print("SessionSRLevelsV9 DisposeWPFControls: " + ex.Message); }
		}

		private Button MakeBtn(Style s, string label, string tip, WMColor bg)
		{
			return new Button() { Content = label, Style = s, Height = 34, Margin = new Thickness(1),
				FontSize = 11, FontWeight = FontWeights.Bold, ToolTip = tip,
				Background = new WMSolidColorBrush(bg), Foreground = Brushes.White };
		}

		private void SetBtn(Button btn, WMColor bg)
		{
			if (btn == null || ChartControl == null) return;
			ChartControl.Dispatcher.InvokeAsync((Action)(() => { if (btn != null) btn.Background = new WMSolidColorBrush(bg); }));
		}

		private void AddHalfRow(Grid grid, int row, Button left, Button right)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
			var g = new Grid() { Margin = new Thickness(0) };
			g.ColumnDefinitions.Add(new ColumnDefinition());
			g.ColumnDefinitions.Add(new ColumnDefinition());
			Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
			g.Children.Add(left); g.Children.Add(right);
			Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
			grid.Children.Add(g);
		}

		private void AddFullRow(Grid grid, int row, Button btn)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
			Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
			grid.Children.Add(btn);
		}

		#region Properties

		[Display(Name = "RTH template name", Order = 0, GroupName = "00 Session Templates",
			Description = "NT8 Trading Hours template used for the RTH window (begin/end + holidays/half-days).")]
		public string RthTemplateName { get; set; }

		[Display(Name = "Expected chart template (informational)", Order = 1, GroupName = "00 Session Templates",
			Description = "Just a sanity check: Print()s a warning at DataLoaded if the chart's own Trading Hours template name differs (expects the 23h Globex template so ETH bars actually exist).")]
		public string FullTemplateNameHint { get; set; }

		[Range(6, 24)]
		[Display(Name = "Label font size", Order = 2, GroupName = "01 Display")]
		public int LabelFontSize { get; set; }

		[Display(Name = "Show price in label", Order = 3, GroupName = "01 Display",
			Description = "Off = just the label text (e.g. \"COY RTH\"), no price value appended.")]
		public bool ShowPriceInLabel { get; set; }

		[Range(0, 500)]
		[Display(Name = "Extend lines right (bars)", Order = 4, GroupName = "01 Display",
			Description = "How many bars past the current bar the lines/labels are drawn out to.")]
		public int ExtendBarsRight { get; set; }

		// ---- Current Day High ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01A Current Day - High")] public bool CDH_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01A Current Day - High")] public string CDH_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01A Current Day - High")] public WMBrush CDH_Color { get; set; }
		[Browsable(false)] public string CDH_ColorSerialize { get { return Serialize.BrushToString(CDH_Color); } set { CDH_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01A Current Day - High")] public int CDH_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01A Current Day - High")] public LevelLineStyle CDH_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01A Current Day - High")] public int CDH_Thickness { get; set; }

		// ---- Current Day Low ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01B Current Day - Low")] public bool CDL_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01B Current Day - Low")] public string CDL_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01B Current Day - Low")] public WMBrush CDL_Color { get; set; }
		[Browsable(false)] public string CDL_ColorSerialize { get { return Serialize.BrushToString(CDL_Color); } set { CDL_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01B Current Day - Low")] public int CDL_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01B Current Day - Low")] public LevelLineStyle CDL_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01B Current Day - Low")] public int CDL_Thickness { get; set; }

		// ---- Expected Move (settings) ----
		[Display(Name = "VIX CSV path", Order = 0, GroupName = "01C Expected Move (settings)", Description = "File the VIX-method reads the latest close from.")] public string VixCsvPath { get; set; }
		[Display(Name = "gexlog raw dir", Order = 1, GroupName = "01C Expected Move (settings)", Description = "Folder with the dated gexlog brief JSON files (reads {date}_morning, else {date-1}_evening).")] public string GexlogRawDir { get; set; }
		[Display(Name = "Manual VIX (0 = auto)", Order = 2, GroupName = "01C Expected Move (settings)", Description = "Override the VIX used by the VIX-method; 0 = read latest close from the CSV.")] public double EmManualVix { get; set; }
		[Range(0.1, 5.0)] [Display(Name = "Sigma multiplier", Order = 3, GroupName = "01C Expected Move (settings)", Description = "1.0 = ~68% band; 2.0 = ~95%. Applies to the VIX method.")] public double EmSigma { get; set; }

		// ---- 1D Max (VIX) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01D 1D Max (VIX formula)")] public bool EMV_Max_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01D 1D Max (VIX formula)")] public string EMV_Max_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01D 1D Max (VIX formula)")] public WMBrush EMV_Max_Color { get; set; }
		[Browsable(false)] public string EMV_Max_ColorSerialize { get { return Serialize.BrushToString(EMV_Max_Color); } set { EMV_Max_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01D 1D Max (VIX formula)")] public int EMV_Max_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01D 1D Max (VIX formula)")] public LevelLineStyle EMV_Max_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01D 1D Max (VIX formula)")] public int EMV_Max_Thickness { get; set; }

		// ---- 1D Min (VIX) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01E 1D Min (VIX formula)")] public bool EMV_Min_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01E 1D Min (VIX formula)")] public string EMV_Min_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01E 1D Min (VIX formula)")] public WMBrush EMV_Min_Color { get; set; }
		[Browsable(false)] public string EMV_Min_ColorSerialize { get { return Serialize.BrushToString(EMV_Min_Color); } set { EMV_Min_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01E 1D Min (VIX formula)")] public int EMV_Min_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01E 1D Min (VIX formula)")] public LevelLineStyle EMV_Min_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01E 1D Min (VIX formula)")] public int EMV_Min_Thickness { get; set; }

		// ---- 1D Max (gexlog) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01F 1D Max (gexlog brief)")] public bool EMG_Max_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01F 1D Max (gexlog brief)")] public string EMG_Max_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01F 1D Max (gexlog brief)")] public WMBrush EMG_Max_Color { get; set; }
		[Browsable(false)] public string EMG_Max_ColorSerialize { get { return Serialize.BrushToString(EMG_Max_Color); } set { EMG_Max_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01F 1D Max (gexlog brief)")] public int EMG_Max_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01F 1D Max (gexlog brief)")] public LevelLineStyle EMG_Max_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01F 1D Max (gexlog brief)")] public int EMG_Max_Thickness { get; set; }

		// ---- 1D Min (gexlog) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01G 1D Min (gexlog brief)")] public bool EMG_Min_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01G 1D Min (gexlog brief)")] public string EMG_Min_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01G 1D Min (gexlog brief)")] public WMBrush EMG_Min_Color { get; set; }
		[Browsable(false)] public string EMG_Min_ColorSerialize { get { return Serialize.BrushToString(EMG_Min_Color); } set { EMG_Min_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01G 1D Min (gexlog brief)")] public int EMG_Min_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01G 1D Min (gexlog brief)")] public LevelLineStyle EMG_Min_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01G 1D Min (gexlog brief)")] public int EMG_Min_Thickness { get; set; }

		// ---- RTH HOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "02 RTH - HOY (prior RTH high)")] public bool RHOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "02 RTH - HOY (prior RTH high)")] public string RHOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "02 RTH - HOY (prior RTH high)")] public WMBrush RHOY_Color { get; set; }
		[Browsable(false)] public string RHOY_ColorSerialize { get { return Serialize.BrushToString(RHOY_Color); } set { RHOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "02 RTH - HOY (prior RTH high)")] public int RHOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "02 RTH - HOY (prior RTH high)")] public LevelLineStyle RHOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "02 RTH - HOY (prior RTH high)")] public int RHOY_Thickness { get; set; }

		// ---- RTH LOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "03 RTH - LOY (prior RTH low)")] public bool RLOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "03 RTH - LOY (prior RTH low)")] public string RLOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "03 RTH - LOY (prior RTH low)")] public WMBrush RLOY_Color { get; set; }
		[Browsable(false)] public string RLOY_ColorSerialize { get { return Serialize.BrushToString(RLOY_Color); } set { RLOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "03 RTH - LOY (prior RTH low)")] public int RLOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "03 RTH - LOY (prior RTH low)")] public LevelLineStyle RLOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "03 RTH - LOY (prior RTH low)")] public int RLOY_Thickness { get; set; }

		// ---- RTH COY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "04 RTH - COY (prior RTH close)")] public bool RCOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "04 RTH - COY (prior RTH close)")] public string RCOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "04 RTH - COY (prior RTH close)")] public WMBrush RCOY_Color { get; set; }
		[Browsable(false)] public string RCOY_ColorSerialize { get { return Serialize.BrushToString(RCOY_Color); } set { RCOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "04 RTH - COY (prior RTH close)")] public int RCOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "04 RTH - COY (prior RTH close)")] public LevelLineStyle RCOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "04 RTH - COY (prior RTH close)")] public int RCOY_Thickness { get; set; }

		// ---- RTH OoD ----
		[Display(Name = "Enabled", Order = 0, GroupName = "05 RTH - OoD (open of day)")] public bool ROoD_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "05 RTH - OoD (open of day)")] public string ROoD_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "05 RTH - OoD (open of day)")] public WMBrush ROoD_Color { get; set; }
		[Browsable(false)] public string ROoD_ColorSerialize { get { return Serialize.BrushToString(ROoD_Color); } set { ROoD_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "05 RTH - OoD (open of day)")] public int ROoD_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "05 RTH - OoD (open of day)")] public LevelLineStyle ROoD_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "05 RTH - OoD (open of day)")] public int ROoD_Thickness { get; set; }

		// ---- RTH OoW ----
		[Display(Name = "Enabled", Order = 0, GroupName = "06 RTH - OoW (open of week)")] public bool ROoW_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "06 RTH - OoW (open of week)")] public string ROoW_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "06 RTH - OoW (open of week)")] public WMBrush ROoW_Color { get; set; }
		[Browsable(false)] public string ROoW_ColorSerialize { get { return Serialize.BrushToString(ROoW_Color); } set { ROoW_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "06 RTH - OoW (open of week)")] public int ROoW_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "06 RTH - OoW (open of week)")] public LevelLineStyle ROoW_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "06 RTH - OoW (open of week)")] public int ROoW_Thickness { get; set; }

		// ---- RTH OoM ----
		[Display(Name = "Enabled", Order = 0, GroupName = "07 RTH - OoM (open of month)")] public bool ROoM_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "07 RTH - OoM (open of month)")] public string ROoM_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "07 RTH - OoM (open of month)")] public WMBrush ROoM_Color { get; set; }
		[Browsable(false)] public string ROoM_ColorSerialize { get { return Serialize.BrushToString(ROoM_Color); } set { ROoM_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "07 RTH - OoM (open of month)")] public int ROoM_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "07 RTH - OoM (open of month)")] public LevelLineStyle ROoM_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "07 RTH - OoM (open of month)")] public int ROoM_Thickness { get; set; }
		[Display(Name = "Manual price (0 = auto)", Order = 6, GroupName = "07 RTH - OoM (open of month)", Description = "Type the RTH open-of-month price here to avoid loading a month of data. Used only when the month below matches the current month.")] public double ROoM_ManualPrice { get; set; }
		[Display(Name = "Manual month (pick any date in it)", Order = 7, GroupName = "07 RTH - OoM (open of month)", Description = "Which month the manual price above is for. The manual price shows only while this month is the current month.")] public DateTime ROoM_ManualMonth { get; set; }

		// ---- ETH HOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "08 ETH - H (current ETH high)")] public bool EHOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "08 ETH - H (current ETH high)")] public string EHOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "08 ETH - H (current ETH high)")] public WMBrush EHOY_Color { get; set; }
		[Browsable(false)] public string EHOY_ColorSerialize { get { return Serialize.BrushToString(EHOY_Color); } set { EHOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "08 ETH - H (current ETH high)")] public int EHOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "08 ETH - H (current ETH high)")] public LevelLineStyle EHOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "08 ETH - H (current ETH high)")] public int EHOY_Thickness { get; set; }

		// ---- ETH LOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "09 ETH - L (current ETH low)")] public bool ELOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "09 ETH - L (current ETH low)")] public string ELOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "09 ETH - L (current ETH low)")] public WMBrush ELOY_Color { get; set; }
		[Browsable(false)] public string ELOY_ColorSerialize { get { return Serialize.BrushToString(ELOY_Color); } set { ELOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "09 ETH - L (current ETH low)")] public int ELOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "09 ETH - L (current ETH low)")] public LevelLineStyle ELOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "09 ETH - L (current ETH low)")] public int ELOY_Thickness { get; set; }

		// ---- ETH COY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "10 ETH - COY (prior ETH-only close)")] public bool ECOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "10 ETH - COY (prior ETH-only close)")] public string ECOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "10 ETH - COY (prior ETH-only close)")] public WMBrush ECOY_Color { get; set; }
		[Browsable(false)] public string ECOY_ColorSerialize { get { return Serialize.BrushToString(ECOY_Color); } set { ECOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "10 ETH - COY (prior ETH-only close)")] public int ECOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "10 ETH - COY (prior ETH-only close)")] public LevelLineStyle ECOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "10 ETH - COY (prior ETH-only close)")] public int ECOY_Thickness { get; set; }

		// ---- ETH OoD ----
		[Display(Name = "Enabled", Order = 0, GroupName = "11 ETH - OoD (open of day / evening open)")] public bool EOoD_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "11 ETH - OoD (open of day / evening open)")] public string EOoD_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "11 ETH - OoD (open of day / evening open)")] public WMBrush EOoD_Color { get; set; }
		[Browsable(false)] public string EOoD_ColorSerialize { get { return Serialize.BrushToString(EOoD_Color); } set { EOoD_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "11 ETH - OoD (open of day / evening open)")] public int EOoD_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "11 ETH - OoD (open of day / evening open)")] public LevelLineStyle EOoD_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "11 ETH - OoD (open of day / evening open)")] public int EOoD_Thickness { get; set; }

		// ---- ETH OoW ----
		[Display(Name = "Enabled", Order = 0, GroupName = "12 ETH - OoW (open of week)")] public bool EOoW_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "12 ETH - OoW (open of week)")] public string EOoW_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "12 ETH - OoW (open of week)")] public WMBrush EOoW_Color { get; set; }
		[Browsable(false)] public string EOoW_ColorSerialize { get { return Serialize.BrushToString(EOoW_Color); } set { EOoW_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "12 ETH - OoW (open of week)")] public int EOoW_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "12 ETH - OoW (open of week)")] public LevelLineStyle EOoW_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "12 ETH - OoW (open of week)")] public int EOoW_Thickness { get; set; }

		// ---- ETH OoM ----
		[Display(Name = "Enabled", Order = 0, GroupName = "13 ETH - OoM (open of month)")] public bool EOoM_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "13 ETH - OoM (open of month)")] public string EOoM_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "13 ETH - OoM (open of month)")] public WMBrush EOoM_Color { get; set; }
		[Browsable(false)] public string EOoM_ColorSerialize { get { return Serialize.BrushToString(EOoM_Color); } set { EOoM_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "13 ETH - OoM (open of month)")] public int EOoM_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "13 ETH - OoM (open of month)")] public LevelLineStyle EOoM_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "13 ETH - OoM (open of month)")] public int EOoM_Thickness { get; set; }
		[Display(Name = "Manual price (0 = auto)", Order = 6, GroupName = "13 ETH - OoM (open of month)", Description = "Type the ETH open-of-month price here to avoid loading a month of data. Used only when the month below matches the current month.")] public double EOoM_ManualPrice { get; set; }
		[Display(Name = "Manual month (pick any date in it)", Order = 7, GroupName = "13 ETH - OoM (open of month)", Description = "Which month the manual price above is for. The manual price shows only while this month is the current month.")] public DateTime EOoM_ManualMonth { get; set; }

		// ---- Custom 1 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "14 Custom 1")] public bool C1_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "14 Custom 1")] public string C1_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "14 Custom 1")] public double C1_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "14 Custom 1")] public WMBrush C1_Color { get; set; }
		[Browsable(false)] public string C1_ColorSerialize { get { return Serialize.BrushToString(C1_Color); } set { C1_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "14 Custom 1")] public int C1_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "14 Custom 1")] public LevelLineStyle C1_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "14 Custom 1")] public int C1_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "14 Custom 1")] public DateTime C1_StartDate { get; set; }

		// ---- Custom 2 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "15 Custom 2")] public bool C2_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "15 Custom 2")] public string C2_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "15 Custom 2")] public double C2_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "15 Custom 2")] public WMBrush C2_Color { get; set; }
		[Browsable(false)] public string C2_ColorSerialize { get { return Serialize.BrushToString(C2_Color); } set { C2_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "15 Custom 2")] public int C2_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "15 Custom 2")] public LevelLineStyle C2_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "15 Custom 2")] public int C2_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "15 Custom 2")] public DateTime C2_StartDate { get; set; }

		// ---- Custom 3 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "16 Custom 3")] public bool C3_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "16 Custom 3")] public string C3_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "16 Custom 3")] public double C3_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "16 Custom 3")] public WMBrush C3_Color { get; set; }
		[Browsable(false)] public string C3_ColorSerialize { get { return Serialize.BrushToString(C3_Color); } set { C3_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "16 Custom 3")] public int C3_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "16 Custom 3")] public LevelLineStyle C3_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "16 Custom 3")] public int C3_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "16 Custom 3")] public DateTime C3_StartDate { get; set; }

		// ---- Custom 4 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "17 Custom 4")] public bool C4_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "17 Custom 4")] public string C4_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "17 Custom 4")] public double C4_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "17 Custom 4")] public WMBrush C4_Color { get; set; }
		[Browsable(false)] public string C4_ColorSerialize { get { return Serialize.BrushToString(C4_Color); } set { C4_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "17 Custom 4")] public int C4_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "17 Custom 4")] public LevelLineStyle C4_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "17 Custom 4")] public int C4_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "17 Custom 4")] public DateTime C4_StartDate { get; set; }

		// ---- Custom 5 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "18 Custom 5")] public bool C5_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "18 Custom 5")] public string C5_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "18 Custom 5")] public double C5_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "18 Custom 5")] public WMBrush C5_Color { get; set; }
		[Browsable(false)] public string C5_ColorSerialize { get { return Serialize.BrushToString(C5_Color); } set { C5_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "18 Custom 5")] public int C5_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "18 Custom 5")] public LevelLineStyle C5_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "18 Custom 5")] public int C5_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "18 Custom 5")] public DateTime C5_StartDate { get; set; }

		// ---- Custom 6 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "19 Custom 6")] public bool C6_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "19 Custom 6")] public string C6_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "19 Custom 6")] public double C6_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "19 Custom 6")] public WMBrush C6_Color { get; set; }
		[Browsable(false)] public string C6_ColorSerialize { get { return Serialize.BrushToString(C6_Color); } set { C6_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "19 Custom 6")] public int C6_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "19 Custom 6")] public LevelLineStyle C6_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "19 Custom 6")] public int C6_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "19 Custom 6")] public DateTime C6_StartDate { get; set; }

		// ---- Custom 7 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "20 Custom 7")] public bool C7_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "20 Custom 7")] public string C7_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "20 Custom 7")] public double C7_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "20 Custom 7")] public WMBrush C7_Color { get; set; }
		[Browsable(false)] public string C7_ColorSerialize { get { return Serialize.BrushToString(C7_Color); } set { C7_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "20 Custom 7")] public int C7_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "20 Custom 7")] public LevelLineStyle C7_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "20 Custom 7")] public int C7_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "20 Custom 7")] public DateTime C7_StartDate { get; set; }

		// ---- Custom 8 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "21 Custom 8")] public bool C8_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "21 Custom 8")] public string C8_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "21 Custom 8")] public double C8_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "21 Custom 8")] public WMBrush C8_Color { get; set; }
		[Browsable(false)] public string C8_ColorSerialize { get { return Serialize.BrushToString(C8_Color); } set { C8_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "21 Custom 8")] public int C8_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "21 Custom 8")] public LevelLineStyle C8_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "21 Custom 8")] public int C8_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "21 Custom 8")] public DateTime C8_StartDate { get; set; }

		#endregion
	}
}
