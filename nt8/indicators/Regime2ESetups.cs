#region Using declarations
using System;
using System.Collections.Generic;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// ── Regime2ESetups ────────────────────────────────────────────────────────
	// DISPLAY-ONLY port of the REGIME-2E v1.1 book (S87-corrected, PF 1.54 no-gap /
	// 1.64 with gap, branch regime/indep). Engine identical to the strategy port
	// nt8/strategies/RegimeSecondEntry.cs (itself audit-matched to the Python
	// research pipeline: regime_second_entry_study.py + regime_2e_causal_check.py).
	// This indicator trades NOTHING — it shows the setups:
	//
	//   background  : regime tint (BULL green / BEAR red / NEUTRAL none)
	//   gray plot   : 20-day SMA of session closes (the regime gate line)
	//   dashed line : an ARMED 2E trigger (1st entry done; next break = 2E)
	//   arrow + box : fired with-trend 2E that passes all gates; box = the
	//                 retest entry zone (trigger .. trigger-6t) alive 6 bars;
	//                 dot = retest filled; red dashes = the 0.30xADR stop
	//   gray diamond: setup fired but FILTERED, 3-letter reason above/below
	//                 (REG wrong regime / SMA wrong side of gate / GAP gap-day
	//                  / TDY day-after-trend-day / WIN outside 09-13 window
	//                  / WARM indicator warmup)
	//
	// Chart: ES 5-MINUTE RTH (all validated numbers are 5-min). Days-to-load
	// 35+ so the 20-day SMA and ADR10 are warm. For faithful HISTORICAL marks
	// enable Tick Replay on the Data Series (the engine is tick-path-dependent:
	// outside-bar first-break + intrabar trigger ordering); live data is exact.
	public class Regime2ESetups : Indicator
	{
		private const double TICK = 0.25;

		// completed-bar series (session-scoped, index = engine bar)
		private List<double> hi, lo, op, cl;
		private List<bool> obUpFirst;

		// ---- phase machine state (verbatim from RegimeSecondEntry.cs) ----
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

		// ---- S61 entry engine state ----
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

		// ---- session / gates ----
		private Data.SessionIterator sessionIt;
		private DateTime winStartT = DateTime.MinValue, winEndT = DateTime.MaxValue;
		private readonly Queue<double> sessRanges = new Queue<double>();
		private readonly Queue<double> sessCloses = new Queue<double>();
		private double prevSessClose = double.NaN, lastSessClose = double.NaN;
		private double sessHigh = double.MinValue, sessLow = double.MaxValue;
		private double smaDaily = double.NaN;
		private bool gapSkip = true, trendDaySkip;
		private double gapPctToday = double.NaN;
		private int adrStopTicks;
		private int sessionStartBar = -1;           // chart CurrentBar of the session's first bar

		// ---- drawn setups being tracked ----
		private class Sig
		{
			public bool IsLong; public double Trig, Lim, Stop;
			public int FireChartBar, FireEngineBar, FillChartBar;
			public int State;                       // 0 pending retest, 1 filled, 2 done
			public string Tag;
		}
		private List<Sig> active;

		private Brush bullBack, bearBack, zoneOutline, zoneFill;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "REGIME-2E v1.1 book, display-only: regime tint, SMA20d gate, armed triggers, fired/filtered 2E setups with retest zone + stop.";
				Name = "Regime2ESetups";
				Calculate = Calculate.OnPriceChange;   // tick-path engine; enable Tick Replay for history
				IsOverlay = true;
				IsAutoScale = false;                   // SMA20d can sit far from price - don't stretch the chart
				DisplayInDataBox = true;
				PaintPriceMarkers = false;
				AddPlot(new Stroke(Brushes.DimGray, DashStyleHelper.Dash, 1), PlotStyle.Line, "SMA20d");

				WindowStartMin = 30;                   // fills from session open + 30 min
				WindowEndMin = 330;                    // ... to open + 5h30 (exclusive)
				RetestTicks = 6;
				StopAdrMult = 0.30;
				StopFloorTicks = 8;
				AdrLookback = 10;
				EntryCancelBars = 6;
				UseGapSkip = true;  GapMaxPct = 0.54;  // v1.1 default (PF 1.64 book); off = PF 1.54 book
				UseSmaGate = true;  SmaLookback = 20;
				UseTrendDaySkip = true; TrendDayMult = 1.6;
				ShowLongs = true; ShowShorts = true;
				ShowFiltered = true;
				ShowTriggerLines = true;
				ShowStatus = true;
			}
			else if (State == State.Configure)
			{
				bullBack = new SolidColorBrush(Color.FromArgb(22, 34, 139, 34)); bullBack.Freeze();
				bearBack = new SolidColorBrush(Color.FromArgb(22, 200, 30, 30)); bearBack.Freeze();
				zoneOutline = new SolidColorBrush(Color.FromArgb(200, 30, 120, 200)); zoneOutline.Freeze();
				zoneFill = new SolidColorBrush(Color.FromArgb(30, 30, 120, 200)); zoneFill.Freeze();
			}
			else if (State == State.DataLoaded)
			{
				active = new List<Sig>();
				ResetSession();
				sessionIt = new Data.SessionIterator(Bars);
				if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 5)
					Log("Regime2ESetups: non-5min series (" + BarsPeriod + ") - the validated book is 5-MINUTE.", LogLevel.Warning);
				if (!Bars.IsTickReplay)
					Log("Regime2ESetups: Tick Replay OFF - historical marks are approximate (close-path only); live marks are exact.", LogLevel.Warning);
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
			if (active != null) active.Clear();
		}

		// ───────────────────────── phase machine ─────────────────────────
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

		// ─────────────── S61 engine, per completed bar (causal) ───────────────
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

		// ───────────────────────── main handler ─────────────────────────
		protected override void OnBarUpdate()
		{
			if (CurrentBar < 1) return;

			if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
			{
				if (sessHigh > double.MinValue && sessLow < double.MaxValue)
				{
					double prevRange = sessHigh - sessLow;
					// skip-after-trend-day: prior session range vs ADR10 as known BEFORE that session
					trendDaySkip = false;
					if (sessRanges.Count >= AdrLookback)
					{
						double adrPrior = 0; foreach (double r in sessRanges) adrPrior += r;
						adrPrior /= sessRanges.Count;
						trendDaySkip = prevRange > TrendDayMult * adrPrior;
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
				sessionStartBar = CurrentBar;
				sessionIt.GetNextSession(Time[0], true);
				winStartT = sessionIt.ActualSessionBegin.AddMinutes(WindowStartMin);
				winEndT = sessionIt.ActualSessionBegin.AddMinutes(WindowEndMin);
				gapSkip = true; gapPctToday = double.NaN; adrStopTicks = 0;
				if (sessRanges.Count >= AdrLookback && !double.IsNaN(prevSessClose) && prevSessClose > 0)
				{
					double adr = 0; foreach (double r in sessRanges) adr += r;
					adr /= sessRanges.Count;
					adrStopTicks = Math.Max(StopFloorTicks,
						(int)Math.Round(StopAdrMult * adr / TICK, MidpointRounding.ToEven));
					gapPctToday = Math.Abs(Close[0] - prevSessClose) / prevSessClose * 100.0;
					gapSkip = gapPctToday > GapMaxPct;
				}
			}
			lastSessClose = Close[0];
			if (Close[0] > sessHigh) sessHigh = Close[0];
			if (Close[0] < sessLow) sessLow = Close[0];

			if (IsFirstTickOfBar)
			{
				if (formBar >= 0 && CurrentBar >= 1)
				{
					hi.Add(High[1]); lo.Add(Low[1]); op.Add(Open[1]); cl.Add(Close[1]);
					obUpFirst.Add(fUpDone && !fDnDone ? true :
					              fDnDone && !fUpDone ? false :
					              obFirstWasUp);
					EngineBar(hi.Count - 1);
				}
				formBar = hi.Count;
				fUpDone = fDnDone = false;
				obFirstRecorded = false; obFirstWasUp = false;
				formHigh = Close[0]; formLow = Close[0];
				RedrawTracked();
			}
			formHigh = Math.Max(formHigh, Close[0]);
			formLow = Math.Min(formLow, Close[0]);
			if (formBar < 1) { TrackFirstBreak(Close[0]); PaintState(); return; }

			double px = Close[0];
			TrackFirstBreak(px);
			MachineTick(px, formBar);

			bool inWindow = Time[0] >= winStartT && Time[0] < winEndT;

			// armed trigger lines (the "watch this level" state)
			if (ShowTriggerLines)
			{
				if (hasLongTrig && ShowLongs)
					Draw.Line(this, "r2e_armL" + armedLongSb, false,
						Math.Min(CurrentBar - sessionStartBar, 20), armedLongTrig, 0, armedLongTrig,
						Brushes.SeaGreen, DashStyleHelper.Dot, 1);
				if (hasShortTrig && ShowShorts)
					Draw.Line(this, "r2e_armS" + armedShortSb, false,
						Math.Min(CurrentBar - sessionStartBar, 20), armedShortTrig, 0, armedShortTrig,
						Brushes.IndianRed, DashStyleHelper.Dot, 1);
			}

			// trigger touch -> setup fires
			if (hasLongTrig && px > armedLongTrig - TICK / 2)
			{
				hasLongTrig = false;
				if (ShowLongs) FireSetup(true, armedLongTrig, inWindow);
			}
			if (hasShortTrig && px < armedShortTrig + TICK / 2)
			{
				hasShortTrig = false;
				if (ShowShorts) FireSetup(false, armedShortTrig, inWindow);
			}

			// track retest fills / stops on every price update
			foreach (Sig s in active)
			{
				if (s.State == 0)
				{
					if (formBar > s.FireEngineBar + EntryCancelBars) { s.State = 2; ExpireZone(s); }
					else if ((s.IsLong && px < s.Lim + TICK / 2) || (!s.IsLong && px > s.Lim - TICK / 2))
					{
						s.State = 1; s.FillChartBar = CurrentBar;
						s.Stop = s.IsLong ? s.Lim - adrStopTicks * TICK : s.Lim + adrStopTicks * TICK;
						Draw.Dot(this, s.Tag + "e", false, 0, s.Lim, s.IsLong ? Brushes.LimeGreen : Brushes.Red);
					}
				}
				else if (s.State == 1)
				{
					if ((s.IsLong && px < s.Stop + TICK / 2) || (!s.IsLong && px > s.Stop - TICK / 2))
					{
						s.State = 2;
						Draw.Text(this, s.Tag + "x", "STOP", 0,
							s.Stop + (s.IsLong ? -8 : 8) * TICK, Brushes.DarkRed);
					}
				}
			}

			PaintState();
		}

		private void FireSetup(bool isLong, double trig, bool inWindow)
		{
			string reason = null;                                  // null = valid book setup
			bool warm = adrStopTicks <= 0 || (UseSmaGate && double.IsNaN(smaDaily));
			if (warm) reason = "WARM";
			else if ((isLong && mode != "BULL") || (!isLong && mode != "BEAR")) reason = "REG";
			else if (UseSmaGate && !(trig > smaDaily)) reason = "SMA";   // book: entry above SMA20d, BOTH sides
			else if (UseGapSkip && gapSkip) reason = "GAP";
			else if (UseTrendDaySkip && trendDaySkip) reason = "TDY";
			else if (!inWindow) reason = "WIN";

			sigSeq++;
			string tg = "r2e" + Time[0].ToString("yyMMdd") + "_" + sigSeq;

			if (reason != null)
			{
				if (!ShowFiltered) return;
				Draw.Diamond(this, tg + "f", false, 0, trig, Brushes.Gray);
				Draw.Text(this, tg + "ft", reason, 0, trig + (isLong ? -10 : 10) * TICK, Brushes.Gray);
				return;
			}

			double lim = isLong ? trig - RetestTicks * TICK : trig + RetestTicks * TICK;
			if (isLong)
			{
				Draw.TriangleUp(this, tg + "a", false, 0, trig - 6 * TICK, Brushes.LimeGreen);
				Draw.Text(this, tg + "t", "2EL", 0, trig - 12 * TICK, Brushes.LimeGreen);
			}
			else
			{
				Draw.TriangleDown(this, tg + "a", false, 0, trig + 6 * TICK, Brushes.Red);
				Draw.Text(this, tg + "t", "2ES", 0, trig + 12 * TICK, Brushes.Red);
			}
			active.Add(new Sig
			{
				IsLong = isLong, Trig = trig, Lim = lim,
				FireChartBar = CurrentBar, FireEngineBar = formBar, State = 0, Tag = tg
			});
		}

		private void RedrawTracked()
		{
			foreach (Sig s in active)
			{
				if (s.State == 0)
					Draw.Rectangle(this, s.Tag + "z", false,
						CurrentBar - s.FireChartBar, s.Trig, 0, s.Lim, zoneOutline, zoneFill, 100);
				else if (s.State == 1)
					Draw.Line(this, s.Tag + "s", false,
						CurrentBar - s.FillChartBar, s.Stop, 0, s.Stop,
						Brushes.Red, DashStyleHelper.Dash, 1);
			}
		}

		private void ExpireZone(Sig s)
		{
			Draw.Rectangle(this, s.Tag + "z", false,
				CurrentBar - s.FireChartBar, s.Trig, 0, s.Lim,
				Brushes.Gray, Brushes.Transparent, 0);
		}

		private void PaintState()
		{
			BackBrush = mode == "BULL" ? bullBack : mode == "BEAR" ? bearBack : null;
			if (!double.IsNaN(smaDaily)) Values[0][0] = smaDaily; else Values[0].Reset();
			if (!ShowStatus) return;
			string gates = (adrStopTicks <= 0 || (UseSmaGate && double.IsNaN(smaDaily))) ? "WARMUP (load 35+ days)"
				: (UseGapSkip && gapSkip ? "DAY SKIPPED: gap " + gapPctToday.ToString("F2") + "%"
				: (UseTrendDaySkip && trendDaySkip ? "DAY SKIPPED: after trend day"
				: "stop " + (adrStopTicks * TICK).ToString("F2") + "pt"
					+ (UseSmaGate ? " | SMA20d " + smaDaily.ToString("F2") : "")));
			Draw.TextFixed(this, "r2e_status",
				"REGIME-2E v1.1 | " + mode + " | " + gates + (Bars.IsTickReplay ? "" : " | TickReplay OFF"),
				TextPosition.TopLeft);
		}

		#region Properties
		[NinjaScriptProperty] public int WindowStartMin { get; set; }
		[NinjaScriptProperty] public int WindowEndMin { get; set; }
		[NinjaScriptProperty] public int RetestTicks { get; set; }
		[NinjaScriptProperty] public double StopAdrMult { get; set; }
		[NinjaScriptProperty] public int StopFloorTicks { get; set; }
		[NinjaScriptProperty] public int AdrLookback { get; set; }
		[NinjaScriptProperty] public int EntryCancelBars { get; set; }
		[NinjaScriptProperty] public bool UseGapSkip { get; set; }
		[NinjaScriptProperty] public double GapMaxPct { get; set; }
		[NinjaScriptProperty] public bool UseSmaGate { get; set; }
		[NinjaScriptProperty] public int SmaLookback { get; set; }
		[NinjaScriptProperty] public bool UseTrendDaySkip { get; set; }
		[NinjaScriptProperty] public double TrendDayMult { get; set; }
		[NinjaScriptProperty] public bool ShowLongs { get; set; }
		[NinjaScriptProperty] public bool ShowShorts { get; set; }
		[NinjaScriptProperty] public bool ShowFiltered { get; set; }
		[NinjaScriptProperty] public bool ShowTriggerLines { get; set; }
		[NinjaScriptProperty] public bool ShowStatus { get; set; }
		#endregion
	}
}
