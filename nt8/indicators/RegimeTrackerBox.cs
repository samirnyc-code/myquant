#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows.Media;
using System.Windows.Threading;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
// SharpDX aliases so System.Windows.Media.* (NT8 brushes/colors) and SharpDX.*
// (the render-target primitives) can both be used without fully qualifying.
using WMColor = System.Windows.Media.Color;
using WMBrush = System.Windows.Media.Brush;
using WMSolidColorBrush = System.Windows.Media.SolidColorBrush;
using D2DSolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

// Enum lives in namespace NinjaTrader.NinjaScript (NOT nested in the class and
// NOT in .Indicators) so the F5-generated wrapper constructors can see it — see
// the note in scripts/nt8_compile_check.ps1.
namespace NinjaTrader.NinjaScript
{
	public enum RegimeBoxCorner { TopLeft, TopRight, BottomLeft, BottomRight }
}

namespace NinjaTrader.NinjaScript.Indicators
{
	// ── RegimeTrackerBox ─────────────────────────────────────────────────────
	// A dashboard box that shows, per timeframe, the current Bull/Bear/Range
	// regime in two columns: RTH and ETH. Each cell is colored by regime.
	//
	// HOW IT WORKS
	//   - Same regime state machine as RegimeTrackerPanel/RegimeTrackerV2 (MyWedge
	//     swings -> BOS/ChoCh -> Bull/Bear/Range), lifted into a self-contained
	//     RegimeEngine so it can run many times in parallel.
	//   - For EACH timeframe in the editable list, TWO data series are added via
	//     AddDataSeries: one on the RTH trading-hours template, one on the ETH
	//     template. The regime is computed INDEPENDENTLY over each bar set, so the
	//     two columns are genuinely different reads (different bars + different
	//     session-reset points), not the same series relabeled.
	//   - One RegimeEngine (with its OWN MyWedge child, bound to that series via
	//     MyWedge(Closes[bip], ...)) per added series. This mirrors the ONE level
	//     of composition RegimeTrackerPanel proved works; nothing nests deeper.
	//   - OnRender paints the table at a configurable corner + X/Y offset, in a
	//     configurable font size; the box auto-sizes to the font.
	//
	// NOTES
	//   - Intraday timeframes (tick/second/minute) reset regime per session when
	//     ResetOnNewSession is on; Daily/Weekly NEVER session-reset (a "session" is
	//     one bar there) so they build a continuous regime across history.
	//   - CurrentSessionOnly only skips pre-current-session history for intraday
	//     reset-on-session engines (safe, those bars are discarded anyway); it is
	//     ignored for D/W and for non-resetting engines, which need their history
	//     to form swings.
	//   - Lag=0 (default here) includes the just-closed bar with no pivot-finality
	//     delay (repaints the forming pivot) — matches the user's live view.
	public class RegimeTrackerBox : Indicator
	{
		private const string BULL = "Bull", BEAR = "Bear", RANGE = "Range";

		// one tracked grid position: timeframe row x session column -> its engine
		private class Cell
		{
			public int Bip;         // BarsInProgress index of its data series
			public int Row;         // timeframe row (0-based)
			public int Col;         // 0 = RTH, 1 = ETH
			public RegimeEngine Eng;
		}

		private class TfDef
		{
			public string Label;
			public BarsPeriodType Type;
			public int Value;
			public bool Intraday;
		}

		private List<TfDef> _tfs;
		private List<Cell>  _cells;
		private Cell[]      _byBip;      // bip -> cell (null for untracked)

		// render brushes (opacity-adjusted); color pickers keep the raw opaque color
		private WMBrush _bullShade, _bearShade, _rangeShade;

		// forces a repaint between bar closes so the live-price-driven cell %s
		// actually refresh (see State.Historical below)
		private DispatcherTimer _renderTimer;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Per-timeframe Bull/Bear/Range regime dashboard (RTH + ETH columns), colored by regime. Same classifier as RegimeTrackerPanel, run on an added RTH and ETH series per timeframe.";
				Name        = "RegimeTrackerBox";
				Calculate   = Calculate.OnBarClose;
				IsOverlay   = true;
				IsSuspendedWhileInactive = false;
				DrawOnPricePanel = true;

				Timeframes = "2000t,5M,15M,60M,240M,D,W";
				RthTemplate = "CME US Index Futures RTH";
				EthTemplate = "CME US Index Futures ETH";
				// generous cushion over a single session for ANY of the intraday
				// periods (even 2000-tick on an active day), while being nowhere near
				// the chart's full lookback -- see Configure. Ignored for Day/Week.
				IntradayBarsToLoad = 1000;

				// MyWedge (defaults = the validated Python run's params, as in RegimeTrackerPanel)
				LookBack      = 12;
				ShowW2L       = true;
				WedgeSymmetry = 4;
				OLSensitivity = 1;
				CTSB_Ignore   = true;
				IB_Ignore     = true;
				ShowWedgeSB   = true;
				SignalBarIBS  = 66.0;
				ContinueMC    = false;
				ContinueOnGap = false;

