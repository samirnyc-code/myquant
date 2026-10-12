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
using NinjaTrader.NinjaScript.Indicators;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
	// Lean stop-entry modes. Separate enum names from BreakoutBoysDashboardV1's
	// BBStopMode/BBTargetMode — both files share this namespace, duplicate enum
	// names would be a compile error.
	public enum BBLiteStopMode { BarStop, LastSwing }

	// ══════════════════════════════════════════════════════════════════════════
	// BreakoutBoysLiteV1 — lean chart-trader button panel, no ATM, no properties
	// dialog needed during the session. Two entry methods only:
	//
	//   SE LONG / SE SHORT        : arm -> on the bar you armed in (the SB) CLOSING,
	//                               gate on IBS, then rest a LIMIT entry offset N
	//                               ticks beyond that close (chase — a marketable-
	//                               limit with a capped max-slippage, not a resting
	//                               pullback order). IBS fails -> no order, popup.
	//   SE LONG 2nd / SE SHORT 2nd: identical entry, but skips the IBS gate — for
	//                               failed-first-attempt second entries.
	//
	// IBS = (Close-Low)/(High-Low) on the SB. Momentum semantics: LONG needs
	// IBS >= threshold (strong close near the high); SHORT needs IBS <= 1-threshold
	// (weak close near the low).
	//
	// Stop: BarStop (SB extreme, walked left through inside bars, + offset) or
	// LastSwing (Swing indicator). Target: R-multiple of the stop-to-entry risk,
	// 0.5x-3x in 0.5 steps. All four of STP mode / TGT R / entry OFFSET / IBS
	// threshold are mini sub-buttons (left-click down, right-click up) — never
	// requires opening the strategy's Properties dialog.
	// ══════════════════════════════════════════════════════════════════════════
	public class BreakoutBoysLiteV1 : Strategy
	{
		// ── chart-trader panel state ────────────────────────────────────────
		private Grid   ctButtonsGrid;
		private bool   ctPanelActive;
		private int    ctBaseRowCount;
		private int    ctRowsAdded;

		private Button btnSELIbs, btnSESIbs, btnSEL2, btnSES2, btnCancel, btnFlat, btnStpMode, btnRMult, btnOffset, btnIbs;

		private Color  ColorOn, ColorOff, ColorArmed;

		// ── runtime state ────────────────────────────────────────────────────
		private BBLiteStopMode _stopMode = BBLiteStopMode.BarStop;
		private double _rMult   = 1.0;   // target = risk * _rMult
		private int    _offsetTicks = 1; // entry = Close +/- this many ticks
		private double _ibsThreshold = 0.50;

		private bool   _pendingLong, _pendingShort;   // armed, waiting for the SB (armed bar) to close
		private bool   _pendingUseIbs;                 // whether the pending arm gates on IBS
		private int    _dir;                           // +1 long / -1 short for the open trade, 0 flat
		private bool   _activeUseIbs;                   // whether the OPEN trade's entry used the IBS gate
		private double _entryPx, _stopPx, _tgtPx;
		private Swing  _swing;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name         = "BreakoutBoysLiteV1";
				Description  = "Lean BreakoutBoys panel — SE LONG/SHORT (IBS-gated) + SE LONG/SHORT 2nd (no gate), limit entry offset from Close, bar/swing stop, R-multiple target.";
				Calculate    = Calculate.OnBarClose;
				EntriesPerDirection = 1;
				EntryHandling = EntryHandling.AllEntries;
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds    = 30;
				BarsRequiredToTrade = 20;
				RealtimeErrorHandling = RealtimeErrorHandling.IgnoreAllErrors;

				SE_Qty             = 1;
				SE_StopOffsetTicks = 1;   // ticks beyond the stop reference bar/swing

				ColorOn    = Color.FromRgb(0,   160, 0);
				ColorOff   = Color.FromRgb(80,  80,  80);
				ColorArmed = Color.FromRgb(200, 140, 0);   // amber = armed / waiting on SB close
			}
			else if (State == State.DataLoaded)
			{
				_swing = Swing(3);
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

		protected override void OnBarUpdate()
		{
			if (CurrentBar < BarsRequiredToTrade) return;

			// The bar that just closed (bar 0) is the SB for whichever side is pending.
			if ((_pendingLong || _pendingShort) && Position.MarketPosition == MarketPosition.Flat)
			{
				bool isLong  = _pendingLong;
				bool useIbs  = _pendingUseIbs;
				_pendingLong = _pendingShort = false;
				TryPlaceStopEntry(isLong, useIbs);
				RefreshSEButtons();
			}
		}

		// Gate on IBS (if requested), then compute entry/stop/target off the SB
		// (bar 0 = the bar that just closed) and rest a limit entry.
		private void TryPlaceStopEntry(bool isLong, bool useIbs)
		{
			double range = High[0] - Low[0];
			double ibs = range > 0 ? (Close[0] - Low[0]) / range : 0.5;

			if (useIbs)
			{
				bool pass = isLong ? ibs >= _ibsThreshold : ibs <= (1.0 - _ibsThreshold);
				if (!pass)
				{
					string need = isLong ? (">= " + _ibsThreshold.ToString("0.00")) : ("<= " + (1.0 - _ibsThreshold).ToString("0.00"));
					string msg = "SE " + (isLong ? "LONG" : "SHORT") + " blocked — SB IBS " + ibs.ToString("0.00") + " does not meet " + need;
					Print(DateTime.Now + " " + msg);
					ShowPopup(msg);
					return;
				}
			}

			double tick = TickSize;

			// STOP reference (BarStop): the SB's extreme, but if the SB is an inside
			// bar, walk LEFT to the first non-inside bar and use that.
			double stopRefHi = High[0], stopRefLo = Low[0];
			if (_stopMode == BBLiteStopMode.BarStop)
			{
				int a = 0;
				while (a + 1 <= CurrentBar && High[a] <= High[a + 1] && Low[a] >= Low[a + 1])
					a++;
				stopRefHi = High[a]; stopRefLo = Low[a];
			}

			if (isLong)
			{
				_entryPx = Close[0] + _offsetTicks * tick;
				_stopPx  = (_stopMode == BBLiteStopMode.LastSwing ? _swing.SwingLow[0] : stopRefLo) - SE_StopOffsetTicks * tick;
			}
			else
			{
				_entryPx = Close[0] - _offsetTicks * tick;
				_stopPx  = (_stopMode == BBLiteStopMode.LastSwing ? _swing.SwingHigh[0] : stopRefHi) + SE_StopOffsetTicks * tick;
			}

			double risk = Math.Abs(_entryPx - _stopPx);
			_tgtPx = isLong ? _entryPx + risk * _rMult : _entryPx - risk * _rMult;

			_dir = isLong ? 1 : -1;
			_activeUseIbs = useIbs;

			if (isLong) EnterLongLimit(SE_Qty, Round(_entryPx), "SE");
			else        EnterShortLimit(SE_Qty, Round(_entryPx), "SE");

			Print(DateTime.Now + "  SE " + (isLong ? "LONG" : "SHORT") + (useIbs ? "" : " 2nd") + " entry@" + _entryPx.ToString("0.00")
				+ " stop@" + _stopPx.ToString("0.00") + " tgt@" + _tgtPx.ToString("0.00")
				+ " [" + _stopMode + "/" + _rMult.ToString("0.0") + "R, IBS " + ibs.ToString("0.00") + (useIbs ? " gated" : " ungated") + "]");
		}

		private double Round(double p) { return Instrument.MasterInstrument.RoundToTickSize(p); }

		// UI-thread popup explaining why no order was placed.
		private void ShowPopup(string msg)
		{
			if (ChartControl == null) return;
			ChartControl.Dispatcher.InvokeAsync((Action)(() =>
			{
				MessageBox.Show(msg, "BreakoutBoys Lite — entry blocked", MessageBoxButton.OK, MessageBoxImage.Warning);
			}));
		}

		protected override void OnExecutionUpdate(Execution execution, string executionId, double price,
			int quantity, MarketPosition marketPosition, string orderId, DateTime time)
		{
			if (execution.Order == null) return;
			if (execution.Order.Name == "SE" && Position.MarketPosition != MarketPosition.Flat)
			{
				if (Position.MarketPosition == MarketPosition.Long)
				{
					ExitLongStopMarket(0, true, Position.Quantity, _stopPx, "SEstop", "SE");
					ExitLongLimit     (0, true, Position.Quantity, _tgtPx,  "SEtgt",  "SE");
				}
				else
				{
					ExitShortStopMarket(0, true, Position.Quantity, _stopPx, "SEstop", "SE");
					ExitShortLimit     (0, true, Position.Quantity, _tgtPx,  "SEtgt",  "SE");
				}
				Print(DateTime.Now + "  SE FILLED " + Position.MarketPosition + " x" + quantity + " @ " + price.ToString("0.00"));
			}
		}

		protected override void OnPositionUpdate(Position position, double averagePrice,
			int quantity, MarketPosition marketPosition)
		{
			if (marketPosition == MarketPosition.Flat)
			{
				_dir = 0; _activeUseIbs = false;
				RefreshSEButtons();
			}
		}

		// ══════════════════════ Chart Trader panel ══════════════════════════
		private void CreateWPFControls()
		{
			if (ctPanelActive) return;
			try
			{
				var win = Window.GetWindow(ChartControl.Parent) as NinjaTrader.Gui.Chart.Chart;
				if (win == null) { Print("BBLite: chart window not found"); return; }
				var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
				if (chartTrader == null) { Print("BBLite: ChartTrader not found (is Chart Trader shown?)"); return; }
				var outerGrid = chartTrader.Content as Grid;
				if (outerGrid == null) return;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { ctButtonsGrid = g; break; }
				}
				if (ctButtonsGrid == null) { Print("BBLite: button grid not found"); return; }

				ctBaseRowCount = ctButtonsGrid.RowDefinitions.Count;
				ctRowsAdded = 0;
				Style s = Application.Current.TryFindResource("Button") as Style;

				// Row: title
				var title = new Button() { Content = "BB LITE", Style = s, Height = 22, Margin = new Thickness(1),
					FontSize = 11, FontWeight = FontWeights.Bold, IsHitTestVisible = false,
					Background = new SolidColorBrush(Color.FromRgb(30,30,30)), Foreground = Brushes.Gray };
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, title);

				// Row: SE LONG | SE SHORT (IBS-gated)
				btnSELIbs = MakeBtn(s, "SE LONG", "Arm a long limit entry off the SB close, gated on IBS", ColorOff);
				btnSELIbs.Click += (o, e) => TriggerCustomEvent(st => ArmSE(true, true), null);
				btnSESIbs = MakeBtn(s, "SE SHORT", "Arm a short limit entry off the SB close, gated on IBS", ColorOff);
				btnSESIbs.Click += (o, e) => TriggerCustomEvent(st => ArmSE(false, true), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnSELIbs, btnSESIbs);

				// Row: SE LONG 2nd | SE SHORT 2nd (no IBS gate — failed-2nd-entry)
				btnSEL2 = MakeBtn(s, "SE LONG 2nd", "Same long entry, no IBS gate — failed-second-entry", ColorOff);
				btnSEL2.Click += (o, e) => TriggerCustomEvent(st => ArmSE(true, false), null);
				btnSES2 = MakeBtn(s, "SE SHORT 2nd", "Same short entry, no IBS gate — failed-second-entry", ColorOff);
				btnSES2.Click += (o, e) => TriggerCustomEvent(st => ArmSE(false, false), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnSEL2, btnSES2);

				// Row: CANCEL | FLATTEN ALL
				btnCancel = MakeBtn(s, "CANCEL", "Cancel working orders (entry + stop/target); leaves an open position", Color.FromRgb(120,90,20));
				btnCancel.Click += (o, e) => TriggerCustomEvent(st => CancelSEOrders(), null);
				btnFlat = MakeBtn(s, "FLATTEN ALL", "Close this strategy's position + cancel all its orders", Color.FromRgb(150,30,30));
				btnFlat.Click += (o, e) => TriggerCustomEvent(st => FlattenSE(), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnCancel, btnFlat);

				// Row: STP mode | TGT R-multiple (cycle / left-right adjust)
				btnStpMode = MakeBtn(s, "STP:" + _stopMode, "Cycle stop mode (BarStop / LastSwing)", Color.FromRgb(60,60,60));
				btnStpMode.Click += (o, e) => { _stopMode = _stopMode == BBLiteStopMode.BarStop ? BBLiteStopMode.LastSwing : BBLiteStopMode.BarStop; btnStpMode.Content = "STP:" + _stopMode; Print(DateTime.Now + " StopMode -> " + _stopMode); };
				btnRMult = MakeBtn(s, RMultLabel(), "Target R-multiple — left-click −0.5, right-click +0.5 (0.5x-3x)", Color.FromRgb(60,60,60));
				btnRMult.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustRMult(-1); };
				btnRMult.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustRMult(+1); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnStpMode, btnRMult);

				// Row: OFFSET (entry ticks off Close) | IBS threshold
				btnOffset = MakeBtn(s, OffsetLabel(), "Entry offset ticks off Close — left-click −1, right-click +1", Color.FromRgb(60,60,60));
				btnOffset.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustOffset(-1); };
				btnOffset.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustOffset(+1); };
				btnIbs = MakeBtn(s, IbsLabel(), "IBS threshold — left-click −0.05, right-click +0.05", Color.FromRgb(60,60,60));
				btnIbs.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustIbs(-1); };
				btnIbs.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustIbs(+1); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnOffset, btnIbs);

				ctPanelActive = true;
			}
			catch (Exception ex) { Print("BBLite CreateWPFControls: " + ex.Message); }
		}

		private void ArmSE(bool isLong, bool useIbs)
		{
			bool sameConfigActive = isLong
				? ((_pendingLong  && _pendingUseIbs == useIbs) || (_dir == 1  && _activeUseIbs == useIbs))
				: ((_pendingShort && _pendingUseIbs == useIbs) || (_dir == -1 && _activeUseIbs == useIbs));

			if (sameConfigActive)
			{
				_pendingLong = _pendingShort = false;
				CancelWorkingEntries();
				RefreshSEButtons();
				Print(DateTime.Now + " SE " + (isLong ? "LONG" : "SHORT") + (useIbs ? "" : " 2nd") + " disarmed");
				return;
			}
			if (Position.MarketPosition != MarketPosition.Flat)
			{ Print(DateTime.Now + " SE: already in a trade — flatten first."); return; }

			_pendingLong = isLong; _pendingShort = !isLong; _pendingUseIbs = useIbs;
			CancelWorkingEntries();
			Print(DateTime.Now + " SE " + (isLong ? "LONG" : "SHORT") + (useIbs ? "" : " 2nd (no IBS gate)")
				+ " armed — SB = the bar it closes on [" + _stopMode + "/" + _rMult.ToString("0.0") + "R]");
			RefreshSEButtons();
		}

		// Set all four entry buttons from live state so colors can never drift out of sync.
		private void RefreshSEButtons()
		{
			bool longIbs  = (_pendingLong  && _pendingUseIbs)  || (_dir == 1  && _activeUseIbs);
			bool longNo   = (_pendingLong  && !_pendingUseIbs) || (_dir == 1  && !_activeUseIbs);
			bool shortIbs = (_pendingShort && _pendingUseIbs)  || (_dir == -1 && _activeUseIbs);
			bool shortNo  = (_pendingShort && !_pendingUseIbs) || (_dir == -1 && !_activeUseIbs);
			SetBtn(btnSELIbs, longIbs  ? ColorArmed : ColorOff);
			SetBtn(btnSEL2,   longNo   ? ColorArmed : ColorOff);
			SetBtn(btnSESIbs, shortIbs ? ColorArmed : ColorOff);
			SetBtn(btnSES2,   shortNo  ? ColorArmed : ColorOff);
		}

		// Live (still-cancelable) order states. A resting LIMIT entry sits in
		// Accepted/Working until filled — both must be cancelable.
		private static bool IsLive(Order o)
		{
			switch (o.OrderState)
			{
				case OrderState.Accepted:
				case OrderState.Working:
				case OrderState.Submitted:
				case OrderState.TriggerPending:
				case OrderState.PartFilled:
				case OrderState.ChangePending:
					return true;
				default:
					return false;
			}
		}

		private void CancelWorkingEntries()
		{
			foreach (Order o in Orders)
				if (o.Name == "SE" && IsLive(o)) CancelOrder(o);
		}

		// Cancel working orders (entry + stop/target) but leave an open position alone.
		private void CancelSEOrders()
		{
			foreach (Order o in Orders)
				if ((o.Name == "SE" || o.Name == "SEstop" || o.Name == "SEtgt") && IsLive(o))
					CancelOrder(o);
			_pendingLong = _pendingShort = false;
			RefreshSEButtons();
			Print(DateTime.Now + " SE CANCEL — working orders cancelled (position kept)");
		}

		private void FlattenSE()
		{
			foreach (Order o in Orders)
				if ((o.Name == "SE" || o.Name == "SEstop" || o.Name == "SEtgt") && IsLive(o))
					CancelOrder(o);
			_pendingLong = _pendingShort = false;
			if (Position.MarketPosition == MarketPosition.Long)       ExitLong ("SEflat", "SE");
			else if (Position.MarketPosition == MarketPosition.Short) ExitShort("SEflat", "SE");
			_dir = 0; _activeUseIbs = false;
			RefreshSEButtons();
			Print(DateTime.Now + " SE FLATTEN ALL");
		}

		private string RMultLabel()  { return "TGT " + _rMult.ToString("0.0") + "R"; }
		private string OffsetLabel() { return "OFS " + _offsetTicks + "t"; }
		private string IbsLabel()    { return "IBS " + _ibsThreshold.ToString("0.00"); }

		private void AdjustRMult(int dir)
		{
			_rMult = Math.Max(0.5, Math.Min(3.0, Math.Round(_rMult + dir * 0.5, 1)));
			btnRMult.Content = RMultLabel();
			Print(DateTime.Now + " " + RMultLabel());
		}

		private void AdjustOffset(int dir)
		{
			_offsetTicks = Math.Max(1, Math.Min(50, _offsetTicks + dir));
			btnOffset.Content = OffsetLabel();
			Print(DateTime.Now + " " + OffsetLabel());
		}

		private void AdjustIbs(int dir)
		{
			_ibsThreshold = Math.Max(0.05, Math.Min(0.95, Math.Round(_ibsThreshold + dir * 0.05, 2)));
			btnIbs.Content = IbsLabel();
			Print(DateTime.Now + " " + IbsLabel());
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
				btnSELIbs = btnSESIbs = btnSEL2 = btnSES2 = btnCancel = btnFlat = btnStpMode = btnRMult = btnOffset = btnIbs = null;
				ctPanelActive = false;
			}
			catch (Exception ex) { Print("BBLite DisposeWPFControls: " + ex.Message); }
		}

		private Button MakeBtn(Style s, string label, string tip, Color bg, bool blackText = false)
		{
			return new Button() { Content = label, Style = s, Height = 34, Margin = new Thickness(1),
				FontSize = 12, FontWeight = FontWeights.Bold, ToolTip = tip,
				Background = new SolidColorBrush(bg), Foreground = blackText ? Brushes.Black : Brushes.White };
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
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
			Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
			grid.Children.Add(btn);
		}

		private void AddHalfRow(Grid grid, int row, Button left, Button right)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
			var g = new Grid() { Margin = new Thickness(0) };
			g.ColumnDefinitions.Add(new ColumnDefinition());
			g.ColumnDefinitions.Add(new ColumnDefinition());
			Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
			g.Children.Add(left); g.Children.Add(right);
			Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
			grid.Children.Add(g);
		}

		#region Properties
		[NinjaScriptProperty, Range(1, 100)]
		[Display(Name = "Contracts", GroupName = "Stop Entry", Order = 0)]
		public int SE_Qty { get; set; }

		[NinjaScriptProperty, Range(0, 100)]
		[Display(Name = "Stop offset (ticks beyond ref)", GroupName = "Stop Entry", Order = 1)]
		public int SE_StopOffsetTicks { get; set; }
		#endregion
	}
}
