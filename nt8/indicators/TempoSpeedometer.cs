// TempoSpeedometer.cs — S116-tempo v2: the ES 2000-tick "speedometer" (observational, not predictive).
//
// v2 = SELF-CALIBRATING. No CSV, no timezone conversion, no session-template dependence.
// The indicator builds its own time-of-day distributions (96 x 15-min buckets over the
// 24h CHART clock) from the chart's own loaded bars, trailing ~TrailingDays sessions.
// Any clock offset cancels because history and the current bar share the same clock;
// the feed matches itself by definition; and calibration is the CURRENT market, not a
// 5-year pool (2021 climax share 1.8% vs 2025 10.1% — the market drifted; see
// tempo/outputs/climax_share_diag_2026-09-10.csv).
//
// On a TICK chart (built for ES 2000t):
//   • Bar opacity = tempo percentile for this time of day (quadratic curve).
//   • Climactic bars (>= ClimacticPct): direction color + gold outline + gold dot above.
//   • Speedometer block: TEMPO/AMPLITUDE/EFFICIENCY pctiles, accel state, state label,
//     live pace-of-tape (realtime), optional climax audio alert, DIAG line.
//   • Session heat strip + 2D tempo x amplitude engine dot.
//
// Warmup: a bucket activates at 30 samples (~4-5 loaded days); until then the global
// rolling window scores the bar and DIAG shows WARM. Load >= 10 days on the chart
// (30+ recommended) so all buckets calibrate.
// Keep state rules in sync with TempoStateStripes.cs.

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
	public class TempoSpeedometer : Indicator
	{
		private const int TODB = 96;                      // 15-min buckets over the 24h chart clock
		private const int MIN_SAMPLES = 30;

		private double[][] bufT, bufA;                    // per-bucket ring buffers (tempo, range)
		private int[] cntT, cntA;
		private int cap;

		private Series<double> tempoPctS, ampPctS, climaxS, effPctS, durS, stateCodeS;
		private List<double> rollTempo, rollRange, rollEff;
		private double emaTempo, emaClose;
		private bool emaInit;

		// chartMode: 0 = tick chart (original path, byte-identical) · 1 = time chart +
		// Tick Replay (tempo from counted prints per bar) · 2 = unsupported (warning only)
		private int chartMode = 2;
		private int tickInBar;
		private readonly List<int> sessStarts = new List<int>();   // bar index of each session's first bar
		private double lastTempoPct = 50, lastAmpPct = 50, lastEffPct = 50, lastAmpAbr = double.NaN;
		private readonly List<double> lastRanges = new List<double>();     // prior 8 bar ranges (ABR-8)
		// 10-bar trend window (EXPAND/GRIND are multi-bar states; reset each session)
		private readonly List<double> w10cl = new List<double>();
		private readonly List<double> w10rng = new List<double>();
		private readonly List<double> w10tp = new List<double>();
		private int lastAccel, lastBucket, lastN;
		private double lastRate;
		private DateTime lastBarTime = DateTime.MinValue;
		private string lastState = "";
		private bool lastClimax, notTickChart;

		private readonly Queue<DateTime> tapeQ = new Queue<DateTime>();
		private double livePacePct = double.NaN;
		private DateTime lastAlertTime = DateTime.MinValue;

		private Dictionary<int, System.Windows.Media.Brush> brushCache;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description   = "S116 tempo speedometer v2: SELF-calibrating time-of-day percentiles from the chart's own bars. Observational only.";
				Name          = "TempoSpeedometer";
				Calculate     = Calculate.OnBarClose;
				IsOverlay     = true;
				DisplayInDataBox = true;
				PaintPriceMarkers = false;
				IsAutoScale   = false;                     // plot values are 0-100, must not touch the price scale
				IsSuspendedWhileInactive = true;

				// Data Box rows (visible brushes = visible row text). Lines never draw:
				// OnRender below does NOT call the base plot renderer.
				AddPlot(System.Windows.Media.Brushes.Gray,       "State");   // 0 CLIMAX 1 EXPAND 2 CHURN 3 ACTIVITY 4 GRIND 5 BALANCE 6 MIXED
				AddPlot(System.Windows.Media.Brushes.DarkOrange, "TempoPct");
				AddPlot(System.Windows.Media.Brushes.SteelBlue,  "AmpPctOfABR8");  // bar range as % of the prior-8-bar average range
				AddPlot(System.Windows.Media.Brushes.SeaGreen,   "EffPct");
				AddPlot(System.Windows.Media.Brushes.Chocolate,  "TicksPerSec");
				AddPlot(System.Windows.Media.Brushes.DimGray,    "DurationSec");

				TrailingDays   = 60;
				RollingWindow  = 200;
				ClimacticPct   = 95;
				ClimaxTagPct   = 99;
				MinOpacityPct  = 10;
				ShowSpeedo     = true;
				ShowHeatStrip  = true;
				ShowEngineDot  = true;
				ShowStateLabel = true;
				ShowDiag       = true;
				ShowClimaxFlip = true;
				PaceWindowSec  = 30;
				AlertOnClimax  = false;
				AlertCooldownSec = 120;

				UpColor        = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0x26, 0xa6, 0x9a));
				DownColor      = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0xef, 0x53, 0x50));
				ClimacticColor = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0xff, 0xd7, 0x00));
				UpColor.Freeze(); DownColor.Freeze(); ClimacticColor.Freeze();
			}
			else if (State == State.Configure)
			{
				brushCache = new Dictionary<int, System.Windows.Media.Brush>();
				rollTempo = new List<double>(); rollRange = new List<double>(); rollEff = new List<double>();
			}
			else if (State == State.DataLoaded)
			{
				tempoPctS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				ampPctS   = new Series<double>(this, MaximumBarsLookBack.Infinite);
				climaxS   = new Series<double>(this, MaximumBarsLookBack.Infinite);
				effPctS   = new Series<double>(this, MaximumBarsLookBack.Infinite);
				durS      = new Series<double>(this, MaximumBarsLookBack.Infinite);
				stateCodeS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				if (BarsPeriod.BarsPeriodType == BarsPeriodType.Tick) chartMode = 0;
				else if (Bars.IsTickReplay && (BarsPeriod.BarsPeriodType == BarsPeriodType.Minute
					|| BarsPeriod.BarsPeriodType == BarsPeriodType.Second)) chartMode = 1;
				else chartMode = 2;
				notTickChart = chartMode == 2;
				cap = Math.Max(80, TrailingDays * 8);      // ~8 bars per 15-min bucket per session
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
			tempoPctS[0] = double.NaN;
			ampPctS[0]   = double.NaN;
			climaxS[0]   = 0;
			effPctS[0]   = double.NaN;
			durS[0]      = double.NaN;
			stateCodeS[0] = double.NaN;

			if (notTickChart || CurrentBar < 1 || Bars.IsFirstBarOfSession)
			{
				if (Bars.IsFirstBarOfSession)
				{
					w10cl.Clear(); w10rng.Clear(); w10tp.Clear();
					if (sessStarts.Count == 0 || sessStarts[sessStarts.Count - 1] != CurrentBar)
						sessStarts.Add(CurrentBar);
				}
				tickInBar = 0;
				for (int p = 0; p < 6; p++) Values[p].Reset();   // blank Data Box rows
				return;
			}

			double duration = (Time[0] - Time[1]).TotalSeconds;
			if (duration < 0.001) duration = 0.001;
			double nticks;
			if (chartMode == 0)
				nticks = BarsPeriod.Value;                       // tick chart: unchanged
			else
			{
				nticks = tickInBar; tickInBar = 0;               // time chart: counted prints (Tick Replay)
				if (nticks < 10)                                  // no replay data for this bar -> skip
				{
					for (int p = 0; p < 6; p++) Values[p].Reset();
					return;
				}
			}
			double tempo = nticks / duration;
			double range = High[0] - Low[0];
			double eff   = range > 0 ? Math.Abs(Close[0] - Open[0]) / range : 0;

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
			Push(rollEff,   eff,   RollingWindow);

			double k = 2.0 / 21.0;
			if (!emaInit) { emaTempo = tempo; emaClose = Close[0]; emaInit = true; }
			double ratio = emaTempo > 0 ? tempo / emaTempo : 1;
			int accel = ratio >= 1.25 ? 1 : (ratio <= 0.8 ? -1 : 0);
			emaTempo += k * (tempo - emaTempo);
			emaClose += k * (Close[0] - emaClose);

			bool climacticBar = !warm && tPct >= ClimacticPct;   // never gold during warmup
			bool climaxTag    = !warm && tPct >= ClimaxTagPct;

			tempoPctS[0] = tPct;
			ampPctS[0]   = aPct;
			effPctS[0]   = ePct;
			durS[0]      = duration;
			// 10-bar trend window: eff10 = |net move| / sum(range), t10 = mean tempo pctile.
			// Gate calibrated 2026-09-11 (eff10_calibration.py): eff10>=0.30 & t10>=50 tags
			// ~8% of bars, catches ~half of top-decile trend-leg bars.
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
			stateCodeS[0] = climacticBar ? 0 :
				(trending && t10 >= 50) ? 1 :                          // EXPAND (multi-bar)
				(!double.IsNaN(eff10) && t10 >= 60 && eff10 <= 0.10) ? 2 : // CHURN (fast, no progress over 10 bars)
				trending ? 4 :                                          // GRIND (directional, slow)
				(tPct >= 80 && aPct < 50) ? 3 :                         // ACTIVITY (per-bar)
				(tPct < 40 && aPct < 40) ? 5 : 6;                       // BALANCE / MIXED
			// ABR(8): this bar's range as % of the mean range of the PRIOR 8 bars
			double abr = 0;
			for (int i = 0; i < lastRanges.Count; i++) abr += lastRanges[i];
			abr = lastRanges.Count > 0 ? abr / lastRanges.Count : double.NaN;
			double ampAbr = abr > 0 ? 100.0 * range / abr : double.NaN;
			lastRanges.Add(range);
			if (lastRanges.Count > 8) lastRanges.RemoveAt(0);

			Values[0][0] = stateCodeS[0];
			Values[1][0] = Math.Round(tPct);
			Values[2][0] = double.IsNaN(ampAbr) ? double.NaN : Math.Round(ampAbr);
			Values[3][0] = Math.Round(ePct);
			Values[4][0] = Math.Round(tempo, 1);
			Values[5][0] = Math.Round(duration, 1);
			lastTempoPct = tPct; lastAmpPct = aPct; lastEffPct = ePct; lastAmpAbr = ampAbr;
			lastAccel = accel; lastClimax = climaxTag;
			lastBucket = bucket; lastN = Math.Min(cntT[bucket], cap); lastRate = tempo;
			lastBarTime = Time[0];
			string dirw = (stateCodeS[0] == 1 || stateCodeS[0] == 4)
				? (net10 >= 0 ? "BULL" : "BEAR") : (Close[0] >= emaClose ? "BULL" : "BEAR");
			switch ((int)stateCodeS[0])
			{
				case 0: lastState = "CLIMACTIC STATE"; break;
				case 1: lastState = "HIGH-TEMPO " + dirw + " EXPANSION"; break;
				case 2: lastState = "HIGH-TEMPO CHURN"; break;
				case 3: lastState = "HIGH ACTIVITY / NO PROGRESS"; break;
				case 4: lastState = dirw + " GRIND"; break;
				case 5: lastState = "BALANCE / QUIET"; break;
				default: lastState = "MIXED"; break;
			}

			bool up = Close[0] >= Open[0];
			if (climacticBar)
			{
				climaxS[0] = 1;
				BarBrush = GetBrush(up ? UpColor : DownColor, 100, up ? 1 : 0);
				CandleOutlineBrush = GetBrush(ClimacticColor, 100, 2);
			}
			else
			{
				double frac = tPct / 100.0;
				int alphaPct = (int)(MinOpacityPct + (100 - MinOpacityPct) * frac * frac);
				alphaPct = 5 * (int)Math.Round(alphaPct / 5.0);
				System.Windows.Media.Brush b = GetBrush(up ? UpColor : DownColor, alphaPct, up ? 1 : 0);
				BarBrush = b;
				CandleOutlineBrush = b;
			}
		}

		protected override void OnMarketData(MarketDataEventArgs marketDataUpdate)
		{
			if (marketDataUpdate.MarketDataType != MarketDataType.Last || notTickChart)
				return;
			if (chartMode == 1)
				tickInBar++;                                     // historical + realtime print counter (Tick Replay)
			if (State != State.Realtime)
				return;                                          // pace/alert below: realtime only (unchanged)
			DateTime now = marketDataUpdate.Time;
			tapeQ.Enqueue(now);
			DateTime cutoff = now.AddSeconds(-PaceWindowSec);
			while (tapeQ.Count > 0 && tapeQ.Peek() < cutoff) tapeQ.Dequeue();
			if (tapeQ.Count < 10) return;
			double rate = tapeQ.Count / (double)PaceWindowSec;
			double pct = PctFromBuf(bufT[lastBucket], cntT[lastBucket], rate);
			if (pct < 0) pct = PctFromRolling(rollTempo, rate);
			livePacePct = pct;

			if (AlertOnClimax && pct >= ClimaxTagPct && (now - lastAlertTime).TotalSeconds >= AlertCooldownSec)
			{
				lastAlertTime = now;
				PlaySound(NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert2.wav");
			}
		}

		private System.Windows.Media.Brush GetBrush(System.Windows.Media.Brush baseBrush, int alphaPct, int kind)
		{
			int key = kind * 1000 + alphaPct;
			System.Windows.Media.Brush cached;
			if (brushCache.TryGetValue(key, out cached)) return cached;
			System.Windows.Media.SolidColorBrush scb = baseBrush as System.Windows.Media.SolidColorBrush;
			System.Windows.Media.Color c = scb != null ? scb.Color : System.Windows.Media.Colors.Gray;
			System.Windows.Media.SolidColorBrush nb = new System.Windows.Media.SolidColorBrush(
				System.Windows.Media.Color.FromArgb((byte)(255 * alphaPct / 100), c.R, c.G, c.B));
			nb.Freeze();
			brushCache[key] = nb;
			return nb;
		}


		#region rendering
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			// no base.OnRender: plots feed the Data Box only, their lines must never draw
			if (RenderTarget == null || ChartBars == null || ChartPanel == null) return;

			TextFormat tf     = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 13f);
			TextFormat tfTiny = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 9f);
			SolidColorBrush white  = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.92f, 0.92f, 1f));
			SolidColorBrush dim    = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.65f, 0.65f, 0.65f, 1f));
			SolidColorBrush gold   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 1f));
			SolidColorBrush bg     = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.05f, 0.05f, 0.08f, 0.72f));
			SolidColorBrush grid   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.5f, 0.5f, 0.5f, 0.35f));

			try
			{
				if (notTickChart)
				{
					RenderTarget.DrawText("TempoSpeedometer: needs a TICK chart, or a minute/second chart with Tick Replay ON", tf,
						new SharpDX.RectangleF(ChartPanel.X + 12, ChartPanel.Y + 12, 700, 22), gold);
					return;
				}
				if (ShowHeatStrip) RenderHeatStrip(chartControl);
				RenderClimaxDots(chartControl, chartScale);
				if (ShowClimaxFlip) RenderClimaxFlips(chartControl, chartScale);
				if (ShowEngineDot) RenderEngineDot(tfTiny, white, dim, bg, grid);
				if (ShowSpeedo)    RenderSpeedo(tf, white, dim, gold, bg);
			}
			finally
			{
				tf.Dispose(); tfTiny.Dispose();
				white.Dispose(); dim.Dispose(); gold.Dispose(); bg.Dispose(); grid.Dispose();
			}
		}

		private void RenderHeatStrip(ChartControl chartControl)
		{
			int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
			if (to <= from) return;
			float stripH = 9f;
			float y0 = ChartPanel.Y + ChartPanel.H - stripH - 1;
			float w = Math.Max(1f, (float)chartControl.GetXByBarIndex(ChartBars, from + 1) - chartControl.GetXByBarIndex(ChartBars, from));
			for (int i = from; i <= to; i++)
			{
				if (i < 0 || i > CurrentBar) continue;
				double pct = tempoPctS.GetValueAt(i);
				if (double.IsNaN(pct)) continue;
				float x = chartControl.GetXByBarIndex(ChartBars, i);
				SolidColorBrush hb = new SolidColorBrush(RenderTarget, HeatColor(pct));
				RenderTarget.FillRectangle(new SharpDX.RectangleF(x - w / 2f, y0, Math.Max(1f, w - 1f), stripH), hb);
				hb.Dispose();
			}
		}

		private void RenderClimaxDots(ChartControl chartControl, ChartScale chartScale)
		{
			int from = ChartBars.FromIndex, to = ChartBars.ToIndex;
			SolidColorBrush gold = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 1f));
			try
			{
				for (int i = Math.Max(0, from); i <= to && i <= CurrentBar; i++)
				{
					if (climaxS.GetValueAt(i) < 0.5) continue;
					float x = chartControl.GetXByBarIndex(ChartBars, i);
					float y = chartScale.GetYByValue(Bars.GetHigh(i)) - 8f;
					RenderTarget.FillEllipse(new Ellipse(new SharpDX.Vector2(x, y), 3.5f, 3.5f), gold);
				}
			}
			finally { gold.Dispose(); }
		}

		private void RenderClimaxFlips(ChartControl chartControl, ChartScale chartScale)
		{
			// SETUP: bull climax bar immediately followed by bear climax bar -> SHORT
			// (mirror -> LONG). Box spans both bars' extremes; entry = close of bar 2;
			// stop = 1 tick beyond the box extreme; entry/stop/1R/2R drawn right only
			// until the FIRST bar whose extreme takes the stop out.
			int from = Math.Max(1, ChartBars.FromIndex - 1), to = ChartBars.ToIndex;
			TextFormat tfT = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
			SolidColorBrush boxFill = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.10f));
			SolidColorBrush boxEdge = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.85f));
			SolidColorBrush entryBr = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.92f, 0.92f, 0.9f));
			SolidColorBrush stopBr  = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.33f, 0.31f, 0.9f));
			SolidColorBrush tgtBr   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 0.85f));
			SolidColorBrush riskZ   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.33f, 0.31f, 0.07f));
			SolidColorBrush rewZ    = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 0.06f));
			try
			{
				float bw = 6f;
				if (to > from)
					bw = Math.Max(2f, (float)chartControl.GetXByBarIndex(ChartBars, from + 1)
									  - chartControl.GetXByBarIndex(ChartBars, from));
				for (int i = from; i <= to && i <= CurrentBar; i++)
				{
					if (climaxS.GetValueAt(i) < 0.5 || climaxS.GetValueAt(i - 1) < 0.5) continue;
					bool up1 = Bars.GetClose(i - 1) >= Bars.GetOpen(i - 1);
					bool up2 = Bars.GetClose(i) >= Bars.GetOpen(i);
					if (up1 == up2) continue;
					bool isShort = up1 && !up2;
					double hi2 = Math.Max(Bars.GetHigh(i - 1), Bars.GetHigh(i));
					double lo2 = Math.Min(Bars.GetLow(i - 1), Bars.GetLow(i));
					double entry = Bars.GetClose(i);
					double stop = isShort ? hi2 + TickSize : lo2 - TickSize;
					double risk = Math.Abs(entry - stop);
					if (risk < TickSize) continue;
					double t1 = isShort ? entry - risk : entry + risk;
					double t2 = isShort ? entry - 2 * risk : entry + 2 * risk;

					double t3 = isShort ? entry - 3 * risk : entry + 3 * risk;
					int endIdx = Math.Min(CurrentBar, i + 500);
					int result = 0;                            // 0 open · 1 stopped · 2 target(3R)
					for (int j = i + 1; j <= Math.Min(CurrentBar, i + 500); j++)
					{
						bool hitStop = isShort ? Bars.GetHigh(j) >= stop : Bars.GetLow(j) <= stop;
						bool hitTgt = isShort ? Bars.GetLow(j) <= t3 : Bars.GetHigh(j) >= t3;
						if (hitStop) { endIdx = j; result = 1; break; }   // both in one bar -> stop (conservative)
						if (hitTgt) { endIdx = j; result = 2; break; }
					}
					bool stopped = result == 1;

					float x0 = chartControl.GetXByBarIndex(ChartBars, i - 1) - bw / 2f;
					float x1 = chartControl.GetXByBarIndex(ChartBars, i) + bw / 2f;
					float xE = chartControl.GetXByBarIndex(ChartBars, endIdx) + (result == 0 ? bw / 2f : 0f);
					float yH = chartScale.GetYByValue(hi2), yL = chartScale.GetYByValue(lo2);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x0, yH, x1 - x0, yL - yH), boxFill);
					RenderTarget.DrawRectangle(new SharpDX.RectangleF(x0, yH, x1 - x0, yL - yH), boxEdge, 1.5f);

					float yEn = chartScale.GetYByValue(entry), ySt = chartScale.GetYByValue(stop);
					float yT1 = chartScale.GetYByValue(t1), yT2 = chartScale.GetYByValue(t2);
					float yT3 = chartScale.GetYByValue(t3);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x1, Math.Min(yEn, ySt), xE - x1, Math.Abs(ySt - yEn)), riskZ);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x1, Math.Min(yEn, yT3), xE - x1, Math.Abs(yT3 - yEn)), rewZ);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yEn), new SharpDX.Vector2(xE, yEn), entryBr, 1.5f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, ySt), new SharpDX.Vector2(xE, ySt), stopBr, 1.5f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yT1), new SharpDX.Vector2(xE, yT1), tgtBr, 1f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yT2), new SharpDX.Vector2(xE, yT2), tgtBr, 1f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yT3), new SharpDX.Vector2(xE, yT3), tgtBr, 1.5f);
					RenderTarget.DrawText((isShort ? "SHORT " : "LONG ")
						+ (result == 1 ? "✕stop" : result == 2 ? "✓3R" : "open"),
						tfT, new SharpDX.RectangleF(x1 + 2, yEn - 13, 110, 12),
						result == 2 ? tgtBr : (result == 1 ? stopBr : entryBr));
					RenderTarget.DrawText("stop", tfT, new SharpDX.RectangleF(xE + 3, ySt - 6, 40, 12), stopBr);
					RenderTarget.DrawText("1R", tfT, new SharpDX.RectangleF(xE + 3, yT1 - 6, 30, 12), tgtBr);
					RenderTarget.DrawText("2R", tfT, new SharpDX.RectangleF(xE + 3, yT2 - 6, 30, 12), tgtBr);
					RenderTarget.DrawText("3R", tfT, new SharpDX.RectangleF(xE + 3, yT3 - 6, 30, 12), tgtBr);
				}

				// ---- session tally (the session containing the last visible bar)
				int lastVis = Math.Min(to, CurrentBar);
				int s0 = 0;
				for (int k = sessStarts.Count - 1; k >= 0; k--)
					if (sessStarts[k] <= lastVis) { s0 = sessStarts[k]; break; }
				int s1 = CurrentBar;
				for (int k = 0; k < sessStarts.Count; k++)
					if (sessStarts[k] > s0) { s1 = sessStarts[k] - 1; break; }
				double ptsPnl = 0, rPnl = 0;
				int wins = 0, losses = 0, open = 0, r1c = 0, r2c = 0, r3c = 0;
				for (int i = Math.Max(1, s0 + 1); i <= s1 && i <= CurrentBar; i++)
				{
					if (climaxS.GetValueAt(i) < 0.5 || climaxS.GetValueAt(i - 1) < 0.5) continue;
					bool u1 = Bars.GetClose(i - 1) >= Bars.GetOpen(i - 1);
					bool u2 = Bars.GetClose(i) >= Bars.GetOpen(i);
					if (u1 == u2) continue;
					bool sh = u1 && !u2;
					double h2 = Math.Max(Bars.GetHigh(i - 1), Bars.GetHigh(i));
					double l2 = Math.Min(Bars.GetLow(i - 1), Bars.GetLow(i));
					double en = Bars.GetClose(i);
					double st = sh ? h2 + TickSize : l2 - TickSize;
					double rk = Math.Abs(en - st);
					if (rk < TickSize) continue;
					double r1v = sh ? en - rk : en + rk;
					double r2v = sh ? en - 2 * rk : en + 2 * rk;
					double tg = sh ? en - 3 * rk : en + 3 * rk;
					int res = 0, reach = 0;
					for (int j = i + 1; j <= Math.Min(CurrentBar, i + 500); j++)
					{
						bool hs = sh ? Bars.GetHigh(j) >= st : Bars.GetLow(j) <= st;
						if (hs) { res = 1; break; }                 // stop first in a bar -> conservative
						if (sh ? Bars.GetLow(j) <= tg : Bars.GetHigh(j) >= tg) { reach = 3; res = 2; break; }
						if (reach < 2 && (sh ? Bars.GetLow(j) <= r2v : Bars.GetHigh(j) >= r2v)) reach = 2;
						else if (reach < 1 && (sh ? Bars.GetLow(j) <= r1v : Bars.GetHigh(j) >= r1v)) reach = 1;
					}
					if (reach >= 1) r1c++;
					if (reach >= 2) r2c++;
					if (reach >= 3) r3c++;
					if (res == 1) { losses++; ptsPnl -= rk; rPnl -= 1; }
					else if (res == 2) { wins++; ptsPnl += 3 * rk; rPnl += 3; }
					else open++;
				}
				if (wins + losses + open > 0)
				{
					string tly = string.Format("FLIP day: {0}{1:F1}R ({2}{3:F2} pt)  W{4} L{5} open{6}  ≥1R:{7} ≥2R:{8} 3R:{9}",
						rPnl >= 0 ? "+" : "", rPnl, ptsPnl >= 0 ? "+" : "", ptsPnl, wins, losses, open, r1c, r2c, r3c);
					TextFormat tfB = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 12f);
					SolidColorBrush tb = new SolidColorBrush(RenderTarget,
						rPnl >= 0 ? new SharpDX.Color4(0.30f, 0.82f, 0.63f, 1f) : new SharpDX.Color4(0.94f, 0.33f, 0.31f, 1f));
					SolidColorBrush tbg = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.05f, 0.05f, 0.08f, 0.72f));
					RenderTarget.FillRectangle(new SharpDX.RectangleF(ChartPanel.X + 10, ChartPanel.Y + 8, 520, 20), tbg);
					RenderTarget.DrawText(tly, tfB, new SharpDX.RectangleF(ChartPanel.X + 16, ChartPanel.Y + 11, 510, 16), tb);
					tfB.Dispose(); tb.Dispose(); tbg.Dispose();
				}
			}
			finally
			{
				tfT.Dispose(); boxFill.Dispose(); boxEdge.Dispose(); entryBr.Dispose();
				stopBr.Dispose(); tgtBr.Dispose(); riskZ.Dispose(); rewZ.Dispose();
			}
		}

		private SharpDX.Color4 HeatColor(double pct)
		{
			if (pct >= ClimacticPct) return new SharpDX.Color4(1f, 0.84f, 0f, 0.95f);
			float t = (float)(pct / 100.0);
			float r = 0.13f + t * (1.00f - 0.13f);
			float g = 0.13f + t * (0.45f - 0.13f);
			float b = 0.16f + t * (0.08f - 0.16f);
			return new SharpDX.Color4(r, g, b, 0.9f);
		}

		private void RenderEngineDot(TextFormat tfTiny, SolidColorBrush white, SolidColorBrush dim, SolidColorBrush bg, SolidColorBrush grid)
		{
			float size = 120f;
			float x0 = ChartPanel.X + 10f;
			float y1 = ChartPanel.Y + ChartPanel.H - 16f;
			float y0 = y1 - size;
			RenderTarget.FillRectangle(new SharpDX.RectangleF(x0, y0, size, size), bg);
			RenderTarget.DrawRectangle(new SharpDX.RectangleF(x0, y0, size, size), grid);
			RenderTarget.DrawLine(new SharpDX.Vector2(x0 + size / 2, y0), new SharpDX.Vector2(x0 + size / 2, y1), grid);
			RenderTarget.DrawLine(new SharpDX.Vector2(x0, y0 + size / 2), new SharpDX.Vector2(x0 + size, y0 + size / 2), grid);
			RenderTarget.DrawText("GRIND",  tfTiny, new SharpDX.RectangleF(x0 + 3, y0 + 2, 60, 11), dim);
			RenderTarget.DrawText("EXPAND", tfTiny, new SharpDX.RectangleF(x0 + size - 42, y0 + 2, 42, 11), dim);
			RenderTarget.DrawText("BALANCE",tfTiny, new SharpDX.RectangleF(x0 + 3, y1 - 13, 60, 11), dim);
			RenderTarget.DrawText("CHURN",  tfTiny, new SharpDX.RectangleF(x0 + size - 38, y1 - 13, 38, 11), dim);

			int trail = 20;
			float px = float.MinValue, py = float.MinValue;
			for (int j = trail; j >= 0; j--)
			{
				int idx = CurrentBar - j;
				if (idx < 0) continue;
				double tp = tempoPctS.GetValueAt(idx), ap = ampPctS.GetValueAt(idx);
				if (double.IsNaN(tp) || double.IsNaN(ap)) continue;
				float cx = x0 + (float)(tp / 100.0) * size;
				float cy = y1 - (float)(ap / 100.0) * size;
				float a = 0.15f + 0.85f * (trail - j) / (float)trail;
				SolidColorBrush tb = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.35f, 0.78f, 1f, a));
				if (px > float.MinValue)
					RenderTarget.DrawLine(new SharpDX.Vector2(px, py), new SharpDX.Vector2(cx, cy), tb, j == 0 ? 2f : 1f);
				if (j == 0)
					RenderTarget.FillEllipse(new Ellipse(new SharpDX.Vector2(cx, cy), 4f, 4f), tb);
				tb.Dispose();
				px = cx; py = cy;
			}
		}

		private void RenderSpeedo(TextFormat tf, SolidColorBrush white, SolidColorBrush dim, SolidColorBrush gold, SolidColorBrush bg)
		{
			float wBox = 235f;
			bool showPace = !double.IsNaN(livePacePct);
			int lines = 4 + (showPace ? 1 : 0) + (ShowStateLabel ? 1 : 0) + (lastClimax ? 1 : 0) + (ShowDiag ? 1 : 0);
			float hBox = 10f + 19f * lines;
			float x0 = ChartPanel.X + ChartPanel.W - wBox - 10f;
			float y0 = ChartPanel.Y + 10f;
			RenderTarget.FillRectangle(new SharpDX.RectangleF(x0, y0, wBox, hBox), bg);

			string accel = lastAccel > 0 ? "ACCELERATING" : (lastAccel < 0 ? "DECELERATING" : "STABLE");
			float y = y0 + 5f;
			DrawLine2(tf, x0 + 8f, ref y, "TEMPO      " + Bar3(lastTempoPct), lastTempoPct >= ClimacticPct ? gold : white);
			if (showPace)
				DrawLine2(tf, x0 + 8f, ref y, "PACE " + PaceWindowSec + "s   " + Bar3(livePacePct), livePacePct >= ClimacticPct ? gold : white);
			DrawLine2(tf, x0 + 8f, ref y, double.IsNaN(lastAmpAbr)
				? "AMPLITUDE  " + Bar3(lastAmpPct)
				: string.Format("AMPLITUDE  {0,3:F0}% ABR8 (p{1:F0})", lastAmpAbr, lastAmpPct), white);
			DrawLine2(tf, x0 + 8f, ref y, "EFFICIENCY " + Bar3(lastEffPct), white);
			DrawLine2(tf, x0 + 8f, ref y, "TEMPO: " + accel, dim);
			if (ShowStateLabel) DrawLine2(tf, x0 + 8f, ref y, lastState, white);
			if (lastClimax)     DrawLine2(tf, x0 + 8f, ref y, "** CLIMACTIC STATE **", gold);
			if (ShowDiag)
			{
				string mode = (lastN >= MIN_SAMPLES ? "SELF" : "WARM " + lastN + "/" + MIN_SAMPLES)
					+ (chartMode == 1 ? " TR" : "");
				DrawLine2(tf, x0 + 8f, ref y, string.Format("DIAG {0:HH:mm} b{1} {2:F0}t/s {3}",
					lastBarTime, lastBucket, lastRate, mode), dim);
			}
		}

		private static string Bar3(double pct)
		{
			int p = (int)Math.Round(pct);
			string n = p.ToString();
			while (n.Length < 3) n = " " + n;
			int cells = Math.Max(0, Math.Min(10, (int)Math.Round(pct / 10.0)));
			return n + " " + new string('|', cells) + new string('.', 10 - cells);
		}

		private void DrawLine2(TextFormat tf, float x, ref float y, string s, SolidColorBrush b)
		{
			RenderTarget.DrawText(s, tf, new SharpDX.RectangleF(x, y, 300, 18), b);
			y += 19f;
		}
		#endregion

		#region properties
		[NinjaScriptProperty, Range(5, 250)]
		[Display(Name = "Self-calibration depth (sessions)", GroupName = "1. Calibration", Order = 0)]
		public int TrailingDays { get; set; }

		[NinjaScriptProperty, Range(30, 2000)]
		[Display(Name = "Warmup rolling window (bars)", GroupName = "1. Calibration", Order = 1)]
		public int RollingWindow { get; set; }

		[NinjaScriptProperty, Range(50, 100)]
		[Display(Name = "Climactic percentile (bar gold)", GroupName = "2. Visual", Order = 0)]
		public int ClimacticPct { get; set; }

		[NinjaScriptProperty, Range(50, 100)]
		[Display(Name = "Climax banner/alert percentile", GroupName = "2. Visual", Order = 1)]
		public int ClimaxTagPct { get; set; }

		[NinjaScriptProperty, Range(0, 90)]
		[Display(Name = "Minimum opacity %", GroupName = "2. Visual", Order = 2)]
		public int MinOpacityPct { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show speedometer", GroupName = "3. Blocks", Order = 0)]
		public bool ShowSpeedo { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show heat strip", GroupName = "3. Blocks", Order = 1)]
		public bool ShowHeatStrip { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show 2D engine dot", GroupName = "3. Blocks", Order = 2)]
		public bool ShowEngineDot { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show state label", GroupName = "3. Blocks", Order = 3)]
		public bool ShowStateLabel { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show DIAG line", GroupName = "3. Blocks", Order = 4)]
		public bool ShowDiag { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show climax-flip setups (box + RR)", GroupName = "3. Blocks", Order = 5)]
		public bool ShowClimaxFlip { get; set; }

		[NinjaScriptProperty, Range(5, 300)]
		[Display(Name = "Live pace window (sec)", GroupName = "4. Live pace / alert", Order = 0)]
		public int PaceWindowSec { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Audio alert on climactic pace", GroupName = "4. Live pace / alert", Order = 1)]
		public bool AlertOnClimax { get; set; }

		[NinjaScriptProperty, Range(10, 3600)]
		[Display(Name = "Alert cooldown (sec)", GroupName = "4. Live pace / alert", Order = 2)]
		public int AlertCooldownSec { get; set; }

		[XmlIgnore]
		[Display(Name = "Up bar color", GroupName = "2. Visual", Order = 3)]
		public System.Windows.Media.Brush UpColor { get; set; }
		[Browsable(false)]
		public string UpColorSerialize { get { return Serialize.BrushToString(UpColor); } set { UpColor = Serialize.StringToBrush(value); } }

		[XmlIgnore]
		[Display(Name = "Down bar color", GroupName = "2. Visual", Order = 4)]
		public System.Windows.Media.Brush DownColor { get; set; }
		[Browsable(false)]
		public string DownColorSerialize { get { return Serialize.BrushToString(DownColor); } set { DownColor = Serialize.StringToBrush(value); } }

		[XmlIgnore]
		[Display(Name = "Climactic bar color", GroupName = "2. Visual", Order = 5)]
		public System.Windows.Media.Brush ClimacticColor { get; set; }
		[Browsable(false)]
		public string ClimacticColorSerialize { get { return Serialize.BrushToString(ClimacticColor); } set { ClimacticColor = Serialize.StringToBrush(value); } }
		#endregion
	}
}
