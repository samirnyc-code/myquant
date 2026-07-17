// MarketDepthLogger — records the LIVE order book (DOM/L2) to daily CSVs (S75M).
//
// WHY: trades leave a permanent record (FootprintExporter rebuilds footprints for any
// historical day), but RESTING liquidity exists only in the moment — DOM pressure,
// refill icebergs, pulling/stacking are unrecoverable once the session ends. This logs
// the RAW book event stream so any future metric can be computed offline in Python
// without re-recording (same philosophy as the footprint ladder). Backlog hypothesis #8
// ("Reversal Order Flow Cluster": DOM-refill iceberg + DOM pressure at PS) is live-only
// and needs this archive to ever be testable for free (paid backfill = Databento MBP-10).
//
// LIVE ONLY: OnMarketDepth fires for real-time L2 — there is no historical depth in NT8.
// Requires a CME market-depth subscription on the connected feed (SuperDOM shows 10
// levels => you have it). Apply to a live ES chart and leave it running all session.
//
// Output: one CSV per session date in ExportDir, e.g. ES_depth_2026-07-17.csv
//   Time(ms),Ev,Side,Pos,Price,Size
//     Ev  = A add / U update / R remove (book events) / T trade (tape, interleaved)
//     Side= B bid / A ask (for T: side of the AGGRESSOR, classified vs quote)
//     Pos = book level 0-9 (T rows: -1)
// Trades are logged in the SAME stream because iceberg/refill detection needs trades
// and book updates on one clock (trade hits level -> Update restores size = refill).
//
// SIZE WARNING: ES books are a firehose (millions of rows/day, hundreds of MB). Files
// go to data/depth/ which is .gitignore'd — NEVER commit them. Gzip old days offline.
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MarketDepthLogger : Indicator
    {
        private StreamWriter writer;
        private DateTime curFileDate = DateTime.MinValue;
        private long linesSinceFlush;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Logs live DOM/L2 book events + tape to daily CSVs (live-only data, unrecoverable later)";
                Name = "MarketDepthLogger";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportDir = @"C:\Users\Admin\myquant\data\depth";
                LogTrades = true;
            }
            else if (State == State.Terminated)
            {
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
                writer = new StreamWriter(path, true, System.Text.Encoding.ASCII, 1 << 20);
                if (fresh) writer.WriteLine("Time,Ev,Side,Pos,Price,Size");
                curFileDate = t.Date;
                Log("MarketDepthLogger -> " + path, LogLevel.Information);
            }
            catch (Exception e) { Log("MarketDepthLogger open failed: " + e.Message, LogLevel.Error); }
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
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (!LogTrades || e.MarketDataType != MarketDataType.Last) return;
            if (State != State.Realtime) return;   // keep the stream live-only, like the book
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
