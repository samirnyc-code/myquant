// CVDDivergenceOscillator — NT8 port of TradingView's
// "Cumulative Volume Delta Divergence [TradingFinder] Periodic EMA"
// https://www.tradingview.com/script/HvOAnchA-Cumulative-Volume-Delta-Divergence-TradingFinder-Periodic-EMA/
// (MPL-2.0, (c) TFlab — ported from the Pine v5 source the user pasted directly, 2026-10-18)
//
// STANDALONE on purpose (separate from CumulativeDelta.cs, which already has its own
// tick-level live-zigzag CVD divergence feature, S142) so the two can be compared.
//
// WHAT'S DIFFERENT FROM CumulativeDelta.cs:
//   - Delta here is a bar-level PROXY (close position within the bar's H-L range *
//     bar Volume), exactly as the Pine source computes it — NOT real tick-level bid/ask
//     classified delta. Works on any bar type incl. non-tick-replay charts.
//   - "Hist" (the CVD line) is either a rolling-window SUM of that delta over CvdPeriod
//     bars ("Periodic" mode) or an EMA of it ("EMA" mode) — matches Pine's math.sum /
//     ta.ema choice exactly, selectable via CumulativeMode.
//   - Divergence uses FIXED-LOOKBACK FRACTAL pivots (n bars either side, like
//     ta.pivothigh/pivotlow), filtered by a trend EMA, not a live reversal-tick zigzag.
//     It is retrospective/one-shot: once a new pivot confirms (n bars after it forms)
//     and the pivot pair satisfies the divergence test, a permanent marker is drawn —
//     there's no "live/growing" line like CumulativeDelta's.
//
// WHAT'S OMITTED FROM THE PINE SOURCE (documented, not silently dropped):
//   - "Market Ultra Data" (UltraData/Market inputs) — the original sums volume across
//     ~26 named Forex/Crypto brokers via request.security() to approximate real volume
//     on symbols with fragmented feeds. ES futures has one consolidated CME feed; NT8
//     has no equivalent multi-broker volume concept, so this is skipped entirely rather
//     than faked. Volume here is always the chart's own bar Volume.
//   - The Pine source also computes CBearDive/CBullDive streak counters and
//     text_power_bull/bear "Normal/Good/Strong Dive" strings and a Bear_Phase/Bull_Phase
//     flag — all of these are computed in the source but never plotted, labeled, or
//     alerted on anywhere in the script (dead code). Not ported.
//   - Pine's Drawing() re-creates a brand-new line+label object on EVERY bar the
//     divergence condition holds (its endpoints never change while held — same two
//     frozen pivots), relying on Pine's max_lines_count/max_labels_count=500 to garbage-
//     collect the resulting duplicates. This port draws each confirmed divergence
//     exactly ONCE (same visual result, no duplicate-object spam).
//   - Pine draws the "+RD"/"-RD" label on BOTH the oscillator pane and the price panel.
//     This port draws the connecting line on both panels but the text label only on the
//     price panel (Draw.Text) — the oscillator-pane line is manual SharpDX (see below)
//     and duplicating the same text there via DirectWrite wasn't worth the complexity
//     for a label that already appears on the price chart.
//
// PANEL SPLIT (same pattern as CumulativeDelta.cs): a non-overlay indicator's
// DrawOnPricePanel flag is global for ALL of its Draw.* calls, so to put markers on BOTH
// this indicator's own panel (Hist-to-Hist lines) AND the price panel (price-to-price
// lines + label) from one indicator, DrawOnPricePanel=true routes Draw.Line/Draw.Text to
// the price panel, and the Hist-pane connecting lines are rendered manually via SharpDX
// inside OnRender instead.
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
#endregion

namespace NinjaTrader.NinjaScript
{
	// Defined in the PARENT namespace, NOT in .Indicators — same reason as
	// SessionSRLevelsV9.cs's LevelLineStyle: NT8 regenerates wrapper code in the sibling
	// .MarketAnalyzerColumns and .Strategies namespaces on every compile using the
	// unqualified enum name, so a [NinjaScriptProperty] enum must live where all three
	// child namespaces can see it by walking up to this common parent. Declaring it in
	// .Indicators compiles fine standalone but throws CS0246 in NT8's own generated
	// wrapper code the moment the whole Custom tree builds together (2026-10-18 — this
	// exact bug blocked a full Custom rebuild; root-caused and fixed same session).
	public enum CvdCumulativeMode { Periodic, EMA }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class CVDDivergenceOscillator : Indicator
    {
        private Series<double> deltaSeries;
        private Series<double> histSeries;

        // last-confirmed / previous-confirmed fractal pivot (bearish side = pivot highs)
        private int hLastBar = -1, hPrevBar = -1;
        private double hLastPrice = double.NaN, hPrevPrice = double.NaN;
        private double hLastHist = double.NaN, hPrevHist = double.NaN;

