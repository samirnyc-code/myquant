// TickExportAddOn.cs — headless NT8 .ncd -> CSV tick exporter (S104, 2026-08-18).
//
// Reads NT8's OWN stored tick data (db/tick/ES 09-26/*.ncd) via BarsRequest, so NT
// decodes its proprietary binary format for us — we NEVER parse .ncd by hand (that
// would risk silently corrupting the 5yr trove). Writes the SAME CSV the old
// RawTickExporter did (header "Time,Price,Volume"), so scripts/ingest_nt_ticks.py is
// unchanged: filename ES_<contract>_ticks_<date>_<stamp>.csv.
//
// WHY AN ADDON (not the old Indicator): auto-loads on NT startup, survives
// compile/restart, needs no chart / no Tick Replay / no GUI. The Indicator kept getting
// dropped off its chart (that's why the export died 2026-08-01).
//
// DRIVEN BY A REQUEST FILE so Python owns the orchestration (it knows which trove days
// are missing):
//   data\nt_ticks\_request.json = {"contract":"ES 09-26","from":"2026-08-04","to":"2026-08-18"}
// The AddOn exports each CALENDAR day in [from,to] (inclusive), ONE AT A TIME (bounded
// memory), to a dated CSV, then writes _request.done.json and deletes _request.json.
//
// TIME ZONE: BarsRequest bar times return in NT's configured zone (CT here, per
// Tools>Options>General). The ingest localizes with --src-tz America/Chicago (identity),
// RTH-filters [08:30,15:15) CT, and runs a seam-continuity check — so a tz/offset slip
// can't silently corrupt the trove; it surfaces as empty days / a flagged seam.
//
// RULE (CLAUDE.md): lives in nt8/ and stays committed. Deploy to
//   Documents\NinjaTrader 8\bin\Custom\AddOns\  then F5.

