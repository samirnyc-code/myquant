#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// This namespace holds Indicators in this folder and is required. Do not change it.
namespace NinjaTrader.NinjaScript.Indicators
{
    // Port of Logan's "Always In" regime logic from the !AlwaysInEMA EasyLanguage indicator.
    //
    // EL logic (per bar):
    //   emaFast = EMA(Close, 20)
    //   mid     = (H + L) / 2                 // GetMidPoint(false,H,L,O,C)  -- assumed HL2
    //   zscore  = (range - mean(range,n)) / std(range,n),  range = H - L      // GetZScoreData(H,L) -- assumed
    //   A) zscore >= thr and mid > emaFast -> AID = +1   (flip if it was -1)
    //      zscore >= thr and mid < emaFast -> AID = -1   (flip if it was +1)
    //   B) C  > emaFast and C[1] > emaFast  -> AID = +1   (evaluated AFTER A, so B wins on the bar)
    //      C  < emaFast and C[1] < emaFast  -> AID = -1
    //
    // The two GetMidPoint / GetZScoreData definitions were NOT in the source screenshots,
    // so MidpointMode + ZScorePeriod + ZScoreThreshold are exposed as parameters to tune.
    public class AlwaysIn : Indicator
    {
        private Series<double> rangeSeries;
        private int            curDir   = 0;   // 0 = not yet established
        private bool           warm     = false;

        private SolidColorBrush ribbonGreen;
        private SolidColorBrush ribbonRed;
        private SolidColorBrush stripeGreen;
        private SolidColorBrush stripeRed;

        private StreamWriter   csvWriter     = null;
        private bool           headerWritten = false;

        // ── Exposed for strategies / MC engine ───────────────────────────────
        [Browsable(false)]
        [XmlIgnore]
        public Series<double> AlwaysInDir { get; private set; }   // +1 / -1 (0 before warmup)

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> FlipBar { get; private set; }       // 1 on bars where direction changed, else 0

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Logan Always-In regime: green/red ribbon panel, flip-bar racing stripes, CSV export.";
                Name        = "AlwaysIn";
                Calculate   = Calculate.OnBarClose;
                IsOverlay   = false;                 // own subpanel for the ribbon
                DisplayInDataBox = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;

                // Logic params
                FastEmaPeriod   = 20;
                ZScorePeriod    = 20;
                ZScoreThreshold = 1.0;
                MidpointUsesOHLC = false;            // false = HL2, true = OHLC4

                // Visual params
                ShowRacingStripes  = true;
                RacingStripeOpacity = 18;            // percent (0-100)

                // CSV params
                WriteCsv = true;
                CsvPath  = @"C:\Users\Admin\Documents\NinjaTrader 8\MCVolumeExport\AlwaysIn_State.csv";

