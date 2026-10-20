#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Controls;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

// ─────────────────────────────────────────────────────────────────────────────
// PATsProfile — right-margin Volume Profile with the full Dalton toolkit, drawn
// OUTWARD from the last bar so price action is never covered. Every level/band/
// node is individually toggleable and colorable.
//
//   Volume Profile : POC, 70% value area (MOM Appendix 1, two-at-a-time),
//                    value-area band OR lines-only, HVN / LVN nodes,
//                    initial balance (RTH-anchored), prior-session value.
//   Labels         : numeric VAH/VAL/POC (current + prior), de-collided with
//                    leader lines so text never overlaps a line or another label.
//   Composite      : merge the last N sessions into one profile.
// Every band/line stops at its own session's left break.
//
// Volume-at-price precision:
//   - TODAY is always built from real trade ticks via OnMarketData — free,
//     since live data streams tick-by-tick regardless of this indicator.
//   - Earlier (closed) sessions use the OHLC bar-split approximation UNLESS
//     you turn on "Tick Replay" in the chart's Data Series settings (NT8-level
//     setting — an Indicator can't enable it from code, only read it via
//     Bars.IsTickReplay). When it's on, NT8 replays historical ticks too
//     (heavier chart load — depends on your feed actually serving tick-level
//     history back that far).
//   - Closed sessions are computed once and cached (barVolBySession) instead
//     of being re-walked on every recompute.
//
// IB (Initial Balance) is anchored to RthStartHHMM (RTH open time-of-day),
// not to the session's own start bar — on a chart whose session includes
// overnight/ETH bars, the session start is NOT the RTH open, and classical
// Market Profile IB is an RTH-only concept.
//
// Commit CS to: repo/nt8/indicators/PATsProfile.cs
// ─────────────────────────────────────────────────────────────────────────────
namespace NinjaTrader.NinjaScript.Indicators
{
	public class PATsProfile : Indicator
	{
		private double rowSize;
		private List<int> sessionStarts;

		private Dictionary<double, double> volByRow;
		private List<double> hvn, lvn;
		private double poc, vah, val, ibh, ibl, maxVol;
		private double pPoc = double.NaN, pVah = double.NaN, pVal = double.NaN; // prior VOLUME VA
		private int winStartBar, priorStartBar = -1, todayStartBar = -1;

		// Developing (today-only) VA, as of the CLOSE of each bar -- the true history,
		// not today's final number projected backward. devVah/devVal/devPoc[k] is the
		// value area computed from only the volume known through bar (devSessionStart+k).
		// Folded incrementally, once per closed bar (see FoldBarIntoDev) -- cheap, and
		// naturally correct on a fresh chart load too (the fold loop just walks every
		// historical bar in order exactly like live does, no separate seeding needed).
		private Dictionary<double, double> devCumVol;
		private int devSessionStart = -1, devFoldedThroughBar = -1;
		private List<double> devVah = new List<double>();
		private List<double> devVal = new List<double>();
		private List<double> devPoc = new List<double>();

		// Session VWAP + volume-weighted SD bands -- unlike VA, VWAP is ALWAYS a running
		// series by definition (every platform plots it developing), so it uses the exact
		// same per-bar fold as devVah/devVal/devPoc above, just a different running stat:
		// cumPV/cumV/cumPV2 -> vwap = cumPV/cumV, sd = sqrt(cumPV2/cumV - vwap^2).
		private double devCumPV, devCumV, devCumPV2;
		private List<double> devVwap = new List<double>();
		private List<double> devVwapSd = new List<double>();
		private double curVwap = double.NaN; // today-only VWAP as of now; set by DrawDevelopingVA, read by the label block

		// Archived developing series for CLOSED sessions, keyed by that session's start bar --
		// a snapshot of devVah/devVal/devPoc/devVwap/devVwapSd taken the moment a session ends
		// (right before the live arrays reset for the new one). This is what DevHistSessions
		// renders: each entry is a finished, immutable session's own full developing trail, not
		// recomputed later. Needs only the chart's own loaded bars (same bar-split approximation
		// as today) -- NOT the L1 tape archive -- so it covers however many days the chart has
		// bars for, same depth as every other closed-session feature in this file.
		private class DevSeries
		{
			public List<double> Vah = new List<double>();
			public List<double> Val = new List<double>();
			public List<double> Poc = new List<double>();
			public List<double> Vwap = new List<double>();
			public List<double> VwapSd = new List<double>();
		}
		private Dictionary<int, DevSeries> devHistBySession = new Dictionary<int, DevSeries>();

		// Chart-toolbar declutter buttons (2026-10-20) -- pattern copied from
		// nt8/vendor/ab/MyABToolbarButtons.cs (chartWindow.MainMenu.Add()), the same
		// technique the now-deleted ClaudeTrackerHealthLight.cs used. Lets the user instantly
		// kill rendering to grab a chart drawing object sitting under a VA fill, instead of
		// digging through the Indicators dialog. Runtime-only state (not NinjaScriptProperty):
		// these are UI toggles, not template-saved preferences.
		private Chart chartWindow;
		private bool toolbarAdded;
		private bool showAll = true;
		private bool devStairstep = true; // false = flat current-level line across the whole session instead of the per-bar staircase
		private int lastDevHistSessions = 1;
		private Button btnVpAll, btnVpVaToday, btnVpVaPrior, btnVpStair, btnVpHist, btnVpLbl;

		// Tick-accurate accumulation (see header note).
		private readonly object liveLock = new object();
		private Dictionary<double, double> liveVolByRow;
		private int liveSessionStartBar = -1;
		private int obuSessionStartBar = -1;
		private Dictionary<int, Dictionary<double, double>> tickHistBySession; // filled only when Bars.IsTickReplay is on
		private Dictionary<int, Dictionary<double, double>> barVolBySession;   // cache of finalized (closed) sessions

		#region Parameters
		[NinjaScriptProperty] [Range(1, int.MaxValue)] [Display(Name = "Row height (ticks)", Order = 0, GroupName = "1 Profile")]
		public int RowTicks { get; set; }
		[NinjaScriptProperty] [Range(1, 60)] [Display(Name = "Composite sessions (1 = today)", Order = 1, GroupName = "1 Profile")]
		public int CompositeSessions { get; set; }
		[NinjaScriptProperty] [Range(20, 800)] [Display(Name = "VP width (px)", Order = 2, GroupName = "1 Profile")]
		public int VpWidthPx { get; set; }
		[NinjaScriptProperty] [Range(0, 800)] [Display(Name = "Right offset (px)", Order = 3, GroupName = "1 Profile")]
		public int RightOffsetPx { get; set; }
		[NinjaScriptProperty] [Range(0.05, 1.0)] [Display(Name = "Opacity", Order = 4, GroupName = "1 Profile")]
		public double Opacity { get; set; }
		[NinjaScriptProperty] [Range(6, 24)] [Display(Name = "Label font size", Order = 5, GroupName = "1 Profile")]
		public int LabelFontSize { get; set; }
		[NinjaScriptProperty] [Range(5, 240)] [Display(Name = "Initial balance minutes", Order = 6, GroupName = "1 Profile")]
		public int IbMinutes { get; set; }
		[NinjaScriptProperty] [Range(0, 2359)] [Display(Name = "RTH start (HHmm, chart time)", Order = 7, GroupName = "1 Profile")]
		public int RthStartHHMM { get; set; }
		[NinjaScriptProperty] [Range(0, 60)] [Display(Name = "Historical developing sessions", Order = 8, GroupName = "1 Profile")]
		public int DevHistSessions { get; set; }

