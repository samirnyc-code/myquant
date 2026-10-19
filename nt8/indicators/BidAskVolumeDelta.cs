// BidAskVolumeDelta.cs — "candidate panel 2" from scripts/bid_ask_volume_ratio_renko.py's
// 3-panel comparison: per-bar AskVol - BidVol, RAW CONTRACTS, unbounded (not the +-100
// bounded ratio BidAskVolumeRatio.cs plots) -- closer in shape to a per-bar CVD spike than
// the ratio oscillator. Ported to NT8 alongside BidAskVolumeRatio.cs and BidAskVolumeSplit.cs
// per S142 (see docs/living/handoff.md); classification/caveats identical to BidAskVolumeRatio.cs.
//
// CLASSIFICATION (same tick rule as BidAskVolumeRatio.cs): each Last print is Ask-side if
// price >= the latest Ask, Bid-side if price <= the latest Bid; strictly-between prints on a
// stale/wide quote are left unclassified.
//
// HONEST CAVEAT (same as BidAskVolumeRatio.cs): OnMarketData is REAL-TIME-ONLY in NinjaTrader
// — it does not fire for historical bars, so every bar before this indicator was actually
// running live on a connected feed reads 0.
//
// 2026-10-19: DownColor's default was Brushes.LightGray — nearly invisible against NT8's dark
// panel background, so negative-delta bars WERE there, just unseeable; only the positive
// (UpColor) spikes ever registered visually, which read as "only blue bars every once in a
// while, that's it?" Fixed to Firebrick (matches CumulativeDelta.cs's own down-color
// convention). Separately: a RAW per-bar delta is inherently spikier/sparser-LOOKING than
// BidAskVolumeRatio's bounded %, because ask/bid volume on a given bar is usually fairly
// balanced (small net, short bar) — occasional lopsided bars are real signal, not a bug, but
// now at least both signs are visible.
//
// 2026-10-19 BACKFILL: same mechanism as BidAskVolumeRatio.cs — a bar with no live tick data
// now falls back to data/bid_ask/bid_ask_vol_buckets.csv (scripts/backfill_bid_ask_log.py,
// 1-second buckets from the recorded L1 tape's own Aggr aggressor tag). See that file's header
// for the full explanation; identical mechanism duplicated here (small, per-file, same pattern
// as every other small shared helper in this repo's NT8 indicators).

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
    public class BidAskVolumeDelta : Indicator
    {
        private double curAskVol, curBidVol;
        private int    accBar = -1;   // CurrentBar the live accumulators belong to

        [XmlIgnore] [Browsable(false)] public Series<double> AskVol;
        [XmlIgnore] [Browsable(false)] public Series<double> BidVol;

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
                Description = "Candidate panel 2 of 3 (see BidAskVolumeRatio.cs/BidAskVolumeSplit.cs): per-bar AskVol-BidVol, raw contracts, unbounded. REAL-TIME ONLY — history before this indicator was running live reads 0.";
                Name        = "BidAskVolumeDelta";
                Calculate   = Calculate.OnEachTick;
                IsOverlay   = false;
                DisplayInDataBox = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;

                UpColor   = Brushes.DodgerBlue;
                DownColor = Brushes.Firebrick;

                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Bar, "Delta");
                AddLine(Brushes.Gray, 0, "Zero");
            }
            else if (State == State.DataLoaded)
            {
                AskVol = new Series<double>(this, MaximumBarsLookBack.Infinite);
                BidVol = new Series<double>(this, MaximumBarsLookBack.Infinite);
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
            // as BidAskVolumeRatio.cs / BidAskVolumeSplit.cs, matches CumulativeDelta.cs).
            double ask = e.Ask, bid = e.Bid;
            if (ask <= 0 || bid <= 0) return;   // quotes not seeded yet this session
            if (e.Price >= ask)      curAskVol += e.Volume;
            else if (e.Price <= bid) curBidVol += e.Volume;
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

            double delta = ask - bid;
            Values[0][0] = delta;
            PlotBrushes[0][0] = delta >= 0 ? UpColor : DownColor;
        }

        #region Properties
        [XmlIgnore]
        [Display(Name = "Up Color", Description = "Bar color when AskVol >= BidVol.", Order = 1, GroupName = "1. Parameters")]
        public Brush UpColor { get; set; }
        [Browsable(false)] public string UpColorSerialize { get { return Serialize.BrushToString(UpColor); } set { UpColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Down Color", Description = "Bar color when BidVol > AskVol.", Order = 2, GroupName = "1. Parameters")]
        public Brush DownColor { get; set; }
        [Browsable(false)] public string DownColorSerialize { get { return Serialize.BrushToString(DownColor); } set { DownColor = Serialize.StringToBrush(value); } }

        [Browsable(false)] [XmlIgnore]
        public Series<double> Delta { get { return Values[0]; } }
        #endregion
    }
}
