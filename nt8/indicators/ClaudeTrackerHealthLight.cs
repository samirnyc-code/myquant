#region Using declarations
using System;
using System.IO;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// ClaudeTrackerHealthLight — a small, separate traffic-light indicator reading
// ClaudeTrackerV2.cs's own ClaudeTracker_Health.json. Deliberately its own
// indicator, not drawing code added back into ClaudeTrackerV2.cs itself: that
// strategy already has documented history of a severe NT8-wide lag incident
// from chart-drawing code (burning per-event annotations onto screenshots,
// one new object per event, never cleared — see JournalApp.tsx's comment on
// this in the trade-playbook repo). This is a fundamentally different shape —
// ONE reused Draw.TextFixed tag, updated in place every ~15s, never a second
// object created — but keeping it in a separate file means it can never touch
// ClaudeTrackerV2's own execution/order-handling code even by accident, and
// can be removed/disabled independently if it ever turns out to be a problem.
//
// GREEN  health file fresh, status "ok"
// AMBER  self-corrected a drift this session (worth noticing even though it
//        healed itself), OR health file is a little stale
// RED    health file missing/very stale during market hours — the self-check
//        loop itself may have stopped (frozen/crashed strategy)
// GREY   no trade folder yet today / outside market hours — nothing expected

namespace NinjaTrader.NinjaScript.Indicators
{
    public class ClaudeTrackerHealthLight : Indicator
    {
        private DateTime lastCheck = DateTime.MinValue;
        private static readonly TimeSpan CheckInterval = TimeSpan.FromSeconds(15);

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "ClaudeTrackerHealthLight";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportRootFolder = @"G:\My Drive\!NT Tracker Export";
            }
        }

        protected override void OnBarUpdate()
        {
            if (State != State.Realtime) return;
            DateTime now = Core.Globals.Now;
            if (now - lastCheck < CheckInterval) return;
            lastCheck = now;
            Render(now);
        }

        private void Render(DateTime now)
        {
            string instrumentFolder = Instrument.FullName.Contains("MES") ? "MES" : "ES";
            string path = Path.Combine(ExportRootFolder, instrumentFolder,
                now.ToString("yyyy-MM-dd"), "ClaudeTracker_Health.json");

            Brush color;
            string label;

            if (!File.Exists(path))
            {
                bool marketLikelyOpen = now.DayOfWeek != DayOfWeek.Saturday
                    && !(now.DayOfWeek == DayOfWeek.Sunday && now.Hour < 17);
                color = marketLikelyOpen ? Brushes.Gray : Brushes.DimGray;
                label = "CT: no health file yet";
            }
            else
            {
                double ageSec = (now - File.GetLastWriteTime(path)).TotalSeconds;
                string status = ExtractJsonField(File.ReadAllText(path), "status");

                if (ageSec > 300)
                {
                    color = Brushes.Red;
                    label = "CT: STALE " + (ageSec / 60.0).ToString("F0") + "m — self-check stopped?";
                }
                else if (status.StartsWith("drift_"))
                {
                    color = Brushes.Orange;
                    label = "CT: recovered a drift (" + status + ")";
                }
                else if (ageSec > 90)
                {
                    color = Brushes.Orange;
                    label = "CT: health file " + ageSec.ToString("F0") + "s old";
                }
                else
                {
                    color = Brushes.LimeGreen;
                    label = "CT: OK";
                }
            }

            Draw.TextFixed(this, "ctHealthLight", "● " + label, TextPosition.TopRight,
                color, new SimpleFont("Consolas", 12),
                Brushes.DimGray, new SolidColorBrush(Color.FromArgb(200, 20, 24, 29)), 60);
        }

        // Minimal hand-rolled extraction, not a JSON library dependency — the
        // health file has a known flat shape (ClaudeTrackerV2.cs writes it),
        // this only ever needs one string field out of it.
        private string ExtractJsonField(string json, string field)
        {
            string needle = "\"" + field + "\":\"";
            int start = json.IndexOf(needle, StringComparison.Ordinal);
            if (start < 0) return "";
            start += needle.Length;
            int end = json.IndexOf("\"", start, StringComparison.Ordinal);
            return end > start ? json.Substring(start, end - start) : "";
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Export Root Folder", Order = 1, GroupName = "Parameters",
            Description = "Must match ClaudeTrackerV2's Export Root Folder setting.")]
        public string ExportRootFolder { get; set; }
        #endregion
    }
}
