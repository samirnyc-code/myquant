// MarketInternalExporter — export the market-internal / index symbols we need ($TICK/^TICK,
// VIX, breadth, TRIN, Nasdaq tick/trin, BANK, USD) to CSV, from a SINGLE indicator on a
// SINGLE chart, so we can build a multi-year history to test the method.
//
// The symbol list, export folder and bar period are HARD-CODED below (SYMS / EXPORT_DIR /
// PERIOD_MINUTES) on purpose: there are no editable parameters, so a previously-applied copy
// of this indicator can't keep a stale/invalid list. Just recompile (F5) and re-apply — it
// runs the list below. To change the list, edit SYMS here and recompile.
//
// It AddDataSeries() each symbol itself (no need to hand-add series to the chart). Internals
// only need standard historical BARS (no Tick Replay); one bar per symbol keeps the $TICK /
// breadth EXTREMES (bar High/Low) for divergence work. A symbol the feed doesn't have is
// skipped (logged) without breaking the rest.
//
// OUTPUT (one row per bar; header line 2, line 1 = exact symbol):
//   # symbol=^TICK
//   Time,Open,High,Low,Close,Volume   Time = bar CLOSE time (NT convention), yyyy-MM-dd HH:mm:ss.
//   Files: TICK_5m_<stamp>.csv, VIX_5m_<stamp>.csv ...  never overwrites a prior dump.
//
// Install: NinjaScript Editor -> Indicators -> paste -> compile (F5). Apply to ANY chart, set
//   the chart days-back to your window, reload. RULE: lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MarketInternalExporter : Indicator
    {
        // ---- hard-coded config (no editable params, so no stale value can apply) ----
        private static readonly string[] SYMS = {
            "^TICK", "^VIX", "^ADD", "^ADV", "^UVOL", "^DVOL", "^TRIN",
            "^TICKQ", "BANK", "DX 09-26"
            // ^TRINQ removed: feed not entitled ("Symbol is inaccessible"). If ^TICKQ (or any
            // other) logs the same, delete it here too and recompile.
        };
        private const string EXPORT_DIR = @"C:\Users\Admin\myquant\data\nt_internals";
        private const int PERIOD_MINUTES = 5;

        private List<string> added;          // symbols that ACTUALLY got added, in series order
        private StreamWriter[] writers;      // writers[i] <-> added[i] <-> BarsInProgress (i+1)
        private long[] counts;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports market internals/indices as bars to CSV from one chart (hard-coded list)";
                Name = "MarketInternalExporter";
                Calculate = Calculate.OnBarClose;     // one final row per closed bar (no Tick Replay needed)
                IsOverlay = true;
                DisplayInDataBox = false;
            }
            else if (State == State.Configure)
            {
                // add only the symbols that succeed; a bad symbol is skipped, not fatal, and
                // does NOT consume a BarsInProgress slot (so 'added' stays aligned to the series).
                added = new List<string>();
                foreach (string s in SYMS)
                {
                    try { AddDataSeries(s, BarsPeriodType.Minute, PERIOD_MINUTES); added.Add(s); }
                    catch (Exception e) { Log("MarketInternalExporter skip '" + s + "': " + e.Message, LogLevel.Warning); }
                }
            }
            else if (State == State.DataLoaded)
            {
                writers = new StreamWriter[added.Count];
                counts = new long[added.Count];
                try { Directory.CreateDirectory(EXPORT_DIR); } catch { }
                string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                for (int i = 0; i < added.Count; i++)
                {
                    try
                    {
                        string safe = Regex.Replace(added[i], @"[^A-Za-z0-9]", "");   // "^TICK"->"TICK", "DX 09-26"->"DX0926"
                        string path = Path.Combine(EXPORT_DIR,
                            string.Format("{0}_{1}m_{2}.csv", safe, PERIOD_MINUTES, stamp));
                        StreamWriter w = new StreamWriter(path, false);
                        w.WriteLine("# symbol=" + added[i]);
                        w.WriteLine("Time,Open,High,Low,Close,Volume");
                        writers[i] = w;
                        Log("MarketInternalExporter -> " + path, LogLevel.Information);
                    }
                    catch (Exception e) { Log("open failed for '" + added[i] + "': " + e.Message, LogLevel.Error); }
                }
            }
            else if (State == State.Terminated)
            {
                if (writers != null)
                {
                    for (int i = 0; i < writers.Length; i++)
                    {
                        if (writers[i] == null) continue;
                        try { writers[i].Flush(); writers[i].Close(); } catch { }
                        Log("MarketInternalExporter " + added[i] + " wrote " + counts[i] + " bars", LogLevel.Information);
                    }
                    writers = null;
                }
            }
        }

        protected override void OnBarUpdate()
        {
            int bip = BarsInProgress;          // 0 = primary chart symbol (skip); 1..N = added series
            if (bip <= 0 || writers == null) return;
            int i = bip - 1;
            if (i >= writers.Length || writers[i] == null || CurrentBars[bip] < 0) return;
            writers[i].WriteLine(string.Format(CultureInfo.InvariantCulture,
                "{0:yyyy-MM-dd HH:mm:ss},{1},{2},{3},{4},{5}",
                Times[bip][0], Opens[bip][0], Highs[bip][0], Lows[bip][0], Closes[bip][0], Volumes[bip][0]));
            counts[i]++;
        }
    }
}
