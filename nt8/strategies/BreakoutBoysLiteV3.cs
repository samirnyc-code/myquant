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
	public class BreakoutBoysLiteV3 : Strategy
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
			public BreakoutBoysLiteV3 active;
			public Button buy, sell, lmtL, lmtS, ibsToggle, ibsMinus, ibsPlus, pickSB, cancel, flat, stpMode, rMult, offset, bars;
			public bool pickArmed;   // SHARED: PICK SB arms it; the next bar-click (on any tab) consumes it on that chart
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
		private bool   _ibsArmed = true;  // IBS gate on/off toggle (applies to BUY/SELL only)
		// immediate (picked-SB) entry: submitted from OnMarketData, NOT the button thread —
		// managed Enter() from TriggerCustomEvent (racing an async cancel vs EntriesPerDirection)
		// silently no-ops; OnMarketData is a valid order-submission context and fires next tick.
		private bool   _immPending; private bool _immLong; private BBEntryKind _immKind; private int _immSbBar = -1;

		private bool   _pendingLong, _pendingShort;   // armed, waiting for the SB (armed bar) to close
		private BBEntryKind _pendingKind;              // which entry mechanism the pending arm uses
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
				Name         = "BreakoutBoysLiteV3";
				Description  = "BreakoutBoys Lite V3 — BUY/SELL auto-type entries (stop-limit if price hasn't reached the SB level, limit if it's past it; never blocked) with an IBS gate TOGGLE, + LMT L BB/S SA pullback limits. Pick a SB = place immediately; no pick = place at the forming bar's close. Bar/swing stop, R-multiple target, bars-alive auto-cancel.";
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
				if (kind == BBEntryKind.LmtPullback) TryPlaceLimitEntry(isLong, kind, sbAgo);
				else                                 PlaceAutoEntry(isLong, kind == BBEntryKind.StopGated, sbAgo);
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
		// Immediate (picked-SB) entries are submitted HERE — OnMarketData is a valid managed-order
		// context (unlike the button's TriggerCustomEvent thread), and by the next tick the earlier
		// CancelWorkingEntries() has settled, so EntriesPerDirection no longer blocks the new order.
		protected override void OnMarketData(MarketDataEventArgs e)
		{
			if (!_immPending || e.MarketDataType != MarketDataType.Last) return;
			_immPending = false;
			if (Position.MarketPosition != MarketPosition.Flat)
			{ Print(DateTime.Now + " immediate entry skipped — already in a trade"); return; }
			int sbAgo = Math.Max(0, CurrentBar - _immSbBar);
			if (_immKind == BBEntryKind.LmtPullback || _immKind == BBEntryKind.LmtRetest)
				TryPlaceLimitEntry(_immLong, _immKind, sbAgo);
			else
				PlaceAutoEntry(_immLong, _immKind == BBEntryKind.StopGated, sbAgo);
			RefreshSEButtons();
		}

		// BUY / SELL auto-entry: level L = the SB breakout extreme +/- offset. The ORDER TYPE is
		// chosen at placement from the LAST price vs L, so it can NEVER be blocked:
		//   price hasn't reached L yet -> stop-limit at L (breakout);
		//   price already past L       -> limit at L (pullback/retest).
		// IBS gate (if armed) still applies to BUY/SELL. Stop/target are SB-structure based.
		private void PlaceAutoEntry(bool isLong, bool useIbs, int sbAgo)
		{
			double tick = TickSize;
			double hi = High[sbAgo], lo = Low[sbAgo], range = hi - lo;
			double ibs = range > 0 ? (Close[sbAgo] - lo) / range : 0.5;

			if (useIbs)
			{
				bool pass = isLong ? ibs >= _ibsThreshold : ibs <= (1.0 - _ibsThreshold);
				if (!pass)
				{
					string need = isLong ? (">= " + (int)Math.Round(_ibsThreshold * 100)) : ("<= " + (int)Math.Round((1.0 - _ibsThreshold) * 100));
					string msg = (isLong ? "BUY" : "SELL") + " skipped - SB IBS " + (int)Math.Round(ibs * 100) + " does not meet " + need;
					Print(DateTime.Now + " " + msg);
					ShowPopup(msg);
					return;
				}
			}

			double L  = isLong ? hi + _offsetTicks * tick : lo - _offsetTicks * tick;
			double px = Close[0];
			bool useStop = isLong ? (px < L) : (px > L);   // not reached yet -> stop; already past -> limit

			_stopPx = ComputeStopLossPx(isLong, sbAgo);
			_dir = isLong ? 1 : -1;
			_activeKind = useIbs ? BBEntryKind.StopGated : BBEntryKind.StopUngated;
			_armedBarIndex = CurrentBar;

			double entryRef;
			if (useStop)
			{
				double trigger = L;
				double limitPx = isLong ? trigger + StopLimitCushionTicks * tick : trigger - StopLimitCushionTicks * tick;
				entryRef = limitPx;
				if (isLong) EnterLongStopLimit (0, true, SE_Qty, Round(limitPx), Round(trigger), "SE");
				else        EnterShortStopLimit(0, true, SE_Qty, Round(limitPx), Round(trigger), "SE");
			}
			else
			{
				entryRef = L;
				if (isLong) EnterLongLimit (0, true, SE_Qty, Round(L), "SE");
				else        EnterShortLimit(0, true, SE_Qty, Round(L), "SE");
			}

			// Safety: the stop MUST sit on the protective side of the entry (below for a long,
			// above for a short). A stale LastSwing can land on the wrong side (stop above a long
			// entry = instant stop-out) — if so, fall back to the SB BarStop (opposite extreme).
			bool stopOk = isLong ? (_stopPx < entryRef) : (_stopPx > entryRef);
			if (!stopOk) _stopPx = isLong ? lo - SE_StopOffsetTicks * tick : hi + SE_StopOffsetTicks * tick;

			double risk = Math.Abs(entryRef - _stopPx);
			_entryPx = entryRef;
			_tgtPx   = isLong ? entryRef + risk * _rMult : entryRef - risk * _rMult;
			RefreshStatusText();

			Print(DateTime.Now + "  " + (isLong ? "BUY" : "SELL") + (useStop ? " STOP-LIMIT@" : " LIMIT@") + L.ToString("0.00")
				+ " stop@" + _stopPx.ToString("0.00") + " tgt@" + _tgtPx.ToString("0.00")
				+ " [" + _stopMode + "/" + _rMult.ToString("0.0") + "R, IBS " + (useIbs ? ("on " + (int)Math.Round(ibs * 100)) : "off")
				+ ", alive " + _maxBarsAlive + "b]");
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
			ClearPickMarker();   // expired unfilled -> remove the SB marker
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
				_pickMarkerTag = null; // RELEASE (don't remove) the SB marker -> it stays on the chart
				                       // forever, marking where a trade was actually taken.
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
			// (no title row — the Chart Trader panel is short; every row is spent on controls so
			// the last one, BARS, never gets clipped off the bottom.)

			// Row: BUY | SELL — auto stop/limit at the SB breakout level; IBS gated per the toggle.
			sh.buy = MakeBtn(s, "BUY", "Long at SB High+OFS — auto stop/limit by price; IBS-gated if armed (active chart)", ColorOff);
			sh.buy.Click  += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(true,  a._ibsArmed ? BBEntryKind.StopGated : BBEntryKind.StopUngated), null); };
			sh.sell = MakeBtn(s, "SELL", "Short at SB Low-OFS — auto stop/limit by price; IBS-gated if armed (active chart)", ColorOff);
			sh.sell.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(false, a._ibsArmed ? BBEntryKind.StopGated : BBEntryKind.StopUngated), null); };
			AddHalf(grid, sh, row++, sh.buy, sh.sell);

			// Row: LMT L BB | LMT S SA — unchanged (plain pullback limits on the near side of the SB).
			sh.lmtL = MakeBtn(s, "LMT L BB", "Buy Below — limit below the SB Low, same-bar pullback (active chart)", ColorOff);
			sh.lmtL.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(true, BBEntryKind.LmtPullback), null); };
			sh.lmtS = MakeBtn(s, "LMT S SA", "Sell Above — limit above the SB High, same-bar pullback (active chart)", ColorOff);
			sh.lmtS.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.ArmSE(false, BBEntryKind.LmtPullback), null); };
			AddHalf(grid, sh, row++, sh.lmtL, sh.lmtS);

			// Row: IBS gate toggle (green = armed; shows the value). Row below: [IBS - | IBS +] adjust.
			sh.ibsToggle = MakeBtn(s, "IBS 50", "IBS gate ON/OFF for BUY/SELL — click to toggle (active chart)", ColorOn);
			sh.ibsToggle.Click += (o, e) => { var a = sh.active; if (a == null) return; a._ibsArmed = !a._ibsArmed; sh.ibsToggle.Background = new SolidColorBrush(a._ibsArmed ? ColorOn : ColorOff); a.Print(DateTime.Now + " IBS gate " + (a._ibsArmed ? "ON" : "OFF")); };
			AddFull(grid, sh, row++, sh.ibsToggle);

			sh.ibsMinus = MakeBtn(s, "IBS -", "Lower the IBS threshold by 5 (active chart)", Color.FromRgb(60,60,60));
			sh.ibsMinus.Click += (o, e) => { var a = sh.active; if (a != null) { a.AdjustIbs(-1); sh.ibsToggle.Content = a.IbsLabel(); } };
			sh.ibsPlus = MakeBtn(s, "IBS +", "Raise the IBS threshold by 5 (active chart)", Color.FromRgb(60,60,60));
			sh.ibsPlus.Click += (o, e) => { var a = sh.active; if (a != null) { a.AdjustIbs(+1); sh.ibsToggle.Content = a.IbsLabel(); } };
			AddHalf(grid, sh, row++, sh.ibsMinus, sh.ibsPlus);

			// Row: PICK SB | CANCEL
			sh.pickSB = MakeBtn(s, "PICK SB", "Toggle, then click a bar to use as the signal bar (active chart)", ColorOff);
			sh.pickSB.Click += (o, e) => { var a = sh.active; if (a == null) return; sh.pickArmed = !sh.pickArmed; sh.pickSB.Background = new SolidColorBrush(sh.pickArmed ? ColorPick : ColorOff); a.Print(DateTime.Now + " PICK SB " + (sh.pickArmed ? "ON — click a bar" : "OFF")); };
			sh.cancel = MakeBtn(s, "CANCEL", "Cancel working orders; keep the position (active chart)", Color.FromRgb(120,90,20));
			sh.cancel.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.CancelSEOrders(), null); };
			AddHalf(grid, sh, row++, sh.pickSB, sh.cancel);

			// Row: FLATTEN ALL
			sh.flat = MakeBtn(s, "FLATTEN ALL", "Close position + cancel all orders (active chart)", Color.FromRgb(150,30,30));
			sh.flat.Click += (o, e) => { var a = sh.active; if (a != null) a.TriggerCustomEvent(st => a.FlattenSE(), null); };
			AddFull(grid, sh, row++, sh.flat);

			// Row: STP mode | TGT R
			sh.stpMode = MakeBtn(s, "STP:" + BBLiteStopMode.BarStop, "Cycle stop mode (active chart)", Color.FromRgb(60,60,60));
			sh.stpMode.Click += (o, e) => { var a = sh.active; if (a == null) return; a._stopMode = a._stopMode == BBLiteStopMode.BarStop ? BBLiteStopMode.LastSwing : BBLiteStopMode.BarStop; sh.stpMode.Content = "STP:" + a._stopMode; a.Print(DateTime.Now + " StopMode -> " + a._stopMode); };
			sh.rMult = MakeBtn(s, "TGT 1.0R", "Target R-multiple — left -0.5 / right +0.5 (active chart)", Color.FromRgb(60,60,60));
			sh.rMult.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustRMult(-1); sh.rMult.Content = a.RMultLabel(); } };
			sh.rMult.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustRMult(+1); sh.rMult.Content = a.RMultLabel(); } };
			AddHalf(grid, sh, row++, sh.stpMode, sh.rMult);

			// Row: OFS | BARS
			sh.offset = MakeBtn(s, "OFS 1t", "Entry offset ticks beyond the SB extreme — left -1 / right +1 (active chart)", Color.FromRgb(60,60,60));
			sh.offset.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustOffset(-1); sh.offset.Content = a.OffsetLabel(); } };
			sh.offset.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustOffset(+1); sh.offset.Content = a.OffsetLabel(); } };
			sh.bars = MakeBtn(s, "BARS 1", "Bars an unfilled entry stays working — left -1 / right +1 (active chart)", Color.FromRgb(60,60,60));
			sh.bars.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustBarsAlive(-1); sh.bars.Content = a.BarsAliveLabel(); } };
			sh.bars.PreviewMouseRightButtonDown += (o, e) => { e.Handled = true; var a = sh.active; if (a != null) { a.AdjustBarsAlive(+1); sh.bars.Content = a.BarsAliveLabel(); } };
			AddHalf(grid, sh, row++, sh.offset, sh.bars);

			return sh;
		}

		private static void AddFull(Grid grid, CtShared sh, int row, UIElement btn)
		{
			var rd = new RowDefinition() { Height = new GridLength(29) };
			grid.RowDefinitions.Add(rd);
			Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
			grid.Children.Add(btn);
			sh.rds.Add(rd); sh.rows.Add(btn);
		}

		private static void AddHalf(Grid grid, CtShared sh, int row, Button left, Button right)
		{
			var rd = new RowDefinition() { Height = new GridLength(29) };
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
			var h = vis ? new GridLength(29) : new GridLength(0);
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
		private static void SyncAll(CtShared sh, BreakoutBoysLiteV3 a)
		{
			if (sh == null || a == null) return;
			SetEntryColors(sh, a);
			sh.stpMode.Content      = "STP:" + a._stopMode;
			sh.rMult.Content        = a.RMultLabel();
			sh.offset.Content       = a.OffsetLabel();
			sh.ibsToggle.Content    = a.IbsLabel();
			sh.ibsToggle.Background = new SolidColorBrush(a._ibsArmed ? ColorOn : ColorOff);
			sh.bars.Content         = a.BarsAliveLabel();
		}

		private static void SetEntryColors(CtShared sh, BreakoutBoysLiteV3 a)
		{
			if (sh == null || a == null) return;
			bool lAuto = (a._pendingLong  && (a._pendingKind == BBEntryKind.StopGated || a._pendingKind == BBEntryKind.StopUngated)) || (a._dir == 1  && (a._activeKind == BBEntryKind.StopGated || a._activeKind == BBEntryKind.StopUngated));
			bool lLmt  = (a._pendingLong  && a._pendingKind == BBEntryKind.LmtPullback) || (a._dir == 1  && a._activeKind == BBEntryKind.LmtPullback);
			bool sAuto = (a._pendingShort && (a._pendingKind == BBEntryKind.StopGated || a._pendingKind == BBEntryKind.StopUngated)) || (a._dir == -1 && (a._activeKind == BBEntryKind.StopGated || a._activeKind == BBEntryKind.StopUngated));
			bool sLmt  = (a._pendingShort && a._pendingKind == BBEntryKind.LmtPullback) || (a._dir == -1 && a._activeKind == BBEntryKind.LmtPullback);
			sh.buy.Background    = new SolidColorBrush(lAuto ? ColorArmed : ColorOff);
			sh.sell.Background   = new SolidColorBrush(sAuto ? ColorArmed : ColorOff);
			sh.lmtL.Background   = new SolidColorBrush(lLmt  ? ColorArmed : ColorOff);
			sh.lmtS.Background   = new SolidColorBrush(sLmt  ? ColorArmed : ColorOff);
			sh.pickSB.Background = new SolidColorBrush(sh.pickArmed ? ColorPick : ColorOff);
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

			// With a PICKED SB: place IMMEDIATELY (the bar's levels are known) — applies to BUY/SELL
			// (auto) AND LMT L BB/S SA alike. This MUST run before the same-config toggle below, or a
			// 2nd picked entry would just disarm the 1st (its _dir/_activeKind are already set) instead
			// of placing a new order.
			if (_sbPickedBar >= 0)
			{
				if (Position.MarketPosition != MarketPosition.Flat)
				{ Print(DateTime.Now + " " + label + ": already in a trade — flatten first."); return; }
				string sideWord = isLmt ? (isLong ? "LONG" : "SHORT") : (isLong ? "BUY" : "SELL");
				// Queue it for OnMarketData (next tick) — do NOT submit the managed entry from here.
				_immPending = true; _immLong = isLong; _immKind = kind; _immSbBar = _sbPickedBar;
				_pendingLong = _pendingShort = false;
				_sbPickedBar = -1;
				try { RemoveDrawObject("BBLiteBlock"); } catch { }
				CancelWorkingEntries();   // replace any still-working entry (completes before the tick fires)
				UpdateStatusText(label + " " + sideWord + " placing...");
				Print(DateTime.Now + " " + label + " " + sideWord + " (picked bar) queued — placing on next tick");
				RefreshSEButtons();
				return;
			}

			if (sameConfigActive)
			{
				_pendingLong = _pendingShort = false;
				CancelWorkingEntries();
				ClearPickMarker();   // disarmed/cancelled unfilled -> remove the SB marker
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
			// PICK is armed on the SHARED panel (set by PICK SB). The bar-click consumes it on
			// WHATEVER chart was clicked — so clicking a bar here makes this the active chart and
			// picks the SB on it, regardless of which tab was active when PICK SB was pressed.
			var ps = Panel();
			if (ps == null || !ps.pickArmed) return;   // not picking -> ignore ordinary clicks
			ps.active = this;                           // the chart you clicked to pick is now active
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
				ps.pickArmed = false;
				if (ps.pickSB != null) ps.pickSB.Background = new SolidColorBrush(ColorOff);

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

		// Cancels any working ENTRY order. Does NOT touch the SB marker — the marker is cleared only
		// by a genuine user cancel/disarm/expire/flatten, and is RELEASED (kept) on a fill. (This
		// runs when placing a new order too, where the current pick's marker must survive.)
		private void CancelWorkingEntries()
		{
			foreach (Order o in Orders)
				if (o.Name == "SE" && IsLive(o)) CancelOrder(o);
			_armedBarIndex = -1;
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
		private string IbsLabel()       { return "IBS " + (int)Math.Round(_ibsThreshold * 100); }
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
			return new Button() { Content = label, Style = s, Height = 27, Margin = new Thickness(1),
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
