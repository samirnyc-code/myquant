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
		private bool          _bosSet;   private double _bosLevel;
		private bool          _legSet;   private double _leg;     private int _legI;
		private bool          _cntSet;   private double _counter; private int _counterI;
		private bool          _candSet;  private double _cand;    private int _candI;
		private HashSet<int>  _majorLow, _majorHigh;
		private int           _prevBarDir;
		private int           _procBar;  // next absolute bar index to process

		// ── rendering ─────────────────────────────────────────────────────────
		private Brush _bullShade, _bearShade, _majLowBrush, _majHighBrush, _minBrush;

		// ── validation export ─────────────────────────────────────────────────
		private List<string> _csvRows;
		private string       _csvPath;

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
				Lag           = 3;
				ShadeOpacity  = 22;
				ShowShading   = true;
				ShowMajors    = true;
				ShowMinors    = false;
				ShowEvents    = true;
				ExportCsv     = false;
				ExportFileName = "";

				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "RegimePlot"); // exposes a visible-less plot slot
			}
			else if (State == State.Configure)
			{
				_bullShade    = MakeShade(Brushes.SeaGreen,  ShadeOpacity);
				_bearShade    = MakeShade(Brushes.IndianRed, ShadeOpacity);
				_majLowBrush  = Frozen(Brushes.LimeGreen);
				_majHighBrush = Frozen(Brushes.OrangeRed);
				_minBrush     = Frozen(Brushes.Gray);
			}
			else if (State == State.DataLoaded)
			{
				Regime = new Series<double>(this, MaximumBarsLookBack.Infinite);

				_trend    = RANGE;
				_zzIdx    = new List<int>();  _zzKind = new List<char>(); _zzPrice = new List<double>();
				_bosSet   = false; _legSet = false; _cntSet = false; _candSet = false;
				_majorLow = new HashSet<int>(); _majorHigh = new HashSet<int>();
				_prevBarDir = 0;
				_procBar    = 0;

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

		private static Brush Frozen(Brush b)
		{
			var c = b.Clone(); if (c.CanFreeze) c.Freeze(); return c;
		}

		private static Brush MakeShade(SolidColorBrush src, int opacityPct)
		{
			byte a = (byte)Math.Max(0, Math.Min(255, (int)Math.Round(opacityPct / 100.0 * 255.0)));
			var c = src.Color;
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
				_csvRows.Add(string.Join(",",
					i.ToString(CultureInfo.InvariantCulture),
					Time[barsAgo].ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
					_trend));
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

		private class Setup { public int CounterBar; public double CounterPrice; public int RefBar; public double RefPrice; }

		// range-exit setup: 1(H) 2(L) 3(H=lower high), BOS then breaks 2. `kind` is
		// the side that must slope (H = bear setup / lower high; L = bull / higher low).
		private Setup EntrySetup(char kind)
		{
			var pos = new List<int>();
			for (int j = 0; j < _zzKind.Count; j++) if (_zzKind[j] == kind) pos.Add(j);
			if (pos.Count < 2 || pos[pos.Count - 1] == 0) return null;
			int j2 = pos[pos.Count - 1];
			double lastPrice = _zzPrice[j2], prevPrice = _zzPrice[pos[pos.Count - 2]];
			bool sloped = kind == 'H' ? lastPrice < prevPrice : lastPrice > prevPrice;
			if (!sloped) return null;
			int refIdx = j2 - 1;
			if (_zzKind[refIdx] == kind) return null;   // not alternating
			return new Setup { CounterBar = _zzIdx[j2], CounterPrice = lastPrice, RefBar = _zzIdx[refIdx], RefPrice = _zzPrice[refIdx] };
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

		// ── major-pivot tracking + rendering ──────────────────────────────────
		private void AddMajorLow(int idx)  { if (_majorLow.Add(idx)  && ShowMajors) Redraw(idx, 'L'); }
		private void AddMajorHigh(int idx) { if (_majorHigh.Add(idx) && ShowMajors) Redraw(idx, 'H'); }

		private void DrawPivot(int i, char kind, double price)
		{
			bool major = kind == 'L' ? _majorLow.Contains(i) : _majorHigh.Contains(i);
			if (!major && !ShowMinors) return;
			if (major && !ShowMajors) return;
			int barsAgo = CurrentBar - i;
			if (barsAgo < 0) return;
			double y = kind == 'L' ? Low[barsAgo] - 2 * TickSize : High[barsAgo] + 2 * TickSize;
			Brush b = major ? (kind == 'L' ? _majLowBrush : _majHighBrush) : _minBrush;
			Draw.Dot(this, "rt_pv_" + i + "_" + kind, false, barsAgo, y, b);
		}

		private void Redraw(int idx, char kind)
		{
			int barsAgo = CurrentBar - idx;
			if (barsAgo < 0) return;
			double y = kind == 'L' ? Low[barsAgo] - 2 * TickSize : High[barsAgo] + 2 * TickSize;
			Brush b = kind == 'L' ? _majLowBrush : _majHighBrush;
			Draw.Dot(this, "rt_pv_" + idx + "_" + kind, false, barsAgo, y, b);
		}

		private void AddEvent(int i, int barsAgo, string kind, string dir, double level)
		{
			if (ExportCsv)
				_csvRows.Add(string.Join(",",
					i.ToString(CultureInfo.InvariantCulture),
					Time[barsAgo].ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
					kind, dir,
					double.IsNaN(level) ? "" : level.ToString("F2", CultureInfo.InvariantCulture)));
			if (!ShowEvents) return;
			bool up = dir == "up";
			double y = up ? High[barsAgo] + 6 * TickSize : Low[barsAgo] - 6 * TickSize;
			Brush b = kind == "ChoCh" ? Brushes.Gold : (up ? _majLowBrush : _majHighBrush);
			Draw.Text(this, "rt_ev_" + i + "_" + kind + "_" + dir, kind, barsAgo, y, b);
		}

		private void WriteCsv()
		{
			if (!ExportCsv || _csvRows == null || _csvRows.Count == 0 || string.IsNullOrEmpty(_csvPath)) return;
			try
			{
				var sb = new StringBuilder();
				sb.AppendLine("bar,time,regime_or_kind,dir,level");
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

		[Browsable(false)] [XmlIgnore] public Series<double> RegimePlot { get { return Values[0]; } }
		#endregion
	}
}
