// EAGapFillPivot — NT8 port of the EminiAddict.com thinkorswim study
// "Half Gap Fill, Full Gap Fill, and Trading Hours only Pivot Point"
// ($V:build_1324:2009.05.09:1.0.3) + Samir's added +/-10/20/30 pt bands.
//
// v1.4:
//   - Per-level visibility toggles (Visibility group): Pivot, Half Gap, Full Gap,
//     Globex Pivot, and per-ring band toggles (+/-1x, +/-2x, +/-3x).
//   - Hover tooltip: move the cursor within a few px of a level line and a
//     name+value label pops up next to the cursor, offset ABOVE the line so it
//     never covers the line itself (chart-label no-overlap rule). Today's levels only.
//   - Optional info box (Draw.TextFixed, corner selectable): one line per visible
//     level — name, price, signed distance from last price in points — sorted
//     nearest-first. Off by default.
//   - Line plots run from the RTH open bar to EOD; current-day projection ahead
//     of the last bar inherits each plot's Plots-panel style and is capped at the
//     cash close; outside RTH every projection object is actively removed.
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
//     empirically against this machine's MarketInternalExporter output. Works on
//     any intraday timeframe; today's RTH open = Open[] of the first bar ending
//     after RthOpenTime.
//   - Session times are properties in the CHART'S DISPLAY TIMEZONE. Defaults are
//     CT (RTH 08:30-15:00, globex close 16:00); NT here is set to Chicago.
//     The 2009 original was ET (09:30/16:00/16:15).
//   - ShowTodayOnly / ShowGlobexPivot / HideGapFillsOnceHit implement the ToS
//     inputs' INTENT (the original's conditions were inverted bugs).
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
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// declared in the parent namespace so NT's auto-generated wrappers
// (Indicators/MarketAnalyzerColumns/Strategies namespaces) can all resolve it
namespace NinjaTrader.NinjaScript
{
    public enum EagfDistanceUnit { Points, Ticks }
}

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

        // today's active (visible) levels, for the hover tooltip + info box
        private class Lvl { public string Name; public double Val; public int PlotIdx; }
        private readonly List<Lvl> activeLevels = new List<Lvl>();
        private readonly object levelLock = new object();

        // mouse state for the hover tooltip (chart-control pixel coords)
        private int  mouseX = -1, mouseY = -1;
        private bool mouseValid;
        private double lastPrice;   // latest close, for info-box distances

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                       = "EAGapFillPivot";
                Description                = "EminiAddict gap fill + RTH pivot (ToS port): levels from the RTH open bar to EOD, hover labels, optional distance box";
                Calculate                  = Calculate.OnBarClose;
                IsOverlay                  = true;
                DisplayInDataBox           = true;
                PaintPriceMarkers          = true;
                IsSuspendedWhileInactive   = true;

                ShowTodayOnly       = false;
                HideGapFillsOnceHit = false;
                RthOpenTime         = 83000;    // HHmmss, chart display time (CT default)
                RthCloseTime        = 150000;
                GlobexCloseTime     = 160000;
                OffsetPoints        = 10;
                FutureBars          = 20;

                ShowPivot           = true;
                ShowHalfGap         = true;
                ShowFullGap         = true;
                ShowGlobexPivot     = false;
                ShowBand1           = true;
                ShowBand2           = true;
                ShowBand3           = true;

                ShowHoverLabel      = true;
                ShowInfoBox         = true;
                InfoBoxPosition     = TextPosition.TopRight;
                InfoBoxTopOffset    = 80;
                DistanceUnit        = EagfDistanceUnit.Points;
                ShowTouchMarkers    = true;
                EnableTouchAlerts   = false;
                AlertSound          = "Alert1.wav";

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
            else if (State == State.DataLoaded)
            {
                if (ChartControl != null)
                {
                    ChartControl.MouseMove  += OnChartMouseMove;
                    ChartControl.MouseLeave += OnChartMouseLeave;
                }
            }
            else if (State == State.Terminated)
            {
                if (ChartControl != null)
                {
                    ChartControl.MouseMove  -= OnChartMouseMove;
                    ChartControl.MouseLeave -= OnChartMouseLeave;
                }
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

                // overnight/premarket (new trading day, after the globex reopen,
                // before the RTH open): draw the pending next-session levels as
                // projection lines. 15:00-16:00 post-settlement stays empty.
                bool overnight = isLastDay && curClose > 0
                    && (t > GlobexCloseTime || t <= RthOpenTime);
                if (overnight)
                {
                    double oFull  = curClose;
                    double oPivot = (curClose + curHigh + curLow) / 3.0;
                    bool[] oRing  = { ShowBand1, ShowBand2, ShowBand3 };
                    FutureLine("piv",  0, oPivot, FutureBars, ShowPivot);
                    // provisional half gap vs current price; locks in at the open
                    FutureLine("half", 1, oFull + (Close[0] - oFull) / 2.0, FutureBars, ShowHalfGap);
                    FutureLine("full", 2, oFull, FutureBars, ShowFullGap);
                    FutureLine("gpiv", 3, pendingGlobexClose > 0
                        ? (pendingGlobexClose + curHigh + curLow) / 3.0 : 0,
                        FutureBars, ShowGlobexPivot && pendingGlobexClose > 0);
                    for (int k = 1; k <= 3; k++)
                    {
                        FutureLine("p" + k, 2 + 2 * k, oFull + k * OffsetPoints, FutureBars, oRing[k - 1]);
                        FutureLine("m" + k, 3 + 2 * k, oFull - k * OffsetPoints, FutureBars, oRing[k - 1]);
                    }
                }
                else
                {
                    RemoveAllLines();   // hard guarantee: nothing after the cash close
                }

                if (isLastDay)
                {
                    // hover + info box stay live outside RTH with the pending
                    // next-session levels (half gap provisional until the open)
                    BuildPendingLevels(Close[0]);
                    lastPrice = Close[0];
                }
                return;
            }

            double pivot   = (prevClose + prevHigh + prevLow) / 3.0;
            double halfGap = prevClose + (rthOpen - prevClose) / 2.0;
            double fullGap = prevClose;

            bool showHalf = ShowHalfGap && !(HideGapFillsOnceHit && halfHit);
            bool showFull = ShowFullGap && !(HideGapFillsOnceHit && fullHit);
            bool haveGpiv = ShowGlobexPivot && prevGlobexClose > 0;
            double gpiv   = haveGpiv ? (prevGlobexClose + prevHigh + prevLow) / 3.0 : 0;
            bool[] ring   = { ShowBand1, ShowBand2, ShowBand3 };

            if (ShowPivot) Values[0][0] = pivot;   else Values[0].Reset();
            if (showHalf)  Values[1][0] = halfGap; else Values[1].Reset();
            if (showFull)  Values[2][0] = fullGap; else Values[2].Reset();
            if (haveGpiv)  Values[3][0] = gpiv;    else Values[3].Reset();
            for (int k = 1; k <= 3; k++)
            {
                if (ring[k - 1])
                {
                    Values[2 + 2 * k][0] = fullGap + k * OffsetPoints;
                    Values[3 + 2 * k][0] = fullGap - k * OffsetPoints;
                }
                else
                {
                    Values[2 + 2 * k].Reset();
                    Values[3 + 2 * k].Reset();
                }
            }

            // register FIRST touches AFTER plotting so the touch bar stays visible
            if (!halfHit && High[0] >= halfGap && Low[0] <= halfGap) { halfHit = true; OnLevelTouch("half", "Half Gap", halfGap, 1); }
            if (!fullHit && High[0] >= fullGap && Low[0] <= fullGap) { fullHit = true; OnLevelTouch("full", "Full Gap", fullGap, 2); }

            if (!isLastDay)
                return;

            // ---- current day only: projection lines, tooltip inventory, info box ----
            int ahead = BarsAhead(t);
            FutureLine("piv",  0, pivot,   ahead, ShowPivot);
            FutureLine("half", 1, halfGap, ahead, showHalf);
            FutureLine("full", 2, fullGap, ahead, showFull);
            FutureLine("gpiv", 3, gpiv,    ahead, haveGpiv);
            for (int k = 1; k <= 3; k++)
            {
                FutureLine("p" + k, 2 + 2 * k, fullGap + k * OffsetPoints, ahead, ring[k - 1]);
                FutureLine("m" + k, 3 + 2 * k, fullGap - k * OffsetPoints, ahead, ring[k - 1]);
            }

            lock (levelLock)
            {
                activeLevels.Clear();
                if (ShowPivot) activeLevels.Add(new Lvl { Name = "Pivot",     Val = pivot,   PlotIdx = 0 });
                if (showHalf)  activeLevels.Add(new Lvl { Name = "Half Gap",  Val = halfGap, PlotIdx = 1 });
                if (showFull)  activeLevels.Add(new Lvl { Name = "Full Gap",  Val = fullGap, PlotIdx = 2 });
                if (haveGpiv)  activeLevels.Add(new Lvl { Name = "Glbx Piv",  Val = gpiv,    PlotIdx = 3 });
                for (int k = 1; k <= 3; k++)
                {
                    if (!ring[k - 1]) continue;
                    activeLevels.Add(new Lvl { Name = "FG +" + k * OffsetPoints, Val = fullGap + k * OffsetPoints, PlotIdx = 2 + 2 * k });
                    activeLevels.Add(new Lvl { Name = "FG -" + k * OffsetPoints, Val = fullGap - k * OffsetPoints, PlotIdx = 3 + 2 * k });
                }
            }

            lastPrice = Close[0];
        }

        // levels known BEFORE the next RTH open (and after today's close), built
        // from the still-accumulating cur* values; half gap is provisional
        // ("~", vs the current price) until the upcoming session's open prints
        private void BuildPendingLevels(double px)
        {
            lock (levelLock)
            {
                activeLevels.Clear();
                if (curHigh <= 0 || curClose <= 0)
                    return;
                double fullGap = curClose;
                double pivot   = (curClose + curHigh + curLow) / 3.0;
                bool[] ring    = { ShowBand1, ShowBand2, ShowBand3 };
                if (ShowPivot)   activeLevels.Add(new Lvl { Name = "Pivot",    Val = pivot,   PlotIdx = 0 });
                if (ShowHalfGap) activeLevels.Add(new Lvl { Name = "Half Gap~", Val = fullGap + (px - fullGap) / 2.0, PlotIdx = 1 });
                if (ShowFullGap) activeLevels.Add(new Lvl { Name = "Full Gap", Val = fullGap, PlotIdx = 2 });
                if (ShowGlobexPivot && pendingGlobexClose > 0)
                    activeLevels.Add(new Lvl { Name = "Glbx Piv", Val = (pendingGlobexClose + curHigh + curLow) / 3.0, PlotIdx = 3 });
                for (int k = 1; k <= 3; k++)
                {
                    if (!ring[k - 1]) continue;
                    activeLevels.Add(new Lvl { Name = "FG +" + k * OffsetPoints, Val = fullGap + k * OffsetPoints, PlotIdx = 2 + 2 * k });
                    activeLevels.Add(new Lvl { Name = "FG -" + k * OffsetPoints, Val = fullGap - k * OffsetPoints, PlotIdx = 3 + 2 * k });
                }
            }
        }

        // info box, custom-rendered so each row draws in its level's plot color:
        // one line per visible level, nearest first, signed distance in points/ticks
        private void RenderInfoBox()
        {
            List<Lvl> snap;
            lock (levelLock) snap = new List<Lvl>(activeLevels);
            double last = lastPrice;
            if (snap.Count == 0 || last <= 0)
                return;
            snap.Sort((a, b) => Math.Abs(a.Val - last).CompareTo(Math.Abs(b.Val - last)));

            var rows = new List<string>();
            var idxs = new List<int>();
            foreach (Lvl l in snap)
            {
                double d = l.Val - last;
                string dist = DistanceUnit == EagfDistanceUnit.Ticks
                    ? string.Format("{0}{1:F0}t", d >= 0 ? "+" : "-", Math.Abs(d) / TickSize)
                    : string.Format("{0}{1:F2}", d >= 0 ? "+" : "-", Math.Abs(d));
                rows.Add(string.Format("{0,-9} {1,9}  {2,8}",
                    l.Name, Instrument.MasterInstrument.FormatPrice(l.Val), dist));
                idxs.Add(l.PlotIdx);
            }

            using (var tf = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Consolas", 13f))
            {
                var layouts = new List<SharpDX.DirectWrite.TextLayout>();
                float maxW = 0, rowH = 0;
                foreach (string r in rows)
                {
                    var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, r, tf, 600, 30);
                    layouts.Add(tl);
                    maxW = Math.Max(maxW, tl.Metrics.Width);
                    rowH = Math.Max(rowH, tl.Metrics.Height);
                }
                float pad = 6, margin = 10;
                float w = maxW + 2 * pad, h = rows.Count * rowH + 2 * pad;
                float x, y;
                switch (InfoBoxPosition)
                {
                    case TextPosition.TopLeft:     x = ChartPanel.X + margin;                    y = ChartPanel.Y + margin + InfoBoxTopOffset; break;
                    case TextPosition.BottomLeft:  x = ChartPanel.X + margin;                    y = ChartPanel.Y + ChartPanel.H - h - margin; break;
                    case TextPosition.BottomRight: x = ChartPanel.X + ChartPanel.W - w - margin; y = ChartPanel.Y + ChartPanel.H - h - margin; break;
                    case TextPosition.Center:      x = ChartPanel.X + (ChartPanel.W - w) / 2;    y = ChartPanel.Y + (ChartPanel.H - h) / 2;    break;
                    default:                       x = ChartPanel.X + ChartPanel.W - w - margin; y = ChartPanel.Y + margin + InfoBoxTopOffset; break; // TopRight
                }
                var rect = new SharpDX.RectangleF(x, y, w, h);
                using (var bg = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0f, 0f, 0.75f)))
                    RenderTarget.FillRectangle(rect, bg);
                using (var border = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0.4f, 0.4f, 0.4f, 1f)))
                    RenderTarget.DrawRectangle(rect, border);
                for (int i = 0; i < layouts.Count; i++)
                {
                    using (var b = Plots[idxs[i]].Brush.ToDxBrush(RenderTarget))
                        RenderTarget.DrawTextLayout(new SharpDX.Vector2(x + pad, y + pad + i * rowH), layouts[i], b);
                    layouts[i].Dispose();
                }
            }
        }

        // hover tooltip: name + value next to the cursor when within a few px of a
        // level line, offset above the line so it never overlaps it
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (RenderTarget == null)
                return;

            if (ShowInfoBox)
                RenderInfoBox();

            if (!ShowHoverLabel || !mouseValid)
                return;

            List<Lvl> snap;
            lock (levelLock) snap = new List<Lvl>(activeLevels);
            if (snap.Count == 0)
                return;

            if (mouseX < ChartPanel.X || mouseX > ChartPanel.X + ChartPanel.W ||
                mouseY < ChartPanel.Y || mouseY > ChartPanel.Y + ChartPanel.H)
                return;

            // nearest level within 8 px of the cursor
            Lvl best = null; double bestPx = 8.0; float bestY = 0;
            foreach (Lvl l in snap)
            {
                float y = chartScale.GetYByValue(l.Val);
                double dpx = Math.Abs(mouseY - y);
                if (dpx <= bestPx) { bestPx = dpx; best = l; bestY = y; }
            }
            if (best == null)
                return;

            string txt = best.Name + "  " + Instrument.MasterInstrument.FormatPrice(best.Val);
            using (var tf = new SharpDX.DirectWrite.TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Segoe UI", 14f))
            using (var tl = new SharpDX.DirectWrite.TextLayout(NinjaTrader.Core.Globals.DirectWriteFactory, txt, tf, 500, 30))
            {
                float w = tl.Metrics.Width + 10, h = tl.Metrics.Height + 6;
                float x = Math.Min(mouseX + 14, ChartPanel.X + ChartPanel.W - w);
                float y = bestY - h - 8;                       // above the line
                if (y < ChartPanel.Y) y = bestY + 8;           // below if no room
                var rect = new SharpDX.RectangleF(x, y, w, h);

                using (var bg = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new SharpDX.Color4(0f, 0f, 0f, 0.85f)))
                    RenderTarget.FillRectangle(rect, bg);
                using (var border = Plots[best.PlotIdx].Brush.ToDxBrush(RenderTarget))
                {
                    RenderTarget.DrawRectangle(rect, border);
                    RenderTarget.DrawTextLayout(new SharpDX.Vector2(x + 5, y + 3), tl, border);
                }
            }
        }

        private void OnChartMouseMove(object sender, System.Windows.Input.MouseEventArgs e)
        {
            if (ChartControl == null) return;
            var p  = e.GetPosition(ChartControl);
            mouseX = ChartingExtensions.ConvertToHorizontalPixels(p.X, ChartControl.PresentationSource);
            mouseY = ChartingExtensions.ConvertToVerticalPixels(p.Y, ChartControl.PresentationSource);
            mouseValid = true;
            if (ShowHoverLabel) ForceRefresh();
        }

        private void OnChartMouseLeave(object sender, System.Windows.Input.MouseEventArgs e)
        {
            mouseValid = false;
            if (ChartControl != null && ShowHoverLabel) ForceRefresh();
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

        // first touch of a gap level: diamond marker on the touch bar at the level
        // price (per-day tag, persists for review) + optional real-time alert
        private void OnLevelTouch(string key, string name, double level, int plotIdx)
        {
            // HARD INVARIANT: gap fills only exist during RTH — never mark or
            // alert a touch on an overnight/premarket bar, no matter the caller
            int t = ToTime(Time[0]);
            if (t <= RthOpenTime || t > RthCloseTime)
                return;
            if (ShowTouchMarkers)
                Draw.Diamond(this, "EAGF_hit_" + key + "_" + curRthDate.ToString("yyyyMMdd"),
                    false, 0, level, Plots[plotIdx].Brush);
            if (EnableTouchAlerts && State == State.Realtime)
                Alert("EAGF_" + key + "_" + curRthDate.ToString("yyyyMMdd"), Priority.High,
                    Instrument.FullName + ": " + name + " touched @ " + Instrument.MasterInstrument.FormatPrice(level),
                    NinjaTrader.Core.Globals.InstallDir + @"\sounds\" + AlertSound, 10,
                    Brushes.Black, Plots[plotIdx].Brush);
        }

        private void RemoveAllLines()
        {
            RemoveDrawObject("EAGF_piv");
            RemoveDrawObject("EAGF_half");
            RemoveDrawObject("EAGF_full");
            RemoveDrawObject("EAGF_gpiv");
            for (int k = 1; k <= 3; k++)
            {
                RemoveDrawObject("EAGF_p" + k);
                RemoveDrawObject("EAGF_m" + k);
            }
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
        [Range(1, 500)]
        [Display(Name = "Extend into future (bars, capped at EOD)", GroupName = "Parameters", Order = 6)]
        public int FutureBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Pivot point", GroupName = "Visibility", Order = 0)]
        public bool ShowPivot { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Half gap fill", GroupName = "Visibility", Order = 1)]
        public bool ShowHalfGap { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Full gap fill", GroupName = "Visibility", Order = 2)]
        public bool ShowFullGap { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Globex pivot", GroupName = "Visibility", Order = 3)]
        public bool ShowGlobexPivot { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Bands +/-1x", GroupName = "Visibility", Order = 4)]
        public bool ShowBand1 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Bands +/-2x", GroupName = "Visibility", Order = 5)]
        public bool ShowBand2 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Bands +/-3x", GroupName = "Visibility", Order = 6)]
        public bool ShowBand3 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Hover label (name + value)", GroupName = "Labels", Order = 0)]
        public bool ShowHoverLabel { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Info box (levels + distance)", GroupName = "Labels", Order = 1)]
        public bool ShowInfoBox { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Info box position", GroupName = "Labels", Order = 2)]
        public TextPosition InfoBoxPosition { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2000)]
        [Display(Name = "Info box offset from top (px)", GroupName = "Labels", Order = 3)]
        public int InfoBoxTopOffset { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Distance unit", GroupName = "Labels", Order = 4)]
        public EagfDistanceUnit DistanceUnit { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Mark first gap-level touch", GroupName = "Touch", Order = 0)]
        public bool ShowTouchMarkers { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Alert on first gap-level touch", GroupName = "Touch", Order = 1)]
        public bool EnableTouchAlerts { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Alert sound file", GroupName = "Touch", Order = 2)]
        public string AlertSound { get; set; }
        #endregion
    }
}