                AddPlot(new Stroke(Brushes.LimeGreen, 2), PlotStyle.Bar, "Regime");
            }
            else if (State == State.Configure)
            {
                ribbonGreen = new SolidColorBrush(Color.FromArgb(210, 0, 170, 0));   ribbonGreen.Freeze();
                ribbonRed   = new SolidColorBrush(Color.FromArgb(210, 200, 0, 0));   ribbonRed.Freeze();
                RebuildStripeBrushes();
            }
            else if (State == State.DataLoaded)
            {
                rangeSeries = new Series<double>(this);
                AlwaysInDir = new Series<double>(this);
                FlipBar     = new Series<double>(this);
                EnsureCsvHeader();
            }
            else if (State == State.Terminated)
            {
                CloseCsv();
            }
        }

        private void RebuildStripeBrushes()
        {
            byte a = (byte)Math.Round(Math.Max(0, Math.Min(100, RacingStripeOpacity)) / 100.0 * 255.0);
            stripeGreen = new SolidColorBrush(Color.FromArgb(a, 0, 170, 0));  stripeGreen.Freeze();
            stripeRed   = new SolidColorBrush(Color.FromArgb(a, 200, 0, 0));  stripeRed.Freeze();
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1) return;

            // Maintain the range series BEFORE any SMA/StdDev call references it.
            rangeSeries[0] = High[0] - Low[0];

            int minBars = Math.Max(FastEmaPeriod, ZScorePeriod) + 1;
            if (CurrentBar < minBars)
            {
                AlwaysInDir[0] = curDir;
                FlipBar[0]     = 0;
                Values[0][0]   = 1;
                PlotBrushes[0][0] = Brushes.Transparent;
                return;
            }

            double emaFast = EMA(Close, FastEmaPeriod)[0];
            double mid     = MidpointUsesOHLC ? (Open[0] + High[0] + Low[0] + Close[0]) / 4.0
                                              : (High[0] + Low[0]) / 2.0;

            double meanR = SMA(rangeSeries, ZScorePeriod)[0];
            double sd    = StdDev(rangeSeries, ZScorePeriod)[0];
            double zscore = sd > 0 ? (rangeSeries[0] - meanR) / sd : 0;

            int newDir = curDir == 0 ? 1 : curDir;   // carry until a trigger fires

            // Trigger A — big bar straddling the fast EMA
            if (zscore >= ZScoreThreshold && mid > emaFast) newDir = 1;
            if (zscore >= ZScoreThreshold && mid < emaFast) newDir = -1;

            // Trigger B — two consecutive closes on one side (evaluated after A, so it wins)
            if (Close[0] > emaFast && Close[1] > emaFast) newDir = 1;
            if (Close[0] < emaFast && Close[1] < emaFast) newDir = -1;

            bool flip = warm && curDir != 0 && newDir != curDir;
            curDir = newDir;
            warm   = true;

            AlwaysInDir[0] = curDir;
            FlipBar[0]     = flip ? 1 : 0;

            // Ribbon (subpanel): solid green/red by current state
            Values[0][0]      = 1;
            PlotBrushes[0][0] = curDir >= 0 ? ribbonGreen : ribbonRed;

            // Racing stripe on the price panel for flip bars
            if (ShowRacingStripes && flip)
                BackBrushes[0] = curDir >= 0 ? stripeGreen : stripeRed;

            if (WriteCsv && flip)
                WriteFlipRow(zscore, emaFast, mid);
        }

        // ── CSV ───────────────────────────────────────────────────────────────
        private void EnsureCsvHeader()
        {
            if (!WriteCsv || headerWritten || string.IsNullOrEmpty(CsvPath)) return;
            try
            {
                string dir = Path.GetDirectoryName(CsvPath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                    Directory.CreateDirectory(dir);
                csvWriter     = new StreamWriter(CsvPath, false);
                headerWritten = true;
                csvWriter.WriteLine("Event,BarTime,BarNum,NewDir,Open,High,Low,Close,EmaFast,Mid,ZScore");
                csvWriter.Flush();
            }
            catch (Exception ex) { Print("AlwaysIn CSV header error: " + ex.Message); }
        }

        private void WriteFlipRow(double zscore, double emaFast, double mid)
        {
            if (csvWriter == null) return;
            try
            {
                int barnum = Bars.BarsSinceNewTradingDay + 1;
                csvWriter.WriteLine(string.Format(
                    "FLIP,{0},{1},{2},{3:F2},{4:F2},{5:F2},{6:F2},{7:F2},{8:F2},{9:F3}",
                    Time[0].ToString("yyyy-MM-dd HH:mm:ss"),
                    barnum,
                    curDir > 0 ? "LONG" : "SHORT",
                    Open[0], High[0], Low[0], Close[0],
                    emaFast, mid, zscore));
                csvWriter.Flush();
            }
            catch (Exception ex) { Print("AlwaysIn CSV row error: " + ex.Message); }
        }

        private void CloseCsv()
        {
            if (csvWriter == null) return;
            try { csvWriter.Flush(); csvWriter.Close(); } catch { }
            csvWriter = null;
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Fast EMA Period", GroupName = "Logic", Order = 1)]
        public int FastEmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(2, int.MaxValue)]
        [Display(Name = "Z-Score Period", GroupName = "Logic", Order = 2)]
        public int ZScorePeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, double.MaxValue)]
        [Display(Name = "Z-Score Threshold (big bar)", GroupName = "Logic", Order = 3)]
        public double ZScoreThreshold { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Midpoint uses OHLC4 (else HL2)", GroupName = "Logic", Order = 4)]
        public bool MidpointUsesOHLC { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Racing Stripes (flip bars)", GroupName = "Visual", Order = 1)]
        public bool ShowRacingStripes { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Racing Stripe Opacity (%)", GroupName = "Visual", Order = 2)]
        public int RacingStripeOpacity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Write CSV", GroupName = "CSV", Order = 1)]
        public bool WriteCsv { get; set; }

        [Display(Name = "CSV Path", GroupName = "CSV", Order = 2)]
        public string CsvPath { get; set; }
        #endregion
    }
}
