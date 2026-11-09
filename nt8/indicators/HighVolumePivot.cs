#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// Port of the MQL5 "High-Volume Pivot" indicator (mql5.com/en/articles/24820).
// Visualization only — no entries/exits/position management, same as the source.
namespace NinjaTrader.NinjaScript
{
    // Defined in the PARENT namespace (NinjaTrader.NinjaScript), NOT in .Indicators, so the
    // auto-generated wrapper code in the sibling .MarketAnalyzerColumns and .Strategies
    // namespaces can resolve the bare name "HvpBreakMode" (same reason as ETHSessionDefinition
    // in ETHLevelsExporter.cs).
    //
    // SingleClose  = confirmed the instant Close is beyond the level (original behavior).
    // NClosesBeyond = requires N CONSECUTIVE closes beyond the level; any close back on the
    //                 original side resets the count (catches DT/DB-style rejections).
    // AtrDistance  = requires price to travel a configurable multiple of ATR(500) beyond the
    //                level (measured off Close) before confirming; also resets on a revert.
    public enum HvpBreakMode
    {
        SingleClose,
        NClosesBeyond,
        AtrDistance
    }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class HighVolumePivot : Indicator
    {
        private const string Version = "v1.1";
        private const int AtrPeriod = 500;
        private const int PercentileWindow = 1000;
        private const double PercentileRank = 95.0;

        private class PivotLevel
        {
            public int BarIndex;
            public double Price;
            public bool IsHigh;
            public bool IsOutlier;
            public bool Crossed;
            public bool Finalized;
            public int CrossBarIndex;
            public string Tag;
            public int BreachCloses;
            public double BreachExtreme;
        }

        private ATR atr500;
        private Series<double> volSum;
        private Series<double> normVol;
        private List<double> volSumHistoryRth;
        private List<double> volSumHistoryEth;
        private List<PivotLevel> levels;

        private TimeZoneInfo sourceTz;
        private TimeZoneInfo targetTz;
        private bool convertTz;
        private int rthStartMin;
        private int rthEndMin;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = Version + " - Pivot highs/lows confirmed by abnormally high volume (vs. a rolling 95th-percentile reference), with ATR-scaled rings and a reaction level that goes dotted once price crosses it.";
                Name = "HighVolumePivot";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;

                LeftBars = 15;
                RightBars = 15;
                DisplayBars = 300;
                FilterVol = 2.0;
                ShowPivotDots = true;
                ShowRings = true;
                Step = 1.0;
                ShowLevels = true;
                ShowVolumeLabel = true;
                MultiplierOnly = false;
                OutlierMultiplier = 2.5;
                ShowOutlierMarkers = true;
                UpperColor = Brushes.Orange;
                LowerColor = Brushes.Teal;
                LabelColor = Brushes.Blue;
                OutlierColor = Brushes.Magenta;

                // RTH = 08:30-15:15 Chicago time (same CME ES window documented/used in
                // ETHLevelsExporter.cs). "Central Standard Time" is the Windows tz id that
                // auto-handles the CST/CDT (summer/winter) switch via .NET's TimeZoneInfo.
                RthStartHHmm = 830;
                RthEndHHmm = 1515;
                TimeZoneId = "Central Standard Time";

                BreakMode = HvpBreakMode.SingleClose;
                BreakClosesRequired = 2;
                BreakAtrMultiple = 0.25;
            }
            else if (State == State.DataLoaded)
            {
                atr500 = ATR(AtrPeriod);
                volSum = new Series<double>(this);
                normVol = new Series<double>(this);
                volSumHistoryRth = new List<double>(PercentileWindow);
                volSumHistoryEth = new List<double>(PercentileWindow);
                levels = new List<PivotLevel>();

                rthStartMin = HHmmToMinutes(RthStartHHmm);
                rthEndMin = HHmmToMinutes(RthEndHHmm);

                // Time[0] is expressed in NT's display timezone; convert into the exchange
                // timezone before applying the RTH window (same approach as ETHLevelsExporter.cs).
                sourceTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
                try
                {
                    targetTz = string.IsNullOrWhiteSpace(TimeZoneId)
                        ? sourceTz
                        : TimeZoneInfo.FindSystemTimeZoneById(TimeZoneId);
                }
                catch (Exception ex)
                {
                    Print("HighVolumePivot: WARNING - unknown TimeZoneId '" + TimeZoneId
                        + "', falling back to NT display timezone. (" + ex.Message + ")");
                    targetTz = sourceTz;
                }
                convertTz = !targetTz.Equals(sourceTz);
            }
        }

        protected override void OnBarUpdate()
        {
            // Trailing volume sum over the last 2*LeftBars bars ending at this bar, clamped
            // at the start of history (not tied to RightBars — that only governs confirmation
            // delay for the pivot check below).
            int volWindow = Math.Min(LeftBars * 2, CurrentBar + 1);
            double sum = 0;
            for (int i = 0; i < volWindow; i++)
                sum += Volume[i];
            volSum[0] = sum;

            // RTH and ETH have structurally different volume regimes, so each gets its own
            // rolling percentile reference — otherwise whichever regime dominates the trailing
            // window skews the threshold for the other.
            DateTime t = convertTz ? TimeZoneInfo.ConvertTime(Time[0], sourceTz, targetTz) : Time[0];
            int todMin = (int)t.TimeOfDay.TotalMinutes;
            bool isRth = todMin >= rthStartMin && todMin < rthEndMin;

            List<double> volSumHistory = isRth ? volSumHistoryRth : volSumHistoryEth;
            volSumHistory.Add(sum);
            if (volSumHistory.Count > PercentileWindow)
                volSumHistory.RemoveAt(0);

            double p95 = PercentileNearestRank(volSumHistory, PercentileRank);
            normVol[0] = p95 > 0 ? (sum / p95) * 5.0 : 0;

            int pivotLookback = LeftBars + RightBars;
            if (CurrentBar < pivotLookback)
                return;

            TryConfirmPivot();
            UpdateLevels();
        }

        private void TryConfirmPivot()
        {
            int pivotBarsAgo = RightBars;
            double candHigh = High[pivotBarsAgo];
            double candLow = Low[pivotBarsAgo];

            bool isPivotHigh = true;
            bool isPivotLow = true;

            for (int i = 1; i <= LeftBars && isPivotHigh; i++)
                if (High[pivotBarsAgo + i] >= candHigh) isPivotHigh = false;
            for (int i = 0; i < pivotBarsAgo && isPivotHigh; i++)
                if (High[i] >= candHigh) isPivotHigh = false;

            for (int i = 1; i <= LeftBars && isPivotLow; i++)
                if (Low[pivotBarsAgo + i] <= candLow) isPivotLow = false;
            for (int i = 0; i < pivotBarsAgo && isPivotLow; i++)
                if (Low[i] <= candLow) isPivotLow = false;

            if (!isPivotHigh && !isPivotLow)
                return;

            // Filter/ring-sizing value is the trailing-window NormVol as of the confirmation
            // bar (now), not the value at the pivot bar itself — confirmed against source.
            double nv = normVol[0];
            if (nv <= FilterVol)
                return;

            int pivotBarIndex = CurrentBar - pivotBarsAgo;
            if (CurrentBar - pivotBarIndex > DisplayBars)
                return;

            if (isPivotHigh)
                DrawPivot(pivotBarIndex, pivotBarsAgo, candHigh, true, nv);
            if (isPivotLow)
                DrawPivot(pivotBarIndex, pivotBarsAgo, candLow, false, nv);
        }

        private void DrawPivot(int pivotBarIndex, int pivotBarsAgo, double price, bool isHigh, double normVolValue)
        {
            bool isOutlier = normVolValue >= FilterVol * OutlierMultiplier;
            Brush color = isOutlier ? OutlierColor : (isHigh ? UpperColor : LowerColor);
            string baseTag = "HVP_" + pivotBarIndex + (isHigh ? "H" : "L");
            double atrAtPivot = atr500[pivotBarsAgo];

            if (isOutlier)
            {
                if (ShowOutlierMarkers)
                    Draw.Diamond(this, baseTag + "_dot", false, pivotBarsAgo, price, color);
            }
            else
            {
                if (ShowPivotDots)
                    Draw.Dot(this, baseTag + "_dot", false, pivotBarsAgo, price, color);
            }

            if (ShowVolumeLabel)
            {
                string multText = normVolValue.ToString("0.0") + "x";
                string volText = MultiplierOnly ? multText : FormatVolume(Volume[pivotBarsAgo]) + " " + multText;
                double labelPrice = isHigh ? price + atrAtPivot * 0.5 : price - atrAtPivot * 0.5;
                SimpleFont font = isOutlier ? new SimpleFont("Arial", 12) { Bold = true } : new SimpleFont("Arial", 10);
                Brush labelBrush = isOutlier ? OutlierColor : LabelColor;

                NinjaTrader.NinjaScript.DrawingTools.Text label = Draw.Text(this, baseTag + "_label", false, volText,
                    pivotBarsAgo, labelPrice, 0, labelBrush, font, System.Windows.TextAlignment.Center,
                    Brushes.Transparent, Brushes.Transparent, 0);
                // Rings and the level line (UpdateLevels) get redrawn every bar, which keeps
                // bumping them to the top of the z-stack and burying the label; pin it above both.
                label.ZOrder = 10;
            }

            if (ShowRings)
            {
                int ringCount = (int)Math.Floor(normVolValue / Step);

                for (int r = 1; r <= ringCount; r++)
                {
                    int aBars = (int)Math.Round(2.0 * r);
                    double vAxisPrice = 0.5 * atrAtPivot * r;

                    // Negative barsAgo projects past the most recently formed bar into future
                    // time (same convention as EAGapFillPivot.cs), so the ring isn't clipped at "now".
                    int startBarsAgo = pivotBarsAgo + aBars;
                    int endBarsAgo = pivotBarsAgo - aBars;

                    NinjaTrader.NinjaScript.DrawingTools.Ellipse ring = Draw.Ellipse(this, baseTag + "_ring" + r,
                        startBarsAgo, price + vAxisPrice, endBarsAgo, price - vAxisPrice, color, false);
                    ring.ZOrder = -1;
                }
            }

            if (ShowLevels)
            {
                levels.Add(new PivotLevel
                {
                    BarIndex = pivotBarIndex,
                    Price = price,
                    IsHigh = isHigh,
                    IsOutlier = isOutlier,
                    Tag = baseTag + "_level"
                });
            }
        }

        private void UpdateLevels()
        {
            if (!ShowLevels)
                return;

            for (int i = levels.Count - 1; i >= 0; i--)
            {
                PivotLevel level = levels[i];
                if (level.Finalized)
                    continue;

                Brush color = level.IsOutlier ? OutlierColor : (level.IsHigh ? UpperColor : LowerColor);
                int barsAgoStart = CurrentBar - level.BarIndex;

                if (!level.Crossed)
                {
                    bool beyond = level.IsHigh ? Close[0] >= level.Price : Close[0] <= level.Price;

                    if (beyond)
                    {
                        level.BreachCloses++;
                        level.BreachExtreme = level.BreachCloses == 1 ? Close[0]
                            : (level.IsHigh ? Math.Max(level.BreachExtreme, Close[0]) : Math.Min(level.BreachExtreme, Close[0]));
                    }
                    else
                    {
                        // Closed back on the original side — the breach attempt is void (this is
                        // exactly the DT/DB rejection case), reset and wait for the next attempt.
                        level.BreachCloses = 0;
                    }

                    bool confirmed;
                    switch (BreakMode)
                    {
                        case HvpBreakMode.NClosesBeyond:
                            confirmed = level.BreachCloses >= BreakClosesRequired;
                            break;
                        case HvpBreakMode.AtrDistance:
                            confirmed = beyond && Math.Abs(level.BreachExtreme - level.Price) >= BreakAtrMultiple * atr500[0];
                            break;
                        default:
                            confirmed = beyond;
                            break;
                    }

                    NinjaTrader.NinjaScript.DrawingTools.Line ln = Draw.Line(this, level.Tag, false,
                        barsAgoStart, level.Price, 0, level.Price, color, DashStyleHelper.Solid, 2);
                    ln.ZOrder = -1;

                    if (confirmed)
                    {
                        level.Crossed = true;
                        level.CrossBarIndex = CurrentBar;
                    }
                }
                else
                {
                    int barsAgoEnd = CurrentBar - level.CrossBarIndex;
                    NinjaTrader.NinjaScript.DrawingTools.Line ln = Draw.Line(this, level.Tag, false,
                        barsAgoStart, level.Price, barsAgoEnd, level.Price, color, DashStyleHelper.Dot, 2);
                    ln.ZOrder = -1;
                    level.Finalized = true;
                }
            }

            if (levels.Count > DisplayBars * 2)
                levels.RemoveRange(0, levels.Count - DisplayBars * 2);
        }

        private static double PercentileNearestRank(List<double> values, double rank)
        {
            if (values.Count == 0)
                return 0;

            List<double> sorted = new List<double>(values);
            sorted.Sort();
            int idx = (int)Math.Ceiling(rank / 100.0 * sorted.Count) - 1;
            idx = Math.Max(0, Math.Min(sorted.Count - 1, idx));
            return sorted[idx];
        }

        private static int HHmmToMinutes(int hhmm)
        {
            return (hhmm / 100) * 60 + (hhmm % 100);
        }

        private static string FormatVolume(double vol)
        {
            if (vol >= 1000000) return (vol / 1000000.0).ToString("0.00") + "M";
            if (vol >= 1000) return (vol / 1000.0).ToString("0.00") + "K";
            return vol.ToString("0");
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Left Bars", Order = 1, GroupName = "Parameters")]
        public int LeftBars { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Right Bars", Order = 2, GroupName = "Parameters")]
        public int RightBars { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Display Bars", Order = 3, GroupName = "Parameters")]
        public int DisplayBars { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, double.MaxValue)]
        [Display(Name = "Filter Volume", Order = 4, GroupName = "Parameters")]
        public double FilterVol { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Pivot Dots", Order = 5, GroupName = "Parameters", Description = "When off, the regular (non-outlier) pivot dot marker is not drawn.")]
        public bool ShowPivotDots { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Rings", Order = 6, GroupName = "Parameters", Description = "When off, the volume rings are not drawn and not calculated at all.")]
        public bool ShowRings { get; set; }

        [NinjaScriptProperty]
        [Range(0.0001, double.MaxValue)]
        [Display(Name = "Ring Step", Order = 7, GroupName = "Parameters")]
        public double Step { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Levels", Order = 8, GroupName = "Parameters")]
        public bool ShowLevels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Volume Label", Order = 9, GroupName = "Parameters", Description = "When off, the per-pivot volume text is not drawn.")]
        public bool ShowVolumeLabel { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Multiplier Only", Order = 10, GroupName = "Parameters", Description = "When on, the label shows only the volume score (e.g. '5.3x') instead of 'volume score'.")]
        public bool MultiplierOnly { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, double.MaxValue)]
        [Display(Name = "Outlier Multiplier", Order = 11, GroupName = "Parameters", Description = "A pivot is marked as an outlier (diamond marker, distinct color/bold label) when its volume score reaches Filter Volume x this multiplier.")]
        public double OutlierMultiplier { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Outlier Markers", Order = 12, GroupName = "Parameters", Description = "When off, the outlier diamond marker is not drawn.")]
        public bool ShowOutlierMarkers { get; set; }

        [XmlIgnore]
        [Display(Name = "Upper Color (Pivot High)", Order = 13, GroupName = "Parameters")]
        public Brush UpperColor { get; set; }

        [Browsable(false)]
        public string UpperColorSerializable
        {
            get { return Serialize.BrushToString(UpperColor); }
            set { UpperColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Lower Color (Pivot Low)", Order = 14, GroupName = "Parameters")]
        public Brush LowerColor { get; set; }

        [Browsable(false)]
        public string LowerColorSerializable
        {
            get { return Serialize.BrushToString(LowerColor); }
            set { LowerColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Label Color", Order = 15, GroupName = "Parameters")]
        public Brush LabelColor { get; set; }

        [Browsable(false)]
        public string LabelColorSerializable
        {
            get { return Serialize.BrushToString(LabelColor); }
            set { LabelColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Outlier Color", Order = 16, GroupName = "Parameters")]
        public Brush OutlierColor { get; set; }

        [Browsable(false)]
        public string OutlierColorSerializable
        {
            get { return Serialize.BrushToString(OutlierColor); }
            set { OutlierColor = Serialize.StringToBrush(value); }
        }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "RTH Start (HHmm)", Order = 1, GroupName = "RTH/ETH Session", Description = "Exchange-time RTH open, e.g. 830 = 08:30.")]
        public int RthStartHHmm { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "RTH End (HHmm)", Order = 2, GroupName = "RTH/ETH Session", Description = "Exchange-time RTH close, e.g. 1515 = 15:15.")]
        public int RthEndHHmm { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Timezone Id (Windows)", Order = 3, GroupName = "RTH/ETH Session", Description = "Windows timezone the RTH window is defined in. 'Central Standard Time' = Chicago (auto CST/CDT).")]
        public string TimeZoneId { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Break Mode", Order = 1, GroupName = "Level Break", Description = "SingleClose = original behavior, confirmed on first close beyond the level. NClosesBeyond = requires N consecutive closes beyond (resets on a revert). AtrDistance = requires price to travel N x ATR(500) beyond the level (resets on a revert).")]
        public HvpBreakMode BreakMode { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Closes Required", Order = 2, GroupName = "Level Break", Description = "NClosesBeyond mode only: consecutive closes beyond the level required to confirm a break.")]
        public int BreakClosesRequired { get; set; }

        [NinjaScriptProperty]
        [Range(0.0001, double.MaxValue)]
        [Display(Name = "Break ATR Multiple", Order = 3, GroupName = "Level Break", Description = "AtrDistance mode only: price must close this many x ATR(500) beyond the level to confirm a break.")]
        public double BreakAtrMultiple { get; set; }
        #endregion
    }
}
