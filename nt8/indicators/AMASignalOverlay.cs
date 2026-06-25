#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows.Media;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// ─────────────────────────────────────────────────────────────────────────────
// AMASignalOverlay — overlays Python-generated AMA Breakouts PB6 signals on
// an NT8 chart.
//
// Racing stripe colors (selectable via ColorMode):
//   Direction : Long = CornflowerBlue  /  Short = Tomato
//   Type      : BO = DodgerBlue / FT = DeepSkyBlue / OB = MediumPurple / BigBO = Goldenrod
//   Outcome   : Win = LimeGreen / Loss = Crimson / Open = Gray
//
// Top-right legend explains the active color scheme.
//
// NT8 Data Box — 23 invisible plots split into 6 toggleable groups:
//   ShowID      Date / Time / Bar#
//   ShowSetup   BO+FT / Long / Day#
//   ShowBars    SBrange / EBrange
//   ShowStop    BarExtreme / BarExt / Offset / Stop
//   ShowTarget  BarRange / TgtPts / Mult / Target
//   ShowResult  PnL_R
//
// Expected data box output for a BO+FT Long on 2024-06-26 09:25:
//   Date       20240626
//   Time           9.25     ← H.MM  (09:25 = 9.25)
//   Bar#          66671
//   BO+FT             1
//   Long              1
//   Day#              4
//   SBrange        5.25
//   EBrange       10.75
//   BarExtreme        1
//   BarExt       5529.25
//   Offset(t)         1
//   Stop         5529.00
//   BarRange          1
//   TgtPts         5.25
//   Mult           1.00
//   Target       5538.25
//   PnL_R          (NaN — hidden until results loaded)
//
// CSV format (scripts/ama_export_signals_nt.py):
//   0 SignalNum  4 EntryBarNum   8 StopPrice   12 SBRange  16 FilterStatus
//   1 SignalType  5 SignalPrice   9 TargetMode  13 EBRange
//   2 Direction   6 StopMode    10 TargetMult  14 PnL_R
//   3 SignalDT    7 StopOffset  11 TargetPts   15 Date
//
// CSV file: %USERPROFILE%\Documents\NinjaTrader 8\{SignalFileName}
// Commit CS to: repo/nt8/indicators/AMASignalOverlay.cs
// ─────────────────────────────────────────────────────────────────────────────

namespace NinjaTrader.NinjaScript.Indicators
{
    public class AMASignalOverlay : Indicator
    {
        // ── Signal record ─────────────────────────────────────────────────────
        private class Sig
        {
            public int    Num;
            public int    DayNum;       // per-calendar-day sequential (computed in LoadSignals)
            public string Type;         // "BO" / "BO+FT" / "OB" / "BigBO" / "CX"
            public int    Dir;          // 1 = Long, -1 = Short
            public double SignalPrice;
            public double StopPrice;
            public double TargetPrice;
            public double TargetPts;
            public double StopPts;
            public string StopMode;
            public int    StopOffset;
            public string TargetMode;
            public double TargetMult;
            public double EBRange;      // entry bar H-L from CSV (NaN if not yet present)
            public double PnL_R;
            public bool   IsWinner;
        }

        private Dictionary<DateTime, Sig> _sigs = new Dictionary<DateTime, Sig>();

        // ── Plot indices — 23 total, invisible on chart, visible in data box ──
        // Group: Identity
        private const int P_DATE    =  0;  // "Date"           YYYYMMDD
        private const int P_TIME    =  1;  // "Time"           H.MM  (09:25 = 9.25)
        private const int P_BARNUM  =  2;  // "Bar#"           NT8 CurrentBar + 1
        // Group: Setup (mutually exclusive — only the active one shows)
        private const int P_BO      =  3;  // "BO"
        private const int P_FT      =  4;  // "BO+FT"
        private const int P_OB      =  5;  // "OB"
        private const int P_BBO     =  6;  // "BigBO"
        // Group: Direction (mutually exclusive)
        private const int P_LONG    =  7;  // "Long"
        private const int P_SHORT   =  8;  // "Short"
        private const int P_DAYNUM  =  9;  // "Day#"
        // Group: Bar geometry
        private const int P_SBRANGE = 10;  // "SBrange"
        private const int P_EBRANGE = 11;  // "EBrange"
        // Group: Stop (mode mutually exclusive)
        private const int P_SM_BARXT= 12;  // "BarExtreme"
        private const int P_SM_BODY = 13;  // "BodyExtreme"
        private const int P_BAREXT  = 14;  // "BarExt"         raw extreme pre-offset
        private const int P_OFF     = 15;  // "Offset(t)"
        private const int P_STOP    = 16;  // "Stop"
        // Group: Target (mode mutually exclusive)
        private const int P_TM_BRRNG= 17;  // "BarRange"
        private const int P_TM_BODY = 18;  // "BodyRange"
        private const int P_TPTS    = 19;  // "TgtPts"
        private const int P_MULT    = 20;  // "Mult"
        private const int P_TARGET  = 21;  // "Target"
        // Group: Result
        private const int P_PNL     = 22;  // "PnL_R"
        private const int NUM_PLOTS  = 23;