		[NinjaScriptProperty] [Display(Name = "Volume Profile", Order = 0, GroupName = "2 Show")]
		public bool ShowVP { get; set; }
		[NinjaScriptProperty] [Display(Name = "VAH / VAL lines", Order = 1, GroupName = "2 Show")]
		public bool ShowVAHVAL { get; set; }
		[NinjaScriptProperty] [Display(Name = "Value-area band (shaded)", Order = 2, GroupName = "2 Show")]
		public bool ShowVABand { get; set; }
		[NinjaScriptProperty] [Display(Name = "POC", Order = 3, GroupName = "2 Show")]
		public bool ShowPOC { get; set; }
		[NinjaScriptProperty] [Display(Name = "Initial balance", Order = 4, GroupName = "2 Show")]
		public bool ShowIB { get; set; }
		[NinjaScriptProperty] [Display(Name = "HVN (high-volume nodes)", Order = 5, GroupName = "2 Show")]
		public bool ShowHVN { get; set; }
		[NinjaScriptProperty] [Display(Name = "LVN (low-volume nodes)", Order = 6, GroupName = "2 Show")]
		public bool ShowLVN { get; set; }
		[NinjaScriptProperty] [Display(Name = "Prior VOLUME-VA lines", Order = 7, GroupName = "2 Show")]
		public bool ShowPriorLines { get; set; }
		[NinjaScriptProperty] [Display(Name = "Prior VOLUME-VA band", Order = 8, GroupName = "2 Show")]
		public bool ShowPriorBand { get; set; }
		[NinjaScriptProperty] [Display(Name = "Labels", Order = 9, GroupName = "2 Show")]
		public bool ShowLabels { get; set; }
		[NinjaScriptProperty] [Display(Name = "Session VWAP + bands", Order = 10, GroupName = "2 Show")]
		public bool ShowVWAP { get; set; }

		[NinjaScriptProperty] [Range(1, 20)] [Display(Name = "Node lookback (rows)", Order = 0, GroupName = "3 Nodes")]
		public int NodeLookback { get; set; }
		[NinjaScriptProperty] [Range(1.0, 5.0)] [Display(Name = "HVN factor (x avg)", Order = 1, GroupName = "3 Nodes")]
		public double HvnFactor { get; set; }
		[NinjaScriptProperty] [Range(0.0, 1.0)] [Display(Name = "LVN factor (x avg)", Order = 2, GroupName = "3 Nodes")]
		public double LvnFactor { get; set; }

		[NinjaScriptProperty] [Range(0.1, 5.0)] [Display(Name = "VWAP band 1 (x SD)", Order = 0, GroupName = "5 VWAP")]
		public double VwapSdMult1 { get; set; }
		[NinjaScriptProperty] [Range(0.1, 5.0)] [Display(Name = "VWAP band 2 (x SD)", Order = 1, GroupName = "5 VWAP")]
		public double VwapSdMult2 { get; set; }

