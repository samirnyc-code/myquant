// CVDRealDivergence — fractal-pivot CVD divergence, same algorithm as
// CVDDivergenceOscillator.cs, but fed by REAL tick-classified delta instead of a
// bar-OHLC proxy. Built 2026-10-28 because the user judged the OHLC-proxy version
// "garbage" and asked for real L1 data — explicitly WITHOUT touching any existing
// indicator (CVDDivergenceOscillator.cs, CumulativeDelta.cs, BidAskVolumeRatio.cs, etc.
// are all untouched; this is a new, separate file).
//
// REAL DELTA, TWO SOURCES, SAME TECHNIQUE CumulativeDelta.cs ALREADY USES (not
// reinvented — this is the same proven pattern, just repurposed from "cumulative
// candle" to "per-bar value feeding a divergence detector"):
//   - LIVE (today, going forward): OnMarketData classifies each tick buy/sell via the
//     embedded quote (Price >= Ask -> buy, Price <= Bid -> sell, else midpoint
//     tie-break) — same rule as FootprintExporter/CumulativeDelta.cs, accumulated into
//     the current bar's running delta.
//   - HISTORICAL (any day the recorder was running): reconstructed from
//     data/bid_ask/bid_ask_vol_buckets.csv — 1-second (ask_vol, bid_vol) buckets
//     derived from the recorded L1 tape's own Aggr aggressor tag (scripts/
//     backfill_bid_ask_log.py). Walking the buckets inside each bar's own
//     (prevBarClose, thisBarClose] time window and summing (askVol-bidVol) gives a
//     REAL per-bar delta from actual recorded trades — not a proxy. A bar with no
//     bucket coverage (recorder wasn't running that day/window) gets delta=0, not a
//     fabricated value — divergence pivots simply won't form across a coverage gap.
//
// NOT real-time-only like CumulativeDelta.cs's own divergence feature: that one has
// no historical backfill for its divergence tracker specifically (its backfill is for
// the CVD candle view only). This indicator backfills real delta for the DIVERGENCE
// detector itself, so pivots/divergences form on past days too, not just live.
//
// DELIBERATELY uses the plain NinjaTrader.NinjaScript.Indicators namespace, NOT
// ....Indicators.My — sidesteps the dual-copy Custom\Indicators\My\ deploy trap found
// 2026-10-28 (see nt8/README.md), no reason to opt into it for a brand-new file.
// Zero companion-file dependency (no shared enum file) for the same reason
// CVDDivergenceOscillator.cs was converted today — a 2-way mode switch is a bool.
//
// Divergence-detection logic (fractal pivots, trend-EMA filter, draw/render) is a
// direct copy of CVDDivergenceOscillator.cs's — same algorithm, intentionally, so the
// two are comparable apples-to-apples with only the delta source different.
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
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

namespace NinjaTrader.NinjaScript.Indicators
{
    public class CVDRealDivergence : Indicator
    {
        private Series<double> deltaSeries;
        private Series<double> histSeries;

        // ---- live per-bar delta accumulation (today, going forward) ----
        private int accumBar = -1;
        private double barDelta;

        // ---- L1-tape bucket backfill (historical bars) — same shape as
        // CumulativeDelta.cs's AdvanceCvdBuckets, but sums a LOCAL per-bar total
        // instead of a persistent running cumulative (this indicator wants "how much
        // real delta happened in this bar," not "cumulative since session start").
        private struct BidAskBucket { public DateTime ts; public double askVol, bidVol; }
        private const string BucketLogPath = @"C:\Users\Admin\myquant\data\bid_ask\bid_ask_vol_buckets.csv";
        private List<BidAskBucket> _buckets = new List<BidAskBucket>();
        private int _bucketCursor;
        private static List<BidAskBucket> _bucketsCache;
        private static DateTime _bucketsCacheFileTime = DateTime.MinValue;
        private TimeZoneInfo _ctTz;
        private DateTime _lastConsumedTs = DateTime.MinValue;
        private DateTime _lastBucketFileCheckUtc = DateTime.MinValue;

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
                Name = "CVDRealDivergence";
                Description = "CVD fractal divergence from REAL tick-classified delta (live OnMarketData + L1-tape bucket backfill for history) — not the OHLC-proxy CVDDivergenceOscillator.cs";
                Calculate = Calculate.OnEachTick;    // needed so OnMarketData keeps accumulating live delta
                IsOverlay = false;
                DrawOnPricePanel = true;             // lets Draw.Line/Draw.Text reach the price panel for the divergence markers
                DisplayInDataBox = true;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = true;

