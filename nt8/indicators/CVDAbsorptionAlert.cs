// CVDAbsorptionAlert — flags HIDDEN CVD divergence: price makes a HIGHER low while
// real CVD makes a LOWER low (bullish continuation), or the mirror bearish case. This
// is the standard-TA name for the pattern the user spotted by hand on a chart (price
// held a 2:59-3:08 PM higher low while real CVD plunged deeper than its prior leg,
// then broke out) and asked for a programmatic alert instead of eyeballing it.
//
// REWRITTEN 2026-11-05 (v2): the original v1 used a sliding N-bar window evaluated
// EVERY bar -- it fired on the first random bounce off any low (confirmed live: it
// marked the 2:59 PM initial low, not the 3:08 PM retest), because "price isn't
// currently falling" is true at nearly every small bounce, not just real retests.
// v2 anchors to CONFIRMED FRACTAL PIVOTS instead (same n-bar-each-side confirmation
// CVDRealDivergence.cs already uses) -- it can only ever fire exactly ON a confirmed
// pivot bar, by construction, not on an arbitrary intermediate bar. The CVD side is
// also no longer a fixed-width window: it's the SUM of real delta across the ENTIRE
// leg between the two pivots (whatever that leg's actual length), so a short sharp
// leg and a long slow leg are both measured on their own real terms.
//
// WHY THIS ISN'T CVDRealDivergence.cs's existing (REGULAR) divergence: that detector
// requires price LOWER low + CVD HIGHER low (reversal), filtered by a trend EMA that
// requires price BELOW the trend EMA -- which would exclude this exact case, since a
// higher low inside an ongoing/resuming uptrend sits ABOVE a rising trend EMA by
// construction. HIDDEN divergence (price HIGHER low + CVD LOWER low = continuation)
// needs the opposite price comparison and the opposite trend-EMA side, so it's
// implemented here rather than bolted onto the proven regular-divergence file.
//
// REAL DELTA SOURCE: identical plumbing to CVDRealDivergence.cs -- live OnMarketData
// tick classification (price vs ask/bid, midpoint tiebreak) going forward, L1-tape
// bucket backfill (data/bid_ask/bid_ask_vol_buckets.csv, via
// scripts/backfill_bid_ask_log.py) for historical bars. Copied, not shared, same
// reason CVDRealDivergence was kept standalone from CVDDivergenceOscillator --
// zero risk of this file's changes affecting the proven histogram indicator.
//
// No fixed magnitude threshold: "significant" is leg-vs-leg relative (this leg's real
// delta at least as extreme as the prior leg's), self-adaptive to whatever volume
// regime the symbol is in. Each pivot bar is evaluated exactly once -- CurrentBar-n
// strictly advances, so there's no need for a separate once-per-episode latch.
//
// Overlay-only (IsOverlay = true): draws markers on the price panel. Pair with
// CVDRealDivergence.cs on a separate panel for the histogram visual this reacts to --
// this indicator does not plot its own histogram, by design, to avoid duplicating it.
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
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class CVDAbsorptionAlert : Indicator
    {
        private Series<double> deltaSeries;

        // ---- live per-bar delta accumulation (identical to CVDRealDivergence.cs) ----
        private int accumBar = -1;
        private double barDelta;

        // ---- confirmed fractal pivots (same algorithm as CVDRealDivergence.cs's
        // hLastBar/lLastBar tracking, but storing the LEG sum of real delta into each
        // pivot instead of a fixed-window histogram snapshot) ----
        private int lLastBar = -1, lPrevBar = -1;
        private double lLastPrice = double.NaN, lPrevPrice = double.NaN;
        private double lLastLeg = double.NaN, lPrevLeg = double.NaN;

        private int hLastBar = -1, hPrevBar = -1;
        private double hLastPrice = double.NaN, hPrevPrice = double.NaN;
        private double hLastLeg = double.NaN, hPrevLeg = double.NaN;

        // ---- L1-tape bucket backfill (identical to CVDRealDivergence.cs) ----
        private struct BidAskBucket { public DateTime ts; public double askVol, bidVol; }
        private const string BucketLogPath = @"C:\Users\Admin\myquant\data\bid_ask\bid_ask_vol_buckets.csv";
        private List<BidAskBucket> _buckets = new List<BidAskBucket>();
        private int _bucketCursor;
        private static List<BidAskBucket> _bucketsCache;
        private static DateTime _bucketsCacheFileTime = DateTime.MinValue;
        private TimeZoneInfo _ctTz;
        private DateTime _lastConsumedTs = DateTime.MinValue;
        private DateTime _lastBucketFileCheckUtc = DateTime.MinValue;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "CVDAbsorptionAlert";
                Description = "Flags HIDDEN CVD divergence: price higher-low + real CVD lower-low (bullish continuation), or the mirror bearish case, confirmed on fractal pivots";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = true;
                // 2026-11-05: was true, copied unexamined from CVDRealDivergence.cs. NT8 suspends
                // OnBarUpdate (and everything inside it, incl. every Print) on this setting whenever
                // the chart isn't the focused/active tab -- plausible real cause of a persistent
                // ZERO debug-line report (not wrong pivots, no pivots detected AT ALL) while looking
                // at the Output window instead of this exact chart tab.
                IsSuspendedWhileInactive = false;

                FractalPeriods = 2;
                MaxPivotGapBars = 30;
                TrendEmaPeriod = 50;
                RequireTrendFilter = true;

                // 2026-11-05: additive second mode, OFF by default -- per-bar footprint-style
                // absorption, independent of the pivot logic above (untouched). See
                // EnablePerBarClose's own Display Description and the OnBarUpdate block below.
                EnablePerBarClose = false;
                PerBarLookback = 50;
                PerBarThresholdMultiplier = 1.5;
                PerBarCloseThreshold = 0.5;

                ShowMarkers = true;
                PlaySound = true;
                MarkerFontSize = 10;
                MarkerOffsetTicks = 6;
                DebugPrint = false;
                BullColor = Brushes.LimeGreen;
                BearColor = Brushes.Firebrick;
            }
            else if (State == State.Configure)
            {
                deltaSeries = new Series<double>(this);
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

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last || CurrentBar < 0) return;

            if (accumBar != CurrentBar)
            {
                accumBar = CurrentBar;
                double seed; bool any;
                AdvanceDeltaBuckets(e.Time, out seed, out any);
                barDelta = any ? seed : 0;
            }

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

            int n = FractalPeriods;
            if (CurrentBar < 2 * n + 1) return;

            double emaNow = EMA(Close, TrendEmaPeriod)[0];

            // ---- pivot LOW confirmed n bars ago -> hidden BULLISH check ----
            if (IsPivotLow(n))
            {
                int pivotBar = CurrentBar - n;
                double price = Low[n];

                // trend filter INVERTED vs regular divergence: hidden bullish is a pullback
                // INSIDE an uptrend, so price should be ABOVE the trend EMA, not below it.
                bool trendOk = !RequireTrendFilter || Close[n] > emaNow;

                double leg = lLastBar >= 0 ? SumDeltaBetween(lLastBar, pivotBar) : double.NaN;

                if (trendOk)
                {
                    lPrevBar = lLastBar; lPrevPrice = lLastPrice; lPrevLeg = lLastLeg;
                    lLastBar = pivotBar; lLastPrice = price; lLastLeg = leg;

                    if (DebugPrint)
                        Print(string.Format("{0} LOW pivot bar={1} price={2} leg={3:F0} | prev bar={4} price={5} leg={6:F0}",
                                             Time[n], lLastBar, lLastPrice, lLastLeg, lPrevBar, lPrevPrice, lPrevLeg));

                    // hidden bullish: price HOLDS/HIGHER low, but real selling into it was AS
                    // HEAVY OR HEAVIER than the leg into the prior low -- effort without result.
                    if (lPrevBar >= 0 && (lLastBar - lPrevBar) < MaxPivotGapBars
                        && lLastPrice >= lPrevPrice && lLastLeg <= lPrevLeg && lLastLeg < 0)
                    {
                        Mark(true, lLastLeg, lLastPrice - lPrevPrice, lPrevBar, lLastBar);
                    }
                }
            }

            // ---- pivot HIGH confirmed n bars ago -> hidden BEARISH check (mirror) ----
            if (IsPivotHigh(n))
            {
                int pivotBar = CurrentBar - n;
                double price = High[n];
                bool trendOk = !RequireTrendFilter || Close[n] < emaNow;

                double leg = hLastBar >= 0 ? SumDeltaBetween(hLastBar, pivotBar) : double.NaN;

                if (trendOk)
                {
                    hPrevBar = hLastBar; hPrevPrice = hLastPrice; hPrevLeg = hLastLeg;
                    hLastBar = pivotBar; hLastPrice = price; hLastLeg = leg;

                    if (DebugPrint)
                        Print(string.Format("{0} HIGH pivot bar={1} price={2} leg={3:F0} | prev bar={4} price={5} leg={6:F0}",
                                             Time[n], hLastBar, hLastPrice, hLastLeg, hPrevBar, hPrevPrice, hPrevLeg));

                    // hidden bearish: price HOLDS/LOWER high, but real buying into it was AS
                    // HEAVY OR HEAVIER than the leg into the prior high.
                    if (hPrevBar >= 0 && (hLastBar - hPrevBar) < MaxPivotGapBars
                        && hLastPrice <= hPrevPrice && hLastLeg >= hPrevLeg && hLastLeg > 0)
                    {
                        Mark(false, hLastLeg, hLastPrice - hPrevPrice, hPrevBar, hLastBar);
                    }
                }
            }

            // ---- additive second mode (2026-11-05), independent of everything above ----
            // Footprint-style single-bar absorption: no pivot/swing required, evaluated once
            // per bar on IsFirstTickOfBar, reading only bar "1" (the one that just closed) --
            // never bar "0" (still forming), so this has none of the mid-bar tick-staleness
            // risk the pivot logic above has. Off by default (EnablePerBarClose); does not
            // alter any state the pivot logic above reads or writes.
            if (EnablePerBarClose && IsFirstTickOfBar && CurrentBar >= PerBarLookback + 1)
            {
                double thisDelta = deltaSeries[1];
                double baseline = StdDev(deltaSeries, PerBarLookback)[1];
                if (baseline > 0)
                {
                    double threshold = baseline * PerBarThresholdMultiplier;
                    double range = High[1] - Low[1];
                    if (range > 0)
                    {
                        double closePos = (Close[1] - Low[1]) / range;   // 0 = closed at low, 1 = closed at high
                        bool pbBullish = thisDelta <= -threshold && closePos >= PerBarCloseThreshold;
                        bool pbBearish = thisDelta >= threshold && closePos <= (1.0 - PerBarCloseThreshold);

                        if (DebugPrint)
                            Print(string.Format("{0} PERBAR bar={1} delta={2:F0} baseline={3:F0} thr={4:F0} closePos={5:F2} bull={6} bear={7}",
                                                 Time[1], CurrentBar - 1, thisDelta, baseline, threshold, closePos, pbBullish, pbBearish));

                        if (pbBullish) MarkPerBar(true, thisDelta, closePos);
                        else if (pbBearish) MarkPerBar(false, thisDelta, closePos);
                    }
                }
            }
        }

        // sums deltaSeries over every bar from fromBar to toBar inclusive (absolute bar
        // indices, CurrentBar-n style) -- the REAL leg delta across however long that leg
        // actually was, not a fixed-width window.
        private double SumDeltaBetween(int fromBar, int toBar)
        {
            double s = 0;
            for (int b = fromBar; b <= toBar; b++)
            {
                int ago = CurrentBar - b;
                if (ago < 0 || ago >= deltaSeries.Count) continue;
                s += deltaSeries[ago];
            }
            return s;
        }

        private bool IsPivotLow(int n)
        {
            double candidate = Low[n];
            for (int k = 1; k <= n; k++) if (Low[n - k] < candidate) return false;
            for (int k = 1; k <= n; k++) if (Low[n + k] <= candidate) return false;
            return true;
        }

        private bool IsPivotHigh(int n)
        {
            double candidate = High[n];
            for (int k = 1; k <= n; k++) if (High[n - k] > candidate) return false;
            for (int k = 1; k <= n; k++) if (High[n + k] >= candidate) return false;
            return true;
        }

        // marks at pivotBar (the confirmed, newer/second pivot -- the actual retest), not
        // always the current bar: pivotBar confirms n bars AFTER it forms, so by the time
        // Mark() runs, "0" would point at the wrong (current, later) bar.
        private void Mark(bool bullish, double legVal, double priceDelta, int prevPivotBar, int pivotBar)
        {
            System.Windows.Media.Brush color = bullish ? BullColor : BearColor;
            string tag = (bullish ? "cvdHiddenBull_" : "cvdHiddenBear_") + prevPivotBar + "_" + pivotBar;
            int barsAgo = CurrentBar - pivotBar;

            if (ShowMarkers)
            {
                double off = MarkerOffsetTicks * (TickSize > 0 ? TickSize : 0.25);
                double y = bullish ? Low[barsAgo] - off : High[barsAgo] + off;
                // one letter per line -- small, stacked, instead of a big arrow glyph
                string label = "A\nB\nS" + (bullish ? "\n+" : "\n-");
                Draw.Text(this, tag + "_txt", false, label, barsAgo, y, 0, color,
                          new SimpleFont("Arial", MarkerFontSize), System.Windows.TextAlignment.Center,
                          Brushes.Transparent, Brushes.Transparent, 0);
            }

            if (PlaySound)
            {
                string msg = (bullish ? "Bullish" : "Bearish") + " hidden CVD divergence: leg delta "
                             + legVal.ToString("F0") + ", price delta " + priceDelta.ToString("F2");
                Alert(tag, Priority.High, msg, @"Alert1.wav", 10, Brushes.Black,
                      bullish ? Brushes.LightGreen : Brushes.LightSalmon);
            }
        }

        // separate from Mark() on purpose -- different tag prefix, different label text
        // ("F/P" stacked instead of "A/B/S") so a per-bar-close hit is visually and
        // programmatically distinguishable from a pivot-based hidden-divergence hit, even
        // when both are enabled and firing on the same chart.
        private void MarkPerBar(bool bullish, double deltaVal, double closePos)
        {
            System.Windows.Media.Brush color = bullish ? BullColor : BearColor;
            string tag = (bullish ? "cvdFootprintBull_" : "cvdFootprintBear_") + (CurrentBar - 1);

            if (ShowMarkers)
            {
                double off = MarkerOffsetTicks * (TickSize > 0 ? TickSize : 0.25);
                double y = bullish ? Low[1] - off : High[1] + off;
                string label = "F\nP" + (bullish ? "\n+" : "\n-");
                Draw.Text(this, tag + "_txt", false, label, 1, y, 0, color,
                          new SimpleFont("Arial", MarkerFontSize), System.Windows.TextAlignment.Center,
                          Brushes.Transparent, Brushes.Transparent, 0);
            }

            if (PlaySound)
            {
                string msg = (bullish ? "Bullish" : "Bearish") + " per-bar CVD absorption: delta "
                             + deltaVal.ToString("F0") + ", close position " + closePos.ToString("F2");
                Alert(tag, Priority.High, msg, @"Alert1.wav", 10, Brushes.Black,
                      bullish ? Brushes.LightGreen : Brushes.LightSalmon);
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Fractal Periods", Description = "Bars required on each side of a swing high/low before it confirms as a pivot -- same meaning as CVDRealDivergence.cs's own setting",
                 GroupName = "1. Logic Setting", Order = 0)]
        public int FractalPeriods { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Max Pivot Gap (bars)", Description = "Two pivots further apart than this are never compared",
                 GroupName = "1. Logic Setting", Order = 1)]
        public int MaxPivotGapBars { get; set; }

        [NinjaScriptProperty]
        [Range(2, 500)]
        [Display(Name = "Trend EMA Period", Description = "EMA of Close used as the trend filter -- hidden bullish requires price ABOVE it, hidden bearish requires price BELOW it",
                 GroupName = "1. Logic Setting", Order = 2)]
        public int TrendEmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Require Trend Filter", Description = "When ON, only flags a hidden-bullish pivot above the trend EMA / hidden-bearish pivot below it -- turn off to see every leg-vs-leg match regardless of trend",
                 GroupName = "1. Logic Setting", Order = 3)]
        public bool RequireTrendFilter { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Per-Bar-Close Mode", Description = "Additive second detection mode: footprint-style single-bar absorption, no swing/pivot required -- independent of the pivot logic above, off by default",
                 GroupName = "3. Per-Bar-Close Setting", Order = 0)]
        public bool EnablePerBarClose { get; set; }

        [NinjaScriptProperty]
        [Range(10, 500)]
        [Display(Name = "Per-Bar Lookback (bars)", Description = "Window used to judge what counts as an unusually large single-bar real-delta magnitude",
                 GroupName = "3. Per-Bar-Close Setting", Order = 1)]
        public int PerBarLookback { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10.0)]
        [Display(Name = "Per-Bar Threshold Multiplier", Description = "This bar's |real delta| must exceed this many StdDevs of recent per-bar delta to count as heavy",
                 GroupName = "3. Per-Bar-Close Setting", Order = 2)]
        public double PerBarThresholdMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(0.5, 1.0)]
        [Display(Name = "Per-Bar Close Threshold", Description = "How far into the bar's own range the close must sit to count as \"didn't follow through\" -- 0.5 = at least the midpoint, 1.0 = at the extreme",
                 GroupName = "3. Per-Bar-Close Setting", Order = 3)]
        public double PerBarCloseThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Markers", Description = "Draw the stacked A/B/S +/- text on the price panel",
                 GroupName = "2. Display Setting", Order = 0)]
        public bool ShowMarkers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Play Sound Alert", Description = "Fire NT8's Alert() (sound + log) when a new absorption episode is flagged",
                 GroupName = "2. Display Setting", Order = 1)]
        public bool PlaySound { get; set; }

        [NinjaScriptProperty]
        [Range(6, 24)]
        [Display(Name = "Marker font size", GroupName = "2. Display Setting", Order = 2)]
        public int MarkerFontSize { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Marker offset (ticks)", Description = "Vertical distance from the bar's high/low to the marker text, in ticks",
                 GroupName = "2. Display Setting", Order = 3)]
        public double MarkerOffsetTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Debug print to Output window", Description = "Print every bar's rolling sum / threshold / retest check to NT8's Output window -- use this to see exactly which gate blocked a fire you expected",
                 GroupName = "2. Display Setting", Order = 4)]
        public bool DebugPrint { get; set; }

        [XmlIgnore]
        [Display(Name = "Bullish color", GroupName = "2. Display Setting", Order = 5)]
        public System.Windows.Media.Brush BullColor { get; set; }
        [Browsable(false)]
        public string BullColorSerialize { get { return Serialize.BrushToString(BullColor); } set { BullColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Bearish color", GroupName = "2. Display Setting", Order = 6)]
        public System.Windows.Media.Brush BearColor { get; set; }
        [Browsable(false)]
        public string BearColorSerialize { get { return Serialize.BrushToString(BearColor); } set { BearColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
