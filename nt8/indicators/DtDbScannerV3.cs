#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// DtDbScannerV3 — DtDbScannerV2 (IsVisible-synced drawings) with re-weighted
// quality score. Detection, confirm/invalidate/expiry, drawing and alert logic
// are unchanged from V2. Only change (2026-10-02, user decision: trend context
// matters most for a reversal pattern like DT/DB):
//
//   factor          V1/V2   V3
//   symmetry         35%    15%
//   depth (ATR)      25%    20%
//   time symmetry    15%    15%
//   trend context    25%    50%
//
// 2026-10-08: (a) swing ties handled like NT8's built-in Swing (earlier of two
// equal highs/lows is the pivot); (b) DT/DB pairing looks back through all
// earlier pivots within MaxBarsBetween, not just the previous one. Rollback
// copy of the pre-(b) file: rollback/DtDbScannerV3_2026-10-08_pre-lookback.cs.bak
//
// 2026-10-12: optional ABR sizing (peak tolerance + min valley depth as a
// multiple of the average High-Low of the last AbrBars bars); neckline-break
// marker is a triangle (was an arrow; text glyph, size = ConfirmTriangleSize,
// DB triangle SeaGreen); black width-4 line joins the two tops/bottoms.
//
// Note: the score gates only the "forming" alert (MinScoreToAlert); the
// CONFIRMED alert still fires regardless of score, same as V1/V2.

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DtDbScannerV3 : Indicator
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

        // Every structure drawn on the chart and not yet resolved. Separate from
        // pendingTop/pendingBottom (which hold only the latest of each type, for
        // alerts) so an older drawing that a newer pattern replaced is still
        // watched and can be deleted when invalidated (DeleteInvalidated).
        private class DrawnStructure
        {
            public string Tag;              // DrawStructure tag prefix
            public bool   IsTop;
            public double Neckline;
            public double InvalidateBeyond;
            public int    FormBar;
        }
        private readonly List<DrawnStructure> openDrawn = new List<DrawnStructure>();

        // ---- state ----------------------------------------------------------
        private readonly List<Pivot> highs = new List<Pivot>();
        private readonly List<Pivot> lows  = new List<Pivot>();
        private Pending pendingTop;
        private Pending pendingBottom;
        private int tickInterval; // auto-read from the chart, used only for labels

        // ── visibility-sync for Draw.* objects (NT8 doesn't tie these to IsVisible) ──
        // OnBarUpdate is NOT a reliable hook for this: toggling the indicator off
        // in the Indicator Manager only sets IsVisible + calls InvalidateVisual(),
        // neither of which fires OnBarUpdate, so a bar-close-only sync can sit
        // stale indefinitely between bars (or forever on a quiet chart). A
        // dispatcher-thread timer checks independently of bar flow.
        private List<DrawingTool> _drawObjs;
        private bool _lastIsVisible;
        private DispatcherTimer _visTimer;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DtDbScannerV3: DtDbScannerV2 (Hide/Show-synced drawings) with re-weighted quality score - 15% symmetry, 20% depth, 15% time symmetry, 50% trend context.";
                Name        = "DtDbScannerV3";
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
                UseAbrSizing      = false; // true: peak tolerance + min valley depth = multiple of the average bar range instead of fixed ticks
                AbrBars           = 8;     // bars in the average bar range (High-Low), ending at the bar the pattern is evaluated on
                PeakToleranceAbr  = 0.5;   // peak tolerance = this x ABR (when UseAbrSizing)
                MinValleyDepthAbr = 0.5;   // min valley depth = this x ABR (when UseAbrSizing)
                MinBarsBetween    = 6;   // peaks closer than this are noise
                MaxBarsBetween    = 120; // peaks farther apart than this are unrelated
                NecklineBufferTicks = 2; // close must break the neckline by this much to confirm
                ConfirmWithinBars = 150; // if no confirm within this many bars after forming, drop the setup
                MinScoreToAlert   = 50;  // suppress forming-alerts below this quality score
                RearmSeconds      = 30;  // alert re-arm window
                ShowDrawings      = true;
                DeleteInvalidated = false; // true: remove a DT/DB's drawings when price invalidates it (new extreme beyond the peaks/troughs)
                ShowLabel         = true;  // 'DT 72' / 'DB 64' text next to each pattern
                ConfirmTriangleSize = 30;  // font size of the neckline-break triangle (~3x NT8's built-in triangle marker)
                ShowDebugPrints   = true; // Output-tab diagnostics: pivot confirms + DT/DB gate pass/fail
            }
            else if (State == State.Configure)
            {
            }
            else if (State == State.DataLoaded)
            {
                _drawObjs = new List<DrawingTool>();
                _lastIsVisible = IsVisible;

                // Auto-read the chart's tick interval for self-labeling alerts.
                if (BarsPeriod.BarsPeriodType == BarsPeriodType.Tick)
                    tickInterval = BarsPeriod.Value;
                else
                {
                    tickInterval = 0;
                    Print("DtDbScannerV3 WARNING: this is not a Tick chart (BarsPeriodType = "
                          + BarsPeriod.BarsPeriodType + "). It will still run, but it is designed for tick charts.");
                }
            }
            else if (State == State.Historical)
            {
                if (ChartControl == null) return;
                ChartControl.Dispatcher.InvokeAsync(() =>
                {
                    _visTimer = new DispatcherTimer(DispatcherPriority.Background, ChartControl.Dispatcher);
                    _visTimer.Interval = TimeSpan.FromMilliseconds(250);
                    _visTimer.Tick += VisTimer_Tick;
                    _visTimer.Start();
                });
            }
            else if (State == State.Terminated)
            {
                if (ChartControl == null) return;
                ChartControl.Dispatcher.InvokeAsync(() =>
                {
                    if (_visTimer != null) { _visTimer.Tick -= VisTimer_Tick; _visTimer.Stop(); _visTimer = null; }
                });
            }
        }

        private void VisTimer_Tick(object sender, EventArgs e)
        {
            SyncVisibility();
        }

        // propagates the indicator's own IsVisible onto every Draw.* object
        // we've created so far, the moment it flips — NT8 does not do this itself.
        // Called from VisTimer_Tick (reliable, independent of bar flow) and again
        // from OnBarUpdate as a cheap redundant backup.
        private void SyncVisibility()
        {
            if (_lastIsVisible == IsVisible) return;
            _lastIsVisible = IsVisible;
            if (_drawObjs != null)
                for (int k = 0; k < _drawObjs.Count; k++)
                    if (_drawObjs[k] != null) _drawObjs[k].IsVisible = IsVisible;
            if (ChartControl != null) ChartControl.InvalidateVisual();
        }

        protected override void OnBarUpdate()
        {
            SyncVisibility();

            // Need enough bars to confirm a pivot on both sides.
            if (CurrentBar < 2 * SwingStrength + 2)
                return;

            // --- 1. confirm the candidate pivot SwingStrength bars back ------
            DetectPivotAt(SwingStrength);

            // --- 2. evaluate structures off the most recent pivots ----------
            // (run after a new pivot is added inside DetectPivotAt via the lists)

            // --- 3. manage any pending structure for neckline confirmation --
            ManagePending();

            // --- 4. resolve every drawn structure (deletes invalidated ones) --
            SweepDrawn();
        }

        // Confirms whether the bar at `offset` bars ago is a swing high/low.
        // Tie rule matches NT8's built-in Swing: the candidate must be strictly
        // beyond every EARLIER bar, but a LATER bar may equal it. So of two equal
        // highs/lows within SwingStrength, the earlier one becomes the pivot
        // (V1/V2 rejected both).
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
                    highBlockedBy = "earlier bar " + (absBar - k) + " (-" + k + ") high=" + High[offset + k];
                }
                if (isHigh && High[offset - k] > candHigh)
                {
                    isHigh = false;
                    highBlockedBy = "later bar " + (absBar + k) + " (+" + k + ") high=" + High[offset - k];
                }
                if (isLow && Low[offset + k] <= candLow)
                {
                    isLow = false;
                    lowBlockedBy = "earlier bar " + (absBar - k) + " (-" + k + ") low=" + Low[offset + k];
                }
                if (isLow && Low[offset - k] < candLow)
                {
                    isLow = false;
                    lowBlockedBy = "later bar " + (absBar + k) + " (+" + k + ") low=" + Low[offset - k];
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
            double tol, minDepth;
            EffectiveSizes(out tol, out minDepth);

            // V3 look-back: pair the new high with the MOST RECENT earlier high that
            // passes every gate - not just the immediately preceding pivot (V1/V2),
            // which missed a DT whenever a lower swing high sat between the peaks.
            // An earlier high only qualifies if no pivot high between the two peaks
            // is above both of them (the peaks must be the top of the structure).
            double highestBetween = double.MinValue;
            for (int j = highs.Count - 2; j >= 0; j--)
            {
                Pivot p1 = highs[j];
                int barsBetween = p2.Bar - p1.Bar;
                if (barsBetween > MaxBarsBetween) break;            // older pivots are only farther away
                if (highestBetween > p2.Price + tol) break;         // a higher high cuts off every older candidate

                if (TryDoubleTop(p1, p2, highestBetween, tol, minDepth, barsBetween)) return;

                highestBetween = Math.Max(highestBetween, p1.Price);
            }

            if (ShowDebugPrints) Print(Time[0] + "  DT-none p2@" + p2.Bar + "=" + p2.Price + "  (no earlier high qualifies within MaxBarsBetween)");
        }

        // Tests one candidate pair; on pass sets pendingTop, draws, alerts and returns true.
        private bool TryDoubleTop(Pivot p1, Pivot p2, double highestBetween, double tol, double minDepth, int barsBetween)
        {
            if (highestBetween > Math.Max(p1.Price, p2.Price))
            {
                if (ShowDebugPrints) Print(Time[0] + "  DT-reject p1@" + p1.Bar + " p2@" + p2.Bar + "  reason=HIGHER_HIGH_BETWEEN (" + highestBetween + ")");
                return false;
            }

            Pivot valley = LowestLowBetween(p1.Bar, p2.Bar);
            if (valley == null)
            {
                if (ShowDebugPrints) Print(Time[0] + "  DT-reject p1@" + p1.Bar + " p2@" + p2.Bar + "  reason=NO_VALLEY (no confirmed low between the two highs)");
                return false;
            }

            double peakDiff = Math.Abs(p1.Price - p2.Price);
            double valleyDepth = Math.Min(p1.Price, p2.Price) - valley.Price;

            if (ShowDebugPrints)
                Print(Time[0] + "  DT-check p1@" + p1.Bar + "=" + p1.Price + " p2@" + p2.Bar + "=" + p2.Price
                    + "  peakDiff=" + Math.Round(peakDiff / TickSize) + "t(tol<=" + Math.Round(tol / TickSize, 1) + "t " + (peakDiff <= tol ? "OK" : "FAIL") + ")"
                    + "  valleyDepth=" + Math.Round(valleyDepth / TickSize) + "t(min>=" + Math.Round(minDepth / TickSize, 1) + "t " + (valleyDepth >= minDepth ? "OK" : "FAIL") + ")"
                    + SizeModeNote()
                    + "  barsBetween=" + barsBetween + "(" + MinBarsBetween + "-" + MaxBarsBetween + " " + (barsBetween >= MinBarsBetween && barsBetween <= MaxBarsBetween ? "OK" : "FAIL") + ")");

            if (peakDiff > tol) return false;
            if (valleyDepth < minDepth) return false;
            if (barsBetween < MinBarsBetween || barsBetween > MaxBarsBetween) return false;

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

            if (ShowDrawings)
            {
                DrawStructure(p1, valley, p2, score, isTop: true);
                TrackDrawn(pendingTop, "DT_" + p2.Bar);   // tag must match DrawStructure
            }

            if (score >= MinScoreToAlert)
                FireAlert("DTform_" + p2.Bar, Priority.High,
                    Label() + " DT forming  score " + score.ToString("F0"), Brushes.Firebrick);
            return true;
        }

        // --------------------------------------------------------------------
        //  DOUBLE BOTTOM: mirror image
        // --------------------------------------------------------------------
        private void CheckDoubleBottom()
        {
            if (lows.Count < 2) return;

            Pivot t2 = lows[lows.Count - 1];
            double tol, minDepth;
            EffectiveSizes(out tol, out minDepth);

            // V3 look-back (mirror of CheckDoubleTop): most recent earlier low that
            // passes every gate, with no pivot low between below both troughs.
            double lowestBetween = double.MaxValue;
            for (int j = lows.Count - 2; j >= 0; j--)
            {
                Pivot t1 = lows[j];
                int barsBetween = t2.Bar - t1.Bar;
                if (barsBetween > MaxBarsBetween) break;
                if (lowestBetween < t2.Price - tol) break;

                if (TryDoubleBottom(t1, t2, lowestBetween, tol, minDepth, barsBetween)) return;

                lowestBetween = Math.Min(lowestBetween, t1.Price);
            }

            if (ShowDebugPrints) Print(Time[0] + "  DB-none t2@" + t2.Bar + "=" + t2.Price + "  (no earlier low qualifies within MaxBarsBetween)");
        }

        private bool TryDoubleBottom(Pivot t1, Pivot t2, double lowestBetween, double tol, double minDepth, int barsBetween)
        {
            if (lowestBetween < Math.Min(t1.Price, t2.Price))
            {
                if (ShowDebugPrints) Print(Time[0] + "  DB-reject t1@" + t1.Bar + " t2@" + t2.Bar + "  reason=LOWER_LOW_BETWEEN (" + lowestBetween + ")");
                return false;
            }

            Pivot peak = HighestHighBetween(t1.Bar, t2.Bar);
            if (peak == null)
            {
                if (ShowDebugPrints) Print(Time[0] + "  DB-reject t1@" + t1.Bar + " t2@" + t2.Bar + "  reason=NO_PEAK (no confirmed high between the two lows)");
                return false;
            }

            double troughDiff = Math.Abs(t1.Price - t2.Price);
            double peakHeight = peak.Price - Math.Max(t1.Price, t2.Price);

            if (ShowDebugPrints)
                Print(Time[0] + "  DB-check t1@" + t1.Bar + "=" + t1.Price + " t2@" + t2.Bar + "=" + t2.Price
                    + "  troughDiff=" + Math.Round(troughDiff / TickSize) + "t(tol<=" + Math.Round(tol / TickSize, 1) + "t " + (troughDiff <= tol ? "OK" : "FAIL") + ")"
                    + "  peakHeight=" + Math.Round(peakHeight / TickSize) + "t(min>=" + Math.Round(minDepth / TickSize, 1) + "t " + (peakHeight >= minDepth ? "OK" : "FAIL") + ")"
                    + SizeModeNote()
                    + "  barsBetween=" + barsBetween + "(" + MinBarsBetween + "-" + MaxBarsBetween + " " + (barsBetween >= MinBarsBetween && barsBetween <= MaxBarsBetween ? "OK" : "FAIL") + ")");

            if (troughDiff > tol) return false;
            if (peakHeight < minDepth) return false;
            if (barsBetween < MinBarsBetween || barsBetween > MaxBarsBetween) return false;

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

            if (ShowDrawings)
            {
                DrawStructure(t1, peak, t2, score, isTop: false);
                TrackDrawn(pendingBottom, "DB_" + t2.Bar); // tag must match DrawStructure
            }

            if (score >= MinScoreToAlert)
                FireAlert("DBform_" + t2.Bar, Priority.High,
                    Label() + " DB forming  score " + score.ToString("F0"), Brushes.SeaGreen);
            return true;
        }

        // --------------------------------------------------------------------
        //  Neckline confirmation / invalidation / expiry
        // --------------------------------------------------------------------
        private void ManagePending()
        {
            double buf = NecklineBufferTicks * TickSize;

            if (pendingTop != null)
            {
                if (High[0] > pendingTop.InvalidateBeyond)                                             // new high -> void
                {
                    pendingTop = null;                     // drawing deletion: SweepDrawn()
                }
                else if (CurrentBar - pendingTop.FormBar > ConfirmWithinBars) pendingTop = null;       // expired
                else if (Close[0] < pendingTop.Neckline - buf)
                {
                    FireAlert("DTconf_" + pendingTop.FormBar, Priority.High,
                        Label() + " DT CONFIRMED  score " + pendingTop.Score.ToString("F0")
                        + "  neckline " + pendingTop.Neckline.ToString(), Brushes.Red);
                    if (ShowDrawings)
                    {
                        TrackDrawObj(DrawConfirmTriangle("DTconfTri_" + pendingTop.FormBar, true, High[0] + 4 * TickSize, Brushes.Red));
                    }
                    pendingTop = null;
                }
            }

            if (pendingBottom != null)
            {
                if (Low[0] < pendingBottom.InvalidateBeyond)                                           // new low -> void
                {
                    pendingBottom = null;                  // drawing deletion: SweepDrawn()
                }
                else if (CurrentBar - pendingBottom.FormBar > ConfirmWithinBars) pendingBottom = null;
                else if (Close[0] > pendingBottom.Neckline + buf)
                {
                    FireAlert("DBconf_" + pendingBottom.FormBar, Priority.High,
                        Label() + " DB CONFIRMED  score " + pendingBottom.Score.ToString("F0")
                        + "  neckline " + pendingBottom.Neckline.ToString(), Brushes.Lime);
                    if (ShowDrawings)
                    {
                        TrackDrawObj(DrawConfirmTriangle("DBconfTri_" + pendingBottom.FormBar, false, Low[0] - 4 * TickSize, Brushes.SeaGreen));
                    }
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

            double score = 100.0 * (0.15 * symmetry + 0.20 * depthScore + 0.15 * timeSym + 0.50 * trend);
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

            TrackDrawObj(Draw.Line(this, tag + "_l1", false, aAgo, a.Price, midAgo, mid.Price, c, DashStyleHelper.Solid, 2));
            TrackDrawObj(Draw.Line(this, tag + "_l2", false, midAgo, mid.Price, bAgo, b.Price, c, DashStyleHelper.Solid, 2));
            TrackDrawObj(Draw.Line(this, tag + "_neck", false, midAgo, mid.Price, 0, mid.Price, c, DashStyleHelper.Dash, 2));
            TrackDrawObj(Draw.Line(this, tag + "_peaks", false, aAgo, a.Price, bAgo, b.Price, Brushes.Black, DashStyleHelper.Solid, 4)); // joins the two tops/bottoms
            if (ShowLabel)
                TrackDrawObj(Draw.Text(this, tag + "_txt", (isTop ? "DT " : "DB ") + score.ToString("F0"),
                          bAgo, isTop ? b.Price + 10 * TickSize : b.Price - 10 * TickSize, c));
        }

        private void TrackDrawn(Pending p, string tag)
        {
            if (p == null) return;
            openDrawn.Add(new DrawnStructure
            {
                Tag              = tag,
                IsTop            = p.IsTop,
                Neckline         = p.Neckline,
                InvalidateBeyond = p.InvalidateBeyond,
                FormBar          = p.FormBar
            });
        }

        // Same resolution rules/order as ManagePending, applied to EVERY drawn
        // structure (incl. ones a newer pattern replaced as the pending one):
        // invalidated -> delete drawings (if DeleteInvalidated) and stop watching;
        // expired or neckline close-break -> keep drawings, stop watching.
        private void SweepDrawn()
        {
            double buf = NecklineBufferTicks * TickSize;
            for (int i = openDrawn.Count - 1; i >= 0; i--)
            {
                DrawnStructure d = openDrawn[i];
                bool invalid   = d.IsTop ? High[0] > d.InvalidateBeyond : Low[0] < d.InvalidateBeyond;
                bool expired   = CurrentBar - d.FormBar > ConfirmWithinBars;
                bool confirmed = d.IsTop ? Close[0] < d.Neckline - buf : Close[0] > d.Neckline + buf;

                if (invalid)
                {
                    if (DeleteInvalidated) RemoveStructure(d.Tag);
                    openDrawn.RemoveAt(i);
                }
                else if (expired || confirmed)
                {
                    openDrawn.RemoveAt(i);
                }
            }
        }

        // Removes every drawing DrawStructure made for one structure (invalidated setups,
        // when DeleteInvalidated is on). Suffixes must match DrawStructure.
        private void RemoveStructure(string tag)
        {
            if (string.IsNullOrEmpty(tag)) return;
            string[] parts = { "_l1", "_l2", "_neck", "_peaks", "_txt" };
            foreach (string s in parts)
                RemoveDrawObject(tag + s);
        }

        // Neckline-break marker. NT8's Draw.TriangleUp/Down have no size setting, so the
        // triangle is a text glyph (U+25BC down / U+25B2 up) whose font size sets its size.
        // Nudged half its height away from the bar so it doesn't overlap the candle.
        private DrawingTool DrawConfirmTriangle(string tag, bool isTop, double y, Brush brush)
        {
            string glyph = isTop ? "▼" : "▲";
            int nudge = isTop ? ConfirmTriangleSize / 2 : -ConfirmTriangleSize / 2;
            return Draw.Text(this, tag, true, glyph, 0, y, nudge, brush,
                             new SimpleFont("Arial", ConfirmTriangleSize), TextAlignment.Center,
                             Brushes.Transparent, Brushes.Transparent, 0);
        }

        // records a freshly-created Draw.* object so SyncVisibility() can flip
        // it later, and matches it to the indicator's current IsVisible now.
        private void TrackDrawObj(DrawingTool obj)
        {
            if (obj == null) return;
            obj.IsVisible = IsVisible;
            if (_drawObjs != null) _drawObjs.Add(obj);
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

        // average bar range (High-Low) of the last AbrBars bars, ending at the current bar
        private double AvgBarRange()
        {
            int n = Math.Min(AbrBars, CurrentBar + 1);
            if (n <= 0) return 0;
            double sum = 0;
            for (int k = 0; k < n; k++) sum += High[k] - Low[k];
            return sum / n;
        }

        // peak tolerance + min valley depth in price: fixed ticks, or multiples of ABR
        private void EffectiveSizes(out double tol, out double minDepth)
        {
            if (UseAbrSizing)
            {
                double abr = AvgBarRange();
                tol      = PeakToleranceAbr * abr;
                minDepth = MinValleyDepthAbr * abr;
            }
            else
            {
                tol      = PeakToleranceTicks * TickSize;
                minDepth = MinValleyDepthTicks * TickSize;
            }
        }

        // debug-print suffix showing which sizing mode produced tol/min
        private string SizeModeNote()
        {
            if (!UseAbrSizing) return "  [ticks]";
            return "  [ABR" + AbrBars + "=" + Math.Round(AvgBarRange() / TickSize, 1) + "t x" + PeakToleranceAbr + "/x" + MinValleyDepthAbr + "]";
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
        [Display(Name = "Show drawings", Description = "Draw the structure, peak line, neckline, score and confirm triangles.", Order = 10, GroupName = "3. Alerts")]
        public bool ShowDrawings { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show debug prints", Description = "Verbose: prints a pivot-test line every bar (pivot or, if blocked, which bar blocked it) plus every DT/DB gate pass/fail, to the NinjaScript Output tab.", Order = 11, GroupName = "4. Debug")]
        public bool ShowDebugPrints { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Size from avg bar range", Description = "On: peak tolerance and min valley depth = multiple x average bar range (ABR) of the last N bars, instead of the fixed tick settings above.", Order = 12, GroupName = "1. Structure")]
        public bool UseAbrSizing { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "ABR bars", Description = "Number of bars in the average bar range (High-Low), ending at the bar the pattern is evaluated on.", Order = 13, GroupName = "1. Structure")]
        public int AbrBars { get; set; }

        [NinjaScriptProperty, Range(0.0, double.MaxValue)]
        [Display(Name = "Peak tolerance (x ABR)", Description = "Used when 'Size from avg bar range' is on: max peak/trough difference = this x ABR.", Order = 14, GroupName = "1. Structure")]
        public double PeakToleranceAbr { get; set; }

        [NinjaScriptProperty, Range(0.0, double.MaxValue)]
        [Display(Name = "Min valley depth (x ABR)", Description = "Used when 'Size from avg bar range' is on: min pullback between the peaks = this x ABR.", Order = 15, GroupName = "1. Structure")]
        public double MinValleyDepthAbr { get; set; }

        [NinjaScriptProperty, Range(4, 200)]
        [Display(Name = "Confirm triangle size", Description = "Font size of the neckline-break triangle.", Order = 16, GroupName = "3. Alerts")]
        public int ConfirmTriangleSize { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Delete invalidated DT/DB", Description = "Remove a pattern's drawings (lines, peak line, neckline, score label) when price makes a new extreme beyond its peaks/troughs before confirming. Expired patterns are kept.", Order = 17, GroupName = "3. Alerts")]
        public bool DeleteInvalidated { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show DT/DB label", Description = "Show the 'DT 72' / 'DB 64' text (pattern type + score) next to each pattern.", Order = 18, GroupName = "3. Alerts")]
        public bool ShowLabel { get; set; }
        #endregion
    }
}
