// FlexRenkoBarsType.cs — Sierra-Chart-style FLEX RENKO as an NT8 custom bar type.
// S120-wyckoff, corrected S141. Lets us chart the same bars "he" uses on Sierra (16-8-4 HTF, 8-4-2 exec)
// natively in NinjaTrader, on the live feed. Appears in the chart Bar Type dropdown as
// "Flex Renko" (custom type). Deploy to Documents\NinjaTrader 8\bin\Custom\BarsTypes\ then F5.
//
// PARAMS (ticks):  Value = Box size.  Value2 = TrendOffset*1000 + ReversalOffset (packed —
//   NT8's BarsType framework only exposes 2 numeric slots on the Data Series dialog, confirmed
//   via NinjaTrader's own support forum: there is no supported way to add a 3rd
//   [NinjaScriptProperty] to a BarsType. Sierra's own UI is one hyphenated field
//   "BarSize-TrendOffset-ReversalOffset" for the same reason; this is the NT8-numeric-field
//   equivalent of that packing. 16-8-4 -> Value=16, Value2=8004 (8*1000+4).
//   8-4-2 -> Value=8, Value2=4002.
//
// ALGORITHM — verified word-for-word against Sierra Chart's own docs (sierrachart.com
//   doc/RenkoCharts.html), NOT derived/guessed:
//   "Trend Offset ... the Renko Open value is offset INSIDE the prior bar by the specified
//    number of ticks" (continuation bar's open = prior close, pulled back toward the prior
//    open by T ticks).
//   "Reversal Offset ... the Renko Open value is offset FROM THE PRIOR BAR OPEN by the
//    specified number of ticks" (reversal bar's open = prior bar's own OPEN, offset by R
//    ticks INTO that prior bar's body).
//   Body is always BoxSize (B). So, with O=prior bar's open, C=prior bar's close:
//     prior bar UP (dir=1):
//       continuation up : new O = C - T,  new C = O + B        (triggers when price >= C+(B-T))
//       reversal   down : new O = O + R,  new C = O - B        (triggers when price <= O+R-B)
//     prior bar DOWN (dir=-1): mirror image of the above.
//   This is an EXACT implementation of those two quoted rules, not a guess — confirmed against
//   Sierra's own documented text (and checked that a hallucinated "reversal offset is from the
//   prior CLOSE" claim from a pasted third-party answer contradicts that text and was rejected).
//
// WICKS — v1 was body-only ("stock Renko has none either", which is false for Sierra: Sierra
//   Renko/Flex Renko bars DO carry true wicks via "Renko Bricks with Wicks" draw style, per the
//   same doc page). Fixed here: track the running tick-level high/low excursion since the last
//   completed brick (reset after each brick), and use THAT as the printed brick's real High/Low
//   instead of the box-only Max/Min(open,close). Mirrors the already-verified Python
//   scripts/renko.py::flex_renko wlo/whi excursion tracking (proved against the raw tape there).
//
// ⚠️ BarsType changes ALWAYS need on-chart F5 testing (the compile check can't validate the
//   bar-build/rendering). Adapts @RenkoBarsType.cs's forming-bar / gap-fill / partial-bar
//   management pattern (NT8's own native Renko source, read directly off this machine).

#region Using declarations
using System;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
#endregion

namespace NinjaTrader.NinjaScript.BarsTypes
{
    public class FlexRenkoBarsType : BarsType
    {
        private const int PACK = 1000;   // Value2 = TrendOffset*PACK + ReversalOffset (ticks each)

        private double flexOpen;    // last completed brick's open
        private double flexClose;   // last completed brick's close
        private int    dir;         // 0 neutral, 1 up, -1 down
        private double excHi, excLo; // true tick-level excursion since the last completed brick (wicks)

        public override void ApplyDefaultBasePeriodValue(BarsPeriod period) { }
        public override void ApplyDefaultValue(BarsPeriod period) { period.Value = 16; period.Value2 = 8004; } // 16-8-4
        public override string ChartLabel(DateTime time) { return time.ToString("T", Core.Globals.GeneralOptions.CurrentCulture); }
        public override int GetInitialLookBackDays(BarsPeriod period, TradingHours tradingHours, int barsBack) { return 3; }
        public override double GetPercentComplete(Bars bars, DateTime now) { return 0; }
        public override bool IsRemoveLastBarSupported { get { return true; } }

