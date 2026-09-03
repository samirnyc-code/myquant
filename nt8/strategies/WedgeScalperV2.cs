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
	// WedgeScalperV2 — renamed from WedgeScalper.  CHANGE LOG (2026-09-02 / S107)
	// ══════════════════════════════════════════════════════════════════════════
	// Today's fixes, in order they were found while debugging in the Analyzer:
	//
	//  1. SINGLE SIZED ENTRY (ScalpQty+RunnerQty) instead of two same-price entries.
	//     Two separate stop entries at the same price did NOT both fill in backtest,
	//     so the runner quantity had no effect (100 vs 1 runners gave identical P&L).
	//
	//  2. ALL-MANUAL EXITS. A Set method (SetStopLoss/SetProfitTarget) mixed with a
	//     manual ExitLimit made NinjaTrader SILENTLY DROP the manual scalp limit, so
	//     the +target never fired and winners ran to the session close (11% win rate,
	//     huge MFE). Stop AND scalp target are now both plain managed orders.
	//
	//  3. IMMEDIATE PROTECTION via OnExecutionUpdate. With Calculate.OnBarClose the
	//     stop used to be placed a full bar after the fill. Now the stop is submitted
	//     the instant the entry fills, and the instant the scalp scales out the stop
	//     is resized to the remaining runner quantity — not a bar later.
	//
	//  4. NO RE-SCALP. _scalpDone latches when the scalp fills so the runner is never
	//     scaled out a second time (that stray exit was the bogus "2nd target").
	//
	//  5. ENTRY AUTO-EXPIRES. Entry order isLiveUntilCancelled = FALSE so an unfilled
	//     entry lapses next bar instead of lingering and later filling against a stale
	//     stop price (which left the stop on the wrong side -> runaway losers).
	//
	//  6. HARD SAFETY NET. If a bar CLOSES beyond the current stop while still in the
	//     position, force a market exit ("StopFail") — bounds any resting-stop leak.
	//
	//  7. FLEXIBILITY. Scalp/Runner contracts may be 0 (0 disables that lot); added
	//     "Runner: trail from entry" mode; LookBack default set to 12.
	//
	//  Behaviour note: ONE POSITION AT A TIME. A wedge that fires while a trade is
	//  open is IGNORED — no reverse, no pyramiding, no queueing. Only the first wedge
	//  after going flat is taken (EXCEPT RunnerHoldToOpposite mode, which reverses).
	//
	//  ── 2026-09-03 (S107 cont) reversal + trail fixes ──
	//  8. REVERSAL NOW ACTUALLY FLIPS. The managed approach attaches exits by entry
	//     name; submitting an opposite entry under the SAME name that already holds
	//     the position was ignored, so the runner never reversed (rode thousands of
	//     bars into "Close position"/"Exit on session close"). Reversals now use a
	//     DISTINCT name, alternating "Wedge" <-> "WedgeRev" (_entryName/_revName); all
	//     exits (Stop/Scalp/StopFail) re-point to whichever name holds the position.
	//     Reversal size = current qty + (Scalp+Runner) so the new side carries a FULL
	//     fresh trade, not just the leftover runner qty.
	//  9. TrailWhileHolding toggle. In RunnerHoldToOpposite mode the runner defaults
	//     to BE-and-hold (no trail). TrailWhileHolding = true ALSO trails 1t/bar while
	//     the reversal stays armed, so a runaway winner keeps locking gains instead of
	//     round-tripping to breakeven.
	// 10. FILLS: RUN WITH TICK REPLAY *OFF*, Calculate.OnBarClose. Verified in the Analyzer:
	//     Tick Replay ON drags resting-stop fills PAST the stop price (Orders grid showed
	//     correct Stop col but Avg fill beyond it); Tick Replay OFF fills the stop AT its
	//     price via the standard bar model. An OnEachTick+TickReplay attempt (and a
	//     1-second helper series) were tried to get intrabar breakeven and REVERTED — they
	//     inherited the Tick-Replay fill breakage. Intrabar BE is deferred to a separate
	//     live-only change; the backtest stays on OnBarClose+[0] with Tick Replay OFF.
	// 11. BEOffsetTicks (signed). Where the stop locks once BE arms: entry ± offset.
	//     +4 on ES locks in 1 point; 0 = pure breakeven; negative leaves room past entry.
	//     BETriggerTicks stays the ARM threshold; BEOffsetTicks is the LOCK level.
	// ══════════════════════════════════════════════════════════════════════════
	//
	// Automated MyWedge scalper. Hosts the black-box MyWedge indicator and trades
	// its signal bars (WedgeBLSB > 0 = long, WedgeBRSB > 0 = short):
	//
	//   ENTRY   ONE stop order sized (ScalpQty + RunnerQty), 1t beyond the SB:
	//             long  = SB.High + StopBeyondSBTicks   (buy stop)
	//             short = SB.Low  - StopBeyondSBTicks   (sell stop)
	//           valid EntryValidBars bar(s), else it lapses.
	//   STOP    whole-position protective stop 1t beyond the OTHER side of the SB:
	//             long  = SB.Low  - StopBeyondSBTicks
	//             short = SB.High + StopBeyondSBTicks
	//   SCALP   ScalpQty contracts exit at +ScalpTargetTicks (limit, scaled out once).
	//   RUNNER  the remainder has no target. At +BETriggerTicks the stop jumps to
	//           BREAKEVEN, then trails 1t beyond each closed bar (favourable-only).
	//           TrailFromEntry = true instead trails from entry with BE as a floor.
	//
	// Managed orders, all manual (no Set methods — see fix #2). Calculate.OnBarClose
	// drives the per-bar trail; OnExecutionUpdate handles the immediate-on-fill work.
	//
	// The 10 MyWedge params are exposed below and MUST match the MyWedge instance on
	// your chart (LookBack 12, etc.), or the strategy trades different signals.
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
		// reversal arm (RunnerHoldToOpposite): an opposite-side entry that flips the
		// position only if its stop-entry price actually triggers.
		private int    _revSide;       // 0 none, 1 long, -1 short
		private int    _revSigBar;
		private double _revEntryPx;
		private double _revStopPx;
		// manual stop override (value-comparison, per @@MCScaleInStrategy):
		private double _stratSetStop;   // last stop price the STRATEGY commanded
		private double _liveStopPrice;  // actual live "Stop" order price (from OnOrderUpdate)
		private bool   _userMovedStop;  // user dragged the stop -> strategy hands off for this trade
		// entry/reversal signal names. The managed approach attaches exits by entry name,
		// so a reversal MUST use a name different from the one currently holding the
		// position (submitting an opposite "Wedge" while a "Wedge" position is live gets
		// ignored -> no flip). We alternate "Wedge" <-> "WedgeRev" on each reversal.
		private string _entryName = "Wedge";  // signal name currently holding the position
		private string _revName;              // signal name of the armed reversal entry

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description  = "MyWedge signal-bar scalper V2: single sized entry, all-manual exits, immediate stop on fill, no re-scalp.";
				Name         = "WedgeScalperV2";
				// ⚠ RUN WITH TICK REPLAY *OFF*. With Tick Replay ON the historical fill
				// engine drags resting-stop fills past the stop price (verified in the
				// Analyzer: Stop col correct, Avg fill beyond it). Tick Replay OFF uses the
				// standard bar fill model, which fills a stop AT the stop price. OnBarClose
				// keeps signal/entry logic reading the just-closed bar [0] unambiguously.
				Calculate    = Calculate.OnBarClose;
				// UniqueEntries: count entries per SIGNAL NAME, so the reversal ("WedgeRev")
				// is not blocked by the entry already held under "Wedge". AllEntries sums both
				// names against one per-direction limit, which can make the managed approach
				// ignore the opposite reversal entry (the flip silently never fires).
				EntriesPerDirection = 1;
				EntryHandling = EntryHandling.UniqueEntries;
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
				ScalpTargetTicks  = 4;
				BETriggerTicks    = 5;    // price must reach entry ± this to ARM breakeven
				BEOffsetTicks     = 0;    // where the stop locks once armed: entry ± this (signed).
				                          //   +4 on ES = lock in 1 point; negative = leave room below/above entry.
				TrailTicks        = 1;
				EntryValidBars    = 1;
				TrailFromEntry    = false;   // true: runner trails from entry, BE floor after trigger
				RunnerHoldToOpposite = false; // runner holds until an OPPOSITE entry triggers (stop-and-reverse)
				TrailWhileHolding = false;   // (hold-to-opposite only) ALSO trail 1t/bar while the reversal is armed
				DebugDraw         = true;    // draw the strategy's OWN signals + entry/reversal lifecycle on the chart

				// ── MyWedge ctor params — SET TO MATCH YOUR CHART ──────────────
				LookBack       = 12;     // confirmed correct (S107)
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

		// entry orders alternate between these two names across reversals (see _entryName)
		private static bool IsEntryOrder(string name) { return name == "Wedge" || name == "WedgeRev"; }

		protected override void OnBarUpdate()
		{
			if (_wedge == null || CurrentBar < BarsRequiredToTrade)
				return;

			_wedge.Update();
			double tick = TickSize;

			// Diagnostics: draw the STRATEGY's own MyWedge signals (cyan up / orange down).
			// If these line up with the chart's MyWedge triangles, params match.
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
				_entryName = "Wedge";   // fresh trade -> base entry name
				if (_revSide != 0)      // stopped out before a reversal triggered -> drop the arm
				{
					foreach (Order o in Orders)
						if (o.OrderState == OrderState.Working && IsEntryOrder(o.Name)) CancelOrder(o);
					_revSide = 0; _revName = null;
				}

				// ── detect a NEW signal on the just-closed bar [0] and rest ONE entry ──
				// Submitted isLiveUntilCancelled = TRUE so the stop rests and fills when
				// price crosses it; cancelled only after the validity window passes.
				if (_pendingSide == 0)
				{
					int side = 0;
					if (_wedge.WedgeBLSB[0] > 0) side = 1;
					else if (_wedge.WedgeBRSB[0] > 0) side = -1;
					if (side != 0)
					{
						_pendingSide = side; _sigBar = CurrentBar;
						if (side == 1) { _entryPx = High[0] + StopBeyondSBTicks * tick; _stopPx = Low[0]  - StopBeyondSBTicks * tick; }
						else           { _entryPx = Low[0]  - StopBeyondSBTicks * tick; _stopPx = High[0] + StopBeyondSBTicks * tick; }
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
								+ "  rest x" + totQ + " entry@" + _entryPx + " protStop@" + _stopPx);
							if (DebugDraw) Draw.Text(this, "sub" + CurrentBar, "SUB@" + _entryPx,
								0, side > 0 ? High[0] + 6 * tick : Low[0] - 6 * tick);
						}
					}
				}
				else if (CurrentBar - _sigBar > EntryValidBars)
				{
					foreach (Order o in Orders)   // window passed unfilled -> cancel the resting entry
						if (o.OrderState == OrderState.Working && IsEntryOrder(o.Name)) CancelOrder(o);
					Print(ST + " " + Time[0] + "  entry LAPSED unfilled ("
						+ (_pendingSide > 0 ? "LONG" : "SHORT") + ")  entry@" + _entryPx);
					if (DebugDraw) Draw.Text(this, "elap" + CurrentBar, "Ecancel", 0, High[0] + 6 * tick);
					_pendingSide = 0;
				}
				return;
			}

			// ══════════════════════ OPEN POSITION ══════════════════════
			int  oppSide = Position.MarketPosition == MarketPosition.Long ? -1 : 1;
			bool oppSig  = oppSide == 1 ? _wedge.WedgeBLSB[0] > 0 : _wedge.WedgeBRSB[0] > 0;

			if (RunnerHoldToOpposite)
			{
				// The managed approach will NOT rest an opposite entry while a position is
				// open (confirmed: the reversal stop order was never even created, across
				// distinct-name / UniqueEntries / cancel-exits attempts). But a MARKET
				// opposite entry DOES reverse cleanly. So: arm on the opposite signal, then
				// when price breaks 1t past the opposite SB (same trigger a stop would use),
				// flip at MARKET. Trade-off: the reversal fills at that bar's close (~1t past
				// the trigger), not exactly at the trigger like a resting stop would.
				if (oppSig && _revSide == 0)
				{
					_revSide = oppSide; _revSigBar = CurrentBar;
					_revName = _entryName == "Wedge" ? "WedgeRev" : "Wedge";
					if (oppSide == 1) { _revEntryPx = High[0] + StopBeyondSBTicks * tick; _revStopPx = Low[0]  - StopBeyondSBTicks * tick; }
					else              { _revEntryPx = Low[0]  - StopBeyondSBTicks * tick; _revStopPx = High[0] + StopBeyondSBTicks * tick; }
					// HOLD means hold: cancel the resting stop/scalp now so it can't fill
					// intrabar and take us flat before the opposite breakout fires the flip.
					foreach (Order o in Orders)
						if (o.OrderState == OrderState.Working && (o.Name == "Stop" || o.Name == "Scalp")) CancelOrder(o);
					Print(ST + " " + Time[0] + "  REVERSAL armed " + (oppSide > 0 ? "LONG" : "SHORT") + "  trigger@" + _revEntryPx);
					if (DebugDraw) Draw.Text(this, "rarm" + CurrentBar, "REVarm@" + _revEntryPx,
						0, oppSide > 0 ? High[0] + 8 * tick : Low[0] - 8 * tick);
				}
				else if (_revSide != 0)
				{
					bool triggered = _revSide == 1 ? High[0] >= _revEntryPx : Low[0] <= _revEntryPx;
					if (triggered)
					{
						int revQ = Position.Quantity + ScalpQty + RunnerQty;   // close current + full fresh trade
						if (_revSide == 1) EnterLong (revQ, _revName);
						else               EnterShort(revQ, _revName);
						Print(ST + " " + Time[0] + "  REVERSAL TRIGGERED -> market " + (_revSide > 0 ? "LONG" : "SHORT")
							+ " x" + revQ + " (" + _revName + ")");
						return;   // let the fill flip us (OnExecutionUpdate re-inits); skip this bar's stop mgmt
					}
					else if (CurrentBar - _revSigBar > EntryValidBars)
					{
						if (DebugDraw) Draw.Text(this, "rlap" + CurrentBar, "REVcancel", 0, High[0] + 8 * tick);
						_revSide = 0; _revName = null;   // window passed without a break -> stay in
					}
				}
			}
			else if (oppSig || _wedge.WedgeBLSB[0] > 0 || _wedge.WedgeBRSB[0] > 0)
			{
				Print(ST + " " + Time[0] + "  signal IGNORED — already in "
					+ Position.MarketPosition + " x" + Position.Quantity + " (one position at a time)");
			}

			// ── stop management (per closed bar) ──
			if (Position.MarketPosition == MarketPosition.Long)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; }

				if (RunnerQty > 0 && !_userMovedStop)   // skip auto-trail once the user drags the stop
				{
					if (RunnerHoldToOpposite)
					{
						// HOLD for the reversal: BE (± offset) after the trigger, then hold there
						// (no trail) unless TrailWhileHolding also ratchets 1t/bar.
						if (!_beActive && High[0] >= _entry + BETriggerTicks * tick) _beActive = true;
						if (_beActive)
						{
							_curStop = Math.Max(_curStop, _entry + BEOffsetTicks * tick);
							if (TrailWhileHolding) _curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick);
						}
					}
					else if (TrailFromEntry)
					{
						_curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick);                   // trail from entry
						if (High[0] >= _entry + BETriggerTicks * tick)
							_curStop = Math.Max(_curStop, _entry + BEOffsetTicks * tick);            // BE floor (± offset)
					}
					else
					{
						if (!_beActive && High[0] >= _entry + BETriggerTicks * tick) _beActive = true;
						if (_beActive)
						{
							_curStop = Math.Max(_curStop, _entry + BEOffsetTicks * tick);            // BE (± offset)
							_curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick);              // 1t/bar trail
						}
					}
				}
				ManageProtection();
				if (Close[0] <= _curStop) ExitLong("StopFail", _entryName);   // safety net (fix #6)
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; }

				if (RunnerQty > 0 && !_userMovedStop)
				{
					if (RunnerHoldToOpposite)
					{
						if (!_beActive && Low[0] <= _entry - BETriggerTicks * tick) _beActive = true;
						if (_beActive)
						{
							_curStop = Math.Min(_curStop, _entry - BEOffsetTicks * tick);
							if (TrailWhileHolding) _curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);
						}
					}
					else if (TrailFromEntry)
					{
						_curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);
						if (Low[0] <= _entry - BETriggerTicks * tick)
							_curStop = Math.Min(_curStop, _entry - BEOffsetTicks * tick);
					}
					else
					{
						if (!_beActive && Low[0] <= _entry - BETriggerTicks * tick) _beActive = true;
						if (_beActive)
						{
							_curStop = Math.Min(_curStop, _entry - BEOffsetTicks * tick);
							_curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);
						}
					}
				}
				ManageProtection();
				if (Close[0] >= _curStop) ExitShort("StopFail", _entryName);
			}
		}

		// Places/updates the whole-position stop and (once) the scalp target. Called
		// both from OnBarUpdate (per-bar trail) and OnExecutionUpdate (immediate on
		// fills) so the stop is live the instant we fill and its qty drops as soon as
		// the scalp scales out — not a bar later (fix #3, #4).
		private void ManageProtection()
		{
			// Manual override: if the live stop price diverged from what we last set, the
			// user dragged it -> hand off the stop for the rest of this trade (adopt their
			// level, stop auto-managing it). The scalp target is untouched by this.
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
					ExitLongStopMarket(0, true, Position.Quantity, _curStop, "Stop", _entryName);
					_stratSetStop = _curStop;
				}
				if (ScalpQty > 0 && !_scalpDone)
					ExitLongLimit(0, true, ScalpQty, _entry + ScalpTargetTicks * TickSize, "Scalp", _entryName);
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				if (!_userMovedStop)
				{
					ExitShortStopMarket(0, true, Position.Quantity, _curStop, "Stop", _entryName);
					_stratSetStop = _curStop;
				}
				if (ScalpQty > 0 && !_scalpDone)
					ExitShortLimit(0, true, ScalpQty, _entry - ScalpTargetTicks * TickSize, "Scalp", _entryName);
			}
		}

		protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity,
			int filled, double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment)
		{
			// track the actual live protective-stop price so a manual drag is detectable
			if (order != null && order.Name == "Stop" && stopPrice > 0)
				_liveStopPrice = stopPrice;
		}

		protected override void OnExecutionUpdate(Execution execution, string executionId, double price,
			int quantity, Cbi.MarketPosition marketPosition, string orderId, DateTime time)
		{
			if (execution.Order == null || Position.MarketPosition == MarketPosition.Flat)
				return;
			string nm = execution.Order.Name;
			if (IsEntryOrder(nm))
			{
				// A reversal fill flips the position -> re-init the trade with the
				// reversal's SB stop (the normal _entry==0 guard won't fire because the
				// OLD side's _entry is still non-zero). Detect it by the reversal's
				// distinct name landing us on the armed side.
				bool reversed = _revSide != 0 && nm == _revName &&
					((_revSide == 1 && Position.MarketPosition == MarketPosition.Long) ||
					 (_revSide == -1 && Position.MarketPosition == MarketPosition.Short));
				if (reversed)
				{
					_stopPx = _revStopPx; _revSide = 0;
					_entryName = _revName; _revName = null;   // the reversal name now HOLDS the position
					_entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false;
					_stratSetStop = 0; _liveStopPrice = 0; _userMovedStop = false;   // new trade -> auto-stop on
					Print(ST + " " + time + "  REVERSED -> now " + Position.MarketPosition
						+ " x" + Position.Quantity + " (" + _entryName + ")  stop@" + _curStop);
					if (DebugDraw)
					{
						int ba = Math.Max(0, CurrentBar - Bars.GetBar(time));   // fill bar from execution time
						Draw.Text(this, "rvd" + executionId, "REVERSED " + Position.MarketPosition, ba,
							Position.MarketPosition == MarketPosition.Long ? Low[ba] - 10 * TickSize : High[ba] + 10 * TickSize);
					}
				}
				else if (_entry == 0)
				{
					_entryName = nm;   // fresh entry from flat -> this name holds the position
					_entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0;
					_stratSetStop = 0; _liveStopPrice = 0; _userMovedStop = false;
					Print(ST + " " + time + "  FILLED entry x" + quantity + " @ " + price + "  -> stop@" + _curStop);
					if (DebugDraw)
					{
						int ba = Math.Max(0, CurrentBar - Bars.GetBar(time));   // fill bar from execution time
						Draw.Text(this, "fil" + executionId, "FILL@" + price, ba,
							Position.MarketPosition == MarketPosition.Long ? Low[ba] - 6 * TickSize : High[ba] + 6 * TickSize);
					}
				}
				ManageProtection();
			}
			else if (nm == "Scalp")
			{
				// scalp scaled out -> never re-scalp (fix #4); drop stop to remaining qty now
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
		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Scalp contracts (0 = no scalp)", GroupName = "1. Trade Structure", Order = 0)]
		public int ScalpQty { get; set; }

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Runner contracts (0 = no runner)", GroupName = "1. Trade Structure", Order = 1)]
		public int RunnerQty { get; set; }

		[NinjaScriptProperty]
		[Range(1, 100)]
		[Display(Name = "Stop/entry offset beyond SB (ticks)", GroupName = "1. Trade Structure", Order = 2)]
		public int StopBeyondSBTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 1000)]
		[Display(Name = "Scalp target (ticks)", GroupName = "1. Trade Structure", Order = 3)]
		public int ScalpTargetTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 1000)]
		[Display(Name = "Breakeven trigger (ticks)", GroupName = "1. Trade Structure", Order = 4)]
		public int BETriggerTicks { get; set; }

		[NinjaScriptProperty]
		[Range(-1000, 1000)]
		[Display(Name = "Breakeven lock offset (ticks, ± entry)", GroupName = "1. Trade Structure", Order = 5)]
		public int BEOffsetTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 1000)]
		[Display(Name = "Runner trail beyond bar (ticks)", GroupName = "1. Trade Structure", Order = 5)]
		public int TrailTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 100)]
		[Display(Name = "Entry valid for N bars", GroupName = "1. Trade Structure", Order = 6)]
		public int EntryValidBars { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Runner: trail from entry (BE after trigger)", GroupName = "1. Trade Structure", Order = 7)]
		public bool TrailFromEntry { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Runner holds until opposite entry triggers", GroupName = "1. Trade Structure", Order = 8)]
		public bool RunnerHoldToOpposite { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Hold-to-opposite: also trail while armed", GroupName = "1. Trade Structure", Order = 9)]
		public bool TrailWhileHolding { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Debug draw (signals + entry/reversal lifecycle)", GroupName = "1. Trade Structure", Order = 10)]
		public bool DebugDraw { get; set; }
		#endregion

		#region MyWedge properties
		[NinjaScriptProperty]
		[Range(1, 10000)]
		[Display(Name = "LookBack", GroupName = "2. MyWedge Settings", Order = 0)]
		public int LookBack { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ShowW2L", GroupName = "2. MyWedge Settings", Order = 1)]
		public bool ShowW2L { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10000)]
		[Display(Name = "WedgeSymmetry", GroupName = "2. MyWedge Settings", Order = 2)]
		public int WedgeSymmetry { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10000)]
		[Display(Name = "OLSensitivity", GroupName = "2. MyWedge Settings", Order = 3)]
		public int OLSensitivity { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "CTSB_Ignore", GroupName = "2. MyWedge Settings", Order = 4)]
		public bool CTSB_Ignore { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "IB_Ignore", GroupName = "2. MyWedge Settings", Order = 5)]
		public bool IB_Ignore { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ShowWedgeSB", GroupName = "2. MyWedge Settings", Order = 6)]
		public bool ShowWedgeSB { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "SignalBarIBS", GroupName = "2. MyWedge Settings", Order = 7)]
		public double SignalBarIBS { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ContinueMC", GroupName = "2. MyWedge Settings", Order = 8)]
		public bool ContinueMC { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ContinueOnGap", GroupName = "2. MyWedge Settings", Order = 9)]
		public bool ContinueOnGap { get; set; }
		#endregion
	}
}
