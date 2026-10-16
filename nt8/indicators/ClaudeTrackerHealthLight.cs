#region Using declarations
using System;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
#endregion

// ClaudeTrackerHealthLight — a toolbar button (not a tiny on-chart text overlay)
// reading ClaudeTrackerV2.cs's ClaudeTracker_Health.json, injected directly into
// the chart window's own MainMenu toolbar — same proven technique as the
// installed "BAF IndicatorManagerUI" (BidAskFlow) indicator on this machine
// (Custom\Indicators\IndicatorManager.cs): get the Chart window via
// Window.GetWindow(ChartControl.Parent), add a WPF control to its MainMenu
// collection, self-heal on a timer in case the toolbar gets rebuilt.
//
// Deliberately its own indicator, not drawing code added back into
// ClaudeTrackerV2.cs itself — that strategy has documented history of a severe
// NT8-wide lag incident from chart-drawing code (trade-playbook's JournalApp.tsx
// has the postmortem). This never touches ClaudeTrackerV2's own code, and reads
// a file, not NinjaScript Draw.* calls.
//
// Click the button for the full detail (trades taken/recorded today, raw status
// text) — the toolbar button itself only has room for a color + short label.
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
        private const string BtnTag = "ClaudeTrackerHealthLight.MainMenuButton";

        private Chart chartWindow;
        private Button btn;
        private DispatcherTimer timer;
        private string lastStatus = "";
        private string lastDetail = "";
        private int tradesTaken = 0;
        private int tradesRecorded = 0;

        [NinjaScriptProperty]
        [Display(Name = "Export Root Folder", Order = 1, GroupName = "Parameters",
            Description = "Must match ClaudeTrackerV2's Export Root Folder setting.")]
        public string ExportRootFolder { get; set; }

        public override string DisplayName { get { return "ClaudeTrackerHealthLight"; } }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "ClaudeTrackerHealthLight";
                IsOverlay = true;
                IsSuspendedWhileInactive = false;
                ExportRootFolder = @"G:\My Drive\!NT Tracker Export";
            }
            else if (State == State.Historical)
            {
                if (ChartControl == null) return;
                ChartControl.Dispatcher.InvokeAsync(() =>
                {
                    chartWindow = Window.GetWindow(ChartControl.Parent) as Chart;
                    if (chartWindow == null) return;

                    EnsureButton();
                    Refresh();

                    timer = new DispatcherTimer(DispatcherPriority.Background, chartWindow.Dispatcher);
                    timer.Interval = TimeSpan.FromSeconds(15);
                    timer.Tick += Timer_Tick;
                    timer.Start();
                });
            }
            else if (State == State.Terminated)
            {
                if (chartWindow == null) return;
                chartWindow.Dispatcher.InvokeAsync(() =>
                {
                    if (timer != null) { timer.Tick -= Timer_Tick; timer.Stop(); timer = null; }
                    RemoveButton();
                    chartWindow = null;
                });
            }
        }

        protected override void OnBarUpdate() { /* no-op — the timer drives this, not bars */ }

        private void Timer_Tick(object sender, EventArgs e)
        {
            EnsureButton(); // self-heal: toolbars can be rebuilt
            Refresh();
        }

        private void EnsureButton()
        {
            if (chartWindow == null || chartWindow.MainMenu == null) return;

            var existing = chartWindow.MainMenu.OfType<Button>().FirstOrDefault(b => Equals(b.Tag, BtnTag));
            if (existing != null) { btn = existing; return; }

            foreach (var b in chartWindow.MainMenu.OfType<Button>().Where(x => Equals(x.Tag, BtnTag)).ToList())
                chartWindow.MainMenu.Remove(b);

            btn = new Button
            {
                Content = "CT",
                Tag = BtnTag,
                Width = 36,
                Height = 20,
                Padding = new Thickness(0),
                Margin = new Thickness(2, 0, 2, 0),
                FontSize = 12,
                FontWeight = FontWeights.SemiBold,
                HorizontalContentAlignment = HorizontalAlignment.Center,
                VerticalContentAlignment = VerticalAlignment.Center,
                Foreground = Brushes.White,
            };
            AutomationProperties.SetAutomationId(btn, BtnTag);
            btn.Click += OnButtonClick;

            chartWindow.MainMenu.Add(btn);
        }

        private void RemoveButton()
        {
            if (chartWindow == null || chartWindow.MainMenu == null) return;
            foreach (var b in chartWindow.MainMenu.OfType<Button>().Where(x => Equals(x.Tag, BtnTag)).ToList())
            {
                b.Click -= OnButtonClick;
                chartWindow.MainMenu.Remove(b);
            }
            btn = null;
        }

        // Reads the health file + counts today's trade folders (EntryStudy.csv present =
        // taken; sibling TradeSummary.csv present = recorded/closed). Same signature as
        // pipeline_health.py's stuck-open scan, reimplemented here so the toolbar button
        // doesn't need any other process running to show real numbers.
        private void Refresh()
        {
            if (btn == null) return;
            DateTime now = Core.Globals.Now;
            string instrumentFolder = Instrument.FullName.Contains("MES") ? "MES" : "ES";
            string dayDir = Path.Combine(ExportRootFolder, instrumentFolder, now.ToString("yyyy-MM-dd"));
            string healthPath = Path.Combine(dayDir, "ClaudeTracker_Health.json");

            Brush color;
            string status, detail;
            tradesTaken = 0; tradesRecorded = 0;

            if (Directory.Exists(dayDir))
            {
                foreach (var dir in Directory.GetDirectories(dayDir))
                {
                    if (Directory.GetFiles(dir, "*_EntryStudy.csv").Length == 0) continue;
                    tradesTaken++;
                    if (Directory.GetFiles(dir, "*_TradeSummary.csv").Length > 0) tradesRecorded++;
                }
            }

            if (!File.Exists(healthPath))
            {
                bool marketLikelyOpen = now.DayOfWeek != DayOfWeek.Saturday
                    && !(now.DayOfWeek == DayOfWeek.Sunday && now.Hour < 17);
                color = marketLikelyOpen ? Brushes.Gray : Brushes.DimGray;
                status = "no_file"; detail = "No health file yet today.";
            }
            else
            {
                double ageSec = (now - File.GetLastWriteTime(healthPath)).TotalSeconds;
                string json = File.ReadAllText(healthPath);
                status = ExtractJsonField(json, "status");
                string rawDetail = ExtractJsonField(json, "detail");

                if (ageSec > 300) { color = Brushes.Red; detail = "STALE " + (ageSec / 60.0).ToString("F0") + "m — self-check loop may have stopped. " + rawDetail; }
                else if (status.StartsWith("drift_")) { color = Brushes.Orange; detail = "Self-corrected a drift this session: " + rawDetail; }
                else if (ageSec > 90) { color = Brushes.Orange; detail = "Health file " + ageSec.ToString("F0") + "s old. " + rawDetail; }
                else { color = Brushes.LimeGreen; detail = rawDetail; }
            }

            if (status == lastStatus && detail == lastDetail) return; // avoid pointless UI churn
            lastStatus = status; lastDetail = detail;

            chartWindow.Dispatcher.InvokeAsync(() =>
            {
                btn.Background = color;
                btn.ToolTip = "ClaudeTracker: " + status + " — click for detail";
            });
        }

        private void OnButtonClick(object sender, RoutedEventArgs e)
        {
            if (chartWindow != null) chartWindow.Dispatcher.InvokeAsync(ShowMenu);
        }

        private void ShowMenu()
        {
            if (btn == null) return;
            var menu = new ContextMenu();

            menu.Items.Add(new MenuItem { Header = "Status: " + lastStatus, IsEnabled = false, FontWeight = FontWeights.Bold });
            menu.Items.Add(new MenuItem { Header = string.IsNullOrEmpty(lastDetail) ? "(no detail)" : lastDetail, IsEnabled = false });
            menu.Items.Add(new Separator());
            menu.Items.Add(new MenuItem { Header = "Trades taken today: " + tradesTaken, IsEnabled = false });
            menu.Items.Add(new MenuItem { Header = "Trades recorded (closed) today: " + tradesRecorded, IsEnabled = false });
            if (tradesTaken > tradesRecorded)
                menu.Items.Add(new MenuItem { Header = (tradesTaken - tradesRecorded) + " still open / unrecorded", IsEnabled = false, Foreground = Brushes.OrangeRed });
            menu.Items.Add(new Separator());
            var refreshItem = new MenuItem { Header = "Refresh now" };
            refreshItem.Click += (s, e) => { lastStatus = null; Refresh(); };
            menu.Items.Add(refreshItem);

            btn.ContextMenu = menu;
            menu.PlacementTarget = btn;
            menu.IsOpen = true;
        }

        // Minimal hand-rolled extraction, not a JSON library dependency — the health
        // file has a known flat shape (ClaudeTrackerV2.cs writes it), this only ever
        // needs a couple of string fields out of it.
        private string ExtractJsonField(string json, string field)
        {
            string needle = "\"" + field + "\":\"";
            int start = json.IndexOf(needle, StringComparison.Ordinal);
            if (start < 0) return "";
            start += needle.Length;
            int end = json.IndexOf("\"", start, StringComparison.Ordinal);
            return end > start ? json.Substring(start, end - start) : "";
        }
    }
}
