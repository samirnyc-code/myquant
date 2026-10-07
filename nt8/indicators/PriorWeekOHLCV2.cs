// PriorWeekOHLCV2 — prior-week O/H/L/C reference lines.
//
// V2 of PriorWeekOHLC.cs: dropped NT8's native HLine AddPlot rendering (which drew clear
// across the whole panel, including far into the empty future space — see S130 screenshot)
// in favor of a custom SharpDX OnRender, same pattern as SessionSRLevelsV5.cs:
//   - line is a ray from the leftmost VISIBLE bar to current-bar+1, not edge-to-edge
//   - label is vertically CENTERED on the line, not drawn via TDEU's old barsAgo Draw.Text
//   - per-level Color/Opacity/Line style/Thickness, same as SessionSRLevelsV5
//   - new "Show price in label" toggle (off by default — old labels never had the price)
//
// Week-accumulation logic (OnBarUpdate) is otherwise UNCHANGED from the Daily-bars fix:
// Math.Max/Min running per bar, week boundary via Time[0].Date.AddDays(7-DayOfWeek). Works
// on intraday AND Daily (BarsPeriodType.Day) series.
//
// AddPlot calls kept (Transparent) so the public PriorWeekOpen/High/Low/Close Series<double>
// + DisplayInDataBox keep working for anything that reads them — same "transparent plot,
// custom visual" trick the file already used for Open/Close before this rewrite.
// RULE (CLAUDE.md): lives in nt8/ committed. Deploy to Documents\...\Custom\Indicators\ then F5.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
// Color/Brush/SolidColorBrush exist in BOTH System.Windows.Media and SharpDX/SharpDX.Direct2D1
// — alias both sides, same fix as SessionSRLevelsV5.cs.
using WMColor = System.Windows.Media.Color;
using WMBrush = System.Windows.Media.Brush;
using WMSolidColorBrush = System.Windows.Media.SolidColorBrush;
using D2DSolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

//This namespace holds Indicators in this folder and is required. Do not change it.
namespace NinjaTrader.NinjaScript.Indicators
{
	/// <summary>
	/// Shows the OHLC of the previous week
	/// </summary>
	public class PriorWeekOHLCV2 : Indicator
	{
		private double weeklyOpen 		= 0;
		private double weeklyHigh 		= 0;
		private double weeklyLow 		= 0;
		private double weeklyClose 	= 0;

		private double prWeeklyOpen 	= 0;
		private double prWeeklyHigh 	= 0;
		private double prWeeklyLow 		= 0;
		private double prWeeklyClose 	= 0;

		// bar index of the running weekly high/low PRINT (updated only when a new extreme
		// is actually made) + the open bar (fixed at week start) and the running "last bar"
		// (close) — frozen into prWeekly*Bar at week-roll, same pattern as SessionSRLevelsV5.
		private int weeklyOpenBar = -1, weeklyHighBar = -1, weeklyLowBar = -1, weeklyCloseBar = -1;
		private int prWeeklyOpenBar = -1, prWeeklyHighBar = -1, prWeeklyLowBar = -1, prWeeklyCloseBar = -1;

		private DateTime newWeek = DateTime.MinValue;

		private struct LevelDef
		{
			public bool enabled; public string label; public double price;
			public WMColor color; public int opacity; public LevelLineStyle style; public int thickness;
			public int startBarIdx;
		}
		private class LabelInfo { public float y; public float trueY; public string text; public D2DSolidColorBrush brush; }

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description					= @"Shows the OHLC of the previous week";
				Name						= "PriorWeekOHLCV2";
				Calculate					= Calculate.OnBarClose;
				IsOverlay					= true;
				DisplayInDataBox			= true;
				DrawOnPricePanel			= true;
				PaintPriceMarkers			= false;   // custom labels replace the native price-axis marker
				IsSuspendedWhileInactive	= true;
				AllowRemovalOfDrawObjects	= true;
				IsAutoScale					= false;

				ShowClose					= true;
				ShowLow						= true;
				ShowHigh					= true;
				ShowOpen					= true;

				LabelFontSize				= 12;
				ShowPriceInLabel			= false;

