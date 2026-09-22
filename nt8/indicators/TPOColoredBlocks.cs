#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
#endregion

// ─────────────────────────────────────────────────────────────────────────────
// TPOColoredBlocks — Market Profile (TPO) drawn as COLORED BLOCKS, one square
// per 30-min bracket per price row, colored blue (early) → red (late). This
// replicates the PATs EOD auction tool (scripts/pats_profile_charts.py) on a
// live NT8 chart. TPO only (time-at-price); needs just the chart's price bars
// (enable Tick Replay for the most accurate historical rows). No L2/depth.
//
// Each session is profiled separately and anchored at its first bar, growing
// rightward as blocks — the classic split-profile look. Row height, bracket
// length, block width and opacity are all adjustable.
//
// Commit CS to: repo/nt8/indicators/TPOColoredBlocks.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class TPOColoredBlocks : Indicator
	{
		private double rowSize;

		private class SessionProfile
		{
			public int StartBar;
			public int EndBar;
			public DateTime Start;
			public Dictionary<double, HashSet<int>> Rows = new Dictionary<double, HashSet<int>>();
		}

		private List<SessionProfile> sessions;
		private SessionProfile cur;

		[NinjaScriptProperty]
		[Range(1, int.MaxValue)]
		[Display(Name = "Row height (ticks)", Order = 0, GroupName = "TPO")]
		public int RowTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, int.MaxValue)]
		[Display(Name = "Bracket minutes", Order = 1, GroupName = "TPO")]
		public int BracketMinutes { get; set; }

		[NinjaScriptProperty]
		[Range(1, int.MaxValue)]
		[Display(Name = "Block width (px)", Order = 2, GroupName = "TPO")]
		public int BlockWidthPx { get; set; }

		[NinjaScriptProperty]
		[Range(0.05, 1.0)]
		[Display(Name = "Opacity", Order = 3, GroupName = "TPO")]
		public double Opacity { get; set; }

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name										= "TPO Colored Blocks";
				Description									= "Market Profile TPO as colored blocks (blue early -> red late), one per bracket per price row.";
				IsOverlay									= true;
				IsChartOnly									= true;
				DrawOnPricePanel							= true;
				IsSuspendedWhileInactive					= true;
				RowTicks									= 4;
				BracketMinutes								= 30;
				BlockWidthPx								= 6;
				Opacity										= 0.85;
			}
			else if (State == State.Configure)
			{
				rowSize = RowTicks * TickSize;
			}
			else if (State == State.DataLoaded)
			{
				sessions = new List<SessionProfile>();
				cur = null;
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0)
				return;
			if (rowSize <= 0)
				rowSize = RowTicks * TickSize;

			if (cur == null || Bars.IsFirstBarOfSession)
			{
				cur = new SessionProfile { StartBar = CurrentBar, Start = Time[0] };
				sessions.Add(cur);
			}
			cur.EndBar = CurrentBar;

			int bracket = (int)((Time[0] - cur.Start).TotalMinutes / BracketMinutes);
			if (bracket < 0)
				bracket = 0;

			double lo = Math.Floor(Low[0] / rowSize) * rowSize;
			for (double p = lo; p <= High[0] + rowSize * 0.5; p += rowSize)
			{
				double key = Math.Round(p, 5);
				HashSet<int> set;
				if (!cur.Rows.TryGetValue(key, out set))
				{
					set = new HashSet<int>();
					cur.Rows[key] = set;
				}
				set.Add(bracket);
			}
		}

		private SharpDX.Color4 BracketColor(int b, int maxB)
		{
			double t = maxB <= 0 ? 0.0 : (double)b / maxB;
			float r, g, bl, u;
			if (t < 0.25) { u = (float)(t / 0.25); r = 0.20f; g = 0.30f + 0.40f * u; bl = 0.90f; }
			else if (t < 0.50) { u = (float)((t - 0.25) / 0.25); r = 0.20f; g = 0.70f + 0.20f * u; bl = 0.90f - 0.60f * u; }
			else if (t < 0.75) { u = (float)((t - 0.50) / 0.25); r = 0.20f + 0.70f * u; g = 0.90f; bl = 0.30f - 0.30f * u; }
			else { u = (float)((t - 0.75) / 0.25); r = 0.90f; g = 0.90f - 0.60f * u; bl = 0.10f; }
			return new SharpDX.Color4(r, g, bl, (float)Opacity);
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (sessions == null || sessions.Count == 0 || ChartBars == null || RenderTarget == null)
				return;

			int toIdx = ChartBars.ToIndex;
			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f)
				rowH = 1f;

			foreach (SessionProfile s in sessions)
			{
				if (s.StartBar > toIdx)
					continue;

				int maxB = 0;
				foreach (KeyValuePair<double, HashSet<int>> kv in s.Rows)
					foreach (int b in kv.Value)
						if (b > maxB)
							maxB = b;

				// Anchor the profile just to the RIGHT of the session's last bar
				// so it sits beside the candles (like the Python panel), not over them.
				float x0 = chartControl.GetXByBarIndex(ChartBars, s.EndBar) + BlockWidthPx * 2f;

				SolidColorBrush[] brushes = new SolidColorBrush[maxB + 1];
				for (int b = 0; b <= maxB; b++)
					brushes[b] = new SolidColorBrush(RenderTarget, BracketColor(b, maxB));

				foreach (KeyValuePair<double, HashSet<int>> kv in s.Rows)
				{
					float yTop = chartScale.GetYByValue(kv.Key + rowSize);
					// Pack this row's blocks LEFT-to-right by stack order (k),
					// color by bracket (b). Position must NOT be the bracket
					// index or the profile skews diagonally on trend days.
					List<int> brs = new List<int>(kv.Value);
					brs.Sort();
					for (int k = 0; k < brs.Count; k++)
					{
						float x = x0 + k * BlockWidthPx;
						RenderTarget.FillRectangle(
							new SharpDX.RectangleF(x, yTop, BlockWidthPx - 1f, rowH - 1f),
							brushes[brs[k]]);
					}
				}

				for (int b = 0; b <= maxB; b++)
					brushes[b].Dispose();
			}
		}
	}
}