		[XmlIgnore] [Display(Name = "POC", Order = 0, GroupName = "4 Colors")]
		public System.Windows.Media.Brush PocColor { get; set; }
		[Browsable(false)] public string PocColorSerialize { get { return Serialize.BrushToString(PocColor); } set { PocColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Value area", Order = 1, GroupName = "4 Colors")]
		public System.Windows.Media.Brush VaColor { get; set; }
		[Browsable(false)] public string VaColorSerialize { get { return Serialize.BrushToString(VaColor); } set { VaColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Prior session", Order = 2, GroupName = "4 Colors")]
		public System.Windows.Media.Brush PriorColor { get; set; }
		[Browsable(false)] public string PriorColorSerialize { get { return Serialize.BrushToString(PriorColor); } set { PriorColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "HVN", Order = 3, GroupName = "4 Colors")]
		public System.Windows.Media.Brush HvnColor { get; set; }
		[Browsable(false)] public string HvnColorSerialize { get { return Serialize.BrushToString(HvnColor); } set { HvnColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "LVN", Order = 4, GroupName = "4 Colors")]
		public System.Windows.Media.Brush LvnColor { get; set; }
		[Browsable(false)] public string LvnColorSerialize { get { return Serialize.BrushToString(LvnColor); } set { LvnColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "Initial balance", Order = 5, GroupName = "4 Colors")]
		public System.Windows.Media.Brush IbColor { get; set; }
		[Browsable(false)] public string IbColorSerialize { get { return Serialize.BrushToString(IbColor); } set { IbColor = Serialize.StringToBrush(value); } }
		[XmlIgnore] [Display(Name = "VWAP", Order = 6, GroupName = "4 Colors")]
		public System.Windows.Media.Brush VwapColor { get; set; }
		[Browsable(false)] public string VwapColorSerialize { get { return Serialize.BrushToString(VwapColor); } set { VwapColor = Serialize.StringToBrush(value); } }

		// Full color/width/dash-style/opacity editor (NT8's native Stroke control -- same
		// pattern as nt8/vendor/ntlambda/.../NTLAnchoredVwap.cs's Stroke properties) for the
		// developing VA's VAH/VAL and POC lines, in BOTH stairstep and flat (Stair-button-off)
		// modes. Unlike the Brush-typed colors above, Stroke serializes natively -- no
		// companion XxxSerialize string property needed.
		[Display(Name = "Developing VAH/VAL line", Order = 7, GroupName = "4 Colors")]
		public Stroke DevVaStroke { get; set; }
		[Display(Name = "Developing POC line", Order = 8, GroupName = "4 Colors")]
		public Stroke DevPocStroke { get; set; }
		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name = "PATs Profile (VP)";
				Description = "Right-margin Volume Profile: POC, value area, HVN/LVN, RTH initial balance, prior-session zone, developing VA staircase (today + N historical sessions), session VWAP+SD bands, labels, composite.";
				IsOverlay = true; IsChartOnly = true; DrawOnPricePanel = true; IsSuspendedWhileInactive = true;
				RowTicks = 4; CompositeSessions = 1; VpWidthPx = 150; RightOffsetPx = 6;
				Opacity = 0.85; LabelFontSize = 11; IbMinutes = 60; RthStartHHMM = 930; DevHistSessions = 1;
				ShowVP = true; ShowVAHVAL = true; ShowVABand = true; ShowPOC = true; ShowIB = true;
				ShowHVN = true; ShowLVN = true; ShowPriorLines = true; ShowPriorBand = true; ShowLabels = true;
				ShowVWAP = false; // 2026-10-20: user is using Lizard Trader's VWAP instead; code stays, defaults off
				NodeLookback = 4; HvnFactor = 1.2; LvnFactor = 0.7;
				VwapSdMult1 = 1.0; VwapSdMult2 = 2.0;
				PocColor = System.Windows.Media.Brushes.Orange;
				VaColor = System.Windows.Media.Brushes.MediumPurple;
				PriorColor = System.Windows.Media.Brushes.SteelBlue;
				HvnColor = System.Windows.Media.Brushes.DarkTurquoise;
				LvnColor = System.Windows.Media.Brushes.IndianRed;
				IbColor = System.Windows.Media.Brushes.Goldenrod;
				VwapColor = System.Windows.Media.Brushes.White;
				DevVaStroke = new Stroke(System.Windows.Media.Brushes.MediumPurple, 1.2f);
				DevPocStroke = new Stroke(System.Windows.Media.Brushes.Orange, 1.2f);
			}
			else if (State == State.Configure) { rowSize = RowTicks * TickSize; }
			else if (State == State.DataLoaded)
			{
				sessionStarts = new List<int>();
				tickHistBySession = new Dictionary<int, Dictionary<double, double>>();
				barVolBySession = new Dictionary<int, Dictionary<double, double>>();
				devHistBySession = new Dictionary<int, DevSeries>();
				liveVolByRow = null; liveSessionStartBar = -1; obuSessionStartBar = -1;
			}
			else if (State == State.Realtime)
			{
				SeedLiveFromHistory();
				if (ChartControl != null && !toolbarAdded)
					ChartControl.Dispatcher.InvokeAsync((Action)(() => AddToolbarButtons()));
			}
			else if (State == State.Terminated)
			{
				if (chartWindow != null)
					ChartControl.Dispatcher.InvokeAsync((Action)(() => RemoveToolbarButtons()));
			}
		}

		// Chart-toolbar declutter buttons -- see field comments above for why/pattern source.
		private void AddToolbarButtons()
		{
			chartWindow = Window.GetWindow(ChartControl.Parent) as Chart;
			if (chartWindow == null || chartWindow.MainMenu == null) return;

			Style btnStyle = new Style(typeof(Button));
			btnStyle.Setters.Add(new Setter(Button.FontSizeProperty, 12.0));
			btnStyle.Setters.Add(new Setter(Button.FontWeightProperty, FontWeights.Bold));
			btnStyle.Setters.Add(new Setter(Button.MarginProperty, new Thickness(2, 0, 2, 0)));
			btnStyle.Setters.Add(new Setter(Button.PaddingProperty, new Thickness(4, 2, 4, 2)));
			btnStyle.Setters.Add(new Setter(Button.ForegroundProperty, System.Windows.Media.Brushes.Blue));
			btnStyle.Setters.Add(new Setter(Button.BackgroundProperty, new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(255, 200, 120)))); // light orange
			btnStyle.Setters.Add(new Setter(Button.HorizontalAlignmentProperty, HorizontalAlignment.Center));

			btnVpAll = new Button { Content = "VP", Style = btnStyle, Visibility = Visibility.Visible };
			btnVpVaToday = new Button { Content = "VAt", Style = btnStyle, Visibility = Visibility.Visible };
			btnVpVaPrior = new Button { Content = "VAp", Style = btnStyle, Visibility = Visibility.Visible };
			btnVpStair = new Button { Content = "Stair", Style = btnStyle, Visibility = Visibility.Visible };
			btnVpHist = new Button { Content = "Hist", Style = btnStyle, Visibility = Visibility.Visible };
			btnVpLbl = new Button { Content = "Lbl", Style = btnStyle, Visibility = Visibility.Visible };

			btnVpAll.Click += (s, e) => { showAll = !showAll; ForceRefresh(); };
			// 2026-10-20: split into two -- VAt controls TODAY's own VA (shading+stepline
			// together), VAp controls PRIOR/historical sessions' VA, independently.
			btnVpVaToday.Click += (s, e) =>
			{
				bool on = !ShowVABand;
				ShowVABand = on; ShowVAHVAL = on;
				ForceRefresh();
			};
			// 2026-10-20 correction: VAp controls the PRIOR SESSION'S VA PROJECTED FORWARD
			// onto each shown session (today gets yesterday's final VA; a historical session
			// shown via DevHistSessions gets ITS OWN predecessor's -- e.g. Friday's VA on
			// Monday) -- i.e. ShowPriorBand+ShowPriorLines, NOT a filter on the staircase.
			btnVpVaPrior.Click += (s, e) =>
			{
				bool on = !ShowPriorBand;
				ShowPriorBand = on; ShowPriorLines = on;
				ForceRefresh();
			};
			btnVpStair.Click += (s, e) => { devStairstep = !devStairstep; ForceRefresh(); };
			btnVpHist.Click += (s, e) =>
			{
				if (DevHistSessions > 0) { lastDevHistSessions = DevHistSessions; DevHistSessions = 0; }
				else DevHistSessions = lastDevHistSessions;
				ForceRefresh();
			};
			btnVpLbl.Click += (s, e) => { ShowLabels = !ShowLabels; ForceRefresh(); };

			chartWindow.MainMenu.Add(btnVpAll);
			chartWindow.MainMenu.Add(btnVpVaToday);
			chartWindow.MainMenu.Add(btnVpVaPrior);
			chartWindow.MainMenu.Add(btnVpStair);
			chartWindow.MainMenu.Add(btnVpHist);
			chartWindow.MainMenu.Add(btnVpLbl);
			toolbarAdded = true;
		}

		private void RemoveToolbarButtons()
		{
			if (chartWindow == null) return;
			if (btnVpAll != null) chartWindow.MainMenu.Remove(btnVpAll);
			if (btnVpVaToday != null) chartWindow.MainMenu.Remove(btnVpVaToday);
			if (btnVpVaPrior != null) chartWindow.MainMenu.Remove(btnVpVaPrior);
			if (btnVpStair != null) chartWindow.MainMenu.Remove(btnVpStair);
			if (btnVpHist != null) chartWindow.MainMenu.Remove(btnVpHist);
			if (btnVpLbl != null) chartWindow.MainMenu.Remove(btnVpLbl);
			toolbarAdded = false;
		}

		// Runs exactly once, at the historical->realtime handoff. Without this,
		// the first live tick in OnMarketData would start today's session's
		// liveVolByRow from empty, silently discarding every bar that already
		// closed today before the chart/indicator was (re)loaded — today's VA
		// would visibly collapse to "from this moment forward" instead of the
		// full session. Seed with whatever's already known (tick-replayed
		// history if Tick Replay was on, else the bar-split approximation),
		// then let OnMarketData add real ticks on top from here forward.
		private void SeedLiveFromHistory()
		{
			if (obuSessionStartBar < 0 || CurrentBar < obuSessionStartBar) return;
			Dictionary<double, double> hist;
			Dictionary<double, double> seed = (tickHistBySession != null && tickHistBySession.TryGetValue(obuSessionStartBar, out hist) && hist.Count > 0)
				? new Dictionary<double, double>(hist)
				: BuildFromBars(obuSessionStartBar, CurrentBar);
			lock (liveLock)
			{
				liveVolByRow = seed;
				liveSessionStartBar = obuSessionStartBar;
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0) return;
			if (rowSize <= 0) rowSize = RowTicks * TickSize;

			bool newSession = (CurrentBar == 0 || Bars.IsFirstBarOfSession) &&
			                   (sessionStarts.Count == 0 || sessionStarts[sessionStarts.Count - 1] != CurrentBar);

			// Fold every bar strictly before the current (possibly still-forming) one into
			// the developing series, exactly once each -- BEFORE the newSession archive/reset
			// below, using whatever session is still current at this point. A `while` (not
			// `if`) so this is correct whether OnBarUpdate fires once per bar (normal) or many
			// times per bar (Tick Replay). Ordering matters: this has to run first so that on
			// the exact call where a new session starts, the OLD session's own final bar
			// (CurrentBar-1) gets folded into ITS series before being archived below -- doing
			// this after the reset would silently archive every session one bar short, missing
			// its own close. Also naturally replays the WHOLE session in order on a fresh chart
			// load, so there's no separate historical-seeding step needed here (unlike
			// liveVolByRow, which this deliberately does not reuse).
			while (devCumVol != null && devFoldedThroughBar < CurrentBar - 1)
			{
				devFoldedThroughBar++;
				FoldBarIntoDev(devFoldedThroughBar);
			}

			if (newSession)
			{
				// Archive the just-finished session's full developing trail before wiping it
				// for the new one -- this is the ONLY place a session's dev series is ever
				// saved, so it has to happen before the Clear() calls below, not after.
				if (devSessionStart >= 0 && devVah.Count > 0)
				{
					devHistBySession[devSessionStart] = new DevSeries
					{
						Vah = new List<double>(devVah), Val = new List<double>(devVal), Poc = new List<double>(devPoc),
						Vwap = new List<double>(devVwap), VwapSd = new List<double>(devVwapSd)
					};
				}
				sessionStarts.Add(CurrentBar);
				obuSessionStartBar = CurrentBar;
				devCumVol = new Dictionary<double, double>();
				devVah.Clear(); devVal.Clear(); devPoc.Clear();
				devVwap.Clear(); devVwapSd.Clear();
				devCumPV = 0; devCumV = 0; devCumPV2 = 0;
				devSessionStart = CurrentBar;
				devFoldedThroughBar = CurrentBar - 1;
			}

			// Historical tick-accurate accumulation — only active when the chart's
			// Data Series "Tick Replay" setting is on (Bars.IsTickReplay); otherwise
			// OnBarUpdate fires once per bar close exactly as before (no added cost).
			if (Bars.IsTickReplay && State == State.Historical)
			{
				Dictionary<double, double> hist;
				if (!tickHistBySession.TryGetValue(obuSessionStartBar, out hist))
				{ hist = new Dictionary<double, double>(); tickHistBySession[obuSessionStartBar] = hist; }
				double key = Math.Round(Math.Floor(Close[0] / rowSize) * rowSize, 5);
				double cv; hist.TryGetValue(key, out cv); hist[key] = cv + Volume[0];
			}
		}

		// Fires on every live trade print regardless of Calculate mode or
		// TickReplayHistory — this is what keeps today's session tick-accurate
		// for free, without opting into historical tick replay.
		protected override void OnMarketData(MarketDataEventArgs e)
		{
			if (e.MarketDataType != MarketDataType.Last) return;
			if (State != State.Realtime) return;
			if (rowSize <= 0) return;
			double key = Math.Round(Math.Floor(e.Price / rowSize) * rowSize, 5);
			lock (liveLock)
			{
				if (liveVolByRow == null || liveSessionStartBar != obuSessionStartBar)
				{
					liveVolByRow = new Dictionary<double, double>();
					liveSessionStartBar = obuSessionStartBar;
				}
				double cv; liveVolByRow.TryGetValue(key, out cv); liveVolByRow[key] = cv + e.Volume;
			}
		}

		#region Computation
		private void Recompute(int endBar)
		{
			volByRow = new Dictionary<double, double>();
			int sc = sessionStarts.Count;
			int wIdx = Math.Max(0, sc - Math.Max(1, CompositeSessions));
			int startBar = sc > 0 ? sessionStarts[wIdx] : 0;
			winStartBar = startBar;
			int lastStart = sc > 0 ? sessionStarts[sc - 1] : 0;
			todayStartBar = lastStart;

			for (int k = wIdx; k < sc; k++)
			{
				int a = sessionStarts[k];
				int b = (k + 1 < sc) ? sessionStarts[k + 1] - 1 : endBar;
				MergeSessionVolume(volByRow, a, a, b, k == sc - 1);
			}

			ComputeIB(lastStart, endBar);

			poc = double.NaN; maxVol = 0;
			foreach (KeyValuePair<double, double> kv in volByRow)
				if (kv.Value > maxVol) { maxVol = kv.Value; poc = kv.Key; }
			ValueAreaOf(volByRow, poc, out val, out vah);
			ComputeNodes();
			ComputePriorLevels();
		}

		// IB is an RTH-only concept: anchor to the first bar in today's session
		// whose time-of-day is >= RthStartHHMM (not to the session's own start
		// bar, which on an ETH-inclusive chart is the overnight/Globex open),
		// then take the high/low of the next IbMinutes of bars from there.
		private void ComputeIB(int lastStart, int endBar)
		{
			ComputeIBFor(lastStart, endBar, out ibh, out ibl);
		}

		// 2026-10-20: generalized from "today only" -- user pointed out IB was never computed
		// for any DevHistSessions entry, only the live session. Same logic, callable per session.
		// 2026-10-20 BUG FIX: the previous version compared only TimeOfDay (clock time,
		// no date) against RthStartHHMM. For an ETH-inclusive session that opens in the
		// EVENING (e.g. 17:00), the very FIRST bar already has TimeOfDay=17:00 >= rthTod
		// (e.g. 09:30) -- so rthOpenBar locked onto the session's own ETH open instead of
		// the actual RTH open the NEXT morning. IB was being computed from the overnight
		// session, not RTH -- exactly the "IBH/L still being calculated on ETH" the user
		// confirmed. Fixed by anchoring to a full DateTime: start from the session's own
		// start-bar date + RthStartHHMM; if that clock time has ALREADY passed by the time
		// the session started (the evening-open case), it must be the following calendar
		// day's RTH open instead.
		private void ComputeIBFor(int sessionStartBar, int sessionEndBarInclusive, out double ibhOut, out double iblOut)
		{
			ibhOut = double.MinValue; iblOut = double.MaxValue;
			TimeSpan rthTod = new TimeSpan(RthStartHHMM / 100, RthStartHHMM % 100, 0);
			DateTime sessStart = Time.GetValueAt(sessionStartBar);
			DateTime rthOpenDt = sessStart.Date.Add(rthTod);
			if (rthOpenDt < sessStart) rthOpenDt = rthOpenDt.AddDays(1);

			int rthOpenBar = -1;
			for (int i = sessionStartBar; i <= sessionEndBarInclusive; i++)
				if (Time.GetValueAt(i) >= rthOpenDt) { rthOpenBar = i; break; }
			if (rthOpenBar < 0) return; // this session hasn't reached RTH open yet (or doesn't include it)

			DateTime ibEnd = rthOpenDt.AddMinutes(IbMinutes);
			for (int i = rthOpenBar; i <= sessionEndBarInclusive; i++)
			{
				if (Time.GetValueAt(i) >= ibEnd) break;
				double h = High.GetValueAt(i), l = Low.GetValueAt(i);
				if (h > ibhOut) ibhOut = h; if (l < iblOut) iblOut = l;
			}
		}

		// Fills `target` with one session's volume-at-price. Prefers real trade-tick
		// data when available (today always, via OnMarketData; earlier sessions only
		// if TickReplayHistory replayed them). Closed sessions are computed once and
		// cached — they never change, so there's no reason to re-walk their bars on
		// every recompute.
		private void MergeSessionVolume(Dictionary<double, double> target, int sessionStartBar, int a, int b, bool isToday)
		{
			Dictionary<double, double> snapshot = null;
			if (isToday)
			{
				lock (liveLock)
				{
					if (liveVolByRow != null && liveSessionStartBar == sessionStartBar && liveVolByRow.Count > 0)
						snapshot = new Dictionary<double, double>(liveVolByRow);
				}
				if (snapshot == null) snapshot = BuildFromBars(a, b); // no live ticks yet (e.g. pre-market attach)
			}
			else
			{
				if (!barVolBySession.TryGetValue(sessionStartBar, out snapshot))
				{
					Dictionary<double, double> hist;
					snapshot = (tickHistBySession.TryGetValue(sessionStartBar, out hist) && hist.Count > 0) ? hist : BuildFromBars(a, b);
					barVolBySession[sessionStartBar] = snapshot;
				}
			}
			foreach (KeyValuePair<double, double> kv in snapshot)
			{
				double cv; target.TryGetValue(kv.Key, out cv); target[kv.Key] = cv + kv.Value;
			}
		}

		// OHLC-bar-split approximation (fallback when no tick-level data is available).
		private Dictionary<double, double> BuildFromBars(int a, int b)
		{
			Dictionary<double, double> vol = new Dictionary<double, double>();
			for (int i = a; i <= b; i++)
			{
				double h = High.GetValueAt(i), l = Low.GetValueAt(i), v = Volume.GetValueAt(i);
				double lo = Math.Floor(l / rowSize) * rowSize;
				int nrows = (int)Math.Round((h - lo) / rowSize) + 1;
				if (nrows < 1) nrows = 1;
				double vShare = v / nrows;
				for (int r = 0; r < nrows; r++)
				{
					double key = Math.Round(lo + r * rowSize, 5);
					double cv; vol.TryGetValue(key, out cv); vol[key] = cv + vShare;
				}
			}
			return vol;
		}

		// Merges one bar's OHLC-approx volume into the running devCumVol total, then
		// records the resulting VA/POC as that bar's developing-series point. Also folds
		// the SAME bar's rows into the running VWAP sums (cumPV/cumV/cumPV2) in the same
		// pass -- one dictionary built, two running series updated from it. Always uses
		// the bar-split approximation (not tick data) -- this trail is about showing the
		// TRUE SHAPE of how VA/VWAP moved through the session, not matching the main
		// numbers' tick-for-tick precision; keeping it simple also keeps the fold cheap.
		private void FoldBarIntoDev(int barIndex)
		{
			if (barIndex < devSessionStart) return;
			Dictionary<double, double> barVol = BuildFromBars(barIndex, barIndex);
			foreach (KeyValuePair<double, double> kv in barVol)
			{
				double cv; devCumVol.TryGetValue(kv.Key, out cv); devCumVol[kv.Key] = cv + kv.Value;
				devCumPV += kv.Key * kv.Value;
				devCumV += kv.Value;
				devCumPV2 += kv.Key * kv.Key * kv.Value;
			}
			double p = double.NaN, mv = 0;
			foreach (KeyValuePair<double, double> kv in devCumVol) if (kv.Value > mv) { mv = kv.Value; p = kv.Key; }
			double vl, vh;
			ValueAreaOf(devCumVol, p, out vl, out vh);
			devVah.Add(vh); devVal.Add(vl); devPoc.Add(p);

			double vwap = devCumV > 0 ? devCumPV / devCumV : double.NaN;
			double variance = devCumV > 0 ? Math.Max(0, devCumPV2 / devCumV - vwap * vwap) : 0;
			devVwap.Add(vwap); devVwapSd.Add(Math.Sqrt(variance));
		}

		// Volume-weighted mean + SD of `vol` (same stats as the fold above, computed
		// once from a full dictionary instead of incrementally) -- used for the VWAP
		// live tip, which needs today's FULL current total, not a per-bar increment.
		private void VwapOf(Dictionary<double, double> vol, out double vwap, out double sd)
		{
			double pv = 0, v = 0, pv2 = 0;
			foreach (KeyValuePair<double, double> kv in vol)
			{
				pv += kv.Key * kv.Value; v += kv.Value; pv2 += kv.Key * kv.Key * kv.Value;
			}
			vwap = v > 0 ? pv / v : double.NaN;
			double variance = v > 0 ? Math.Max(0, pv2 / v - vwap * vwap) : 0;
			sd = Math.Sqrt(variance);
		}

		// Dalton volume value area (MOM Appendix 1): from POC, add the heavier of
		// the two rows above vs the two below, until 70% of volume is enclosed.
		private void ValueAreaOf(Dictionary<double, double> vol, double pocv, out double valO, out double vahO)
		{
			List<double> prices = new List<double>(vol.Keys); prices.Sort();
			int n = prices.Count;
			if (n == 0 || double.IsNaN(pocv)) { valO = vahO = double.NaN; return; }
			int pocI = prices.IndexOf(pocv); if (pocI < 0) pocI = 0;
			double total = 0; foreach (double vv in vol.Values) total += vv;
			double target = 0.70 * total; double acc = vol[prices[pocI]];
			int lo = pocI, hi = pocI;
			while (acc < target && (lo > 0 || hi < n - 1))
			{
				double up = (hi + 1 < n ? vol[prices[hi + 1]] : 0) + (hi + 2 < n ? vol[prices[hi + 2]] : 0);
				double dn = (lo - 1 >= 0 ? vol[prices[lo - 1]] : 0) + (lo - 2 >= 0 ? vol[prices[lo - 2]] : 0);
				bool upok = hi < n - 1, dnok = lo > 0;
				if (upok && (up >= dn || !dnok)) for (int k = 0; k < 2 && hi < n - 1; k++) { hi++; acc += vol[prices[hi]]; }
				else if (dnok) for (int k = 0; k < 2 && lo > 0; k++) { lo--; acc += vol[prices[lo]]; }
				else break;
			}
			valO = prices[lo]; vahO = prices[hi];
		}

		// HVN = local volume peak > avg*HvnFactor; LVN = local trough < avg*LvnFactor.
		// Contiguous rows tied at the same volume collapse to a single flagged node
		// (the first row of the run) instead of marking every tied row.
		private void ComputeNodes()
		{
			hvn = new List<double>(); lvn = new List<double>();
			List<double> prices = new List<double>(volByRow.Keys); prices.Sort();
			int n = prices.Count; if (n < 3) return;
			double total = 0; foreach (double v in volByRow.Values) total += v;
			double avg = total / n;
			for (int i = 0; i < n; i++)
			{
				double v = volByRow[prices[i]];
				bool isMax = true, isMin = true;
				for (int j = Math.Max(0, i - NodeLookback); j <= Math.Min(n - 1, i + NodeLookback); j++)
				{
					if (j == i) continue;
					double vj = volByRow[prices[j]];
					if (vj > v) isMax = false;
					if (vj < v) isMin = false;
				}
				bool tiedWithPrevFlagged = i > 0 && volByRow[prices[i - 1]] == v;
				if (isMax && v >= avg * HvnFactor && !(tiedWithPrevFlagged && hvn.Count > 0 && hvn[hvn.Count - 1] == prices[i - 1])) hvn.Add(prices[i]);
				if (isMin && v <= avg * LvnFactor && !(tiedWithPrevFlagged && lvn.Count > 0 && lvn[lvn.Count - 1] == prices[i - 1])) lvn.Add(prices[i]);
			}
		}

		private void ComputePriorLevels()
		{
			pPoc = pVah = pVal = double.NaN;
			priorStartBar = -1;
			int sc = sessionStarts.Count;
			if (sc < 2) return;
			priorStartBar = sessionStarts[sc - 2];
			ComputePriorFor(sc - 1, out pVal, out pVah, out pPoc);
		}

		// The predecessor-session's FINAL VA for sessionIdx (an index into sessionStarts).
		// Generalizes what ComputePriorLevels used to hardcode as "only today vs yesterday" --
		// 2026-10-20: user pointed out the prior-VA projection never showed on HISTORICAL
		// sessions (e.g. Friday's final VA projected onto Monday), only on today vs yesterday,
		// because this computation only ever ran once, for the last session. Now callable for
		// any session shown (today, or any DevHistSessions entry), each projecting ITS OWN
		// predecessor's final VA onto itself.
		private void ComputePriorFor(int sessionIdx, out double pval, out double pvah, out double ppoc)
		{
			pval = pvah = ppoc = double.NaN;
			if (sessionIdx < 1 || sessionIdx >= sessionStarts.Count) return;
			int ps = sessionStarts[sessionIdx - 1];
			int pe = sessionStarts[sessionIdx] - 1;
			if (pe < ps) return;
			Dictionary<double, double> pvol = new Dictionary<double, double>();
			MergeSessionVolume(pvol, ps, ps, pe, false);
			if (pvol.Count == 0) return;
			double mv = 0;
			foreach (KeyValuePair<double, double> kv in pvol) if (kv.Value > mv) { mv = kv.Value; ppoc = kv.Key; }
			ValueAreaOf(pvol, ppoc, out pval, out pvah);
		}

		// Renders one session's OWN predecessor's final VA as a flat band+lines, bounded to
		// [leftX, rightX] -- for today that's todayStartX..vpMaxRight (extends into the live VP
		// margin, as before); for a historical session shown via DevHistSessions, that's its own
		// start..its own end (the next session's start), never spilling into neighboring sessions.
		private void DrawPriorOnSession(ChartScale cs, float leftX, float rightX, double pval, double pvah, double ppoc,
			SolidColorBrush lineBr, SolidColorBrush bandBr)
		{
			if (double.IsNaN(pvah) || rightX <= leftX) return;
			if (ShowPriorBand)
			{
				float y1 = cs.GetYByValue(pvah), y2 = cs.GetYByValue(pval);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(leftX, Math.Min(y1, y2), rightX - leftX, Math.Abs(y2 - y1)), bandBr);
			}
			if (ShowPriorLines)
			{
				DrawLevel(cs, leftX, rightX, pvah, lineBr, 1.0f);
				DrawLevel(cs, leftX, rightX, pval, lineBr, 1.0f);
				DrawLevel(cs, leftX, rightX, ppoc, lineBr, 1.5f);
			}
		}
		#endregion

