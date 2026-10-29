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
        private const int MaxKept = 200;   // ring buffer — old entries age out, readers only care about recent ones
        private static readonly object Lock = new object();
        private static readonly List<DtDbCvdPivot> Recent = new List<DtDbCvdPivot>();
        private static int nextId = 1;

        public static void Publish(string instrumentFullName, bool isTop,
            DateTime p1Time, double p1Price, DateTime p2Time, double p2Price)
        {
            lock (Lock)
            {
                Recent.Add(new DtDbCvdPivot
                {
                    Id = nextId++, InstrumentFullName = instrumentFullName, IsTop = isTop,
                    P1Time = p1Time, P1Price = p1Price, P2Time = p2Time, P2Price = p2Price
                });
                if (Recent.Count > MaxKept) Recent.RemoveAt(0);
            }
        }

        // Returns every published pivot for instrumentFullName with Id > sinceId (i.e.
        // new since the caller's last read), oldest first. Callers track their own
        // last-seen Id.
        public static List<DtDbCvdPivot> GetSince(string instrumentFullName, int sinceId)
        {
            lock (Lock)
            {
                List<DtDbCvdPivot> result = new List<DtDbCvdPivot>();
                foreach (DtDbCvdPivot p in Recent)
                    if (p.Id > sinceId && p.InstrumentFullName == instrumentFullName) result.Add(p);
                return result;
            }
        }
    }
}
