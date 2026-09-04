#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
	// ══════════════════════════════════════════════════════════════════════════
	// WedgeScalperV2 — MyWedge signal-bar scalper.
	// ══════════════════════════════════════════════════════════════════════════
	// 2026-09-03: ALL reversal / "hold-to-opposite" / flip logic REMOVED. This is
	// the plain scalper only. ONE POSITION AT A TIME — a wedge that fires while a
	// trade is open is ignored; only the first wedge after going flat is taken.
	//
	//   ENTRY   ONE stop order sized (ScalpQty + RunnerQty), 1t beyond the SB:
	//             long  = SB.High + StopBeyondSBTicks   (buy stop)
	//             short = SB.Low  - StopBeyondSBTicks   (sell stop)
	//           valid EntryValidBars bar(s), else it lapses.
	//   STOP    whole-position protective stop 1t beyond the OTHER side of the SB.
	//   SCALP   ScalpQty contracts exit at +ScalpTargetTicks (limit, scaled out once).
	//   RUNNER  the stop HOLDS at the SB level until price moves +BETriggerTicks in
	//           favor; then it locks entry ± BEOffsetTicks and trails 1t beyond each
	//           closed bar. It never tightens before BE (no trail-from-entry — S110).
	//
	// ⚠ RUN WITH TICK REPLAY *OFF*, Calculate.OnBarClose — Tick Replay ON drags
	//   resting-stop fills past the stop price; OFF fills at the stop price.
	// The MyWedge params below MUST match the MyWedge instance on your chart.
	public class WedgeScalperV2 : Strategy
	{
		private Indicators.My.MyWedge _wedge;

		// entry state machine (while flat)
		private int    _pendingSide;   // 0 none, 1 long, -1 short
		private int    _sigBar;        // CurrentBar of the signal
		private double _entryPx;       // stop-entry trigger price
		private double _stopPx;        // initial protective stop (1t beyond SB)

		// open-trade state
		private double _entry;         // actual fill price (Position.AveragePrice)
		private bool   _beActive;      // runner has armed breakeven/trail
		private double _curStop;       // current protective stop level
		private bool   _scalpDone;     // scalp lot has scaled out (never re-scalp)
		private int    _entryBar;      // CurrentBar at the fill (left edge of the R:R boxes)

		// manual stop override (value-comparison, per @@MCScaleInStrategy):
		private double _stratSetStop;   // last stop price the STRATEGY commanded
		private double _liveStopPrice;  // actual live "Stop" order price (from OnOrderUpdate)
		private bool   _userMovedStop;  // user dragged the stop -> strategy hands off for this trade
		private Order  _entryOrder;     // the resting "Wedge" entry, so we can cancel it precisely

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description  = "MyWedge signal-bar scalper: single sized entry, all-manual exits, immediate stop on fill, no re-scalp. No reversal.";
				Name         = "WedgeScalperV2";
				Calculate    = Calculate.OnBarClose;
				EntriesPerDirection = 1;
				EntryHandling = EntryHandling.AllEntries;
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds    = 30;
				BarsRequiredToTrade          = 20;
				IsUnmanaged                  = false;
				// A rejected order must NOT disable the strategy (which wipes the chart's
				// trade markers). Fail quietly and keep running instead.
				RealtimeErrorHandling        = RealtimeErrorHandling.IgnoreAllErrors;

				// ── trade structure ────────────────────────────────────────────
				ScalpQty          = 1;   // 0 = no scalp lot
				RunnerQty         = 1;   // 0 = no runner lot
				StopBeyondSBTicks = 1;
				InsideBarUsePriorBar = true;  // SB is an inside bar -> stop beyond the prior bar
				ScalpTargetTicks  = 4;
				BETriggerTicks    = 5;    // price must reach entry ± this to ARM breakeven
				BEOffsetTicks     = 0;    // where the stop locks once armed: entry ± this (signed, +4 = lock 1pt)
				TrailTicks        = 1;
				EntryValidBars    = 1;

				// ── chart visuals ──────────────────────────────────────────────
				ShowRiskReward    = true;    // green reward box (entry->scalp tgt) + red risk box (entry->initial stop) + R multiple
				ShowBELine        = true;    // dashed gold line where the runner locks BE (entry ± BETriggerTicks)
				DebugDraw         = false;   // draw the strategy's OWN signals + entry/exit lifecycle on the chart

				// ── MyWedge ctor params — SET TO MATCH YOUR CHART ──────────────
				LookBack       = 12;
				ShowW2L        = true;
				WedgeSymmetry  = 0;
				OLSensitivity  = 0;
				CTSB_Ignore    = false;
				IB_Ignore      = false;
				ShowWedgeSB    = true;
				SignalBarIBS   = 0.0;
				ContinueMC     = false;
				ContinueOnGap  = false;
			}
			else if (State == State.DataLoaded)
			{
				_wedge = MyWedge(Input, LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);
			}
			else if (State == State.Realtime)
			{
				Print("=== WedgeScalperV2 REALTIME: now live. It will ONLY act on NEW "
					+ "signals from here forward — historical signals on the chart are not traded. ===");
			}
		}

		private string ST { get { return State == State.Realtime ? "RT  " : "HIST"; } }

		// True if a protective "Stop" order is currently resting. When one is, it exits at
		// the stop PRICE; the StopFail market net should defer to it (else we eat slippage).
		private bool HasWorkingStop()
		{
			foreach (Order o in Orders)
				if (o.OrderState == OrderState.Working && o.Name == "Stop") return true;
			return false;
		}

		protected override void OnBarUpdate()
		{
			if (_wedge == null || CurrentBar < BarsRequiredToTrade)
				return;

			_wedge.Update();
			double tick = TickSize;

			// Diagnostics: draw the STRATEGY's own MyWedge signals (cyan up / orange down).
			if (DebugDraw)
			{
				if (_wedge.WedgeBLSB[0] > 0) Draw.Dot(this, "wbl" + CurrentBar, false, 0, Low[0]  - 16 * tick, Brushes.Cyan);
				if (_wedge.WedgeBRSB[0] > 0) Draw.Dot(this, "wbr" + CurrentBar, false, 0, High[0] + 16 * tick, Brushes.Orange);
			}

			// ═══════════════════════════ FLAT ═══════════════════════════
			if (Position.MarketPosition == MarketPosition.Flat)
			{
				// reset leftover open-trade state
				_entry = 0; _beActive = false; _curStop = 0; _scalpDone = false;
				_stratSetStop = 0; _liveStopPrice = 0; _userMovedStop = false;
				ClearTradeVisuals();   // wipe R:R boxes + BE line once flat

				// ── detect a NEW signal on the just-closed bar [0] and rest ONE entry ──
				if (_pendingSide == 0)
				{
					int side = 0;
					if (_wedge.WedgeBLSB[0] > 0) side = 1;
					else if (_wedge.WedgeBRSB[0] > 0) side = -1;
					if (side != 0)
					{
						_pendingSide = side; _sigBar = CurrentBar;
						// If the SB is an INSIDE bar (contained in the prior bar), its range is
						// too tight for a protective stop -> put the stop beyond the PRIOR bar
						// instead. Entry stays at the SB breakout level either way.
						bool insideBar = InsideBarUsePriorBar && CurrentBar >= 1
							&& High[0] <= High[1] && Low[0] >= Low[1];
						double stopHi = insideBar ? High[1] : High[0];
						double stopLo = insideBar ? Low[1]  : Low[0];
						if (side == 1) { _entryPx = High[0] + StopBeyondSBTicks * tick; _stopPx = stopLo - StopBeyondSBTicks * tick; }
						else           { _entryPx = Low[0]  - StopBeyondSBTicks * tick; _stopPx = stopHi + StopBeyondSBTicks * tick; }
						int totQ = ScalpQty + RunnerQty;
						if (totQ > 0)
						{
							// A stop entry can't sit on the wrong side of the market (NT rejects
							// a buy-stop BELOW / sell-stop ABOVE market). If price already ran
							// past the level, rest a LIMIT at the same price instead.
							if (side == 1)
							{
								double ask = State == State.Realtime ? GetCurrentAsk() : Close[0];
								if (_entryPx > ask) EnterLongStopMarket(0, true, totQ, _entryPx, "Wedge");
								else                EnterLongLimit (0, true, totQ, _entryPx, "Wedge");
							}
							else
							{
								double bid = State == State.Realtime ? GetCurrentBid() : Close[0];
								if (_entryPx < bid) EnterShortStopMarket(0, true, totQ, _entryPx, "Wedge");
								else                EnterShortLimit (0, true, totQ, _entryPx, "Wedge");
							}
							Print(ST + " " + Time[0] + "  SIGNAL " + (side > 0 ? "LONG " : "SHORT")
								+ "  rest x" + totQ + " entry@" + _entryPx + " protStop@" + _stopPx
								+ (insideBar ? "  [inside bar -> stop beyond prior bar]" : ""));
							if (DebugDraw) Draw.Text(this, "sub" + CurrentBar, "SUB@" + _entryPx,
								0, side > 0 ? High[0] + 6 * tick : Low[0] - 6 * tick);
						}
					}
				}
				else if (CurrentBar - _sigBar > EntryValidBars)
				{
					// Window passed: REQUEST cancel only. The Ecancel marker + _pendingSide
					// reset happen only when NT CONFIRMS the order Cancelled (OnOrderUpdate) —
					// never optimistically, or a fill that beats the cancel gets a false
					// Ecancel (the SUB -> Ecancel -> FILL contradiction). Kept idempotent.
					if (_entryOrder != null) CancelOrder(_entryOrder);
					else foreach (Order o in Orders)
						if (o.OrderState == OrderState.Working && o.Name == "Wedge") CancelOrder(o);
				}
				return;
			}

			// ══════════════════════ OPEN POSITION ══════════════════════
			// One position at a time — opposite/new signals are ignored while in a trade.
			if (Position.MarketPosition == MarketPosition.Long)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; _entryBar = CurrentBar; }

				if (RunnerQty > 0 && !_userMovedStop)   // skip auto-trail once the user drags the stop
				{
					// HOLD the SB protective stop until the trade earns it: arm BE only when
					// price has moved +BETriggerTicks in favor, THEN lock BE and trail 1t beyond
					// each closed bar. No trailing from entry — that tightened the stop INSIDE
					// the SB and stopped trades out prematurely (S110). Pre-BE, _curStop stays
					// at the initial SB stop (_stopPx) — untouched here.
					if (!_beActive && High[0] >= _entry + BETriggerTicks * tick) _beActive = true;
					if (_beActive)
					{
						_curStop = Math.Max(_curStop, _entry + BEOffsetTicks * tick);            // lock BE (± offset)
						_curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick);              // then trail 1t/bar
					}
				}
				ManageProtection();
				if (!HasWorkingStop() && Close[0] <= _curStop) ExitLong("StopFail", "Wedge");   // true last-resort only
				DrawTradeVisuals(true);
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; _entryBar = CurrentBar; }

				if (RunnerQty > 0 && !_userMovedStop)
				{
					// HOLD the SB protective stop until BE arms (price moves +BETriggerTicks in
					// favor), THEN lock BE and trail 1t beyond each closed bar. No trailing from
					// entry (S110). Pre-BE, _curStop stays at the initial SB stop (_stopPx).
					if (!_beActive && Low[0] <= _entry - BETriggerTicks * tick) _beActive = true;
					if (_beActive)
					{
						_curStop = Math.Min(_curStop, _entry - BEOffsetTicks * tick);            // lock BE (± offset)
						_curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);             // then trail 1t/bar
					}
				}
				ManageProtection();
				if (!HasWorkingStop() && Close[0] >= _curStop) ExitShort("StopFail", "Wedge");
				DrawTradeVisuals(false);
			}
		}

		// Draw the live-trade R:R picture: green reward box (entry -> scalp target),
		// red risk box (entry -> stop), the R multiple, and a dashed line where the
		// runner locks breakeven. The risk box uses the INITIAL stop (so R doesn't move
		// on the auto-trail) UNLESS the user has manually dragged the stop — then it
		// follows that stop and R recomputes live.
		// Boxes span from the entry bar to the current bar (extend right as bars form).
		private void DrawTradeVisuals(bool isLong)
		{
			if (_entry == 0 || (!ShowRiskReward && !ShowBELine)) return;
			double tick = TickSize;
			int startBarsAgo = Math.Max(0, CurrentBar - _entryBar);

			// effective stop for the R:R: manual drag wins, else the initial stop
			double riskStop = (_userMovedStop && _liveStopPrice > 0) ? _liveStopPrice : _stopPx;
			double scalpTgt = isLong ? _entry + ScalpTargetTicks * tick : _entry - ScalpTargetTicks * tick;
			double beTrig   = isLong ? _entry + BETriggerTicks   * tick : _entry - BETriggerTicks   * tick;

			if (ShowRiskReward)
			{
				Draw.Rectangle(this, "rrRew",  false, startBarsAgo, _entry, 0, scalpTgt, Brushes.Transparent, Brushes.SeaGreen,  25);
				Draw.Rectangle(this, "rrRisk", false, startBarsAgo, _entry, 0, riskStop, Brushes.Transparent, Brushes.Firebrick, 25);

				double riskT = Math.Abs(_entry - riskStop) / tick;
				double rr    = riskT > 0 ? ScalpTargetTicks / riskT : 0;
				Draw.Text(this, "rrTxt",
					"R 1:" + rr.ToString("0.00") + "   (tgt " + ScalpTargetTicks + "t / risk " + riskT.ToString("0") + "t)"
						+ (_userMovedStop ? " [manual stop]" : ""),
					0, isLong ? scalpTgt + 4 * tick : scalpTgt - 4 * tick);
			}

			if (ShowBELine)
			{
				Draw.HorizontalLine(this, "beLine", beTrig, Brushes.Gold, DashStyleHelper.Dash, 1);
				Draw.Text(this, "beTxt", "BE trig " + BETriggerTicks + "t",
					0, isLong ? beTrig + 2 * tick : beTrig - 2 * tick);
			}
		}

		private void ClearTradeVisuals()
		{
			RemoveDrawObject("rrRew");
			RemoveDrawObject("rrRisk");
			RemoveDrawObject("rrTxt");
			RemoveDrawObject("beLine");
			RemoveDrawObject("beTxt");
		}

		// Places/updates the whole-position stop and (once) the scalp target. Called
		// both from OnBarUpdate (per-bar trail) and OnExecutionUpdate (immediate on fills)
		// so the stop is live the instant we fill and its qty drops as soon as the scalp
		// scales out — not a bar later.
		private void ManageProtection()
		{
			// Manual override: if the live stop price diverged from what we last set, the
			// user dragged it -> hand off the stop for the rest of this trade.
			if (!_userMovedStop && _stratSetStop > 0 && _liveStopPrice > 0
				&& Math.Abs(_liveStopPrice - _stratSetStop) > TickSize / 2)
			{
				_userMovedStop = true;
				_curStop = _liveStopPrice;
				Print(ST + " " + Time[0] + "  manual stop @ " + _liveStopPrice + " -> auto-stop OFF for this trade");
			}

			if (Position.MarketPosition == MarketPosition.Long)
			{
				if (!_userMovedStop)
				{
					// set BEFORE submitting so a strategy-driven stop move is never mistaken
					// for a user drag when OnOrderUpdate fires back with the new price.
					_stratSetStop = _curStop;
					ExitLongStopMarket(0, true, Position.Quantity, _curStop, "Stop", "Wedge");
				}
				if (ScalpQty > 0 && !_scalpDone)
					ExitLongLimit(0, true, ScalpQty, _entry + ScalpTargetTicks * TickSize, "Scalp", "Wedge");
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				if (!_userMovedStop)
				{
					_stratSetStop = _curStop;
					ExitShortStopMarket(0, true, Position.Quantity, _curStop, "Stop", "Wedge");
				}
				if (ScalpQty > 0 && !_scalpDone)
					ExitShortLimit(0, true, ScalpQty, _entry - ScalpTargetTicks * TickSize, "Scalp", "Wedge");
			}
		}

		protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity,
			int filled, double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment)
		{
			if (order == null) return;
			// track the actual live protective-stop price so a manual drag is detectable
			if (order.Name == "Stop" && stopPrice > 0)
			{
				_liveStopPrice = stopPrice;

				// Immediate manual-drag detection (realtime, doesn't wait for the next bar
				// close): if the live stop diverged from what the strategy last commanded,
				// the user dragged it -> hand off + snap the R:R risk box now.
				if (!_userMovedStop && _stratSetStop > 0
					&& Math.Abs(_liveStopPrice - _stratSetStop) > TickSize / 2
					&& Position.MarketPosition != MarketPosition.Flat)
				{
					_userMovedStop = true;
					_curStop = _liveStopPrice;
					Print(ST + " " + time + "  manual stop @ " + _liveStopPrice + " -> auto-stop OFF for this trade");
				}

				// Redraw the R:R so a stop drag (or any stop-price change) reflects live.
				if (Position.MarketPosition != MarketPosition.Flat)
					DrawTradeVisuals(Position.MarketPosition == MarketPosition.Long);
			}

			// Entry lifecycle: an entry either FILLS (a trade) or CANCELS — never both.
			// Only mark Ecancel / reset on the CONFIRMED cancel state; a fill is handled in
			// OnExecutionUpdate. This removes the SUB -> Ecancel -> FILL race.
			if (order.Name == "Wedge")
			{
				if (order.OrderState == OrderState.Cancelled)
				{
					Print(ST + " " + time + "  entry CANCEL confirmed (" + (_pendingSide > 0 ? "LONG" : "SHORT") + ")");
					if (DebugDraw) Draw.Text(this, "elap" + order.OrderId, "Ecancel", 0, High[0] + 6 * TickSize);
					_pendingSide = 0; _entryOrder = null;
				}
				else if (order.OrderState == OrderState.Filled)
					_entryOrder = null;   // it's a trade now — OnExecutionUpdate inits it
				else if (order.OrderState == OrderState.Working || order.OrderState == OrderState.Accepted)
					_entryOrder = order;  // capture the resting entry so we can cancel it precisely
			}
		}

		protected override void OnExecutionUpdate(Execution execution, string executionId, double price,
			int quantity, Cbi.MarketPosition marketPosition, string orderId, DateTime time)
		{
			if (execution.Order == null || Position.MarketPosition == MarketPosition.Flat)
				return;
			string nm = execution.Order.Name;
			if (nm == "Wedge")
			{
				if (_entry == 0)
				{
					_entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; _entryBar = CurrentBar;
					_stratSetStop = 0; _liveStopPrice = 0; _userMovedStop = false;
					Print(ST + " " + time + "  FILLED entry x" + quantity + " @ " + price + "  -> stop@" + _curStop);
					// No custom FILL marker: Bars.GetBar(time) is unreliable on a tick chart
					// (many bars share a timestamp) so it lands on the wrong bar. NT's own
					// entry arrow already marks the exact fill bar.
				}
				ManageProtection();
			}
			else if (nm == "Scalp")
			{
				// scalp scaled out -> never re-scalp; drop stop to remaining qty now
				_scalpDone = true;
				Print(ST + " " + time + "  SCALP filled x" + quantity + " @ " + price + "  runner left x" + Position.Quantity);
				ManageProtection();
			}
			else if (nm == "Stop" || nm == "StopFail")
			{
				Print(ST + " " + time + "  " + nm + " filled x" + quantity + " @ " + price);
			}
		}

		#region Trade structure properties

		// ── 1. Position Sizing ──────────────────────────────────────────────
		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Scalp contracts (0 = no scalp)", GroupName = "1. Position Sizing", Order = 0)]
		public int ScalpQty { get; set; }

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Runner contracts (0 = no runner)", GroupName = "1. Position Sizing", Order = 1)]
		public int RunnerQty { get; set; }

		// ── 2. Entry ────────────────────────────────────────────────────────
		[NinjaScriptProperty]
		[Range(1, 100)]
		[Display(Name = "Stop/entry offset beyond SB (ticks)", GroupName = "2. Entry", Order = 0)]
		public int StopBeyondSBTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 100)]
		[Display(Name = "Entry valid for N bars", GroupName = "2. Entry", Order = 1)]
		public int EntryValidBars { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Inside-bar SB: stop beyond prior bar", GroupName = "2. Entry", Order = 2)]
		public bool InsideBarUsePriorBar { get; set; }

		// ── 3. Scalp Target ─────────────────────────────────────────────────
		[NinjaScriptProperty]
		[Range(1, 1000)]
		[Display(Name = "Scalp target (ticks)", GroupName = "3. Scalp Target", Order = 0)]
		public int ScalpTargetTicks { get; set; }

		// ── 4. Runner / Breakeven ───────────────────────────────────────────
		[NinjaScriptProperty]
		[Range(1, 1000)]
		[Display(Name = "Breakeven trigger (ticks)", GroupName = "4. Runner / Breakeven", Order = 0)]
		public int BETriggerTicks { get; set; }

		[NinjaScriptProperty]
		[Range(-1000, 1000)]
		[Display(Name = "Breakeven lock offset (ticks, ± entry)", GroupName = "4. Runner / Breakeven", Order = 1)]
		public int BEOffsetTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 1000)]
		[Display(Name = "Runner trail beyond bar (ticks)", GroupName = "4. Runner / Breakeven", Order = 2)]
		public int TrailTicks { get; set; }

		// ── 5. Chart Visuals ────────────────────────────────────────────────
		[NinjaScriptProperty]
		[Display(Name = "Show risk/reward boxes + R multiple", GroupName = "5. Chart Visuals", Order = 0)]
		public bool ShowRiskReward { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show breakeven-trigger line", GroupName = "5. Chart Visuals", Order = 1)]
		public bool ShowBELine { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Debug draw (signals + entry/exit lifecycle)", GroupName = "5. Chart Visuals", Order = 2)]
		public bool DebugDraw { get; set; }
		#endregion

		#region MyWedge properties
		[NinjaScriptProperty]
		[Range(1, 10000)]
		[Display(Name = "LookBack", GroupName = "6. MyWedge Settings", Order = 0)]
		public int LookBack { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ShowW2L", GroupName = "6. MyWedge Settings", Order = 1)]
		public bool ShowW2L { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10000)]
		[Display(Name = "WedgeSymmetry", GroupName = "6. MyWedge Settings", Order = 2)]
		public int WedgeSymmetry { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10000)]
		[Display(Name = "OLSensitivity", GroupName = "6. MyWedge Settings", Order = 3)]
		public int OLSensitivity { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "CTSB_Ignore", GroupName = "6. MyWedge Settings", Order = 4)]
		public bool CTSB_Ignore { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "IB_Ignore", GroupName = "6. MyWedge Settings", Order = 5)]
		public bool IB_Ignore { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ShowWedgeSB", GroupName = "6. MyWedge Settings", Order = 6)]
		public bool ShowWedgeSB { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "SignalBarIBS", GroupName = "6. MyWedge Settings", Order = 7)]
		public double SignalBarIBS { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ContinueMC", GroupName = "6. MyWedge Settings", Order = 8)]
		public bool ContinueMC { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ContinueOnGap", GroupName = "6. MyWedge Settings", Order = 9)]
		public bool ContinueOnGap { get; set; }
		#endregion
	}
}
