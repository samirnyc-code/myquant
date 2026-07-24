#region Using declarations
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
	// ── RegimeSecondEntry ─────────────────────────────────────────────────────
	// S83 headline stack (branch regime/indep, 2026-07-23), ported from the
	// Python research pipeline (scripts/regime_second_entry_study.py +
	// regime_2e_causal_check.py — the CAUSAL variant, audit-verified equivalent:
	// n=875 vs 876, PF 1.202 vs 1.201 over 2021-2026 strict fills).
	//
	// THE RULES (all causal, all mechanical):
	//   regime : tick-driven phase machine v4 (BULL/NEUTRAL/BEAR, day-scoped)
	//   signal : S61 second entry (2EL/2ES), origin-reset counting
	//   filter : with-trend only (2EL in BULL, 2ES in BEAR), evaluated at the
	//            TRIGGER touch; optional ER10 top-half filter (prior completed bar)
	//   entry  : RETEST LIMIT 4 ticks back from the trigger; unfilled = skipped;
	//            entry limits cancelled at the window end
	//   window : fills allowed [WindowStartMin, WindowEndMin) minutes after the
	//            session open (research: 30..330 on the 08:30 machine-tz session
	//            = 09:00-13:59; VERIFY against your chart's session template)
	//   risk   : fixed 4-point stop per entry; no target; flat at session close
	//
	// ⚠ UNVALIDATED PORT — before any live/eval use:
	//   1. Run on an ES 5-min RTH chart WITH TICK REPLAY enabled (OnPriceChange
	//      on plain historical data only sees OHLC points — signals WILL differ).
	//   2. Set WriteSignalsCsv=true, run 2021-2026, and diff the exported CSV
	//      against data/regime/causal_check_20260723.csv (repo). Only a match
	//      graduates this file from "port" to "strategy".
	//   3. Backtest limit fills here are touch-fills; the research strict number
	//      (+$29k) required trade-THROUGH. Live fills land in between — log them.
	public class RegimeSecondEntry : Strategy
	{
		private const double TICK = 0.25;

		// completed-bar series (absolute session index)
		private List<double> hi, lo, op, cl;
		private List<bool> obUpFirst;              // per completed bar: first break was up?

		// ---- phase machine state (names mirror the Python) ----
		private class Piv { public int Bar; public bool IsH; public string Tag; public string Disp; }
		private List<Piv> piv;
		private int prevH, prevL;
		private bool firstPivotDone;
		private string mode;                        // NEUTRAL | BULL | BEAR
		private bool hasStanding; private int standingBar; private double standingPx;
		private int runB; private double runPx; private bool hasRun;
		private Piv cand; private double candRefPx; private bool candHasRef;
		private Piv hiP, loP, lsh, lsl, structHl, structLh;
		private bool hasHl, hasLh;
		private int legD; private double legPx; private int legBar; private bool hasLeg;
		private bool upDone, dnDone;

		// ---- S61 entry engine state (causal event keying) ----
		private class SPiv { public int Idx; public double Prc; public bool IsH; public string Lbl; }
		private List<SPiv> sw;
		private int sDir, sExt, sPj;
		private double sRefH, sRefL; private bool sHasRefH, sHasRefL;
		private int engRegime;                      // engine-internal regime (-1/0/+1)
		private bool hasConfLH, hasConfHL; private double confLHpx, confHLpx;
		private int ecS, ecL;
		private double refS, refLo, orgS, orgL;
		private bool hasRefS, hasRefLo, hasOrgS, hasOrgL;
		private int refSb, refLb;

		// forming-bar bookkeeping
		private int formBar;                        // absolute index of the forming bar
		private bool fUpDone, fDnDone;              // first-break-events on forming bar
		private double armedLongTrig, armedShortTrig;
		private bool hasLongTrig, hasShortTrig;
		private int armedLongSb, armedShortSb;      // signal-bar index of each armed trigger
		private int fadeExpiryBar = -1;             // f2EL fade stop-order lives until this bar
		private string fadeOrderName;
		private int sessionBarCount;
		private int sigSeq;
		private List<string> csvRows;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "S83 regime x second-entry stack: with-trend 2E, retest limit, 4pt stop, EOD flat.";
				Name = "RegimeSecondEntry";
				Calculate = Calculate.OnPriceChange;   // REQUIRES Tick Replay for historical parity
				EntriesPerDirection = 10;              // research book pyramids overlapping 2Es
				EntryHandling = EntryHandling.UniqueEntries;
				IsExitOnSessionCloseStrategy = true;
				ExitOnSessionCloseSeconds = 20;
				IsUnmanaged = false;
				BarsRequiredToTrade = 2;
				WindowStartMin = 30;                   // fills allowed from open+30min
				WindowEndMin = 330;                    // ...until open+5h30 (exclusive)
				FlatAfterMin = 404;                    // hard flat: open+6h44 (=15:14 on an 08:30 RTH session)
				RetestTicks = 6;                       // FINAL SPEC: limit 6t back from trigger
				StopAdrMult = 0.30;                    // FINAL SPEC: stop = 0.30 x ADR10
				StopFloorTicks = 8;                    // stop floor 2.0 pts
				GapMaxPct = 0.54;                      // FINAL SPEC: skip day when |gap| > 0.54%
				EntryCancelBars = 6;                   // FINAL SPEC: unfilled entry limit dies after 6 bars
				AdrLookback = 10;
				TradeLongs = true;
				TradeShorts = true;                // FINAL SPEC book: 2ES in BEAR (PF 1.35) is IN
				UseFadeShorts = false;             // f2EL fade = side book, forward-validate first
				FadeKBars = 2;                     // failure must print within K bars of the 2EL trigger
				UseErFilter = false;
				ErThreshold = 0.201;
				Contracts = 1;
				WriteSignalsCsv = true;            // validation build: export ON by default
			}
			else if (State == State.DataLoaded)
			{
				csvRows = new List<string>();
				ResetSession();
				sessionIt = new Data.SessionIterator(Bars);
				if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 5)
					Log("RegimeSecondEntry: non-5min series (" + BarsPeriod + ") — all "
						+ "validated numbers are 5-MINUTE; this run is an experiment.",
						LogLevel.Warning);
				if (!Bars.IsTickReplay)
					Log("RegimeSecondEntry: TICK REPLAY IS OFF — historical signals will be "
						+ "WRONG. Enable Tick Replay on the Data Series.", LogLevel.Error);
			}
			else if (State == State.Terminated)
			{
				if (WriteSignalsCsv && csvRows != null && csvRows.Count > 0)
				{
					try
					{
						string p = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
							"regime2e_signals_" + Instrument.MasterInstrument.Name + ".csv");
						File.WriteAllText(p, "Date,dir,fire_bar,trig,limit\r\n" + string.Join("\r\n", csvRows), Encoding.ASCII);
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
			upDone = dnDone = true;
			sw = new List<SPiv>(); sDir = 0; sExt = 0; sPj = 0;
			sHasRefH = sHasRefL = false; engRegime = 0;
			hasConfLH = hasConfHL = false;
			ecS = ecL = 0; hasRefS = hasRefLo = hasOrgS = hasOrgL = false;
			formBar = -1; fUpDone = fDnDone = true;
			hasLongTrig = hasShortTrig = false;
			sessionBarCount = 0;
		}

		// ───────────────────────── phase machine ─────────────────────────
		// hi/lo hold COMPLETED bars only; the machine may reference the forming bar
		// (leg extreme / termination on the current bar) -> running extremes.
		private double formHigh, formLow;

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

		// ─────────────────── S61 engine, per completed bar (causal) ───────────────────
		private void EngineBar(int i)
		{
			if (i < 1) return;
			double Hi = hi[i], Li = lo[i], Hp = hi[i - 1], Lp = lo[i - 1];
			bool isIB = Hi < Hp && Li > Lp;
			bool isOB = Hi > Hp && Li < Lp;

			// legs -> pivots (structure events keyed HERE = the flip bar: causal)
			var newEvents = new List<Tuple<string, double>>();   // kind ("LL"/"HH"), partner price
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

			// consume this bar's structure events (engine regime bootstrap)
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

			// one-pass trackers (verbatim S61 semantics on completed bar i)
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

			// arm the NEXT forming bar's triggers (counts as they stand now)
			hasShortTrig = hasRefS && engRegime <= 0 && ecS == 1;   // next break = 2nd entry
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

		private double Er10(int lastCompleted)
		{
			if (lastCompleted < 10) return double.NaN;
			double den = 0;
			for (int j = lastCompleted - 9; j <= lastCompleted; j++)
				den += Math.Abs(cl[j] - cl[j - 1]);
			if (den <= 0) return 0;
			return Math.Abs(cl[lastCompleted] - cl[lastCompleted - 10]) / den;
		}

		// ───────────────────────── main handler ─────────────────────────
		private Data.SessionIterator sessionIt;
		private DateTime winStartT = DateTime.MinValue, winEndT = DateTime.MaxValue;
		private DateTime flatT = DateTime.MaxValue;

		// ---- FINAL SPEC state: ADR stop, gap filter, entry-order expiry ----
		private readonly Queue<double> sessRanges = new Queue<double>();
		private double prevSessClose = double.NaN;
		private double sessHigh = double.MinValue, sessLow = double.MaxValue;
		private double lastSessClose = double.NaN;
		private bool skipDay = true;              // true until ADR ready and gap checked
		private int adrStopTicks;
		private readonly List<Tuple<string, int>> pendingEntry = new List<Tuple<string, int>>();

		protected override void OnBarUpdate()
		{
			if (BarsInProgress != 0) return;

			if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
			{
				// finalize PRIOR session stats before resetting
				if (sessHigh > double.MinValue && sessLow < double.MaxValue)
				{
					sessRanges.Enqueue(sessHigh - sessLow);
					while (sessRanges.Count > AdrLookback) sessRanges.Dequeue();
					prevSessClose = lastSessClose;
				}
				sessHigh = double.MinValue; sessLow = double.MaxValue;
				ResetSession();
				pendingEntry.Clear();
				// time-based entry window — works on ANY bar type (time or volume)
				sessionIt.GetNextSession(Time[0], true);
				winStartT = sessionIt.ActualSessionBegin.AddMinutes(WindowStartMin);
				winEndT = sessionIt.ActualSessionBegin.AddMinutes(WindowEndMin);
				// hard EOD anchor independent of NT's close mechanism / template quirks:
				// never in a trade later than session open + FlatAfterMin.
				flatT = sessionIt.ActualSessionBegin.AddMinutes(FlatAfterMin);
				// ---- FINAL SPEC day gate: ADR10 stop size + gap filter ----
				skipDay = true;
				if (sessRanges.Count >= AdrLookback && !double.IsNaN(prevSessClose) && prevSessClose > 0)
				{
					double adr = 0; foreach (double r in sessRanges) adr += r;
					adr /= sessRanges.Count;
					adrStopTicks = Math.Max(StopFloorTicks,
						(int)Math.Round(StopAdrMult * adr / TICK, MidpointRounding.ToEven));
					double gapPct = Math.Abs(Close[0] - prevSessClose) / prevSessClose * 100.0;
					skipDay = gapPct > GapMaxPct;
					if (skipDay)
						Log(string.Format("RegimeSecondEntry {0:d}: GAP {1:F2}% > {2:F2}% - day skipped",
							Time[0], gapPct, GapMaxPct), LogLevel.Information);
				}
			}
			lastSessClose = Close[0];
			if (Close[0] > sessHigh) sessHigh = Close[0];
			if (Close[0] < sessLow) sessLow = Close[0];

			// ---- belt-and-suspenders exits (template-proof) ----
			if (Position.MarketPosition != MarketPosition.Flat)
			{
				// 1) hard flat past the anchor (covers broken session-close on odd templates)
				if (Time[0] >= flatT)
				{
					if (Position.MarketPosition == MarketPosition.Long) ExitLong("HardEOD", "");
					else ExitShort("HardEOD", "");
				}
				// 2) dead-stop catch: adverse move beyond 2x the stop means the stop order
				//    is not working — exit market immediately.
				else
				{
					double adverse = Position.MarketPosition == MarketPosition.Long
						? Position.AveragePrice - Close[0] : Close[0] - Position.AveragePrice;
					if (adrStopTicks > 0 && adverse > 2 * adrStopTicks * TICK)
					{
						Log("RegimeSecondEntry: DEAD-STOP CATCH - adverse "
							+ adverse + "pt with no stop fill; exiting market.", LogLevel.Error);
						if (Position.MarketPosition == MarketPosition.Long) ExitLong("DeadStop", "");
						else ExitShort("DeadStop", "");
					}
				}
			}

			if (IsFirstTickOfBar)
			{
				if (formBar >= 0)
				{
					// finalize the completed bar
					hi.Add(High[1]); lo.Add(Low[1]); op.Add(Open[1]); cl.Add(Close[1]);
					obUpFirst.Add(fUpDone && !fDnDone ? true :
					              fDnDone && !fUpDone ? false :
					              obFirstWasUp);
					EngineBar(hi.Count - 1);
				}
				formBar = hi.Count;
				fUpDone = fDnDone = false;
				obFirstRecorded = false; obFirstWasUp = false;
				sessionBarCount = formBar;
				formHigh = Close[0]; formLow = Close[0];
			}
			formHigh = Math.Max(formHigh, Close[0]);
			formLow = Math.Min(formLow, Close[0]);
			if (formBar < 1) { TrackFirstBreak(Close[0]); return; }

			double px = Close[0];
			TrackFirstBreak(px);
			MachineTick(px, formBar);

			// window: fill time inside [sessionOpen+WindowStartMin, sessionOpen+WindowEndMin)
			bool inWindow = Time[0] >= winStartT && Time[0] < winEndT;
			if (!inWindow)
			{
				// cancel working entry limits outside the fill window
				var toCancel = new List<Order>();
				foreach (Order o in Orders)
					if (o.OrderState == OrderState.Working && o.OrderType == OrderType.Limit
						&& o.Name.StartsWith("2E"))
						toCancel.Add(o);
				foreach (Order o in toCancel) CancelOrder(o);
			}

			// expire a pending f2EL fade stop after FadeKBars
			if (fadeExpiryBar >= 0 && formBar > fadeExpiryBar)
			{
				var fc = new List<Order>();
				foreach (Order o in Orders)
					if (o.OrderState == OrderState.Working && o.Name == fadeOrderName)
						fc.Add(o);
				foreach (Order o in fc) CancelOrder(o);
				fadeExpiryBar = -1;
			}

			// trigger touch on the forming bar -> regime gate -> entry
			// expire unfilled entry limits after EntryCancelBars
			if (pendingEntry.Count > 0)
			{
				var dead = new List<Tuple<string, int>>();
				foreach (var pe in pendingEntry)
					if (formBar > pe.Item2) dead.Add(pe);
				foreach (var pe in dead)
				{
					pendingEntry.Remove(pe);
					var tc = new List<Order>();
					foreach (Order o in Orders)
						if (o.OrderState == OrderState.Working && o.Name == pe.Item1)
							tc.Add(o);
					foreach (Order o in tc) CancelOrder(o);
				}
			}

			if (hasLongTrig && px > armedLongTrig - TICK / 2)
			{
				int sbIdx = armedLongSb;
				hasLongTrig = false;
				if (mode == "BULL" && TradeLongs && PassesEr() && inWindow && !skipDay)
					SubmitRetest(true, armedLongTrig);
				else if (mode == "BEAR" && UseFadeShorts && inWindow && !skipDay && sbIdx >= 0 && sbIdx < lo.Count)
				{
					// f2EL fade: a counter-trend 2EL just triggered in a BEAR — if it
					// fails (tick 1t below its signal bar within FadeKBars), go short.
					double failPx = lo[sbIdx] - TICK;
					CancelWorkingEntries(true, false);   // clear working long entries first
					sigSeq++;
					fadeOrderName = "F2E" + sigSeq;
					fadeExpiryBar = formBar + FadeKBars;
					SetStopLoss(fadeOrderName, CalculationMode.Ticks, adrStopTicks, false);
					EnterShortStopMarket(0, true, Contracts, failPx, fadeOrderName);
					if (WriteSignalsCsv)
						csvRows.Add(string.Format("{0:yyyy-MM-dd},F2ES,{1},{2},{3}",
							Time[0], formBar + 1, failPx, failPx));
				}
			}
			if (hasShortTrig && px < armedShortTrig + TICK / 2)
			{
				hasShortTrig = false;
				if (mode == "BEAR" && TradeShorts && PassesEr() && inWindow && !skipDay)
					SubmitRetest(false, armedShortTrig);
			}
		}

		private bool obFirstRecorded, obFirstWasUp;
		private void TrackFirstBreak(double px)
		{
			if (formBar < 1) return;
			if (!obFirstRecorded)
			{
				if (px > hi[formBar - 1]) { obFirstRecorded = true; obFirstWasUp = true; }
				else if (px < lo[formBar - 1]) { obFirstRecorded = true; obFirstWasUp = false; }
			}
		}

		private bool PassesEr()
		{
			if (!UseErFilter) return true;
			double er = Er10(hi.Count - 1);          // last COMPLETED bar (live-causal)
			return !double.IsNaN(er) && er >= ErThreshold;
		}

		private void CancelWorkingEntries(bool longs, bool shorts)
		{
			var toCancel = new List<Order>();
			foreach (Order o in Orders)
				if (o.OrderState == OrderState.Working
					&& (o.Name.StartsWith("2E") || o.Name.StartsWith("F2E"))
					&& ((longs && o.OrderAction == OrderAction.Buy)
						|| (shorts && (o.OrderAction == OrderAction.Sell
							|| o.OrderAction == OrderAction.SellShort))))
					toCancel.Add(o);
			foreach (Order o in toCancel) CancelOrder(o);
		}

		private void SubmitRetest(bool isLong, double trig)
		{
			// NT managed mode refuses opposing working entries ("Internal Order Handling
			// Rules") — clear the other side first or this submission is silently ignored.
			CancelWorkingEntries(!isLong, isLong);
			double lim = isLong ? trig - RetestTicks * TICK : trig + RetestTicks * TICK;
			sigSeq++;
			string sig = "2E" + (isLong ? "L" : "S") + sigSeq;
			pendingEntry.Add(Tuple.Create(sig, formBar + EntryCancelBars));
			SetStopLoss(sig, CalculationMode.Ticks, adrStopTicks, false);
			if (isLong) EnterLongLimit(0, true, Contracts, lim, sig);
			else EnterShortLimit(0, true, Contracts, lim, sig);
			if (WriteSignalsCsv)
				csvRows.Add(string.Format("{0:yyyy-MM-dd},{1},{2},{3},{4}",
					Time[0], isLong ? "L" : "S", formBar + 1, trig, lim));
		}

		#region Properties
		[NinjaScriptProperty] public int WindowStartMin { get; set; }
		[NinjaScriptProperty] public int WindowEndMin { get; set; }
		[NinjaScriptProperty] public int RetestTicks { get; set; }
		[NinjaScriptProperty] public double StopAdrMult { get; set; }
		[NinjaScriptProperty] public int StopFloorTicks { get; set; }
		[NinjaScriptProperty] public double GapMaxPct { get; set; }
		[NinjaScriptProperty] public int EntryCancelBars { get; set; }
		[NinjaScriptProperty] public int AdrLookback { get; set; }
		[NinjaScriptProperty] public bool TradeLongs { get; set; }
		[NinjaScriptProperty] public bool TradeShorts { get; set; }
		[NinjaScriptProperty] public bool UseFadeShorts { get; set; }
		[NinjaScriptProperty] public int FadeKBars { get; set; }
		[NinjaScriptProperty] public int FlatAfterMin { get; set; }
		[NinjaScriptProperty] public bool UseErFilter { get; set; }
		[NinjaScriptProperty] public double ErThreshold { get; set; }
		[NinjaScriptProperty] public int Contracts { get; set; }
		[NinjaScriptProperty] public bool WriteSignalsCsv { get; set; }
		#endregion
	}
}
