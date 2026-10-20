#region Using declarations
using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
#endregion

// ─────────────────────────────────────────────────────────────────────────────
// PATsChartButtons — two small chart-toolbar utility buttons, independent of
// PATsProfile (VP-specific buttons live there; these two are unrelated concerns
// so they get their own file). Pattern: chartWindow.MainMenu.Add(button), same
// technique as nt8/vendor/ab/MyABToolbarButtons.cs and the now-deleted
// ClaudeTrackerHealthLight.cs.
//
//   CT status light : green/red reflecting whether the ClaudeTrackerV2 STRATEGY
//                      is currently enabled on this chart. Read from
//                      ChartControl.Strategies (NOT ChartObjects -- that only
//                      holds indicators), matched by Name == "ClaudeTrackerV2",
//                      "enabled" = found AND State != State.Terminated. This
//                      logic is correct whichever way NT8 handles a disabled
//                      instance (removed from the collection vs kept with
//                      State.Terminated) -- both resolve to red. Deliberately
//                      does NOT infer health/correctness (that's what got the
//                      old ClaudeTrackerHealthLight deleted for false "green"
//                      reassurance) -- this only reflects the literal
//                      enabled/disabled checkbox state, nothing more. Refreshes
//                      every 10s and on click.
//   VWAP toggle      : shows/hides the Lizard Trader "LT_Current_Day_VWAP"
//                      indicator on this chart, matched by its .NET type name
//                      (known with certainty from the generated NT8 wrapper),
//                      not by its display Name string (unverifiable -- the
//                      vendor's assembly is obfuscated, the display name isn't
//                      present as plain text anywhere discoverable).
//
// Commit CS to: repo/nt8/indicators/PATsChartButtons.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsChartButtons : Indicator
	{
		private const string ClaudeTrackerStrategyName = "ClaudeTrackerV2";
		private const string LizardVwapTypeFullName = "NinjaTrader.NinjaScript.Indicators.LizardTrader.LT_Current_Day_VWAP";

		private Chart chartWindow;
		private bool toolbarAdded;
		private Button btnCtStatus, btnVwapToggle;
		private DispatcherTimer statusTimer;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "PATs Chart Buttons";
				Description = "Chart-toolbar utility buttons: ClaudeTrackerV2 enabled/disabled status light, Lizard Trader Daily VWAP show/hide.";
				IsOverlay = true; IsChartOnly = true; DrawOnPricePanel = false; IsSuspendedWhileInactive = false;
				Calculate = Calculate.OnBarClose;
			}
			else if (State == State.Realtime)
			{
				if (ChartControl != null && !toolbarAdded)
					ChartControl.Dispatcher.InvokeAsync((Action)(() => AddButtons()));
			}
			else if (State == State.Terminated)
			{
				if (chartWindow != null)
					ChartControl.Dispatcher.InvokeAsync((Action)(() => RemoveButtons()));
			}
		}

		protected override void OnBarUpdate() { }
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale) { }

		private void AddButtons()
		{
			chartWindow = Window.GetWindow(ChartControl.Parent) as Chart;
			if (chartWindow == null || chartWindow.MainMenu == null) return;

			Style btnStyle = new Style(typeof(Button));
			btnStyle.Setters.Add(new Setter(Button.FontSizeProperty, 12.0));
			btnStyle.Setters.Add(new Setter(Button.FontWeightProperty, FontWeights.Bold));
			btnStyle.Setters.Add(new Setter(Button.MarginProperty, new Thickness(2, 0, 2, 0)));
			btnStyle.Setters.Add(new Setter(Button.PaddingProperty, new Thickness(4, 2, 4, 2)));
			btnStyle.Setters.Add(new Setter(Button.HorizontalAlignmentProperty, HorizontalAlignment.Center));

			btnCtStatus = new Button { Content = "CT ?", Style = btnStyle, Background = Brushes.Gray, Foreground = Brushes.White, Visibility = Visibility.Visible };
			btnCtStatus.Click += (s, e) => RefreshCtStatus();

			btnVwapToggle = new Button { Content = "VWAP", Style = btnStyle, Background = Brushes.LightGray, Foreground = Brushes.Blue, Visibility = Visibility.Visible };
			btnVwapToggle.Click += (s, e) => ToggleLizardVwap();

			chartWindow.MainMenu.Add(btnCtStatus);
			chartWindow.MainMenu.Add(btnVwapToggle);
			toolbarAdded = true;

			RefreshCtStatus();
			statusTimer = new DispatcherTimer(DispatcherPriority.Background, chartWindow.Dispatcher);
			statusTimer.Interval = TimeSpan.FromSeconds(10);
			statusTimer.Tick += (s, e) => RefreshCtStatus();
			statusTimer.Start();
		}

		// Literal enabled/disabled reflection only -- no health/correctness inference.
		private void RefreshCtStatus()
		{
			if (chartWindow == null || btnCtStatus == null || chartWindow.ActiveChartControl == null) return;
			bool enabled = false;
			try
			{
				foreach (NinjaTrader.NinjaScript.Strategies.Strategy strat in chartWindow.ActiveChartControl.Strategies)
				{
					if (strat != null && strat.Name == ClaudeTrackerStrategyName && strat.State != State.Terminated)
					{
						enabled = true;
						break;
					}
				}
			}
			catch { enabled = false; }
			btnCtStatus.Background = enabled ? Brushes.Green : Brushes.Red;
			btnCtStatus.Content = enabled ? "CT ON" : "CT OFF";
		}

		private void ToggleLizardVwap()
		{
			if (chartWindow == null || chartWindow.ActiveChartControl == null) return;
			foreach (object obj in chartWindow.ActiveChartControl.ChartObjects)
			{
				Indicator indi = obj as Indicator;
				if (indi != null && indi.GetType().FullName == LizardVwapTypeFullName)
					indi.IsVisible = !indi.IsVisible;
			}
			chartWindow.ActiveChartControl.InvalidateVisual();
			ForceRefresh();
		}

		private void RemoveButtons()
		{
			if (statusTimer != null) statusTimer.Stop();
			if (chartWindow == null) return;
			if (btnCtStatus != null) chartWindow.MainMenu.Remove(btnCtStatus);
			if (btnVwapToggle != null) chartWindow.MainMenu.Remove(btnVwapToggle);
			toolbarAdded = false;
		}
	}
}
