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
        private bool loggedRegistered;

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
                // OnEachTick, not OnBarClose: the re-registration in OnBarUpdate below must not
                // wait for a bar to close. On a 2000-tick ES chart during low-volume ETH hours,
                // a single bar can take far longer than the time between trades — found
                // 2026-10-28 when a real trade's screenshot missed the tag because the chart's
                // only historical 2000-tick bar hadn't closed yet since load, so the "self-heal"
                // never got a chance to run even once.
                Calculate = NinjaTrader.NinjaScript.Calculate.OnEachTick;
            }
            else if (State == State.Historical || State == State.DataLoaded || State == State.Realtime)
            {
                TryRegister();
            }
            else if (State == State.Terminated)
            {
                if (Instrument != null)
                    ClaudeTrackerChartRegistry.Unregister(Instrument.FullName, ChartControl);
            }
        }

        // Belt-and-suspenders re-registration: the State.* hooks above can land before
        // ChartControl is populated (observed after an overnight session/historical-data
        // rollover — worked all day 2026-10-23, silently dead every day since because the
        // single DataLoaded attempt never retried). Re-registering on every tick is idempotent
        // (same key/value almost every call) and, unlike the old OnBarClose cadence, self-heals
        // within one real tick instead of waiting on a bar that may not close for a long time.
        protected override void OnBarUpdate()
        {
            TryRegister();
        }

        private void TryRegister()
        {
            if (ChartControl == null || Instrument == null) return;
            ClaudeTrackerChartRegistry.Register(Instrument.FullName, ChartControl);
            if (!loggedRegistered)
            {
                loggedRegistered = true;
                Print("[ClaudeTrackerChartTag] registered \"" + Instrument.FullName + "\" for screenshot targeting.");
            }
        }
    }
}
