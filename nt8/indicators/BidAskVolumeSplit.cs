// BidAskVolumeSplit.cs — "candidate panel 3" from scripts/bid_ask_volume_ratio_renko.py's
// 3-panel comparison: raw AskVol and BidVol per bar, BOTH POSITIVE, twin bars (Ask above
// zero, Bid plotted negative so it renders below zero) -- total activity per side, not a
// net figure like BidAskVolumeDelta.cs or the bounded ratio in BidAskVolumeRatio.cs. Ported
// to NT8 per S142 (see docs/living/handoff.md); classification/caveats identical to the
// other two.
//
// CLASSIFICATION (same tick rule as BidAskVolumeRatio.cs): each Last print is Ask-side if
// price >= the latest Ask, Bid-side if price <= the latest Bid; strictly-between prints on a
// stale/wide quote are left unclassified.
//
// HONEST CAVEAT (same as BidAskVolumeRatio.cs): OnMarketData is REAL-TIME-ONLY in NinjaTrader
// — it does not fire for historical bars, so every bar before this indicator was actually
// running live on a connected feed reads 0.
//
// 2026-10-19 BACKFILL: same mechanism as BidAskVolumeRatio.cs — a bar with no live tick data
// now falls back to data/bid_ask/bid_ask_vol_buckets.csv (scripts/backfill_bid_ask_log.py,
// 1-second buckets from the recorded L1 tape's own Aggr aggressor tag). Also fixed the same
// near-invisible LightGray default on the "Bid Vol" plot (-> Firebrick) found while fixing
// BidAskVolumeDelta.cs's identical bug.

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
    public class BidAskVolumeSplit : Indicator
    {
        private double curAskVol, curBidVol;
        private int    accBar = -1;   // CurrentBar the live accumulators belong to

        // ── L1-tape backfill for bars with no live tick data (2026-10-19) ──────────────
        private struct BidAskBucket { public DateTime ts; public double askVol, bidVol; }
        private const string BucketLogPath = @"C:\Users\Admin\myquant\data\bid_ask\bid_ask_vol_buckets.csv";
        private List<BidAskBucket> _buckets = new List<BidAskBucket>();
        private int _bucketCursor;
        private static List<BidAskBucket> _bucketsCache;
        private static DateTime _bucketsCacheFileTime = DateTime.MinValue;
        private TimeZoneInfo _ctTz;
        private DateTime _lastConsumedTs = DateTime.MinValue;
        private DateTime _lastBucketFileCheckUtc = DateTime.MinValue;

        private void LoadBidAskBuckets()
        {
            _buckets = new List<BidAskBucket>(); _bucketCursor = 0; _lastConsumedTs = DateTime.MinValue;
            try { _ctTz = TimeZoneInfo.FindSystemTimeZoneById("Central Standard Time"); }
            catch { _ctTz = null; }
            ReadBucketFile();
        }

        // 2026-10-20 FIX: see BidAskVolumeRatio.cs's ReadBucketFile for the full root-cause
        // note — this used to be a one-shot load at State.DataLoaded, so the cursor walked off
        // the end of a frozen snapshot and flatlined forever regardless of later backfill
        // refreshes. Now re-checked every AdvanceBucketCursor, throttled to once per 30s, and
        // re-seeks the cursor by TIMESTAMP via ReseekCursor so nothing is ever double-counted.
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

        private void AdvanceBucketCursor(DateTime barCloseTime, out double ask, out double bid)
        {
            ask = 0; bid = 0;
            if ((DateTime.UtcNow - _lastBucketFileCheckUtc).TotalSeconds >= 30)
            { _lastBucketFileCheckUtc = DateTime.UtcNow; ReadBucketFile(); }
            if (_buckets.Count == 0) return;
            DateTime t = ConvertToCt(barCloseTime);
            while (_bucketCursor < _buckets.Count && _buckets[_bucketCursor].ts <= t)
            {
                ask += _buckets[_bucketCursor].askVol;
                bid += _buckets[_bucketCursor].bidVol;
                _lastConsumedTs = _buckets[_bucketCursor].ts;
                _bucketCursor++;
            }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Candidate panel 3 of 3 (see BidAskVolumeRatio.cs/BidAskVolumeDelta.cs): raw AskVol (positive) and BidVol (plotted negative) per bar, twin bars, not net. REAL-TIME ONLY — history before this indicator was running live reads 0.";
                Name        = "BidAskVolumeSplit";
                Calculate   = Calculate.OnEachTick;
                IsOverlay   = false;
                DisplayInDataBox = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;

                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Bar, "Ask Vol");
                AddPlot(new Stroke(Brushes.Firebrick, 2), PlotStyle.Bar, "Bid Vol");
                AddLine(Brushes.Gray, 0, "Zero");
            }
            else if (State == State.DataLoaded)
            {
                LoadBidAskBuckets();
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last) return;

            if (CurrentBar != accBar) { curAskVol = 0; curBidVol = 0; accBar = CurrentBar; }

            // 2026-10-19 FIX: see BidAskVolumeRatio.cs's OnMarketData for the full root-cause
            // note — was caching lastAsk/lastBid from separate MarketDataType.Ask/Bid push
            // events that this chart's indicator pipeline wasn't reliably delivering. e.Ask/
            // e.Bid are embedded in every Last event's own args; use those instead (same fix
            // as BidAskVolumeRatio.cs / BidAskVolumeDelta.cs, matches CumulativeDelta.cs).
            double ask = e.Ask, bid = e.Bid;
            if (ask <= 0 || bid <= 0) return;   // quotes not seeded yet this session
            if (e.Price >= ask)      curAskVol += e.Volume;
            else if (e.Price <= bid) curBidVol += e.Volume;
        }

        protected override void OnBarUpdate()
        {
            double histAsk, histBid;
            AdvanceBucketCursor(Time[0], out histAsk, out histBid);
            // 2026-10-20 FIX: see BidAskVolumeRatio.cs's OnBarUpdate for the full root-cause
            // note — accBar==CurrentBar alone doesn't prove this bar's ask/bid are real; a
            // quote-feed hiccup (trades print, embedded Ask/Bid momentarily invalid) left
            // curAskVol/curBidVol at 0 while still being treated as "live", permanently
            // locking out the bucket fallback for that bar.
            bool liveThisBar = accBar == CurrentBar && (curAskVol + curBidVol) > 0;
            double ask = liveThisBar ? curAskVol : histAsk;
            double bid = liveThisBar ? curBidVol : histBid;

            Values[0][0] =  ask;
            Values[1][0] = -bid;
        }

        #region Properties
        [Browsable(false)] [XmlIgnore]
        public Series<double> AskVolPlot { get { return Values[0]; } }

        [Browsable(false)] [XmlIgnore]
        public Series<double> BidVolPlot { get { return Values[1]; } }
        #endregion
    }
}
