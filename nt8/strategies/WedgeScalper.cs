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
	// ── WedgeScalper ──────────────────────────────────────────────────────────
	// Automated MyWedge scalper. Hosts the black-box MyWedge indicator and trades
	// its signal bars (WedgeBLSB > 0 = long, WedgeBRSB > 0 = short) with a 2-lot,
	// scale-out + runner structure:
	//
	//   ENTRY   stop order 1t beyond the signal bar (SB):
	//             long  = SB.High + StopBeyondSBTicks       (buy stop)
	//             short = SB.Low  - StopBeyondSBTicks       (sell stop)
	//           valid for EntryValidBars bar(s), else it auto-cancels.
	//   STOP    initial protective stop 1t beyond the OTHER side of the SB:
	//             long  = SB.Low  - StopBeyondSBTicks
	//             short = SB.High + StopBeyondSBTicks
	//           shared by both contracts until the scalp scales out.
	//   SCALP   contract 1 exits at +ScalpTargetTicks (limit).
	//   RUNNER  contract 2 has no target. When price reaches +BETriggerTicks the
	//           runner stop jumps to BREAKEVEN, then trails 1t beyond each closed
	//           bar (long = Low[0]-TrailTicks, short = High[0]+TrailTicks). The
	//           stop only ever ratchets in the favourable direction.
	//
	// Because +ScalpTargetTicks (4) is reached before +BETriggerTicks (5) on the
	// way up, the scalp has always scaled out by the time BE arms, so the runner
	// management naturally applies to the single remaining contract. This is why a
	// single 2-lot entry with quantity-aware exits is correct and avoids the
	// per-leg bookkeeping bugs of two separate entries.
	//
	// Managed orders. Calculate.OnBarClose: the resting stop/limit orders still
	// fill intrabar (tick by tick); only the stop-move LOGIC re-evaluates at each
	// bar close, which is exactly what "trail every bar" means.
	//
	// The 10 MyWedge params are exposed below and MUST match the MyWedge instance
	// you trade / exported with, or the strategy trades different signals.
	public class WedgeScalper : Strategy
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

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description  = "MyWedge signal-bar scalper: stop entry 1t beyond SB, +4t scalp, runner to BE at +5t then 1t/bar trail.";
				Name         = "WedgeScalper";
				Calculate    = Calculate.OnBarClose;
				EntriesPerDirection = 2;                       // scalp + runner, same dir
				EntryHandling = EntryHandling.UniqueEntries;   // manage each by signal name
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds    = 30;
				BarsRequiredToTrade          = 20;
				IsUnmanaged                  = false;

				// ── trade structure ────────────────────────────────────────────
				ScalpQty          = 1;
				RunnerQty         = 1;
				StopBeyondSBTicks = 1;
				ScalpTargetTicks  = 4;
				BETriggerTicks    = 5;
				TrailTicks        = 1;
				EntryValidBars    = 1;

				// ── MyWedge ctor params — SET TO MATCH YOUR CHART ──────────────
				LookBack       = 20;     // confirmed correct (S107)
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
				_entry = 0; _beActive = false; _curStop = 0;

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

				// ── submit the stop entries while still valid, else let them lapse
				// Two independent 1-lot(-ish) entries so each has its OWN clean
				// stop (no oversized-stop / partial-fill mismatch).
				if (_pendingSide != 0)
				{
					if (CurrentBar - _sigBar < EntryValidBars)
					{
						if (_pendingSide == 1)
						{
							EnterLongStopMarket(0, true, ScalpQty,  _entryPx, "LScalp");
							EnterLongStopMarket(0, true, RunnerQty, _entryPx, "LRun");
						}
						else
						{
							EnterShortStopMarket(0, true, ScalpQty,  _entryPx, "SScalp");
							EnterShortStopMarket(0, true, RunnerQty, _entryPx, "SRun");
						}
					}
					else
					{
						// past validity, still flat -> cancel the working entries
						foreach (Order o in Orders)
							if (o.OrderState == OrderState.Working &&
							    (o.Name == "LScalp" || o.Name == "LRun" ||
							     o.Name == "SScalp" || o.Name == "SRun"))
								CancelOrder(o);
						_pendingSide = 0;
					}
				}
				return;
			}

			// ── manage an open position ───────────────────────────────────────
			// Protective stops are submitted isLiveUntilCancelled = true so they
			// REST in the market across bars (the prior bug: default-false orders
			// were cancelled every bar-close and left gaps where price ran away).
			if (Position.MarketPosition == MarketPosition.Long)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _pendingSide = 0; }

				if (!_beActive && High[0] >= _entry + BETriggerTicks * tick)
					_beActive = true;

				if (_beActive)
				{
					_curStop = Math.Max(_curStop, _entry);                    // breakeven
					_curStop = Math.Max(_curStop, Low[0] - TrailTicks * tick); // 1t/bar trail
				}

				// scalp lot: fixed SB stop + target
				ExitLongStopMarket(0, true, ScalpQty, _stopPx, "LScalpStop", "LScalp");
				ExitLongLimit     (0, true, ScalpQty, _entry + ScalpTargetTicks * tick, "LScalpTgt", "LScalp");
				// runner lot: dynamic stop (SB -> BE -> trail)
				ExitLongStopMarket(0, true, RunnerQty, _curStop, "LRunStop", "LRun");
			}
			else if (Position.MarketPosition == MarketPosition.Short)
			{
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _pendingSide = 0; }

				if (!_beActive && Low[0] <= _entry - BETriggerTicks * tick)
					_beActive = true;

				if (_beActive)
				{
					_curStop = Math.Min(_curStop, _entry);
					_curStop = Math.Min(_curStop, High[0] + TrailTicks * tick);
				}

				ExitShortStopMarket(0, true, ScalpQty, _stopPx, "SScalpStop", "SScalp");
				ExitShortLimit     (0, true, ScalpQty, _entry - ScalpTargetTicks * tick, "SScalpTgt", "SScalp");
				ExitShortStopMarket(0, true, RunnerQty, _curStop, "SRunStop", "SRun");
			}
		}

		#region Trade structure properties
		[NinjaScriptProperty]
		[Range(1, 100)]
		[Display(Name = "Scalp contracts", GroupName = "1. Trade Structure", Order = 0)]
		public int ScalpQty { get; set; }

		[NinjaScriptProperty]
		[Range(1, 100)]
		[Display(Name = "Runner contracts", GroupName = "1. Trade Structure", Order = 1)]
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
