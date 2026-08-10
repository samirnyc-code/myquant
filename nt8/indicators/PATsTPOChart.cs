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

// PATsTPOChart — pure split-TPO chart for its own window (hide the candles).
// Each session is a profile column, laid left→right; parameter-based MERGE
// combines adjacent sessions into one cumulative-value-area column.
// Color schemes: Sierra (VA colored / rest gray), TimeGradient (blue early ->
// red late), Monochrome. Commit CS to: repo/nt8/indicators/PATsTPOChart.cs

namespace NinjaTrader.NinjaScript
{
	public enum TpoColorScheme { Sierra, TimeGradient, Monochrome }
}

namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsTPOChart : Indicator
	{
		private double rowSize;
		private List<int> sessionStarts;
		private string sig = "";
		private List<Col> cols;
		private List<Zone> zones;
		private int globalMaxBracket;

		private class Zone { public double Low, High; public int StartBar, EndBar, Age; public bool Filled; }

		private class Col
		{
			public int Start, End, MaxBracket;
			public string Label;
			public Dictionary<double, List<int>> Rows = new Dictionary<double, List<int>>();
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
		[NinjaScriptProperty] [Display(Name = "Color scheme", Order = 7, GroupName = "1 Profile")]
		public TpoColorScheme ColorScheme { get; set; }
		[NinjaScriptProperty] [Display(Name = "Auto-merge overlapping VAs", Order = 8, GroupName = "1 Profile")]
		public bool AutoMerge { get; set; }
		[NinjaScriptProperty] [Range(1, 100)] [Display(Name = "Auto-merge overlap %", Order = 9, GroupName = "1 Profile")]
		public double AutoMergeOverlapPct { get; set; }

		[NinjaScriptProperty] [Display(Name = "POC", Order = 0, GroupName = "2 Show")]
		public bool ShowPOC { get; set; }
		[NinjaScriptProperty] [Display(Name = "Single prints (excess)", Order = 1, GroupName = "2 Show")]
		public bool ShowSinglePrints { get; set; }
		[NinjaScriptProperty] [Display(Name = "Level lines (VAH/VAL/POC across session)", Order = 3, GroupName = "2 Show")]
		public bool ShowLevelLines { get; set; }

		[NinjaScriptProperty] [Display(Name = "Date + merged header", Order = 0, GroupName = "5 Labels")]
		public bool ShowDate { get; set; }
		[NinjaScriptProperty] [Display(Name = "VAH label", Order = 1, GroupName = "5 Labels")]
		public bool ShowVahLabel { get; set; }
		[NinjaScriptProperty] [Display(Name = "VAL label", Order = 2, GroupName = "5 Labels")]
		public bool ShowValLabel { get; set; }
		[NinjaScriptProperty] [Display(Name = "POC label", Order = 3, GroupName = "5 Labels")]
		public bool ShowPocLabel { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label name (VAH/VAL/POC text)", Order = 4, GroupName = "5 Labels")]
		public bool ShowLabelName { get; set; }
		[NinjaScriptProperty] [Display(Name = "Label price", Order = 5, GroupName = "5 Labels")]
		public bool ShowLabelPrice { get; set; }

		[NinjaScriptProperty] [Display(Name = "Forward single-print zones", Order = 0, GroupName = "6 SP Zones")]
		public bool ShowSpZones { get; set; }
		[NinjaScriptProperty] [Range(1, 20)] [Display(Name = "Min single-print run (rows)", Order = 1, GroupName = "6 SP Zones")]
		public int MinSingleRun { get; set; }
		[NinjaScriptProperty] [Range(0, 200)] [Display(Name = "Grey after N sessions", Order = 2, GroupName = "6 SP Zones")]
		public int GreyAfterSessions { get; set; }
		[NinjaScriptProperty] [Range(1, 200)] [Display(Name = "Drop after N sessions", Order = 3, GroupName = "6 SP Zones")]
		public int MaxForwardSessions { get; set; }
		[NinjaScriptProperty] [Display(Name = "Dim once filled", Order = 4, GroupName = "6 SP Zones")]
		public bool DimFilled { get; set; }
		[XmlIgnore] [Display(Name = "Recent SP-zone color", Order = 5, GroupName = "6 SP Zones")]
		public System.Windows.Media.Brush SpZoneColor { get; set; }
		[Browsable(false)] public string SpZoneColorSerialize { get { return Serialize.BrushToString(SpZoneColor); } set { SpZoneColor = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "Value area (Sierra)", Order = 0, GroupName = "3 Colors")]
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
		[XmlIgnore] [Display(Name = "Monochrome", Order = 4, GroupName = "3 Colors")]
		public System.Windows.Media.Brush MonoColor { get; set; }
		[Browsable(false)] public string MonoColorSerialize { get { return Serialize.BrushToString(MonoColor); } set { MonoColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Labels", Order = 5, GroupName = "3 Colors")]
		public System.Windows.Media.Brush LabelColor { get; set; }
		[Browsable(false)] public string LabelColorSerialize { get { return Serialize.BrushToString(LabelColor); } set { LabelColor = Serialize.StringToBrush(value); } }
		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "PATs TPO Chart (split/merge)";
				Description = "Pure TPO chart: split daily profiles with parameter merge for cumulative value areas. Own chart, candles hidden. Sierra / time-gradient / mono color schemes.";
				IsOverlay = true; IsChartOnly = true; DrawOnPricePanel = true; IsSuspendedWhileInactive = true;
				RowTicks = 1; BracketMinutes = 30; MaxProfiles = 15; BlockWidthPx = 6; ColumnGapPx = 16; LabelFontSize = 11;
				MergeGroups = ""; ColorScheme = TpoColorScheme.Sierra;
				AutoMerge = true; AutoMergeOverlapPct = 50;
				ShowPOC = true; ShowSinglePrints = true; ShowLevelLines = true;
				ShowDate = true; ShowVahLabel = true; ShowValLabel = true; ShowPocLabel = true;
				ShowLabelName = true; ShowLabelPrice = true;
				ShowSpZones = true; MinSingleRun = 2; GreyAfterSessions = 3; MaxForwardSessions = 20; DimFilled = true;
				SpZoneColor = System.Windows.Media.Brushes.Goldenrod;
				VaColor = System.Windows.Media.Brushes.DodgerBlue;
				RestColor = System.Windows.Media.Brushes.Gray;
				PocColor = System.Windows.Media.Brushes.Magenta;
				SingleColor = System.Windows.Media.Brushes.Goldenrod;
				MonoColor = System.Windows.Media.Brushes.SteelBlue;
				LabelColor = System.Windows.Media.Brushes.DimGray;
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
			foreach (string p in MergeGroups.Split(','))
			{
				string t = p.Trim();
				if (t.Length == 0) continue;
				int dash = t.IndexOf('-'); int a, b;
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
			cols = new List<Col>(); globalMaxBracket = 0;
			int sc = sessionStarts.Count;
			if (sc == 0) return;
			List<int[]> sess = new List<int[]>();
			for (int i = 0; i < sc; i++)
			{
				int st = sessionStarts[i];
				int en = (i + 1 < sc) ? sessionStarts[i + 1] - 1 : endBar;
				if (en >= st) sess.Add(new int[] { st, en });
			}
			int firstIdx = Math.Max(0, sess.Count - MaxProfiles);
			List<int[]> shown = sess.GetRange(firstIdx, sess.Count - firstIdx);
			int K = shown.Count;
			List<int[]> merges = AutoMerge ? AutoMergeRanges(shown) : ParseMerges();
			int idx = 1;
			while (idx <= K)
			{
				int rangeEnd = -1;
				foreach (int[] r in merges) if (idx >= r[0] && idx <= r[1]) { rangeEnd = Math.Min(r[1], K); break; }
				Col c = new Col();
				if (rangeEnd >= idx) { c.Start = shown[idx - 1][0]; c.End = shown[rangeEnd - 1][1]; c.Label = idx + "-" + rangeEnd; idx = rangeEnd + 1; }
				else { c.Start = shown[idx - 1][0]; c.End = shown[idx - 1][1]; c.Label = idx.ToString(); idx++; }
				BuildCol(c);
				if (c.MaxBracket > globalMaxBracket) globalMaxBracket = c.MaxBracket;
				cols.Add(c);
			}
			BuildZones(shown, endBar);
		}

		// Per-session single-print runs, projected forward; aged + fill-checked.
		private void BuildZones(List<int[]> shown, int endBar)
		{
			zones = new List<Zone>();
			if (!ShowSpZones) return;
			int K = shown.Count;
			for (int i = 0; i < K; i++)
			{
				Col t = new Col(); t.Start = shown[i][0]; t.End = shown[i][1]; BuildCol(t);
				if (t.Singles.Count == 0) continue;
				List<double> sp = new List<double>(t.Singles); sp.Sort();
				int a = 0;
				while (a < sp.Count)
				{
					int b = a;
					while (b + 1 < sp.Count && Math.Abs(sp[b + 1] - sp[b] - rowSize) < rowSize * 0.5) b++;
					int len = b - a + 1;
					if (len >= MinSingleRun)
					{
						Zone z = new Zone { Low = sp[a], High = sp[b], StartBar = t.Start, EndBar = t.End, Age = (K - 1) - i };
						double minLow = double.MaxValue, maxHigh = double.MinValue;
						for (int j = t.End + 1; j <= endBar; j++)
						{
							double l = Low.GetValueAt(j), h = High.GetValueAt(j);
							if (l < minLow) minLow = l;
							if (h > maxHigh) maxHigh = h;
						}
						z.Filled = (minLow < z.Low) && (maxHigh > z.High);   // price traded through it
						zones.Add(z);
					}
					a = b + 1;
				}
			}
		}

		// Auto-merge: chain consecutive sessions whose TPO value areas overlap >= pct.
		private List<int[]> AutoMergeRanges(List<int[]> shown)
		{
			int K = shown.Count;
			double[] vah = new double[K], val = new double[K];
			for (int i = 0; i < K; i++)
			{
				Col t = new Col(); t.Start = shown[i][0]; t.End = shown[i][1];
				BuildCol(t); vah[i] = t.Vah; val[i] = t.Val;
			}
			List<int[]> ranges = new List<int[]>();
			int a = 0;
			while (a < K)
			{
				int j = a;
				while (j + 1 < K && VaOverlap(val[j], vah[j], val[j + 1], vah[j + 1]) >= AutoMergeOverlapPct / 100.0) j++;
				if (j > a) ranges.Add(new int[] { a + 1, j + 1 });   // 1-based, only real merges
				a = j + 1;
			}
			return ranges;
		}

		private double VaOverlap(double a1, double a2, double b1, double b2)
		{
			if (double.IsNaN(a2) || double.IsNaN(b2)) return 0;
			double ov = Math.Min(a2, b2) - Math.Max(a1, b1);
			if (ov <= 0) return 0;
			double m = Math.Min(a2 - a1, b2 - b1);
			return m <= 0 ? 0 : ov / m;
		}

		private void BuildCol(Col c)
		{
			DateTime w = Time.GetValueAt(c.Start);
			for (int i = c.Start; i <= c.End; i++)
			{
				double h = High.GetValueAt(i), l = Low.GetValueAt(i);
				int bk = (int)((Time.GetValueAt(i) - w).TotalMinutes / BracketMinutes);
				if (bk < 0) bk = 0;
				if (bk > c.MaxBracket) c.MaxBracket = bk;
				double lo = Math.Floor(l / rowSize) * rowSize;
				for (double p = lo; p <= h + rowSize * 0.5; p += rowSize)
				{
					double key = Math.Round(p, 5);
					List<int> lst;
					if (!c.Rows.TryGetValue(key, out lst)) { lst = new List<int>(); c.Rows[key] = lst; }
					if (!lst.Contains(bk)) lst.Add(bk);
				}
			}
			Dictionary<double, double> cnt = new Dictionary<double, double>();
			foreach (KeyValuePair<double, List<int>> kv in c.Rows)
			{
				kv.Value.Sort();
				double n = kv.Value.Count;
				cnt[kv.Key] = n;
				if (n > c.MaxCount) { c.MaxCount = n; c.Poc = kv.Key; }
				if (n == 1) c.Singles.Add(kv.Key);
			}
			List<double> prices = new List<double>(cnt.Keys); prices.Sort();
			int np = prices.Count;
			if (np == 0 || double.IsNaN(c.Poc)) return;
			int pocI = prices.IndexOf(c.Poc); if (pocI < 0) pocI = 0;
			double total = 0; foreach (double v in cnt.Values) total += v;
			double target = 0.70 * total; double acc = cnt[prices[pocI]];
			int lo2 = pocI, hi = pocI;
			while (acc < target && (lo2 > 0 || hi < np - 1))
			{
				double up = (hi + 1 < np ? cnt[prices[hi + 1]] : 0) + (hi + 2 < np ? cnt[prices[hi + 2]] : 0);
				double dn = (lo2 - 1 >= 0 ? cnt[prices[lo2 - 1]] : 0) + (lo2 - 2 >= 0 ? cnt[prices[lo2 - 2]] : 0);
				bool upok = hi < np - 1, dnok = lo2 > 0;
				if (upok && (up >= dn || !dnok)) for (int k = 0; k < 2 && hi < np - 1; k++) { hi++; acc += cnt[prices[hi]]; }
				else if (dnok) for (int k = 0; k < 2 && lo2 > 0; k++) { lo2--; acc += cnt[prices[lo2]]; }
				else break;
			}
			c.Val = prices[lo2]; c.Vah = prices[hi];
		}
		#endregion

		private SharpDX.Color4 Dx(System.Windows.Media.Brush b, float a)
		{
			System.Windows.Media.SolidColorBrush s = b as System.Windows.Media.SolidColorBrush;
			if (s == null) return new SharpDX.Color4(0.6f, 0.6f, 0.6f, a);
			System.Windows.Media.Color c = s.Color;
			return new SharpDX.Color4(c.R / 255f, c.G / 255f, c.B / 255f, a);
		}

		private SharpDX.Color4 Gradient(int b, int maxB)
		{
			double t = maxB <= 0 ? 0.0 : (double)b / maxB;
			float r, g, bl, u;
			if (t < 0.25) { u = (float)(t / 0.25); r = 0.20f; g = 0.30f + 0.40f * u; bl = 0.90f; }
			else if (t < 0.50) { u = (float)((t - 0.25) / 0.25); r = 0.20f; g = 0.70f + 0.20f * u; bl = 0.90f - 0.60f * u; }
			else if (t < 0.75) { u = (float)((t - 0.50) / 0.25); r = 0.20f + 0.70f * u; g = 0.90f; bl = 0.30f - 0.30f * u; }
			else { u = (float)((t - 0.75) / 0.25); r = 0.90f; g = 0.90f - 0.60f * u; bl = 0.10f; }
			return new SharpDX.Color4(r, g, bl, 0.95f);
		}

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (sessionStarts == null || RenderTarget == null || Bars == null) return;
			int endBar = Bars.Count - 1;
			if (endBar < 0) return;
			string s = endBar + "|" + MaxProfiles + "|" + RowTicks + "|" + BracketMinutes + "|" + MergeGroups + "|" + AutoMerge + "|" + AutoMergeOverlapPct + "|" + ShowSpZones + "|" + MinSingleRun;
			if (s != sig || cols == null) { Recompute(endBar); sig = s; }
			if (cols == null || cols.Count == 0) return;

			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f) rowH = 1f;
			int nc = cols.Count;

			SolidColorBrush vaBr = new SolidColorBrush(RenderTarget, Dx(VaColor, 0.95f));
			SolidColorBrush restBr = new SolidColorBrush(RenderTarget, Dx(RestColor, 0.9f));
			SolidColorBrush pocBr = new SolidColorBrush(RenderTarget, Dx(PocColor, 0.95f));
			SolidColorBrush singleBr = new SolidColorBrush(RenderTarget, Dx(SingleColor, 0.95f));
			SolidColorBrush monoBr = new SolidColorBrush(RenderTarget, Dx(MonoColor, 0.95f));
			SolidColorBrush monoFaint = new SolidColorBrush(RenderTarget, Dx(MonoColor, 0.4f));
			SolidColorBrush labelBr = new SolidColorBrush(RenderTarget, Dx(LabelColor, 0.95f));
			SolidColorBrush[] grad = new SolidColorBrush[globalMaxBracket + 1];
			for (int b = 0; b <= globalMaxBracket; b++) grad[b] = new SolidColorBrush(RenderTarget, Gradient(b, globalMaxBracket));
			SolidColorBrush spRecent = new SolidColorBrush(RenderTarget, Dx(SpZoneColor, 0.22f));
			SolidColorBrush spGrey = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.5f, 0.5f, 0.5f, 0.13f));
			SolidColorBrush spFilled = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.5f, 0.5f, 0.5f, 0.05f));
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);

			// forward single-print zones (drawn behind the profiles)
			if (ShowSpZones && zones != null)
			{
				foreach (Zone z in zones)
				{
					if (z.Age > MaxForwardSessions) continue;
					if (z.Filled && !DimFilled) continue;
					float zx0 = chartControl.GetXByBarIndex(ChartBars, z.StartBar);   // begin in the session that made the excess
					float zx1 = chartControl.GetXByBarIndex(ChartBars, endBar);
					if (zx1 <= zx0) continue;
					float zy1 = chartScale.GetYByValue(z.High), zy2 = chartScale.GetYByValue(z.Low);
					SolidColorBrush zb = z.Filled ? spFilled : (z.Age > GreyAfterSessions ? spGrey : spRecent);
					RenderTarget.FillRectangle(new SharpDX.RectangleF(zx0, Math.Min(zy1, zy2), zx1 - zx0, Math.Abs(zy2 - zy1) + 1f), zb);
				}
			}

			for (int ci = 0; ci < nc; ci++)
			{
				Col c = cols[ci];
				if (c.Rows.Count == 0 || c.MaxCount <= 0) continue;
				// anchor to the session's real bar position so it moves/scales with the time axis
				float colX = chartControl.GetXByBarIndex(ChartBars, c.Start);
				float colEndX = chartControl.GetXByBarIndex(ChartBars, c.End);
				float sessW = Math.Max(colEndX - colX - ColumnGapPx, 8f);
				float lblW = Math.Max(sessW, 90f);
				float bw = Math.Min((float)BlockWidthPx, sessW / (float)Math.Max(1.0, c.MaxCount));
				if (bw < 1f) bw = 1f;
				float topY = float.MaxValue;

				foreach (KeyValuePair<double, List<int>> kv in c.Rows)
				{
					double price = kv.Key;
					List<int> brs = kv.Value;
					float yTop = chartScale.GetYByValue(price + rowSize);
					if (yTop < topY) topY = yTop;
					bool inVA = !double.IsNaN(c.Vah) && price <= c.Vah + 1e-9 && price >= c.Val - 1e-9;
					bool isPoc = ShowPOC && price == c.Poc;
					bool isSingle = ShowSinglePrints && brs.Count == 1;
					for (int k = 0; k < brs.Count; k++)
					{
						SolidColorBrush br;
						if (ColorScheme == TpoColorScheme.TimeGradient) br = grad[brs[k]];
						else if (ColorScheme == TpoColorScheme.Monochrome) br = inVA ? monoBr : monoFaint;
						else br = isPoc ? pocBr : (isSingle ? singleBr : (inVA ? vaBr : restBr)); // Sierra
						RenderTarget.FillRectangle(new SharpDX.RectangleF(colX + k * bw, yTop, Math.Max(1f, bw - 0.5f), Math.Max(1f, rowH)), br);
					}
				}

				// level lines across the session (start -> end)
				if (ShowLevelLines && !double.IsNaN(c.Vah))
				{
					float yv1 = chartScale.GetYByValue(c.Vah), yv2 = chartScale.GetYByValue(c.Val), yp = chartScale.GetYByValue(c.Poc);
					RenderTarget.DrawLine(new SharpDX.Vector2(colX, yv1), new SharpDX.Vector2(colEndX, yv1), vaBr, 1f);
					RenderTarget.DrawLine(new SharpDX.Vector2(colX, yv2), new SharpDX.Vector2(colEndX, yv2), vaBr, 1f);
					RenderTarget.DrawLine(new SharpDX.Vector2(colX, yp), new SharpDX.Vector2(colEndX, yp), pocBr, 1.4f);
				}

				// labels sit to the RIGHT of the profile blocks, ABOVE each level line
				float labelX = colX + (float)c.MaxCount * bw + 5f;
				float lh = LabelFontSize + 3f;
				bool merged = c.Label.IndexOf('-') > 0;
				if (ShowDate)
				{
					string head;
					if (merged)
					{
						string[] pp = c.Label.Split('-'); int aa, bb, days = 0;
						if (int.TryParse(pp[0], out aa) && int.TryParse(pp[1], out bb)) days = bb - aa + 1;
						head = "MERGED " + Time.GetValueAt(c.Start).ToString("MM-dd") + "→" + Time.GetValueAt(c.End).ToString("MM-dd") + " (" + days + "d)";
						RenderTarget.DrawLine(new SharpDX.Vector2(colX, topY - (lh + 3f)), new SharpDX.Vector2(colEndX, topY - (lh + 3f)), labelBr, 1f);   // neutral span marker, not a level
					}
					else head = c.Label + "  " + Time.GetValueAt(c.End).ToString("MM-dd");
					RenderTarget.DrawText(head, tf, new SharpDX.RectangleF(colX, topY - (lh + 2f), lblW, lh), merged ? pocBr : labelBr);
				}
				if (!double.IsNaN(c.Vah))
				{
					if (ShowVahLabel) { string t = (ShowLabelName ? "VAH " : "") + (ShowLabelPrice ? c.Vah.ToString("0.##") : ""); if (t.Length > 0) RenderTarget.DrawText(t, tf, new SharpDX.RectangleF(labelX, chartScale.GetYByValue(c.Vah) - lh, 90f, lh), labelBr); }
					if (ShowValLabel) { string t = (ShowLabelName ? "VAL " : "") + (ShowLabelPrice ? c.Val.ToString("0.##") : ""); if (t.Length > 0) RenderTarget.DrawText(t, tf, new SharpDX.RectangleF(labelX, chartScale.GetYByValue(c.Val) - lh, 90f, lh), labelBr); }
					if (ShowPocLabel) { string t = (ShowLabelName ? "POC " : "") + (ShowLabelPrice ? c.Poc.ToString("0.##") : ""); if (t.Length > 0) RenderTarget.DrawText(t, tf, new SharpDX.RectangleF(labelX, chartScale.GetYByValue(c.Poc) - lh, 90f, lh), pocBr); }
				}
			}

			vaBr.Dispose(); restBr.Dispose(); pocBr.Dispose(); singleBr.Dispose(); monoBr.Dispose(); monoFaint.Dispose(); labelBr.Dispose();
			spRecent.Dispose(); spGrey.Dispose(); spFilled.Dispose();
			for (int b = 0; b <= globalMaxBracket; b++) grad[b].Dispose();
			tf.Dispose();
		}
	}
}
