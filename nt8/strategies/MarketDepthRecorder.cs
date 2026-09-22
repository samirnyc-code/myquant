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
// Files follow the SESSION TEMPLATE, not the calendar (S75V, user decision 2026-07-20):
// everything from 17:00 CT onward belongs to the NEXT trading day (CME/NT8 trade-date
// convention), so ONE file = ONE full session (Sun 17:00 -> Mon 16:00 = "_2026-07-21").
// A session file is closed at 16:00 and can be parqueted + archived in the same halt.
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
        private System.Timers.Timer haltTimer;   // releases the session file during the halt
        private readonly object fileLock = new object();

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
            else if (State == State.Realtime)
            {
                // In the 16:00-17:00 halt no events fire, so the writer would sit on the
                // finished session file until 17:00 - blocking the 16:05 parquet rollover.
                // This timer closes the file once the session is over; the 17:00 open
                // re-creates the (next-session) file via EnsureFile as usual.
                haltTimer = new System.Timers.Timer(60000);
                haltTimer.Elapsed += (s, a) =>
                {
                    try
                    {
                        TimeSpan now = Core.Globals.Now.TimeOfDay;
                        if (now >= new TimeSpan(16, 0, 30) && now < new TimeSpan(16, 59, 0))
                            lock (fileLock)
                                if (writer != null)
                                {
                                    Log("MarketDepthRecorder: session over - releasing file for rollover", LogLevel.Information);
                                    CloseFile();
                                }
                    }
                    catch { }
                };
                haltTimer.Start();
            }
            else if (State == State.Terminated)
            {
                if (haltTimer != null) { try { haltTimer.Stop(); haltTimer.Dispose(); } catch { } haltTimer = null; }
                if (writer != null)
                    Log(string.Format("MarketDepthRecorder stopped: {0:N0} book + {1:N0} tape rows",
                        bookRows, tapeRows), LogLevel.Information);
                CloseFile();
            }
        }

        /// Trading day a timestamp belongs to: >= 17:00 CT rolls to the NEXT weekday
        /// (Sun 17:00 -> Monday's session; Fri evening/weekend anomalies -> Monday too).
        private static DateTime TradeDate(DateTime t)
        {
            DateTime d = t.Date;
            if (t.TimeOfDay >= new TimeSpan(17, 0, 0)) d = d.AddDays(1);
            while (d.DayOfWeek == DayOfWeek.Saturday || d.DayOfWeek == DayOfWeek.Sunday)
                d = d.AddDays(1);
            return d;
        }

        private void EnsureFile(DateTime t)
        {
          lock (fileLock)
          {
            if (TradeDate(t) == curFileDate && writer != null) return;
            CloseFile();
            try
            {
                Directory.CreateDirectory(ExportDir);
                // FULL contract, not just "ES": a file named ES_depth_... does not say
                // WHICH contract it holds, and a chart left on a rolled-off contract records
                // perfectly happily. On a roll the two contracts must never share a filename.
                string sym = Instrument.FullName.Replace(" ", "_");   // "ES 09-26" -> "ES_09-26"
                DateTime td = TradeDate(t);
                string path = Path.Combine(ExportDir,
                    string.Format("{0}_depth_{1:yyyy-MM-dd}.csv", sym, td));
                bool fresh = !File.Exists(path);
                // APPEND: a restart mid-session must never truncate the day's capture
                writer = new StreamWriter(path, true, System.Text.Encoding.ASCII, 1 << 20);
                if (fresh) writer.WriteLine("Time,Ev,Side,Pos,Price,Size");
                curFileDate = td;
                Log("MarketDepthRecorder -> " + path, LogLevel.Information);
            }
            catch (Exception e) { Log("MarketDepthRecorder open failed: " + e.Message, LogLevel.Error); }
          }
        }

        private void CloseFile()
        {
            lock (fileLock)
                if (writer != null) { try { writer.Flush(); writer.Close(); } catch { } writer = null; }
        }

        private void WriteRow(DateTime t, char ev, char side, int pos, double price, long size)
        {
          lock (fileLock)
          {
            if (writer == null) return;
            writer.WriteLine(string.Format("{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2},{3},{4},{5}",
                t, ev, side, pos, price, size));
            if (++linesSinceFlush >= 5000) { writer.Flush(); linesSinceFlush = 0; }
          }
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

        /// Stamp connection transitions INTO the data stream.
        ///
        /// Without this a disconnect is invisible: the file just has fewer rows for a while, and
        /// any footprint/CVD derived from it later silently spans the hole as if nothing happened.
        /// A 'C' row makes every gap explicit and self-documenting, and marks where the burst of
        /// 'A' rows after a reconnect is a BOOK RESYNC rather than real activity.
        ///   C,D = feed disconnected   C,C = feed connected (resync follows)
        /// Uses Core.Globals.Now (NT8's clock) NOT DateTime.Now: this PC runs Berlin time while
        /// NT8 and every data event run Chicago time. Mixing them made EnsureFile flip between
        /// two daily files on every connection event.
        protected override void OnConnectionStatusUpdate(ConnectionStatusEventArgs e)
        {
            try
            {
                DateTime now = Core.Globals.Now;   // NT8 clock (exchange TZ), NOT the PC's
                if (e.PriceStatus == ConnectionStatus.Connected)
                {
                    EnsureFile(now);
                    WriteRow(now, 'C', 'C', -1, 0, 0);
                    if (writer != null) writer.Flush();
                    Log("MarketDepthRecorder: feed CONNECTED (book resync follows)", LogLevel.Information);
                }
                else if (e.PriceStatus == ConnectionStatus.Disconnected ||
                         e.PriceStatus == ConnectionStatus.ConnectionLost)
                {
                    WriteRow(now, 'C', 'D', -1, 0, 0);
                    if (writer != null) writer.Flush();   // flush NOW: the gap starts here
                    Log(string.Format("MarketDepthRecorder: feed LOST after {0:N0} book + {1:N0} tape rows",
                        bookRows, tapeRows), LogLevel.Warning);
                }
            }
            catch { /* never let logging break the recorder */ }
        }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 0)]
        public string ExportDir { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "LogTrades", Description = "Interleave tape rows (needed for iceberg/refill detection)",
                 GroupName = "Parameters", Order = 1)]
        public bool LogTrades { get; set; }
    }
}
