#region Using declarations
using System;
using System.Collections.Generic;
using System.Text;
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
	// ── RegimePhaseMachine ────────────────────────────────────────────────────
	// The S83 tick-driven regime engine (phase machine v4) as a chart indicator.
	// Full research look: regime background shading, pivot tags (hh/hl/lh/ll),
	// major promotions (HH/HL/LH/LL), trend start / termination verticals,
	// LIVE decision levels (race levels in NEUTRAL, standing HL/LH in trend),
	// armed 2E triggers + OB first-break dots, and the cockpit info box
	// (DOW/TOD/bar#/bar class/regime/distances/gap/stop/window/PnL/W-L).
	//
	// Run on ES 5-minute RTH, Calculate.OnPriceChange, Tick Replay for history.
	// Day-scoped: everything resets at the session open. UNVALIDATED PORT until
	// diffed against the research engine — same caveat as the strategy.
	public class RegimePhaseMachine : Indicator
	{
		private const double TICK = 0.25;

		private List<double> hi, lo, op, cl;
		private class Piv { public int Bar; public bool IsH; public string Tag; public string Disp;
			public string MajLab; public bool Major; }
		private List<Piv> piv;
		private int prevH, prevL; private bool firstPivotDone;
		private string mode = "NEUTRAL";
		private bool hasStanding; private int standingBar; private double standingPx;
		private int runB; private double runPx; private bool hasRun;
		private Piv cand; private double candRefPx; private bool candHasRef;
		private Piv hiP, loP, lsh, lsl, structHl, structLh;
		private bool hasHl, hasLh;
		private int legD; private double legPx; private int legBar; private bool hasLeg;
		private bool fUpDone, fDnDone, obRec, obUp;
		private int formBar = -1;
		private double formHigh, formLow;
		private int trendStartBar = -1;

		// S61 count state (for armed 2E triggers)
		private class SPiv { public int Idx; public double Prc; public bool IsH; public string Lbl; }
		private List<SPiv> sw;
		private int sDir, sExt, sPj;
		private double sRefH, sRefL; private bool sHasRefH, sHasRefL;
		private int engRegime; private bool hasConfLH, hasConfHL; private double confLHpx, confHLpx;
		private int ecS, ecL;
		private double refS, refLo, orgS, orgL;
		private bool hasRefS, hasRefLo, hasOrgS, hasOrgL;
		private int refSb, refLb;
		private double armedLongTrig, armedShortTrig; private bool hasLongTrig, hasShortTrig;

		// MenthorQ HVL (gamma regime)
		private double hvl = double.NaN, hvl0 = double.NaN;
		private string hvlDate = "";
		private bool hvlIsPrev;

		private void ReadHvl(DateTime sessionDate)
		{
			hvl = double.NaN; hvl0 = double.NaN; hvlDate = ""; hvlIsPrev = false;
			try
			{
				string[] lines = System.IO.File.ReadAllLines(HvlCsvPath);
				if (lines.Length < 2) return;
				string[] hdr = lines[0].Split(',');
				int iDate = Array.IndexOf(hdr, "session_date");
				int iHvl = Array.IndexOf(hdr, "hvl");
				int iHvl0 = Array.IndexOf(hdr, "hvl0");
				if (iDate < 0 || iHvl < 0) return;
				string want = sessionDate.ToString("yyyy-MM-dd");
				for (int i = lines.Length - 1; i >= 1 && i >= lines.Length - 12; i--)
				{
					string[] f = lines[i].Split(',');
					if (f.Length <= Math.Max(iHvl, iHvl0)) continue;
					double v;
					if (f[iDate] == want || hvlDate == "")
					{
						if (double.TryParse(f[iHvl], System.Globalization.NumberStyles.Any,
							System.Globalization.CultureInfo.InvariantCulture, out v) && v > 0)
						{
							hvl = v; hvlDate = f[iDate]; hvlIsPrev = f[iDate] != want;
							if (iHvl0 >= 0 && double.TryParse(f[iHvl0],
								System.Globalization.NumberStyles.Any,
								System.Globalization.CultureInfo.InvariantCulture, out v) && v > 0)
								hvl0 = v;
						}
						if (f[iDate] == want) break;
					}
				}
			}
			catch { }
		}

		// session / day stats
		private readonly Queue<double> sessRanges = new Queue<double>();
		private double prevSessClose = double.NaN, lastSessClose = double.NaN;
		private double sessHigh = double.MinValue, sessLow = double.MaxValue;
		private double gapPct = double.NaN; private bool skipDay;
		private int adrStopTicks; private double adr10 = double.NaN;
		private Data.SessionIterator sessionIt;
		private DateTime winStartT, winEndT, flatT;

		// account PnL tracking (FIFO, this instrument)
		private Account acct;
		private double realized; private int wins, losses;
		private readonly List<Tuple<int, double>> fifo = new List<Tuple<int, double>>(); // qty(+/-), px
		private DateTime pnlDay = DateTime.MinValue;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "S83 regime phase machine v4 — full research display + cockpit box.";
				Name = "RegimePhaseMachine";
				Calculate = Calculate.OnPriceChange;
				IsOverlay = true;
				DrawOnPricePanel = true;
				MaximumBarsLookBack = MaximumBarsLookBack.Infinite;   // keep plot values for ALL bars (Data Box on any past session)
				AccountName = "Sim101";
				HvlCsvPath = @"C:\Users\Admin\myquant\data\menthorq\ES1!_mq_levels_history.csv";
				ShowHvlLine = true;
				ShowPivotTags = true;
				ShowLevels = true;
				ShowTriggers = true;
				GapMaxPct = 0.54;
				StopAdrMult = 0.30;
				StopFloorTicks = 8;
				WindowStartMin = 30;
				WindowEndMin = 330;
				FlatAfterMin = 404;
			}
			else if (State == State.Configure)
			{
				// Tier-1 hover: hidden plots -> NT Data Box shows per-bar values on hover.
				// Regime: +1 BULL / 0 NEUTRAL / -1 BEAR
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "Regime");
				// BarClass: 1 up / -1 down / 0 inside / 2 EQUAL-IB / 3 OB U-first / -3 OB D-first
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "BarClass");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "DistMinorPiv");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "DistMajorPiv");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "StandingLvl");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "GapPct");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "SkipDay");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "StopTicksNow");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "Count2E_L");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "Count2E_S");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "BarsInTrend");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "DayRngVsADR");
				// GammaRegime: +1 above HVL (positive) / -1 below / 0 unknown
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "GammaRegime");
				AddPlot(new Stroke(Brushes.Transparent), PlotStyle.Line, "DistToHVL");
			}
			else if (State == State.DataLoaded)
			{
				sessionIt = new Data.SessionIterator(Bars);
				ResetDay();
				foreach (Account a in Account.All)
					if (a.Name == AccountName) { acct = a; break; }
				if (acct != null)
					acct.ExecutionUpdate += OnExec;
			}
			else if (State == State.Terminated)
			{
				if (acct != null) acct.ExecutionUpdate -= OnExec;
			}
		}

		private void OnExec(object sender, ExecutionEventArgs e)
		{
			try
			{
				if (e.Execution.Instrument.MasterInstrument.Name
					!= Instrument.MasterInstrument.Name) return;
				if (e.Execution.Time.Date != pnlDay)
				{ realized = 0; wins = 0; losses = 0; fifo.Clear(); pnlDay = e.Execution.Time.Date; }
				int q = e.Execution.Quantity *
					(e.Execution.MarketPosition == MarketPosition.Long ? 1 : -1);
				double px = e.Execution.Price;
				double pv = Instrument.MasterInstrument.PointValue;
				while (q != 0 && fifo.Count > 0 && Math.Sign(fifo[0].Item1) != Math.Sign(q))
				{
					var lot = fifo[0];
					int close = Math.Min(Math.Abs(q), Math.Abs(lot.Item1)) * Math.Sign(lot.Item1);
					double pnl = (px - lot.Item2) * close * pv;
					realized += pnl;
					if (pnl > 0) wins++; else if (pnl < 0) losses++;
					int rem = lot.Item1 - close;
					if (rem == 0) fifo.RemoveAt(0); else fifo[0] = Tuple.Create(rem, lot.Item2);
					q += close;
				}
				if (q != 0) fifo.Add(Tuple.Create(q, px));
			}
			catch { }
		}

		private void ResetDay()
		{
			hi = new List<double>(); lo = new List<double>();
			op = new List<double>(); cl = new List<double>();
			piv = new List<Piv>();
			prevH = 0; prevL = 0; firstPivotDone = false; mode = "NEUTRAL";
			hasStanding = false; hasRun = false; cand = null; candHasRef = false;
			hiP = loP = lsh = lsl = structHl = structLh = null;
			hasHl = hasLh = false; legD = 0; hasLeg = false;
			formBar = -1; trendStartBar = -1;
			sw = new List<SPiv>(); sDir = 0; sExt = 0; sPj = 0;
			sHasRefH = sHasRefL = false; engRegime = 0;
			hasConfLH = hasConfHL = false;
			ecS = ecL = 0; hasRefS = hasRefLo = hasOrgS = hasOrgL = false;
			hasLongTrig = hasShortTrig = false;
		}

		private double HiAt(int b) { return b < hi.Count ? hi[b] : formHigh; }
		private double LoAt(int b) { return b < lo.Count ? lo[b] : formLow; }

		// ── phase machine (with display labels) ──
		private void AddPivot(int bar, bool isH)
		{
			string t;
			if (isH) { t = HiAt(bar) > HiAt(prevH) ? "hh" : (HiAt(bar) < HiAt(prevH) ? "lh" : "dh"); prevH = bar; }
			else { t = LoAt(bar) > LoAt(prevL) ? "hl" : (LoAt(bar) < LoAt(prevL) ? "ll" : "dl"); prevL = bar; }
			string disp = firstPivotDone ? t : (isH ? "H" : "L");
			firstPivotDone = true;
			var p = new Piv { Bar = bar, IsH = isH, Tag = t, Disp = disp };
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
			{ if (cand == null || LoAt(bar) < LoAt(cand.Bar)) { cand = p; candRefPx = runPx; candHasRef = hasRun; } }
			else if (mode == "BEAR" && isH)
			{ if (cand == null || HiAt(bar) > HiAt(cand.Bar)) { cand = p; candRefPx = runPx; candHasRef = hasRun; } }
			if (mode == "BULL" && isH && bar == runB) { p.Major = true; p.MajLab = "HH"; }
			else if (mode == "BEAR" && !isH && bar == runB) { p.Major = true; p.MajLab = "LL"; }
			if (ShowPivotTags) DrawPivot(p);
		}

		private void DrawPivot(Piv p)
		{
			double off = TickSize * 6;
			double y = p.IsH ? HiAt(p.Bar) + off : LoAt(p.Bar) - off;
			int ago = CurrentBar - BarOfSession(p.Bar);
			if (ago < 0) return;
			Brush br = p.Disp.Length == 1 ? Brushes.DarkGoldenrod
				: (p.Tag == "hh" || p.Tag == "hl" ? Brushes.Green : Brushes.Firebrick);
			Draw.Text(this, "pv" + p.Bar + (p.IsH ? "H" : "L"), false, p.Disp, ago, y, 0,
				br, new Gui.Tools.SimpleFont("Arial", 11), System.Windows.TextAlignment.Center,
				Brushes.Transparent, Brushes.Transparent, 0);
		}

		private void PromoteMajor(Piv p, string lab)
		{
			if (p == null || p.Major) return;
			p.Major = true; p.MajLab = lab;
			if (!ShowPivotTags) return;
			double off = TickSize * 14;
			double y = p.IsH ? HiAt(p.Bar) + off : LoAt(p.Bar) - off;
			int ago = CurrentBar - BarOfSession(p.Bar);
			if (ago < 0) return;
			Brush br = lab.Length == 1 ? Brushes.DarkGoldenrod
				: (lab == "HH" || lab == "HL" ? Brushes.Green : Brushes.Firebrick);
			Draw.Text(this, "mj" + p.Bar + (p.IsH ? "H" : "L"), false, lab, ago, y, 0, br,
				new Gui.Tools.SimpleFont("Arial", 12) { Bold = true },
				System.Windows.TextAlignment.Center, br, Brushes.Transparent, 0);
		}

		private int sessFirstCurrentBar;
		private int BarOfSession(int sessBar) { return sessFirstCurrentBar + sessBar; }

		private void StartTrend(bool up, int b, double px)
		{
			Piv broken = up ? lsh : lsl;
			Piv partner = up ? structHl : structLh;
			Piv opp = up ? loP : hiP;
			PromoteMajor(broken, up ? "HH" : "LL");
			if (partner != null && !partner.Major)
				PromoteMajor(partner, partner.Disp.Length == 1 ? partner.Disp : (up ? "HL" : "LH"));
			if (opp != null && opp != partner && !opp.Major)
				PromoteMajor(opp, opp.Disp.Length == 1 ? opp.Disp : opp.Tag.ToUpper());
			hasStanding = false;
			if (partner != null)
			{ standingBar = partner.Bar; standingPx = up ? LoAt(partner.Bar) : HiAt(partner.Bar); hasStanding = true; }
			runB = b; runPx = px; hasRun = true;
			mode = up ? "BULL" : "BEAR"; cand = null; candHasRef = false;
			trendStartBar = b;
			Draw.VerticalLine(this, "st" + CurrentBar, 0, up ? Brushes.Green : Brushes.Firebrick,
				DashStyleHelper.Dash, 2);
		}

		private void Terminate(int b)
		{
			mode = "NEUTRAL";
			cand = null; candHasRef = false; hasStanding = false; hasRun = false;
			hiP = loP = lsh = lsl = null; hasHl = hasLh = false;
			structHl = structLh = null;
			prevH = b; prevL = b;
			legD = 0; hasLeg = false; trendStartBar = -1;
			Draw.VerticalLine(this, "tm" + CurrentBar, 0, Brushes.Teal, DashStyleHelper.Dash, 2);
		}

		private void MachineTick(double px, int b)
		{
			if (b < 1) return;
			if (legD == 1 && (!hasLeg || px > legPx)) { legPx = px; legBar = b; hasLeg = true; }
			if (legD == -1 && (!hasLeg || px < legPx)) { legPx = px; legBar = b; hasLeg = true; }
			if (!fUpDone && px > hi[b - 1])
			{
				fUpDone = true;
				if (!obRec) { obRec = true; obUp = true; }
				if (legD == -1) { AddPivot(legBar, false); legD = 1; legPx = px; legBar = b; }
				else if (legD == 0) { legD = 1; legPx = px; legBar = b; hasLeg = true; }
			}
			if (!fDnDone && px < lo[b - 1])
			{
				fDnDone = true;
				if (!obRec) { obRec = true; obUp = false; }
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
						PromoteMajor(cand, mode == "BULL" ? "HL" : "LH");
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

		// ── S61 engine per completed bar (counts + armed triggers) ──
		private void EngineBar(int i)
		{
			if (i < 1) return;
			double Hi = hi[i], Li = lo[i], Hp = hi[i - 1], Lp = lo[i - 1];
			bool isIB = Hi < Hp && Li > Lp;
			bool isOB = Hi > Hp && Li < Lp;
			var evts = new List<Tuple<string, double>>();
			if (!isIB)
			{
				if (isOB)
				{
					bool cf = sDir == 1 ? lastObUpList[i] : !lastObUpList[i];
					if (sDir == 1)
					{
						if (cf) { if (Hi >= hi[sExt]) sExt = i; PushSPiv(sExt, hi[sExt], true, evts); sDir = -1; sExt = i; }
						else { PushSPiv(sExt, hi[sExt], true, evts); PushSPiv(i, Li, false, evts); sDir = 1; sExt = i; }
					}
					else
					{
						if (cf) { if (Li <= lo[sExt]) sExt = i; PushSPiv(sExt, lo[sExt], false, evts); sDir = 1; sExt = i; }
						else { PushSPiv(sExt, lo[sExt], false, evts); PushSPiv(i, Hi, true, evts); sDir = -1; sExt = i; }
					}
					sPj = i;
				}
				else
				{
					if (sDir == 1)
					{
						if (Hi >= hi[sExt]) sExt = i;
						if (Li < lo[sPj]) { PushSPiv(sExt, hi[sExt], true, evts); sDir = -1; sExt = i; }
					}
					else
					{
						if (Li <= lo[sExt]) sExt = i;
						if (Hi > hi[sPj]) { PushSPiv(sExt, lo[sExt], false, evts); sDir = 1; sExt = i; }
					}
					sPj = i;
				}
			}
			foreach (var ev in evts)
			{
				if (ev.Item1 == "LL")
				{ hasConfLH = true; confLHpx = ev.Item2;
				  if (engRegime == 0) { engRegime = -1; ecL = 0; hasRefLo = hasOrgL = false; ecS = 0; } }
				else
				{ hasConfHL = true; confHLpx = ev.Item2;
				  if (engRegime == 0) { engRegime = 1; ecS = 0; hasRefS = hasOrgS = false; ecL = 0; } }
			}
			if (engRegime == 1) { ecS = 0; hasRefS = hasOrgS = false; }
			else
			{
				if (hasRefS && Li < refS - TICK / 2)
				{
					ecS += 1;
					if (engRegime == 0) { engRegime = -1; ecL = 0; hasRefLo = hasOrgL = false; ecS = 0; }
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
			if (engRegime == -1) { ecL = 0; hasRefLo = hasOrgL = false; }
			else
			{
				if (hasRefLo && Hi > refLo + TICK / 2)
				{
					ecL += 1;
					if (engRegime == 0) { engRegime = 1; ecS = 0; hasRefS = hasOrgS = false; ecL = 0; }
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
			{ engRegime = 1; hasConfLH = false; ecS = 0; hasRefS = hasOrgS = false; ecL = 0; }
			else if (engRegime == 1 && hasConfHL && cl[i] < confHLpx)
			{ engRegime = -1; hasConfHL = false; ecL = 0; hasRefLo = hasOrgL = false; ecS = 0; }
			hasShortTrig = hasRefS && engRegime <= 0 && ecS == 1;
			if (hasShortTrig) armedShortTrig = refS - TICK;
			hasLongTrig = hasRefLo && engRegime >= 0 && ecL == 1;
			if (hasLongTrig) armedLongTrig = refLo + TICK;
		}

		private void PushSPiv(int idx, double prc, bool isH, List<Tuple<string, double>> evts)
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
					{ lh.Lbl = "LH"; sRefH = lh.Prc; sHasRefH = true; evts.Add(Tuple.Create("LL", lh.Prc)); }
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
					{ hl.Lbl = "HL"; sRefL = hl.Prc; sHasRefL = true; evts.Add(Tuple.Create("HH", hl.Prc)); }
				}
			}
		}

		private List<bool> lastObUpList = new List<bool>();

		private string CurBarClass()
		{
			if (formBar < 1 || hi.Count < 1) return "-";
			double Hp = hi[hi.Count - 1], Lp = lo[lo.Count - 1];
			bool bt = formHigh > Hp, bb = formLow < Lp;
			bool eqH = Math.Abs(formHigh - Hp) < TICK / 2, eqL = Math.Abs(formLow - Lp) < TICK / 2;
			if (bt && bb) return "OB " + (obUp ? "U-first" : "D-first");
			if (bt) return "up";
			if (bb) return "down";
			if (eqH && eqL) return "EQUAL=IB";
			return "inside";
		}

		protected override void OnBarUpdate()
		{
			if (BarsInProgress != 0 || CurrentBar < 1) return;

			if (Bars.IsFirstBarOfSession && IsFirstTickOfBar)
			{
				if (sessHigh > double.MinValue)
				{
					sessRanges.Enqueue(sessHigh - sessLow);
					while (sessRanges.Count > 10) sessRanges.Dequeue();
					prevSessClose = lastSessClose;
				}
				sessHigh = double.MinValue; sessLow = double.MaxValue;
				ResetDay();
				lastObUpList = new List<bool>();
				sessFirstCurrentBar = CurrentBar;
				sessionIt.GetNextSession(Time[0], true);
				winStartT = sessionIt.ActualSessionBegin.AddMinutes(WindowStartMin);
				winEndT = sessionIt.ActualSessionBegin.AddMinutes(WindowEndMin);
				flatT = sessionIt.ActualSessionBegin.AddMinutes(FlatAfterMin);
				gapPct = double.NaN; skipDay = true; adr10 = double.NaN; adrStopTicks = 0;
				ReadHvl(sessionIt.ActualSessionBegin.Date);
				RemoveDrawObject("hvlLn"); RemoveDrawObject("hvl0Ln");
				if (ShowHvlLine && !double.IsNaN(hvl))
				{
					Draw.HorizontalLine(this, "hvlLn", hvl, Brushes.DarkGoldenrod,
						DashStyleHelper.Solid, 2);
					if (!double.IsNaN(hvl0))
						Draw.HorizontalLine(this, "hvl0Ln", hvl0, Brushes.Goldenrod,
							DashStyleHelper.Dot, 1);
				}
				if (sessRanges.Count >= 10 && !double.IsNaN(prevSessClose) && prevSessClose > 0)
				{
					double a = 0; foreach (double r in sessRanges) a += r;
					adr10 = a / sessRanges.Count;
					adrStopTicks = Math.Max(StopFloorTicks,
						(int)Math.Round(StopAdrMult * adr10 / TICK, MidpointRounding.ToEven));
					gapPct = (Close[0] - prevSessClose) / prevSessClose * 100.0;
					skipDay = Math.Abs(gapPct) > GapMaxPct;
				}
			}
			lastSessClose = Close[0];
			if (Close[0] > sessHigh) sessHigh = Close[0];
			if (Close[0] < sessLow) sessLow = Close[0];

			if (IsFirstTickOfBar)
			{
				if (formBar >= 0)
				{
					hi.Add(High[1]); lo.Add(Low[1]); op.Add(Open[1]); cl.Add(Close[1]);
					lastObUpList.Add(obRec ? obUp : true);
					EngineBar(hi.Count - 1);
				}
				formBar = hi.Count;
				fUpDone = fDnDone = false; obRec = false;
				formHigh = Close[0]; formLow = Close[0];
			}
			formHigh = Math.Max(formHigh, Close[0]);
			formLow = Math.Min(formLow, Close[0]);
			if (formBar >= 1)
				MachineTick(Close[0], formBar);

			// regime background shading (per bar, so history keeps its own state colors)
			BackBrush = mode == "BULL" ? new SolidColorBrush(Color.FromArgb(26, 31, 122, 61))
				: mode == "BEAR" ? new SolidColorBrush(Color.FromArgb(26, 178, 58, 46))
				: new SolidColorBrush(Color.FromArgb(20, 128, 134, 139));

			// live decision levels
			int lb = Math.Min(12, CurrentBar);          // clamp lookback to available bars
			int tb = Math.Min(6, CurrentBar);
			if (ShowLevels)
			{
				RemoveDrawObject("lvS"); RemoveDrawObject("lvRU"); RemoveDrawObject("lvRD");
				if (mode != "NEUTRAL" && hasStanding)
					Draw.Line(this, "lvS", false, lb, standingPx, -4, standingPx,
						Brushes.DimGray, DashStyleHelper.Dash, 2);
				if (mode == "NEUTRAL")
				{
					if (lsh != null && hasHl)
						Draw.Line(this, "lvRU", false, lb, HiAt(lsh.Bar), -4, HiAt(lsh.Bar),
							Brushes.Green, DashStyleHelper.Dot, 2);
					if (lsl != null && hasLh)
						Draw.Line(this, "lvRD", false, lb, LoAt(lsl.Bar), -4, LoAt(lsl.Bar),
							Brushes.Firebrick, DashStyleHelper.Dot, 2);
				}
			}
			// armed 2E triggers
			if (ShowTriggers)
			{
				RemoveDrawObject("tgL"); RemoveDrawObject("tgS");
				if (hasLongTrig && mode == "BULL" && !skipDay)
					Draw.Line(this, "tgL", false, tb, armedLongTrig, -4, armedLongTrig,
						Brushes.LimeGreen, DashStyleHelper.DashDot, 2);
				if (hasShortTrig && mode == "BEAR" && !skipDay)
					Draw.Line(this, "tgS", false, tb, armedShortTrig, -4, armedShortTrig,
						Brushes.OrangeRed, DashStyleHelper.DashDot, 2);
			}

			// Tier-1 hover plots (Data Box shows these per hovered bar)
			Values[0][0] = mode == "BULL" ? 1 : mode == "BEAR" ? -1 : 0;
			string bc = CurBarClass();
			Values[1][0] = bc == "up" ? 1 : bc == "down" ? -1 : bc == "EQUAL=IB" ? 2
				: bc.StartsWith("OB U") ? 3 : bc.StartsWith("OB D") ? -3 : 0;
			double dMinP = double.NaN, dMajP = double.NaN;
			for (int i = piv.Count - 1; i >= 0; i--)
			{
				double pp = piv[i].IsH ? HiAt(piv[i].Bar) : LoAt(piv[i].Bar);
				if (double.IsNaN(dMinP)) dMinP = Close[0] - pp;
				if (piv[i].Major) { dMajP = Close[0] - pp; break; }
			}
			Values[2][0] = double.IsNaN(dMinP) ? 0 : dMinP;
			Values[3][0] = double.IsNaN(dMajP) ? 0 : dMajP;
			Values[4][0] = mode != "NEUTRAL" && hasStanding ? standingPx : 0;
			Values[5][0] = double.IsNaN(gapPct) ? 0 : gapPct;
			Values[6][0] = skipDay ? 1 : 0;
			Values[7][0] = adrStopTicks;
			Values[8][0] = ecL;
			Values[9][0] = ecS;
			Values[10][0] = mode != "NEUTRAL" && trendStartBar >= 0 ? formBar - trendStartBar : 0;
			Values[11][0] = !double.IsNaN(adr10) && adr10 > 0 && sessHigh > sessLow
				? (sessHigh - sessLow) / adr10 : 0;
			Values[12][0] = double.IsNaN(hvl) ? 0 : (Close[0] >= hvl ? 1 : -1);
			Values[13][0] = double.IsNaN(hvl) ? 0 : Close[0] - hvl;

			DrawInfoBox();
		}

		private void DrawInfoBox()
		{
			double px = Close[0];
			// distances to last minor / major pivot
			double dMin = double.NaN, dMaj = double.NaN;
			string majLab = "-";
			for (int i = piv.Count - 1; i >= 0; i--)
			{
				double pp = piv[i].IsH ? HiAt(piv[i].Bar) : LoAt(piv[i].Bar);
				if (double.IsNaN(dMin)) dMin = px - pp;
				if (piv[i].Major) { dMaj = px - pp; majLab = piv[i].MajLab; break; }
			}
			double openPnl = 0;
			foreach (var lot in fifo) openPnl += (px - lot.Item2) * lot.Item1
				* Instrument.MasterInstrument.PointValue;
			int nTr = wins + losses;
			bool inWin = Time[0] >= winStartT && Time[0] < winEndT;
			var sb = new StringBuilder();
			if (!Bars.IsTickReplay)
				sb.Append("!! TICK REPLAY OFF - HISTORICAL STATES UNRELIABLE !!\n");
			sb.AppendFormat("{0:ddd}  {0:HH:mm:ss}   b#{1}\n", Time[0], formBar + 1);
			sb.AppendFormat("bar: {0}\n", CurBarClass());
			sb.AppendFormat("REGIME: {0}{1}\n", mode,
				mode != "NEUTRAL" && trendStartBar >= 0 ? "  (b" + (trendStartBar + 1) + ", " + (formBar - trendStartBar) + " bars)" : "");
			sb.AppendFormat("last minor piv: {0}\n",
				double.IsNaN(dMin) ? "-" : (dMin >= 0 ? "+" : "") + dMin.ToString("F2") + " pts");
			sb.AppendFormat("last MAJOR ({0}): {1}\n", majLab,
				double.IsNaN(dMaj) ? "-" : (dMaj >= 0 ? "+" : "") + dMaj.ToString("F2") + " pts");
			if (mode != "NEUTRAL" && hasStanding)
				sb.AppendFormat("standing lvl: {0:F2} ({1}{2:F2})\n", standingPx,
					px - standingPx >= 0 ? "+" : "", px - standingPx);
			if (!double.IsNaN(hvl))
				sb.AppendFormat("GAMMA: {0}  HVL {1:F0} ({2}{3:F2}p){4}{5}\n",
					px >= hvl ? "POS" : "NEG", hvl,
					px - hvl >= 0 ? "+" : "", px - hvl,
					double.IsNaN(hvl0) ? "" : "  0dte " + hvl0.ToString("F0"),
					hvlIsPrev ? "  [prev " + hvlDate + "]" : "");
			else
				sb.Append("GAMMA: no HVL data\n");
			sb.AppendFormat("gap: {0}   ADR10: {1}\n",
				double.IsNaN(gapPct) ? "warmup" : gapPct.ToString("+0.00;-0.00") + "%"
					+ (skipDay ? "  SKIP-DAY" : ""),
				double.IsNaN(adr10) ? "-" : adr10.ToString("F1") + "p");
			sb.AppendFormat("stop: {0}\n", adrStopTicks > 0
				? adrStopTicks + "t (" + (adrStopTicks * TICK).ToString("F2") + "p)" : "warmup");
			sb.AppendFormat("window: {0}\n", inWin
				? "OPEN " + (winEndT - Time[0]).TotalMinutes.ToString("F0") + "m left"
				: (Time[0] < winStartT ? "opens " + (winStartT - Time[0]).TotalMinutes.ToString("F0") + "m"
					: "CLOSED"));
			sb.AppendFormat("flat-by: {0:HH:mm}   day rng/ADR: {1}\n", flatT,
				double.IsNaN(adr10) || sessHigh <= sessLow ? "-"
					: ((sessHigh - sessLow) / adr10).ToString("F2"));
			sb.AppendFormat("2E: L {0}  S {1}\n",
				hasLongTrig ? "ARMED @" + armedLongTrig.ToString("F2") : "ec" + ecL,
				hasShortTrig ? "ARMED @" + armedShortTrig.ToString("F2") : "ec" + ecS);
			if (acct != null)
				sb.AppendFormat("PnL: {0:+0;-0}$ real  {1:+0;-0}$ open   W/L: {2}/{3} ({4}%)",
					realized, openPnl, wins, losses, nTr > 0 ? (100 * wins / nTr) : 0);
			else
				sb.Append("PnL: account '" + AccountName + "' not found");
			Draw.TextFixed(this, "cockpit", sb.ToString(), TextPosition.BottomRight,
				Brushes.White, new Gui.Tools.SimpleFont("Consolas", 12),
				Brushes.DimGray, new SolidColorBrush(Color.FromArgb(200, 20, 24, 29)), 60);
		}

		#region Properties
		[NinjaScriptProperty] public string AccountName { get; set; }
		[NinjaScriptProperty] public string HvlCsvPath { get; set; }
		[NinjaScriptProperty] public bool ShowHvlLine { get; set; }
		[NinjaScriptProperty] public bool ShowPivotTags { get; set; }
		[NinjaScriptProperty] public bool ShowLevels { get; set; }
		[NinjaScriptProperty] public bool ShowTriggers { get; set; }
		[NinjaScriptProperty] public double GapMaxPct { get; set; }
		[NinjaScriptProperty] public double StopAdrMult { get; set; }
		[NinjaScriptProperty] public int StopFloorTicks { get; set; }
		[NinjaScriptProperty] public int WindowStartMin { get; set; }
		[NinjaScriptProperty] public int WindowEndMin { get; set; }
		[NinjaScriptProperty] public int FlatAfterMin { get; set; }
		#endregion
	}
}
