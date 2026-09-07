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
	// Stop-entry stop/target modes (fresh, wedge/SB based — NOT the MC channel modes).
	public enum BBStopMode   { BarStop, LastSwing }
	public enum BBTargetMode { Scalp, AbrMult, RMult, Atm }

	// ══════════════════════════════════════════════════════════════════════════
	// BreakoutBoysDashboardV1 — chart-trader button panel + SB stop-entry engine.
	// ══════════════════════════════════════════════════════════════════════════
	// Fresh build (no MC channel indicator). Reuses the proven chart-trader button
	// mount pattern from MCStrategyDashboardV3.
	//
	//   MASTER / LONG / SHORT : remote-control the SEPARATE WedgeScalperV2 via shared
	//                           statics (arm/disarm + side filter). MASTER refuses to
	//                           arm when no live WedgeScalperV2 instance exists.
	//   STOP ENTRY L / S      : this dashboard's OWN stop entry. Arm -> on the signal
	//                           bar's close, rest a stop 1t beyond the SB, enter next
	//                           bar. SB = the bar you armed in (default) or a PICK-SB
	//                           selected bar.
	//     STOP  = BarStop (1t beyond SB; IB -> walk left to first non-IB) or LastSwing.
	//     TGT   = Scalp (fixed ticks) / AbrMult (avg-bar-range(N) x mult) / RMult (x risk).
	public class BreakoutBoysDashboardV1 : Strategy
	{
		// ── chart-trader panel state ────────────────────────────────────────
		private NinjaTrader.Gui.Chart.ChartTrader _chartTrader;   // kept so we can read its ATM dropdown
		private Grid   ctButtonsGrid;
		private bool   ctPanelActive;
		private int    ctBaseRowCount;
		private int    ctRowsAdded;
		private bool   _mouseHooked;

		private Button btnMaster, btnLong, btnShort;
		private Button btnSEL, btnSES, btnPickSB, btnFlat, btnCancel, btnStpMode, btnTgtMode, btnTgtVal;

		private Color  ColorOn, ColorOff, ColorArmed, ColorPick;

		// ── stop-entry runtime state ────────────────────────────────────────
		private BBStopMode   _stopMode = BBStopMode.BarStop;
		private BBTargetMode _tgtMode  = BBTargetMode.Scalp;
		private bool   _pendingLong, _pendingShort;   // armed, waiting for SB close
		private bool   _pickArmed;                     // next chart click selects the SB
		private int    _sbPickedBar = -1;              // absolute bar index of a manually-picked SB (-1 = none)
		private int    _entryBar    = -1;
		private double _entryPx, _stopPx, _tgtPx;
		private int    _dir;                           // +1 long / -1 short for the working/open trade
		private Swing  _swing;

		// ── ATM-mode runtime state ──────────────────────────────────────────
		private string _cachedAtmTemplate = "";        // last ATM template read from the Chart Trader dropdown (UI thread)
		private string _atmId = "", _atmOrderId = "";  // active ATM strategy + entry-order ids
		private bool   _atmActive;                      // an ATM entry has been created and not yet closed
		private bool   _atmEntered;                     // the ATM has actually taken a position (for flat-detection)

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name         = "BreakoutBoysDashboardV1";
				Description  = "Breakout Boys Dashboard v1 — CT buttons: MASTER/LONG/SHORT steer WedgeScalperV2; STOP ENTRY L/S place SB stop entries";
				Calculate    = Calculate.OnBarClose;
				EntriesPerDirection = 1;
				EntryHandling = EntryHandling.AllEntries;
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds    = 30;
				BarsRequiredToTrade = 20;
				RealtimeErrorHandling = RealtimeErrorHandling.IgnoreAllErrors;

				// stop-entry settings
				SE_RestImmediately = true;   // rest the stop entry on arm (off last closed/picked bar); false = wait for the SB's close
				SE_AtmTemplate    = "";      // fallback ATM template name used only if the Chart Trader dropdown read is empty
				SE_Qty            = 1;
				SE_EntryOffsetTicks = 1;   // entry this many ticks beyond the SB
				SE_StopOffsetTicks  = 1;   // stop this many ticks beyond the stop-reference bar/swing
				SE_ScalpTicks     = 4;
				SE_AbrBars        = 8;
				SE_AbrMult        = 1.0;
				SE_RMult          = 1.0;
				SE_SwingStrength  = 3;

				ColorOn    = Color.FromRgb(0,   160, 0);
				ColorOff   = Color.FromRgb(80,  80,  80);
				ColorArmed = Color.FromRgb(200, 140, 0);   // amber = armed / waiting
				ColorPick  = Color.FromRgb(0,   110, 200); // blue = pick mode
			}
			else if (State == State.DataLoaded)
			{
				_swing = Swing(SE_SwingStrength);
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

			// Track an active ATM trade: clear our state once it has taken a position and gone flat again.
			if (_atmActive && !string.IsNullOrEmpty(_atmId))
			{
				MarketPosition amp = GetAtmStrategyMarketPosition(_atmId);
				if (amp != MarketPosition.Flat) _atmEntered = true;
				else if (_atmEntered)
				{ _atmActive = false; _atmEntered = false; _dir = 0; RefreshSEButtons(); Print(DateTime.Now + " SE ATM closed."); }
			}

			// Place a pending stop entry at the signal bar's close (deferred mode only —
			// in immediate mode the order is already resting from ArmStopEntry).
			if ((_pendingLong || _pendingShort) && !_atmActive && Position.MarketPosition == MarketPosition.Flat)
			{
				bool isLong = _pendingLong;
				int sbAgo = _sbPickedBar >= 0 ? Math.Max(0, CurrentBar - _sbPickedBar) : 0;
				PlaceStopEntry(isLong, sbAgo);
				_pendingLong = _pendingShort = false;
				_sbPickedBar = -1;
				RefreshSEButtons();
			}
		}

		// Compute entry/stop/target from the SB and rest the entry stop order.
		private void PlaceStopEntry(bool isLong, int sbAgo)
		{
			double tick = TickSize;
			double sbHi = High[sbAgo], sbLo = Low[sbAgo];

			// STOP reference bar (BarStop): 1t beyond the SB, but if the SB is an inside
			// bar, walk LEFT to the first non-inside bar and use that.
			double stopRefHi = sbHi, stopRefLo = sbLo;
			if (_stopMode == BBStopMode.BarStop)
			{
				int a = sbAgo;
				while (a + 1 <= CurrentBar && High[a] <= High[a + 1] && Low[a] >= Low[a + 1])
					a++;   // bar a is inside bar a+1 -> step left
				stopRefHi = High[a]; stopRefLo = Low[a];
			}

			if (isLong)
			{
				_dir = 1;
				_entryPx = sbHi + SE_EntryOffsetTicks * tick;
				_stopPx  = (_stopMode == BBStopMode.LastSwing ? _swing.SwingLow[0] : stopRefLo) - SE_StopOffsetTicks * tick;
			}
			else
			{
				_dir = -1;
				_entryPx = sbLo - SE_EntryOffsetTicks * tick;
				_stopPx  = (_stopMode == BBStopMode.LastSwing ? _swing.SwingHigh[0] : stopRefHi) + SE_StopOffsetTicks * tick;
			}

			// ── ATM MODE: hand the entry to a selected ATM template; it owns stop/target ──
			if (_tgtMode == BBTargetMode.Atm)
			{
				string tmpl = ResolveAtmTemplate();
				if (string.IsNullOrEmpty(tmpl))
				{ Print(DateTime.Now + " SE ATM: no ATM selected in Chart Trader and no fallback template set — entry aborted."); _dir = 0; return; }

				_atmOrderId = "SE_ORD_" + GetAtmStrategyUniqueId();
				_atmId      = "SE_ATM_" + GetAtmStrategyUniqueId();
				_atmActive  = true; _atmEntered = false;
				string tmplC = tmpl;
				AtmStrategyCreate(isLong ? OrderAction.Buy : OrderAction.Sell, OrderType.StopMarket,
					0, Round(_entryPx), TimeInForce.Day, _atmOrderId, tmpl, _atmId,
					(err, cbId) => Print(DateTime.Now + " SE ATM callback " + (err == ErrorCode.NoError ? "OK — template '" + tmplC + "'" : "FAILED: " + err)));
				Print(DateTime.Now + "  SE " + (isLong ? "LONG" : "SHORT") + " ATM entry@" + _entryPx.ToString("0.00")
					+ " template='" + tmpl + "'  (ATM owns stop/target)");
				return;
			}

			double risk = Math.Abs(_entryPx - _stopPx);
			double tgtDist;
			switch (_tgtMode)
			{
				case BBTargetMode.AbrMult: tgtDist = Abr(SE_AbrBars) * SE_AbrMult; break;
				case BBTargetMode.RMult:   tgtDist = risk * SE_RMult;             break;
				default:                   tgtDist = SE_ScalpTicks * tick;        break;   // Scalp
			}
			_tgtPx = isLong ? _entryPx + tgtDist : _entryPx - tgtDist;

			if (isLong) EnterLongStopMarket(SE_Qty, _entryPx, "SE");
			else        EnterShortStopMarket(SE_Qty, _entryPx, "SE");
			Print(DateTime.Now + "  SE " + (isLong ? "LONG" : "SHORT") + " entry@" + _entryPx.ToString("0.00")
				+ " stop@" + _stopPx.ToString("0.00") + " tgt@" + _tgtPx.ToString("0.00")
				+ " [" + _stopMode + "/" + _tgtMode + "]");
		}

		private double Round(double p) { return Instrument.MasterInstrument.RoundToTickSize(p); }

		// Resolve the ATM template name (safe on ANY thread): returns the last value
		// read from the Chart Trader dropdown on the UI thread, else the typed fallback.
		private string ResolveAtmTemplate()
		{
			return !string.IsNullOrEmpty(_cachedAtmTemplate) ? _cachedAtmTemplate : SE_AtmTemplate;
		}

		// UI-THREAD ONLY: walk the Chart Trader visual tree, read the selected ATM
		// template, cache it. Called from click handlers (which run on the UI thread).
		private string ReadAtmSelectorUi()
		{
			try
			{
				var sel = FindAtmSelector(_chartTrader);
				if (sel != null)
				{
					string name = AtmNameFrom(sel.SelectedAtmStrategy);
					if (!string.IsNullOrEmpty(name) && name != "Custom" && name != "<Custom>")
					{ _cachedAtmTemplate = name; return name; }
				}
				else Print(DateTime.Now + " BB ATM: Chart Trader ATM selector not found — will use fallback param '" + SE_AtmTemplate + "'.");
			}
			catch (Exception ex) { Print(DateTime.Now + " BB ATM read failed (" + ex.Message + ") — will use fallback param."); }
			return _cachedAtmTemplate;
		}

		// Extract a template-name string from whatever SelectedAtmStrategy returns
		// (may be a string, or an object exposing Template/Name/DisplayName).
		private string AtmNameFrom(object v)
		{
			if (v == null) return null;
			if (v is string) return (string)v;
			foreach (string prop in new[] { "Template", "Name", "DisplayName" })
			{
				var pi = v.GetType().GetProperty(prop);
				if (pi != null)
				{
					object pv = pi.GetValue(v, null);
					if (pv is string && !string.IsNullOrEmpty((string)pv)) return (string)pv;
				}
			}
			return v.ToString();
		}

		// Walk the Chart Trader visual tree for the ATM selector control.
		private NinjaTrader.Gui.NinjaScript.AtmStrategy.AtmStrategySelector FindAtmSelector(DependencyObject root)
		{
			if (root == null) return null;
			int n = System.Windows.Media.VisualTreeHelper.GetChildrenCount(root);
			for (int i = 0; i < n; i++)
			{
				var c = System.Windows.Media.VisualTreeHelper.GetChild(root, i);
				var s = c as NinjaTrader.Gui.NinjaScript.AtmStrategy.AtmStrategySelector;
				if (s != null) return s;
				var deep = FindAtmSelector(c);
				if (deep != null) return deep;
			}
			return null;
		}

		// Average bar range (High-Low) over the prior n bars (excludes the current bar).
		private double Abr(int n)
		{
			double sum = 0; int c = 0;
			for (int i = 1; i <= n && i <= CurrentBar; i++) { sum += High[i] - Low[i]; c++; }
			return c > 0 ? sum / c : 0;
		}

		protected override void OnExecutionUpdate(Execution execution, string executionId, double price,
			int quantity, MarketPosition marketPosition, string orderId, DateTime time)
		{
			if (execution.Order == null) return;
			if (_atmActive) return;   // ATM template manages its own stop/target
			if (execution.Order.Name == "SE" && Position.MarketPosition != MarketPosition.Flat)
			{
				_entryBar = CurrentBar;
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
				_dir = 0; _entryBar = -1;
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
				if (win == null) { Print("BB: chart window not found"); return; }
				var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
				if (chartTrader == null) { Print("BB: ChartTrader not found (is Chart Trader shown?)"); return; }
				_chartTrader = chartTrader;
				var outerGrid = chartTrader.Content as Grid;
				if (outerGrid == null) return;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { ctButtonsGrid = g; break; }
				}
				if (ctButtonsGrid == null) { Print("BB: button grid not found"); return; }

				ctBaseRowCount = ctButtonsGrid.RowDefinitions.Count;
				ctRowsAdded = 0;
				Style s = Application.Current.TryFindResource("Button") as Style;

				// Row: MASTER (arm/disarm WedgeScalperV2)
				btnMaster = MakeBtn(s, MasterLabel(), "Arm/disarm WedgeScalperV2 new entries", WedgeArmedColor());
				btnMaster.Click += (o, e) =>
				{
					if (!WedgeScalperV2.MasterArmed && WedgeScalperV2.LiveInstances <= 0)
					{ Print(DateTime.Now + " MASTER: no live WedgeScalperV2 to arm — add + enable it on a chart first."); return; }
					WedgeScalperV2.MasterArmed = !WedgeScalperV2.MasterArmed;
					btnMaster.Content = MasterLabel();
					SetBtn(btnMaster, WedgeArmedColor());
					Print(DateTime.Now + " MASTER -> WedgeScalperV2 " + (WedgeScalperV2.MasterArmed ? "ARMED" : "DISARMED"));
				};
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnMaster);

				// Row: LONG | SHORT (wedge side filter)
				btnLong  = MakeBtn(s, "LONG",  "Allow WedgeScalperV2 LONG entries",  WedgeScalperV2.MasterAllowLong  ? ColorOn : ColorOff);
				btnLong.Click += (o, e) => { WedgeScalperV2.MasterAllowLong = !WedgeScalperV2.MasterAllowLong; SetBtn(btnLong, WedgeScalperV2.MasterAllowLong ? ColorOn : ColorOff); Print(DateTime.Now + " Wedge LONG " + (WedgeScalperV2.MasterAllowLong ? "ON" : "OFF")); };
				btnShort = MakeBtn(s, "SHORT", "Allow WedgeScalperV2 SHORT entries", WedgeScalperV2.MasterAllowShort ? ColorOn : ColorOff);
				btnShort.Click += (o, e) => { WedgeScalperV2.MasterAllowShort = !WedgeScalperV2.MasterAllowShort; SetBtn(btnShort, WedgeScalperV2.MasterAllowShort ? ColorOn : ColorOff); Print(DateTime.Now + " Wedge SHORT " + (WedgeScalperV2.MasterAllowShort ? "ON" : "OFF")); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnLong, btnShort);

				// Row: STOP ENTRY L | STOP ENTRY S (this dashboard's own entries)
				btnSEL = MakeBtn(s, "STOP ENT L", "Arm a long stop entry off the SB", ColorOff);
				btnSEL.Click += (o, e) => { if (_tgtMode == BBTargetMode.Atm) ReadAtmSelectorUi(); TriggerCustomEvent(st => ArmStopEntry(true), null); };
				btnSES = MakeBtn(s, "STOP ENT S", "Arm a short stop entry off the SB", ColorOff);
				btnSES.Click += (o, e) => { if (_tgtMode == BBTargetMode.Atm) ReadAtmSelectorUi(); TriggerCustomEvent(st => ArmStopEntry(false), null); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnSEL, btnSES);

				// Row: PICK SB | CANCEL (cancel disarms + cancels working orders, keeps any open position)
				btnPickSB = MakeBtn(s, "PICK SB", "Toggle, then click a bar to use it as the signal bar", ColorOff);
				btnPickSB.Click += (o, e) => { _pickArmed = !_pickArmed; SetBtn(btnPickSB, _pickArmed ? ColorPick : ColorOff); Print(DateTime.Now + " PICK SB " + (_pickArmed ? "ON — click a bar" : "OFF")); };
				btnCancel = MakeBtn(s, "CANCEL", "Cancel the dashboard's working orders (entry + stop/target); leaves an open position", Color.FromRgb(120,90,20));
				btnCancel.Click += (o, e) => TriggerCustomEvent(st => CancelSEOrders(), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnPickSB, btnCancel);

				// Row: FLATTEN (close position + cancel all)
				btnFlat = MakeBtn(s, "FLATTEN", "Close the dashboard's SE position + cancel its orders", Color.FromRgb(150,30,30));
				btnFlat.Click += (o, e) => TriggerCustomEvent(st => FlattenSE(), null);
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnFlat);

				// Row: STP mode | TGT mode (cycle)
				btnStpMode = MakeBtn(s, "STP:" + _stopMode, "Cycle stop mode (BarStop / LastSwing)", Color.FromRgb(60,60,60));
				btnStpMode.Click += (o, e) => { _stopMode = _stopMode == BBStopMode.BarStop ? BBStopMode.LastSwing : BBStopMode.BarStop; btnStpMode.Content = "STP:" + _stopMode; Print(DateTime.Now + " StopMode -> " + _stopMode); };
				btnTgtMode = MakeBtn(s, "TGT:" + _tgtMode, "Cycle target mode (Scalp / AbrMult / RMult)", Color.FromRgb(60,60,60));
				btnTgtMode.Click += (o, e) => { _tgtMode = (BBTargetMode)(((int)_tgtMode + 1) % 4); btnTgtMode.Content = "TGT:" + _tgtMode; if (btnTgtVal != null) btnTgtVal.Content = TgtValLabel(); Print(DateTime.Now + " TargetMode -> " + _tgtMode); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnStpMode, btnTgtMode);

				// Row: TGT value adjust (left-click = down, right-click = up; adapts to target mode)
				btnTgtVal = MakeBtn(s, TgtValLabel(), "Target value — left-click −, right-click +", Color.FromRgb(60,60,60));
				btnTgtVal.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustTgtVal(-1); };
				btnTgtVal.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustTgtVal(+1); };
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnTgtVal);

				if (!_mouseHooked) { ChartControl.PreviewMouseDown += OnChartMouseDown; _mouseHooked = true; }
				ctPanelActive = true;
			}
			catch (Exception ex) { Print("BB CreateWPFControls: " + ex.Message); }
		}

		private void ArmStopEntry(bool isLong)
		{
			bool sameSideActive = isLong ? (_pendingLong || _dir == 1) : (_pendingShort || _dir == -1);

			// Clicking the side that is already armed/working = disarm it.
			if (sameSideActive)
			{
				_pendingLong = _pendingShort = false;
				CancelWorkingEntries();
				CancelAtmIfActive();
				RefreshSEButtons();
				Print(DateTime.Now + " SE " + (isLong ? "LONG" : "SHORT") + " disarmed");
				return;
			}
			if (Position.MarketPosition != MarketPosition.Flat || _atmActive)
			{ Print(DateTime.Now + " SE: already in a trade — flatten first."); return; }

			// Mutually exclusive: arming one side clears the other + any stale entry.
			_pendingLong = isLong; _pendingShort = !isLong;
			CancelWorkingEntries();

			if (SE_RestImmediately)
			{
				// Rest the stop entry NOW off the last completed bar (or picked bar) —
				// no waiting for another bar close.
				int sbAgo = _sbPickedBar >= 0 ? Math.Max(0, CurrentBar - _sbPickedBar) : 0;
				PlaceStopEntry(isLong, sbAgo);
				_pendingLong = _pendingShort = false;
				_sbPickedBar = -1;
			}
			else
			{
				Print(DateTime.Now + " SE " + (isLong ? "LONG" : "SHORT") + " armed — SB = "
					+ (_sbPickedBar >= 0 ? "picked bar" : "the bar it closes on") + " [" + _stopMode + "/" + _tgtMode + "]");
			}
			RefreshSEButtons();
		}

		// Set both SE buttons from the live state so colors can never drift out of sync.
		private void RefreshSEButtons()
		{
			SetBtn(btnSEL, (_pendingLong  || _dir == 1)  ? ColorArmed : ColorOff);
			SetBtn(btnSES, (_pendingShort || _dir == -1) ? ColorArmed : ColorOff);
		}

		private void CancelWorkingEntries()
		{
			foreach (Order o in Orders)
				if (o.Name == "SE" && o.OrderState == OrderState.Working) CancelOrder(o);
		}

		// Close/cancel an active ATM trade (position -> close; resting entry -> cancel).
		private void CancelAtmIfActive()
		{
			if (!_atmActive || string.IsNullOrEmpty(_atmId)) return;
			try
			{
				MarketPosition amp = GetAtmStrategyMarketPosition(_atmId);
				if (amp != MarketPosition.Flat) AtmStrategyClose(_atmId);
				else if (!string.IsNullOrEmpty(_atmOrderId)) AtmStrategyCancelEntryOrder(_atmOrderId);
				Print(DateTime.Now + " SE ATM cancelled/closed (" + amp + ")");
			}
			catch (Exception ex) { Print(DateTime.Now + " BB ATM cancel: " + ex.Message); }
			_atmActive = false; _atmEntered = false;
		}

		// Cancel working dashboard orders (entry + stop/target) but leave an open position alone.
		private void CancelSEOrders()
		{
			foreach (Order o in Orders)
				if ((o.Name == "SE" || o.Name == "SEstop" || o.Name == "SEtgt") && o.OrderState == OrderState.Working)
					CancelOrder(o);
			CancelAtmIfActive();
			_pendingLong = _pendingShort = false;
			RefreshSEButtons();
			Print(DateTime.Now + " SE CANCEL — working orders cancelled (position kept)");
		}

		private void FlattenSE()
		{
			foreach (Order o in Orders)
				if ((o.Name == "SE" || o.Name == "SEstop" || o.Name == "SEtgt") && o.OrderState == OrderState.Working)
					CancelOrder(o);
			CancelAtmIfActive();
			_pendingLong = _pendingShort = false;
			if (Position.MarketPosition == MarketPosition.Long)  ExitLong ("SEflat", "SE");
			else if (Position.MarketPosition == MarketPosition.Short) ExitShort("SEflat", "SE");
			_dir = 0;
			SetBtn(btnSEL, ColorOff); SetBtn(btnSES, ColorOff);
			Print(DateTime.Now + " SE FLATTEN");
		}

		private string TgtValLabel()
		{
			switch (_tgtMode)
			{
				case BBTargetMode.AbrMult: return "TGT " + SE_AbrMult.ToString("0.0") + "xABR";
				case BBTargetMode.RMult:   return "TGT " + SE_RMult.ToString("0.0") + "R";
				case BBTargetMode.Atm:     { string t = ReadAtmSelectorUi(); if (string.IsNullOrEmpty(t)) t = SE_AtmTemplate; return "ATM: " + (string.IsNullOrEmpty(t) ? "(none)" : t); }
				default:                   return "TGT " + SE_ScalpTicks + "t";
			}
		}

		private void AdjustTgtVal(int dir)
		{
			switch (_tgtMode)
			{
				case BBTargetMode.Atm:     { string t = ReadAtmSelectorUi(); if (string.IsNullOrEmpty(t)) t = SE_AtmTemplate; Print(DateTime.Now + " ATM template resolves to: '" + (t ?? "") + "'"); if (btnTgtVal != null) btnTgtVal.Content = TgtValLabel(); break; }   // click just re-reads/prints
				case BBTargetMode.AbrMult: SE_AbrMult = Math.Max(0.1, Math.Round(SE_AbrMult + dir * 0.1, 1)); break;
				case BBTargetMode.RMult:   SE_RMult   = Math.Max(0.1, Math.Round(SE_RMult   + dir * 0.1, 1)); break;
				default:                   SE_ScalpTicks = Math.Max(1, SE_ScalpTicks + dir);                  break;
			}
			if (btnTgtVal != null) btnTgtVal.Content = TgtValLabel();
			Print(DateTime.Now + " " + TgtValLabel());
		}

		private void OnChartMouseDown(object sender, MouseButtonEventArgs e)
		{
			if (!_pickArmed || ChartControl == null || ChartBars == null) return;
			try
			{
				// Coordinate must be relative to ChartControl (NOT ChartPanel) for
				// GetBarIdxByX to resolve — this was the PICK-SB bug.
				var pos = e.GetPosition(ChartControl);
				int idx = ChartBars.GetBarIdxByX(ChartControl, (int)pos.X);
				if (idx < 0 || idx > CurrentBar) { Print(DateTime.Now + " PICK SB: click off the bars (idx " + idx + ")"); return; }
				_sbPickedBar = idx;
				_pickArmed = false;
				SetBtn(btnPickSB, ColorOff);
				Print(DateTime.Now + " SB picked @ bar " + idx + " (" + Time.GetValueAt(Math.Min(idx, CurrentBar)) + ")");
			}
			catch (Exception ex) { Print("BB pick: " + ex.Message); }
		}

		private void DisposeWPFControls()
		{
			try
			{
				if (_mouseHooked && ChartControl != null) { ChartControl.PreviewMouseDown -= OnChartMouseDown; _mouseHooked = false; }
				if (!ctPanelActive || ctButtonsGrid == null) return;
				int baseRows = Math.Max(0, ctBaseRowCount);
				while (ctButtonsGrid.Children.Count > baseRows)
					ctButtonsGrid.Children.RemoveAt(ctButtonsGrid.Children.Count - 1);
				while (ctButtonsGrid.RowDefinitions.Count > baseRows)
					ctButtonsGrid.RowDefinitions.RemoveAt(ctButtonsGrid.RowDefinitions.Count - 1);
				btnMaster = btnLong = btnShort = btnSEL = btnSES = btnPickSB = btnFlat = btnCancel = btnStpMode = btnTgtMode = btnTgtVal = null;
				_chartTrader = null;
				ctPanelActive = false;
			}
			catch (Exception ex) { Print("BB DisposeWPFControls: " + ex.Message); }
		}

		private string MasterLabel()     { return WedgeScalperV2.MasterArmed ? "WEDGE: ARMED" : "WEDGE: DISARMED"; }
		private Color  WedgeArmedColor() { return WedgeScalperV2.MasterArmed ? ColorOn : ColorOff; }

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
		[NinjaScriptProperty]
		[Display(Name = "Rest entry immediately on arm", GroupName = "Stop Entry", Order = 0)]
		public bool SE_RestImmediately { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ATM template (fallback if dropdown empty)", GroupName = "Stop Entry", Order = 9)]
		public string SE_AtmTemplate { get; set; }

		[NinjaScriptProperty, Range(1, 100)]
		[Display(Name = "Contracts", GroupName = "Stop Entry", Order = 1)]
		public int SE_Qty { get; set; }

		[NinjaScriptProperty, Range(1, 100)]
		[Display(Name = "Entry offset (ticks beyond SB)", GroupName = "Stop Entry", Order = 1)]
		public int SE_EntryOffsetTicks { get; set; }

		[NinjaScriptProperty, Range(0, 100)]
		[Display(Name = "Stop offset (ticks beyond ref)", GroupName = "Stop Entry", Order = 2)]
		public int SE_StopOffsetTicks { get; set; }

		[NinjaScriptProperty, Range(1, 1000)]
		[Display(Name = "Scalp target (ticks)", GroupName = "Stop Entry", Order = 3)]
		public int SE_ScalpTicks { get; set; }

		[NinjaScriptProperty, Range(1, 500)]
		[Display(Name = "ABR bars", GroupName = "Stop Entry", Order = 4)]
		public int SE_AbrBars { get; set; }

		[NinjaScriptProperty, Range(0.1, 20)]
		[Display(Name = "ABR multiple", GroupName = "Stop Entry", Order = 5)]
		public double SE_AbrMult { get; set; }

		[NinjaScriptProperty, Range(0.1, 20)]
		[Display(Name = "R multiple", GroupName = "Stop Entry", Order = 6)]
		public double SE_RMult { get; set; }

		[NinjaScriptProperty, Range(1, 50)]
		[Display(Name = "Swing strength", GroupName = "Stop Entry", Order = 7)]
		public int SE_SwingStrength { get; set; }
		#endregion
	}
}
