#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
	// ══════════════════════════════════════════════════════════════════════════
	// BreakoutBoysDashboardV1 — chart-trader button panel.
	// ══════════════════════════════════════════════════════════════════════════
	// Built fresh (NOT the MC channel dashboard). The MC MicroChannel indicator is
	// intentionally NOT used here — entries will be SB/wedge-based (added in later
	// increments). Reuses the proven chart-trader button-mount pattern from
	// MCStrategyDashboardV3 (FindFirst("ChartWindowChartTraderControl") -> button grid).
	//
	// INCREMENT 1 (this file): MASTER button only — arms/disarms the SEPARATE
	// WedgeScalperV2 strategy via the shared static WedgeScalperV2.MasterArmed
	// (both compile into NinjaTrader.Custom = same process). Green = armed.
	//
	// TODO (next increments): PICK SB (bar-select), STOP ENTRY L/S with stop modes
	// {BarStop, LastSwing} + target modes {Scalp, AbrMult, RMult}, then Speedo/Lmt.
	public class BreakoutBoysDashboardV1 : Strategy
	{
		// ── chart-trader panel state ────────────────────────────────────────
		private Grid   ctButtonsGrid;
		private bool   ctPanelActive;
		private int    ctBaseRowCount;
		private int    ctRowsAdded;
		private Button btnMaster;
		private Button btnLong;
		private Button btnShort;

		private Color  ColorOn;
		private Color  ColorOff;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name         = "BreakoutBoysDashboardV1";
				Description  = "Breakout Boys Dashboard v1 — chart-trader buttons (MASTER controls WedgeScalperV2)";
				Calculate    = Calculate.OnBarClose;
				IsUnmanaged  = false;
				IsExitOnSessionCloseStrategy = false;
				BarsRequiredToTrade = 1;

				ColorOn  = Color.FromRgb(0,  160, 0);
				ColorOff = Color.FromRgb(80, 80,  80);
			}
			else if (State == State.Historical)
			{
				if (ChartControl != null && !ctPanelActive)
					ChartControl.Dispatcher.InvokeAsync((Action)CreateWPFControls);
			}
			else if (State == State.Terminated)
			{
				if (ChartControl != null)
					ChartControl.Dispatcher.InvokeAsync((Action)DisposeWPFControls);
			}
		}

		protected override void OnBarUpdate() { /* no trading logic yet (button host) */ }

		// ── mount the panel into the Chart Trader button grid ───────────────
		private void CreateWPFControls()
		{
			if (ctPanelActive) return;
			try
			{
				var win = Window.GetWindow(ChartControl.Parent) as NinjaTrader.Gui.Chart.Chart;
				if (win == null) { Print("BB: chart window not found"); return; }
				var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
				if (chartTrader == null) { Print("BB: ChartTrader not found (is Chart Trader shown?)"); return; }
				var outerGrid = chartTrader.Content as Grid;
				if (outerGrid == null) return;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { ctButtonsGrid = g; break; }
				}
				if (ctButtonsGrid == null) { Print("BB: button grid not found"); return; }

				ctBaseRowCount = ctButtonsGrid.RowDefinitions.Count;
				ctRowsAdded    = 0;
				Style s = Application.Current.TryFindResource("Button") as Style;

				// Row 0: MASTER — arm/disarm WedgeScalperV2 entries
				btnMaster = MakeBtn(s, MasterLabel(), "Arm/disarm WedgeScalperV2 new entries", WedgeArmedColor());
				btnMaster.Click += (o, e) =>
				{
					WedgeScalperV2.MasterArmed = !WedgeScalperV2.MasterArmed;
					btnMaster.Content = MasterLabel();
					SetBtn(btnMaster, WedgeArmedColor());
					Print(DateTime.Now + " MASTER -> WedgeScalperV2 " + (WedgeScalperV2.MasterArmed ? "ARMED" : "DISARMED"));
				};
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded, btnMaster);
				ctRowsAdded++;

				// Row 1: LONG | SHORT — allow/deny each side on WedgeScalperV2
				btnLong = MakeBtn(s, "LONG", "Allow WedgeScalperV2 LONG entries", WedgeScalperV2.MasterAllowLong ? ColorOn : ColorOff);
				btnLong.Click += (o, e) =>
				{
					WedgeScalperV2.MasterAllowLong = !WedgeScalperV2.MasterAllowLong;
					SetBtn(btnLong, WedgeScalperV2.MasterAllowLong ? ColorOn : ColorOff);
					Print(DateTime.Now + " WedgeScalperV2 LONG " + (WedgeScalperV2.MasterAllowLong ? "ON" : "OFF"));
				};
				btnShort = MakeBtn(s, "SHORT", "Allow WedgeScalperV2 SHORT entries", WedgeScalperV2.MasterAllowShort ? ColorOn : ColorOff);
				btnShort.Click += (o, e) =>
				{
					WedgeScalperV2.MasterAllowShort = !WedgeScalperV2.MasterAllowShort;
					SetBtn(btnShort, WedgeScalperV2.MasterAllowShort ? ColorOn : ColorOff);
					Print(DateTime.Now + " WedgeScalperV2 SHORT " + (WedgeScalperV2.MasterAllowShort ? "ON" : "OFF"));
				};
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded, btnLong, btnShort);
				ctRowsAdded++;

				ctPanelActive = true;
			}
			catch (Exception ex) { Print("BB CreateWPFControls: " + ex.Message); }
		}

		private void DisposeWPFControls()
		{
			try
			{
				if (!ctPanelActive || ctButtonsGrid == null) return;
				int baseRows = Math.Max(0, ctBaseRowCount);
				while (ctButtonsGrid.Children.Count > baseRows)
					ctButtonsGrid.Children.RemoveAt(ctButtonsGrid.Children.Count - 1);
				while (ctButtonsGrid.RowDefinitions.Count > baseRows)
					ctButtonsGrid.RowDefinitions.RemoveAt(ctButtonsGrid.RowDefinitions.Count - 1);
				btnMaster = null; btnLong = null; btnShort = null;
				ctPanelActive = false;
			}
			catch (Exception ex) { Print("BB DisposeWPFControls: " + ex.Message); }
		}

		private string MasterLabel()  { return WedgeScalperV2.MasterArmed ? "WEDGE: ARMED" : "WEDGE: DISARMED"; }
		private Color  WedgeArmedColor() { return WedgeScalperV2.MasterArmed ? ColorOn : ColorOff; }

		// ── button helpers (from MCStrategyDashboardV3) ─────────────────────
		private Button MakeBtn(Style s, string label, string tip, Color bg, bool blackText = false)
		{
			return new Button() { Content = label, Style = s, Height = 36, Margin = new Thickness(1),
				FontSize = 13, FontWeight = FontWeights.Bold, ToolTip = tip,
				Background = new SolidColorBrush(bg),
				Foreground = blackText ? Brushes.Black : Brushes.White };
		}

		private void SetBtn(Button btn, Color bg, bool blackText = false)
		{
			if (btn == null || ChartControl == null) return;
			ChartControl.Dispatcher.InvokeAsync((Action)(() =>
			{
				if (btn == null) return;
				btn.Background = new SolidColorBrush(bg);
				btn.Foreground = blackText ? Brushes.Black : Brushes.White;
			}));
		}

		private void AddFullRow(Grid grid, int row, Button btn)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(38) });
			Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
			grid.Children.Add(btn);
		}

		private void AddHalfRow(Grid grid, int row, Button left, Button right)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(38) });
			var g = new Grid() { Margin = new Thickness(0) };
			g.ColumnDefinitions.Add(new ColumnDefinition());
			g.ColumnDefinitions.Add(new ColumnDefinition());
			Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
			g.Children.Add(left); g.Children.Add(right);
			Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
			grid.Children.Add(g);
		}
	}
}
