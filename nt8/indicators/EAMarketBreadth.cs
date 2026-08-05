// EAMarketBreadth — NT8 port of the ToS BWD_MarketBreadth study v1.1
// (BigWaveDave / thinkscripter MARKETBREADTH lineage), LABEL-ONLY style
// (the user's ToS display: AddLabel chips on the price chart, no plots),
// EXTENDED beyond the original: ALL FOUR metrics available at once in one
// instance, toggleable —
//   Vol ratio   uvol>dvol ? uvol/dvol : -dvol/uvol      [on by default]
//   Iss ratio   adv>decl  ? adv/decl  : -decl/adv       [on by default]
//   Vol diff    uvol - dvol                             [off]
//   Iss diff    adv - decl                              [off]
// One chip row per market (NYSE row, NASDAQ row below when Market=Both).
// Chip = solid rectangle, black text, bg pos/neg color by metric rising vs
// falling vs prior bar (exact ToS AddLabel behavior).
//
// FEED SYMBOLS (My NinjaTrader / CQG — probed live 2026-08-05, EABreadthProbe):
//   NYSE:   ^ADV / ^DECL (issues)   ^UVOL / ^DVOL (volume)
//   NASDAQ: ^NUPI / ^NDNI (issues)  ^NUPV / ^NDNV (volume)
// Panel-plot v1 of this port lives at git 93903caf if ever wanted.
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
    public enum EabMarket { NYSE, NASDAQ, Both }
    public enum EabLabelCorner { TopLeft, TopRight }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class EAMarketBreadth : Indicator
    {
        // per market: BarsInProgress indices of adv/decl issues + up/down volume
        private int[] issA = { -1, -1 }, issD = { -1, -1 }, volU = { -1, -1 }, volD = { -1, -1 };
        // cur/prev per market [0]=NYSE [1]=NASDAQ, per metric 0=VolRatio 1=IssRatio 2=VolDiff 3=IssDiff
        private readonly double[,] cur  = new double[2, 4];
        private readonly double[,] prev = new double[2, 4];

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                     = "EAMarketBreadth";
                Description              = "ToS BWD_MarketBreadth port, label-only chips: vol/issues ratio+diff, NYSE/NASDAQ, all in one instance";
                Calculate                = Calculate.OnBarClose;
                IsOverlay                = true;
                DisplayInDataBox         = false;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = true;

                Market          = EabMarket.NYSE;
                ShowVolumeRatio = true;
                ShowIssuesRatio = true;
                ShowVolumeDiff  = false;
                ShowIssuesDiff  = false;
                AbbreviateText  = false;
                LabelCorner     = EabLabelCorner.TopLeft;
                LabelOffsetY    = 30;

                NYSEPosColor    = Brushes.Green;
                NYSENegColor    = Brushes.Red;
                NASDAQPosColor  = Brushes.DodgerBlue;
                NASDAQNegColor  = Brushes.DarkOrange;

                for (int m = 0; m < 2; m++)
                    for (int k = 0; k < 4; k++)
                        { cur[m, k] = double.NaN; prev[m, k] = double.NaN; }
            }
            else if (State == State.Configure)
            {
                int bip = 1;
                if (Market != EabMarket.NASDAQ)
                {
                    AddDataSeries("^ADV");  issA[0] = bip++;
                    AddDataSeries("^DECL"); issD[0] = bip++;
                    AddDataSeries("^UVOL"); volU[0] = bip++;
                    AddDataSeries("^DVOL"); volD[0] = bip++;
                }
                if (Market != EabMarket.NYSE)
                {
                    AddDataSeries("^NUPI"); issA[1] = bip++;
                    AddDataSeries("^NDNI"); issD[1] = bip++;
                    AddDataSeries("^NUPV"); volU[1] = bip++;
                    AddDataSeries("^NDNV"); volD[1] = bip++;
                }
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;
            for (int m = 0; m < 2; m++)
            {
                if (issA[m] < 0) continue;
                double a = Val(issA[m]), d = Val(issD[m]), u = Val(volU[m]), v = Val(volD[m]);
                if (u > 0 && v > 0)
                {
                    Set(m, 0, u > v ? u / v : -v / u);   // VolRatio
                    Set(m, 2, u - v);                    // VolDiff
                }
                if (a > 0 && d > 0)
                {
                    Set(m, 1, a > d ? a / d : -d / a);   // IssRatio
                    Set(m, 3, a - d);                    // IssDiff
                }
            }
        }

        private double Val(int idx)
        {
            return (idx >= 0 && CurrentBars[idx] >= 0) ? Closes[idx][0] : 0;
        }

        private void Set(int m, int k, double raw)
        {
            if (!double.IsNaN(cur[m, k]) && raw != cur[m, k])
                prev[m, k] = cur[m, k];
            cur[m, k] = raw;
        }

        // chip rows, ToS AddLabel style: one row per market, chips left-to-right
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null)
                return;

            bool[] show = { ShowVolumeRatio, ShowIssuesRatio, ShowVolumeDiff, ShowIssuesDiff };
            string[] tag = { "Vol", "Iss", "Vol", "Iss" };
            string[] mktName = { "NYSE", "NASDAQ" };
            Brush[] posB = { NYSEPosColor, NASDAQPosColor };
            Brush[] negB = { NYSENegColor, NASDAQNegColor };

            using (var tf = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 13f))
            using (var black = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0f, 0f, 1f)))
            {
                // grid layout: metrics = columns (uniform width), markets = rows,
                // so Both + 2 metrics renders an aligned 2x2 block
                var cols = new List<int>();
                for (int k = 0; k < 4; k++)
                    if (show[k]) cols.Add(k);
                if (cols.Count == 0)
                    return;

                var layouts = new SharpDX.DirectWrite.TextLayout[2, cols.Count];
                var fills   = new Brush[2, cols.Count];
                float[] colW = new float[cols.Count];
                float chipH = 0;
                for (int m = 0; m < 2; m++)
                {
                    if (issA[m] < 0) continue;
                    for (int c = 0; c < cols.Count; c++)
                    {
                        int k = cols[c];
                        if (double.IsNaN(cur[m, k])) continue;
                        // single metric -> exact ToS label text ("2.1734:1 NYSE");
                        // the "Vol "/"Iss " prefix only disambiguates multiple chips
                        string prefix = cols.Count > 1 ? tag[k] + " " : "";
                        var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory,
                            prefix + FormatVal(cur[m, k], k < 2) + " " + mktName[m], tf, 500, 30);
                        layouts[m, c] = tl;
                        fills[m, c]   = double.IsNaN(prev[m, k]) || cur[m, k] > prev[m, k] ? posB[m] : negB[m];
                        colW[c]  = Math.Max(colW[c], tl.Metrics.Width + 12);
                        chipH    = Math.Max(chipH, tl.Metrics.Height + 6);
                    }
                }

                float totalW = 0;
                foreach (float w in colW) totalW += w + 6;
                float x0 = LabelCorner == EabLabelCorner.TopRight
                    ? ChartPanel.X + ChartPanel.W - totalW - 8
                    : ChartPanel.X + 8;
                float y = ChartPanel.Y + LabelOffsetY;
                for (int m = 0; m < 2; m++)
                {
                    bool any = false;
                    float x = x0;
                    for (int c = 0; c < cols.Count; c++)
                    {
                        if (layouts[m, c] != null)
                        {
                            using (var fill = fills[m, c].ToDxBrush(RenderTarget))
                            {
                                RenderTarget.FillRectangle(new SharpDX.RectangleF(x, y, colW[c], chipH), fill);
                                RenderTarget.DrawTextLayout(new SharpDX.Vector2(x + 6, y + 3), layouts[m, c], black);
                            }
                            layouts[m, c].Dispose();
                            any = true;
                        }
                        x += colW[c] + 6;
                    }
                    if (any)
                        y += chipH + 4;   // next market row directly beneath, aligned
                }
            }
        }

        private string FormatVal(double raw, bool ratio)
        {
            // ToS: full precision + ":1" unless AbbreviateText, then Round(x,2) without ":1"
            if (ratio)
                return AbbreviateText ? Math.Round(raw, 2).ToString("0.##") : raw.ToString("0.####") + ":1";
            return raw.ToString("+#,0;-#,0");
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Market", GroupName = "Parameters", Order = 0)]
        public EabMarket Market { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Volume ratio", GroupName = "Metrics", Order = 0)]
        public bool ShowVolumeRatio { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Issues ratio", GroupName = "Metrics", Order = 1)]
        public bool ShowIssuesRatio { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Volume difference", GroupName = "Metrics", Order = 2)]
        public bool ShowVolumeDiff { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Issues difference", GroupName = "Metrics", Order = 3)]
        public bool ShowIssuesDiff { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Abbreviate text", GroupName = "Parameters", Order = 1)]
        public bool AbbreviateText { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Label corner", GroupName = "Parameters", Order = 2)]
        public EabLabelCorner LabelCorner { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2000)]
        [Display(Name = "Label offset from top (px)", GroupName = "Parameters", Order = 3)]
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
