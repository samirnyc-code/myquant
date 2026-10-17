// HeikenAshiOverlay.cs — Heiken Ashi as a drawn OVERLAY on top of whatever bars are
// already on the chart, instead of NT8's native "Heiken Ashi" Bar Type.
//
// WHY: NT8's Bar Type dropdown (Data Series -> Type) is a single exclusive choice —
// picking Heiken Ashi there REPLACES the underlying bar construction, you can't have
// both "Heiken Ashi" and "Flex Renko" selected at once (confirmed: no supported way to
// stack two Bar Types on one series). Sierra Chart's "HA overlay on top of Flex Renko"
// is a different mechanism — it runs the standard Heiken Ashi smoothing formula ON TOP
// of the already-built Renko/whatever bars and draws the smoothed result as an extra
// layer, while the chart's real bars (and anything reading them, e.g. RegimeTracker's
// pivot detection) are untouched underneath. That's what this indicator does: it reads
// Open/High/Low/Close of whatever bar series it's added to (works on Flex Renko,
// standard bars, anything) and draws synthetic HA candles over them.
//
// Classic Heiken Ashi formula (unchanged, standard):
//   haClose = (O+H+L+C)/4
//   haOpen  = (prior haOpen + prior haClose)/2   (first bar: (O+C)/2)
//   haHigh  = max(H, haOpen, haClose)
//   haLow   = min(L, haOpen, haClose)
//
// Drawn as two vertical Draw.Line segments per bar at that bar's barsAgo x-position
// (thick = body open-to-close, thin = wick low-to-high) rather than Draw.Rectangle,
// since Draw.Rectangle's bar-offset parameters are ints only — no fractional width to
// center a narrower body on a single bar. Same tag per bar across ticks, so the
// currently-forming bar's candle updates live instead of stacking new shapes.

#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class HeikenAshiOverlay : Indicator
    {
        private Series<double> haOpen, haClose, haHigh, haLow;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Heiken Ashi drawn as an overlay on top of the chart's real bars (any bar type, incl. Renko) — not NT8's native Heiken Ashi Bar Type, which would replace the underlying bars instead of layering on them.";
                Name        = "HeikenAshiOverlay";
                Calculate   = Calculate.OnEachTick;   // forming candle updates live, matching how real candles look
                IsOverlay   = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;

                BodyWidth  = 6;   // pixels
                WickWidth  = 2;   // pixels
                UpBrush    = Brushes.LimeGreen;
                DownBrush  = Brushes.Red;
                Opacity    = 100; // 0-100 % of UpBrush/DownBrush
            }
            else if (State == State.DataLoaded)
            {
                haOpen  = new Series<double>(this, MaximumBarsLookBack.Infinite);
                haClose = new Series<double>(this, MaximumBarsLookBack.Infinite);
                haHigh  = new Series<double>(this, MaximumBarsLookBack.Infinite);
                haLow   = new Series<double>(this, MaximumBarsLookBack.Infinite);
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 0) return;

            double o = Open[0], h = High[0], l = Low[0], c = Close[0];
            double hc = (o + h + l + c) / 4.0;
            double ho = CurrentBar == 0 ? (o + c) / 2.0 : (haOpen[1] + haClose[1]) / 2.0;
            double hh = Math.Max(h, Math.Max(ho, hc));
            double hl = Math.Min(l, Math.Min(ho, hc));

            haOpen[0] = ho; haClose[0] = hc; haHigh[0] = hh; haLow[0] = hl;

            bool up = hc >= ho;
            Brush brush = up ? WithOpacity(UpBrush, Opacity) : WithOpacity(DownBrush, Opacity);
            string tag = "ha_" + CurrentBar;

            Draw.Line(this, tag + "_wick", false, 0, hl, 0, hh, brush, DashStyleHelper.Solid, WickWidth);
            Draw.Line(this, tag + "_body", false, 0, ho, 0, hc, brush, DashStyleHelper.Solid, BodyWidth);
        }

        private static Brush WithOpacity(Brush src, int pct)
        {
            var scb = src as SolidColorBrush;
            Color base_ = scb != null ? scb.Color : Colors.Gray;
            byte a = (byte)Math.Max(0, Math.Min(255, (int)Math.Round(pct / 100.0 * 255.0)));
            var b = new SolidColorBrush(Color.FromArgb(a, base_.R, base_.G, base_.B));
            b.Freeze();
            return b;
        }

        #region Properties
        [NinjaScriptProperty, Range(1, 50)]
        [Display(Name = "Body width (px)", Description = "Thickness of the Open-Close body line.", Order = 1, GroupName = "1. Style")]
        public int BodyWidth { get; set; }

        [NinjaScriptProperty, Range(1, 50)]
        [Display(Name = "Wick width (px)", Description = "Thickness of the High-Low wick line.", Order = 2, GroupName = "1. Style")]
        public int WickWidth { get; set; }

        [NinjaScriptProperty, Range(0, 100)]
        [Display(Name = "Opacity %", Description = "Opacity applied to both Up/Down colors.", Order = 3, GroupName = "1. Style")]
        public int Opacity { get; set; }

        [XmlIgnore]
        [Display(Name = "Up color", Description = "Color when the HA close is >= the HA open.", Order = 4, GroupName = "1. Style")]
        public Brush UpBrush { get; set; }
        [Browsable(false)]
        public string UpBrushSerialize { get { return Serialize.BrushToString(UpBrush); } set { UpBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Down color", Description = "Color when the HA close is < the HA open.", Order = 5, GroupName = "1. Style")]
        public Brush DownBrush { get; set; }
        [Browsable(false)]
        public string DownBrushSerialize { get { return Serialize.BrushToString(DownBrush); } set { DownBrush = Serialize.StringToBrush(value); } }
        #endregion
    }
}
