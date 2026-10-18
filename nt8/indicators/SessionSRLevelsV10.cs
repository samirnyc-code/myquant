// SessionSRLevelsV10 — RTH + ETH session S/R levels, drawn from NT8's OWN CME trading-hours
// templates (not hardcoded clock times), so the lines land at the right spot on holidays
// and half-days too. Forked from SessionSRLevelsV9 (V9 left untouched, same pattern as every
// prior Vn jump in this file's history) to add developing POC/Value-Area.
//
// DEVELOPING POC/VA (S142+, 2026-10-18) — OFF by default (ShowDevPocVa), togglable to
// conserve resources per explicit user ask: when off, OnMarketData returns immediately
// and does zero work, matching V9's existing "feature off = its entire cost disappears"
// leanness philosophy (see the needEth/needRth/needSettle gating above).
//   LIVE, REAL-TIME ONLY: per-tick OnMarketData price/volume binning into a per-session
//   price->volume table (same real-time-only limitation as BidAskVolumeRatio.cs — it
//   does not fire for historical bars, so a day before this was running live has nothing
//   to accumulate). Developing POC/VAH/VAL recompute once per primary bar close (not
//   every tick — the greedy value-area expansion is cheap but there's no reason to pay
//   it more than once a bar).
//   HISTORY IS BUILT GOING FORWARD BY DEFAULT, BUT CAN BE BACKFILLED: each trading day's
//   FINAL developing POC/VAH/VAL is appended to a small persisted log
//   (data/vp_levels/session_vp_live_log.csv, date,vpoc,vah,val) the moment that day's
//   session boundary rolls — this is the only path while the feature stays running.
//   scripts/backfill_vp_log.py (S145, 2026-10-18) can also write rows into that SAME log
//   straight from the recorded L1 tape (data/l1_tape/), for any day BEFORE the feature was
//   ever turned on live — it never overwrites a day the live indicator already wrote. Both
//   VpByDate consumers below (the per-session box and the prior-session projection) just
//   read whatever is in the log; they don't care whether a given day's row came from the
//   live accumulator or the backfill script.
//
//   TWO DISTINCT THINGS ARE DRAWN (S145-3 revision — corrected THREE times after the user
//   flagged each miss: v1 drew #1 as a flat ray using the LATEST value only, not a real
//   developing trail; v1.5 drew #2 as thin dashed lines instead of a "colored range"; v1.5
//   ALSO still only showed a single static end-of-day box for every historical session,
//   which is what "retarded... where was the session's POC and VA on the first tick"
//   called out directly — v2 fixes that by reconstructing the real intraday shape for
//   history too, not just today):
//   1. EVERY session's OWN developing POC/VA as a literal BAR-BY-BAR TRAIL, not a single
//      finished value:
//        - TODAY (still live): _devTrail, one snapshot per bar close built from the live
//          _vapToday/OnMarketData ticks (genuinely tick-accurate).
//        - EVERY HISTORICAL day: _histDevTrailByDate, built by MapHistDevTrailBar mapping
//          each of THIS chart's own historical bars onto the closest-at-or-before snapshot
//          in _vpTrailByDate — which is loaded from data/vp_levels/session_vp_dev_trail.csv,
//          produced by scripts/backfill_vp_log.py replaying the recorded L1 tape in
//          `--bucket-minutes` (default 5) chunks and recomputing the developing POC/VA
//          cumulatively from that day's session open, exactly the same cumulative-from-open
//          semantic as the live path, just sourced from the tape instead of live ticks. Both
//          render through the SAME DrawDevTrail step-line method. A day that was only ever
//          run through the OLD final-value-only backfill (no dev-trail row) falls back to a
//          single end-of-day box, so nothing regresses for a day the trail hasn't been built
//          for yet — but every day backfilled with the current script shows the real shape.
//   2. The PRIOR completed session's FINAL POC/VA, projected FORWARD as a FILLED COLORED
//      RANGE (box — PriorVaBoxColor/PriorPocColor, same FillRectangle visual as the
//      historical own-box fallback, not thin lines) across the CURRENT/next session's own
//      bars (ShowPriorVp, on by default) — the classic "yesterday's value area as today's
//      reference level" read, deliberately a single static range (not a trail) since it's
//      a reference to what ALREADY FINISHED, not something still developing. Drawn for
//      today (prior = _rthHist's last entry) AND for every historical session shown via
//      VpHistSessions (prior = that session's own predecessor in _rthHist) — so every
//      session on screen shows both what it did and what it opened against.
//
//   S145-4: ShowDevTrail is a real OFF switch for #1 (both the trail and its box-
//   fallback) — fully skips drawing, independent of PocOpacity/VaOpacity. Those two
//   opacity properties are new too: PocColor/VaColor's alpha was previously HARDCODED
//   in DrawDevTrail (1f/0.85f) regardless of any color transparency the user picked —
//   that's why "transparent" still showed up solid on a dark chart background. Fixed by
//   reading PocOpacity/VaOpacity instead of the hardcoded constants.
//
// LEVELS (12 total, independently stylable): for BOTH the RTH session and the ETH
// (overnight/non-RTH) session —
//   HOY/LOY/COY = High/Low/Close of the prior completed session (NOT "of year" despite
//                 the name — "Of Yesterday" in the Globex-sense of "the last one").
//   OoD/OoW/OoM = Open of Day / Week / Month for that session.
//   EXCEPTION: EHOY/ELOY (properties still named *HOY*/*LOY* for template/persistence
//              compatibility, but relabeled "H ETH"/"L ETH") track the CURRENT, still
//              in-progress ETH-only session's running high/low, not the prior completed
//              one — live-updating reference, requested instead of the prior-day version.
//
// SESSION SOURCE (why this gets the timing right):
//   RTH window   = read from the NT8 Trading Hours template named by RthTemplateName
//                  (default "CME US Index Futures RTH": Mon-Fri 08:30-15:15 Central,
//                  with NT's own Holidays + PartialHolidays calendar baked in — half-day
//                  early closes on July 3, day-after-Thanksgiving, Christmas Eve, etc.
//                  are already correct in that template file and get picked up for free
//                  via Data.SessionIterator; nothing here reimplements the CME calendar).
//   Full/ETH day = the CHART's own Bars.TradingHours (expected to be the 23h Globex
//                  template, e.g. "CME US Index Futures ETH", so both sessions actually
//                  exist in the loaded bars). A bar is "ETH" simply when it falls inside
//                  the full day but OUTSIDE that day's resolved RTH window.
//
// Two Chart Trader buttons (RTH / ETH) toggle each session's levels on/off — same mount
// pattern as BreakoutBoysDashboardV1.cs (chartTrader.Content -> button Grid).
//
// PLANNED (not built yet): a manual-levels section, deliberately left out of scope now.
//
// ⚠ Session-boundary correctness on a real half-day should be eyeballed once on F5 (scroll
// to the most recent Thanksgiving Friday / Christmas Eve) — OnRender/SessionIterator
// behavior isn't covered by nt8_compile_check.ps1.
// RULE (CLAUDE.md): lives in nt8/ committed. Deploy to Documents\...\Custom\Indicators\ then F5.

#region Using declarations
using System;
using System.Collections.Generic;
using System.IO;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
// Color/Brush/SolidColorBrush exist in BOTH System.Windows.Media (WPF, used by button/property
// colors) and SharpDX/SharpDX.Direct2D1 (used by OnRender) — alias both sides to kill the
// ambiguous-reference compile errors instead of fully qualifying every single use.
using WMColor = System.Windows.Media.Color;
using WMBrush = System.Windows.Media.Brush;
using WMSolidColorBrush = System.Windows.Media.SolidColorBrush;
using D2DSolidColorBrush = SharpDX.Direct2D1.SolidColorBrush;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

// NOTE: LevelLineStyle is NOT redeclared here. SessionSRLevelsV9.cs already defines it in
// the parent NinjaTrader.NinjaScript namespace (visible to this file without a using), and
// V9.cs stays deployed alongside V10.cs in Custom\Indicators (kept for rollback) — two
// copies of the same enum in the SAME Custom folder is a guaranteed CS0101 duplicate-
// definition error the moment either recompiles. If V9.cs is ever removed from Custom,
// this enum must be re-added here first (copy verbatim from SessionSRLevelsV9.cs).

namespace NinjaTrader.NinjaScript.Indicators.My
{
	public class SessionSRLevelsV10 : Indicator
	{
		// ── session plumbing ───────────────────────────────────────────────
		private SessionIterator _dayIter;      // Bars-bound: full trading-day/week/month boundaries
		private TradingHours    _rthHours;     // resolved RTH-only template
		private SessionIterator _rthIter;      // TradingHours-bound: RTH sub-session begin/end (holiday/half-day aware)
		private bool            _rthOk;         // false if RTH template name didn't resolve
		private TimeZoneInfo    _displayTz;
		private DateTime        _rthSessBegin = Core.Globals.MinDate;
		private DateTime        _rthSessEnd   = Core.Globals.MinDate;

		// ── per-trading-day accumulators ──────────────────────────────────
		private DateTime _curTradingDay = Core.Globals.MinDate;
		private DateTime _curWeekStart  = Core.Globals.MinDate;
		private int      _curMonthKey   = -1;
		private bool     _haveRth, _haveEth;
		private double   _rthHigh, _rthLow, _rthCloseLast;
		private double   _ethHigh, _ethLow, _ethCloseLast;
		private bool     _rthOpenCapturedToday;
		private bool     _weekAwaitingRthOpen, _monthAwaitingRthOpen;

		// bar index of the running RTH/ETH high/low PRINT (updated only when a new
		// extreme is actually made) + the most recent bar processed in that session —
		// these become the "prior" start-bars below once the session flushes.
		private int _rthHighBar = -1, _rthLowBar = -1, _rthLastBar = -1;
		private int _ethHighBar = -1, _ethLowBar = -1, _ethLastBar = -1;

		// ── values actually drawn (prior completed session + opens) ──────
		private double _priorRthHigh = double.NaN, _priorRthLow = double.NaN, _priorRthClose = double.NaN;
		private double _priorEthHigh = double.NaN, _priorEthLow = double.NaN, _priorEthClose = double.NaN;
		private double _rthOpenToday = double.NaN, _rthOpenThisWeek = double.NaN, _rthOpenThisMonth = double.NaN;
		private double _ethOpenToday = double.NaN, _ethOpenThisWeek = double.NaN, _ethOpenThisMonth = double.NaN;

		// ── bar index each level's line should START drawing from — the bar where
		// that EXACT price actually printed (the high/low/close tick itself), NOT an
		// administrative marker like the day-roll bar. Lines are rays from here to the
		// current bar, never full chart-width spans.
		private int _priorRthHighStartBar = -1, _priorRthLowStartBar = -1, _priorRthCloseStartBar = -1;
		private int _priorEthHighStartBar = -1, _priorEthLowStartBar = -1, _priorEthCloseStartBar = -1;
		private int _rthOpenStartBar  = -1, _ethOpenStartBar  = -1;
		private int _rthWeekStartBar  = -1, _ethWeekStartBar  = -1;
		private int _rthMonthStartBar = -1, _ethMonthStartBar = -1;

		// ── ETH from a dedicated hidden ETH-hours series (BarsArray[1]) so ETH levels
		// work on ANY chart — incl. an RTH-only chart whose own bars never fall in ETH
		// hours. This series has its own session timeline, tracked separately from RTH.
		private SessionIterator _ethDayIter;
		// Bars-bound iterator over the hidden RTH-hours series itself, used ONLY to resolve
		// "which RTH trading day" a primary bar's timestamp falls on (GetTradingDay requires
		// a Bars-constructed SessionIterator -- _rthIter below is built from a TradingHours
		// object instead, for IsNewSession/GetNextSession, and does NOT support GetTradingDay;
		// calling it there throws "can only be called when SessionIterator was created with
		// 'Bars'-parameter" and disables the whole indicator -- confirmed via the NT8 Control
		// Center log after the first attempt at this). Same proven pattern as _ethDayIter.
		private SessionIterator _rthBarsIter;
		private SessionIterator _rthMembershipIter;   // separate RTH iterator used to lock the overnight H/L at RTH open

		// ── RTH session OPENS (OoD/OoW/OoM) come from a dedicated hidden 1-min RTH-hours
		// series (BarsArray[2]). On a tick/volume chart the primary's "first RTH bar" is the
		// bar that CLOSES at/after 08:30, so its Open is a PRE-open tick — wrong. An RTH-hours
		// time series RESETS at the session start, so the first bar of each RTH session opens
		// exactly on the RTH open. We key the opens by date so both live and historical levels
		// read the correct value regardless of the primary chart's type.
		private bool     _rthSeriesAdded;
		private int      _ethBip = -1, _rthBip = -1;   // actual BarsInProgress index of each hidden series
		private DateTime _rthSeriesLastDate = Core.Globals.MinDate;

		// 2026-10-16: the Daily-period RTH series above (_rthBip) stopped delivering a bar
		// for the current trading day mid-session — confirmed via NT8's own on-disk
		// historical cache (complete days archived fine through the prior day; nothing ever
		// built for today on this specific Daily+custom-template combination) and via the
		// debug trail (RthRoll never recorded a transition into today, even after a full
		// platform restart). That's an NT8-side gap specific to Daily bars on a non-default
		// Trading Hours template; the SAME template at Minute granularity has no such
		// problem (the existing 5-min ETH hidden series below proves it, and NT8's own
		// MINUTE/TICK cache folders for this instrument+template were actively updating).
		// Dedicated 1-min RTH-hours series purely for OoD RTH's precise open price — kept
		// separate and minimal (added only when ROoD_Enabled, not the broader needRth) so it
		// doesn't reintroduce the historical bar-count cost that was the original reason
		// OoD's source was moved off a 1-min series onto Daily in the first place. A 1-min
		// bar's Open is the price of the first trade in that bar, same as a 1-tick bar's
		// Open would be, since the session genuinely resets exactly at the RTH open on an
		// RTH-templated series — exact, not an approximation.
		private bool     _rthMinSeriesAdded;
		private int      _rthMinBip = -1;
		private SessionIterator _rthMinDayIter;
		private DateTime _rthOpenPreciseDay = Core.Globals.MinDate;
		private double   _rthOpenPrecise = double.NaN;
		// Day -> precise RTH open, same source as _rthOpenPrecise, for Hist_OoD's per-day
		// lookup in DrawHistorical. 2026-10-16: without this, the historical path still fell
		// back through _rthOpenByDay (old broken series) to s.o (= _rthOpenToday at push
		// time, ALSO only ever written by the old broken series) — so even after fixing the
		// LIVE value, history kept reading a source that was never actually fixed. This gives
		// history its own clean path to the same reliable 1-min series, independent of that
		// entire old/contaminated chain.
		private readonly Dictionary<DateTime, double> _rthOpenByDayPrecise = new Dictionary<DateTime, double>();

		// ── Settlement = close of the Daily ETH chart. Read it STRAIGHT from a hidden Daily
		// ETH series (same template as the chart) rather than reconstructing it from 1-min bars,
		// so it matches the Daily ETH bar close exactly. Keyed by trading day for live+historical.
		private bool     _ethDaySeriesAdded;
		private int      _ethDayBip = -1;
		private SessionIterator _ethDaySessIter;
		private readonly Dictionary<DateTime, double> _settleByDay = new Dictionary<DateTime, double>();
		private DateTime _rthSeriesWeek     = Core.Globals.MinDate;
		private int      _rthSeriesMonthKey = -1;
		private readonly Dictionary<DateTime, double> _rthOpenByDay   = new Dictionary<DateTime, double>(); // trading day -> RTH open
		private readonly Dictionary<DateTime, double> _rthWeekOpenBy  = new Dictionary<DateTime, double>(); // Monday     -> week's RTH open
		private readonly Dictionary<DateTime, double> _rthMonthOpenBy = new Dictionary<DateTime, double>(); // 1st-of-mo  -> month's RTH open
		private bool     _ethSeriesAdded;
		private bool     _ethLocked;                  // true once RTH has opened for the current ETH session
		private DateTime _ethCurTradingDay = Core.Globals.MinDate;
		private DateTime _ethCurWeekStart  = Core.Globals.MinDate;
		private int      _ethCurMonthKey   = -1;

		// ── Historical levels (Model A: each level confined to its own session) ──
		// One record per COMPLETED RTH session, pushed at the day roll; bounded list.
		// dayStartBar = the trading-day/session-break boundary (where the vertical break line
		// is); dayEndBar = last bar of that trading day. Prior-day H/L/C lines span the whole
		// trading day from the session break; OoD starts at the RTH open (oBar).
		private class HRSess { public DateTime date; public double o, h, l, c, weekOpen, monthOpen; public int oBar, hBar, lBar, cBar, dayStartBar, dayEndBar; }
		private readonly List<HRSess> _rthHist = new List<HRSess>();
		// trading day -> {overnight ETH high, ETH low, ETH session close} (H/L locked at RTH
		// open; close = the Daily ETH bar's close), filled at the ETH roll.
		private readonly Dictionary<DateTime, double[]> _ethByDay = new Dictionary<DateTime, double[]>();
		// caches for historical expected-move: VIX close by date (whole CSV) + gexlog move by date.
		private readonly Dictionary<DateTime, double> _vixByDate = new Dictionary<DateTime, double>();
		private readonly Dictionary<DateTime, double> _gexMoveByDate = new Dictionary<DateTime, double>();
		private DateTime _vixMapStamp = DateTime.MinValue;

		// Primary chart's current-session open bars = first bar of the current trading day /
		// week / month on THIS chart (RTH open on an RTH chart, ETH/Globex 17:00 open on an
		// ETH chart). ETH lines start here on intraday charts so they begin at the session
		// open the user is looking at. (On daily charts these stay -1 — the primary loop that
		// sets them is skipped — and rendering falls back to the calendar-date walk.)
		private int      _primaryDayOpenBar   = -1;
		private int      _primaryWeekOpenBar  = -1;
		private int      _primaryMonthOpenBar = -1;

		// Daily/Weekly primary only: trading day -> that day's own primary bar index (one
		// bar = one day). The intraday RTH/ETH sub-session classification loop below can't
		// run on a whole-day bar, so HandleRthSeries/HandleEthSeries (driven by their own
		// hidden series, independent of the primary's period) use this to anchor their
		// lines/historical segments to the right bar on THIS chart.
		private readonly Dictionary<DateTime, int> _dailyPrimaryBarByDate = new Dictionary<DateTime, int>();

		// ── developing POC/Value-Area (S142+) ──────────────────────────────
		private readonly Dictionary<double, double> _vapToday = new Dictionary<double, double>();
		private double _devPoc = double.NaN, _devVah = double.NaN, _devVal = double.NaN;
		// Bar-by-bar snapshot of today's developing POC/VAH/VAL (S145 revision) — one entry
		// per RecomputeDevPocVa call (= once per bar close), so the chart can show the level
		// AS IT DEVELOPED through the session, not just its latest value flattened across
		// every bar already elapsed. Cleared at the day roll in FinalizeDevPocVa.
		private struct DevSnap { public int bar; public double poc, vah, val; }
		private readonly List<DevSnap> _devTrail = new List<DevSnap>();
		private readonly Dictionary<DateTime, double[]> _vpByDate = new Dictionary<DateTime, double[]>();   // date -> [vpoc,vah,val]
		private readonly string _vpLogPath = @"C:\Users\Admin\myquant\data\vp_levels\session_vp_live_log.csv";

