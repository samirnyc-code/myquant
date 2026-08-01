// MarketInternalExporter — export MANY market-internal / index symbols at once ($TICK,
// $VIX, breadth, TRIN, ...) to CSV, from a SINGLE indicator on a SINGLE chart, so we can
// build a 5-year history the same way RawTickExporter feeds the ES continuous DB.
//
// HOW IT WORKS
//   You give it a comma-separated Symbols list. It AddDataSeries() each one itself (as a
//   tick series), so you do NOT have to add them to the chart by hand — just apply this
//   indicator to any chart, set the list, and it dumps every symbol to its own CSV in one
//   run. One file per symbol per load (symbol + date stamp), never overwrites a prior dump.
//
// REQUIRES TICK REPLAY for tick granularity ($TICK): right-click the PRIMARY data series ->
//   "Tick Replay" ON, and set the chart enough days back to cover your window (up to 5yr if
//   the feed has it). Added series inherit the historical range of the chart.
//   Calculate = OnEachTick. If a symbol only has coarser history the feed emits what it has.
//
// OUTPUT (one row per Last update, header on line 2; line 1 = exact symbol):
//   # symbol=$TICK
//   Time,Value            Time = yyyy-MM-dd HH:mm:ss.fff in the chart's time zone (the
//   Python ingest converts to CT). Value = the symbol's Last value ($TICK reading, VIX
//   level, breadth count, ...). Files: TICK_<stamp>.csv, VIX_<stamp>.csv, ADD_<stamp>.csv ...
//
// NOTE ON BARS: this exports the RAW update stream (exact timestamps). There is NO bar
// open/close labeling here to get wrong; any bar aggregation happens later in Python where
// NT's convention (bar timestamp = bar CLOSE) is applied explicitly.
//
// Install: NinjaScript Editor -> Indicators -> paste -> compile. Apply to ANY chart with
// Tick Replay ON, set Symbols, reload. RULE: lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
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
        private string[] syms;
        private Dictionary<string, StreamWriter> writers;   // keyed by exact symbol
        private Dictionary<string, long> counts;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports many market internals/indices ($TICK,$VIX,breadth,...) to CSV from one chart";
                Name = "MarketInternalExporter";
                Calculate = Calculate.OnEachTick;     // per-update; Tick Replay feeds Last here
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportDir = @"C:\Users\Admin\myquant\data\nt_internals";
                Symbols = "$TICK,$VIX,$ADD,$TRIN,$ADV,$DECL,$UVOL,$DVOL";
            }
            else if (State == State.Configure)
            {
                syms = SplitSymbols(Symbols);
                foreach (string s in syms)
                {
                    // add each as a 1-tick series so OnMarketData(Last) streams every update
                    try { AddDataSeries(s, BarsPeriodType.Tick, 1); }
                    catch (Exception e) { Log("AddDataSeries failed for '" + s + "': " + e.Message, LogLevel.Error); }
                }
            }
            else if (State == State.DataLoaded)
            {
                writers = new Dictionary<string, StreamWriter>();
                counts = new Dictionary<string, long>();
                try { Directory.CreateDirectory(ExportDir); } catch { }
                string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                foreach (string s in syms)
                {
                    try
                    {
                        string safe = Regex.Replace(s, @"[^A-Za-z0-9]", "");   // "$TICK" -> "TICK"
                        string path = Path.Combine(ExportDir, string.Format("{0}_{1}.csv", safe, stamp));
                        StreamWriter w = new StreamWriter(path, false);
                        w.WriteLine("# symbol=" + s);
                        w.WriteLine("Time,Value");
                        writers[s] = w;
                        counts[s] = 0;
                        Log("MarketInternalExporter -> " + path, LogLevel.Information);
                    }
                    catch (Exception e) { Log("open failed for '" + s + "': " + e.Message, LogLevel.Error); }
                }
            }
            else if (State == State.Terminated)
            {
                if (writers != null)
                {
                    foreach (var kv in writers)
                    {
                        try { kv.Value.Flush(); kv.Value.Close(); } catch { }
                        Log("MarketInternalExporter " + kv.Key + " wrote " + counts[kv.Key] + " updates", LogLevel.Information);
                    }
                    writers = null;
                }
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (writers == null || e.MarketDataType != MarketDataType.Last) return;
            StreamWriter w = ResolveWriter(e.Instrument);
            if (w == null) return;
            w.WriteLine(string.Format(CultureInfo.InvariantCulture,
                "{0:yyyy-MM-dd HH:mm:ss.fff},{1}", e.Time, e.Price));
        }

        // match the update's instrument to one of our symbol writers (exact, then loose)
        private StreamWriter ResolveWriter(Instrument inst)
        {
            if (inst == null) return null;
            string full = inst.FullName;
            string master = inst.MasterInstrument != null ? inst.MasterInstrument.Name : full;
            foreach (string s in syms)
            {
                if (string.Equals(s, full, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(s, master, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(s.TrimStart('$', '^'), master.TrimStart('$', '^'), StringComparison.OrdinalIgnoreCase))
                {
                    counts[s]++;
                    return writers[s];
                }
            }
            return null;
        }

        private static string[] SplitSymbols(string csv)
        {
            var list = new List<string>();
            foreach (string part in (csv ?? "").Split(','))
            {
                string t = part.Trim();
                if (t.Length > 0) list.Add(t);
            }
            return list.ToArray();
        }

        protected override void OnBarUpdate() { /* all work happens in OnMarketData */ }

        [NinjaScriptProperty]
        [Display(Name = "Symbols", GroupName = "Parameters", Order = 0,
            Description = "Comma-separated internals/indices to export, e.g. $TICK,$VIX,$ADD,$TRIN")]
        public string Symbols { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 1)]
        public string ExportDir { get; set; }
    }
}
