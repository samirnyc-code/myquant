// RawTickExporter — dumps every Last trade (time, price, size) to CSV so we can
// extend the continuous 5M database from NT8's own tick data when the Massive/Databento
// flatfile pull isn't available (S90).
//
// This is the RAW-TICK sibling of FootprintExporter: FootprintExporter reconstructs a
// per-price bid/ask ladder (order flow); this one just emits the plain trade tape that
// scripts\ingest_nt_ticks.py resamples into data\ticks_continuous\{date}.parquet exactly
// the way massive.py builds it from flatfiles.
//
// REQUIRES TICK REPLAY: right-click the ES data series -> "Tick Replay" ON, then set the
// chart to enough days back to cover the window you want (e.g. 15 days). On load, Tick
// Replay streams the historical Last ticks through OnMarketData and they are written out.
//
// CONTRACT DISCIPLINE (CLAUDE.md / the user's offset+contract ask):
//   Apply this to the SPECIFIC front-month contract chart ("ES 09-26"), NOT a continuous
//   "ES ##-##" series. NT back-adjusts continuous series with ITS OWN offset; our Python
//   pipeline applies the Panama offset itself (0 for the current anchor). Feeding it an
//   already-back-adjusted continuous price would double-count. The full contract name is
//   written into the filename so the ingest can verify it against rolls.json.
//
// Output CSV (one row per Last trade), header on line 1:
//   Time,Price,Volume         Time = yyyy-MM-dd HH:mm:ss.fff in the chart's time zone
//   (NT's configured Tools>Options>General>"Time zone" — the ingest converts to CT; if NT
//   is already on exchange/Central time it's an identity round-trip).
//
// One file per load, date-stamped, so a chart reload never overwrites a prior dump
// (same rule FootprintExporter learned the hard way on 2026-07-19).
//   ES_09-26_ticks_20260728_101500.csv
//
// Install: NinjaScript Editor -> Indicators -> paste -> compile. Apply to an ES 09-26
// chart with Tick Replay ON and the desired days-back. RULE: lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class RawTickExporter : Indicator
    {
        private StreamWriter writer;
        private long rows;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Dumps every Last trade (time,price,size) to CSV for the continuous-DB ingest";
                Name = "RawTickExporter";
                Calculate = Calculate.OnEachTick;     // MUST be per-tick (Tick Replay feeds Last here)
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportDir = @"C:\Users\Admin\myquant\data\nt_ticks";
            }
            else if (State == State.DataLoaded)
            {
                try
                {
                    Directory.CreateDirectory(ExportDir);
                    // FULL contract ("ES 09-26") in the name so the ingest can assert the
                    // export contract == the front-month contract for those dates.
                    string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                    string fname = string.Format("{0}_ticks_{1}.csv",
                        Instrument.FullName.Replace(" ", "_"), stamp);
                    string path = Path.Combine(ExportDir, fname);
                    writer = new StreamWriter(path, false);
                    writer.WriteLine("Time,Price,Volume");
                    rows = 0;
                    Log("RawTickExporter -> " + path, LogLevel.Information);
                }
                catch (Exception e) { Log("RawTickExporter open failed: " + e.Message, LogLevel.Error); }
            }
            else if (State == State.Terminated)
            {
                if (writer != null)
                {
                    writer.Flush(); writer.Close(); writer = null;
                    Log("RawTickExporter wrote " + rows + " ticks", LogLevel.Information);
                }
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (writer == null || e.MarketDataType != MarketDataType.Last) return;
            // invariant culture so the decimal point is '.' regardless of PC locale (the
            // ingest parses with pandas which expects '.').
            writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                "{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2}", e.Time, e.Price, (long)e.Volume));
            rows++;
        }

        protected override void OnBarUpdate() { /* all work happens in OnMarketData */ }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 0)]
        public string ExportDir { get; set; }
    }
}
