// BidAskVolumeRatio.cs — port of Sierra Chart's "Bid Ask Volume Ratio" study
// (sierrachart.com doc/StudiesReference.php?ID=230), verified against their docs, not guessed.
//
// FORMULA (Sierra's own spec, quoted):
//   "This study calculates and displays a Moving Average of the Bid Ask Volume Ratio at
//   each chart bar." Per-bar raw ratio, toggle via "Difference Calculation Method":
//     Ask Volume - Bid Volume:  VR = 100 x (AskVol - BidVol) / (AskVol + BidVol)
//     Bid Volume - Ask Volume:  VR = 100 x (BidVol - AskVol) / (AskVol + BidVol)
//   (0 when AskVol+BidVol == 0), then smoothed by a selectable Moving Average
//   (Simple/Exponential/Weighted/LinearRegression/Wilders/Smoothed) over "Length" bars.
//   Output range ~ -100..+100; positive = ask-side (buy) volume dominant.
//
// CLASSIFICATION (standard tick rule, same pattern as NT8's own stock BuySellVolume
// indicator): each Last trade print is Ask-side if price >= the latest Ask, Bid-side if
// price <= the latest Bid; a print strictly between a stale/wide quote is left unclassified
// (matches the common NT8 community pattern — Sierra does not document its own tie rule).
//
// HONEST CAVEAT (mirrors Sierra's own documented limitation verbatim: "you may not
// receive historical Ask and Bid Volumes... not all services will provide this"):
// OnMarketData is a REAL-TIME-ONLY NinjaTrader event — it does not fire for historical
// bars. Every bar before this indicator was actually running live on a connected feed
// will show 0, not a reconstructed value. This is not a bug to fix; it is the same
// limitation Sierra documents for its own study.
//
// 2026-10-19 BACKFILL: the above is still true of OnMarketData itself, but a bar that has
// NO live tick data now falls back to data/bid_ask/bid_ask_vol_buckets.csv — built by
// scripts/backfill_bid_ask_log.py, which replays the recorded L1 tape (data/l1_tape/) into
// 1-second (ask_vol,bid_vol) buckets via the tape's own Aggr aggressor tag. Each bar sums
// exactly the buckets inside its own (prevBarClose, thisBarClose] window — bar-ACCURATE
// regardless of bar type (tick/time/renko), not a pre-baked guess at one granularity. A bar
// that received live ticks keeps using the live accumulators (accBar==CurrentBar), unchanged
// and exact; only bars that never went live fall back. Days with no backfill file still read
// 0, same as before. NOT guaranteed byte-identical to the live tick-rule (price vs last
// quote) — Aggr is the tape's own independently-resolved aggressor tag, a very close proxy.

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

namespace NinjaTrader.NinjaScript.Indicators.My
{
    public enum BavrDiffMethod { AskMinusBid, BidMinusAsk }
    public enum BavrMaType { Simple, Exponential, Weighted, LinearRegression, Wilders, Smoothed }

    public class BidAskVolumeRatio : Indicator
    {
        private double lastAsk, lastBid;
        private double curAskVol, curBidVol;
        private int    accBar = -1;   // CurrentBar the live accumulators belong to

        [XmlIgnore] [Browsable(false)] public Series<double> AskVol;
        [XmlIgnore] [Browsable(false)] public Series<double> BidVol;
        [XmlIgnore] [Browsable(false)] public Series<double> RawRatio;   // unsmoothed per-bar VR

        // ── L1-tape backfill for bars with no live tick data (2026-10-19) ──────────────
        private struct BidAskBucket { public DateTime ts; public double askVol, bidVol; }
        private const string BucketLogPath = @"C:\Users\Admin\myquant\data\bid_ask\bid_ask_vol_buckets.csv";
        private List<BidAskBucket> _buckets = new List<BidAskBucket>();
        private int _bucketCursor;
        // Shared across instances of THIS class within one NT8 session (not across the other
        // 3 indicator classes — each is a separate type with its own static cache) so adding
        // several of these to the same chart / reloading repeatedly doesn't re-parse a ~30MB
        // file every time; invalidated automatically if the backfill file's write time changes.
        private static List<BidAskBucket> _bucketsCache;
        private static DateTime _bucketsCacheFileTime = DateTime.MinValue;
        private TimeZoneInfo _ctTz;

