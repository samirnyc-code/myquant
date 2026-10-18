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

#region Using declarations
using System;
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
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class BidAskVolumeDelta : Indicator
    {
        private double lastAsk, lastBid;
        private double curAskVol, curBidVol;
        private int    accBar = -1;   // CurrentBar the live accumulators belong to

        [XmlIgnore] [Browsable(false)] public Series<double> AskVol;
        [XmlIgnore] [Browsable(false)] public Series<double> BidVol;

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
                DownColor = Brushes.LightGray;

                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Bar, "Delta");
                AddLine(Brushes.Gray, 0, "Zero");
            }
            else if (State == State.DataLoaded)
            {
                AskVol = new Series<double>(this, MaximumBarsLookBack.Infinite);
                BidVol = new Series<double>(this, MaximumBarsLookBack.Infinite);
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
            AskVol[0] = curAskVol;
            BidVol[0] = curBidVol;

            double delta = curAskVol - curBidVol;
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
