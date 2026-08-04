// EAGapFillPivot — NT8 port of the EminiAddict.com thinkorswim study
// "Half Gap Fill, Full Gap Fill, and Trading Hours only Pivot Point"
// ($V:build_1324:2009.05.09:1.0.3) + Samir's added +/-10/20/30 pt bands.
//
// v1.2 DISPLAY: pure line segments (no plots/dots). TODAY's levels only, each
// drawn as a horizontal Draw.Line from LookbackBars behind the current bar to
// FutureBars into the right margin. (The ToS original could only paint per-bar
// dots — no future projection or trailing window exists in thinkscript.)
//
// LEVELS:
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
//   - HideGapFillsOnceHit: half/full lines are removed once price touches them
//     intraday (the ToS setHiding intent; its actual condition was inverted).
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
                Description                = "EminiAddict gap fill + RTH pivot (ToS port): today's levels as line segments, LookbackBars back to FutureBars forward";
                Calculate                  = Calculate.OnBarClose;
                IsOverlay                  = true;
                DisplayInDataBox           = false;
                PaintPriceMarkers          = false;
                IsSuspendedWhileInactive   = true;

                HideGapFillsOnceHit = false;
                ShowGlobexPivot     = false;
                RthOpenTime         = 83000;    // HHmmss, chart display time (CT default)
                RthCloseTime        = 150000;
                GlobexCloseTime     = 160000;
                OffsetPoints        = 10;
                LookbackBars        = 20;
                FutureBars          = 20;
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

            // draw only for the chart's last (= current) day, during its RTH
            if (!isRth || prevClose <= 0 || Time[0].Date != Bars.GetTime(Bars.Count - 1).Date)
                return;

            double pivot   = (prevClose + prevHigh + prevLow) / 3.0;
            double halfGap = prevClose + (rthOpen - prevClose) / 2.0;
            double fullGap = prevClose;

            LevelLine("piv",  pivot,   Brushes.Cyan,  2, true);
            LevelLine("half", halfGap, Brushes.Lime,  2, !(HideGapFillsOnceHit && halfHit));
            LevelLine("full", fullGap, Brushes.White, 2, !(HideGapFillsOnceHit && fullHit));
            LevelLine("gpiv", ShowGlobexPivot && prevGlobexClose > 0
                ? (prevGlobexClose + prevHigh + prevLow) / 3.0 : 0,
                Brushes.LightGreen, 2, ShowGlobexPivot && prevGlobexClose > 0);
            for (int k = 1; k <= 3; k++)
            {
                LevelLine("p" + k, fullGap + k * OffsetPoints, Brushes.Silver, 1, true);
                LevelLine("m" + k, fullGap - k * OffsetPoints, Brushes.Silver, 1, true);
            }

            // register touches AFTER drawing so the touch bar's line is still visible
            if (High[0] >= halfGap && Low[0] <= halfGap) halfHit = true;
            if (High[0] >= fullGap && Low[0] <= fullGap) fullHit = true;
        }

        // one horizontal segment per level: LookbackBars behind the current bar
        // to FutureBars into the right margin. Constant tags -> the segment
        // advances with each new bar instead of stacking.
        private void LevelLine(string key, double y, Brush brush, int width, bool show)
        {
            string tag = "EAGF_" + key;
            if (!show)
            {
                RemoveDrawObject(tag);
                return;
            }
            int back = Math.Min(LookbackBars, CurrentBar);
            Draw.Line(this, tag, false, back, y, -FutureBars, y, brush, DashStyleHelper.Solid, width);
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Hide gap fills once hit", GroupName = "Parameters", Order = 0)]
        public bool HideGapFillsOnceHit { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show globex pivot", GroupName = "Parameters", Order = 1)]
        public bool ShowGlobexPivot { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "RTH open (HHmmss, chart time)", GroupName = "Parameters", Order = 2)]
        public int RthOpenTime { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "RTH close (HHmmss, chart time)", GroupName = "Parameters", Order = 3)]
        public int RthCloseTime { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "Globex close (HHmmss, chart time)", GroupName = "Parameters", Order = 4)]
        public int GlobexCloseTime { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, double.MaxValue)]
        [Display(Name = "Offset band step (points)", GroupName = "Parameters", Order = 5)]
        public double OffsetPoints { get; set; }

        [NinjaScriptProperty]
        [Range(0, 5000)]
        [Display(Name = "Line length back (bars)", GroupName = "Parameters", Order = 6)]
        public int LookbackBars { get; set; }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Extend into future (bars)", GroupName = "Parameters", Order = 7)]
        public int FutureBars { get; set; }
        #endregion
    }
}
