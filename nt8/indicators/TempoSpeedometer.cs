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

namespace NinjaTrader.NinjaScript
{
	public enum TempoBoxCorner { TopLeft, TopRight, BottomLeft, BottomRight }
	public enum FlipEntryMode { StopEntry, Close }
}

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

		// per-setup hover cards (climax-flip trades)
		private readonly List<float[]> flipRects = new List<float[]>();   // x,y,w,h per rendered trade
		private readonly List<string[]> flipInfos = new List<string[]>();
		private int flipHover = -1;
		private float hoverX, hoverY;

		// prior-day high/low for the whole-chart spring/upthrust detector (beyond-PD poke + snap-back)
		private Series<double> pdhS, pdlS;
		private double curSessHi = double.NaN, curSessLo = double.NaN, pdHigh = double.NaN, pdLow = double.NaN;

		private int inspectBar = -1;      // bar the user middle-clicked to inspect (Wyckoff read-out)

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
				SpeedoCorner   = TempoBoxCorner.BottomRight;
				EntryMode      = FlipEntryMode.StopEntry;
				ShowHeatStrip  = true;
				ShowEngineDot  = true;
				ShowStateLabel = true;
				ShowDiag       = true;
				ShowClimaxFlip = true;
				ReverseOnOpposite = true;                  // variant 1: opposite signal while in trade = exit @ close + reverse
				UseIbsDirection   = true;                  // SB dir from IBS (>=0.55 / <=0.45, middle = no signal); bar1 = color only
				EbScratch         = true;                  // EB rule: first bar after entry non-climax opposite-IBS -> scratch @ close
			MinSbBodyTicks    = 4;                     // SB body |close-open| must be >= this many ticks, else no signal
			SeOrderLifeBars   = 1;                     // SE pending pulled after this many bars past the SB
			EbOnSignalBar     = true;                  // EB = bar after SB (false: the bar that fills the SE)
				ShowSpringTypes   = true;                  // mark Wyckoff spring type on each flip (validated vol filter)
				Sp3MaxRatio       = 0.94;                  // reversal/trap volume <= this = Spring #3 (best)
				TsoMinRatio       = 1.03;                  // reversal/trap volume >= this = Terminal Shakeout (worst)
				SkipTerminalShakeout = false;              // if true, do NOT enter TSO flips (SAR still closes; walk-forward-validated)
				ShowSpringUpthrust = true;                 // whole-chart beyond-prior-day spring/upthrust marks (Wyckoff Event 5)
				ShakeoutLowIntensity  = 0.85;              // (depth+vol+range)/3 <= this = #3 (slight/low/narrow, best)
				ShakeoutHighIntensity = 1.50;              // (depth+vol+range)/3 >= this = #1 Terminal Shakeout (deep/high/wide)
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
				pdhS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				pdlS = new Series<double>(this, MaximumBarsLookBack.Infinite);
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
			else if (State == State.Historical)
			{
				if (ChartControl != null)
					ChartControl.Dispatcher.InvokeAsync(new Action(delegate
					{ ChartControl.PreviewMouseMove += OnChartMouseMove;
					  ChartControl.PreviewMouseDown += OnChartMouseDown; }));
			}
			else if (State == State.Terminated)
			{
				if (ChartControl != null)
					ChartControl.Dispatcher.InvokeAsync(new Action(delegate
					{ ChartControl.PreviewMouseMove -= OnChartMouseMove;
					  ChartControl.PreviewMouseDown -= OnChartMouseDown; }));
			}
		}

		private void OnChartMouseMove(object sender, System.Windows.Input.MouseEventArgs e)
		{
			try
			{
				System.Windows.Point p = e.GetPosition(ChartControl);
				hoverX = (float)p.X; hoverY = (float)p.Y;
				int hit = -1;
				for (int k = 0; k < flipRects.Count; k++)
				{
					float[] r = flipRects[k];
					if (p.X >= r[0] && p.X <= r[0] + r[2] && p.Y >= r[1] && p.Y <= r[1] + r[3]) { hit = k; break; }
				}
				if (hit != flipHover) { flipHover = hit; ForceRefresh(); }
			}
			catch { }
		}

		// middle-mouse (mousewheel) click a bar -> pin a Wyckoff read-out card for that bar.
		// Click the same bar again to hide.
		private void OnChartMouseDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
		{
			try
			{
				if (e.ChangedButton != System.Windows.Input.MouseButton.Middle) return;
				System.Windows.Point p = e.GetPosition(ChartControl);
				int nearest = -1; double best = double.MaxValue;
				for (int i = ChartBars.FromIndex; i <= ChartBars.ToIndex; i++)
				{
					if (i < 0 || i > CurrentBar) continue;
					double bx = ChartControl.GetXByBarIndex(ChartBars, i);
					double d = Math.Abs(bx - p.X);
					if (d < best) { best = d; nearest = i; }
				}
				inspectBar = (nearest == inspectBar) ? -1 : nearest;   // toggle off on re-click
				ForceRefresh();
			}
			catch { }
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

			// prior-day high/low tracking (for the beyond-PD spring/upthrust detector)
			if (!notTickChart)
			{
				if (Bars.IsFirstBarOfSession || CurrentBar == 0)
				{
					if (!double.IsNaN(curSessHi)) { pdHigh = curSessHi; pdLow = curSessLo; }
					curSessHi = High[0]; curSessLo = Low[0];
				}
				else { curSessHi = Math.Max(curSessHi, High[0]); curSessLo = Math.Min(curSessLo, Low[0]); }
				pdhS[0] = pdHigh; pdlS[0] = pdLow;
			}

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
					if (ShowSpringUpthrust) RenderSpringUpthrust(chartControl, chartScale);
				if (ShowEngineDot) RenderEngineDot(tfTiny, white, dim, bg, grid);
				if (ShowSpeedo)    RenderSpeedo(tf, white, dim, gold, bg);
					RenderInspectCard(chartControl, chartScale);
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

		// climax-flip helpers ---------------------------------------------------
		private int BarDir(int k)                         // 1 bull · -1 bear · 0 undecided (IBS band)
		{
			if (!UseIbsDirection) return Bars.GetClose(k) >= Bars.GetOpen(k) ? 1 : -1;
			double rg = Bars.GetHigh(k) - Bars.GetLow(k);
			if (rg < TickSize / 2) return 0;
			double ibs = (Bars.GetClose(k) - Bars.GetLow(k)) / rg;
			return ibs >= 0.55 ? 1 : (ibs <= 0.45 ? -1 : 0);
		}

		private int FlipDir(int i)                        // 0 none · 1 short · 2 long
		{
			if (i < 1 || climaxS.GetValueAt(i) < 0.5 || climaxS.GetValueAt(i - 1) < 0.5) return 0;
			// bar1: color only (doji = no color = no signal); SB: IBS band + body
			// >= MinSbBodyTicks (user rules 2026-09-12)
			double o1 = Bars.GetOpen(i - 1), c1 = Bars.GetClose(i - 1);
			double o2 = Bars.GetOpen(i),     c2 = Bars.GetClose(i);
			if (Math.Abs(c1 - o1) < TickSize / 2) return 0;
			if (Math.Abs(c2 - o2) < MinSbBodyTicks * TickSize - TickSize / 2) return 0;
			int d1 = c1 >= o1 ? 1 : -1;
			int d2 = BarDir(i);
			if (d2 == 0 || d1 == d2) return 0;
			return d1 == 1 ? 1 : 2;
		}

		// Entry per EntryMode: StopEntry = 1 tick beyond the SB extreme (tick-through
		// fill), Close = at the SB close.
		private bool FlipPrices(int i, bool isShort, out double entry, out double stop, out double risk)
		{
			double h2 = Math.Max(Bars.GetHigh(i - 1), Bars.GetHigh(i));
			double l2 = Math.Min(Bars.GetLow(i - 1), Bars.GetLow(i));
			entry = EntryMode == FlipEntryMode.Close ? Bars.GetClose(i)
				: (isShort ? Bars.GetLow(i) - TickSize : Bars.GetHigh(i) + TickSize);
			stop = isShort ? h2 + TickSize : l2 - TickSize;
			risk = Math.Abs(entry - stop);
			return risk >= TickSize;
		}

		// ONE TRADE AT A TIME + optional STOP-AND-REVERSE, stop-entry pending orders.
		// Pending dies if the protective-stop side breaks first (canc), on a newer
		// signal (replaced) or at session end. Bar crossing SE and stop together =
		// filled-then-stopped (conservative). Record per signal:
		// Pending pulled after SeOrderLifeBars bars past the SB. EB reference per
		// EbOnSignalBar: true = bar after SB (fills+wrong IBS -> scratch; no fill +
		// wrong IBS -> pull order), false = the bar that fills the SE. Record per signal:
		// int[]{sigBar, isShort, result(0 open/1 stop/2 3R/4 reversed/5 eb-scr/
		//       6 no-fill/7 cancelled/8 eb-canc), endIdx, reach, openedByRev, fillBar(-1 if none)}
		private List<int[]> SimFlipSession(int s0, int s1)
		{
			List<int[]> trades = new List<int[]>();
			int pi = -1, pSig = -1; bool pSh = false; int reach = 0; bool pByRev = false;
			double en = 0, st = 0, rk = 0, tg = 0, r1 = 0, r2 = 0;
			int qSig = -1; bool qSh = false, qByRev = false;
			double qEn = 0, qSt = 0;
			for (int i = Math.Max(1, s0 + 1); i <= s1 && i <= CurrentBar; i++)
			{
				if (pi >= 0)
				{
					bool hs = pSh ? Bars.GetHigh(i) >= st : Bars.GetLow(i) <= st;
					bool ht = pSh ? Bars.GetLow(i) <= tg : Bars.GetHigh(i) >= tg;
					if (hs) { trades.Add(new[] { pSig, pSh ? 1 : 0, 1, i, reach, pByRev ? 1 : 0, pi }); pi = -1; }
					else if (ht) { trades.Add(new[] { pSig, pSh ? 1 : 0, 2, i, 3, pByRev ? 1 : 0, pi }); pi = -1; }
					else
					{
						if (reach < 2 && (pSh ? Bars.GetLow(i) <= r2 : Bars.GetHigh(i) >= r2)) reach = 2;
						else if (reach < 1 && (pSh ? Bars.GetLow(i) <= r1 : Bars.GetHigh(i) >= r1)) reach = 1;
						// Close-entry EB scratch: bar after the SB closes wrong-IBS non-climax
						if (EntryMode == FlipEntryMode.Close && EbScratch && i == pi + 1)
						{
							int dEB = BarDir(i);
							bool opp = climaxS.GetValueAt(i) < 0.5
								&& ((pSh && dEB == 1) || (!pSh && dEB == -1));
							if (opp) { trades.Add(new[] { pSig, pSh ? 1 : 0, 5, i, reach, pByRev ? 1 : 0, pi }); pi = -1; }
						}
					}
				}
				if (qSig >= 0 && pi < 0)
				{
					if (i > qSig + SeOrderLifeBars)
					{ trades.Add(new[] { qSig, qSh ? 1 : 0, 6, i - 1, 0, qByRev ? 1 : 0, -1 }); qSig = -1; }
					else
					{
					bool inval = qSh ? Bars.GetHigh(i) >= qSt : Bars.GetLow(i) <= qSt;
					bool trig  = qSh ? Bars.GetLow(i) <= qEn - TickSize : Bars.GetHigh(i) >= qEn + TickSize;
					if (trig)
					{
						pi = i; pSig = qSig; pSh = qSh; pByRev = qByRev;
						en = qEn; st = qSt; rk = Math.Abs(en - st);
						double sg = pSh ? -1 : 1;
						tg = en + sg * 3 * rk; r1 = en + sg * rk; r2 = en + sg * 2 * rk; reach = 0;
						qSig = -1;
						if (inval) { trades.Add(new[] { pSig, pSh ? 1 : 0, 1, i, 0, pByRev ? 1 : 0, pi }); pi = -1; }
						else
						{
							if (reach < 2 && (pSh ? Bars.GetLow(i) <= r2 : Bars.GetHigh(i) >= r2)) reach = 2;
							else if (reach < 1 && (pSh ? Bars.GetLow(i) <= r1 : Bars.GetHigh(i) >= r1)) reach = 1;
							bool ht0 = pSh ? Bars.GetLow(i) <= tg : Bars.GetHigh(i) >= tg;
							if (ht0) { trades.Add(new[] { pSig, pSh ? 1 : 0, 2, i, 3, pByRev ? 1 : 0, pi }); pi = -1; }
							else if (EbScratch && (EbOnSignalBar ? i == pSig + 1 : true))
							{
								// EB scratch at the close of: ON = bar after SB (if it filled),
								// OFF = whichever bar fills the SE
								int dEB = BarDir(i);
								bool opp = climaxS.GetValueAt(i) < 0.5
									&& ((pSh && dEB == 1) || (!pSh && dEB == -1));
								if (opp) { trades.Add(new[] { pSig, pSh ? 1 : 0, 5, i, reach, pByRev ? 1 : 0, pi }); pi = -1; }
							}
						}
					}
					else if (inval)
					{ trades.Add(new[] { qSig, qSh ? 1 : 0, 7, i, 0, qByRev ? 1 : 0, -1 }); qSig = -1; }
					else if (EbScratch && EbOnSignalBar && i == qSig + 1)
					{
						// EB (bar after SB) didn't fill the SE and closes wrong-IBS -> pull the order
						int dEB = BarDir(i);
						bool opp = climaxS.GetValueAt(i) < 0.5
							&& ((qSh && dEB == 1) || (!qSh && dEB == -1));
						if (opp) { trades.Add(new[] { qSig, qSh ? 1 : 0, 8, i, 0, qByRev ? 1 : 0, -1 }); qSig = -1; }
					}
					}
				}
				int fd = FlipDir(i);
				if (fd == 0) continue;
				bool sh = fd == 1;
				bool byRev = false;
				if (pi >= 0)
				{
					if (ReverseOnOpposite && sh != pSh)
					{ trades.Add(new[] { pSig, pSh ? 1 : 0, 4, i, reach, pByRev ? 1 : 0, pi }); pi = -1; byRev = true; }
					else continue;
				}
				if (qSig >= 0)
				{ trades.Add(new[] { qSig, qSh ? 1 : 0, 6, i, 0, qByRev ? 1 : 0, -1 }); qSig = -1; }
				double e2, s2, k2;
				if (SkipTerminalShakeout) { double _tvr; if (SpringType(i, out _tvr) == 2) continue; }  // Wyckoff: drop Terminal Shakeout entries (SAR close above already ran)
					if (!FlipPrices(i, sh, out e2, out s2, out k2)) continue;
				if (EntryMode == FlipEntryMode.Close)
				{
					pi = i; pSig = i; pSh = sh; pByRev = byRev;
					en = e2; st = s2; rk = k2;
					double sg2 = sh ? -1 : 1;
					tg = en + sg2 * 3 * rk; r1 = en + sg2 * rk; r2 = en + sg2 * 2 * rk; reach = 0;
					continue;
				}
				qSig = i; qSh = sh; qByRev = byRev; qEn = e2; qSt = s2;
			}
			if (pi >= 0) trades.Add(new[] { pSig, pSh ? 1 : 0, 0, Math.Min(s1, CurrentBar), reach, pByRev ? 1 : 0, pi });
			if (qSig >= 0) trades.Add(new[] { qSig, qSh ? 1 : 0, 6, Math.Min(s1, CurrentBar), 0, qByRev ? 1 : 0, -1 });
			return trades;
		}

		private int SessionStartFor(int barIdx)
		{
			int s0 = 0;
			for (int k = sessStarts.Count - 1; k >= 0; k--)
				if (sessStarts[k] <= barIdx) { s0 = sessStarts[k]; break; }
			return s0;
		}

		private int SessionEndFor(int s0)
		{
			for (int k = 0; k < sessStarts.Count; k++)
				if (sessStarts[k] > s0) return sessStarts[k] - 1;
			return CurrentBar;
		}

		// Wyckoff spring type of a climax-flip, from reversal(SB) vs trap-bar volume.
		// Validated (flip_wyckoff_effort.py + walk-forward): LOW ratio = Spring #3
		// (supply exhausted, best); HIGH = Terminal Shakeout / Spring #1 (worst, loses OOS).
		// Returns 0 = SP3 · 1 = SP2 · 2 = TSO; the ratio comes back via `ratio`.
		private int SpringType(int i, out double ratio)
		{
			double vt = Bars.GetVolume(i - 1), vs = Bars.GetVolume(i);
			ratio = vt > 0 ? vs / vt : double.NaN;
			if (double.IsNaN(ratio)) return 1;
			if (ratio <= Sp3MaxRatio) return 0;
			if (ratio >= TsoMinRatio) return 2;
			return 1;
		}

		private void RenderClimaxFlips(ChartControl chartControl, ChartScale chartScale)
		{
			int from = Math.Max(1, ChartBars.FromIndex - 1), to = ChartBars.ToIndex;
			int lastVis = Math.Min(to, CurrentBar);
			if (lastVis < 1) return;
			flipRects.Clear(); flipInfos.Clear();

			Dictionary<int, int[]> taken = new Dictionary<int, int[]>();
			List<int[]> tallyTrades = null;
			int tallyS0 = SessionStartFor(lastVis);
			int s = SessionStartFor(from);
			while (true)
			{
				int sEnd = SessionEndFor(s);
				List<int[]> tr = SimFlipSession(s, sEnd);
				for (int k = 0; k < tr.Count; k++) taken[tr[k][0]] = tr[k];
				if (s == tallyS0) tallyTrades = tr;
				if (sEnd >= lastVis || sEnd >= CurrentBar) break;
				s = sEnd + 1;
			}
			if (tallyTrades == null) tallyTrades = SimFlipSession(tallyS0, SessionEndFor(tallyS0));

			TextFormat tfT = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 10f);
			SolidColorBrush boxFill = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.10f));
			SolidColorBrush boxEdge = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.85f));
			SolidColorBrush boxDim  = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.30f));
			SolidColorBrush entryBr = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.92f, 0.92f, 0.9f));
			SolidColorBrush stopBr  = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.33f, 0.31f, 0.9f));
			SolidColorBrush tgtBr   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 0.85f));
			SolidColorBrush revBr   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.55f, 0.75f, 1f, 0.9f));
			SolidColorBrush riskZ   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.33f, 0.31f, 0.07f));
			SolidColorBrush rewZ    = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 0.06f));
			SolidColorBrush spGreen = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 0.95f));  // SP3
			SolidColorBrush spAmber = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.95f));        // SP2
			SolidColorBrush spRed   = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.33f, 0.31f, 0.95f));  // TSO
			try
			{
				float bw = 6f;
				if (to > from)
					bw = Math.Max(2f, (float)chartControl.GetXByBarIndex(ChartBars, from + 1)
									  - chartControl.GetXByBarIndex(ChartBars, from));
				for (int i = from; i <= lastVis; i++)
				{
					int fd = FlipDir(i);
					if (fd == 0) continue;
					bool sh = fd == 1;
					double en, st, rk;
					if (!FlipPrices(i, sh, out en, out st, out rk)) continue;
					double h2 = Math.Max(Bars.GetHigh(i - 1), Bars.GetHigh(i));
					double l2 = Math.Min(Bars.GetLow(i - 1), Bars.GetLow(i));
					float x0 = chartControl.GetXByBarIndex(ChartBars, i - 1) - bw / 2f;
					float x1 = chartControl.GetXByBarIndex(ChartBars, i) + bw / 2f;
					float yH = chartScale.GetYByValue(h2), yL = chartScale.GetYByValue(l2);

						// Wyckoff spring-type badge under the 2-bar box (green SP3 / amber SP2 / red TSO)
						double _vr; int _sp = SpringType(i, out _vr);
						if (ShowSpringTypes)
						{
							SolidColorBrush _spb = _sp == 0 ? spGreen : _sp == 2 ? spRed : spAmber;
							// LONG flip = spring (SP) -> label BELOW box; SHORT flip = upthrust (UT) -> label ABOVE box
							string _spn = (sh ? "UT" : "SP") + (_sp == 0 ? "3" : _sp == 1 ? "2" : "1");
							float _spy = sh ? yH - 15f : yL + 3f;
							RenderTarget.DrawText(_spn + " " + _vr.ToString("F2"), tfT,
								new SharpDX.RectangleF(x0, _spy, 84f, 12f), _spb);
						}

					if (!taken.ContainsKey(i))
					{
						RenderTarget.DrawRectangle(new SharpDX.RectangleF(x0, yH, x1 - x0, yL - yH), boxDim, 1f);
						RenderTarget.DrawText("skip", tfT, new SharpDX.RectangleF(x1 + 2, yH - 12, 40, 12), boxDim);
						continue;
					}
					int[] t = taken[i];
					int result = t[2], endIdx = t[3];
					if (result == 6 || result == 7 || result == 8)
					{
						// stop-entry never filled: expired/replaced (6), invalidated (7), EB-cancelled (8)
						RenderTarget.DrawRectangle(new SharpDX.RectangleF(x0, yH, x1 - x0, yL - yH), boxDim, 1f);
						float ySe = chartScale.GetYByValue(en);
						float xD = chartControl.GetXByBarIndex(ChartBars, endIdx);
						RenderTarget.DrawLine(new SharpDX.Vector2(x1, ySe), new SharpDX.Vector2(xD, ySe), boxDim, 1f);
						RenderTarget.DrawText(result == 6 ? "no fill" : result == 7 ? "canc" : "eb-canc", tfT,
							new SharpDX.RectangleF(x1 + 2, yH - 12, 60, 12), boxDim);
						flipRects.Add(new[] { Math.Min(x0, x1), yH - 18f,
							Math.Max(xD + 40f, x1) - Math.Min(x0, x1), yL - yH + 18f });
						flipInfos.Add(new[] {
							(t[5] == 1 ? "EB Reversal" : "Basic") + "  ·  " + (sh ? "SHORT" : "LONG"),
							string.Format("SE {0:F2}  never filled", en),
							result == 6 ? "order life expired / replaced" :
							result == 7 ? "stop side broke first (invalidated)" :
							"EB wrong IBS, no fill -> order pulled",
						});
						continue;
					}
					double sgn = sh ? -1 : 1;
					double t1 = en + sgn * rk, t2 = en + sgn * 2 * rk, t3 = en + sgn * 3 * rk;
					float xE = chartControl.GetXByBarIndex(ChartBars, endIdx) + (result == 0 ? bw / 2f : 0f);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x0, yH, x1 - x0, yL - yH), boxFill);
					RenderTarget.DrawRectangle(new SharpDX.RectangleF(x0, yH, x1 - x0, yL - yH), boxEdge, 1.5f);
					float yEn = chartScale.GetYByValue(en), ySt = chartScale.GetYByValue(st);
					float yT1 = chartScale.GetYByValue(t1), yT2 = chartScale.GetYByValue(t2);
					float yT3 = chartScale.GetYByValue(t3);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x1, Math.Min(yEn, ySt), xE - x1, Math.Abs(ySt - yEn)), riskZ);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(x1, Math.Min(yEn, yT3), xE - x1, Math.Abs(yT3 - yEn)), rewZ);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yEn), new SharpDX.Vector2(xE, yEn), entryBr, 1.5f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, ySt), new SharpDX.Vector2(xE, ySt), stopBr, 1.5f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yT1), new SharpDX.Vector2(xE, yT1), tgtBr, 1f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yT2), new SharpDX.Vector2(xE, yT2), tgtBr, 1f);
					RenderTarget.DrawLine(new SharpDX.Vector2(x1, yT3), new SharpDX.Vector2(xE, yT3), tgtBr, 1.5f);
					string tag = result == 1 ? "Xstop" : result == 2 ? "OK 3R" : result == 4 ? "rev"
						: result == 5 ? "eb-scr" : "open";
					SolidColorBrush tagBr = result == 2 ? tgtBr : result == 1 ? stopBr
						: (result == 4 || result == 5) ? revBr : entryBr;
					RenderTarget.DrawText((sh ? "SHORT " : "LONG ") + tag,
						tfT, new SharpDX.RectangleF(x1 + 2, yEn - 13, 110, 12), tagBr);
					RenderTarget.DrawText("stop", tfT, new SharpDX.RectangleF(xE + 3, ySt - 6, 40, 12), stopBr);
					RenderTarget.DrawText("1R", tfT, new SharpDX.RectangleF(xE + 3, yT1 - 6, 30, 12), tgtBr);
					RenderTarget.DrawText("2R", tfT, new SharpDX.RectangleF(xE + 3, yT2 - 6, 30, 12), tgtBr);
					RenderTarget.DrawText("3R", tfT, new SharpDX.RectangleF(xE + 3, yT3 - 6, 30, 12), tgtBr);

					// hover hit-region + card content for this trade
					double exitPx = result == 1 ? st : result == 2 ? t3 : Bars.GetClose(endIdx);
					double pnl = (exitPx - en) * sgn;
					float top = Math.Min(Math.Min(yH, yT3), Math.Min(yEn, ySt)) - 18f;
					float bot = Math.Max(Math.Max(yL, yT3), Math.Max(yEn, ySt));
					flipRects.Add(new[] { Math.Min(x0, x1), top, Math.Max(xE + 40f, x1) - Math.Min(x0, x1), bot - top });
					flipInfos.Add(new[] {
						(t[5] == 1 ? "EB Reversal" : "Basic") + "  ·  " + (sh ? "SHORT" : "LONG"),
						string.Format("in  {0:HH:mm:ss}  @ {1:F2}{2}", Bars.GetTime(t[6] >= 0 ? t[6] : i), en,
							EntryMode == FlipEntryMode.Close ? "" : " (SE)"),
						string.Format("out {0:HH:mm:ss}  @ {1:F2}  ({2})", Bars.GetTime(endIdx), exitPx, tag),
						string.Format("stop {0:F2}   risk {1:F2} pt", st, rk),
						string.Format("PnL {0}{1:F2} pt  ({2}{3:F2}R)   reach {4}R",
							pnl >= 0 ? "+" : "", pnl, pnl >= 0 ? "+" : "", pnl / rk, t[4]),
					});
				}

				// session tally (sequential, incl. reversals)
				double ptsPnl = 0, rPnl = 0;
				int wins = 0, losses = 0, open = 0, revs = 0, r1c = 0, r2c = 0, r3c = 0, nofill = 0;
				for (int k = 0; k < tallyTrades.Count; k++)
				{
					int[] t = tallyTrades[k];
					if (t[2] >= 6) { nofill++; continue; }
					bool sh = t[1] == 1;
					double en, st, rk;
					if (!FlipPrices(t[0], sh, out en, out st, out rk)) continue;
					if (t[4] >= 1) r1c++;
					if (t[4] >= 2) r2c++;
					if (t[4] >= 3) r3c++;
					double sgn = sh ? -1 : 1;
					if (t[2] == 1) { losses++; ptsPnl -= rk; rPnl -= 1; }
					else if (t[2] == 2) { wins++; ptsPnl += 3 * rk; rPnl += 3; }
					else if (t[2] == 4 || t[2] == 5)
					{
						revs++;
						double p = (Bars.GetClose(t[3]) - en) * sgn;
						ptsPnl += p; rPnl += p / rk;
					}
					else open++;
				}
				if (wins + losses + revs + open + nofill > 0)
				{
					string tly = string.Format("FLIP day ({0} 1-at-a-time{1}): {2}{3:F1}R ({4}{5:F2} pt)  W{6} L{7} rev{8} open{9} nofill{10}  >=1R:{11} >=2R:{12} 3R:{13}",
						EntryMode == FlipEntryMode.Close ? "CLOSE" : "SE",
						ReverseOnOpposite ? ", SAR" : "", rPnl >= 0 ? "+" : "", rPnl,
						ptsPnl >= 0 ? "+" : "", ptsPnl, wins, losses, revs, open, nofill, r1c, r2c, r3c);
					TextFormat tfB = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 12f);
					SolidColorBrush tb = new SolidColorBrush(RenderTarget,
						rPnl >= 0 ? new SharpDX.Color4(0.30f, 0.82f, 0.63f, 1f) : new SharpDX.Color4(0.94f, 0.33f, 0.31f, 1f));
					SolidColorBrush tbg = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.05f, 0.05f, 0.08f, 0.72f));
					RenderTarget.FillRectangle(new SharpDX.RectangleF(ChartPanel.X + 10, ChartPanel.Y + 8, 620, 20), tbg);
					RenderTarget.DrawText(tly, tfB, new SharpDX.RectangleF(ChartPanel.X + 16, ChartPanel.Y + 11, 610, 16), tb);
					tfB.Dispose(); tb.Dispose(); tbg.Dispose();
					if (ShowSpringTypes)
					{
						SolidColorBrush lg = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.72f, 0.72f, 0.72f, 0.9f));
						RenderTarget.DrawText("Wyckoff  SP=spring (long) / UT=upthrust (short)  ·  tier 3 low-vol (best) · 2 mid · 1 high-vol terminal (weak)",
							tfT, new SharpDX.RectangleF(ChartPanel.X + 16, ChartPanel.Y + 30, 760, 14), lg);
						lg.Dispose();
					}
				}

				// hover card for the setup under the cursor
				if (flipHover >= 0 && flipHover < flipInfos.Count)
				{
					string[] card = flipInfos[flipHover];
					float cw = 250f, ch = card.Length * 15f + 10f;
					float cx = hoverX + 16f, cy = hoverY + 12f;
					if (cx + cw > ChartPanel.X + ChartPanel.W) cx = hoverX - cw - 16f;
					if (cy + ch > ChartPanel.Y + ChartPanel.H) cy = hoverY - ch - 12f;
					TextFormat tfC = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 11f);
					SolidColorBrush cbg = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.05f, 0.05f, 0.08f, 0.92f));
					SolidColorBrush cbd = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.7f));
					SolidColorBrush cin = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.92f, 0.92f, 1f));
					RenderTarget.FillRectangle(new SharpDX.RectangleF(cx, cy, cw, ch), cbg);
					RenderTarget.DrawRectangle(new SharpDX.RectangleF(cx, cy, cw, ch), cbd);
					float yy = cy + 5f;
					for (int k = 0; k < card.Length; k++)
					{
						RenderTarget.DrawText(card[k], tfC, new SharpDX.RectangleF(cx + 7f, yy, cw - 12f, 14f),
							k == 0 ? cbd : cin);
						yy += 15f;
					}
					tfC.Dispose(); cbg.Dispose(); cbd.Dispose(); cin.Dispose();
				}
			}
			finally
			{
				tfT.Dispose(); boxFill.Dispose(); boxEdge.Dispose(); boxDim.Dispose();
				entryBr.Dispose(); stopBr.Dispose(); tgtBr.Dispose(); revBr.Dispose();
				riskZ.Dispose(); rewZ.Dispose();
				spGreen.Dispose(); spAmber.Dispose(); spRed.Dispose();
			}
		}

		// Wyckoff spring / upthrust per Event 5 (tradingwyckoff.com). The THREE factors
		// TOGETHER set the type -> penetration DEPTH, VOLUME, and RANGE:
		//   #3 (best):  slight penetration + low volume + narrow range (exhaustion, tradable)
		//   #2 (mid):   contained penetration + moderate volume        (needs a test)
		//   #1 (worst): deep penetration + high volume + wide range    (Terminal Shakeout)
		// Spring = break below the prior-day LOW then RECOVER (close back above it) on the first
		// breaching bar; upthrust mirrors it at the prior-day HIGH. Candle colour is NOT a Wyckoff
		// criterion -- the recovery plus the depth/volume/range profile are. type 0=#3 .. 2=#1.
		private bool WyckoffPoke(int i, out bool upthrust, out int type,
			out double penFrac, out double volRatio, out double rangeRatio, out double intensity)
		{
			upthrust = false; type = 1;
			penFrac = volRatio = rangeRatio = intensity = double.NaN;
			if (i < 1) return false;
			double pdh = pdhS.GetValueAt(i), pdl = pdlS.GetValueAt(i);
			double h = Bars.GetHigh(i), l = Bars.GetLow(i), c = Bars.GetClose(i);
			bool ut = !double.IsNaN(pdh) && h > pdh && c <= pdh && Bars.GetHigh(i - 1) <= pdh;
			bool sp = !double.IsNaN(pdl) && l < pdl && c >= pdl && Bars.GetLow(i - 1) >= pdl;
			if (!ut && !sp) return false;
			upthrust = ut;
			double avgR = 0, avgV = 0; int nc = 0;
			for (int j = i - 8; j < i; j++)
				if (j >= 0) { avgR += Bars.GetHigh(j) - Bars.GetLow(j); avgV += Bars.GetVolume(j); nc++; }
			avgR = nc > 0 ? avgR / nc : (h - l);
			avgV = nc > 0 ? avgV / nc : Bars.GetVolume(i);
			double pen = ut ? (h - pdh) : (pdl - l);                 // DEPTH of penetration beyond the level
			penFrac    = avgR > 0 ? pen / avgR : 1;
			volRatio   = avgV > 0 ? Bars.GetVolume(i) / avgV : 1;    // VOLUME vs recent
			rangeRatio = avgR > 0 ? (h - l) / avgR : 1;              // RANGE (bar spread) vs recent
			intensity  = (penFrac + volRatio + rangeRatio) / 3.0;    // Wyckoff's 3 factors, combined
			type = intensity <= ShakeoutLowIntensity ? 0
				 : (intensity >= ShakeoutHighIntensity ? 2 : 1);
			return true;
		}

		// Whole-chart spring/upthrust marks: down-triangle+label above an upthrust,
		// up-triangle+label below a spring; colour by Wyckoff type (green #3 / amber #2 / red #1).
		private void RenderSpringUpthrust(ChartControl chartControl, ChartScale chartScale)
		{
			int from = Math.Max(1, ChartBars.FromIndex), to = Math.Min(ChartBars.ToIndex, CurrentBar);
			if (to < from) return;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 9f);
			SolidColorBrush g = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 0.95f));
			SolidColorBrush a = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.95f));
			SolidColorBrush r = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.33f, 0.31f, 0.95f));
			try
			{
				for (int i = from; i <= to; i++)
				{
					bool ut; int type; double pf, vrr, rr, inten;
					if (!WyckoffPoke(i, out ut, out type, out pf, out vrr, out rr, out inten)) continue;
					SolidColorBrush br = type == 0 ? g : type == 2 ? r : a;
					string lab = (ut ? "UT" : "SP") + (type == 0 ? "3" : type == 1 ? "2" : "1");
					float x = chartControl.GetXByBarIndex(ChartBars, i);
					if (ut)
					{
						float y = chartScale.GetYByValue(Bars.GetHigh(i));
						FillTriangle(x, y - 13f, y - 4f, 5f, br);
						RenderTarget.DrawText(lab, tf, new SharpDX.RectangleF(x + 7f, y - 19f, 40f, 12f), br);
					}
					else
					{
						float y = chartScale.GetYByValue(Bars.GetLow(i));
						FillTriangle(x, y + 13f, y + 4f, 5f, br);
						RenderTarget.DrawText(lab, tf, new SharpDX.RectangleF(x + 7f, y + 5f, 40f, 12f), br);
					}
				}
			}
			finally { tf.Dispose(); g.Dispose(); a.Dispose(); r.Dispose(); }
		}

		// small filled triangle: base edge (two corners) at baseY, apex at tipY.
		private void FillTriangle(float cx, float baseY, float tipY, float hw, SolidColorBrush br)
		{
			using (PathGeometry geo = new PathGeometry(RenderTarget.Factory))
			{
				using (GeometrySink sink = geo.Open())
				{
					sink.BeginFigure(new SharpDX.Vector2(cx - hw, baseY), FigureBegin.Filled);
					sink.AddLine(new SharpDX.Vector2(cx + hw, baseY));
					sink.AddLine(new SharpDX.Vector2(cx, tipY));
					sink.EndFigure(FigureEnd.Closed);
					sink.Close();
				}
				RenderTarget.FillGeometry(geo, br);
			}
		}

		// Middle-click read-out: full Wyckoff picture for the inspected bar (climax-flip
		// spring/upthrust type, beyond-PD spring/upthrust, plus bull/bear + IBS + tempo).
		private void RenderInspectCard(ChartControl chartControl, ChartScale chartScale)
		{
			if (inspectBar < 1 || inspectBar > CurrentBar) return;
			int i = inspectBar;
			double o = Bars.GetOpen(i), h = Bars.GetHigh(i), l = Bars.GetLow(i), c = Bars.GetClose(i), v = Bars.GetVolume(i);
			double rg = h - l; double ibs = rg > 0 ? (c - l) / rg : 0.5;
			List<string> lines = new List<string>();
			lines.Add(string.Format("BAR  {0:HH:mm:ss}", Bars.GetTime(i)));
			lines.Add(string.Format("{0}   IBS {1:F2}   vol {2:F0}", c >= o ? "BULL bar" : "BEAR bar", ibs, v));
			lines.Add(string.Format("O {0:F2}  H {1:F2}  L {2:F2}  C {3:F2}", o, h, l, c));
			lines.Add(string.Format("tempo p{0}   climax {1}",
				double.IsNaN(tempoPctS.GetValueAt(i)) ? 0 : (int)Math.Round(tempoPctS.GetValueAt(i)),
				climaxS.GetValueAt(i) >= 0.5 ? "YES" : "no"));

			int fd = FlipDir(i);
			if (fd != 0)
			{
				bool sh = fd == 1; double vr; int sp = SpringType(i, out vr);
				string nm = (sh ? "UT" : "SP") + (sp == 0 ? "3" : sp == 1 ? "2" : "1");
				lines.Add("---- climax-flip ----");
				lines.Add(string.Format("{0}  {1}   rev/trap vol x{2:F2}", sh ? "SHORT" : "LONG", nm, vr));
				lines.Add(sp == 0 ? "  low-vol reversal (Spring #3) - best"
					: sp == 2 ? "  high-vol Terminal Shakeout - weak" : "  moderate volume");
			}

			double pdh = pdhS.GetValueAt(i), pdl = pdlS.GetValueAt(i);
			bool utE; int spType; double pf, vrr, rrr, inten;
			bool pokeEv = WyckoffPoke(i, out utE, out spType, out pf, out vrr, out rrr, out inten);
			if (pokeEv)
			{
				lines.Add("---- beyond prior-day (Wyckoff) ----");
				lines.Add(string.Format("{0}  {1}", utE ? "UPTHRUST" : "SPRING",
					(utE ? "UT" : "SP") + (spType == 0 ? "3  (best)" : spType == 1 ? "2" : "1  Terminal")));
				lines.Add(string.Format("  depth x{0:F2}  vol x{1:F2}  range x{2:F2}", pf, vrr, rrr));
				lines.Add(string.Format("  vs {0} {1:F2}  (observational)", utE ? "PDH" : "PDL", utE ? pdh : pdl));
			}
			if (fd == 0 && !pokeEv) lines.Add("no Wyckoff event on this bar");

			TextFormat tfc = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 11f);
			SolidColorBrush cbg = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.05f, 0.05f, 0.08f, 0.94f));
			SolidColorBrush cbd = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 0.84f, 0f, 0.85f));
			SolidColorBrush cin = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.92f, 0.92f, 0.92f, 1f));
			SolidColorBrush cmk = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.45f, 0.78f, 1f, 1f));
			try
			{
				float cw = 250f, ch = lines.Count * 15f + 10f;
				float bx = (float)chartControl.GetXByBarIndex(ChartBars, i);
				float by = chartScale.GetYByValue(h) - ch - 14f;
				float cx = bx + 8f, cy = by;
				if (cx + cw > ChartPanel.X + ChartPanel.W) cx = bx - cw - 8f;
				if (cy < ChartPanel.Y + 2f) cy = chartScale.GetYByValue(l) + 14f;
				// marker line from the bar to the card
				RenderTarget.DrawLine(new SharpDX.Vector2(bx, chartScale.GetYByValue(h)),
					new SharpDX.Vector2(bx, chartScale.GetYByValue(h) - 10f), cmk, 1.5f);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(cx, cy, cw, ch), cbg);
				RenderTarget.DrawRectangle(new SharpDX.RectangleF(cx, cy, cw, ch), cbd);
				float yy = cy + 5f;
				for (int k = 0; k < lines.Count; k++)
				{
					bool hdr = lines[k].StartsWith("----");
					RenderTarget.DrawText(lines[k], tfc, new SharpDX.RectangleF(cx + 7f, yy, cw - 12f, 14f),
						k == 0 ? cbd : hdr ? cmk : cin);
					yy += 15f;
				}
			}
			finally { tfc.Dispose(); cbg.Dispose(); cbd.Dispose(); cin.Dispose(); cmk.Dispose(); }
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

		// heat color for a percentile: cool blue -> amber -> orange -> red (climax)
		private SharpDX.Color4 PctColor(double p)
		{
			if (p >= 95) return new SharpDX.Color4(0.95f, 0.30f, 0.25f, 1f);
			if (p >= 80) return new SharpDX.Color4(1f, 0.62f, 0.15f, 1f);
			if (p >= 50) return new SharpDX.Color4(1f, 0.84f, 0.30f, 1f);
			return new SharpDX.Color4(0.45f, 0.65f, 0.85f, 1f);
		}

		// label + colored value + colored fill gauge with a notch at the climax percentile
		private void GaugeLine(TextFormat tf, float x, ref float y, string label, double pct,
			string valText, SolidColorBrush white)
		{
			RenderTarget.DrawText(label, tf, new SharpDX.RectangleF(x, y, 76f, 18f), white);
			bool ok = !double.IsNaN(pct);
			SolidColorBrush cb = new SolidColorBrush(RenderTarget, ok ? PctColor(pct)
				: new SharpDX.Color4(0.65f, 0.65f, 0.65f, 1f));
			RenderTarget.DrawText(valText ?? (ok ? "p" + Math.Round(pct) : "-"), tf,
				new SharpDX.RectangleF(x + 76f, y, 70f, 18f), cb);
			float gx = x + 148f, gw = 84f, gh = 7f, gy = y + 5f;
			SolidColorBrush trk = new SolidColorBrush(RenderTarget, new SharpDX.Color4(1f, 1f, 1f, 0.12f));
			RenderTarget.FillRectangle(new SharpDX.RectangleF(gx, gy, gw, gh), trk);
			if (ok)
				RenderTarget.FillRectangle(new SharpDX.RectangleF(gx, gy,
					(float)(gw * Math.Max(0.0, Math.Min(100.0, pct)) / 100.0), gh), cb);
			float nx = gx + gw * (float)(ClimacticPct / 100.0);
			RenderTarget.DrawLine(new SharpDX.Vector2(nx, gy - 2f), new SharpDX.Vector2(nx, gy + gh + 2f), trk, 1f);
			trk.Dispose(); cb.Dispose();
			y += 19f;
		}

		private void RenderSpeedo(TextFormat tf, SolidColorBrush white, SolidColorBrush dim, SolidColorBrush gold, SolidColorBrush bg)
		{
			float wBox = 248f;
			bool showPace = !double.IsNaN(livePacePct);
			int lines = 4 + (showPace ? 1 : 0) + (ShowStateLabel ? 1 : 0) + (lastClimax ? 1 : 0) + (ShowDiag ? 1 : 0);
			float hBox = 10f + 19f * lines;
			bool left = SpeedoCorner == TempoBoxCorner.TopLeft || SpeedoCorner == TempoBoxCorner.BottomLeft;
			bool top  = SpeedoCorner == TempoBoxCorner.TopLeft || SpeedoCorner == TempoBoxCorner.TopRight;
			float x0 = left ? ChartPanel.X + 10f : ChartPanel.X + ChartPanel.W - wBox - 10f;
			float y0 = top ? ChartPanel.Y + 10f : ChartPanel.Y + ChartPanel.H - hBox - 16f;
			RenderTarget.FillRectangle(new SharpDX.RectangleF(x0, y0, wBox, hBox), bg);
			SolidColorBrush edge = new SolidColorBrush(RenderTarget, PctColor(lastTempoPct));
			RenderTarget.DrawRectangle(new SharpDX.RectangleF(x0, y0, wBox, hBox), edge, 1.2f);

			float y = y0 + 5f;
			GaugeLine(tf, x0 + 8f, ref y, "TEMPO", lastTempoPct, null, white);
			if (showPace)
				GaugeLine(tf, x0 + 8f, ref y, "PACE " + PaceWindowSec + "s", livePacePct, null, white);
			GaugeLine(tf, x0 + 8f, ref y, "AMPLITUDE", lastAmpPct, double.IsNaN(lastAmpAbr)
				? null : string.Format("{0:F0}% ABR8", lastAmpAbr), white);
			GaugeLine(tf, x0 + 8f, ref y, "EFFICIENCY", lastEffPct, null, white);
			if (lastAccel > 0)
			{
				SolidColorBrush ab = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.30f, 0.82f, 0.63f, 1f));
				DrawLine2(tf, x0 + 8f, ref y, "TEMPO: ACCELERATING", ab); ab.Dispose();
			}
			else if (lastAccel < 0)
			{
				SolidColorBrush ab = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.94f, 0.45f, 0.40f, 1f));
				DrawLine2(tf, x0 + 8f, ref y, "TEMPO: DECELERATING", ab); ab.Dispose();
			}
			else DrawLine2(tf, x0 + 8f, ref y, "TEMPO: STABLE", dim);
			if (ShowStateLabel) DrawLine2(tf, x0 + 8f, ref y, lastState, white);
			if (lastClimax)     DrawLine2(tf, x0 + 8f, ref y, "** CLIMACTIC STATE **", gold);
			if (ShowDiag)
			{
				string mode = (lastN >= MIN_SAMPLES ? "SELF" : "WARM " + lastN + "/" + MIN_SAMPLES)
					+ (chartMode == 1 ? " TR" : "");
				DrawLine2(tf, x0 + 8f, ref y, string.Format("DIAG {0:HH:mm} b{1} {2:F0}t/s {3}",
					lastBarTime, lastBucket, lastRate, mode), dim);
			}
			edge.Dispose();
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

		// --- 3. Boxes / display ------------------------------------------------
		[NinjaScriptProperty]
		[Display(Name = "Show speedometer", GroupName = "3. Boxes / display", Order = 0)]
		public bool ShowSpeedo { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Speedometer corner", GroupName = "3. Boxes / display", Order = 1)]
		public TempoBoxCorner SpeedoCorner { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show heat strip", GroupName = "3. Boxes / display", Order = 2)]
		public bool ShowHeatStrip { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show 2D engine dot", GroupName = "3. Boxes / display", Order = 3)]
		public bool ShowEngineDot { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show state label", GroupName = "3. Boxes / display", Order = 4)]
		public bool ShowStateLabel { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show DIAG line", GroupName = "3. Boxes / display", Order = 5)]
		public bool ShowDiag { get; set; }

		// --- 4. Flip setup (signal -> entry -> management) ---------------------
		[NinjaScriptProperty]
		[Display(Name = "Show climax-flip setups (box + RR)", GroupName = "4. Flip setup", Order = 0)]
		public bool ShowClimaxFlip { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Signal: SB IBS direction (0.55/0.45; bar1=color)", GroupName = "4. Flip setup", Order = 1)]
		public bool UseIbsDirection { get; set; }

		[NinjaScriptProperty, Range(0, 20)]
		[Display(Name = "Signal: min SB body (ticks)", GroupName = "4. Flip setup", Order = 2)]
		public int MinSbBodyTicks { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Entry: mode (StopEntry / Close)", GroupName = "4. Flip setup", Order = 3)]
		public FlipEntryMode EntryMode { get; set; }

		[NinjaScriptProperty, Range(1, 20)]
		[Display(Name = "Entry: SE order life (bars after SB)", GroupName = "4. Flip setup", Order = 4)]
		public int SeOrderLifeBars { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Manage: reverse on opposite signal (SAR)", GroupName = "4. Flip setup", Order = 5)]
		public bool ReverseOnOpposite { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Manage: EB opposite-IBS scratch", GroupName = "4. Flip setup", Order = 6)]
		public bool EbScratch { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Manage: EB on bar after SB (off = the bar that fills the SE)", GroupName = "4. Flip setup", Order = 7)]
		public bool EbOnSignalBar { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Wyckoff: show spring type (SP3 / SP2 / TSO)", GroupName = "4. Flip setup", Order = 8)]
		public bool ShowSpringTypes { get; set; }

		[NinjaScriptProperty, Range(0.10, 2.0)]
		[Display(Name = "Wyckoff: SP3 max vol ratio (reversal/trap)", GroupName = "4. Flip setup", Order = 9)]
		public double Sp3MaxRatio { get; set; }

		[NinjaScriptProperty, Range(0.10, 3.0)]
		[Display(Name = "Wyckoff: TSO min vol ratio (Terminal Shakeout)", GroupName = "4. Flip setup", Order = 10)]
		public double TsoMinRatio { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Wyckoff: SKIP Terminal Shakeout entries", GroupName = "4. Flip setup", Order = 11)]
		public bool SkipTerminalShakeout { get; set; }

		// --- 6. Springs & upthrusts (whole-chart, beyond prior-day) ------------
		[NinjaScriptProperty]
		[Display(Name = "Show springs / upthrusts (beyond prior-day)", GroupName = "6. Springs & upthrusts", Order = 0)]
		public bool ShowSpringUpthrust { get; set; }

		[NinjaScriptProperty, Range(0.10, 3.0)]
		[Display(Name = "Shakeout intensity: #3 max (depth+vol+range)", GroupName = "6. Springs & upthrusts", Order = 1)]
		public double ShakeoutLowIntensity { get; set; }

		[NinjaScriptProperty, Range(0.20, 5.0)]
		[Display(Name = "Shakeout intensity: #1 min (Terminal Shakeout)", GroupName = "6. Springs & upthrusts", Order = 2)]
		public double ShakeoutHighIntensity { get; set; }

		// --- 5. Live pace / alert ----------------------------------------------
		[NinjaScriptProperty, Range(5, 300)]
		[Display(Name = "Live pace window (sec)", GroupName = "5. Live pace / alert", Order = 0)]
		public int PaceWindowSec { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Audio alert on climactic pace", GroupName = "5. Live pace / alert", Order = 1)]
		public bool AlertOnClimax { get; set; }

		[NinjaScriptProperty, Range(10, 3600)]
		[Display(Name = "Alert cooldown (sec)", GroupName = "5. Live pace / alert", Order = 2)]
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
