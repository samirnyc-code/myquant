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
// PATsProfile — right-margin TPO (Market Profile) + Volume Profile with the full
// Dalton toolkit, drawn OUTWARD from the last bar so price action is never
// covered. Every level/band/node is individually toggleable and colorable.
//
//   Volume Profile : POC, 70% value area (MOM Appendix 1, two-at-a-time),
//                    value-area band OR lines-only, HVN / LVN nodes,
//                    initial balance, prior-session value (trade-from zone).
//   TPO            : colored blocks (blue early -> red late), single prints
//                    (excess), and VAH/VAL/POC only — no nodes.
//   Labels         : numeric VAH/VAL/POC (current + prior), de-collided with
//                    leader lines so text never overlaps a line or another label.
//   Composite      : merge the last N sessions into one profile.
// Every band/line stops at its own session's left break.
//
// Commit CS to: repo/nt8/indicators/PATsProfile.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsProfile : Indicator
	{
		private double rowSize;
		private List<int> sessionStarts;

		private string sig = "";
		private Dictionary<double, double> volByRow;
		private Dictionary<double, List<int>> tpoByRow;
		private List<double> hvn, lvn, singlePrints;
		private double poc, vah, val, ibh, ibl, maxVol;
		private double pPoc = double.NaN, pVah = double.NaN, pVal = double.NaN;
		private int maxBracket, winStartBar, priorStartBar = -1;

		#region Parameters
		[NinjaScriptProperty] [Range(1, int.MaxValue)] [Display(Name = "Row height (ticks)", Order = 0, GroupName = "1 Profile")]
		public int RowTicks { get; set; }
		[NinjaScriptProperty] [Range(1, int.MaxValue)] [Display(Name = "Bracket minutes", Order = 1, GroupName = "1 Profile")]
		public int BracketMinutes { get; set; }
		[NinjaScriptProperty] [Range(1, 60)] [Display(Name = "Composite sessions (1 = today)", Order = 2, GroupName = "1 Profile")]
		public int CompositeSessions { get; set; }
		[NinjaScriptProperty] [Range(20, 800)] [Display(Name = "VP width (px)", Order = 3, GroupName = "1 Profile")]
		public int VpWidthPx { get; set; }
		[NinjaScriptProperty] [Range(2, 40)] [Display(Name = "TPO block width (px)", Order = 4, GroupName = "1 Profile")]
		public int BlockWidthPx { get; set; }
		[NinjaScriptProperty] [Range(0, 800)] [Display(Name = "Right offset (px)", Order = 5, GroupName = "1 Profile")]
		public int RightOffsetPx { get; set; }
		[NinjaScriptProperty] [Range(0.05, 1.0)] [Display(Name = "Opacity", Order = 6, GroupName = "1 Profile")]
		public double Opacity { get; set; }
		[NinjaScriptProperty] [Range(6, 24)] [Display(Name = "Label font size", Order = 7, GroupName = "1 Profile")]
		public int LabelFontSize { get; set; }

		[NinjaScriptProperty] [Display(Name = "TPO blocks", Order = 0, GroupName = "2 Show")]
		public bool ShowTPO { get; set; }
		[NinjaScriptProperty] [Display(Name = "Volume Profile", Order = 1, GroupName = "2 Show")]
		public bool ShowVP { get; set; }
		[NinjaScriptProperty] [Display(Name = "VAH / VAL lines", Order = 2, GroupName = "2 Show")]
		public bool ShowVAHVAL { get; set; }
		[NinjaScriptProperty] [Display(Name = "Value-area band (shaded)", Order = 3, GroupName = "2 Show")]
		public bool ShowVABand { get; set; }
		[NinjaScriptProperty] [Display(Name = "POC", Order = 4, GroupName = "2 Show")]
		public bool ShowPOC { get; set; }
		[NinjaScriptProperty] [Display(Name = "Initial balance", Order = 5, GroupName = "2 Show")]
		public bool ShowIB { get; set; }
		[NinjaScriptProperty] [Display(Name = "HVN (high-volume nodes)", Order = 6, GroupName = "2 Show")]
		public bool ShowHVN { get; set; }
		[NinjaScriptProperty] [Display(Name = "LVN (low-volume nodes)", Order = 7, GroupName = "2 Show")]
		public bool ShowLVN { get; set; }
		[NinjaScriptProperty] [Display(Name = "Single prints (excess)", Order = 8, GroupName = "2 Show")]
		public bool ShowSinglePrints { get; set; }
		[NinjaScriptProperty] [Display(Name = "Prior-session lines", Order = 9, GroupName = "2 Show")]
		public bool ShowPriorLines { get; set; }
		[NinjaScriptProperty] [Display(Name = "Prior-session band (trade-from zone)", Order = 10, GroupName = "2 Show")]
		public bool ShowPriorBand { get; set; }
		[NinjaScriptProperty] [Display(Name = "Labels", Order = 11, GroupName = "2 Show")]
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
		[XmlIgnore] [Display(Name = "Single prints", Order = 6, GroupName = "4 Colors")]
		public System.Windows.Media.Brush SinglePrintColor { get; set; }
		[Browsable(false)] public string SinglePrintColorSerialize { get { return Serialize.BrushToString(SinglePrintColor); } set { SinglePrintColor = Serialize.StringToBrush(value); } }
		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "PATs Profile (TPO+VP)";
				Description = "Right-margin TPO + Volume Profile: POC, value area, HVN/LVN, single prints, initial balance, prior-session zone, labels, composite.";
				IsOverlay = true; IsChartOnly = true; DrawOnPricePanel = true; IsSuspendedWhileInactive = true;
				RowTicks = 4; BracketMinutes = 30; CompositeSessions = 1; VpWidthPx = 150; BlockWidthPx = 7; RightOffsetPx = 6;
				Opacity = 0.85; LabelFontSize = 11;
				ShowTPO = true; ShowVP = true; ShowVAHVAL = true; ShowVABand = true; ShowPOC = true; ShowIB = true;
				ShowHVN = true; ShowLVN = true; ShowSinglePrints = true; ShowPriorLines = true; ShowPriorBand = true; ShowLabels = true;
				NodeLookback = 4; HvnFactor = 1.2; LvnFactor = 0.7;
				PocColor = System.Windows.Media.Brushes.Orange;
				VaColor = System.Windows.Media.Brushes.MediumPurple;
				PriorColor = System.Windows.Media.Brushes.SteelBlue;
				HvnColor = System.Windows.Media.Brushes.DarkTurquoise;
				LvnColor = System.Windows.Media.Brushes.IndianRed;
				IbColor = System.Windows.Media.Brushes.Goldenrod;
				SinglePrintColor = System.Windows.Media.Brushes.White;
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

		#region Computation
		private void Recompute(int endBar)
		{
			volByRow = new Dictionary<double, double>();
			tpoByRow = new Dictionary<double, List<int>>();
			int sc = sessionStarts.Count;
			int wIdx = Math.Max(0, sc - Math.Max(1, CompositeSessions));
			int startBar = sc > 0 ? sessionStarts[wIdx] : 0;
			winStartBar = startBar;
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
				if (i >= lastStart && t < lastSess.AddMinutes(60)) { if (h > ibh) ibh = h; if (l < ibl) ibl = l; }
			}

			poc = double.NaN; maxVol = 0;
			foreach (KeyValuePair<double, double> kv in volByRow)
				if (kv.Value > maxVol) { maxVol = kv.Value; poc = kv.Key; }
			ValueAreaOf(volByRow, poc, out val, out vah);
			ComputeNodes();
			ComputeSinglePrints();
			ComputePriorLevels();
		}

		private Dictionary<double, double> BuildVolume(int a, int b, out double pocOut)
		{
			Dictionary<double, double> vol = new Dictionary<double, double>();
			for (int i = a; i <= b; i++)
			{
				double h = High.GetValueAt(i), l = Low.GetValueAt(i), v = Volume.GetValueAt(i);
				double lo = Math.Floor(l / rowSize) * rowSize;
				int nrows = 0;
				for (double p = lo; p <= h + rowSize * 0.5; p += rowSize) nrows++;
				if (nrows < 1) nrows = 1;
				double vShare = v / nrows;
				for (double p = lo; p <= h + rowSize * 0.5; p += rowSize)
				{
					double key = Math.Round(p, 5);
					double cv; vol.TryGetValue(key, out cv); vol[key] = cv + vShare;
				}
			}
			pocOut = double.NaN; double mv = 0;
			foreach (KeyValuePair<double, double> kv in vol) if (kv.Value > mv) { mv = kv.Value; pocOut = kv.Key; }
			return vol;
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
				if (isMax && v >= avg * HvnFactor) hvn.Add(prices[i]);
				if (isMin && v <= avg * LvnFactor) lvn.Add(prices[i]);
			}
		}

		private void ComputeSinglePrints()
		{
			singlePrints = new List<double>();
			foreach (KeyValuePair<double, List<int>> kv in tpoByRow)
				if (kv.Value.Count == 1) singlePrints.Add(kv.Key);
		}

		private void ComputePriorLevels()
		{
			pPoc = pVah = pVal = double.NaN; priorStartBar = -1;
			int sc = sessionStarts.Count;
			if (sc < 2) return;
			int ps = sessionStarts[sc - 2];
			int pe = sessionStarts[sc - 1] - 1;
			if (pe < ps) return;
			priorStartBar = ps;
			double ppoc;
			Dictionary<double, double> pvol = BuildVolume(ps, pe, out ppoc);
			pPoc = ppoc;
			ValueAreaOf(pvol, pPoc, out pVal, out pVah);
		}
		#endregion

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

		private SharpDX.Color4 Dx(System.Windows.Media.Brush b, float alpha)
		{
			System.Windows.Media.SolidColorBrush scb = b as System.Windows.Media.SolidColorBrush;
			if (scb == null) return new SharpDX.Color4(0.6f, 0.6f, 0.6f, alpha);
			System.Windows.Media.Color c = scb.Color;
			return new SharpDX.Color4(c.R / 255f, c.G / 255f, c.B / 255f, alpha);
		}

		private class Lbl { public float y; public string text; public SolidColorBrush brush; public float trueY; }

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (sessionStarts == null || RenderTarget == null || ChartBars == null || Bars == null) return;
			int endBar = Bars.Count - 1;
			if (endBar < 0) return;
			string s = endBar + "|" + CompositeSessions + "|" + RowTicks + "|" + BracketMinutes + "|" + NodeLookback + "|" + HvnFactor + "|" + LvnFactor;
			if (s != sig || volByRow == null) { Recompute(endBar); sig = s; }
			if (volByRow == null || volByRow.Count == 0 || maxVol <= 0) return;

			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f) rowH = 1f;
			float panelLeft = (float)ChartPanel.X;
			float winStartX = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, winStartBar));
			float priorStartX = priorStartBar >= 0 ? Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, priorStartBar)) : panelLeft;
			float vpLeft = chartControl.GetXByBarIndex(ChartBars, endBar) + RightOffsetPx;
			float vpMaxRight = vpLeft + VpWidthPx;
			float tpoLeft = vpMaxRight + 10f;

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
			SolidColorBrush spBr = new SolidColorBrush(RenderTarget, Dx(SinglePrintColor, 0.95f));
			SolidColorBrush[] brackets = new SolidColorBrush[maxBracket + 1];
			for (int b = 0; b <= maxBracket; b++) brackets[b] = new SolidColorBrush(RenderTarget, BracketColor(b, maxBracket));
			HashSet<double> hvnSet = new HashSet<double>(hvn ?? new List<double>());
			HashSet<double> lvnSet = new HashSet<double>(lvn ?? new List<double>());
			HashSet<double> spSet = new HashSet<double>(singlePrints ?? new List<double>());

			// bands (behind)
			if (ShowVABand && !double.IsNaN(vah))
			{
				float y1 = chartScale.GetYByValue(vah), y2 = chartScale.GetYByValue(val);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(winStartX, Math.Min(y1, y2), vpMaxRight - winStartX, Math.Abs(y2 - y1)), vaBandBr);
			}
			if (ShowPriorBand && !double.IsNaN(pVah))
			{
				float y1 = chartScale.GetYByValue(pVah), y2 = chartScale.GetYByValue(pVal);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(priorStartX, Math.Min(y1, y2), vpMaxRight - priorStartX, Math.Abs(y2 - y1)), priorBandBr);
			}

			// rows: VP bars (with node coloring) + TPO blocks + single-print ticks
			foreach (KeyValuePair<double, double> kv in volByRow)
			{
				double price = kv.Key;
				float yTop = chartScale.GetYByValue(price + rowSize);
				if (ShowVP)
				{
					float w = (float)(VpWidthPx * kv.Value / maxVol);
					SolidColorBrush br = teal;
					if (ShowPOC && price == poc) br = pocBr;
					else if (ShowHVN && hvnSet.Contains(price)) br = hvnBr;
					else if (ShowLVN && lvnSet.Contains(price)) br = lvnBr;
					RenderTarget.FillRectangle(new SharpDX.RectangleF(vpLeft, yTop, w, rowH - 1f), br);
				}
				if (ShowTPO)
				{
					List<int> brs;
					if (tpoByRow.TryGetValue(price, out brs))
					{
						brs.Sort();
						for (int k = 0; k < brs.Count; k++)
							RenderTarget.FillRectangle(new SharpDX.RectangleF(tpoLeft + k * BlockWidthPx, yTop, BlockWidthPx - 1f, rowH - 1f), brackets[brs[k]]);
						if (ShowSinglePrints && spSet.Contains(price))
							RenderTarget.FillRectangle(new SharpDX.RectangleF(tpoLeft - 4f, yTop, 3f, rowH - 1f), spBr);
					}
				}
			}

			// lines (current)
			if (ShowPOC && !double.IsNaN(poc)) DrawLevel(chartScale, winStartX, vpMaxRight, poc, pocBr, 1.4f);
			if (ShowVAHVAL && !double.IsNaN(vah)) { DrawLevel(chartScale, winStartX, vpMaxRight, vah, vaLineBr, 1.0f); DrawLevel(chartScale, winStartX, vpMaxRight, val, vaLineBr, 1.0f); }
			if (ShowIB && ibh > double.MinValue) { DrawLevel(chartScale, winStartX, vpMaxRight, ibh, ibBr, 0.9f); DrawLevel(chartScale, winStartX, vpMaxRight, ibl, ibBr, 0.9f); }
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
				float labelX = tpoLeft + (maxBracket + 1) * BlockWidthPx + 8f;
				List<Lbl> labels = new List<Lbl>();
				if (ShowPOC && !double.IsNaN(poc)) AddLbl(labels, chartScale, "POC " + FmtP(poc), poc, pocBr);
				if (ShowVAHVAL && !double.IsNaN(vah)) { AddLbl(labels, chartScale, "VAH " + FmtP(vah), vah, vaLineBr); AddLbl(labels, chartScale, "VAL " + FmtP(val), val, vaLineBr); }
				if (ShowPriorLines && !double.IsNaN(pVah)) { AddLbl(labels, chartScale, "pVAH " + FmtP(pVah), pVah, priorLineBr); AddLbl(labels, chartScale, "pPOC " + FmtP(pPoc), pPoc, priorLineBr); AddLbl(labels, chartScale, "pVAL " + FmtP(pVal), pVal, priorLineBr); }
				if (ShowIB && ibh > double.MinValue) { AddLbl(labels, chartScale, "IBH " + FmtP(ibh), ibh, ibBr); AddLbl(labels, chartScale, "IBL " + FmtP(ibl), ibl, ibBr); }
				DrawLabels(labels, labelX, vpMaxRight);
			}

			teal.Dispose(); pocBr.Dispose(); vaLineBr.Dispose(); vaBandBr.Dispose(); ibBr.Dispose();
			priorLineBr.Dispose(); priorBandBr.Dispose(); hvnBr.Dispose(); lvnBr.Dispose(); spBr.Dispose();
			for (int b = 0; b <= maxBracket; b++) brackets[b].Dispose();
		}

		private void DrawLevel(ChartScale cs, float x0, float x1, double price, SolidColorBrush br, float wdt)
		{
			float y = cs.GetYByValue(price);
			RenderTarget.DrawLine(new SharpDX.Vector2(x0, y), new SharpDX.Vector2(x1, y), br, wdt);
		}

		private void AddLbl(List<Lbl> list, ChartScale cs, string text, double price, SolidColorBrush br)
		{
			float y = cs.GetYByValue(price);
			list.Add(new Lbl { y = y, trueY = y, text = text, brush = br });
		}

		private void DrawLabels(List<Lbl> labels, float x, float leaderFromX)
		{
			if (labels.Count == 0) return;
			labels.Sort(delegate (Lbl a, Lbl b) { return a.y.CompareTo(b.y); });
			float gap = LabelFontSize + 4f;
			for (int i = 1; i < labels.Count; i++)
				if (labels[i].y < labels[i - 1].y + gap) labels[i].y = labels[i - 1].y + gap;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			foreach (Lbl L in labels)
			{
				if (Math.Abs(L.y - L.trueY) > 1.5f)
					RenderTarget.DrawLine(new SharpDX.Vector2(leaderFromX, L.trueY), new SharpDX.Vector2(x - 2f, L.y + LabelFontSize * 0.5f), L.brush, 0.6f);
				RenderTarget.DrawText(L.text, tf, new SharpDX.RectangleF(x, L.y, 150f, LabelFontSize + 6f), L.brush);
			}
			tf.Dispose();
		}

		private string FmtP(double p)
		{
			return p.ToString("0.##");
		}
	}
}
