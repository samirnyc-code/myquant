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
// PATsProfile — right-margin TPO (Market Profile) + Volume Profile, side by
// side, pinned to the price axis (off the candles). Dalton stats: POC, 70%
// value area (Mind Over Markets, two-prices-at-a-time), initial balance, and a
// value-area band. Composite mode merges the last N sessions into one profile.
//
// This supersedes TPOColoredBlocks. Profiles are drawn in the chart's right
// margin so they never sit on the wrong day. Volume-per-row is distributed
// evenly across each bar's price rows (bar approximation; enable Tick Replay
// for finer rows).
//
// Follow-ups (not yet built): numeric VAH/VAL/POC text labels, a chart-toolbar
// toggle button, and interactive right-click Merge Left/Right between sessions.
//
// Commit CS to: repo/nt8/indicators/PATsProfile.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsProfile : Indicator
	{
		private double rowSize;
		private List<int> sessionStarts;

		// cached aggregate (recomputed only when signature changes)
		private string sig = "";
		private Dictionary<double, double> volByRow;
		private Dictionary<double, List<int>> tpoByRow;
		private double poc, vah, val, ibh, ibl, maxVol;
		private int maxBracket;

		[NinjaScriptProperty] [Range(1, int.MaxValue)]
		[Display(Name = "Row height (ticks)", Order = 0, GroupName = "1 Profile")]
		public int RowTicks { get; set; }

		[NinjaScriptProperty] [Range(1, int.MaxValue)]
		[Display(Name = "Bracket minutes", Order = 1, GroupName = "1 Profile")]
		public int BracketMinutes { get; set; }

		[NinjaScriptProperty] [Range(1, 60)]
		[Display(Name = "Composite sessions (1 = today only)", Order = 2, GroupName = "1 Profile")]
		public int CompositeSessions { get; set; }

		[NinjaScriptProperty] [Range(20, 800)]
		[Display(Name = "VP width (px)", Order = 3, GroupName = "1 Profile")]
		public int VpWidthPx { get; set; }

		[NinjaScriptProperty] [Range(2, 40)]
		[Display(Name = "TPO block width (px)", Order = 4, GroupName = "1 Profile")]
		public int BlockWidthPx { get; set; }

		[NinjaScriptProperty] [Range(0, 800)]
		[Display(Name = "Right offset (px)", Order = 5, GroupName = "1 Profile")]
		public int RightOffsetPx { get; set; }

		[NinjaScriptProperty] [Range(0.05, 1.0)]
		[Display(Name = "Opacity", Order = 6, GroupName = "1 Profile")]
		public double Opacity { get; set; }

		[NinjaScriptProperty] [Display(Name = "Show TPO", Order = 0, GroupName = "2 Toggles")]
		public bool ShowTPO { get; set; }

		[NinjaScriptProperty] [Display(Name = "Show Volume Profile", Order = 1, GroupName = "2 Toggles")]
		public bool ShowVP { get; set; }

		[NinjaScriptProperty] [Display(Name = "Show Value Area", Order = 2, GroupName = "2 Toggles")]
		public bool ShowVA { get; set; }

		[NinjaScriptProperty] [Display(Name = "Show POC", Order = 3, GroupName = "2 Toggles")]
		public bool ShowPOC { get; set; }

		[NinjaScriptProperty] [Display(Name = "Show Initial Balance", Order = 4, GroupName = "2 Toggles")]
		public bool ShowIB { get; set; }

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name							= "PATs Profile (TPO+VP)";
				Description						= "Right-margin TPO + Volume Profile with Dalton value area / POC / initial balance and composite merge.";
				IsOverlay						= true;
				IsChartOnly						= true;
				DrawOnPricePanel				= true;
				IsSuspendedWhileInactive		= true;
				RowTicks						= 4;
				BracketMinutes					= 30;
				CompositeSessions				= 1;
				VpWidthPx						= 150;
				BlockWidthPx					= 7;
				RightOffsetPx					= 6;
				Opacity							= 0.85;
				ShowTPO							= true;
				ShowVP							= true;
				ShowVA							= true;
				ShowPOC							= true;
				ShowIB							= true;
			}
			else if (State == State.Configure)
			{
				rowSize = RowTicks * TickSize;
			}
			else if (State == State.DataLoaded)
			{
				sessionStarts = new List<int>();
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0)
				return;
			if (rowSize <= 0)
				rowSize = RowTicks * TickSize;
			if (CurrentBar == 0 || Bars.IsFirstBarOfSession)
				sessionStarts.Add(CurrentBar);
		}

		private void Recompute(int endBar)
		{
			volByRow = new Dictionary<double, double>();
			tpoByRow = new Dictionary<double, List<int>>();
			int sc = sessionStarts.Count;
			int wIdx = Math.Max(0, sc - Math.Max(1, CompositeSessions));
			int startBar = sc > 0 ? sessionStarts[wIdx] : 0;
			int lastStart = sc > 0 ? sessionStarts[sc - 1] : 0;
			DateTime wStart = Time.GetValueAt(startBar);
			DateTime lastSess = Time.GetValueAt(lastStart);
			ibh = double.MinValue; ibl = double.MaxValue; maxBracket = 0;

			for (int i = startBar; i <= endBar; i++)
			{
				double h = High.GetValueAt(i), l = Low.GetValueAt(i), v = Volume.GetValueAt(i);
				DateTime t = Time.GetValueAt(i);
				int bracket = (int)((t - wStart).TotalMinutes / BracketMinutes);
				if (bracket < 0) bracket = 0;
				if (bracket > maxBracket) maxBracket = bracket;

				double lo = Math.Floor(l / rowSize) * rowSize;
				int nrows = 0;
				for (double p = lo; p <= h + rowSize * 0.5; p += rowSize) nrows++;
				if (nrows < 1) nrows = 1;
				double vShare = v / nrows;

				for (double p = lo; p <= h + rowSize * 0.5; p += rowSize)
				{
					double key = Math.Round(p, 5);
					double cv; volByRow.TryGetValue(key, out cv); volByRow[key] = cv + vShare;
					List<int> lst;
					if (!tpoByRow.TryGetValue(key, out lst)) { lst = new List<int>(); tpoByRow[key] = lst; }
					if (!lst.Contains(bracket)) lst.Add(bracket);
				}

				if (i >= lastStart && t < lastSess.AddMinutes(60))
				{
					if (h > ibh) ibh = h;
					if (l < ibl) ibl = l;
				}
			}

			poc = double.NaN; maxVol = 0;
			foreach (KeyValuePair<double, double> kv in volByRow)
				if (kv.Value > maxVol) { maxVol = kv.Value; poc = kv.Key; }
			ComputeValueArea();
		}

		// Dalton volume value area (MOM Appendix 1): from POC, compare the two
		// rows above vs the two below, add the heavier pair, until 70% volume.
		private void ComputeValueArea()
		{
			List<double> prices = new List<double>(volByRow.Keys);
			prices.Sort();
			int n = prices.Count;
			if (n == 0) { vah = val = double.NaN; return; }
			int pocI = prices.IndexOf(poc);
			if (pocI < 0) pocI = 0;
			double total = 0;
			foreach (double vv in volByRow.Values) total += vv;
			double target = 0.70 * total;
			double acc = volByRow[prices[pocI]];
			int lo = pocI, hi = pocI;
			while (acc < target && (lo > 0 || hi < n - 1))
			{
				double up = (hi + 1 < n ? volByRow[prices[hi + 1]] : 0) + (hi + 2 < n ? volByRow[prices[hi + 2]] : 0);
				double dn = (lo - 1 >= 0 ? volByRow[prices[lo - 1]] : 0) + (lo - 2 >= 0 ? volByRow[prices[lo - 2]] : 0);
				bool upok = hi < n - 1, dnok = lo > 0;
				if (upok && (up >= dn || !dnok))
					for (int k = 0; k < 2 && hi < n - 1; k++) { hi++; acc += volByRow[prices[hi]]; }
				else if (dnok)
					for (int k = 0; k < 2 && lo > 0; k++) { lo--; acc += volByRow[prices[lo]]; }
				else break;
			}
			val = prices[lo]; vah = prices[hi];
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
			if (sessionStarts == null || RenderTarget == null || ChartBars == null || Bars == null)
				return;
			int endBar = Bars.Count - 1;
			if (endBar < 0)
				return;

			string s = endBar + "|" + CompositeSessions + "|" + RowTicks + "|" + BracketMinutes;
			if (s != sig || volByRow == null) { Recompute(endBar); sig = s; }
			if (volByRow == null || volByRow.Count == 0 || maxVol <= 0)
				return;

			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f) rowH = 1f;
			float panelLeft = (float)ChartPanel.X;
			float vpRight = (float)(ChartPanel.X + ChartPanel.W) - RightOffsetPx;
			float vpLeft = vpRight - VpWidthPx;
			float tpoRight = vpLeft - 8f;

			SolidColorBrush teal = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.35f, 0.71f, 0.82f, (float)Opacity));
			SolidColorBrush pocBr = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.88f, 0.53f, 0.25f, 0.95f));
			SolidColorBrush vaBr = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.72f, 0.55f, 0.85f, 0.12f));
			SolidColorBrush ibBr = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.88f, 0.71f, 0.37f, 0.75f));
			SolidColorBrush[] brackets = new SolidColorBrush[maxBracket + 1];
			for (int b = 0; b <= maxBracket; b++)
				brackets[b] = new SolidColorBrush(RenderTarget, BracketColor(b, maxBracket));

			// value-area band across the whole panel (behind everything)
			if (ShowVA && !double.IsNaN(vah))
			{
				float y1 = chartScale.GetYByValue(vah), y2 = chartScale.GetYByValue(val);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(panelLeft, Math.Min(y1, y2),
					vpRight - panelLeft, Math.Abs(y2 - y1)), vaBr);
			}

			foreach (KeyValuePair<double, double> kv in volByRow)
			{
				double price = kv.Key;
				float yTop = chartScale.GetYByValue(price + rowSize);
				if (ShowVP)
				{
					float w = (float)(VpWidthPx * kv.Value / maxVol);
					SolidColorBrush br = (ShowPOC && price == poc) ? pocBr : teal;
					RenderTarget.FillRectangle(new SharpDX.RectangleF(vpRight - w, yTop, w, rowH - 1f), br);
				}
				if (ShowTPO)
				{
					List<int> brs;
					if (tpoByRow.TryGetValue(price, out brs))
					{
						brs.Sort();
						for (int k = 0; k < brs.Count; k++)
						{
							float x = tpoRight - (k + 1) * BlockWidthPx;
							RenderTarget.FillRectangle(new SharpDX.RectangleF(x, yTop, BlockWidthPx - 1f, rowH - 1f), brackets[brs[k]]);
						}
					}
				}
			}

			if (ShowPOC && !double.IsNaN(poc))
			{
				float y = chartScale.GetYByValue(poc);
				RenderTarget.DrawLine(new SharpDX.Vector2(panelLeft, y), new SharpDX.Vector2(vpRight, y), pocBr, 1.2f);
			}
			if (ShowIB && ibh > double.MinValue)
			{
				float yh = chartScale.GetYByValue(ibh), yl = chartScale.GetYByValue(ibl);
				RenderTarget.DrawLine(new SharpDX.Vector2(panelLeft, yh), new SharpDX.Vector2(vpRight, yh), ibBr, 0.9f);
				RenderTarget.DrawLine(new SharpDX.Vector2(panelLeft, yl), new SharpDX.Vector2(vpRight, yl), ibBr, 0.9f);
			}

			teal.Dispose(); pocBr.Dispose(); vaBr.Dispose(); ibBr.Dispose();
			for (int b = 0; b <= maxBracket; b++) brackets[b].Dispose();
		}
	}
}
