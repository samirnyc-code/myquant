#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

// ─────────────────────────────────────────────────────────────────────────────
// PATsTPOChart — a "pure TPO chart" for its OWN chart window (hide the candles):
// each session drawn as its own profile COLUMN, laid out left→right, Sierra
// style — value area in blue, the rest in gray. Parameter-based MERGE combines
// adjacent sessions into one column showing the cumulative value area (the map
// that governs a multi-day swing). POC highlighted; VAH/VAL/POC labeled per
// column; single prints (excess) optionally marked.
//
// Usage: put on a fresh chart, hide the price bars (Chart Style → set the bar
// colors to transparent, or use a wide time frame). Set "Max profiles" and, to
// merge, e.g. Merge groups = "3-6,10-12" (1-based, left→right of what's shown).
//
// Commit CS to: repo/nt8/indicators/PATsTPOChart.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsTPOChart : Indicator
	{
		private double rowSize;
		private List<int> sessionStarts;
		private string sig = "";
		private List<Col> cols;

		private class Col
		{
			public int Start, End;
			public string Label;
			public Dictionary<double, double> Tpo = new Dictionary<double, double>();
			public double Poc = double.NaN, Vah = double.NaN, Val = double.NaN, MaxCount = 0;
			public HashSet<double> Singles = new HashSet<double>();
		}

		#region Parameters
		[NinjaScriptProperty] [Range(1, int.MaxValue)] [Display(Name = "Row height (ticks)", Order = 0, GroupName = "1 Profile")]
		public int RowTicks { get; set; }
		[NinjaScriptProperty] [Range(1, int.MaxValue)] [Display(Name = "Bracket minutes", Order = 1, GroupName = "1 Profile")]
		public int BracketMinutes { get; set; }
		[NinjaScriptProperty] [Range(1, 200)] [Display(Name = "Max profiles (last N sessions)", Order = 2, GroupName = "1 Profile")]
		public int MaxProfiles { get; set; }
		[NinjaScriptProperty] [Range(1, 40)] [Display(Name = "Block width (px)", Order = 3, GroupName = "1 Profile")]
		public int BlockWidthPx { get; set; }
		[NinjaScriptProperty] [Range(0, 60)] [Display(Name = "Column gap (px)", Order = 4, GroupName = "1 Profile")]
		public int ColumnGapPx { get; set; }
		[NinjaScriptProperty] [Range(6, 24)] [Display(Name = "Label font size", Order = 5, GroupName = "1 Profile")]
		public int LabelFontSize { get; set; }
		[NinjaScriptProperty] [Display(Name = "Merge groups (e.g. 3-6,10-12)", Order = 6, GroupName = "1 Profile")]
		public string MergeGroups { get; set; }

		[NinjaScriptProperty] [Display(Name = "POC", Order = 0, GroupName = "2 Show")]
		public bool ShowPOC { get; set; }
		[NinjaScriptProperty] [Display(Name = "Single prints (excess)", Order = 1, GroupName = "2 Show")]
		public bool ShowSinglePrints { get; set; }
		[NinjaScriptProperty] [Display(Name = "Labels (date + VAH/VAL/POC)", Order = 2, GroupName = "2 Show")]
		public bool ShowLabels { get; set; }

		[XmlIgnore] [Display(Name = "Value area", Order = 0, GroupName = "3 Colors")]
		public System.Windows.Media.Brush VaColor { get; set; }
		[Browsable(false)] public string VaColorSerialize { get { return Serialize.BrushToString(VaColor); } set { VaColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Rest of profile", Order = 1, GroupName = "3 Colors")]
		public System.Windows.Media.Brush RestColor { get; set; }
		[Browsable(false)] public string RestColorSerialize { get { return Serialize.BrushToString(RestColor); } set { RestColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "POC", Order = 2, GroupName = "3 Colors")]
		public System.Windows.Media.Brush PocColor { get; set; }
		[Browsable(false)] public string PocColorSerialize { get { return Serialize.BrushToString(PocColor); } set { PocColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Single prints", Order = 3, GroupName = "3 Colors")]
		public System.Windows.Media.Brush SingleColor { get; set; }
		[Browsable(false)] public string SingleColorSerialize { get { return Serialize.BrushToString(SingleColor); } set { SingleColor = Serialize.StringToBrush(value); } }
		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "PATs TPO Chart (split/merge)";
				Description = "Pure TPO chart: split daily profiles (VA blue / rest gray) with parameter-based merge for cumulative value areas. Put on its own chart with candles hidden.";
				IsOverlay = true; IsChartOnly = true; DrawOnPricePanel = true; IsSuspendedWhileInactive = true;
				RowTicks = 1; BracketMinutes = 30; MaxProfiles = 15; BlockWidthPx = 6; ColumnGapPx = 14; LabelFontSize = 11;
				MergeGroups = "";
				ShowPOC = true; ShowSinglePrints = true; ShowLabels = true;
				VaColor = System.Windows.Media.Brushes.DodgerBlue;
				RestColor = System.Windows.Media.Brushes.Gainsboro;
				PocColor = System.Windows.Media.Brushes.Magenta;
				SingleColor = System.Windows.Media.Brushes.Goldenrod;
			}
			else if (State == State.Configure) { rowSize = RowTicks * TickSize; }
			else if (State == State.DataLoaded) { sessionStarts = new List<int>(); }
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0) return;
			if (rowSize <= 0) rowSize = RowTicks * TickSize;
			if (CurrentBar == 0 || Bars.IsFirstBarOfSession) sessionStarts.Add(CurrentBar);
		}

		#region Build
		private List<int[]> ParseMerges()
		{
			List<int[]> ranges = new List<int[]>();
			if (string.IsNullOrEmpty(MergeGroups)) return ranges;
			string[] parts = MergeGroups.Split(',');
			foreach (string p in parts)
			{
				string t = p.Trim();
				if (t.Length == 0) continue;
				int dash = t.IndexOf('-');
				int a, b;
				if (dash > 0)
				{
					if (int.TryParse(t.Substring(0, dash).Trim(), out a) && int.TryParse(t.Substring(dash + 1).Trim(), out b) && b >= a)
						ranges.Add(new int[] { a, b });
				}
				else if (int.TryParse(t, out a)) ranges.Add(new int[] { a, a });
			}
			return ranges;
		}

		private void Recompute(int endBar)
		{
			cols = new List<Col>();
			int sc = sessionStarts.Count;
			if (sc == 0) return;
			// chronological session (start,end)
			List<int[]> sess = new List<int[]>();
			for (int i = 0; i < sc; i++)
			{
				int st = sessionStarts[i];
				int en = (i + 1 < sc) ? sessionStarts[i + 1] - 1 : endBar;
				if (en >= st) sess.Add(new int[] { st, en });
			}
			int first = Math.Max(0, sess.Count - MaxProfiles);
			List<int[]> shown = sess.GetRange(first, sess.Count - first);   // oldest..newest
			int K = shown.Count;
			List<int[]> merges = ParseMerges();

			int idx = 1;   // 1-based over shown
			while (idx <= K)
			{
				int rangeEnd = -1;
				foreach (int[] r in merges) if (idx >= r[0] && idx <= r[1]) { rangeEnd = Math.Min(r[1], K); break; }
				Col c = new Col();
				if (rangeEnd >= idx)
				{
					c.Start = shown[idx - 1][0]; c.End = shown[rangeEnd - 1][1];
					c.Label = idx + "-" + rangeEnd;
					idx = rangeEnd + 1;
				}
				else { c.Start = shown[idx - 1][0]; c.End = shown[idx - 1][1]; c.Label = idx.ToString(); idx++; }
				BuildCol(c);
				cols.Add(c);
			}
		}

		private void BuildCol(Col c)
		{
			Dictionary<double, HashSet<int>> br = new Dictionary<double, HashSet<int>>();
			DateTime w = Time.GetValueAt(c.Start);
			for (int i = c.Start; i <= c.End; i++)
			{
				double h = High.GetValueAt(i), l = Low.GetValueAt(i);
				int bk = (int)((Time.GetValueAt(i) - w).TotalMinutes / BracketMinutes);
				if (bk < 0) bk = 0;
				double lo = Math.Floor(l / rowSize) * rowSize;
				for (double p = lo; p <= h + rowSize * 0.5; p += rowSize)
				{
					double key = Math.Round(p, 5);
					HashSet<int> set;
					if (!br.TryGetValue(key, out set)) { set = new HashSet<int>(); br[key] = set; }
					set.Add(bk);
				}
			}
			foreach (KeyValuePair<double, HashSet<int>> kv in br)
			{
				double cnt = kv.Value.Count;
				c.Tpo[kv.Key] = cnt;
				if (cnt > c.MaxCount) { c.MaxCount = cnt; c.Poc = kv.Key; }
				if (cnt == 1) c.Singles.Add(kv.Key);
			}
			// TPO value area (two-at-a-time to 70%)
			List<double> prices = new List<double>(c.Tpo.Keys); prices.Sort();
			int n = prices.Count;
			if (n == 0 || double.IsNaN(c.Poc)) return;
			int pocI = prices.IndexOf(c.Poc); if (pocI < 0) pocI = 0;
			double total = 0; foreach (double v in c.Tpo.Values) total += v;
			double target = 0.70 * total; double acc = c.Tpo[prices[pocI]];
			int lo2 = pocI, hi = pocI;
			while (acc < target && (lo2 > 0 || hi < n - 1))
			{
				double up = (hi + 1 < n ? c.Tpo[prices[hi + 1]] : 0) + (hi + 2 < n ? c.Tpo[prices[hi + 2]] : 0);
				double dn = (lo2 - 1 >= 0 ? c.Tpo[prices[lo2 - 1]] : 0) + (lo2 - 2 >= 0 ? c.Tpo[prices[lo2 - 2]] : 0);
				bool upok = hi < n - 1, dnok = lo2 > 0;
				if (upok && (up >= dn || !dnok)) for (int k = 0; k < 2 && hi < n - 1; k++) { hi++; acc += c.Tpo[prices[hi]]; }
				else if (dnok) for (int k = 0; k < 2 && lo2 > 0; k++) { lo2--; acc += c.Tpo[prices[lo2]]; }
				else break;
			}
			c.Val = prices[lo2]; c.Vah = prices[hi];
		}
		#endregion

		private SharpDX.Color4 Dx(System.Windows.Media.Brush b, float a)
		{
			System.Windows.Media.SolidColorBrush s = b as System.Windows.Media.SolidColorBrush;
			if (s == null) return new SharpDX.Color4(0.7f, 0.7f, 0.7f, a);
			System.Windows.Media.Color c = s.Color;
			return new SharpDX.Color4(c.R / 255f, c.G / 255f, c.B / 255f, a);
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (sessionStarts == null || RenderTarget == null || Bars == null) return;
			int endBar = Bars.Count - 1;
			if (endBar < 0) return;
			string s = endBar + "|" + MaxProfiles + "|" + RowTicks + "|" + BracketMinutes + "|" + MergeGroups;
			if (s != sig || cols == null) { Recompute(endBar); sig = s; }
			if (cols == null || cols.Count == 0) return;

			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f) rowH = 1f;
			float left = (float)ChartPanel.X + 6f;
			float avail = (float)ChartPanel.W - 12f;
			int nc = cols.Count;
			float slotW = avail / nc;

			SolidColorBrush vaBr = new SolidColorBrush(RenderTarget, Dx(VaColor, 0.95f));
			SolidColorBrush restBr = new SolidColorBrush(RenderTarget, Dx(RestColor, 0.9f));
			SolidColorBrush pocBr = new SolidColorBrush(RenderTarget, Dx(PocColor, 0.95f));
			SolidColorBrush singleBr = new SolidColorBrush(RenderTarget, Dx(SingleColor, 0.95f));
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);

			for (int ci = 0; ci < nc; ci++)
			{
				Col c = cols[ci];
				if (c.Tpo.Count == 0 || c.MaxCount <= 0) continue;
				float colX = left + ci * slotW;
				float bw = Math.Min((float)BlockWidthPx, (slotW - ColumnGapPx) / (float)Math.Max(1.0, c.MaxCount));
				if (bw < 1f) bw = 1f;
				float topY = float.MaxValue;

				foreach (KeyValuePair<double, double> kv in c.Tpo)
				{
					double price = kv.Key;
					float yTop = chartScale.GetYByValue(price + rowSize);
					if (yTop < topY) topY = yTop;
					int count = (int)kv.Value;
					bool inVA = !double.IsNaN(c.Vah) && price <= c.Vah + 1e-9 && price >= c.Val - 1e-9;
					bool isPoc = ShowPOC && price == c.Poc;
					bool isSingle = ShowSinglePrints && c.Singles.Contains(price);
					SolidColorBrush br = isPoc ? pocBr : (isSingle ? singleBr : (inVA ? vaBr : restBr));
					for (int k = 0; k < count; k++)
						RenderTarget.FillRectangle(new SharpDX.RectangleF(colX + k * bw, yTop, bw - 0.5f, rowH - 0.5f), br);
				}

				if (ShowLabels)
				{
					string date = Time.GetValueAt(c.End).ToString("MM-dd");
					string head = c.Label + "  " + date;
					RenderTarget.DrawText(head, tf, new SharpDX.RectangleF(colX, topY - (LabelFontSize + 4f), slotW, LabelFontSize + 4f), restBr);
					if (!double.IsNaN(c.Vah))
					{
						RenderTarget.DrawText("VAH " + c.Vah.ToString("0.##"), tf, new SharpDX.RectangleF(colX, chartScale.GetYByValue(c.Vah) - LabelFontSize, slotW, LabelFontSize + 3f), vaBr);
						RenderTarget.DrawText("VAL " + c.Val.ToString("0.##"), tf, new SharpDX.RectangleF(colX, chartScale.GetYByValue(c.Val), slotW, LabelFontSize + 3f), vaBr);
						if (ShowPOC) RenderTarget.DrawText("POC " + c.Poc.ToString("0.##"), tf, new SharpDX.RectangleF(colX, chartScale.GetYByValue(c.Poc) - LabelFontSize * 0.5f, slotW, LabelFontSize + 3f), pocBr);
					}
				}
			}

			vaBr.Dispose(); restBr.Dispose(); pocBr.Dispose(); singleBr.Dispose(); tf.Dispose();
		}
	}
}
