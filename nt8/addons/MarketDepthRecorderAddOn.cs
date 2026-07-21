// MarketDepthRecorderAddOn.cs — ADDON version of MarketDepthRecorder (S75V, 2026-07-21).
//
// WHY AN ADDON (the fix for hands-free unattended recording):
//   A STRATEGY must be manually ENABLED in the Control Center, and any compile/restart
//   DISABLES it — we lost recording to this 3x (7/19 twice on compile, 7/21 on the SuperDOM
//   crash). An ADDON is instantiated and RUN automatically the moment NinjaTrader starts —
//   no enable step, no Strategies-grid row, survives restarts/crashes with ZERO clicks.
//   NT Watchdog restarts the NT process; this AddOn then re-records itself. Together = truly
//   unattended.
//
// STATUS: ⚠️ UNTESTED — must be COMPILED (F5) + verified recording in a 16:00-17:00 CT halt
//   before we trust it. Every API used here is from the official NT8 Help Guide (AddOn
//   framework p2092-2095; MarketDepth<MarketDepthRow> subscription p2083; MarketData p2081;
//   Connection.ConnectionStatusUpdate p2050-2051; MarketDepthEventArgs fields p1846). The
//   halt test validates that the AddOn instantiates on startup and the depth subscription
//   actually fires — the one integration point docs can't prove.
//
// Writes the IDENTICAL schema/filenames as MarketDepthRecorder.cs (Strategy), so
// depth_verify.py / pipeline_health / depth_rollover all work unchanged:
//   data\depth\{Instrument.FullName}_depth_{TRADE-DATE}.csv   Time,Ev,Side,Pos,Price,Size
//   Ev = A/U/R book · T tape (aggressor side) · C connection markers (C,D lost / C,C back)
// Files follow the SESSION TEMPLATE (>=17:00 CT -> next trading day), same as the Strategy.
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and is committed immediately, even untested.
// Deploy to: Documents\NinjaTrader 8\bin\Custom\AddOns\ then F5. Keep the STRATEGY as the
// live recorder until this AddOn is proven in the halt; do not run both at once.

