#region Using declarations
using System;
using System.IO;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Text.RegularExpressions;
using System.Windows.Media;
using System.Windows.Threading;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.Indicators;
#endregion

// ClaudeTrackerWatchdog — a SEPARATE script from ClaudeTrackerV2.cs on purpose.
// 2026-10-21/22: the user asked for "a very clear alert on my screen when the
// ClaudeTracker gets dropped/disabled." A Strategy can't reliably report its own
// death — once NT8 disables it (or it crashes, or the chart it's attached to
// closes), nothing of it is left running to draw a warning. This indicator reads
// the SAME heartbeat file ClaudeTrackerV2 already writes every ~30s
// (ClaudeTracker_Health.json) on an independent wall-clock timer — NOT tied to
// tick arrival, so it still alerts even if the data feed itself goes fully quiet
// — and is a totally separate NinjaScript instance, so it keeps running and
// alerting even if ClaudeTrackerV2 itself has stopped dead.
namespace NinjaTrader.NinjaScript.Indicators
{
    public class ClaudeTrackerWatchdog : Indicator
    {
        [NinjaScriptProperty]
        [Display(Name = "Export Root Folder", Order = 1, GroupName = "Parameters",
            Description = "Must match ClaudeTrackerV2's own Export Root Folder parameter — this is where its health file lives.")]
        public string ExportRootFolder { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Stale After Seconds", Order = 2, GroupName = "Parameters",
            Description = "If the heartbeat hasn't updated in this long, ClaudeTracker is treated as offline/disabled.")]
        public int StaleAfterSeconds { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Resound Alert Every Seconds", Order = 3, GroupName = "Parameters",
            Description = "While still offline, repeat the sound alert this often so it can't be missed/dismissed once.")]
        public int ResoundEverySeconds { get; set; }

        private DispatcherTimer checkTimer;
        private string watchStatus = "unknown"; // unknown | ok | gap | offline
        private DateTime lastAlertSoundAt = DateTime.MinValue;
        private static readonly Regex StatusRe    = new Regex("\"status\":\"([^\"]*)\"", RegexOptions.Compiled);
        private static readonly Regex DetailRe    = new Regex("\"detail\":\"([^\"]*)\"", RegexOptions.Compiled);
        private static readonly Regex CheckedAtRe = new Regex("\"checkedAt\":\"([^\"]*)\"", RegexOptions.Compiled);

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                 = "ClaudeTrackerWatchdog";
                Calculate            = Calculate.OnEachTick;
                IsOverlay            = true;
                ExportRootFolder     = @"G:\My Drive\!NT Tracker Export";
                StaleAfterSeconds    = 60;
                ResoundEverySeconds  = 120;
            }
            else if (State == State.Realtime)
            {
                if (ChartControl != null)
                {
                    ChartControl.Dispatcher.InvokeAsync(() =>
                    {
                        checkTimer = new DispatcherTimer(DispatcherPriority.Background, ChartControl.Dispatcher);
                        checkTimer.Interval = TimeSpan.FromSeconds(5);
                        checkTimer.Tick += (s, e) => CheckHealth();
                        checkTimer.Start();
                    });
                }
                CheckHealth(); // first check immediately, don't wait for the first tick
            }
            else if (State == State.Terminated)
            {
                if (checkTimer != null)
                {
                    DispatcherTimer t = checkTimer;
                    checkTimer = null;
                    if (ChartControl != null) ChartControl.Dispatcher.InvokeAsync(() => t.Stop());
                    else t.Stop();
                }
            }
        }

        protected override void OnBarUpdate() { } // all work happens on the wall-clock timer, not tick/bar flow

        private string HealthFilePath()
        {
            string instrumentFolder = Instrument != null && Instrument.FullName.Contains("MES") ? "MES" : "ES";
            string root = string.IsNullOrWhiteSpace(ExportRootFolder)
                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "NinjaTrader 8", "ClaudeTracker")
                : ExportRootFolder;
            string today = Core.Globals.Now.ToString("yyyy-MM-dd");
            return Path.Combine(root, instrumentFolder, today, "ClaudeTracker_Health.json");
        }

        private void CheckHealth()
        {
            try
            {
                string path = HealthFilePath();
                string newStatus;
                string message;

                if (!File.Exists(path))
                {
                    newStatus = "offline";
                    message = "⚠ CLAUDETRACKER OFFLINE ⚠\nNo heartbeat file found yet today — not recording trades.";
                }
                else
                {
                    string json = File.ReadAllText(path);
                    string status    = ExtractJson(StatusRe, json);
                    string detail    = ExtractJson(DetailRe, json);
                    string checkedAt= ExtractJson(CheckedAtRe, json);
                    DateTime checkedAtTime;
                    bool parsed = DateTime.TryParse(checkedAt, out checkedAtTime);
                    double ageSec = parsed ? (Core.Globals.Now - checkedAtTime).TotalSeconds : double.MaxValue;

                    if (!parsed || ageSec > StaleAfterSeconds)
                    {
                        newStatus = "offline";
                        message = "⚠ CLAUDETRACKER OFFLINE ⚠\nLast heartbeat " + (parsed ? Math.Round(ageSec).ToString() + "s ago" : "unreadable")
                            + " — not recording trades.\nCheck NT8 Output log / re-enable the strategy.";
                    }
                    else if (status == "gap_reconciled")
                    {
                        newStatus = "gap";
                        message = "⚠ CLAUDETRACKER RESUMED WITH AN UNVERIFIED GAP ⚠\n" + detail + "\nVerify this trade's fills/P&L manually.";
                    }
                    else
                    {
                        newStatus = "ok";
                        message = string.Empty;
                    }
                }

                bool becameBad = (newStatus == "offline" || newStatus == "gap") && watchStatus != newStatus;
                bool stillBad  = (newStatus == "offline" || newStatus == "gap")
                    && (Core.Globals.Now - lastAlertSoundAt).TotalSeconds >= ResoundEverySeconds;

                if (becameBad || stillBad)
                {
                    lastAlertSoundAt = Core.Globals.Now;
                    PlaySound(NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert2.wav");
                    Print("[ClaudeTrackerWatchdog] " + message.Replace("\n", " "));
                }

                watchStatus = newStatus;
                DrawBanner(newStatus, message);
            }
            catch (Exception ex) { Print("[ClaudeTrackerWatchdog] check failed: " + ex.Message); }
        }

        private void DrawBanner(string status, string message)
        {
            if (status == "ok")
            {
                RemoveDrawObject("ctw_banner");
                return;
            }
            Brush bg = status == "offline" ? Brushes.DarkRed : Brushes.DarkOrange;
            Draw.TextFixed(this, "ctw_banner", message, TextPosition.Center,
                Brushes.White, new SimpleFont("Arial", 20) { Bold = true }, Brushes.Black, bg, 90);
        }

        private string ExtractJson(Regex re, string json)
        {
            Match m = re.Match(json);
            return m.Success ? m.Groups[1].Value : string.Empty;
        }
    }
}
