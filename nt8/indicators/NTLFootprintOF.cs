// NTLFootprintOF.cs — REAL footprint overlay indicator for NinjaTrader 8.
//
// WHY THIS EXISTS: the bundled NTLFootprintChartStyle ESTIMATES bid/ask from OHLC
// (directionBias 0.62/0.38) because ChartStyles cannot see the tick series — it is a
// cosmetic footprint, useless for absorption. This indicator reconstructs the TRUE
// per-price bid/ask ladder from Tick Replay, using the exact aggressor rule the suite's
// real order-flow indicators use (NTLCore.IsAskTrade on BarsArray[1].GetBid/GetAsk).
//
// VALIDATED: scripts/footprint_classify_validate.py replays the recorded L1 tape and shows
// IsAskTrade reproduces our recorder's live aggressor tags 100.000% on ES (2026-09-16 RTH,
// 941,582 trades) — ES trades at a 1-tick spread so there are no inside-spread trades where
// the rule could diverge. => this footprint matches our MzPack-validated one exactly.
//
// REQUIRES Tick Replay (Tools>Options>Market Data + chart Data Series). Overlay indicator:
// set the chart to wide bar spacing so the ladder cells have room.
//
// Stage 1+2 (data engine + render). Stage 3 (green/red imbalance cells like the python zoom)
// + Stage 4 (absorption / divergence markers) follow.
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators.NTLambda;   // NTLCore, NTLBidAskLayout, NTLFootprint* enums
using SharpDX;
using DxBrush = SharpDX.Direct2D1.Brush;
using DwFactory = SharpDX.DirectWrite.Factory;
using TextFormat = SharpDX.DirectWrite.TextFormat;
using WpfBrush = System.Windows.Media.Brush;
using WpfBrushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.NTLambda
{
    public class NTLFootprintOF : Indicator
    {
        private sealed class Row
        {
            public double Price;
            public double Bid;
            public double Ask;
            public double Total { get { return Bid + Ask; } }
            public double Delta { get { return Ask - Bid; } }
            public bool BuyImbalance;
            public bool SellImbalance;
            public bool InValueArea;
            public bool IsPoc;
        }

        // barIndex (absolute on BarsArray[0]) -> price bucket -> [bid, ask]
        private readonly Dictionary<int, SortedDictionary<double, double[]>> ladders =
            new Dictionary<int, SortedDictionary<double, double[]>>();
        private double lastPrice = double.NaN;
        private int activeBar = -1;
        private const int MaxBarsKept = 4000;

        private DxBrush bidBrushDx, askBrushDx, outlineBrushDx, textBrushDx, pocBrushDx, valueAreaBrushDx, imbalanceBrushDx;
        private DxBrush askBgDx, bidBgDx, pocBgDx, buyImbTextDx, sellImbTextDx;   // flat-cell render
        private DwFactory textFactory;
        private TextFormat textFormat;
        private int cachedTextSize;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "NTL Footprint OF";
                Description = "Real footprint (per-price bid/ask from Tick Replay). Requires Tick Replay.";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                IsChartOnly = true;
                PaintPriceMarkers = false;

                BidAskLayout = NTLBidAskLayout.BidAsk;
                FootprintType = NTLFootprintDisplayType.BuySell;
                BucketTicks = 1;
                ReadableRows = true;
                AutoWidth = true;
                BucketPixelWidth = 90;
                TextSize = 9;
                ShowNumbers = true;
                ApplyGradient = true;
                ShowPoc = true;
                ShowValueArea = false;
                ValueAreaPercent = 70;
                HighlightImbalances = true;
                ImbalancePercent = 300;
                ShowGrid = false;

                BidColor = WpfBrushes.IndianRed;
                AskColor = WpfBrushes.Teal;
                PocColor = WpfBrushes.Gold;
                ValueAreaColor = WpfBrushes.RoyalBlue;
                ImbalanceColor = WpfBrushes.Yellow;
                OutlineColor = WpfBrushes.Gray;
                TextColor = WpfBrushes.Black;
                BuyImbalanceColor = WpfBrushes.SeaGreen;
                SellImbalanceColor = WpfBrushes.Crimson;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Tick, 1);
            }
            else if (State == State.Terminated)
            {
                DisposeBrushes();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                ProcessTick();
                return;
            }
            if (BarsInProgress != 0) return;

            // soft prune so a long tick-replay load does not grow unbounded
            if (ladders.Count > MaxBarsKept)
            {
                int cut = ladders.Keys.Min() + (ladders.Count - MaxBarsKept);
                foreach (var k in ladders.Keys.Where(x => x < cut).ToList())
                    ladders.Remove(k);
            }
        }

        private void ProcessTick()
        {
            if (CurrentBars == null || CurrentBars.Length < 2 || CurrentBars[0] < 0 || CurrentBars[1] < 0) return;
            int tickIndex = CurrentBars[1];
            int bar = BarsArray[0].GetBar(BarsArray[1].GetTime(tickIndex));
            if (bar < 0) return;

            double price = BarsArray[1].GetClose(tickIndex);
            double bid = BarsArray[1].GetBid(tickIndex);
            double ask = BarsArray[1].GetAsk(tickIndex);
            double volume = BarsArray[1].GetVolume(tickIndex);
            if (volume <= 0) return;

            if (bar != activeBar) { activeBar = bar; lastPrice = double.NaN; }

            double bucketSize = TickSizeSafe() * Math.Max(1, BucketTicks);
            double bucket = Math.Round(price / bucketSize) * bucketSize;

            SortedDictionary<double, double[]> ladder;
            if (!ladders.TryGetValue(bar, out ladder))
            {
                ladder = new SortedDictionary<double, double[]>();
                ladders[bar] = ladder;
            }
            double[] cell;
            if (!ladder.TryGetValue(bucket, out cell)) { cell = new double[2]; ladder[bucket] = cell; }

            if (IsAskTrade(price, bid, ask, lastPrice)) cell[1] += volume;   // ask = aggressive buy
            else cell[0] += volume;                                          // bid = aggressive sell
            lastPrice = price;
        }

        // Aggressor rule — inlined (validated 100% vs our recorder on 2026-09-16 ES RTH,
        // scripts/footprint_classify_validate.py). Same logic as NTLCore.IsAskTrade; kept
        // local so this indicator has no dependency on the vendored suite's internal API.
        private static bool IsAskTrade(double price, double bid, double ask, double last)
        {
            if (ask > 0 && price >= ask) return true;
            if (bid > 0 && price <= bid) return false;
            return double.IsNaN(last) || price >= last;
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (chartControl == null || chartScale == null || ChartBars == null || RenderTarget == null) return;
            if (ladders.Count == 0) return;
            if (bidBrushDx == null) OnRenderTargetChanged();
            EnsureTextFormat();
            if (bidBrushDx == null) return;

            RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;
            int from = Math.Max(0, ChartBars.FromIndex);
            int to = Math.Min(ChartBars.ToIndex, ChartBars.Bars.Count - 1);
            double tick = TickSizeSafe();
            // RENDER bucket auto-grows so each row is tall enough to print text at the current
            // price zoom (this is what fixes "unreadable pastel stripes"). Data stays fine-grained.
            double renderBucket = ReadableRows ? ReadableBucket(chartScale, tick) : tick * Math.Max(1, BucketTicks);
            // cell width tracks the actual bar spacing so columns pack edge-to-edge (no gaps).
            float spacing = BucketPixelWidth;
            if (to > from)
                spacing = Math.Abs(chartControl.GetXByBarIndex(ChartBars, from + 1) - chartControl.GetXByBarIndex(ChartBars, from));
            float halfWidth = (AutoWidth ? Math.Max(8f, spacing - 1f) : Math.Max(10, BucketPixelWidth)) / 2f;

            for (int barIdx = from; barIdx <= to; barIdx++)
            {
                SortedDictionary<double, double[]> ladder;
                if (!ladders.TryGetValue(barIdx, out ladder) || ladder.Count == 0) continue;

                // aggregate the fine ladder into readable-height buckets
                var coarse = new SortedDictionary<double, double[]>();
                foreach (var kv in ladder)
                {
                    double cp = Math.Floor(kv.Key / renderBucket) * renderBucket + renderBucket * 0.5;
                    double[] c;
                    if (!coarse.TryGetValue(cp, out c)) { c = new double[2]; coarse[cp] = c; }
                    c[0] += kv.Value[0]; c[1] += kv.Value[1];
                }

                var rows = coarse.Select(kv => new Row { Price = kv.Key, Bid = kv.Value[0], Ask = kv.Value[1] }).ToList();
                Annotate(rows);
                double maxBid = Math.Max(1, rows.Select(r => r.Bid).DefaultIfEmpty(1).Max());
                double maxAsk = Math.Max(1, rows.Select(r => r.Ask).DefaultIfEmpty(1).Max());
                double maxTotal = Math.Max(1, rows.Select(r => Math.Max(Math.Abs(r.Delta), r.Total)).DefaultIfEmpty(1).Max());

                float x = chartControl.GetXByBarIndex(ChartBars, barIdx);
                foreach (var row in rows)
                {
                    if (row.Price < chartScale.MinValue || row.Price > chartScale.MaxValue) continue;
                    float yTop = chartScale.GetYByValue(row.Price + renderBucket * 0.5);
                    float yBottom = chartScale.GetYByValue(row.Price - renderBucket * 0.5);
                    float rowHeight = Math.Max(1, yBottom - yTop);
                    DrawRow(x, yTop, rowHeight, halfWidth, row, maxBid, maxAsk, maxTotal);
                }
            }
        }

        // smallest price bucket whose on-screen height clears the text, so rows stay readable at any zoom
        private double ReadableBucket(ChartScale chartScale, double tick)
        {
            double floorBucket = tick * Math.Max(1, BucketTicks);
            double canvasH = Math.Abs(chartScale.GetYByValue(chartScale.MinValue) - chartScale.GetYByValue(chartScale.MaxValue));
            if (canvasH < 1) return floorBucket;
            double priceRange = Math.Max(tick, chartScale.MaxValue - chartScale.MinValue);
            double pricePerPixel = priceRange / canvasH;
            double desiredPixels = Math.Max(TextSize + 3, 11);
            double needTicks = Math.Ceiling((pricePerPixel * desiredPixels) / tick);
            return Math.Max(floorBucket, Math.Max(1, needTicks) * tick);
        }

        private void Annotate(List<Row> rows)
        {
            if (rows.Count == 0) return;
            Row poc = rows.OrderByDescending(r => r.Total).First();
            poc.IsPoc = true;

            double target = rows.Sum(r => r.Total) * Math.Max(1, Math.Min(100, ValueAreaPercent)) / 100.0;
            double running = 0;
            foreach (var row in rows.OrderByDescending(r => r.Total))
            {
                row.InValueArea = true;
                running += row.Total;
                if (running >= target) break;
            }

            double threshold = Math.Max(100, ImbalancePercent) / 100.0;
            // rows are price-ascending (SortedDictionary). Diagonal imbalance: ask@price vs bid@price-1 bucket.
            for (int i = 0; i < rows.Count; i++)
            {
                double lowerBid = i > 0 ? rows[i - 1].Bid : 0;
                double upperAsk = i < rows.Count - 1 ? rows[i + 1].Ask : 0;
                rows[i].BuyImbalance = HighlightImbalances && lowerBid > 0 && rows[i].Ask >= threshold * lowerBid;
                rows[i].SellImbalance = HighlightImbalances && upperAsk > 0 && rows[i].Bid >= threshold * upperAsk;
            }
        }

        private void DrawRow(float x, float yTop, float rowHeight, float halfWidth, Row row, double maxBid, double maxAsk, double maxTotal)
        {
            // Flat-cell footprint (matches the validated python zoom): one tinted cell per price
            // showing "bid x ask", tint by delta sign, gold for POC, bold green/red for imbalance.
            float leftX = x - halfWidth;
            RectangleF full = new RectangleF(leftX, yTop, halfWidth * 2, rowHeight);

            DxBrush bg = row.IsPoc ? pocBgDx : (row.Delta >= 0 ? askBgDx : bidBgDx);
            RenderTarget.FillRectangle(full, bg);
            if (row.InValueArea && ShowValueArea)
                RenderTarget.FillRectangle(full, valueAreaBrushDx);
            if (ShowGrid)
                RenderTarget.DrawRectangle(full, outlineBrushDx, 1f);
            if (row.IsPoc && ShowPoc)
                RenderTarget.DrawRectangle(full, pocBrushDx, 2f);

            if (ShowNumbers && textFormat != null && rowHeight >= TextSize + 1)
            {
                DxBrush tb = row.BuyImbalance ? buyImbTextDx : (row.SellImbalance ? sellImbTextDx : textBrushDx);
                string s = ((long)Math.Round(row.Bid)).ToString() + " x " + ((long)Math.Round(row.Ask)).ToString();
                RenderTarget.DrawText(s, textFormat, full, tb);
            }
        }

        private double TickSizeSafe()
        {
            try
            {
                if (Instrument != null && Instrument.MasterInstrument != null)
                    return Instrument.MasterInstrument.TickSize;
            }
            catch { }
            return 0.25;
        }

        public override void OnRenderTargetChanged()
        {
            DisposeBrushes();
            if (RenderTarget == null) return;
            bidBrushDx = BidColor.ToDxBrush(RenderTarget);
            askBrushDx = AskColor.ToDxBrush(RenderTarget);
            outlineBrushDx = OutlineColor.ToDxBrush(RenderTarget);
            textBrushDx = TextColor.ToDxBrush(RenderTarget);
            pocBrushDx = PocColor.ToDxBrush(RenderTarget);
            valueAreaBrushDx = ValueAreaColor.ToDxBrush(RenderTarget);
            imbalanceBrushDx = ImbalanceColor.ToDxBrush(RenderTarget);
            askBgDx = AskColor.ToDxBrush(RenderTarget);
            bidBgDx = BidColor.ToDxBrush(RenderTarget);
            pocBgDx = PocColor.ToDxBrush(RenderTarget);
            buyImbTextDx = BuyImbalanceColor.ToDxBrush(RenderTarget);
            sellImbTextDx = SellImbalanceColor.ToDxBrush(RenderTarget);
            outlineBrushDx.Opacity = 0.55f;
            textBrushDx.Opacity = 0.95f;
            valueAreaBrushDx.Opacity = 0.18f;
            askBgDx.Opacity = 0.20f;    // soft pastel cell fill
            bidBgDx.Opacity = 0.20f;
            pocBgDx.Opacity = 0.38f;
        }

        private void EnsureTextFormat()
        {
            if (!ShowNumbers) return;
            if (textFormat != null && cachedTextSize == TextSize) return;
            if (textFormat != null) { textFormat.Dispose(); textFormat = null; }
            if (textFactory == null) textFactory = new DwFactory();
            cachedTextSize = TextSize;
            textFormat = new TextFormat(textFactory, "Consolas", Math.Max(6, TextSize));
            textFormat.TextAlignment = SharpDX.DirectWrite.TextAlignment.Center;
            textFormat.ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Center;
        }

        private void DisposeBrushes()
        {
            if (bidBrushDx != null) { bidBrushDx.Dispose(); bidBrushDx = null; }
            if (askBrushDx != null) { askBrushDx.Dispose(); askBrushDx = null; }
            if (outlineBrushDx != null) { outlineBrushDx.Dispose(); outlineBrushDx = null; }
            if (textBrushDx != null) { textBrushDx.Dispose(); textBrushDx = null; }
            if (pocBrushDx != null) { pocBrushDx.Dispose(); pocBrushDx = null; }
            if (valueAreaBrushDx != null) { valueAreaBrushDx.Dispose(); valueAreaBrushDx = null; }
            if (imbalanceBrushDx != null) { imbalanceBrushDx.Dispose(); imbalanceBrushDx = null; }
            if (askBgDx != null) { askBgDx.Dispose(); askBgDx = null; }
            if (bidBgDx != null) { bidBgDx.Dispose(); bidBgDx = null; }
            if (pocBgDx != null) { pocBgDx.Dispose(); pocBgDx = null; }
            if (buyImbTextDx != null) { buyImbTextDx.Dispose(); buyImbTextDx = null; }
            if (sellImbTextDx != null) { sellImbTextDx.Dispose(); sellImbTextDx = null; }
            if (textFormat != null) { textFormat.Dispose(); textFormat = null; }
            if (textFactory != null) { textFactory.Dispose(); textFactory = null; }
        }

        #region Properties
        [Display(Name = "Bid/ask layout", GroupName = "Footprint", Order = 0)]
        public NTLBidAskLayout BidAskLayout { get; set; }
        [Display(Name = "Type", GroupName = "Footprint", Order = 1)]
        public NTLFootprintDisplayType FootprintType { get; set; }
        [Range(1, 100)]
        [Display(Name = "Bucket ticks", GroupName = "Footprint", Order = 2)]
        public int BucketTicks { get; set; }
        [Display(Name = "Readable rows (auto-merge to fit text)", GroupName = "Footprint", Order = 2)]
        public bool ReadableRows { get; set; }
        [Display(Name = "Auto width (match bar spacing)", GroupName = "Footprint", Order = 3)]
        public bool AutoWidth { get; set; }
        [Range(8, 200)]
        [Display(Name = "Bucket pixel width (if auto off)", GroupName = "Footprint", Order = 4)]
        public int BucketPixelWidth { get; set; }
        [Range(6, 24)]
        [Display(Name = "Text size", GroupName = "Footprint", Order = 4)]
        public int TextSize { get; set; }
        [Display(Name = "Show numbers", GroupName = "Footprint", Order = 5)]
        public bool ShowNumbers { get; set; }
        [Display(Name = "Apply gradient", GroupName = "Footprint", Order = 6)]
        public bool ApplyGradient { get; set; }
        [Display(Name = "Show POC", GroupName = "Footprint", Order = 7)]
        public bool ShowPoc { get; set; }
        [Display(Name = "Show value area", GroupName = "Footprint", Order = 8)]
        public bool ShowValueArea { get; set; }
        [Range(1, 100)]
        [Display(Name = "Value area percent", GroupName = "Footprint", Order = 9)]
        public double ValueAreaPercent { get; set; }
        [Display(Name = "Show grid", GroupName = "Footprint", Order = 10)]
        public bool ShowGrid { get; set; }
        [Display(Name = "Highlight imbalances", GroupName = "Imbalance", Order = 11)]
        public bool HighlightImbalances { get; set; }
        [Range(100, 1000)]
        [Display(Name = "Imbalance percent", GroupName = "Imbalance", Order = 12)]
        public double ImbalancePercent { get; set; }

        [XmlIgnore]
        [Display(Name = "Bid color", GroupName = "Colors", Order = 13)] public WpfBrush BidColor { get; set; }
        [Browsable(false)] public string BidColorSerializable { get { return Serialize.BrushToString(BidColor); } set { BidColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Ask color", GroupName = "Colors", Order = 14)] public WpfBrush AskColor { get; set; }
        [Browsable(false)] public string AskColorSerializable { get { return Serialize.BrushToString(AskColor); } set { AskColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "POC color", GroupName = "Colors", Order = 15)] public WpfBrush PocColor { get; set; }
        [Browsable(false)] public string PocColorSerializable { get { return Serialize.BrushToString(PocColor); } set { PocColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Value area color", GroupName = "Colors", Order = 16)] public WpfBrush ValueAreaColor { get; set; }
        [Browsable(false)] public string ValueAreaColorSerializable { get { return Serialize.BrushToString(ValueAreaColor); } set { ValueAreaColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Imbalance color", GroupName = "Colors", Order = 17)] public WpfBrush ImbalanceColor { get; set; }
        [Browsable(false)] public string ImbalanceColorSerializable { get { return Serialize.BrushToString(ImbalanceColor); } set { ImbalanceColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Buy imbalance text", GroupName = "Colors", Order = 22)] public WpfBrush BuyImbalanceColor { get; set; }
        [Browsable(false)] public string BuyImbalanceColorSerializable { get { return Serialize.BrushToString(BuyImbalanceColor); } set { BuyImbalanceColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Sell imbalance text", GroupName = "Colors", Order = 23)] public WpfBrush SellImbalanceColor { get; set; }
        [Browsable(false)] public string SellImbalanceColorSerializable { get { return Serialize.BrushToString(SellImbalanceColor); } set { SellImbalanceColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Outline color", GroupName = "Colors", Order = 18)] public WpfBrush OutlineColor { get; set; }
        [Browsable(false)] public string OutlineColorSerializable { get { return Serialize.BrushToString(OutlineColor); } set { OutlineColor = Serialize.StringToBrush(value); } }
        [XmlIgnore]
        [Display(Name = "Text color", GroupName = "Colors", Order = 19)] public WpfBrush TextColor { get; set; }
        [Browsable(false)] public string TextColorSerializable { get { return Serialize.BrushToString(TextColor); } set { TextColor = Serialize.StringToBrush(value); } }
        #endregion
    }
}
