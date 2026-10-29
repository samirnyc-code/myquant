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
//     ta.ema choice exactly, selectable via the UseEmaMode checkbox.
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

namespace NinjaTrader.NinjaScript.Indicators.My
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

        // last DtDbCvdPivotRegistry.Id this instance has already drawn — only used when
        // OnlyShowAtDtDb is on. See DtDbCvdPivotRegistry.cs for the sharing mechanism.
        private int _lastSeenDtDbId;

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
                UseEmaMode = false; // false = Periodic (rolling SUM), true = EMA — default matches the Pine source
                TrendEmaPeriod = 50;
                MaxPivotGapBars = 30;

                ShowLabels = true;
                DivLabelFontSize = 10;
                BullColor = Brushes.LimeGreen;
                BearColor = Brushes.Firebrick;
                // .Freeze() both -- 2026-10-19: these were the ONLY two brushes in this file
                // built from a custom ARGB color instead of a pre-frozen named Brushes.X
                // constant (BullColor/BearColor etc. all use Brushes.X, already frozen/thread-
                // safe). An unfrozen WPF Freezable is owned by whatever thread constructed it
                // (the UI thread, here, since SetDefaults runs there) -- assigning it to
                // PlotBrushes[] from OnBarUpdate running on a DIFFERENT thread (confirmed via
                // NT8's own log: custom bar types like Flex Renko apparently run historical
                // calculation on a background thread, unlike standard bar types) threw "The
                // calling thread cannot access this object because a different thread owns
                // it" on bar 0 every time -- killed the indicator immediately, which is why
                // the whole panel rendered completely empty, not just the colors being wrong.
                var posHist = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(140, 76, 175, 79));
                posHist.Freeze();
                PosHistColor = posHist;
                var negHist = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(140, 255, 82, 82));
                negHist.Freeze();
                NegHistColor = negHist;

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

            double hist = UseEmaMode
                ? EMA(deltaSeries, CvdPeriod)[0]
                : SUM(deltaSeries, CvdPeriod)[0];
            histSeries[0] = hist;
            Values[0][0] = hist;
            PlotBrushes[0][0] = hist >= 0 ? PosHistColor : NegHistColor;

            // 2026-10-29: when ON, this REPLACES the fractal-pivot detection below
            // entirely — divergence lines come only from DtDbScannerV3's own confirmed
            // DT/DB pivots (via the shared registry), not this indicator's independent
            // fractal detection. User's own framing: "only shows DBDT based on the
            // current setting in the Scanner" — DtDbScannerV3 only publishes a pivot
            // pair when ITS OWN CvdAgrees fires, so what shows here already reflects
            // whatever the scanner currently confirms, not a separate re-derivation.
            if (OnlyShowAtDtDb)
            {
                DrawFromDtDbRegistry();
                return;
            }

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

        // Only called when OnlyShowAtDtDb is on. Reads every DtDbCvdPivotRegistry entry
        // published since this instance last checked, draws the same price-panel line +
        // label + Hist-pane mark as DrawDivergence above, but tagged separately
        // ("cvdDtDbDiv..." vs "cvdFracDiv...") so the two draw paths can never collide —
        // mutually exclusive at runtime (this replaces the fractal block entirely when
        // on), but kept visually distinct on principle. bearish = IsTop (a confirmed DT
        // the scanner's own CVD agreed with is the bearish case here, same convention
        // as the fractal block's hLast/hPrev branch).
        private void DrawFromDtDbRegistry()
        {
            List<DtDbCvdPivot> fresh = DtDbCvdPivotRegistry.GetSince(_lastSeenDtDbId);
            foreach (DtDbCvdPivot p in fresh)
            {
                _lastSeenDtDbId = p.Id;
                if (p.P1Bar < 0 || p.P2Bar < 0 || p.P1Bar > CurrentBar || p.P2Bar > CurrentBar) continue;

                bool bearish = p.IsTop;
                System.Windows.Media.Brush color = bearish ? BearColor : BullColor;
                string tag = (bearish ? "cvdDtDbDivBear_" : "cvdDtDbDivBull_") + p.P1Bar + "_" + p.P2Bar;
                int baA = CurrentBar - p.P1Bar, baB = CurrentBar - p.P2Bar;

                Draw.Line(this, tag, false, baA, p.P1Price, baB, p.P2Price, color, DashStyleHelper.Solid, 2);
                if (ShowLabels)
                {
                    double off = 8 * (TickSize > 0 ? TickSize : 0.25);
                    Draw.Text(this, tag + "_txt", false, bearish ? "-RD" : "+RD", baB,
                              bearish ? p.P2Price + off : p.P2Price - off, 0, color,
                              new SimpleFont("Arial", DivLabelFontSize), System.Windows.TextAlignment.Center,
                              Brushes.Transparent, Brushes.Transparent, 0);
                }

                double histA = p.P1Bar <= CurrentBar ? histSeries[CurrentBar - p.P1Bar] : 0.0;
                double histB = p.P2Bar <= CurrentBar ? histSeries[CurrentBar - p.P2Bar] : 0.0;
                marks.Add(new DivMark { barA = p.P1Bar, barB = p.P2Bar, histA = histA, histB = histB, bearish = bearish });
            }
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

        // Was a CvdCumulativeMode enum (shared from BidAskSharedEnums.cs) — converted to a
        // bool 2026-10-28 so this file has zero companion-file dependency: Thomas (or anyone
        // else) can deploy just this one .cs and compile, no second file needed. Enums must
        // live in the NinjaTrader.NinjaScript namespace for NT8's generator to resolve them in
        // sibling namespaces (see BidAskSharedEnums.cs's header) — primitives like bool don't
        // have that constraint, so there was never a real reason this needed to be an enum.
        [NinjaScriptProperty]
        [Display(Name = "Use EMA Mode", Description = "Unchecked (default) = Periodic, rolling SUM of delta over CVD Period bars; Checked = EMA of delta over CVD Period bars",
                 GroupName = "1. Logic Setting", Order = 2)]
        public bool UseEmaMode { get; set; }

        // 2026-10-29: when ON, replaces this indicator's own independent fractal-pivot
        // divergence detection with DtDbScannerV3's confirmed DT/DB pivots (shared via
        // DtDbCvdPivotRegistry.cs — requires DtDbScannerV3.cs running on the SAME chart,
        // publishing, which only happens when ITS OWN bar-proxy CVD agrees with the
        // pattern's bias). Off by default — this file stays standalone/fractal-only
        // unless explicitly turned on. NOTE: turning this on re-introduces a companion-
        // file dependency (DtDbCvdPivotRegistry.cs, and functionally DtDbScannerV3.cs)
        // that CvdCumulativeMode's removal on 2026-10-28 specifically eliminated — if
        // Thomas only needs the standalone fractal-divergence view, he does NOT need
        // either extra file; this toggle is the one feature that needs them.
        [NinjaScriptProperty]
        [Display(Name = "Only show at DT/DB (requires DtDbScannerV3)", Description = "Replaces this indicator's own fractal-pivot divergence detection with DtDbScannerV3's confirmed DT/DB pivots (only the ones where DtDbScannerV3's own CVD check agrees). Requires DtDbScannerV3 + DtDbCvdPivotRegistry.cs on the same chart.",
                 GroupName = "1. Logic Setting", Order = 3)]
        public bool OnlyShowAtDtDb { get; set; }

        [NinjaScriptProperty]
        [Range(2, 500)]
        [Display(Name = "Trend EMA Period", Description = "EMA of Close used as the trend filter a fractal pivot must agree with (Pine: hardcoded 50)",
                 GroupName = "1. Logic Setting", Order = 4)]
        public int TrendEmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Max Pivot Gap (bars)", Description = "Two fractal pivots further apart than this are never compared for divergence (Pine: hardcoded 30)",
                 GroupName = "1. Logic Setting", Order = 5)]
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