                DivergenceFractalPeriods = 2;
                CvdPeriod = 21;
                UseEmaMode = false; // false = Periodic (rolling SUM), true = EMA
                TrendEmaPeriod = 50;
                MaxPivotGapBars = 30;

                ShowLabels = true;
                DivLabelFontSize = 10;
                BullColor = Brushes.LimeGreen;
                BearColor = Brushes.Firebrick;
                // .Freeze() both — same reason as CVDDivergenceOscillator.cs: an unfrozen
                // WPF Freezable assigned to PlotBrushes[] from a different thread than it
                // was constructed on throws "calling thread cannot access this object."
                var posHist = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(140, 76, 175, 79));
                posHist.Freeze();
                PosHistColor = posHist;
                var negHist = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(140, 255, 82, 82));
                negHist.Freeze();
                NegHistColor = negHist;

                AddPlot(new Stroke(Brushes.Gray, 2), PlotStyle.Bar, "CVD Hist (real)");
            }
            else if (State == State.Configure)
            {
                deltaSeries = new Series<double>(this);
                histSeries = new Series<double>(this);
            }
            else if (State == State.DataLoaded)
            {
                LoadBuckets();
            }
        }

        private void LoadBuckets()
        {
            _buckets = new List<BidAskBucket>(); _bucketCursor = 0; _lastConsumedTs = DateTime.MinValue;
            try { _ctTz = TimeZoneInfo.FindSystemTimeZoneById("Central Standard Time"); }
            catch { _ctTz = null; }
            ReadBucketFile();
        }

        // Re-checked every AdvanceDeltaBuckets call, throttled to once per 30s (same
        // pattern as CumulativeDelta.cs/BidAskVolumeRatio.cs) — re-seeks the cursor by
        // TIMESTAMP on a file change instead of re-adding already-consumed buckets.
        private void ReadBucketFile()
        {
            if (!File.Exists(BucketLogPath)) return;

            DateTime fileTime = File.GetLastWriteTimeUtc(BucketLogPath);
            if (_bucketsCache != null && fileTime == _bucketsCacheFileTime)
            {
                if (!ReferenceEquals(_buckets, _bucketsCache)) { _buckets = _bucketsCache; ReseekCursor(); }
                return;
            }

            var list = new List<BidAskBucket>();
            try
            {
                foreach (string line in File.ReadAllLines(BucketLogPath))
                {
                    if (line.Length == 0 || line[0] == 'd') continue;
                    string[] p = line.Split(',');
                    if (p.Length < 4) continue;
                    DateTime ts; double a, b;
                    if (DateTime.TryParse(p[1], CultureInfo.InvariantCulture, DateTimeStyles.None, out ts)
                        && double.TryParse(p[2], NumberStyles.Any, CultureInfo.InvariantCulture, out a)
                        && double.TryParse(p[3], NumberStyles.Any, CultureInfo.InvariantCulture, out b))
                        list.Add(new BidAskBucket { ts = ts, askVol = a, bidVol = b });
                }
                list.Sort((x, y) => x.ts.CompareTo(y.ts));
            }
            catch (Exception ex) { Print(Name + ": could not read bid/ask bucket log: " + ex.Message); return; }

            _bucketsCache = list; _bucketsCacheFileTime = fileTime;
            _buckets = list;
            ReseekCursor();
        }

        private void ReseekCursor()
        {
            _bucketCursor = 0;
            while (_bucketCursor < _buckets.Count && _buckets[_bucketCursor].ts <= _lastConsumedTs)
                _bucketCursor++;
        }

        private DateTime ConvertToCt(DateTime t)
        {
            if (_ctTz == null) return t;
            TimeZoneInfo displayTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
            return displayTz.Equals(_ctTz) ? t : TimeZoneInfo.ConvertTime(t, displayTz, _ctTz);
        }

        // Walks every unconsumed bucket up to barCloseTime, summing (askVol-bidVol) into
        // a LOCAL per-bar total (not a persistent cumulative — this indicator wants this
        // bar's own real delta, matching CVDDivergenceOscillator.cs's deltaSeries[0]
        // shape). `any` is false if nothing was consumed (no bucket coverage for this
        // bar's window) — caller leaves delta at 0 rather than fabricating a value.
        private void AdvanceDeltaBuckets(DateTime barCloseTime, out double sum, out bool any)
        {
            sum = 0; any = false;
            if ((DateTime.UtcNow - _lastBucketFileCheckUtc).TotalSeconds >= 30)
            { _lastBucketFileCheckUtc = DateTime.UtcNow; ReadBucketFile(); }
            if (_buckets.Count == 0) return;
            DateTime t = ConvertToCt(barCloseTime);
            while (_bucketCursor < _buckets.Count && _buckets[_bucketCursor].ts <= t)
            {
                sum += _buckets[_bucketCursor].askVol - _buckets[_bucketCursor].bidVol;
                _lastConsumedTs = _buckets[_bucketCursor].ts;
                _bucketCursor++;
                any = true;
            }
        }

        // classify each trade exactly like FootprintExporter/CumulativeDelta.cs (quote
        // embedded in the tick) — accumulates into the CURRENT bar's running delta.
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last || CurrentBar < 0) return;

            if (accumBar != CurrentBar) { accumBar = CurrentBar; barDelta = 0; }

            long v = (long)e.Volume;
            if (v <= 0) return;
            double ask = e.Ask, bid = e.Bid; bool buy;
            if (ask > 0 && bid > 0)
            {
                if (e.Price >= ask) buy = true;
                else if (e.Price <= bid) buy = false;
                else buy = e.Price >= (ask + bid) / 2.0;
            }
            else buy = true;
            barDelta += buy ? v : -v;
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 0) return;

            bool liveThisBar = accumBar == CurrentBar;
            double delta;
            if (liveThisBar)
            {
                delta = barDelta;
            }
            else
            {
                double sum; bool any;
                AdvanceDeltaBuckets(Time[0], out sum, out any);
                delta = any ? sum : 0.0;
            }
            deltaSeries[0] = delta;

            double hist = UseEmaMode
                ? EMA(deltaSeries, CvdPeriod)[0]
                : SUM(deltaSeries, CvdPeriod)[0];
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

        private void DrawDivergence(int barA, double priceA, double histA, int barB, double priceB, double histB, bool bearish)
        {
            System.Windows.Media.Brush color = bearish ? BearColor : BullColor;
            string tag = (bearish ? "cvdRealDivBear_" : "cvdRealDivBull_") + barA + "_" + barB;
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
        [Display(Name = "Divergence Fractal Periods", Description = "Bars required on each side of a swing high/low before it confirms as a pivot",
                 GroupName = "1. Logic Setting", Order = 0)]
        public int DivergenceFractalPeriods { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "CVD Period", Description = "Rolling-sum window (Periodic mode) or smoothing length (EMA mode) applied to the real per-bar delta",
                 GroupName = "1. Logic Setting", Order = 1)]
        public int CvdPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Use EMA Mode", Description = "Unchecked (default) = Periodic, rolling SUM of delta over CVD Period bars; Checked = EMA of delta over CVD Period bars",
                 GroupName = "1. Logic Setting", Order = 2)]
        public bool UseEmaMode { get; set; }

        [NinjaScriptProperty]
        [Range(2, 500)]
        [Display(Name = "Trend EMA Period", Description = "EMA of Close used as the trend filter a fractal pivot must agree with",
                 GroupName = "1. Logic Setting", Order = 3)]
        public int TrendEmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Max Pivot Gap (bars)", Description = "Two fractal pivots further apart than this are never compared for divergence",
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
