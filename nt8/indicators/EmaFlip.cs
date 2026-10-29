#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// EmaFlip
// Marks "regime flips": a fast, wide-bar reversal from an extended swing extreme
// that closes decisively through a still-sloping EMA and does not immediately cross back.
// Uses only price bars, the EMA and ATR (for scale-independent distances).
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed. Recovered 2026-10-29 —
// existed only in the NT8 Custom folder (last modified 2026-10-27), never committed. No
// code changed in this recovery commit; next commit adds the DT/DB divergence gate.

namespace NinjaTrader.NinjaScript.Indicators
{
    public class EmaFlip : Indicator
    {
        private EMA ema;
        private ATR atr;
        private Series<double> signal;

        // pending (unconfirmed) flip
        private int      pendingDir;
        private int      pendingBar;
        private string   pendingTag;
        private DateTime pendingStart;
        private DateTime pendingEnd;
        private double   pendingHi;
        private double   pendingLo;
        private int      pendingExtremeBar;

        // absolute bar index of the extreme each direction last confirmed from
        private int lastBullExtreme = -1;
        private int lastBearExtreme = -1;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                     = "EmaFlip";
                Description              = "Detects EMA regime flips from swing extremes";
                Calculate                = Calculate.OnBarClose;
                IsOverlay                = true;
                DisplayInDataBox         = true;
                DrawOnPricePanel         = true;
                PaintPriceMarkers        = false;
                IsSuspendedWhileInactive = true;

                // --- defaults = user's settings, synced 2026-10-29 from the saved live
                // template (Documents\NinjaTrader 8\templates\Indicator\EmaFlip\Default.xml)
                // — this indicator was tuned live well before this session started
                // (recovered file, previously uncommitted), so these replace placeholder
                // values, not re-sync drift from a prior commit. ---
                EmaPeriod         = 20;
                AtrPeriod         = 8;
                MaxBarsToCross    = 15;
                SwingLookback     = 8;
                MinStretchAtr     = 1;
                StretchBars       = 10;
                StretchPct        = 50;
                RequireEmaSlope   = false;
                SlopeBars         = 3;
                BreakCloseAtr     = 0.2;
                RequireBodyBeyond = true;
                RangeExpansion    = 0.7;
                RangeLookback     = 8;
                ConfirmBars       = 2;

                RequireDtDbDivergence   = true;
                IncludeHiddenDivergence = true;

                BullBrush         = Brushes.LimeGreen;
                BearBrush         = Brushes.Red;
                PendingOpacity    = 15;
                ConfirmedOpacity  = 25;
                ShowDiagnostics   = false;
                DiagBrush         = Brushes.Black;

