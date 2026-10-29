// DtDbCvdPivotRegistry.cs — shared in-process lookup: DtDbScannerV3 publishes the two
// pivot bars/prices of every confirmed DT/DB where its own bar-proxy CVD agrees with
// the pattern's bias; CVDDivergenceOscillator.cs reads this (when its new "Only show
// at DT/DB" toggle is on) to draw its divergence line ONLY at those pivots instead of
// its own independently-detected fractal pivots. Same pattern as
// ClaudeTrackerChartRegistry.cs (nt8/indicators/ClaudeTrackerChartRegistry.cs) — a
// plain static class in the NinjaTrader.NinjaScript namespace (parent of
// .Indicators), so both files can reference it without a using statement pointing at
// each other, and it works across files because NT8 compiles the whole Custom\ tree
// into one assembly.
//
// Bar indices are valid to share directly ONLY because both indicators are expected
// to run on the SAME chart (same underlying Bars object) — CurrentBar there is an
// absolute index from bar 0, identical across every indicator on that one chart. This
// would NOT be safe to share across two different charts/instruments.
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

using System.Collections.Generic;

namespace NinjaTrader.NinjaScript
{
    public struct DtDbCvdPivot
    {
        public int Id;              // monotonic, so a reader can tell "new since I last checked"
        public bool IsTop;
        public int P1Bar, P2Bar;
        public double P1Price, P2Price;
    }

    public static class DtDbCvdPivotRegistry
    {
        private const int MaxKept = 200;   // ring buffer — old entries age out, readers only care about recent ones
        private static readonly object Lock = new object();
        private static readonly List<DtDbCvdPivot> Recent = new List<DtDbCvdPivot>();
        private static int nextId = 1;

        public static void Publish(bool isTop, int p1Bar, double p1Price, int p2Bar, double p2Price)
        {
            lock (Lock)
            {
                Recent.Add(new DtDbCvdPivot
                {
                    Id = nextId++, IsTop = isTop,
                    P1Bar = p1Bar, P1Price = p1Price, P2Bar = p2Bar, P2Price = p2Price
                });
                if (Recent.Count > MaxKept) Recent.RemoveAt(0);
            }
        }

        // Returns every published pivot with Id > sinceId (i.e. new since the caller's
        // last read), oldest first. Callers track their own last-seen Id.
        public static List<DtDbCvdPivot> GetSince(int sinceId)
        {
            lock (Lock)
            {
                List<DtDbCvdPivot> result = new List<DtDbCvdPivot>();
                foreach (DtDbCvdPivot p in Recent)
                    if (p.Id > sinceId) result.Add(p);
                return result;
            }
        }
    }
}
