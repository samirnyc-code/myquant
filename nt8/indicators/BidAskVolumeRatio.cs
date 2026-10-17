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
            AskVol[0] = curAskVol;
            BidVol[0] = curBidVol;

            double denom = curAskVol + curBidVol;
            double sign  = DiffMethod == BavrDiffMethod.AskMinusBid ? 1.0 : -1.0;
            RawRatio[0]  = denom > 0 ? 100.0 * sign * (curAskVol - curBidVol) / denom : 0.0;

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