                AddPlot(Brushes.RoyalBlue, "EMA");
            }
            else if (State == State.DataLoaded)
            {
                ema    = EMA(EmaPeriod);
                atr    = ATR(AtrPeriod);
                signal = new Series<double>(this);
            }
        }

        protected override void OnBarUpdate()
        {
            Values[0][0] = ema[0];
            signal[0]    = 0;

            int warmup = Math.Max(EmaPeriod, AtrPeriod)
                       + MaxBarsToCross
                       + Math.Max(SwingLookback, Math.Max(StretchBars, Math.Max(RangeLookback, SlopeBars)))
                       + 2;
            if (CurrentBar < warmup)
                return;

            // 1) resolve a pending flip: fail if price closes back across the EMA,
            //    confirm once it has held for ConfirmBars bars
            if (pendingDir != 0)
            {
                bool crossedBack = pendingDir == 1 ? Close[0] < ema[0] : Close[0] > ema[0];
                if (crossedBack)
                {
                    RemoveDrawObject(pendingTag);
                    if (ShowDiagnostics)
                        Draw.Text(this, pendingTag + "_x", "X", 0,
                            pendingDir == 1 ? Low[0] - atr[0] : High[0] + atr[0], DiagBrush);
                    pendingDir = 0;
                }
                else if (CurrentBar - pendingBar >= ConfirmBars)
                {
                    Confirm();
                }
            }

            // 2) look for a new flip
            if (pendingDir != 0)
                return;

            for (int dir = 1; dir >= -1; dir -= 2)
            {
                int e;
                string fails;
                if (TryDetect(dir, out e, out fails))
                {
                    StartFlip(dir, e);
                    break;
                }
                if (ShowDiagnostics && fails.Length > 0 && IsFreshCross(dir))
                    Draw.Text(this, "EmaFlipDiag_" + CurrentBar + "_" + dir, fails, 0,
                        dir == 1 ? Low[0] - atr[0] : High[0] + atr[0], DiagBrush);
            }
        }

        // the previous bar was not yet decisively beyond the EMA in this direction
        private bool IsFreshCross(int dir)
        {
            double m = BreakCloseAtr * atr[1];
            return dir == 1 ? Close[1] < ema[1] + m : Close[1] > ema[1] - m;
        }

        // dir = +1: bullish flip from a swing low; dir = -1: bearish flip from a swing high.
        // e = barsAgo of the swing extreme. fails = codes of failed filters (diagnostics).
        //   W = extreme is not a swing over SwingLookback
        //   S = not stretched enough from EMA (value = ATRs)
        //   P = too few bars on the old side of the EMA
        //   L = EMA not sloping the old way
        //   R = no range expansion (value = ratio)
        //   B = body not fully beyond EMA
        private bool TryDetect(int dir, out int e, out string fails)
        {
            e = -1;
            fails = "";
            bool bull = dir == 1;

            // candidate only if this bar closes decisively beyond the EMA
            double margin = BreakCloseAtr * atr[0];
            if (bull ? Close[0] < ema[0] + margin : Close[0] > ema[0] - margin)
                return false;

            // swing extreme within the last MaxBarsToCross bars (fast trip to the EMA)
            double extreme = bull ? double.MaxValue : double.MinValue;
            for (int i = 1; i <= MaxBarsToCross; i++)
            {
                double v = bull ? Low[i] : High[i];
                if (bull ? v < extreme : v > extreme)
                {
                    extreme = v;
                    e = i;
                }
            }
            if (e < 1)
                return false;

            // each extreme can produce only one confirmed flip
            if (CurrentBar - e == (bull ? lastBullExtreme : lastBearExtreme))
                return false;

            if (RequireBodyBeyond)
            {
                double bodyEdge = bull ? Math.Min(Open[0], Close[0]) : Math.Max(Open[0], Close[0]);
                bool isDoji     = Math.Abs(Close[0] - Open[0]) < TickSize / 2;
                if (isDoji || (bull ? bodyEdge <= ema[0] : bodyEdge >= ema[0]))
                    fails += "B ";
            }

            // extreme must be a real swing
            for (int i = e + 1; i <= e + SwingLookback; i++)
            {
                if (bull ? Low[i] < extreme : High[i] > extreme)
                {
                    fails += "W ";
                    break;
                }
            }

            // stretched away from the EMA at the extreme
            double dist = bull ? ema[e] - extreme : extreme - ema[e];
            double stretch = atr[e] > 0 ? dist / atr[e] : 0;
            if (stretch < MinStretchAtr)
                fails += "S" + stretch.ToString("0.0") + " ";

            // holding on the old side of the EMA before the extreme
            int sameSide = 0;
            for (int i = e; i < e + StretchBars; i++)
            {
                if (bull ? Close[i] < ema[i] : Close[i] > ema[i])
                    sameSide++;
            }
            if (sameSide < StretchPct / 100.0 * StretchBars)
                fails += "P ";

            // EMA still sloping the old way at the extreme
            if (RequireEmaSlope && (bull ? ema[e] >= ema[e + SlopeBars] : ema[e] <= ema[e + SlopeBars]))
                fails += "L ";

            // range expansion: bars after the extreme vs. bars before it
            double turnRange = 0;
            for (int i = 0; i < e; i++)
                turnRange += High[i] - Low[i];
            turnRange /= e;

            double priorRange = 0;
            for (int i = e + 1; i <= e + RangeLookback; i++)
                priorRange += High[i] - Low[i];
            priorRange /= RangeLookback;

            double ratio = priorRange > 0 ? turnRange / priorRange : 0;
            if (ratio < RangeExpansion)
                fails += "R" + ratio.ToString("0.00") + " ";

            // 2026-10-29: user ask — only paint a flip box when its own starting bar (the
            // swing extreme, "e" bars back) is also one of DtDbScannerV3's own two pivots
            // for a CVD-confirmed DT/DB (regular divergence; optionally hidden divergence
            // too via IncludeHiddenDivergence). Off by default — existing behavior
            // unchanged unless explicitly turned on.
            if (RequireDtDbDivergence && !ExtremeIsDtDbPivot(CurrentBar - e))
                fails += "D ";

            fails = fails.Trim();
            return fails.Length == 0;
        }

        // Reads DtDbCvdPivotRegistry (same shared registry DtDbScannerV3.cs/
        // CVDDivergenceOscillator.cs already use) for THIS instrument and checks whether
        // extremeBar matches either pivot (P1 or P2) of any published entry. Every entry
        // in the registry is already CVD-confirmed by construction — DtDbScannerV3 only
        // ever publishes when its own CvdAgrees (regular) or CvdHiddenAgrees (hidden)
        // fired — so no extra divergence check is needed here beyond the IsHidden filter.
        // Full scan, not an incremental last-seen-id window like CVDDivergenceOscillator's
        // per-bar poll: this only runs when TryDetect's other filters already hold (a rare
        // candidate bar, not every bar), so the cost is negligible.
        private bool ExtremeIsDtDbPivot(int extremeBar)
        {
            if (Instrument == null) return false;
            System.Collections.Generic.List<DtDbCvdPivot> all =
                DtDbCvdPivotRegistry.GetSince(Instrument.FullName, 0);
            foreach (DtDbCvdPivot p in all)
            {
                if (p.IsHidden && !IncludeHiddenDivergence) continue;
                int p1Bar = Bars.GetBar(p.P1Time);
                int p2Bar = Bars.GetBar(p.P2Time);
                if (p1Bar == extremeBar || p2Bar == extremeBar) return true;
            }
            return false;
        }

        private void StartFlip(int dir, int e)
        {
            double hi = double.MinValue, lo = double.MaxValue;
            for (int i = 0; i <= e; i++)
            {
                hi = Math.Max(hi, High[i]);
                lo = Math.Min(lo, Low[i]);
            }

            pendingDir   = dir;
            pendingBar   = CurrentBar;
            pendingTag   = "EmaFlip_" + CurrentBar;
            pendingStart = Time[e];
            pendingEnd   = Time[0];
            pendingHi    = hi;
            pendingLo    = lo;
            pendingExtremeBar = CurrentBar - e;

            if (ConfirmBars <= 0)
                Confirm();
            else
                DrawBox(PendingOpacity);
        }

        private void Confirm()
        {
            DrawBox(ConfirmedOpacity);
            signal[0] = pendingDir;
            if (pendingDir == 1)
                lastBullExtreme = pendingExtremeBar;
            else
                lastBearExtreme = pendingExtremeBar;
            pendingDir = 0;
        }

        private void DrawBox(int opacity)
        {
            Brush b = pendingDir == 1 ? BullBrush : BearBrush;
            Draw.Rectangle(this, pendingTag, false,
                pendingStart, pendingHi, pendingEnd, pendingLo,
                Brushes.Transparent, b, opacity);
        }

        #region Properties

        [Browsable(false), XmlIgnore]
        public Series<double> FlipSignal
        {
            get { Update(); return signal; }   // +1 bull flip, -1 bear flip, on the confirming bar
        }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "EMA period", Order = 1, GroupName = "1. EMA / ATR")]
        public int EmaPeriod { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "ATR period", Order = 2, GroupName = "1. EMA / ATR")]
        public int AtrPeriod { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Max bars extreme → cross", Description = "Speed: how quickly price must get from the extreme through the EMA", Order = 1, GroupName = "2. Swing extreme")]
        public int MaxBarsToCross { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Swing lookback", Description = "Extreme must be the high/low of this many bars before it", Order = 2, GroupName = "2. Swing extreme")]
        public int SwingLookback { get; set; }

        [NinjaScriptProperty, Range(0, double.MaxValue)]
        [Display(Name = "Min stretch (ATR)", Description = "Distance from extreme to EMA, in ATRs", Order = 1, GroupName = "3. Stretch")]
        public double MinStretchAtr { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Stretch bars", Description = "Bars before the extreme checked for side of EMA", Order = 2, GroupName = "3. Stretch")]
        public int StretchBars { get; set; }

        [NinjaScriptProperty, Range(0, 100)]
        [Display(Name = "Stretch % on old side", Order = 3, GroupName = "3. Stretch")]
        public int StretchPct { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Require EMA sloping old way", Order = 4, GroupName = "3. Stretch")]
        public bool RequireEmaSlope { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Slope bars", Order = 5, GroupName = "3. Stretch")]
        public int SlopeBars { get; set; }

        [NinjaScriptProperty, Range(0, double.MaxValue)]
        [Display(Name = "Break close beyond EMA (ATR)", Order = 1, GroupName = "4. Break")]
        public double BreakCloseAtr { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Require body fully beyond EMA", Order = 2, GroupName = "4. Break")]
        public bool RequireBodyBeyond { get; set; }

        [NinjaScriptProperty, Range(0, double.MaxValue)]
        [Display(Name = "Range expansion ratio", Description = "Avg bar range after extreme / avg range before", Order = 3, GroupName = "4. Break")]
        public double RangeExpansion { get; set; }

        [NinjaScriptProperty, Range(1, int.MaxValue)]
        [Display(Name = "Range lookback", Order = 4, GroupName = "4. Break")]
        public int RangeLookback { get; set; }

        [NinjaScriptProperty, Range(0, int.MaxValue)]
        [Display(Name = "Confirm bars (no cross back)", Description = "0 = signal immediately on the break bar", Order = 1, GroupName = "5. Confirmation")]
        public int ConfirmBars { get; set; }

        // 2026-10-29: this property's mere presence requires DtDbCvdPivotRegistry.cs on
        // the same Custom tree at compile time, same caveat as
        // CVDDivergenceOscillator.cs's OnlyShowAtDtDb — functionally a no-op when OFF
        // (the default) but the type reference exists regardless of toggle state.
        [NinjaScriptProperty]
        [Display(Name = "Require DT/DB divergence at extreme (requires DtDbScannerV3)", Description = "Only paint a flip box when its own starting bar (the swing extreme) is also one of DtDbScannerV3's confirmed, CVD-divergence pivots. Off by default.", Order = 1, GroupName = "5a. DT/DB Divergence Gate")]
        public bool RequireDtDbDivergence { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Also allow hidden divergence", Description = "When the gate above is on, also accept a starting bar that's a hidden-CVD-divergence pivot (not just regular). Ignored when the gate above is off.", Order = 2, GroupName = "5a. DT/DB Divergence Gate")]
        public bool IncludeHiddenDivergence { get; set; }

        [XmlIgnore]
        [Display(Name = "Bull color", Order = 1, GroupName = "6. Visuals")]
        public Brush BullBrush { get; set; }

        [Browsable(false)]
        public string BullBrushSerialize
        {
            get { return Serialize.BrushToString(BullBrush); }
            set { BullBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Bear color", Order = 2, GroupName = "6. Visuals")]
        public Brush BearBrush { get; set; }

        [Browsable(false)]
        public string BearBrushSerialize
        {
            get { return Serialize.BrushToString(BearBrush); }
            set { BearBrush = Serialize.StringToBrush(value); }
        }

        [Range(0, 100)]
        [Display(Name = "Pending box opacity", Order = 3, GroupName = "6. Visuals")]
        public int PendingOpacity { get; set; }

        [Range(0, 100)]
        [Display(Name = "Confirmed box opacity", Order = 4, GroupName = "6. Visuals")]
        public int ConfirmedOpacity { get; set; }

        [Display(Name = "Show diagnostics", Description = "Label rejected EMA crosses with the filters they failed", Order = 1, GroupName = "7. Diagnostics")]
        public bool ShowDiagnostics { get; set; }

        [XmlIgnore]
        [Display(Name = "Diagnostics text color", Order = 2, GroupName = "7. Diagnostics")]
        public Brush DiagBrush { get; set; }

        [Browsable(false)]
        public string DiagBrushSerialize
        {
            get { return Serialize.BrushToString(DiagBrush); }
            set { DiagBrush = Serialize.StringToBrush(value); }
        }

        #endregion
    }
}
