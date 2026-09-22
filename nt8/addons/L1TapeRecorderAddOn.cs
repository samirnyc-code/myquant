// L1TapeRecorderAddOn.cs — full-tape (L1) recorder for the Wyckoff-2.0 order-flow DB.
// S120-wyckoff (2026-09-16). User directive: record EVERYTHING (tick + best bid/ask + vol)
// 23h/day, starting with ES. Capture level chosen = L1 (tape + best bid/ask), NOT full L2
// DOM — footprint/delta-complete at a fraction of the disk (see docs handoff S120-wyckoff #18).
//
// WHY AN ADDON (same reasoning as MarketDepthRecorderAddOn): an AddOn is instantiated and
// RUN automatically the moment NinjaTrader starts — no enable step, no Strategies-grid row,
// survives restarts/crashes with ZERO clicks. The NT watchdog restarts the NT process; this
// AddOn re-records itself. Together = truly unattended.
//
// WHAT THIS RECORDS (L1 only — NO depth book beyond top-of-book):
//   T  tape print   — every Last: Price, Size, Aggr (A = buy aggressor lifting the ask,
//                     B = sell aggressor hitting the bid)  → footprint + cumulative delta
//   B  best bid     — top-of-book bid changed: Price, Size (= bid size), Aggr blank
//   A  best ask     — top-of-book ask changed: Price, Size (= ask size), Aggr blank
//   C  connection   — C,D feed lost (gap starts) · C,C feed back (resync follows)
//
// FILE (session template: >=17:00 CT belongs to the NEXT trading day):
//   data\l1_tape\{Instrument.FullName}_l1_{TRADE-DATE}.csv
//   header: Time,Ev,Side,Price,Size,Aggr  (Side is a spare kept for parity with the depth
//           schema — blank on all L1 rows; Aggr is A/B on tape rows only)
// Nightly: scripts\l1_rollover.py compresses the finished CSV to parquet in the 16:00-17:00
//   halt (verified re-read before delete) and mirrors to the private archive repo.
//
// ⚠️ UNTESTED until F5 + verified writing in a live session. Every API used is the same set
//   proven by MarketDepthRecorderAddOn (AddOn framework, MarketData subscription,
//   Connection.ConnectionStatusUpdate). The one integration point docs can't prove — that
//   MarketData.Update fires for Bid/Ask/Last on this feed — is what the first live run checks.
//
// ⚠️ CONTRACT ROLL: front-month is "ES 12-26" (desk rolled from 09-26 on 2026-09-15; the roll
//   is by VOLUME, not the calendar). Change SymbolName the same day the NT chart rolls, or the
//   recorder silently records the wrong (dying) contract — this is the single manual step.
//   Next roll: whenever the desk moves to "ES 03-27" (~mid-Dec 2026).
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and is committed immediately, even untested.
// Deploy to: Documents\NinjaTrader 8\bin\Custom\AddOns\ then F5 (when flat).
//
// COEXISTENCE: this does NOT subscribe to MarketDepth, so it is much lighter than
//   MarketDepthRecorderAddOn. Running both would double-write the tape — the user chose L1
//   only, so the L2 AddOn should stay off (do not enable both). Nothing is disabled here.