        // bullish side = pivot lows
        private int lLastBar = -1, lPrevBar = -1;
        private double lLastPrice = double.NaN, lPrevPrice = double.NaN;
        private double lLastHist = double.NaN, lPrevHist = double.NaN;

        private struct DivMark { public int barA, barB; public double histA, histB; public bool bearish; }
        private List<DivMark> marks = new List<DivMark>();

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "CVDDivergenceOscillator";
                Description = "NT8 port of TradingView 'Cumulative Volume Delta Divergence [TradingFinder] Periodic EMA' — bar-proxy CVD (Periodic sum or EMA) + fixed-lookback fractal regular divergence";
                Calculate = Calculate.OnBarClose;    // matches the Pine source (bar-close based, not tick-based)
                IsOverlay = false;
                DrawOnPricePanel = true;             // lets Draw.Line/Draw.Text reach the price panel for the divergence markers
                DisplayInDataBox = true;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = true;

                DivergenceFractalPeriods = 2;
                CvdPeriod = 21;
                CumulativeMode = CvdCumulativeMode.Periodic;
                TrendEmaPeriod = 50;
                MaxPivotGapBars = 30;

                ShowLabels = true;
                DivLabelFontSize = 10;
                BullColor = Brushes.LimeGreen;
                BearColor = Brushes.Firebrick;
                PosHistColor = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(140, 76, 175, 79));
                NegHistColor = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(140, 255, 82, 82));

                AddPlot(new Stroke(Brushes.Gray, 2), PlotStyle.Bar, "CVD Hist");
            }
            else if (State == State.Configure)
            {
                deltaSeries = new Series<double>(this);
                histSeries = new Series<double>(this);
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 0) return;

            double range = High[0] - Low[0];
            double buying = range > 0 ? Volume[0] * (Close[0] - Low[0]) / range : 0;
            double selling = range > 0 ? Volume[0] * (High[0] - Close[0]) / range : 0;
            deltaSeries[0] = buying - selling;

            double hist = CumulativeMode == CvdCumulativeMode.Periodic
                ? SUM(deltaSeries, CvdPeriod)[0]
                : EMA(deltaSeries, CvdPeriod)[0];
            histSeries[0] = hist;
            Values[0][0] = hist;
            PlotBrushes[0][0] = hist >= 0 ? PosHistColor : NegHistColor;

            int n = DivergenceFractalPeriods;
            if (CurrentBar < 2 * n) return;

            double emaNow = EMA(Close, TrendEmaPeriod)[0];

            if (IsPivotHigh(n) && Close[n] > emaNow)
            {
                int pivotBar = CurrentBar - n;
                double price = High[n];
                double hv = histSeries[n];

                hPrevBar = hLastBar; hPrevPrice = hLastPrice; hPrevHist = hLastHist;
                hLastBar = pivotBar; hLastPrice = price; hLastHist = hv;

                if (hPrevBar >= 0 && (hLastBar - hPrevBar) < MaxPivotGapBars
                    && hLastHist > 0 && hPrevHist > 0
                    && hLastPrice > hPrevPrice && hLastHist < hPrevHist)
                {
                    DrawDivergence(hPrevBar, hPrevPrice, hPrevHist, hLastBar, hLastPrice, hLastHist, true);
                }
            }

            if (IsPivotLow(n) && Close[n] < emaNow)
            {
                int pivotBar = CurrentBar - n;
                double price = Low[n];
                double hv = histSeries[n];

                lPrevBar = lLastBar; lPrevPrice = lLastPrice; lPrevHist = lLastHist;
                lLastBar = pivotBar; lLastPrice = price; lLastHist = hv;

                if (lPrevBar >= 0 && (lLastBar - lPrevBar) < MaxPivotGapBars
                    && lLastHist < 0 && lPrevHist < 0
                    && lLastPrice < lPrevPrice && lLastHist > lPrevHist)
                {
                    DrawDivergence(lPrevBar, lPrevPrice, lPrevHist, lLastBar, lLastPrice, lLastHist, false);
                }
            }
        }

        // fractal pivot high/low over n bars each side; ties resolve to the earlier bar
        // (matches ta.pivothigh(n,n)/ta.pivotlow(n,n) semantics close enough for this use)
        private bool IsPivotHigh(int n)
        {
            double candidate = High[n];
            for (int k = 1; k <= n; k++) if (High[n - k] > candidate) return false;
            for (int k = 1; k <= n; k++) if (High[n + k] >= candidate) return false;
            return true;
        }

        private bool IsPivotLow(int n)
        {
            double candidate = Low[n];
            for (int k = 1; k <= n; k++) if (Low[n - k] < candidate) return false;
            for (int k = 1; k <= n; k++) if (Low[n + k] <= candidate) return false;
            return true;
        }

        // price-panel line + label (Draw.* API, routed to the price panel by DrawOnPricePanel=true)
        // + queue the Hist-pane connecting line for manual rendering in OnRender.
        private void DrawDivergence(int barA, double priceA, double histA, int barB, double priceB, double histB, bool bearish)
        {
            System.Windows.Media.Brush color = bearish ? BearColor : BullColor;
            string tag = (bearish ? "cvdFracDivBear_" : "cvdFracDivBull_") + barA + "_" + barB;
            int baA = CurrentBar - barA, baB = CurrentBar - barB;

            Draw.Line(this, tag, false, baA, priceA, baB, priceB, color, DashStyleHelper.Solid, 2);
            if (ShowLabels)
            {
                double off = 8 * (TickSize > 0 ? TickSize : 0.25);
                Draw.Text(this, tag + "_txt", false, bearish ? "-RD" : "+RD", baB,
                          bearish ? priceB + off : priceB - off, 0, color,
                          new SimpleFont("Arial", DivLabelFontSize), System.Windows.TextAlignment.Center,
                          Brushes.Transparent, Brushes.Transparent, 0);
            }

            marks.Add(new DivMark { barA = barA, barB = barB, histA = histA, histB = histB, bearish = bearish });
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (marks.Count == 0 || ChartBars == null || RenderTarget == null) return;

            int fromV = ChartBars.FromIndex, toV = ChartBars.ToIndex;
            var bearBr = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(BearColor));
            var bullBr = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(BullColor));

            foreach (DivMark m in marks)
            {
                if (m.barA < fromV - 1 && m.barB < fromV - 1) continue;
                if (m.barA > toV + 1 && m.barB > toV + 1) continue;
                float xA = chartControl.GetXByBarIndex(ChartBars, m.barA), xB = chartControl.GetXByBarIndex(ChartBars, m.barB);
                float yA = chartScale.GetYByValue(m.histA), yB = chartScale.GetYByValue(m.histB);
                RenderTarget.DrawLine(new Vector2(xA, yA), new Vector2(xB, yB), m.bearish ? bearBr : bullBr, 2f);
            }

            bearBr.Dispose(); bullBr.Dispose();
        }

        private static Color4 ToColor4(System.Windows.Media.Brush b)
        {
            var scb = b as System.Windows.Media.SolidColorBrush;
            if (scb == null) return new Color4(1f, 1f, 1f, 1f);
            var c = scb.Color;
            return new Color4(c.R / 255f, c.G / 255f, c.B / 255f, c.A / 255f);
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Divergence Fractal Periods", Description = "Bars required on each side of a swing high/low before it confirms as a pivot (Pine: n)",
                 GroupName = "1. Logic Setting", Order = 0)]
        public int DivergenceFractalPeriods { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "CVD Period", Description = "Rolling-sum window (Periodic mode) or smoothing length (EMA mode) applied to the per-bar delta proxy",
                 GroupName = "1. Logic Setting", Order = 1)]
        public int CvdPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Cumulative Mode", Description = "Periodic = rolling SUM of delta over CVD Period bars; EMA = EMA of delta over CVD Period bars",
                 GroupName = "1. Logic Setting", Order = 2)]
        public CvdCumulativeMode CumulativeMode { get; set; }

        [NinjaScriptProperty]
        [Range(2, 500)]
        [Display(Name = "Trend EMA Period", Description = "EMA of Close used as the trend filter a fractal pivot must agree with (Pine: hardcoded 50)",
                 GroupName = "1. Logic Setting", Order = 3)]
        public int TrendEmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Max Pivot Gap (bars)", Description = "Two fractal pivots further apart than this are never compared for divergence (Pine: hardcoded 30)",
                 GroupName = "1. Logic Setting", Order = 4)]
        public int MaxPivotGapBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Labels", Description = "Draw +RD/-RD text on the price panel at each confirmed divergence",
                 GroupName = "2. Display Setting", Order = 0)]
        public bool ShowLabels { get; set; }

        [NinjaScriptProperty]
        [Range(6, 24)]
        [Display(Name = "Label font size", GroupName = "2. Display Setting", Order = 1)]
        public int DivLabelFontSize { get; set; }

        [XmlIgnore]
        [Display(Name = "Bullish color", GroupName = "2. Display Setting", Order = 2)]
        public System.Windows.Media.Brush BullColor { get; set; }
        [Browsable(false)]
        public string BullColorSerialize { get { return Serialize.BrushToString(BullColor); } set { BullColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Bearish color", GroupName = "2. Display Setting", Order = 3)]
        public System.Windows.Media.Brush BearColor { get; set; }
        [Browsable(false)]
        public string BearColorSerialize { get { return Serialize.BrushToString(BearColor); } set { BearColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Positive hist color", GroupName = "2. Display Setting", Order = 4)]
        public System.Windows.Media.Brush PosHistColor { get; set; }
        [Browsable(false)]
        public string PosHistColorSerialize { get { return Serialize.BrushToString(PosHistColor); } set { PosHistColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Negative hist color", GroupName = "2. Display Setting", Order = 5)]
        public System.Windows.Media.Brush NegHistColor { get; set; }
        [Browsable(false)]
        public string NegHistColorSerialize { get { return Serialize.BrushToString(NegHistColor); } set { NegHistColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
