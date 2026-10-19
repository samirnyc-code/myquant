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
        private double lastAsk, lastBid;
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
            if (e.MarketDataType == MarketDataType.Ask) { lastAsk = e.Price; return; }
            if (e.MarketDataType == MarketDataType.Bid) { lastBid = e.Price; return; }
            if (e.MarketDataType != MarketDataType.Last) return;

            if (CurrentBar != accBar) { curAskVol = 0; curBidVol = 0; accBar = CurrentBar; }

            if (lastAsk <= 0 || lastBid <= 0) return;   // quotes not seeded yet this session
            if (e.Price >= lastAsk)      curAskVol += e.Volume;
            else if (e.Price <= lastBid) curBidVol += e.Volume;
        }

        protected override void OnBarUpdate()
        {
            double histAsk, histBid;
            AdvanceBucketCursor(Time[0], out histAsk, out histBid);
            bool liveThisBar = accBar == CurrentBar;
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