#region Using declarations
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Timers;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public class TickExportAddOn : AddOnBase
    {
        private const string ExportDir = @"C:\Users\Admin\myquant\data\nt_ticks";
        private static readonly string REQ = Path.Combine(ExportDir, "_request.json");
        private static readonly string DONE = Path.Combine(ExportDir, "_request.done.json");

        private System.Timers.Timer poll;
        private readonly object gate = new object();
        private bool busy;                       // one export run at a time
        private bool started;                    // AddOns get SetDefaults (maybe >1x); init once

        protected override void OnStateChange()
        {
            // AddOnBase fires State.SetDefaults (NOT Configure/DataLoaded — those are for
            // indicators/strategies). All init happens here, guarded so a repeat SetDefaults
            // doesn't spawn a second timer (same pattern as MarketDepthRecorderAddOn).
            if (State == State.SetDefaults)
            {
                Name = "TickExportAddOn";
                Description = "Headless .ncd -> CSV tick exporter driven by data\\nt_ticks\\_request.json";
                if (!started)
                {
                    try { Directory.CreateDirectory(ExportDir); } catch { }
                    poll = new System.Timers.Timer(20000);   // check for a request every 20s
                    poll.Elapsed += (s, e) => TryProcess();
                    poll.Start();
                    started = true;
                    Log("TickExportAddOn: loaded, watching " + REQ, LogLevel.Information);
                }
            }
            else if (State == State.Terminated)
            {
                if (poll != null) { try { poll.Stop(); poll.Dispose(); } catch { } poll = null; }
                started = false;
            }
        }

        // ---- request handling -------------------------------------------------------
        private void TryProcess()
        {
            lock (gate) { if (busy) return; if (!File.Exists(REQ)) return; busy = true; }
            try
            {
                string txt = File.ReadAllText(REQ);
                string contract = JsonStr(txt, "contract");
                DateTime from = DateTime.ParseExact(JsonStr(txt, "from"), "yyyy-MM-dd", CultureInfo.InvariantCulture);
                DateTime to = DateTime.ParseExact(JsonStr(txt, "to"), "yyyy-MM-dd", CultureInfo.InvariantCulture);
                if (string.IsNullOrEmpty(contract) || to < from)
                {
                    Log("TickExportAddOn: bad request " + txt, LogLevel.Error);
                    Finish("bad request"); return;
                }
                Instrument instr = Instrument.GetInstrument(contract);
                if (instr == null) { Log("TickExportAddOn: instrument not found: " + contract, LogLevel.Error); Finish("instrument not found"); return; }

                int period = 1;                          // ticks per bar; 1 = raw tick tape
                int.TryParse(JsonStr(txt, "period"), out period);
                if (period < 1) period = 1;

                var days = new List<DateTime>();
                for (DateTime d = from.Date; d <= to.Date; d = d.AddDays(1))
                    if (d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday)
                        days.Add(d);
                Log(string.Format("TickExportAddOn: request {0} {1:yyyy-MM-dd}..{2:yyyy-MM-dd} ({3} weekdays, {4}-tick)",
                                  contract, from, to, days.Count, period), LogLevel.Information);
                ExportNext(instr, contract, days, 0, 0, period);
            }
            catch (Exception ex) { Log("TickExportAddOn request err: " + ex.Message, LogLevel.Error); Finish("error: " + ex.Message); }
        }

        // Export days sequentially: fire one BarsRequest, and in its callback write the
        // CSV and recurse to the next day. Bounded memory, and one failed day is isolated.
        private void ExportNext(Instrument instr, string contract, List<DateTime> days, int idx, int okCount, int period)
        {
            if (idx >= days.Count) { Finish(string.Format("exported {0}/{1} day(s)", okCount, days.Count)); return; }
            DateTime day = days[idx];
            DateTime f = day.Date;                 // 00:00 local (NT/CT)
            DateTime t = day.Date.AddDays(1);      // next 00:00 — full calendar day; ingest RTH-filters
            try
            {
                BarsRequest req = new BarsRequest(instr, f, t);
                req.BarsPeriod = new BarsPeriod { BarsPeriodType = BarsPeriodType.Tick, Value = period };
                req.Request((r, err, msg) =>
                {
                    int wrote = 0;
                    try
                    {
                        if (err != ErrorCode.NoError)
                            Log(string.Format("TickExportAddOn: {0:yyyy-MM-dd} request error {1} {2}", day, err, msg), LogLevel.Warning);
                        else if (r != null && r.Bars != null && r.Bars.Count > 0)
                            wrote = WriteDay(contract, day, r.Bars, period);
                        else
                            Log(string.Format("TickExportAddOn: {0:yyyy-MM-dd} no data", day), LogLevel.Warning);
                    }
                    catch (Exception ex) { Log("TickExportAddOn write err " + day.ToString("yyyy-MM-dd") + ": " + ex.Message, LogLevel.Error); }
                    finally { try { if (r != null) r.Dispose(); } catch { } }
                    ExportNext(instr, contract, days, idx + 1, okCount + (wrote > 0 ? 1 : 0), period);
                });
            }
            catch (Exception ex)
            {
                Log("TickExportAddOn BarsRequest err " + day.ToString("yyyy-MM-dd") + ": " + ex.Message, LogLevel.Error);
                ExportNext(instr, contract, days, idx + 1, okCount, period);
            }
        }

        private int WriteDay(string contract, DateTime day, Bars bars, int period)
        {
            string sym = contract.Replace(" ", "_");
            // period 1 -> raw tick tape (Time,Price,Volume) for the ingest; period>1 -> native
            // N-tick OHLCV bars, for bar-by-bar validation against our resampled bars.
            bool tape = period <= 1;
            string kind = tape ? "ticks" : ("bars" + period + "t");
            string path = Path.Combine(ExportDir, string.Format("{0}_{1}_{2:yyyyMMdd}_{3:HHmmss}.csv",
                                       sym, kind, day, DateTime.Now));
            int n = 0;
            using (var w = new StreamWriter(path, false, System.Text.Encoding.ASCII, 1 << 20))
            {
                w.WriteLine(tape ? "Time,Price,Volume" : "Time,Open,High,Low,Close,Volume");
                for (int i = 0; i < bars.Count; i++)
                {
                    if (tape)
                        w.WriteLine(string.Format(CultureInfo.InvariantCulture,
                            "{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2}",
                            bars.GetTime(i), bars.GetClose(i), (long)bars.GetVolume(i)));
                    else
                        w.WriteLine(string.Format(CultureInfo.InvariantCulture,
                            "{0:yyyy-MM-dd HH:mm:ss.fff},{1},{2},{3},{4},{5}",
                            bars.GetTime(i), bars.GetOpen(i), bars.GetHigh(i), bars.GetLow(i),
                            bars.GetClose(i), (long)bars.GetVolume(i)));
                    n++;
                }
            }
            Log(string.Format("TickExportAddOn: {0:yyyy-MM-dd} -> {1} ({2} {3})", day, Path.GetFileName(path), n, kind), LogLevel.Information);
            return n;
        }

        private void Finish(string note)
        {
            try
            {
                File.WriteAllText(DONE, "{\"done\":\"" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "\",\"note\":\"" + note.Replace("\"", "'") + "\"}");
                if (File.Exists(REQ)) File.Delete(REQ);
            }
            catch (Exception ex) { Log("TickExportAddOn finish err: " + ex.Message, LogLevel.Error); }
            Log("TickExportAddOn: " + note, LogLevel.Information);
            lock (gate) { busy = false; }
        }

        // tiny dependency-free JSON string field reader (values are simple strings)
        private static string JsonStr(string json, string key)
        {
            string needle = "\"" + key + "\"";
            int k = json.IndexOf(needle, StringComparison.Ordinal);
            if (k < 0) return null;
            int c = json.IndexOf(':', k + needle.Length);
            if (c < 0) return null;
            int q1 = json.IndexOf('"', c + 1);
            if (q1 < 0) return null;
            int q2 = json.IndexOf('"', q1 + 1);
            if (q2 < 0) return null;
            return json.Substring(q1 + 1, q2 - q1 - 1);
        }
    }
}
