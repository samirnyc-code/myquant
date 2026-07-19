// MarketDepthRecorder — STRATEGY version of MarketDepthLogger (S75V).
//
// WHY A STRATEGY: the indicator version only runs while its chart is open in the active
// workspace, so the one dataset we can NEVER re-collect (resting liquidity) depended on
// which window happened to be on screen. Switching workspaces, closing a chart or a layout
// change could silently stop the recording, and you would not find out until morning.
// A strategy runs from Control Center -> Strategies with NO chart at all: workspace-
// independent, visible in one place, and it cannot be killed by closing a chart.
//
// THIS STRATEGY NEVER PLACES AN ORDER. It only listens. Run it on the Sim101 account.
//
// LIVE ONLY: OnMarketDepth fires for real-time L2 — there is no historical depth in NT8.
// Requires a CME depth subscription on the connected feed (SuperDOM shows 10 levels => OK).
//
// Output (identical schema to MarketDepthLogger, so scripts/depth_verify.py works unchanged):
//   data\depth\ES_depth_2026-07-20.csv    Time(ms),Ev,Side,Pos,Price,Size
//     Ev  = A add / U update / R remove (book events) / T trade (tape, interleaved)
//     Side= B bid / A ask (for T: side of the AGGRESSOR, classified vs quote)
//     Pos = book level 0-9 (T rows: -1)
// Trades share the stream because iceberg/refill detection needs trades and book updates
// on ONE clock (trade hits a level -> Update restores size = refill).
//
// Files are named from NT8's clock (Chicago), so an ETH session opening 17:00 CT rolls to
// the next file at Chicago midnight. depth_verify.py checks both candidate days.
//
// SIZE: ES books are a firehose (millions of rows/day, hundreds of MB). data/depth/ is
// .gitignore'd — NEVER commit the CSVs. Convert to parquet in the 16:00-17:00 CT halt.
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class MarketDepthRecorder : Strategy
    {
        private StreamWriter writer;
        private DateTime curFileDate = DateTime.MinValue;
        private long linesSinceFlush;
        private long bookRows, tapeRows;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Records live DOM/L2 book events + tape to daily CSVs. Never trades.";
                Name = "MarketDepthRecorder";
                Calculate = Calculate.OnEachTick;      // MUST be per-tick
                IsInstantiatedOnEachOptimizationIteration = false;
                // we never trade: start listening immediately, don't wait for bars
                BarsRequiredToTrade = 0;
                EntriesPerDirection = 1;
                ExportDir = @"C:\Users\Admin\myquant\data\depth";
                LogTrades = true;
            }
            else if (State == State.Terminated)
            {
                if (writer != null)
                    Log(string.Format("MarketDepthRecorder stopped: {0:N0} book + {1:N0} tape rows",
                        bookRows, tapeRows), LogLevel.Information);
                CloseFile();
            }
        }

        private void EnsureFile(DateTime t)
        {
            if (t.Date == curFileDate && writer != null) return;
            CloseFile();
            try
            {
                Directory.CreateDirectory(ExportDir);
                string path = Path.Combine(ExportDir,
                    string.Format("{0}_depth_{1:yyyy-MM-dd}.csv",
                        Instrument.MasterInstrument.Name, t));
                bool fresh = !File.Exists(path);
                // APPEND: a restart mid-session must never truncate the day's capture
                writer = new StreamWriter(path, true, System.Text.Encoding.ASCII, 1 << 20);
                if (fresh) writer.WriteLine("Time,Ev,Side,Pos,Price,Size");
                curFileDate = t.Date;
                Log("MarketDepthRecorder -> " + path, LogLevel.Information);
            }
            catch (Exception e) { Log("MarketDepthRecorder open failed: " + e.Message, LogLevel.Error); }
        }

        private void CloseFile()
        {
            if (writer != null) { try { writer.Flush(); writer.Close(); } catch { } writer = null; }
        }

        private void WriteRow(DateTime t, char ev, char side, int pos, double price, long size)
        {
            if (writer == null) return;
            writer.WriteLine(string.Format("{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2},{3},{4},{5}",
                t, ev, side, pos, price, size));
            if (++linesSinceFlush >= 5000) { writer.Flush(); linesSinceFlush = 0; }
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            // real-time only by construction: OnMarketDepth never fires historically
            EnsureFile(e.Time);
            char ev = e.Operation == Operation.Add ? 'A'
                    : e.Operation == Operation.Update ? 'U' : 'R';
            char side = e.MarketDataType == MarketDataType.Bid ? 'B' : 'A';
            WriteRow(e.Time, ev, side, e.Position, e.Price, (long)e.Volume);
            bookRows++;
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (!LogTrades || e.MarketDataType != MarketDataType.Last) return;
            if (State != State.Realtime) return;   // keep the tape live-only, like the book
            EnsureFile(e.Time);
            double ask = e.Ask, bid = e.Bid;
            bool buy;
            if (ask > 0 && bid > 0)
            {
                if (e.Price >= ask) buy = true;               // same classification as
                else if (e.Price <= bid) buy = false;         // FootprintExporter
                else buy = e.Price >= (ask + bid) / 2.0;
            }
            else buy = true;
            WriteRow(e.Time, 'T', buy ? 'A' : 'B', -1, e.Price, (long)e.Volume);
            tapeRows++;
        }

        protected override void OnBarUpdate() { /* everything happens in the event handlers */ }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 0)]
        public string ExportDir { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "LogTrades", Description = "Interleave tape rows (needed for iceberg/refill detection)",
                 GroupName = "Parameters", Order = 1)]
        public bool LogTrades { get; set; }
    }
}
