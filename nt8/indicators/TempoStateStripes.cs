// TempoStateStripes.cs — S116-tempo v2 companion: the state/regime RACING-STRIPES panel.
//
// v2 = SELF-CALIBRATING, same engine as TempoSpeedometer v2: per-time-of-day percentile
// distributions (96 x 15-min buckets over the 24h CHART clock) built from the chart's
// own loaded bars, trailing ~TrailingDays sessions. No CSV, no timezone code. Keep the
// state rules in sync with TempoSpeedometer.StateLabel. Descriptive only.
//
// Own panel, seven lanes; each completed bar fills a cell in its active lane:
//   CLIMAX    gold      (tempo >= ClimacticPct for this time of day — matches the dots)
//   EXPAND    teal/red  (fast + big + efficient, colored by direction)
//   CHURN     orange    (fast + big + inefficient)
//   ACTIVITY  magenta   (fast, no amplitude)
//   GRIND     pale t/r  (slow + directional)
//   BALANCE   blue      (slow + small = quiet)
//   MIXED     gray      (everything else)
//
// Per-bar values land in the Data Box via transparent plots:
//   State (0..6 in lane order above), TempoPct, AmplitudePct, EffPct, TicksPerSec, DurationSec.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	public class TempoStateStripes : Indicator
	{
		private const int TODB = 96;
		private const int MIN_SAMPLES = 30;
		private const int NLANES = 7;
		private static readonly string[] LaneNames = { "CLIMAX", "EXPAND", "CHURN", "ACTIVITY", "GRIND", "BALANCE", "MIXED" };

		private double[][] bufT, bufA;
		private int[] cntT, cntA;
		private int cap;

		private Series<double> stateS, dirS;
		private List<double> rollTempo, rollRange, rollEff;
		private double emaClose;
		private bool emaInit, notTickChart;
		private readonly List<double> lastRanges = new List<double>();     // prior 8 bar ranges (ABR-8)
		// 10-bar trend window (EXPAND/GRIND are multi-bar states; reset each session)
		private readonly List<double> w10cl = new List<double>();
		private readonly List<double> w10rng = new List<double>();
		private readonly List<double> w10tp = new List<double>();

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "S116 tempo state stripes v2: self-calibrating 7-lane regime timeline (matches TempoSpeedometer). Observational only.";
				Name = "TempoStateStripes";
				Calculate = Calculate.OnBarClose;
				IsOverlay = false;
				DisplayInDataBox = true;
				PaintPriceMarkers = false;
				IsSuspendedWhileInactive = true;

				// visible brushes: the Data Box paints each row's TEXT with its plot brush
				// (Transparent = invisible rows). Lines never draw — OnRender below skips
				// base plot rendering; only the lanes are painted.
				AddPlot(System.Windows.Media.Brushes.Gray,       "State");
				AddPlot(System.Windows.Media.Brushes.DarkOrange, "TempoPct");
				AddPlot(System.Windows.Media.Brushes.SteelBlue,  "AmpPctOfABR8");  // bar range as % of the prior-8-bar average range
				AddPlot(System.Windows.Media.Brushes.SeaGreen,   "EffPct");
				AddPlot(System.Windows.Media.Brushes.Chocolate,  "TicksPerSec");
				AddPlot(System.Windows.Media.Brushes.DimGray,    "DurationSec");

				TrailingDays = 60;
				RollingWindow = 200;
				ClimacticPct = 95;
			}
			else if (State == State.Configure)
			{
				rollTempo = new List<double>(); rollRange = new List<double>(); rollEff = new List<double>();
			}
			else if (State == State.DataLoaded)
			{
				stateS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				dirS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				notTickChart = BarsPeriod.BarsPeriodType != BarsPeriodType.Tick;
				cap = Math.Max(80, TrailingDays * 8);
				bufT = new double[TODB][]; bufA = new double[TODB][];
				cntT = new int[TODB]; cntA = new int[TODB];
				for (int b = 0; b < TODB; b++) { bufT[b] = new double[cap]; bufA[b] = new double[cap]; }
			}
		}

		private double PctFromBuf(double[] buf, int cnt, double v)
		{
			int n = Math.Min(cnt, cap);
			if (n < MIN_SAMPLES) return -1;
			int below = 0;
			for (int i = 0; i < n; i++) if (buf[i] <= v) below++;
			return Math.Max(1, Math.Min(99, 100.0 * below / (n + 1)));
		}

		private static double PctFromRolling(List<double> w, double v)
		{
			if (w.Count < 30) return 50;
			int below = 0;
			for (int i = 0; i < w.Count; i++) if (w[i] <= v) below++;
			return Math.Max(1, Math.Min(99, 100.0 * below / (w.Count + 1)));
		}

		private static void Push(List<double> w, double v, int capN)
		{
			w.Add(v);
			if (w.Count > capN) w.RemoveAt(0);
		}

		protected override void OnBarUpdate()
		{
			stateS[0] = double.NaN; dirS[0] = 0;
			if (notTickChart || CurrentBar < 1 || Bars.IsFirstBarOfSession)
			{
				if (Bars.IsFirstBarOfSession) { w10cl.Clear(); w10rng.Clear(); w10tp.Clear(); }
				for (int p = 0; p < 6; p++) Values[p].Reset();
				return;
			}

			double duration = (Time[0] - Time[1]).TotalSeconds;
			if (duration < 0.001) duration = 0.001;
			double tempo = BarsPeriod.Value / duration;
			double range = High[0] - Low[0];
			double eff = range > 0 ? Math.Abs(Close[0] - Open[0]) / range : 0;

			int bucket = (int)(Time[0].TimeOfDay.TotalMinutes / 15.0);
			if (bucket < 0) bucket = 0;
			if (bucket > TODB - 1) bucket = TODB - 1;

			double tPct = PctFromBuf(bufT[bucket], cntT[bucket], tempo);
			double aPct = PctFromBuf(bufA[bucket], cntA[bucket], range);
			bool warm = tPct < 0 || aPct < 0;
			if (tPct < 0) tPct = PctFromRolling(rollTempo, tempo);
			if (aPct < 0) aPct = PctFromRolling(rollRange, range);
			double ePct = PctFromRolling(rollEff, eff);

			bufT[bucket][cntT[bucket] % cap] = tempo; cntT[bucket]++;
			bufA[bucket][cntA[bucket] % cap] = range; cntA[bucket]++;
			Push(rollTempo, tempo, RollingWindow);
			Push(rollRange, range, RollingWindow);
			Push(rollEff, eff, RollingWindow);

			double k = 2.0 / 21.0;
			if (!emaInit) { emaClose = Close[0]; emaInit = true; }
			bool bull = Close[0] >= emaClose;
			emaClose += k * (Close[0] - emaClose);

			// SAME rules as TempoSpeedometer (keep in sync). EXPAND/GRIND are 10-bar states
			// (gate calibrated 2026-09-11: eff10>=0.30 & t10>=50); no gold during warmup.
			w10cl.Add(Close[0]); w10rng.Add(range); w10tp.Add(tPct);
			if (w10cl.Count > 11) { w10cl.RemoveAt(0); w10rng.RemoveAt(0); w10tp.RemoveAt(0); }
			double eff10 = double.NaN, t10 = double.NaN, net10 = 0;
			if (w10cl.Count == 11)
			{
				net10 = w10cl[10] - w10cl[0];
				double sr = 0, st = 0;
				for (int i = 1; i <= 10; i++) { sr += w10rng[i]; st += w10tp[i]; }
				if (sr > 0) eff10 = Math.Abs(net10) / sr;
				t10 = st / 10.0;
			}
			bool trending = !double.IsNaN(eff10) && eff10 >= 0.30;
			int state;
			if (!warm && tPct >= ClimacticPct) state = 0;                     // CLIMAX
			else if (trending && t10 >= 50) state = 1;                        // EXPAND (multi-bar)
			else if (!double.IsNaN(eff10) && t10 >= 60 && eff10 <= 0.10) state = 2; // CHURN
			else if (trending) state = 4;                                     // GRIND
			else if (tPct >= 80 && aPct < 50) state = 3;                      // ACTIVITY
			else if (tPct < 40 && aPct < 40) state = 5;                       // BALANCE
			else state = 6;                                                   // MIXED
			stateS[0] = state;
			dirS[0] = (state == 1 || state == 4) ? (net10 >= 0 ? 1 : -1) : (bull ? 1 : -1);

			double abr = 0;
			for (int i = 0; i < lastRanges.Count; i++) abr += lastRanges[i];
			abr = lastRanges.Count > 0 ? abr / lastRanges.Count : double.NaN;
			double ampAbr = abr > 0 ? 100.0 * range / abr : double.NaN;
			lastRanges.Add(range);
			if (lastRanges.Count > 8) lastRanges.RemoveAt(0);

			Values[0][0] = state;
			Values[1][0] = Math.Round(tPct);
			Values[2][0] = double.IsNaN(ampAbr) ? double.NaN : Math.Round(ampAbr);
			Values[3][0] = Math.Round(ePct);
			Values[4][0] = Math.Round(tempo, 1);
			Values[5][0] = Math.Round(duration, 1);
		}

		private SharpDX.Color4 LaneColor(int state, double dir)
		{
			switch (state)
			{
				case 0: return new SharpDX.Color4(1f, 0.84f, 0f, 1f);
				case 1: return dir >= 0 ? new SharpDX.Color4(0.10f, 0.62f, 0.44f, 1f)
									   : new SharpDX.Color4(0.89f, 0.29f, 0.28f, 1f);
				case 2: return new SharpDX.Color4(0.85f, 0.35f, 0.15f, 1f);
				case 3: return new SharpDX.Color4(0.84f, 0.32f, 0.51f, 1f);
				case 4: return dir >= 0 ? new SharpDX.Color4(0.56f, 0.82f, 0.74f, 1f)
									   : new SharpDX.Color4(0.94f, 0.64f, 0.61f, 1f);
				case 5: return new SharpDX.Color4(0.22f, 0.53f, 0.90f, 1f);
				default: return new SharpDX.Color4(0.60f, 0.63f, 0.65f, 1f);
			}
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (RenderTarget == null || ChartBars == null || ChartPanel == null) return;

			TextFormat tfTiny = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 9f);
			SolidColorBrush dim = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.45f, 0.47f, 0.50f, 1f));
			SolidColorBrush sep = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.5f, 0.5f, 0.5f, 0.18f));
			try
			{
				if (notTickChart)
				{
					RenderTarget.DrawText("TempoStateStripes: needs a TICK chart", tfTiny,
						new SharpDX.RectangleF(ChartPanel.X + 8, ChartPanel.Y + 8, 400, 14), dim);
					return;
				}
				float top = ChartPanel.Y + 2f, hAll = ChartPanel.H - 6f;
				float laneH = hAll / NLANES;
				int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
				float w = 3f;
				if (to > from)
					w = Math.Max(1f, (float)chartControl.GetXByBarIndex(ChartBars, from + 1)
									 - chartControl.GetXByBarIndex(ChartBars, from));

				for (int l = 1; l < NLANES; l++)
					RenderTarget.DrawLine(new SharpDX.Vector2(ChartPanel.X, top + l * laneH),
						new SharpDX.Vector2(ChartPanel.X + ChartPanel.W, top + l * laneH), sep);

				for (int i = Math.Max(0, from); i <= to && i <= CurrentBar; i++)
				{
					double sv = stateS.GetValueAt(i);
					if (double.IsNaN(sv)) continue;
					int st = (int)sv;
					float x = chartControl.GetXByBarIndex(ChartBars, i);
					SolidColorBrush cb = new SolidColorBrush(RenderTarget, LaneColor(st, dirS.GetValueAt(i)));
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x - w / 2f, top + st * laneH + 1f,
						Math.Max(1f, w), laneH - 2f), cb);
					cb.Dispose();
				}

				for (int l = 0; l < NLANES; l++)
					RenderTarget.DrawText(LaneNames[l], tfTiny,
						new SharpDX.RectangleF(ChartPanel.X + 4, top + l * laneH + (laneH - 11f) / 2f, 70, 12), dim);

			}
			finally { tfTiny.Dispose(); dim.Dispose(); sep.Dispose(); }
		}

		#region properties
		[NinjaScriptProperty, Range(5, 250)]
		[Display(Name = "Self-calibration depth (sessions)", GroupName = "1. Calibration", Order = 0)]
		public int TrailingDays { get; set; }

		[NinjaScriptProperty, Range(30, 2000)]
		[Display(Name = "Warmup rolling window (bars)", GroupName = "1. Calibration", Order = 1)]
		public int RollingWindow { get; set; }

		[NinjaScriptProperty, Range(50, 100)]
		[Display(Name = "Climactic percentile (match TempoSpeedometer)", GroupName = "1. Calibration", Order = 2)]
		public int ClimacticPct { get; set; }
		#endregion
	}
}
