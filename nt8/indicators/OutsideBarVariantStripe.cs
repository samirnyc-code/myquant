#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
#endregion

// OutsideBarVariantStripe (2026-10-21) — eyeball tool only, no signals/alerts.
// Paints a racing stripe (the bar's chart background, BackBrush — same mechanism as
// AMASignalOverlay.cs) behind every "outside bar variant":
//   range (High - Low) LARGER than the prior bar's range, AND
//   High == prior High  OR  Low == prior Low   (equal = within half a tick)
// Purpose: check by eye how these bars relate to DtDbScannerV4's DP / DT-pullback
// marks before deciding whether the scanner should treat them specially.
// Note: BackBrush stripes are not tied to the Indicator Manager hide/show toggle
// (NT8 limitation, see the S127 handoff block) — remove the indicator to clear them.
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

namespace NinjaTrader.NinjaScript.Indicators.My
{
    public class OutsideBarVariantStripe : Indicator
    {
        private Brush _stripe;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Racing stripe behind every outside-bar variant: larger range than the prior bar AND same High or same Low as the prior bar.";
                Name        = "OutsideBarVariantStripe";
                Calculate   = Calculate.OnBarClose;
                IsOverlay   = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                StripeBrush   = Brushes.Gold;
                StripeOpacity = 35;
            }
            else if (State == State.DataLoaded)
            {
                // semi-transparent, frozen copy of the chosen color
                Color c = StripeBrush is SolidColorBrush ? ((SolidColorBrush)StripeBrush).Color : Colors.Gold;
                SolidColorBrush b = new SolidColorBrush(Color.FromArgb((byte)(255 * StripeOpacity / 100), c.R, c.G, c.B));
                b.Freeze();
                _stripe = b;
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1) return;

            double half = TickSize / 2.0;
            bool largerRange = (High[0] - Low[0]) > (High[1] - Low[1]) + half;
            bool sameHigh    = Math.Abs(High[0] - High[1]) < half;
            bool sameLow     = Math.Abs(Low[0] - Low[1]) < half;

            if (largerRange && (sameHigh || sameLow))
                BackBrush = _stripe;
        }

        #region Properties
        [XmlIgnore]
        [Display(Name = "Stripe color", Order = 1, GroupName = "Display")]
        public Brush StripeBrush { get; set; }
        [Browsable(false)]
        public string StripeBrushSerialize { get { return Serialize.BrushToString(StripeBrush); } set { StripeBrush = Serialize.StringToBrush(value); } }

        [Range(5, 100)]
        [Display(Name = "Stripe opacity %", Order = 2, GroupName = "Display")]
        public int StripeOpacity { get; set; }
        #endregion
    }
}
