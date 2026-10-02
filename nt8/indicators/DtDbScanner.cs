#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// DtDbScanner — Double Top / Double Bottom structure scanner for tick charts.
//
// WHAT IT DOES
//   Drop this on an ES tick chart (any tick interval). It auto-reads the chart's
//   tick count from BarsPeriod.Value, so a 2500-tick chart labels its alerts
//   "DB @ 2500" with zero per-chart configuration. It detects DT / DB structures
//   on THAT chart's own primary series, draws them, scores them 0-100, and alerts
//   twice: once when the structure FORMS (second peak/trough prints near the first),
//   and again when the neckline CONFIRMS (close beyond the intervening valley/peak).
//
//   Execution is manual by design — the indicator finds and scores the setup; you
//   pull the trigger in ChartTrader on whichever chart shows the best score.
//
// TUNING — the whole game is the detection definition. Every geometric rule below
//   is a parameter. Defaults are a sane ES starting point, not gospel. Walk them
//   on a few tick intervals first (that was the plan), then widen coverage.
//
// NEXT STAGE (not in v1): a cross-chart ranker. Because `static` fields are shared
//   across all instances of an indicator in the NT8 process, each chart's instance
//   can register its live score into a shared static registry, and one panel reads
//   the whole thing to tell you WHICH open chart has the best setup right now.
//   Hook points for that are marked `// RANKER:` below.

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DtDbScanner : Indicator
    {
        // ---- internal types -------------------------------------------------
        private class Pivot
        {
            public double Price;
            public int    Bar;     // absolute CurrentBar index
            public Pivot(double price, int bar) { Price = price; Bar = bar; }
        }

        private class Pending
        {
            public double Neckline;        // the level a confirming close must break
            public double InvalidateBeyond; // if price moves beyond this first, the setup is void
            public int    FormBar;         // CurrentBar when the structure formed
            public double Score;
            public bool   IsTop;           // true = double top, false = double bottom
        }

        // ---- state ----------------------------------------------------------
        private readonly List<Pivot> highs = new List<Pivot>();
        private readonly List<Pivot> lows  = new List<Pivot>();
        private Pending pendingTop;
        private Pending pendingBottom;
        private int tickInterval; // auto-read from the chart, used only for labels

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Scans a tick chart for Double Top / Double Bottom structures, scores them, and alerts (forming + neckline confirm) with the chart's tick interval as the label.";
                Name        = "DtDbScanner";
                Calculate   = Calculate.OnBarClose; // detection on closed bars avoids repaint; switch to OnEachTick for faster neckline breaks
                IsOverlay   = true;
                DisplayInDataBox = false;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;

                // --- detection parameters (defaults = ES starting point) ---
                SwingStrength     = 4;   // bars required on each side of a pivot to confirm it (bigger = fewer, stronger swings; adds this much lag)
                PeakToleranceTicks = 6;  // max price difference between the two peaks/troughs, in ticks
                MinValleyDepthTicks = 10;// the pullback between peaks must be at least this deep, in ticks (rejects flat tops)
                MinBarsBetween    = 6;   // peaks closer than this are noise
                MaxBarsBetween    = 120; // peaks farther apart than this are unrelated
                NecklineBufferTicks = 2; // close must break the neckline by this much to confirm
                ConfirmWithinBars = 150; // if no confirm within this many bars after forming, drop the setup
                MinScoreToAlert   = 50;  // suppress forming-alerts below this quality score
                RearmSeconds      = 30;  // alert re-arm window
                ShowDrawings      = true;
                ShowDebugPrints   = true; // Output-tab diagnostics: pivot confirms + DT/DB gate pass/fail
            }
            else if (State == State.Configure)
            {
            }
            else if (State == State.DataLoaded)
            {
                // Auto-read the chart's tick interval for self-labeling alerts.
                if (BarsPeriod.BarsPeriodType == BarsPeriodType.Tick)
                    tickInterval = BarsPeriod.Value;
                else
                {
                    tickInterval = 0;
                    Print("DtDbScanner WARNING: this is not a Tick chart (BarsPeriodType = "
                          + BarsPeriod.BarsPeriodType + "). It will still run, but it is designed for tick charts.");
                }
            }
        }

        protected override void OnBarUpdate()
        {
            // Need enough bars to confirm a pivot on both sides.
            if (CurrentBar < 2 * SwingStrength + 2)
                return;

            // --- 1. confirm the candidate pivot SwingStrength bars back ------
            DetectPivotAt(SwingStrength);

            // --- 2. evaluate structures off the most recent pivots ----------
            // (run after a new pivot is added inside DetectPivotAt via the lists)

            // --- 3. manage any pending structure for neckline confirmation --
            ManagePending();
        }

        // Confirms whether the bar at `offset` bars ago is a strict swing high/low.
        private void DetectPivotAt(int offset)
        {
            double candHigh = High[offset];
            double candLow  = Low[offset];
            bool isHigh = true, isLow = true;
            string highBlockedBy = null, lowBlockedBy = null; // first bar that disqualified the candidate (debug only)

            int absBar = CurrentBar - offset;

            for (int k = 1; k <= SwingStrength; k++)
            {
                if (isHigh && High[offset + k] >= candHigh)
                {
                    isHigh = false;
                    highBlockedBy = "later bar " + (absBar + k) + " (+" + k + ") high=" + High[offset + k];
                }
                if (isHigh && High[offset - k] >= candHigh)
                {
                    isHigh = false;
                    highBlockedBy = "earlier bar " + (absBar - k) + " (-" + k + ") high=" + High[offset - k];
                }
                if (isLow && Low[offset + k] <= candLow)
                {
                    isLow = false;
                    lowBlockedBy = "later bar " + (absBar + k) + " (+" + k + ") low=" + Low[offset + k];
                }
                if (isLow && Low[offset - k] <= candLow)
                {
                    isLow = false;
                    lowBlockedBy = "earlier bar " + (absBar - k) + " (-" + k + ") low=" + Low[offset - k];
                }
            }

            // Per-bar candidate test — the only way to see WHY a bar never became a
            // pivot at all (e.g. a nearby bar within SwingStrength disqualified it),
            // which the DT/DB gate prints below can never show since they only run
            // on pivots that already confirmed.
            if (ShowDebugPrints)
                Print(Time[0] + "  pivot-test bar " + absBar
                    + "  HIGH=" + candHigh + " " + (isHigh ? "-> PIVOT" : "blocked by " + highBlockedBy)
                    + "   LOW=" + candLow + " " + (isLow ? "-> PIVOT" : "blocked by " + lowBlockedBy));

            if (isHigh)
            {
                if (highs.Count == 0 || highs[highs.Count - 1].Bar != absBar)
                {
                    highs.Add(new Pivot(candHigh, absBar));
                    TrimPivots(highs);
                    CheckDoubleTop();
                }
            }
            if (isLow)
            {
                if (lows.Count == 0 || lows[lows.Count - 1].Bar != absBar)
                {
                    lows.Add(new Pivot(candLow, absBar));
                    TrimPivots(lows);
                    CheckDoubleBottom();
                }
            }
        }

        private void TrimPivots(List<Pivot> list)
        {
            // keep memory bounded; we never look back more than MaxBarsBetween (+ context)
            while (list.Count > 50) list.RemoveAt(0);
        }

        // --------------------------------------------------------------------
        //  DOUBLE TOP: two swing highs ~equal, with a deep-enough valley between
        // --------------------------------------------------------------------
        private void CheckDoubleTop()
        {
            if (highs.Count < 2) return;

            Pivot p2 = highs[highs.Count - 1];
            Pivot p1 = highs[highs.Count - 2];

            Pivot valley = LowestLowBetween(p1.Bar, p2.Bar);
            if (valley == null)
            {
                if (ShowDebugPrints) Print(Time[0] + "  DT-reject p1@" + p1.Bar + " p2@" + p2.Bar + "  reason=NO_VALLEY (no confirmed low between the two highs)");
                return;
            }

            double tol   = PeakToleranceTicks * TickSize;
            double peakDiff = Math.Abs(p1.Price - p2.Price);
            double valleyDepth = Math.Min(p1.Price, p2.Price) - valley.Price;
            int barsBetween = p2.Bar - p1.Bar;

            if (ShowDebugPrints)
                Print(Time[0] + "  DT-check p1@" + p1.Bar + "=" + p1.Price + " p2@" + p2.Bar + "=" + p2.Price
                    + "  peakDiff=" + Math.Round(peakDiff / TickSize) + "t(tol<=" + PeakToleranceTicks + "t " + (peakDiff <= tol ? "OK" : "FAIL") + ")"
                    + "  valleyDepth=" + Math.Round(valleyDepth / TickSize) + "t(min>=" + MinValleyDepthTicks + "t " + (valleyDepth >= MinValleyDepthTicks * TickSize ? "OK" : "FAIL") + ")"
                    + "  barsBetween=" + barsBetween + "(" + MinBarsBetween + "-" + MaxBarsBetween + " " + (barsBetween >= MinBarsBetween && barsBetween <= MaxBarsBetween ? "OK" : "FAIL") + ")");

            if (peakDiff > tol) return;
            if (valleyDepth < MinValleyDepthTicks * TickSize) return;
            if (barsBetween < MinBarsBetween || barsBetween > MaxBarsBetween) return;

            double score = ScoreStructure(p1, valley, p2, peakDiff, tol, valleyDepth, barsBetween, isTop: true);

            pendingTop = new Pending
            {
                Neckline         = valley.Price,
                InvalidateBeyond = Math.Max(p1.Price, p2.Price),
                FormBar          = CurrentBar,
                Score            = score,
                IsTop            = true
            };

            // RANKER: register score here, e.g. Registry[Instrument+tickInterval] = (score, "DT");

            if (ShowDrawings) DrawStructure(p1, valley, p2, score, isTop: true);

            if (score >= MinScoreToAlert)
                FireAlert("DTform_" + p2.Bar, Priority.High,
                    Label() + " DT forming  score " + score.ToString("F0"), Brushes.Firebrick);
        }

        // --------------------------------------------------------------------
        //  DOUBLE BOTTOM: mirror image
        // --------------------------------------------------------------------
        private void CheckDoubleBottom()
        {
            if (lows.Count < 2) return;

            Pivot t2 = lows[lows.Count - 1];
            Pivot t1 = lows[lows.Count - 2];

            Pivot peak = HighestHighBetween(t1.Bar, t2.Bar);
            if (peak == null)
            {
                if (ShowDebugPrints) Print(Time[0] + "  DB-reject t1@" + t1.Bar + " t2@" + t2.Bar + "  reason=NO_PEAK (no confirmed high between the two lows)");
                return;
            }

            double tol = PeakToleranceTicks * TickSize;
            double troughDiff = Math.Abs(t1.Price - t2.Price);
            double peakHeight = peak.Price - Math.Max(t1.Price, t2.Price);
            int barsBetween = t2.Bar - t1.Bar;

            if (ShowDebugPrints)
                Print(Time[0] + "  DB-check t1@" + t1.Bar + "=" + t1.Price + " t2@" + t2.Bar + "=" + t2.Price
                    + "  troughDiff=" + Math.Round(troughDiff / TickSize) + "t(tol<=" + PeakToleranceTicks + "t " + (troughDiff <= tol ? "OK" : "FAIL") + ")"
                    + "  peakHeight=" + Math.Round(peakHeight / TickSize) + "t(min>=" + MinValleyDepthTicks + "t " + (peakHeight >= MinValleyDepthTicks * TickSize ? "OK" : "FAIL") + ")"
                    + "  barsBetween=" + barsBetween + "(" + MinBarsBetween + "-" + MaxBarsBetween + " " + (barsBetween >= MinBarsBetween && barsBetween <= MaxBarsBetween ? "OK" : "FAIL") + ")");

            if (troughDiff > tol) return;
            if (peakHeight < MinValleyDepthTicks * TickSize) return;
            if (barsBetween < MinBarsBetween || barsBetween > MaxBarsBetween) return;

            double score = ScoreStructure(t1, peak, t2, troughDiff, tol, peakHeight, barsBetween, isTop: false);

            pendingBottom = new Pending
            {
                Neckline         = peak.Price,
                InvalidateBeyond = Math.Min(t1.Price, t2.Price),
                FormBar          = CurrentBar,
                Score            = score,
                IsTop            = false
            };

            // RANKER: register score here.

            if (ShowDrawings) DrawStructure(t1, peak, t2, score, isTop: false);

            if (score >= MinScoreToAlert)
                FireAlert("DBform_" + t2.Bar, Priority.High,
                    Label() + " DB forming  score " + score.ToString("F0"), Brushes.SeaGreen);
        }

        // --------------------------------------------------------------------
        //  Neckline confirmation / invalidation / expiry
        // --------------------------------------------------------------------
        private void ManagePending()
        {
            double buf = NecklineBufferTicks * TickSize;

            if (pendingTop != null)
            {
                if (High[0] > pendingTop.InvalidateBeyond)                 pendingTop = null;          // new high -> void
                else if (CurrentBar - pendingTop.FormBar > ConfirmWithinBars) pendingTop = null;       // expired
                else if (Close[0] < pendingTop.Neckline - buf)
                {
                    FireAlert("DTconf_" + pendingTop.FormBar, Priority.High,
                        Label() + " DT CONFIRMED  score " + pendingTop.Score.ToString("F0")
                        + "  neckline " + pendingTop.Neckline.ToString(), Brushes.Red);
                    if (ShowDrawings)
                        Draw.ArrowDown(this, "DTconfArr_" + pendingTop.FormBar, true, 0, High[0] + 4 * TickSize, Brushes.Red);
                    pendingTop = null;
                }
            }

            if (pendingBottom != null)
            {
                if (Low[0] < pendingBottom.InvalidateBeyond)                 pendingBottom = null;
                else if (CurrentBar - pendingBottom.FormBar > ConfirmWithinBars) pendingBottom = null;
                else if (Close[0] > pendingBottom.Neckline + buf)
                {
                    FireAlert("DBconf_" + pendingBottom.FormBar, Priority.High,
                        Label() + " DB CONFIRMED  score " + pendingBottom.Score.ToString("F0")
                        + "  neckline " + pendingBottom.Neckline.ToString(), Brushes.Lime);
                    if (ShowDrawings)
                        Draw.ArrowUp(this, "DBconfArr_" + pendingBottom.FormBar, true, 0, Low[0] - 4 * TickSize, Brushes.Lime);
                    pendingBottom = null;
                }
            }
        }

        // --------------------------------------------------------------------
        //  Quality score 0-100 — this is what the ranker will compare.
        //  Factors: peak symmetry, valley depth (in ATR band), time symmetry,
        //  prior-trend context. Tune the weights to match what "looks excellent".
        // --------------------------------------------------------------------
        private double ScoreStructure(Pivot a, Pivot mid, Pivot b,
                                      double peakDiff, double tol, double depth,
                                      int barsBetween, bool isTop)
        {
            double atr = (CurrentBar > 14) ? ATR(14)[0] : TickSize * 20;
            if (atr <= 0) atr = TickSize * 20;

            // 1. symmetry: closer peaks score higher (1 at identical, 0 at tolerance edge)
            double symmetry = Clamp01(1.0 - peakDiff / tol);

            // 2. depth: ideal valley/peak size is a band in ATR; full score in [1.5,3] ATR
            double depthAtr = depth / atr;
            double depthScore = Band(depthAtr, 0.3, 1.5, 3.0, 6.0);

            // 3. time symmetry: the two legs (a->mid, mid->b) should be roughly equal
            int leg1 = mid.Bar - a.Bar;
            int leg2 = b.Bar - mid.Bar;
            double timeSym = Clamp01(1.0 - Math.Abs(leg1 - leg2) / (double)Math.Max(1, barsBetween));

            // 4. prior-trend context: a real DT needs a rally into it (DB: a decline)
            double trend = TrendContext(a, isTop, atr);

            double score = 100.0 * (0.35 * symmetry + 0.25 * depthScore + 0.15 * timeSym + 0.25 * trend);
            return Clamp(score, 0, 100);
        }

        // size of the move leading INTO the first peak/trough, normalized to ATR, capped
        private double TrendContext(Pivot first, bool isTop, double atr)
        {
            if (isTop)
            {
                Pivot priorLow = LastPivotBefore(lows, first.Bar);
                if (priorLow == null) return 0.5;
                return Clamp01((first.Price - priorLow.Price) / (atr * 3.0));
            }
            else
            {
                Pivot priorHigh = LastPivotBefore(highs, first.Bar);
                if (priorHigh == null) return 0.5;
                return Clamp01((priorHigh.Price - first.Price) / (atr * 3.0));
            }
        }

        // --------------------------------------------------------------------
        //  helpers
        // --------------------------------------------------------------------
        private Pivot LowestLowBetween(int barA, int barB)
        {
            Pivot best = null;
            foreach (Pivot p in lows)
                if (p.Bar > barA && p.Bar < barB && (best == null || p.Price < best.Price))
                    best = p;
            return best;
        }

        private Pivot HighestHighBetween(int barA, int barB)
        {
            Pivot best = null;
            foreach (Pivot p in highs)
                if (p.Bar > barA && p.Bar < barB && (best == null || p.Price > best.Price))
                    best = p;
            return best;
        }

        private Pivot LastPivotBefore(List<Pivot> list, int bar)
        {
            Pivot best = null;
            foreach (Pivot p in list)
                if (p.Bar < bar && (best == null || p.Bar > best.Bar))
                    best = p;
            return best;
        }

        private void DrawStructure(Pivot a, Pivot mid, Pivot b, double score, bool isTop)
        {
            Brush c = isTop ? Brushes.Firebrick : Brushes.SeaGreen;
            string tag = (isTop ? "DT_" : "DB_") + b.Bar;
            int aAgo   = CurrentBar - a.Bar;
            int midAgo = CurrentBar - mid.Bar;
            int bAgo   = CurrentBar - b.Bar;

            Draw.Line(this, tag + "_l1", false, aAgo, a.Price, midAgo, mid.Price, c, DashStyleHelper.Solid, 2);
            Draw.Line(this, tag + "_l2", false, midAgo, mid.Price, bAgo, b.Price, c, DashStyleHelper.Solid, 2);
            Draw.Line(this, tag + "_neck", false, midAgo, mid.Price, 0, mid.Price, c, DashStyleHelper.Dash, 1);
            Draw.Text(this, tag + "_txt", (isTop ? "DT " : "DB ") + Label() + "  " + score.ToString("F0"),
                      bAgo, isTop ? b.Price + 6 * TickSize : b.Price - 6 * TickSize, c);
        }

        private void FireAlert(string id, Priority priority, string msg, Brush back)
        {
            Alert(id, priority, msg, "", RearmSeconds, back, Brushes.White);
            Print(Time[0] + "  " + msg);
        }

        // label used in every alert/drawing — the chart's own tick interval
        private string Label()
        {
            return tickInterval > 0 ? tickInterval.ToString() : (BarsPeriod.Value + "" + BarsPeriod.BarsPeriodType);
        }

        private static double Clamp(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }
        private static double Clamp01(double v) { return Clamp(v, 0, 1); }

        // trapezoid: 0 below `zeroLo`, ramps to 1 at `fullLo`, stays 1 to `fullHi`, ramps to 0 at `zeroHi`
        private static double Band(double x, double zeroLo, double fullLo, double fullHi, double zeroHi)
        {
            if (x <= zeroLo || x >= zeroHi) return 0;
            if (x < fullLo)  return (x - zeroLo) / (fullLo - zeroLo);
            if (x > fullHi)  return (zeroHi - x) / (zeroHi - fullHi);
            return 1.0;
        }

        #region Properties
        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Swing strength", Description = "Bars required on each side to confirm a pivot (adds this much detection lag).", Order = 1, GroupName = "1. Structure")]
        public int SwingStrength { get; set; }

        [NinjaScriptProperty, Range(0, int.MaxValue)]
        [Display(Name = "Peak tolerance (ticks)", Description = "Max price difference between the two peaks/troughs.", Order = 2, GroupName = "1. Structure")]
        public int PeakToleranceTicks { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Min valley depth (ticks)", Description = "Minimum pullback between the peaks (rejects flat tops).", Order = 3, GroupName = "1. Structure")]
        public int MinValleyDepthTicks { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Min bars between", Description = "Peaks closer than this are treated as noise.", Order = 4, GroupName = "1. Structure")]
        public int MinBarsBetween { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Max bars between", Description = "Peaks farther apart than this are unrelated.", Order = 5, GroupName = "1. Structure")]
        public int MaxBarsBetween { get; set; }

        [NinjaScriptProperty, Range(0, int.MaxValue)]
        [Display(Name = "Neckline buffer (ticks)", Description = "Close must break the neckline by this much to confirm.", Order = 6, GroupName = "2. Confirmation")]
        public int NecklineBufferTicks { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Confirm within bars", Description = "Drop the setup if no confirm within this many bars of forming.", Order = 7, GroupName = "2. Confirmation")]
        public int ConfirmWithinBars { get; set; }

        [NinjaScriptProperty, Range(0, 100)]
        [Display(Name = "Min score to alert", Description = "Suppress forming-alerts below this quality score.", Order = 8, GroupName = "3. Alerts")]
        public double MinScoreToAlert { get; set; }

        [NinjaScriptProperty, Range(0, int.MaxValue)]
        [Display(Name = "Alert re-arm (sec)", Description = "Re-arm window passed to NT8 Alert().", Order = 9, GroupName = "3. Alerts")]
        public int RearmSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show drawings", Description = "Draw the structure, neckline, score and confirm arrows.", Order = 10, GroupName = "3. Alerts")]
        public bool ShowDrawings { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show debug prints", Description = "Verbose: prints a pivot-test line every bar (pivot or, if blocked, which bar blocked it) plus every DT/DB gate pass/fail, to the NinjaScript Output tab.", Order = 11, GroupName = "4. Debug")]
        public bool ShowDebugPrints { get; set; }
        #endregion
    }
}
