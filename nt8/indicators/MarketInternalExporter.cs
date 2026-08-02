// MarketInternalExporter — export MANY market-internal / index symbols at once (^TICK,
// ^VIX, ^ADD, ^ADV, ^UVOL, ^DVOL, ^TRIN, ^TICKQ, ^TRINQ, BANK, DX 09-26, ...) to CSV, from a
// SINGLE indicator on a SINGLE chart, so we can build a multi-year history to test the method.
//
// HOW IT WORKS
//   Give it a comma-separated Symbols list. It AddDataSeries() each one itself at the chosen
//   PeriodMinutes, so you do NOT have to add them to the chart by hand — just apply this
//   indicator, set the list + period + days-back, and it writes one CSV per symbol. Internals
//   only need standard historical BARS (no Tick Replay), and one bar per symbol keeps the
//   $TICK / breadth EXTREMES (bar High/Low) for divergence work. Symbols that don't exist in
//   your feed are SKIPPED (logged) without breaking the rest.
//
// OUTPUT (one row per bar; header line 2, line 1 = exact symbol):
//   # symbol=^TICK
//   Time,Open,High,Low,Close,Volume   Time = bar CLOSE time (NT convention),
//   yyyy-MM-dd HH:mm:ss in the chart's time zone (the Python ingest converts to CT).
//   Files: TICK_5m_<stamp>.csv, VIX_5m_<stamp>.csv ...  never overwrites a prior dump.
//
// FEED: quote symbols exactly as your feed's Instrument list shows them (yours uses "^":
//   ^TICK,^VIX,^ADD,^ADV,^UVOL,^DVOL,^TRIN,^TICKQ,^TRINQ; plus BANK and DX 09-26 for the
//   USD/BANK signals). ^ADVN/^DECN do NOT exist in this feed — use ^ADV/^ADD/^UVOL/^DVOL.
//
// Install: NinjaScript Editor -> Indicators -> paste -> compile (F5). Apply to ANY chart, set
//   Symbols + PeriodMinutes + chart days-back, reload. RULE: lives in nt8/ and stays committed.

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
        private List<string> added;          // symbols that ACTUALLY got added, in series order
        private StreamWriter[] writers;      // writers[i] <-> added[i] <-> BarsInProgress (i+1)
        private long[] counts;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports many market internals/indices as bars to CSV from one chart";
                Name = "MarketInternalExporter";
                Calculate = Calculate.OnBarClose;     // one final row per closed bar (no Tick Replay needed)
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportDir = @"C:\Users\Admin\myquant\data\nt_internals";
                Symbols = "^TICK,^VIX,^ADD,^ADV,^UVOL,^DVOL,^TRIN,^TICKQ,^TRINQ";
                PeriodMinutes = 5;
            }
            else if (State == State.Configure)
            {
                // add only the symbols that succeed; a bad symbol is skipped, not fatal, and
                // does NOT consume a BarsInProgress slot (so 'added' stays aligned to series).
                added = new List<string>();
                foreach (string s in SplitSymbols(Symbols))
                {
                    try { AddDataSeries(s, BarsPeriodType.Minute, PeriodMinutes); added.Add(s); }
                    catch (Exception e) { Log("MarketInternalExporter skip '" + s + "': " + e.Message, LogLevel.Warning); }
                }
            }
            else if (State == State.DataLoaded)
            {
                writers = new StreamWriter[added.Count];
                counts = new long[added.Count];
                try { Directory.CreateDirectory(ExportDir); } catch { }
                string stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                for (int i = 0; i < added.Count; i++)
                {
                    try
                    {
                        string safe = Regex.Replace(added[i], @"[^A-Za-z0-9]", "");   // "^TICK"->"TICK", "DX 09-26"->"DX0926"
                        string path = Path.Combine(ExportDir,
                            string.Format("{0}_{1}m_{2}.csv", safe, PeriodMinutes, stamp));
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

        [NinjaScriptProperty]
        [Display(Name = "Symbols", GroupName = "Parameters", Order = 0,
            Description = "Comma-separated internals/indices exactly as your feed lists them, e.g. ^TICK,^VIX,^ADD,^ADV,^UVOL,^DVOL,^TRIN")]
        public string Symbols { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "PeriodMinutes", GroupName = "Parameters", Order = 1)]
        public int PeriodMinutes { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 2)]
        public string ExportDir { get; set; }
    }
}
