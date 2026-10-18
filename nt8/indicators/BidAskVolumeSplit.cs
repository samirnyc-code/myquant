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

namespace NinjaTrader.NinjaScript.Indicators.My
{
    public class BidAskVolumeSplit : Indicator
    {
        private double lastAsk, lastBid;
        private double curAskVol, curBidVol;
        private int    accBar = -1;   // CurrentBar the live accumulators belong to

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
                AddPlot(new Stroke(Brushes.LightGray, 2), PlotStyle.Bar, "Bid Vol");
                AddLine(Brushes.Gray, 0, "Zero");
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
            Values[0][0] =  curAskVol;
            Values[1][0] = -curBidVol;
        }

        #region Properties
        [Browsable(false)] [XmlIgnore]
        public Series<double> AskVolPlot { get { return Values[0]; } }

        [Browsable(false)] [XmlIgnore]
        public Series<double> BidVolPlot { get { return Values[1]; } }
        #endregion
    }
}
