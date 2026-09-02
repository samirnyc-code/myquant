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
	//  after going flat is taken.
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

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description  = "MyWedge signal-bar scalper V2: single sized entry, all-manual exits, immediate stop on fill, no re-scalp.";
				Name         = "WedgeScalperV2";
				Calculate    = Calculate.OnBarClose;
				EntriesPerDirection = 1;                       // single "Wedge" entry
				EntryHandling = EntryHandling.AllEntries;
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds    = 30;
				BarsRequiredToTrade          = 20;
				IsUnmanaged                  = false;

				// ── trade structure ────────────────────────────────────────────
				ScalpQty          = 1;   // 0 = no scalp lot
				RunnerQty         = 1;   // 0 = no runner lot
				StopBeyondSBTicks = 1;
				ScalpTargetTicks  = 4;
				BETriggerTicks    = 5;
				TrailTicks        = 1;
				EntryValidBars    = 1;
				TrailFromEntry    = false;   // true: runner trails from entry, BE floor after trigger

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
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < BarsRequiredToTrade || _wedge == null)
				return;

			_wedge.Update();
			double tick = TickSize;

			if (Position.MarketPosition == MarketPosition.Flat)
			{
				// reset any leftover open-trade state
				_entry = 0; _beActive = false; _curStop = 0; _scalpDone = false;

				// ── detect a new signal ────────────────────────────────────────
				if (_pendingSide == 0)
				{
					if (_wedge.WedgeBLSB[0] > 0)
					{
						_pendingSide = 1; _sigBar = CurrentBar;
						_entryPx = High[0] + StopBeyondSBTicks * tick;
						_stopPx  = Low[0]  - StopBeyondSBTicks * tick;
					}
					else if (_wedge.WedgeBRSB[0] > 0)
					{
						_pendingSide = -1; _sigBar = CurrentBar;
						_entryPx = Low[0]  - StopBeyondSBTicks * tick;
						_stopPx  = High[0] + StopBeyondSBTicks * tick;
					}
				}

				// ── submit ONE sized entry while valid, else let it lapse ──────
				if (_pendingSide != 0)
				{
					if (CurrentBar - _sigBar < EntryValidBars)
					{
						// Single entry sized to the whole position (fix #1). Exits are
						// ALL manual (fix #2) — do NOT add a Set method or NT drops the
						// manual scalp limit. isLiveUntilCancelled = FALSE so an unfilled
						// entry auto-expires next bar rather than filling later against a
						// stale stop (fix #5).
						int totQ = ScalpQty + RunnerQty;
						if (totQ > 0)
						{
							if (_pendingSide == 1)
								EnterLongStopMarket(0, false, totQ, _entryPx, "Wedge");
							else
								EnterShortStopMarket(0, false, totQ, _entryPx, "Wedge");
						}
					}
					else
					{
						// past validity, still flat -> cancel the working entry
						foreach (Order o in Orders)
							if (o.OrderState == OrderState.Working && o.Name == "Wedge")
								CancelOrder(o);
						_pendingSide = 0;
					}
				}
				return;
			}

			// ── manage an open position (per-bar trail) ───────────────────────
			// The stop is already live from the fill (OnExecutionUpdate). Here we
			// only move _curStop (BE / trail) and re-submit via ManageProtection().
			if (Position.MarketPosition == MarketPosition.Long)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; }

				// runner trail moves the whole-position stop up once the scalp is out
				if (RunnerQty > 0)
				{
					if (TrailFromEntry)
					{
						_curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick);   // trail from entry
						if (High[0] >= _entry + BETriggerTicks * tick)
							_curStop = Math.Max(_curStop, _entry);                   // BE floor after X ticks
					}
					else
					{
						if (!_beActive && High[0] >= _entry + BETriggerTicks * tick) _beActive = true;
						if (_beActive)
						{
							_curStop = Math.Max(_curStop, _entry);                    // breakeven
							_curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick); // 1t/bar trail
						}
					}
				}
				ManageProtection();      // trail the stop (scalp already handled; won't re-scalp)
				if (Close[0] <= _curStop)
					ExitLong("StopFail", "Wedge");   // safety net (fix #6)
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; }

				if (RunnerQty > 0)
				{
					if (TrailFromEntry)
					{
						_curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);
						if (Low[0] <= _entry - BETriggerTicks * tick)
							_curStop = Math.Min(_curStop, _entry);
					}
					else
					{
						if (!_beActive && Low[0] <= _entry - BETriggerTicks * tick) _beActive = true;
						if (_beActive)
						{
							_curStop = Math.Min(_curStop, _entry);
							_curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);
						}
					}
				}
				ManageProtection();
				if (Close[0] >= _curStop)
					ExitShort("StopFail", "Wedge");
			}
		}

		// Places/updates the whole-position stop and (once) the scalp target. Called
		// both from OnBarUpdate (per-bar trail) and OnExecutionUpdate (immediate on
		// fills) so the stop is live the instant we fill and its qty drops as soon as
		// the scalp scales out — not a bar later (fix #3, #4).
		private void ManageProtection()
		{
			if (Position.MarketPosition == MarketPosition.Long)
			{
				ExitLongStopMarket(0, true, Position.Quantity, _curStop, "Stop", "Wedge");
				if (ScalpQty > 0 && !_scalpDone)
					ExitLongLimit(0, true, ScalpQty, _entry + ScalpTargetTicks * TickSize, "Scalp", "Wedge");
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				ExitShortStopMarket(0, true, Position.Quantity, _curStop, "Stop", "Wedge");
				if (ScalpQty > 0 && !_scalpDone)
					ExitShortLimit(0, true, ScalpQty, _entry - ScalpTargetTicks * TickSize, "Scalp", "Wedge");
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
				// entry just filled -> lock entry price and protect IMMEDIATELY (fix #3)
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; }
				ManageProtection();
			}
			else if (nm == "Scalp")
			{
				// scalp scaled out -> never re-scalp (fix #4); drop stop to remaining qty now
				_scalpDone = true;
				ManageProtection();
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
