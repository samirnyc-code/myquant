// DtDbCvdPivotRegistry.cs — shared in-process lookup: DtDbScannerV3 publishes the two
// pivot TIMES/prices of every confirmed DT/DB where its own bar-proxy CVD agrees with
// the pattern's bias; CVDDivergenceOscillator.cs reads this (when its new "Only show
// at DT/DB" toggle is on) to draw its divergence line ONLY at those pivots instead of
// its own independently-detected fractal pivots. Same pattern as
// ClaudeTrackerChartRegistry.cs (nt8/indicators/ClaudeTrackerChartRegistry.cs) — a
// plain static class in the NinjaTrader.NinjaScript namespace (parent of
// .Indicators), so both files can reference it without a using statement pointing at
// each other, and it works across files because NT8 compiles the whole Custom\ tree
// into one assembly.
//
// 2026-10-29 FIX: v1 shared raw CurrentBar indices, valid ONLY if both indicators run
// on the exact same chart/bar-series — confirmed broken live: user had
// CVDDivergenceOscillator's new toggle on a 2000-tick chart, drew nothing, because
// DtDbScannerV3 wasn't necessarily on that same chart/bar-type (a 1000-tick chart's
// bar index for the same wall-clock moment is a completely different number). Switched
// to DateTime + Instrument.FullName: a timestamp means the same real market moment
// regardless of bar type, and each side converts independently via its OWN Bars object
// (Bars.GetTime(barIndex) to publish, Bars.GetBar(DateTime) to consume — both are
// standard NT8 Bars methods, already used this way elsewhere in this repo, e.g.
// nt8/vendor/ntlambda's BarsArray[0].GetBar(...) calls). Also now scoped by instrument
// so two different instruments' structures can never cross-contaminate.
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

using System;
using System.Collections.Generic;
using System.IO;

namespace NinjaTrader.NinjaScript
{
    public struct DtDbCvdPivot
    {
        public int Id;              // monotonic, so a reader can tell "new since I last checked"
        public string InstrumentFullName;
        public bool IsTop;
        public DateTime P1Time, P2Time;
        public double P1Price, P2Price;
    }

    public static class DtDbCvdPivotRegistry
    {
        // 2026-10-29 FIX: was 200. Confirmed via diagnostic log a 200-cap evicts entries
        // faster than a consumer whose own historical replay finishes later (or slower)
        // than the publisher's can ever read them — DtDbScannerV3 published 2,289+
        // entries during its historical catch-up alone, so ~2,000 were being silently
        // evicted before CVDDivergenceOscillator's one-time State.Realtime catch-up (or
        // its ongoing per-bar poll) ever got to them. 20000 comfortably covers a full
        // historical replay's worth of confirmed DT/DB structures with headroom; this is
        // a plain List<struct>, not expensive to hold at this size.
        private const int MaxKept = 20000;
        private static readonly object Lock = new object();
        private static readonly List<DtDbCvdPivot> Recent = new List<DtDbCvdPivot>();
        private static int nextId = 1;

        // 2026-10-29 TEMP DIAGNOSTIC: user reports zero lines drawn across two already-
        // applied fixes (cross-chart bar index, historical-replay ordering) — rather than
        // guess a third cause, log every Publish AND every GetSince call (incl. zero-result
        // ones) to a plain file so the actual failure point can be read directly instead of
        // inferred. Remove once root-caused. Append-only, tiny, no lock contention risk
        // (separate try/catch, never blocks the real Lock above).
        private const string DiagPath = @"C:\Users\Admin\myquant\data\_dtdb_cvd_registry_diag.log";
        public static void Diag(string msg)
        {
            try { File.AppendAllText(DiagPath, DateTime.Now.ToString("HH:mm:ss.fff") + "  " + msg + "\r\n"); }
            catch { /* diagnostic only, never let logging break the real feature */ }
        }

        public static void Publish(string instrumentFullName, bool isTop,
            DateTime p1Time, double p1Price, DateTime p2Time, double p2Price)
        {
            lock (Lock)
            {
                int id = nextId++;
                Recent.Add(new DtDbCvdPivot
                {
                    Id = id, InstrumentFullName = instrumentFullName, IsTop = isTop,
                    P1Time = p1Time, P1Price = p1Price, P2Time = p2Time, P2Price = p2Price
                });
                if (Recent.Count > MaxKept) Recent.RemoveAt(0);
                Diag("PUBLISH id=" + id + " instr=\"" + instrumentFullName + "\" isTop=" + isTop
                    + " p1=" + p1Time.ToString("MM-dd HH:mm:ss") + "@" + p1Price
                    + " p2=" + p2Time.ToString("MM-dd HH:mm:ss") + "@" + p2Price
                    + " totalKept=" + Recent.Count);
            }
        }

        // Returns every published pivot for instrumentFullName with Id > sinceId (i.e.
        // new since the caller's last read), oldest first. Callers track their own
        // last-seen Id.
        // GetSince is called every bar when OnlyShowAtDtDb is on — only log the FIRST ever
        // call (proves the consumer side is wired up at all) and any call that actually
        // matches something (the interesting case), not the routine zero-match majority,
        // or this file would grow unbounded on a tick chart.
        private static bool loggedFirstGetSince;
        public static List<DtDbCvdPivot> GetSince(string instrumentFullName, int sinceId)
        {
            lock (Lock)
            {
                List<DtDbCvdPivot> result = new List<DtDbCvdPivot>();
                foreach (DtDbCvdPivot p in Recent)
                    if (p.Id > sinceId && p.InstrumentFullName == instrumentFullName) result.Add(p);
                if (!loggedFirstGetSince || result.Count > 0)
                {
                    loggedFirstGetSince = true;
                    Diag("GETSINCE instr=\"" + instrumentFullName + "\" sinceId=" + sinceId
                        + " totalInRegistry=" + Recent.Count + " matched=" + result.Count);
                }
                return result;
            }
        }
    }
}
