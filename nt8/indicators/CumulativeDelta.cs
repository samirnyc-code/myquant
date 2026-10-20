// CumulativeDelta — CVD panel (cumulative volume delta) rendered as CANDLES, computed
// from ticks so it needs NO Order Flow+ license and matches our footprint pipeline's
// trade classification EXACTLY (same e.Bid/e.Ask embedded-quote rule as FootprintExporter).
//
// WHY: so Samir can eyeball CVD in NinjaTrader and mark price/CVD divergences on the
// chart, and what he sees == what we analyze offline (ES_bars delta / CVD).
//
// VIEW: per-bar CVD candle — Open = CVD at bar start, Close = CVD at bar end,
// High/Low = the intrabar cumulative-delta extremes. Candles (not a line) so CVD's own
// swing highs/lows are visible to compare against price swing highs/lows.
//
// REQUIRES TICK REPLAY for historical bars (right-click data series -> Tick Replay ON).
// Calculate = OnEachTick. Lives in a SEPARATE panel (IsOverlay = false).
//
// FILTERS (extensible — add more here later):
//   ResetMode   : Session (reset CVD each RTH session) | None (continuous)
//   LargeLotMin : 0 = count every trade; >0 = only count trades >= N contracts
//                 (large-lot / "smart money" filtered CVD — the mzVolumeDelta idea)
//
// DIVERGENCE (2026-10-18, S142+): LIVE, not confirmed-after-the-fact. A lightweight
// incremental swing tracker (ZigZag-style: a leg's running extreme becomes a CONFIRMED
// swing the moment price reverses by ReversalTicks — no symmetric look-ahead window,
// so a pivot is known as soon as it actually happens) tracks the last confirmed CVD
// swing high/low each session. On EVERY tick (OnBarUpdate fires per-tick under
// Calculate.OnEachTick, same as the CVD accumulation below), the instant price pushes
// past that last confirmed swing extreme (= "a new extreme from a previous pivot"),
// this checks whether CVD is failing to confirm it and — if so — starts drawing the
// connecting line immediately and keeps extending it bar by bar for as long as the
// push continues:
//   regular bearish (live): price > last confirmed swing high, CVD < CVD at that high
//   regular bullish (live): price < last confirmed swing low,  CVD > CVD at that low
// If CVD catches back up before the leg reverses, the in-progress line is removed (the
// condition stopped holding — matches LuxAlgo's own caveat that divergence is a
// condition, not a one-shot trigger). Once the leg actually reverses, whatever is on
// screen at that instant is left as a permanent historical mark and a fresh episode
// starts against the newly confirmed pivot.
//   hidden bearish/bullish (continuation, OFF by default): unlike the regular case
//   above, these compare two ALREADY-COMPLETED swings, so they're only evaluated once,
//   at the moment a new swing confirms — there's no live/growing form of hidden
//   divergence by definition.
// Drawn in TWO places from the same live state: the CVD-to-CVD connecting line is
// manual SharpDX drawing inside OnRender (same mechanism as the candles below, so it
// renders in this indicator's OWN panel); the price-to-price connecting line uses the
// NinjaScript Draw.Line/Draw.Text drawing-object API with DrawOnPricePanel=true, the
// documented way a sub-panel indicator places markers on the price panel without
// becoming an overlay itself — these two mechanisms are independent, so the same
// instance can target both panels simultaneously.
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.
//
// 2026-10-19 BACKFILL: a bar with no live tick data (accumBar != CurrentBar, i.e. OnMarketData
// never touched it) now reconstructs its own cvO/cvH/cvL/cvC candle from
// data/bid_ask/bid_ask_vol_buckets.csv (scripts/backfill_bid_ask_log.py, 1-second (ask_vol,
// bid_vol) buckets from the recorded L1 tape's own Aggr aggressor tag — same file the three
// BidAskVolume*.cs indicators read). Walking the buckets inside a bar's own (prevClose,
// thisClose] window and tracking the running cumulative's min/max along the way gives a REAL
// open/high/low/close reconstruction, not a flatlined "last known value" — the existing
// NaN-seed fallback below stays as the final safety net for days with no backfill at all. This
// also means the existing live divergence tracker (UpdateDivergence) now naturally works back
// through backfilled history too, since it just reads cvC[]/GetValueAt() same as always. NOT
// guaranteed byte-identical to the live embedded-quote+midpoint-tiebreak classification — Aggr
// is the tape's own independently-resolved aggressor tag, a very close but different method.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.My
{
    // CvdResetMode lives in BidAskSharedEnums.cs (namespace NinjaTrader.NinjaScript) — NOT
    // redeclared here, and deliberately NOT a second namespace block in THIS file either;
    // see that file's header for why (a real, confirmed NT8 wrapper-generation bug: a second
    // top-level namespace block in a file that ALSO contains an Indicator class breaks NT8's
    // "My." relative-prefix generation for that class's own convenience-constructor wrapper).
    public class CumulativeDelta : Indicator
    {
        private Series<double> cvO, cvH, cvL, cvC;   // per-bar CVD open/high/low/close
        // 1.0 = this bar got real live ticks (cvO/cvH/cvL/cvC are tick-accurate), 0.0 = it
        // was reconstructed from the L1-tape bucket backfill (or flatlined, if neither was
        // available) -- OnRender uses this to draw full candle detail only where it's
        // actually trustworthy; see OnRender's comment.
        private Series<double> cvLiveFlag;
        private double runCum;                        // running cumulative delta
        private int accumBar = -1;
        private double barOpen, barHi, barLo, barClose;
        private SharpDX.Direct2D1.Brush upBrush, dnBrush;

        // ---- live incremental swing/divergence tracking ----
        private enum SwingDir { Up, Down }
        private SwingDir dir = SwingDir.Up;
        private int legExtBar = -1; private double legExtPrice = double.NaN;
        private int sessionStartBar = -1;
        private int lastHighBar = -1; private double lastHighPrice = double.NaN, lastHighCvd = double.NaN;
        private int lastLowBar = -1;  private double lastLowPrice = double.NaN, lastLowCvd = double.NaN;
        private string bearTag, bullTag;   // non-null while a live episode is actively being drawn

        private struct DivMark { public int barA, barB; public double cvdA, cvdB; public bool bearish; }
        private List<DivMark> hist = new List<DivMark>();           // frozen, historical marks (CVD-panel side)
        private DivMark? liveMark;                                   // currently-growing mark, or null

        // ── L1-tape backfill for bars with no live tick data (2026-10-19) ──────────────
        private struct BidAskBucket { public DateTime ts; public double askVol, bidVol; }
        private const string BucketLogPath = @"C:\Users\Admin\myquant\data\bid_ask\bid_ask_vol_buckets.csv";
        private List<BidAskBucket> _buckets = new List<BidAskBucket>();
        private int _bucketCursor;
        private static List<BidAskBucket> _bucketsCache;
        private static DateTime _bucketsCacheFileTime = DateTime.MinValue;
        private TimeZoneInfo _ctTz;
        private DateTime _lastConsumedTs = DateTime.MinValue;
        private DateTime _lastBucketFileCheckUtc = DateTime.MinValue;

        private void LoadBidAskBuckets()
        {
            _buckets = new List<BidAskBucket>(); _bucketCursor = 0; _lastConsumedTs = DateTime.MinValue;
            try { _ctTz = TimeZoneInfo.FindSystemTimeZoneById("Central Standard Time"); }
            catch { _ctTz = null; }
            ReadBucketFile();
        }

        // 2026-10-20 FIX: see BidAskVolumeRatio.cs's ReadBucketFile for the full root-cause
        // note — this used to be a one-shot load at State.DataLoaded, so the cursor walked off
        // the end of a frozen snapshot and flatlined forever regardless of later backfill
        // refreshes. Now re-checked every AdvanceCvdBuckets, throttled to once per 30s, and
        // re-seeks the cursor by TIMESTAMP via ReseekCursor — this is what keeps a reload safe
        // for CVD specifically: `runCum` is never touched here, only which list/index the
        // cursor points into, so a reseek can never re-add an already-consumed bucket into the
        // running total.
        private void ReadBucketFile()
        {
            if (!File.Exists(BucketLogPath)) return;

            DateTime fileTime = File.GetLastWriteTimeUtc(BucketLogPath);
            if (_bucketsCache != null && fileTime == _bucketsCacheFileTime)
            {
                if (!ReferenceEquals(_buckets, _bucketsCache)) { _buckets = _bucketsCache; ReseekCursor(); }
                return;
            }

            var list = new List<BidAskBucket>();
            try
            {
                foreach (string line in File.ReadAllLines(BucketLogPath))
                {
                    if (line.Length == 0 || line[0] == 'd') continue;
                    string[] p = line.Split(',');
                    if (p.Length < 4) continue;
                    DateTime ts; double a, b;
                    if (DateTime.TryParse(p[1], CultureInfo.InvariantCulture, DateTimeStyles.None, out ts)
                        && double.TryParse(p[2], NumberStyles.Any, CultureInfo.InvariantCulture, out a)
                        && double.TryParse(p[3], NumberStyles.Any, CultureInfo.InvariantCulture, out b))
                        list.Add(new BidAskBucket { ts = ts, askVol = a, bidVol = b });
                }
                list.Sort((x, y) => x.ts.CompareTo(y.ts));
            }
            catch (Exception ex) { Print(Name + ": could not read bid/ask bucket log: " + ex.Message); return; }

            _bucketsCache = list; _bucketsCacheFileTime = fileTime;
            _buckets = list;
            ReseekCursor();
        }

        private void ReseekCursor()
        {
            _bucketCursor = 0;
            while (_bucketCursor < _buckets.Count && _buckets[_bucketCursor].ts <= _lastConsumedTs)
                _bucketCursor++;
        }

        private DateTime ConvertToCt(DateTime t)
        {
            if (_ctTz == null) return t;
            TimeZoneInfo displayTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
            return displayTz.Equals(_ctTz) ? t : TimeZoneInfo.ConvertTime(t, displayTz, _ctTz);
        }

        // Cumulative variant of the other 3 indicators' AdvanceBucketCursor: walks every
        // bucket up to barCloseTime, ADDING (ask-bid) into the running `runCum` (not
        // resetting per bar — CVD is cumulative) and tracking this bar's own open/high/low/
        // close along the way. `any` is false if no buckets were consumed (nothing to
        // reconstruct for this bar — caller falls through to the existing NaN-seed fallback).
        private void AdvanceCvdBuckets(DateTime barCloseTime, out double o, out double h, out double l, out double c, out bool any)
        {
            o = h = l = c = runCum; any = false;
            if ((DateTime.UtcNow - _lastBucketFileCheckUtc).TotalSeconds >= 30)
            { _lastBucketFileCheckUtc = DateTime.UtcNow; ReadBucketFile(); }
            if (_buckets.Count == 0) return;
            DateTime t = ConvertToCt(barCloseTime);
            while (_bucketCursor < _buckets.Count && _buckets[_bucketCursor].ts <= t)
            {
                runCum += _buckets[_bucketCursor].askVol - _buckets[_bucketCursor].bidVol;
                if (runCum > h) h = runCum;
                if (runCum < l) l = runCum;
                _lastConsumedTs = _buckets[_bucketCursor].ts;
                _bucketCursor++;
                any = true;
            }
            c = runCum;
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "CumulativeDelta";
                Description = "Cumulative volume delta (CVD) as candles, from ticks — no Order Flow+ needed — with live price/CVD divergence marking";
                Calculate = Calculate.OnEachTick;   // MUST be per-tick
                IsOverlay = false;                  // its own panel
                DrawOnPricePanel = true;             // lets Draw.Line/Draw.Text (divergence only) reach the price panel
                DisplayInDataBox = true;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = true;
                ResetMode = CvdResetMode.Session;
                LargeLotMin = 0;
                UpColor = Brushes.SeaGreen;
                DownColor = Brushes.Firebrick;

                ShowDivergence = true;
                ShowHiddenDivergence = false;
                ReversalTicks = 8;
                DivLabelFontSize = 10;
                ShowLabels = true;
                BearColor = Brushes.OrangeRed;
                BullColor = Brushes.Lime;
                HiddenBearColor = Brushes.DarkOrange;
                HiddenBullColor = Brushes.Cyan;

                // transparent plots drive the panel autoscale to include the CVD high/low;
                // a faint Close line is a fallback in case custom rendering is unavailable
                AddPlot(new Stroke(Brushes.DimGray, 1), PlotStyle.Line, "CVD");     // Values[0]=Close
                AddPlot(Brushes.Transparent, "CvdHigh");                            // Values[1]
                AddPlot(Brushes.Transparent, "CvdLow");                            // Values[2]
            }
            else if (State == State.Configure)
            {
                cvO = new Series<double>(this);
                cvH = new Series<double>(this);
                cvL = new Series<double>(this);
                cvC = new Series<double>(this);
                cvLiveFlag = new Series<double>(this);
            }
            else if (State == State.DataLoaded)
            {
                LoadBidAskBuckets();
            }
            else if (State == State.Terminated)
            {
                if (upBrush != null) { upBrush.Dispose(); upBrush = null; }
                if (dnBrush != null) { dnBrush.Dispose(); dnBrush = null; }
            }
        }

        // classify each trade exactly like FootprintExporter (quote embedded in the tick)
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last || CurrentBar < 0) return;

            if (accumBar != CurrentBar)                 // bar rolled
            {
                if (ResetMode == CvdResetMode.Session && Bars.IsFirstBarOfSession)
                    runCum = 0;
                accumBar = CurrentBar;
                barOpen = barHi = barLo = barClose = runCum;
            }

            long v = (long)e.Volume;
            if (LargeLotMin > 0 && v < LargeLotMin) v = 0;   // large-lot filter
            if (v > 0)
            {
                double ask = e.Ask, bid = e.Bid; bool buy;
                if (ask > 0 && bid > 0)
                {
                    if (e.Price >= ask) buy = true;
                    else if (e.Price <= bid) buy = false;
                    else buy = e.Price >= (ask + bid) / 2.0;
                }
                else buy = true;
                runCum += buy ? v : -v;
            }
            barClose = runCum;
            if (runCum > barHi) barHi = runCum;
            if (runCum < barLo) barLo = runCum;

            cvO[0] = barOpen; cvH[0] = barHi; cvL[0] = barLo; cvC[0] = barClose;
            Values[0][0] = barClose; Values[1][0] = barHi; Values[2][0] = barLo;
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 0) return;

            // Historical bar (OnMarketData never touched it this chart load) — reconstruct
            // a real open/high/low/close from the L1-tape backfill instead of leaving it to
            // flatline. Skipped entirely for a bar that WAS live: OnMarketData already built
            // its exact cvO/cvH/cvL/cvC/runCum during the tick stream, don't touch it.
            bool liveThisBar = accumBar == CurrentBar;
            cvLiveFlag[0] = liveThisBar ? 1.0 : 0.0;
            if (!liveThisBar)
            {
                if (ResetMode == CvdResetMode.Session && Bars.IsFirstBarOfSession) runCum = 0;
                double bo, bh, bl, bc; bool any;
                AdvanceCvdBuckets(Time[0], out bo, out bh, out bl, out bc, out any);
                if (any)
                {
                    cvO[0] = bo; cvH[0] = bh; cvL[0] = bl; cvC[0] = bc;
                    Values[0][0] = bc; Values[1][0] = bh; Values[2][0] = bl;
                }
            }

            // seed a flat value on bars with no data at all — neither live nor backfilled
            // (no bucket file, or a day it doesn't cover) — so the plot/scale stay
            // continuous. Final safety net, unchanged from before the backfill.
            if (double.IsNaN(cvC[0]))
            {
                cvO[0] = cvH[0] = cvL[0] = cvC[0] = runCum;
                Values[0][0] = Values[1][0] = Values[2][0] = runCum;
            }

            if (Bars.IsFirstBarOfSession)
            {
                sessionStartBar = CurrentBar;
                dir = SwingDir.Up; legExtBar = CurrentBar; legExtPrice = High[0];
                lastHighBar = lastLowBar = -1;
                bearTag = bullTag = null; liveMark = null;
            }
            else if (legExtBar < 0)
            {
                legExtBar = CurrentBar; legExtPrice = dir == SwingDir.Up ? High[0] : Low[0];
            }

            if (ShowDivergence) UpdateDivergence();
        }

        // ---- live incremental ZigZag swing tracker + divergence (see header) ----
        private void UpdateDivergence()
        {
            double tick = TickSize > 0 ? TickSize : 0.25;
            double revAmt = ReversalTicks * tick;

            if (dir == SwingDir.Up)
            {
                if (High[0] > legExtPrice) { legExtPrice = High[0]; legExtBar = CurrentBar; }
                else if (Low[0] <= legExtPrice - revAmt)
                {
                    ConfirmHigh(legExtBar, legExtPrice);
                    dir = SwingDir.Down; legExtPrice = Low[0]; legExtBar = CurrentBar;
                }
            }
            else
            {
                if (Low[0] < legExtPrice) { legExtPrice = Low[0]; legExtBar = CurrentBar; }
                else if (High[0] >= legExtPrice + revAmt)
                {
                    ConfirmLow(legExtBar, legExtPrice);
                    dir = SwingDir.Up; legExtPrice = High[0]; legExtBar = CurrentBar;
                }
            }

            bool pushingHigh = dir == SwingDir.Up && lastHighBar >= sessionStartBar && lastHighBar >= 0
                                && High[0] > lastHighPrice;
            if (pushingHigh)
            {
                double curCvd = cvC[0];
                if (curCvd < lastHighCvd)
                {
                    if (bearTag == null) bearTag = "cvdDivBear_" + lastHighBar + "_" + CurrentBar;
                    DrawLivePrice(bearTag, lastHighBar, lastHighPrice, CurrentBar, High[0], BearColor, "Bear Div", true);
                    liveMark = new DivMark { barA = lastHighBar, barB = CurrentBar, cvdA = lastHighCvd, cvdB = curCvd, bearish = true };
                }
                else if (bearTag != null) { RemoveLivePrice(bearTag); bearTag = null; liveMark = null; }
            }
            else if (bearTag != null) { RemoveLivePrice(bearTag); bearTag = null; liveMark = null; }

            bool pushingLow = dir == SwingDir.Down && lastLowBar >= sessionStartBar && lastLowBar >= 0
                               && Low[0] < lastLowPrice;
            if (pushingLow)
            {
                double curCvd = cvC[0];
                if (curCvd > lastLowCvd)
                {
                    if (bullTag == null) bullTag = "cvdDivBull_" + lastLowBar + "_" + CurrentBar;
                    DrawLivePrice(bullTag, lastLowBar, lastLowPrice, CurrentBar, Low[0], BullColor, "Bull Div", false);
                    liveMark = new DivMark { barA = lastLowBar, barB = CurrentBar, cvdA = lastLowCvd, cvdB = curCvd, bearish = false };
                }
                else if (bullTag != null) { RemoveLivePrice(bullTag); bullTag = null; liveMark = null; }
            }
            else if (bullTag != null) { RemoveLivePrice(bullTag); bullTag = null; liveMark = null; }
        }

        private void ConfirmHigh(int bar, double price)
        {
            double cvd = cvC.GetValueAt(bar);
            if (ShowHiddenDivergence && lastHighBar >= sessionStartBar && lastHighBar >= 0
                && price < lastHighPrice && cvd > lastHighCvd)
            {
                DrawFinalPrice("cvdHDivBear_" + bar, lastHighBar, lastHighPrice, bar, price, HiddenBearColor, "H.Bear Div");
                hist.Add(new DivMark { barA = lastHighBar, barB = bar, cvdA = lastHighCvd, cvdB = cvd, bearish = true });
            }
            else if (bearTag != null)
            {
                hist.Add(new DivMark { barA = lastHighBar, barB = bar, cvdA = lastHighCvd, cvdB = cvd, bearish = true });
            }
            lastHighBar = bar; lastHighPrice = price; lastHighCvd = cvd;
            bearTag = null; liveMark = null;   // episode closed; whatever is drawn stays, untouched
        }

        private void ConfirmLow(int bar, double price)
        {
            double cvd = cvC.GetValueAt(bar);
            if (ShowHiddenDivergence && lastLowBar >= sessionStartBar && lastLowBar >= 0
                && price > lastLowPrice && cvd < lastLowCvd)
            {
                DrawFinalPrice("cvdHDivBull_" + bar, lastLowBar, lastLowPrice, bar, price, HiddenBullColor, "H.Bull Div");
                hist.Add(new DivMark { barA = lastLowBar, barB = bar, cvdA = lastLowCvd, cvdB = cvd, bearish = false });
            }
            else if (bullTag != null)
            {
                hist.Add(new DivMark { barA = lastLowBar, barB = bar, cvdA = lastLowCvd, cvdB = cvd, bearish = false });
            }
            lastLowBar = bar; lastLowPrice = price; lastLowCvd = cvd;
            bullTag = null; liveMark = null;
        }

        // price-panel connecting line + label (drawing-object API; auto-persists/auto-
        // renders itself via NT8, routed to the price panel by DrawOnPricePanel=true).
        // 2026-10-19: this was the source of the "Bear Div"/"Bull Div"/"H.Bear Div"/
        // "H.Bull Div" text cluttering the price panel — unlike CVDDivergenceOscillator.cs's
        // own ShowLabels, there was no way to turn the text off and keep just the lines.
        // Added ShowLabels here too (same property name/behavior as that file).
        private void DrawLivePrice(string tag, int barA, double priceA, int barB, double priceB, System.Windows.Media.Brush color, string label, bool above)
        {
            int baA = CurrentBar - barA, baB = CurrentBar - barB;
            Draw.Line(this, tag, false, baA, priceA, baB, priceB, color, DashStyleHelper.Solid, 2);
            if (ShowLabels)
            {
                double off = 8 * (TickSize > 0 ? TickSize : 0.25);
                Draw.Text(this, tag + "_txt", false, label, baB, above ? priceB + off : priceB - off, 0,
                          color, new NinjaTrader.Gui.Tools.SimpleFont("Arial", DivLabelFontSize), System.Windows.TextAlignment.Center,
                          Brushes.Transparent, Brushes.Transparent, 0);
            }
        }

        private void DrawFinalPrice(string tag, int barA, double priceA, int barB, double priceB, System.Windows.Media.Brush color, string label)
        {
            DrawLivePrice(tag, barA, priceA, barB, priceB, color, label, priceB >= priceA);
        }

        private void RemoveLivePrice(string tag)
        {
            RemoveDrawObject(tag);
            RemoveDrawObject(tag + "_txt");
        }

        public override void OnRenderTargetChanged()
        {
            if (upBrush != null) { upBrush.Dispose(); upBrush = null; }
            if (dnBrush != null) { dnBrush.Dispose(); dnBrush = null; }
            if (RenderTarget != null)
            {
                upBrush = UpColor.ToDxBrush(RenderTarget);
                dnBrush = DownColor.ToDxBrush(RenderTarget);
            }
        }

        // draw the CVD candlesticks + CVD-panel-side divergence connecting lines.
        // 2026-10-19: user — "cum delta plot is not usable like this... maybe mountains?
        // this doesn't show me anything currently." A reconstructed bar's O/H/L only
        // reflects whatever fell inside its own 50-trade buckets, not true tick-level
        // range — rendering THAT as a full candle on a fast tick-bar chart produced a
        // string of near-zero-range bodies that, since each bar's open == the prior bar's
        // close exactly (continuous by construction), visually merged into one flat smooth
        // line with no legible texture. Fix: ALWAYS draw a continuous close-to-close
        // backbone line (the "mountain" ask) across every bar, live or reconstructed; layer
        // full candle body+wick on TOP of that line only where cvLiveFlag says the bar is
        // genuinely tick-accurate, so real intrabar texture is still visible exactly where
        // it's trustworthy, without faking it where it isn't.
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);
            if (Bars == null || ChartBars == null || RenderTarget == null || upBrush == null) return;

            float w = (float)Math.Max(1.0, chartControl.Properties.BarDistance * 0.30);

            float prevX = 0, prevYc = 0; bool havePrev = false;
            var lineBr = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.55f, 0.55f, 0.55f, 1f));
            for (int idx = ChartBars.FromIndex; idx <= ChartBars.ToIndex; idx++)
            {
                if (idx < 0 || idx > cvC.Count - 1) { havePrev = false; continue; }
                double c0 = cvC.GetValueAt(idx);
                if (double.IsNaN(c0)) { havePrev = false; continue; }
                float x0 = chartControl.GetXByBarIndex(ChartBars, idx);
                float yC0 = chartScale.GetYByValue(c0);
                if (havePrev) RenderTarget.DrawLine(new Vector2(prevX, prevYc), new Vector2(x0, yC0), lineBr, 1.5f);
                prevX = x0; prevYc = yC0; havePrev = true;
            }
            lineBr.Dispose();

            for (int idx = ChartBars.FromIndex; idx <= ChartBars.ToIndex; idx++)
            {
                if (idx < 0 || idx > cvC.Count - 1) continue;
                if (cvLiveFlag.GetValueAt(idx) < 0.5) continue;   // reconstructed bar -- backbone line only, no fake candle
                double o = cvO.GetValueAt(idx), h = cvH.GetValueAt(idx),
                       l = cvL.GetValueAt(idx), c = cvC.GetValueAt(idx);
                if (double.IsNaN(o)) continue;

                float x  = chartControl.GetXByBarIndex(ChartBars, idx);
                float yO = chartScale.GetYByValue(o), yH = chartScale.GetYByValue(h),
                      yL = chartScale.GetYByValue(l), yC = chartScale.GetYByValue(c);
                var br = c >= o ? upBrush : dnBrush;

                RenderTarget.DrawLine(new Vector2(x, yH), new Vector2(x, yL), br, 1f);   // wick
                float top = Math.Min(yO, yC), bot = Math.Max(yO, yC);
                RenderTarget.FillRectangle(new RectangleF(x - w, top, 2f * w, Math.Max(bot - top, 1f)), br);   // body
            }

            if (!ShowDivergence) return;
            int fromV = ChartBars.FromIndex, toV = ChartBars.ToIndex;
            var bearBr = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(BearColor));
            var bullBr = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(BullColor));
            foreach (DivMark m in hist) DrawCvdMark(chartControl, chartScale, m, fromV, toV, m.bearish ? bearBr : bullBr);
            if (liveMark.HasValue) DrawCvdMark(chartControl, chartScale, liveMark.Value, fromV, toV, liveMark.Value.bearish ? bearBr : bullBr);
            bearBr.Dispose(); bullBr.Dispose();
        }

        private void DrawCvdMark(ChartControl cc, ChartScale cs, DivMark m, int fromV, int toV, SharpDX.Direct2D1.Brush br)
        {
            if (m.barA < fromV - 1 && m.barB < fromV - 1) return;
            if (m.barA > toV + 1 && m.barB > toV + 1) return;
            float xA = cc.GetXByBarIndex(ChartBars, m.barA), xB = cc.GetXByBarIndex(ChartBars, m.barB);
            float yA = cs.GetYByValue(m.cvdA), yB = cs.GetYByValue(m.cvdB);
            RenderTarget.DrawLine(new Vector2(xA, yA), new Vector2(xB, yB), br, 2f);
        }

        private static Color4 ToColor4(System.Windows.Media.Brush b)
        {
            var scb = b as System.Windows.Media.SolidColorBrush;
            if (scb == null) return new Color4(1f, 1f, 1f, 1f);
            var c = scb.Color;
            return new Color4(c.R / 255f, c.G / 255f, c.B / 255f, c.A / 255f);
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "ResetMode", Description = "Reset CVD each session or run continuous",
                 GroupName = "1. Parameters", Order = 0)]
        public CvdResetMode ResetMode { get; set; }

        [NinjaScriptProperty]
        [Range(0, int.MaxValue)]
        [Display(Name = "LargeLotMin", Description = "0 = all trades; >0 = only count trades >= N contracts",
                 GroupName = "1. Parameters", Order = 1)]
        public int LargeLotMin { get; set; }

        [XmlIgnore]
        [Display(Name = "Up color", GroupName = "1. Parameters", Order = 2)]
        public System.Windows.Media.Brush UpColor { get; set; }
        [Browsable(false)]
        public string UpColorSerialize { get { return Serialize.BrushToString(UpColor); } set { UpColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Down color", GroupName = "1. Parameters", Order = 3)]
        public System.Windows.Media.Brush DownColor { get; set; }
        [Browsable(false)]
        public string DownColorSerialize { get { return Serialize.BrushToString(DownColor); } set { DownColor = Serialize.StringToBrush(value); } }

        [NinjaScriptProperty]
        [Display(Name = "Show divergence (live)", Description = "Live regular price/CVD divergence — starts drawing the instant price pushes past the prior confirmed swing with CVD not confirming, grows with the leg, freezes when the leg reverses.",
                 GroupName = "2. Divergence", Order = 0)]
        public bool ShowDivergence { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show hidden divergence", Description = "Continuation pattern: evaluated once, when a swing confirms (not live/growing by definition). Off by default.",
                 GroupName = "2. Divergence", Order = 1)]
        public bool ShowHiddenDivergence { get; set; }

        [NinjaScriptProperty]
        [Range(1, 1000)]
        [Display(Name = "Reversal (ticks)", Description = "How far price must pull back from a leg's running extreme before that extreme is a CONFIRMED swing pivot.",
                 GroupName = "2. Divergence", Order = 2)]
        public int ReversalTicks { get; set; }

        [NinjaScriptProperty]
        [Range(6, 24)]
        [Display(Name = "Label font size", GroupName = "2. Divergence", Order = 3)]
        public int DivLabelFontSize { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Labels", Description = "Draw Bear Div/Bull Div/H.Bear Div/H.Bull Div text on the price panel at each divergence. Turn off to keep just the connecting lines — same property as CVDDivergenceOscillator.cs's own Show Labels.",
                 GroupName = "2. Divergence", Order = 4)]
        public bool ShowLabels { get; set; }

        [XmlIgnore]
        [Display(Name = "Bearish color", GroupName = "2. Divergence", Order = 5)]
        public System.Windows.Media.Brush BearColor { get; set; }
        [Browsable(false)]
        public string BearColorSerialize { get { return Serialize.BrushToString(BearColor); } set { BearColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Bullish color", GroupName = "2. Divergence", Order = 6)]
        public System.Windows.Media.Brush BullColor { get; set; }
        [Browsable(false)]
        public string BullColorSerialize { get { return Serialize.BrushToString(BullColor); } set { BullColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Hidden bearish color", GroupName = "2. Divergence", Order = 7)]
        public System.Windows.Media.Brush HiddenBearColor { get; set; }
        [Browsable(false)]
        public string HiddenBearColorSerialize { get { return Serialize.BrushToString(HiddenBearColor); } set { HiddenBearColor = Serialize.StringToBrush(value); } }

        [XmlIgnore]
        [Display(Name = "Hidden bullish color", GroupName = "2. Divergence", Order = 8)]
        public System.Windows.Media.Brush HiddenBullColor { get; set; }
        [Browsable(false)]
        public string HiddenBullColorSerialize { get { return Serialize.BrushToString(HiddenBullColor); } set { HiddenBullColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
