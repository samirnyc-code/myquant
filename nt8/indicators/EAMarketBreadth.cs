// EAMarketBreadth — NT8 port of the ToS BWD_MarketBreadth study v1.1
// (BigWaveDave / thinkscripter MARKETBREADTH lineage, 6/26/12).
//
// Lower-panel breadth trend: A/D issues or volume, as difference or zero-based
// normalized ratio, NYSE / NASDAQ / both, with gradient line coloring by where
// the current value sits in the last TrendStrengthLength bars (the ToS
// AssignNormGradientColor equivalent) and corner value labels colored by
// rising/falling.
//
// FEED SYMBOLS (My NinjaTrader / CQG — probed live 2026-08-05, EABreadthProbe):
//   NYSE:   ^ADV / ^DECL (issues)   ^UVOL / ^DVOL (volume)
//   NASDAQ: ^NUPI / ^NDNI (issues)  ^NUPV / ^NDNV (volume)
// (ToS $ADVN/$DECN/$UVOL/$DVOL and the /q variants.) ^ADD is dead on this feed;
// differences are computed from the components instead.
//
// MODES (DisplayValue):
//   ADIssuesRatio  adv>decl ? adv/decl : -decl/adv   (ratio, normalizable)
//   ADIssues       adv - decl
//   ADVolumeRatio  uvol>dvol ? uvol/dvol : -dvol/uvol  [ToS default]
//   ADVolume       uvol - dvol
// NormalizeToZeroLine (ratio modes only): >=1 -> v-1, else v+1 (zero-based, the
// ToS default). Non-normalized ratio blanks the sign-crossing bar like ToS does.
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
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript
{
    public enum EabDisplayValue { ADIssuesRatio, ADIssues, ADVolumeRatio, ADVolume }
    public enum EabMarket { NYSE, NASDAQ, Both }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class EAMarketBreadth : Indicator
    {
        private bool useVolume, isRatio;
        private int nyA = -1, nyD = -1, nqA = -1, nqD = -1;   // BarsInProgress indices
        private Series<double> nySer, nqSer;                   // plotted values (for gradient window)
        private double nyRaw, nyRawPrev = double.NaN, nqRaw, nqRawPrev = double.NaN;
        private Brush[] nyGrad, nqGrad;                        // 11-step frozen gradients neg->pos

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                     = "EAMarketBreadth";
                Description              = "ToS BWD_MarketBreadth port: A/D issues/volume breadth, normalized ratio, gradient trend coloring";
                Calculate                = Calculate.OnBarClose;
                IsOverlay                = false;
                DisplayInDataBox         = true;
                PaintPriceMarkers        = true;
                IsSuspendedWhileInactive = true;

                DisplayValue         = EabDisplayValue.ADVolumeRatio;
                Market               = EabMarket.NYSE;
                NormalizeToZeroLine  = true;
                DisplayZeroLine      = true;
                TrendStrengthLength  = 5;
                ShowChartLabels      = true;

                NYSEPosColor    = Brushes.Green;
                NYSENegColor    = Brushes.Red;
                NASDAQPosColor  = Brushes.DodgerBlue;
                NASDAQNegColor  = Brushes.DarkOrange;

                AddPlot(new Stroke(Brushes.Green,      2), PlotStyle.Line, "NYSEBreadth");    // Values[0]
                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Line, "NASDAQBreadth");  // Values[1]
                AddPlot(new Stroke(Brushes.DarkGray, DashStyleHelper.Dash, 1), PlotStyle.Line, "ZeroLine"); // Values[2]
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
            else if (State == State.DataLoaded)
            {
                nySer  = new Series<double>(this);
                nqSer  = new Series<double>(this);
                nyGrad = MakeGradient(NYSENegColor, NYSEPosColor);
                nqGrad = MakeGradient(NASDAQNegColor, NASDAQPosColor);
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            if (nyA >= 0)
                nyRawPrev = DoMarket(nyA, nyD, nySer, nyGrad, 0, ref nyRaw, nyRawPrev);
            if (nqA >= 0)
                nqRawPrev = DoMarket(nqA, nqD, nqSer, nqGrad, 1, ref nqRaw, nqRawPrev);

            if (DisplayZeroLine)
                Values[2][0] = 0;
            else
                Values[2].Reset();
        }

        // computes one market's breadth, plots it with gradient color; returns the
        // raw value to carry as next bar's "previous" (label color + cross blanking)
        private double DoMarket(int aIdx, int dIdx, Series<double> ser, Brush[] grad, int plotIdx, ref double rawOut, double rawPrev)
        {
            if (CurrentBars[aIdx] < 0 || CurrentBars[dIdx] < 0)
                { Values[plotIdx].Reset(); return rawPrev; }
            double a = Closes[aIdx][0], d = Closes[dIdx][0];
            if (a <= 0 || d <= 0)
                { Values[plotIdx].Reset(); return rawPrev; }

            double raw = isRatio ? (a > d ? a / d : -d / a) : a - d;
            rawOut = raw;

            double v;
            bool blank = false;
            if (isRatio && NormalizeToZeroLine)
                v = raw >= 1 ? raw - 1 : raw + 1;
            else if (isRatio)
            {
                // ToS: blank the bar where the ratio flips sign (avoids the jump line)
                v = raw;
                blank = !double.IsNaN(rawPrev) && ((raw >= 1 && rawPrev < 1) || (raw < 1 && rawPrev >= 1));
            }
            else
                v = raw;

            ser[0] = v;
            if (blank)
                Values[plotIdx].Reset();
            else
            {
                Values[plotIdx][0] = v;
                PlotBrushes[plotIdx][0] = GradientBrush(ser, grad);
            }
            return raw;
        }

        // color by where the current value sits within the min..max of the last
        // TrendStrengthLength bars (ToS AssignNormGradientColor equivalent)
        private Brush GradientBrush(Series<double> ser, Brush[] grad)
        {
            int len = Math.Min(TrendStrengthLength, CurrentBar + 1);
            double mn = double.MaxValue, mx = double.MinValue;
            for (int i = 0; i < len; i++)
            {
                double s = ser[i];
                if (s < mn) mn = s;
                if (s > mx) mx = s;
            }
            double pos = mx > mn ? (ser[0] - mn) / (mx - mn) : 0.5;
            return grad[(int)Math.Round(pos * 10)];
        }

        private static Brush[] MakeGradient(Brush negBrush, Brush posBrush)
        {
            Color neg = ((SolidColorBrush)negBrush).Color, pos = ((SolidColorBrush)posBrush).Color;
            var g = new Brush[11];
            for (int i = 0; i <= 10; i++)
            {
                float t = i / 10f;
                var b = new SolidColorBrush(Color.FromRgb(
                    (byte)(neg.R + (pos.R - neg.R) * t),
                    (byte)(neg.G + (pos.G - neg.G) * t),
                    (byte)(neg.B + (pos.B - neg.B) * t)));
                b.Freeze();
                g[i] = b;
            }
            return g;
        }

        // corner labels, one colored row per market: value + market name,
        // colored pos/neg by rising vs falling (ToS AddLabel behavior)
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (!ShowChartLabels || RenderTarget == null)
                return;

            var rows = new List<string>();
            var brushes = new List<Brush>();
            if (nyA >= 0 && nyRaw != 0)
            {
                rows.Add(FormatLabel(nyRaw) + " NYSE");
                brushes.Add(nyRaw > nyRawPrev ? NYSEPosColor : NYSENegColor);
            }
            if (nqA >= 0 && nqRaw != 0)
            {
                rows.Add(FormatLabel(nqRaw) + " NASDAQ");
                brushes.Add(nqRaw > nqRawPrev ? NASDAQPosColor : NASDAQNegColor);
            }
            if (rows.Count == 0)
                return;

            using (var tf = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 14f))
            {
                float y = ChartPanel.Y + 8;
                foreach (var pair in System.Linq.Enumerable.Zip(rows, brushes, (r, b) => new { r, b }))
                {
                    using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, pair.r, tf, 400, 30))
                    using (var dx = pair.b.ToDxBrush(RenderTarget))
                    {
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(ChartPanel.X + 8, y), tl, dx);
                        y += tl.Metrics.Height + 2;
                    }
                }
            }
        }

        private string FormatLabel(double raw)
        {
            return isRatio ? raw.ToString("0.00") + ":1" : raw.ToString("+#,0;-#,0");
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Display value", GroupName = "Parameters", Order = 0)]
        public EabDisplayValue DisplayValue { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Market", GroupName = "Parameters", Order = 1)]
        public EabMarket Market { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Normalize ratio to zero line", GroupName = "Parameters", Order = 2)]
        public bool NormalizeToZeroLine { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Display zero line", GroupName = "Parameters", Order = 3)]
        public bool DisplayZeroLine { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Trend strength length (bars)", GroupName = "Parameters", Order = 4)]
        public int TrendStrengthLength { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show chart labels", GroupName = "Parameters", Order = 5)]
        public bool ShowChartLabels { get; set; }

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
