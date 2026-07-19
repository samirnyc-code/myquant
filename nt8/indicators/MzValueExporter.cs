// MzValueExporter — captures MzPack's OWN computed values while the 14-day trial lasts (S75V).
//
// WHY: mzVolumeDelta exposes public Series (Delta, CumDelta, BuyVolume, SellVolume) and
// mzVolumeProfile exposes POC/VAH/VAL. Those are an INDEPENDENT commercial implementation of
// the same metrics we compute ourselves from the tape. Recording them gives a ground-truth
// set to validate our own math against — the S75H footprint validation was six bars eyeballed;
// this makes it thousands of bars, systematically. The trial expires ~2026-07-30 and these
// values are unreproducible afterwards, so the capture window is fixed.
//
// This is a VALIDATION REFERENCE, not a data source. We can already derive delta/CVD/POC at
// any timeframe from the recorded tape; the point is to prove those derivations are right.
// One timeframe is enough (5M) — if our 5M matches theirs, the same code path at 1M/6500V
// is trustworthy too.
//
// HOW IT WORKS: MzPack ships as a separate assembly, so NT8 generates no wrapper methods
// (mzVolumeDelta(...) is not callable). Instead this finds the ALREADY-RUNNING instances on
// the same chart and reads their public members. ALL access is via reflection, so this file
// compiles whether or not MzPack is installed and whatever their API looks like — a mismatch
// degrades to empty columns and a log line, never a compile error or a runtime throw.
//
// INSTALL: apply to a chart that ALREADY has mzVolumeDelta and/or mzVolumeProfile on it.
// Writes data\footprint\ES_5Min_mzvalues_<stamp>.csv (one row per closed bar).
//
// SAFETY: every reflection call is individually guarded. If anything is missing the column is
// blank. This indicator must never be able to destabilise a recording session.
// RULE (CLAUDE.md): lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Reflection;
using NinjaTrader.Cbi;          // LogLevel
using NinjaTrader.Data;         // BarsPeriodType
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MzValueExporter : Indicator
    {
        private StreamWriter w;
        private object volDelta, volProfile;      // the live MzPack instances (untyped)
        private bool resolved;
        private long rows;

        private const BindingFlags PUB = BindingFlags.Public | BindingFlags.Instance | BindingFlags.FlattenHierarchy;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "MzValueExporter";
                Description = "Logs mzVolumeDelta / mzVolumeProfile values as a validation reference (trial-window capture)";
                Calculate = Calculate.OnBarClose;   // one row per CLOSED bar: stable, comparable
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportDir = @"C:\Users\Admin\myquant\data\footprint";
            }
            else if (State == State.DataLoaded)
            {
                try
                {
                    Directory.CreateDirectory(ExportDir);
                    string path = Path.Combine(ExportDir, string.Format("{0}_{1}_mzvalues_{2:yyyyMMdd_HHmmss}.csv",
                        Instrument.MasterInstrument.Name, PeriodTag(), DateTime.Now));
                    w = new StreamWriter(path, false);
                    w.WriteLine("BarIdx,BarTime,mzDelta,mzCumDelta,mzBuyVol,mzSellVol,mzPOC,mzVAH,mzVAL");
                    Log("MzValueExporter -> " + path, NinjaTrader.Cbi.LogLevel.Information);
                }
                catch (Exception e) { Log("MzValueExporter open failed: " + e.Message, NinjaTrader.Cbi.LogLevel.Error); }
            }
            else if (State == State.Terminated)
            {
                if (w != null)
                {
                    Log(string.Format("MzValueExporter wrote {0:N0} rows (volDelta={1}, volProfile={2})",
                        rows, volDelta != null, volProfile != null), NinjaTrader.Cbi.LogLevel.Information);
                    try { w.Flush(); w.Close(); } catch { }
                    w = null;
                }
            }
        }

        private string PeriodTag()
        {
            int v = BarsPeriod.Value;
            switch (BarsPeriod.BarsPeriodType)
            {
                case BarsPeriodType.Minute: return v + "Min";
                case BarsPeriodType.Volume: return v + "V";
                case BarsPeriodType.Tick:   return v + "T";
                case BarsPeriodType.Range:  return v + "R";
                default:                    return BarsPeriod.BarsPeriodType + "" + v;
            }
        }

        /// Find the MzPack indicators already applied to this chart. Reflection throughout:
        /// ChartControl's indicator collection differs across NT8 builds, so we probe for any
        /// enumerable property and match on type NAME rather than binding to their types.
        private void Resolve()
        {
            resolved = true;
            try
            {
                if (ChartControl == null) { Log("MzValueExporter: no ChartControl (apply to a CHART)", NinjaTrader.Cbi.LogLevel.Warning); return; }
                foreach (PropertyInfo p in ChartControl.GetType().GetProperties(PUB))
                {
                    if (!typeof(IEnumerable).IsAssignableFrom(p.PropertyType) || p.PropertyType == typeof(string)) continue;
                    IEnumerable coll = null;
                    try { coll = p.GetValue(ChartControl, null) as IEnumerable; } catch { }
                    if (coll == null) continue;
                    foreach (object o in coll)
                    {
                        if (o == null) continue;
                        string n = o.GetType().Name;
                        if (n == "mzVolumeDelta" && volDelta == null) volDelta = o;
                        else if (n == "mzVolumeProfile" && volProfile == null) volProfile = o;
                    }
                    if (volDelta != null && volProfile != null) break;
                }
                Log(string.Format("MzValueExporter resolved: mzVolumeDelta={0} mzVolumeProfile={1}",
                    volDelta != null, volProfile != null),
                    (volDelta == null && volProfile == null) ? NinjaTrader.Cbi.LogLevel.Warning : NinjaTrader.Cbi.LogLevel.Information);
            }
            catch (Exception e) { Log("MzValueExporter resolve failed: " + e.Message, NinjaTrader.Cbi.LogLevel.Warning); }
        }

        /// Read Series<double> member `name` at barsAgo 0. Blank on any mismatch.
        private string Ser(object host, string name)
        {
            if (host == null) return "";
            try
            {
                PropertyInfo p = host.GetType().GetProperty(name, PUB);
                object s = p == null ? null : p.GetValue(host, null);
                if (s == null) return "";
                object v = s.GetType().InvokeMember("Item", BindingFlags.GetProperty, null, s, new object[] { 0 });
                return v == null ? "" : Convert.ToDouble(v).ToString("0.####");
            }
            catch { return ""; }
        }

        /// Read a plain numeric property (POC / VAH / VAL) off the CURRENT volume profile.
        private string Val(object host, string name)
        {
            if (host == null) return "";
            try
            {
                PropertyInfo p = host.GetType().GetProperty(name, PUB);
                if (p != null)
                {
                    object v = p.GetValue(host, null);
                    if (v != null) return Convert.ToDouble(v).ToString("0.####");
                }
                // not on the indicator itself -> try the newest profile in its Profiles collection
                PropertyInfo pf = host.GetType().GetProperty("Profiles", PUB);
                IEnumerable profiles = pf == null ? null : pf.GetValue(host, null) as IEnumerable;
                if (profiles == null) return "";
                object last = null;
                foreach (object o in profiles) if (o != null) last = o;
                if (last == null) return "";
                PropertyInfo p2 = last.GetType().GetProperty(name, PUB);
                object v2 = p2 == null ? null : p2.GetValue(last, null);
                return v2 == null ? "" : Convert.ToDouble(v2).ToString("0.####");
            }
            catch { return ""; }
        }

        protected override void OnBarUpdate()
        {
            if (w == null || CurrentBar < 1) return;
            if (!resolved) Resolve();
            if (volDelta == null && volProfile == null) return;   // nothing to log; stay silent
            try
            {
                w.WriteLine(string.Join(",", new string[] {
                    CurrentBar.ToString(),
                    Time[0].ToString("yyyy-MM-dd HH:mm:ss"),
                    Ser(volDelta, "Delta"), Ser(volDelta, "CumDelta"),
                    Ser(volDelta, "BuyVolume"), Ser(volDelta, "SellVolume"),
                    Val(volProfile, "POC"), Val(volProfile, "VAH"), Val(volProfile, "VAL")
                }));
                if (++rows % 50 == 0) w.Flush();
            }
            catch (Exception e) { Log("MzValueExporter row failed: " + e.Message, NinjaTrader.Cbi.LogLevel.Warning); }
        }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 0)]
        public string ExportDir { get; set; }
    }
}
