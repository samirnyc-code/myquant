// FlexRenkoBarsType.cs — Sierra-Chart-style FLEX RENKO as an NT8 custom bar type.
// S120-wyckoff. Lets us chart the same bars "he" uses on Sierra (16-8-4 HTF, 8-4-2 exec)
// natively in NinjaTrader, on the live feed. Appears in the chart Bar Type dropdown as
// "Flex Renko" (custom type). Deploy to Documents\NinjaTrader 8\bin\Custom\BarsTypes\ then F5.
//
// PARAMS (ticks):  Value = Box size,  Value2 = Trend offset.  Reversal offset is derived as
//   Trend/2 to match his ratio (box : box/2 : box/4). So Value=16,Value2=8 -> 16-8-4;
//   Value=8,Value2=4 -> 8-4-2. (If he ever uses a non-ratio reversal, we expose a 3rd field.)
//
// ALGORITHM (derived from the Sierra doc's open-offset rules; verified in Python flex_renko):
//   B=Box, T=Trend, R=Reversal (=T/2), all in price.  Bricks body = B, overlapping.
//   Up brick: open O(bottom), close C=O+B(top).
//     continuation up : triggers at C+(B-T); new O=C-T, new C=C+(B-T)
//     reversal   down : triggers at O+R-B ; new(down) O=O+R(top), C=O+R-B(bottom)
//   Down brick mirror.
//
// ⚠️ FIRST DRAFT — BarsTypes ALWAYS need on-chart F5 testing (the compile check can't validate
//   the bar-build/rendering). Body-only bricks for v1 (no wicks yet; stock Renko has none either).
//   Adapts @RenkoBarsType.cs's forming-bar / gap-fill / partial-bar management pattern.

#region Using declarations
using System;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Data;
#endregion

namespace NinjaTrader.NinjaScript.BarsTypes
{
    public class FlexRenkoBarsType : BarsType
    {
        private double flexOpen;    // last completed brick renko open
        private double flexClose;   // last completed brick renko close
        private int    dir;         // 0 neutral, 1 up, -1 down

        public override void ApplyDefaultBasePeriodValue(BarsPeriod period) { }
        public override void ApplyDefaultValue(BarsPeriod period) { period.Value = 16; period.Value2 = 8; }
        public override string ChartLabel(DateTime time) { return time.ToString("T", Core.Globals.GeneralOptions.CurrentCulture); }
        public override int GetInitialLookBackDays(BarsPeriod period, TradingHours tradingHours, int barsBack) { return 3; }
        public override double GetPercentComplete(Bars bars, DateTime now) { return 0; }
        public override bool IsRemoveLastBarSupported { get { return true; } }

        protected override void OnDataPoint(Bars bars, double open, double high, double low, double close, DateTime time, long volume, bool isBar, double bid, double ask)
        {
            if (SessionIterator == null) SessionIterator = new SessionIterator(bars);
            double tick = bars.Instrument.MasterInstrument.TickSize;
            double B = bars.BarsPeriod.Value  * tick;
            double T = bars.BarsPeriod.Value2 * tick;
            double R = (bars.BarsPeriod.Value2 / 2.0) * tick;   // reversal = trend/2 (his ratio)

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
                AddBar(bars, close, close, close, close, time, volume);
                bars.LastPrice = close;
                return;
            }

            DateTime barTime = bars.GetTime(bars.Count - 1);
            long     barVol  = bars.GetVolume(bars.Count - 1);

            int guard = 0;
            while (guard++ < 10000)
            {
                // current triggers given state
                double upTrig, dnTrig;
                if (dir == 1)      { upTrig = flexClose + (B - T); dnTrig = flexOpen + R - B; }
                else if (dir == -1){ dnTrig = flexClose - (B - T); upTrig = flexOpen - R + B; }
                else               { upTrig = flexClose + B;        dnTrig = flexClose - B;      }

                if (close.ApproxCompare(upTrig) >= 0)                       // ---- UP brick completes ----
                {
                    double On, Cn;
                    if (dir == 1)  { On = flexClose - T;  Cn = flexClose + (B - T); }   // continuation
                    else if (dir == -1) { On = flexOpen - R; Cn = On + B; }             // reversal up
                    else           { On = flexClose;      Cn = flexClose + B; }         // first
                    // finalize the forming bar as this completed brick
                    RemoveLastBar(bars);
                    AddBar(bars, On, Math.Max(On, Cn), Math.Min(On, Cn), Cn, barTime, barVol);
                    flexOpen = On; flexClose = Cn; dir = 1;
                    // open a fresh partial forming bar at the new brick top, marked to current price
                    AddBar(bars, Cn, Math.Max(Cn, close), Math.Min(Cn, close), close, time, volume);
                    barTime = time; barVol = volume;
                    continue;
                }
                if (close.ApproxCompare(dnTrig) <= 0)                       // ---- DOWN brick completes ----
                {
                    double On, Cn;
                    if (dir == -1) { On = flexClose + T;  Cn = flexClose - (B - T); }   // continuation
                    else if (dir == 1)  { On = flexOpen + R; Cn = On - B; }             // reversal down
                    else           { On = flexClose;      Cn = flexClose - B; }         // first
                    RemoveLastBar(bars);
                    AddBar(bars, On, Math.Max(On, Cn), Math.Min(On, Cn), Cn, barTime, barVol);
                    flexOpen = On; flexClose = Cn; dir = -1;
                    AddBar(bars, Cn, Math.Max(Cn, close), Math.Min(Cn, close), close, time, volume);
                    barTime = time; barVol = volume;
                    continue;
                }
                break;
            }

            // no brick completed this tick: just update the forming bar
            double fh = Math.Max(bars.GetHigh(bars.Count - 1), close);
            double fl = Math.Min(bars.GetLow(bars.Count - 1), close);
            UpdateBar(bars, close, fh, fl, time, volume);
            bars.LastPrice = close;
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name              = "Flex Renko";
                BarsPeriod        = new BarsPeriod { BarsPeriodType = (BarsPeriodType)76308, Value = 16, Value2 = 8 };
                BuiltFrom         = BarsPeriodType.Tick;
                DaysToLoad        = 3;
                DefaultChartStyle = Gui.Chart.ChartStyleType.OpenClose;
                IsIntraday        = true;
                IsTimeBased       = false;
            }
            else if (State == State.Configure)
            {
                Name = string.Format("Flex Renko {0}-{1}-{2}", BarsPeriod.Value, BarsPeriod.Value2, Math.Max(1, BarsPeriod.Value2 / 2));
                Properties.Remove(Properties.Find("BaseBarsPeriodType", true));
                Properties.Remove(Properties.Find("BaseBarsPeriodValue", true));
                Properties.Remove(Properties.Find("PointAndFigurePriceType", true));
                Properties.Remove(Properties.Find("ReversalType", true));
                SetPropertyName("Value", "Box size (ticks)");
                SetPropertyName("Value2", "Trend offset (ticks)");
            }
        }
    }
}
