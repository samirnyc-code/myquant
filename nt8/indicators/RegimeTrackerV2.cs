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
using System.Windows.Threading;
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
	// ── RegimeTrackerV2 ──────────────────────────────────────────────────────
	// Resource-comparison CLONE of RegimeTracker.cs — logic is identical (same
	// state machine, same Lag/session-reset rules; see RegimeTracker.cs for the
	// full design notes). The only functional difference is how visuals are
	// drawn, to fix the "toggling the indicator off only hides the pivot dots"
	// bug: shading was written straight into the chart's BackBrushes array and
	// BOS/ChoCh labels were plain Draw.Text calls, neither of which NT8 ties to
	// the indicator's own IsVisible flag — only the OnRender-painted dots
	// respected it.
	//
	// Fix applied here:
	//   - shading: no longer writes BackBrushes; stores per-bar trend in
	//     _barTrend and paints it as a rectangle inside OnRender (same loop,
	//     same bounded ChartBars.FromIndex..ToIndex range as the dots), so it
	//     now shares the dots' already-correct show/hide behavior.
	//   - BOS/ChoCh labels: the Draw.Text return value is kept in _eventObjs;
	//     OnBarUpdate (which keeps running even while hidden) detects an
	//     IsVisible flip and syncs every tracked label's own .IsVisible to match.
	//
	// This file exists ONLY to A/B the CPU/memory cost of that fix against the
	// original RegimeTracker — do not deploy both permanently, retire whichever
	// loses the comparison.
	public class RegimeTrackerV2 : Indicator
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

		// ── current-session-only calc ──────────────────────────────────────────
		// bar index where the most-recently-started session begins; bars before
		// it are skipped entirely (no wedge update, no regime/pivot/event calc,
		// no drawing) instead of just resetting state at the boundary, so a
		// chart loaded with years of history doesn't pay for all of it.
		private int _sessionOnlyCutoffBar = -1;   // -1 = not yet computed

		// ── rendering ─────────────────────────────────────────────────────────
		private Brush _bullShade, _bearShade;
		private Dictionary<int, bool>   _pivLow, _pivHigh;   // bar index -> isMajor (drawn in OnRender)
		private Dictionary<int, double> _barTrend;           // bar index -> Regime value, painted as shading in OnRender

		// ── visibility-sync for Draw.* objects (NT8 doesn't tie these to IsVisible) ──
		// OnBarUpdate is NOT a reliable hook for this: toggling the indicator off
		// in the Indicator Manager only sets IsVisible + calls InvalidateVisual(),
		// neither of which fires OnBarUpdate, so a bar-close-only sync can sit
		// stale indefinitely between bars (or forever on a quiet chart). A
		// dispatcher-thread timer checks independently of bar flow.
		private List<DrawingTool> _eventObjs;
		private bool _lastIsVisible;
		private DispatcherTimer _visTimer;

		// ── validation export ─────────────────────────────────────────────────
		private List<string> _csvRows;
		private string       _csvPath;

		// XmlIgnore is REQUIRED: XmlSerializer reflects public fields too, and a
		// Series<double> is not serializable — without this, saving a workspace or
		// chart template throws "There was an error reflecting type ... RegimeTrackerV2".
		[XmlIgnore] [Browsable(false)]
		public Series<double> Regime;   // 1 Bull / -1 Bear / 0 Range (exposed for strategies/exporters)

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "RegimeTrackerV2 (resource-comparison clone): same Bull/Bear/Trading-range classifier as RegimeTracker, with OnRender-based shading + visibility-synced BOS/ChoCh labels so Hide/Show fully hides every visual, not just the pivot dots.";
				Name        = "RegimeTrackerV2";
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
				CurrentSessionOnly = false;

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
				_barTrend = new Dictionary<int, double>();
				_eventObjs = new List<DrawingTool>();
				_lastIsVisible = IsVisible;
				_prevBarDir = 0;
				_procBar    = 0;
				_sessionIt  = new Data.SessionIterator(Bars);
				_weekAnchor = DateTime.MinValue;
				_sessionOnlyCutoffBar = -1;

				_wedge = MyWedge(Input, LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);

				if (ExportCsv)
				{
					_csvRows = new List<string>();
					_csvPath = string.IsNullOrWhiteSpace(ExportFileName)
						? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
							string.Format("regime_tracker_v2_{0}.csv", Instrument.MasterInstrument.Name))
						: ExportFileName;
				}
			}
			else if (State == State.Historical)
			{
				if (ChartControl == null) return;
				ChartControl.Dispatcher.InvokeAsync(() =>
				{
					_visTimer = new DispatcherTimer(DispatcherPriority.Background, ChartControl.Dispatcher);
					_visTimer.Interval = TimeSpan.FromMilliseconds(250);
					_visTimer.Tick += VisTimer_Tick;
					_visTimer.Start();
				});
			}
			else if (State == State.Realtime || State == State.Terminated)
			{
				WriteCsv();
				if (State == State.Terminated && ChartControl != null)
				{
					ChartControl.Dispatcher.InvokeAsync(() =>
					{
						if (_visTimer != null) { _visTimer.Tick -= VisTimer_Tick; _visTimer.Stop(); _visTimer = null; }
					});
				}
			}
		}

		private void VisTimer_Tick(object sender, EventArgs e)
		{
			SyncEventVisibility();
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

		// propagates the indicator's own IsVisible onto every Draw.* object we've
		// created so far, the moment it flips — NT8 does not do this itself.
		// Called from VisTimer_Tick (reliable, independent of bar flow) and again
		// from OnBarUpdate as a cheap redundant backup.
		private void SyncEventVisibility()
		{
			if (_lastIsVisible == IsVisible) return;
			_lastIsVisible = IsVisible;
			if (_eventObjs != null)
				for (int k = 0; k < _eventObjs.Count; k++)
					if (_eventObjs[k] != null) _eventObjs[k].IsVisible = IsVisible;
			if (ChartControl != null) ChartControl.InvalidateVisual();
		}

		protected override void OnBarUpdate()
		{
			SyncEventVisibility();

			if (_wedge == null) return;

			if (CurrentSessionOnly && _sessionOnlyCutoffBar < 0)
				_sessionOnlyCutoffBar = FindCurrentSessionStartBar();

			// below the cutoff: skip the wedge update too (not just regime/draw
			// logic) so a multi-year chart doesn't pay MyWedge's per-bar cost either.
			// MyWedge already treats BarsSinceNewTradingDay==0/1 as a fresh-session
			// start, which is exactly the state it's in the first time Update() is
			// called here (at the cutoff bar) with this skipped.
			if (!(CurrentSessionOnly && CurrentBar < _sessionOnlyCutoffBar))
				_wedge.Update();

			// carry the exposed Regime plot/series forward each bar so downstream
			// reads never hit an unset value (updated for real once bar is processed)
			Regime[0] = _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0;

			// process every bar that is now Lag-settled (usually exactly one/bar)
			while (_procBar <= CurrentBar - Lag)
			{
				int barsAgo = CurrentBar - _procBar;
				if (!(CurrentSessionOnly && _procBar < _sessionOnlyCutoffBar))
					ProcessBar(_procBar, barsAgo);
				_procBar++;
			}
		}

		// one-time forward scan (Bars is already fully loaded by the time
		// OnBarUpdate first fires) to find the bar index where the most recent
		// session in the loaded data begins, so historical bars before it can be
		// skipped outright instead of merely reset at the boundary.
		private int FindCurrentSessionStartBar()
		{
			if (Bars == null || Bars.Count == 0) return 0;
			var si = new Data.SessionIterator(Bars);
			int lastNewSessionBar = 0;
			for (int b = 0; b < Bars.Count; b++)
			{
				DateTime t = Bars.GetTime(b);
				if (si.IsNewSession(t, true))
				{
					lastNewSessionBar = b;
					si.GetNextSession(t, true);
				}
			}
			return lastNewSessionBar;
		}

		// ── the compute_regime() loop body, for one finalised bar ─────────────
		private void ProcessBar(int i, int barsAgo)
		{
			// bar 0 has nothing to reset (DataLoaded already started the state
			// machine fresh); SessionIterator is only exercised from bar 1 on,
			// same as RegimePhaseMachine.cs's CurrentBar<1 guard.
			if (i > 0 && (ResetOnNewSession || CurrentSessionOnly))
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
					if (ResetOnNewSession && (!WeeklyResetOnly || weekStart != _weekAnchor))
					{
						ResetRegimeState();
						_weekAnchor = weekStart;
					}
					// a later session than the pre-scanned cutoff has started live
					// (chart rolled into a new day) -- it becomes the new "current
					// session"; this bar itself (i == the new cutoff) still runs.
					if (CurrentSessionOnly && i > _sessionOnlyCutoffBar)
						_sessionOnlyCutoffBar = i;
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

			// finalise this bar's regime label; shading is now painted in OnRender
			// from _barTrend instead of writing BackBrushes directly, so it shares
			// the dots' IsVisible-respecting behavior.
			Regime[barsAgo] = _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0;
			if (ShowShading)
				_barTrend[i] = Regime[barsAgo];

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
			DrawingTool txt = Draw.Text(this, "rt_ev_" + i + "_" + kind + "_" + dir, false, label, barsAgo, y, 0,
				b, font, System.Windows.TextAlignment.Center, null, null, 0);
			if (txt != null)
			{
				txt.IsVisible = IsVisible;    // match current state immediately on creation
				_eventObjs.Add(txt);          // tracked so SyncEventVisibility() can flip it later
			}
		}

		// ── pivot dots + shading (custom-painted in OnRender so both respect
		//    IsVisible the same way; Draw.Dot has no size knob and BackBrushes
		//    doesn't respect IsVisible at all) ───────────────────────────────
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (ChartBars == null || RenderTarget == null || Bars == null) return;
			if (_pivLow == null || _pivHigh == null) return;

			var minorDx  = MinorDotBrush.ToDxBrush(RenderTarget);
			var majLowDx = MajorLowBrush.ToDxBrush(RenderTarget);
			var majHiDx  = MajorHighBrush.ToDxBrush(RenderTarget);
			var bullDx   = _bullShade.ToDxBrush(RenderTarget);
			var bearDx   = _bearShade.ToDxBrush(RenderTarget);
			try
			{
				int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
				float yTop = chartScale.GetYByValue(chartScale.MaxValue);
				float yBot = chartScale.GetYByValue(chartScale.MinValue);

				for (int bi = Math.Max(0, from); bi <= to && bi < Bars.Count; bi++)
				{
					float x = chartControl.GetXByBarIndex(ChartBars, bi);

					if (ShowShading && _barTrend != null)
					{
						double trendVal;
						if (_barTrend.TryGetValue(bi, out trendVal) && trendVal != 0)
						{
							float xNext = bi < to ? chartControl.GetXByBarIndex(ChartBars, bi + 1)
							                      : x + (bi > 0 ? x - chartControl.GetXByBarIndex(ChartBars, bi - 1) : 6f);
							float w = Math.Max(1f, xNext - x);
							RenderTarget.FillRectangle(new SharpDX.RectangleF(x - w / 2f, yTop, w, yBot - yTop),
								trendVal > 0 ? bullDx : bearDx);
						}
					}

					if (!ShowMinors && !ShowMajors) continue;

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
			finally { minorDx.Dispose(); majLowDx.Dispose(); majHiDx.Dispose(); bullDx.Dispose(); bearDx.Dispose(); }
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
				Print(string.Format("RegimeTrackerV2: {0} rows -> {1}", _csvRows.Count, _csvPath));
			}
			catch (Exception ex) { Print("RegimeTrackerV2 CSV write failed: " + ex.Message); }
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
		[Display(Name = "Export file (empty = Documents\\regime_tracker_v2_<instr>.csv)", GroupName = "Regime", Order = 7)] public string ExportFileName { get; set; }
		[NinjaScriptProperty] [Display(Name = "Reset on new session", GroupName = "Regime", Order = 8)] public bool ResetOnNewSession { get; set; }
		[NinjaScriptProperty] [Display(Name = "Weekly reset only (Sunday ETH start)", GroupName = "Regime", Order = 9)] public bool WeeklyResetOnly { get; set; }
		[NinjaScriptProperty] [Display(Name = "Only calculate current session (skip history, cheaper on long charts)", GroupName = "Regime", Order = 10)] public bool CurrentSessionOnly { get; set; }

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