        private void LoadBidAskBuckets()
        {
            _buckets = new List<BidAskBucket>(); _bucketCursor = 0;
            try { _ctTz = TimeZoneInfo.FindSystemTimeZoneById("Central Standard Time"); }
            catch { _ctTz = null; }
            if (!File.Exists(BucketLogPath)) return;

            DateTime fileTime = File.GetLastWriteTimeUtc(BucketLogPath);
            if (_bucketsCache != null && fileTime == _bucketsCacheFileTime)
            { _buckets = _bucketsCache; return; }

            var list = new List<BidAskBucket>();
            try
            {
                foreach (string line in File.ReadAllLines(BucketLogPath))
                {
                    if (line.Length == 0 || line[0] == 'd') continue;   // header: "date,..."
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
        }

        private DateTime ConvertToCt(DateTime t)
        {
            if (_ctTz == null) return t;
            TimeZoneInfo displayTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
            return displayTz.Equals(_ctTz) ? t : TimeZoneInfo.ConvertTime(t, displayTz, _ctTz);
        }

        // Sums every bucket with ts in (whatever the cursor already consumed, barCloseTime] —
        // a monotonic forward-only walk, correct because NT8 always calls OnBarUpdate in
        // strict chronological order (historical replay AND live) for a single primary series.
        private void AdvanceBucketCursor(DateTime barCloseTime, out double ask, out double bid)
        {
            ask = 0; bid = 0;
            if (_buckets.Count == 0) return;
            DateTime t = ConvertToCt(barCloseTime);
            while (_bucketCursor < _buckets.Count && _buckets[_bucketCursor].ts <= t)
            {
                ask += _buckets[_bucketCursor].askVol;
                bid += _buckets[_bucketCursor].bidVol;
                _bucketCursor++;
            }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Sierra Chart 'Bid Ask Volume Ratio' port: MA of 100x(AskVol-BidVol)/(AskVol+BidVol) per bar. REAL-TIME ONLY — OnMarketData does not fire on historical bars, so history before this indicator was running live on a connected feed reads 0 (same limitation Sierra documents for its own study).";
                Name        = "BidAskVolumeRatio";
                Calculate   = Calculate.OnEachTick;   // live-updating current bar, matches Sierra's live behavior
                IsOverlay   = false;
                DisplayInDataBox = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;

                DiffMethod = BavrDiffMethod.AskMinusBid;
                Length     = 14;
                MaType     = BavrMaType.Exponential;

                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Line, "VR MA");
                AddLine(Brushes.Gray, 0, "Zero");
            }
            else if (State == State.DataLoaded)
            {
                AskVol   = new Series<double>(this, MaximumBarsLookBack.Infinite);
                BidVol   = new Series<double>(this, MaximumBarsLookBack.Infinite);
                RawRatio = new Series<double>(this, MaximumBarsLookBack.Infinite);
                LoadBidAskBuckets();
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType == MarketDataType.Ask) { lastAsk = e.Price; return; }
            if (e.MarketDataType == MarketDataType.Bid) { lastBid = e.Price; return; }
            if (e.MarketDataType != MarketDataType.Last) return;

            if (CurrentBar != accBar) { curAskVol = 0; curBidVol = 0; accBar = CurrentBar; }

            if (lastAsk <= 0 || lastBid <= 0) return;   // quotes not seeded yet this session
            if (e.Price >= lastAsk)      curAskVol += e.Volume;
            else if (e.Price <= lastBid) curBidVol += e.Volume;
            // price strictly between a stale/wide bid-ask: left unclassified, same as the
            // standard NT8 tick-rule pattern (no documented Sierra tie-break to match).
        }

        protected override void OnBarUpdate()
        {
            double histAsk, histBid;
            AdvanceBucketCursor(Time[0], out histAsk, out histBid);
            bool liveThisBar = accBar == CurrentBar;
            double ask = liveThisBar ? curAskVol : histAsk;
            double bid = liveThisBar ? curBidVol : histBid;

            AskVol[0] = ask;
            BidVol[0] = bid;

            double denom = ask + bid;
            double sign  = DiffMethod == BavrDiffMethod.AskMinusBid ? 1.0 : -1.0;
            RawRatio[0]  = denom > 0 ? 100.0 * sign * (ask - bid) / denom : 0.0;

            Values[0][0] = ComputeMA();
        }

        private double ComputeMA()
        {
            int n = Math.Min(Length, CurrentBar + 1);
            if (n <= 0) return 0;

            switch (MaType)
            {
                case BavrMaType.Simple:
                {
                    double sum = 0;
                    for (int k = 0; k < n; k++) sum += RawRatio[k];
                    return sum / n;
                }
                case BavrMaType.Weighted:
                {
                    double sumW = 0, sum = 0;
                    for (int k = 0; k < n; k++) { double w = n - k; sum += RawRatio[k] * w; sumW += w; }
                    return sumW > 0 ? sum / sumW : 0;
                }
                case BavrMaType.LinearRegression:
                {
                    // least squares over the last n points (k=0 newest); value at the newest x
                    double sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
                    for (int k = 0; k < n; k++)
                    {
                        double x = n - 1 - k;   // oldest = 0, newest = n-1
                        double y = RawRatio[k];
                        sumX += x; sumY += y; sumXY += x * y; sumXX += x * x;
                    }
                    double denom = n * sumXX - sumX * sumX;
                    if (denom == 0) return RawRatio[0];
                    double slope = (n * sumXY - sumX * sumY) / denom;
                    double intercept = (sumY - slope * sumX) / n;
                    return intercept + slope * (n - 1);
                }
                default:   // Exponential / Wilders / Smoothed — all recursive, Wilders==Smoothed (alpha=1/Length)
                {
                    double alpha = MaType == BavrMaType.Exponential ? 2.0 / (Length + 1.0) : 1.0 / Length;
                    if (CurrentBar == 0) return RawRatio[0];
                    double prev = Values[0][1];
                    return prev + alpha * (RawRatio[0] - prev);
                }
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Difference Calculation Method", Description = "Ask Volume - Bid Volume (positive = ask dominant), or Bid Volume - Ask Volume (positive = bid dominant).", Order = 1, GroupName = "1. Parameters")]
        public BavrDiffMethod DiffMethod { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Length", Description = "Moving average period.", Order = 2, GroupName = "1. Parameters")]
        public int Length { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Moving Average Type", Description = "Simple, Exponential, Weighted, Linear Regression, Wilders, or Smoothed (Wilders and Smoothed use the same alpha=1/Length recursion).", Order = 3, GroupName = "1. Parameters")]
        public BavrMaType MaType { get; set; }

        [Browsable(false)] [XmlIgnore]
        public Series<double> VRMA { get { return Values[0]; } }
        #endregion
    }
}
