// SessionSRLevels — RTH + ETH session S/R levels, drawn from NT8's OWN CME trading-hours
// templates (not hardcoded clock times), so the lines land at the right spot on holidays
// and half-days too.
//
// LEVELS (12 total, independently stylable): for BOTH the RTH session and the ETH
// (overnight/non-RTH) session —
//   HOY/LOY/COY = High/Low/Close of the prior completed session (NOT "of year" despite
//                 the name — "Of Yesterday" in the Globex-sense of "the last one").
//   OoD/OoW/OoM = Open of Day / Week / Month for that session.
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
	public class SessionSRLevels : Indicator
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

		// ── values actually drawn (prior completed session + opens) ──────
		private double _priorRthHigh = double.NaN, _priorRthLow = double.NaN, _priorRthClose = double.NaN;
		private double _priorEthHigh = double.NaN, _priorEthLow = double.NaN, _priorEthClose = double.NaN;
		private double _rthOpenToday = double.NaN, _rthOpenThisWeek = double.NaN, _rthOpenThisMonth = double.NaN;
		private double _ethOpenToday = double.NaN, _ethOpenThisWeek = double.NaN, _ethOpenThisMonth = double.NaN;

		// ── bar index each level's line should START drawing from (the bar where that
		// value was established) — lines are rays from here to the current bar, NOT
		// full chart-width spans.
		private int _priorRthStartBar = -1, _priorEthStartBar = -1;
		private int _rthOpenStartBar  = -1, _ethOpenStartBar  = -1;
		private int _rthWeekStartBar  = -1, _ethWeekStartBar  = -1;
		private int _rthMonthStartBar = -1, _ethMonthStartBar = -1;

		// ── Chart Trader toggle buttons ───────────────────────────────────
		private Grid   ctButtonsGrid;
		private bool   ctPanelActive;
		private int    ctBaseRowCount;
		private Button btnRth, btnEth;
		private bool   _rthVisible = true, _ethVisible = true;
		private WMColor ColorOn  = WMColor.FromRgb(0, 140, 0);
		private WMColor ColorOff = WMColor.FromRgb(80, 80, 80);

		private struct LevelDef
		{
			public bool enabled; public string label; public double price;
			public WMColor color; public int opacity; public LevelLineStyle style; public int thickness;
			public int col; public int startBarIdx;
		}

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name                     = "SessionSRLevels";
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

				// RTH defaults: solid, saturated, thickness 2. Label = "{metric} RTH".
				RHOY_Enabled = true;  RHOY_Label = "HOY RTH"; RHOY_Color = Brushes.IndianRed;      RHOY_Opacity = 100; RHOY_Style = LevelLineStyle.Solid; RHOY_Thickness = 2;
				RLOY_Enabled = true;  RLOY_Label = "LOY RTH"; RLOY_Color = Brushes.RoyalBlue;      RLOY_Opacity = 100; RLOY_Style = LevelLineStyle.Solid; RLOY_Thickness = 2;
				RCOY_Enabled = true;  RCOY_Label = "COY RTH"; RCOY_Color = Brushes.Goldenrod;      RCOY_Opacity = 100; RCOY_Style = LevelLineStyle.Solid; RCOY_Thickness = 2;
				ROoD_Enabled = true;  ROoD_Label = "OoD RTH"; ROoD_Color = Brushes.MediumSeaGreen; ROoD_Opacity = 100; ROoD_Style = LevelLineStyle.Solid; ROoD_Thickness = 2;
				ROoW_Enabled = true;  ROoW_Label = "OoW RTH"; ROoW_Color = Brushes.DarkOrange;     ROoW_Opacity = 100; ROoW_Style = LevelLineStyle.Solid; ROoW_Thickness = 2;
				ROoM_Enabled = true;  ROoM_Label = "OoM RTH"; ROoM_Color = Brushes.MediumPurple;   ROoM_Opacity = 100; ROoM_Style = LevelLineStyle.Solid; ROoM_Thickness = 2;

				// ETH defaults: same hue family, dashed, thickness 1, lower default opacity. Label = "{metric} ETH".
				EHOY_Enabled = true;  EHOY_Label = "HOY ETH"; EHOY_Color = Brushes.IndianRed;      EHOY_Opacity = 70; EHOY_Style = LevelLineStyle.Dash; EHOY_Thickness = 1;
				ELOY_Enabled = true;  ELOY_Label = "LOY ETH"; ELOY_Color = Brushes.RoyalBlue;      ELOY_Opacity = 70; ELOY_Style = LevelLineStyle.Dash; ELOY_Thickness = 1;
				ECOY_Enabled = true;  ECOY_Label = "COY ETH"; ECOY_Color = Brushes.Goldenrod;      ECOY_Opacity = 70; ECOY_Style = LevelLineStyle.Dash; ECOY_Thickness = 1;
				EOoD_Enabled = true;  EOoD_Label = "OoD ETH"; EOoD_Color = Brushes.MediumSeaGreen; EOoD_Opacity = 70; EOoD_Style = LevelLineStyle.Dash; EOoD_Thickness = 1;
				EOoW_Enabled = true;  EOoW_Label = "OoW ETH"; EOoW_Color = Brushes.DarkOrange;     EOoW_Opacity = 70; EOoW_Style = LevelLineStyle.Dash; EOoW_Thickness = 1;
				EOoM_Enabled = true;  EOoM_Label = "OoM ETH"; EOoM_Color = Brushes.MediumPurple;   EOoM_Opacity = 70; EOoM_Style = LevelLineStyle.Dash; EOoM_Thickness = 1;
			}
			else if (State == State.Configure)
			{
				_dayIter = null; _rthHours = null; _rthIter = null; _rthOk = false;
				_curTradingDay = Core.Globals.MinDate; _curWeekStart = Core.Globals.MinDate; _curMonthKey = -1;
				_haveRth = _haveEth = false;
				_rthOpenCapturedToday = false; _weekAwaitingRthOpen = false; _monthAwaitingRthOpen = false;
				_priorRthHigh = _priorRthLow = _priorRthClose = double.NaN;
				_priorEthHigh = _priorEthLow = _priorEthClose = double.NaN;
				_rthOpenToday = _rthOpenThisWeek = _rthOpenThisMonth = double.NaN;
				_ethOpenToday = _ethOpenThisWeek = _ethOpenThisMonth = double.NaN;
				_priorRthStartBar = _priorEthStartBar = -1;
				_rthOpenStartBar  = _ethOpenStartBar  = -1;
				_rthWeekStartBar  = _ethWeekStartBar  = -1;
				_rthMonthStartBar = _ethMonthStartBar = -1;
			}
			else if (State == State.DataLoaded)
			{
				_displayTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
				_dayIter   = new SessionIterator(Bars);

				try
				{
					_rthHours = TradingHours.Get(RthTemplateName);
					if (_rthHours == null) throw new Exception("template not found");
					_rthIter = new SessionIterator(_rthHours);
					_rthOk   = true;
				}
				catch (Exception ex)
				{
					Print("SessionSRLevels: WARNING - RTH template '" + RthTemplateName + "' did not resolve (" + ex.Message + "). RTH/ETH split disabled; every bar will be treated as ETH.");
					_rthOk = false;
				}

				if (Bars.TradingHours != null && !string.IsNullOrEmpty(FullTemplateNameHint)
					&& Bars.TradingHours.Name != FullTemplateNameHint)
					Print("SessionSRLevels: NOTE - chart Trading Hours template is '" + Bars.TradingHours.Name
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
			if (CurrentBar < 0 || !Bars.BarsType.IsIntraday) return;

			DateTime barTime    = Time[0];
			DateTime tradingDay = _dayIter.GetTradingDay(barTime);

			if (tradingDay != _curTradingDay)
			{
				if (_haveRth) { _priorRthHigh = _rthHigh; _priorRthLow = _rthLow; _priorRthClose = _rthCloseLast; _priorRthStartBar = CurrentBar; }
				if (_haveEth) { _priorEthHigh = _ethHigh; _priorEthLow = _ethLow; _priorEthClose = _ethCloseLast; _priorEthStartBar = CurrentBar; }

				_curTradingDay        = tradingDay;
				_haveRth = _haveEth   = false;
				_rthOpenCapturedToday = false;

				_ethOpenToday    = Open[0];   // full Globex day's first bar = the overnight ("ETH") open
				_ethOpenStartBar = CurrentBar;

				DateTime wkStart = MondayOf(tradingDay);
				if (wkStart != _curWeekStart)
				{
					_curWeekStart         = wkStart;
					_ethOpenThisWeek      = Open[0];
					_ethWeekStartBar      = CurrentBar;
					_weekAwaitingRthOpen  = true;
				}
				int monthKey = tradingDay.Year * 12 + tradingDay.Month;
				if (monthKey != _curMonthKey)
				{
					_curMonthKey           = monthKey;
					_ethOpenThisMonth      = Open[0];
					_ethMonthStartBar      = CurrentBar;
					_monthAwaitingRthOpen  = true;
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

			bool isRth = false;
			if (_rthOk && _rthSessBegin != Core.Globals.MinDate)
			{
				DateTime tRth = ConvertToRthTz(barTime);
				isRth = tRth >= _rthSessBegin && tRth <= _rthSessEnd;
			}

			if (isRth)
			{
				if (!_haveRth) { _rthHigh = High[0]; _rthLow = Low[0]; _haveRth = true; }
				else           { _rthHigh = Math.Max(_rthHigh, High[0]); _rthLow = Math.Min(_rthLow, Low[0]); }
				_rthCloseLast = Close[0];

				if (!_rthOpenCapturedToday)
				{
					_rthOpenToday         = Open[0];
					_rthOpenStartBar      = CurrentBar;
					_rthOpenCapturedToday = true;
					if (_weekAwaitingRthOpen)  { _rthOpenThisWeek  = Open[0]; _rthWeekStartBar  = CurrentBar; _weekAwaitingRthOpen  = false; }
					if (_monthAwaitingRthOpen) { _rthOpenThisMonth = Open[0]; _rthMonthStartBar = CurrentBar; _monthAwaitingRthOpen = false; }
				}
			}
			else
			{
				if (!_haveEth) { _ethHigh = High[0]; _ethLow = Low[0]; _haveEth = true; }
				else           { _ethHigh = Math.Max(_ethHigh, High[0]); _ethLow = Math.Min(_ethLow, Low[0]); }
				_ethCloseLast = Close[0];
			}
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

		// ══════════════════════════ Rendering ════════════════════════════
		// Lines are RAYS: they start at the bar where that level's value was actually
		// established and run right to the current bar — never the full panel width,
		// never past "now" (same idea as PADayTradingSR). Labels sit just past that
		// right end, not pinned to the chart's physical right edge.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;

			var defs = BuildLevelDefs();
			if (defs.Count == 0) return;

			float panelLeft = (float)ChartPanel.X;
			int lastIdx = ChartBars.ToIndex;
			if (lastIdx < 0) return;
			float lineEndX = chartControl.GetXByBarIndex(ChartBars, lastIdx);

			var labels = new List<LabelInfo>();
			foreach (LevelDef d in defs)
			{
				if (!d.enabled || double.IsNaN(d.price) || d.startBarIdx < 0) continue;

				int startIdx = Math.Max(d.startBarIdx, ChartBars.FromIndex);
				float xStart = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, startIdx));
				if (xStart >= lineEndX) continue;

				float a = Math.Max(0f, Math.Min(1f, d.opacity / 100f));
				var sdxBrush = new D2DSolidColorBrush(RenderTarget,
					new Color4(d.color.R / 255f, d.color.G / 255f, d.color.B / 255f, a));

				float y = chartScale.GetYByValue(d.price);
				DrawStyledLine(xStart, lineEndX, y, sdxBrush, d.thickness, d.style);

				string text = ShowPriceInLabel ? d.label + " " + F(d.price) : d.label;
				labels.Add(new LabelInfo { y = y, trueY = y, text = text, brush = sdxBrush, col = d.col });
			}

			DrawLabels(labels, lineEndX + 6f);

			foreach (LabelInfo li in labels) li.brush.Dispose();
		}

		private List<LevelDef> BuildLevelDefs()
		{
			var list = new List<LevelDef>(12);
			if (_rthVisible)
			{
				Add(list, RHOY_Enabled, RHOY_Label, _priorRthHigh,    RHOY_Color, RHOY_Opacity, RHOY_Style, RHOY_Thickness, 0, _priorRthStartBar);
				Add(list, RLOY_Enabled, RLOY_Label, _priorRthLow,     RLOY_Color, RLOY_Opacity, RLOY_Style, RLOY_Thickness, 0, _priorRthStartBar);
				Add(list, RCOY_Enabled, RCOY_Label, _priorRthClose,   RCOY_Color, RCOY_Opacity, RCOY_Style, RCOY_Thickness, 0, _priorRthStartBar);
				Add(list, ROoD_Enabled, ROoD_Label, _rthOpenToday,    ROoD_Color, ROoD_Opacity, ROoD_Style, ROoD_Thickness, 0, _rthOpenStartBar);
				Add(list, ROoW_Enabled, ROoW_Label, _rthOpenThisWeek, ROoW_Color, ROoW_Opacity, ROoW_Style, ROoW_Thickness, 0, _rthWeekStartBar);
				Add(list, ROoM_Enabled, ROoM_Label, _rthOpenThisMonth,ROoM_Color, ROoM_Opacity, ROoM_Style, ROoM_Thickness, 0, _rthMonthStartBar);
			}
			if (_ethVisible)
			{
				Add(list, EHOY_Enabled, EHOY_Label, _priorEthHigh,    EHOY_Color, EHOY_Opacity, EHOY_Style, EHOY_Thickness, 1, _priorEthStartBar);
				Add(list, ELOY_Enabled, ELOY_Label, _priorEthLow,     ELOY_Color, ELOY_Opacity, ELOY_Style, ELOY_Thickness, 1, _priorEthStartBar);
				Add(list, ECOY_Enabled, ECOY_Label, _priorEthClose,   ECOY_Color, ECOY_Opacity, ECOY_Style, ECOY_Thickness, 1, _priorEthStartBar);
				Add(list, EOoD_Enabled, EOoD_Label, _ethOpenToday,    EOoD_Color, EOoD_Opacity, EOoD_Style, EOoD_Thickness, 1, _ethOpenStartBar);
				Add(list, EOoW_Enabled, EOoW_Label, _ethOpenThisWeek, EOoW_Color, EOoW_Opacity, EOoW_Style, EOoW_Thickness, 1, _ethWeekStartBar);
				Add(list, EOoM_Enabled, EOoM_Label, _ethOpenThisMonth,EOoM_Color, EOoM_Opacity, EOoM_Style, EOoM_Thickness, 1, _ethMonthStartBar);
			}
			return list;
		}

		private static void Add(List<LevelDef> list, bool enabled, string label, double price,
			WMBrush brush, int opacity, LevelLineStyle style, int thickness, int col, int startBarIdx)
		{
			var scb = brush as WMSolidColorBrush;
			list.Add(new LevelDef
			{
				enabled = enabled, label = label, price = price,
				color = scb != null ? scb.Color : Colors.Gray,
				opacity = opacity, style = style, thickness = thickness, col = col, startBarIdx = startBarIdx
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

		private class LabelInfo { public float y; public float trueY; public string text; public D2DSolidColorBrush brush; public int col; }

		// Two columns (RTH / ETH), anchored just past where the lines end (the current
		// bar), de-collided top-to-bottom with leader lines when a label had to be
		// nudged off its true price — same pattern as WyckoffVPLevels.
		private void DrawLabels(List<LabelInfo> labels, float baseX)
		{
			if (labels.Count == 0) return;
			float colW = LabelFontSize * 6.5f;
			float gap  = LabelFontSize + 4f;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			for (int c = 0; c <= 1; c++)
			{
				var col = new List<LabelInfo>();
				foreach (LabelInfo li in labels) if (li.col == c) col.Add(li);
				if (col.Count == 0) continue;
				col.Sort(delegate (LabelInfo a, LabelInfo b) { return a.y.CompareTo(b.y); });
				for (int i = 1; i < col.Count; i++)
					if (col[i].y < col[i - 1].y + gap) col[i].y = col[i - 1].y + gap;
				float x = baseX + c * colW;
				foreach (LabelInfo li in col)
				{
					if (Math.Abs(li.y - li.trueY) > 1.5f)
						RenderTarget.DrawLine(new Vector2(x - 6f, li.trueY), new Vector2(x - 1f, li.y + LabelFontSize * 0.5f), li.brush, 0.6f);
					RenderTarget.DrawText(li.text, tf, new RectangleF(x, li.y, colW, LabelFontSize + 6f), li.brush);
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
				if (win == null) { Print("SessionSRLevels: chart window not found"); return; }
				var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
				if (chartTrader == null) { Print("SessionSRLevels: ChartTrader not found (is Chart Trader shown?)"); return; }
				var outerGrid = chartTrader.Content as Grid;
				if (outerGrid == null) return;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { ctButtonsGrid = g; break; }
				}
				if (ctButtonsGrid == null) { Print("SessionSRLevels: button grid not found"); return; }

				ctBaseRowCount = ctButtonsGrid.RowDefinitions.Count;
				Style s = Application.Current.TryFindResource("Button") as Style;

				btnRth = MakeBtn(s, "RTH LEVELS", "Toggle RTH session levels", _rthVisible ? ColorOn : ColorOff);
				btnRth.Click += (o, e) => { _rthVisible = !_rthVisible; SetBtn(btnRth, _rthVisible ? ColorOn : ColorOff); ChartControl.InvalidateVisual(); };

				btnEth = MakeBtn(s, "ETH LEVELS", "Toggle ETH session levels", _ethVisible ? ColorOn : ColorOff);
				btnEth.Click += (o, e) => { _ethVisible = !_ethVisible; SetBtn(btnEth, _ethVisible ? ColorOn : ColorOff); ChartControl.InvalidateVisual(); };

				AddHalfRow(ctButtonsGrid, ctBaseRowCount, btnRth, btnEth);
				ctPanelActive = true;
			}
			catch (Exception ex) { Print("SessionSRLevels CreateWPFControls: " + ex.Message); }
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
				btnRth = btnEth = null;
				ctPanelActive = false;
			}
			catch (Exception ex) { Print("SessionSRLevels DisposeWPFControls: " + ex.Message); }
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

		#region Properties

		[NinjaScriptProperty]
		[Display(Name = "RTH template name", Order = 0, GroupName = "00 Session Templates",
			Description = "NT8 Trading Hours template used for the RTH window (begin/end + holidays/half-days).")]
		public string RthTemplateName { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Expected chart template (informational)", Order = 1, GroupName = "00 Session Templates",
			Description = "Just a sanity check: Print()s a warning at DataLoaded if the chart's own Trading Hours template name differs (expects the 23h Globex template so ETH bars actually exist).")]
		public string FullTemplateNameHint { get; set; }

		[NinjaScriptProperty]
		[Range(6, 24)]
		[Display(Name = "Label font size", Order = 2, GroupName = "01 Display")]
		public int LabelFontSize { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show price in label", Order = 3, GroupName = "01 Display",
			Description = "Off = just the label text (e.g. \"COY RTH\"), no price value appended.")]
		public bool ShowPriceInLabel { get; set; }

		// ---- RTH HOY ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "02 RTH - HOY (prior RTH high)")] public bool RHOY_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "02 RTH - HOY (prior RTH high)")] public string RHOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "02 RTH - HOY (prior RTH high)")] public WMBrush RHOY_Color { get; set; }
		[Browsable(false)] public string RHOY_ColorSerialize { get { return Serialize.BrushToString(RHOY_Color); } set { RHOY_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "02 RTH - HOY (prior RTH high)")] public int RHOY_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "02 RTH - HOY (prior RTH high)")] public LevelLineStyle RHOY_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "02 RTH - HOY (prior RTH high)")] public int RHOY_Thickness { get; set; }

		// ---- RTH LOY ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "03 RTH - LOY (prior RTH low)")] public bool RLOY_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "03 RTH - LOY (prior RTH low)")] public string RLOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "03 RTH - LOY (prior RTH low)")] public WMBrush RLOY_Color { get; set; }
		[Browsable(false)] public string RLOY_ColorSerialize { get { return Serialize.BrushToString(RLOY_Color); } set { RLOY_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "03 RTH - LOY (prior RTH low)")] public int RLOY_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "03 RTH - LOY (prior RTH low)")] public LevelLineStyle RLOY_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "03 RTH - LOY (prior RTH low)")] public int RLOY_Thickness { get; set; }

		// ---- RTH COY ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "04 RTH - COY (prior RTH close)")] public bool RCOY_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "04 RTH - COY (prior RTH close)")] public string RCOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "04 RTH - COY (prior RTH close)")] public WMBrush RCOY_Color { get; set; }
		[Browsable(false)] public string RCOY_ColorSerialize { get { return Serialize.BrushToString(RCOY_Color); } set { RCOY_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "04 RTH - COY (prior RTH close)")] public int RCOY_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "04 RTH - COY (prior RTH close)")] public LevelLineStyle RCOY_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "04 RTH - COY (prior RTH close)")] public int RCOY_Thickness { get; set; }

		// ---- RTH OoD ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "05 RTH - OoD (open of day)")] public bool ROoD_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "05 RTH - OoD (open of day)")] public string ROoD_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "05 RTH - OoD (open of day)")] public WMBrush ROoD_Color { get; set; }
		[Browsable(false)] public string ROoD_ColorSerialize { get { return Serialize.BrushToString(ROoD_Color); } set { ROoD_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "05 RTH - OoD (open of day)")] public int ROoD_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "05 RTH - OoD (open of day)")] public LevelLineStyle ROoD_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "05 RTH - OoD (open of day)")] public int ROoD_Thickness { get; set; }

		// ---- RTH OoW ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "06 RTH - OoW (open of week)")] public bool ROoW_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "06 RTH - OoW (open of week)")] public string ROoW_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "06 RTH - OoW (open of week)")] public WMBrush ROoW_Color { get; set; }
		[Browsable(false)] public string ROoW_ColorSerialize { get { return Serialize.BrushToString(ROoW_Color); } set { ROoW_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "06 RTH - OoW (open of week)")] public int ROoW_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "06 RTH - OoW (open of week)")] public LevelLineStyle ROoW_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "06 RTH - OoW (open of week)")] public int ROoW_Thickness { get; set; }

		// ---- RTH OoM ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "07 RTH - OoM (open of month)")] public bool ROoM_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "07 RTH - OoM (open of month)")] public string ROoM_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "07 RTH - OoM (open of month)")] public WMBrush ROoM_Color { get; set; }
		[Browsable(false)] public string ROoM_ColorSerialize { get { return Serialize.BrushToString(ROoM_Color); } set { ROoM_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "07 RTH - OoM (open of month)")] public int ROoM_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "07 RTH - OoM (open of month)")] public LevelLineStyle ROoM_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "07 RTH - OoM (open of month)")] public int ROoM_Thickness { get; set; }

		// ---- ETH HOY ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "08 ETH - HOY (prior ETH-only high)")] public bool EHOY_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "08 ETH - HOY (prior ETH-only high)")] public string EHOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "08 ETH - HOY (prior ETH-only high)")] public WMBrush EHOY_Color { get; set; }
		[Browsable(false)] public string EHOY_ColorSerialize { get { return Serialize.BrushToString(EHOY_Color); } set { EHOY_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "08 ETH - HOY (prior ETH-only high)")] public int EHOY_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "08 ETH - HOY (prior ETH-only high)")] public LevelLineStyle EHOY_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "08 ETH - HOY (prior ETH-only high)")] public int EHOY_Thickness { get; set; }

		// ---- ETH LOY ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "09 ETH - LOY (prior ETH-only low)")] public bool ELOY_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "09 ETH - LOY (prior ETH-only low)")] public string ELOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "09 ETH - LOY (prior ETH-only low)")] public WMBrush ELOY_Color { get; set; }
		[Browsable(false)] public string ELOY_ColorSerialize { get { return Serialize.BrushToString(ELOY_Color); } set { ELOY_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "09 ETH - LOY (prior ETH-only low)")] public int ELOY_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "09 ETH - LOY (prior ETH-only low)")] public LevelLineStyle ELOY_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "09 ETH - LOY (prior ETH-only low)")] public int ELOY_Thickness { get; set; }

		// ---- ETH COY ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "10 ETH - COY (prior ETH-only close)")] public bool ECOY_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "10 ETH - COY (prior ETH-only close)")] public string ECOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "10 ETH - COY (prior ETH-only close)")] public WMBrush ECOY_Color { get; set; }
		[Browsable(false)] public string ECOY_ColorSerialize { get { return Serialize.BrushToString(ECOY_Color); } set { ECOY_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "10 ETH - COY (prior ETH-only close)")] public int ECOY_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "10 ETH - COY (prior ETH-only close)")] public LevelLineStyle ECOY_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "10 ETH - COY (prior ETH-only close)")] public int ECOY_Thickness { get; set; }

		// ---- ETH OoD ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "11 ETH - OoD (open of day / evening open)")] public bool EOoD_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "11 ETH - OoD (open of day / evening open)")] public string EOoD_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "11 ETH - OoD (open of day / evening open)")] public WMBrush EOoD_Color { get; set; }
		[Browsable(false)] public string EOoD_ColorSerialize { get { return Serialize.BrushToString(EOoD_Color); } set { EOoD_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "11 ETH - OoD (open of day / evening open)")] public int EOoD_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "11 ETH - OoD (open of day / evening open)")] public LevelLineStyle EOoD_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "11 ETH - OoD (open of day / evening open)")] public int EOoD_Thickness { get; set; }

		// ---- ETH OoW ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "12 ETH - OoW (open of week)")] public bool EOoW_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "12 ETH - OoW (open of week)")] public string EOoW_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "12 ETH - OoW (open of week)")] public WMBrush EOoW_Color { get; set; }
		[Browsable(false)] public string EOoW_ColorSerialize { get { return Serialize.BrushToString(EOoW_Color); } set { EOoW_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "12 ETH - OoW (open of week)")] public int EOoW_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "12 ETH - OoW (open of week)")] public LevelLineStyle EOoW_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "12 ETH - OoW (open of week)")] public int EOoW_Thickness { get; set; }

		// ---- ETH OoM ----
		[NinjaScriptProperty] [Display(Name = "Enabled", Order = 0, GroupName = "13 ETH - OoM (open of month)")] public bool EOoM_Enabled { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label", Order = 1, GroupName = "13 ETH - OoM (open of month)")] public string EOoM_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "13 ETH - OoM (open of month)")] public WMBrush EOoM_Color { get; set; }
		[Browsable(false)] public string EOoM_ColorSerialize { get { return Serialize.BrushToString(EOoM_Color); } set { EOoM_Color = Serialize.StringToBrush(value); } }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "13 ETH - OoM (open of month)")] public int EOoM_Opacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Line style", Order = 4, GroupName = "13 ETH - OoM (open of month)")] public LevelLineStyle EOoM_Style { get; set; }
		[NinjaScriptProperty] [Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "13 ETH - OoM (open of month)")] public int EOoM_Thickness { get; set; }

		#endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private SessionSRLevels[] cacheSessionSRLevels;
		public SessionSRLevels SessionSRLevels()
		{
			return SessionSRLevels(Input);
		}

		public SessionSRLevels SessionSRLevels(ISeries<double> input)
		{
			if (cacheSessionSRLevels != null)
				for (int idx = 0; idx < cacheSessionSRLevels.Length; idx++)
					if (cacheSessionSRLevels[idx] != null && cacheSessionSRLevels[idx].EqualsInput(input))
						return cacheSessionSRLevels[idx];
			return CacheIndicator<SessionSRLevels>(new SessionSRLevels(), input, ref cacheSessionSRLevels);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.SessionSRLevels SessionSRLevels()
		{
			return indicator.SessionSRLevels(Input);
		}

		public Indicators.SessionSRLevels SessionSRLevels(ISeries<double> input)
		{
			return indicator.SessionSRLevels(input);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.SessionSRLevels SessionSRLevels()
		{
			return indicator.SessionSRLevels(Input);
		}

		public Indicators.SessionSRLevels SessionSRLevels(ISeries<double> input)
		{
			return indicator.SessionSRLevels(input);
		}
	}
}

#endregion