		// S145-3: HISTORICAL sessions' developing trail, reconstructed from the recorded L1
		// tape (scripts/backfill_vp_log.py --bucket-minutes), because the live-only path
		// above can only ever snapshot the CURRENTLY-live day — every day before today only
		// ever had its FINAL value persisted (_vpByDate), which is why earlier passes could
		// only draw a static end-of-day box for history, not a real developing shape. Fix:
		// _vpTrailByDate = the file's raw (timestamp, poc, vah, val) snapshots per day, in
		// CT ("RTH-tz") wall-clock time, loaded once at State.DataLoaded. _histDevTrailByDate
		// = those same snapshots mapped onto THIS chart's own bar indices as NT8 walks each
		// historical bar (MapHistDevTrailBar, called from the main per-bar loop below) — one
		// chart-bar-indexed entry per bar whose converted time crosses into a new snapshot,
		// built incrementally exactly like _devTrail is for the live day, just sourced from
		// the file instead of live ticks.
		private struct TrailPt { public DateTime ts; public double poc, vah, val; }
		private readonly Dictionary<DateTime, List<TrailPt>> _vpTrailByDate = new Dictionary<DateTime, List<TrailPt>>();
		private readonly Dictionary<DateTime, List<DevSnap>> _histDevTrailByDate = new Dictionary<DateTime, List<DevSnap>>();
		private readonly string _vpTrailLogPath = @"C:\Users\Admin\myquant\data\vp_levels\session_vp_dev_trail.csv";

		// Current-day running High/Low, tracked from the ACTUAL bars (not the visible window)
		// so it stays locked when you scroll/zoom. Intraday only; on daily OnBarUpdate is
		// skipped and the current-day H/L is just the latest daily bar's own High/Low.
		private double   _curDayHigh = double.NaN, _curDayLow = double.NaN;
		private int      _curDayStartBar = -1;

		// Expected-move 1-day bands — two methods compared side by side:
		//   VIX  = prior RTH close ± close*(VIX/100)/sqrt(252)*sigma   (matches options_gameplan.em_halfwidth)
		//   GEX  = emUpper/emLower read straight from the gexlog morning (or prior-evening) brief
		// Both read repo files on a throttle; manual VIX override available.
		private double   _emvMax = double.NaN, _emvMin = double.NaN;   // VIX-formula band
		private double   _emgMax = double.NaN, _emgMin = double.NaN;   // gexlog published band
		private double   _vixUsed = double.NaN;
		private DateTime _emLastRead = DateTime.MinValue;
		private const double SQRT252 = 15.874507866387544;

		// ── Chart Trader toggle buttons (shared panel, routed to the active tab) ──
		private bool   ctPanelActive;
		private bool   _rthVisible = true, _ethVisible = true, _labelsVisible = true;
		private bool   _priceVisibleSet = false; private bool _priceVisible = true;  // CT price toggle; seeded from ShowPriceInLabel on first render

		// A chart WINDOW has ONE Chart Trader shared by all its tabs — so build ONE button set
		// per grid and route each click to whichever chart tab is currently ACTIVE (set when the
		// mouse enters that chart). Keyed by the grid so separate windows stay independent.
		private sealed class CtShared { public SessionSRLevelsV10 active; public Button rth, eth, labels, price; public Grid row1, row2; public RowDefinition rd1, rd2; public int refs; }
		private static readonly Dictionary<Grid, CtShared> _ctByGrid = new Dictionary<Grid, CtShared>();
		private Grid _ctGrid;
		private System.Windows.Input.MouseEventHandler _ctEnter;
		private static readonly WMColor CtOn  = WMColor.FromRgb(0, 140, 0);
		private static readonly WMColor CtOff = WMColor.FromRgb(80, 80, 80);

		// diagnostic-only: Daily-chart date/value trail for the HOY/LOY/COY-via-hidden-RTH-
		// series path (S139). Low frequency (fires only on a session roll, not per tick) so a
		// plain AppendAllText per row is fine -- no batching/flush-timer needed.
		private string _dbgPath;
		private void LogDbg(string row)
		{
			if (!DebugLog) return;
			try
			{
				if (_dbgPath == null)
					_dbgPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
						string.Format("sessionsrlevels_debug_{0}.csv", Instrument != null ? Instrument.MasterInstrument.Name : "unknown"));
				File.AppendAllText(_dbgPath, row + "\r\n");
			}
			catch { }
		}

		private struct LevelDef
		{
			public bool enabled; public string label; public double price;
			public WMColor color; public int opacity; public LevelLineStyle style; public int thickness;
			public int col; public int startBarIdx; public int endBarIdx;   // endBarIdx -1 = extend to current+ExtendBarsRight
		}

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name                     = "SessionSRLevelsV10";
				Description              = "RTH + ETH session S/R levels (HOY/LOY/COY/OoD/OoW/OoM) from NT8's own CME trading-hours templates, + optional developing POC/Value-Area.";
				Calculate                = Calculate.OnBarClose;
				IsOverlay                = true;
				IsChartOnly              = true;
				DisplayInDataBox         = false;
				PaintPriceMarkers        = false;
				BarsRequiredToPlot       = 0;

				RthTemplateName     = "CME US Index Futures RTH";
				FullTemplateNameHint = "CME US Index Futures ETH";
				EthFromPrimary      = true;   // ETH levels off THIS chart's bars (exact + no 5-min ETH feed); turn off only on RTH-only charts
				DebugLog            = false;
				LabelFontSize       = 11;
				ShowPriceInLabel    = true;
				ExtendBarsRight     = 10;
				HistSessions        = 5;
				HistOpacity         = 45;
				Hist_HOY = true; Hist_LOY = true; Hist_COY = true; Hist_OoD = true; Hist_OoW = true; Hist_OoM = true;
				Hist_EthH = true; Hist_EthL = true; Hist_Settle = true;
				Hist_EMV_Max = true; Hist_EMV_Min = true; Hist_EMG_Max = true; Hist_EMG_Min = true;

				// Current-day running High/Low (computed from the chart's own bars for today).
				CDH_Enabled = true; CDH_Label = "HoD"; CDH_Color = Brushes.DarkCyan; CDH_Opacity = 100; CDH_Style = LevelLineStyle.Solid; CDH_Thickness = 1;
				CDL_Enabled = true; CDL_Label = "LoD"; CDL_Color = Brushes.DarkCyan; CDL_Opacity = 100; CDL_Style = LevelLineStyle.Solid; CDL_Thickness = 1;

				// Expected-move bands (two methods, for comparison).
				VixCsvPath   = @"C:\Users\Admin\myquant\data\vix_daily.csv";
				GexlogRawDir = @"C:\Users\Admin\myquant\data\gexlog\raw";
				EmManualVix  = 0;     // 0 = auto (read last close from VixCsvPath)
				EmSigma      = 1.0;
				EMV_Max_Enabled = true; EMV_Max_Label = "1D Max VIX"; EMV_Max_Color = Brushes.Plum;     EMV_Max_Opacity = 90; EMV_Max_Style = LevelLineStyle.Dot; EMV_Max_Thickness = 1;
				EMV_Min_Enabled = true; EMV_Min_Label = "1D Min VIX"; EMV_Min_Color = Brushes.Plum;     EMV_Min_Opacity = 90; EMV_Min_Style = LevelLineStyle.Dot; EMV_Min_Thickness = 1;
				EMG_Max_Enabled = true; EMG_Max_Label = "1D Max GEX"; EMG_Max_Color = Brushes.Khaki;    EMG_Max_Opacity = 90; EMG_Max_Style = LevelLineStyle.Dot; EMG_Max_Thickness = 1;
				EMG_Min_Enabled = true; EMG_Min_Label = "1D Min GEX"; EMG_Min_Color = Brushes.Khaki;    EMG_Min_Opacity = 90; EMG_Min_Style = LevelLineStyle.Dot; EMG_Min_Thickness = 1;

				// RTH defaults: solid, saturated, thickness 2. Label = "{metric} RTH".
				RHOY_Enabled = true;  RHOY_Label = "HOY RTH"; RHOY_Color = Brushes.IndianRed;      RHOY_Opacity = 100; RHOY_Style = LevelLineStyle.Solid; RHOY_Thickness = 2;
				RLOY_Enabled = true;  RLOY_Label = "LOY RTH"; RLOY_Color = Brushes.RoyalBlue;      RLOY_Opacity = 100; RLOY_Style = LevelLineStyle.Solid; RLOY_Thickness = 2;
				RCOY_Enabled = true;  RCOY_Label = "COY RTH"; RCOY_Color = Brushes.Goldenrod;      RCOY_Opacity = 100; RCOY_Style = LevelLineStyle.Solid; RCOY_Thickness = 2;
				ROoD_Enabled = true;  ROoD_Label = "OoD RTH"; ROoD_Color = Brushes.MediumSeaGreen; ROoD_Opacity = 100; ROoD_Style = LevelLineStyle.Solid; ROoD_Thickness = 2;
				ROoW_Enabled = true;  ROoW_Label = "OoW RTH"; ROoW_Color = Brushes.DarkOrange;     ROoW_Opacity = 100; ROoW_Style = LevelLineStyle.Solid; ROoW_Thickness = 2;
				ROoM_Enabled = true;  ROoM_Label = "OoM RTH"; ROoM_Color = Brushes.MediumPurple;   ROoM_Opacity = 100; ROoM_Style = LevelLineStyle.Solid; ROoM_Thickness = 2;
				ROoM_ManualPrice = 0; ROoM_ManualMonth = Core.Globals.MinDate;

				// ETH defaults: same hue family, dashed, thickness 1, lower default opacity. Label = "{metric} ETH".
				EHOY_Enabled = true;  EHOY_Label = "H ETH";   EHOY_Color = Brushes.IndianRed;      EHOY_Opacity = 70; EHOY_Style = LevelLineStyle.Dash; EHOY_Thickness = 1;
				ELOY_Enabled = true;  ELOY_Label = "L ETH";   ELOY_Color = Brushes.RoyalBlue;      ELOY_Opacity = 70; ELOY_Style = LevelLineStyle.Dash; ELOY_Thickness = 1;
				ECOY_Enabled = true;  ECOY_Label = "COY ETH"; ECOY_Color = Brushes.Goldenrod;      ECOY_Opacity = 70; ECOY_Style = LevelLineStyle.Dash; ECOY_Thickness = 1;
				EOoD_Enabled = true;  EOoD_Label = "OoD ETH"; EOoD_Color = Brushes.MediumSeaGreen; EOoD_Opacity = 70; EOoD_Style = LevelLineStyle.Dash; EOoD_Thickness = 1;
				EOoW_Enabled = true;  EOoW_Label = "OoW ETH"; EOoW_Color = Brushes.DarkOrange;     EOoW_Opacity = 70; EOoW_Style = LevelLineStyle.Dash; EOoW_Thickness = 1;
				EOoM_Enabled = true;  EOoM_Label = "OoM ETH"; EOoM_Color = Brushes.MediumPurple;   EOoM_Opacity = 70; EOoM_Style = LevelLineStyle.Dash; EOoM_Thickness = 1;
				EOoM_ManualPrice = 0; EOoM_ManualMonth = Core.Globals.MinDate;
				// Settlement = close of the Daily ETH chart (prior ETH-session close). Distinct
				// solid line so it stands apart from the dashed ETH family.
				Settle_Enabled = true; Settle_Label = "Settlement"; Settle_Color = Brushes.White; Settle_Opacity = 85; Settle_Style = LevelLineStyle.Solid; Settle_Thickness = 1;

				// Custom/manual levels: off and price=0 by default (nothing drawn until you
				// type a price in and tick Enabled). StartDate defaults to the MinDate
				// sentinel (= "not set" -> leftmost visible bar); pick a date via the
				// calendar dropdown to anchor the ray there instead. Neutral gray/solid so
				// they read as user-placed, not computed.
				// C1/C2 restored from the "SR Daily" template saved under the old V5 name
				// (templates\Indicator\SessionSRLevelsV5\SR Daily.xml) — these were real
				// configured levels, wiped when the V5->V6 rename orphaned that template.
				C1_Enabled = true;  C1_Label = "MM ATH";      C1_Price = 7946.75; C1_StartDate = Core.Globals.MinDate; C1_Color = Brushes.DeepPink; C1_Opacity = 100; C1_Style = LevelLineStyle.Solid; C1_Thickness = 2;
				C2_Enabled = true;  C2_Label = "ATH 8/13/26"; C2_Price = 7906.25; C2_StartDate = Core.Globals.MinDate; C2_Color = Brushes.Magenta;  C2_Opacity = 100; C2_Style = LevelLineStyle.Dash;  C2_Thickness = 2;
				C3_Enabled = false; C3_Label = "Custom 3"; C3_Price = 0; C3_StartDate = Core.Globals.MinDate; C3_Color = Brushes.Silver; C3_Opacity = 100; C3_Style = LevelLineStyle.Solid; C3_Thickness = 2;
				C4_Enabled = false; C4_Label = "Custom 4"; C4_Price = 0; C4_StartDate = Core.Globals.MinDate; C4_Color = Brushes.Silver; C4_Opacity = 100; C4_Style = LevelLineStyle.Solid; C4_Thickness = 2;
				C5_Enabled = false; C5_Label = "Custom 5"; C5_Price = 0; C5_StartDate = Core.Globals.MinDate; C5_Color = Brushes.Silver; C5_Opacity = 100; C5_Style = LevelLineStyle.Solid; C5_Thickness = 2;
				C6_Enabled = false; C6_Label = "Custom 6"; C6_Price = 0; C6_StartDate = Core.Globals.MinDate; C6_Color = Brushes.Silver; C6_Opacity = 100; C6_Style = LevelLineStyle.Solid; C6_Thickness = 2;
				C7_Enabled = false; C7_Label = "Custom 7"; C7_Price = 0; C7_StartDate = Core.Globals.MinDate; C7_Color = Brushes.Silver; C7_Opacity = 100; C7_Style = LevelLineStyle.Solid; C7_Thickness = 2;
				C8_Enabled = false; C8_Label = "Custom 8"; C8_Price = 0; C8_StartDate = Core.Globals.MinDate; C8_Color = Brushes.Silver; C8_Opacity = 100; C8_Style = LevelLineStyle.Solid; C8_Thickness = 2;

