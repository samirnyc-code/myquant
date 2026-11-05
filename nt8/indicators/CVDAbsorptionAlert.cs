// CVDAbsorptionAlert — flags ABSORPTION, not divergence: a rolling window where real
// tick-classified volume was heavily one-sided but price didn't follow it. Built
// 2026-11-05 after the user manually spotted this exact pattern on a chart (a 2:59-
// 3:08 PM higher low on real heavy selling, absorbed, followed by a breakout) and
// asked for a programmatic alert instead of eyeballing it.
//
// WHY THIS ISN'T CVDRealDivergence.cs's existing fractal-pivot divergence: that
// detector requires price and CVD to form OPPOSING fractal pivots (e.g. price lower
// low + CVD higher low), confirmed n bars later, filtered by a trend EMA that
// explicitly excludes pivots on the "wrong" side of trend. The absorption case here
// is different and simpler: price barely moves (or moves the "wrong" way for the
// volume) while real volume is unusually heavy in one direction over a short rolling
// window -- no fractal pivot confirmation needed, no trend-EMA gate, just "effort
// without result."
//
// REAL DELTA SOURCE: identical plumbing to CVDRealDivergence.cs -- live OnMarketData
// tick classification (price vs ask/bid, midpoint tiebreak) going forward, L1-tape
// bucket backfill (data/bid_ask/bid_ask_vol_buckets.csv, via
// scripts/backfill_bid_ask_log.py) for historical bars. Copied, not shared, same
// reason CVDRealDivergence was kept standalone from CVDDivergenceOscillator --
// zero risk of this file's changes affecting the proven histogram indicator.
//
// "Significant volume" is adaptive: compares the rolling real-delta sum's own
// magnitude to its recent StdDev (StdDevLookback bars), not a fixed number -- a fixed
// threshold would need re-tuning every time overall volume/volatility regime shifts.
//
// Latches per episode (BullActive/BearActive) so a condition that holds for several
// bars fires once, not every bar -- resets only once the condition clears.
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
        private Series<double> rollingSum;

        // ---- live per-bar delta accumulation (identical to CVDRealDivergence.cs) ----
        private int accumBar = -1;
        private double barDelta;

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

        private bool bullActive, bearActive;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "CVDAbsorptionAlert";
                Description = "Flags real-volume absorption: heavy one-sided tick-classified volume over a rolling window that price didn't follow -- not divergence, no pivot confirmation needed";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = true;

                AbsorptionLookback = 10;
                StdDevLookback = 100;
                ThresholdMultiplier = 1.5;
                FlatPriceMoveTicks = 4;

                ShowMarkers = true;
                PlaySound = true;
                MarkerFontSize = 10;
                BullColor = Brushes.LimeGreen;
                BearColor = Brushes.Firebrick;
            }
            else if (State == State.Configure)
            {
                deltaSeries = new Series<double>(this);
                rollingSum = new Series<double>(this);
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

            int minBarsNeeded = Math.Max(AbsorptionLookback, StdDevLookback) + 1;
            if (CurrentBar < minBarsNeeded)
            {
                rollingSum[0] = 0;
                return;
            }

            rollingSum[0] = SUM(deltaSeries, AbsorptionLookback)[0];
            double baseline = StdDev(rollingSum, StdDevLookback)[0];
            if (baseline <= 0) return;   // not enough variation yet to judge "significant"

            double threshold = baseline * ThresholdMultiplier;
            int backBar = Math.Min(AbsorptionLookback, CurrentBar);
            double priceMove = Close[0] - Close[backBar];
            double flat = FlatPriceMoveTicks * (TickSize > 0 ? TickSize : 0.25);

            bool bullCondition = rollingSum[0] <= -threshold && priceMove >= -flat;
            bool bearCondition = rollingSum[0] >= threshold && priceMove <= flat;

            if (bullCondition && !bullActive)
            {
                bullActive = true; bearActive = false;
                Mark(true, rollingSum[0], priceMove);
            }
            else if (!bullCondition) bullActive = false;

            if (bearCondition && !bearActive)
            {
                bearActive = true; bullActive = false;
                Mark(false, rollingSum[0], priceMove);
            }
            else if (!bearCondition) bearActive = false;
        }

        private void Mark(bool bullish, double sumVal, double priceMove)
        {
            System.Windows.Media.Brush color = bullish ? BullColor : BearColor;
            string tag = (bullish ? "cvdAbsorbBull_" : "cvdAbsorbBear_") + CurrentBar;

            if (ShowMarkers)
            {
                double off = 6 * (TickSize > 0 ? TickSize : 0.25);
                double y = bullish ? Low[0] - off : High[0] + off;
                if (bullish) Draw.ArrowUp(this, tag, false, 0, y, color);
                else Draw.ArrowDown(this, tag, false, 0, y, color);
                Draw.Text(this, tag + "_txt", false, bullish ? "ABS+" : "ABS-", 0,
                          bullish ? y - off : y + off, 0, color,
                          new SimpleFont("Arial", MarkerFontSize), System.Windows.TextAlignment.Center,
                          Brushes.Transparent, Brushes.Transparent, 0);
            }

            if (PlaySound)
            {
                string msg = (bullish ? "Bullish" : "Bearish") + " CVD absorption: real delta sum "
                             + sumVal.ToString("F0") + " vs price move " + priceMove.ToString("F2");
                Alert(tag, Priority.High, msg, @"Alert1.wav", 10, Brushes.Black,
                      bullish ? Brushes.LightGreen : Brushes.LightSalmon);
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(2, 200)]
        [Display(Name = "Absorption Lookback (bars)", Description = "Rolling window for the real-delta sum being checked against price",
                 GroupName = "1. Logic Setting", Order = 0)]
        public int AbsorptionLookback { get; set; }

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "StdDev Lookback (bars)", Description = "Window used to judge what counts as an unusually large rolling-sum magnitude",
                 GroupName = "1. Logic Setting", Order = 1)]
        public int StdDevLookback { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10.0)]
        [Display(Name = "Threshold Multiplier", Description = "Rolling-sum magnitude must exceed this many StdDevs to count as significant",
                 GroupName = "1. Logic Setting", Order = 2)]
        public double ThresholdMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Flat Price Move (ticks)", Description = "Price is allowed to move up to this many ticks against the heavy side and still count as absorption",
                 GroupName = "1. Logic Setting", Order = 3)]
        public double FlatPriceMoveTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Markers", Description = "Draw ABS+/ABS- triangles on the price panel",
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

        [XmlIgnore]
        [Display(Name = "Bullish color", GroupName = "2. Display Setting", Order = 3)]
        public System.Windows.Media.Brush BullColor { get; set; }
        [Browsable(false)]
        public string BullColorSerialize { get { return Serialize.BrushToString(BullColor); } set { BullColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Bearish color", GroupName = "2. Display Setting", Order = 4)]
        public System.Windows.Media.Brush BearColor { get; set; }
        [Browsable(false)]
        public string BearColorSerialize { get { return Serialize.BrushToString(BearColor); } set { BearColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
