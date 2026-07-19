// FootprintExporter — reconstructs the bid/ask footprint from tick data and writes it
// to CSV, so we get order-flow (delta, absorption) WITHOUT MzPack's paid exporter (S75).
//
// Footprint = per-price BID-hit volume (aggressive sells) vs ASK-hit volume (aggressive
// buys) per bar. Delta = AskVol - BidVol. Everything MzPack's L1 footprint shows is
// derivable from this; absorption = big volume at a price with little price progress +
// delta flipping (computed offline in Python). L2/DOM is the ONLY thing this can't do.
//
// REQUIRES TICK REPLAY: right-click the ES data series -> enable "Tick Replay" so
// OnMarketData replays historical bid/ask. We loaded 5yr of ES ticks, so this runs the
// full history. Calculate MUST be OnEachTick.
//
// Output CSV (one row per bar x price):
//   BarIdx,BarTime,Price,BidVol,AskVol,BidVolLarge,AskVolLarge
//   (delta = AskVol-BidVol; *Large = only trades >= LargeLotMin contracts — the
//   filtered-CD / absorption inputs; computed offline in Python)
//
// VALIDATION PLAN: apply this AND MzPack's free mzFootprint to the SAME ES chart for one
// session, then compare our CSV per-price bid/ask volume to MzPack's display. If they
// match, our reconstruction is correct -> run it over 5 years. (Uses MzPack free as the
// reference; no paid API needed.)
//
// Install: NT8 -> NinjaScript Editor -> Indicators -> paste -> compile. Apply to an ES
// chart with Tick Replay ON. Set BarType/interval on the chart (1-min or a volume/range
// footprint) BEFORE running — this exports whatever bars the chart uses.
// RULE (CLAUDE.md): lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class FootprintExporter : Indicator
    {
        private StreamWriter writer;
        private StreamWriter barsWriter;           // per-bar tick-order summary
        private Dictionary<double, long[]> book;   // price -> [bidVol, askVol]
        private int accumBar = -1;
        private DateTime accumTime;
        // per-bar running trackers (need intrabar tick ORDER — lost in the ladder)
        private double barOpen, barClose, barHi, barLo;
        private long curCum, curMin, curMax;
        private DateTime barStart, barEnd;
        private bool barSeeded;
        private string stamp;                      // one per load -> one file set per load

        // Several instances of this indicator run AT ONCE (1Min / 5Min / 6500V charts on the
        // same instrument), so the filename must identify the SERIES, not just the time --
        // otherwise two charts loading in the same second open the same path and clobber each
        // other. -> ES_5Min_footprint_20260719_170000.csv
        private string Stamped(string kind)
        {
            // FULL contract ("ES 09-26"), not the master name ("ES") - the file must say
            // which contract produced it, and a roll must not collide with the old one.
            return string.Format("{0}_{1}_{2}_{3}.csv",
                Instrument.FullName.Replace(" ", "_"), PeriodTag(), kind, stamp);
        }

        // 1Min / 5Min / 6500V / 4000T / 12R -- short, filename-safe, unambiguous
        private string PeriodTag()
        {
            int v = BarsPeriod.Value;
            switch (BarsPeriod.BarsPeriodType)
            {
                case BarsPeriodType.Minute: return v + "Min";
                case BarsPeriodType.Volume: return v + "V";
                case BarsPeriodType.Tick:   return v + "T";
                case BarsPeriodType.Range:  return v + "R";
                case BarsPeriodType.Second: return v + "S";
                case BarsPeriodType.Day:    return v + "D";
                default:                    return BarsPeriod.BarsPeriodType + "" + v;
            }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Reconstructs bid/ask footprint from ticks -> CSV (order flow without MzPack)";
                Name = "FootprintExporter";
                Calculate = Calculate.OnEachTick;   // MUST be per-tick
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportPath = @"C:\Users\Admin\myquant\data\footprint\ES_footprint.csv";
                LargeLotMin = 10;
            }
            else if (State == State.Configure)
            {
                book = new Dictionary<double, long[]>();
            }
            else if (State == State.DataLoaded)
            {
                try
                {
                    string dir = Path.GetDirectoryName(ExportPath);
                    Directory.CreateDirectory(dir);

                    // ONE FILE PER LOAD, date-stamped (S75V).
                    //
                    // History: S75J appended on every (re)run -> the ladder was written 3x,
                    // identical rows, volume/delta silently tripled. The fix was to TRUNCATE
                    // on start, which killed the duplicates but made the file disposable:
                    // every chart reload wiped it, so the archive only ever held the LAST
                    // load's lookback. On 2026-07-19 a reload silently destroyed ~2/3 of the
                    // stored history (30,428 ladder rows) — recoverable only from git.
                    //
                    // Now each load writes its OWN stamped file. Nothing is ever overwritten,
                    // so no reload can destroy history, and BarIdx stays chart-relative WITHIN
                    // a file (which is what footprint_metrics.py's groupby needs — BarIdx is
                    // CurrentBar and restarts at 0 on every load, so it must never be pooled
                    // across files; merge on BarTime instead).
                    stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                    string fpPath = Path.Combine(dir, Stamped("footprint"));
                    string barsPath = Path.Combine(dir, Stamped("bars"));

                    writer = new StreamWriter(fpPath, false);
                    writer.WriteLine("BarIdx,BarTime,Price,BidVol,AskVol,BidVolLarge,AskVolLarge");
                    barsWriter = new StreamWriter(barsPath, false);
                    barsWriter.WriteLine(
                        "BarIdx,BarTime,Open,Close,High,Low,MinDelta,MaxDelta,Delta,DurationSec,DeltaRate,UnfHigh,UnfLow");
                    Log("FootprintExporter -> " + fpPath, LogLevel.Information);
                }
                catch (Exception e) { Log("FootprintExporter open failed: " + e.Message, LogLevel.Error); }
            }
            else if (State == State.Terminated)
            {
                if (accumBar >= 0) FlushBar();     // last bar
                if (writer != null) { writer.Flush(); writer.Close(); writer = null; }
                if (barsWriter != null) { barsWriter.Flush(); barsWriter.Close(); barsWriter = null; }
            }
        }

        // classify each trade against the resting bid/ask -> footprint
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last || CurrentBar < 0) return;

            if (accumBar != CurrentBar)            // bar rolled -> flush the finished bar
            {
                if (accumBar >= 0) FlushBar();
                book.Clear();
                accumBar = CurrentBar;
                accumTime = Time[0];
            }

            double key = Instrument.MasterInstrument.RoundToTickSize(e.Price);
            long v = (long)e.Volume;
            long[] cell;
            if (!book.TryGetValue(key, out cell)) { cell = new long[4]; book[key] = cell; }
            // classify against the quote that came WITH this trade (Tick Replay embeds it in e)
            double ask = e.Ask, bid = e.Bid;
            bool buy;
            if (ask > 0 && bid > 0)
            {
                if (e.Price >= ask) buy = true;                   // at/above ask = aggressive BUY
                else if (e.Price <= bid) buy = false;             // at/below bid = aggressive SELL
                else buy = e.Price >= (ask + bid) / 2.0;          // mid split
            }
            else buy = true;                                      // no quote context -> buy
            if (buy) cell[1] += v; else cell[0] += v;
            // large-lot slice (>= LargeLotMin contracts per trade) — the filtered-CD /
            // absorption inputs for H5 (mzVolumeDelta's TradeFilterMin equivalent)
            if (v >= LargeLotMin) { if (buy) cell[3] += v; else cell[2] += v; }

            // intrabar tick-order tracking (for Min/Max delta, Open/Close, delta rate)
            if (!barSeeded)
            {
                barOpen = barHi = barLo = e.Price; curCum = curMin = curMax = 0;
                barStart = e.Time; barSeeded = true;
            }
            barClose = e.Price; barEnd = e.Time;
            if (e.Price > barHi) barHi = e.Price;
            if (e.Price < barLo) barLo = e.Price;
            curCum += buy ? v : -v;
            if (curCum < curMin) curMin = curCum;
            if (curCum > curMax) curMax = curCum;
        }

        private void FlushBar()
        {
            if (writer == null) return;
            try
            {
                foreach (var kv in book)
                    writer.WriteLine(string.Format("{0},{1:yyyy-MM-dd HH:mm:ss},{2},{3},{4},{5},{6}",
                        accumBar, accumTime, kv.Key, kv.Value[0], kv.Value[1], kv.Value[2], kv.Value[3]));
                writer.Flush();

                if (barsWriter != null && barSeeded)   // per-bar tick-order summary
                {
                    double dur = Math.Max(0.001, (barEnd - barStart).TotalSeconds);
                    double unfHi = 0, unfLo = 0; long[] hc, lc;
                    if (book.TryGetValue(Instrument.MasterInstrument.RoundToTickSize(barHi), out hc)
                        && hc[0] > 0 && hc[1] > 0) unfHi = barHi;   // both sides at the high = unfinished
                    if (book.TryGetValue(Instrument.MasterInstrument.RoundToTickSize(barLo), out lc)
                        && lc[0] > 0 && lc[1] > 0) unfLo = barLo;
                    barsWriter.WriteLine(string.Format(
                        "{0},{1:yyyy-MM-dd HH:mm:ss},{2},{3},{4},{5},{6},{7},{8},{9:F1},{10:F2},{11},{12}",
                        accumBar, accumTime, barOpen, barClose, barHi, barLo, curMin, curMax,
                        curCum, dur, curCum / dur, unfHi, unfLo));
                    barsWriter.Flush();
                }
                barSeeded = false;   // reset trackers for the next bar
            }
            catch (Exception e) { Log("FootprintExporter write failed: " + e.Message, LogLevel.Warning); }
        }

        protected override void OnBarUpdate() { /* accumulation happens in OnMarketData */ }

        [NinjaScriptProperty]
        [Display(Name = "ExportPath", GroupName = "Parameters", Order = 0)]
        public string ExportPath { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "LargeLotMin", Description = "Min contracts per trade to count as large-lot",
                 GroupName = "Parameters", Order = 1)]
        public int LargeLotMin { get; set; }
    }
}
