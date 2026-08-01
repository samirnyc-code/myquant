// MarketInternalExporter — dumps every Last update (time, value) for a market-internal
// or index symbol ($TICK, $VIX, $ADD, $TRIN, $UVOL, $DVOL, ...) to CSV so we can build a
// 5-year history the same way RawTickExporter feeds the ES continuous DB.
//
// This is the market-internals sibling of RawTickExporter. Same mechanism: with Tick
// Replay ON, the historical Last stream is written out one row per update. Apply it to a
// chart of the internal you want ($TICK, then $VIX, then the breadth symbols) and set the
// chart enough days back to cover the window (e.g. up to 5 years if the feed has it).
//
// REQUIRES TICK REPLAY for tick-granularity ($TICK): right-click the data series ->
// "Tick Replay" ON. For symbols that only have coarser history the same load still emits
// whatever updates the feed provides (down to that resolution).
//
// Output CSV (one row per Last update), header on line 1:
//   Time,Value            Time = yyyy-MM-dd HH:mm:ss.fff in the chart's time zone
//   (NT's Tools>Options>General "Time zone"; the ingest converts to CT. Value = the
//   internal's Last value: the $TICK reading, the VIX level, the breadth count, etc.)
//
// One file per load, symbol + date stamped so a reload never overwrites a prior dump:
//   TICK_20260801_190000.csv   VIX_20260801_190000.csv
// The symbol is sanitized ($ and ^ stripped) for the filename; the raw Instrument name
// is written into the header comment line so the ingest can verify what it is.
//
// NOTE ON BARS: this exports the RAW update stream (exact timestamps), so there is NO bar
// open/close labeling to get wrong here. Any bar aggregation happens later in Python, where
// NT's convention (bar timestamp = bar CLOSE) is applied explicitly.
//
// Install: NinjaScript Editor -> Indicators -> paste -> compile. Apply to a $TICK (etc.)
// chart with Tick Replay ON and the desired days-back. RULE: lives in nt8/ and stays committed.

#region Using declarations
using System;
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
        private StreamWriter writer;
        private long rows;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Dumps every Last update (time,value) of a market internal/index ($TICK,$VIX,...) to CSV";
                Name = "MarketInternalExporter";
                Calculate = Calculate.OnEachTick;     // per-update; Tick Replay feeds Last here
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportDir = @"C:\Users\Admin\myquant\data\nt_internals";
            }
            else if (State == State.DataLoaded)
            {
                try
                {
                    Directory.CreateDirectory(ExportDir);
                    string raw = Instrument.FullName;                 // e.g. "$TICK" / "^VIX"
                    string safe = Regex.Replace(raw, @"[^A-Za-z0-9]", "");   // -> "TICK" / "VIX"
                    string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                    string path = Path.Combine(ExportDir, string.Format("{0}_{1}.csv", safe, stamp));
                    writer = new StreamWriter(path, false);
                    writer.WriteLine("# symbol=" + raw);              // exact instrument for the ingest to verify
                    writer.WriteLine("Time,Value");
                    rows = 0;
                    Log("MarketInternalExporter -> " + path, LogLevel.Information);
                }
                catch (Exception e) { Log("MarketInternalExporter open failed: " + e.Message, LogLevel.Error); }
            }
            else if (State == State.Terminated)
            {
                if (writer != null)
                {
                    writer.Flush(); writer.Close(); writer = null;
                    Log("MarketInternalExporter wrote " + rows + " updates", LogLevel.Information);
                }
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (writer == null || e.MarketDataType != MarketDataType.Last) return;
            // invariant culture so the decimal point is '.' regardless of PC locale
            writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                "{0:yyyy-MM-dd HH:mm:ss.fff},{1}", e.Time, e.Price));
            rows++;
        }

        protected override void OnBarUpdate() { /* all work happens in OnMarketData */ }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 0)]
        public string ExportDir { get; set; }
    }
}