        // ── Parameters ────────────────────────────────────────────────────────
        [NinjaScriptProperty]
        [Display(Name = "Signal file", GroupName = "Source", Order = 1,
                 Description = "Filename in Documents\\NinjaTrader 8 folder")]
        public string SignalFileName { get; set; }

        // Signal type filters
        [NinjaScriptProperty]
        [Display(Name = "Show BO",    GroupName = "Filters", Order = 10)]
        public bool ShowBO { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show BO+FT", GroupName = "Filters", Order = 11)]
        public bool ShowFT { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show OB",    GroupName = "Filters", Order = 12)]
        public bool ShowOB { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show BigBO", GroupName = "Filters", Order = 13)]
        public bool ShowBigBO { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Outcome filter", GroupName = "Filters", Order = 14)]
        public OutcomeFilter OutcomeMode { get; set; }

        // Chart display
        [NinjaScriptProperty]
        [Display(Name = "Stripe color mode", GroupName = "Display", Order = 20)]
        public StripeColorMode ColorMode { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Stripe opacity %", GroupName = "Display", Order = 21)]
        public int StripeOpacity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show labels", GroupName = "Display", Order = 22)]
        public bool ShowLabels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Label offset (ticks)", GroupName = "Display", Order = 23)]
        public int LabelOffsetTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show stop dash", GroupName = "Display", Order = 24)]
        public bool ShowStopDash { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show target dash", GroupName = "Display", Order = 25)]
        public bool ShowTargetDash { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Dash width (bars)", GroupName = "Display", Order = 26)]
        public int DashWidthBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show entry dot", GroupName = "Display", Order = 27)]
        public bool ShowEntryDot { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show legend", GroupName = "Display", Order = 28)]
        public bool ShowLegend { get; set; }

        // Data box section toggles
        [NinjaScriptProperty]
        [Display(Name = "Show ID (Date/Time/Bar#)", GroupName = "Data Box", Order = 40)]
        public bool DBShowID { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Setup (type/dir/Day#)", GroupName = "Data Box", Order = 41)]
        public bool DBShowSetup { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Bar geometry (SB/EB range)", GroupName = "Data Box", Order = 42)]
        public bool DBShowBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Stop details", GroupName = "Data Box", Order = 43)]
        public bool DBShowStop { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Target details", GroupName = "Data Box", Order = 44)]
        public bool DBShowTarget { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show PnL_R", GroupName = "Data Box", Order = 45)]
        public bool DBShowResult { get; set; }

        // ── Enums ─────────────────────────────────────────────────────────────
        public enum OutcomeFilter   { All, WinnersOnly, LosersOnly }
        public enum StripeColorMode { Direction, Type, Outcome }

        // ── Lifecycle ─────────────────────────────────────────────────────────
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Overlays Python-generated AMA Breakouts signals on the chart.";
                Name        = "AMASignalOverlay";
                IsOverlay   = true;
                IsSuspendedWhileInactive = true;

                // ── 23 invisible data-box plots ────────────────────────────────
                // Transparent brush = not drawn on chart.
                // NT8 hides NaN-valued plots in the data box automatically.
                // Only non-NaN plots appear, so mutually exclusive groups show one entry.
                // Identity:
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Date");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Time");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Bar#");
                // Setup type (only active one gets value 1):
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BO");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BO+FT");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "OB");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BigBO");
                // Direction (only active one gets value 1):
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Long");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Short");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Day#");
                // Bar geometry:
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "SBrange");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "EBrange");
                // Stop (mode mutually exclusive):
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BarExtreme");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BodyExtreme");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BarExt");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Offset(t)");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Stop");
                // Target (mode mutually exclusive):
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BarRange");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "BodyRange");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "TgtPts");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Mult");
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "Target");
                // Result:
                AddPlot(new Stroke(Brushes.Transparent, 0), PlotStyle.Block, "PnL_R");

                // Defaults
                SignalFileName   = "ama_signals_default.csv";
                ShowBO           = true;
                ShowFT           = true;
                ShowOB           = true;
                ShowBigBO        = true;
                OutcomeMode      = OutcomeFilter.All;
                ColorMode        = StripeColorMode.Direction;
                StripeOpacity    = 20;
                ShowLabels       = true;
                LabelOffsetTicks = 4;
                ShowStopDash     = true;
                ShowTargetDash   = true;
                DashWidthBars    = 3;
                ShowEntryDot     = true;
                ShowLegend       = true;
                DBShowID         = true;
                DBShowSetup      = true;
                DBShowBars       = true;
                DBShowStop       = true;
                DBShowTarget     = true;
                DBShowResult     = true;
            }
            else if (State == State.DataLoaded)
            {
                LoadSignals();
            }
        }

        // ── CSV loader ────────────────────────────────────────────────────────
        private void LoadSignals()
        {
            _sigs.Clear();

            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string path = System.IO.Path.Combine(docs, "NinjaTrader 8", SignalFileName);

            if (!File.Exists(path))
            {
                Print("AMASignalOverlay: file not found — " + path);
                return;
            }

            var rawList = new List<(DateTime barOpen, Sig sig)>();
            try
            {
                var ci    = System.Globalization.CultureInfo.InvariantCulture;
                var ns    = System.Globalization.NumberStyles.Any;
                string[] lines = File.ReadAllLines(path);

                for (int li = 1; li < lines.Length; li++)
                {
                    string line = lines[li].Trim();
                    if (string.IsNullOrEmpty(line)) continue;
                    string[] f = line.Split(',');
                    if (f.Length < 12) continue;

                    var s = new Sig();
                    if (!int.TryParse(f[0].Trim(), out s.Num)) continue;
                    s.Type = f[1].Trim();
                    s.Dir  = f[2].Trim() == "Long" ? 1 : -1;

                    DateTime barOpen;
                    if (!DateTime.TryParseExact(f[3].Trim(), "yyyy-MM-dd HH:mm:ss",
                            ci, System.Globalization.DateTimeStyles.None, out barOpen))
                        if (!DateTime.TryParse(f[3].Trim(), out barOpen)) continue;

                    if (!double.TryParse(f[5].Trim(), ns, ci, out s.SignalPrice)) continue;
                    s.StopMode = f[6].Trim();
                    int.TryParse(f[7].Trim(), out s.StopOffset);
                    double.TryParse(f[8].Trim(), ns, ci, out s.StopPrice);
                    s.TargetMode = f[9].Trim();
                    double.TryParse(f[10].Trim(), ns, ci, out s.TargetMult);
                    double.TryParse(f[11].Trim(), ns, ci, out s.TargetPts);
                    s.TargetPrice = s.SignalPrice + s.Dir * s.TargetPts;
                    s.StopPts     = Math.Abs(s.SignalPrice - s.StopPrice);

                    s.EBRange = f.Length > 13 ? ParseD(f[13], ns, ci) : double.NaN;
                    double pnl = f.Length > 14 ? ParseD(f[14], ns, ci) : double.NaN;
                    s.PnL_R    = pnl;
                    s.IsWinner = !double.IsNaN(pnl) && pnl > 0;

                    if (!_sigs.ContainsKey(barOpen))
                        rawList.Add((barOpen, s));
                }
            }
            catch (Exception ex)
            {
                Print("AMASignalOverlay: load error — " + ex.Message);
                return;
            }

            // Assign per-day sequential numbers (Day#)
            var dayCounters = new Dictionary<string, int>();
            foreach (var (barOpen, s) in rawList.OrderBy(x => x.barOpen))
            {
                string dayKey = barOpen.ToString("yyyyMMdd");
                int n;
                dayCounters.TryGetValue(dayKey, out n);
                s.DayNum        = n + 1;
                dayCounters[dayKey] = s.DayNum;
                _sigs[barOpen]  = s;
            }

            Print("AMASignalOverlay: loaded " + _sigs.Count + " signals from " + SignalFileName);
        }

        private static double ParseD(string v,
            System.Globalization.NumberStyles ns,
            System.Globalization.CultureInfo ci)
        {
            double d;
            return double.TryParse(v.Trim(), ns, ci, out d) ? d : double.NaN;
        }

        // ── Bar update ────────────────────────────────────────────────────────
        protected override void OnBarUpdate()
        {
            // Reset every plot to NaN — hides all rows in data box on non-signal bars,
            // and hides toggled-off groups on signal bars.
            for (int p = 0; p < NUM_PLOTS; p++)
                Values[p][0] = double.NaN;

            DateTime t = Time[0];
            Sig s;
            if (!_sigs.TryGetValue(t, out s)) return;
            if (!ShouldShow(s)) return;

            // ── Racing stripe ──────────────────────────────────────────────────
            BackBrush = StripeColor(s);

            // ── Label ──────────────────────────────────────────────────────────
            if (ShowLabels)
            {
                double off = LabelOffsetTicks * TickSize;
                Brush  clr = s.Dir > 0 ? Brushes.CornflowerBlue : Brushes.Tomato;
                string tag = Abbrev(s.Type);
                if (s.Dir > 0)
                    Draw.Text(this, "lbl_" + CurrentBar, true, tag, 0,
                              High[0] + off, 0, clr,
                              new SimpleFont("Arial", 7), TextAlignment.Center,
                              Brushes.Transparent, Brushes.Transparent, 0);
                else
                    Draw.Text(this, "lbl_" + CurrentBar, true, tag, 0,
                              Low[0] - off, 0, clr,
                              new SimpleFont("Arial", 7), TextAlignment.Center,
                              Brushes.Transparent, Brushes.Transparent, 0);
            }

            // ── Entry dot on fill bar ──────────────────────────────────────────
            if (ShowEntryDot)
                Draw.Diamond(this, "ent_" + CurrentBar, false, -1, s.SignalPrice,
                             s.Dir > 0 ? Brushes.CornflowerBlue : Brushes.Tomato);

            // ── Stop dash ─────────────────────────────────────────────────────
            if (ShowStopDash && s.StopPts > 0)
                Draw.Line(this, "stp_" + CurrentBar, false,
                          DashWidthBars, s.StopPrice, 0, s.StopPrice,
                          Brushes.Crimson, DashStyleHelper.Dash, 1);

            // ── Target dash ───────────────────────────────────────────────────
            if (ShowTargetDash && s.TargetPts > 0)
                Draw.Line(this, "tgt_" + CurrentBar, false,
                          DashWidthBars, s.TargetPrice, 0, s.TargetPrice,
                          Brushes.LimeGreen, DashStyleHelper.Dash, 1);

            // ── Data box plots ─────────────────────────────────────────────────
            // Each group only sets values if its toggle is on.
            // Mutually exclusive plots: set exactly one to 1, leave others NaN.

            // Identity group
            if (DBShowID)
            {
                DateTime dt  = Time[0];
                // Date as YYYYMMDD integer (e.g. 20240626)
                Values[P_DATE  ][0] = dt.Year * 10000 + dt.Month * 100 + dt.Day;
                // Time as H.MM decimal (09:25 → 9.25, 14:05 → 14.05)
                Values[P_TIME  ][0] = dt.Hour + dt.Minute / 100.0;
                Values[P_BARNUM][0] = CurrentBar + 1;
            }

            // Setup group
            if (DBShowSetup)
            {
                switch (s.Type)
                {
                    case "BO":    Values[P_BO ][0] = 1; break;
                    case "BO+FT": Values[P_FT ][0] = 1; break;
                    case "OB":    Values[P_OB ][0] = 1; break;
                    case "BigBO": Values[P_BBO][0] = 1; break;
                }
                if (s.Dir > 0) Values[P_LONG ][0] = 1;
                else           Values[P_SHORT][0] = 1;
                Values[P_DAYNUM][0] = s.DayNum;
            }

            // Bar geometry group
            if (DBShowBars)
            {
                Values[P_SBRANGE][0] = Math.Round(High[0] - Low[0], 2);
                Values[P_EBRANGE][0] = double.IsNaN(s.EBRange)
                                       ? double.NaN
                                       : Math.Round(s.EBRange, 2);
            }

            // Stop group
            if (DBShowStop)
            {
                // Raw bar extreme before offset:
                //   Long:  BarExt = Stop + offset*tick
                //   Short: BarExt = Stop - offset*tick
                double barExt = s.StopPrice + s.Dir * s.StopOffset * TickSize;
                if (s.StopMode == "BarExtreme") Values[P_SM_BARXT][0] = 1;
                else                            Values[P_SM_BODY ][0] = 1;
                Values[P_BAREXT][0] = Math.Round(barExt, 2);
                Values[P_OFF   ][0] = s.StopOffset;
                Values[P_STOP  ][0] = s.StopPrice;
            }

            // Target group
            if (DBShowTarget)
            {
                if (s.TargetMode == "BarRange") Values[P_TM_BRRNG][0] = 1;
                else                            Values[P_TM_BODY ][0] = 1;
                Values[P_TPTS  ][0] = Math.Round(s.TargetPts, 2);
                Values[P_MULT  ][0] = s.TargetMult;
                Values[P_TARGET][0] = s.TargetPrice;
            }

            // Result group
            if (DBShowResult)
                Values[P_PNL][0] = double.IsNaN(s.PnL_R)
                                   ? double.NaN
                                   : Math.Round(s.PnL_R, 2);
        }

        // ── Legend ────────────────────────────────────────────────────────────
        protected override void OnRender(ChartControl cc, ChartScale cs)
        {
            if (!ShowLegend) return;

            string legend;
            switch (ColorMode)
            {
                case StripeColorMode.Direction:
                    legend = "AMA Signals\n"
                           + "Blue   = Long\n"
                           + "Orange = Short";
                    break;
                case StripeColorMode.Type:
                    legend = "AMA Signals\n"
                           + "DodgerBlue  = BO\n"
                           + "DeepSkyBlue = BO+FT\n"
                           + "Purple      = OB\n"
                           + "Goldenrod   = BigBO";
                    break;
                default:
                    legend = "AMA Signals\n"
                           + "Green = Winner\n"
                           + "Red   = Loser\n"
                           + "Gray  = Open";
                    break;
            }

            Draw.TextFixed(this, "ama_legend", legend, TextPosition.TopRight,
                           Brushes.WhiteSmoke, new SimpleFont("Consolas", 9),
                           Brushes.Transparent, Brushes.DimGray, 60);
        }

        // ── Helpers ───────────────────────────────────────────────────────────
        private bool ShouldShow(Sig s)
        {
            switch (s.Type)
            {
                case "BO":    if (!ShowBO)    return false; break;
                case "BO+FT": if (!ShowFT)    return false; break;
                case "OB":    if (!ShowOB)    return false; break;
                case "BigBO": if (!ShowBigBO) return false; break;
            }
            if (OutcomeMode == OutcomeFilter.WinnersOnly
                && (double.IsNaN(s.PnL_R) || !s.IsWinner)) return false;
            if (OutcomeMode == OutcomeFilter.LosersOnly
                && (double.IsNaN(s.PnL_R) ||  s.IsWinner)) return false;
            return true;
        }

        private static string Abbrev(string type)
        {
            switch (type)
            {
                case "BO":      return "BO";
                case "BO+FT":   return "FT";
                case "OB":      return "OB";
                case "BigBO":   return "BBO";
                case "CX":      return "CX";
                case "OB_Doji": return "DOJ";
                default:        return type.Length > 4 ? type.Substring(0, 4) : type;
            }
        }

        private Brush StripeColor(Sig s)
        {
            byte a = (byte)(255 * StripeOpacity / 100f);

            if (ColorMode == StripeColorMode.Outcome)
            {
                if (double.IsNaN(s.PnL_R))
                    return new SolidColorBrush(Color.FromArgb(a, 128, 128, 128));
                return s.IsWinner
                    ? new SolidColorBrush(Color.FromArgb(a, 50,  205, 50 ))
                    : new SolidColorBrush(Color.FromArgb(a, 220, 20,  60 ));
            }

            if (ColorMode == StripeColorMode.Type)
            {
                switch (s.Type)
                {
                    case "BO":    return new SolidColorBrush(Color.FromArgb(a, 30,  144, 255));
                    case "BO+FT": return new SolidColorBrush(Color.FromArgb(a, 0,   191, 255));
                    case "OB":    return new SolidColorBrush(Color.FromArgb(a, 147, 112, 219));
                    case "BigBO": return new SolidColorBrush(Color.FromArgb(a, 218, 165, 32 ));
                    default:      return new SolidColorBrush(Color.FromArgb(a, 169, 169, 169));
                }
            }

            return s.Dir > 0
                ? new SolidColorBrush(Color.FromArgb(a, 100, 149, 237))
                : new SolidColorBrush(Color.FromArgb(a, 255, 99,  71 ));
        }
    }
}
