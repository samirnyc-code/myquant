// EAMarketBreadth — NT8 port of the ToS BWD_MarketBreadth study v1.1
// (BigWaveDave / thinkscripter MARKETBREADTH lineage, 6/26/12), in the
// LABEL-ONLY style the user runs it in ToS ("unselect 'show plot', move to the
// upper chart"): colored AddLabel-style chips on the PRICE chart, no plots.
//
// CHIP = solid rectangle, black text, laid left-to-right at the top-left:
//   "2.09:1 NYSE"  background green when breadth rising vs prior bar, red when
//   falling (NASDAQ: blue / dark orange) — exact ToS AddLabel behavior.
//
// FEED SYMBOLS (My NinjaTrader / CQG — probed live 2026-08-05, EABreadthProbe):
//   NYSE:   ^ADV / ^DECL (issues)   ^UVOL / ^DVOL (volume)
//   NASDAQ: ^NUPI / ^NDNI (issues)  ^NUPV / ^NDNV (volume)
// (ToS $ADVN/$DECN/$UVOL/$DVOL and the /q variants.)
//
// MODES (DisplayValue, ToS default ADVolumeRatio):
//   ADIssuesRatio  adv>decl ? adv/decl : -decl/adv
//   ADIssues       adv - decl
//   ADVolumeRatio  uvol>dvol ? uvol/dvol : -dvol/uvol
//   ADVolume       uvol - dvol
// AbbreviateText (ToS input): No -> full value + ":1" on ratios; Yes -> 2dp.
// The plot/zero-line rendering of the original is intentionally NOT ported —
// the user's display is chips only (panel-plot version lives in git history
// at 93903caf if ever wanted).
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript
{
    public enum EabDisplayValue { ADIssuesRatio, ADIssues, ADVolumeRatio, ADVolume }
    public enum EabMarket { NYSE, NASDAQ, Both }
    public enum EabLabelCorner { TopLeft, TopRight }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class EAMarketBreadth : Indicator
    {
        private bool useVolume, isRatio;
        private int nyA = -1, nyD = -1, nqA = -1, nqD = -1;   // BarsInProgress indices
        private double nyCur = double.NaN, nyPrev = double.NaN;
        private double nqCur = double.NaN, nqPrev = double.NaN;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                     = "EAMarketBreadth";
                Description              = "ToS BWD_MarketBreadth port, label-only style: colored breadth chips on the price chart";
                Calculate                = Calculate.OnBarClose;
                IsOverlay                = true;
                DisplayInDataBox         = false;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = true;

                DisplayValue    = EabDisplayValue.ADVolumeRatio;
                Market          = EabMarket.NYSE;
                AbbreviateText  = false;
                LabelCorner     = EabLabelCorner.TopLeft;
                LabelOffsetY    = 30;

                NYSEPosColor    = Brushes.Green;
                NYSENegColor    = Brushes.Red;
                NASDAQPosColor  = Brushes.DodgerBlue;
                NASDAQNegColor  = Brushes.DarkOrange;
            }
            else if (State == State.Configure)
            {
                useVolume = DisplayValue == EabDisplayValue.ADVolumeRatio || DisplayValue == EabDisplayValue.ADVolume;
                isRatio   = DisplayValue == EabDisplayValue.ADVolumeRatio || DisplayValue == EabDisplayValue.ADIssuesRatio;
                int bip = 1;
                if (Market != EabMarket.NASDAQ)
                {
                    AddDataSeries(useVolume ? "^UVOL" : "^ADV");  nyA = bip++;
                    AddDataSeries(useVolume ? "^DVOL" : "^DECL"); nyD = bip++;
                }
                if (Market != EabMarket.NYSE)
                {
                    AddDataSeries(useVolume ? "^NUPV" : "^NUPI"); nqA = bip++;
                    AddDataSeries(useVolume ? "^NDNV" : "^NDNI"); nqD = bip++;
                }
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;
            if (nyA >= 0)
                Compute(nyA, nyD, ref nyCur, ref nyPrev);
            if (nqA >= 0)
                Compute(nqA, nqD, ref nqCur, ref nqPrev);
        }

        private void Compute(int aIdx, int dIdx, ref double cur, ref double prev)
        {
            if (CurrentBars[aIdx] < 0 || CurrentBars[dIdx] < 0)
                return;
            double a = Closes[aIdx][0], d = Closes[dIdx][0];
            if (a <= 0 || d <= 0)
                return;
            double raw = isRatio ? (a > d ? a / d : -d / a) : a - d;
            if (!double.IsNaN(cur) && raw != cur)
                prev = cur;
            cur = raw;
        }

        // ToS AddLabel style: solid chip, black text, left-to-right at top-left
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null)
                return;

            var texts = new List<string>();
            var fills = new List<Brush>();
            if (nyA >= 0 && !double.IsNaN(nyCur))
            {
                texts.Add(FormatLabel(nyCur) + " NYSE");
                fills.Add(double.IsNaN(nyPrev) || nyCur > nyPrev ? NYSEPosColor : NYSENegColor);
            }
            if (nqA >= 0 && !double.IsNaN(nqCur))
            {
                texts.Add(FormatLabel(nqCur) + " NASDAQ");
                fills.Add(double.IsNaN(nqPrev) || nqCur > nqPrev ? NASDAQPosColor : NASDAQNegColor);
            }
            if (texts.Count == 0)
                return;

            using (var tf = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 13f))
            using (var black = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0f, 0f, 1f)))
            {
                // measure chips first so a right-anchored row can be laid out right-to-left
                var layouts = new List<SharpDX.DirectWrite.TextLayout>();
                float totalW = 0, chipH = 0;
                foreach (string t in texts)
                {
                    var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, t, tf, 500, 30);
                    layouts.Add(tl);
                    totalW += tl.Metrics.Width + 12 + 6;
                    chipH = Math.Max(chipH, tl.Metrics.Height + 6);
                }
                float x = LabelCorner == EabLabelCorner.TopRight
                    ? ChartPanel.X + ChartPanel.W - totalW - 8
                    : ChartPanel.X + 8;
                float y = ChartPanel.Y + LabelOffsetY;
                for (int i = 0; i < layouts.Count; i++)
                {
                    using (var fill = fills[i].ToDxBrush(RenderTarget))
                    {
                        float w = layouts[i].Metrics.Width + 12;
                        RenderTarget.FillRectangle(new SharpDX.RectangleF(x, y, w, chipH), fill);
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(x + 6, y + 3), layouts[i], black);
                        x += w + 6;   // next chip to the right, ToS label row style
                    }
                    layouts[i].Dispose();
                }
            }
        }

        private string FormatLabel(double raw)
        {
            if (AbbreviateText)
                return Math.Round(raw, 2).ToString("0.##");
            return isRatio ? raw.ToString("0.####") + ":1" : raw.ToString("#,0");
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Display value", GroupName = "Parameters", Order = 0)]
        public EabDisplayValue DisplayValue { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Market", GroupName = "Parameters", Order = 1)]
        public EabMarket Market { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Abbreviate text", GroupName = "Parameters", Order = 2)]
        public bool AbbreviateText { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Label corner", GroupName = "Parameters", Order = 3)]
        public EabLabelCorner LabelCorner { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2000)]
        [Display(Name = "Label offset from top (px)", GroupName = "Parameters", Order = 4)]
        public int LabelOffsetY { get; set; }

        [XmlIgnore]
        [Display(Name = "NYSE positive", GroupName = "Colors", Order = 0)]
        public Brush NYSEPosColor { get; set; }
        [Browsable(false)]
        public string NYSEPosColorSerialize { get { return Serialize.BrushToString(NYSEPosColor); } set { NYSEPosColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "NYSE negative", GroupName = "Colors", Order = 1)]
        public Brush NYSENegColor { get; set; }
        [Browsable(false)]
        public string NYSENegColorSerialize { get { return Serialize.BrushToString(NYSENegColor); } set { NYSENegColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "NASDAQ positive", GroupName = "Colors", Order = 2)]
        public Brush NASDAQPosColor { get; set; }
        [Browsable(false)]
        public string NASDAQPosColorSerialize { get { return Serialize.BrushToString(NASDAQPosColor); } set { NASDAQPosColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "NASDAQ negative", GroupName = "Colors", Order = 3)]
        public Brush NASDAQNegColor { get; set; }
        [Browsable(false)]
        public string NASDAQNegColorSerialize { get { return Serialize.BrushToString(NASDAQNegColor); } set { NASDAQNegColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
