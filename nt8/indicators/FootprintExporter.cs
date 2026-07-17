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
//   BarTime,Price,BidVol,AskVol      (delta = AskVol-BidVol, computed in Python)
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
        private Dictionary<double, long[]> book;   // price -> [bidVol, askVol]
        private int accumBar = -1;
        private DateTime accumTime;

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
            }
            else if (State == State.Configure)
            {
                book = new Dictionary<double, long[]>();
            }
            else if (State == State.DataLoaded)
            {
                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(ExportPath));
                    bool fresh = !File.Exists(ExportPath);
                    writer = new StreamWriter(ExportPath, true);
                    if (fresh) writer.WriteLine("BarIdx,BarTime,Price,BidVol,AskVol");
                }
                catch (Exception e) { Log("FootprintExporter open failed: " + e.Message, LogLevel.Error); }
            }
            else if (State == State.Terminated)
            {
                if (accumBar >= 0) FlushBar();     // last bar
                if (writer != null) { writer.Flush(); writer.Close(); writer = null; }
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
            if (!book.TryGetValue(key, out cell)) { cell = new long[2]; book[key] = cell; }
            // classify against the quote that came WITH this trade (Tick Replay embeds it in e)
            double ask = e.Ask, bid = e.Bid;
            if (ask > 0 && bid > 0)
            {
                if (e.Price >= ask) cell[1] += v;                 // at/above ask = aggressive BUY
                else if (e.Price <= bid) cell[0] += v;            // at/below bid = aggressive SELL
                else if (e.Price >= (ask + bid) / 2.0) cell[1] += v;  // upper half -> buy
                else cell[0] += v;                                // lower half -> sell
            }
            else cell[1] += v;                                    // no quote context -> park as buy
        }

        private void FlushBar()
        {
            if (writer == null) return;
            try
            {
                foreach (var kv in book)
                    writer.WriteLine(string.Format("{0},{1:yyyy-MM-dd HH:mm:ss},{2},{3},{4}",
                        accumBar, accumTime, kv.Key, kv.Value[0], kv.Value[1]));
                writer.Flush();
            }
            catch (Exception e) { Log("FootprintExporter write failed: " + e.Message, LogLevel.Warning); }
        }

        protected override void OnBarUpdate() { /* accumulation happens in OnMarketData */ }

        [NinjaScriptProperty]
        [Display(Name = "ExportPath", GroupName = "Parameters", Order = 0)]
        public string ExportPath { get; set; }
    }
}
