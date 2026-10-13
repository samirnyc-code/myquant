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
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
	// Lean stop-entry modes. Separate enum names from BreakoutBoysDashboardV1's
	// BBStopMode/BBTargetMode — both files share this namespace, duplicate enum
	// names would be a compile error.
	public enum BBLiteStopMode { BarStop, LastSwing }

	// Which of the four entry mechanisms a side is armed/active with.
	public enum BBEntryKind { StopGated, StopUngated, LmtPullback, LmtRetest }

	// ══════════════════════════════════════════════════════════════════════════
	// BreakoutBoysLiteV1 — lean chart-trader button panel, no ATM, no properties
	// dialog needed during the session. Four entry methods:
	//
	//   SE LONG / SE SHORT        : arm -> on the bar you armed in (the SB) CLOSING,
	//                               gate on IBS, then rest a genuine STOP-LIMIT
	//                               entry: stop TRIGGER at the SB's High (long) /
	//                               Low (short) + your OFFSET N ticks of
	//                               confirmation — price must actually trade back
	//                               through that level — with a small fixed LIMIT
	//                               cushion past the trigger (bounds slippage once
	//                               it fires; the fill can land anywhere between
	//                               trigger and that cushion, often right at the
	//                               trigger). IBS fails, or the trigger is already
	//                               stale (through current price) -> no order, popup.
	//                               Breakout/continuation: betting price keeps
	//                               moving the direction the SB already went.
	//   SE LONG 2nd / SE SHORT 2nd: identical entry, but skips the IBS gate — for
	//                               failed-first-attempt second entries.
	//   LMT L BB / LMT S SA       : plain LIMIT resting on the NEAR side of the SB
	//                               (SB Low - OFFSET long / SB High + OFFSET short)
	//                               — a same-bar pullback/fade, no IBS gate. Only
	//                               valid (non-marketable, won't fire instantly) if
	//                               the level is still on the correct side of the
	//                               last price — true by construction for the SB
	//                               you just armed in.
	//   LMT L ▲ / LMT S ▼         : plain LIMIT resting on the FAR side of the SB
	//                               instead (SB High + OFFSET long / SB Low -
	//                               OFFSET short) — a RETEST entry, only valid when
	//                               price has already moved past that level since
	//                               (almost always requires PICK SB on an older
	//                               bar — for the bar that just closed, this side
	//                               is still on the marketable side of price and
	//                               gets rejected, same staleness guard as above).
	//
	// IBS = (Close-Low)/(High-Low) on the SB. Momentum semantics: LONG needs
	// IBS >= threshold (strong close near the high); SHORT needs IBS <= 1-threshold
	// (weak close near the low).
	//
	// Stop: BarStop (SB extreme, walked left through inside bars, + offset) or
	// LastSwing (Swing indicator). Target: R-multiple of the stop-to-entry risk,
	// 0.5x-3x in 0.5 steps — shared by all three entry methods. STP mode / TGT R /
	// entry OFFSET / IBS threshold / BARS-alive are all mini sub-buttons
	// (left-click down, right-click up) — never requires opening the strategy's
	// Properties dialog.
	// ══════════════════════════════════════════════════════════════════════════
	public class BreakoutBoysLiteV1 : Strategy
	{
		// ── chart-trader panel state ────────────────────────────────────────
		private Grid   ctButtonsGrid;
		private bool   ctPanelActive;
		private int    ctBaseRowCount;
		private int    ctRowsAdded;

		private Button btnSELIbs, btnSESIbs, btnSEL2, btnSES2, btnLmtL, btnLmtS, btnLmtLUp, btnLmtSDn, btnPickSB, btnCancel, btnFlat, btnStpMode, btnRMult, btnOffset, btnIbs, btnBars;
		private bool   _mouseHooked;

		private Color  ColorOn, ColorOff, ColorArmed, ColorPick;

		// ── runtime state ────────────────────────────────────────────────────
		private const int StopLimitCushionTicks = 2; // fixed, not user-exposed: limit = trigger +/- this, just to bound slippage once the trigger fires

		private BBLiteStopMode _stopMode = BBLiteStopMode.BarStop;
		private double _rMult   = 1.0;   // target = risk * _rMult
		private int    _offsetTicks = 1; // stop-limit TRIGGER = SB High/Low +/- this many ticks (confirmation beyond the SB)
		private double _ibsThreshold = 0.50;
		private int    _maxBarsAlive = 1; // how many bars a still-unfilled entry order stays working before auto-cancel

		private bool   _pendingLong, _pendingShort;   // armed, waiting for the SB (armed bar) to close
		private BBEntryKind _pendingKind;              // which entry mechanism the pending arm uses
		private bool   _pickArmed;                     // next chart click selects the SB
		private int    _sbPickedBar = -1;              // absolute bar index of a manually-picked SB (-1 = none)
		private int    _armedBarIndex = -1;            // CurrentBar when the working entry order was submitted (-1 = none working)
		private int    _dir;                           // +1 long / -1 short for the open trade, 0 flat
		private BBEntryKind _activeKind;               // which entry mechanism the OPEN trade used
		private double _entryPx, _stopPx, _tgtPx;
		private Swing  _swing;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name         = "BreakoutBoysLiteV1";
				Description  = "Lean BreakoutBoys panel — SE LONG/SHORT (IBS-gated stop-limit) + SE LONG/SHORT 2nd (ungated stop-limit) + LMT L BB/S SA (pullback limit) + LMT L/S retest (far-side limit), bar/swing stop, R-multiple target.";
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
				ColorPick  = Color.FromRgb(0,   110, 200); // blue = pick mode
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

			ExpireStaleEntry();

			// SB = the manually-picked bar if one is set, else the bar that just closed.
			if ((_pendingLong || _pendingShort) && Position.MarketPosition == MarketPosition.Flat)
			{
				bool isLong  = _pendingLong;
				BBEntryKind kind = _pendingKind;
				int  sbAgo   = _sbPickedBar >= 0 ? Math.Max(0, CurrentBar - _sbPickedBar) : 0;
				bool hadPick = _sbPickedBar >= 0;
				_pendingLong = _pendingShort = false;
				_sbPickedBar = -1;
				if (hadPick) { try { RemoveDrawObject("BBLitePickSB"); } catch (Exception ex) { Print("BBLite remove marker: " + ex.Message); } }
				if (kind == BBEntryKind.LmtPullback || kind == BBEntryKind.LmtRetest) TryPlaceLimitEntry(isLong, kind, sbAgo);
				else                                                                 TryPlaceStopEntry(isLong, kind == BBEntryKind.StopGated, sbAgo);
				RefreshSEButtons();
			}
		}

		// Gate on IBS (if requested), then compute a genuine STOP-LIMIT entry off the
		// SB (sbAgo bars back — 0 = the bar that just closed, or a manually-picked
		// bar): a stop TRIGGER at the SB's own extreme (price must actually trade
		// back through it — this is what makes it a stop entry, not a chase) and a
		// LIMIT cap offset ticks past the trigger (bounds worst-case slippage once
		// triggered, same role a plain stop-market's slippage risk would otherwise
		// carry unbounded).
		private void TryPlaceStopEntry(bool isLong, bool useIbs, int sbAgo)
		{
			double range = High[sbAgo] - Low[sbAgo];
			double ibs = range > 0 ? (Close[sbAgo] - Low[sbAgo]) / range : 0.5;

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

			// TRIGGER = the SB extreme + your confirmation offset — price must
			// actually trade this far beyond the SB before the entry activates at
			// all (matches the original dashboard's stop-market convention, where
			// the offset defined the entry level itself). LIMIT = trigger + a small
			// fixed cushion, not user-exposed, purely to bound slippage once it
			// fires — it is NOT where you should expect the fill to land; the fill
			// can legitimately land anywhere between trigger and limit, often right
			// at the trigger.
			double triggerPx = isLong ? High[sbAgo] + _offsetTicks * tick : Low[sbAgo] - _offsetTicks * tick;
			double limitPx    = isLong ? triggerPx + StopLimitCushionTicks * tick : triggerPx - StopLimitCushionTicks * tick;

			// Guard against a stale SB (e.g. an old PICK SB bar price has already
			// moved through): the trigger must still be on the correct side of the
			// last traded price, or a stop order there would fire instantly — the
			// exact "disaster" a plain chase-limit produced before this fix.
			// >= / <= (not strict >/<): the default (non-picked) SB's own High/Low is
			// always >= / <= its own Close, so a bar that closed exactly at its
			// extreme (the strongest, most normal case) must still pass.
			double lastPx = Close[0];
			bool triggerValid = isLong ? triggerPx >= lastPx : triggerPx <= lastPx;
			if (!triggerValid)
			{
				string msg = "SE " + (isLong ? "LONG" : "SHORT") + " blocked — SB trigger " + triggerPx.ToString("0.00")
					+ " is already " + (isLong ? "below" : "above") + " the last price " + lastPx.ToString("0.00")
					+ " (stale SB) — would fire instantly, not a real stop entry.";
				Print(DateTime.Now + " " + msg);
				ShowPopup(msg);
				return;
			}

			_stopPx = ComputeStopLossPx(isLong, sbAgo);

			double risk = Math.Abs(limitPx - _stopPx);
			_entryPx = limitPx;   // intended (pre-fill) entry — the stop-limit's limit price, used for display + the OnExecutionUpdate recompute baseline
			_tgtPx   = isLong ? limitPx + risk * _rMult : limitPx - risk * _rMult;

			_dir = isLong ? 1 : -1;
			_activeKind = useIbs ? BBEntryKind.StopGated : BBEntryKind.StopUngated;
			_armedBarIndex = CurrentBar;

			// NinjaScript signature is (barsInProgressIndex, isLiveUntilCancelled,
			// quantity, limitPrice, stopPrice, signalName) — LIMIT before STOP
			// (verified via reflection on StrategyBase; the reversed price order
			// threw "Limit price can't be greater than stop price"). isLiveUntilCancelled
			// = true so NT8 doesn't auto-cancel this at the next bar close on its
			// own — ExpireStaleEntry() below now owns that via _maxBarsAlive instead.
			if (isLong) EnterLongStopLimit(0, true, SE_Qty, Round(limitPx), Round(triggerPx), "SE");
			else        EnterShortStopLimit(0, true, SE_Qty, Round(limitPx), Round(triggerPx), "SE");

			Print(DateTime.Now + "  SE " + (isLong ? "LONG" : "SHORT") + (useIbs ? "" : " 2nd") + " trigger@" + triggerPx.ToString("0.00")
				+ " limit@" + limitPx.ToString("0.00") + " stop@" + _stopPx.ToString("0.00") + " tgt@" + _tgtPx.ToString("0.00")
				+ " [" + _stopMode + "/" + _rMult.ToString("0.0") + "R, IBS " + ibs.ToString("0.00") + (useIbs ? " gated" : " ungated")
				+ ", alive " + _maxBarsAlive + " bar(s)]");
		}

		// NT8's default managed behavior auto-cancels an unfilled entry order at
		// the next bar close; isLiveUntilCancelled=true above opts out of that so
		// we can honor _maxBarsAlive instead (user-adjustable via the BARS button).
		private void ExpireStaleEntry()
		{
			if (_armedBarIndex < 0) return;
			if (CurrentBar - _armedBarIndex < _maxBarsAlive) return;

			bool hasLiveEntry = false;
			foreach (Order o in Orders) if (o.Name == "SE" && IsLive(o)) { hasLiveEntry = true; break; }
			_armedBarIndex = -1;
			if (!hasLiveEntry) return;   // already filled or otherwise resolved

			CancelWorkingEntries();
			_dir = 0;
			RefreshSEButtons();
			Print(DateTime.Now + " SE expired — unfilled after " + _maxBarsAlive + " bar(s), order cancelled");
		}

		// Plain LIMIT entry. Pullback: near side of the SB, same-bar dip/rip (SB Low
		// for longs / SB High for shorts) — valid by construction for the bar you
		// just armed in. Retest: far side instead (SB High for longs / SB Low for
		// shorts) — only valid once price has already moved past that level, which
		// in practice means PICK SB on an older bar. Either way: no IBS gate, and
		// the level must still be on the non-marketable side of the last price or
		// it would fire instantly (same staleness guard as the stop entries).
		private void TryPlaceLimitEntry(bool isLong, BBEntryKind kind, int sbAgo)
		{
			double tick = TickSize;
			bool pullback = kind == BBEntryKind.LmtPullback;
			double limitPx = isLong
				? (pullback ? Low[sbAgo] - _offsetTicks * tick : High[sbAgo] + _offsetTicks * tick)
				: (pullback ? High[sbAgo] + _offsetTicks * tick : Low[sbAgo] - _offsetTicks * tick);

			double lastPx = Close[0];
			bool valid = isLong ? limitPx <= lastPx : limitPx >= lastPx;
			if (!valid)
			{
				string msg = "LMT " + (isLong ? "LONG" : "SHORT") + (pullback ? "" : " (retest)") + " blocked — level " + limitPx.ToString("0.00")
					+ " is already " + (isLong ? "above" : "below") + " the last price " + lastPx.ToString("0.00")
					+ " (stale SB" + (pullback ? "" : " — retest needs PICK SB on a bar price has already moved past") + ") — would fire instantly, not a real limit entry.";
				Print(DateTime.Now + " " + msg);
				ShowPopup(msg);
				return;
			}

			_stopPx = ComputeStopLossPx(isLong, sbAgo);
			double risk = Math.Abs(limitPx - _stopPx);
			_entryPx = limitPx;
			_tgtPx   = isLong ? limitPx + risk * _rMult : limitPx - risk * _rMult;

			_dir = isLong ? 1 : -1;
			_activeKind = kind;
			_armedBarIndex = CurrentBar;

			if (isLong) EnterLongLimit (0, true, SE_Qty, Round(limitPx), "SE");
			else        EnterShortLimit(0, true, SE_Qty, Round(limitPx), "SE");

			Print(DateTime.Now + "  LMT " + (isLong ? "LONG" : "SHORT") + (pullback ? "" : " (retest)") + " @" + limitPx.ToString("0.00")
				+ " stop@" + _stopPx.ToString("0.00") + " tgt@" + _tgtPx.ToString("0.00")
				+ " [" + _stopMode + "/" + _rMult.ToString("0.0") + "R, alive " + _maxBarsAlive + " bar(s)]");
		}

		// STOP-LOSS reference (BarStop): the SB's OPPOSITE extreme, but if the SB is
		// an inside bar, walk LEFT to the first non-inside bar and use that. Shared
		// by all three entry methods.
		private double ComputeStopLossPx(bool isLong, int sbAgo)
		{
			double tick = TickSize;
			double stopRefHi = High[sbAgo], stopRefLo = Low[sbAgo];
			if (_stopMode == BBLiteStopMode.BarStop)
			{
				int a = sbAgo;
				while (a + 1 <= CurrentBar && High[a] <= High[a + 1] && Low[a] >= Low[a + 1])
					a++;
				stopRefHi = High[a]; stopRefLo = Low[a];
			}
			return isLong ? (_stopMode == BBLiteStopMode.LastSwing ? _swing.SwingLow[0]  : stopRefLo) - SE_StopOffsetTicks * tick
			              : (_stopMode == BBLiteStopMode.LastSwing ? _swing.SwingHigh[0] : stopRefHi) + SE_StopOffsetTicks * tick;
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
				// A marketable "chase" limit can fill at a better price than the
				// intended _entryPx (never worse — but never exactly on it either).
				// Recompute target off the REAL fill price so it stays a true
				// R-multiple of the ACTUAL risk, not the pre-fill estimate — stop
				// stays anchored to the SB structure, unaffected by fill price.
				double risk = Math.Abs(price - _stopPx);
				_tgtPx = Position.MarketPosition == MarketPosition.Long ? price + risk * _rMult : price - risk * _rMult;
				_tgtPx = Round(_tgtPx);

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
				Print(DateTime.Now + "  SE FILLED [" + _activeKind + "] " + Position.MarketPosition + " x" + quantity + " @ " + price.ToString("0.00")
					+ " (intended " + _entryPx.ToString("0.00") + ") — stop@" + _stopPx.ToString("0.00")
					+ " tgt@" + _tgtPx.ToString("0.00") + " [" + _rMult.ToString("0.0") + "R off real entry]");
				_armedBarIndex = -1;   // filled — no longer a working entry to expire
			}
		}

		// If the protective stop (SEstop) gets manually moved (e.g. dragged on the
		// chart) before IT fills, keep the target a true R-multiple of the new
		// risk: recompute off the real entry (Position.AveragePrice) and the
		// stop's new price, then move the resting SEtgt order to match. Only
		// reacts to orders still working — a filled/cancelled order can't be
		// "moved" and nothing downstream needs recalculating from it.
		protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity,
			int filled, double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment)
		{
			if (order == null || order.Name != "SEstop" || !IsLiveState(orderState)) return;

			double tick = TickSize;
			if (Math.Abs(stopPrice - _stopPx) < tick / 2) return;   // unchanged — including our own just-submitted price

			_stopPx = stopPrice;
			bool isLong = _dir == 1;
			double risk = Math.Abs(Position.AveragePrice - _stopPx);
			double newTgt = Round(isLong ? Position.AveragePrice + risk * _rMult : Position.AveragePrice - risk * _rMult);
			if (Math.Abs(newTgt - _tgtPx) < tick / 2) return;
			_tgtPx = newTgt;

			foreach (Order o in Orders)
			{
				if (o.Name == "SEtgt" && IsLive(o))
				{
					ChangeOrder(o, o.Quantity, _tgtPx, 0);
					Print(DateTime.Now + "  SE stop moved to " + _stopPx.ToString("0.00") + " -> target recalculated to "
						+ _tgtPx.ToString("0.00") + " [" + _rMult.ToString("0.0") + "R]");
					break;
				}
			}
		}

		protected override void OnPositionUpdate(Position position, double averagePrice,
			int quantity, MarketPosition marketPosition)
		{
			if (marketPosition == MarketPosition.Flat)
			{
				_dir = 0;
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
				btnSELIbs = MakeBtn(s, "SE LONG", "Arm a long stop-limit entry triggered at the SB High, gated on IBS", ColorOff);
				btnSELIbs.Click += (o, e) => TriggerCustomEvent(st => ArmSE(true, BBEntryKind.StopGated), null);
				btnSESIbs = MakeBtn(s, "SE SHORT", "Arm a short stop-limit entry triggered at the SB Low, gated on IBS", ColorOff);
				btnSESIbs.Click += (o, e) => TriggerCustomEvent(st => ArmSE(false, BBEntryKind.StopGated), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnSELIbs, btnSESIbs);

				// Row: SE LONG 2nd | SE SHORT 2nd (no IBS gate — failed-2nd-entry)
				btnSEL2 = MakeBtn(s, "SE LONG 2nd", "Same stop-limit long entry, no IBS gate — failed-second-entry", ColorOff);
				btnSEL2.Click += (o, e) => TriggerCustomEvent(st => ArmSE(true, BBEntryKind.StopUngated), null);
				btnSES2 = MakeBtn(s, "SE SHORT 2nd", "Same stop-limit short entry, no IBS gate — failed-second-entry", ColorOff);
				btnSES2.Click += (o, e) => TriggerCustomEvent(st => ArmSE(false, BBEntryKind.StopUngated), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnSEL2, btnSES2);

				// Row: LMT L BB | LMT S SA (plain limit, near side of the SB — same-bar pullback, no IBS)
				btnLmtL = MakeBtn(s, "LMT L BB", "Buy Below — limit resting below the SB Low, same-bar pullback, no IBS gate", ColorOff);
				btnLmtL.Click += (o, e) => TriggerCustomEvent(st => ArmSE(true, BBEntryKind.LmtPullback), null);
				btnLmtS = MakeBtn(s, "LMT S SA", "Sell Above — limit resting above the SB High, same-bar pullback, no IBS gate", ColorOff);
				btnLmtS.Click += (o, e) => TriggerCustomEvent(st => ArmSE(false, BBEntryKind.LmtPullback), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnLmtL, btnLmtS);

				// Row: LMT L ▲ | LMT S ▼ (plain limit, far side of the SB — retest, needs price to have already moved past; no IBS)
				btnLmtLUp = MakeBtn(s, "LMT L ▲", "Buy above the SB High — retest entry, needs price already past that level (usually PICK SB on an older bar), no IBS gate", ColorOff);
				btnLmtLUp.Click += (o, e) => TriggerCustomEvent(st => ArmSE(true, BBEntryKind.LmtRetest), null);
				btnLmtSDn = MakeBtn(s, "LMT S ▼", "Sell below the SB Low — retest entry, needs price already past that level (usually PICK SB on an older bar), no IBS gate", ColorOff);
				btnLmtSDn.Click += (o, e) => TriggerCustomEvent(st => ArmSE(false, BBEntryKind.LmtRetest), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnLmtLUp, btnLmtSDn);

				// Row: PICK SB | CANCEL
				btnPickSB = MakeBtn(s, "PICK SB", "Toggle, then click a bar to use it as the signal bar (overrides the default: the bar you armed in)", ColorOff);
				btnPickSB.Click += (o, e) => { _pickArmed = !_pickArmed; SetBtn(btnPickSB, _pickArmed ? ColorPick : ColorOff); Print(DateTime.Now + " PICK SB " + (_pickArmed ? "ON — click a bar" : "OFF")); };
				btnCancel = MakeBtn(s, "CANCEL", "Cancel working orders (entry + stop/target); leaves an open position", Color.FromRgb(120,90,20));
				btnCancel.Click += (o, e) => TriggerCustomEvent(st => CancelSEOrders(), null);
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnPickSB, btnCancel);

				// Row: FLATTEN ALL
				btnFlat = MakeBtn(s, "FLATTEN ALL", "Close this strategy's position + cancel all its orders", Color.FromRgb(150,30,30));
				btnFlat.Click += (o, e) => TriggerCustomEvent(st => FlattenSE(), null);
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnFlat);

				// Row: STP mode | TGT R-multiple (cycle / left-right adjust)
				btnStpMode = MakeBtn(s, "STP:" + _stopMode, "Cycle stop mode (BarStop / LastSwing)", Color.FromRgb(60,60,60));
				btnStpMode.Click += (o, e) => { _stopMode = _stopMode == BBLiteStopMode.BarStop ? BBLiteStopMode.LastSwing : BBLiteStopMode.BarStop; btnStpMode.Content = "STP:" + _stopMode; Print(DateTime.Now + " StopMode -> " + _stopMode); };
				btnRMult = MakeBtn(s, RMultLabel(), "Target R-multiple — left-click −0.5, right-click +0.5 (0.5x-3x)", Color.FromRgb(60,60,60));
				btnRMult.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustRMult(-1); };
				btnRMult.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustRMult(+1); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnStpMode, btnRMult);

				// Row: OFFSET (stop-limit trigger confirmation, ticks beyond the SB High/Low) | IBS threshold
				btnOffset = MakeBtn(s, OffsetLabel(), "Stop trigger confirmation ticks beyond the SB High (long) / Low (short) — left-click −1, right-click +1", Color.FromRgb(60,60,60));
				btnOffset.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustOffset(-1); };
				btnOffset.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustOffset(+1); };
				btnIbs = MakeBtn(s, IbsLabel(), "IBS threshold — left-click −0.05, right-click +0.05", Color.FromRgb(60,60,60));
				btnIbs.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustIbs(-1); };
				btnIbs.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustIbs(+1); };
				AddHalfRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnOffset, btnIbs);

				// Row: BARS (how long an unfilled entry order stays working before auto-cancel)
				btnBars = MakeBtn(s, BarsAliveLabel(), "Bars an unfilled entry stays working before auto-cancel — left-click −1, right-click +1", Color.FromRgb(60,60,60));
				btnBars.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; AdjustBarsAlive(-1); };
				btnBars.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; AdjustBarsAlive(+1); };
				AddFullRow(ctButtonsGrid, ctBaseRowCount + ctRowsAdded++, btnBars);

				if (!_mouseHooked) { ChartControl.PreviewMouseDown += OnChartMouseDown; _mouseHooked = true; }
				ctPanelActive = true;
			}
			catch (Exception ex) { Print("BBLite CreateWPFControls: " + ex.Message); }
		}

		private void ArmSE(bool isLong, BBEntryKind kind)
		{
			bool sameConfigActive = isLong
				? ((_pendingLong  && _pendingKind == kind) || (_dir == 1  && _activeKind == kind))
				: ((_pendingShort && _pendingKind == kind) || (_dir == -1 && _activeKind == kind));

			bool isLmt = kind == BBEntryKind.LmtPullback || kind == BBEntryKind.LmtRetest;
			string label = isLmt ? "LMT" : "SE";
			string tag   = kind == BBEntryKind.StopUngated ? " 2nd (no IBS gate)"
			             : kind == BBEntryKind.LmtRetest   ? " retest"
			             : "";

			if (sameConfigActive)
			{
				_pendingLong = _pendingShort = false;
				CancelWorkingEntries();
				RefreshSEButtons();
				Print(DateTime.Now + " " + label + " " + (isLong ? "LONG" : "SHORT") + tag + " disarmed");
				return;
			}
			if (Position.MarketPosition != MarketPosition.Flat)
			{ Print(DateTime.Now + " " + label + ": already in a trade — flatten first."); return; }

			_pendingLong = isLong; _pendingShort = !isLong; _pendingKind = kind;
			CancelWorkingEntries();
			if (_sbPickedBar >= 0) DrawPickMarker(_sbPickedBar, isLong);   // flip above/below once the side is known
			Print(DateTime.Now + " " + label + " " + (isLong ? "LONG" : "SHORT") + tag
				+ " armed — SB = " + (_sbPickedBar >= 0 ? "picked bar" : "the bar it closes on")
				+ " [" + _stopMode + "/" + _rMult.ToString("0.0") + "R]");
			RefreshSEButtons();
		}

		// Set all eight entry buttons from live state so colors can never drift out of sync.
		private void RefreshSEButtons()
		{
			bool longStopG  = (_pendingLong  && _pendingKind == BBEntryKind.StopGated)   || (_dir == 1  && _activeKind == BBEntryKind.StopGated);
			bool longStopU  = (_pendingLong  && _pendingKind == BBEntryKind.StopUngated) || (_dir == 1  && _activeKind == BBEntryKind.StopUngated);
			bool longLmtPb  = (_pendingLong  && _pendingKind == BBEntryKind.LmtPullback) || (_dir == 1  && _activeKind == BBEntryKind.LmtPullback);
			bool longLmtRt  = (_pendingLong  && _pendingKind == BBEntryKind.LmtRetest)   || (_dir == 1  && _activeKind == BBEntryKind.LmtRetest);
			bool shortStopG = (_pendingShort && _pendingKind == BBEntryKind.StopGated)   || (_dir == -1 && _activeKind == BBEntryKind.StopGated);
			bool shortStopU = (_pendingShort && _pendingKind == BBEntryKind.StopUngated) || (_dir == -1 && _activeKind == BBEntryKind.StopUngated);
			bool shortLmtPb = (_pendingShort && _pendingKind == BBEntryKind.LmtPullback) || (_dir == -1 && _activeKind == BBEntryKind.LmtPullback);
			bool shortLmtRt = (_pendingShort && _pendingKind == BBEntryKind.LmtRetest)   || (_dir == -1 && _activeKind == BBEntryKind.LmtRetest);
			SetBtn(btnSELIbs, longStopG  ? ColorArmed : ColorOff);
			SetBtn(btnSEL2,   longStopU  ? ColorArmed : ColorOff);
			SetBtn(btnLmtL,   longLmtPb  ? ColorArmed : ColorOff);
			SetBtn(btnLmtLUp, longLmtRt  ? ColorArmed : ColorOff);
			SetBtn(btnSESIbs, shortStopG ? ColorArmed : ColorOff);
			SetBtn(btnSES2,   shortStopU ? ColorArmed : ColorOff);
			SetBtn(btnLmtS,   shortLmtPb ? ColorArmed : ColorOff);
			SetBtn(btnLmtSDn, shortLmtRt ? ColorArmed : ColorOff);
		}

		private void OnChartMouseDown(object sender, MouseButtonEventArgs e)
		{
			if (!_pickArmed || ChartControl == null || ChartBars == null) return;
			try
			{
				// Coordinate must be relative to ChartControl (NOT ChartPanel) for
				// GetBarIdxByX to resolve.
				var pos = e.GetPosition(ChartControl);
				int idx = ChartBars.GetBarIdxByX(ChartControl, (int)pos.X);
				if (idx < 0 || idx > CurrentBar) { Print(DateTime.Now + " PICK SB: click off the bars (idx " + idx + ")"); return; }
				_sbPickedBar = idx;
				_pickArmed = false;
				SetBtn(btnPickSB, ColorOff);

				// Visual confirmation on the chart. If a side is already pending (armed
				// BEFORE picking — the reverse of the recommended order), honor it;
				// otherwise default to long-style until ArmSE flips it once a side is
				// actually chosen.
				DrawPickMarker(idx, !_pendingShort);

				Print(DateTime.Now + " SB picked @ bar " + idx + " (" + Time.GetValueAt(Math.Min(idx, CurrentBar)) + ")");
			}
			catch (Exception ex) { Print("BBLite pick: " + ex.Message); }
		}

		// Same tag every time, so re-drawing just moves the one marker rather than
		// littering old ones. Long: below the bar, pointing up. Short: above the
		// bar, pointing down — a below-bar marker reads as "buy here" regardless of
		// which side it's actually for, so it must flip for shorts.
		private void DrawPickMarker(int barIdx, bool isLong)
		{
			try
			{
				int barsAgo = Math.Max(0, CurrentBar - barIdx);
				double tick = TickSize;
				// Same tag does NOT swap an existing drawing object's tool type (an
				// ArrowUp stays an ArrowUp even if you re-call Draw with that tag as
				// ArrowDown) — it just repositions it. Remove first so the correct
				// shape actually gets (re)created. Separate try/catch so a failed
				// removal (e.g. nothing to remove yet) can never block the draw below.
				try { RemoveDrawObject("BBLitePickSB"); } catch { }

				Brush brush = new SolidColorBrush(ColorPick);   // blue regardless of direction
				if (isLong)
				{
					var a = Draw.ArrowUp(this, "BBLitePickSB", false, barsAgo, Low[barsAgo] - 2 * tick, brush);
					if (a != null) a.Size = ChartMarkerSize.Small;
					else Print(DateTime.Now + " BBLite pick marker: Draw.ArrowUp returned null");
				}
				else
				{
					var a = Draw.ArrowDown(this, "BBLitePickSB", false, barsAgo, High[barsAgo] + 2 * tick, brush);
					if (a != null) a.Size = ChartMarkerSize.Small;
					else Print(DateTime.Now + " BBLite pick marker: Draw.ArrowDown returned null");
				}
			}
			catch (Exception ex) { Print(DateTime.Now + " BBLite DrawPickMarker FAILED: " + ex); }
		}

		// Live (still-cancelable) order states. A resting LIMIT entry sits in
		// Accepted/Working until filled — both must be cancelable.
		private static bool IsLive(Order o) { return IsLiveState(o.OrderState); }

		private static bool IsLiveState(OrderState s)
		{
			switch (s)
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
			_armedBarIndex = -1;
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
			_dir = 0;
			RefreshSEButtons();
			Print(DateTime.Now + " SE FLATTEN ALL");
		}

		private string RMultLabel()     { return "TGT " + _rMult.ToString("0.0") + "R"; }
		private string OffsetLabel()    { return "OFS " + _offsetTicks + "t"; }
		private string IbsLabel()       { return "IBS " + _ibsThreshold.ToString("0.00"); }
		private string BarsAliveLabel() { return "BARS " + _maxBarsAlive; }

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

		private void AdjustBarsAlive(int dir)
		{
			_maxBarsAlive = Math.Max(1, Math.Min(50, _maxBarsAlive + dir));
			btnBars.Content = BarsAliveLabel();
			Print(DateTime.Now + " " + BarsAliveLabel());
		}

		private void DisposeWPFControls()
		{
			try
			{
				if (_mouseHooked && ChartControl != null) { ChartControl.PreviewMouseDown -= OnChartMouseDown; _mouseHooked = false; }
				try { RemoveDrawObject("BBLitePickSB"); } catch { }
				if (!ctPanelActive || ctButtonsGrid == null) return;
				int baseRows = Math.Max(0, ctBaseRowCount);
				while (ctButtonsGrid.Children.Count > baseRows)
					ctButtonsGrid.Children.RemoveAt(ctButtonsGrid.Children.Count - 1);
				while (ctButtonsGrid.RowDefinitions.Count > baseRows)
					ctButtonsGrid.RowDefinitions.RemoveAt(ctButtonsGrid.RowDefinitions.Count - 1);
				btnSELIbs = btnSESIbs = btnSEL2 = btnSES2 = btnLmtL = btnLmtS = btnLmtLUp = btnLmtSDn = btnPickSB = btnCancel = btnFlat = btnStpMode = btnRMult = btnOffset = btnIbs = btnBars = null;
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
