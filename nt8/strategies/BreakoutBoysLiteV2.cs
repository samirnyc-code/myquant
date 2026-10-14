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
	// BBLiteStopMode / BBEntryKind are declared in BreakoutBoysLiteV1.cs (same namespace), reused here.

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
	public class BreakoutBoysLiteV2 : Strategy
	{
		// ── chart-trader panel state (shared per window, routed to the active tab) ──
		private bool   ctPanelActive;
		private bool   _mouseHooked;        // PICK SB chart-click hook
		private Grid   _ctGrid;
		private System.Windows.Input.MouseEventHandler _ctEnter;   // tab-activation (mouse-enter) hook

		private static readonly Color ColorOn    = Color.FromRgb(0,   160, 0);
		private static readonly Color ColorOff   = Color.FromRgb(80,  80,  80);
		private static readonly Color ColorArmed = Color.FromRgb(200, 140, 0);   // amber = armed
		private static readonly Color ColorPick  = Color.FromRgb(0,   110, 200); // blue = pick mode

		// A chart WINDOW shares ONE Chart Trader across its tabs — build ONE button set per grid
		// and route each click to whichever chart tab is ACTIVE (set on mouse-enter). Only one
		// chart trades at a time, so this is purely which chart the panel drives.
		private sealed class CtShared
		{
			public BreakoutBoysLiteV2 active;
			public Button selIbs, sesIbs, sel2, ses2, lmtL, lmtS, lmtLUp, lmtSDn, pickSB, cancel, flat, stpMode, rMult, offset, ibs, bars;
			public List<RowDefinition> rds = new List<RowDefinition>();
			public List<UIElement> rows = new List<UIElement>();
			public int refs;
		}
		private static readonly Dictionary<Grid, CtShared> _ctByGrid = new Dictionary<Grid, CtShared>();

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
		private string _pickMarkerTag;                 // current pick-marker's draw tag (unique per draw — see DrawPickMarker)
		private int    _armedBarIndex = -1;            // CurrentBar when the working entry order was submitted (-1 = none working)
		private int    _dir;                           // +1 long / -1 short for the open trade, 0 flat
		private BBEntryKind _activeKind;               // which entry mechanism the OPEN trade used
		private double _entryPx, _stopPx, _tgtPx;
		private Swing  _swing;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name         = "BreakoutBoysLiteV2";
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
				_pendingLong = _pendingShort = false;
				_sbPickedBar = -1;   // pick consumed into sbAgo above — the MARKER itself stays
				                     // on the chart until the order resolves (fill/cancel/expire),
				                     // cleared in CancelWorkingEntries / OnExecutionUpdate instead.
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
			RefreshStatusText();

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
			RefreshStatusText();   // keep the N/M-bars countdown current every bar while working
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
			RefreshStatusText();

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

		// NON-BLOCKING "why no order was placed" notice. A modal MessageBox.Show here
		// froze the WHOLE platform (it blocks NT8's UI thread until dismissed, and can
		// open behind the chart) — so instead draw it as fixed on-chart text (plus the
		// Print the callers already do). Cleared on the next arm / fill / resolve.
		private void ShowPopup(string msg)
		{
			try { Draw.TextFixed(this, "BBLiteBlock", DateTime.Now.ToString("HH:mm:ss") + "  ⛔ " + msg, TextPosition.BottomRight); }
			catch (Exception ex) { Print("BBLite block notice: " + ex.Message); }
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
				ClearPickMarker();
				ClearStatusText();
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
				_ctGrid = null;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { _ctGrid = g; break; }
				}
				if (_ctGrid == null) { Print("BBLite: button grid not found"); return; }

				CtShared sh;
				if (!_ctByGrid.TryGetValue(_ctGrid, out sh)) { sh = BuildPanel(_ctGrid); _ctByGrid[_ctGrid] = sh; }
				sh.refs++;
				ShowPanel(sh, true);
				sh.active = this;
				SyncAll(sh, this);

				// Re-target the panel to whichever chart the mouse is over (tab switch in one window).
				_ctEnter = (o, e) => { CtShared ss; if (_ctGrid != null && _ctByGrid.TryGetValue(_ctGrid, out ss)) { ss.active = this; SyncAll(ss, this); } };
				ChartControl.MouseEnter += _ctEnter;
				if (!_mouseHooked) { ChartControl.PreviewMouseDown += OnChartMouseDown; _mouseHooked = true; }
				ctPanelActive = true;
			}
			catch (Exception ex) { Print("BBLite CreateWPFControls: " + ex.Message); }
		}

		// ONE shared button set per window grid. Every click routes to sh.active — the chart tab
		// whose chart the mouse last entered — and runs on THAT strategy's own thread.
		private CtShared BuildPanel(Grid grid)
		{
			Style s = Application.Current.TryFindResource("Button") as Style;
			var sh = new CtShared();
			int row = grid.RowDefinitions.Count;

			var title = new Button() { Content = "BB LITE", Style = s, Height = 22, Margin = new Thickness(1),
				FontSize = 11, FontWeight = FontWeights.Bold, IsHitTestVisible = false,
				Background = new SolidColorBrush(Color.FromRgb(30,30,30)), Foreground = Brushes.Gray };
			AddFull(grid, sh, row++, title);

			sh.selIbs = MakeBtn(s, "SE LONG", "Arm a long stop-limit entry at the SB High, IBS-gated (active chart)", ColorOff);
			sh.selIbs.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(true, BBEntryKind.StopGated), null); };
			sh.sesIbs = MakeBtn(s, "SE SHORT", "Arm a short stop-limit entry at the SB Low, IBS-gated (active chart)", ColorOff);
			sh.sesIbs.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(false, BBEntryKind.StopGated), null); };
			AddHalf(grid, sh, row++, sh.selIbs, sh.sesIbs);

			sh.sel2 = MakeBtn(s, "SE LONG 2nd", "Same long stop-limit, no IBS gate (active chart)", ColorOff);
			sh.sel2.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(true, BBEntryKind.StopUngated), null); };
			sh.ses2 = MakeBtn(s, "SE SHORT 2nd", "Same short stop-limit, no IBS gate (active chart)", ColorOff);
			sh.ses2.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(false, BBEntryKind.StopUngated), null); };
			AddHalf(grid, sh, row++, sh.sel2, sh.ses2);

			sh.lmtL = MakeBtn(s, "LMT L BB", "Buy Below — limit below the SB Low, same-bar pullback (active chart)", ColorOff);
			sh.lmtL.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(true, BBEntryKind.LmtPullback), null); };
			sh.lmtS = MakeBtn(s, "LMT S SA", "Sell Above — limit above the SB High, same-bar pullback (active chart)", ColorOff);
			sh.lmtS.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(false, BBEntryKind.LmtPullback), null); };
			AddHalf(grid, sh, row++, sh.lmtL, sh.lmtS);

			sh.lmtLUp = MakeBtn(s, "LMT L ▲", "Buy above the SB High — retest entry (active chart)", ColorOff);
			sh.lmtLUp.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(true, BBEntryKind.LmtRetest), null); };
			sh.lmtSDn = MakeBtn(s, "LMT S ▼", "Sell below the SB Low — retest entry (active chart)", ColorOff);
			sh.lmtSDn.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(false, BBEntryKind.LmtRetest), null); };
			AddHalf(grid, sh, row++, sh.lmtLUp, sh.lmtSDn);

			sh.pickSB = MakeBtn(s, "PICK SB", "Toggle, then click a bar to use as the signal bar (active chart)", ColorOff);
			sh.pickSB.Click += (o, e) => { var a = sh.active; if (a == null) return; a._pickArmed = !a._pickArmed; sh.pickSB.Background = new SolidColorBrush(a._pickArmed ? ColorPick : ColorOff); a.Print(DateTime.Now + " PICK SB " + (a._pickArmed ? "ON — click a bar" : "OFF")); };
			sh.cancel = MakeBtn(s, "CANCEL", "Cancel working orders; keep the position (active chart)", Color.FromRgb(120,90,20));
			sh.cancel.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.CancelSEOrders(), null); };
			AddHalf(grid, sh, row++, sh.pickSB, sh.cancel);

			sh.flat = MakeBtn(s, "FLATTEN ALL", "Close position + cancel all orders (active chart)", Color.FromRgb(150,30,30));
			sh.flat.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.FlattenSE(), null); };
			AddFull(grid, sh, row++, sh.flat);

			sh.stpMode = MakeBtn(s, "STP:" + BBLiteStopMode.BarStop, "Cycle stop mode (active chart)", Color.FromRgb(60,60,60));
			sh.stpMode.Click += (o, e) => { var a = sh.active; if (a == null) return; a._stopMode = a._stopMode == BBLiteStopMode.BarStop ? BBLiteStopMode.LastSwing : BBLiteStopMode.BarStop; sh.stpMode.Content = "STP:" + a._stopMode; a.Print(DateTime.Now + " StopMode -> " + a._stopMode); };
			sh.rMult = MakeBtn(s, "TGT 1.0R", "Target R-multiple — left −0.5 / right +0.5 (active chart)", Color.FromRgb(60,60,60));
			sh.rMult.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustRMult(-1); sh.rMult.Content = a.RMultLabel(); } };
			sh.rMult.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustRMult(+1); sh.rMult.Content = a.RMultLabel(); } };
			AddHalf(grid, sh, row++, sh.stpMode, sh.rMult);

			sh.offset = MakeBtn(s, "OFS 1t", "Stop-trigger confirmation ticks — left −1 / right +1 (active chart)", Color.FromRgb(60,60,60));
			sh.offset.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustOffset(-1); sh.offset.Content = a.OffsetLabel(); } };
			sh.offset.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustOffset(+1); sh.offset.Content = a.OffsetLabel(); } };
			sh.ibs = MakeBtn(s, "IBS 0.50", "IBS threshold — left −0.05 / right +0.05 (active chart)", Color.FromRgb(60,60,60));
			sh.ibs.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustIbs(-1); sh.ibs.Content = a.IbsLabel(); } };
			sh.ibs.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustIbs(+1); sh.ibs.Content = a.IbsLabel(); } };
			AddHalf(grid, sh, row++, sh.offset, sh.ibs);

			sh.bars = MakeBtn(s, "BARS 1", "Bars an unfilled entry stays working — left −1 / right +1 (active chart)", Color.FromRgb(60,60,60));
			sh.bars.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustBarsAlive(-1); sh.bars.Content = a.BarsAliveLabel(); } };
			sh.bars.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustBarsAlive(+1); sh.bars.Content = a.BarsAliveLabel(); } };
			AddFull(grid, sh, row++, sh.bars);

			return sh;
		}

		private static void AddFull(Grid grid, CtShared sh, int row, UIElement btn)
		{
			var rd = new RowDefinition() { Height = new GridLength(36) };
			grid.RowDefinitions.Add(rd);
			Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
			grid.Children.Add(btn);
			sh.rds.Add(rd); sh.rows.Add(btn);
		}

		private static void AddHalf(Grid grid, CtShared sh, int row, Button left, Button right)
		{
			var rd = new RowDefinition() { Height = new GridLength(36) };
			grid.RowDefinitions.Add(rd);
			var g = new Grid() { Margin = new Thickness(0) };
			g.ColumnDefinitions.Add(new ColumnDefinition());
			g.ColumnDefinitions.Add(new ColumnDefinition());
			Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
			g.Children.Add(left); g.Children.Add(right);
			Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
			grid.Children.Add(g);
			sh.rds.Add(rd); sh.rows.Add(g);
		}

		private static void ShowPanel(CtShared sh, bool vis)
		{
			var h = vis ? new GridLength(36) : new GridLength(0);
			foreach (var rd in sh.rds) rd.Height = h;
			foreach (var r in sh.rows) r.Visibility = vis ? Visibility.Visible : Visibility.Collapsed;
		}

		private CtShared Panel()
		{
			CtShared sh;
			if (_ctGrid != null && _ctByGrid.TryGetValue(_ctGrid, out sh)) return sh;
			return null;
		}

		// Sync every shared button (colors + sub-button labels) to instance a's current state.
		private static void SyncAll(CtShared sh, BreakoutBoysLiteV2 a)
		{
			if (sh == null || a == null) return;
			SetEntryColors(sh, a);
			sh.stpMode.Content = "STP:" + a._stopMode;
			sh.rMult.Content   = a.RMultLabel();
			sh.offset.Content  = a.OffsetLabel();
			sh.ibs.Content     = a.IbsLabel();
			sh.bars.Content    = a.BarsAliveLabel();
		}

		private static void SetEntryColors(CtShared sh, BreakoutBoysLiteV2 a)
		{
			if (sh == null || a == null) return;
			bool lG = (a._pendingLong  && a._pendingKind == BBEntryKind.StopGated)   || (a._dir == 1  && a._activeKind == BBEntryKind.StopGated);
			bool lU = (a._pendingLong  && a._pendingKind == BBEntryKind.StopUngated) || (a._dir == 1  && a._activeKind == BBEntryKind.StopUngated);
			bool lP = (a._pendingLong  && a._pendingKind == BBEntryKind.LmtPullback) || (a._dir == 1  && a._activeKind == BBEntryKind.LmtPullback);
			bool lR = (a._pendingLong  && a._pendingKind == BBEntryKind.LmtRetest)   || (a._dir == 1  && a._activeKind == BBEntryKind.LmtRetest);
			bool sG = (a._pendingShort && a._pendingKind == BBEntryKind.StopGated)   || (a._dir == -1 && a._activeKind == BBEntryKind.StopGated);
			bool sU = (a._pendingShort && a._pendingKind == BBEntryKind.StopUngated) || (a._dir == -1 && a._activeKind == BBEntryKind.StopUngated);
			bool sP = (a._pendingShort && a._pendingKind == BBEntryKind.LmtPullback) || (a._dir == -1 && a._activeKind == BBEntryKind.LmtPullback);
			bool sR = (a._pendingShort && a._pendingKind == BBEntryKind.LmtRetest)   || (a._dir == -1 && a._activeKind == BBEntryKind.LmtRetest);
			sh.selIbs.Background = new SolidColorBrush(lG ? ColorArmed : ColorOff);
			sh.sel2.Background   = new SolidColorBrush(lU ? ColorArmed : ColorOff);
			sh.lmtL.Background   = new SolidColorBrush(lP ? ColorArmed : ColorOff);
			sh.lmtLUp.Background = new SolidColorBrush(lR ? ColorArmed : ColorOff);
			sh.sesIbs.Background = new SolidColorBrush(sG ? ColorArmed : ColorOff);
			sh.ses2.Background   = new SolidColorBrush(sU ? ColorArmed : ColorOff);
			sh.lmtS.Background   = new SolidColorBrush(sP ? ColorArmed : ColorOff);
			sh.lmtSDn.Background = new SolidColorBrush(sR ? ColorArmed : ColorOff);
			sh.pickSB.Background = new SolidColorBrush(a._pickArmed ? ColorPick : ColorOff);
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
			try { RemoveDrawObject("BBLiteBlock"); } catch { }   // clear any prior block notice on a fresh arm
			CancelWorkingEntries();
			if (_sbPickedBar >= 0) DrawPickMarker(_sbPickedBar, isLong);   // flip above/below once the side is known
			UpdateStatusText(label + " PENDING " + (isLong ? "L" : "S") + " — bar closes to place");
			Print(DateTime.Now + " " + label + " " + (isLong ? "LONG" : "SHORT") + tag
				+ " armed — SB = " + (_sbPickedBar >= 0 ? "picked bar" : "the bar it closes on")
				+ " [" + _stopMode + "/" + _rMult.ToString("0.0") + "R]");
			RefreshSEButtons();
		}

		// Sync the shared entry-button colors to THIS chart's state — but only while THIS chart is
		// the active one (so a background tab's fills never recolor the panel the other tab owns).
		private void RefreshSEButtons()
		{
			var sh = Panel();
			if (sh == null || sh.active != this || ChartControl == null) return;
			ChartControl.Dispatcher.InvokeAsync((Action)(() => SetEntryColors(sh, this)));
		}

		private void OnChartMouseDown(object sender, MouseButtonEventArgs e)
		{
			if (!_pickArmed) return;   // don't log every ordinary chart click, only while actively picking
			Print(DateTime.Now + " PICK SB: click seen (button=" + e.ChangedButton + " handled=" + e.Handled
				+ " ChartControl=" + (ChartControl != null) + " ChartBars=" + (ChartBars != null) + ")");
			if (ChartControl == null || ChartBars == null) { Print(DateTime.Now + " PICK SB: aborted — ChartControl or ChartBars null"); return; }
			try
			{
				// Coordinate must be relative to ChartControl (NOT ChartPanel) for
				// GetBarIdxByX to resolve.
				var pos = e.GetPosition(ChartControl);
				int idx = ChartBars.GetBarIdxByX(ChartControl, (int)pos.X);
				Print(DateTime.Now + " PICK SB: pos=" + pos + " resolved idx=" + idx + " CurrentBar=" + CurrentBar);
				if (idx < 0 || idx > CurrentBar) { Print(DateTime.Now + " PICK SB: click off the bars (idx " + idx + ")"); return; }
				_sbPickedBar = idx;
				_pickArmed = false;
				{ var ps = Panel(); if (ps != null && ps.active == this && ps.pickSB != null) ps.pickSB.Background = new SolidColorBrush(ColorOff); }

				// Visual confirmation on the chart. If a side is already pending (armed
				// BEFORE picking — the reverse of the recommended order), honor it;
				// otherwise default to long-style until ArmSE flips it once a side is
				// actually chosen.
				DrawPickMarker(idx, !_pendingShort);

				double sbHi = ChartBars.Bars.GetHigh(idx), sbLo = ChartBars.Bars.GetLow(idx);
				Print(DateTime.Now + " SB picked @ bar " + idx + " (" + Time.GetValueAt(Math.Min(idx, CurrentBar)) + ") H=" + sbHi.ToString("0.00") + " L=" + sbLo.ToString("0.00"));
			}
			catch (Exception ex) { Print("BBLite pick: " + ex.Message); }
		}

		// Unique tag every call (not a fixed reused one): removing an object and
		// immediately re-adding a DIFFERENT drawing-tool type under the exact same
		// tag in the same call is the kind of same-frame race NinjaScript's drawing
		// manager is not guaranteed to handle cleanly. Drawing the NEW marker under
		// a fresh tag first, then removing the OLD one by its own tag, sidesteps
		// that entirely. Long: below the bar, pointing up. Short: above the bar,
		// pointing down.
		private void DrawPickMarker(int barIdx, bool isLong)
		{
			try
			{
				int barsAgo = Math.Max(0, CurrentBar - barIdx);
				double tick = TickSize;
				string oldTag = _pickMarkerTag;
				_pickMarkerTag = "BBLitePickSB_" + Environment.TickCount;

				// Read price data via ChartBars.Bars.GetLow/GetHigh (absolute index),
				// NOT the Low[]/High[] series indexers. Those indexers are only
				// reliable from the strategy's own processing thread (OnBarUpdate
				// etc.) -- this method can run from a raw UI-thread chart click
				// (OnChartMouseDown), where they throw "Parameter name: barsAgo" for
				// bars far enough back (confirmed live). Same fix MCStrategyDashboardV3
				// already uses for this exact reason.
				double lo = ChartBars.Bars.GetLow(barIdx);
				double hi = ChartBars.Bars.GetHigh(barIdx);

				Brush brush = new SolidColorBrush(ColorPick);   // blue regardless of direction
				if (isLong)
				{
					var a = Draw.ArrowUp(this, _pickMarkerTag, false, barsAgo, lo - 2 * tick, brush);
					if (a != null) { a.Size = ChartMarkerSize.Small; Print(DateTime.Now + " BBLite pick marker drawn (ArrowUp, tag=" + _pickMarkerTag + ")"); }
					else Print(DateTime.Now + " BBLite pick marker: Draw.ArrowUp returned null");
				}
				else
				{
					var a = Draw.ArrowDown(this, _pickMarkerTag, false, barsAgo, hi + 2 * tick, brush);
					if (a != null) { a.Size = ChartMarkerSize.Small; Print(DateTime.Now + " BBLite pick marker drawn (ArrowDown, tag=" + _pickMarkerTag + ")"); }
					else Print(DateTime.Now + " BBLite pick marker: Draw.ArrowDown returned null");
				}

				if (!string.IsNullOrEmpty(oldTag)) { try { RemoveDrawObject(oldTag); } catch { } }
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
			ClearPickMarker();
			ClearStatusText();
		}

		// Remove the SB pick marker — called wherever a working/pending entry
		// resolves (cancelled, disarmed, flattened, expired, or filled), NOT when
		// the order is merely placed: the whole point is the marker stays visible
		// for as long as the order is still live, however many bars that takes.
		private void ClearPickMarker()
		{
			if (string.IsNullOrEmpty(_pickMarkerTag)) return;
			try { RemoveDrawObject(_pickMarkerTag); } catch (Exception ex) { Print("BBLite remove marker: " + ex.Message); }
			_pickMarkerTag = null;
		}

		// A second, distinct on-chart signal (separate from the SB marker) so an
		// armed-but-not-yet-placed order (PENDING) and an actually-resting order
		// (WORKING, counting down its BARS-alive window) are visually obvious
		// without having to check the panel button colors. Fixed tag — same
		// drawing-tool type (Text) every call, so no type-swap hazard like the
		// Arrow markers had; safe to just reposition/retext in place.
		private void UpdateStatusText(string text)
		{
			try { Draw.Text(this, "BBLiteStatus", text, 0, High[0] + 4 * TickSize); }
			catch (Exception ex) { Print(DateTime.Now + " BBLite status text FAILED: " + ex.Message); }
		}

		private void ClearStatusText()
		{
			try { RemoveDrawObject("BBLiteStatus"); } catch { }
			try { RemoveDrawObject("BBLiteBlock");  } catch { }
		}

		// Rebuilds the WORKING status text from current state (elapsed/_maxBarsAlive
		// bars) -- called every bar while an order is resting so the countdown stays
		// live, and once right after submission for the initial draw.
		private void RefreshStatusText()
		{
			if (_armedBarIndex < 0) { ClearStatusText(); return; }
			bool isLong = _dir == 1;
			bool isLmt  = _activeKind == BBEntryKind.LmtPullback || _activeKind == BBEntryKind.LmtRetest;
			int elapsed = CurrentBar - _armedBarIndex;
			UpdateStatusText((isLmt ? "LMT" : "SE") + " WORKING " + (isLong ? "L" : "S") + " " + elapsed + "/" + _maxBarsAlive + "b");
		}

		// Cancel working orders (entry + stop/target) but leave an open position alone.
		private void CancelSEOrders()
		{
			foreach (Order o in Orders)
				if ((o.Name == "SE" || o.Name == "SEstop" || o.Name == "SEtgt") && IsLive(o))
					CancelOrder(o);
			_pendingLong = _pendingShort = false;
			_armedBarIndex = -1;
			ClearPickMarker();
			ClearStatusText();
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
			_armedBarIndex = -1;
			ClearPickMarker();
			ClearStatusText();
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
			Print(DateTime.Now + " " + RMultLabel());
		}

		private void AdjustOffset(int dir)
		{
			_offsetTicks = Math.Max(1, Math.Min(50, _offsetTicks + dir));
			Print(DateTime.Now + " " + OffsetLabel());
		}

		private void AdjustIbs(int dir)
		{
			_ibsThreshold = Math.Max(0.05, Math.Min(0.95, Math.Round(_ibsThreshold + dir * 0.05, 2)));
			Print(DateTime.Now + " " + IbsLabel());
		}

		private void AdjustBarsAlive(int dir)
		{
			_maxBarsAlive = Math.Max(1, Math.Min(50, _maxBarsAlive + dir));
			Print(DateTime.Now + " " + BarsAliveLabel());
		}

		private void DisposeWPFControls()
		{
			try
			{
				if (_mouseHooked && ChartControl != null) { ChartControl.PreviewMouseDown -= OnChartMouseDown; _mouseHooked = false; }
				try { if (_ctEnter != null && ChartControl != null) ChartControl.MouseEnter -= _ctEnter; } catch { }
				_ctEnter = null;
				if (!string.IsNullOrEmpty(_pickMarkerTag)) { try { RemoveDrawObject(_pickMarkerTag); } catch { } _pickMarkerTag = null; }
				ClearStatusText();
				if (!ctPanelActive) return;
				CtShared sh;
				if (_ctGrid != null && _ctByGrid.TryGetValue(_ctGrid, out sh))
				{
					if (sh.active == this) sh.active = null;   // leave the buttons; another tab may still own them
					sh.refs--;
					if (sh.refs <= 0) ShowPanel(sh, false);    // last one gone -> hide the rows (no index surgery)
				}
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
