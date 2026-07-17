// CumulativeDelta — CVD panel (cumulative volume delta) rendered as CANDLES, computed
// from ticks so it needs NO Order Flow+ license and matches our footprint pipeline's
// trade classification EXACTLY (same e.Bid/e.Ask embedded-quote rule as FootprintExporter).
//
// WHY: so Samir can eyeball CVD in NinjaTrader and mark price/CVD divergences on the
// chart, and what he sees == what we analyze offline (ES_bars delta / CVD).
//
// VIEW: per-bar CVD candle — Open = CVD at bar start, Close = CVD at bar end,
// High/Low = the intrabar cumulative-delta extremes. Candles (not a line) so CVD's own
// swing highs/lows are visible to compare against price swing highs/lows.
//
// REQUIRES TICK REPLAY for historical bars (right-click data series -> Tick Replay ON).
// Calculate = OnEachTick. Lives in a SEPARATE panel (IsOverlay = false).
//
// FILTERS (extensible — add more here later):
//   ResetMode   : Session (reset CVD each RTH session) | None (continuous)
//   LargeLotMin : 0 = count every trade; >0 = only count trades >= N contracts
//                 (large-lot / "smart money" filtered CVD — the mzVolumeDelta idea)
// TODO(next): auto-detect + draw regular/hidden divergences; export marks to CSV.
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

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
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public enum CvdResetMode { Session, None }

    public class CumulativeDelta : Indicator
    {
        private Series<double> cvO, cvH, cvL, cvC;   // per-bar CVD open/high/low/close
        private double runCum;                        // running cumulative delta
        private int accumBar = -1;
        private double barOpen, barHi, barLo, barClose;
        private SharpDX.Direct2D1.Brush upBrush, dnBrush;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "CumulativeDelta";
                Description = "Cumulative volume delta (CVD) as candles, from ticks — no Order Flow+ needed";
                Calculate = Calculate.OnEachTick;   // MUST be per-tick
                IsOverlay = false;                  // its own panel
                DrawOnPricePanel = false;
                DisplayInDataBox = true;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = true;
                ResetMode = CvdResetMode.Session;
                LargeLotMin = 0;
                UpColor = Brushes.SeaGreen;
                DownColor = Brushes.Firebrick;
                // transparent plots drive the panel autoscale to include the CVD high/low;
                // a faint Close line is a fallback in case custom rendering is unavailable
                AddPlot(new Stroke(Brushes.DimGray, 1), PlotStyle.Line, "CVD");     // Values[0]=Close
                AddPlot(Brushes.Transparent, "CvdHigh");                            // Values[1]
                AddPlot(Brushes.Transparent, "CvdLow");                            // Values[2]
            }
            else if (State == State.Configure)
            {
                cvO = new Series<double>(this);
                cvH = new Series<double>(this);
                cvL = new Series<double>(this);
                cvC = new Series<double>(this);
            }
            else if (State == State.Terminated)
            {
                if (upBrush != null) { upBrush.Dispose(); upBrush = null; }
                if (dnBrush != null) { dnBrush.Dispose(); dnBrush = null; }
            }
        }

        // classify each trade exactly like FootprintExporter (quote embedded in the tick)
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last || CurrentBar < 0) return;

            if (accumBar != CurrentBar)                 // bar rolled
            {
                if (ResetMode == CvdResetMode.Session && Bars.IsFirstBarOfSession)
                    runCum = 0;
                accumBar = CurrentBar;
                barOpen = barHi = barLo = barClose = runCum;
            }

            long v = (long)e.Volume;
            if (LargeLotMin > 0 && v < LargeLotMin) v = 0;   // large-lot filter
            if (v > 0)
            {
                double ask = e.Ask, bid = e.Bid; bool buy;
                if (ask > 0 && bid > 0)
                {
                    if (e.Price >= ask) buy = true;
                    else if (e.Price <= bid) buy = false;
                    else buy = e.Price >= (ask + bid) / 2.0;
                }
                else buy = true;
                runCum += buy ? v : -v;
            }
            barClose = runCum;
            if (runCum > barHi) barHi = runCum;
            if (runCum < barLo) barLo = runCum;

            cvO[0] = barOpen; cvH[0] = barHi; cvL[0] = barLo; cvC[0] = barClose;
            Values[0][0] = barClose; Values[1][0] = barHi; Values[2][0] = barLo;
        }

        protected override void OnBarUpdate()
        {
            // seed a value on bars with no ticks so the plot/scale stay continuous
            if (CurrentBar < 0) return;
            if (double.IsNaN(cvC[0]))
            {
                cvO[0] = cvH[0] = cvL[0] = cvC[0] = runCum;
                Values[0][0] = Values[1][0] = Values[2][0] = runCum;
            }
        }

        public override void OnRenderTargetChanged()
        {
            if (upBrush != null) { upBrush.Dispose(); upBrush = null; }
            if (dnBrush != null) { dnBrush.Dispose(); dnBrush = null; }
            if (RenderTarget != null)
            {
                upBrush = UpColor.ToDxBrush(RenderTarget);
                dnBrush = DownColor.ToDxBrush(RenderTarget);
            }
        }

        // draw the CVD candlesticks
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (Bars == null || ChartBars == null || RenderTarget == null || upBrush == null) return;

            float w = (float)Math.Max(1.0, chartControl.Properties.BarDistance * 0.30);
            for (int idx = ChartBars.FromIndex; idx <= ChartBars.ToIndex; idx++)
            {
                if (idx < 0 || idx > cvC.Count - 1) continue;
                double o = cvO.GetValueAt(idx), h = cvH.GetValueAt(idx),
                       l = cvL.GetValueAt(idx), c = cvC.GetValueAt(idx);
                if (double.IsNaN(o)) continue;

                float x  = chartControl.GetXByBarIndex(ChartBars, idx);
                float yO = chartScale.GetYByValue(o), yH = chartScale.GetYByValue(h),
                      yL = chartScale.GetYByValue(l), yC = chartScale.GetYByValue(c);
                var br = c >= o ? upBrush : dnBrush;

                RenderTarget.DrawLine(new Vector2(x, yH), new Vector2(x, yL), br, 1f);   // wick
                float top = Math.Min(yO, yC), bot = Math.Max(yO, yC);
                RenderTarget.FillRectangle(new RectangleF(x - w, top, 2f * w, Math.Max(bot - top, 1f)), br);   // body
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "ResetMode", Description = "Reset CVD each session or run continuous",
                 GroupName = "Parameters", Order = 0)]
        public CvdResetMode ResetMode { get; set; }

        [NinjaScriptProperty]
        [Range(0, int.MaxValue)]
        [Display(Name = "LargeLotMin", Description = "0 = all trades; >0 = only count trades >= N contracts",
                 GroupName = "Parameters", Order = 1)]
        public int LargeLotMin { get; set; }

        [XmlIgnore]
        [Display(Name = "Up color", GroupName = "Parameters", Order = 2)]
        public System.Windows.Media.Brush UpColor { get; set; }
        [Browsable(false)]
        public string UpColorSerialize { get { return Serialize.BrushToString(UpColor); } set { UpColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Down color", GroupName = "Parameters", Order = 3)]
        public System.Windows.Media.Brush DownColor { get; set; }
        [Browsable(false)]
        public string DownColorSerialize { get { return Serialize.BrushToString(DownColor); } set { DownColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