				// Developing POC/VA — OFF by default (resource-conserving; OnMarketData does
				// zero work while this is false, same leanness pattern as needEth/needRth below).
				ShowDevPocVa    = false;
				VaPercent       = 0.70;
				VpHistSessions  = 1;
				PocColor = Brushes.Red; VaColor = Brushes.MediumSeaGreen; VaBoxColor = Brushes.MediumSeaGreen;
				ShowPriorVp     = true;
				PriorPocColor = Brushes.Orange; PriorVaBoxColor = Brushes.Goldenrod; PriorVpOpacity = 20;
				ShowDevTrail = true; PocOpacity = 100; VaOpacity = 85;
			}
			else if (State == State.Configure)
			{
				// Load each hidden feed ONLY if a level that depends on it is enabled — so
				// turning a feature off removes its entire data-series cost (leanness). Each
				// feed is skipped only when ALL its dependent levels are off, so nothing you
				// can see ever loses its data. Re-evaluated on every reconfigure (property edits).
				bool needEth    = EHOY_Enabled || ELOY_Enabled || ECOY_Enabled || EOoD_Enabled || EOoW_Enabled || EOoM_Enabled || Hist_EthH || Hist_EthL;
				bool needRth    = ROoD_Enabled || ROoW_Enabled || ROoM_Enabled || Hist_OoD || Hist_OoW || Hist_OoM;
				bool needSettle = Settle_Enabled || Hist_Settle;

				// Hidden ETH-hours series: feeds ALL ETH levels so they work regardless of
				// the chart's own Trading Hours template (incl. RTH-only charts). 5-MIN (not
				// 1-min) to cut ~5x the bar-processing load: a bar's High/Low aggregates the
				// extreme, so the overnight H/L stays exact; only the RTH-open lock boundary is
				// coarsened to ~5 min (the quiet pre-open window rarely holds the overnight extreme).
				// EthFromPrimary is also IGNORED (hidden series added anyway) when the primary
				// isn't intraday: computing ETH overnight H/L from the primary's own bars means
				// classifying each bar as RTH-time or ETH-time, which a single whole-day Daily
				// bar can't support -- the hidden series is the only way ETH works on a Daily chart.
				bool primaryIntraday = Bars != null && Bars.BarsType.IsIntraday;
				_ethSeriesAdded = false;
				if (needEth && (!EthFromPrimary || !primaryIntraday) && !string.IsNullOrEmpty(FullTemplateNameHint))
				{
					try
					{
						AddDataSeries(Instrument.FullName,
							new BarsPeriod { BarsPeriodType = BarsPeriodType.Minute, Value = 5 },
							FullTemplateNameHint);
						_ethSeriesAdded = true;
					}
					catch (Exception ex) { Print("SessionSRLevelsV10: could not add ETH data series '" + FullTemplateNameHint + "': " + ex.Message); }
				}

				// Hidden DAILY RTH-hours series: the authoritative source for the RTH session
				// OPENS (OoD/OoW/OoM). The session resets at 08:30, so each daily RTH bar OPENS
				// exactly on the RTH open — one bar per session (vs ~100k for a 1-min series),
				// which is why this is Daily, not intraday.
				_rthSeriesAdded = false;
				if (needRth && !string.IsNullOrEmpty(RthTemplateName))
				{
					try
					{
						AddDataSeries(Instrument.FullName,
							new BarsPeriod { BarsPeriodType = BarsPeriodType.Day, Value = 1 },
							RthTemplateName);
						_rthSeriesAdded = true;
					}
					catch (Exception ex) { Print("SessionSRLevelsV10: could not add RTH data series '" + RthTemplateName + "': " + ex.Message); }
				}
				_rthSeriesLastDate = Core.Globals.MinDate; _rthSeriesWeek = Core.Globals.MinDate; _rthSeriesMonthKey = -1;
				_rthOpenByDay.Clear(); _rthWeekOpenBy.Clear(); _rthMonthOpenBy.Clear();

				// Hidden DAILY ETH series: the authoritative source for Settlement (the Daily ETH
				// bar close). Same ETH template as the chart, Day period.
				_ethDaySeriesAdded = false;
				if (needSettle && !string.IsNullOrEmpty(FullTemplateNameHint))
				{
					try
					{
						AddDataSeries(Instrument.FullName,
							new BarsPeriod { BarsPeriodType = BarsPeriodType.Day, Value = 1 },
							FullTemplateNameHint);
						_ethDaySeriesAdded = true;
					}
					catch (Exception ex) { Print("SessionSRLevelsV10: could not add Daily ETH data series: " + ex.Message); }
				}
				_ethDaySessIter = null; _settleByDay.Clear();

				// Dedicated 1-min RTH series for OoD RTH's precise open — see field comment.
				// Scoped to ROoD_Enabled specifically (not needRth) to stay minimal. Added LAST
				// (call order matters — it's what the BIP resolution below keys off).
				_rthMinSeriesAdded = false;
				if (ROoD_Enabled && !string.IsNullOrEmpty(RthTemplateName))
				{
					try
					{
						AddDataSeries(Instrument.FullName,
							new BarsPeriod { BarsPeriodType = BarsPeriodType.Minute, Value = 1 },
							RthTemplateName);
						_rthMinSeriesAdded = true;
					}
					catch (Exception ex) { Print("SessionSRLevelsV10: could not add 1-min RTH data series '" + RthTemplateName + "': " + ex.Message); }
				}
				_rthOpenPreciseDay = Core.Globals.MinDate; _rthOpenPrecise = double.NaN;
				_rthOpenByDayPrecise.Clear();

				// Resolve each hidden series' BarsInProgress index in the EXACT order their
				// AddDataSeries calls appear above (primary = 0, ETH 5-min, RTH Daily, Daily
				// ETH, RTH 1-min). Stays correct if any is skipped — but the ORDER here must
				// match the call order above exactly, or indices silently cross-wire (2026-10-16:
				// this exact mismatch happened — RTH 1-min and Daily ETH were swapped because the
				// new block was inserted between RTH Daily and Daily ETH while this formula still
				// assumed Daily ETH came third; moved the AddDataSeries call to match instead of
				// just reordering the formula, so the two can't drift apart silently again).
				{ int bip = 1; _ethBip = _ethSeriesAdded ? bip++ : -1; _rthBip = _rthSeriesAdded ? bip++ : -1; _ethDayBip = _ethDaySeriesAdded ? bip++ : -1; _rthMinBip = _rthMinSeriesAdded ? bip++ : -1; }

				_ethDayIter = null; _rthBarsIter = null; _rthMembershipIter = null; _rthMinDayIter = null; _ethLocked = false;
				_ethCurTradingDay = Core.Globals.MinDate; _ethCurWeekStart = Core.Globals.MinDate; _ethCurMonthKey = -1;
				_primaryDayOpenBar = _primaryWeekOpenBar = _primaryMonthOpenBar = -1;
				_curDayHigh = _curDayLow = double.NaN; _curDayStartBar = -1;
				_rthHist.Clear(); _ethByDay.Clear(); _vixByDate.Clear(); _gexMoveByDate.Clear(); _vixMapStamp = DateTime.MinValue;
			_histDevTrailByDate.Clear(); _vpTrailByDate.Clear();

				_dayIter = null; _rthHours = null; _rthIter = null; _rthOk = false;
				_curTradingDay = Core.Globals.MinDate; _curWeekStart = Core.Globals.MinDate; _curMonthKey = -1;
				_haveRth = _haveEth = false;
				_rthOpenCapturedToday = false; _weekAwaitingRthOpen = false; _monthAwaitingRthOpen = false;
				_priorRthHigh = _priorRthLow = _priorRthClose = double.NaN;
				_priorEthHigh = _priorEthLow = _priorEthClose = double.NaN;
				_rthOpenToday = _rthOpenThisWeek = _rthOpenThisMonth = double.NaN;
				_ethOpenToday = _ethOpenThisWeek = _ethOpenThisMonth = double.NaN;
				_rthHighBar = _rthLowBar = _rthLastBar = -1;
				_ethHighBar = _ethLowBar = _ethLastBar = -1;
				_priorRthHighStartBar = _priorRthLowStartBar = _priorRthCloseStartBar = -1;
				_priorEthHighStartBar = _priorEthLowStartBar = _priorEthCloseStartBar = -1;
				_rthOpenStartBar  = _ethOpenStartBar  = -1;
				_rthWeekStartBar  = _ethWeekStartBar  = -1;
				_rthMonthStartBar = _ethMonthStartBar = -1;
			}
			else if (State == State.DataLoaded)
			{
				_displayTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
				_dayIter   = new SessionIterator(Bars);

				if (_ethSeriesAdded && _ethBip >= 0 && BarsArray.Length > _ethBip)
					_ethDayIter = new SessionIterator(BarsArray[_ethBip]);

				if (_rthSeriesAdded && _rthBip >= 0 && BarsArray.Length > _rthBip)
					_rthBarsIter = new SessionIterator(BarsArray[_rthBip]);

				if (_ethDaySeriesAdded && _ethDayBip >= 0 && BarsArray.Length > _ethDayBip)
					_ethDaySessIter = new SessionIterator(BarsArray[_ethDayBip]);

				if (_rthMinSeriesAdded && _rthMinBip >= 0 && BarsArray.Length > _rthMinBip)
					_rthMinDayIter = new SessionIterator(BarsArray[_rthMinBip]);

				try
				{
					_rthHours = TradingHours.Get(RthTemplateName);
					if (_rthHours == null) throw new Exception("template not found");
					_rthIter = new SessionIterator(_rthHours);
					_rthMembershipIter = new SessionIterator(_rthHours);
					_rthOk   = true;
				}
				catch (Exception ex)
				{
					Print("SessionSRLevelsV10: WARNING - RTH template '" + RthTemplateName + "' did not resolve (" + ex.Message + "). RTH/ETH split disabled; every bar will be treated as ETH.");
					_rthOk = false;
				}

				if (Bars.TradingHours != null && !string.IsNullOrEmpty(FullTemplateNameHint)
					&& Bars.TradingHours.Name != FullTemplateNameHint)
					Print("SessionSRLevelsV10: NOTE - chart Trading Hours template is '" + Bars.TradingHours.Name
						+ "', expected '" + FullTemplateNameHint + "' (the 23h Globex template). If this chart"
						+ " is RTH-only, ETH levels will have nothing to draw.");

				if (ShowDevPocVa) { LoadVpLog(); LoadVpTrailLog(); }
			}
			else if (State == State.Historical)
			{
				if (ChartControl != null && !ctPanelActive)
					ChartControl.Dispatcher.InvokeAsync((Action)CreateWPFControls);
			}
			else if (State == State.Terminated)
			{
				if (ChartControl != null)
					ChartControl.Dispatcher.InvokeAsync((Action)DisposeWPFControls);
			}
		}

		// Per-tick price/volume binning for the developing POC/VA (S142+). Independent of
		// Calculate (OnMarketData fires on every live tick regardless) and independent of
		// BarsInProgress (all the hidden AddDataSeries calls above share this SAME
		// instrument's live feed, so this fires once per real tick, not once per series).
		// Returns immediately — zero cost — whenever the feature is off.
		protected override void OnMarketData(MarketDataEventArgs e)
		{
			if (!ShowDevPocVa || e.MarketDataType != MarketDataType.Last || e.Volume <= 0) return;
			double tick = TickSize > 0 ? TickSize : 0.25;
			double px = Math.Round(e.Price / tick) * tick;
			double v;
			_vapToday.TryGetValue(px, out v);
			_vapToday[px] = v + e.Volume;
		}

		protected override void OnBarUpdate()
		{
			if (_ethBip >= 0 && BarsInProgress == _ethBip) { HandleEthSeries(); return; }
			if (_rthBip >= 0 && BarsInProgress == _rthBip) { HandleRthSeries(); return; }
			if (_ethDayBip >= 0 && BarsInProgress == _ethDayBip) { HandleEthDailySeries(); return; }
			if (_rthMinBip >= 0 && BarsInProgress == _rthMinBip) { HandleRthOpenPrecise(); return; }
			if (BarsInProgress != 0) return;
			if (CurrentBar < 0) return;
			if (ShowDevPocVa && Bars.BarsType.IsIntraday) RecomputeDevPocVa();   // once per primary bar close, not per tick
			if (!Bars.BarsType.IsIntraday)
			{
				// Daily/Weekly primary: one bar = one whole day/week, so there's no intraday
				// RTH/ETH sub-session to classify bar-by-bar (everything below needs that).
				// Still record date -> bar index so HandleRthSeries/HandleEthSeries (driven by
				// their OWN hidden series, unaffected by the primary's period) can anchor their
				// lines/historical segments to the right bar on THIS chart.
				//
				// Resolve the day via _rthBarsIter (Bars-bound, over the hidden RTH series'
				// OWN bars), NOT _dayIter (bound to the PRIMARY's own template -- typically
				// ETH/Globex on a chart like this, a DIFFERENT day boundary than the hidden
				// RTH-hours series' own dates, which HandleRthSeries keys everything by --
				// using the wrong one here is what shifted HOY/LOY/COY onto the wrong day).
				// NOTE: _rthIter (built from a TradingHours object, not Bars) does NOT support
				// GetTradingDay -- confirmed via NT8 Control Center log ("can only be called
				// when SessionIterator was created with 'Bars'-parameter"), which THREW on
				// every bar and disabled the whole indicator on the first attempt (nothing in
				// this file catches OnBarUpdate exceptions -- one throw = total outage). Wrapped
				// defensively this time: if _rthBarsIter.GetTradingDay ever throws for a reason
				// not yet seen (e.g. called before the hidden series has any bars), fall back to
				// _dayIter rather than take the whole indicator down again.
				DateTime td;
				try { td = _rthBarsIter != null ? _rthBarsIter.GetTradingDay(Time[0]) : _dayIter.GetTradingDay(Time[0]); }
				catch { td = _dayIter.GetTradingDay(Time[0]); }
				_curTradingDay = td;
				_curWeekStart  = MondayOf(td);
				_curMonthKey   = td.Year * 12 + td.Month;
				_dailyPrimaryBarByDate[td] = CurrentBar;
				LogDbg(string.Format("PrimaryBar,{0:yyyy-MM-dd HH:mm:ss},rawTime={1:yyyy-MM-dd HH:mm:ss},rthDay={2:yyyy-MM-dd},bar={3}",
					DateTime.Now, Time[0], td, CurrentBar));
				return;
			}

			DateTime barTime    = Time[0];
			DateTime tradingDay = _dayIter.GetTradingDay(barTime);

			if (tradingDay != _curTradingDay)
			{
				if (_haveRth)
				{
					_priorRthHigh = _rthHigh; _priorRthHighStartBar = _rthHighBar;
					_priorRthLow  = _rthLow;  _priorRthLowStartBar  = _rthLowBar;
					_priorRthClose = _rthCloseLast; _priorRthCloseStartBar = _rthLastBar;

					// Push the just-completed RTH session into history (Model A confined segment).
					// _primaryDayOpenBar still holds THIS (completed) day's session-break bar
					// (it's updated to the new day's bar just below); CurrentBar-1 is this
					// trading day's last bar.
					_rthHist.Add(new HRSess {
						date = _curTradingDay,
						o = _rthOpenToday, oBar = _rthOpenStartBar,
						h = _rthHigh, hBar = _rthHighBar, l = _rthLow, lBar = _rthLowBar,
						c = _rthCloseLast, cBar = _rthLastBar,
						weekOpen = _rthOpenThisWeek, monthOpen = _rthOpenThisMonth,
						dayStartBar = _primaryDayOpenBar >= 0 ? _primaryDayOpenBar : _rthOpenStartBar,
						dayEndBar = CurrentBar - 1 });
					if (_rthHist.Count > 70) _rthHist.RemoveAt(0);
				}

				// ETH overnight H/L + opens + close computed straight from THIS chart's bars
				// (EthFromPrimary) — exact, and no hidden 5-min ETH feed. Record the completed
				// ETH session, then reset for the new one (this bar = the ETH/Globex open).
				if (EthFromPrimary)
				{
					if (_haveEth)
					{
						_priorEthHigh = _ethHigh; _priorEthLow = _ethLow; _priorEthClose = _ethCloseLast;
						_ethByDay[_curTradingDay] = new double[] { _ethHigh, _ethLow, _ethCloseLast };
						if (_ethByDay.Count > 90)
						{
							DateTime oldest = Core.Globals.MaxDate;
							foreach (DateTime dk in _ethByDay.Keys) if (dk < oldest) oldest = dk;
							_ethByDay.Remove(oldest);
						}
					}
					_ethHigh = High[0]; _ethLow = Low[0]; _haveEth = true; _ethLocked = false;
					_ethOpenToday = Open[0];
					DateTime ewk = MondayOf(tradingDay);
					if (ewk != _ethCurWeekStart) { _ethCurWeekStart = ewk; _ethOpenThisWeek = Open[0]; }
					int emk = tradingDay.Year * 12 + tradingDay.Month;
					if (emk != _ethCurMonthKey) { _ethCurMonthKey = emk; _ethOpenThisMonth = Open[0]; }
				}

				// _curTradingDay still holds the day that JUST completed and _vapToday still
				// holds its full accumulated volume -- finalize + persist it, THEN reset for
				// the new day starting below.
				if (ShowDevPocVa) FinalizeDevPocVa(_curTradingDay);

				_curTradingDay        = tradingDay;
				_haveRth              = false;
				_rthOpenCapturedToday = false;
				_primaryDayOpenBar    = CurrentBar;   // first bar of this chart's trading day = its session open
				_curDayHigh = High[0]; _curDayLow = Low[0]; _curDayStartBar = CurrentBar;   // reset current-day H/L

				DateTime wkStart = MondayOf(tradingDay);
				if (wkStart != _curWeekStart)
				{
					_curWeekStart         = wkStart;
					_weekAwaitingRthOpen  = true;
					_primaryWeekOpenBar   = CurrentBar;   // first bar of this chart's week = its week's session open
				}
				int monthKey = tradingDay.Year * 12 + tradingDay.Month;
				if (monthKey != _curMonthKey)
				{
					_curMonthKey           = monthKey;
					_monthAwaitingRthOpen  = true;
					_primaryMonthOpenBar   = CurrentBar;  // first bar of this chart's month
				}

				if (_rthOk)
				{
					DateTime tRth = ConvertToRthTz(barTime);
					if (_rthIter.IsNewSession(tRth, true))
						_rthIter.GetNextSession(tRth, true);
					_rthSessBegin = _rthIter.ActualSessionBegin;
					_rthSessEnd   = _rthIter.ActualSessionEnd;
				}
			}

			// Current-day H/L across every bar of the trading day (independent of RTH/ETH).
			if (!double.IsNaN(_curDayHigh) && High[0] > _curDayHigh) _curDayHigh = High[0];
			if (!double.IsNaN(_curDayLow)  && Low[0]  < _curDayLow)  _curDayLow  = Low[0];

			// Map this bar onto the backfilled dev-trail for its trading day (every bar,
			// historical or live — a no-op for today, see MapHistDevTrailBar comment).
			if (ShowDevPocVa) MapHistDevTrailBar(barTime);

			bool isRth = false;
			if (_rthOk && _rthSessBegin != Core.Globals.MinDate)
			{
				DateTime tRth = ConvertToRthTz(barTime);
				isRth = tRth >= _rthSessBegin && tRth <= _rthSessEnd;
			}

			// ETH overnight H/L from THIS chart: accumulate from the ETH/Globex open until the
			// RTH open, then LOCK (the first RTH bar locks it and is excluded). _ethCloseLast
			// tracks every bar so at the next roll it holds the ETH session's final (16:00) close.
			if (EthFromPrimary && _haveEth)
			{
				_ethCloseLast = Close[0];
				if (isRth) _ethLocked = true;
				if (!_ethLocked)
				{
					if (High[0] > _ethHigh) _ethHigh = High[0];
					if (Low[0]  < _ethLow)  _ethLow  = Low[0];
				}
			}

			if (isRth)
			{
				if (!_haveRth) { _rthHigh = High[0]; _rthHighBar = CurrentBar; _rthLow = Low[0]; _rthLowBar = CurrentBar; _haveRth = true; }
				else
				{
					if (High[0] > _rthHigh) { _rthHigh = High[0]; _rthHighBar = CurrentBar; }
					if (Low[0]  < _rthLow)  { _rthLow  = Low[0];  _rthLowBar  = CurrentBar; }
				}
				_rthCloseLast = Close[0];
				_rthLastBar   = CurrentBar;

				if (!_rthOpenCapturedToday)
				{
					// Only the START BAR (anchor) comes from the primary chart. The OPEN PRICE
					// (OoD/OoW/OoM) comes from the RTH-hours series via HandleRthSeries — on a
					// tick/volume chart this straddle bar's Open[0] is a pre-open tick.
					_rthOpenStartBar      = CurrentBar;
					_rthOpenCapturedToday = true;
					if (_weekAwaitingRthOpen)  { _rthWeekStartBar  = CurrentBar; _weekAwaitingRthOpen  = false; }
					if (_monthAwaitingRthOpen) { _rthMonthStartBar = CurrentBar; _monthAwaitingRthOpen = false; }
				}
			}
		}

		// ETH levels come from the hidden ETH-hours series (BarsArray[1]) — so they work
		// on any chart, including RTH-only. The ETH template is 23h (17:00->16:00), which
		// INCLUDES RTH — so the ETH H/L is the OVERNIGHT range only: it accumulates from the
		// session open up to the RTH open, then LOCKS (stays frozen through RTH and the
		// post-RTH tail until the next overnight session begins). ETH lines render full
		// visible width since an overnight extreme has no corresponding primary (RTH) bar.
		private void HandleEthSeries()
		{
			if (!_ethSeriesAdded || _ethDayIter == null || _ethBip < 0 || CurrentBars[_ethBip] < 0) return;

			DateTime et  = Times[_ethBip][0];
			DateTime etd = _ethDayIter.GetTradingDay(et);

			if (etd != _ethCurTradingDay)
			{
				if (_haveEth)
				{
					_priorEthHigh  = _ethHigh;
					_priorEthLow   = _ethLow;
					_priorEthClose = _ethCloseLast;
					// record the completed ETH session's locked overnight H/L + its close (= the
					// Daily ETH bar close / Settlement), keyed by its trading day
					_ethByDay[_ethCurTradingDay] = new double[] { _ethHigh, _ethLow, _ethCloseLast };
					if (_ethByDay.Count > 90)
					{
						DateTime oldest = Core.Globals.MaxDate;
						foreach (DateTime dk in _ethByDay.Keys) if (dk < oldest) oldest = dk;
						_ethByDay.Remove(oldest);
					}
				}
				_ethCurTradingDay = etd;
				_haveEth          = false;
				_ethLocked        = false;   // new overnight session — accumulate again until RTH open
				_ethOpenToday     = Opens[_ethBip][0];

				DateTime wk = MondayOf(etd);
				if (wk != _ethCurWeekStart) { _ethCurWeekStart = wk; _ethOpenThisWeek = Opens[_ethBip][0]; }
				int mk = etd.Year * 12 + etd.Month;
				if (mk != _ethCurMonthKey)  { _ethCurMonthKey = mk; _ethOpenThisMonth = Opens[_ethBip][0]; }
			}

			// Once this ETH bar is inside the RTH window, lock the overnight H/L for the rest
			// of the ETH session (stays locked through RTH + the 15:15-16:00 post-close tail).
			if (!_ethLocked && _rthOk && _rthMembershipIter != null)
			{
				DateTime tRth = ConvertToRthTz(et);
				if (_rthMembershipIter.IsNewSession(tRth, true))
					_rthMembershipIter.GetNextSession(tRth, true);
				if (tRth >= _rthMembershipIter.ActualSessionBegin && tRth <= _rthMembershipIter.ActualSessionEnd)
					_ethLocked = true;
			}

			if (!_ethLocked)
			{
				if (!_haveEth) { _ethHigh = Highs[_ethBip][0]; _ethLow = Lows[_ethBip][0]; _haveEth = true; }
				else
				{
					if (Highs[_ethBip][0] > _ethHigh) _ethHigh = Highs[_ethBip][0];
					if (Lows[_ethBip][0]  < _ethLow)  _ethLow  = Lows[_ethBip][0];
				}
			}
			_ethCloseLast = Closes[_ethBip][0];
		}

		// 2026-10-16: precise OoD RTH open, sourced from the dedicated 1-min RTH series
		// instead of the Daily one below (which stopped delivering a bar for the current
		// day — see field comment on _rthMinBip). Same exact-open logic as HandleRthSeries
		// (the series resets at the session start, so bar 0's Open IS the RTH open), just on
		// a series/mechanism proven to still be receiving live data. GetTradingDay is called
		// on _rthMinDayIter specifically because it's Bars-bound (SessionIterator built from
		// a TradingHours object instead does NOT support GetTradingDay and throws — see the
		// warning on _rthBarsIter's usage above).
		private void HandleRthOpenPrecise()
		{
			if (!_rthMinSeriesAdded || _rthMinDayIter == null || _rthMinBip < 0 || CurrentBars[_rthMinBip] < 0) return;

			DateTime t;
			try { t = _rthMinDayIter.GetTradingDay(Times[_rthMinBip][0]); }
			catch { return; }

			if (t == _rthOpenPreciseDay) return;
			_rthOpenPreciseDay = t;
			_rthOpenPrecise    = Opens[_rthMinBip][0];
			_rthOpenByDayPrecise[t] = _rthOpenPrecise;
			TrimOldestDate(_rthOpenByDayPrecise, 90);
		}

		// RTH session OPENS from the hidden DAILY RTH-hours series. Because that series RESETS
		// at the session start, each daily RTH bar opens EXACTLY on the RTH open — so its Open
		// is the true OoD (unlike the primary tick/volume chart's straddle bar). One bar per
		// session; opens are keyed by date so live AND historical OoD/OoW/OoM read the right value.
		private void HandleRthSeries()
		{
			if (!_rthSeriesAdded || _rthBip < 0 || CurrentBars[_rthBip] < 0) return;

			// One daily RTH bar per session, so a change of Times[rth].Date marks a new RTH
			// session; Opens[rth][0] on that bar is the RTH open.
			DateTime d = Times[_rthBip][0].Date;
			if (d == _rthSeriesLastDate) return;
			DateTime prevDate = _rthSeriesLastDate;
			_rthSeriesLastDate = d;

			// Daily/Weekly primary only: the primary's own OnBarUpdate loop (which normally
			// rolls _priorRthHigh/_priorRthLow/_priorRthClose and pushes _rthHist) is skipped
			// entirely on a non-intraday chart (see OnBarUpdate). This hidden RTH-daily series
			// already gives exactly one bar per RTH session, so read the just-COMPLETED one's
			// own High/Low/Close directly here instead -- independent of the primary's period,
			// which is why HOY/LOY/COY + the historical Model-A segments can work on a Daily
			// chart even though the intraday classification loop below never runs for it.
			if (BarsArray != null && BarsArray.Length > 0 && !BarsArray[0].BarsType.IsIntraday
				&& prevDate > Core.Globals.MinDate && CurrentBars[_rthBip] >= 1)
			{
				double prevHigh = Highs[_rthBip][1], prevLow = Lows[_rthBip][1];
				double prevClose = Closes[_rthBip][1], prevOpen = Opens[_rthBip][1];
				int prevHighBar, prevLowBar, prevCloseBar;
				if (!_dailyPrimaryBarByDate.TryGetValue(prevDate, out prevHighBar)) prevHighBar = -1;
				prevLowBar = prevCloseBar = prevHighBar;

				_priorRthHigh = prevHigh;  _priorRthHighStartBar  = prevHighBar;
				_priorRthLow  = prevLow;   _priorRthLowStartBar   = prevLowBar;
				_priorRthClose = prevClose; _priorRthCloseStartBar = prevCloseBar;

				LogDbg(string.Format("RthRoll,{0:yyyy-MM-dd HH:mm:ss},prevDate={1:yyyy-MM-dd},newRthBarDate={2:yyyy-MM-dd},H={3},L={4},C={5},O={6},anchorBar={7},anchorFound={8}",
					DateTime.Now, prevDate, d, prevHigh, prevLow, prevClose, prevOpen, prevHighBar, _dailyPrimaryBarByDate.ContainsKey(prevDate)));

				double prevWeekOpen, prevMonthOpen;
				if (!_rthWeekOpenBy.TryGetValue(MondayOf(prevDate), out prevWeekOpen)) prevWeekOpen = prevOpen;
				if (!_rthMonthOpenBy.TryGetValue(new DateTime(prevDate.Year, prevDate.Month, 1), out prevMonthOpen)) prevMonthOpen = prevOpen;

				_rthHist.Add(new HRSess {
					date = prevDate,
					o = prevOpen, oBar = prevHighBar,
					h = prevHigh, hBar = prevHighBar, l = prevLow, lBar = prevLowBar,
					c = prevClose, cBar = prevCloseBar,
					weekOpen = prevWeekOpen, monthOpen = prevMonthOpen,
					dayStartBar = prevHighBar, dayEndBar = prevHighBar });
				if (_rthHist.Count > 70) _rthHist.RemoveAt(0);
			}

			double op = Opens[_rthBip][0];                 // true RTH open for this session
			_rthOpenByDay[d] = op;
			_rthOpenToday    = op;                         // live current day

			DateTime wk = MondayOf(d);
			if (!_rthWeekOpenBy.ContainsKey(wk)) _rthWeekOpenBy[wk] = op;   // first RTH session of the week
			if (wk != _rthSeriesWeek) { _rthSeriesWeek = wk; }
			_rthOpenThisWeek = _rthWeekOpenBy[wk];

			DateTime mo = new DateTime(d.Year, d.Month, 1);
			if (!_rthMonthOpenBy.ContainsKey(mo)) _rthMonthOpenBy[mo] = op;  // first RTH session of the month
			int mk = d.Year * 12 + d.Month;
			if (mk != _rthSeriesMonthKey) { _rthSeriesMonthKey = mk; }
			_rthOpenThisMonth = _rthMonthOpenBy[mo];

			TrimOldestDate(_rthOpenByDay, 90);
			TrimOldestDate(_rthWeekOpenBy, 30);
			TrimOldestDate(_rthMonthOpenBy, 24);
		}

		// Settlement from the hidden Daily ETH series — the Daily ETH bar close, keyed by its
		// trading day. Updates as the current day's bar forms; past days hold their final close.
		private void HandleEthDailySeries()
		{
			if (!_ethDaySeriesAdded || _ethDayBip < 0 || CurrentBars[_ethDayBip] < 0) return;
			DateTime dday = (_ethDaySessIter != null
				? _ethDaySessIter.GetTradingDay(Times[_ethDayBip][0])
				: Times[_ethDayBip][0]).Date;
			_settleByDay[dday] = Closes[_ethDayBip][0];
			TrimOldestDate(_settleByDay, 120);
		}

		// Settlement reference for a chart day = the Daily ETH close of the most recent trading
		// day STRICTLY BEFORE it (Friday shows Thursday's; Monday shows Friday's). Robust across
		// weekends/holidays/gaps. NaN if none recorded yet.
		private double SettlementBefore(DateTime day)
		{
			DateTime d0 = day.Date;
			DateTime best = Core.Globals.MinDate; double bestVal = double.NaN;
			foreach (KeyValuePair<DateTime, double> kv in _settleByDay)
				if (kv.Key < d0 && kv.Key > best) { best = kv.Key; bestVal = kv.Value; }
			return bestVal;
		}

		private static void TrimOldestDate(Dictionary<DateTime, double> map, int keep)
		{
			while (map.Count > keep)
			{
				DateTime oldest = Core.Globals.MaxDate;
				foreach (DateTime k in map.Keys) if (k < oldest) oldest = k;
				map.Remove(oldest);
			}
		}

		private DateTime ConvertToRthTz(DateTime t)
		{
			if (_rthHours == null) return t;
			TimeZoneInfo rthTz = _rthHours.TimeZoneInfo;
			return rthTz.Equals(_displayTz) ? t : TimeZoneInfo.ConvertTime(t, _displayTz, rthTz);
		}

		private static DateTime MondayOf(DateTime d)
		{
			int diff = (7 + (d.DayOfWeek - DayOfWeek.Monday)) % 7;
			return d.Date.AddDays(-diff);
		}

		// year*12+month key for a manual-OoM month; <=MinDate (unset) returns a non-matching -1.
		private static int MonthKeyOf(DateTime d)
		{
			return d <= Core.Globals.MinDate ? -1 : d.Year * 12 + d.Month;
		}

		// First VISIBLE primary bar of the current day(0)/week(1)/month(2), resolved straight
		// from the chart bars' calendar dates — NO SessionIterator (which is unreliable here
		// because the primary OnBarUpdate loop, which normally advances it, is skipped on a
		// daily chart). Scans the visible bars forward from the left edge and returns the
		// first one whose date falls in the same period as the last visible bar. Works on
		// any chart period: intraday RTH -> that day's session-open bar (RTH charts have no
		// overnight bars, so the day's first bar IS the RTH open); daily -> the period's
		// first daily bar.
		private int FirstBarOfCurrentPeriod(int period)
		{
			if (ChartBars == null) return 0;
			var bars = ChartBars.Bars;
			int from = Math.Max(0, ChartBars.FromIndex);
			int to   = ChartBars.ToIndex;
			if (bars == null || to < from) return from;

			DateTime refD = bars.GetTime(to).Date;
			for (int i = from; i <= to; i++)
			{
				DateTime d = bars.GetTime(i).Date;
				bool same = period == 2 ? (d.Year == refD.Year && d.Month == refD.Month)
						  : period == 1 ? (MondayOf(d) == MondayOf(refD))
						  :               (d == refD);
				if (same) return i;
			}
			return to;
		}

		// Current day's High/Low from the ACTUAL bars (not the visible window) so it stays
		// locked when you scroll/zoom. Intraday: the values tracked per-bar in OnBarUpdate.
		// Daily (OnBarUpdate skipped): the latest daily bar's own High/Low (one bar = one day).
		private void CurrentDayHighLow(out double hi, out double lo, out int startBar)
		{
			hi = double.NaN; lo = double.NaN; startBar = -1;
			if (BarsArray == null || BarsArray.Length == 0) return;
			var b = BarsArray[0];

			if (b.BarsType.IsIntraday)
			{
				hi = _curDayHigh; lo = _curDayLow; startBar = _curDayStartBar;
				return;
			}
			int last = b.Count - 1;
			if (last < 0) return;
			hi = b.GetHigh(last); lo = b.GetLow(last); startBar = last;
		}

		// ══════════════════════ Expected-move bands ══════════════════════
		// Throttled (≤ once/5s) re-read of the repo files + recompute of both bands.
		private void ReloadEm()
		{
			DateTime now = DateTime.UtcNow;
			if ((now - _emLastRead).TotalSeconds < 5) return;
			_emLastRead = now;

			// ---- VIX-formula band: prior RTH close ± close*(VIX/100)/sqrt(252)*sigma ----
			double vix = EmManualVix > 0 ? EmManualVix : ReadLastVixClose();
			_vixUsed = vix;
			double rf = _priorRthClose;
			if (!double.IsNaN(rf) && rf > 0 && !double.IsNaN(vix) && vix > 0)
			{
				double hw = rf * (vix / 100.0) / SQRT252 * Math.Max(0.0, EmSigma);
				_emvMax = rf + hw; _emvMin = rf - hw;
			}
			else { _emvMax = _emvMin = double.NaN; }

			// ---- gexlog method: gexlog's published expectedMove, anchored on the SAME prior
			// RTH close (NOT gexlog's own pivot `levels.current`, which sits ~55pt off the
			// close — that mismatch was the whole VIX-vs-GEX gap). Compares move SIZE only.
			double gexMove = ReadGexlogMove();
			if (!double.IsNaN(rf) && rf > 0 && !double.IsNaN(gexMove) && gexMove > 0)
			{
				_emgMax = rf + gexMove; _emgMin = rf - gexMove;
			}
			else { _emgMax = _emgMin = double.NaN; }
		}

		private double ReadLastVixClose()
		{
			try
			{
				if (!File.Exists(VixCsvPath)) return double.NaN;
				string[] lines = File.ReadAllLines(VixCsvPath);
				for (int i = lines.Length - 1; i >= 1; i--)   // skip header (row 0)
				{
					string ln = lines[i];
					if (string.IsNullOrWhiteSpace(ln)) continue;
					string[] p = ln.Split(',');
					double v;
					if (p.Length >= 1 && double.TryParse(p[p.Length - 1].Trim(),
							System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out v))
						return v;
				}
			}
			catch { }
			return double.NaN;
		}

		// gexlog's published 1-day expectedMove (half-width in points). We use THIS and anchor
		// it ourselves on the prior RTH close, rather than gexlog's own emUpper/emLower (which
		// are anchored on gexlog's pivot `levels.current`, ~55pt off the close).
		private double ReadGexlogMove()
		{
			try
			{
				if (string.IsNullOrWhiteSpace(GexlogRawDir) || !Directory.Exists(GexlogRawDir)) return double.NaN;

				// Resolve the brief for the current trading day: {date}_morning, else {date-1}_evening,
				// else the newest brief file in the dir.
				DateTime refDate = _curTradingDay > Core.Globals.MinDate ? _curTradingDay : DateTime.Today;
				string path = Path.Combine(GexlogRawDir, refDate.ToString("yyyy-MM-dd") + "_morning.json");
				if (!File.Exists(path))
					path = Path.Combine(GexlogRawDir, refDate.AddDays(-1).ToString("yyyy-MM-dd") + "_evening.json");
				if (!File.Exists(path))
				{
					string newest = null; DateTime newestT = DateTime.MinValue;
					foreach (string f in Directory.GetFiles(GexlogRawDir, "*.json"))
					{
						DateTime t = File.GetLastWriteTimeUtc(f);
						if (t > newestT) { newestT = t; newest = f; }
					}
					path = newest;
				}
				if (path == null || !File.Exists(path)) return double.NaN;

				return JsonNum(File.ReadAllText(path), "expectedMove");
			}
			catch { return double.NaN; }
		}

		// --- historical EM helpers: VIX close by date (whole CSV) + gexlog move per date ---
		private void EnsureVixMap()
		{
			try
			{
				if (string.IsNullOrWhiteSpace(VixCsvPath) || !File.Exists(VixCsvPath)) return;
				DateTime t = File.GetLastWriteTimeUtc(VixCsvPath);
				if (t == _vixMapStamp && _vixByDate.Count > 0) return;
				_vixMapStamp = t; _vixByDate.Clear();
				foreach (string ln in File.ReadAllLines(VixCsvPath))
				{
					string[] p = ln.Split(',');
					if (p.Length < 2) continue;
					DateTime d; double c;
					if (DateTime.TryParse(p[0].Trim(), System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out d)
						&& double.TryParse(p[p.Length - 1].Trim(), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out c))
						_vixByDate[d.Date] = c;
				}
			}
			catch { }
		}

		// VIX close for the latest trading date strictly before `date`.
		private double VixPriorTo(DateTime date)
		{
			double best = double.NaN; DateTime bestD = DateTime.MinValue;
			foreach (var kv in _vixByDate)
				if (kv.Key < date.Date && kv.Key > bestD) { bestD = kv.Key; best = kv.Value; }
			return best;
		}

		// gexlog expectedMove for a specific trading date (cached; {date}_morning else {date-1}_evening).
		private double GexMoveFor(DateTime date)
		{
			double v;
			if (_gexMoveByDate.TryGetValue(date.Date, out v)) return v;
			v = double.NaN;
			try
			{
				if (!string.IsNullOrWhiteSpace(GexlogRawDir) && Directory.Exists(GexlogRawDir))
				{
					string path = Path.Combine(GexlogRawDir, date.ToString("yyyy-MM-dd") + "_morning.json");
					if (!File.Exists(path))
						path = Path.Combine(GexlogRawDir, date.AddDays(-1).ToString("yyyy-MM-dd") + "_evening.json");
					if (File.Exists(path)) v = JsonNum(File.ReadAllText(path), "expectedMove");
				}
			}
			catch { }
			_gexMoveByDate[date.Date] = v;
			return v;
		}

		// Minimal JSON number extractor for a unique key (expectedMove is unique in the brief).
		private static double JsonNum(string json, string key)
		{
			int i = json.IndexOf("\"" + key + "\"");
			if (i < 0) return double.NaN;
			i = json.IndexOf(':', i);
			if (i < 0) return double.NaN;
			i++;
			while (i < json.Length && char.IsWhiteSpace(json[i])) i++;
			int j = i;
			while (j < json.Length)
			{
				char c = json[j];
				if (char.IsDigit(c) || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E') j++;
				else break;
			}
			double v;
			if (j > i && double.TryParse(json.Substring(i, j - i),
					System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out v))
				return v;
			return double.NaN;
		}

		// ══════════════════ Developing POC/Value-Area (S142+) ═════════════
		// Greedy value-area expansion from the POC, same method as the already-validated
		// scripts/volume_profile.py::value_area() — take whichever adjacent price level
		// (above or below) holds more volume at each step, until VaPercent of the day's
		// total volume is enclosed.
		private void RecomputeDevPocVa()
		{
			if (_vapToday.Count == 0) { _devPoc = _devVah = _devVal = double.NaN; return; }
			double pocPx = double.NaN, pocVol = -1, total = 0;
			foreach (var kv in _vapToday) { total += kv.Value; if (kv.Value > pocVol) { pocVol = kv.Value; pocPx = kv.Key; } }

			var prices = new List<double>(_vapToday.Keys);
			prices.Sort();
			int pocIdx = prices.IndexOf(pocPx);
			int lo = pocIdx, hi = pocIdx;
			double acc = _vapToday[pocPx], target = VaPercent * total;
			while (acc < target && (lo > 0 || hi < prices.Count - 1))
			{
				double up = hi < prices.Count - 1 ? _vapToday[prices[hi + 1]] : -1.0;
				double dn = lo > 0 ? _vapToday[prices[lo - 1]] : -1.0;
				if (up >= dn) { hi++; acc += _vapToday[prices[hi]]; }
				else { lo--; acc += _vapToday[prices[lo]]; }
			}
			_devPoc = pocPx; _devVal = prices[lo]; _devVah = prices[hi];

			if (_devTrail.Count == 0 || _devTrail[_devTrail.Count - 1].bar != CurrentBar)
				_devTrail.Add(new DevSnap { bar = CurrentBar, poc = _devPoc, vah = _devVah, val = _devVal });
			else
				_devTrail[_devTrail.Count - 1] = new DevSnap { bar = CurrentBar, poc = _devPoc, vah = _devVah, val = _devVal };
		}

		// Called exactly once per session boundary, while _vapToday + the passed-in `day`
		// still refer to the day that just completed. Appends one row to the persisted log
		// (skipped if that date is already in it — e.g. a chart reload replaying the same
		// day) then clears the accumulator for the day starting now.
		private void FinalizeDevPocVa(DateTime day)
		{
			RecomputeDevPocVa();
			if (!double.IsNaN(_devPoc) && !_vpByDate.ContainsKey(day.Date))
			{
				_vpByDate[day.Date] = new double[] { _devPoc, _devVah, _devVal };
				try
				{
					string dir = Path.GetDirectoryName(_vpLogPath);
					if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
					bool isNew = !File.Exists(_vpLogPath);
					using (var sw = new StreamWriter(_vpLogPath, true))
					{
						if (isNew) sw.WriteLine("date,vpoc,vah,val");
						sw.WriteLine(string.Format(System.Globalization.CultureInfo.InvariantCulture,
							"{0:yyyy-MM-dd},{1},{2},{3}", day, _devPoc, _devVah, _devVal));
					}
				}
				catch (Exception ex) { Print("SessionSRLevelsV10: could not write VP log: " + ex.Message); }
			}
			_vapToday.Clear();
			_devTrail.Clear();
			_devPoc = _devVah = _devVal = double.NaN;
		}

		// Loaded once at State.DataLoaded; grows in-memory via FinalizeDevPocVa as the live
		// session keeps running. Days before this feature was ever turned on simply aren't
		// in the file — nothing to backfill, by design (see header comment).
		private void LoadVpLog()
		{
			_vpByDate.Clear();
			if (!File.Exists(_vpLogPath)) return;
			try
			{
				foreach (string line in File.ReadAllLines(_vpLogPath))
				{
					if (line.Length == 0 || line.StartsWith("date")) continue;
					string[] p = line.Split(',');
					if (p.Length < 4) continue;
					DateTime d; double vp, vh, vl;
					if (DateTime.TryParse(p[0], System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out d)
						&& double.TryParse(p[1], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out vp)
						&& double.TryParse(p[2], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out vh)
						&& double.TryParse(p[3], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out vl))
						_vpByDate[d.Date] = new double[] { vp, vh, vl };
				}
			}
			catch (Exception ex) { Print("SessionSRLevelsV10: could not read VP log: " + ex.Message); }
		}

		// Loaded once at State.DataLoaded, same as LoadVpLog. Rows are grouped by `date`
		// (the trading-day label) into a per-day list sorted ascending by `timestamp` (the
		// bucket's own real CT calendar+clock time — may be the day BEFORE `date` for early/
		// overnight buckets, which is exactly why this is a full timestamp and not just a
		// time-of-day: comparing full timestamps in MapHistDevTrailBar sidesteps any
		// midnight-wrap ambiguity entirely).
		private void LoadVpTrailLog()
		{
			_vpTrailByDate.Clear();
			if (!File.Exists(_vpTrailLogPath)) return;
			try
			{
				foreach (string line in File.ReadAllLines(_vpTrailLogPath))
				{
					if (line.Length == 0 || line.StartsWith("date")) continue;
					string[] p = line.Split(',');
					if (p.Length < 5) continue;
					DateTime d, ts; double poc, vah, val;
					if (DateTime.TryParse(p[0], System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out d)
						&& DateTime.TryParse(p[1], System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out ts)
						&& double.TryParse(p[2], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out poc)
						&& double.TryParse(p[3], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out vah)
						&& double.TryParse(p[4], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out val))
					{
						List<TrailPt> list;
						if (!_vpTrailByDate.TryGetValue(d.Date, out list))
						{ list = new List<TrailPt>(); _vpTrailByDate[d.Date] = list; }
						list.Add(new TrailPt { ts = ts, poc = poc, vah = vah, val = val });
					}
				}
				foreach (List<TrailPt> list in _vpTrailByDate.Values)
					list.Sort((x, y) => x.ts.CompareTo(y.ts));
			}
			catch (Exception ex) { Print("SessionSRLevelsV10: could not read VP dev-trail log: " + ex.Message); }
		}

		// Called from the main per-bar intraday loop (every bar, historical or live) when
		// ShowDevPocVa is on. Maps this bar's own converted time onto the LATEST dev-trail
		// snapshot at-or-before it for its trading day (binary search over the sorted list),
		// appending a new _histDevTrailByDate entry only when it differs from the running
		// day's last one — the exact same incremental-build pattern _devTrail uses for the
		// live day, just reading from the file instead of live ticks. A no-op (and
		// essentially free) for today, since today's date is never in the backfilled file
		// yet — today keeps using the live _devTrail exclusively, by construction, no
		// explicit guard needed.
		private void MapHistDevTrailBar(DateTime barTime)
		{
			List<TrailPt> trail;
			if (!_vpTrailByDate.TryGetValue(_curTradingDay.Date, out trail) || trail.Count == 0) return;
			DateTime tRth = ConvertToRthTz(barTime);
			int lo = 0, hi = trail.Count - 1, at = -1;
			while (lo <= hi)
			{
				int mid = (lo + hi) / 2;
				if (trail[mid].ts <= tRth) { at = mid; lo = mid + 1; }
				else hi = mid - 1;
			}
			if (at < 0) return;
			TrailPt pt = trail[at];
			List<DevSnap> hist;
			if (!_histDevTrailByDate.TryGetValue(_curTradingDay.Date, out hist))
			{ hist = new List<DevSnap>(); _histDevTrailByDate[_curTradingDay.Date] = hist; }
			if (hist.Count == 0 || hist[hist.Count - 1].bar != CurrentBar)
				hist.Add(new DevSnap { bar = CurrentBar, poc = pt.poc, vah = pt.vah, val = pt.val });
			else
				hist[hist.Count - 1] = new DevSnap { bar = CurrentBar, poc = pt.poc, vah = pt.vah, val = pt.val };
		}

		// Two distinct things, per the S145-2 revision (see header comment — corrected after
		// the first pass drew the wrong visual for both halves): (1) TODAY's own POC/VA
		// drawn as an actual bar-by-bar developing trail (_devTrail — a flat step per bar,
		// holding each bar's own snapshot value until the next bar updates it), so you see
		// the level move as the session develops, not a flat ray using only the latest
		// value; (2) the PRIOR completed session's FINAL POC/VA projected FORWARD as a
		// FILLED COLORED RANGE (box, same visual language as the historical own-box below —
		// not thin lines) across the CURRENT/next session's bars (ShowPriorVp).
		private void DrawDevPocVa(ChartControl cc, ChartScale cs)
		{
			if (!ShowDevPocVa || ChartBars == null || RenderTarget == null) return;
			int fromV = ChartBars.FromIndex, toV = ChartBars.ToIndex;
			if (toV < 0) return;

			// (1a) Today's own developing POC/VAH/VAL, bar by bar — see _devTrail comment.
			// ShowDevTrail is a real off switch (independent of PocOpacity/VaOpacity) —
			// skips drawing entirely rather than relying on a transparent color.
			if (ShowDevTrail) DrawDevTrail(_devTrail, CurrentBar, cc, cs, fromV, toV);

			// (2a) PRIOR session's final POC/VA projected onto TODAY (still developing), as
			// a colored range. "Prior" = the most recently completed entry in _rthHist — one
			// real trading session, calendar gaps (weekends/holidays) already excluded.
			if (ShowPriorVp && _curDayStartBar >= 0 && _curDayStartBar <= toV && _rthHist.Count > 0)
			{
				double[] pvp;
				if (_vpByDate.TryGetValue(_rthHist[_rthHist.Count - 1].date.Date, out pvp))
				{
					int sIdx = Math.Max(_curDayStartBar, fromV), eIdx = Math.Min(CurrentBar, toV);
					if (eIdx >= sIdx)
					{
						float xL = cc.GetXByBarIndex(ChartBars, sIdx), xR = cc.GetXByBarIndex(ChartBars, eIdx);
						DrawPriorVpBox(pvp, xL, xR, cs);
					}
				}
			}

			// (1b)+(2b) Each of the last VpHistSessions completed sessions: its OWN
			// developing trail if the L1-tape backfill has one (bar-by-bar, same as today —
			// see MapHistDevTrailBar/_histDevTrailByDate), else a static box using only the
			// FINAL value (old behavior, kept as the fallback for a day that was only ever
			// run through the final-value-only backfill) — over its OWN bars, plus (if
			// ShowPriorVp) ITS predecessor's VP projected onto it the same way, so every
			// session shown also shows both what it did and what it opened against.
			if (VpHistSessions > 0 && _rthHist.Count > 0)
			{
				var boxBr = new D2DSolidColorBrush(RenderTarget, ToColor4(VaBoxColor, 0.12f));
				var pocBr = new D2DSolidColorBrush(RenderTarget, ToColor4(PocColor, PocOpacity / 100f));
				int shown = 0;
				for (int k = _rthHist.Count - 1; k >= 0 && shown < VpHistSessions; k--)
				{
					HRSess s = _rthHist[k];
					double[] vp;
					if (!_vpByDate.TryGetValue(s.date.Date, out vp)) continue;
					shown++;
					if (s.dayEndBar < fromV || s.dayStartBar > toV) continue;
					int sIdx = Math.Max(s.dayStartBar, fromV), eIdx = Math.Min(s.dayEndBar, toV);
					if (eIdx < sIdx) continue;
					float xL = cc.GetXByBarIndex(ChartBars, sIdx), xR = cc.GetXByBarIndex(ChartBars, eIdx);

					if (ShowDevTrail)
					{
						List<DevSnap> hist;
						if (_histDevTrailByDate.TryGetValue(s.date.Date, out hist) && hist.Count > 0)
						{
							DrawDevTrail(hist, s.dayEndBar, cc, cs, fromV, toV);
						}
						else
						{
							float yHi = cs.GetYByValue(vp[1]), yLo = cs.GetYByValue(vp[2]);
							RenderTarget.FillRectangle(new RectangleF(xL, Math.Min(yHi, yLo), Math.Max(xR - xL, 1f), Math.Max(Math.Abs(yLo - yHi), 1f)), boxBr);
							float yPoc = cs.GetYByValue(vp[0]);
							RenderTarget.DrawLine(new Vector2(xL, yPoc), new Vector2(xR, yPoc), pocBr, 1.5f);
						}
					}

					if (ShowPriorVp && k > 0)
					{
						double[] pvp;
						if (_vpByDate.TryGetValue(_rthHist[k - 1].date.Date, out pvp))
							DrawPriorVpBox(pvp, xL, xR, cs);
					}
				}
				boxBr.Dispose(); pocBr.Dispose();
			}
		}

		// A session's developing POC/VAH/VAL, drawn as a literal bar-by-bar step trail
		// instead of one flat ray: each entry holds flat from its own bar until the NEXT
		// snapshot's bar (or `endBar` for the most recent one — CurrentBar for today-live,
		// that session's own dayEndBar for a completed historical day), so the line visibly
		// steps up/down exactly where the developing value actually changed through the
		// session. Shared by today's live _devTrail AND every backfilled historical day's
		// _histDevTrailByDate entry (same rendering, different trail source).
		private void DrawDevTrail(List<DevSnap> trail, int endBar, ChartControl cc, ChartScale cs, int fromV, int toV)
		{
			if (trail.Count == 0) return;
			var pocBr = new D2DSolidColorBrush(RenderTarget, ToColor4(PocColor, PocOpacity / 100f));
			var vaBr  = new D2DSolidColorBrush(RenderTarget, ToColor4(VaColor, VaOpacity / 100f));
			for (int i = 0; i < trail.Count; i++)
			{
				DevSnap snap = trail[i];
				int segEnd = (i + 1 < trail.Count) ? trail[i + 1].bar : endBar;
				int sIdx = Math.Max(snap.bar, fromV), eIdx = Math.Min(segEnd, toV);
				if (eIdx < sIdx) continue;
				float xL = cc.GetXByBarIndex(ChartBars, sIdx), xR = cc.GetXByBarIndex(ChartBars, eIdx);
				RenderTarget.DrawLine(new Vector2(xL, cs.GetYByValue(snap.poc)), new Vector2(xR, cs.GetYByValue(snap.poc)), pocBr, 2f);
				RenderTarget.DrawLine(new Vector2(xL, cs.GetYByValue(snap.vah)), new Vector2(xR, cs.GetYByValue(snap.vah)), vaBr, 1f);
				RenderTarget.DrawLine(new Vector2(xL, cs.GetYByValue(snap.val)), new Vector2(xR, cs.GetYByValue(snap.val)), vaBr, 1f);
			}
			pocBr.Dispose(); vaBr.Dispose();
		}

		// The prior session's VPOC/VAH/VAL as a FILLED colored range spanning [xL,xR] of the
		// NEXT session — either today's still-developing bars or a historical session's own
		// bars. Same FillRectangle + POC-line visual language as the historical own-box
		// below, just in the Prior* colors, so it reads as "a value area" not a thin line.
		private void DrawPriorVpBox(double[] pvp, float xL, float xR, ChartScale cs)
		{
			var boxBr = new D2DSolidColorBrush(RenderTarget, ToColor4(PriorVaBoxColor, PriorVpOpacity / 100f));
			var pocBr = new D2DSolidColorBrush(RenderTarget, ToColor4(PriorPocColor, 0.9f));
			float yHi = cs.GetYByValue(pvp[1]), yLo = cs.GetYByValue(pvp[2]);
			RenderTarget.FillRectangle(new RectangleF(xL, Math.Min(yHi, yLo), Math.Max(xR - xL, 1f), Math.Max(Math.Abs(yLo - yHi), 1f)), boxBr);
			float yPoc = cs.GetYByValue(pvp[0]);
			RenderTarget.DrawLine(new Vector2(xL, yPoc), new Vector2(xR, yPoc), pocBr, 1.5f);
			boxBr.Dispose(); pocBr.Dispose();
		}

		private static Color4 ToColor4(WMBrush b, float alpha)
		{
			var scb = b as WMSolidColorBrush;
			if (scb == null) return new Color4(1f, 1f, 1f, alpha);
			WMColor c = scb.Color;
			return new Color4(c.R / 255f, c.G / 255f, c.B / 255f, alpha);
		}

		// ══════════════════════════ Rendering ════════════════════════════
		// Lines are RAYS: they start at the bar where that level's value was actually
		// established and run right to the current bar — never the full panel width,
		// never past "now" (same idea as PADayTradingSR). Labels sit just past that
		// right end, not pinned to the chart's physical right edge.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;

			ReloadEm();

			var defs = MergeSamePrice(BuildLevelDefs());
			if (defs.Count == 0) return;

			float panelLeft = (float)ChartPanel.X;
			int lastIdx = ChartBars.ToIndex;
			if (lastIdx < 0) return;
			float lineEndX = chartControl.GetXByBarIndex(ChartBars, lastIdx + ExtendBarsRight);

			var labels = new List<LabelInfo>();
			foreach (LevelDef d in defs)
			{
				if (!d.enabled || double.IsNaN(d.price) || d.startBarIdx < 0) continue;

				int startIdx = Math.Max(d.startBarIdx, ChartBars.FromIndex);
				float xStart = Math.Max(panelLeft, chartControl.GetXByBarIndex(ChartBars, startIdx));

				// Optional per-level right cap (e.g. OoD RTH stops at its RTH session end
				// instead of spilling into the following ETH session). The cap still honors
				// ExtendBarsRight — the line runs ExtendBarsRight bars past the session end,
				// never beyond the global right edge (lineEndX).
				float xEnd = lineEndX;
				if (d.endBarIdx >= 0)
				{
					float xe = chartControl.GetXByBarIndex(ChartBars, d.endBarIdx + ExtendBarsRight);
					if (xe < xEnd) xEnd = xe;
				}
				if (xStart >= xEnd) continue;

				float a = Math.Max(0f, Math.Min(1f, d.opacity / 100f));
				var sdxBrush = new D2DSolidColorBrush(RenderTarget,
					new Color4(d.color.R / 255f, d.color.G / 255f, d.color.B / 255f, a));

				float y = chartScale.GetYByValue(d.price);
				DrawStyledLine(xStart, xEnd, y, sdxBrush, d.thickness, d.style);

				string text = (_priceVisibleSet ? _priceVisible : ShowPriceInLabel) ? d.label + " " + F(d.price) : d.label;
				bool capped = xEnd < lineEndX - 0.5f;   // line stops before the right edge -> label sits at the cap
				labels.Add(new LabelInfo { y = y, trueY = y, text = text, brush = sdxBrush, col = d.col, inline = capped, xInline = xEnd + 6f });
			}

			if (_labelsVisible) DrawLabels(labels, lineEndX + 6f);

			foreach (LabelInfo li in labels) li.brush.Dispose();

			DrawHistorical(chartControl, chartScale);
			DrawDevPocVa(chartControl, chartScale);
		}

		// Historical levels (Model A): each completed RTH session's O/H/L/C as a horizontal
		// segment confined to that session (startBar→endBar), dimmed, with a centered label
		// placed above the line (H/C/O) or below it (L) to stay off the candles.
		private void DrawHistorical(ChartControl chartControl, ChartScale chartScale)
		{
			if (HistSessions <= 0 || _rthHist.Count == 0 || ChartBars == null) return;
			int fromV = ChartBars.FromIndex, toV = ChartBars.ToIndex;
			if (toV < 0) return;
			float panelLeft = (float)ChartPanel.X, panelRight = (float)(ChartPanel.X + ChartPanel.W);
			float dim = Math.Max(0.1f, Math.Min(1f, HistOpacity / 100f));
			float textH = LabelFontSize + 6f;

			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			tf.WordWrapping = WordWrapping.NoWrap;

			EnsureVixMap();

			// Each day D shows its OWN open/week/month/ETH-range, plus the PRIOR session's
			// High/Low/Close and prior-close-anchored 1D bands (HOY/LOY/COY = "of yesterday"),
			// same semantics as the live levels. H/L/C and the EM anchor come from record k-1.
			int n = Math.Min(HistSessions, _rthHist.Count);
			for (int k = _rthHist.Count - n; k < _rthHist.Count; k++)
			{
				if (k < 0) continue;
				HRSess s = _rthHist[k];
				if (s.dayEndBar < fromV || s.dayStartBar > toV) continue;   // trading day fully off-screen
				int ds = s.dayStartBar, de = s.dayEndBar;
				var hentries = new List<HistEntry>();

				// This day's own levels. Opens come from the RTH-hours series (keyed by date),
				// NOT the primary chart. Same-price levels get merged below into one line + label.
				double oD, oW, oM;
				// Precise 1-min-series source tried FIRST (see _rthOpenByDayPrecise comment —
				// 2026-10-16: the old _rthOpenByDay / s.o fallback chain below is only ever
				// written by the Daily RTH series that stopped updating, so history kept
				// reading a stale/wrong source even after the live value was fixed).
				bool hasOD = _rthOpenByDayPrecise.TryGetValue(s.date, out oD);
				if (!hasOD) hasOD = _rthOpenByDay.TryGetValue(s.date, out oD);
				bool hasOW = _rthWeekOpenBy.TryGetValue(MondayOf(s.date), out oW);
				bool hasOM = _rthMonthOpenBy.TryGetValue(new DateTime(s.date.Year, s.date.Month, 1), out oM);
				if (!hasOD) { oD = s.o;        hasOD = !double.IsNaN(oD); }   // fallback to stored open
				if (!hasOW) { oW = s.weekOpen;  hasOW = !double.IsNaN(oW); }
				if (!hasOM) { oM = s.monthOpen; hasOM = !double.IsNaN(oM); }
				AddHist(hentries, Hist_OoD && hasOD, oD, ROoD_Label, ROoD_Color, ROoD_Style, ROoD_Thickness, true, s.oBar);
				AddHist(hentries, Hist_OoW && hasOW, oW, ROoW_Label, ROoW_Color, ROoW_Style, ROoW_Thickness, true, ds);
				AddHist(hentries, Hist_OoM && hasOM, oM, ROoM_Label, ROoM_Color, ROoM_Style, ROoM_Thickness, true, ds);
				double[] eth;
				if (_ethByDay.TryGetValue(s.date, out eth) && eth != null && eth.Length >= 2)
				{
					AddHist(hentries, Hist_EthH, eth[0], EHOY_Label, EHOY_Color, EHOY_Style, EHOY_Thickness, true, ds);
					AddHist(hentries, Hist_EthL, eth[1], ELOY_Label, ELOY_Color, ELOY_Style, ELOY_Thickness, false, ds);
				}

				// Settlement = the PRIOR trading day's Daily ETH close (Friday shows Thursday's).
				double settle = SettlementBefore(s.date);
				AddHist(hentries, Hist_Settle && !double.IsNaN(settle), settle, Settle_Label, Settle_Color, Settle_Style, Settle_Thickness, true, ds);

				// Prior-session-derived levels (need record k-1).
				if (k >= 1)
				{
					HRSess p = _rthHist[k - 1];
					double pc = p.c;   // prior RTH close (EM anchor)
					AddHist(hentries, Hist_HOY, p.h, RHOY_Label, RHOY_Color, RHOY_Style, RHOY_Thickness, true, ds);
					AddHist(hentries, Hist_LOY, p.l, RLOY_Label, RLOY_Color, RLOY_Style, RLOY_Thickness, false, ds);
					AddHist(hentries, Hist_COY, pc, RCOY_Label, RCOY_Color, RCOY_Style, RCOY_Thickness, true, ds);

					// 1D bands, both anchored on the prior RTH close (matches live).
					double vix = VixPriorTo(s.date);
					if (!double.IsNaN(pc) && pc > 0 && !double.IsNaN(vix) && vix > 0)
					{
						double m = pc * (vix / 100.0) / SQRT252 * Math.Max(0.0, EmSigma);
						AddHist(hentries, Hist_EMV_Max, pc + m, EMV_Max_Label, EMV_Max_Color, EMV_Max_Style, EMV_Max_Thickness, true, ds);
						AddHist(hentries, Hist_EMV_Min, pc - m, EMV_Min_Label, EMV_Min_Color, EMV_Min_Style, EMV_Min_Thickness, false, ds);
					}
					double gm = GexMoveFor(s.date);
					if (!double.IsNaN(pc) && pc > 0 && !double.IsNaN(gm) && gm > 0)
					{
						AddHist(hentries, Hist_EMG_Max, pc + gm, EMG_Max_Label, EMG_Max_Color, EMG_Max_Style, EMG_Max_Thickness, true, ds);
						AddHist(hentries, Hist_EMG_Min, pc - gm, EMG_Min_Label, EMG_Min_Color, EMG_Min_Style, EMG_Min_Thickness, false, ds);
					}
				}

				// Draw, collapsing any levels that share a price into one line + combined label.
				foreach (HistEntry he in MergeHistEntries(hentries))
					DrawHistSeg(chartControl, chartScale, tf, he.startBar, de, panelLeft, panelRight, dim, textH, true, he.price, he.label, he.brush, he.style, he.thickness, he.above);
			}
			tf.Dispose();
		}

		private void DrawHistSeg(ChartControl cc, ChartScale cs, TextFormat tf, int startBar, int endBar,
			float panelLeft, float panelRight, float dim, float textH,
			bool enabled, double price, string label, WMBrush brush, LevelLineStyle style, int thickness, bool above)
		{
			if (!enabled || double.IsNaN(price) || startBar < 0 || endBar < startBar) return;
			int sIdx = Math.Max(startBar, ChartBars.FromIndex);
			int eIdx = Math.Min(endBar, ChartBars.ToIndex);
			if (eIdx < sIdx) return;
			float xL = Math.Max(panelLeft, cc.GetXByBarIndex(ChartBars, sIdx));
			float xR = Math.Min(panelRight, cc.GetXByBarIndex(ChartBars, eIdx));
			if (xR <= xL) return;

			var scb = brush as WMSolidColorBrush;
			WMColor wc = scb != null ? scb.Color : Colors.Gray;
			var d2d = new D2DSolidColorBrush(RenderTarget, new Color4(wc.R / 255f, wc.G / 255f, wc.B / 255f, dim));
			float y = cs.GetYByValue(price);
			DrawStyledLine(xL, xR, y, d2d, thickness, style);

			if (_labelsVisible && label != null && label.Length > 0)
			{
				string txt = ShowPriceInLabel ? label + " " + F(price) : label;
				float cx = (xL + xR) / 2f - (txt.Length * LabelFontSize * 0.28f);   // roughly centered
				float ty = above ? (y - textH - 1f) : (y + 1f);
				RenderTarget.DrawText(txt, tf, new RectangleF(cx, ty, LabelFontSize * 18f, textH), d2d);
			}
			d2d.Dispose();
		}

		// One historical level to be drawn for a given day (collected, merged by price, then drawn).
		private struct HistEntry { public double price; public string label; public WMBrush brush; public LevelLineStyle style; public int thickness; public bool above; public int startBar; }

		private static void AddHist(List<HistEntry> es, bool enabled, double price, string label,
			WMBrush brush, LevelLineStyle style, int thickness, bool above, int startBar)
		{
			if (!enabled || double.IsNaN(price)) return;
			es.Add(new HistEntry { price = price, label = label, brush = brush, style = style, thickness = thickness, above = above, startBar = startBar });
		}

		// Same-price merge for a day's historical levels — the per-day analogue of MergeSamePrice:
		// collapse levels at the same price into one entry with a combined "a / b" label and the
		// earliest start bar; the first entry keeps its style/color/above placement.
		private List<HistEntry> MergeHistEntries(List<HistEntry> src)
		{
			var outp = new List<HistEntry>();
			foreach (HistEntry e in src)
			{
				int gi = -1;
				for (int k = 0; k < outp.Count; k++)
					if (Math.Abs(outp[k].price - e.price) < TickSize * 0.5) { gi = k; break; }
				if (gi < 0) { outp.Add(e); continue; }
				HistEntry g = outp[gi];
				if (!string.IsNullOrEmpty(e.label) && (g.label == null || !LabelAlreadyIn(g.label, e.label)))
					g.label = string.IsNullOrEmpty(g.label) ? e.label : g.label + " / " + e.label;
				if (e.startBar < g.startBar) g.startBar = e.startBar;
				outp[gi] = g;
			}
			return outp;
		}

		private List<LevelDef> BuildLevelDefs()
		{
			var list = new List<LevelDef>(12);

			// Current-day running High/Low — from the chart's own bars, works on any period.
			// Independent of the RTH/ETH toggles; gated only by their own Enabled.
			if (CDH_Enabled || CDL_Enabled)
			{
				double cdHi, cdLo; int cdStart;
				CurrentDayHighLow(out cdHi, out cdLo, out cdStart);
				Add(list, CDH_Enabled, CDH_Label, cdHi, CDH_Color, CDH_Opacity, CDH_Style, CDH_Thickness, 0, cdStart);
				Add(list, CDL_Enabled, CDL_Label, cdLo, CDL_Color, CDL_Opacity, CDL_Style, CDL_Thickness, 0, cdStart);
			}

			// Expected-move 1-day bands (two methods, anchored at the current day's open bar).
			{
				int fb = ChartBars != null ? ChartBars.FromIndex : 0;
				int emStart;
				if (BarsArray != null && BarsArray.Length > 0 && BarsArray[0].BarsType.IsIntraday)
					emStart = _primaryDayOpenBar >= 0 ? _primaryDayOpenBar : fb;
				else
					emStart = FirstBarOfCurrentPeriod(0);
				Add(list, EMV_Max_Enabled, EMV_Max_Label, _emvMax, EMV_Max_Color, EMV_Max_Opacity, EMV_Max_Style, EMV_Max_Thickness, 0, emStart);
				Add(list, EMV_Min_Enabled, EMV_Min_Label, _emvMin, EMV_Min_Color, EMV_Min_Opacity, EMV_Min_Style, EMV_Min_Thickness, 0, emStart);
				Add(list, EMG_Max_Enabled, EMG_Max_Label, _emgMax, EMG_Max_Color, EMG_Max_Opacity, EMG_Max_Style, EMG_Max_Thickness, 0, emStart);
				Add(list, EMG_Min_Enabled, EMG_Min_Label, _emgMin, EMG_Min_Color, EMG_Min_Opacity, EMG_Min_Style, EMG_Min_Thickness, 0, emStart);
			}

			if (_rthVisible)
			{
				Add(list, RHOY_Enabled, RHOY_Label, _priorRthHigh,    RHOY_Color, RHOY_Opacity, RHOY_Style, RHOY_Thickness, 0, _priorRthHighStartBar);
				Add(list, RLOY_Enabled, RLOY_Label, _priorRthLow,     RLOY_Color, RLOY_Opacity, RLOY_Style, RLOY_Thickness, 0, _priorRthLowStartBar);
				Add(list, RCOY_Enabled, RCOY_Label, _priorRthClose,   RCOY_Color, RCOY_Opacity, RCOY_Style, RCOY_Thickness, 0, _priorRthCloseStartBar);

				// RTH start bars: on an INTRADAY chart use the anchors tracked live in
				// OnBarUpdate. On a DAILY chart that loop is skipped, so fall back to the
				// calendar date walk (same pattern as the ETH block below).
				int rthOpenStart, rthLastBarEff, rthWeekStart, rthMonthStart;
				if (BarsArray != null && BarsArray.Length > 0 && BarsArray[0].BarsType.IsIntraday)
				{
					rthOpenStart  = _rthOpenStartBar;
					rthLastBarEff = _rthLastBar;
					rthWeekStart  = _rthWeekStartBar;
					rthMonthStart = _rthMonthStartBar;
				}
				else
				{
					rthOpenStart  = FirstBarOfCurrentPeriod(0);
					rthLastBarEff = -1;   // no intraday RTH-only tail to cap on a daily bar -- extend normally
					rthWeekStart  = FirstBarOfCurrentPeriod(1);
					rthMonthStart = FirstBarOfCurrentPeriod(2);
				}
				// 2026-10-16: OoD/OoW/OoM RTH went stale mid-session — _rthSeriesLastDate (and
				// therefore _rthOpenToday/_rthOpenThisWeek/_rthOpenThisMonth) only ever update
				// when HandleRthSeries actually runs, which depends on the hidden RTH data
				// series continuing to deliver bars. If that subscription silently stops
				// (a feed hiccup, independent of the primary chart's own live data — this
				// platform had plenty of instability today), these fields freeze at whatever
				// day they last confirmed and nothing in the old code could ever detect or
				// show that — it just kept drawing an old day's open as if it were today's,
				// with no indication anything was wrong. Fail safe instead: only draw these
				// three if _rthSeriesLastDate is actually today's date (checked against the
				// live clock, not cached state); otherwise suppress them rather than show a
				// stale price with no warning. A real reload (which re-subscribes the hidden
				// series from scratch) is still required to recover the line itself.
				bool rthOpenFresh = _rthSeriesLastDate == Core.Globals.Now.Date;

				// 2026-10-16: OoD RTH's price now comes from the dedicated 1-min series
				// (_rthOpenPrecise/_rthOpenPreciseDay, set by HandleRthOpenPrecise) instead of
				// the Daily series above, which stopped delivering a bar for the current day.
				// Exact — bar 0 of that series opens precisely on the RTH open, same guarantee
				// the Daily series was meant to provide, just on a mechanism still receiving
				// live data. If it's not confirmed for today either, suppress rather than show
				// any approximation — no silent wrong number, and no guessed one either.
				bool roodPreciseFresh = _rthOpenPreciseDay == Core.Globals.Now.Date;
				Add(list, ROoD_Enabled && roodPreciseFresh, ROoD_Label, _rthOpenPrecise, ROoD_Color, ROoD_Opacity, ROoD_Style, ROoD_Thickness, 0, rthOpenStart, rthLastBarEff);
				if (!roodPreciseFresh && DebugLog)
					LogDbg(string.Format("RthOpenPreciseStale,{0:yyyy-MM-dd HH:mm:ss},lastConfirmedDay={1:yyyy-MM-dd},today={2:yyyy-MM-dd}",
						Core.Globals.Now, _rthOpenPreciseDay, Core.Globals.Now.Date));

				Add(list, ROoW_Enabled && rthOpenFresh, ROoW_Label, _rthOpenThisWeek, ROoW_Color, ROoW_Opacity, ROoW_Style, ROoW_Thickness, 0, rthWeekStart);
				// RTH OoM: manual override wins when a price is set and its month == the current month
				double rOoM = _rthOpenThisMonth; int rOoMBar = rthMonthStart;
				if (ROoM_ManualPrice != 0 && MonthKeyOf(ROoM_ManualMonth) == _curMonthKey)
				{ rOoM = ROoM_ManualPrice; rOoMBar = ChartBars.FromIndex; }
				Add(list, ROoM_Enabled && (rthOpenFresh || ROoM_ManualPrice != 0), ROoM_Label, rOoM, ROoM_Color, ROoM_Opacity, ROoM_Style, ROoM_Thickness, 0, rOoMBar);
				if (!rthOpenFresh && DebugLog)
					LogDbg(string.Format("RthOpenStale,{0:yyyy-MM-dd HH:mm:ss},lastConfirmedDay={1:yyyy-MM-dd},today={2:yyyy-MM-dd}",
						Core.Globals.Now, _rthSeriesLastDate, Core.Globals.Now.Date));
			}
			if (_ethVisible)
			{
				// ETH start bars: on an INTRADAY chart use the primary chart's own session-open
				// bars (RTH open on an RTH chart, ETH/Globex 17:00 open on an ETH chart) tracked
				// in OnBarUpdate — so ETH lines begin at the session open, not calendar midnight.
				// On a DAILY chart that primary loop is skipped, so fall back to the calendar
				// date walk (the day/week/month's first daily bar).
				int ethDayStart, ethWeekStart, ethMonthStart;
				if (BarsArray != null && BarsArray.Length > 0 && BarsArray[0].BarsType.IsIntraday)
				{
					int fb = ChartBars != null ? ChartBars.FromIndex : 0;
					ethDayStart   = _primaryDayOpenBar   >= 0 ? _primaryDayOpenBar   : fb;
					ethWeekStart  = _primaryWeekOpenBar  >= 0 ? _primaryWeekOpenBar  : fb;
					ethMonthStart = _primaryMonthOpenBar >= 0 ? _primaryMonthOpenBar : fb;
				}
				else
				{
					ethDayStart   = FirstBarOfCurrentPeriod(0);
					ethWeekStart  = FirstBarOfCurrentPeriod(1);
					ethMonthStart = FirstBarOfCurrentPeriod(2);
				}
				// col 0 = same label column as the RTH levels (de-collision merges them).
				Add(list, EHOY_Enabled, EHOY_Label, _ethHigh,          EHOY_Color, EHOY_Opacity, EHOY_Style, EHOY_Thickness, 0, ethDayStart);
				Add(list, ELOY_Enabled, ELOY_Label, _ethLow,           ELOY_Color, ELOY_Opacity, ELOY_Style, ELOY_Thickness, 0, ethDayStart);
				Add(list, ECOY_Enabled, ECOY_Label, _priorEthClose,    ECOY_Color, ECOY_Opacity, ECOY_Style, ECOY_Thickness, 0, ethDayStart);
				// Settlement = the PRIOR trading day's Daily ETH close (today's reference), read
				// straight from the hidden Daily ETH series.
				Add(list, Settle_Enabled, Settle_Label, SettlementBefore(_curTradingDay), Settle_Color, Settle_Opacity, Settle_Style, Settle_Thickness, 0, ethDayStart);
				Add(list, EOoD_Enabled, EOoD_Label, _ethOpenToday,     EOoD_Color, EOoD_Opacity, EOoD_Style, EOoD_Thickness, 0, ethDayStart);
				Add(list, EOoW_Enabled, EOoW_Label, _ethOpenThisWeek,  EOoW_Color, EOoW_Opacity, EOoW_Style, EOoW_Thickness, 0, ethWeekStart);
				// ETH OoM: manual override wins when a price is set and its month == the current ETH month
				double eOoM = _ethOpenThisMonth;
				if (EOoM_ManualPrice != 0 && MonthKeyOf(EOoM_ManualMonth) == _ethCurMonthKey)
					eOoM = EOoM_ManualPrice;
				Add(list, EOoM_Enabled, EOoM_Label, eOoM, EOoM_Color, EOoM_Opacity, EOoM_Style, EOoM_Thickness, 0, ethMonthStart);
			}

			// Custom/manual levels: no "session" origin bar to anchor to, so the start date
			// is a user-picked calendar date (StartDate property -> a calendar dropdown in
			// the Properties grid). Left unset (Core.Globals.MinDate sentinel) -> falls back
			// to the leftmost visible bar, same as before.
			Add(list, C1_Enabled && C1_Price != 0, C1_Label, C1_Price, C1_Color, C1_Opacity, C1_Style, C1_Thickness, 0, ResolveCustomStartBar(C1_StartDate));
			Add(list, C2_Enabled && C2_Price != 0, C2_Label, C2_Price, C2_Color, C2_Opacity, C2_Style, C2_Thickness, 0, ResolveCustomStartBar(C2_StartDate));
			Add(list, C3_Enabled && C3_Price != 0, C3_Label, C3_Price, C3_Color, C3_Opacity, C3_Style, C3_Thickness, 0, ResolveCustomStartBar(C3_StartDate));
			Add(list, C4_Enabled && C4_Price != 0, C4_Label, C4_Price, C4_Color, C4_Opacity, C4_Style, C4_Thickness, 0, ResolveCustomStartBar(C4_StartDate));
			Add(list, C5_Enabled && C5_Price != 0, C5_Label, C5_Price, C5_Color, C5_Opacity, C5_Style, C5_Thickness, 0, ResolveCustomStartBar(C5_StartDate));
			Add(list, C6_Enabled && C6_Price != 0, C6_Label, C6_Price, C6_Color, C6_Opacity, C6_Style, C6_Thickness, 0, ResolveCustomStartBar(C6_StartDate));
			Add(list, C7_Enabled && C7_Price != 0, C7_Label, C7_Price, C7_Color, C7_Opacity, C7_Style, C7_Thickness, 0, ResolveCustomStartBar(C7_StartDate));
			Add(list, C8_Enabled && C8_Price != 0, C8_Label, C8_Price, C8_Color, C8_Opacity, C8_Style, C8_Thickness, 0, ResolveCustomStartBar(C8_StartDate));

			return list;
		}

		// StartDate unset (still the MinDate sentinel) -> leftmost visible bar (old
		// behavior). Otherwise resolve to the bar index at/after that calendar date;
		// Bars.GetBar(-1) (date before all loaded history, or not found) -> also falls
		// back to leftmost visible rather than hiding the level entirely.
		private int ResolveCustomStartBar(DateTime startDate)
		{
			if (startDate <= Core.Globals.MinDate) return ChartBars.FromIndex;
			int idx = Bars.GetBar(startDate);
			return idx >= 0 ? idx : ChartBars.FromIndex;
		}

		private static void Add(List<LevelDef> list, bool enabled, string label, double price,
			WMBrush brush, int opacity, LevelLineStyle style, int thickness, int col, int startBarIdx, int endBarIdx = -1)
		{
			var scb = brush as WMSolidColorBrush;
			list.Add(new LevelDef
			{
				enabled = enabled, label = label, price = price,
				color = scb != null ? scb.Color : Colors.Gray,
				opacity = opacity, style = style, thickness = thickness, col = col, startBarIdx = startBarIdx, endBarIdx = endBarIdx
			});
		}

		// Collapse levels that sit at the SAME price (within half a tick) into a single line +
		// one combined label ("OoD RTH / OoW RTH / OoM RTH"), instead of stacking identical lines
		// with overlapping labels (e.g. OoW=OoD=OoM on the first ETH session of a month, or
		// OoW ETH=OoD ETH each week). The first level in build order keeps its line style/color;
		// the merged line spans the union (earliest start, longest right-extent). Price is appended
		// once at render time, so labels here stay price-free.
		private List<LevelDef> MergeSamePrice(List<LevelDef> src)
		{
			var outp = new List<LevelDef>();
			foreach (LevelDef d in src)
			{
				if (!d.enabled || double.IsNaN(d.price) || d.startBarIdx < 0) continue;   // render-invalid anyway
				int gi = -1;
				for (int k = 0; k < outp.Count; k++)
					if (Math.Abs(outp[k].price - d.price) < TickSize * 0.5) { gi = k; break; }
				if (gi < 0) { outp.Add(d); continue; }

				LevelDef g = outp[gi];   // struct copy — mutate then write back
				if (!string.IsNullOrEmpty(d.label) && (g.label == null || !LabelAlreadyIn(g.label, d.label)))
					g.label = string.IsNullOrEmpty(g.label) ? d.label : g.label + " / " + d.label;
				if (d.startBarIdx < g.startBarIdx) g.startBarIdx = d.startBarIdx;
				if (g.endBarIdx < 0 || d.endBarIdx < 0) g.endBarIdx = -1;          // either extends to the edge -> keep longest
				else if (d.endBarIdx > g.endBarIdx)     g.endBarIdx = d.endBarIdx;
				outp[gi] = g;
			}
			return outp;
		}

		// True if `piece` is already one of the " / "-separated parts of `combined`.
		private static bool LabelAlreadyIn(string combined, string piece)
		{
			foreach (string part in combined.Split(new[] { " / " }, StringSplitOptions.None))
				if (part == piece) return true;
			return false;
		}

		// Dependency-free dashing (no Direct2D1 StrokeStyle/Factory needed) — segments the
		// line into on/off chunks left-to-right across the panel.
		private void DrawStyledLine(float xL, float xR, float y, SharpDX.Direct2D1.Brush br, float thickness, LevelLineStyle style)
		{
			if (style == LevelLineStyle.Solid)
			{
				RenderTarget.DrawLine(new Vector2(xL, y), new Vector2(xR, y), br, thickness);
				return;
			}
			float[] pattern = style == LevelLineStyle.Dot      ? new float[] { 2f, 4f }
							: style == LevelLineStyle.DashDot   ? new float[] { 8f, 4f, 2f, 4f }
							:                                      new float[] { 8f, 5f };   // Dash
			float x = xL;
			int pi = 0;
			while (x < xR)
			{
				float seg = Math.Min(pattern[pi % pattern.Length], xR - x);
				if (pi % 2 == 0) RenderTarget.DrawLine(new Vector2(x, y), new Vector2(x + seg, y), br, thickness);
				x += seg;
				pi++;
			}
		}

		private class LabelInfo { public float y; public float trueY; public string text; public D2DSolidColorBrush brush; public int col; public bool inline; public float xInline; }

		// Two columns (RTH / ETH), anchored just past where the lines end (the current
		// bar), de-collided top-to-bottom with leader lines when a label had to be
		// nudged off its true price — same pattern as WyckoffVPLevels.
		private void DrawLabels(List<LabelInfo> labels, float baseX)
		{
			if (labels.Count == 0) return;
			float colW = LabelFontSize * 6.5f;
			float drawW = LabelFontSize * 18f;   // wide draw rect so "label price" never wraps to a 2nd line
			float gap  = LabelFontSize + 4f;
			float textH = LabelFontSize + 6f;
			TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
			tf.WordWrapping = WordWrapping.NoWrap;   // keep label + price on ONE line (right of the label, not below)

			// Inline labels (capped lines, e.g. OoD RTH) sit at the line's end, centered on it.
			foreach (LabelInfo li in labels)
				if (li.inline)
					RenderTarget.DrawText(li.text, tf, new RectangleF(li.xInline, li.trueY - textH / 2f, drawW, textH), li.brush);

			for (int c = 0; c <= 2; c++)   // 0=RTH, 1=ETH, 2=Custom (right-edge columns)
			{
				var col = new List<LabelInfo>();
				foreach (LabelInfo li in labels) if (!li.inline && li.col == c) col.Add(li);
				if (col.Count == 0) continue;
				col.Sort(delegate (LabelInfo a, LabelInfo b) { return a.y.CompareTo(b.y); });
				for (int i = 1; i < col.Count; i++)
					if (col[i].y < col[i - 1].y + gap) col[i].y = col[i - 1].y + gap;
				float x = baseX + c * colW;
				foreach (LabelInfo li in col)
				{
					if (Math.Abs(li.y - li.trueY) > 1.5f)
						RenderTarget.DrawLine(new Vector2(x - 6f, li.trueY), new Vector2(x - 1f, li.y), li.brush, 0.6f);
					// Vertically CENTER the text on the line's y; wide rect + NoWrap keeps the price on the same line.
					RenderTarget.DrawText(li.text, tf, new RectangleF(x, li.y - textH / 2f, drawW, textH), li.brush);
				}
			}
			tf.Dispose();
		}

		private static string F(double p) { return p.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture); }

		// ══════════════════════ Chart Trader panel ══════════════════════
		private void CreateWPFControls()
		{
			if (ctPanelActive) return;
			try
			{
				var win = Window.GetWindow(ChartControl.Parent) as NinjaTrader.Gui.Chart.Chart;
				if (win == null) { Print("SessionSRLevelsV10: chart window not found"); return; }
				var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
				if (chartTrader == null) { Print("SessionSRLevelsV10: ChartTrader not found (is Chart Trader shown?)"); return; }
				var outerGrid = chartTrader.Content as Grid;
				if (outerGrid == null) return;
				_ctGrid = null;
				foreach (UIElement child in outerGrid.Children)
				{
					Grid g = child as Grid;
					if (g != null) { _ctGrid = g; break; }
				}
				if (_ctGrid == null) { Print("SessionSRLevelsV10: button grid not found"); return; }

				CtShared sh;
				if (!_ctByGrid.TryGetValue(_ctGrid, out sh))
				{
					sh = BuildPanel(_ctGrid);   // ONE button set for the whole window, created once
					_ctByGrid[_ctGrid] = sh;
				}
				sh.refs++;
				ShowPanel(sh, true);

				// This chart becomes the active target; sync the buttons to its state.
				sh.active = this;
				RefreshPanelColors(sh, this);

				// Re-target to whichever chart the mouse is over (tab switch within one window).
				_ctEnter = (o, e) =>
				{
					CtShared ss;
					if (_ctGrid != null && _ctByGrid.TryGetValue(_ctGrid, out ss)) { ss.active = this; RefreshPanelColors(ss, this); }
				};
				ChartControl.MouseEnter += _ctEnter;

				ctPanelActive = true;
			}
			catch (Exception ex) { Print("SessionSRLevelsV10 CreateWPFControls: " + ex.Message); }
		}

		// Build the shared button set once per grid. Clicks route to sh.active (the chart whose
		// tab is currently active), toggle ITS state, recolor the button, and invalidate ITS chart.
		private CtShared BuildPanel(Grid grid)
		{
			Style s = Application.Current.TryFindResource("Button") as Style;
			var sh = new CtShared();

			sh.rth = MakeBtn(s, "RTH LEVELS", "Toggle RTH session levels (active chart)", CtOff);
			sh.rth.Click += (o, e) => { var a = sh.active; if (a == null) return; a._rthVisible = !a._rthVisible; sh.rth.Background = new WMSolidColorBrush(a._rthVisible ? CtOn : CtOff); if (a.ChartControl != null) a.ChartControl.InvalidateVisual(); };

			sh.eth = MakeBtn(s, "ETH LEVELS", "Toggle ETH session levels (active chart)", CtOff);
			sh.eth.Click += (o, e) => { var a = sh.active; if (a == null) return; a._ethVisible = !a._ethVisible; sh.eth.Background = new WMSolidColorBrush(a._ethVisible ? CtOn : CtOff); if (a.ChartControl != null) a.ChartControl.InvalidateVisual(); };

			sh.labels = MakeBtn(s, "LABELS", "Toggle level labels (active chart)", CtOff);
			sh.labels.Click += (o, e) => { var a = sh.active; if (a == null) return; a._labelsVisible = !a._labelsVisible; sh.labels.Background = new WMSolidColorBrush(a._labelsVisible ? CtOn : CtOff); if (a.ChartControl != null) a.ChartControl.InvalidateVisual(); };

			sh.price = MakeBtn(s, "PRICE", "Toggle the price in labels (active chart)", CtOff);
			sh.price.Click += (o, e) => { var a = sh.active; if (a == null) return; if (!a._priceVisibleSet) { a._priceVisible = a.ShowPriceInLabel; a._priceVisibleSet = true; } a._priceVisible = !a._priceVisible; sh.price.Background = new WMSolidColorBrush(a._priceVisible ? CtOn : CtOff); if (a.ChartControl != null) a.ChartControl.InvalidateVisual(); };

			int baseRow = grid.RowDefinitions.Count;
			sh.rd1 = new RowDefinition() { Height = new GridLength(36) }; grid.RowDefinitions.Add(sh.rd1);
			sh.row1 = MakeHalfRow(sh.rth, sh.eth); Grid.SetRow(sh.row1, baseRow); Grid.SetColumn(sh.row1, 0); Grid.SetColumnSpan(sh.row1, 3); grid.Children.Add(sh.row1);
			sh.rd2 = new RowDefinition() { Height = new GridLength(36) }; grid.RowDefinitions.Add(sh.rd2);
			sh.row2 = MakeHalfRow(sh.labels, sh.price); Grid.SetRow(sh.row2, baseRow + 1); Grid.SetColumn(sh.row2, 0); Grid.SetColumnSpan(sh.row2, 3); grid.Children.Add(sh.row2);
			return sh;
		}

		private static Grid MakeHalfRow(Button left, Button right)
		{
			var g = new Grid() { Margin = new Thickness(0) };
			g.ColumnDefinitions.Add(new ColumnDefinition());
			g.ColumnDefinitions.Add(new ColumnDefinition());
			Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
			g.Children.Add(left); g.Children.Add(right);
			return g;
		}

		private void RefreshPanelColors(CtShared sh, SessionSRLevelsV10 inst)
		{
			if (sh == null || inst == null) return;
			if (!inst._priceVisibleSet) { inst._priceVisible = inst.ShowPriceInLabel; inst._priceVisibleSet = true; }
			sh.rth.Background    = new WMSolidColorBrush(inst._rthVisible    ? CtOn : CtOff);
			sh.eth.Background    = new WMSolidColorBrush(inst._ethVisible    ? CtOn : CtOff);
			sh.labels.Background = new WMSolidColorBrush(inst._labelsVisible ? CtOn : CtOff);
			sh.price.Background  = new WMSolidColorBrush(inst._priceVisible  ? CtOn : CtOff);
		}

		private static void ShowPanel(CtShared sh, bool vis)
		{
			var h = vis ? new GridLength(36) : new GridLength(0);
			if (sh.rd1 != null) sh.rd1.Height = h;
			if (sh.rd2 != null) sh.rd2.Height = h;
			if (sh.row1 != null) sh.row1.Visibility = vis ? Visibility.Visible : Visibility.Collapsed;
			if (sh.row2 != null) sh.row2.Visibility = vis ? Visibility.Visible : Visibility.Collapsed;
		}

		private void DisposeWPFControls()
		{
			try
			{
				if (!ctPanelActive) return;
				try { if (_ctEnter != null && ChartControl != null) ChartControl.MouseEnter -= _ctEnter; } catch { }
				_ctEnter = null;

				CtShared sh;
				if (_ctGrid != null && _ctByGrid.TryGetValue(_ctGrid, out sh))
				{
					if (sh.active == this) sh.active = null;   // leave the buttons; another tab may still own them
					sh.refs--;
					if (sh.refs <= 0) ShowPanel(sh, false);    // last one gone -> hide the rows (no index surgery)
				}
				ctPanelActive = false;
			}
			catch (Exception ex) { Print("SessionSRLevelsV10 DisposeWPFControls: " + ex.Message); }
		}

		private Button MakeBtn(Style s, string label, string tip, WMColor bg)
		{
			return new Button() { Content = label, Style = s, Height = 34, Margin = new Thickness(1),
				FontSize = 11, FontWeight = FontWeights.Bold, ToolTip = tip,
				Background = new WMSolidColorBrush(bg), Foreground = Brushes.White };
		}

		private void SetBtn(Button btn, WMColor bg)
		{
			if (btn == null || ChartControl == null) return;
			ChartControl.Dispatcher.InvokeAsync((Action)(() => { if (btn != null) btn.Background = new WMSolidColorBrush(bg); }));
		}

		private void AddHalfRow(Grid grid, int row, Button left, Button right)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
			var g = new Grid() { Margin = new Thickness(0) };
			g.ColumnDefinitions.Add(new ColumnDefinition());
			g.ColumnDefinitions.Add(new ColumnDefinition());
			Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
			g.Children.Add(left); g.Children.Add(right);
			Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
			grid.Children.Add(g);
		}

		private void AddFullRow(Grid grid, int row, Button btn)
		{
			grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
			Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
			grid.Children.Add(btn);
		}

		#region Properties

		[Display(Name = "RTH template name", Order = 0, GroupName = "00 Session Templates",
			Description = "NT8 Trading Hours template used for the RTH window (begin/end + holidays/half-days).")]
		public string RthTemplateName { get; set; }

		[Display(Name = "Expected chart template (informational)", Order = 1, GroupName = "00 Session Templates",
			Description = "Just a sanity check: Print()s a warning at DataLoaded if the chart's own Trading Hours template name differs (expects the 23h Globex template so ETH bars actually exist).")]
		public string FullTemplateNameHint { get; set; }

		[Display(Name = "ETH levels from THIS chart (ETH/Globex charts)", Order = 2, GroupName = "00 Session Templates", Description = "ON (default): compute ETH overnight H/L + ETH opens + ETH close from this chart's own bars — exact tick match, and NO hidden 5-min ETH feed (much lighter). Use ON for an ETH/Globex chart with overnight bars; turn OFF on an RTH-only chart to fall back to the hidden ETH feed.")]
		public bool EthFromPrimary { get; set; }

		[Display(Name = "Debug log (writes Documents\\sessionsrlevels_debug_<instrument>.csv)", Order = 3, GroupName = "00 Session Templates",
			Description = "Investigative only: logs the Daily-chart date/bar resolution and HOY/LOY/COY source values every time the hidden RTH series rolls to a new session.")]
		public bool DebugLog { get; set; }

		[Range(6, 24)]
		[Display(Name = "Label font size", Order = 2, GroupName = "01 Display")]
		public int LabelFontSize { get; set; }

		[Display(Name = "Show price in label", Order = 3, GroupName = "01 Display",
			Description = "Off = just the label text (e.g. \"COY RTH\"), no price value appended.")]
		public bool ShowPriceInLabel { get; set; }

		[Range(0, 500)]
		[Display(Name = "Extend lines right (bars)", Order = 4, GroupName = "01 Display",
			Description = "How many bars past the current bar the lines/labels are drawn out to.")]
		public int ExtendBarsRight { get; set; }

		// ---- Historical levels (each level has its own show-historically checkbox) ----
		[Range(0, 60)]
		[Display(Name = "Historical sessions (0 = off)", Order = 0, GroupName = "22 Historical",
			Description = "Draw the last N completed sessions' levels as confined per-day segments (Model A). 0 = off.")]
		public int HistSessions { get; set; }
		[Range(10, 100)]
		[Display(Name = "Opacity %", Order = 1, GroupName = "22 Historical",
			Description = "Dim factor for historical level lines + labels.")]
		public int HistOpacity { get; set; }
		[Display(Name = "RTH HOY (prior high)", Order = 2, GroupName = "22 Historical")] public bool Hist_HOY { get; set; }
		[Display(Name = "RTH LOY (prior low)", Order = 3, GroupName = "22 Historical")] public bool Hist_LOY { get; set; }
		[Display(Name = "RTH COY (prior close)", Order = 4, GroupName = "22 Historical")] public bool Hist_COY { get; set; }
		[Display(Name = "RTH OoD (open of day)", Order = 5, GroupName = "22 Historical")] public bool Hist_OoD { get; set; }
		[Display(Name = "RTH OoW (open of week)", Order = 6, GroupName = "22 Historical")] public bool Hist_OoW { get; set; }
		[Display(Name = "RTH OoM (open of month)", Order = 7, GroupName = "22 Historical")] public bool Hist_OoM { get; set; }
		[Display(Name = "ETH H (overnight high)", Order = 8, GroupName = "22 Historical")] public bool Hist_EthH { get; set; }
		[Display(Name = "ETH L (overnight low)", Order = 9, GroupName = "22 Historical")] public bool Hist_EthL { get; set; }
			[Display(Name = "Settlement (Daily ETH close)", Order = 14, GroupName = "22 Historical")] public bool Hist_Settle { get; set; }
		[Display(Name = "1D Max (VIX)", Order = 10, GroupName = "22 Historical")] public bool Hist_EMV_Max { get; set; }
		[Display(Name = "1D Min (VIX)", Order = 11, GroupName = "22 Historical")] public bool Hist_EMV_Min { get; set; }
		[Display(Name = "1D Max (GEX)", Order = 12, GroupName = "22 Historical")] public bool Hist_EMG_Max { get; set; }
		[Display(Name = "1D Min (GEX)", Order = 13, GroupName = "22 Historical")] public bool Hist_EMG_Min { get; set; }

		// ---- Current Day High ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01A Current Day - High")] public bool CDH_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01A Current Day - High")] public string CDH_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01A Current Day - High")] public WMBrush CDH_Color { get; set; }
		[Browsable(false)] public string CDH_ColorSerialize { get { return Serialize.BrushToString(CDH_Color); } set { CDH_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01A Current Day - High")] public int CDH_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01A Current Day - High")] public LevelLineStyle CDH_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01A Current Day - High")] public int CDH_Thickness { get; set; }

		// ---- Current Day Low ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01B Current Day - Low")] public bool CDL_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01B Current Day - Low")] public string CDL_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01B Current Day - Low")] public WMBrush CDL_Color { get; set; }
		[Browsable(false)] public string CDL_ColorSerialize { get { return Serialize.BrushToString(CDL_Color); } set { CDL_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01B Current Day - Low")] public int CDL_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01B Current Day - Low")] public LevelLineStyle CDL_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01B Current Day - Low")] public int CDL_Thickness { get; set; }

		// ---- Expected Move (settings) ----
		[Display(Name = "VIX CSV path", Order = 0, GroupName = "01C Expected Move (settings)", Description = "File the VIX-method reads the latest close from.")] public string VixCsvPath { get; set; }
		[Display(Name = "gexlog raw dir", Order = 1, GroupName = "01C Expected Move (settings)", Description = "Folder with the dated gexlog brief JSON files (reads {date}_morning, else {date-1}_evening).")] public string GexlogRawDir { get; set; }
		[Display(Name = "Manual VIX (0 = auto)", Order = 2, GroupName = "01C Expected Move (settings)", Description = "Override the VIX used by the VIX-method; 0 = read latest close from the CSV.")] public double EmManualVix { get; set; }
		[Range(0.1, 5.0)] [Display(Name = "Sigma multiplier", Order = 3, GroupName = "01C Expected Move (settings)", Description = "1.0 = ~68% band; 2.0 = ~95%. Applies to the VIX method.")] public double EmSigma { get; set; }

		// ---- 1D Max (VIX) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01D 1D Max (VIX formula)")] public bool EMV_Max_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01D 1D Max (VIX formula)")] public string EMV_Max_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01D 1D Max (VIX formula)")] public WMBrush EMV_Max_Color { get; set; }
		[Browsable(false)] public string EMV_Max_ColorSerialize { get { return Serialize.BrushToString(EMV_Max_Color); } set { EMV_Max_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01D 1D Max (VIX formula)")] public int EMV_Max_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01D 1D Max (VIX formula)")] public LevelLineStyle EMV_Max_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01D 1D Max (VIX formula)")] public int EMV_Max_Thickness { get; set; }

		// ---- 1D Min (VIX) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01E 1D Min (VIX formula)")] public bool EMV_Min_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01E 1D Min (VIX formula)")] public string EMV_Min_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01E 1D Min (VIX formula)")] public WMBrush EMV_Min_Color { get; set; }
		[Browsable(false)] public string EMV_Min_ColorSerialize { get { return Serialize.BrushToString(EMV_Min_Color); } set { EMV_Min_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01E 1D Min (VIX formula)")] public int EMV_Min_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01E 1D Min (VIX formula)")] public LevelLineStyle EMV_Min_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01E 1D Min (VIX formula)")] public int EMV_Min_Thickness { get; set; }

		// ---- 1D Max (gexlog) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01F 1D Max (gexlog brief)")] public bool EMG_Max_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01F 1D Max (gexlog brief)")] public string EMG_Max_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01F 1D Max (gexlog brief)")] public WMBrush EMG_Max_Color { get; set; }
		[Browsable(false)] public string EMG_Max_ColorSerialize { get { return Serialize.BrushToString(EMG_Max_Color); } set { EMG_Max_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01F 1D Max (gexlog brief)")] public int EMG_Max_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01F 1D Max (gexlog brief)")] public LevelLineStyle EMG_Max_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01F 1D Max (gexlog brief)")] public int EMG_Max_Thickness { get; set; }

		// ---- 1D Min (gexlog) ----
		[Display(Name = "Enabled", Order = 0, GroupName = "01G 1D Min (gexlog brief)")] public bool EMG_Min_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "01G 1D Min (gexlog brief)")] public string EMG_Min_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "01G 1D Min (gexlog brief)")] public WMBrush EMG_Min_Color { get; set; }
		[Browsable(false)] public string EMG_Min_ColorSerialize { get { return Serialize.BrushToString(EMG_Min_Color); } set { EMG_Min_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "01G 1D Min (gexlog brief)")] public int EMG_Min_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "01G 1D Min (gexlog brief)")] public LevelLineStyle EMG_Min_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "01G 1D Min (gexlog brief)")] public int EMG_Min_Thickness { get; set; }

		// ---- RTH HOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "02 RTH - HOY (prior RTH high)")] public bool RHOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "02 RTH - HOY (prior RTH high)")] public string RHOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "02 RTH - HOY (prior RTH high)")] public WMBrush RHOY_Color { get; set; }
		[Browsable(false)] public string RHOY_ColorSerialize { get { return Serialize.BrushToString(RHOY_Color); } set { RHOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "02 RTH - HOY (prior RTH high)")] public int RHOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "02 RTH - HOY (prior RTH high)")] public LevelLineStyle RHOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "02 RTH - HOY (prior RTH high)")] public int RHOY_Thickness { get; set; }

		// ---- RTH LOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "03 RTH - LOY (prior RTH low)")] public bool RLOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "03 RTH - LOY (prior RTH low)")] public string RLOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "03 RTH - LOY (prior RTH low)")] public WMBrush RLOY_Color { get; set; }
		[Browsable(false)] public string RLOY_ColorSerialize { get { return Serialize.BrushToString(RLOY_Color); } set { RLOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "03 RTH - LOY (prior RTH low)")] public int RLOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "03 RTH - LOY (prior RTH low)")] public LevelLineStyle RLOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "03 RTH - LOY (prior RTH low)")] public int RLOY_Thickness { get; set; }

		// ---- RTH COY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "04 RTH - COY (prior RTH close)")] public bool RCOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "04 RTH - COY (prior RTH close)")] public string RCOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "04 RTH - COY (prior RTH close)")] public WMBrush RCOY_Color { get; set; }
		[Browsable(false)] public string RCOY_ColorSerialize { get { return Serialize.BrushToString(RCOY_Color); } set { RCOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "04 RTH - COY (prior RTH close)")] public int RCOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "04 RTH - COY (prior RTH close)")] public LevelLineStyle RCOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "04 RTH - COY (prior RTH close)")] public int RCOY_Thickness { get; set; }

		// ---- RTH OoD ----
		[Display(Name = "Enabled", Order = 0, GroupName = "05 RTH - OoD (open of day)")] public bool ROoD_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "05 RTH - OoD (open of day)")] public string ROoD_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "05 RTH - OoD (open of day)")] public WMBrush ROoD_Color { get; set; }
		[Browsable(false)] public string ROoD_ColorSerialize { get { return Serialize.BrushToString(ROoD_Color); } set { ROoD_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "05 RTH - OoD (open of day)")] public int ROoD_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "05 RTH - OoD (open of day)")] public LevelLineStyle ROoD_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "05 RTH - OoD (open of day)")] public int ROoD_Thickness { get; set; }

		// ---- RTH OoW ----
		[Display(Name = "Enabled", Order = 0, GroupName = "06 RTH - OoW (open of week)")] public bool ROoW_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "06 RTH - OoW (open of week)")] public string ROoW_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "06 RTH - OoW (open of week)")] public WMBrush ROoW_Color { get; set; }
		[Browsable(false)] public string ROoW_ColorSerialize { get { return Serialize.BrushToString(ROoW_Color); } set { ROoW_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "06 RTH - OoW (open of week)")] public int ROoW_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "06 RTH - OoW (open of week)")] public LevelLineStyle ROoW_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "06 RTH - OoW (open of week)")] public int ROoW_Thickness { get; set; }

		// ---- RTH OoM ----
		[Display(Name = "Enabled", Order = 0, GroupName = "07 RTH - OoM (open of month)")] public bool ROoM_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "07 RTH - OoM (open of month)")] public string ROoM_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "07 RTH - OoM (open of month)")] public WMBrush ROoM_Color { get; set; }
		[Browsable(false)] public string ROoM_ColorSerialize { get { return Serialize.BrushToString(ROoM_Color); } set { ROoM_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "07 RTH - OoM (open of month)")] public int ROoM_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "07 RTH - OoM (open of month)")] public LevelLineStyle ROoM_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "07 RTH - OoM (open of month)")] public int ROoM_Thickness { get; set; }
		[Display(Name = "Manual price (0 = auto)", Order = 6, GroupName = "07 RTH - OoM (open of month)", Description = "Type the RTH open-of-month price here to avoid loading a month of data. Used only when the month below matches the current month.")] public double ROoM_ManualPrice { get; set; }
		[Display(Name = "Manual month (pick any date in it)", Order = 7, GroupName = "07 RTH - OoM (open of month)", Description = "Which month the manual price above is for. The manual price shows only while this month is the current month.")] public DateTime ROoM_ManualMonth { get; set; }

		// ---- ETH HOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "08 ETH - H (current ETH high)")] public bool EHOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "08 ETH - H (current ETH high)")] public string EHOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "08 ETH - H (current ETH high)")] public WMBrush EHOY_Color { get; set; }
		[Browsable(false)] public string EHOY_ColorSerialize { get { return Serialize.BrushToString(EHOY_Color); } set { EHOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "08 ETH - H (current ETH high)")] public int EHOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "08 ETH - H (current ETH high)")] public LevelLineStyle EHOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "08 ETH - H (current ETH high)")] public int EHOY_Thickness { get; set; }

		// ---- ETH LOY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "09 ETH - L (current ETH low)")] public bool ELOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "09 ETH - L (current ETH low)")] public string ELOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "09 ETH - L (current ETH low)")] public WMBrush ELOY_Color { get; set; }
		[Browsable(false)] public string ELOY_ColorSerialize { get { return Serialize.BrushToString(ELOY_Color); } set { ELOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "09 ETH - L (current ETH low)")] public int ELOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "09 ETH - L (current ETH low)")] public LevelLineStyle ELOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "09 ETH - L (current ETH low)")] public int ELOY_Thickness { get; set; }

		// ---- ETH COY ----
		[Display(Name = "Enabled", Order = 0, GroupName = "10 ETH - COY (prior ETH-only close)")] public bool ECOY_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "10 ETH - COY (prior ETH-only close)")] public string ECOY_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "10 ETH - COY (prior ETH-only close)")] public WMBrush ECOY_Color { get; set; }
		[Browsable(false)] public string ECOY_ColorSerialize { get { return Serialize.BrushToString(ECOY_Color); } set { ECOY_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "10 ETH - COY (prior ETH-only close)")] public int ECOY_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "10 ETH - COY (prior ETH-only close)")] public LevelLineStyle ECOY_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "10 ETH - COY (prior ETH-only close)")] public int ECOY_Thickness { get; set; }

			// ---- Settlement (close of the Daily ETH chart = prior ETH-session close) ----
			[Display(Name = "Enabled", Order = 0, GroupName = "10b Settlement (Daily ETH close)")] public bool Settle_Enabled { get; set; }
			[Display(Name = "Label", Order = 1, GroupName = "10b Settlement (Daily ETH close)")] public string Settle_Label { get; set; }
			[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "10b Settlement (Daily ETH close)")] public WMBrush Settle_Color { get; set; }
			[Browsable(false)] public string Settle_ColorSerialize { get { return Serialize.BrushToString(Settle_Color); } set { Settle_Color = Serialize.StringToBrush(value); } }
			[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "10b Settlement (Daily ETH close)")] public int Settle_Opacity { get; set; }
			[Display(Name = "Line style", Order = 4, GroupName = "10b Settlement (Daily ETH close)")] public LevelLineStyle Settle_Style { get; set; }
			[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "10b Settlement (Daily ETH close)")] public int Settle_Thickness { get; set; }

		// ---- ETH OoD ----
		[Display(Name = "Enabled", Order = 0, GroupName = "11 ETH - OoD (open of day / evening open)")] public bool EOoD_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "11 ETH - OoD (open of day / evening open)")] public string EOoD_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "11 ETH - OoD (open of day / evening open)")] public WMBrush EOoD_Color { get; set; }
		[Browsable(false)] public string EOoD_ColorSerialize { get { return Serialize.BrushToString(EOoD_Color); } set { EOoD_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "11 ETH - OoD (open of day / evening open)")] public int EOoD_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "11 ETH - OoD (open of day / evening open)")] public LevelLineStyle EOoD_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "11 ETH - OoD (open of day / evening open)")] public int EOoD_Thickness { get; set; }

		// ---- ETH OoW ----
		[Display(Name = "Enabled", Order = 0, GroupName = "12 ETH - OoW (open of week)")] public bool EOoW_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "12 ETH - OoW (open of week)")] public string EOoW_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "12 ETH - OoW (open of week)")] public WMBrush EOoW_Color { get; set; }
		[Browsable(false)] public string EOoW_ColorSerialize { get { return Serialize.BrushToString(EOoW_Color); } set { EOoW_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "12 ETH - OoW (open of week)")] public int EOoW_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "12 ETH - OoW (open of week)")] public LevelLineStyle EOoW_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "12 ETH - OoW (open of week)")] public int EOoW_Thickness { get; set; }

		// ---- ETH OoM ----
		[Display(Name = "Enabled", Order = 0, GroupName = "13 ETH - OoM (open of month)")] public bool EOoM_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "13 ETH - OoM (open of month)")] public string EOoM_Label { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 2, GroupName = "13 ETH - OoM (open of month)")] public WMBrush EOoM_Color { get; set; }
		[Browsable(false)] public string EOoM_ColorSerialize { get { return Serialize.BrushToString(EOoM_Color); } set { EOoM_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 3, GroupName = "13 ETH - OoM (open of month)")] public int EOoM_Opacity { get; set; }
		[Display(Name = "Line style", Order = 4, GroupName = "13 ETH - OoM (open of month)")] public LevelLineStyle EOoM_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 5, GroupName = "13 ETH - OoM (open of month)")] public int EOoM_Thickness { get; set; }
		[Display(Name = "Manual price (0 = auto)", Order = 6, GroupName = "13 ETH - OoM (open of month)", Description = "Type the ETH open-of-month price here to avoid loading a month of data. Used only when the month below matches the current month.")] public double EOoM_ManualPrice { get; set; }
		[Display(Name = "Manual month (pick any date in it)", Order = 7, GroupName = "13 ETH - OoM (open of month)", Description = "Which month the manual price above is for. The manual price shows only while this month is the current month.")] public DateTime EOoM_ManualMonth { get; set; }

		// ---- Custom 1 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "14 Custom 1")] public bool C1_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "14 Custom 1")] public string C1_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "14 Custom 1")] public double C1_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "14 Custom 1")] public WMBrush C1_Color { get; set; }
		[Browsable(false)] public string C1_ColorSerialize { get { return Serialize.BrushToString(C1_Color); } set { C1_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "14 Custom 1")] public int C1_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "14 Custom 1")] public LevelLineStyle C1_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "14 Custom 1")] public int C1_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "14 Custom 1")] public DateTime C1_StartDate { get; set; }

		// ---- Custom 2 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "15 Custom 2")] public bool C2_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "15 Custom 2")] public string C2_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "15 Custom 2")] public double C2_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "15 Custom 2")] public WMBrush C2_Color { get; set; }
		[Browsable(false)] public string C2_ColorSerialize { get { return Serialize.BrushToString(C2_Color); } set { C2_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "15 Custom 2")] public int C2_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "15 Custom 2")] public LevelLineStyle C2_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "15 Custom 2")] public int C2_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "15 Custom 2")] public DateTime C2_StartDate { get; set; }

		// ---- Custom 3 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "16 Custom 3")] public bool C3_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "16 Custom 3")] public string C3_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "16 Custom 3")] public double C3_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "16 Custom 3")] public WMBrush C3_Color { get; set; }
		[Browsable(false)] public string C3_ColorSerialize { get { return Serialize.BrushToString(C3_Color); } set { C3_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "16 Custom 3")] public int C3_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "16 Custom 3")] public LevelLineStyle C3_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "16 Custom 3")] public int C3_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "16 Custom 3")] public DateTime C3_StartDate { get; set; }

		// ---- Custom 4 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "17 Custom 4")] public bool C4_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "17 Custom 4")] public string C4_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "17 Custom 4")] public double C4_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "17 Custom 4")] public WMBrush C4_Color { get; set; }
		[Browsable(false)] public string C4_ColorSerialize { get { return Serialize.BrushToString(C4_Color); } set { C4_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "17 Custom 4")] public int C4_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "17 Custom 4")] public LevelLineStyle C4_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "17 Custom 4")] public int C4_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "17 Custom 4")] public DateTime C4_StartDate { get; set; }

		// ---- Custom 5 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "18 Custom 5")] public bool C5_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "18 Custom 5")] public string C5_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "18 Custom 5")] public double C5_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "18 Custom 5")] public WMBrush C5_Color { get; set; }
		[Browsable(false)] public string C5_ColorSerialize { get { return Serialize.BrushToString(C5_Color); } set { C5_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "18 Custom 5")] public int C5_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "18 Custom 5")] public LevelLineStyle C5_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "18 Custom 5")] public int C5_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "18 Custom 5")] public DateTime C5_StartDate { get; set; }

		// ---- Custom 6 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "19 Custom 6")] public bool C6_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "19 Custom 6")] public string C6_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "19 Custom 6")] public double C6_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "19 Custom 6")] public WMBrush C6_Color { get; set; }
		[Browsable(false)] public string C6_ColorSerialize { get { return Serialize.BrushToString(C6_Color); } set { C6_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "19 Custom 6")] public int C6_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "19 Custom 6")] public LevelLineStyle C6_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "19 Custom 6")] public int C6_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "19 Custom 6")] public DateTime C6_StartDate { get; set; }

		// ---- Custom 7 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "20 Custom 7")] public bool C7_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "20 Custom 7")] public string C7_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "20 Custom 7")] public double C7_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "20 Custom 7")] public WMBrush C7_Color { get; set; }
		[Browsable(false)] public string C7_ColorSerialize { get { return Serialize.BrushToString(C7_Color); } set { C7_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "20 Custom 7")] public int C7_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "20 Custom 7")] public LevelLineStyle C7_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "20 Custom 7")] public int C7_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "20 Custom 7")] public DateTime C7_StartDate { get; set; }

		// ---- Custom 8 ----
		[Display(Name = "Enabled", Order = 0, GroupName = "21 Custom 8")] public bool C8_Enabled { get; set; }
		[Display(Name = "Label", Order = 1, GroupName = "21 Custom 8")] public string C8_Label { get; set; }
		[Display(Name = "Price", Order = 2, GroupName = "21 Custom 8")] public double C8_Price { get; set; }
		[XmlIgnore] [Display(Name = "Color", Order = 3, GroupName = "21 Custom 8")] public WMBrush C8_Color { get; set; }
		[Browsable(false)] public string C8_ColorSerialize { get { return Serialize.BrushToString(C8_Color); } set { C8_Color = Serialize.StringToBrush(value); } }
		[Range(0, 100)] [Display(Name = "Opacity %", Order = 4, GroupName = "21 Custom 8")] public int C8_Opacity { get; set; }
		[Display(Name = "Line style", Order = 5, GroupName = "21 Custom 8")] public LevelLineStyle C8_Style { get; set; }
		[Range(1, 8)] [Display(Name = "Thickness", Order = 6, GroupName = "21 Custom 8")] public int C8_Thickness { get; set; }
		[Display(Name = "Start date (blank = leftmost visible bar)", Order = 7, GroupName = "21 Custom 8")] public DateTime C8_StartDate { get; set; }

		[Display(Name = "Show developing POC/VA", Order = 0, GroupName = "23 Volume Profile",
			Description = "OFF by default to conserve resources. ON: live per-tick price/volume binning (OnMarketData, real-time only) drives a developing POC + Value-Area for today and logs each day's final values on session close — data/vp_levels/session_vp_live_log.csv, which scripts/backfill_vp_log.py can also backfill from the recorded L1 tape for days before this was ever turned on live.")]
		public bool ShowDevPocVa { get; set; }

		[Range(0.5, 0.95)] [Display(Name = "Value area %", Order = 1, GroupName = "23 Volume Profile",
			Description = "Fraction of the day's volume enclosed by VAH/VAL around the POC (standard = 0.70).")]
		public double VaPercent { get; set; }

		[Range(0, 70)] [Display(Name = "Historical VA sessions (0 = off)", Order = 2, GroupName = "23 Volume Profile",
			Description = "How many prior sessions' OWN POC/VA to draw, confined to each one's own bars. Shows the real bar-by-bar developing trail (session_vp_dev_trail.csv) when backfill_vp_log.py has built one for that day; falls back to a single end-of-day box (session_vp_live_log.csv) if only the final value was ever backfilled.")]
		public int VpHistSessions { get; set; }

		[XmlIgnore] [Display(Name = "POC color (this session)", Order = 3, GroupName = "23 Volume Profile")] public WMBrush PocColor { get; set; }
		[Browsable(false)] public string PocColorSerialize { get { return Serialize.BrushToString(PocColor); } set { PocColor = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "VA line color (today)", Order = 4, GroupName = "23 Volume Profile")] public WMBrush VaColor { get; set; }
		[Browsable(false)] public string VaColorSerialize { get { return Serialize.BrushToString(VaColor); } set { VaColor = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "VA box color (historical, this session)", Order = 5, GroupName = "23 Volume Profile")] public WMBrush VaBoxColor { get; set; }
		[Browsable(false)] public string VaBoxColorSerialize { get { return Serialize.BrushToString(VaBoxColor); } set { VaBoxColor = Serialize.StringToBrush(value); } }

		[Display(Name = "Show prior session's VA projected forward", Order = 6, GroupName = "23 Volume Profile",
			Description = "ON by default. Draws the PRIOR completed session's final POC/VAH/VAL as a FILLED colored range (box) spanning the CURRENT/next session's own bars (today's still-developing bars, and each historical session shown by 'Historical VA sessions' above) — the classic 'yesterday's value area' read, separate from that session's own developing POC/VA trail.")]
		public bool ShowPriorVp { get; set; }

		[XmlIgnore] [Display(Name = "Prior-session POC color", Order = 7, GroupName = "23 Volume Profile")] public WMBrush PriorPocColor { get; set; }
		[Browsable(false)] public string PriorPocColorSerialize { get { return Serialize.BrushToString(PriorPocColor); } set { PriorPocColor = Serialize.StringToBrush(value); } }

		[XmlIgnore] [Display(Name = "Prior-session VA box color", Order = 8, GroupName = "23 Volume Profile")] public WMBrush PriorVaBoxColor { get; set; }
		[Browsable(false)] public string PriorVaBoxColorSerialize { get { return Serialize.BrushToString(PriorVaBoxColor); } set { PriorVaBoxColor = Serialize.StringToBrush(value); } }

		[Range(0, 100)] [Display(Name = "Prior-session VA box opacity %", Order = 9, GroupName = "23 Volume Profile",
			Description = "Fill opacity of the projected prior-session range. Kept low by default (box, not lines) so it reads as a zone behind price, not a lines obscuring it.")]
		public int PriorVpOpacity { get; set; }

		[Display(Name = "Show this session's developing POC/VA", Order = 10, GroupName = "23 Volume Profile",
			Description = "ON by default. A real OFF switch, independent of color/opacity: hides THIS session's own POC/VA display completely (today's live trail, and every historical day's reconstructed trail or box-fallback) — not just made transparent, drawn or not. Leaves the PRIOR-session projected range (ShowPriorVp, above) untouched either way.")]
		public bool ShowDevTrail { get; set; }

		[Range(0, 100)] [Display(Name = "POC opacity % (this session)", Order = 11, GroupName = "23 Volume Profile",
			Description = "Opacity of this session's own POC line (today's trail, historical trail, and the box-fallback's POC line). Previously hardcoded and did NOT respect any opacity setting — that was the bug behind 'transparent but still visible'.")]
		public int PocOpacity { get; set; }

		[Range(0, 100)] [Display(Name = "VA line opacity % (this session)", Order = 12, GroupName = "23 Volume Profile",
			Description = "Opacity of this session's own VAH/VAL lines (today's and historical trails). Previously hardcoded at 85% regardless of any setting.")]
		public int VaOpacity { get; set; }

		#endregion
	}
}
