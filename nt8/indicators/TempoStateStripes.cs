// TempoStateStripes.cs — S116-tempo companion: the state/regime RACING-STRIPES panel.
//
// Own panel (IsOverlay=false), seven horizontal lanes, one per market state; each
// completed 2000t bar fills a cell in its active lane, so regime changes read as
// lane jumps. States and thresholds MATCH TempoSpeedometer.StateLabel — keep the
// two files in sync if rules change. Descriptive only (Stage-2: no predictive edge).
//
// Lanes (top->bottom, "energy" order) and colors:
//   CLIMAX    gold #ffd700 (tempo >= climax pct for this time of day)
//   EXPAND    bull teal #199e70 / bear red #e34948  (fast + big + efficient)
//   CHURN     orange #d95926                        (fast + big + inefficient)
//   ACTIVITY  magenta #d55181                       (fast, no amplitude)
//   GRIND     pale teal #8fd0bc / pale red #f0a29b  (slow + directional)
//   BALANCE   blue #3987e5                          (slow + small = quiet)
//   MIXED     gray #9aa0a6                          (everything else)
//
// Calibration identical to TempoSpeedometer: tod_percentiles.csv (or rolling toggle),
// buckets anchored to the 08:30 exchange clock via NT display tz -> exchange tz.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
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
		private const int NBUCKETS = 27;
		private const int NLANES = 7;
		private static readonly string[] LaneNames = { "CLIMAX", "EXPAND", "CHURN", "ACTIVITY", "GRIND", "BALANCE", "MIXED" };

		private double[][] gridTempo, gridRange;
		private double[] gridEff;
		private bool tableOk, notTickChart;
		private Series<double> stateS, dirS;               // state 0..6 (NaN = no data), dir +1/-1
		private List<double> rollTempo, rollRange, rollEff;
		private double emaClose;
		private bool emaInit;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "S116 tempo state stripes: 7-lane regime timeline (matches TempoSpeedometer states). Observational only.";
				Name = "TempoStateStripes";
				Calculate = Calculate.OnBarClose;
				IsOverlay = false;
				DisplayInDataBox = true;
				PaintPriceMarkers = false;
				IsSuspendedWhileInactive = true;

				// transparent plots: nothing extra draws, but every value lands in the Data Box
				AddPlot(System.Windows.Media.Brushes.Transparent, "State");        // 0 CLIMAX 1 EXPAND 2 CHURN 3 ACTIVITY 4 GRIND 5 BALANCE 6 MIXED
				AddPlot(System.Windows.Media.Brushes.Transparent, "TempoPct");
				AddPlot(System.Windows.Media.Brushes.Transparent, "AmplitudePct");
				AddPlot(System.Windows.Media.Brushes.Transparent, "EffPct");
				AddPlot(System.Windows.Media.Brushes.Transparent, "TicksPerSec");
				AddPlot(System.Windows.Media.Brushes.Transparent, "DurationSec");

				CsvPath = @"C:\Users\Admin\myquant\tempo\outputs\tod_percentiles.csv";
				UseTodCalibration = true;
				RollingWindow = 200;
				ClimacticPct = 95;
			}
			else if (State == State.Configure)
			{
				rollTempo = new List<double>(); rollRange = new List<double>(); rollEff = new List<double>();
				tableOk = false;
				if (UseTodCalibration) LoadTable();
			}
			else if (State == State.DataLoaded)
			{
				stateS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				dirS = new Series<double>(this, MaximumBarsLookBack.Infinite);
				notTickChart = BarsPeriod.BarsPeriodType != BarsPeriodType.Tick;
			}
		}

		private void LoadTable()
		{
			try
			{
				if (!File.Exists(CsvPath)) { Log("TempoStateStripes: calibration csv not found -> rolling mode", LogLevel.Warning); return; }
				gridTempo = new double[NBUCKETS + 1][];
				gridRange = new double[NBUCKETS + 1][];
				string[] lines = File.ReadAllLines(CsvPath);
				for (int li = 1; li < lines.Length; li++)
				{
					string[] c = lines[li].Split(',');
					if (c.Length < 102) continue;
					int bucket = int.Parse(c[1], System.Globalization.CultureInfo.InvariantCulture);
					double[] g = new double[99];
					for (int p = 0; p < 99; p++)
						g[p] = double.Parse(c[3 + p], System.Globalization.CultureInfo.InvariantCulture);
					int idx = bucket + 1;
					if (idx < 0 || idx > NBUCKETS) continue;
					if (c[0] == "tempo") gridTempo[idx] = g;
					else if (c[0] == "range") gridRange[idx] = g;
					else if (c[0] == "eff" && bucket == -1) gridEff = g;
				}
				tableOk = gridTempo[0] != null && gridRange[0] != null && gridEff != null;
			}
			catch (Exception ex) { tableOk = false; Log("TempoStateStripes: csv load failed (" + ex.Message + ")", LogLevel.Warning); }
		}

		private static double PctFromGrid(double[] g, double v)
		{
			if (g == null) return 50;
			if (v <= g[0]) return 1;
			if (v >= g[98]) return 99;
			int lo = 0, hi = 98;
			while (hi - lo > 1) { int m = (lo + hi) / 2; if (g[m] <= v) lo = m; else hi = m; }
			double frac = g[hi] > g[lo] ? (v - g[lo]) / (g[hi] - g[lo]) : 0;
			return (lo + 1) + frac;
		}

		private static double PctFromRolling(List<double> w, double v)
		{
			if (w.Count < 30) return 50;
			int below = 0;
			for (int i = 0; i < w.Count; i++) if (w[i] <= v) below++;
			return Math.Max(1, Math.Min(99, 100.0 * below / (w.Count + 1)));
		}

		private static void Push(List<double> w, double v, int cap)
		{
			w.Add(v);
			if (w.Count > cap) w.RemoveAt(0);
		}

		protected override void OnBarUpdate()
		{
			stateS[0] = double.NaN; dirS[0] = 0;
			if (notTickChart || CurrentBar < 1 || Bars.IsFirstBarOfSession)
			{
				for (int p = 0; p < 6; p++) Values[p].Reset();
				return;
			}

			double duration = (Time[0] - Time[1]).TotalSeconds;
			if (duration < 0.001) duration = 0.001;
			double tempo = BarsPeriod.Value / duration;
			double range = High[0] - Low[0];
			double eff = range > 0 ? Math.Abs(Close[0] - Open[0]) / range : 0;

			bool outsideRth = false;
			int bucket = 0;
			DateTime exch = Time[0];
			try
			{
				TimeZoneInfo srcTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
				TimeZoneInfo exTz = Bars.TradingHours.TimeZoneInfo;
				exch = TimeZoneInfo.ConvertTime(DateTime.SpecifyKind(Time[0], DateTimeKind.Unspecified), srcTz, exTz);
			}
			catch { }
			double mins = (exch.TimeOfDay - new TimeSpan(8, 30, 0)).TotalMinutes;
			if (mins < 0 || mins >= 405) outsideRth = true;
			else bucket = Math.Min(NBUCKETS - 1, Math.Max(0, (int)Math.Floor(mins / 15.0)));

			double tPct, aPct, ePct;
			if (UseTodCalibration && tableOk)
			{
				int gi = outsideRth ? 0 : bucket + 1;
				tPct = PctFromGrid(gridTempo[gi] != null ? gridTempo[gi] : gridTempo[0], tempo);
				aPct = PctFromGrid(gridRange[gi] != null ? gridRange[gi] : gridRange[0], range);
				ePct = PctFromGrid(gridEff, eff);
			}
			else
			{
				tPct = PctFromRolling(rollTempo, tempo);
				aPct = PctFromRolling(rollRange, range);
				ePct = PctFromRolling(rollEff, eff);
			}
			Push(rollTempo, tempo, RollingWindow);
			Push(rollRange, range, RollingWindow);
			Push(rollEff, eff, RollingWindow);

			double k = 2.0 / 21.0;
			if (!emaInit) { emaClose = Close[0]; emaInit = true; }
			bool bull = Close[0] >= emaClose;
			emaClose += k * (Close[0] - emaClose);

			// SAME rules as TempoSpeedometer (CLIMAX lane == the gold bar dots: >= ClimacticPct)
			int state;
			if (tPct >= ClimacticPct) state = 0;                              // CLIMAX
			else if (tPct >= 80 && aPct >= 80 && eff >= 0.60) state = 1;      // EXPAND
			else if (tPct >= 80 && aPct >= 80 && eff < 0.35) state = 2;       // CHURN
			else if (tPct >= 80 && aPct < 50) state = 3;                      // ACTIVITY / no progress
			else if (tPct < 40 && aPct < 40) state = 5;                       // BALANCE
			else if (tPct < 40 && eff >= 0.60) state = 4;                     // GRIND
			else state = 6;                                                   // MIXED
			stateS[0] = state;
			dirS[0] = bull ? 1 : -1;

			Values[0][0] = state;
			Values[1][0] = Math.Round(tPct);
			Values[2][0] = Math.Round(aPct);
			Values[3][0] = Math.Round(ePct);
			Values[4][0] = Math.Round(tempo, 1);
			Values[5][0] = Math.Round(duration, 1);
		}

		private SharpDX.Color4 LaneColor(int state, double dir)
		{
			switch (state)
			{
				case 0: return new SharpDX.Color4(1f, 0.84f, 0f, 1f);                                   // gold
				case 1: return dir >= 0 ? new SharpDX.Color4(0.10f, 0.62f, 0.44f, 1f)                    // teal
									   : new SharpDX.Color4(0.89f, 0.29f, 0.28f, 1f);                    // red
				case 2: return new SharpDX.Color4(0.85f, 0.35f, 0.15f, 1f);                              // orange
				case 3: return new SharpDX.Color4(0.84f, 0.32f, 0.51f, 1f);                              // magenta
				case 4: return dir >= 0 ? new SharpDX.Color4(0.56f, 0.82f, 0.74f, 1f)                    // pale teal
									   : new SharpDX.Color4(0.94f, 0.64f, 0.61f, 1f);                    // pale red
				case 5: return new SharpDX.Color4(0.22f, 0.53f, 0.90f, 1f);                              // blue
				default: return new SharpDX.Color4(0.60f, 0.63f, 0.65f, 1f);                             // gray
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
						Math.Max(1f, w - 1f), laneH - 2f), cb);
					cb.Dispose();
				}

				for (int l = 0; l < NLANES; l++)
					RenderTarget.DrawText(LaneNames[l], tfTiny,
						new SharpDX.RectangleF(ChartPanel.X + 4, top + l * laneH + (laneH - 11f) / 2f, 70, 12), dim);
			}
			finally { tfTiny.Dispose(); dim.Dispose(); sep.Dispose(); }
		}

		#region properties
		[NinjaScriptProperty]
		[Display(Name = "Calibration CSV path", GroupName = "1. Calibration", Order = 0)]
		public string CsvPath { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Time-of-day calibration (off = rolling)", GroupName = "1. Calibration", Order = 1)]
		public bool UseTodCalibration { get; set; }

		[NinjaScriptProperty, Range(30, 2000)]
		[Display(Name = "Rolling window (bars)", GroupName = "1. Calibration", Order = 2)]
		public int RollingWindow { get; set; }

		[NinjaScriptProperty, Range(50, 100)]
		[Display(Name = "Climactic percentile (match TempoSpeedometer)", GroupName = "1. Calibration", Order = 3)]
		public int ClimacticPct { get; set; }
		#endregion
	}
}
