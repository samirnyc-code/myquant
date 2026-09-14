#region Using declarations
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript
{
	// Position-management mode for the 2E book (kept in NinjaScript namespace so the
	// generated wrapper can see it — see nt8-compile-check note).
	public enum Regime2EPosMode
	{
		OnePerDay,   // first FILLED 2E of the day; hold to stop/EOD; no re-entry   (validated default)
		Flip,        // opposite valid 2E reverses the position
		Single       // one position at a time; ignore signals while in a trade; re-enter after a stop
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	// ── Regime2EStrategy ──────────────────────────────────────────────────────
	// EXECUTABLE port of REGIME-2E v1.1 (S87-corrected book). Engine is the SAME
	// phase-machine + S61 second-entry detector as the display indicator
	// nt8/indicators/Regime2ESetups.cs (signal-matched to the python causal engine
	// at 98.6%). This class adds a single-position ORDER layer + the account-viable
	// gates ON (SMA20-day, skip-day-after-trend-day, gap<=0.54%).
	//
	// FROZEN SPEC (matches the backtest that survives the $4,500 EOD static-DD acct):
	//   regime  : tick-driven phase machine (BULL/NEUTRAL/BEAR), day-scoped
	//   signal  : S61 second entry (2EL/2ES), origin-reset counting, with-trend only
	//   gates   : entry trigger > 20-day SMA of session closes (BOTH sides)
	//             | skip day after a trend day (prior range > 1.6 x prior ADR10)
	//             | skip |gap| > 0.54%  | fills 09:00-13:59 (open+30..open+330 min)
	//   entry   : RETEST LIMIT 6 ticks back from the trigger; fills when price trades
	//             through; unfilled limit cancelled after 6 bars
	//   stop    : 0.30 x ADR10 (8-tick floor), fills on touch
	//   exit    : flat at session close (EOD)
	//   size    : ONE position (no pyramiding). PosMode picks how repeats are handled.
	//
	// ⚠ VALIDATION BEFORE ANY FUNDED USE:
	//   1. ES 5-min RTH chart, Tick Replay ON for historical parity (the engine is
	//      tick-path-dependent). Live/forward it reads real ticks (Calculate.OnPriceChange).
	//   2. WriteSignalsCsv=true, run, diff regime2e_strat_signals_<instr>.csv against
	//      the indicator log + python (scripts/regime2e_nt_diff.py). Match -> trust.
	//   3. Paper account only until fills reconcile with the backtest.
	public class Regime2EStrategy : Strategy
	{
		private const double TICK = 0.25;

		// completed-bar series (session-scoped)
		private List<double> hi, lo, op, cl;
		private List<bool> obUpFirst;

		// phase machine state
		private class Piv { public int Bar; public bool IsH; public string Tag; public string Disp; }
		private List<Piv> piv;
		private int prevH, prevL;
		private bool firstPivotDone;
		private string mode;
		private bool hasStanding; private int standingBar; private double standingPx;
		private int runB; private double runPx; private bool hasRun;
		private Piv cand; private double candRefPx; private bool candHasRef;
		private Piv hiP, loP, lsh, lsl, structHl, structLh;
		private bool hasHl, hasLh;
		private int legD; private double legPx; private int legBar; private bool hasLeg;

		// S61 entry engine state
		private class SPiv { public int Idx; public double Prc; public bool IsH; public string Lbl; }
		private List<SPiv> sw;
		private int sDir, sExt, sPj;
		private double sRefH, sRefL; private bool sHasRefH, sHasRefL;
		private int engRegime;
		private bool hasConfLH, hasConfHL; private double confLHpx, confHLpx;
		private int ecS, ecL;
		private double refS, refLo, orgS, orgL;
		private bool hasRefS, hasRefLo, hasOrgS, hasOrgL;
		private int refSb, refLb;

		// forming-bar bookkeeping
		private int formBar;
		private bool fUpDone, fDnDone;
		private double formHigh, formLow;
		private bool obFirstRecorded, obFirstWasUp;
		private double armedLongTrig, armedShortTrig;
		private bool hasLongTrig, hasShortTrig;
		private int armedLongSb, armedShortSb;
		private int sigSeq;

		// session / gates
		private Data.SessionIterator sessionIt;
		private DateTime winStartT = DateTime.MinValue, winEndT = DateTime.MaxValue, flatT = DateTime.MaxValue;
		private readonly Queue<double> sessRanges = new Queue<double>();
		private readonly Queue<double> sessCloses = new Queue<double>();
		private double prevSessClose = double.NaN, lastSessClose = double.NaN;
		private double sessHigh = double.MinValue, sessLow = double.MaxValue;
		private double smaDaily = double.NaN;
		private bool gapSkip = true, trendDaySkip = false;
		private int adrStopTicks;

		// order/position management
		private bool dayFilled;                 // OnePerDay: a 2E has filled this session
		private readonly List<string> pendingEntry = new List<string>();  // working entry names
		private readonly List<int> pendingExpiry = new List<int>();       // expiry bar per working entry
		private List<string> csvRows;
		private Brush bullBack, bearBack;

		// on-chart visuals: trade/stop-line + daily P&L tile
		private MarketPosition prevMP = MarketPosition.Flat;
		private bool inPos; private int entryBar, tradeSeq; private double stopDraw; private string tradeTag;
		private DateTime entryTime;
		private int prevTradeCount;
		private string dayKey; private double dayRealized; private int dayStartBar; private double dayHigh;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "REGIME-2E v1.1 executable: with-trend 2E, SMA20d+trend-day+gap gates, retest limit, 0.30xADR stop, EOD flat, single position.";
				Name = "Regime2EStrategy";
				Calculate = Calculate.OnPriceChange;   // REQUIRES Tick Replay for historical parity
				IsOverlay = true;
				AddPlot(new Stroke(Brushes.DimGray, DashStyleHelper.Dash, 1), PlotStyle.Line, "SMA20d");
				ShowVisuals = true;
				EntriesPerDirection = 1;
				EntryHandling = EntryHandling.AllEntries;
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds = 30;
				IsUnmanaged = false;
				BarsRequiredToTrade = 2;

				PosMode = Regime2EPosMode.OnePerDay;   // validated default (lowest DD)
				Contracts = 1;
				WindowStartMin = 30;                   // fills from open+30min (09:00 on 08:30 RTH)
				WindowEndMin = 330;                    // ... to open+5h30 (14:00 exclusive)
				FlatAfterMin = 404;                    // hard flat backstop (open+6h44)
				RetestTicks = 6;
				StopAdrMult = 0.30;
				StopFloorTicks = 8;
				GapMaxPct = 0.54;
				EntryCancelBars = 6;
				AdrLookback = 10;
				SmaLookback = 20;
				TrendDayMult = 1.6;
				TradeLongs = true;
				TradeShorts = true;
				WriteSignalsCsv = true;
				PnLTileOffsetTicks = 24;               // vertical offset (ticks) of the per-day P&L tile above the close
			}
			else if (State == State.Configure)
			{
				bullBack = new SolidColorBrush(Color.FromArgb(22, 34, 139, 34)); bullBack.Freeze();
				bearBack = new SolidColorBrush(Color.FromArgb(22, 200, 30, 30)); bearBack.Freeze();
			}
			else if (State == State.DataLoaded)
			{
				csvRows = new List<string>();
				prevTradeCount = 0; prevMP = MarketPosition.Flat; inPos = false;
				ResetSession();
				sessionIt = new Data.SessionIterator(Bars);
				if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 5)
					Log("Regime2EStrategy: non-5min series (" + BarsPeriod + ") — the validated book is 5-MINUTE.", LogLevel.Warning);
				if (!Bars.IsTickReplay)
					Log("Regime2EStrategy: TICK REPLAY OFF — historical fills will differ; live is exact.", LogLevel.Warning);
			}
			else if (State == State.Terminated)
			{
				if (WriteSignalsCsv && csvRows != null && csvRows.Count > 0)
				{
					try
					{
						string p = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
							"regime2e_strat_signals_" + Instrument.MasterInstrument.Name + ".csv");
						File.WriteAllText(p, "date,time,event,seq,dir,trig,limit,regime,sma20d,reason\r\n"
							+ string.Join("\r\n", csvRows), Encoding.ASCII);
					}
					catch { }
				}
			}
		}

		private void ResetSession()
		{
			hi = new List<double>(); lo = new List<double>();
			op = new List<double>(); cl = new List<double>();
			obUpFirst = new List<bool>();
			piv = new List<Piv>();
			prevH = 0; prevL = 0; firstPivotDone = false; mode = "NEUTRAL";
			hasStanding = false; hasRun = false; cand = null; candHasRef = false;
			hiP = loP = lsh = lsl = structHl = structLh = null;
			hasHl = hasLh = false; legD = 0; hasLeg = false;
			sw = new List<SPiv>(); sDir = 0; sExt = 0; sPj = 0;
			sHasRefH = sHasRefL = false; engRegime = 0;
			hasConfLH = hasConfHL = false;
			ecS = ecL = 0; hasRefS = hasRefLo = hasOrgS = hasOrgL = false;
			formBar = -1; fUpDone = fDnDone = true;
			hasLongTrig = hasShortTrig = false;
			dayFilled = false;
			pendingEntry.Clear(); pendingExpiry.Clear();
		}

		// ───────────────────────── phase machine (verbatim from the indicator) ─────────────────────────
		private double HiAt(int b2) { return b2 < hi.Count ? hi[b2] : formHigh; }
		private double LoAt(int b2) { return b2 < lo.Count ? lo[b2] : formLow; }

		private void AddPivot(int bar, bool isH)
		{
			string t;
			if (isH) { t = HiAt(bar) > HiAt(prevH) ? "hh" : (HiAt(bar) < HiAt(prevH) ? "lh" : "dh"); prevH = bar; }
			else { t = LoAt(bar) > LoAt(prevL) ? "hl" : (LoAt(bar) < LoAt(prevL) ? "ll" : "dl"); prevL = bar; }
			string disp = firstPivotDone ? t : (isH ? "H" : "L");
			firstPivotDone = true;
			Piv p = new Piv { Bar = bar, IsH = isH, Tag = t, Disp = disp };
			piv.Add(p);
			if (mode == "NEUTRAL")
			{
				if (isH)
				{
					lsh = p;
					if (hiP == null || HiAt(bar) > HiAt(hiP.Bar)) hiP = p;
					if (t == "lh" || disp.Length == 1) { hasLh = true; structLh = p; }
				}
				else
				{
					lsl = p;
					if (loP == null || LoAt(bar) < LoAt(loP.Bar)) loP = p;
					if (t == "hl" || disp.Length == 1) { hasHl = true; structHl = p; }
				}
			}
			else if (mode == "BULL" && !isH)
			{
				if (cand == null || LoAt(bar) < LoAt(cand.Bar)) { cand = p; candRefPx = runPx; candHasRef = hasRun; }
			}
			else if (mode == "BEAR" && isH)
			{
				if (cand == null || HiAt(bar) > HiAt(cand.Bar)) { cand = p; candRefPx = runPx; candHasRef = hasRun; }
			}
		}

		private void StartTrend(bool up, int b, double px)
		{
			Piv partner = up ? structHl : structLh;
			hasStanding = false;
			if (partner != null)
			{
				standingBar = partner.Bar;
				standingPx = up ? LoAt(partner.Bar) : HiAt(partner.Bar);
				hasStanding = true;
			}
			runB = b; runPx = px; hasRun = true;
			mode = up ? "BULL" : "BEAR"; cand = null; candHasRef = false;
		}

		private void Terminate(int b)
		{
			mode = "NEUTRAL";
			cand = null; candHasRef = false; hasStanding = false; hasRun = false;
			hiP = loP = lsh = lsl = null; hasHl = hasLh = false;
			structHl = structLh = null;
			prevH = b; prevL = b;
			legD = 0; hasLeg = false;
		}

		private void MachineTick(double px, int b)
		{
			if (b < 1) return;
			if (legD == 1 && (!hasLeg || px > legPx)) { legPx = px; legBar = b; hasLeg = true; }
			if (legD == -1 && (!hasLeg || px < legPx)) { legPx = px; legBar = b; hasLeg = true; }
			if (!fUpDone && px > hi[b - 1])
			{
				fUpDone = true;
				if (legD == -1) { AddPivot(legBar, false); legD = 1; legPx = px; legBar = b; }
				else if (legD == 0) { legD = 1; legPx = px; legBar = b; hasLeg = true; }
			}
			if (!fDnDone && px < lo[b - 1])
			{
				fDnDone = true;
				if (legD == 1) { AddPivot(legBar, true); legD = -1; legPx = px; legBar = b; }
				else if (legD == 0) { legD = -1; legPx = px; legBar = b; hasLeg = true; }
			}
			if (mode == "NEUTRAL")
			{
				if (lsh != null && px > HiAt(lsh.Bar) && hasHl) StartTrend(true, b, px);
				else if (lsl != null && px < LoAt(lsl.Bar) && hasLh) StartTrend(false, b, px);
			}
			else
			{
				if (cand != null && candHasRef)
				{
					bool hit = mode == "BULL" ? px > candRefPx : px < candRefPx;
					if (hit)
					{
						standingBar = cand.Bar;
						standingPx = mode == "BULL" ? LoAt(cand.Bar) : HiAt(cand.Bar);
						hasStanding = true; cand = null; candHasRef = false;
					}
				}
				if (mode == "BULL" && px > runPx) { runB = b; runPx = px; }
				if (mode == "BEAR" && px < runPx) { runB = b; runPx = px; }
				if (hasStanding && ((mode == "BULL" && px < standingPx) || (mode == "BEAR" && px > standingPx)))
					Terminate(b);
			}
		}

		private void EngineBar(int i)
		{
			if (i < 1) return;
			double Hi = hi[i], Li = lo[i], Hp = hi[i - 1], Lp = lo[i - 1];
			bool isIB = Hi < Hp && Li > Lp;
			bool isOB = Hi > Hp && Li < Lp;

			var newEvents = new List<Tuple<string, double>>();
			if (!isIB)
			{
				if (isOB)
				{
					bool cf = sDir == 1 ? obUpFirst[i] : !obUpFirst[i];
					if (sDir == 1)
					{
						if (cf) { if (Hi >= hi[sExt]) sExt = i; PushSPiv(sExt, hi[sExt], true, newEvents); sDir = -1; sExt = i; }
						else { PushSPiv(sExt, hi[sExt], true, newEvents); PushSPiv(i, Li, false, newEvents); sDir = 1; sExt = i; }
					}
					else
					{
						if (cf) { if (Li <= lo[sExt]) sExt = i; PushSPiv(sExt, lo[sExt], false, newEvents); sDir = 1; sExt = i; }
						else { PushSPiv(sExt, lo[sExt], false, newEvents); PushSPiv(i, Hi, true, newEvents); sDir = -1; sExt = i; }
					}
					sPj = i;
				}
				else
				{
					if (sDir == 1)
					{
						if (Hi >= hi[sExt]) sExt = i;
						if (Li < lo[sPj]) { PushSPiv(sExt, hi[sExt], true, newEvents); sDir = -1; sExt = i; }
					}
					else
					{
						if (Li <= lo[sExt]) sExt = i;
						if (Hi > hi[sPj]) { PushSPiv(sExt, lo[sExt], false, newEvents); sDir = 1; sExt = i; }
					}
					sPj = i;
				}
			}

			foreach (var ev in newEvents)
			{
				if (ev.Item1 == "LL")
				{
					hasConfLH = true; confLHpx = ev.Item2;
					if (engRegime == 0) { engRegime = -1; ClearL(); ecS = 0; }
				}
				else
				{
					hasConfHL = true; confHLpx = ev.Item2;
					if (engRegime == 0) { engRegime = 1; ClearS(); ecL = 0; }
				}
			}

			if (engRegime == 1) ClearS();
			else
			{
				if (hasRefS && Li < refS - TICK / 2)
				{
					ecS += 1;
					if (engRegime == 0) { engRegime = -1; ClearL(); ecS = 0; }
					hasRefS = false;
					if (isOB && Hi > Hp) { refS = Li; refSb = i; hasRefS = true; }
					if (hasOrgS && Li < orgS - TICK / 2) { ecS = 0; hasOrgS = false; }
				}
				else if (hasOrgS && Li < orgS - TICK / 2) { ecS = 0; hasOrgS = false; }
				if (engRegime <= 0)
				{
					if (isOB) { if (!hasOrgS) { orgS = Li; hasOrgS = true; } refS = Li; refSb = i; hasRefS = true; }
					else if (Hi > Hp || Li >= Lp - TICK / 2)
					{ if (!hasRefS && !hasOrgS) { orgS = Lp; hasOrgS = true; } refS = Li; refSb = i; hasRefS = true; }
				}
			}
			if (engRegime == -1) ClearL();
			else
			{
				if (hasRefLo && Hi > refLo + TICK / 2)
				{
					ecL += 1;
					if (engRegime == 0) { engRegime = 1; ClearS(); ecL = 0; }
					hasRefLo = false;
					if (isOB && Li < Lp) { refLo = Hi; refLb = i; hasRefLo = true; }
					if (hasOrgL && Hi > orgL + TICK / 2) { ecL = 0; hasOrgL = false; }
				}
				else if (hasOrgL && Hi > orgL + TICK / 2) { ecL = 0; hasOrgL = false; }
				if (engRegime >= 0)
				{
					if (isOB) { if (!hasOrgL) { orgL = Hi; hasOrgL = true; } refLo = Hi; refLb = i; hasRefLo = true; }
					else if (Li < Lp || Hi <= Hp + TICK / 2)
					{ if (!hasRefLo && !hasOrgL) { orgL = Hp; hasOrgL = true; } refLo = Hi; refLb = i; hasRefLo = true; }
				}
			}
			if (engRegime == -1 && hasConfLH && cl[i] > confLHpx)
			{ engRegime = 1; hasConfLH = false; ClearS(); ecL = 0; }
			else if (engRegime == 1 && hasConfHL && cl[i] < confHLpx)
			{ engRegime = -1; hasConfHL = false; ClearL(); ecS = 0; }

			hasShortTrig = hasRefS && engRegime <= 0 && ecS == 1;
			if (hasShortTrig) { armedShortTrig = refS - TICK; armedShortSb = refSb; }
			hasLongTrig = hasRefLo && engRegime >= 0 && ecL == 1;
			if (hasLongTrig) { armedLongTrig = refLo + TICK; armedLongSb = refLb; }
		}

		private void ClearS() { ecS = 0; hasRefS = false; hasOrgS = false; }
		private void ClearL() { ecL = 0; hasRefLo = false; hasOrgL = false; }

		private void PushSPiv(int idx, double prc, bool isH, List<Tuple<string, double>> events)
		{
			var p = new SPiv { Idx = idx, Prc = prc, IsH = isH, Lbl = "" };
			sw.Add(p);
			int k = sw.Count - 1;
			if (!isH)
			{
				if (!sHasRefL) { sRefL = prc; sHasRefL = true; }
				else if (prc < sRefL)
				{
					p.Lbl = "LL"; sRefL = prc;
					int j0 = -1;
					for (int j = k - 1; j >= 0; j--) if (!sw[j].IsH) { j0 = j; break; }
					SPiv lh = null;
					for (int j = j0 + 1; j < k; j++)
						if (sw[j].IsH && (lh == null || sw[j].Prc > lh.Prc)) lh = sw[j];
					if (lh != null && lh.Lbl == "" && (!sHasRefH || lh.Prc < sRefH))
					{ lh.Lbl = "LH"; sRefH = lh.Prc; sHasRefH = true; events.Add(Tuple.Create("LL", lh.Prc)); }
				}
			}
			else
			{
				if (!sHasRefH) { sRefH = prc; sHasRefH = true; }
				else if (prc > sRefH)
				{
					p.Lbl = "HH"; sRefH = prc;
					int j0 = -1;
					for (int j = k - 1; j >= 0; j--) if (sw[j].IsH) { j0 = j; break; }
					SPiv hl = null;
					for (int j = j0 + 1; j < k; j++)
						if (!sw[j].IsH && (hl == null || sw[j].Prc < hl.Prc)) hl = sw[j];
					if (hl != null && hl.Lbl == "" && (!sHasRefL || hl.Prc > sRefL))
					{ hl.Lbl = "HL"; sRefL = hl.Prc; sHasRefL = true; events.Add(Tuple.Create("HH", hl.Prc)); }
				}
			}
		}

		private void TrackFirstBreak(double px)
		{
			if (formBar < 1) return;
			if (!obFirstRecorded)
			{
				if (px > hi[formBar - 1]) { obFirstRecorded = true; obFirstWasUp = true; }
				else if (px < lo[formBar - 1]) { obFirstRecorded = true; obFirstWasUp = false; }
			}
		}

		private void CsvRow(string ev, int seq, string dir, double trig, double lim, string reason)
		{
			if (!WriteSignalsCsv || csvRows == null) return;
			csvRows.Add(string.Format("{0:yyyy-MM-dd},{0:HH:mm:ss},{1},{2},{3},{4},{5},{6},{7},{8}",
				Time[0], ev, seq, dir, trig, lim, mode,
				double.IsNaN(smaDaily) ? "" : smaDaily.ToString("F2"), reason));
		}

		// ───────────────────────── main handler ─────────────────────────
		protected override void OnBarUpdate()
		{
			if (BarsInProgress != 0 || CurrentBar < 1) return;

			if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
			{
				if (sessHigh > double.MinValue && sessLow < double.MaxValue)
				{
					double prevRange = sessHigh - sessLow;
					trendDaySkip = false;
					if (sessRanges.Count >= AdrLookback)
					{
						double adrPrior = 0; foreach (double r in sessRanges) adrPrior += r;
						adrPrior /= sessRanges.Count;
						trendDaySkip = prevRange > TrendDayMult * adrPrior;   // computed BEFORE enqueue
					}
					sessRanges.Enqueue(prevRange);
					while (sessRanges.Count > AdrLookback) sessRanges.Dequeue();
					prevSessClose = lastSessClose;
					sessCloses.Enqueue(lastSessClose);
					while (sessCloses.Count > SmaLookback) sessCloses.Dequeue();
					if (sessCloses.Count >= SmaLookback)
					{ double sc = 0; foreach (double v in sessCloses) sc += v; smaDaily = sc / sessCloses.Count; }
					else smaDaily = double.NaN;
				}
				sessHigh = double.MinValue; sessLow = double.MaxValue;
				ResetSession();
				sessionIt.GetNextSession(Time[0], true);
				winStartT = sessionIt.ActualSessionBegin.AddMinutes(WindowStartMin);
				winEndT = sessionIt.ActualSessionBegin.AddMinutes(WindowEndMin);
				flatT = sessionIt.ActualSessionBegin.AddMinutes(FlatAfterMin);
				gapSkip = true; adrStopTicks = 0;
				if (sessRanges.Count >= AdrLookback && !double.IsNaN(prevSessClose) && prevSessClose > 0)
				{
					double adr = 0; foreach (double r in sessRanges) adr += r;
					adr /= sessRanges.Count;
					adrStopTicks = Math.Max(StopFloorTicks,
						(int)Math.Round(StopAdrMult * adr / TICK, MidpointRounding.ToEven));
					double gapPct = Math.Abs(Close[0] - prevSessClose) / prevSessClose * 100.0;
					gapSkip = gapPct > GapMaxPct;
				}
				// new-day visuals reset
				dayKey = Time[0].ToString("yyyyMMdd"); dayRealized = 0.0;
				dayStartBar = CurrentBar; dayHigh = High[0];
			}
			if (High[0] > dayHigh) dayHigh = High[0];
			lastSessClose = Close[0];
			if (Close[0] > sessHigh) sessHigh = Close[0];
			if (Close[0] < sessLow) sessLow = Close[0];

			// OnePerDay: a live position means today's entry has happened
			if (PosMode == Regime2EPosMode.OnePerDay && Position.MarketPosition != MarketPosition.Flat)
				dayFilled = true;

			// belt-and-suspenders EOD flat + dead-stop catch
			if (Position.MarketPosition != MarketPosition.Flat)
			{
				if (Time[0] >= flatT)
				{
					if (Position.MarketPosition == MarketPosition.Long) ExitLong("HardEOD", "");
					else ExitShort("HardEOD", "");
				}
				else
				{
					double adverse = Position.MarketPosition == MarketPosition.Long
						? Position.AveragePrice - Close[0] : Close[0] - Position.AveragePrice;
					if (adrStopTicks > 0 && adverse > 2 * adrStopTicks * TICK)
					{
						Log("Regime2EStrategy: DEAD-STOP CATCH — exiting market.", LogLevel.Error);
						if (Position.MarketPosition == MarketPosition.Long) ExitLong("DeadStop", "");
						else ExitShort("DeadStop", "");
					}
				}
			}

			if (IsFirstTickOfBar)
			{
				if (formBar >= 0 && CurrentBar >= 1)
				{
					hi.Add(High[1]); lo.Add(Low[1]); op.Add(Open[1]); cl.Add(Close[1]);
					obUpFirst.Add(fUpDone && !fDnDone ? true : fDnDone && !fUpDone ? false : obFirstWasUp);
					EngineBar(hi.Count - 1);
				}
				formBar = hi.Count;
				fUpDone = fDnDone = false;
				obFirstRecorded = false; obFirstWasUp = false;
				formHigh = Close[0]; formLow = Close[0];
			}
			formHigh = Math.Max(formHigh, Close[0]);
			formLow = Math.Min(formLow, Close[0]);
			if (formBar < 1) { TrackFirstBreak(Close[0]); return; }

			double px = Close[0];
			TrackFirstBreak(px);
			MachineTick(px, formBar);

			bool inWindow = Time[0] >= winStartT && Time[0] < winEndT;

			// cancel working entry limits outside the window
			if (!inWindow) CancelWorkingEntries(true, true);

			// expire unfilled entry limits after EntryCancelBars
			for (int k = pendingEntry.Count - 1; k >= 0; k--)
			{
				if (formBar > pendingExpiry[k])
				{
					CancelByName(pendingEntry[k]);
					pendingEntry.RemoveAt(k); pendingExpiry.RemoveAt(k);
				}
			}

			// trigger touches -> mode-aware entry
			if (hasLongTrig && px > armedLongTrig - TICK / 2)
			{
				hasLongTrig = false;
				if (TradeLongs) TryEnter(true, armedLongTrig, inWindow);
			}
			if (hasShortTrig && px < armedShortTrig + TICK / 2)
			{
				hasShortTrig = false;
				if (TradeShorts) TryEnter(false, armedShortTrig, inWindow);
			}

			if (ShowVisuals) DrawVisuals();
		}

		private void DrawVisuals()
		{
			// regime shading + SMA20d line
			BackBrush = mode == "BULL" ? bullBack : mode == "BEAR" ? bearBack : null;
			if (!double.IsNaN(smaDaily)) Values[0][0] = smaDaily; else Values[0].Reset();

			// ── stop line, TIME-anchored (no barsAgo drift) ──
			MarketPosition mp = Position.MarketPosition;
			if (mp != prevMP)
			{
				if (inPos && tradeTag != null)         // finalize prior line at the exit/reversal bar
					Draw.Line(this, tradeTag, false, entryTime, stopDraw, Time[0], stopDraw,
						Brushes.Red, DashStyleHelper.Solid, 2);
				if (mp == MarketPosition.Flat) inPos = false;
				else
				{
					inPos = true; entryTime = Time[0]; tradeSeq++;
					tradeTag = "r2e_stop" + tradeSeq;
					stopDraw = mp == MarketPosition.Long
						? Position.AveragePrice - adrStopTicks * TICK
						: Position.AveragePrice + adrStopTicks * TICK;
				}
				prevMP = mp;
			}
			if (inPos && tradeTag != null)             // extend the live stop line to the current bar
				Draw.Line(this, tradeTag, false, entryTime, stopDraw, Time[0], stopDraw,
					Brushes.Red, DashStyleHelper.Solid, 2);

			// realized P&L accrual (per closed trade)
			bool tradeClosed = false;
			if (SystemPerformance.AllTrades.Count > prevTradeCount)
			{
				for (int k = prevTradeCount; k < SystemPerformance.AllTrades.Count; k++)
					dayRealized += SystemPerformance.AllTrades[k].ProfitCurrency;
				prevTradeCount = SystemPerformance.AllTrades.Count;
				tradeClosed = true;
			}

			// running-totals tiles (fixed top-right + one snapshot per day). recompute
			// once per bar, and again when a trade closes so the day's last trade counts.
			if (IsFirstTickOfBar || tradeClosed) DrawStatsTable();
		}

		private string Dollar(double v) { return v.ToString("$+#,##0;-$#,##0;$0"); }

		private void DrawStatsTable()
		{
			var tr = SystemPerformance.AllTrades;
			int n = tr.Count;
			var font = new NinjaTrader.Gui.Tools.SimpleFont("Consolas", 13);
			if (n == 0)
			{
				Draw.TextFixed(this, "r2e_stats", "REGIME-2E — no closed trades yet",
					TextPosition.TopRight, Brushes.White, font, Brushes.Transparent, Brushes.Black, 40);
				return;
			}
			var cal = System.Globalization.CultureInfo.InvariantCulture.Calendar;
			int cy = Time[0].Year, cm = Time[0].Month;
			int cw = cal.GetWeekOfYear(Time[0], System.Globalization.CalendarWeekRule.FirstFourDayWeek, DayOfWeek.Monday);
			string cd = Time[0].ToString("yyyyMMdd");
			double gW = 0, gL = 0, mxW = double.MinValue, mxL = double.MaxValue;
			double all = 0, day = 0, wk = 0, mo = 0, yr = 0; int wins = 0;
			for (int i = 0; i < n; i++)
			{
				double pc = tr[i].ProfitCurrency; DateTime et = tr[i].Exit.Time;
				all += pc; if (pc > 0) { wins++; gW += pc; } else gL += -pc;
				if (pc > mxW) mxW = pc;
				if (pc < mxL) mxL = pc;
				if (et.ToString("yyyyMMdd") == cd) day += pc;
				if (et.Year == cy)
				{
					yr += pc;
					if (et.Month == cm) mo += pc;
					if (cal.GetWeekOfYear(et, System.Globalization.CalendarWeekRule.FirstFourDayWeek, DayOfWeek.Monday) == cw) wk += pc;
				}
			}
			double pf = gL > 0 ? gW / gL : 0.0;
			string s =
				"REGIME-2E  (" + PosMode + ")\n" +
				"Day    " + Dollar(day) + "\n" +
				"Week   " + Dollar(wk) + "\n" +
				"Month  " + Dollar(mo) + "\n" +
				"Year   " + Dollar(yr) + "\n" +
				"All    " + Dollar(all) + "\n" +
				"────────────────\n" +
				"Trades " + n + "   Win " + (100.0 * wins / n).ToString("F0") + "%\n" +
				"PF " + pf.ToString("F2") + "   Exp " + Dollar(all / n) + "\n" +
				"MaxW " + Dollar(mxW) + "   MaxL " + Dollar(mxL);
			// always-visible current snapshot (top-right)
			Draw.TextFixed(this, "r2e_stats", s, TextPosition.TopRight,
				Brushes.White, font, Brushes.Transparent, Brushes.Black, 45);
			// per-day snapshot: RIGHT-aligned at the day's last bar so the box stays
			// inside its own day and does not spill into the next day's bars.
			if (dayKey != null)
				Draw.Text(this, "r2e_day" + dayKey, false, s,
					0, dayHigh + PnLTileOffsetTicks * TICK, 0,
					Brushes.White, font, System.Windows.TextAlignment.Right,
					Brushes.DimGray, Brushes.Black, 55);
		}

		private void TryEnter(bool isLong, double trig, bool inWindow)
		{
			// gate reasons (same as the indicator)
			string reason = null;
			bool warm = adrStopTicks <= 0 || double.IsNaN(smaDaily);
			if (warm) reason = "WARM";
			else if ((isLong && mode != "BULL") || (!isLong && mode != "BEAR")) reason = "REG";
			else if (!(trig > smaDaily)) reason = "SMA";
			else if (gapSkip) reason = "GAP";
			else if (trendDaySkip) reason = "TDY";
			else if (!inWindow) reason = "WIN";
			if (reason != null) { CsvRow("SKIP", sigSeq + 1, isLong ? "L" : "S", trig, 0, reason); return; }

			MarketPosition pos = Position.MarketPosition;
			bool haveWorking = pendingEntry.Count > 0;

			switch (PosMode)
			{
				case Regime2EPosMode.OnePerDay:
					if (dayFilled || pos != MarketPosition.Flat || haveWorking) return;
					SubmitRetest(isLong, trig);
					break;

				case Regime2EPosMode.Single:
					if (pos != MarketPosition.Flat || haveWorking) return;   // hold; ignore incl. opposite
					SubmitRetest(isLong, trig);
					break;

				case Regime2EPosMode.Flip:
					if ((isLong && pos == MarketPosition.Long) || (!isLong && pos == MarketPosition.Short))
						return;                                              // same dir -> ignore
					// opposite dir (or flat): clear opposite working entries, submit this side.
					// In managed mode a fill while opposite auto-closes & reverses (EntriesPerDirection=1).
					CancelWorkingEntries(!isLong, isLong);
					SubmitRetest(isLong, trig);
					break;
			}
		}

		private void SubmitRetest(bool isLong, double trig)
		{
			CancelWorkingEntries(!isLong, isLong);       // never leave an opposing working entry
			double lim = isLong ? trig - RetestTicks * TICK : trig + RetestTicks * TICK;
			sigSeq++;
			string sig = "2E" + (isLong ? "L" : "S") + sigSeq;
			pendingEntry.Add(sig); pendingExpiry.Add(formBar + EntryCancelBars);
			SetStopLoss(sig, CalculationMode.Ticks, adrStopTicks, false);
			if (isLong) EnterLongLimit(0, true, Contracts, lim, sig);
			else EnterShortLimit(0, true, Contracts, lim, sig);
			CsvRow("FIRE", sigSeq, isLong ? "L" : "S", trig, lim, "OK");
			// mark the signal bar with an arrow at its extreme
			if (ShowVisuals)
			{
				if (isLong) Draw.ArrowUp(this, "r2e_sb" + sigSeq, false, 0, formLow - 4 * TICK, Brushes.LimeGreen);
				else Draw.ArrowDown(this, "r2e_sb" + sigSeq, false, 0, formHigh + 4 * TICK, Brushes.Red);
			}
		}

		private void CancelWorkingEntries(bool longs, bool shorts)
		{
			var toCancel = new List<Order>();
			foreach (Order o in Orders)
				if (o.OrderState == OrderState.Working && o.OrderType == OrderType.Limit
					&& o.Name != null && o.Name.StartsWith("2E")
					&& ((longs && o.OrderAction == OrderAction.Buy)
						|| (shorts && (o.OrderAction == OrderAction.Sell || o.OrderAction == OrderAction.SellShort))))
					toCancel.Add(o);
			foreach (Order o in toCancel)
			{
				CancelOrder(o);
				int idx = pendingEntry.IndexOf(o.Name);
				if (idx >= 0) { pendingEntry.RemoveAt(idx); pendingExpiry.RemoveAt(idx); }
			}
		}

		private void CancelByName(string name)
		{
			foreach (Order o in Orders)
				if (o.OrderState == OrderState.Working && o.Name == name) CancelOrder(o);
		}

		#region Properties
		[NinjaScriptProperty] public Regime2EPosMode PosMode { get; set; }
		[NinjaScriptProperty] public int Contracts { get; set; }
		[NinjaScriptProperty] public int WindowStartMin { get; set; }
		[NinjaScriptProperty] public int WindowEndMin { get; set; }
		[NinjaScriptProperty] public int FlatAfterMin { get; set; }
		[NinjaScriptProperty] public int RetestTicks { get; set; }
		[NinjaScriptProperty] public double StopAdrMult { get; set; }
		[NinjaScriptProperty] public int StopFloorTicks { get; set; }
		[NinjaScriptProperty] public double GapMaxPct { get; set; }
		[NinjaScriptProperty] public int EntryCancelBars { get; set; }
		[NinjaScriptProperty] public int AdrLookback { get; set; }
		[NinjaScriptProperty] public int SmaLookback { get; set; }
		[NinjaScriptProperty] public double TrendDayMult { get; set; }
		[NinjaScriptProperty] public bool TradeLongs { get; set; }
		[NinjaScriptProperty] public bool TradeShorts { get; set; }
		[NinjaScriptProperty] public bool WriteSignalsCsv { get; set; }
		[NinjaScriptProperty] public bool ShowVisuals { get; set; }
		[NinjaScriptProperty] public int PnLTileOffsetTicks { get; set; }
		#endregion
	}
}