		private SharpDX.Color4 Dx(System.Windows.Media.Brush b, float alpha)
		{
			System.Windows.Media.SolidColorBrush scb = b as System.Windows.Media.SolidColorBrush;
			if (scb == null) return new SharpDX.Color4(0.6f, 0.6f, 0.6f, alpha);
			System.Windows.Media.Color c = scb.Color;
			return new SharpDX.Color4(c.R / 255f, c.G / 255f, c.B / 255f, alpha);
		}

		private class Lbl { public float y; public string text; public SolidColorBrush brush; public float trueY; public int col; }

		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (sessionStarts == null || RenderTarget == null || ChartBars == null || Bars == null) return;
			int endBar = Bars.Count - 1;
			if (endBar < 0) return;
			Recompute(endBar); // cheap now (cached closed sessions) — keeps today's VA current with live ticks
			if (volByRow == null || volByRow.Count == 0 || maxVol <= 0) return;
			if (!showAll) return; // "VP" toolbar button -- Recompute above still ran (keeps state current), nothing drawn

			float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(rowSize));
			if (rowH < 1f) rowH = 1f;
			float panelLeft = (float)ChartPanel.X;
			float winStartX = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, winStartBar));
			float todayStartX = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, todayStartBar));
			float vpLeft = chartControl.GetXByBarIndex(ChartBars, endBar) + RightOffsetPx;
			float vpMaxRight = vpLeft + VpWidthPx;

			// brushes
			SolidColorBrush teal = new SolidColorBrush(RenderTarget, new SharpDX.Color4(0.35f, 0.71f, 0.82f, (float)Opacity));
			SolidColorBrush pocBr = new SolidColorBrush(RenderTarget, Dx(PocColor, 0.95f));
			SolidColorBrush vaLineBr = new SolidColorBrush(RenderTarget, Dx(VaColor, 0.9f));
			SolidColorBrush vaBandBr = new SolidColorBrush(RenderTarget, Dx(VaColor, 0.12f));
			SolidColorBrush ibBr = new SolidColorBrush(RenderTarget, Dx(IbColor, 0.8f));
			SolidColorBrush priorLineBr = new SolidColorBrush(RenderTarget, Dx(PriorColor, 0.85f));
			SolidColorBrush priorBandBr = new SolidColorBrush(RenderTarget, Dx(PriorColor, 0.14f));
			SolidColorBrush hvnBr = new SolidColorBrush(RenderTarget, Dx(HvnColor, 0.95f));
			SolidColorBrush lvnBr = new SolidColorBrush(RenderTarget, Dx(LvnColor, 0.95f));
			SolidColorBrush vwapBr = new SolidColorBrush(RenderTarget, Dx(VwapColor, 0.9f));
			if (DevVaStroke != null) DevVaStroke.RenderTarget = RenderTarget;
			if (DevPocStroke != null) DevPocStroke.RenderTarget = RenderTarget;
			HashSet<double> hvnSet = new HashSet<double>(hvn ?? new List<double>());
			HashSet<double> lvnSet = new HashSet<double>(lvn ?? new List<double>());

			// bands (behind). Current VA band only spans winStartX..todayStartX -- the
			// COMPLETED prior days inside a composite window, where a flat band is an
			// honest fact. It deliberately stops at today's own bars instead of extending
			// through them: see the developing staircase below for today's true history.
			if (ShowVABand && !double.IsNaN(vah) && todayStartX > winStartX)
			{
				float y1 = chartScale.GetYByValue(vah), y2 = chartScale.GetYByValue(val);
				RenderTarget.FillRectangle(new SharpDX.RectangleF(winStartX, Math.Min(y1, y2), todayStartX - winStartX, Math.Abs(y2 - y1)), vaBandBr);
			}
			// rows: VP bars (with node coloring)
			if (ShowVP)
			{
				foreach (KeyValuePair<double, double> kv in volByRow)
				{
					double price = kv.Key;
					float yTop = chartScale.GetYByValue(price + rowSize);
					float w = (float)(VpWidthPx * kv.Value / maxVol);
					SolidColorBrush br = teal;
					if (ShowPOC && price == poc) br = pocBr;
					else if (ShowHVN && hvnSet.Contains(price)) br = hvnBr;
					else if (ShowLVN && lvnSet.Contains(price)) br = lvnBr;
					RenderTarget.FillRectangle(new SharpDX.RectangleF(vpLeft, yTop, w, rowH - 1f), br);
				}
			}

			// lines (current). Same winStartX..todayStartX trim as the band above, same
			// reason -- only the completed-prior-days portion is a flat, honest fact.
			if (todayStartX > winStartX)
			{
				if (ShowPOC && !double.IsNaN(poc)) DrawLevel(chartScale, winStartX, todayStartX, poc, pocBr, 1.4f);
				if (ShowVAHVAL && !double.IsNaN(vah)) { DrawLevel(chartScale, winStartX, todayStartX, vah, vaLineBr, 1.0f); DrawLevel(chartScale, winStartX, todayStartX, val, vaLineBr, 1.0f); }
			}
			if (ShowIB && ibh > double.MinValue) { DrawLevel(chartScale, todayStartX, vpMaxRight, ibh, ibBr, 0.9f); DrawLevel(chartScale, todayStartX, vpMaxRight, ibl, ibBr, 0.9f); }
			DrawDevelopingVA(chartScale, chartControl, todayStartX, vpMaxRight, endBar, vaBandBr, vwapBr);
			int sc2 = sessionStarts.Count;
			if (DevHistSessions > 0)
			{
				List<string> histDates = new List<string>();
				for (int back = 1; back <= DevHistSessions && sc2 - 1 - back >= 0; back++)
				{
					int idxH = sc2 - 1 - back;
					int sBar = sessionStarts[idxH];
					DrawHistSessionDevVA(chartScale, chartControl, sBar, panelLeft, vaBandBr, vwapBr);
					// IB, generalized the same way as the VA/prior-VA fixes above: was only ever
					// computed for today (2026-10-20 user: "IBH/L only gets calculated from the
					// RTH open onwards!" -- true, but also only for the LIVE session, never shown
					// on any DevHistSessions entry).
					if (ShowIB)
					{
						int sEnd = sessionStarts[idxH + 1] - 1;
						double hibh, hibl;
						ComputeIBFor(sBar, sEnd, out hibh, out hibl);
						if (hibh > double.MinValue)
						{
							float hLeftIb = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, sBar));
							float hRightIb = chartControl.GetXByBarIndex(ChartBars, sessionStarts[idxH + 1]);
							DrawLevel(chartScale, hLeftIb, hRightIb, hibh, ibBr, 0.9f);
							DrawLevel(chartScale, hLeftIb, hRightIb, hibl, ibBr, 0.9f);
						}
					}
					histDates.Add("H-" + back + " " + Time.GetValueAt(sBar).ToString("MM/dd"));
				}
				// Diagnostic readout: which actual calendar dates DevHistSessions resolved to --
				// "H-1"/"H-2"/etc. are session-boundary counts (per the chart's own trading-hours
				// template, e.g. a Sunday-evening ETH sliver can be its own session), NOT calendar
				// days back, so they don't line up 1:1 with weekday counting. This makes it
				// directly checkable instead of guessed (2026-10-20: user expected Friday to show
				// and it didn't -- answer is either DevHistSessions needs to be higher, or the
				// chart's own "Days to load" doesn't have Friday's bars loaded at all, in which
				// case it can never appear here regardless of this setting).
				if (ShowLabels && histDates.Count > 0)
				{
					TextFormat diagTf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
					RenderTarget.DrawText(string.Join("   ", histDates), diagTf,
						new SharpDX.RectangleF(vpLeft, (float)ChartPanel.Y + 4f, 500f, LabelFontSize + 6f), vaLineBr);
					diagTf.Dispose();
				}
			}

			// Prior-session VA projected onto EACH shown session's own bars, not just today's --
			// 2026-10-20: this used to run once (today vs yesterday only), so it never appeared
			// on any DevHistSessions session (e.g. Friday's final VA projected onto Monday).
			// Drawn AFTER the staircases (band+lines together, last-drawn = on top) so it isn't
			// visually buried under them either.
			DrawPriorOnSession(chartScale, todayStartX, vpMaxRight, pVal, pVah, pPoc, priorLineBr, priorBandBr);
			for (int back = 1; back <= DevHistSessions && sc2 - 1 - back >= 0; back++)
			{
				int idx = sc2 - 1 - back;
				float hLeft = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, sessionStarts[idx]));
				float hRight = chartControl.GetXByBarIndex(ChartBars, sessionStarts[idx + 1]);
				double hpv, hph, hpp;
				ComputePriorFor(idx, out hpv, out hph, out hpp);
				DrawPriorOnSession(chartScale, hLeft, hRight, hpv, hph, hpp, priorLineBr, priorBandBr);
			}

			// labels (de-collided, with leaders), placed right of the profile
			if (ShowLabels)
			{
				float labelX = vpMaxRight + 8f;
				List<Lbl> labels = new List<Lbl>();
				// column 0 = current session
				if (ShowPOC && !double.IsNaN(poc)) AddLbl(labels, chartScale, "POC " + FmtP(poc), poc, pocBr, 0);
				if (ShowVAHVAL && !double.IsNaN(vah)) { AddLbl(labels, chartScale, "VAH " + FmtP(vah), vah, vaLineBr, 0); AddLbl(labels, chartScale, "VAL " + FmtP(val), val, vaLineBr, 0); }
				if (ShowIB && ibh > double.MinValue) { AddLbl(labels, chartScale, "IBH " + FmtP(ibh), ibh, ibBr, 0); AddLbl(labels, chartScale, "IBL " + FmtP(ibl), ibl, ibBr, 0); }
				if (ShowVWAP && !double.IsNaN(curVwap)) AddLbl(labels, chartScale, "VWAP " + FmtP(curVwap), curVwap, vwapBr, 0);
				// column 1 = prior VOLUME value area
				if (ShowPriorLines && !double.IsNaN(pVah)) { AddLbl(labels, chartScale, "pVAH " + FmtP(pVah), pVah, priorLineBr, 1); AddLbl(labels, chartScale, "pPOC " + FmtP(pPoc), pPoc, priorLineBr, 1); AddLbl(labels, chartScale, "pVAL " + FmtP(pVal), pVal, priorLineBr, 1); }
				DrawLabels(labels, labelX, vpMaxRight);
			}

			teal.Dispose(); pocBr.Dispose(); vaLineBr.Dispose(); vaBandBr.Dispose(); ibBr.Dispose();
			priorLineBr.Dispose(); priorBandBr.Dispose();
			hvnBr.Dispose(); lvnBr.Dispose(); vwapBr.Dispose();
		}

		private void DrawLevel(ChartScale cs, float x0, float x1, double price, SolidColorBrush br, float wdt)
		{
			float y = cs.GetYByValue(price);
			RenderTarget.DrawLine(new SharpDX.Vector2(x0, y), new SharpDX.Vector2(x1, y), br, wdt);
		}

		private void PolyLine(ChartScale cs, float x0, double price0, float x1, double price1, SolidColorBrush br, float wdt)
		{
			RenderTarget.DrawLine(new SharpDX.Vector2(x0, cs.GetYByValue(price0)), new SharpDX.Vector2(x1, cs.GetYByValue(price1)), br, wdt);
		}

		// VWAP center + both SD band pairs for one segment. Each endpoint uses its OWN sd
		// (sd0 at x0, sd1 at x1), so the band width is itself a sloped line, not a fixed offset.
		private void DrawVwapBand(ChartScale cs, float x0, double v0, double sd0, float x1, double v1, double sd1, SolidColorBrush br)
		{
			PolyLine(cs, x0, v0, x1, v1, br, 1.4f);
			PolyLine(cs, x0, v0 + sd0 * VwapSdMult1, x1, v1 + sd1 * VwapSdMult1, br, 0.8f);
			PolyLine(cs, x0, v0 - sd0 * VwapSdMult1, x1, v1 - sd1 * VwapSdMult1, br, 0.8f);
			PolyLine(cs, x0, v0 + sd0 * VwapSdMult2, x1, v1 + sd1 * VwapSdMult2, br, 0.5f);
			PolyLine(cs, x0, v0 - sd0 * VwapSdMult2, x1, v1 - sd1 * VwapSdMult2, br, 0.5f);
		}

		// Shared step+fill+VWAP renderer for one session's developing trail, given its own
		// point series (one entry per folded bar) and a left anchor. Used for TODAY (point
		// series built by DrawDevelopingVA, with a live tip appended) and for each CLOSED
		// session shown via DevHistSessions (point series = that session's archived DevSeries,
		// fixed, no live tip -- the session is over, its last point IS its final value).
		private void DrawDevSeries(ChartScale cs, float startX, List<float> xs, List<double> vhs, List<double> vls,
			List<double> ps, List<double> vws, List<double> sds,
			bool showBand, bool showLines, bool showPoc, SolidColorBrush fillBr, SolidColorBrush vwapBr)
		{
			int cnt = xs.Count;
			if (cnt == 0) return;
			bool haveVa = DevVaStroke != null, havePoc = DevPocStroke != null;

			// VWAP + bands: a normal connected (sloping) line through each point, NOT a step --
			// unlike VA, VWAP is a continuously-defined running mean, so a straight segment
			// between consecutive values is both the standard rendering and the honest one.
			// Each endpoint's band offset uses THAT point's own SD (not a single shared value),
			// so the band width itself is a sloped line too, correctly narrow early/wide later.
			if (ShowVWAP && !double.IsNaN(vws[0]))
			{
				// flat lead-in from session start to the first fold point, using bar 0's own
				// value (there's no VWAP "before" any bar has closed) -- without this the line
				// visibly started one bar later than the VA staircase and the price itself.
				DrawVwapBand(cs, startX, vws[0], sds[0], xs[0], vws[0], sds[0], vwapBr);
				for (int k = 0; k + 1 < cnt; k++)
				{
					if (double.IsNaN(vws[k]) || double.IsNaN(vws[k + 1])) continue;
					DrawVwapBand(cs, xs[k], vws[k], sds[k], xs[k + 1], vws[k + 1], sds[k + 1], vwapBr);
				}
			}

			// "Stair" toolbar button: when OFF, skip the whole step/riser rendering below and
			// just draw ONE flat segment using the LAST point's values (today's live tip, or a
			// closed session's own final fold point) across the full [startX, xs[cnt-1]] width --
			// the pre-staircase behavior, kept as a toggle instead of removed, since sometimes
			// "where's the final number" is what's wanted instead of the developing shape.
			if (!devStairstep)
			{
				int last = cnt - 1;
				float yh0 = cs.GetYByValue(vhs[last]), yl0 = cs.GetYByValue(vls[last]);
				if (showBand)
					RenderTarget.FillRectangle(new SharpDX.RectangleF(startX, Math.Min(yh0, yl0), xs[last] - startX, Math.Abs(yl0 - yh0)), fillBr);
				if (showLines && haveVa)
				{
					RenderTarget.DrawLine(new SharpDX.Vector2(startX, yh0), new SharpDX.Vector2(xs[last], yh0), DevVaStroke.BrushDX, DevVaStroke.Width, DevVaStroke.StrokeStyle);
					RenderTarget.DrawLine(new SharpDX.Vector2(startX, yl0), new SharpDX.Vector2(xs[last], yl0), DevVaStroke.BrushDX, DevVaStroke.Width, DevVaStroke.StrokeStyle);
				}
				if (showPoc && havePoc)
				{
					float yp0 = cs.GetYByValue(ps[last]);
					RenderTarget.DrawLine(new SharpDX.Vector2(startX, yp0), new SharpDX.Vector2(xs[last], yp0), DevPocStroke.BrushDX, DevPocStroke.Width, DevPocStroke.StrokeStyle);
				}
				return;
			}

			float prevX = startX;
			for (int k = 0; k < cnt; k++)
			{
				float x = xs[k];
				if (x > prevX)
				{
					float yh = cs.GetYByValue(vhs[k]), yl = cs.GetYByValue(vls[k]);
					if (showBand)
						RenderTarget.FillRectangle(new SharpDX.RectangleF(prevX, Math.Min(yh, yl), x - prevX, Math.Abs(yl - yh)), fillBr);
					if (showLines && haveVa)
					{
						RenderTarget.DrawLine(new SharpDX.Vector2(prevX, yh), new SharpDX.Vector2(x, yh), DevVaStroke.BrushDX, DevVaStroke.Width, DevVaStroke.StrokeStyle);
						RenderTarget.DrawLine(new SharpDX.Vector2(prevX, yl), new SharpDX.Vector2(x, yl), DevVaStroke.BrushDX, DevVaStroke.Width, DevVaStroke.StrokeStyle);
					}
					if (showPoc && havePoc)
					{
						float yp = cs.GetYByValue(ps[k]);
						RenderTarget.DrawLine(new SharpDX.Vector2(prevX, yp), new SharpDX.Vector2(x, yp), DevPocStroke.BrushDX, DevPocStroke.Width, DevPocStroke.StrokeStyle);
					}
				}
				if (k + 1 < cnt)
				{
					if (showLines && haveVa)
					{
						float yh = cs.GetYByValue(vhs[k]), yhN = cs.GetYByValue(vhs[k + 1]);
						float yl = cs.GetYByValue(vls[k]), ylN = cs.GetYByValue(vls[k + 1]);
						RenderTarget.DrawLine(new SharpDX.Vector2(x, yh), new SharpDX.Vector2(x, yhN), DevVaStroke.BrushDX, DevVaStroke.Width, DevVaStroke.StrokeStyle);
						RenderTarget.DrawLine(new SharpDX.Vector2(x, yl), new SharpDX.Vector2(x, ylN), DevVaStroke.BrushDX, DevVaStroke.Width, DevVaStroke.StrokeStyle);
					}
					if (showPoc && havePoc)
					{
						float yp = cs.GetYByValue(ps[k]), ypN = cs.GetYByValue(ps[k + 1]);
						RenderTarget.DrawLine(new SharpDX.Vector2(x, yp), new SharpDX.Vector2(x, ypN), DevPocStroke.BrushDX, DevPocStroke.Width, DevPocStroke.StrokeStyle);
					}
				}
				prevX = x;
			}
		}

		// Today's VA as a connected, filled staircase instead of a flat backward-extended
		// band: each historical point is the VA as of that bar's CLOSE (devVah/devVal,
		// folded incrementally -- see FoldBarIntoDev), rendered step-after (the value holds
		// flat across the bar it was computed from, then jumps -- via a drawn vertical riser,
		// not just an implied gap -- to the next bar's value). The final segment is the LIVE
		// tip: today-only VA as of right now, extended through to the VP margin so the
		// staircase visually connects into the current profile panel. Reuses the same
		// ShowVABand/ShowVAHVAL/ShowPOC toggles and brushes as the (now prior-days-only)
		// static band/lines above -- this IS that same concept, just rendered honestly for
		// a still-developing session instead of as a single backward-projected snapshot.
		private void DrawDevelopingVA(ChartScale cs, ChartControl cc, float startX, float vpRight, int endBar,
			SolidColorBrush fillBr, SolidColorBrush vwapBr)
		{
			if (devSessionStart < 0 || todayStartBar < 0) return;

			int n = devVah.Count;
			List<float> xs = new List<float>(n + 1);
			List<double> vhs = new List<double>(n + 1);
			List<double> vls = new List<double>(n + 1);
			List<double> ps = new List<double>(n + 1);
			List<double> vws = new List<double>(n + 1);
			List<double> sds = new List<double>(n + 1);
			for (int k = 0; k < n; k++)
			{
				xs.Add(cc.GetXByBarIndex(ChartBars, devSessionStart + k + 1)); // boundary = start of next bar
				vhs.Add(devVah[k]); vls.Add(devVal[k]); ps.Add(devPoc[k]);
				vws.Add(devVwap[k]); sds.Add(devVwapSd[k]);
			}

			// live tip: today-only VA/VWAP as of right now (correct regardless of
			// CompositeSessions -- reuses the exact same today-prefers-live-ticks logic the
			// main numbers use, ONE dict shared by both the VA and VWAP live calculations).
			Dictionary<double, double> todayNow = new Dictionary<double, double>();
			MergeSessionVolume(todayNow, todayStartBar, todayStartBar, endBar, true);
			if (todayNow.Count > 0)
			{
				double tp = double.NaN, tmv = 0;
				foreach (KeyValuePair<double, double> kv in todayNow) if (kv.Value > tmv) { tmv = kv.Value; tp = kv.Key; }
				double tvl, tvh;
				ValueAreaOf(todayNow, tp, out tvl, out tvh);
				double tvwap, tsd;
				VwapOf(todayNow, out tvwap, out tsd);
				xs.Add(vpRight); // stretch the final segment into the VP margin panel
				vhs.Add(tvh); vls.Add(tvl); ps.Add(tp);
				vws.Add(tvwap); sds.Add(tsd);
				curVwap = tvwap;
			}
			else curVwap = double.NaN;

			if (xs.Count == 0) return;
			DrawDevSeries(cs, startX, xs, vhs, vls, ps, vws, sds, ShowVABand, ShowVAHVAL, ShowPOC, fillBr, vwapBr);
		}

		// One CLOSED session's own developing trail, drawn only over its own bars (fixed,
		// archived at DevSeries -- never recomputed, never extends into the next session).
		// 2026-10-20 correction: uses the SAME ShowVABand/ShowVAHVAL/ShowPOC globals as
		// today's own (DrawDevelopingVA) -- VAt is the master for "developing VA
		// shading+stepline" across every shown session, today or historical, since they're
		// the same rendering concept per session. VAp is a DIFFERENT, orthogonal layer (the
		// prior session's VA projected forward -- see DrawPriorOnSession), not a filter here.
		private void DrawHistSessionDevVA(ChartScale cs, ChartControl cc, int sessionStartBar, float panelLeft,
			SolidColorBrush fillBr, SolidColorBrush vwapBr)
		{
			DevSeries d;
			if (!devHistBySession.TryGetValue(sessionStartBar, out d) || d.Vah.Count == 0) return;
			int n = d.Vah.Count;
			List<float> xs = new List<float>(n);
			for (int k = 0; k < n; k++)
				xs.Add(cc.GetXByBarIndex(ChartBars, sessionStartBar + k + 1));
			float startX = Math.Max(panelLeft, cc.GetXByBarIndex(ChartBars, sessionStartBar));
			DrawDevSeries(cs, startX, xs, d.Vah, d.Val, d.Poc, d.Vwap, d.VwapSd,
				ShowVABand, ShowVAHVAL, ShowPOC, fillBr, vwapBr);
		}

		private void AddLbl(List<Lbl> list, ChartScale cs, string text, double price, SolidColorBrush br, int col)
		{
			float y = cs.GetYByValue(price);
			list.Add(new Lbl { y = y, trueY = y, text = text, brush = br, col = col });
		}

		// Each column is a separate x-slot; de-collide vertically within each column.
		private void DrawLabels(List<Lbl> labels, float baseX, float leaderFromX)
		{
			if (labels.Count == 0) return;
			float colW = LabelFontSize * 6.5f;
			float gap = LabelFontSize + 4f;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			for (int c = 0; c <= 1; c++)
			{
				List<Lbl> col = new List<Lbl>();
				foreach (Lbl L in labels) if (L.col == c) col.Add(L);
				if (col.Count == 0) continue;
				col.Sort(delegate (Lbl a, Lbl b) { return a.y.CompareTo(b.y); });
				for (int i = 1; i < col.Count; i++)
					if (col[i].y < col[i - 1].y + gap) col[i].y = col[i - 1].y + gap;
				float x = baseX + c * colW;
				foreach (Lbl L in col)
				{
					if (Math.Abs(L.y - L.trueY) > 1.5f)
						RenderTarget.DrawLine(new SharpDX.Vector2(x - 6f, L.trueY), new SharpDX.Vector2(x - 1f, L.y + LabelFontSize * 0.5f), L.brush, 0.6f);
					RenderTarget.DrawText(L.text, tf, new SharpDX.RectangleF(x, L.y, colW, LabelFontSize + 6f), L.brush);
				}
			}
			tf.Dispose();
		}

		private string FmtP(double p)
		{
			return p.ToString("0.##");
		}
	}
}
