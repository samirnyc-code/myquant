// EABreadthProbe — one-shot probe: which CQG breadth symbols does THIS feed
// actually deliver? Needed before porting the ToS BWD_MarketBreadth study
// (NYSE+NASDAQ adv/decl issues + up/down volume).
//
// Already VERIFIED live via MarketInternalExporter: ^ADV, ^UVOL, ^DVOL, ^TICK,
// ^TICKQ, ^TRIN, ^VIX. This probes the still-unverified ones (CQG list per
// EdgeClear "Market Internals - CQG"): ^DECL, NASDAQ ^NUPI/^NDNI/^NUPV/^NDNV,
// plus ^TRINQ and ^ADD re-checks.
//
// USE: compile (F5), apply to any ES chart with >=5 days loaded, wait for the
// chart to finish loading. It writes data/nt_internals/breadth_probe_<stamp>.txt
// with "symbol,bars,lastTime,lastClose" per symbol (0 bars = feed has nothing).
// Then remove it from the chart. RULE: lives in nt8/ and stays committed.

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
    public class EABreadthProbe : Indicator
    {
        private static readonly string[] SYMS = {
            "^DECL", "^NUPI", "^NDNI", "^NUPV", "^NDNV", "^TRINQ", "^ADD"
        };
        private const string EXPORT_DIR = @"C:\Users\Admin\myquant\data\nt_internals";

        private List<string> added;
        private long[] counts;
        private DateTime[] lastTime;
        private double[] lastClose;
        private bool wrote;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "EABreadthProbe";
                Description = "Probe which CQG breadth symbols deliver data (writes breadth_probe_*.txt)";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
            }
            else if (State == State.Configure)
            {
                added = new List<string>();
                foreach (string s in SYMS)
                {
                    try { AddDataSeries(s, BarsPeriodType.Minute, 5); added.Add(s); }
                    catch (Exception e) { Log("EABreadthProbe skip '" + s + "': " + e.Message, LogLevel.Warning); }
                }
            }
            else if (State == State.DataLoaded)
            {
                counts    = new long[added.Count];
                lastTime  = new DateTime[added.Count];
                lastClose = new double[added.Count];
            }
            else if (State == State.Terminated)
            {
                WriteReport();
            }
        }

        protected override void OnBarUpdate()
        {
            int bip = BarsInProgress;
            if (bip > 0)
            {
                int i = bip - 1;
                if (counts == null || i >= counts.Length) return;
                counts[i]++;
                lastTime[i]  = Times[bip][0];
                lastClose[i] = Closes[bip][0];
                return;
            }
            // end of the primary series' historical bars: write the report once
            if (!wrote && State == State.Historical && CurrentBar == BarsArray[0].Count - 1)
                WriteReport();
        }

        private void WriteReport()
        {
            if (counts == null) return;
            wrote = true;
            try
            {
                Directory.CreateDirectory(EXPORT_DIR);
                string path = Path.Combine(EXPORT_DIR,
                    "breadth_probe_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".txt");
                using (var w = new StreamWriter(path, false))
                {
                    w.WriteLine("symbol,bars,lastTime,lastClose");
                    for (int i = 0; i < added.Count; i++)
                        w.WriteLine(string.Format(CultureInfo.InvariantCulture, "{0},{1},{2:yyyy-MM-dd HH:mm:ss},{3}",
                            added[i], counts[i], lastTime[i], lastClose[i]));
                }
                Log("EABreadthProbe report -> " + path, LogLevel.Information);
            }
            catch (Exception e) { Log("EABreadthProbe write failed: " + e.Message, LogLevel.Error); }
        }
    }
}