#region Using declarations
using System;
using System.IO;
using System.Timers;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public class L1TapeRecorderAddOn : AddOnBase
    {
        // -------- config (front-month; update on the quarterly roll — see header) --------
        // Rolled 09-26 -> 12-26 on 2026-09-15 (the desk rolls on VOLUME; 09-26 expires Fri
        // 2026-09-18). Next roll: whenever the desk moves to "ES 03-27" (~mid-Dec 2026).
        private const string SymbolName = "ES 12-26";
        private const string ExportDir  = @"C:\Users\Admin\myquant\data\l1_tape";

        private Instrument instrument;
        private MarketData marketData;

        private StreamWriter writer;
        private DateTime curFileDate = DateTime.MinValue;
        private readonly object fileLock = new object();
        private long linesSinceFlush, tapeRows, quoteRows;

        // last-seen top-of-book so a Bid/Ask row is only written when it actually CHANGES
        // (MarketData.Update can re-fire the same top; dedup keeps the file honest + small).
        private double lastBidP = double.NaN, lastAskP = double.NaN;
        private long   lastBidS = -1,         lastAskS = -1;

        private bool hooked;       // Connection event hooked once
        private bool subscribed;   // market-data subscription live
        private System.Timers.Timer haltTimer;
        private DateTime lastData = DateTime.MinValue;   // wall-time of the last data event (silent-stall detector)
        private const double StallResubSecs = 90;        // no data this long while open -> force a resubscribe

        // ================================================================ lifecycle
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "L1TapeRecorderAddOn";
                Description = "Auto-records ES L1 tape + best bid/ask to CSV on NT startup. No enable step (AddOn). Never trades.";
                if (!hooked)
                {
                    Connection.ConnectionStatusUpdate += OnConnectionStatusUpdate;
                    hooked = true;
                    Log("L1TapeRecorderAddOn: loaded, waiting for price feed", LogLevel.Information);
                }
            }
            else if (State == State.Terminated)
            {
                if (hooked) { Connection.ConnectionStatusUpdate -= OnConnectionStatusUpdate; hooked = false; }
                if (haltTimer != null) { try { haltTimer.Stop(); haltTimer.Dispose(); } catch { } haltTimer = null; }
                Unsubscribe();
                if (writer != null)
                    Log(string.Format("L1TapeRecorderAddOn stopped: {0:N0} tape + {1:N0} quote rows", tapeRows, quoteRows), LogLevel.Information);
                CloseFile();
            }
        }

        // Subscribe when the PRICE feed connects; re-subscribe on reconnect; mark disconnects.
        private void OnConnectionStatusUpdate(object sender, ConnectionStatusEventArgs e)
        {
            try
            {
                if (e.PriceStatus == ConnectionStatus.Connected)
                {
                    if (!subscribed) Subscribe();
                }
                else if (e.PriceStatus == ConnectionStatus.Disconnected || e.PriceStatus == ConnectionStatus.ConnectionLost)
                {
                    if (subscribed)
                    {
                        DateTime now = Core.Globals.Now;   // NT8 exchange clock, NOT DateTime.Now
                        WriteRow(now, 'C', 'D', 0, 0, ' ');   // feed lost — the gap starts here
                        Flush();
                        Log(string.Format("L1TapeRecorderAddOn: feed LOST after {0:N0} tape + {1:N0} quote rows", tapeRows, quoteRows), LogLevel.Warning);
                        Unsubscribe();
                    }
                }
            }
            catch (Exception ex) { Log("L1TapeRecorderAddOn conn err: " + ex.Message, LogLevel.Error); }
        }

        private void Subscribe()
        {
            try
            {
                instrument = Instrument.GetInstrument(SymbolName);
                if (instrument == null) { Log("L1TapeRecorderAddOn: instrument not found: " + SymbolName, LogLevel.Error); return; }
                // subscribe/unsubscribe MUST be on the instrument's dispatcher thread (Help Guide)
                instrument.Dispatcher.InvokeAsync(() =>
                {
                    try
                    {
                        marketData = new MarketData(instrument);
                        marketData.Update += OnMarketData;
                        subscribed = true;
                        lastBidP = lastAskP = double.NaN; lastBidS = lastAskS = -1;   // force a fresh quote after resync
                        DateTime now = Core.Globals.Now;
                        lastData = now;   // grace period so a fresh subscription doesn't instantly trip the stall detector
                        EnsureFile(now);
                        WriteRow(now, 'C', 'C', 0, 0, ' ');   // connected (quote resync follows)
                        Flush();
                        EnsureHaltTimer();
                        Log("L1TapeRecorderAddOn: feed CONNECTED, recording " + SymbolName, LogLevel.Information);
                    }
                    catch (Exception ex) { Log("L1TapeRecorderAddOn subscribe err: " + ex.Message, LogLevel.Error); }
                });
            }
            catch (Exception ex) { Log("L1TapeRecorderAddOn Subscribe err: " + ex.Message, LogLevel.Error); }
        }

        private void Unsubscribe()
        {
            try
            {
                var inst = instrument;
                var mdata = marketData;
                if (inst != null && mdata != null)
                    inst.Dispatcher.InvokeAsync(() =>
                    {
                        try { if (mdata != null) mdata.Update -= OnMarketData; } catch { }
                    });
            }
            catch { }
            subscribed = false;
        }

        // ================================================================ data handler (L1 only)
        private void OnMarketData(object sender, MarketDataEventArgs e)
        {
            lastData = Core.Globals.Now;   // proof of life for the silent-stall detector
            switch (e.MarketDataType)
            {
                case MarketDataType.Last:
                {
                    EnsureFile(e.Time);
                    // aggressor from the current top-of-book (same rule as FootprintExporter / L2 AddOn)
                    double ask = (marketData != null && marketData.Ask != null) ? marketData.Ask.Price : 0;
                    double bid = (marketData != null && marketData.Bid != null) ? marketData.Bid.Price : 0;
                    bool buy;
                    if (ask > 0 && bid > 0)
                    {
                        if (e.Price >= ask) buy = true;
                        else if (e.Price <= bid) buy = false;
                        else buy = e.Price >= (ask + bid) / 2.0;
                    }
                    else buy = true;
                    WriteRow(e.Time, 'T', ' ', e.Price, (long)e.Volume, buy ? 'A' : 'B');
                    tapeRows++;
                    break;
                }
                case MarketDataType.Bid:
                {
                    if (e.Price == lastBidP && (long)e.Volume == lastBidS) return;   // unchanged top
                    lastBidP = e.Price; lastBidS = (long)e.Volume;
                    EnsureFile(e.Time);
                    WriteRow(e.Time, 'B', ' ', e.Price, (long)e.Volume, ' ');
                    quoteRows++;
                    break;
                }
                case MarketDataType.Ask:
                {
                    if (e.Price == lastAskP && (long)e.Volume == lastAskS) return;   // unchanged top
                    lastAskP = e.Price; lastAskS = (long)e.Volume;
                    EnsureFile(e.Time);
                    WriteRow(e.Time, 'A', ' ', e.Price, (long)e.Volume, ' ');
                    quoteRows++;
                    break;
                }
                // ignore DailyHigh/Low/Volume/Settlement/etc — not part of the L1 tape record
            }
        }

        // ================================================================ file (session template)
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
                string sym = instrument != null ? instrument.FullName.Replace(" ", "_") : "ES";
                DateTime td = TradeDate(t);
                string path = Path.Combine(ExportDir, string.Format("{0}_l1_{1:yyyy-MM-dd}.csv", sym, td));
                bool fresh = !File.Exists(path);
                writer = new StreamWriter(path, true, System.Text.Encoding.ASCII, 1 << 20);
                if (fresh) writer.WriteLine("Time,Ev,Side,Price,Size,Aggr");
                curFileDate = td;
                Log("L1TapeRecorderAddOn -> " + path, LogLevel.Information);
            }
            catch (Exception e) { Log("L1TapeRecorderAddOn open failed: " + e.Message, LogLevel.Error); }
          }
        }

        private void CloseFile()
        {
            lock (fileLock)
                if (writer != null) { try { writer.Flush(); writer.Close(); } catch { } writer = null; }
        }

        private void Flush()
        {
            lock (fileLock) { if (writer != null) try { writer.Flush(); } catch { } }
        }

        // Schema: Time,Ev,Side,Price,Size,Aggr  (Side kept as a spare column for parity with
        // the depth schema / future use; blank for L1 rows). Aggr is A/B on tape rows only.
        private void WriteRow(DateTime t, char ev, char side, double price, long size, char aggr)
        {
          lock (fileLock)
          {
            if (writer == null) return;
            writer.WriteLine(string.Format("{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2},{3},{4},{5}",
                                           t, ev, side == ' ' ? "" : side.ToString(),
                                           price, size, aggr == ' ' ? "" : aggr.ToString()));
            if (++linesSinceFlush >= 5000) { try { writer.Flush(); } catch { } linesSinceFlush = 0; }
          }
        }

        // Maintenance timer (every 5s while recording): flush so the on-disk file mtime stays
        // fresh for pipeline_health/watchdog freshness checks; release the finished session
        // file in the 16:00-17:00 halt for l1_rollover; self-heal a SILENT data stall by
        // resubscribing. Identical shape to MarketDepthRecorderAddOn's halt timer.
        private void EnsureHaltTimer()
        {
            if (haltTimer != null) return;
            haltTimer = new System.Timers.Timer(5000);
            haltTimer.Elapsed += (s, a) =>
            {
                try
                {
                    Flush();
                    DateTime now = Core.Globals.Now;
                    TimeSpan tod = now.TimeOfDay;
                    bool inHalt = tod >= new TimeSpan(16, 0, 0) && tod < new TimeSpan(17, 0, 0);

                    if (tod >= new TimeSpan(16, 0, 30) && tod < new TimeSpan(16, 59, 0))
                        lock (fileLock)
                            if (writer != null)
                            {
                                Log("L1TapeRecorderAddOn: session over - releasing file for rollover", LogLevel.Information);
                                CloseFile();
                            }

                    if (subscribed && !inHalt && lastData != DateTime.MinValue
                        && (now - lastData).TotalSeconds > StallResubSecs)
                    {
                        Log(string.Format("L1TapeRecorderAddOn: data SILENT {0:N0}s while open — forcing resubscribe",
                                          (now - lastData).TotalSeconds), LogLevel.Warning);
                        lastData = now;
                        Unsubscribe();
                        Subscribe();
                    }
                }
                catch { }
            };
            haltTimer.Start();
        }
    }
}