				OpenLabel  = "OoLW"; OpenColor  = Brushes.Gold;    OpenOpacity  = 100; OpenStyle  = LevelLineStyle.DashDot; OpenThickness  = 2;
				HighLabel  = "HoLW"; HighColor  = Brushes.Magenta; HighOpacity  = 100; HighStyle  = LevelLineStyle.DashDot; HighThickness  = 2;
				LowLabel   = "LoLW"; LowColor   = Brushes.Cyan;    LowOpacity   = 100; LowStyle   = LevelLineStyle.DashDot; LowThickness   = 2;
				CloseLabel = "CoLW"; CloseColor = Brushes.Orange;  CloseOpacity = 100; CloseStyle = LevelLineStyle.DashDot; CloseThickness = 2;

				// Transparent native plots: keeps PriorWeekOpen/High/Low/Close Series<double>
				// + DisplayInDataBox working; actual visuals are drawn in OnRender below.
				AddPlot(new Stroke(Brushes.Transparent, DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekOpen");
				AddPlot(new Stroke(Brushes.Transparent, DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekHigh");
				AddPlot(new Stroke(Brushes.Transparent, DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekLow");
				AddPlot(new Stroke(Brushes.Transparent, DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekClose");
			}
		}

		public override string DisplayName
		{
	  		get
			{
				if  (State == State.SetDefaults)
				{
					return Name + " ";
				}
				else return "";
			}
		}

		protected override void OnBarUpdate()
		{
			if (!Bars.BarsType.IsIntraday && Bars.BarsPeriod.BarsPeriodType != BarsPeriodType.Day)
			{
				Draw.TextFixed(this, "error1", "PriorWeekOHLCV2 only works on intraday or daily data series", TextPosition.BottomRight);
				return;
			}

			if (newWeek < Time[0])
			{
				prWeeklyOpen 	= weeklyOpen;	prWeeklyOpenBar  = weeklyOpenBar;
				prWeeklyHigh 	= weeklyHigh;	prWeeklyHighBar  = weeklyHighBar;
				prWeeklyLow 	= weeklyLow;	prWeeklyLowBar   = weeklyLowBar;
				prWeeklyClose 	= weeklyClose;	prWeeklyCloseBar = weeklyCloseBar;

				weeklyOpen 		= Open[0];  weeklyOpenBar = CurrentBar;
				weeklyHigh 		= High[0];  weeklyHighBar = CurrentBar;
				weeklyLow 		= Low[0];   weeklyLowBar  = CurrentBar;
				weeklyClose 	= Close[0]; weeklyCloseBar = CurrentBar;

				newWeek = Time[0].Date.AddDays(7 - (int)Time[0].DayOfWeek);
			}

			if (prWeeklyOpen != 0)
			{
				if (ShowOpen)	PriorWeekOpen[0] 	= prWeeklyOpen;
				if (ShowHigh)	PriorWeekHigh[0] 	= prWeeklyHigh;
				if (ShowLow)	PriorWeekLow[0] 	= prWeeklyLow;
				if (ShowClose)	PriorWeekClose[0] 	= prWeeklyClose;
			}

			if (High[0] > weeklyHigh) { weeklyHigh = High[0]; weeklyHighBar = CurrentBar; }
			if (Low[0]  < weeklyLow)  { weeklyLow  = Low[0];  weeklyLowBar  = CurrentBar; }
			weeklyClose 	= Close[0];
			weeklyCloseBar 	= CurrentBar;
		}

		// ══════════════════════════ Rendering ════════════════════════════
		// Line is a ray from the leftmost VISIBLE bar to current-bar+1 — never the full
		// panel width / into empty future space. Label centered on the line, same as
		// SessionSRLevelsV5.cs.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;
			if (prWeeklyOpen == 0 && prWeeklyHigh == 0 && prWeeklyLow == 0 && prWeeklyClose == 0) return;

			float panelLeft = (float)ChartPanel.X;
			int lastIdx = ChartBars.ToIndex;
			if (lastIdx < 0) return;
			float lineEndX = chartControl.GetXByBarIndex(ChartBars, lastIdx + 1);   // current bar + 1

			var defs = new List<LevelDef>(4);
			AddDef(defs, ShowOpen,  OpenLabel,  prWeeklyOpen,  OpenColor,  OpenOpacity,  OpenStyle,  OpenThickness,  prWeeklyOpenBar);
			AddDef(defs, ShowHigh,  HighLabel,  prWeeklyHigh,  HighColor,  HighOpacity,  HighStyle,  HighThickness,  prWeeklyHighBar);
			AddDef(defs, ShowLow,   LowLabel,   prWeeklyLow,   LowColor,   LowOpacity,   LowStyle,   LowThickness,   prWeeklyLowBar);
			AddDef(defs, ShowClose, CloseLabel, prWeeklyClose, CloseColor, CloseOpacity, CloseStyle, CloseThickness, prWeeklyCloseBar);

			var labels = new List<LabelInfo>();
			foreach (LevelDef d in defs)
			{
				if (!d.enabled || d.price == 0 || d.startBarIdx < 0) continue;

				int startIdx = Math.Max(d.startBarIdx, ChartBars.FromIndex);
				float xStart = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, startIdx));
				if (xStart >= lineEndX) continue;

				float a = Math.Max(0f, Math.Min(1f, d.opacity / 100f));
				var sdxBrush = new D2DSolidColorBrush(RenderTarget,
					new Color4(d.color.R / 255f, d.color.G / 255f, d.color.B / 255f, a));

				float y = chartScale.GetYByValue(d.price);
				DrawStyledLine(xStart, lineEndX, y, sdxBrush, d.thickness, d.style);

				string text = ShowPriceInLabel ? d.label + " " + F(d.price) : d.label;
				labels.Add(new LabelInfo { y = y, trueY = y, text = text, brush = sdxBrush });
			}

			DrawLabels(labels, lineEndX + 6f);

			foreach (LabelInfo li in labels) li.brush.Dispose();
		}

		private static void AddDef(List<LevelDef> list, bool enabled, string label, double price,
			WMBrush brush, int opacity, LevelLineStyle style, int thickness, int startBarIdx)
		{
			var scb = brush as WMSolidColorBrush;
			list.Add(new LevelDef
			{
				enabled = enabled, label = label, price = price,
				color = scb != null ? scb.Color : Colors.Gray,
				opacity = opacity, style = style, thickness = thickness, startBarIdx = startBarIdx
			});
		}

		// Dependency-free dashing (no Direct2D1 StrokeStyle/Factory needed).
		private void DrawStyledLine(float xL, float xR, float y, SharpDX.Direct2D1.Brush br, float thickness, LevelLineStyle style)
		{
			if (style == LevelLineStyle.Solid)
			{
				RenderTarget.DrawLine(new Vector2(xL, y), new Vector2(xR, y), br, thickness);
				return;
			}
			float[] pattern = style == LevelLineStyle.Dot      ? new float[] { 2f, 4f }
							: style == LevelLineStyle.DashDot   ? new float[] { 8f, 4f, 2f, 4f }
							:                                      new float[] { 8f, 5f };   // Dash
			float x = xL;
			int pi = 0;
			while (x < xR)
			{
				float seg = Math.Min(pattern[pi % pattern.Length], xR - x);
				if (pi % 2 == 0) RenderTarget.DrawLine(new Vector2(x, y), new Vector2(x + seg, y), br, thickness);
				x += seg;
				pi++;
			}
		}

		// Single column, de-collided top-to-bottom with leader lines when a label had to be
		// nudged off its true price — same pattern as SessionSRLevelsV5.cs.
		private void DrawLabels(List<LabelInfo> labels, float baseX)
		{
			if (labels.Count == 0) return;
			float colW = LabelFontSize * 6.5f;
			float gap  = LabelFontSize + 4f;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			labels.Sort(delegate (LabelInfo a, LabelInfo b) { return a.y.CompareTo(b.y); });
			for (int i = 1; i < labels.Count; i++)
				if (labels[i].y < labels[i - 1].y + gap) labels[i].y = labels[i - 1].y + gap;
			float textH = LabelFontSize + 6f;
			foreach (LabelInfo li in labels)
			{
				if (Math.Abs(li.y - li.trueY) > 1.5f)
					RenderTarget.DrawLine(new Vector2(baseX - 6f, li.trueY), new Vector2(baseX - 1f, li.y), li.brush, 0.6f);
				// Vertically CENTER the text on the line's y, not top-aligned below it.
				RenderTarget.DrawText(li.text, tf, new RectangleF(baseX, li.y - textH / 2f, colW, textH), li.brush);
			}
			tf.Dispose();
		}

		private static string F(double p) { return p.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture); }

		#region Properties
        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekOpen
        {
            get { return Values[0]; }
        }

        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekHigh
        {
            get { return Values[1]; }
        }

        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekLow
        {
            get { return Values[2]; }
        }

        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekClose
        {
            get { return Values[3]; }
        }

		[Display(Name = "Label font size", Order = 0, GroupName = "00 Display")]
		[Range(6, 24)]
		public int LabelFontSize { get; set; }

		[Display(Name = "Show price in label", Order = 1, GroupName = "00 Display",
			Description = "Off = just the label text (e.g. \"HoLW\"), no price value appended.")]
		public bool ShowPriceInLabel { get; set; }

		// ---- Open ----
		[Display(Name = "Show Weekly Open", Order = 0, GroupName = "01 Open")]
		public bool ShowOpen { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01 Open")]
		public string OpenLabel { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01 Open")]
		public WMBrush OpenColor { get; set; }
		[Browsable(false)] public string OpenColorSerialize { get { return Serialize.BrushToString(OpenColor); } set { OpenColor = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01 Open")]
		public int OpenOpacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01 Open")]
		public LevelLineStyle OpenStyle { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01 Open")]
		public int OpenThickness { get; set; }

		// ---- High ----
		[Display(Name = "Show Weekly High", Order = 0, GroupName = "02 High")]
		public bool ShowHigh { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "02 High")]
		public string HighLabel { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "02 High")]
		public WMBrush HighColor { get; set; }
		[Browsable(false)] public string HighColorSerialize { get { return Serialize.BrushToString(HighColor); } set { HighColor = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "02 High")]
		public int HighOpacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "02 High")]
		public LevelLineStyle HighStyle { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "02 High")]
		public int HighThickness { get; set; }

		// ---- Low ----
		[Display(Name = "Show Weekly Low", Order = 0, GroupName = "03 Low")]
		public bool ShowLow { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "03 Low")]
		public string LowLabel { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "03 Low")]
		public WMBrush LowColor { get; set; }
		[Browsable(false)] public string LowColorSerialize { get { return Serialize.BrushToString(LowColor); } set { LowColor = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "03 Low")]
		public int LowOpacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "03 Low")]
		public LevelLineStyle LowStyle { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "03 Low")]
		public int LowThickness { get; set; }

		// ---- Close ----
		[Display(Name = "Show Weekly Close", Order = 0, GroupName = "04 Close")]
		public bool ShowClose { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "04 Close")]
		public string CloseLabel { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "04 Close")]
		public WMBrush CloseColor { get; set; }
		[Browsable(false)] public string CloseColorSerialize { get { return Serialize.BrushToString(CloseColor); } set { CloseColor = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "04 Close")]
		public int CloseOpacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "04 Close")]
		public LevelLineStyle CloseStyle { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "04 Close")]
		public int CloseThickness { get; set; }
        #endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private PriorWeekOHLCV2[] cachePriorWeekOHLCV2;
		public PriorWeekOHLCV2 PriorWeekOHLCV2()
		{
			return PriorWeekOHLCV2(Input);
		}

		public PriorWeekOHLCV2 PriorWeekOHLCV2(ISeries<double> input)
		{
			if (cachePriorWeekOHLCV2 != null)
				for (int idx = 0; idx < cachePriorWeekOHLCV2.Length; idx++)
					if (cachePriorWeekOHLCV2[idx] != null &&  cachePriorWeekOHLCV2[idx].EqualsInput(input))
						return cachePriorWeekOHLCV2[idx];
			return CacheIndicator<PriorWeekOHLCV2>(new PriorWeekOHLCV2(), input, ref cachePriorWeekOHLCV2);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.PriorWeekOHLCV2 PriorWeekOHLCV2()
		{
			return indicator.PriorWeekOHLCV2(Input);
		}

		public Indicators.PriorWeekOHLCV2 PriorWeekOHLCV2(ISeries<double> input )
		{
			return indicator.PriorWeekOHLCV2(input);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.PriorWeekOHLCV2 PriorWeekOHLCV2()
		{
			return indicator.PriorWeekOHLCV2(Input);
		}

		public Indicators.PriorWeekOHLCV2 PriorWeekOHLCV2(ISeries<double> input )
		{
			return indicator.PriorWeekOHLCV2(input);
		}
	}
}

#endregion
