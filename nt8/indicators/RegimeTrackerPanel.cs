#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
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
	// SELF-CONTAINED, NOT a wrapper around a hidden RegimeTrackerV2 child. A first
	// attempt ran RegimeTrackerV2 as a nested child (Panel -> V2 -> MyWedge, two
	// levels of indicator composition) calling .Update() on it each bar; logging
	// proved that child got stuck at State.DataLoaded / CurrentBar=-1 forever --
	// it never actually processed a single bar, hence an empty panel. The ONE
	// level of composition RegimeTrackerV2 itself uses (-> MyWedge, with the same
	// .Update() pattern) DOES work -- so this duplicates that exact single-level
	// shape instead: its OWN MyWedge child, same regime state machine inlined
	// directly (same logic as RegimeTrackerV2.cs, stripped of all overlay drawing/
	// CSV export, which this panel doesn't need), so it only ever nests one level deep.
	public class RegimeTrackerPanel : Indicator
	{
		private const string BULL = "Bull", BEAR = "Bear", RANGE = "Range";

		private My.MyWedge _wedge;

		private string        _trend;
		private List<int>     _zzIdx;    private List<char> _zzKind; private List<double> _zzPrice;
		private List<int>     _seqIdx;   private List<char> _seqKind; private List<double> _seqPrice;
		private bool          _bosSet;   private double _bosLevel;
		private bool          _legSet;   private double _leg;     private int _legI;
		private bool          _cntSet;   private double _counter; private int _counterI;
		private bool          _candSet;  private double _cand;    private int _candI;
		private int           _prevBarDir;
		private int           _procBar;

		private Data.SessionIterator _sessionIt;
		private DateTime      _weekAnchor;
		private int           _sessionOnlyCutoffBar = -1;

		// bar index -> Regime value, painted full-panel-height in OnRender (same
		// technique as RegimeTrackerV2's price-panel shading, just filling this
		// panel's whole height instead of the price range) so bars sit edge-to-edge
		// as one solid band instead of NT8's native Bar plot style (which splits
		// +/- around a zero line and leaves gaps between bars).
		private Dictionary<int, double> _barRegime;

		// ShadeOpacity-adjusted brushes actually used for painting (same ARGB-alpha
		// technique as RegimeTrackerV2.MakeShade); the raw BullBrush/BearBrush/
		// TransitionBrush properties stay fully opaque so the color pickers show
		// the true color.
		private Brush _bullShade, _bearShade, _transShade;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Regime (Bull/Bear/Range) classification, same logic as RegimeTrackerV2, plotted as a colored band in its own panel -- no pivots/events/price overlay.";
				Name        = "RegimeTrackerPanel";
				Calculate   = Calculate.OnBarClose;
				IsOverlay   = false;
				IsSuspendedWhileInactive = false;

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
				Lag           = 1;
				ResetOnNewSession  = true;
				WeeklyResetOnly    = false;
				CurrentSessionOnly = false;

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
				FreezeIf(BullBrush); FreezeIf(BearBrush); FreezeIf(TransitionBrush);
				_bullShade  = MakeShade(BullBrush, ShadeOpacity);
				_bearShade  = MakeShade(BearBrush, ShadeOpacity);
				_transShade = MakeShade(TransitionBrush, ShadeOpacity);
			}
			else if (State == State.DataLoaded)
			{
				_trend    = RANGE;
				_zzIdx    = new List<int>();  _zzKind = new List<char>(); _zzPrice = new List<double>();
				_seqIdx   = new List<int>();  _seqKind = new List<char>(); _seqPrice = new List<double>();
				_bosSet   = false; _legSet = false; _cntSet = false; _candSet = false;
				_prevBarDir = 0;
				_procBar    = 0;
				_sessionIt  = new Data.SessionIterator(Bars);
				_weekAnchor = DateTime.MinValue;
				_sessionOnlyCutoffBar = -1;
				_barRegime  = new Dictionary<int, double>();

				_wedge = MyWedge(Input, LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);
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

			if (CurrentSessionOnly && _sessionOnlyCutoffBar < 0)
				_sessionOnlyCutoffBar = FindCurrentSessionStartBar();

			if (!(CurrentSessionOnly && CurrentBar < _sessionOnlyCutoffBar))
				_wedge.Update();

			while (_procBar <= CurrentBar - Lag)
			{
				int barsAgo = CurrentBar - _procBar;
				if (!(CurrentSessionOnly && _procBar < _sessionOnlyCutoffBar))
					ProcessBar(_procBar, barsAgo);
				_procBar++;
			}
		}

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

		private void ProcessBar(int i, int barsAgo)
		{
			if (i > 0 && (ResetOnNewSession || CurrentSessionOnly))
			{
				DateTime t = Time[barsAgo];
				if (_sessionIt.IsNewSession(t, true))
				{
					DateTime weekStart = t.Date.AddDays(-(int)t.Date.DayOfWeek);
					if (ResetOnNewSession && (!WeeklyResetOnly || weekStart != _weekAnchor))
					{
						ResetRegimeState();
						_weekAnchor = weekStart;
					}
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

			double r = _trend == BULL ? 1.0 : _trend == BEAR ? -1.0 : 0.0;
			Values[0][barsAgo] = r;
			_barRegime[i] = r;
		}

		// paints one full-panel-height, edge-to-edge rectangle per bar -- a solid
		// band with no zero-line split and no gaps, unlike NT8's native Bar plot style.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (ChartBars == null || RenderTarget == null || Bars == null || _barRegime == null) return;

			var bullDx = _bullShade.ToDxBrush(RenderTarget);
			var bearDx = _bearShade.ToDxBrush(RenderTarget);
			var transDx = _transShade.ToDxBrush(RenderTarget);
			try
			{
				int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
				float yTop = chartScale.GetYByValue(chartScale.MaxValue);
				float yBot = chartScale.GetYByValue(chartScale.MinValue);

				for (int bi = Math.Max(0, from); bi <= to && bi < Bars.Count; bi++)
				{
					double r;
					if (!_barRegime.TryGetValue(bi, out r)) continue;

					float x = chartControl.GetXByBarIndex(ChartBars, bi);
					float xNext = bi < to ? chartControl.GetXByBarIndex(ChartBars, bi + 1)
					                      : x + (bi > 0 ? x - chartControl.GetXByBarIndex(ChartBars, bi - 1) : 6f);
					float w = Math.Max(1f, xNext - x);
					var brush = r > 0 ? bullDx : r < 0 ? bearDx : transDx;
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x - w / 2f, yTop, w, yBot - yTop), brush);
				}
			}
			finally { bullDx.Dispose(); bearDx.Dispose(); transDx.Dispose(); }
		}

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
		[NinjaScriptProperty] [Display(Name = "Reset on new session", GroupName = "Regime", Order = 1)] public bool ResetOnNewSession { get; set; }
		[NinjaScriptProperty] [Display(Name = "Weekly reset only (Sunday ETH start)", GroupName = "Regime", Order = 2)] public bool WeeklyResetOnly { get; set; }
		[NinjaScriptProperty] [Display(Name = "Only calculate current session (skip history, cheaper on long charts)", GroupName = "Regime", Order = 3)] public bool CurrentSessionOnly { get; set; }

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
