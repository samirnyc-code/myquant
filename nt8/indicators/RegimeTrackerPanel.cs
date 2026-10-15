#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Windows.Media;
using System.Windows.Threading;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// ── RegimeTrackerPanel ───────────────────────────────────────────────────
	// Sub-panel companion to RegimeTrackerV2: draws ONLY the Bull/Bear/Range
	// classification, as a colored band in its own panel below the chart -- no
	// pivot dots, no BOS/ChoCh labels, no price-panel shading.
	//
	// MULTI-TIMEFRAME (ported from RegimeTrackerBox): leave Timeframe blank to
	// classify the chart's OWN bars (original behavior, unchanged). Set
	// Timeframe (e.g. "5M") to classify a DIFFERENT timeframe instead -- this
	// calls AddDataSeries INTERNALLY (same mechanism RegimeTrackerBox uses for
	// its dashboard rows), so the added series is never shown in the chart's own
	// Data Series list and never plots its own candles -- the chart's primary
	// bars (e.g. a 2000-tick series) are completely untouched. The band is still
	// painted across the PRIMARY chart's bars: whichever regime the higher
	// (or lower) timeframe last closed in gets carried forward onto every
	// primary bar until that series' next bar closes with a different regime --
	// exactly like reading a 5M regime off a 5M chart while actually trading
	// off a 2000-tick one.
	//
	// SELF-CONTAINED, NOT a wrapper around a hidden RegimeTrackerV2 child -- see
	// the ARCHITECTURE note on RegimeEngine below for why.
	public class RegimeTrackerPanel : Indicator
	{
		private const string BULL = "Bull", BEAR = "Bear", RANGE = "Range";

		// bar index (on the PRIMARY series, bip 0) -> Regime value, painted
		// full-panel-height in OnRender (same technique as RegimeTrackerV2's
		// price-panel shading, just filling this panel's whole height instead of
		// the price range) so bars sit edge-to-edge as one solid band instead of
		// NT8's native Bar plot style (which splits +/- around a zero line and
		// leaves gaps between bars). Always keyed by the PRIMARY bar index even
		// when the engine itself is driven by an added (e.g. 5M) series, so the
		// band always aligns with the chart's own x-axis.
		private Dictionary<int, double> _barRegime;

		// ShadeOpacity-adjusted brushes actually used for painting (same ARGB-alpha
		// technique as RegimeTrackerV2.MakeShade); the raw BullBrush/BearBrush/
		// TransitionBrush properties stay fully opaque so the color pickers show
		// the true color.
		private Brush _bullShade, _bearShade, _transShade;

		private RegimeEngine _engine;
		private int          _engineBip;   // 0 = chart's own primary series; 1 = the added Timeframe series

		// diagnostic-only: catches any exception in OnBarUpdate/OnRender and writes it
		// here instead of letting it vanish -- added after the panel was observed going
		// blank with NOTHING in NT8's own Control Center Log, so whatever's failing
		// (if anything still is) is visible here even when NT8 doesn't surface it.
		private string _errPath;

		// diagnostic-only: continuous CSV state log (same pattern as
		// RegimeTrackerBox's own DebugLog) -- written in the background regardless
		// of whether anyone is watching the chart at the moment it goes blank, so
		// there's nothing to "catch in the act" on screen. One row per OnBarUpdate
		// call plus a throttled heartbeat row from OnRender (so a stop in OnRender
		// itself being CALLED shows up as a gap in timestamps, not just missing data).
		private long _bip0Calls, _bip1Calls;
		private List<string> _debugRows;
		private string       _debugPath;
		private int          _debugFlushedCount;
		private DispatcherTimer _debugFlushTimer;
		private readonly object _debugLock = new object();
		private DateTime _lastRenderLogUtc = DateTime.MinValue;

		private struct TfDef { public BarsPeriodType Type; public int Value; public bool Intraday; }

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Regime (Bull/Bear/Range) classification, same logic as RegimeTrackerV2, plotted as a colored band in its own panel -- no pivots/events/price overlay. Timeframe (blank = chart's own bars) lets the band classify a DIFFERENT timeframe via an internal AddDataSeries, without adding a visible data series to the chart.";
				Name        = "RegimeTrackerPanel";
				Calculate   = Calculate.OnBarClose;
				IsOverlay   = false;
				IsSuspendedWhileInactive = false;

				Timeframe           = "";
				Template            = "CME US Index Futures ETH";
				IntradayBarsToLoad  = 1000;
				DaysToLoad          = 365;
				DebugLog            = false;

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
				Lag           = 0;
				ResetOnNewSession  = true;
				WeeklyResetOnly    = false;
				CurrentSessionOnly = true;    // default ON: skip historical calc (O(n^2) swing rescan over the full lookback) — the 37.6s Utilization cost.
				IncludePriorSession = true;   // with CurrentSessionOnly: compute the last TWO sessions continuously (no reset between) so the current session inherits the prior session's ending regime (ETH 17:00 continues the 16:00 regime; RTH = continue from yesterday).

				BullBrush       = Brushes.SeaGreen;
				BearBrush       = Brushes.IndianRed;
				TransitionBrush = Brushes.Gold;
				ShadeOpacity    = 100;   // solid band by default -- this panel IS the content, nothing to see through

				// kept only so the panel has a non-degenerate Y-range for OnRender's
				// chartScale.MaxValue/MinValue math and so Regime is readable from the
				// Data Box / exported -- rendered transparent, the band itself is
				// custom-painted in OnRender.
				AddPlot(new Stroke(Brushes.Transparent, 1), PlotStyle.Line, "Regime");
			}
			else if (State == State.Configure)
			{
				_errPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
					string.Format("regime_tracker_panel_errors_{0}.log", Instrument != null ? Instrument.MasterInstrument.Name : "unknown"));

				FreezeIf(BullBrush); FreezeIf(BearBrush); FreezeIf(TransitionBrush);
				_bullShade  = MakeShade(BullBrush, ShadeOpacity);
				_bearShade  = MakeShade(BearBrush, ShadeOpacity);
				_transShade = MakeShade(TransitionBrush, ShadeOpacity);

				try
				{
					TfDef tf;
					if (TryParseTimeframe(Timeframe, out tf))
					{
						int bars;
						bool? resetArg;
						if (tf.Intraday)
						{
							// CONFIRMED via the debug CSV: the barsBack count passed to
							// AddDataSeries is NOT just an initial-history request -- NT8
							// caps the added series' TOTAL lifetime bar count at this number.
							// Once hit, the series stops accepting new real-time bars
							// entirely (bip1Calls froze dead while bip0Calls kept climbing,
							// identically in two separate runs regardless of RTH/ETH). A
							// Panel instance has to keep extending for as long as the chart
							// stays open, so floor this WAY above IntradayBarsToLoad's
							// user-facing value -- 200000 5-minute bars is ~2 years of
							// continuous 24/7 bars, comfortably beyond any realistic
							// between-reload lifetime, at negligible memory cost.
							bars = Math.Max(200000, IntradayBarsToLoad);
							resetArg = ResetOnNewSession;
						}
						else
						{
							// AddDataSeries only accepts a BAR count -- convert DaysToLoad
							// (calendar days, matches a normal NT8 Data Series dialog) per
							// period type: ~260 Daily bars, ~52 Weekly bars for 365 days.
							bars = tf.Type == BarsPeriodType.Week
								? Math.Max(10, (int)Math.Ceiling(DaysToLoad / 7.0))
								: Math.Max(10, (int)Math.Ceiling(DaysToLoad * 260.0 / 365.0));
							resetArg = null;   // use NT8's own default, matches RegimeTrackerBox
						}
						// every AddDataSeries call elsewhere in this codebase (RegimeTrackerBox)
						// always passes a real trading-hours template string, never null -- and
						// specifically NEVER defaults to RTH: RegimeTrackerBox's own comments
						// (and this exact symptom, confirmed via the debug CSV -- bip1 stopped
						// advancing at a fixed bar while bip0 kept ticking) document that an
						// RTH-templated intraday series STALLS once RTH closes for the day,
						// while ETH keeps advancing through the evening/overnight session.
						string template = string.IsNullOrWhiteSpace(Template) ? "CME US Index Futures ETH" : Template;
						AddDataSeries(Instrument.FullName, new BarsPeriod { BarsPeriodType = tf.Type, Value = tf.Value }, bars, template, resetArg);
						_engineBip = 1;
					}
					else
					{
						_engineBip = 0;   // blank/invalid Timeframe -> classify the chart's own bars (unchanged default behavior)
					}
				}
				catch (Exception ex) { LogError("Configure AddDataSeries Timeframe=" + Timeframe, ex); _engineBip = 0; }
			}
			else if (State == State.DataLoaded)
			{
				_barRegime = new Dictionary<int, double>();

				_debugRows = new List<string>();
				_debugPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
					string.Format("regime_tracker_panel_debug_{0}.csv", Instrument != null ? Instrument.MasterInstrument.Name : "unknown"));
				if (DebugLog)
					_debugRows.Add("WallClock,Source,BarsInProgress,CurrentBar,EngineBip,CurrentRegime,BarRegimeCount,ChartBarsNull,BarsNull,RenderTargetNull,Bip0Calls,Bip1Calls,Note");

				My.MyWedge wedge = MyWedge(Closes[_engineBip], LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);

				_engine = new RegimeEngine(wedge, Opens[_engineBip], Highs[_engineBip], Lows[_engineBip],
					Closes[_engineBip], Times[_engineBip], BarsArray[_engineBip], Lag, ResetOnNewSession,
					WeeklyResetOnly, CurrentSessionOnly, IncludePriorSession);
			}
			else if (State == State.Realtime)
			{
				// initial write as soon as historical catch-up finishes, so the file
				// is readable immediately without waiting for a live bar (same
				// pattern as RegimeTrackerBox's own DebugLog).
				FlushDebugCsv();
				if (DebugLog && ChartControl != null)
				{
					ChartControl.Dispatcher.InvokeAsync(() =>
					{
						_debugFlushTimer = new DispatcherTimer(DispatcherPriority.Background, ChartControl.Dispatcher);
						_debugFlushTimer.Interval = TimeSpan.FromSeconds(2);
						_debugFlushTimer.Tick += (s, e) => FlushDebugCsv();
						_debugFlushTimer.Start();
					});
				}
			}
			else if (State == State.Terminated)
			{
				FlushDebugCsv();   // final flush
				if (ChartControl != null)
				{
					ChartControl.Dispatcher.InvokeAsync(() =>
					{
						if (_debugFlushTimer != null) { _debugFlushTimer.Stop(); _debugFlushTimer = null; }
					});
				}
			}
		}

		private void LogDebug(string source, string note)
		{
			if (!DebugLog || _debugRows == null) return;
			string row = string.Format("{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12}",
				DateTime.Now, source, BarsInProgress, CurrentBar, _engineBip,
				_engine != null ? _engine.CurrentRegime.ToString("0.0") : "",
				_barRegime != null ? _barRegime.Count.ToString() : "",
				ChartBars == null ? "1" : "0", Bars == null ? "1" : "0", RenderTarget == null ? "1" : "0",
				_bip0Calls, _bip1Calls, note);
			lock (_debugLock) { _debugRows.Add(row); }
		}

		private void FlushDebugCsv()
		{
			if (!DebugLog || _debugRows == null || _debugPath == null) return;
			List<string> snapshot;
			lock (_debugLock)
			{
				if (_debugRows.Count <= 1 || _debugRows.Count == _debugFlushedCount) return;
				snapshot = new List<string>(_debugRows);
				_debugFlushedCount = _debugRows.Count;
			}
			try { File.WriteAllLines(_debugPath, snapshot); }
			catch { }
		}

		// Suffix: t/T=tick, s/S=second, m/M=minute, D=day, W=week (case-insensitive).
		// T/S/M require a numeric prefix (e.g. "5M"); D/W default to 1 if bare.
		// Blank or unrecognized input returns false (chart's own bars).
		private static bool TryParseTimeframe(string s, out TfDef tf)
		{
			tf = default(TfDef);
			if (string.IsNullOrWhiteSpace(s)) return false;
			string t = s.Trim();
			char suf = t[t.Length - 1];
			string numPart = t.Substring(0, t.Length - 1).Trim();
			int val;
			bool hasNum = int.TryParse(numPart, out val);

			switch (char.ToUpperInvariant(suf))
			{
				case 'T': tf.Type = BarsPeriodType.Tick;   tf.Intraday = true;  if (!hasNum) return false; break;
				case 'S': tf.Type = BarsPeriodType.Second; tf.Intraday = true;  if (!hasNum) return false; break;
				case 'M': tf.Type = BarsPeriodType.Minute; tf.Intraday = true;  if (!hasNum) return false; break;
				case 'D': tf.Type = BarsPeriodType.Day;    tf.Intraday = false; val = hasNum ? val : 1;    break;
				case 'W': tf.Type = BarsPeriodType.Week;   tf.Intraday = false; val = hasNum ? val : 1;    break;
				default:  return false;
			}
			if (val <= 0) return false;
			tf.Value = val;
			return true;
		}

		private void LogError(string where, Exception ex)
		{
			try
			{
				if (_errPath == null) return;
				string row = string.Format("{0:yyyy-MM-dd HH:mm:ss.fff},{1},bip={2},{3},{4}\r\n",
					DateTime.Now, where, BarsInProgress, ex.GetType().Name, ex.Message.Replace(",", ";").Replace("\r", " ").Replace("\n", " "));
				File.AppendAllText(_errPath, row);
			}
			catch { }   // diagnostic logging must never itself throw
		}

		private static void FreezeIf(Brush b) { if (b != null && b.CanFreeze && !b.IsFrozen) b.Freeze(); }

		private static Brush MakeShade(Brush src, int opacityPct)
		{
			var scb = src as SolidColorBrush;
			Color c = scb != null ? scb.Color : Colors.Gray;
			byte a = (byte)Math.Max(0, Math.Min(255, (int)Math.Round(opacityPct / 100.0 * 255.0)));
			var b = new SolidColorBrush(Color.FromArgb(a, c.R, c.G, c.B));
			b.Freeze();
			return b;
		}

		protected override void OnBarUpdate()
		{
			if (_engine == null) return;

			try
			{
				if (BarsInProgress == _engineBip)
					_engine.OnBar(CurrentBar);

				if (BarsInProgress == 0) _bip0Calls++;
				if (BarsInProgress == 1) _bip1Calls++;

				// always snapshot keyed by the PRIMARY bar (bip 0) so the band renders
				// aligned to the chart's own x-axis, whichever series actually drives
				// the engine. Unconditional (no HasProcessed gate): CurrentRegime
				// defaults validly to 0.0 (Range) even before the engine has processed
				// its first bar, so every primary bar always gets an entry -- an
				// earlier gated version left gaps (entries missing under
				// CurrentSessionOnly's session-skip) that read as the panel "going
				// blank" as the chart scrolled past the lucky bars that DID get written.
				if (BarsInProgress == 0)
				{
					double r = _engine.CurrentRegime;
					Values[0][0] = r;
					_barRegime[CurrentBar] = r;
				}

				LogDebug("OnBarUpdate", "");
			}
			catch (Exception ex) { LogError("OnBarUpdate CurrentBar=" + CurrentBar, ex); }
		}

		// paints one full-panel-height, edge-to-edge rectangle per bar -- a solid
		// band with no zero-line split and no gaps, unlike NT8's native Bar plot style.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (RenderTarget == null) return;

			// throttled heartbeat row -- written BEFORE the null-guards below so a
			// gap in these timestamps (or a guard tripping) shows up in the CSV even
			// if OnRender stops being called/succeeding altogether, not just missing data.
			if (DebugLog && (DateTime.UtcNow - _lastRenderLogUtc).TotalSeconds >= 1)
			{
				_lastRenderLogUtc = DateTime.UtcNow;
				LogDebug("OnRender", ChartBars == null ? "ChartBars NULL" : Bars == null ? "Bars NULL" : "");
			}

			if (ChartBars == null || Bars == null || _barRegime == null) return;

			var bullDx = _bullShade.ToDxBrush(RenderTarget);
			var bearDx = _bearShade.ToDxBrush(RenderTarget);
			var transDx = _transShade.ToDxBrush(RenderTarget);
			try
			{
				int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
				float yTop = chartScale.GetYByValue(chartScale.MaxValue);
				float yBot = chartScale.GetYByValue(chartScale.MinValue);

				int lastBar = Bars.Count - 1;
				for (int bi = Math.Max(0, from); bi <= to && bi < Bars.Count; bi++)
				{
					double r;
					if (!_barRegime.TryGetValue(bi, out r))
					{
						// the currently-forming bar (not yet closed -> never got an
						// OnBarUpdate call -> never got a _barRegime entry) would
						// otherwise be a permanent unpainted gap at the live edge --
						// most visible when zoomed in close, which is exactly where
						// the user is actually watching. Fall back to the engine's
						// live CurrentRegime for ONLY that one bar instead of skipping it.
						if (bi != lastBar || _engine == null) continue;
						r = _engine.CurrentRegime;
					}

					float x = chartControl.GetXByBarIndex(ChartBars, bi);
					float xNext = bi < to ? chartControl.GetXByBarIndex(ChartBars, bi + 1)
					                      : x + (bi > 0 ? x - chartControl.GetXByBarIndex(ChartBars, bi - 1) : 6f);
					float w = Math.Max(1f, xNext - x);
					var brush = r > 0 ? bullDx : r < 0 ? bearDx : transDx;
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x - w / 2f, yTop, w, yBot - yTop), brush);
				}
			}
			catch (Exception ex) { LogError("OnRender", ex); }
			finally { bullDx.Dispose(); bearDx.Dispose(); transDx.Dispose(); }
		}

		#region RegimeEngine — self-contained Bull/Bear/Range state machine
		// ARCHITECTURE: parameterized on a single series' Open/High/Low/Close/Time
		// + its own MyWedge child, so it can be bound to EITHER the chart's own
		// primary series (bip 0, default) OR an internally-added series (bip 1,
		// when Timeframe is set) without duplicating this logic. This is the same
		// shape RegimeTrackerBox uses to run many of these in parallel -- see that
		// file's ARCHITECTURE note for why a deeper nested-indicator-child wrapper
		// does NOT work (a first attempt at wrapping RegimeTrackerV2 as a hidden
		// child got stuck at State.DataLoaded, CurrentBar=-1 forever).
		//
		// NOTE this version is NOT identical to RegimeTrackerBox's RegimeEngine --
		// it additionally supports IncludePriorSession (continuous current+prior
		// session regime, no reset at the boundary), which Box's dashboard rows
		// don't need but this panel's existing default behavior depends on.
		private class RegimeEngine
		{
			private readonly My.MyWedge _wedge;
			private readonly ISeries<double> _open, _high, _low, _close;
			private readonly TimeSeries _time;
			private readonly Bars _bars;
			private readonly int _lag;
			private readonly bool _resetOnSession, _weeklyResetOnly, _sessionSkip, _includePriorSession;

			private string _trend = RANGE;
			private List<int> _zzIdx, _seqIdx;  private List<char> _zzKind, _seqKind;  private List<double> _zzPrice, _seqPrice;
			private bool   _bosSet;  private double _bosLevel;
			private bool   _legSet;  private double _leg;      private int _legI;
			private bool   _cntSet;  private double _counter;  private int _counterI;
			private bool   _candSet; private double _cand;     private int _candI;
			private int    _prevBarDir;
			private int    _procBar;
			private Data.SessionIterator _sessionIt;
			private DateTime _weekAnchor = DateTime.MinValue;
			private int _cutoffBar = -1;

			public double CurrentRegime { get; private set; }

			public RegimeEngine(My.MyWedge wedge, ISeries<double> open, ISeries<double> high, ISeries<double> low,
				ISeries<double> close, TimeSeries time, Bars bars, int lag, bool resetOnSession, bool weeklyResetOnly,
				bool sessionSkip, bool includePriorSession)
			{
				_wedge = wedge; _open = open; _high = high; _low = low; _close = close; _time = time; _bars = bars;
				_lag = lag; _resetOnSession = resetOnSession; _weeklyResetOnly = weeklyResetOnly;
				_sessionSkip = sessionSkip; _includePriorSession = includePriorSession;

				_zzIdx  = new List<int>();  _zzKind  = new List<char>();  _zzPrice  = new List<double>();
				_seqIdx = new List<int>();  _seqKind = new List<char>();  _seqPrice = new List<double>();
				_sessionIt = new Data.SessionIterator(bars);
			}

			public void OnBar(int currentBar)
			{
				if (_wedge == null) return;

				if (_sessionSkip && _cutoffBar < 0)
					_cutoffBar = FindSessionStartBar(_includePriorSession ? 1 : 0);

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

			// Start bar of the session `sessionsBack` sessions before the current (last) one.
			// 0 = current session start; 1 = prior session start (so current+prior get computed).
			private int FindSessionStartBar(int sessionsBack)
			{
				if (_bars == null || _bars.Count == 0) return 0;
				var si = new Data.SessionIterator(_bars);
				var starts = new List<int>();
				for (int b = 0; b < _bars.Count; b++)
				{
					DateTime t = _bars.GetTime(b);
					if (si.IsNewSession(t, true))
					{
						starts.Add(b);
						si.GetNextSession(t, true);
					}
				}
				if (starts.Count == 0) return 0;
				int idx = starts.Count - 1 - Math.Max(0, sessionsBack);
				return idx < 0 ? 0 : starts[idx];
			}

			private void ProcessBar(int i, int barsAgo)
			{
				if (i > 0 && (_resetOnSession || _sessionSkip))
				{
					DateTime t = _time[barsAgo];
					if (_sessionIt.IsNewSession(t, true))
					{
						// "Current + prior session" mode (_sessionSkip + _includePriorSession)
						// runs the two sessions as ONE continuous stretch: never reset at the
						// session boundary, and never advance the cutoff past the prior-session
						// start — that's what carries the prior regime into the current session.
						bool continuous = _sessionSkip && _includePriorSession;
						DateTime weekStart = t.Date.AddDays(-(int)t.Date.DayOfWeek);
						if (!continuous && _resetOnSession && (!_weeklyResetOnly || weekStart != _weekAnchor))
						{
							ResetRegimeState();
							_weekAnchor = weekStart;
						}
						if (_sessionSkip && !_includePriorSession && i > _cutoffBar)
							_cutoffBar = i;
						_sessionIt.GetNextSession(t, true);
					}
				}

				double lp = _low[barsAgo], hp = _high[barsAgo];
				bool isLow  = _wedge.SwingLow.IsValidDataPoint(barsAgo);
				bool isHigh = _wedge.SwingHigh.IsValidDataPoint(barsAgo);

				int barDir  = ComputeBarDir(barsAgo);
				_prevBarDir = barDir;
				bool lowFirst = barDir >= 0;

				char[] sides = lowFirst ? new[] { 'L', 'H' } : new[] { 'H', 'L' };

				foreach (char side in sides)
				{
					if (_trend == RANGE)
					{
						if (side == 'H')
						{
							var s = EntrySetup('L');
							if (s != null && hp > s.RefPrice) Enter(i, BULL, hp);
						}
						else
						{
							var s = EntrySetup('H');
							if (s != null && lp < s.RefPrice) Enter(i, BEAR, lp);
						}
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

				if (_legSet && !_bosSet)
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

				CurrentRegime = _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0;
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
				{
					if (_zzKind[j] == kind)
					{
						outp.Add(new KeyValuePair<int, double>(_zzIdx[j], _zzPrice[j]));
						if (outp.Count == count) break;
					}
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

			private void SetTrend(string newTrend) { _trend = newTrend; }

			private void ResetRegimeState()
			{
				_trend = RANGE;
				_zzIdx.Clear();  _zzKind.Clear();  _zzPrice.Clear();
				_seqIdx.Clear(); _seqKind.Clear(); _seqPrice.Clear();
				_bosSet = false; _legSet = false; _cntSet = false; _candSet = false;
				_prevBarDir = 0;
			}
		}
		#endregion

		#region Properties
		[NinjaScriptProperty]
		[Display(Name = "Timeframe (blank = chart's own bars; else t/s/M/D/W e.g. 5M)", GroupName = "Timeframe", Order = 0)]
		public string Timeframe { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Trading hours template (blank = ETH; RTH will STALL after RTH closes for the day -- only used when Timeframe is set)", GroupName = "Timeframe", Order = 1)]
		public string Template { get; set; }

		[NinjaScriptProperty] [Range(50, 10000)]
		[Display(Name = "Intraday bars to load (tick/sec/min only; floored at 200000 internally -- this value also caps the series' LIFETIME bar count, not just initial history)", GroupName = "Timeframe", Order = 2)]
		public int IntradayBarsToLoad { get; set; }

		[NinjaScriptProperty] [Range(14, 7300)]
		[Display(Name = "Daily/Weekly days to load (D/W only, calendar days)", GroupName = "Timeframe", Order = 3)]
		public int DaysToLoad { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Debug log (writes Documents\\regime_tracker_panel_debug_<instrument>.csv -- investigative only)", GroupName = "Timeframe", Order = 4)]
		public bool DebugLog { get; set; }

		[NinjaScriptProperty] [Range(1, 10000)]
		[Display(Name = "LookBack", GroupName = "MyWedge", Order = 0)] public int LookBack { get; set; }
		[NinjaScriptProperty] [Display(Name = "ShowW2L", GroupName = "MyWedge", Order = 1)] public bool ShowW2L { get; set; }
		[NinjaScriptProperty] [Range(0, 10000)] [Display(Name = "WedgeSymmetry", GroupName = "MyWedge", Order = 2)] public int WedgeSymmetry { get; set; }
		[NinjaScriptProperty] [Range(1, 10000)] [Display(Name = "OLSensitivity", GroupName = "MyWedge", Order = 3)] public int OLSensitivity { get; set; }
		[NinjaScriptProperty] [Display(Name = "CTSB_Ignore", GroupName = "MyWedge", Order = 4)] public bool CTSB_Ignore { get; set; }
		[NinjaScriptProperty] [Display(Name = "IB_Ignore", GroupName = "MyWedge", Order = 5)] public bool IB_Ignore { get; set; }
		[NinjaScriptProperty] [Display(Name = "ShowWedgeSB", GroupName = "MyWedge", Order = 6)] public bool ShowWedgeSB { get; set; }
		[NinjaScriptProperty] [Display(Name = "SignalBarIBS", GroupName = "MyWedge", Order = 7)] public double SignalBarIBS { get; set; }
		[NinjaScriptProperty] [Display(Name = "ContinueMC", GroupName = "MyWedge", Order = 8)] public bool ContinueMC { get; set; }
		[NinjaScriptProperty] [Display(Name = "ContinueOnGap", GroupName = "MyWedge", Order = 9)] public bool ContinueOnGap { get; set; }

		[NinjaScriptProperty] [Range(0, 20)]
		[Display(Name = "Lag (bars, pivot finality)", GroupName = "Regime", Order = 0)] public int Lag { get; set; }
		[NinjaScriptProperty] [Display(Name = "Reset on new session", GroupName = "Regime", Order = 1)] public bool ResetOnNewSession { get; set; }
		[NinjaScriptProperty] [Display(Name = "Weekly reset only (Sunday ETH start)", GroupName = "Regime", Order = 2)] public bool WeeklyResetOnly { get; set; }
		[NinjaScriptProperty] [Display(Name = "Only calculate current session (skip history, cheaper on long charts)", GroupName = "Regime", Order = 3)] public bool CurrentSessionOnly { get; set; }
		[NinjaScriptProperty] [Display(Name = "Include prior session (current + last = 2 sessions, continuous across the roll)", GroupName = "Regime", Order = 4)] public bool IncludePriorSession { get; set; }

		[NinjaScriptProperty] [Range(0, 100)]
		[Display(Name = "Band opacity %", GroupName = "Style", Order = -1)] public int ShadeOpacity { get; set; }

		[XmlIgnore] [Display(Name = "Bull color", GroupName = "Style", Order = 0)]
		public Brush BullBrush { get; set; }
		[Browsable(false)] public string BullBrushSerialize { get { return Serialize.BrushToString(BullBrush); } set { BullBrush = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "Bear color", GroupName = "Style", Order = 1)]
		public Brush BearBrush { get; set; }
		[Browsable(false)] public string BearBrushSerialize { get { return Serialize.BrushToString(BearBrush); } set { BearBrush = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "Transition (Range) color", GroupName = "Style", Order = 2)]
		public Brush TransitionBrush { get; set; }
		[Browsable(false)] public string TransitionBrushSerialize { get { return Serialize.BrushToString(TransitionBrush); } set { TransitionBrush = Serialize.StringToBrush(value); } }
		#endregion
	}
}
