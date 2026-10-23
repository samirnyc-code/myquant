#region Using declarations
using System;
using NinjaTrader.NinjaScript;
#endregion

// ClaudeTrackerChartTag.cs — tiny invisible marker indicator. Drop it on the ONE chart that
// is the real execution chart (the one you actually place orders from) for a given
// instrument. Built 2026-10-23 because window-TITLE matching (ClaudeTrackerAddOn's prior
// fix) got a real screenshot but from the WRONG window — NT8 titles every chart window
// "Chart - <Instrument.FullName>" after its active tab, so if more than one open chart
// happens to have that instrument active (a second analysis chart, a different timeframe,
// etc.), title text alone can't tell which one is the trading chart. This can: on load it
// registers its own ChartControl into ClaudeTrackerChartRegistry (NinjaTrader.NinjaScript
// namespace, shared across the Custom.dll assembly) keyed by instrument full name, and
// ClaudeTrackerAddOn checks that registry FIRST before ever falling back to title matching.
// Only ONE chart per instrument should carry this tag — if dropped on more than one, the
// last one to reach State.DataLoaded wins (simple overwrite, not a list), so pick the real
// execution chart deliberately, not every chart showing that instrument.
namespace NinjaTrader.NinjaScript.Indicators
{
    public class ClaudeTrackerChartTag : Indicator
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "ClaudeTracker Chart Tag";
                Description = "Marks THIS chart as the execution chart for ClaudeTrackerAddOn screenshots. "
                    + "Drop on the one chart you actually trade from, not every chart showing this instrument.";
                IsOverlay = true;
                IsChartOnly = true;
                DrawOnPricePanel = false;
                IsSuspendedWhileInactive = false;
                Calculate = NinjaTrader.NinjaScript.Calculate.OnBarClose;
            }
            else if (State == State.DataLoaded)
            {
                if (ChartControl != null && Instrument != null)
                    ClaudeTrackerChartRegistry.Register(Instrument.FullName, ChartControl);
            }
            else if (State == State.Terminated)
            {
                if (Instrument != null)
                    ClaudeTrackerChartRegistry.Unregister(Instrument.FullName, ChartControl);
            }
        }

        protected override void OnBarUpdate() { }
    }
}
