#region Using declarations
using System.Collections.Generic;
#endregion

// ClaudeTrackerChartRegistry.cs — shared in-process lookup: instrument full name ->
// ChartControl, populated by ClaudeTrackerChartTag.cs (drop it on the real execution
// chart), read by ClaudeTrackerAddOn.cs's RequestScreenshot(). Lives in the plain
// NinjaTrader.NinjaScript namespace (parent of both .Indicators and .AddOns) so both
// sides can reference it without a using statement pointing at the other's namespace.
// All Custom\ .cs files compile into one assembly (NinjaTrader.Custom.dll) so this works
// across files same as any other NinjaScript cross-file reference in this repo.
namespace NinjaTrader.NinjaScript
{
    public static class ClaudeTrackerChartRegistry
    {
        private static readonly object Lock = new object();
        private static readonly Dictionary<string, NinjaTrader.Gui.Chart.ChartControl> ByInstrument =
            new Dictionary<string, NinjaTrader.Gui.Chart.ChartControl>();

        public static void Register(string instrumentFullName, NinjaTrader.Gui.Chart.ChartControl cc)
        {
            lock (Lock) { ByInstrument[instrumentFullName] = cc; }
        }

        public static void Unregister(string instrumentFullName, NinjaTrader.Gui.Chart.ChartControl cc)
        {
            lock (Lock)
            {
                NinjaTrader.Gui.Chart.ChartControl existing;
                if (ByInstrument.TryGetValue(instrumentFullName, out existing) && existing == cc)
                    ByInstrument.Remove(instrumentFullName);
            }
        }

        public static NinjaTrader.Gui.Chart.ChartControl Get(string instrumentFullName)
        {
            lock (Lock)
            {
                NinjaTrader.Gui.Chart.ChartControl cc;
                return ByInstrument.TryGetValue(instrumentFullName, out cc) ? cc : null;
            }
        }
    }
}
