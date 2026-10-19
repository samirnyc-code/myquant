#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

// ─────────────────────────────────────────────────────────────────────────────
// PATsProfile — right-margin Volume Profile with the full Dalton toolkit, drawn
// OUTWARD from the last bar so price action is never covered. Every level/band/
// node is individually toggleable and colorable.
//
//   Volume Profile : POC, 70% value area (MOM Appendix 1, two-at-a-time),
//                    value-area band OR lines-only, HVN / LVN nodes,
//                    initial balance (RTH-anchored), prior-session value.
//   Labels         : numeric VAH/VAL/POC (current + prior), de-collided with
//                    leader lines so text never overlaps a line or another label.
//   Composite      : merge the last N sessions into one profile.
// Every band/line stops at its own session's left break.
//
// Volume-at-price precision:
//   - TODAY is always built from real trade ticks via OnMarketData — free,
//     since live data streams tick-by-tick regardless of this indicator.
//   - Earlier (closed) sessions use the OHLC bar-split approximation UNLESS
//     you turn on "Tick Replay" in the chart's Data Series settings (NT8-level
//     setting — an Indicator can't enable it from code, only read it via
//     Bars.IsTickReplay). When it's on, NT8 replays historical ticks too
//     (heavier chart load — depends on your feed actually serving tick-level
//     history back that far).
//   - Closed sessions are computed once and cached (barVolBySession) instead
//     of being re-walked on every recompute.
//
// IB (Initial Balance) is anchored to RthStartHHMM (RTH open time-of-day),
// not to the session's own start bar — on a chart whose session includes
// overnight/ETH bars, the session start is NOT the RTH open, and classical
// Market Profile IB is an RTH-only concept.
//
// Commit CS to: repo/nt8/indicators/PATsProfile.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsProfile : Indicator
	{
		private double rowSize;
		private List<int> sessionStarts;

		private Dictionary<double, double> volByRow;
		private List<double> hvn, lvn;
		private double poc, vah, val, ibh, ibl, maxVol;
		private double pPoc = double.NaN, pVah = double.NaN, pVal = double.NaN; // prior VOLUME VA
		private int winStartBar, priorStartBar = -1, todayStartBar = -1;

		// Developing (today-only) VA, as of the CLOSE of each bar -- the true history,
		// not today's final number projected backward. devVah/devVal/devPoc[k] is the
		// value area computed from only the volume known through bar (devSessionStart+k).
		// Folded incrementally, once per closed bar (see FoldBarIntoDev) -- cheap, and
		// naturally correct on a fresh chart load too (the fold loop just walks every
		// historical bar in order exactly like live does, no separate seeding needed).
		private Dictionary<double, double> devCumVol;
		private int devSessionStart = -1, devFoldedThroughBar = -1;
		private List<double> devVah = new List<double>();
		private List<double> devVal = new List<double>();
		private List<double> devPoc = new List<double>();

		// Tick-accurate accumulation (see header note).
		private readonly object liveLock = new object();
		private Dictionary<double, double> liveVolByRow;
		private int liveSessionStartBar = -1;
		private int obuSessionStartBar = -1;
		private Dictionary<int, Dictionary<double, double>> tickHistBySession; // filled only when Bars.IsTickReplay is on
		private Dictionary<int, Dictionary<double, double>> barVolBySession;   // cache of finalized (closed) sessions

		#region Parameters
		[NinjaScriptProperty] [Range(1, int.MaxValue)] [Display(Name = "Row height (ticks)", Order = 0, GroupName = "1 Profile")]
		public int RowTicks { get; set; }
		[NinjaScriptProperty] [Range(1, 60)] [Display(Name = "Composite sessions (1 = today)", Order = 1, GroupName = "1 Profile")]
		public int CompositeSessions { get; set; }
		[NinjaScriptProperty] [Range(20, 800)] [Display(Name = "VP width (px)", Order = 2, GroupName = "1 Profile")]
		public int VpWidthPx { get; set; }
		[NinjaScriptProperty] [Range(0, 800)] [Display(Name = "Right offset (px)", Order = 3, GroupName = "1 Profile")]
		public int RightOffsetPx { get; set; }
		[NinjaScriptProperty] [Range(0.05, 1.0)] [Display(Name = "Opacity", Order = 4, GroupName = "1 Profile")]
		public double Opacity { get; set; }
		[NinjaScriptProperty] [Range(6, 24)] [Display(Name = "Label font size", Order = 5, GroupName = "1 Profile")]
		public int LabelFontSize { get; set; }
		[NinjaScriptProperty] [Range(5, 240)] [Display(Name = "Initial balance minutes", Order = 6, GroupName = "1 Profile")]
		public int IbMinutes { get; set; }
		[NinjaScriptProperty] [Range(0, 2359)] [Display(Name = "RTH start (HHmm, chart time)", Order = 7, GroupName = "1 Profile")]
		public int RthStartHHMM { get; set; }

		[NinjaScriptProperty] [Display(Name = "Volume Profile", Order = 0, GroupName = "2 Show")]
		public bool ShowVP { get; set; }
		[NinjaScriptProperty] [Display(Name = "VAH / VAL lines", Order = 1, GroupName = "2 Show")]
		public bool ShowVAHVAL { get; set; }
		[NinjaScriptProperty] [Display(Name = "Value-area band (shaded)", Order = 2, GroupName = "2 Show")]
		public bool ShowVABand { get; set; }
		[NinjaScriptProperty] [Display(Name = "POC", Order = 3, GroupName = "2 Show")]
		public bool ShowPOC { get; set; }
		[NinjaScriptProperty] [Display(Name = "Initial balance", Order = 4, GroupName = "2 Show")]
		public bool ShowIB { get; set; }
		[NinjaScriptProperty] [Display(Name = "HVN (high-volume nodes)", Order = 5, GroupName = "2 Show")]
		public bool ShowHVN { get; set; }
		[NinjaScriptProperty] [Display(Name = "LVN (low-volume nodes)", Order = 6, GroupName = "2 Show")]
		public bool ShowLVN { get; set; }
		[NinjaScriptProperty] [Display(Name = "Prior VOLUME-VA lines", Order = 7, GroupName = "2 Show")]
		public bool ShowPriorLines { get; set; }
		[NinjaScriptProperty] [Display(Name = "Prior VOLUME-VA band", Order = 8, GroupName = "2 Show")]
		public bool ShowPriorBand { get; set; }
		[NinjaScriptProperty] [Display(Name = "Labels", Order = 9, GroupName = "2 Show")]
		public bool ShowLabels { get; set; }

		[NinjaScriptProperty] [Range(1, 20)] [Display(Name = "Node lookback (rows)", Order = 0, GroupName = "3 Nodes")]
		public int NodeLookback { get; set; }
		[NinjaScriptProperty] [Range(1.0, 5.0)] [Display(Name = "HVN factor (x avg)", Order = 1, GroupName = "3 Nodes")]
		public double HvnFactor { get; set; }
		[NinjaScriptProperty] [Range(0.0, 1.0)] [Display(Name = "LVN factor (x avg)", Order = 2, GroupName = "3 Nodes")]
		public double LvnFactor { get; set; }

		[XmlIgnore] [Display(Name = "POC", Order = 0, GroupName = "4 Colors")]
		public System.Windows.Media.Brush PocColor { get; set; }
		[Browsable(false)] public string PocColorSerialize { get { return Serialize.BrushToString(PocColor); } set { PocColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Value area", Order = 1, GroupName = "4 Colors")]
		public System.Windows.Media.Brush VaColor { get; set; }
		[Browsable(false)] public string VaColorSerialize { get { return Serialize.BrushToString(VaColor); } set { VaColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Prior session", Order = 2, GroupName = "4 Colors")]
		public System.Windows.Media.Brush PriorColor { get; set; }
		[Browsable(false)] public string PriorColorSerialize { get { return Serialize.BrushToString(PriorColor); } set { PriorColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "HVN", Order = 3, GroupName = "4 Colors")]
		public System.Windows.Media.Brush HvnColor { get; set; }
		[Browsable(false)] public string HvnColorSerialize { get { return Serialize.BrushToString(HvnColor); } set { HvnColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "LVN", Order = 4, GroupName = "4 Colors")]
		public System.Windows.Media.Brush LvnColor { get; set; }
		[Browsable(false)] public string LvnColorSerialize { get { return Serialize.BrushToString(LvnColor); } set { LvnColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Initial balance", Order = 5, GroupName = "4 Colors")]
		public System.Windows.Media.Brush IbColor { get; set; }
		[Browsable(false)] public string IbColorSerialize { get { return Serialize.BrushToString(IbColor); } set { IbColor = Serialize.StringToBrush(value); } }
		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "PATs Profile (VP)";
				Description = "Right-margin Volume Profile: POC, value area, HVN/LVN, RTH initial balance, prior-session zone, labels, composite.";
				IsOverlay = true; IsChartOnly = true; DrawOnPricePanel = true; IsSuspendedWhileInactive = true;
				RowTicks = 4; CompositeSessions = 1; VpWidthPx = 150; RightOffsetPx = 6;
				Opacity = 0.85; LabelFontSize = 11; IbMinutes = 60; RthStartHHMM = 930;
				ShowVP = true; ShowVAHVAL = true; ShowVABand = true; ShowPOC = true; ShowIB = true;
				ShowHVN = true; ShowLVN = true; ShowPriorLines = true; ShowPriorBand = true; ShowLabels = true;
				NodeLookback = 4; HvnFactor = 1.2; LvnFactor = 0.7;
				PocColor = System.Windows.Media.Brushes.Orange;
				VaColor = System.Windows.Media.Brushes.MediumPurple;
				PriorColor = System.Windows.Media.Brushes.SteelBlue;
				HvnColor = System.Windows.Media.Brushes.DarkTurquoise;
				LvnColor = System.Windows.Media.Brushes.IndianRed;
				IbColor = System.Windows.Media.Brushes.Goldenrod;
			}
			else if (State == State.Configure) { rowSize = RowTicks * TickSize; }
			else if (State == State.DataLoaded)
			{
				sessionStarts = new List<int>();
				tickHistBySession = new Dictionary<int, Dictionary<double, double>>();
				barVolBySession = new Dictionary<int, Dictionary<double, double>>();
				liveVolByRow = null; liveSessionStartBar = -1; obuSessionStartBar = -1;
			}
			else if (State == State.Realtime) { SeedLiveFromHistory(); }
		}

		// Runs exactly once, at the historical->realtime handoff. Without this,
		// the first live tick in OnMarketData would start today's session's
		// liveVolByRow from empty, silently discarding every bar that already
		// closed today before the chart/indicator was (re)loaded — today's VA
		// would visibly collapse to "from this moment forward" instead of the
		// full session. Seed with whatever's already known (tick-replayed
		// history if Tick Replay was on, else the bar-split approximation),
		// then let OnMarketData add real ticks on top from here forward.
		private void SeedLiveFromHistory()
		{
			if (obuSessionStartBar < 0 || CurrentBar < obuSessionStartBar) return;
			Dictionary<double, double> hist;
			Dictionary<double, double> seed = (tickHistBySession != null && tickHistBySession.TryGetValue(obuSessionStartBar, out hist) && hist.Count > 0)
				? new Dictionary<double, double>(hist)
				: BuildFromBars(obuSessionStartBar, CurrentBar);
			lock (liveLock)
			{
				liveVolByRow = seed;
				liveSessionStartBar = obuSessionStartBar;
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0) return;
			if (rowSize <= 0) rowSize = RowTicks * TickSize;

			bool newSession = (CurrentBar == 0 || Bars.IsFirstBarOfSession) &&
			                   (sessionStarts.Count == 0 || sessionStarts[sessionStarts.Count - 1] != CurrentBar);
			if (newSession)
			{
				sessionStarts.Add(CurrentBar);
				obuSessionStartBar = CurrentBar;
				devCumVol = new Dictionary<double, double>();
				devVah.Clear(); devVal.Clear(); devPoc.Clear();
				devSessionStart = CurrentBar;
				devFoldedThroughBar = CurrentBar - 1;
			}

			// Fold every bar strictly before the current (possibly still-forming) one into
			// the developing series, exactly once each. A `while` (not `if`) so this is
			// correct whether OnBarUpdate fires once per bar (normal) or many times per bar
			// (Tick Replay) -- it only advances when CurrentBar has actually moved past the
			// next unfolded bar, and it naturally replays the WHOLE session in order on a
			// fresh chart load too, so there's no separate historical-seeding step needed
			// here (unlike liveVolByRow, which this deliberately does not reuse).
			while (devCumVol != null && devFoldedThroughBar < CurrentBar - 1)
			{
				devFoldedThroughBar++;
				FoldBarIntoDev(devFoldedThroughBar);
			}

			// Historical tick-accurate accumulation — only active when the chart's
			// Data Series "Tick Replay" setting is on (Bars.IsTickReplay); otherwise
			// OnBarUpdate fires once per bar close exactly as before (no added cost).
			if (Bars.IsTickReplay && State == State.Historical)
			{
				Dictionary<double, double> hist;
				if (!tickHistBySession.TryGetValue(obuSessionStartBar, out hist))
				{ hist = new Dictionary<double, double>(); tickHistBySession[obuSessionStartBar] = hist; }
				double key = Math.Round(Math.Floor(Close[0] / rowSize) * rowSize, 5);
				double cv; hist.TryGetValue(key, out cv); hist[key] = cv + Volume[0];
			}
		}

		// Fires on every live trade print regardless of Calculate mode or
		// TickReplayHistory — this is what keeps today's session tick-accurate
		// for free, without opting into historical tick replay.
		protected override void OnMarketData(MarketDataEventArgs e)
		{
			if (e.MarketDataType != MarketDataType.Last) return;
			if (State != State.Realtime) return;
			if (rowSize <= 0) return;
			double key = Math.Round(Math.Floor(e.Price / rowSize) * rowSize, 5);
			lock (liveLock)
			{
				if (liveVolByRow == null || liveSessionStartBar != obuSessionStartBar)
				{
					liveVolByRow = new Dictionary<double, double>();
					liveSessionStartBar = obuSessionStartBar;
				}
				double cv; liveVolByRow.TryGetValue(key, out cv); liveVolByRow[key] = cv + e.Volume;
			}
		}

		#region Computation
		private void Recompute(int endBar)
		{
			volByRow = new Dictionary<double, double>();
			int sc = sessionStarts.Count;
			int wIdx = Math.Max(0, sc - Math.Max(1, CompositeSessions));
			int startBar = sc > 0 ? sessionStarts[wIdx] : 0;
			winStartBar = startBar;
			int lastStart = sc > 0 ? sessionStarts[sc - 1] : 0;
			todayStartBar = lastStart;

			for (int k = wIdx; k < sc; k++)
			{
				int a = sessionStarts[k];
				int b = (k + 1 < sc) ? sessionStarts[k + 1] - 1 : endBar;
				MergeSessionVolume(volByRow, a, a, b, k == sc - 1);
			}

			ComputeIB(lastStart, endBar);

			poc = double.NaN; maxVol = 0;
			foreach (KeyValuePair<double, double> kv in volByRow)
				if (kv.Value > maxVol) { maxVol = kv.Value; poc = kv.Key; }
			ValueAreaOf(volByRow, poc, out val, out vah);
			ComputeNodes();
			ComputePriorLevels();
		}

		// IB is an RTH-only concept: anchor to the first bar in today's session
		// whose time-of-day is >= RthStartHHMM (not to the session's own start
		// bar, which on an ETH-inclusive chart is the overnight/Globex open),
		// then take the high/low of the next IbMinutes of bars from there.
		private void ComputeIB(int lastStart, int endBar)
		{
			ibh = double.MinValue; ibl = double.MaxValue;
			TimeSpan rthTod = new TimeSpan(RthStartHHMM / 100, RthStartHHMM % 100, 0);
			int rthOpenBar = -1;
			for (int i = lastStart; i <= endBar; i++)
				if (Time.GetValueAt(i).TimeOfDay >= rthTod) { rthOpenBar = i; break; }
			if (rthOpenBar < 0) return; // today's session hasn't reached RTH open yet (or doesn't include it)

			DateTime ibEnd = Time.GetValueAt(rthOpenBar).AddMinutes(IbMinutes);
			for (int i = rthOpenBar; i <= endBar; i++)
			{
				if (Time.GetValueAt(i) >= ibEnd) break;
				double h = High.GetValueAt(i), l = Low.GetValueAt(i);
				if (h > ibh) ibh = h; if (l < ibl) ibl = l;
			}
		}

		// Fills `target` with one session's volume-at-price. Prefers real trade-tick
		// data when available (today always, via OnMarketData; earlier sessions only
		// if TickReplayHistory replayed them). Closed sessions are computed once and
		// cached — they never change, so there's no reason to re-walk their bars on
		// every recompute.
		private void MergeSessionVolume(Dictionary<double, double> target, int sessionStartBar, int a, int b, bool isToday)
		{
			Dictionary<double, double> snapshot = null;
			if (isToday)
			{
				lock (liveLock)
				{
					if (liveVolByRow != null && liveSessionStartBar == sessionStartBar && liveVolByRow.Count > 0)
						snapshot = new Dictionary<double, double>(liveVolByRow);
				}
				if (snapshot == null) snapshot = BuildFromBars(a, b); // no live ticks yet (e.g. pre-market attach)
			}
			else
			{
				if (!barVolBySession.TryGetValue(sessionStartBar, out snapshot))
				{
					Dictionary<double, double> hist;
					snapshot = (tickHistBySession.TryGetValue(sessionStartBar, out hist) && hist.Count > 0) ? hist : BuildFromBars(a, b);
					barVolBySession[sessionStartBar] = snapshot;
				}
			}
			foreach (KeyValuePair<double, double> kv in snapshot)
			{
				double cv; target.TryGetValue(kv.Key, out cv); target[kv.Key] = cv + kv.Value;
			}
		}

		// OHLC-bar-split approximation (fallback when no tick-level data is available).
		private Dictionary<double, double> BuildFromBars(int a, int b)
		{
			Dictionary<double, double> vol = new Dictionary<double, double>();
			for (int i = a; i <= b; i++)
			{
				double h = High.GetValueAt(i), l = Low.GetValueAt(i), v = Volume.GetValueAt(i);
				double lo = Math.Floor(l / rowSize) * rowSize;
				int nrows = (int)Math.Round((h - lo) / rowSize) + 1;
				if (nrows < 1) nrows = 1;
				double vShare = v / nrows;
				for (int r = 0; r < nrows; r++)
				{
					double key = Math.Round(lo + r * rowSize, 5);
					double cv; vol.TryGetValue(key, out cv); vol[key] = cv + vShare;
				}
			}
			return vol;
		}

		// Merges one bar's OHLC-approx volume into the running devCumVol total, then
		// records the resulting VA/POC as that bar's developing-series point. Always uses
		// the bar-split approximation (not tick data) -- this trail is about showing the
		// TRUE SHAPE of how VA moved through the session, not matching the main numbers'
		// tick-for-tick precision; keeping it simple also keeps the per-bar fold cheap.
		private void FoldBarIntoDev(int barIndex)
		{
			if (barIndex < devSessionStart) return;
			Dictionary<double, double> barVol = BuildFromBars(barIndex, barIndex);
			foreach (KeyValuePair<double, double> kv in barVol)
			{
				double cv; devCumVol.TryGetValue(kv.Key, out cv); devCumVol[kv.Key] = cv + kv.Value;
			}
			double p = double.NaN, mv = 0;
			foreach (KeyValuePair<double, double> kv in devCumVol) if (kv.Value > mv) { mv = kv.Value; p = kv.Key; }
			double vl, vh;
			ValueAreaOf(devCumVol, p, out vl, out vh);
			devVah.Add(vh); devVal.Add(vl); devPoc.Add(p);
		}

		// Dalton volume value area (MOM Appendix 1): from POC, add the heavier of
		// the two rows above vs the two below, until 70% of volume is enclosed.
		private void ValueAreaOf(Dictionary<double, double> vol, double pocv, out double valO, out double vahO)
		{
			List<double> prices = new List<double>(vol.Keys); prices.Sort();
			int n = prices.Count;
			if (n == 0 || double.IsNaN(pocv)) { valO = vahO = double.NaN; return; }
			int pocI = prices.IndexOf(pocv); if (pocI < 0) pocI = 0;
			double total = 0; foreach (double vv in vol.Values) total += vv;
			double target = 0.70 * total; double acc = vol[prices[pocI]];
			int lo = pocI, hi = pocI;
			while (acc < target && (lo > 0 || hi < n - 1))
			{
				double up = (hi + 1 < n ? vol[prices[hi + 1]] : 0) + (hi + 2 < n ? vol[prices[hi + 2]] : 0);
				double dn = (lo - 1 >= 0 ? vol[prices[lo - 1]] : 0) + (lo - 2 >= 0 ? vol[prices[lo - 2]] : 0);
				bool upok = hi < n - 1, dnok = lo > 0;
				if (upok && (up >= dn || !dnok)) for (int k = 0; k < 2 && hi < n - 1; k++) { hi++; acc += vol[prices[hi]]; }
				else if (dnok) for (int k = 0; k < 2 && lo > 0; k++) { lo--; acc += vol[prices[lo]]; }
				else break;
			}
			valO = prices[lo]; vahO = prices[hi];
		}

		// HVN = local volume peak > avg*HvnFactor; LVN = local trough < avg*LvnFactor.
		// Contiguous rows tied at the same volume collapse to a single flagged node
		// (the first row of the run) instead of marking every tied row.
		private void ComputeNodes()
		{
			hvn = new List<double>(); lvn = new List<double>();
			List<double> prices = new List<double>(volByRow.Keys); prices.Sort();
			int n = prices.Count; if (n < 3) return;
			double total = 0; foreach (double v in volByRow.Values) total += v;
			double avg = total / n;
			for (int i = 0; i < n; i++)
			{
				double v = volByRow[prices[i]];
				bool isMax = true, isMin = true;
				for (int j = Math.Max(0, i - NodeLookback); j <= Math.Min(n - 1, i + NodeLookback); j++)
				{
					if (j == i) continue;
					double vj = volByRow[prices[j]];
					if (vj > v) isMax = false;
					if (vj < v) isMin = false;
				}
				bool tiedWithPrevFlagged = i > 0 && volByRow[prices[i - 1]] == v;
				if (isMax && v >= avg * HvnFactor && !(tiedWithPrevFlagged && hvn.Count > 0 && hvn[hvn.Count - 1] == prices[i - 1])) hvn.Add(prices[i]);
				if (isMin && v <= avg * LvnFactor && !(tiedWithPrevFlagged && lvn.Count > 0 && lvn[lvn.Count - 1] == prices[i - 1])) lvn.Add(prices[i]);
			}
		}

		private void ComputePriorLevels()
		{
			pPoc = pVah = pVal = double.NaN;
			priorStartBar = -1;
			int sc = sessionStarts.Count;
			if (sc < 2) return;
			int ps = sessionStarts[sc - 2];
			int pe = sessionStarts[sc - 1] - 1;
			if (pe < ps) return;
			priorStartBar = ps;
			Dictionary<double, double> pvol = new Dictionary<double, double>();
			MergeSessionVolume(pvol, ps, ps, pe, false);
			if (pvol.Count == 0) return;
			double mv = 0;
			foreach (KeyValuePair<double, double> kv in pvol) if (kv.Value > mv) { mv = kv.Value; pPoc = kv.Key; }
			ValueAreaOf(pvol, pPoc, out pVal, out pVah);
		}
		#endregion

		private SharpDX.Color4 Dx(System.Windows.Media.Brush b, float alpha)
		{
			System.Windows.Media.SolidColorBrush scb = b as System.Windows.Media.SolidColorBrush;
			if (scb == null) return new SharpDX.Color4(0.6f, 0.6f, 0.6f, alpha);
			System.Windows.Media.Color c = scb.Color;
			return new SharpDX.Color4(c.R / 255f, c.G / 255f, c.B / 255f, alpha);
		}

		private class Lbl { public float y; public string text; public SolidColorBrush brush; public float trueY; public int col; }

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (sessionStarts == null || RenderTarget == null || ChartBars == null || Bars == null) return;
			int endBar = Bars.Count - 1;
			if (endBar < 0) return;
			Recompute(endBar); // cheap now (cached closed sessions) — keeps today's VA current with live ticks
			if (volByRow == null || volByRow.Count == 0 || maxVol <= 0) return;

			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f) rowH = 1f;
			float panelLeft = (float)ChartPanel.X;
			float winStartX = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, winStartBar));
			float todayStartX = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, todayStartBar));
			float priorStartX = priorStartBar >= 0 ? Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, priorStartBar)) : panelLeft;
			float vpLeft = chartControl.GetXByBarIndex(ChartBars, endBar) + RightOffsetPx;
			float vpMaxRight = vpLeft + VpWidthPx;

			// brushes
			SolidColorBrush teal = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.35f, 0.71f, 0.82f, (float)Opacity));
			SolidColorBrush pocBr = new SolidColorBrush(RenderTarget, Dx(PocColor, 0.95f));
			SolidColorBrush vaLineBr = new SolidColorBrush(RenderTarget, Dx(VaColor, 0.9f));
			SolidColorBrush vaBandBr = new SolidColorBrush(RenderTarget, Dx(VaColor, 0.12f));
			SolidColorBrush ibBr = new SolidColorBrush(RenderTarget, Dx(IbColor, 0.8f));
			SolidColorBrush priorLineBr = new SolidColorBrush(RenderTarget, Dx(PriorColor, 0.85f));
			SolidColorBrush priorBandBr = new SolidColorBrush(RenderTarget, Dx(PriorColor, 0.14f));
			SolidColorBrush hvnBr = new SolidColorBrush(RenderTarget, Dx(HvnColor, 0.95f));
			SolidColorBrush lvnBr = new SolidColorBrush(RenderTarget, Dx(LvnColor, 0.95f));
			HashSet<double> hvnSet = new HashSet<double>(hvn ?? new List<double>());
			HashSet<double> lvnSet = new HashSet<double>(lvn ?? new List<double>());

			// bands (behind). Current VA band only spans winStartX..todayStartX -- the
			// COMPLETED prior days inside a composite window, where a flat band is an
			// honest fact. It deliberately stops at today's own bars instead of extending
			// through them: see the developing staircase below for today's true history.
			if (ShowVABand && !double.IsNaN(vah) && todayStartX > winStartX)
			{
				float y1 = chartScale.GetYByValue(vah), y2 = chartScale.GetYByValue(val);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(winStartX, Math.Min(y1, y2), todayStartX - winStartX, Math.Abs(y2 - y1)), vaBandBr);
			}
			if (ShowPriorBand && !double.IsNaN(pVah))
			{
				float y1 = chartScale.GetYByValue(pVah), y2 = chartScale.GetYByValue(pVal);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(priorStartX, Math.Min(y1, y2), vpMaxRight - priorStartX, Math.Abs(y2 - y1)), priorBandBr);
			}

			// rows: VP bars (with node coloring)
			if (ShowVP)
			{
				foreach (KeyValuePair<double, double> kv in volByRow)
				{
					double price = kv.Key;
					float yTop = chartScale.GetYByValue(price + rowSize);
					float w = (float)(VpWidthPx * kv.Value / maxVol);
					SolidColorBrush br = teal;
					if (ShowPOC && price == poc) br = pocBr;
					else if (ShowHVN && hvnSet.Contains(price)) br = hvnBr;
					else if (ShowLVN && lvnSet.Contains(price)) br = lvnBr;
					RenderTarget.FillRectangle(new SharpDX.RectangleF(vpLeft, yTop, w, rowH - 1f), br);
				}
			}

			// lines (current). Same winStartX..todayStartX trim as the band above, same
			// reason -- only the completed-prior-days portion is a flat, honest fact.
			if (todayStartX > winStartX)
			{
				if (ShowPOC && !double.IsNaN(poc)) DrawLevel(chartScale, winStartX, todayStartX, poc, pocBr, 1.4f);
				if (ShowVAHVAL && !double.IsNaN(vah)) { DrawLevel(chartScale, winStartX, todayStartX, vah, vaLineBr, 1.0f); DrawLevel(chartScale, winStartX, todayStartX, val, vaLineBr, 1.0f); }
			}
			if (ShowIB && ibh > double.MinValue) { DrawLevel(chartScale, todayStartX, vpMaxRight, ibh, ibBr, 0.9f); DrawLevel(chartScale, todayStartX, vpMaxRight, ibl, ibBr, 0.9f); }
			DrawDevelopingVA(chartScale, chartControl, todayStartX, vpMaxRight, endBar, pocBr, vaLineBr, vaBandBr);
			// lines (prior)
			if (ShowPriorLines && !double.IsNaN(pVah))
			{
				DrawLevel(chartScale, priorStartX, vpMaxRight, pVah, priorLineBr, 1.0f);
				DrawLevel(chartScale, priorStartX, vpMaxRight, pVal, priorLineBr, 1.0f);
				DrawLevel(chartScale, priorStartX, vpMaxRight, pPoc, priorLineBr, 1.5f);
			}

			// labels (de-collided, with leaders), placed right of the profile
			if (ShowLabels)
			{
				float labelX = vpMaxRight + 8f;
				List<Lbl> labels = new List<Lbl>();
				// column 0 = current session
				if (ShowPOC && !double.IsNaN(poc)) AddLbl(labels, chartScale, "POC " + FmtP(poc), poc, pocBr, 0);
				if (ShowVAHVAL && !double.IsNaN(vah)) { AddLbl(labels, chartScale, "VAH " + FmtP(vah), vah, vaLineBr, 0); AddLbl(labels, chartScale, "VAL " + FmtP(val), val, vaLineBr, 0); }
				if (ShowIB && ibh > double.MinValue) { AddLbl(labels, chartScale, "IBH " + FmtP(ibh), ibh, ibBr, 0); AddLbl(labels, chartScale, "IBL " + FmtP(ibl), ibl, ibBr, 0); }
				// column 1 = prior VOLUME value area
				if (ShowPriorLines && !double.IsNaN(pVah)) { AddLbl(labels, chartScale, "pVAH " + FmtP(pVah), pVah, priorLineBr, 1); AddLbl(labels, chartScale, "pPOC " + FmtP(pPoc), pPoc, priorLineBr, 1); AddLbl(labels, chartScale, "pVAL " + FmtP(pVal), pVal, priorLineBr, 1); }
				DrawLabels(labels, labelX, vpMaxRight);
			}

			teal.Dispose(); pocBr.Dispose(); vaLineBr.Dispose(); vaBandBr.Dispose(); ibBr.Dispose();
			priorLineBr.Dispose(); priorBandBr.Dispose();
			hvnBr.Dispose(); lvnBr.Dispose();
		}

		private void DrawLevel(ChartScale cs, float x0, float x1, double price, SolidColorBrush br, float wdt)
		{
			float y = cs.GetYByValue(price);
			RenderTarget.DrawLine(new SharpDX.Vector2(x0, y), new SharpDX.Vector2(x1, y), br, wdt);
		}

		// Today's VA as a connected, filled staircase instead of a flat backward-extended
		// band: each historical point is the VA as of that bar's CLOSE (devVah/devVal,
		// folded incrementally -- see FoldBarIntoDev), rendered step-after (the value holds
		// flat across the bar it was computed from, then jumps -- via a drawn vertical riser,
		// not just an implied gap -- to the next bar's value). The final segment is the LIVE
		// tip: today-only VA as of right now, extended through to the VP margin so the
		// staircase visually connects into the current profile panel. Reuses the same
		// ShowVABand/ShowVAHVAL/ShowPOC toggles and brushes as the (now prior-days-only)
		// static band/lines above -- this IS that same concept, just rendered honestly for
		// a still-developing session instead of as a single backward-projected snapshot.
		private void DrawDevelopingVA(ChartScale cs, ChartControl cc, float startX, float vpRight, int endBar,
			SolidColorBrush pocBr, SolidColorBrush lineBr, SolidColorBrush fillBr)
		{
			if (devSessionStart < 0 || todayStartBar < 0) return;

			int n = devVah.Count;
			List<float> xs = new List<float>(n + 1);
			List<double> vhs = new List<double>(n + 1);
			List<double> vls = new List<double>(n + 1);
			List<double> ps = new List<double>(n + 1);
			for (int k = 0; k < n; k++)
			{
				xs.Add(cc.GetXByBarIndex(ChartBars, devSessionStart + k + 1)); // boundary = start of next bar
				vhs.Add(devVah[k]); vls.Add(devVal[k]); ps.Add(devPoc[k]);
			}

			// live tip: today-only VA as of right now (correct regardless of CompositeSessions
			// -- reuses the exact same today-prefers-live-ticks logic the main VA uses).
			Dictionary<double, double> todayNow = new Dictionary<double, double>();
			MergeSessionVolume(todayNow, todayStartBar, todayStartBar, endBar, true);
			if (todayNow.Count > 0)
			{
				double tp = double.NaN, tmv = 0;
				foreach (KeyValuePair<double, double> kv in todayNow) if (kv.Value > tmv) { tmv = kv.Value; tp = kv.Key; }
				double tvl, tvh;
				ValueAreaOf(todayNow, tp, out tvl, out tvh);
				xs.Add(vpRight); // stretch the final segment into the VP margin panel
				vhs.Add(tvh); vls.Add(tvl); ps.Add(tp);
			}

			int cnt = xs.Count;
			if (cnt == 0) return;

			float prevX = startX;
			for (int k = 0; k < cnt; k++)
			{
				float x = xs[k];
				if (x > prevX)
				{
					float yh = cs.GetYByValue(vhs[k]), yl = cs.GetYByValue(vls[k]);
					if (ShowVABand)
						RenderTarget.FillRectangle(new SharpDX.RectangleF(prevX, Math.Min(yh, yl), x - prevX, Math.Abs(yl - yh)), fillBr);
					if (ShowVAHVAL)
					{
						RenderTarget.DrawLine(new SharpDX.Vector2(prevX, yh), new SharpDX.Vector2(x, yh), lineBr, 1.2f);
						RenderTarget.DrawLine(new SharpDX.Vector2(prevX, yl), new SharpDX.Vector2(x, yl), lineBr, 1.2f);
					}
					if (ShowPOC)
					{
						float yp = cs.GetYByValue(ps[k]);
						RenderTarget.DrawLine(new SharpDX.Vector2(prevX, yp), new SharpDX.Vector2(x, yp), pocBr, 1.2f);
					}
				}
				if (k + 1 < cnt)
				{
					if (ShowVAHVAL)
					{
						float yh = cs.GetYByValue(vhs[k]), yhN = cs.GetYByValue(vhs[k + 1]);
						float yl = cs.GetYByValue(vls[k]), ylN = cs.GetYByValue(vls[k + 1]);
						RenderTarget.DrawLine(new SharpDX.Vector2(x, yh), new SharpDX.Vector2(x, yhN), lineBr, 1.2f);
						RenderTarget.DrawLine(new SharpDX.Vector2(x, yl), new SharpDX.Vector2(x, ylN), lineBr, 1.2f);
					}
					if (ShowPOC)
					{
						float yp = cs.GetYByValue(ps[k]), ypN = cs.GetYByValue(ps[k + 1]);
						RenderTarget.DrawLine(new SharpDX.Vector2(x, yp), new SharpDX.Vector2(x, ypN), pocBr, 1.2f);
					}
				}
				prevX = x;
			}
		}

		private void AddLbl(List<Lbl> list, ChartScale cs, string text, double price, SolidColorBrush br, int col)
		{
			float y = cs.GetYByValue(price);
			list.Add(new Lbl { y = y, trueY = y, text = text, brush = br, col = col });
		}

		// Each column is a separate x-slot; de-collide vertically within each column.
		private void DrawLabels(List<Lbl> labels, float baseX, float leaderFromX)
		{
			if (labels.Count == 0) return;
			float colW = LabelFontSize * 6.5f;
			float gap = LabelFontSize + 4f;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			for (int c = 0; c <= 1; c++)
			{
				List<Lbl> col = new List<Lbl>();
				foreach (Lbl L in labels) if (L.col == c) col.Add(L);
				if (col.Count == 0) continue;
				col.Sort(delegate (Lbl a, Lbl b) { return a.y.CompareTo(b.y); });
				for (int i = 1; i < col.Count; i++)
					if (col[i].y < col[i - 1].y + gap) col[i].y = col[i - 1].y + gap;
				float x = baseX + c * colW;
				foreach (Lbl L in col)
				{
					if (Math.Abs(L.y - L.trueY) > 1.5f)
						RenderTarget.DrawLine(new SharpDX.Vector2(x - 6f, L.trueY), new SharpDX.Vector2(x - 1f, L.y + LabelFontSize * 0.5f), L.brush, 0.6f);
					RenderTarget.DrawText(L.text, tf, new SharpDX.RectangleF(x, L.y, colW, LabelFontSize + 6f), L.brush);
				}
			}
			tf.Dispose();
		}

		private string FmtP(double p)
		{
			return p.ToString("0.##");
		}
	}
}
