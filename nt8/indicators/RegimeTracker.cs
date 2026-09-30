#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// ── RegimeTracker ─────────────────────────────────────────────────────────
	// NT8 port of regime_tracker/regime_tracker.py (compute_regime): a Bull / Bear /
	// Trading-range classifier read straight from Market Structure.pdf (BOS / ChoCh).
	//
	// It does NOT re-derive swings. It HOSTS the black-box MyWedge indicator
	// (Indicators.My.MyWedge) and reads its public SwingLow / SwingHigh series for
	// the pivots — exactly the arrays the Python consumes — then runs the same
	// state machine on them. The pivot PRICE is the raw bar High/Low (the swing
	// arrays only hold an offset stop level; the Python uses them purely as a
	// "is there a pivot on this bar?" flag, so we test IsValidDataPoint).
	//
	// FIDELITY — the processing LAG:
	//   MyWedge retroactively invalidates a swing pivot up to 2 bars back
	//   (SwingLow.Reset(1/2)). The Python runs compute_regime over the FINALISED
	//   swing array, so it never sees a transient pivot that a later bar removes.
	//   To match that live, we process bar (CurrentBar - Lag): by then MyWedge's
	//   retro-resets for that bar have all fired, so _wedge.SwingLow[Lag] is final.
	//   Lag>=3 covers the deepest reset (Reset(2)) with a margin. Consequence: the
	//   regime label for a bar is finalised Lag bars after it closes (honest — the
	//   underlying MyWedge pivots repaint over the same window regardless).
	//
	// bar_dir: MyWedge's BarDir is private, so it is recomputed here bar-by-bar
	//   from O/H/L/C + IBS (verbatim port of MyWedge.cs's BarDir rule). It is only
	//   used to order the two extremes within a bar (low-first vs high-first).
	//
	// State is CONTINUOUS across sessions (matches run_regime_parquet.py: one pass,
	//   no per-session reset; a fresh session merely opens in Range only when it is
	//   the very first bar of the whole series). MyWedge handles its own per-session
	//   swing resets internally via the chart's session template.
	//
	// MyWedge ctor params below default to the values the validated Python run used
	//   (ShowW2L on, WedgeSymmetry 4, OLSensitivity 1, CTSB_Ignore/IB_Ignore on,
	//   SignalBarIBS 66). LookBack only delays when MyWedge starts emitting swings;
	//   lower = pivots available earlier in the session. SET THESE TO MATCH the
	//   MyWedge instance you trade, or the pivots (and regime) will differ.
	public class RegimeTracker : Indicator
	{
		private const string BULL = "Bull", BEAR = "Bear", RANGE = "Range";

		private My.MyWedge _wedge;

		// ── regime state machine (mirrors compute_regime locals) ──────────────
		private string        _trend;
		private List<int>     _zzIdx;    private List<char> _zzKind; private List<double> _zzPrice;
		private List<int>     _seqIdx;   private List<char> _seqKind; private List<double> _seqPrice;
		private bool          _bosSet;   private double _bosLevel;
		private bool          _legSet;   private double _leg;     private int _legI;
		private bool          _cntSet;   private double _counter; private int _counterI;
		private bool          _candSet;  private double _cand;    private int _candI;
		private HashSet<int>  _majorLow, _majorHigh;
		private int           _prevBarDir;
		private int           _procBar;  // next absolute bar index to process

		// ── session/weekly reset ───────────────────────────────────────────────
		private Data.SessionIterator _sessionIt;
		private DateTime      _weekAnchor;   // Sunday-anchored week-start date of the last week a weekly reset fired for

		// ── rendering ─────────────────────────────────────────────────────────
		private Brush _bullShade, _bearShade;
		private Dictionary<int, bool> _pivLow, _pivHigh;   // bar index -> isMajor (drawn in OnRender)

		// ── validation export ─────────────────────────────────────────────────
		private List<string> _csvRows;
		private string       _csvPath;

		// XmlIgnore is REQUIRED: XmlSerializer reflects public fields too, and a
		// Series<double> is not serializable — without this, saving a workspace or
		// chart template throws "There was an error reflecting type ... RegimeTracker".
		[XmlIgnore] [Browsable(false)]
		public Series<double> Regime;   // 1 Bull / -1 Bear / 0 Range (exposed for strategies/exporters)

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Bull/Bear/Trading-range classifier (Market Structure BOS/ChoCh) on MyWedge pivots. Port of regime_tracker.py.";
				Name        = "RegimeTracker";
				Calculate   = Calculate.OnBarClose;   // Python runs a bar-close replay
				IsOverlay   = true;
				IsSuspendedWhileInactive = false;
				DrawOnPricePanel = true;

				// MyWedge ctor (defaults = the validated Python run's params)
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

				// regime tracker
				Lag           = 1;   // canonical (2026-09-24): matches the live chart; Lag>=2 = finalised/non-repaint view
				ShadeOpacity  = 22;
				ShowShading   = true;
				ShowMajors    = true;
				ShowMinors    = false;
				ShowEvents    = true;
				ExportCsv     = false;
				ExportFileName = "";
				ResetOnNewSession = true;
				WeeklyResetOnly   = false;

				// style — pivots
				MinorDotBrush  = Brushes.Gray;
				MinorDotSize   = 3;
				MajorLowBrush  = Brushes.LimeGreen;
				MajorHighBrush = Brushes.OrangeRed;
				MajorDotSize   = 5;
				// style — events
				BosBrush        = Brushes.DodgerBlue;
				ChoChBrush      = Brushes.Gold;
				EventFontSize   = 12;
				EventOffsetTicks = 6;
				BosText         = "BOS";
				ChoChText       = "ChoCh";
				// style — shading
				BullShadeBrush = Brushes.SeaGreen;
				BearShadeBrush = Brushes.IndianRed;

				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "RegimePlot"); // exposes a visible-less plot slot
			}
			else if (State == State.Configure)
			{
				_bullShade = MakeShade(BullShadeBrush, ShadeOpacity);
				_bearShade = MakeShade(BearShadeBrush, ShadeOpacity);
				FreezeIf(MinorDotBrush); FreezeIf(MajorLowBrush); FreezeIf(MajorHighBrush);
				FreezeIf(BosBrush); FreezeIf(ChoChBrush);
			}
			else if (State == State.DataLoaded)
			{
				Regime = new Series<double>(this, MaximumBarsLookBack.Infinite);

				_trend    = RANGE;
				_zzIdx    = new List<int>();  _zzKind = new List<char>(); _zzPrice = new List<double>();
				_seqIdx   = new List<int>();  _seqKind = new List<char>(); _seqPrice = new List<double>();
				_bosSet   = false; _legSet = false; _cntSet = false; _candSet = false;
				_majorLow = new HashSet<int>(); _majorHigh = new HashSet<int>();
				_pivLow   = new Dictionary<int, bool>(); _pivHigh = new Dictionary<int, bool>();
				_prevBarDir = 0;
				_procBar    = 0;
				_sessionIt  = new Data.SessionIterator(Bars);
				_weekAnchor = DateTime.MinValue;

				_wedge = MyWedge(Input, LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);

				if (ExportCsv)
				{
					_csvRows = new List<string>();
					_csvPath = string.IsNullOrWhiteSpace(ExportFileName)
						? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
							string.Format("regime_tracker_{0}.csv", Instrument.MasterInstrument.Name))
						: ExportFileName;
				}
			}
			else if (State == State.Realtime || State == State.Terminated)
			{
				WriteCsv();
			}
		}

		private static void FreezeIf(Brush b)
		{
			if (b != null && b.CanFreeze && !b.IsFrozen) b.Freeze();
		}

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
			if (_wedge == null) return;
			_wedge.Update();

			// carry the exposed Regime plot/series forward each bar so downstream
			// reads never hit an unset value (updated for real once bar is processed)
			Regime[0] = _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0;

			// process every bar that is now Lag-settled (usually exactly one/bar)
			while (_procBar <= CurrentBar - Lag)
			{
				int barsAgo = CurrentBar - _procBar;
				ProcessBar(_procBar, barsAgo);
				_procBar++;
			}
		}

		// ── the compute_regime() loop body, for one finalised bar ─────────────
		private void ProcessBar(int i, int barsAgo)
		{
			// bar 0 has nothing to reset (DataLoaded already started the state
			// machine fresh); SessionIterator is only exercised from bar 1 on,
			// same as RegimePhaseMachine.cs's CurrentBar<1 guard.
			if (i > 0 && ResetOnNewSession)
			{
				DateTime t = Time[barsAgo];
				if (_sessionIt.IsNewSession(t, true))
				{
					// Sunday-anchored week start (CME's trading week opens Sunday
					// ETH): if Sunday's session is closed for a holiday, the first
					// session that week (e.g. Monday) still carries a NEW week-start
					// date relative to _weekAnchor, so the weekly reset still fires
					// on the first session of the week even without a literal Sunday bar.
					DateTime weekStart = t.Date.AddDays(-(int)t.Date.DayOfWeek);
					if (!WeeklyResetOnly || weekStart != _weekAnchor)
					{
						ResetRegimeState();
						_weekAnchor = weekStart;
					}
					_sessionIt.GetNextSession(t, true);
				}
			}

			double lp = Low[barsAgo], hp = High[barsAgo];
			bool isLow  = _wedge.SwingLow.IsValidDataPoint(barsAgo);
			bool isHigh = _wedge.SwingHigh.IsValidDataPoint(barsAgo);

			int barDir  = ComputeBarDir(barsAgo);
			_prevBarDir = barDir;
			bool lowFirst = barDir >= 0;

			char[] sides = lowFirst ? new[] { 'L', 'H' } : new[] { 'H', 'L' };

			// --- 1. breaks, on raw price, against the relevant levels as they
			//        stand before this bar's own pivots can move them ---
			foreach (char side in sides)
			{
				if (_trend == RANGE)
				{
					if (side == 'H')
					{
						var s = EntrySetup('L');            // higher low in place -> turn up
						if (s != null && hp > s.RefPrice)
						{
							AddEvent(i, barsAgo, "BOS", "up", s.RefPrice);
							AddMajorHigh(s.RefBar);            // the high the break took out
							Enter(i, BULL, hp);
						}
					}
					else
					{
						var s = EntrySetup('H');            // lower high in place -> turn down
						if (s != null && lp < s.RefPrice)
						{
							AddEvent(i, barsAgo, "BOS", "down", s.RefPrice);
							AddMajorLow(s.RefBar);
							Enter(i, BEAR, lp);
						}
					}
				}
				else if (_trend == BULL)
				{
					if (side == 'L' && _cntSet && lp < _counter)
					{
						AddEvent(i, barsAgo, "ChoCh", "down", _counter);
						_bosSet = false;
						SetTrend(RANGE);
					}
					else if (side == 'H' && _bosSet && hp > _bosLevel)
						Bos(i, barsAgo, "up", hp);
				}
				else // BEAR
				{
					if (side == 'H' && _cntSet && hp > _counter)
					{
						AddEvent(i, barsAgo, "ChoCh", "up", _counter);
						_bosSet = false;
						SetTrend(RANGE);
					}
					else if (side == 'L' && _bosSet && lp < _bosLevel)
						Bos(i, barsAgo, "down", lp);
				}
			}

			// while a leg is still running, its extreme keeps moving
			if (_legSet && !_bosSet)
			{
				if (_trend == BULL && hp > _leg) { _leg = hp; _legI = i; }
				else if (_trend == BEAR && lp < _leg) { _leg = lp; _legI = i; }
			}

			// --- 2. fold this bar's pivots in, keep the pullback candidate ---
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
						if (!_bosSet && _legSet) { _bosSet = true; _bosLevel = _leg; AddMajorHigh(_legI); }
						if (!_candSet || price < _cand) { _cand = price; _candI = i; _candSet = true; }
					}
				}
				else
				{
					if (_trend == BEAR)
					{
						if (!_bosSet && _legSet) { _bosSet = true; _bosLevel = _leg; AddMajorLow(_legI); }
						if (!_candSet || price > _cand) { _cand = price; _candI = i; _candSet = true; }
					}
				}

				// draw the pivot (minor by default; upgraded to major on promotion)
				DrawPivot(i, kind, price);
			}

			// finalise this bar's regime label + shading
			Regime[barsAgo] = _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0;
			if (ShowShading)
			{
				if (_trend == BULL)      BackBrushes[barsAgo] = _bullShade;
				else if (_trend == BEAR) BackBrushes[barsAgo] = _bearShade;
			}
			if (ExportCsv)
			{
				var ci = CultureInfo.InvariantCulture;
				// BAR row carries OHLC so the CSV is a self-sufficient bar source:
				// the Python diff replays compute_mywedge+compute_regime on these exact
				// bars, so any regime mismatch is a logic difference, not bar drift.
				_csvRows.Add(string.Join(",",
					"BAR",
					i.ToString(ci),
					Time[barsAgo].ToString("yyyy-MM-dd HH:mm:ss", ci),
					Open[barsAgo].ToString("F2", ci),
					High[barsAgo].ToString("F2", ci),
					Low[barsAgo].ToString("F2", ci),
					Close[barsAgo].ToString("F2", ci),
					_trend, "", "", ""));
			}
		}

		// ── bar direction (verbatim MyWedge.cs BarDir rule) ───────────────────
		private int ComputeBarDir(int barsAgo)
		{
			double o = Open[barsAgo], c = Close[barsAgo], h = High[barsAgo], l = Low[barsAgo];
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

		// ── zz swing sequence helpers ─────────────────────────────────────────
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

		// last `count` tips of a kind, most-recent first
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

		// ── outside-bar collapse ──────────────────────────────────────────────
		// MyWedge marks an outside bar as BOTH a swing high and a swing low, so zz
		// records two swings for one bar. That splits a single pullback in half: a
		// pullback ending HIGHER than the one before it then gets compared against
		// its own other half and reads as a lower low, and the setup is lost.
		//
		// Whether the bar counts as one swing or two turns on whether it EXTENDED
		// the structure at both ends -- ran past the last swing of its own kind on
		// each side. Both ends extended: the bar really made new ground both ways
		// and both swings stand. Only one end did (or neither): the bar is one move
		// with an overshoot attached, and collapses to the extreme it LEFT ON, from
		// BarDir. Mirrors swings()/extends() in regime_tracker.py.

		// Does this extreme run past the last swing of its own kind in `s`?
		private static bool Extends(List<char> sKind, List<double> sPrice, char kind, double price)
		{
			for (int j = sKind.Count - 1; j >= 0; j--)
				if (sKind[j] == kind)
					return kind == 'H' ? price > sPrice[j] : price < sPrice[j];
			return true;                        // nothing to compare against yet
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
					continue;                   // one-sided bar: its later extreme wins
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

		// range-exit setup: 1(H) 2(L) 3(H=lower high), BOS then breaks 2. `kind` is
		// the side that must slope (H = bear setup / lower high; L = bull / higher low).
		private Setup EntrySetup(char kind)
		{
			// read the collapsed sequence, not zz itself
			Swings(_seqIdx, _seqKind, _seqPrice);
			var pos = new List<int>();
			for (int j = 0; j < _seqKind.Count; j++) if (_seqKind[j] == kind) pos.Add(j);
			if (pos.Count < 2 || pos[pos.Count - 1] == 0) return null;
			int j2 = pos[pos.Count - 1];
			double lastPrice = _seqPrice[j2], prevPrice = _seqPrice[pos[pos.Count - 2]];
			bool sloped = kind == 'H' ? lastPrice < prevPrice : lastPrice > prevPrice;
			if (!sloped) return null;
			int refIdx = j2 - 1;
			if (_seqKind[refIdx] == kind) return null;   // not alternating
			return new Setup { CounterBar = _seqIdx[j2], CounterPrice = lastPrice, RefBar = _seqIdx[refIdx], RefPrice = _seqPrice[refIdx] };
		}

		private void Enter(int i, string newTrend, double level)
		{
			var t = Tips(newTrend == BULL ? 'L' : 'H', 1);
			if (t.Count > 0)
			{
				_counterI = t[0].Key; _counter = t[0].Value; _cntSet = true;
				if (newTrend == BULL) AddMajorLow(_counterI); else AddMajorHigh(_counterI);
			}
			_bosSet = false;
			_leg = level; _legI = i; _legSet = true;
			_candSet = false;
			SetTrend(newTrend);
		}

		private void Bos(int i, int barsAgo, string direction, double level)
		{
			AddEvent(i, barsAgo, "BOS", direction, _bosSet ? _bosLevel : double.NaN);
			if (_candSet)
			{
				_counter = _cand; _counterI = _candI; _cntSet = true;
				if (direction == "up") AddMajorLow(_candI); else AddMajorHigh(_candI);
			}
			_bosSet = false;
			_leg = level; _legI = i; _legSet = true;
			_candSet = false;
		}

		private void SetTrend(string newTrend) { _trend = newTrend; }

		// clears only the forward-going state machine (trend/BOS-ChoCh/legs/zz+seq
		// sequences) so classification starts fresh from Range. Majors/minors and
		// already-rendered shading are NOT touched — chart history stays intact.
		private void ResetRegimeState()
		{
			_trend = RANGE;
			_zzIdx.Clear();  _zzKind.Clear();  _zzPrice.Clear();
			_seqIdx.Clear(); _seqKind.Clear(); _seqPrice.Clear();
			_bosSet = false; _legSet = false; _cntSet = false; _candSet = false;
			_prevBarDir = 0;
		}

		// ── major-pivot tracking (drawn in OnRender; visibility decided there) ──
		private void AddMajorLow(int idx)  { if (_majorLow.Add(idx))  _pivLow[idx]  = true; }
		private void AddMajorHigh(int idx) { if (_majorHigh.Add(idx)) _pivHigh[idx] = true; }

		// record a pivot for OnRender to draw (major flag can be upgraded later)
		private void DrawPivot(int i, char kind, double price)
		{
			if (kind == 'L') _pivLow[i]  = _majorLow.Contains(i);
			else             _pivHigh[i] = _majorHigh.Contains(i);
		}

		private void AddEvent(int i, int barsAgo, string kind, string dir, double level)
		{
			if (ExportCsv)
			{
				var ci = CultureInfo.InvariantCulture;
				_csvRows.Add(string.Join(",",
					"EVT",
					i.ToString(ci),
					Time[barsAgo].ToString("yyyy-MM-dd HH:mm:ss", ci),
					"", "", "", "", "",
					kind, dir,
					double.IsNaN(level) ? "" : level.ToString("F2", ci)));
			}
			if (!ShowEvents) return;
			bool up = dir == "up";
			double y = up ? High[barsAgo] + EventOffsetTicks * TickSize
			              : Low[barsAgo]  - EventOffsetTicks * TickSize;
			Brush b = kind == "ChoCh" ? ChoChBrush : BosBrush;
			string label = kind == "ChoCh" ? ChoChText : BosText;
			var font = new NinjaTrader.Gui.Tools.SimpleFont("Arial", EventFontSize);
			Draw.Text(this, "rt_ev_" + i + "_" + kind + "_" + dir, false, label, barsAgo, y, 0,
				b, font, System.Windows.TextAlignment.Center, null, null, 0);
		}

		// ── pivot dots (custom size via OnRender; Draw.Dot has no size knob) ───
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (ChartBars == null || RenderTarget == null || Bars == null) return;
			if (_pivLow == null || _pivHigh == null) return;
			if (!ShowMinors && !ShowMajors) return;

			var minorDx  = MinorDotBrush.ToDxBrush(RenderTarget);
			var majLowDx = MajorLowBrush.ToDxBrush(RenderTarget);
			var majHiDx  = MajorHighBrush.ToDxBrush(RenderTarget);
			try
			{
				int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
				for (int bi = Math.Max(0, from); bi <= to && bi < Bars.Count; bi++)
				{
					float x = chartControl.GetXByBarIndex(ChartBars, bi);

					bool majL;
					if (_pivLow.TryGetValue(bi, out majL) && ((majL && ShowMajors) || (!majL && ShowMinors)))
					{
						float r = majL ? MajorDotSize : MinorDotSize;
						float y = chartScale.GetYByValue(Bars.GetLow(bi) - 2 * TickSize) + r + 1f;
						RenderTarget.FillEllipse(new SharpDX.Direct2D1.Ellipse(new SharpDX.Vector2(x, y), r, r),
							majL ? majLowDx : minorDx);
					}
					bool majH;
					if (_pivHigh.TryGetValue(bi, out majH) && ((majH && ShowMajors) || (!majH && ShowMinors)))
					{
						float r = majH ? MajorDotSize : MinorDotSize;
						float y = chartScale.GetYByValue(Bars.GetHigh(bi) + 2 * TickSize) - r - 1f;
						RenderTarget.FillEllipse(new SharpDX.Direct2D1.Ellipse(new SharpDX.Vector2(x, y), r, r),
							majH ? majHiDx : minorDx);
					}
				}
			}
			finally { minorDx.Dispose(); majLowDx.Dispose(); majHiDx.Dispose(); }
		}

		private void WriteCsv()
		{
			if (!ExportCsv || _csvRows == null || _csvRows.Count == 0 || string.IsNullOrEmpty(_csvPath)) return;
			try
			{
				var sb = new StringBuilder();
				sb.AppendLine("type,bar,time,o,h,l,c,regime,kind,dir,level");
				foreach (var r in _csvRows) sb.AppendLine(r);
				var tmp = _csvPath + ".tmp";
				File.WriteAllText(tmp, sb.ToString());
				if (File.Exists(_csvPath)) File.Delete(_csvPath);
				File.Move(tmp, _csvPath);
				Print(string.Format("RegimeTracker: {0} rows -> {1}", _csvRows.Count, _csvPath));
			}
			catch (Exception ex) { Print("RegimeTracker CSV write failed: " + ex.Message); }
		}

		#region Properties
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
		[NinjaScriptProperty] [Range(0, 100)]
		[Display(Name = "Shade opacity %", GroupName = "Regime", Order = 1)] public int ShadeOpacity { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show shading", GroupName = "Regime", Order = 2)] public bool ShowShading { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show major pivots", GroupName = "Regime", Order = 3)] public bool ShowMajors { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show minor pivots", GroupName = "Regime", Order = 4)] public bool ShowMinors { get; set; }
		[NinjaScriptProperty] [Display(Name = "Show BOS/ChoCh", GroupName = "Regime", Order = 5)] public bool ShowEvents { get; set; }
		[NinjaScriptProperty] [Display(Name = "Export validation CSV", GroupName = "Regime", Order = 6)] public bool ExportCsv { get; set; }
		[Display(Name = "Export file (empty = Documents\\regime_tracker_<instr>.csv)", GroupName = "Regime", Order = 7)] public string ExportFileName { get; set; }
		[NinjaScriptProperty] [Display(Name = "Reset on new session", GroupName = "Regime", Order = 8)] public bool ResetOnNewSession { get; set; }
		[NinjaScriptProperty] [Display(Name = "Weekly reset only (Sunday ETH start)", GroupName = "Regime", Order = 9)] public bool WeeklyResetOnly { get; set; }

		// ── Style: pivots ─────────────────────────────────────────────────────
		[XmlIgnore] [Display(Name = "Minor dot color", GroupName = "Style — pivots", Order = 0)]
		public Brush MinorDotBrush { get; set; }
		[Browsable(false)] public string MinorDotBrushSerialize { get { return Serialize.BrushToString(MinorDotBrush); } set { MinorDotBrush = Serialize.StringToBrush(value); } }

		[Range(1, 50)] [Display(Name = "Minor dot size (px)", GroupName = "Style — pivots", Order = 1)]
		public int MinorDotSize { get; set; }

		[XmlIgnore] [Display(Name = "Major LOW dot color", GroupName = "Style — pivots", Order = 2)]
		public Brush MajorLowBrush { get; set; }
		[Browsable(false)] public string MajorLowBrushSerialize { get { return Serialize.BrushToString(MajorLowBrush); } set { MajorLowBrush = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "Major HIGH dot color", GroupName = "Style — pivots", Order = 3)]
		public Brush MajorHighBrush { get; set; }
		[Browsable(false)] public string MajorHighBrushSerialize { get { return Serialize.BrushToString(MajorHighBrush); } set { MajorHighBrush = Serialize.StringToBrush(value); } }

		[Range(1, 50)] [Display(Name = "Major dot size (px)", GroupName = "Style — pivots", Order = 4)]
		public int MajorDotSize { get; set; }

		// ── Style: events (BOS / ChoCh text) ──────────────────────────────────
		[XmlIgnore] [Display(Name = "BOS text color", GroupName = "Style — events", Order = 0)]
		public Brush BosBrush { get; set; }
		[Browsable(false)] public string BosBrushSerialize { get { return Serialize.BrushToString(BosBrush); } set { BosBrush = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "ChoCh text color", GroupName = "Style — events", Order = 1)]
		public Brush ChoChBrush { get; set; }
		[Browsable(false)] public string ChoChBrushSerialize { get { return Serialize.BrushToString(ChoChBrush); } set { ChoChBrush = Serialize.StringToBrush(value); } }

		[Range(4, 72)] [Display(Name = "Event font size", GroupName = "Style — events", Order = 2)]
		public int EventFontSize { get; set; }
		[Range(-100, 100)] [Display(Name = "Event vertical offset (ticks, +up/-down side)", GroupName = "Style — events", Order = 3)]
		public int EventOffsetTicks { get; set; }
		[Display(Name = "BOS label text", GroupName = "Style — events", Order = 4)] public string BosText { get; set; }
		[Display(Name = "ChoCh label text", GroupName = "Style — events", Order = 5)] public string ChoChText { get; set; }

		// ── Style: shading ────────────────────────────────────────────────────
		[XmlIgnore] [Display(Name = "Bull shade color", GroupName = "Style — shading", Order = 0)]
		public Brush BullShadeBrush { get; set; }
		[Browsable(false)] public string BullShadeBrushSerialize { get { return Serialize.BrushToString(BullShadeBrush); } set { BullShadeBrush = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "Bear shade color", GroupName = "Style — shading", Order = 1)]
		public Brush BearShadeBrush { get; set; }
		[Browsable(false)] public string BearShadeBrushSerialize { get { return Serialize.BrushToString(BearShadeBrush); } set { BearShadeBrush = Serialize.StringToBrush(value); } }

		[Browsable(false)] [XmlIgnore] public Series<double> RegimePlot { get { return Values[0]; } }
		#endregion
	}
}
