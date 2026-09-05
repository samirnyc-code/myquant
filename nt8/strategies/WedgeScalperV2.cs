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

		// Master arm/disarm — shared in-process so the BreakoutBoysDashboard MASTER button can
		// control this strategy (both compile into NinjaTrader.Custom = same process). Default
		// armed so the strategy trades standalone; the dashboard sets it false to disarm NEW
		// entries (open trades keep being managed).
		public static bool MasterArmed = true;

		// Side filter, also dashboard-controllable (LONG / SHORT buttons). Both true = take both.
		// Disallowed-side signals are skipped. Both false = no new entries.
		public static bool MasterAllowLong  = true;
		public static bool MasterAllowShort = true;

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

		// R:R hover tooltip (info box shows only while the cursor is over the R:R boxes)
		private bool   _mouseHooked;
		private bool   _rrHover;
		private int    _rrStartBar = -1;    // left edge (signal/entry bar) for hover hit-test
		private double _rrLoPrice, _rrHiPrice;
		private string _rrText = "";

		// per-trade summary log — one clean stacked block per closed trade (thick-bar separated)
		private int      _tSide;            // +1 long / -1 short / 0 = no open trade logged
		private DateTime _tTime;            // entry time
		private double   _tEntry, _tInitStop;
		private int      _tQty;             // initial position size (for max-risk / R)
		private double   _tTicks, _tUsd;    // running realized result
		private System.Text.StringBuilder _tLegs;

		// running per-DAY scoreboard (resets when the trade date rolls over)
		private DateTime _dayDate = DateTime.MinValue;
		private int      _dayN, _dayWins, _dayLosses;
		private double   _dayUsd, _dayR;

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
				MinRiskReward     = 0.0;      // 0 = off; else skip setups with scalp-tgt:risk worse than this
				MaxSBAbrMult      = 0.0;      // 0 = off; else skip if SB range > avg-bar-range(8) x this
				ScalpTargetTicks  = 4;
				BETriggerTicks    = 5;    // price must reach entry ± this to ARM breakeven
				BEOffsetTicks     = 0;    // where the stop locks once armed: entry ± this (signed, +4 = lock 1pt)
				TrailTicks        = 1;
				EntryValidBars    = 1;

				// ── chart visuals ──────────────────────────────────────────────
				ShowRiskReward    = true;    // green reward box (entry->scalp tgt) + red risk box (entry->initial stop)
				RiskRewardOpacity = 25;      // 0-100 fill opacity of the R:R boxes
				ShowBELine        = true;    // dashed ray (SB->right edge) where the runner locks BE
				BELineBrush       = Brushes.DodgerBlue;   // BE line color (user-settable)
				DebugDraw         = false;   // draw the SUB tag + entry/exit lifecycle prints

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
			else if (State == State.Configure)
			{
				// Set PrintTo here (NOT SetDefaults) so it reliably overrides the strategy
				// instance's serialized value on every load — isolates our Output on Tab2,
				// away from other strategies sharing the global window (e.g. the PB33 dashboard).
				PrintTo = PrintTo.OutputTab2;

				// 1-tick series (BarsInProgress==1) fires every tick -> lets the BE/stop move
				// INTRABAR. The primary series stays OnBarClose so signals/entries/fills are
				// unchanged (no Tick Replay needed). All orders are submitted against series 0.
				AddDataSeries(BarsPeriodType.Tick, 1);
			}
			else if (State == State.DataLoaded)
			{
				_wedge = MyWedge(Input, LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);
			}
			else if (State == State.Historical)
			{
				// Hook mouse-move for the R:R hover tooltip (only when chart-attached).
				if (ChartControl != null && !_mouseHooked)
				{
					ChartControl.Dispatcher.InvokeAsync((Action)(() =>
					{
						ChartPanel.MouseMove += OnChartMouseMove;
						_mouseHooked = true;
					}));
				}
			}
			else if (State == State.Realtime)
			{
				if (DebugDraw) Print("=== WedgeScalperV2 REALTIME: now live. It will ONLY act on NEW "
					+ "signals from here forward — historical signals on the chart are not traded. ===");
			}
			else if (State == State.Terminated)
			{
				if (ChartControl != null && _mouseHooked)
				{
					ChartControl.Dispatcher.InvokeAsync((Action)(() =>
					{
						ChartPanel.MouseMove -= OnChartMouseMove;
					}));
					_mouseHooked = false;
				}
			}
		}

		// ── R:R hover tooltip plumbing ──────────────────────────────────────
		private void OnChartMouseMove(object sender, System.Windows.Input.MouseEventArgs e)
		{
			if (ChartControl == null || ChartPanel == null || !ShowRiskReward) return;
			int mx = (int)e.GetPosition(ChartPanel).X;
			int my = (int)e.GetPosition(ChartPanel).Y;
			bool over = _entry != 0 && _rrStartBar >= 0 && HitTestRR(mx, my);
			if (over != _rrHover)
			{
				_rrHover = over;
				// marshal the Draw call onto the NinjaScript thread
				TriggerCustomEvent((o) => { UpdateHoverText(); ChartControl.InvalidateVisual(); }, null);
			}
		}

		private bool HitTestRR(int x, int y)
		{
			double price = PriceFromY(y);
			if (price < _rrLoPrice || price > _rrHiPrice) return false;
			int xLeft  = ChartControl.GetXByBarIndex(ChartBars, _rrStartBar);
			int xRight = ChartControl.GetXByBarIndex(ChartBars, ChartBars.Count - 1);
			return x >= xLeft - 2 && x <= Math.Max(xLeft, xRight) + 6;
		}

		private double PriceFromY(int y)
		{
			double min = ChartPanel.MinValue, max = ChartPanel.MaxValue;
			return (((ChartPanel.Y + ChartPanel.H) - y) * Math.Max(Math.Abs(max - min), 1E-05)) / ChartPanel.H + min;
		}

		// Add (or remove) the readable info box. Anchored at the right edge of the boxes.
		private void UpdateHoverText()
		{
			if (_rrHover && _entry != 0 && _rrText.Length > 0)
			{
				// keep the box OUT of the trade: above the R:R zone for a SHORT, below for a LONG
				double pad = 6 * TickSize;
				double y = _tSide < 0 ? _rrHiPrice + pad : _rrLoPrice - pad;
				Draw.Text(this, "rrTxt", false, _rrText, 0, y, 0,
					Brushes.White, new NinjaTrader.Gui.Tools.SimpleFont("Arial", 12), System.Windows.TextAlignment.Left,
					Brushes.Transparent, Brushes.Black, 85);
			}
			else
			{
				RemoveDrawObject("rrTxt");
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
			// BarsInProgress==1 = the 1-tick series: run intrabar stop management only.
			if (BarsInProgress == 1)
			{
				IntrabarManageStop();
				return;
			}

			if (_wedge == null || CurrentBar < BarsRequiredToTrade)
				return;

			_wedge.Update();
			double tick = TickSize;

			// ═══════════════════════════ FLAT ═══════════════════════════
			if (Position.MarketPosition == MarketPosition.Flat)
			{
				// reset leftover open-trade state
				_entry = 0; _beActive = false; _curStop = 0; _scalpDone = false;
				_stratSetStop = 0; _liveStopPrice = 0; _userMovedStop = false;
				ClearTradeVisuals();   // wipe R:R boxes + BE line once flat

				// ── detect a NEW signal on the just-closed bar [0] and rest ONE entry ──
				// MasterArmed gates NEW entries (dashboard MASTER button); a resting entry from
				// before a disarm still lapses/cancels via the else-branch below.
				if (MasterArmed && _pendingSide == 0)
				{
					int side = 0;
					if (_wedge.WedgeBLSB[0] > 0) side = 1;
					else if (_wedge.WedgeBRSB[0] > 0) side = -1;
					// side filter (dashboard LONG/SHORT buttons)
					if (side == 1 && !MasterAllowLong)  side = 0;
					if (side == -1 && !MasterAllowShort) side = 0;
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

						// SB-SIZE FILTER: skip if the signal bar's range is bigger than the
						// AVERAGE BAR RANGE of the prior 8 bars x MaxSBAbrMult (0 = off). The
						// average excludes the SB itself so a big SB can't inflate its threshold.
						double sbRange = High[0] - Low[0];
						double abrSum = 0;
						for (int i = 1; i <= 8; i++) abrSum += High[i] - Low[i];
						double abr = abrSum / 8.0;
						if (MaxSBAbrMult > 0 && abr > 0 && sbRange > abr * MaxSBAbrMult)
						{
							if (DebugDraw) Print(ST + " " + Time[0] + "  SKIP " + (side > 0 ? "LONG" : "SHORT")
								+ " — SB " + (sbRange / tick).ToString("0") + "t > ABR8 " + (abr / tick).ToString("0")
								+ "t x " + MaxSBAbrMult.ToString("0.00"));
							_pendingSide = 0;
							return;
						}

						// R:R FILTER: skip the setup if the scalp-target:risk ratio is worse than
						// MinRiskReward (0 = off). risk = SB/prior-bar stop distance.
						double riskTicks = Math.Abs(_entryPx - _stopPx) / tick;
						double planRR    = riskTicks > 0 ? ScalpTargetTicks / riskTicks : 0;
						if (MinRiskReward > 0 && planRR < MinRiskReward)
						{
							if (DebugDraw) Print(ST + " " + Time[0] + "  SKIP " + (side > 0 ? "LONG" : "SHORT")
								+ " — R:R 1:" + planRR.ToString("0.00") + " < min 1:" + MinRiskReward.ToString("0.00"));
							_pendingSide = 0;
							return;
						}

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
							if (DebugDraw) Print(ST + " " + Time[0] + "  SIGNAL " + (side > 0 ? "LONG " : "SHORT")
								+ "  rest x" + totQ + " entry@" + _entryPx + " protStop@" + _stopPx
								+ (insideBar ? "  [inside bar -> stop beyond prior bar]" : ""));
							// Place the SUB tag OUT of the trade's way: above the bar for a SHORT
							// (price works down), below the bar for a LONG (price works up).
							if (DebugDraw) Draw.Text(this, "sub" + CurrentBar, "SUB@" + _entryPx,
								0, side > 0 ? Low[0] - 6 * tick : High[0] + 6 * tick);
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
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; _entryBar = CurrentBar; if (_tSide == 0) BeginTradeLog(1, Time[0]); }

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
				if (_entry == 0) { _entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; _entryBar = CurrentBar; if (_tSide == 0) BeginTradeLog(-1, Time[0]); }

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

		// Draw the live-trade R:R picture: green reward box (entry -> scalp target) +
		// red risk box (entry -> stop). The risk box uses the INITIAL stop (so R doesn't
		// move on the auto-trail) UNLESS the user dragged the stop — then it follows that
		// stop and R recomputes live. The R info is shown only on HOVER (see hover
		// plumbing). A short dashed BE segment (SB -> right) marks the runner's BE lock.
		// Boxes span from the entry bar to the current bar (extend right as bars form).
		private void DrawTradeVisuals(bool isLong)
		{
			if (_entry == 0 || (!ShowRiskReward && !ShowBELine)) return;
			double tick = TickSize;
			int startBarsAgo = Math.Max(0, CurrentBar - _entryBar);
			int opacity = Math.Max(0, Math.Min(100, RiskRewardOpacity));

			// effective stop for the R:R: manual drag wins, else the initial stop
			double riskStop = (_userMovedStop && _liveStopPrice > 0) ? _liveStopPrice : _stopPx;
			double scalpTgt = isLong ? _entry + ScalpTargetTicks * tick : _entry - ScalpTargetTicks * tick;
			double beTrig   = isLong ? _entry + BETriggerTicks   * tick : _entry - BETriggerTicks   * tick;

			if (ShowRiskReward)
			{
				Draw.Rectangle(this, "rrRew",  false, startBarsAgo, _entry, 0, scalpTgt, Brushes.Transparent, Brushes.SeaGreen,  opacity);
				Draw.Rectangle(this, "rrRisk", false, startBarsAgo, _entry, 0, riskStop, Brushes.Transparent, Brushes.Firebrick, opacity);

				// stash the info + hit-test bounds for the hover tooltip (not drawn here)
				double riskT = Math.Abs(_entry - riskStop) / tick;
				double rr    = riskT > 0 ? ScalpTargetTicks / riskT : 0;
				_rrText     = "R 1:" + rr.ToString("0.00") + "   tgt " + ScalpTargetTicks + "t / risk "
					+ riskT.ToString("0") + "t" + (_userMovedStop ? "   [manual stop]" : "");
				_rrStartBar = _entryBar;
				_rrLoPrice  = Math.Min(_entry, Math.Min(riskStop, scalpTgt));
				_rrHiPrice  = Math.Max(_entry, Math.Max(riskStop, scalpTgt));
				if (_rrHover) UpdateHoverText();   // keep an open tooltip current
			}

			if (ShowBELine)
			{
				// horizontal RAY from the signal bar, extending to the right edge (grows with
				// each new bar automatically). Color is user-settable (BELineBrush).
				int beStart = Math.Max(0, CurrentBar - _sigBar);
				Ray be = Draw.Ray(this, "beLine", beStart, beTrig, 0, beTrig, BELineBrush);
				be.Stroke = new Stroke(BELineBrush, DashStyleHelper.Dash, 1);
				Draw.Text(this, "beTxt", "BE", beStart, isLong ? beTrig + 2 * tick : beTrig - 2 * tick);
			}
		}

		private void ClearTradeVisuals()
		{
			RemoveDrawObject("rrRew");
			RemoveDrawObject("rrRisk");
			RemoveDrawObject("rrTxt");
			RemoveDrawObject("beLine");
			RemoveDrawObject("beTxt");
			_rrHover = false; _rrStartBar = -1; _rrText = "";
		}

		// Delete the trade visuals the INSTANT the position goes flat (don't wait for the
		// next bar close) so the BE line / R:R boxes / tooltip disappear on the exit fill.
		// Also emit the clean per-trade summary block.
		protected override void OnPositionUpdate(Position position, double averagePrice,
			int quantity, MarketPosition marketPosition)
		{
			if (marketPosition == MarketPosition.Flat)
			{
				ClearTradeVisuals();
				EmitTradeLog();
			}
		}

		// Start a per-trade record when an entry fills (called wherever _entry is first set).
		private void BeginTradeLog(int side, DateTime t)
		{
			_tSide = side; _tTime = t; _tEntry = _entry; _tInitStop = _stopPx;
			_tQty = Position.Quantity; _tTicks = 0; _tUsd = 0;
			_tLegs = new System.Text.StringBuilder();
		}

		// Record one exit leg (scalp / runner / session-close) into the current trade record.
		private void AddExitLeg(string orderName, double price, int qty)
		{
			if (_tSide == 0 || _tLegs == null) return;
			double tickVal  = Instrument.MasterInstrument.PointValue * TickSize;
			double legTicks = (price - _tEntry) / TickSize * _tSide;   // + = profit
			double legUsd   = legTicks * tickVal * qty;
			_tTicks += legTicks; _tUsd += legUsd;
			string label = orderName == "Scalp" ? "scalp " : (orderName == "Stop" || orderName == "StopFail") ? "runner" : orderName;
			_tLegs.Append("   " + label + " x" + qty + " @ " + price.ToString("0.00") + "   "
				+ (legTicks >= 0 ? "+" : "") + legTicks.ToString("0") + "t  "
				+ (legUsd >= 0 ? "+$" : "-$") + Math.Abs(legUsd).ToString("0") + "\n");
		}

		// Print the clean stacked block on trade close. Always on (not gated by DebugDraw).
		private void EmitTradeLog()
		{
			if (_tSide == 0 || _tLegs == null) return;
			double tickVal   = Instrument.MasterInstrument.PointValue * TickSize;
			double riskTicks = Math.Abs(_tEntry - _tInitStop) / TickSize;
			double maxRisk   = riskTicks * tickVal * Math.Max(1, _tQty);
			double rMult     = maxRisk > 0 ? _tUsd / maxRisk : 0;
			string bar = new string('═', 52);

			Print("\n" + bar);
			Print(" " + (_tSide > 0 ? "LONG " : "SHORT") + "  " + _tTime
				+ "   x" + _tQty + " @ " + _tEntry.ToString("0.00")
				+ "   stop " + _tInitStop.ToString("0.00") + "   risk " + riskTicks.ToString("0") + "t");
			Print(_tLegs.ToString().TrimEnd('\n'));
			Print("   " + new string('─', 30));
			Print("   RESULT  " + (_tTicks >= 0 ? "+" : "") + _tTicks.ToString("0") + "t   "
				+ (_tUsd >= 0 ? "+$" : "-$") + Math.Abs(_tUsd).ToString("0.00")
				+ "   (" + (rMult >= 0 ? "+" : "") + rMult.ToString("0.00") + "R)");

			// running daily scoreboard — reset when the trade date rolls over
			if (_tTime.Date != _dayDate)
			{
				_dayDate = _tTime.Date;
				_dayN = 0; _dayWins = 0; _dayLosses = 0; _dayUsd = 0; _dayR = 0;
			}
			_dayN++; _dayUsd += _tUsd; _dayR += rMult;
			if (_tUsd >= 0) _dayWins++; else _dayLosses++;
			Print("   DAY " + _dayDate.ToString("M/d") + "  " + _dayN + "T  " + _dayWins + "W-" + _dayLosses + "L   "
				+ (_dayUsd >= 0 ? "+$" : "-$") + Math.Abs(_dayUsd).ToString("0")
				+ "   (" + (_dayR >= 0 ? "+" : "") + _dayR.ToString("0.00") + "R)");
			Print(bar);
			_tSide = 0; _tLegs = null;
		}

		// Runs on every tick (1-tick series). Moves the BE lock the INSTANT price touches
		// the trigger intrabar — no waiting for the primary bar to close. Only re-submits
		// the stop when the level actually changes (no per-tick order churn). The per-bar
		// 1t trail stays on the primary bar close; this handles the BE lock speed.
		private void IntrabarManageStop()
		{
			if (Position.MarketPosition == MarketPosition.Flat || _entry == 0) return;
			if (RunnerQty <= 0 || _userMovedStop) return;

			double tick = TickSize;
			double hi = Highs[0][0], lo = Lows[0][0];   // running extremes of the forming primary bar
			double before = _curStop;

			if (Position.MarketPosition == MarketPosition.Long)
			{
				if (!_beActive && hi >= _entry + BETriggerTicks * tick) _beActive = true;
				if (_beActive) _curStop = Math.Max(_curStop, _entry + BEOffsetTicks * tick);   // BE lock, intrabar
			}
			else
			{
				if (!_beActive && lo <= _entry - BETriggerTicks * tick) _beActive = true;
				if (_beActive) _curStop = Math.Min(_curStop, _entry - BEOffsetTicks * tick);
			}

			if (_curStop != before) ManageProtection();   // push the new stop only when it moved
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
				if (DebugDraw) Print(ST + " " + Time[0] + "  manual stop @ " + _liveStopPrice + " -> auto-stop OFF for this trade");
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
					if (DebugDraw) Print(ST + " " + time + "  manual stop @ " + _liveStopPrice + " -> auto-stop OFF for this trade");
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
					if (DebugDraw) Print(ST + " " + time + "  entry CANCEL confirmed (" + (_pendingSide > 0 ? "LONG" : "SHORT") + ")");
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
			if (execution.Order == null)
				return;
			string nm = execution.Order.Name;

			// Record every EXIT leg (anything but the "Wedge" entry) for the per-trade summary
			// BEFORE the flat-return below, so the CLOSING leg is captured too.
			if (nm != "Wedge")
				AddExitLeg(nm, price, quantity);

			if (Position.MarketPosition == MarketPosition.Flat)
				return;
			if (nm == "Wedge")
			{
				if (_entry == 0)
				{
					_entry = Position.AveragePrice; _curStop = _stopPx; _beActive = false; _scalpDone = false; _pendingSide = 0; _entryBar = CurrentBar;
					_stratSetStop = 0; _liveStopPrice = 0; _userMovedStop = false;
					BeginTradeLog(Position.MarketPosition == MarketPosition.Long ? 1 : -1, time);
					if (DebugDraw) Print(ST + " " + time + "  FILLED entry x" + quantity + " @ " + price + "  -> stop@" + _curStop);
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
				if (DebugDraw) Print(ST + " " + time + "  SCALP filled x" + quantity + " @ " + price + "  runner left x" + Position.Quantity);
				ManageProtection();
			}
			else if (nm == "Stop" || nm == "StopFail")
			{
				if (DebugDraw) Print(ST + " " + time + "  " + nm + " filled x" + quantity + " @ " + price);
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

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Min R:R (scalp tgt / risk, 0 = off)", GroupName = "2. Entry", Order = 3)]
		public double MinRiskReward { get; set; }

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Max SB size (× avg bar range 8, 0 = off)", GroupName = "2. Entry", Order = 4)]
		public double MaxSBAbrMult { get; set; }

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
		[Display(Name = "Show risk/reward boxes (info on hover)", GroupName = "5. Chart Visuals", Order = 0)]
		public bool ShowRiskReward { get; set; }

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "Risk/reward box opacity (0-100)", GroupName = "5. Chart Visuals", Order = 1)]
		public int RiskRewardOpacity { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Show breakeven-trigger line", GroupName = "5. Chart Visuals", Order = 2)]
		public bool ShowBELine { get; set; }

		[XmlIgnore]
		[Display(Name = "BE line color", GroupName = "5. Chart Visuals", Order = 3)]
		public Brush BELineBrush { get; set; }

		[Browsable(false)]
		public string BELineBrushSerialize
		{
			get { return Serialize.BrushToString(BELineBrush); }
			set { BELineBrush = Serialize.StringToBrush(value); }
		}

		[NinjaScriptProperty]
		[Display(Name = "Debug draw (SUB tag + lifecycle prints)", GroupName = "5. Chart Visuals", Order = 4)]
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
