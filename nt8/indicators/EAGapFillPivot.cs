// EAGapFillPivot — NT8 port of the EminiAddict.com thinkorswim study
// "Half Gap Fill, Full Gap Fill, and Trading Hours only Pivot Point"
// ($V:build_1324:2009.05.09:1.0.3) + Samir's added +/-10/20/30 pt bands.
//
// v1.3 DISPLAY: line PLOTS (fully customizable per-level in the chart dialog's
// Plots panel — color/width/dash) starting at the RTH OPEN bar and running
// right until EOD. On the current day the levels are additionally projected up
// to FutureBars past the current bar via Draw.Line segments that INHERIT each
// plot's Plots-panel style, capped so they never extend past the RTH close.
// (The ToS original could only paint per-bar dots — no future projection
// exists in thinkscript.)
//
// LEVELS (default colors):
//   PivotPoint   = (prevRthClose + prevRthHigh + prevRthLow) / 3   [cyan]
//   HalfGapFill  = prevRthClose + (todayRthOpen - prevRthClose)/2  [lime]
//   FullGapFill  = prevRthClose                                    [white]
//   GlobexPivot  = (prevGlobexClose + prevRthHigh + prevRthLow)/3  [light green, off by default]
//   FullGap +/- 1x,2x,3x OffsetPoints bands                        [silver]
//
// PORT NOTES vs the ToS original:
//   - NT8 stamps bars with their END time (ToS uses start time) — verified
//     empirically against this machine's MarketInternalExporter output. So the
//     ToS 09:45 "offset" bar gymnastics are gone and this works on ANY intraday
//     timeframe. Today's RTH open = Open[] of the first bar ending after RthOpenTime.
//   - Session times are properties in the CHART'S DISPLAY TIMEZONE. Defaults are
//     CT (RTH 08:30-15:00, globex close 16:00); NT here is set to Chicago.
//     The 2009 original was ET (09:30/16:00/16:15).
//   - ShowTodayOnly / ShowGlobexPivot / HideGapFillsOnceHit implement the ToS
//     inputs' INTENT (the original's conditions were inverted bugs).
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
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class EAGapFillPivot : Indicator
    {
        // today's building RTH values
        private DateTime curRthDate = DateTime.MinValue;
        private double   curHigh, curLow, curClose, rthOpen;
        // yesterday's completed values (what we draw from)
        private double   prevHigh, prevLow, prevClose, prevGlobexClose;
        // globex close captured after today's RTH, promoted at next RTH roll
        private double   pendingGlobexClose;
        private bool     halfHit, fullHit;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                       = "EAGapFillPivot";
                Description                = "EminiAddict gap fill + RTH pivot (ToS port): levels from the RTH open bar to EOD, projected ahead intraday";
                Calculate                  = Calculate.OnBarClose;
                IsOverlay                  = true;
                DisplayInDataBox           = true;
                PaintPriceMarkers          = true;
                IsSuspendedWhileInactive   = true;

                ShowTodayOnly       = false;
                HideGapFillsOnceHit = false;
                ShowGlobexPivot     = false;
                RthOpenTime         = 83000;    // HHmmss, chart display time (CT default)
                RthCloseTime        = 150000;
                GlobexCloseTime     = 160000;
                OffsetPoints        = 10;
                FutureBars          = 20;

                AddPlot(new Stroke(Brushes.Cyan,       2), PlotStyle.Line, "PivotPoint");    // Values[0]
                AddPlot(new Stroke(Brushes.Lime,       2), PlotStyle.Line, "HalfGapFill");   // Values[1]
                AddPlot(new Stroke(Brushes.White,      2), PlotStyle.Line, "FullGapFill");   // Values[2]
                AddPlot(new Stroke(Brushes.LightGreen, 2), PlotStyle.Line, "GlobexPivot");   // Values[3]
                AddPlot(new Stroke(Brushes.Silver,     1), PlotStyle.Line, "FullGapP1");     // Values[4]
                AddPlot(new Stroke(Brushes.Silver,     1), PlotStyle.Line, "FullGapM1");     // Values[5]
                AddPlot(new Stroke(Brushes.Silver,     1), PlotStyle.Line, "FullGapP2");     // Values[6]
                AddPlot(new Stroke(Brushes.Silver,     1), PlotStyle.Line, "FullGapM2");     // Values[7]
                AddPlot(new Stroke(Brushes.Silver,     1), PlotStyle.Line, "FullGapP3");     // Values[8]
                AddPlot(new Stroke(Brushes.Silver,     1), PlotStyle.Line, "FullGapM3");     // Values[9]
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1 || !Bars.BarsType.IsIntraday)
                return;

            int t     = ToTime(Time[0]);   // bar END time, HHmmss
            int tPrev = ToTime(Time[1]);
            bool isRth = t > RthOpenTime && t <= RthCloseTime;

            // capture the globex close: first bar whose end time crosses GlobexCloseTime
            if (tPrev < GlobexCloseTime && t >= GlobexCloseTime)
                pendingGlobexClose = (t == GlobexCloseTime) ? Close[0] : Close[1];

            if (isRth)
            {
                if (Time[0].Date != curRthDate)
                {
                    // first RTH bar of a new day: roll yesterday's values, start today's
                    if (curHigh > 0)
                    {
                        prevHigh        = curHigh;
                        prevLow         = curLow;
                        prevClose       = curClose;
                        prevGlobexClose = pendingGlobexClose;
                    }
                    curRthDate = Time[0].Date;
                    rthOpen    = Open[0];
                    curHigh    = High[0];
                    curLow     = Low[0];
                    halfHit    = false;
                    fullHit    = false;
                }
                else
                {
                    curHigh = Math.Max(curHigh, High[0]);
                    curLow  = Math.Min(curLow,  Low[0]);
                }
                curClose = Close[0];
            }

            bool isLastDay = Time[0].Date == Bars.GetTime(Bars.Count - 1).Date;
            bool plotOk    = isRth && prevClose > 0 && (!ShowTodayOnly || isLastDay);

            if (!plotOk)
            {
                for (int i = 0; i < 10; i++)
                    Values[i].Reset();
                return;
            }

            double pivot   = (prevClose + prevHigh + prevLow) / 3.0;
            double halfGap = prevClose + (rthOpen - prevClose) / 2.0;
            double fullGap = prevClose;

            Values[0][0] = pivot;

            if (!(HideGapFillsOnceHit && halfHit)) Values[1][0] = halfGap; else Values[1].Reset();
            if (!(HideGapFillsOnceHit && fullHit)) Values[2][0] = fullGap; else Values[2].Reset();

            bool haveGpiv = ShowGlobexPivot && prevGlobexClose > 0;
            double gpiv   = haveGpiv ? (prevGlobexClose + prevHigh + prevLow) / 3.0 : 0;
            if (haveGpiv) Values[3][0] = gpiv; else Values[3].Reset();

            Values[4][0] = fullGap + 1 * OffsetPoints;
            Values[5][0] = fullGap - 1 * OffsetPoints;
            Values[6][0] = fullGap + 2 * OffsetPoints;
            Values[7][0] = fullGap - 2 * OffsetPoints;
            Values[8][0] = fullGap + 3 * OffsetPoints;
            Values[9][0] = fullGap - 3 * OffsetPoints;

            // register touches AFTER plotting so the touch bar stays visible
            if (High[0] >= halfGap && Low[0] <= halfGap) halfHit = true;
            if (High[0] >= fullGap && Low[0] <= fullGap) fullHit = true;

            // project today's levels ahead of the current bar, capped at EOD.
            // Constant tags -> the segments advance with each new bar.
            if (isLastDay)
            {
                int ahead = BarsAhead(t);
                FutureLine("piv",  0, pivot,   ahead, true);
                FutureLine("half", 1, halfGap, ahead, !(HideGapFillsOnceHit && halfHit));
                FutureLine("full", 2, fullGap, ahead, !(HideGapFillsOnceHit && fullHit));
                FutureLine("gpiv", 3, gpiv,    ahead, haveGpiv);
                for (int k = 1; k <= 3; k++)
                {
                    FutureLine("p" + k, 2 + 2 * k, fullGap + k * OffsetPoints, ahead, true);
                    FutureLine("m" + k, 3 + 2 * k, fullGap - k * OffsetPoints, ahead, true);
                }
            }
        }

        // how many bars to project: FutureBars, but never past the RTH close.
        // For non-time bar types the remaining-bar count is unknowable -> FutureBars.
        private int BarsAhead(int tHHmmss)
        {
            int barSecs = 0;
            if (BarsPeriod.BarsPeriodType == BarsPeriodType.Minute)      barSecs = BarsPeriod.Value * 60;
            else if (BarsPeriod.BarsPeriodType == BarsPeriodType.Second) barSecs = BarsPeriod.Value;
            if (barSecs <= 0)
                return FutureBars;
            int tSecs     = tHHmmss / 10000 * 3600 + tHHmmss / 100 % 100 * 60 + tHHmmss % 100;
            int closeSecs = RthCloseTime / 10000 * 3600 + RthCloseTime / 100 % 100 * 60 + RthCloseTime % 100;
            return Math.Min(FutureBars, Math.Max(0, (closeSecs - tSecs) / barSecs));
        }

        // future segment styled from the corresponding plot, so Plots-panel
        // customization (color/width/dash) applies to the projection too
        private void FutureLine(string key, int plotIdx, double y, int ahead, bool show)
        {
            string tag = "EAGF_" + key;
            if (!show || ahead <= 0)
            {
                RemoveDrawObject(tag);
                return;
            }
            Draw.Line(this, tag, false, 0, y, -ahead, y,
                Plots[plotIdx].Brush, Plots[plotIdx].DashStyleHelper, (int)Plots[plotIdx].Width);
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Show today only", GroupName = "Parameters", Order = 0)]
        public bool ShowTodayOnly { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Hide gap fills once hit", GroupName = "Parameters", Order = 1)]
        public bool HideGapFillsOnceHit { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show globex pivot", GroupName = "Parameters", Order = 2)]
        public bool ShowGlobexPivot { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "RTH open (HHmmss, chart time)", GroupName = "Parameters", Order = 3)]
        public int RthOpenTime { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "RTH close (HHmmss, chart time)", GroupName = "Parameters", Order = 4)]
        public int RthCloseTime { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "Globex close (HHmmss, chart time)", GroupName = "Parameters", Order = 5)]
        public int GlobexCloseTime { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, double.MaxValue)]
        [Display(Name = "Offset band step (points)", GroupName = "Parameters", Order = 6)]
        public double OffsetPoints { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Extend into future (bars, capped at EOD)", GroupName = "Parameters", Order = 7)]
        public int FutureBars { get; set; }
        #endregion
    }
}
