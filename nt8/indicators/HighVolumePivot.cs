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
namespace NinjaTrader.NinjaScript.Indicators
{
    public class HighVolumePivot : Indicator
    {
        private const int AtrPeriod = 500;
        private const int PercentileWindow = 1000;
        private const double PercentileRank = 95.0;

        private class PivotLevel
        {
            public int BarIndex;
            public double Price;
            public bool IsHigh;
            public bool Crossed;
            public bool Finalized;
            public int CrossBarIndex;
            public string Tag;
        }

        private ATR atr500;
        private Series<double> volSum;
        private Series<double> normVol;
        private List<double> volSumHistory;
        private List<PivotLevel> levels;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Pivot highs/lows confirmed by abnormally high volume (vs. a rolling 95th-percentile reference), with ATR-scaled rings and a reaction level that goes dotted once price crosses it.";
                Name = "HighVolumePivot";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;

                LeftBars = 15;
                RightBars = 15;
                UseRealVolume = false;
                DisplayBars = 300;
                FilterVol = 2.0;
                Step = 1.0;
                ShowLevels = true;
                UpperColor = Brushes.Orange;
                LowerColor = Brushes.Teal;
                LabelColor = Brushes.Blue;
            }
            else if (State == State.DataLoaded)
            {
                atr500 = ATR(AtrPeriod);
                volSum = new Series<double>(this);
                normVol = new Series<double>(this);
                volSumHistory = new List<double>(PercentileWindow);
                levels = new List<PivotLevel>();
            }
        }

        protected override void OnBarUpdate()
        {
            // Trailing volume sum over the last 2*LeftBars bars ending at this bar, clamped
            // at the start of history (not tied to RightBars — that only governs confirmation
            // delay for the pivot check below).
            // NinjaTrader's Volume[] already reflects actual traded volume on most feeds,
            // so UseRealVolume has no distinct series to switch to here (kept for UI parity
            // with the source indicator's tick-volume/real-volume toggle).
            int volWindow = Math.Min(LeftBars * 2, CurrentBar + 1);
            double sum = 0;
            for (int i = 0; i < volWindow; i++)
                sum += Volume[i];
            volSum[0] = sum;

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
            Brush color = isHigh ? UpperColor : LowerColor;
            string baseTag = "HVP_" + pivotBarIndex + (isHigh ? "H" : "L");
            double atrAtPivot = atr500[pivotBarsAgo];

            Draw.Dot(this, baseTag + "_dot", false, pivotBarsAgo, price, color);

            string volText = FormatVolume(Volume[pivotBarsAgo]);
            double labelPrice = isHigh ? price + atrAtPivot * 0.5 : price - atrAtPivot * 0.5;
            Draw.Text(this, baseTag + "_label", volText, pivotBarsAgo, labelPrice, LabelColor);

            int ringCount = (int)Math.Floor(normVolValue / Step);
            DateTime pivotTime = Time[pivotBarsAgo];
            double barSeconds = GetBarSeconds();

            for (int r = 1; r <= ringCount; r++)
            {
                double aBars = Math.Round(2.0 * r);
                double vAxisPrice = 0.5 * atrAtPivot * r;
                double secs = aBars * barSeconds;

                // Time-based anchors (matching the source's PeriodSeconds() scaling) so the
                // ring can extend past the most recently formed bar into future time, instead
                // of being clipped at "now" the way bar-indexed anchors would force it to be.
                DateTime leftTime = pivotTime.AddSeconds(-secs);
                DateTime rightTime = pivotTime.AddSeconds(secs);

                Draw.Ellipse(this, baseTag + "_ring" + r, false,
                    leftTime, price + vAxisPrice,
                    rightTime, price - vAxisPrice,
                    color);
            }

            if (ShowLevels)
            {
                levels.Add(new PivotLevel
                {
                    BarIndex = pivotBarIndex,
                    Price = price,
                    IsHigh = isHigh,
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

                Brush color = level.IsHigh ? UpperColor : LowerColor;
                int barsAgoStart = CurrentBar - level.BarIndex;

                if (!level.Crossed)
                {
                    bool crossedNow = level.IsHigh
                        ? Close[1] < level.Price && Close[0] >= level.Price
                        : Close[1] > level.Price && Close[0] <= level.Price;

                    Draw.Line(this, level.Tag, false, barsAgoStart, level.Price, 0, level.Price,
                        color, DashStyleHelper.Solid, 2);

                    if (crossedNow)
                    {
                        level.Crossed = true;
                        level.CrossBarIndex = CurrentBar;
                    }
                }
                else
                {
                    int barsAgoEnd = CurrentBar - level.CrossBarIndex;
                    Draw.Line(this, level.Tag, false, barsAgoStart, level.Price, barsAgoEnd, level.Price,
                        color, DashStyleHelper.Dot, 2);
                    level.Finalized = true;
                }
            }

            if (levels.Count > DisplayBars * 2)
                levels.RemoveRange(0, levels.Count - DisplayBars * 2);
        }

        private double GetBarSeconds()
        {
            switch (BarsPeriod.BarsPeriodType)
            {
                case BarsPeriodType.Second: return BarsPeriod.Value;
                case BarsPeriodType.Minute: return BarsPeriod.Value * 60.0;
                case BarsPeriodType.Day: return BarsPeriod.Value * 86400.0;
                case BarsPeriodType.Week: return BarsPeriod.Value * 604800.0;
                case BarsPeriodType.Month: return BarsPeriod.Value * 2629800.0;
                default:
                    // Tick/Volume/Range bars have no fixed duration; fall back to the
                    // most recent observed bar-to-bar time delta.
                    return CurrentBar > 0 ? Math.Max(1.0, (Time[0] - Time[1]).TotalSeconds) : 60.0;
            }
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
        [Display(Name = "Use Real Volume", Order = 3, GroupName = "Parameters", Description = "Kept for parity with the source indicator; NinjaTrader volume feeds don't expose a separate tick-volume series, so this has no effect.")]
        public bool UseRealVolume { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Display Bars", Order = 4, GroupName = "Parameters")]
        public int DisplayBars { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, double.MaxValue)]
        [Display(Name = "Filter Volume", Order = 5, GroupName = "Parameters")]
        public double FilterVol { get; set; }

        [NinjaScriptProperty]
        [Range(0.0001, double.MaxValue)]
        [Display(Name = "Ring Step", Order = 6, GroupName = "Parameters")]
        public double Step { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Levels", Order = 7, GroupName = "Parameters")]
        public bool ShowLevels { get; set; }

        [XmlIgnore]
        [Display(Name = "Upper Color (Pivot High)", Order = 8, GroupName = "Parameters")]
        public Brush UpperColor { get; set; }

        [Browsable(false)]
        public string UpperColorSerializable
        {
            get { return Serialize.BrushToString(UpperColor); }
            set { UpperColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Lower Color (Pivot Low)", Order = 9, GroupName = "Parameters")]
        public Brush LowerColor { get; set; }

        [Browsable(false)]
        public string LowerColorSerializable
        {
            get { return Serialize.BrushToString(LowerColor); }
            set { LowerColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Label Color", Order = 10, GroupName = "Parameters")]
        public Brush LabelColor { get; set; }

        [Browsable(false)]
        public string LabelColorSerializable
        {
            get { return Serialize.BrushToString(LabelColor); }
            set { LabelColor = Serialize.StringToBrush(value); }
        }
        #endregion
    }
}