				// regime
				Lag                = 0;
				ResetOnNewSession  = true;
				WeeklyResetOnly    = false;
				CurrentSessionOnly = true;

				// box layout
				Corner       = RegimeBoxCorner.TopRight;
				OffsetX      = 20;
				OffsetY      = 20;
				FontSize     = 14;
				CellPadding  = 6;
				ShowRegimeText = true;
				ShowPct        = true;
				RenderIntervalMs = 500;
				ShowBorder     = true;

				// colors
				BullBrush   = Brushes.SeaGreen;
				BearBrush   = Brushes.IndianRed;
				RangeBrush  = Brushes.DimGray;
				TextBrush   = Brushes.White;
				HeaderBrush = Brushes.Gainsboro;
				BorderBrush = Brushes.Black;
				CellOpacity = 85;
			}
			else if (State == State.Configure)
			{
				_tfs = ParseTimeframes(Timeframes);
				_cells = new List<Cell>();

				int bip = 1;   // bip 0 = the chart's own primary series (untracked)
				for (int r = 0; r < _tfs.Count; r++)
				{
					TfDef tf = _tfs[r];
					// RTH column first (left), then ETH — fixed order = deterministic bip.
					// Intraday (tick/second/minute) series reset their regime every
					// session (ResetOnNewSession), so history before the current session
					// is useless to the calc -- cap NT8's OWN historical load to
					// IntradayBarsToLoad (not the chart's full lookback) and tell NT8's
					// bar engine itself to reset on each new trading day. Daily/Weekly
					// are intentionally NEVER session-reset (need real multi-month
					// history for a persistent regime) and stay uncapped -- cheap anyway
					// at a few hundred bars/year.
					if (tf.Intraday)
					{
						bool resetSession = ResetOnNewSession;
						AddDataSeries(Instrument.FullName, MakePeriod(tf), IntradayBarsToLoad, RthTemplate, resetSession);
						_cells.Add(new Cell { Bip = bip++, Row = r, Col = 0 });
						AddDataSeries(Instrument.FullName, MakePeriod(tf), IntradayBarsToLoad, EthTemplate, resetSession);
						_cells.Add(new Cell { Bip = bip++, Row = r, Col = 1 });
					}
					else
					{
						AddDataSeries(Instrument.FullName, MakePeriod(tf), RthTemplate);
						_cells.Add(new Cell { Bip = bip++, Row = r, Col = 0 });
						AddDataSeries(Instrument.FullName, MakePeriod(tf), EthTemplate);
						_cells.Add(new Cell { Bip = bip++, Row = r, Col = 1 });
					}
				}

				FreezeIf(BullBrush); FreezeIf(BearBrush); FreezeIf(RangeBrush);
				FreezeIf(TextBrush); FreezeIf(HeaderBrush); FreezeIf(BorderBrush);
				_bullShade  = MakeShade(BullBrush, CellOpacity);
				_bearShade  = MakeShade(BearBrush, CellOpacity);
				_rangeShade = MakeShade(RangeBrush, CellOpacity);
			}
			else if (State == State.DataLoaded)
			{
				int maxBip = 0;
				foreach (Cell c in _cells) if (c.Bip > maxBip) maxBip = c.Bip;
				_byBip = new Cell[maxBip + 1];

				foreach (Cell c in _cells)
				{
					TfDef tf = _tfs[c.Row];
					bool resetSession = ResetOnNewSession && tf.Intraday;   // never for D/W

					My.MyWedge wedge = MyWedge(Closes[c.Bip], LookBack, ShowW2L, WedgeSymmetry,
						OLSensitivity, CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS,
						ContinueMC, ContinueOnGap);

					c.Eng = new RegimeEngine(
						wedge,
						Opens[c.Bip], Highs[c.Bip], Lows[c.Bip], Closes[c.Bip], Times[c.Bip],
						BarsArray[c.Bip], Lag, resetSession, WeeklyResetOnly,
						CurrentSessionOnly && resetSession);

					_byBip[c.Bip] = c;
				}
			}
			else if (State == State.Historical)
			{
				// Regime-only cells change at bar close, which already redraws the
				// chart naturally -- no extra cost needed. The % value reads LIVE
				// price (Close[0]) between bar closes, so ONLY when % is shown do we
				// pay for a forced-redraw timer (same InvalidateVisual pattern as
				// RegimeTrackerV2's visibility-sync timer / DtDbScannerV2/V3), at a
				// user-editable interval instead of a hardcoded fast one.
				if (!ShowPct || ChartControl == null) return;
				ChartControl.Dispatcher.InvokeAsync(() =>
				{
					_renderTimer = new DispatcherTimer(DispatcherPriority.Background, ChartControl.Dispatcher);
					_renderTimer.Interval = TimeSpan.FromMilliseconds(Math.Max(100, RenderIntervalMs));
					_renderTimer.Tick += (s, e) => { if (ChartControl != null) ChartControl.InvalidateVisual(); };
					_renderTimer.Start();
				});
			}
			else if (State == State.Terminated)
			{
				if (ChartControl != null)
				{
					ChartControl.Dispatcher.InvokeAsync(() =>
					{
						if (_renderTimer != null) { _renderTimer.Stop(); _renderTimer = null; }
					});
				}
			}
		}

		protected override void OnBarUpdate()
		{
			int bip = BarsInProgress;
			if (_byBip == null || bip <= 0 || bip >= _byBip.Length) return;   // skip primary + out-of-range
			Cell c = _byBip[bip];
			if (c == null || c.Eng == null) return;
			c.Eng.OnBar(CurrentBar);   // CurrentBar is the current index of THIS series
		}

		// ── table render ──────────────────────────────────────────────────────
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (RenderTarget == null || ChartPanel == null || _tfs == null || _cells == null) return;

			var factory = NinjaTrader.Core.Globals.DirectWriteFactory;
			float fs = Math.Max(6, FontSize);
			float pad = Math.Max(0, CellPadding);

			using (var tfCenter = new TextFormat(factory, "Arial", fs)
				{ TextAlignment = TextAlignment.Center, ParagraphAlignment = ParagraphAlignment.Center })
			using (var tfBold = new TextFormat(factory, "Arial", FontWeight.Bold, FontStyle.Normal, FontStretch.Normal, fs)
				{ TextAlignment = TextAlignment.Center, ParagraphAlignment = ParagraphAlignment.Center })
			{
				// column widths: label col sized to widest timeframe label; the two
				// data cols sized to the widest of their header + regime words.
				float labelW = 0f;
				for (int r = 0; r < _tfs.Count; r++)
					labelW = Math.Max(labelW, Measure(factory, tfBold, _tfs[r].Label));
				labelW = Math.Max(labelW, Measure(factory, tfBold, "TF")) + 2 * pad;

				float dataW = Measure(factory, tfBold, "RTH");
				dataW = Math.Max(dataW, Measure(factory, tfBold, "ETH"));
				if (ShowRegimeText || ShowPct)
				{
					// worst-case strings: regime word alone, and regime + a 3-digit
					// (possibly negative, possibly >100) pct -- leg pct is unclamped.
					string[] samples = { BULL, BEAR, RANGE, BULL + " -100%", BEAR + " 150%", RANGE + " 100%" };
					foreach (string s in samples)
						dataW = Math.Max(dataW, Measure(factory, tfCenter, s));
				}
				dataW += 2 * pad;

				float rowH   = fs + 2 * pad;
				float totalW = labelW + 2 * dataW;
				float totalH = rowH * (_tfs.Count + 1);   // + header row

				float px = (float)ChartPanel.X, py = (float)ChartPanel.Y;
				float pw = (float)ChartPanel.W, ph = (float)ChartPanel.H;
				float x0, y0;
				switch (Corner)
				{
					case RegimeBoxCorner.TopLeft:     x0 = px + OffsetX;                    y0 = py + OffsetY;                    break;
					case RegimeBoxCorner.BottomLeft:  x0 = px + OffsetX;                    y0 = py + ph - totalH - OffsetY;      break;
					case RegimeBoxCorner.BottomRight: x0 = px + pw - totalW - OffsetX;      y0 = py + ph - totalH - OffsetY;      break;
					default:                    x0 = px + pw - totalW - OffsetX;      y0 = py + OffsetY;                    break; // TopRight
				}

				var textDx   = ToDx(TextBrush);
				var headerDx = ToDx(HeaderBrush);
				var borderDx = ToDx(BorderBrush);
				var bullDx   = ToDx(_bullShade);
				var bearDx   = ToDx(_bearShade);
				var rangeDx  = ToDx(_rangeShade);
				try
				{
					// header row
					float hx1 = x0 + labelW;
					float hx2 = x0 + labelW + dataW;
					RenderTarget.DrawText("TF",  tfBold, Rect(x0,  y0, labelW, rowH), headerDx);
					RenderTarget.DrawText("RTH", tfBold, Rect(hx1, y0, dataW,  rowH), headerDx);
					RenderTarget.DrawText("ETH", tfBold, Rect(hx2, y0, dataW,  rowH), headerDx);

					for (int r = 0; r < _tfs.Count; r++)
					{
						float ry = y0 + rowH * (r + 1);
						RenderTarget.DrawText(_tfs[r].Label, tfBold, Rect(x0, ry, labelW, rowH), textDx);

						DrawCell(r, 0, hx1, ry, dataW, rowH, tfCenter, textDx, bullDx, bearDx, rangeDx);
						DrawCell(r, 1, hx2, ry, dataW, rowH, tfCenter, textDx, bullDx, bearDx, rangeDx);
					}

					if (ShowBorder)
					{
						// outer frame + column separators + header underline
						RenderTarget.DrawRectangle(new RectangleF(x0, y0, totalW, totalH), borderDx, 1f);
						RenderTarget.DrawLine(new Vector2(hx1, y0), new Vector2(hx1, y0 + totalH), borderDx, 1f);
						RenderTarget.DrawLine(new Vector2(hx2, y0), new Vector2(hx2, y0 + totalH), borderDx, 1f);
						RenderTarget.DrawLine(new Vector2(x0, y0 + rowH), new Vector2(x0 + totalW, y0 + rowH), borderDx, 1f);
					}
				}
				finally
				{
					textDx.Dispose(); headerDx.Dispose(); borderDx.Dispose();
					bullDx.Dispose(); bearDx.Dispose(); rangeDx.Dispose();
				}
			}
		}

		private void DrawCell(int row, int col, float x, float y, float w, float h,
			TextFormat tf, D2DSolidColorBrush textDx,
			D2DSolidColorBrush bullDx, D2DSolidColorBrush bearDx, D2DSolidColorBrush rangeDx)
		{
			Cell c = _cells.FirstOrDefault(z => z.Row == row && z.Col == col);
			double reg = (c != null && c.Eng != null) ? c.Eng.CurrentRegime : 0.0;
			var fill = reg > 0 ? bullDx : reg < 0 ? bearDx : rangeDx;
			RenderTarget.FillRectangle(new RectangleF(x, y, w, h), fill);

			if (!ShowRegimeText && !ShowPct) return;
			string txt = ShowRegimeText ? (reg > 0 ? BULL : reg < 0 ? BEAR : RANGE) : "";
			if (ShowPct && c != null && c.Eng != null)
			{
				double pct = c.Eng.CurrentPct;
				if (!double.IsNaN(pct))
					txt += (txt.Length > 0 ? " " : "") + Math.Round(pct).ToString("0") + "%";
			}
			if (txt.Length > 0) RenderTarget.DrawText(txt, tf, Rect(x, y, w, h), textDx);
		}

		private static RectangleF Rect(float x, float y, float w, float h) { return new RectangleF(x, y, w, h); }

		private static float Measure(SharpDX.DirectWrite.Factory factory, TextFormat tf, string s)
		{
			using (var layout = new TextLayout(factory, s ?? "", tf, 4000f, 400f))
				return layout.Metrics.WidthIncludingTrailingWhitespace;
		}

		// ── helpers ─────────────────────────────────────────────────────────────
		private D2DSolidColorBrush ToDx(WMBrush b)
		{
			var scb = b as WMSolidColorBrush;
			WMColor c = scb != null ? scb.Color : Colors.Gray;
			return new D2DSolidColorBrush(RenderTarget, new Color4(c.R / 255f, c.G / 255f, c.B / 255f, c.A / 255f));
		}

		private static void FreezeIf(WMBrush b) { if (b != null && b.CanFreeze && !b.IsFrozen) b.Freeze(); }

		private static WMBrush MakeShade(WMBrush src, int opacityPct)
		{
			var scb = src as WMSolidColorBrush;
			WMColor c = scb != null ? scb.Color : Colors.Gray;
			byte a = (byte)Math.Max(0, Math.Min(255, (int)Math.Round(opacityPct / 100.0 * 255.0)));
			var b = new WMSolidColorBrush(WMColor.FromArgb(a, c.R, c.G, c.B));
			b.Freeze();
			return b;
		}

		private BarsPeriod MakePeriod(TfDef tf)
		{
			return new BarsPeriod { BarsPeriodType = tf.Type, Value = tf.Value };
		}

		// "2000t,5M,15M,60M,240M,D,W" -> list of (type,value,label,intraday).
		// Suffix: t/T=tick, s/S=second, m/M=minute, D=day, W=week. D/W may carry a
		// leading count (e.g. "2D"); default count 1. Bad tokens are skipped.
		private static List<TfDef> ParseTimeframes(string s)
		{
			var outp = new List<TfDef>();
			if (string.IsNullOrWhiteSpace(s)) return outp;
			foreach (string raw in s.Split(new[] { ',', ';' }, StringSplitOptions.RemoveEmptyEntries))
			{
				string t = raw.Trim();
				if (t.Length == 0) continue;
				char suf = t[t.Length - 1];
				string numPart = t.Substring(0, t.Length - 1).Trim();
				int val;
				bool hasNum = int.TryParse(numPart, out val);

				BarsPeriodType type;
				bool intraday;
				switch (char.ToUpperInvariant(suf))
				{
					case 'T': type = BarsPeriodType.Tick;   intraday = true;  if (!hasNum) continue; break;
					case 'S': type = BarsPeriodType.Second; intraday = true;  if (!hasNum) continue; break;
					case 'M': type = BarsPeriodType.Minute; intraday = true;  if (!hasNum) continue; break;
					case 'D': type = BarsPeriodType.Day;    intraday = false; if (!hasNum) val = 1;  break;
					case 'W': type = BarsPeriodType.Week;   intraday = false; if (!hasNum) val = 1;  break;
					default:  continue;
				}
				if (val <= 0) continue;
				outp.Add(new TfDef { Label = t, Type = type, Value = val, Intraday = intraday });
			}
			return outp;
		}

		#region RegimeEngine — self-contained Bull/Bear/Range state machine (one per series)
		// Ported verbatim from RegimeTrackerPanel's inlined logic, parameterized on
		// a single series' Open/High/Low/Close/Time + its own MyWedge child, so it
		// can run independently for each (timeframe x session) data series.
		private class RegimeEngine
		{
			private readonly My.MyWedge _wedge;
			private readonly ISeries<double> _open, _high, _low, _close;
			private readonly TimeSeries      _time;
			private readonly Bars _bars;
			private readonly int  _lag;
			private readonly bool _resetOnSession, _weeklyResetOnly, _sessionSkip;

			private string _trend = RANGE;
			private List<int> _zzIdx, _seqIdx;  private List<char> _zzKind, _seqKind;  private List<double> _zzPrice, _seqPrice;
			private bool   _bosSet;  private double _bosLevel;
			private bool   _legSet;  private double _leg;      private int _legI;
			private bool   _cntSet;  private double _counter;  private int _counterI;
			private bool   _candSet; private double _cand;     private int _candI;
			private int    _prevBarDir;
			private int    _procBar;
			// running range extremes, tracked only while _trend == RANGE (reset
			// fresh every time trend transitions INTO range -- see SetTrend/
			// ResetRegimeState). 0% = _rangeLow, 100% = _rangeHigh.
			private bool   _rangeSet;  private double _rangeHigh, _rangeLow;
			private Data.SessionIterator _sessionIt;
			private DateTime _weekAnchor = DateTime.MinValue;
			private int _cutoffBar = -1;

			public RegimeEngine(My.MyWedge wedge, ISeries<double> open, ISeries<double> high,
				ISeries<double> low, ISeries<double> close, TimeSeries time, Bars bars,
				int lag, bool resetOnSession, bool weeklyResetOnly, bool sessionSkip)
			{
				_wedge = wedge; _open = open; _high = high; _low = low; _close = close; _time = time;
				_bars = bars; _lag = lag; _resetOnSession = resetOnSession;
				_weeklyResetOnly = weeklyResetOnly; _sessionSkip = sessionSkip;

				_zzIdx = new List<int>(); _zzKind = new List<char>(); _zzPrice = new List<double>();
				_seqIdx = new List<int>(); _seqKind = new List<char>(); _seqPrice = new List<double>();
				_sessionIt = new Data.SessionIterator(bars);
			}

			public double CurrentRegime { get { return _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0; } }

			// Position-in-range-or-leg, as a percent, read against the LIVE price
			// (_close[0] -- updates tick-by-tick even under Calculate.OnBarClose,
			// independent of when the forming bar actually closes and registers a
			// new extreme). NaN = not enough state yet (e.g. no counter pivot formed).
			//
			// RANGE: 0% = running range low, 100% = running range high since the
			// range began; CLAMPED to [0,100] (by definition of "where in the range").
			//
			// BULL/BEAR: 0% = the leg's invalidation level (_counter -- the counter-
			// trend swing that, if broken, flips back to RANGE), 100% = the leg's
			// running extreme (_leg -- last HH in a bull, last LL in a bear).
			// UNCLAMPED: >100% means price is live-trading beyond the last
			// registered HH/LL (hasn't been registered as the new extreme yet);
			// <0% means price has pulled back through the invalidation level before
			// the regime flip has been detected/processed.
			public double CurrentPct
			{
				get
				{
					double price = _close[0];
					if (_trend == RANGE)
					{
						if (!_rangeSet || _rangeHigh <= _rangeLow) return double.NaN;
						double p = (price - _rangeLow) / (_rangeHigh - _rangeLow) * 100.0;
						return Math.Max(0.0, Math.Min(100.0, p));
					}
					if (!_legSet || !_cntSet) return double.NaN;
					if (_trend == BULL)
					{
						if (_leg <= _counter) return double.NaN;
						return (price - _counter) / (_leg - _counter) * 100.0;
					}
					// BEAR
					if (_counter <= _leg) return double.NaN;
					return (_counter - price) / (_counter - _leg) * 100.0;
				}
			}

			public void OnBar(int currentBar)
			{
				if (_wedge == null) return;

				if (_sessionSkip && _cutoffBar < 0)
					_cutoffBar = FindCurrentSessionStartBar();

				if (!(_sessionSkip && currentBar < _cutoffBar))
					_wedge.Update();

				while (_procBar <= currentBar - _lag)
				{
					int barsAgo = currentBar - _procBar;
					if (!(_sessionSkip && _procBar < _cutoffBar))
						ProcessBar(_procBar, barsAgo);
					_procBar++;
				}
			}

			private int FindCurrentSessionStartBar()
			{
				if (_bars == null || _bars.Count == 0) return 0;
				var si = new Data.SessionIterator(_bars);
				int lastNewSessionBar = 0;
				for (int b = 0; b < _bars.Count; b++)
				{
					DateTime t = _bars.GetTime(b);
					if (si.IsNewSession(t, true)) { lastNewSessionBar = b; si.GetNextSession(t, true); }
				}
				return lastNewSessionBar;
			}

			private void ProcessBar(int i, int barsAgo)
			{
				if (i > 0 && (_resetOnSession || _sessionSkip))
				{
					DateTime t = _time[barsAgo];
					if (_sessionIt.IsNewSession(t, true))
					{
						DateTime weekStart = t.Date.AddDays(-(int)t.Date.DayOfWeek);
						if (_resetOnSession && (!_weeklyResetOnly || weekStart != _weekAnchor))
						{
							ResetRegimeState();
							_weekAnchor = weekStart;
						}
						if (_sessionSkip && i > _cutoffBar) _cutoffBar = i;
						_sessionIt.GetNextSession(t, true);
					}
				}

				double lp = _low[barsAgo], hp = _high[barsAgo];
				bool isLow  = _wedge.SwingLow.IsValidDataPoint(barsAgo);
				bool isHigh = _wedge.SwingHigh.IsValidDataPoint(barsAgo);

				int barDir = ComputeBarDir(barsAgo);
				_prevBarDir = barDir;
				bool lowFirst = barDir >= 0;

				char[] sides = lowFirst ? new[] { 'L', 'H' } : new[] { 'H', 'L' };
				foreach (char side in sides)
				{
					if (_trend == RANGE)
					{
						if (side == 'H') { var s = EntrySetup('L'); if (s != null && hp > s.RefPrice) Enter(i, BULL, hp); }
						else             { var s = EntrySetup('H'); if (s != null && lp < s.RefPrice) Enter(i, BEAR, lp); }
					}
					else if (_trend == BULL)
					{
						if (side == 'L' && _cntSet && lp < _counter) { _bosSet = false; SetTrend(RANGE); }
						else if (side == 'H' && _bosSet && hp > _bosLevel) Bos(i, hp);
					}
					else // BEAR
					{
						if (side == 'H' && _cntSet && hp > _counter) { _bosSet = false; SetTrend(RANGE); }
						else if (side == 'L' && _bosSet && lp < _bosLevel) Bos(i, lp);
					}
				}

				if (_trend == RANGE)
				{
					if (!_rangeSet) { _rangeHigh = hp; _rangeLow = lp; _rangeSet = true; }
					else
					{
						if (hp > _rangeHigh) _rangeHigh = hp;
						if (lp < _rangeLow)  _rangeLow  = lp;
					}
				}
				else if (_legSet && !_bosSet)
				{
					if (_trend == BULL && hp > _leg) { _leg = hp; _legI = i; }
					else if (_trend == BEAR && lp < _leg) { _leg = lp; _legI = i; }
				}

				var order = new List<KeyValuePair<char, double>>();
				if (isLow && isHigh)
				{
					if (lowFirst) { order.Add(KV('L', lp)); order.Add(KV('H', hp)); }
					else          { order.Add(KV('H', hp)); order.Add(KV('L', lp)); }
				}
				else if (isLow)  order.Add(KV('L', lp));
				else if (isHigh) order.Add(KV('H', hp));

				foreach (var kv in order)
				{
					char kind = kv.Key; double price = kv.Value;
					Push(i, kind, price);
					if (kind == 'L')
					{
						if (_trend == BULL)
						{
							if (!_bosSet && _legSet) { _bosSet = true; _bosLevel = _leg; }
							if (!_candSet || price < _cand) { _cand = price; _candI = i; _candSet = true; }
						}
					}
					else
					{
						if (_trend == BEAR)
						{
							if (!_bosSet && _legSet) { _bosSet = true; _bosLevel = _leg; }
							if (!_candSet || price > _cand) { _cand = price; _candI = i; _candSet = true; }
						}
					}
				}
			}

			private int ComputeBarDir(int barsAgo)
			{
				double o = _open[barsAgo], c = _close[barsAgo], h = _high[barsAgo], l = _low[barsAgo];
				double br = h - l;
				double ibs = br != 0 ? (c - l) / br * 100.0 : 0.0;
				if (c > o && ibs >= 50) return 1;
				if (c < o && ibs <= 50) return -1;
				if (c == o && ibs > 50) return 1;
				if (c == o && ibs < 50) return -1;
				if (c == o && ibs == 50) return _prevBarDir;
				if (c < o && ibs > 50) return 1;
				if (c > o && ibs < 50) return -1;
				if (ibs == 50) return _prevBarDir;
				return _prevBarDir;
			}

			private static KeyValuePair<char, double> KV(char k, double v) { return new KeyValuePair<char, double>(k, v); }

			private void Push(int i, char kind, double price)
			{
				int n = _zzKind.Count;
				if (n > 0 && _zzKind[n - 1] == kind)
				{
					bool moreExtreme = kind == 'H' ? price > _zzPrice[n - 1] : price < _zzPrice[n - 1];
					if (moreExtreme) { _zzIdx[n - 1] = i; _zzPrice[n - 1] = price; }
				}
				else { _zzIdx.Add(i); _zzKind.Add(kind); _zzPrice.Add(price); }
			}

			private List<KeyValuePair<int, double>> Tips(char kind, int count)
			{
				var outp = new List<KeyValuePair<int, double>>();
				for (int j = _zzKind.Count - 1; j >= 0; j--)
					if (_zzKind[j] == kind)
					{
						outp.Add(new KeyValuePair<int, double>(_zzIdx[j], _zzPrice[j]));
						if (outp.Count == count) break;
					}
				return outp;
			}

			private static bool Extends(List<char> sKind, List<double> sPrice, char kind, double price)
			{
				for (int j = sKind.Count - 1; j >= 0; j--)
					if (sKind[j] == kind)
						return kind == 'H' ? price > sPrice[j] : price < sPrice[j];
				return true;
			}

			private void Swings(List<int> oIdx, List<char> oKind, List<double> oPrice)
			{
				oIdx.Clear(); oKind.Clear(); oPrice.Clear();
				for (int t = 0; t < _zzKind.Count; t++)
				{
					int idx = _zzIdx[t]; char k = _zzKind[t]; double price = _zzPrice[t];
					bool pair = t + 1 < _zzKind.Count && _zzIdx[t + 1] == idx && _zzKind[t + 1] != k;
					if (pair && !(Extends(oKind, oPrice, k, price)
					           && Extends(oKind, oPrice, _zzKind[t + 1], _zzPrice[t + 1])))
						continue;
					int n = oKind.Count;
					if (n > 0 && oKind[n - 1] == k)
					{
						bool moreExtreme = k == 'H' ? price > oPrice[n - 1] : price < oPrice[n - 1];
						if (moreExtreme) { oIdx[n - 1] = idx; oPrice[n - 1] = price; }
					}
					else { oIdx.Add(idx); oKind.Add(k); oPrice.Add(price); }
				}
			}

			private class Setup { public int CounterBar; public double CounterPrice; public int RefBar; public double RefPrice; }

			private Setup EntrySetup(char kind)
			{
				Swings(_seqIdx, _seqKind, _seqPrice);
				var pos = new List<int>();
				for (int j = 0; j < _seqKind.Count; j++) if (_seqKind[j] == kind) pos.Add(j);
				if (pos.Count < 2 || pos[pos.Count - 1] == 0) return null;
				int j2 = pos[pos.Count - 1];
				double lastPrice = _seqPrice[j2], prevPrice = _seqPrice[pos[pos.Count - 2]];
				bool sloped = kind == 'H' ? lastPrice < prevPrice : lastPrice > prevPrice;
				if (!sloped) return null;
				int refIdx = j2 - 1;
				if (_seqKind[refIdx] == kind) return null;
				return new Setup { CounterBar = _seqIdx[j2], CounterPrice = lastPrice, RefBar = _seqIdx[refIdx], RefPrice = _seqPrice[refIdx] };
			}

			private void Enter(int i, string newTrend, double level)
			{
				var t = Tips(newTrend == BULL ? 'L' : 'H', 1);
				if (t.Count > 0) { _counterI = t[0].Key; _counter = t[0].Value; _cntSet = true; }
				_bosSet = false;
				_leg = level; _legI = i; _legSet = true;
				_candSet = false;
				SetTrend(newTrend);
			}

			private void Bos(int i, double level)
			{
				if (_candSet) { _counter = _cand; _counterI = _candI; _cntSet = true; }
				_bosSet = false;
				_leg = level; _legI = i; _legSet = true;
				_candSet = false;
			}

			private void SetTrend(string newTrend)
			{
				_trend = newTrend;
				if (newTrend == RANGE) _rangeSet = false;   // fresh range envelope starts next ProcessBar
			}

			private void ResetRegimeState()
			{
				_trend = RANGE;
				_zzIdx.Clear(); _zzKind.Clear(); _zzPrice.Clear();
				_seqIdx.Clear(); _seqKind.Clear(); _seqPrice.Clear();
				_bosSet = false; _legSet = false; _cntSet = false; _candSet = false;
				_rangeSet = false;
				_prevBarDir = 0;
			}
		}
		#endregion

		#region Properties
		[NinjaScriptProperty]
		[Display(Name = "Timeframes (comma list: t/s/M/D/W)", GroupName = "1 Timeframes", Order = 0)]
		public string Timeframes { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "RTH trading-hours template", GroupName = "1 Timeframes", Order = 1)]
		public string RthTemplate { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ETH trading-hours template", GroupName = "1 Timeframes", Order = 2)]
		public string EthTemplate { get; set; }

		[NinjaScriptProperty] [Range(50, 10000)]
		[Display(Name = "Intraday bars to load (tick/sec/min only; ignored for D/W)", GroupName = "1 Timeframes", Order = 3)]
		public int IntradayBarsToLoad { get; set; }

		[NinjaScriptProperty] [Range(0, 20)]
		[Display(Name = "Lag (bars, pivot finality)", GroupName = "2 Regime", Order = 0)] public int Lag { get; set; }
		[NinjaScriptProperty] [Display(Name = "Reset on new session (intraday only)", GroupName = "2 Regime", Order = 1)] public bool ResetOnNewSession { get; set; }
		[NinjaScriptProperty] [Display(Name = "Weekly reset only (Sunday ETH start)", GroupName = "2 Regime", Order = 2)] public bool WeeklyResetOnly { get; set; }
		[NinjaScriptProperty] [Display(Name = "Only calculate current session (cheaper; intraday only)", GroupName = "2 Regime", Order = 3)] public bool CurrentSessionOnly { get; set; }

		[NinjaScriptProperty] [Range(1, 10000)] [Display(Name = "LookBack", GroupName = "3 MyWedge", Order = 0)] public int LookBack { get; set; }
		[NinjaScriptProperty] [Display(Name = "ShowW2L", GroupName = "3 MyWedge", Order = 1)] public bool ShowW2L { get; set; }
		[NinjaScriptProperty] [Range(0, 10000)] [Display(Name = "WedgeSymmetry", GroupName = "3 MyWedge", Order = 2)] public int WedgeSymmetry { get; set; }
		[NinjaScriptProperty] [Range(1, 10000)] [Display(Name = "OLSensitivity", GroupName = "3 MyWedge", Order = 3)] public int OLSensitivity { get; set; }
		[NinjaScriptProperty] [Display(Name = "CTSB_Ignore", GroupName = "3 MyWedge", Order = 4)] public bool CTSB_Ignore { get; set; }
		[NinjaScriptProperty] [Display(Name = "IB_Ignore", GroupName = "3 MyWedge", Order = 5)] public bool IB_Ignore { get; set; }
		[NinjaScriptProperty] [Display(Name = "ShowWedgeSB", GroupName = "3 MyWedge", Order = 6)] public bool ShowWedgeSB { get; set; }
		[NinjaScriptProperty] [Display(Name = "SignalBarIBS", GroupName = "3 MyWedge", Order = 7)] public double SignalBarIBS { get; set; }
		[NinjaScriptProperty] [Display(Name = "ContinueMC", GroupName = "3 MyWedge", Order = 8)] public bool ContinueMC { get; set; }
		[NinjaScriptProperty] [Display(Name = "ContinueOnGap", GroupName = "3 MyWedge", Order = 9)] public bool ContinueOnGap { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Corner", GroupName = "4 Box", Order = 0)] public RegimeBoxCorner Corner { get; set; }
		[NinjaScriptProperty] [Range(0, 5000)] [Display(Name = "Offset X (px)", GroupName = "4 Box", Order = 1)] public int OffsetX { get; set; }
		[NinjaScriptProperty] [Range(0, 5000)] [Display(Name = "Offset Y (px)", GroupName = "4 Box", Order = 2)] public int OffsetY { get; set; }
		[NinjaScriptProperty] [Range(6, 72)] [Display(Name = "Font size", GroupName = "4 Box", Order = 3)] public int FontSize { get; set; }
		[NinjaScriptProperty] [Range(0, 40)] [Display(Name = "Cell padding (px)", GroupName = "4 Box", Order = 4)] public int CellPadding { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show regime text in cells", GroupName = "4 Box", Order = 5)] public bool ShowRegimeText { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show % in cells (range: 0%=low,100%=high; leg: 0%=invalidation,100%=last HH/LL, can exceed)", GroupName = "4 Box", Order = 8)] public bool ShowPct { get; set; }
		[NinjaScriptProperty] [Range(100, 5000)] [Display(Name = "% refresh interval (ms, only runs while Show % is on)", GroupName = "4 Box", Order = 9)] public int RenderIntervalMs { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show border", GroupName = "4 Box", Order = 6)] public bool ShowBorder { get; set; }
		[NinjaScriptProperty] [Range(0, 100)] [Display(Name = "Cell opacity %", GroupName = "4 Box", Order = 7)] public int CellOpacity { get; set; }

		[XmlIgnore] [Display(Name = "Bull color", GroupName = "5 Colors", Order = 0)] public WMBrush BullBrush { get; set; }
		[Browsable(false)] public string BullBrushSerialize { get { return Serialize.BrushToString(BullBrush); } set { BullBrush = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Bear color", GroupName = "5 Colors", Order = 1)] public WMBrush BearBrush { get; set; }
		[Browsable(false)] public string BearBrushSerialize { get { return Serialize.BrushToString(BearBrush); } set { BearBrush = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Range color", GroupName = "5 Colors", Order = 2)] public WMBrush RangeBrush { get; set; }
		[Browsable(false)] public string RangeBrushSerialize { get { return Serialize.BrushToString(RangeBrush); } set { RangeBrush = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Cell text color", GroupName = "5 Colors", Order = 3)] public WMBrush TextBrush { get; set; }
		[Browsable(false)] public string TextBrushSerialize { get { return Serialize.BrushToString(TextBrush); } set { TextBrush = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Header text color", GroupName = "5 Colors", Order = 4)] public WMBrush HeaderBrush { get; set; }
		[Browsable(false)] public string HeaderBrushSerialize { get { return Serialize.BrushToString(HeaderBrush); } set { HeaderBrush = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Border color", GroupName = "5 Colors", Order = 5)] public WMBrush BorderBrush { get; set; }
		[Browsable(false)] public string BorderBrushSerialize { get { return Serialize.BrushToString(BorderBrush); } set { BorderBrush = Serialize.StringToBrush(value); } }
		#endregion
	}
}
