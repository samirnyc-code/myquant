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
        public bool IsHidden;       // 2026-10-29: hidden-CVD-divergence pivot, not a regular-agree one
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

        // 2026-10-29: isHidden param added so a hidden-CVD-divergence pivot (separate
        // condition from the regular CvdAgrees check that feeds the default publishes)
        // can be told apart on the consumer side — CVDDivergenceOscillator draws it in a
        // distinct color, not bull/bear. Default false keeps every existing call site
        // (regular-agree publishes) unchanged.
        public static void Publish(string instrumentFullName, bool isTop,
            DateTime p1Time, double p1Price, DateTime p2Time, double p2Price, bool isHidden = false)
        {
            lock (Lock)
            {
                int id = nextId++;
                Recent.Add(new DtDbCvdPivot
                {
                    Id = id, InstrumentFullName = instrumentFullName, IsTop = isTop,
                    P1Time = p1Time, P1Price = p1Price, P2Time = p2Time, P2Price = p2Price,
                    IsHidden = isHidden
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