#region Using declarations
using System;
using System.IO;
using System.Timers;
using System.Windows;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public class MarketDepthRecorderAddOn : AddOnBase
    {
        // -------- config (front-month; update on the quarterly roll) --------
        private const string SymbolName = "ES 09-26";
        private const string ExportDir  = @"C:\Users\Admin\myquant\data\depth";

        private Instrument instrument;
        private MarketDepth<MarketDepthRow> marketDepth;
        private MarketData marketData;

        private StreamWriter writer;
        private DateTime curFileDate = DateTime.MinValue;
        private readonly object fileLock = new object();
        private long linesSinceFlush, bookRows, tapeRows;

        private bool hooked;       // Connection event hooked once
        private bool subscribed;   // depth/data subscriptions live
        private System.Timers.Timer haltTimer;

        // ================================================================ lifecycle
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "MarketDepthRecorderAddOn";
                Description = "Auto-records ES L2 book + tape to CSV on NT startup. No enable step (AddOn). Never trades.";
                // hook the connection ONCE (SetDefaults can fire more than once)
                if (!hooked)
                {
                    Connection.ConnectionStatusUpdate += OnConnectionStatusUpdate;
                    hooked = true;
                    Log("MarketDepthRecorderAddOn: loaded, waiting for price feed", LogLevel.Information);
                }
            }
            else if (State == State.Terminated)
            {
                if (hooked) { Connection.ConnectionStatusUpdate -= OnConnectionStatusUpdate; hooked = false; }
                if (haltTimer != null) { try { haltTimer.Stop(); haltTimer.Dispose(); } catch { } haltTimer = null; }
                Unsubscribe();
                if (writer != null)
                    Log(string.Format("MarketDepthRecorderAddOn stopped: {0:N0} book + {1:N0} tape rows", bookRows, tapeRows), LogLevel.Information);
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
                        WriteRow(now, 'C', 'D', -1, 0, 0);  // feed lost — the gap starts here
                        Flush();
                        Log(string.Format("MarketDepthRecorderAddOn: feed LOST after {0:N0} book + {1:N0} tape rows", bookRows, tapeRows), LogLevel.Warning);
                        Unsubscribe();
                    }
                }
            }
            catch (Exception ex) { Log("MarketDepthRecorderAddOn conn err: " + ex.Message, LogLevel.Error); }
        }

        private void Subscribe()
        {
            try
            {
                instrument = Instrument.GetInstrument(SymbolName);
                if (instrument == null) { Log("MarketDepthRecorderAddOn: instrument not found: " + SymbolName, LogLevel.Error); return; }
                // subscribe/unsubscribe MUST be on the instrument's dispatcher thread (Help Guide)
                instrument.Dispatcher.InvokeAsync(() =>
                {
                    try
                    {
                        marketDepth = new MarketDepth<MarketDepthRow>(instrument);
                        marketDepth.Update += OnMarketDepth;
                        marketData = new MarketData(instrument);
                        marketData.Update += OnMarketData;
                        subscribed = true;
                        DateTime now = Core.Globals.Now;
                        EnsureFile(now);
                        WriteRow(now, 'C', 'C', -1, 0, 0);   // connected (book resync follows)
                        Flush();
                        EnsureHaltTimer();
                        Log("MarketDepthRecorderAddOn: feed CONNECTED, recording " + SymbolName, LogLevel.Information);
                    }
                    catch (Exception ex) { Log("MarketDepthRecorderAddOn subscribe err: " + ex.Message, LogLevel.Error); }
                });
            }
            catch (Exception ex) { Log("MarketDepthRecorderAddOn Subscribe err: " + ex.Message, LogLevel.Error); }
        }

        private void Unsubscribe()
        {
            try
            {
                var inst = instrument;
                var md = marketDepth;
                var mdata = marketData;
                if (inst != null && (md != null || mdata != null))
                    inst.Dispatcher.InvokeAsync(() =>
                    {
                        try { if (md != null) md.Update -= OnMarketDepth; } catch { }
                        try { if (mdata != null) mdata.Update -= OnMarketData; } catch { }
                    });
            }
            catch { }
            subscribed = false;
        }

        // ================================================================ data handlers
        private void OnMarketDepth(object sender, MarketDepthEventArgs e)
        {
            EnsureFile(e.Time);
            char ev = e.Operation == Operation.Add ? 'A'
                    : e.Operation == Operation.Update ? 'U' : 'R';
            char side = e.MarketDataType == MarketDataType.Bid ? 'B' : 'A';
            WriteRow(e.Time, ev, side, e.Position, e.Price, (long)e.Volume);
            bookRows++;
        }

        private void OnMarketData(object sender, MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last) return;
            EnsureFile(e.Time);
            // aggressor from the current NBBO snapshot (same rule as FootprintExporter/Strategy)
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
            WriteRow(e.Time, 'T', buy ? 'A' : 'B', -1, e.Price, (long)e.Volume);
            tapeRows++;
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
                string path = Path.Combine(ExportDir, string.Format("{0}_depth_{1:yyyy-MM-dd}.csv", sym, td));
                bool fresh = !File.Exists(path);
                writer = new StreamWriter(path, true, System.Text.Encoding.ASCII, 1 << 20);
                if (fresh) writer.WriteLine("Time,Ev,Side,Pos,Price,Size");
                curFileDate = td;
                Log("MarketDepthRecorderAddOn -> " + path, LogLevel.Information);
            }
            catch (Exception e) { Log("MarketDepthRecorderAddOn open failed: " + e.Message, LogLevel.Error); }
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

        private void WriteRow(DateTime t, char ev, char side, int pos, double price, long size)
        {
          lock (fileLock)
          {
            if (writer == null) return;
            writer.WriteLine(string.Format("{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2},{3},{4},{5}", t, ev, side, pos, price, size));
            if (++linesSinceFlush >= 5000) { try { writer.Flush(); } catch { } linesSinceFlush = 0; }
          }
        }

        // release the finished session file during the 16:00-17:00 halt so depth_rollover can
        // convert it the same afternoon (identical to the Strategy's halt-timer).
        private void EnsureHaltTimer()
        {
            if (haltTimer != null) return;
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
                                Log("MarketDepthRecorderAddOn: session over - releasing file for rollover", LogLevel.Information);
                                CloseFile();
                            }
                }
                catch { }
            };
            haltTimer.Start();
        }
    }
}
