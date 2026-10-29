#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;
using System.Xml.Serialization;
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
// 2026-10-17: (a) confirm triangle rebuilt as a real Draw.Triangle (3 explicit
// points sized in ticks/bars) instead of a font glyph — the glyph's
// "ConfirmTriangleSize" font-point value didn't give predictable/working visual
// sizing; (b) the peak/trough line is now perfectly horizontal at the more
// extreme of the two prices (was sloped whenever the two peaks/troughs weren't
// exactly equal); (c) the label's pattern-name ("DT"/"DB") and quality-score
// rating are now two independent toggles instead of one combined ShowLabel.
//
// Note: the score gates only the "forming" alert (MinScoreToAlert); the
// CONFIRMED alert still fires regardless of score, same as V1/V2.

namespace NinjaTrader.NinjaScript.Indicators.My
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
            public string DrawTag;         // DrawStructure tag prefix (set when drawn), links the confirm triangle
            public int    P1Bar, P2Bar;     // the two peak/trough pivot bars (CVD divergence check)
            public double P1Price, P2Price;
        }

        // Every structure still on the chart, oldest first, with its confirm
        // triangle's tag once confirmed. Drives ShowLastN.
        private class DrawnRecord
        {
            public string Tag;
            public string TriTag;
        }
        private readonly List<DrawnRecord> drawnHistory = new List<DrawnRecord>();

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
            public int    NeckBar;          // bar of the valley/peak the neckline starts from
            public int    P1Bar, P2Bar;     // the two peak/trough pivot bars (CVD divergence check)
            public double P1Price, P2Price; // same two pivots' prices (hidden-CVD-divergence check)
        }
        private readonly List<DrawnStructure> openDrawn = new List<DrawnStructure>();

        // a structure that just confirmed (neckline break) and is being watched for a
        // pullback/retest of the neckline, to label the CVD reading at that retest too
        private class WatchRetest
        {
            public string Tag;
            public bool   IsTop;
            public double Neckline;
            public int    ConfirmBar;
            public double BreakCvd;     // smoothed CVD at the confirm/break bar
            public double InvalidateBeyond; // price beyond the tops (DT) / bottoms (DB) -> stop watching
        }
        private readonly List<WatchRetest> watchingRetest = new List<WatchRetest>();

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

        // ── CVD divergence (2026-10-18) ──────────────────────────────────────
        // Same bar-proxy delta as CVDDivergenceOscillator.cs (Volume * close-position-
        // in-range, no tick replay needed): Hist = rolling SUM (Periodic) or EMA of
        // that delta over CvdPeriod bars. At every DT/DB confirm, CVD at the two
        // peak/trough pivots is compared: for a DT, CVD weaker at the 2nd top than the
        // 1st (cvd2 < cvd1) agrees with the bearish thesis; for a DB, CVD stronger at
        // the 2nd trough (cvd2 > cvd1) agrees with the bullish thesis. Labeled for
        // EVERY confirmed instance (agree or not) so the hit rate can be eyeballed —
        // advisory only, not a filter/gate on anything the scanner already does.
        private Series<double> _cvdDelta, _cvdHist;

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

                // --- defaults = user's settings, re-synced 2026-10-29 from the saved live
                // template (Documents\NinjaTrader 8\templates\Indicator\DtDbScannerV3\Default.xml)
                // — this block had drifted from what's actually configured live; every value
                // below now matches that file exactly, not guessed or carried over stale. ---
                SwingStrength     = 3;   // bars required on each side of a pivot to confirm it (bigger = fewer, stronger swings; adds this much lag)
                PeakToleranceTicks = 6;  // max price difference between the two peaks/troughs, in ticks
                MinValleyDepthTicks = 5;// the pullback between peaks must be at least this deep, in ticks (rejects flat tops)
                UseAbrSizing      = true;  // true: peak tolerance + min valley depth = multiple of the average bar range instead of fixed ticks
                AbrBars           = 8;     // bars in the average bar range (High-Low), ending at the bar the pattern is evaluated on
                PeakToleranceAbr  = 0.5;   // peak tolerance = this x ABR (when UseAbrSizing)
                MinValleyDepthAbr = 0.5;   // min valley depth = this x ABR (when UseAbrSizing)
                MinBarsBetween    = 2;   // peaks closer than this are noise
                MaxBarsBetween    = 50;  // peaks farther apart than this are unrelated
                NecklineBufferTicks = 0; // close must break the neckline by this much to confirm
                ConfirmOnClose    = true; // false: a trade beyond the neckline (+buffer) confirms, close not required
                ConfirmWithinBars = 50;  // if no confirm within this many bars after forming, drop the setup
                MinScoreToAlert   = 50;  // suppress forming-alerts below this quality score
                RearmSeconds      = 30;  // alert re-arm window
                ShowDrawings      = true;
                DeleteInvalidated = true;  // true: remove a DT/DB's drawings when price invalidates it (new extreme beyond the peaks/troughs)
                ShowPatternName   = false; // 'DT'/'DB' text next to each pattern
                ShowRating        = false; // quality score number next to each pattern
                DtLegBrush        = Brushes.Transparent;  // peak -> valley -> peak legs of a DT (user turned these off live)
                DbLegBrush        = Brushes.Transparent;  // trough -> peak -> trough legs of a DB (user turned these off live)
                LegDashStyle      = DashStyleHelper.Solid;
                LegWidth          = 2;
                PeakLineBrush     = Brushes.Black;        // line joining the two tops/bottoms
                PeakLineDashStyle = DashStyleHelper.Solid;
                PeakLineWidth     = 2;
                NecklineDtBrush   = Brushes.Firebrick;    // DT neckline (was hardcoded)
                NecklineDbBrush   = Brushes.SeaGreen;     // DB neckline (was hardcoded)
                NecklineDashStyle = DashStyleHelper.Dash;
                NecklineWidth     = 2;
                DtDotBrush        = Brushes.Transparent;  // DT neckline-break dot (user turned off live)
                DbDotBrush        = Brushes.Transparent;  // DB neckline-break dot (user turned off live)
                ShowLastN         = 0;                    // 0 = show all; N = keep only the newest N DT/DB on the chart
                ShowDebugPrints   = true;  // Output-tab diagnostics: pivot confirms + DT/DB gate pass/fail

                ShowCvdDivergence = false;
                CvdPeriod         = 21;
                CvdMode           = CvdCumulativeMode.Periodic;
                CvdDivBrush       = Brushes.Cyan;
                ShowPullbackCvd   = false;
                PullbackWatchBars = 30;
                RetestToleranceTicks = 4;
                FilterToDivergenceOnly = true;
                ShowCvdDivergenceLine = true;
                CvdDivLineDtBrush = Brushes.Firebrick;    // matches CVDDivergenceOscillator.cs's BearColor default
                CvdDivLineDbBrush = Brushes.LimeGreen;    // matches CVDDivergenceOscillator.cs's BullColor default
                ShowHiddenCvdDivergence = true;
                HiddenCvdBrush = Brushes.Orange;
            }
            else if (State == State.Configure)
            {
                _cvdDelta = new Series<double>(this);
                _cvdHist  = new Series<double>(this);
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
                    if (ShowDebugPrints)
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
            UpdateCvd();

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

            // --- 5. watch confirmed structures for a neckline pullback/retest --
            ManageRetest();
        }

        // bar-proxy CVD (same formula as CVDDivergenceOscillator.cs): Volume weighted by
        // where Close sits in the bar's H-L range. Hist = rolling SUM (Periodic) or EMA.
        private void UpdateCvd()
        {
            double range = High[0] - Low[0];
            double buying  = range > 0 ? Volume[0] * (Close[0] - Low[0]) / range : 0;
            double selling = range > 0 ? Volume[0] * (High[0] - Close[0]) / range : 0;
            _cvdDelta[0] = buying - selling;
            _cvdHist[0] = CvdMode == CvdCumulativeMode.Periodic
                ? SUM(_cvdDelta, CvdPeriod)[0]
                : EMA(_cvdDelta, CvdPeriod)[0];
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

            Pivot valley = NecklineLow(p1.Bar, p2.Bar);
            if (valley == null)
            {
                if (ShowDebugPrints) Print(Time[0] + "  DT-reject p1@" + p1.Bar + " p2@" + p2.Bar + "  reason=NO_VALLEY (no bar between the two highs)");
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
                IsTop            = true,
                P1Bar = p1.Bar, P1Price = p1.Price, P2Bar = p2.Bar, P2Price = p2.Price
            };

            // RANKER: register score here, e.g. Registry[Instrument+tickInterval] = (score, "DT");

            if (ShowDrawings)
            {
                DrawStructure(p1, valley, p2, score, isTop: true);
                TrackDrawn(pendingTop, "DT_" + p2.Bar, valley.Bar);   // tag must match DrawStructure
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

            Pivot peak = NecklineHigh(t1.Bar, t2.Bar);
            if (peak == null)
            {
                if (ShowDebugPrints) Print(Time[0] + "  DB-reject t1@" + t1.Bar + " t2@" + t2.Bar + "  reason=NO_PEAK (no bar between the two lows)");
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
                IsTop            = false,
                P1Bar = t1.Bar, P1Price = t1.Price, P2Bar = t2.Bar, P2Price = t2.Price
            };

            // RANKER: register score here.

            if (ShowDrawings)
            {
                DrawStructure(t1, peak, t2, score, isTop: false);
                TrackDrawn(pendingBottom, "DB_" + t2.Bar, peak.Bar); // tag must match DrawStructure
            }

            if (score >= MinScoreToAlert)
                FireAlert("DBform_" + t2.Bar, Priority.High,
                    Label() + " DB forming  score " + score.ToString("F0"), Brushes.SeaGreen);
            return true;
        }

        // --------------------------------------------------------------------
        //  Neckline confirmation / invalidation / expiry
        // --------------------------------------------------------------------
        // Neckline break test on the current bar. ConfirmOnClose (default): the CLOSE
        // must be beyond neckline +/- buffer. Off: any trade beyond it counts (DT: Low,
        // DB: High), even if the bar closes back inside. Detection is still on bar close
        // (Calculate.OnBarClose), so the marker appears when that bar closes.
        private bool BrokeNeckline(bool isTop, double neckline, double buf)
        {
            if (isTop) return (ConfirmOnClose ? Close[0] : Low[0])  < neckline - buf;
            return            (ConfirmOnClose ? Close[0] : High[0]) > neckline + buf;
        }

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
                else if (BrokeNeckline(true, pendingTop.Neckline, buf))
                {
                    FireAlert("DTconf_" + pendingTop.FormBar, Priority.High,
                        Label() + " DT CONFIRMED  score " + pendingTop.Score.ToString("F0")
                        + "  neckline " + pendingTop.Neckline.ToString(), Brushes.Red);
                    // alert above fires unconditionally regardless of the filter (same as
                    // score never gating it) — only the confirm-dot VISUAL is gated.
                    if (ShowDrawings && (!FilterToDivergenceOnly || CvdAgrees(true, pendingTop.P1Bar, pendingTop.P2Bar)))
                    {
                        string triTag = "DTconfTri_" + pendingTop.FormBar;
                        TrackDrawObj(DrawConfirmDot(triTag, true, High[0] + 4 * TickSize, DtDotBrush));
                        LinkTriangle(pendingTop, triTag);
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
                else if (BrokeNeckline(false, pendingBottom.Neckline, buf))
                {
                    FireAlert("DBconf_" + pendingBottom.FormBar, Priority.High,
                        Label() + " DB CONFIRMED  score " + pendingBottom.Score.ToString("F0")
                        + "  neckline " + pendingBottom.Neckline.ToString(), Brushes.Lime);
                    // alert above fires unconditionally regardless of the filter (same as
                    // score never gating it) — only the confirm-dot VISUAL is gated.
                    if (ShowDrawings && (!FilterToDivergenceOnly || CvdAgrees(false, pendingBottom.P1Bar, pendingBottom.P2Bar)))
                    {
                        string triTag = "DBconfTri_" + pendingBottom.FormBar;
                        TrackDrawObj(DrawConfirmDot(triTag, false, Low[0] - 4 * TickSize, DbDotBrush));
                        LinkTriangle(pendingBottom, triTag);
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
        // DT neckline: lowest Low of every bar strictly between the two peaks (no swing
        // pivot required). Outside-bar special case — a peak bar's OWN low also counts
        // when it most likely printed on the valley side of its high: peak-1 bar closing
        // DOWN (high assumed before low), peak-2 bar closing UP (low assumed before high).
        // Dojis (Close == Open) are ambiguous and never count.
        private Pivot NecklineLow(int barA, int barB)
        {
            Pivot best = null;
            for (int bar = barA; bar <= barB; bar++)
            {
                int ago = CurrentBar - bar;
                if (bar == barA && !(Close[ago] < Open[ago])) continue;
                if (bar == barB && !(Close[ago] > Open[ago])) continue;
                if (best == null || Low[ago] < best.Price) best = new Pivot(Low[ago], bar);
            }
            return best;
        }

        // DB neckline: mirror — highest High between the two troughs; trough-1 bar's own
        // high counts if it closed UP (low before high, e.g. an outside up bar), trough-2
        // bar's own high counts if it closed DOWN (high before low).
        private Pivot NecklineHigh(int barA, int barB)
        {
            Pivot best = null;
            for (int bar = barA; bar <= barB; bar++)
            {
                int ago = CurrentBar - bar;
                if (bar == barA && !(Close[ago] > Open[ago])) continue;
                if (bar == barB && !(Close[ago] < Open[ago])) continue;
                if (best == null || High[ago] > best.Price) best = new Pivot(High[ago], bar);
            }
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

            Brush leg = isTop ? DtLegBrush : DbLegBrush;
            TrackDrawObj(Draw.Line(this, tag + "_l1", false, aAgo, a.Price, midAgo, mid.Price, leg, LegDashStyle, LegWidth));
            TrackDrawObj(Draw.Line(this, tag + "_l2", false, midAgo, mid.Price, bAgo, b.Price, leg, LegDashStyle, LegWidth));
            DrawNeckline(tag, isTop, mid.Bar, mid.Price);   // to the current bar; extended on the break (SweepDrawn)
            // joins the two tops/bottoms — perfectly horizontal at the MORE EXTREME of the
            // two prices (the higher top for a DT, the lower bottom for a DB), not sloped
            // between the two actual (possibly unequal) pivot prices.
            double peakLevel = isTop ? Math.Max(a.Price, b.Price) : Math.Min(a.Price, b.Price);
            TrackDrawObj(Draw.Line(this, tag + "_peaks", false, aAgo, peakLevel, bAgo, peakLevel, PeakLineBrush, PeakLineDashStyle, PeakLineWidth));
            if (ShowPatternName || ShowRating)
            {
                string txt = ShowPatternName ? (isTop ? "DT" : "DB") : "";
                if (ShowRating) txt += (txt.Length > 0 ? " " : "") + score.ToString("F0");
                TrackDrawObj(Draw.Text(this, tag + "_txt", txt,
                          bAgo, isTop ? b.Price + 10 * TickSize : b.Price - 10 * TickSize, c));
            }
        }

        // Neckline from the valley/peak bar to the CURRENT bar. Called when the pattern
        // forms, and again (same tag = same line, redrawn) on the bar that closes beyond it.
        private void DrawNeckline(string tag, bool isTop, int neckBar, double price)
        {
            Brush c = isTop ? NecklineDtBrush : NecklineDbBrush;
            TrackDrawObj(Draw.Line(this, tag + "_neck", false, CurrentBar - neckBar, price, 0, price, c, NecklineDashStyle, NecklineWidth));
        }

        private void TrackDrawn(Pending p, string tag, int neckBar)
        {
            if (p == null) return;
            p.DrawTag = tag;
            drawnHistory.Add(new DrawnRecord { Tag = tag });
            EnforceShowLast();
            openDrawn.Add(new DrawnStructure
            {
                Tag              = tag,
                IsTop            = p.IsTop,
                Neckline         = p.Neckline,
                InvalidateBeyond = p.InvalidateBeyond,
                FormBar          = p.FormBar,
                NeckBar          = neckBar,
                P1Bar            = p.P1Bar,
                P2Bar            = p.P2Bar,
                P1Price          = p.P1Price,
                P2Price          = p.P2Price
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
                bool confirmed = BrokeNeckline(d.IsTop, d.Neckline, buf);

                if (invalid)
                {
                    if (DeleteInvalidated)
                    {
                        RemoveStructure(d.Tag);
                        drawnHistory.RemoveAll(r => r.Tag == d.Tag);   // no longer on the chart
                    }
                    openDrawn.RemoveAt(i);
                }
                else if (expired)
                {
                    openDrawn.RemoveAt(i);
                }
                else if (confirmed)
                {
                    // Pure display filter, applied right at confirm — detection/scoring/
                    // confirm itself already happened above (BrokeNeckline), unchanged.
                    // A structure that fails this just loses its drawings, same cleanup
                    // RemoveStructure already does for an invalidated one; it still
                    // confirmed as far as the rest of the indicator (incl. alerts) knows.
                    //
                    // 2026-10-29 FIX: computed cvdHiddenOk BEFORE the gate and let it rescue
                    // a structure the regular check would otherwise delete. Root cause of
                    // "hidden divergence never fires" wasn't the earlier strict-inequality
                    // bug — it's that CvdHiddenAgrees's cvdCond is the exact logical negation
                    // of CvdAgrees (isTop ? cvd2>cvd1 : cvd2<cvd1, vs CvdAgrees's cvd2<cvd1 :
                    // cvd2>cvd1). With the old gate removing anything CvdAgrees didn't like
                    // BEFORE the hidden check ever ran, only agreeing structures survived to
                    // reach it — and agreeing structures can never satisfy hidden's condition
                    // by construction (confirmed via diag log: 0/1339 cvdCond=True). Only
                    // evaluated when the toggle is on, so the no-op case when it's off is
                    // unchanged.
                    bool cvdHiddenOk = ShowHiddenCvdDivergence
                        && CvdHiddenAgrees(d.IsTop, d.P1Bar, d.P2Bar, d.P1Price, d.P2Price);
                    if (FilterToDivergenceOnly && !CvdAgrees(d.IsTop, d.P1Bar, d.P2Bar) && !cvdHiddenOk)
                    {
                        RemoveStructure(d.Tag);
                        drawnHistory.RemoveAll(r => r.Tag == d.Tag);
                        openDrawn.RemoveAt(i);
                        continue;
                    }

                    DrawNeckline(d.Tag, d.IsTop, d.NeckBar, d.Neckline);   // extend to the bar that closed beyond
                    if (ShowCvdDivergence) DrawCvdDivergenceBadge(d);
                    if (ShowCvdDivergenceLine) DrawCvdDivergenceLine(d);
                    if (ShowHiddenCvdDivergence) DrawCvdHiddenDivergenceBadge(d, cvdHiddenOk);
                    // Recolor the existing "_peaks" line (default black, drawn at formation
                    // time in DrawStructure) to HiddenCvdBrush when this structure is a hidden
                    // divergence — same tag, so Draw.Line overwrites it in place rather than
                    // adding a second line. User ask 2026-10-29: wanted the DT/DB peak line
                    // itself to flag hidden divergence, not just the "H.CVD" text badge.
                    if (cvdHiddenOk) RecolorPeaksLine(d, HiddenCvdBrush);
                    // Publish to the shared registry whenever CVD agrees — independent of
                    // every display toggle above, including FilterToDivergenceOnly, so
                    // CVDDivergenceOscillator.cs's "Only show at DT/DB" mode works off this
                    // scanner's actual confirms regardless of which of ITS OWN visuals are on.
                    // Published by TIME (Bars.GetTime), not bar index — a raw index is only
                    // meaningful on THIS chart's own bar series; the consumer may be on a
                    // different bar type/chart entirely (confirmed broken live 2026-10-29:
                    // a 2000-tick chart's CVDDivergenceOscillator drew nothing reading this
                    // scanner's 1000-tick bar indices).
                    if (CvdAgrees(d.IsTop, d.P1Bar, d.P2Bar))
                        DtDbCvdPivotRegistry.Publish(Instrument.FullName, d.IsTop,
                            Bars.GetTime(d.P1Bar), d.P1Price, Bars.GetTime(d.P2Bar), d.P2Price);
                    if (ShowPullbackCvd)
                        watchingRetest.Add(new WatchRetest
                        {
                            Tag = d.Tag, IsTop = d.IsTop, Neckline = d.Neckline,
                            ConfirmBar = CurrentBar, BreakCvd = _cvdHist[0], InvalidateBeyond = d.InvalidateBeyond
                        });
                    openDrawn.RemoveAt(i);
                }
            }
        }

        // ShowLastN > 0: keep only the newest N structures (DT + DB together) on the
        // chart; older ones lose all their drawings incl. the confirm triangle.
        private void EnforceShowLast()
        {
            if (ShowLastN <= 0) return;
            while (drawnHistory.Count > ShowLastN)
            {
                DrawnRecord old = drawnHistory[0];
                RemoveStructure(old.Tag);
                if (!string.IsNullOrEmpty(old.TriTag)) RemoveDrawObject(old.TriTag);
                openDrawn.RemoveAll(d => d.Tag == old.Tag);
                watchingRetest.RemoveAll(w => w.Tag == old.Tag);   // no late retest label for a removed pattern
                drawnHistory.RemoveAt(0);
            }
        }

        // remembers which confirm triangle belongs to which structure (for ShowLastN)
        private void LinkTriangle(Pending p, string triTag)
        {
            if (p == null || p.DrawTag == null) return;
            foreach (DrawnRecord r in drawnHistory)
                if (r.Tag == p.DrawTag) { r.TriTag = triTag; return; }
        }

        // Removes every drawing DrawStructure made for one structure (invalidated setups,
        // when DeleteInvalidated is on). Suffixes must match DrawStructure.
        private void RemoveStructure(string tag)
        {
            if (string.IsNullOrEmpty(tag)) return;
            string[] parts = { "_l1", "_l2", "_neck", "_peaks", "_txt", "_cvd", "_hcvd", "_cvdln", "_rt" };
            foreach (string s in parts)
                RemoveDrawObject(tag + s);
        }

        // Neckline-break marker: NT8's actual native Draw.Dot. Fixed small pixel size, no
        // size parameter at all — which is exactly the point: price/bar-space sizing
        // (ticks/bars) scales with zoom and bar width, so "small" at one zoom level became
        // huge at another. This stays visually small and constant regardless of zoom.
        private DrawingTool DrawConfirmDot(string tag, bool isTop, double anchorY, Brush brush)
        {
            return Draw.Dot(this, tag, false, 0, anchorY, brush);
        }

        // CVD-at-the-two-pivots agree/disagree check. Shared by the badge (labels every
        // confirmed DT/DB, agree or not), FilterToDivergenceOnly in SweepDrawn (removes
        // the drawn lines/neckline/badge for ones that disagree), and the confirm-dot
        // gate in ManagePending below (same filter, applied to the OTHER place a
        // confirmed structure draws something) — one calculation, three call sites.
        private bool CvdAgrees(bool isTop, int p1Bar, int p2Bar)
        {
            double cvd1 = _cvdHist[CurrentBar - p1Bar];
            double cvd2 = _cvdHist[CurrentBar - p2Bar];
            return isTop ? cvd2 < cvd1 : cvd2 > cvd1;
        }

        // CVD-at-the-two-pivots check, labeled for every confirmed DT/DB (agree or not)
        // so the hit rate can be audited visually rather than filtered silently.
        private void DrawCvdDivergenceBadge(DrawnStructure d)
        {
            double cvd1 = _cvdHist[CurrentBar - d.P1Bar];
            double cvd2 = _cvdHist[CurrentBar - d.P2Bar];
            bool agrees = CvdAgrees(d.IsTop, d.P1Bar, d.P2Bar);
            string txt = (agrees ? "CVD✓ " : "CVD✗ ") + (cvd2 - cvd1 >= 0 ? "+" : "") + (cvd2 - cvd1).ToString("F0");
            double y = d.IsTop ? High[0] + 10 * TickSize : Low[0] - 10 * TickSize;
            TrackDrawObj(Draw.Text(this, d.Tag + "_cvd", txt, 0, y, agrees ? CvdDivBrush : Brushes.Gray));
        }

        // HIDDEN CVD divergence, on the SAME two DT/DB pivots the regular check above
        // uses — independent, separate toggle, does not touch CvdAgrees's own return value
        // or the regular badge/line. It DOES get a say in the FilterToDivergenceOnly
        // survive/remove gate in SweepDrawn now (2026-10-29 fix below) — otherwise the two
        // checks being logical negations of each other means hidden could never fire.
        //
        // Mirrors CumulativeDelta.cs's existing ShowHiddenDivergence definition (price
        // makes a SHALLOWER extreme, CVD makes a STRONGER one — continuation shape, the
        // inverse pairing of regular divergence) onto DT/DB's own two pivots instead of
        // an independently-tracked swing stream. One real difference from
        // CumulativeDelta.cs's context: there, hidden divergence is checked on ordinary
        // trend swings mid-trend. Here, P1/P2 are the two tops/bottoms of a REVERSAL
        // pattern, not a continuation leg — so "hidden" firing here (2nd top NOT higher
        // than the 1st + CVD stronger anyway, for a DT) is read as: price already
        // failed to clearly exceed the first top, but order flow was building anyway —
        // a tension against the DT's own bearish thesis, not a trend-continuation call
        // the way it is in CumulativeDelta.cs. Label it as what it mechanically is
        // (same hidden-divergence shape); the interpretation in a reversal-pattern
        // context is for the user to judge, not asserted here.
        //
        // 2026-10-29 FIX: originally a STRICT p2Price < p1Price (DT) / > (DB) — fired
        // zero times. Root cause: TryDoubleTop/TryDoubleBottom only confirm a pattern
        // when peakDiff <= tol in the first place (the two peaks/troughs MUST already
        // be close, often landing on the exact same tick — that's what makes it a
        // recognized "double" pattern), so a strictly-lower 2nd top is a near-empty
        // set by construction, not a rare-but-real condition. Loosened to <=/>= (2nd
        // pivot not clearly BETTER than the 1st, including exactly equal) so the check
        // actually has bars to fire on.
        private bool CvdHiddenAgrees(bool isTop, int p1Bar, int p2Bar, double p1Price, double p2Price)
        {
            double cvd1 = _cvdHist[CurrentBar - p1Bar];
            double cvd2 = _cvdHist[CurrentBar - p2Bar];
            bool priceCond = isTop ? (p2Price <= p1Price) : (p2Price >= p1Price);
            bool cvdCond = isTop ? (cvd2 > cvd1) : (cvd2 < cvd1);
            bool result = priceCond && cvdCond;
            // TEMP DIAGNOSTIC 2026-10-29 — user reports zero hidden divergences even after
            // the strict-inequality fix; logs every evaluation (one per confirmed DT/DB,
            // low volume, no throttling needed) with BOTH sub-conditions broken out, so
            // it's visible whether price never qualifies, CVD never qualifies, or both —
            // instead of just "still zero." Remove once root-caused.
            try
            {
                System.IO.File.AppendAllText(@"C:\Users\Admin\myquant\data\_dtdb_hidden_div_diag.log",
                    DateTime.Now.ToString("HH:mm:ss.fff") + "  isTop=" + isTop
                    + " p1=" + p1Price + " p2=" + p2Price + " priceCond=" + priceCond
                    + " cvd1=" + cvd1.ToString("F1") + " cvd2=" + cvd2.ToString("F1") + " cvdCond=" + cvdCond
                    + " -> " + (result ? "HIDDEN FIRES" : "no") + "\r\n");
            }
            catch { }
            return result;
        }

        // Only drawn when it actually fires (same as CumulativeDelta.cs's hidden
        // divergence — not labeled "no" for every instance like the regular badge is).
        private void DrawCvdHiddenDivergenceBadge(DrawnStructure d, bool hiddenAgrees)
        {
            if (!hiddenAgrees) return;
            double y = d.IsTop ? High[0] + 20 * TickSize : Low[0] - 20 * TickSize;
            TrackDrawObj(Draw.Text(this, d.Tag + "_hcvd", "H.CVD", 0, y, HiddenCvdBrush));
        }

        // Overwrites DrawStructure's "_peaks" line (same tag -> Draw.Line replaces it in
        // place) in the given color. Recomputed at CURRENT bar, not the bar the line was
        // originally drawn at — aAgo/bAgo shift every bar until confirm, same as every
        // other re-anchored draw call in this file.
        private void RecolorPeaksLine(DrawnStructure d, Brush color)
        {
            double peakLevel = d.IsTop ? Math.Max(d.P1Price, d.P2Price) : Math.Min(d.P1Price, d.P2Price);
            int aAgo = CurrentBar - d.P1Bar, bAgo = CurrentBar - d.P2Bar;
            TrackDrawObj(Draw.Line(this, d.Tag + "_peaks", false, aAgo, peakLevel, bAgo, peakLevel, color, PeakLineDashStyle, PeakLineWidth));
        }

        // The actual connecting LINE between the DT/DB's own two pivots — same visual
        // CVDDivergenceOscillator.cs/CVDRealDivergence.cs draw for their own independent
        // divergence pivots (Draw.Line, bull/bear colored), anchored here to the DT/DB's
        // pivots instead. User's own distinction (2026-10-29): the existing text badge
        // isn't the same thing as this line — wanted the line specifically, only at
        // DT/DB spots, not the standalone CVD indicator's own unrelated pivots
        // everywhere on the chart. Drawn only when CvdAgrees (regular) fires, same as
        // CVDDivergenceOscillator.cs only ever draws its own line when its divergence
        // condition holds — never a "disagrees" line.
        private void DrawCvdDivergenceLine(DrawnStructure d)
        {
            if (!CvdAgrees(d.IsTop, d.P1Bar, d.P2Bar)) return;
            int baA = CurrentBar - d.P1Bar, baB = CurrentBar - d.P2Bar;
            Brush color = d.IsTop ? CvdDivLineDtBrush : CvdDivLineDbBrush;
            TrackDrawObj(Draw.Line(this, d.Tag + "_cvdln", false, baA, d.P1Price, baB, d.P2Price, color, DashStyleHelper.Solid, 2));
        }

        // watches a just-confirmed structure for the FIRST bar price pulls back to
        // retest the broken neckline, then labels the CVD reading there too (purely
        // informational — no verdict, no gating).
        private void ManageRetest()
        {
            for (int i = watchingRetest.Count - 1; i >= 0; i--)
            {
                WatchRetest w = watchingRetest[i];
                if (CurrentBar - w.ConfirmBar > PullbackWatchBars) { watchingRetest.RemoveAt(i); continue; }
                if (CurrentBar <= w.ConfirmBar) continue;   // the confirm bar's own High/Low often still
                                                             // sits near the neckline it just broke --
                                                             // a retest can only happen on a LATER bar

                // invalidated (new extreme beyond the tops/bottoms) -> no retest any more;
                // checked first so a bar that both invalidates and touches the neckline gets no label
                bool invalid = w.IsTop ? High[0] > w.InvalidateBeyond : Low[0] < w.InvalidateBeyond;
                if (invalid) { watchingRetest.RemoveAt(i); continue; }

                double tol = RetestToleranceTicks * TickSize;
                bool isRetest = w.IsTop
                    ? High[0] >= w.Neckline - tol && Close[0] <= w.Neckline   // DT: bounce back up, no full reclaim
                    : Low[0]  <= w.Neckline + tol && Close[0] >= w.Neckline;  // DB: pulls back down, no full reclaim
                if (!isRetest) continue;

                double retestCvd = _cvdHist[0];
                double d = retestCvd - w.BreakCvd;
                string txt = "Retest CVDΔ" + (d >= 0 ? "+" : "") + d.ToString("F0");
                double y = w.IsTop ? High[0] + 6 * TickSize : Low[0] - 6 * TickSize;
                TrackDrawObj(Draw.Text(this, w.Tag + "_rt", txt, 0, y, CvdDivBrush));
                watchingRetest.RemoveAt(i);
            }
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

        [Display(Name = "Confirm on close", Description = "On: the bar must CLOSE beyond the neckline (+ buffer). Off: any trade beyond it confirms (DT: low, DB: high), even if the bar closes back inside.", Order = 8, GroupName = "2. Confirmation")]
        public bool ConfirmOnClose { get; set; }

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

        [NinjaScriptProperty]
        [Display(Name = "Delete invalidated DT/DB", Description = "Remove a pattern's drawings (lines, peak line, neckline, score label) when price makes a new extreme beyond its peaks/troughs before confirming. Expired patterns are kept.", Order = 17, GroupName = "3. Alerts")]
        public bool DeleteInvalidated { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show pattern name", Description = "Show the 'DT'/'DB' pattern-type text next to each pattern.", Order = 18, GroupName = "3. Alerts")]
        public bool ShowPatternName { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show rating", Description = "Show the quality score number next to each pattern.", Order = 19, GroupName = "3. Alerts")]
        public bool ShowRating { get; set; }

        [XmlIgnore]
        [Display(Name = "DT leg color", Description = "Color of the peak -> valley -> peak lines of a double top.", Order = 1, GroupName = "5. Lines")]
        public Brush DtLegBrush { get; set; }
        [Browsable(false)]
        public string DtLegBrushSerialize { get { return Serialize.BrushToString(DtLegBrush); } set { DtLegBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "DB leg color", Description = "Color of the trough -> peak -> trough lines of a double bottom.", Order = 2, GroupName = "5. Lines")]
        public Brush DbLegBrush { get; set; }
        [Browsable(false)]
        public string DbLegBrushSerialize { get { return Serialize.BrushToString(DbLegBrush); } set { DbLegBrush = Serialize.StringToBrush(value); } }

        [Display(Name = "Leg style", Description = "Dash style of the peak/valley lines (DT and DB).", Order = 3, GroupName = "5. Lines")]
        public DashStyleHelper LegDashStyle { get; set; }

        [Range(1, 20)]
        [Display(Name = "Leg width", Description = "Width of the peak/valley lines (DT and DB).", Order = 4, GroupName = "5. Lines")]
        public int LegWidth { get; set; }

        [XmlIgnore]
        [Display(Name = "Peak line color", Description = "Color of the line joining the two tops (DT) / two bottoms (DB).", Order = 5, GroupName = "5. Lines")]
        public Brush PeakLineBrush { get; set; }
        [Browsable(false)]
        public string PeakLineBrushSerialize { get { return Serialize.BrushToString(PeakLineBrush); } set { PeakLineBrush = Serialize.StringToBrush(value); } }

        [Display(Name = "Peak line style", Description = "Dash style of the line joining the two tops/bottoms.", Order = 6, GroupName = "5. Lines")]
        public DashStyleHelper PeakLineDashStyle { get; set; }

        [Range(1, 20)]
        [Display(Name = "Peak line width", Description = "Width of the line joining the two tops/bottoms.", Order = 7, GroupName = "5. Lines")]
        public int PeakLineWidth { get; set; }

        [XmlIgnore]
        [Display(Name = "DT neckline color", Description = "Color of the double-top neckline.", Order = 10, GroupName = "5. Lines")]
        public Brush NecklineDtBrush { get; set; }
        [Browsable(false)]
        public string NecklineDtBrushSerialize { get { return Serialize.BrushToString(NecklineDtBrush); } set { NecklineDtBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "DB neckline color", Description = "Color of the double-bottom neckline.", Order = 11, GroupName = "5. Lines")]
        public Brush NecklineDbBrush { get; set; }
        [Browsable(false)]
        public string NecklineDbBrushSerialize { get { return Serialize.BrushToString(NecklineDbBrush); } set { NecklineDbBrush = Serialize.StringToBrush(value); } }

        [Display(Name = "Neckline style", Description = "Dash style of the neckline.", Order = 12, GroupName = "5. Lines")]
        public DashStyleHelper NecklineDashStyle { get; set; }

        [Range(1, 20)]
        [Display(Name = "Neckline width", Description = "Width of the neckline.", Order = 13, GroupName = "5. Lines")]
        public int NecklineWidth { get; set; }

        [XmlIgnore]
        [Display(Name = "DT dot color", Description = "Color of the double-top neckline-break dot.", Order = 8, GroupName = "5. Lines")]
        public Brush DtDotBrush { get; set; }
        [Browsable(false)]
        public string DtDotBrushSerialize { get { return Serialize.BrushToString(DtDotBrush); } set { DtDotBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "DB dot color", Description = "Color of the double-bottom neckline-break dot.", Order = 9, GroupName = "5. Lines")]
        public Brush DbDotBrush { get; set; }
        [Browsable(false)]
        public string DbDotBrushSerialize { get { return Serialize.BrushToString(DbDotBrush); } set { DbDotBrush = Serialize.StringToBrush(value); } }

        [Range(0, int.MaxValue)]
        [Display(Name = "Show last N DT/DB", Description = "0 = show all. N > 0 = keep only the newest N patterns (DT and DB counted together) on the chart; older ones are removed incl. their triangle.", Order = 20, GroupName = "3. Alerts")]
        public int ShowLastN { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show CVD divergence", Description = "At every confirmed DT/DB, compare bar-proxy CVD at the two peaks/troughs and label agree/disagree (advisory only, every instance labeled — not a filter).", Order = 1, GroupName = "6. CVD Divergence")]
        public bool ShowCvdDivergence { get; set; }

        [NinjaScriptProperty, Range(1, 500)]
        [Display(Name = "CVD period", Description = "Rolling-sum window (Periodic) or smoothing length (EMA) applied to the per-bar delta proxy.", Order = 2, GroupName = "6. CVD Divergence")]
        public int CvdPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CVD mode", Description = "Periodic = rolling SUM of delta over CVD period bars; EMA = EMA of delta over CVD period bars.", Order = 3, GroupName = "6. CVD Divergence")]
        public CvdCumulativeMode CvdMode { get; set; }

        [XmlIgnore]
        [Display(Name = "CVD agree color", Description = "Text color when CVD agrees with the pattern's bias (disagree always shows Gray).", Order = 4, GroupName = "6. CVD Divergence")]
        public Brush CvdDivBrush { get; set; }
        [Browsable(false)]
        public string CvdDivBrushSerialize { get { return Serialize.BrushToString(CvdDivBrush); } set { CvdDivBrush = Serialize.StringToBrush(value); } }

        [NinjaScriptProperty]
        [Display(Name = "Show pullback CVD", Description = "After a DT/DB confirms, watch for the first pullback/retest of the broken neckline and label the CVD change there too.", Order = 5, GroupName = "6. CVD Divergence")]
        public bool ShowPullbackCvd { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Pullback watch (bars)", Description = "Stop watching for a neckline retest after this many bars past confirmation.", Order = 6, GroupName = "6. CVD Divergence")]
        public int PullbackWatchBars { get; set; }

        [NinjaScriptProperty, Range(0, int.MaxValue)]
        [Display(Name = "Retest tolerance (ticks)", Description = "How close price must come back to the neckline (without fully reclaiming it) to count as a retest.", Order = 7, GroupName = "6. CVD Divergence")]
        public int RetestToleranceTicks { get; set; }

        // 2026-10-29: DT/DB detection/confirm/scoring is UNCHANGED by this — it's a pure
        // display filter applied only at the moment a structure confirms (SweepDrawn), on
        // top of the existing CVD-agree check DrawCvdDivergenceBadge already computes.
        // Off by default so nothing changes unless explicitly turned on.
        [NinjaScriptProperty]
        [Display(Name = "Only show CVD-confirmed DT/DB", Description = "When ON, a confirmed DT/DB whose bar-proxy CVD does NOT agree with the pattern's bias (same agree/disagree check as the CVD badge) has its drawings removed instead of kept — only divergence-confirmed patterns stay visible. Does not change detection/confirmation/scoring, and does not suppress alerts.", Order = 8, GroupName = "6. CVD Divergence")]
        public bool FilterToDivergenceOnly { get; set; }

        // 2026-10-29: the actual connecting LINE between the DT/DB's own two pivots
        // (same visual shape as CVDDivergenceOscillator.cs's own divergence line) — the
        // existing CVD badge above is text-only, this is the line specifically asked for.
        [NinjaScriptProperty]
        [Display(Name = "Show CVD divergence line", Description = "Draws a connecting line between the DT/DB's own two peaks/troughs (like CVDDivergenceOscillator.cs's divergence line), only when CVD agrees with the pattern's bias — never drawn when it disagrees.", Order = 9, GroupName = "6. CVD Divergence")]
        public bool ShowCvdDivergenceLine { get; set; }

        [XmlIgnore]
        [Display(Name = "CVD divergence line (DT) color", Order = 10, GroupName = "6. CVD Divergence")]
        public Brush CvdDivLineDtBrush { get; set; }
        [Browsable(false)]
        public string CvdDivLineDtBrushSerialize { get { return Serialize.BrushToString(CvdDivLineDtBrush); } set { CvdDivLineDtBrush = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "CVD divergence line (DB) color", Order = 11, GroupName = "6. CVD Divergence")]
        public Brush CvdDivLineDbBrush { get; set; }
        [Browsable(false)]
        public string CvdDivLineDbBrushSerialize { get { return Serialize.BrushToString(CvdDivLineDbBrush); } set { CvdDivLineDbBrush = Serialize.StringToBrush(value); } }

        // 2026-10-29: hidden CVD divergence at the SAME two DT/DB pivots — see
        // CvdHiddenAgrees's own comment for the mechanical definition and the caveat
        // about what "hidden" means in a reversal-pattern context specifically. Off by
        // default, independent of every other CVD toggle above (incl. FilterToDivergenceOnly,
        // which stays tied to the regular check only).
        [NinjaScriptProperty]
        [Display(Name = "Show hidden CVD divergence", Description = "At every confirmed DT/DB, also checks the INVERSE pairing (price makes a shallower 2nd peak/trough than the 1st, but CVD is stronger anyway) — the same 'hidden divergence' shape CumulativeDelta.cs already has, applied to the DT/DB's own two pivots. Only labeled when it actually fires. Independent of the regular CVD check and the line above.", Order = 12, GroupName = "6. CVD Divergence")]
        public bool ShowHiddenCvdDivergence { get; set; }

        [XmlIgnore]
        [Display(Name = "Hidden CVD divergence color", Order = 13, GroupName = "6. CVD Divergence")]
        public Brush HiddenCvdBrush { get; set; }
        [Browsable(false)]
        public string HiddenCvdBrushSerialize { get { return Serialize.BrushToString(HiddenCvdBrush); } set { HiddenCvdBrush = Serialize.StringToBrush(value); } }
        #endregion
    }
}