        protected override void OnDataPoint(Bars bars, double open, double high, double low, double close, DateTime time, long volume, bool isBar, double bid, double ask)
        {
            if (SessionIterator == null) SessionIterator = new SessionIterator(bars);
            double tick = bars.Instrument.MasterInstrument.TickSize;
            double B = bars.BarsPeriod.Value * tick;
            int    to = bars.BarsPeriod.Value2 / PACK;
            int    ro = bars.BarsPeriod.Value2 % PACK;
            double T = to * tick;
            double R = ro * tick;

            bool isNewSession = SessionIterator.IsNewSession(time, isBar);
            if (isNewSession) SessionIterator.GetNextSession(time, isBar);

            // seed / session reset
            if (bars.Count == 0 || (bars.IsResetOnNewTradingDay && isNewSession))
            {
                if (bars.Count > 0)
                {
                    double lc = bars.GetClose(bars.Count - 1); DateTime lt = bars.GetTime(bars.Count - 1); long lv = bars.GetVolume(bars.Count - 1);
                    RemoveLastBar(bars);
                    AddBar(bars, lc, lc, lc, lc, lt, lv);
                }
                flexOpen = flexClose = close; dir = 0;
                excHi = excLo = close;
                AddBar(bars, close, close, close, close, time, volume);
                bars.LastPrice = close;
                return;
            }

            if (high > excHi) excHi = high;
            if (low  < excLo) excLo = low;

            DateTime barTime = bars.GetTime(bars.Count - 1);
            long     barVol  = bars.GetVolume(bars.Count - 1);

            int guard = 0;
            while (guard++ < 10000)
            {
                // current triggers given state (fall out algebraically from new-C = new-O ± B)
                double upTrig, dnTrig;
                if (dir == 1)      { upTrig = flexClose + (B - T); dnTrig = flexOpen + R - B; }
                else if (dir == -1){ dnTrig = flexClose - (B - T); upTrig = flexOpen - R + B; }
                else               { upTrig = flexClose + B;        dnTrig = flexClose - B;      }

                if (close.ApproxCompare(upTrig) >= 0)                       // ---- UP brick completes ----
                {
                    double On, Cn;
                    if (dir == 1)       { On = flexClose - T; Cn = On + B; }   // continuation: open offset INSIDE prior bar
                    else if (dir == -1) { On = flexOpen - R;  Cn = On + B; }   // reversal up:   open offset from prior bar's OPEN
                    else                { On = flexClose;     Cn = On + B; }   // first
                    double wHi = Math.Max(excHi, Cn), wLo = Math.Min(excLo, On);
                    RemoveLastBar(bars);
                    AddBar(bars, On, wHi, wLo, Cn, barTime, barVol);
                    flexOpen = On; flexClose = Cn; dir = 1;
                    excHi = excLo = Cn;                      // excursion for the NEXT brick starts fresh here
                    // open a fresh partial forming bar at the new brick top, marked to current price
                    AddBar(bars, Cn, Math.Max(Cn, high), Math.Min(Cn, low), close, time, volume);
                    barTime = time; barVol = volume;
                    continue;
                }
                if (close.ApproxCompare(dnTrig) <= 0)                       // ---- DOWN brick completes ----
                {
                    double On, Cn;
                    if (dir == -1)     { On = flexClose + T; Cn = On - B; }   // continuation: open offset INSIDE prior bar
                    else if (dir == 1) { On = flexOpen + R;  Cn = On - B; }   // reversal down: open offset from prior bar's OPEN
                    else               { On = flexClose;     Cn = On - B; }   // first
                    double wHi = Math.Max(excHi, On), wLo = Math.Min(excLo, Cn);
                    RemoveLastBar(bars);
                    AddBar(bars, On, wHi, wLo, Cn, barTime, barVol);
                    flexOpen = On; flexClose = Cn; dir = -1;
                    excHi = excLo = Cn;
                    AddBar(bars, Cn, Math.Max(Cn, high), Math.Min(Cn, low), close, time, volume);
                    barTime = time; barVol = volume;
                    continue;
                }
                break;
            }

            // no brick completed this tick: just update the forming bar (true high/low, not just close)
            double fh = Math.Max(bars.GetHigh(bars.Count - 1), high);
            double fl = Math.Min(bars.GetLow(bars.Count - 1), low);
            UpdateBar(bars, close, fh, fl, time, volume);
            bars.LastPrice = close;
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name              = "Flex Renko";
                BarsPeriod        = new BarsPeriod { BarsPeriodType = (BarsPeriodType)76308, Value = 16, Value2 = 8004 };
                BuiltFrom         = BarsPeriodType.Tick;
                DaysToLoad        = 3;
                DefaultChartStyle = Gui.Chart.ChartStyleType.CandleStick;
                IsIntraday        = true;
                IsTimeBased       = false;
            }
            else if (State == State.Configure)
            {
                int to = BarsPeriod.Value2 / PACK, ro = BarsPeriod.Value2 % PACK;
                Name = string.Format("Flex Renko {0}-{1}-{2}", BarsPeriod.Value, to, ro);
                Properties.Remove(Properties.Find("BaseBarsPeriodType", true));
                Properties.Remove(Properties.Find("BaseBarsPeriodValue", true));
                Properties.Remove(Properties.Find("PointAndFigurePriceType", true));
                Properties.Remove(Properties.Find("ReversalType", true));
                SetPropertyName("Value", "Box size (ticks)");
                SetPropertyName("Value2", "TrendOffset*1000 + ReversalOffset (ticks) e.g. 8004 = 8-4");
            }
        }
    }
}
