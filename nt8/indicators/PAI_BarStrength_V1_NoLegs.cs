#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using System.Xml.Serialization;
using System.Windows.Media;
#endregion

// ============================================================================
// Price Action AI - V1
// BarStrength only
// CSV export only
// Bar-close only
// ============================================================================
public enum SessionTemplateOption
{
    None,
    CME_US_Index_Futures_RTH,
    CME_US_Index_Futures_ETH
}
namespace NinjaTrader.NinjaScript.Indicators
{
    [Category("00 Price Action AI")]
	public class PAI_BarStrength_V1 : Indicator
    {
        // ====================================================================
        // SECTION 1: CONSTANTS
        // ====================================================================

        // Fixed indicator version string for CSV export and debugging
        private const string InternalIndicatorVersion = "1.7";

        // Fixed V1 heuristic weights for BarStrengthScore
        // These are intentionally fixed for V1 because all raw inputs are exported.
        // Later AI / Sheets analysis can determine better weights.
        private const double BodyWeight = 0.50;
        private const double CloseWeight = 0.35;
        private const double OppTailWeight = 0.15;

        // Neutral fallback values / safeguards
        private const double MinRangeFallback = 0.0000001;

        // ====================================================================
        // SECTION 2: USER PROPERTIES
        // ====================================================================

        // ------------------------------
        // General
        // ------------------------------

        [NinjaScriptProperty]
        [Display(Name = "Enable BarStrength", Order = 1, GroupName = "General")]
        public bool EnableBarStrength { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Leg Lines", Order = 2, GroupName = "General")]
        public bool ShowLegLines { get; set; }

        // ------------------------------
        // CSV Export
        // ------------------------------

        [NinjaScriptProperty]
        [Display(Name = "Enable CSV Export", Order = 1, GroupName = "CSV Export")]
        public bool EnableCsvExport { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CSV File Path", Order = 2, GroupName = "CSV Export")]
        public string CsvFilePath { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export Start Date", Order = 3, GroupName = "CSV Export")]
        public DateTime ExportStartDate { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export End Date", Order = 4, GroupName = "CSV Export")]
        public DateTime ExportEndDate { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export Session Template (optional exact match)", Order = 5, GroupName = "CSV Export")]
        public SessionTemplateOption ExportSessionTemplate { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Use Export Time Offset", Order = 6, GroupName = "CSV Export")]
        public bool UseExportTimeOffset { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export Time Offset Hours", Order = 7, GroupName = "CSV Export")]
        public int ExportTimeOffsetHours { get; set; }

        // ------------------------------
        // BarStrength Metric
        // ------------------------------

        [NinjaScriptProperty]
        [Display(Name = "BarStrength Include In CSV", Order = 1, GroupName = "BarStrength Metric")]
        public bool BarStrengthIncludeInCsv { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BarStrength CSV Order", Order = 2, GroupName = "BarStrength Metric")]
        public int BarStrengthCsvOrder { get; set; }

        // ====================================================================
        // SECTION 3: INTERNAL STATE
        // ====================================================================

        // ------------------------------
        // Runtime current-bar values
        // ------------------------------

        // Raw BarStrength components for the current completed bar
		private double currentBarRange;
		private double currentBodySize;
        private double currentBodyPctRaw;
        private double currentCloseStrengthPctRaw;
        private double currentOppTailPctRaw;
		private double currentOverlapPctRaw;
		private double currentOverlapScore;
		private double currentContinuationPullbackDepthPctRaw;
        private int currentBarDirection;
        private int currentBarType;
        private double currentABR8;
        private double currentAvgBarRange8;
        private double currentBreakoutDisplacement;
        private int currentBreakoutGapScore;
        private int currentConsecutiveTrendBars;
        private double currentBarUniformity;
        private double currentTailSuppressionScore;
        private int currentConsecutiveBreakoutCloses;
        private double currentTrendEfficiency;
        private double currentBarStrengthScore;

        // ------------------------------
        // Historical series storage
        // ------------------------------

        private Series<double> bodyPctRawSeries;
        private Series<double> closeStrengthPctRawSeries;
        private Series<double> oppTailPctRawSeries;
		private Series<double> overlapPctRawSeries;
		private Series<double> overlapScoreSeries;
		private Series<double> continuationPullbackDepthPctRawSeries;
        private Series<double> barDirectionSeries;
        private Series<double> abr8Series;
        private Series<double> avgBarRange8Series;
        private Series<double> breakoutDisplacementSeries;
        private Series<double> breakoutGapScoreSeries;
        private Series<double> barTypeSeries;
        private Series<double> consecutiveTrendBarsSeries;
        private Series<double> barUniformitySeries;
        private Series<double> tailSuppressionScoreSeries;
        private Series<double> consecutiveBreakoutClosesSeries;
        private Series<double> trendEfficiencySeries;
        private Series<double> barStrengthScoreSeries;

        // ------------------------------
        // Session/export bookkeeping
        // ------------------------------

        private SessionIterator sessionIterator;
        private int barNumberInSession;
        private DateTime currentSessionDate;
        private string cachedInstrumentName;
        private string cachedTimeframeName;
        private string cachedSessionTemplateName;

        // ------------------------------
        // CSV writer state
        // ------------------------------

        private StreamWriter csvWriter;
        private bool csvHeaderWritten;
        private bool csvReady;

        // ====================================================================
        // SECTION 4: NINJATRADER STATE MACHINE
        // ====================================================================

        protected override void OnStateChange()
        {
            // ------------------------------------------------------------
            // SetDefaults
            // ------------------------------------------------------------
            if (State == State.SetDefaults)
            {
                Name = "PAI_BarStrength";
                Description = "Price Action AI V1 - CSV export only, bar-close only.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;
                DisplayInDataBox = false;
                DrawOnPricePanel = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
				AddPlot(Brushes.DodgerBlue, "BarStrength");

                // General defaults
                EnableBarStrength = true;
                ShowLegLines = false;

                // CSV export defaults
                EnableCsvExport = true;
                CsvFilePath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "PriceActionAI_BarStrength_V1.csv");

				ExportStartDate = DateTime.Today;
				ExportEndDate = DateTime.Today;
                ExportSessionTemplate = SessionTemplateOption.None;
                UseExportTimeOffset = false;
                ExportTimeOffsetHours = 0;

                // Metric export defaults
                BarStrengthIncludeInCsv = true;
                BarStrengthCsvOrder = 1;
            }
            // ------------------------------------------------------------
            // DataLoaded
            // ------------------------------------------------------------
            else if (State == State.DataLoaded)
            {
                sessionIterator = new SessionIterator(Bars);

                bodyPctRawSeries = new Series<double>(this);
				closeStrengthPctRawSeries = new Series<double>(this);
				oppTailPctRawSeries = new Series<double>(this);
				overlapPctRawSeries = new Series<double>(this);
				overlapScoreSeries = new Series<double>(this);
				continuationPullbackDepthPctRawSeries = new Series<double>(this);
				barDirectionSeries = new Series<double>(this);
				barTypeSeries = new Series<double>(this);
				abr8Series = new Series<double>(this);
				avgBarRange8Series = new Series<double>(this);
				breakoutDisplacementSeries = new Series<double>(this);
				breakoutGapScoreSeries = new Series<double>(this);
				consecutiveTrendBarsSeries = new Series<double>(this);
				barUniformitySeries = new Series<double>(this);
				tailSuppressionScoreSeries = new Series<double>(this);
				consecutiveBreakoutClosesSeries = new Series<double>(this);
				trendEfficiencySeries = new Series<double>(this);
				barStrengthScoreSeries = new Series<double>(this);

                cachedInstrumentName = Instrument != null ? Instrument.FullName : string.Empty;
                cachedTimeframeName = BuildTimeframeName();
                cachedSessionTemplateName = Bars != null && Bars.TradingHours != null
                    ? Bars.TradingHours.Name
                    : string.Empty;

                barNumberInSession = 0;
                currentSessionDate = Core.Globals.MinDate;

                InitializeCsv();
            }
            // ------------------------------------------------------------
            // Terminated
            // ------------------------------------------------------------
            else if (State == State.Terminated)
            {
                CloseCsv();
            }
        }

        // ====================================================================
        // SECTION 5: MAIN BAR-CLOSE EXECUTION FLOW
        // ====================================================================

        protected override void OnBarUpdate()
        {
            if (!EnableBarStrength)
                return;

            if (CurrentBar < 0)
                return;

            // ------------------------------------------------------------
            // Session bookkeeping
            // ------------------------------------------------------------

            if (Bars.IsFirstBarOfSession)
                barNumberInSession = 1;
            else
                barNumberInSession++;

            currentSessionDate = sessionIterator.GetTradingDay(Time[0]);

            // ------------------------------------------------------------
			// Calculate metrics for the current completed bar
			// ------------------------------------------------------------
			CalculateBarStrengthForCurrentBar();
			CalculateOverlapForCurrentBar();
			CalculateContinuationPullbackDepthForCurrentBar();
            CalculateABR8ForCurrentBar();
            CalculateAvgBarRange8ForCurrentBar();
            CalculateBreakoutDisplacementForCurrentBar();
            CalculateBreakoutGapScoreForCurrentBar();
            CalculateBarTypeForCurrentBar();
            CalculateConsecutiveTrendBarsForCurrentBar();
            CalculateBarUniformityForCurrentBar();
            CalculateTailSuppressionScoreForCurrentBar();
            CalculateConsecutiveBreakoutClosesForCurrentBar();
            CalculateTrendEfficiencyForCurrentBar();

            // ------------------------------------------------------------
            // Store results in series
            // ------------------------------------------------------------
            bodyPctRawSeries[0] = currentBodyPctRaw;
			closeStrengthPctRawSeries[0] = currentCloseStrengthPctRaw;
			oppTailPctRawSeries[0] = currentOppTailPctRaw;
			overlapPctRawSeries[0] = currentOverlapPctRaw;
			overlapScoreSeries[0] = currentOverlapScore;
			continuationPullbackDepthPctRawSeries[0] = currentContinuationPullbackDepthPctRaw;
			barDirectionSeries[0] = currentBarDirection;
            barTypeSeries[0] = currentBarType;
            abr8Series[0] = currentABR8;
            avgBarRange8Series[0] = currentAvgBarRange8;
            breakoutDisplacementSeries[0] = currentBreakoutDisplacement;
            breakoutGapScoreSeries[0] = currentBreakoutGapScore;
            consecutiveTrendBarsSeries[0] = currentConsecutiveTrendBars;
            barUniformitySeries[0] = currentBarUniformity;
            tailSuppressionScoreSeries[0] = currentTailSuppressionScore;
            consecutiveBreakoutClosesSeries[0] = currentConsecutiveBreakoutCloses;
            trendEfficiencySeries[0] = currentTrendEfficiency;
			barStrengthScoreSeries[0] = currentBarStrengthScore;

            // ------------------------------------------------------------
            // CSV export for this completed bar only
            // ------------------------------------------------------------
            if (EnableCsvExport && csvReady && IsBarEligibleForExport(Time[0]))
                WriteCsvRowForCurrentBar();
        }

        // ====================================================================
        // SECTION 6: BARSTRENGTH CALCULATION HELPERS
        // ====================================================================

        private void CalculateBarStrengthForCurrentBar()
        {
            double open = Open[0];
            double high = High[0];
            double low = Low[0];
            double close = Close[0];

			currentBarRange = high - low;
			currentBodySize = Math.Abs(close - open);
			
			double safeBarRange = GetSafeBarRange(high, low);
			
			// 1) BodyPctRaw
			currentBodyPctRaw = currentBodySize / safeBarRange;

            // 2) CloseStrengthPctRaw
            double bullClosePct = (close - low) / safeBarRange;
			double bearClosePct = (high - close) / safeBarRange;
            currentCloseStrengthPctRaw = Math.Max(bullClosePct, bearClosePct);

            // 3) BarDirection
            if (close > open)
                currentBarDirection = 1;
            else if (close < open)
                currentBarDirection = -1;
            else
                currentBarDirection = 0;

            // 4) OppTailPctRaw
            if (currentBarDirection >= 0)
                currentOppTailPctRaw = (Math.Min(open, close) - low) / safeBarRange;
            else
                currentOppTailPctRaw = (high - Math.Max(open, close)) / safeBarRange;

            currentOppTailPctRaw = Clamp01(currentOppTailPctRaw);

            // 5) Composite BarStrength score
            double barStrengthRaw =
                BodyWeight * currentBodyPctRaw
                + CloseWeight * currentCloseStrengthPctRaw
                + OppTailWeight * (1.0 - currentOppTailPctRaw);

            currentBarStrengthScore = 100.0 * Clamp01(barStrengthRaw);
        }

        private void CalculateOverlapForCurrentBar()
        {
            if (CurrentBar < 1)
            {
                currentOverlapPctRaw = 0.0;
                currentOverlapScore = 0.0;
                return;
            }

            double currentHigh = High[0];
            double currentLow = Low[0];
            double priorHigh = High[1];
            double priorLow = Low[1];

            double overlapAmount = Math.Max(0.0, Math.Min(currentHigh, priorHigh) - Math.Max(currentLow, priorLow));

            double currentSafeRange = GetSafeBarRange(currentHigh, currentLow);
            double priorSafeRange = GetSafeBarRange(priorHigh, priorLow);
            double minSafeRange = Math.Min(currentSafeRange, priorSafeRange);

            currentOverlapPctRaw = Clamp01(overlapAmount / minSafeRange);
            currentOverlapScore = 100.0 * (1.0 - currentOverlapPctRaw);
        }

        private void CalculateContinuationPullbackDepthForCurrentBar()
        {
            if (CurrentBar < 1)
            {
                currentContinuationPullbackDepthPctRaw = 0.0;
                return;
            }

            double currentClose = Close[0];
            double priorClose = Close[1];
            double currentHigh = High[0];
            double currentLow = Low[0];
            double priorHigh = High[1];
            double priorLow = Low[1];

            double priorSafeRange = GetSafeBarRange(priorHigh, priorLow);

            if (currentClose > priorClose)
            {
                double pullbackAmount = priorHigh - currentLow;
                currentContinuationPullbackDepthPctRaw = Clamp01(pullbackAmount / priorSafeRange);
                return;
            }

            if (currentClose < priorClose)
            {
                double pullbackAmount = currentHigh - priorLow;
                currentContinuationPullbackDepthPctRaw = Clamp01(pullbackAmount / priorSafeRange);
                return;
            }

            currentContinuationPullbackDepthPctRaw = 0.0;
        }

        private void CalculateABR8ForCurrentBar()
        {
            if (CurrentBar < 7)
            {
                currentABR8 = 0.0;
                return;
            }

            double sum = 0.0;

            for (int i = 0; i < 8; i++)
                sum += (High[i] - Low[i]);

            currentABR8 = sum / 8.0;
        }

        private void CalculateAvgBarRange8ForCurrentBar()
        {
            currentAvgBarRange8 = currentABR8;
        }

        private void CalculateBreakoutDisplacementForCurrentBar()
        {
            if (currentABR8 <= 0.0)
            {
                currentBreakoutDisplacement = 0.0;
                return;
            }

            currentBreakoutDisplacement = currentBarRange / currentABR8;
        }

        private void CalculateBreakoutGapScoreForCurrentBar()
        {
            if (CurrentBar < 1)
            {
                currentBreakoutGapScore = 0;
                return;
            }

            bool bullTickGap = Low[0] > High[1];
            bool bearTickGap = High[0] < Low[1];

            bool bullMicroGap = CurrentBar >= 2 && Low[0] > High[2];
            bool bearMicroGap = CurrentBar >= 2 && High[0] < Low[2];

            if (bullTickGap && bullMicroGap)
            {
                currentBreakoutGapScore = 3;
                return;
            }

            if (bearTickGap && bearMicroGap)
            {
                currentBreakoutGapScore = -3;
                return;
            }

            if (bullMicroGap)
            {
                currentBreakoutGapScore = 2;
                return;
            }

            if (bearMicroGap)
            {
                currentBreakoutGapScore = -2;
                return;
            }

            if (bullTickGap)
            {
                currentBreakoutGapScore = 1;
                return;
            }

            if (bearTickGap)
            {
                currentBreakoutGapScore = -1;
                return;
            }

            currentBreakoutGapScore = 0;
        }

        private void CalculateBarTypeForCurrentBar()
        {
            bool isInsideBar = CurrentBar >= 1 && High[0] <= High[1] && Low[0] >= Low[1];
            bool isOutsideBar = CurrentBar >= 1 && High[0] > High[1] && Low[0] < Low[1];

            bool isDoji = currentBodyPctRaw < 0.20 || currentBarDirection == 0;

            bool isBullClimax =
                currentBarDirection == 1 &&
                currentBreakoutDisplacement >= 1.8 &&
                currentBodyPctRaw >= 0.65 &&
                currentCloseStrengthPctRaw >= 0.75 &&
                currentOppTailPctRaw <= 0.15;

            bool isBearClimax =
                currentBarDirection == -1 &&
                currentBreakoutDisplacement >= 1.8 &&
                currentBodyPctRaw >= 0.65 &&
                currentCloseStrengthPctRaw >= 0.75 &&
                currentOppTailPctRaw <= 0.15;

            if (isDoji)            { currentBarType = 0;  return; }
            if (isBullClimax)      { currentBarType = 6;  return; }
            if (isBearClimax)      { currentBarType = -6; return; }

            if (isOutsideBar && currentBarDirection == 1)  { currentBarType = 3;  return; }
            if (isOutsideBar && currentBarDirection == -1) { currentBarType = -3; return; }
            if (isInsideBar  && currentBarDirection == 1)  { currentBarType = 2;  return; }
            if (isInsideBar  && currentBarDirection == -1) { currentBarType = -2; return; }
            if (currentBarDirection == 1)                  { currentBarType = 1;  return; }
            if (currentBarDirection == -1)                 { currentBarType = -1; return; }

            currentBarType = 0;
        }

        private void CalculateConsecutiveTrendBarsForCurrentBar()
        {
            int count = 0;

            for (int i = 0; i <= CurrentBar; i++)
            {
                double open = Open[i];
                double close = Close[i];
                double high = High[i];
                double low = Low[i];

                double safeRange = GetSafeBarRange(high, low);
                double bodySize = Math.Abs(close - open);
                double bodyPct = bodySize / safeRange;

                int direction = 0;
                if (close > open)
                    direction = 1;
                else if (close < open)
                    direction = -1;

                double oppTailPct;
                if (direction >= 0)
                    oppTailPct = (Math.Min(open, close) - low) / safeRange;
                else
                    oppTailPct = (high - Math.Max(open, close)) / safeRange;

                oppTailPct = Clamp01(oppTailPct);

                bool qualifies =
                    direction != 0 &&
                    bodyPct >= 0.60 &&
                    oppTailPct <= 0.25;

                if (!qualifies)
                    break;

                if (i == 0)
                {
                    count = 1;
                    continue;
                }

                int priorDirection = 0;
                if (Close[i - 1] > Open[i - 1])
                    priorDirection = 1;
                else if (Close[i - 1] < Open[i - 1])
                    priorDirection = -1;

                if (direction != priorDirection)
                    break;

                count++;
            }

            currentConsecutiveTrendBars = count;
        }

        private void CalculateBarUniformityForCurrentBar()
        {
            if (CurrentBar < 4)
            {
                currentBarUniformity = 0.0;
                return;
            }

            double[] ranges = new double[5];
            double mean = 0.0;

            for (int i = 0; i < 5; i++)
            {
                ranges[i] = High[i] - Low[i];
                mean += ranges[i];
            }

            mean /= 5.0;

            if (mean <= 0.0)
            {
                currentBarUniformity = 0.0;
                return;
            }

            double variance = 0.0;
            for (int i = 0; i < 5; i++)
                variance += Math.Pow(ranges[i] - mean, 2.0);

            variance /= 5.0;
            double stdDev = Math.Sqrt(variance);

            currentBarUniformity = Clamp01(1.0 - (stdDev / mean));
        }

        private void CalculateTailSuppressionScoreForCurrentBar()
        {
            currentTailSuppressionScore = 100.0 * Clamp01(1.0 - currentOppTailPctRaw);
        }

        private void CalculateConsecutiveBreakoutClosesForCurrentBar()
        {
            if (CurrentBar < 1)
            {
                currentConsecutiveBreakoutCloses = 0;
                return;
            }

            int count = 0;
            int direction = currentBarDirection;

            if (direction == 0)
            {
                currentConsecutiveBreakoutCloses = 0;
                return;
            }

            for (int i = 0; i < CurrentBar; i++)
            {
                int barDirection = 0;
                if (Close[i] > Open[i])
                    barDirection = 1;
                else if (Close[i] < Open[i])
                    barDirection = -1;

                if (barDirection != direction)
                    break;

                bool isBreakoutClose =
                    direction == 1
                    ? Close[i] > High[i + 1]
                    : Close[i] < Low[i + 1];

                if (!isBreakoutClose)
                    break;

                count++;
            }

            currentConsecutiveBreakoutCloses = count;
        }

        private void CalculateTrendEfficiencyForCurrentBar()
        {
            if (CurrentBar < 5)
            {
                currentTrendEfficiency = 0.0;
                return;
            }

            int lookback = Math.Min(10, CurrentBar);

            double netMove = Math.Abs(Close[0] - Close[lookback]);
            double totalMove = 0.0;

            for (int i = 0; i < lookback; i++)
                totalMove += Math.Abs(Close[i] - Close[i + 1]);

            if (totalMove <= 0.0)
            {
                currentTrendEfficiency = 0.0;
                return;
            }

            currentTrendEfficiency = Clamp01(netMove / totalMove);
        }

        // Returns a safe non-zero bar range.
        private double GetSafeBarRange(double high, double low)
        {
            double rawRange = high - low;

            if (TickSize > 0)
                return Math.Max(rawRange, TickSize);

            return Math.Max(rawRange, MinRangeFallback);
        }

        // Simple clamp helper for normalized values.
        private double Clamp01(double value)
        {
            if (value < 0.0) return 0.0;
            if (value > 1.0) return 1.0;
            return value;
        }

        // ====================================================================
        // SECTION 7: CSV INITIALIZATION / FILTER HELPERS
        // ====================================================================

        private void InitializeCsv()
        {
            csvReady = false;
            csvHeaderWritten = false;

            if (!EnableCsvExport)
                return;

            try
            {
                if (string.IsNullOrWhiteSpace(CsvFilePath))
                    return;

                string directory = Path.GetDirectoryName(CsvFilePath);

                if (string.IsNullOrWhiteSpace(directory))
                    return;

                if (!Directory.Exists(directory))
                    Directory.CreateDirectory(directory);

                csvWriter = new StreamWriter(CsvFilePath, false);
                csvWriter.AutoFlush = true;

                WriteCsvHeader();
                csvReady = true;
            }
            catch
            {
                csvReady = false;
            }
        }

        private void CloseCsv()
        {
            try
            {
                if (csvWriter != null)
                {
                    csvWriter.Flush();
                    csvWriter.Close();
                    csvWriter.Dispose();
                    csvWriter = null;
                }
            }
            catch { }
        }

        private bool IsBarEligibleForExport(DateTime barTimeExchange)
        {
            DateTime barDate = barTimeExchange.Date;

            if (barDate < ExportStartDate.Date)
                return false;

            if (barDate > ExportEndDate.Date)
                return false;

            if (ExportSessionTemplate != SessionTemplateOption.None)
            {
                string expectedTemplate =
                    ExportSessionTemplate == SessionTemplateOption.CME_US_Index_Futures_RTH
                    ? "CME US Index Futures RTH"
                    : "CME US Index Futures ETH";

                if (!string.Equals(cachedSessionTemplateName, expectedTemplate, StringComparison.OrdinalIgnoreCase))
                    return false;
            }

            return true;
        }

        // ====================================================================
        // SECTION 8: CSV WRITE HELPERS
        // ====================================================================

        private void WriteCsvHeader()
        {
            if (csvWriter == null || csvHeaderWritten)
                return;

            string header =
                "BarIndex," +
                "Instrument," +
                "Timeframe," +
                "Date," +
                "Time," +
                "DateTimeExchange," +
                "DateTimeExport," +
                "UnixTime," +
                "SessionTemplate," +
                "SessionDate," +
                "ExportTimeOffsetHours," +
                "BarNumberInSession," +
                "IndicatorVersion," +
				"BarRange," +
				"BodySize," +
				"BodyPctRaw," +
				"CloseStrengthPctRaw," +
				"OppTailPctRaw," +
				"OverlapPctRaw," +
				"ContinuationPullbackDepthPctRaw," +
				"BarDirection," +
                "BarType," +
                "ABR8," +
                "AvgBarRange8," +
                "BreakoutDisplacement," +
                "BreakoutGapScore," +
                "ConsecutiveTrendBars," +
                "BarUniformity," +
                "TailSuppressionScore," +
                "ConsecutiveBreakoutCloses," +
                "TrendEfficiency," +
				"BarStrengthScore," +
				"OverlapScore";

            csvWriter.WriteLine(header);
            csvHeaderWritten = true;
        }

        private void WriteCsvRowForCurrentBar()
        {
            if (csvWriter == null)
                return;

            DateTime dateTimeExchange = Time[0];

            DateTime dateTimeExport = UseExportTimeOffset
                ? dateTimeExchange.AddHours(ExportTimeOffsetHours)
                : dateTimeExchange;

            long unixTime = ToNaiveUnixTime(dateTimeExport);

            string dateField             = dateTimeExport.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            string timeField             = dateTimeExport.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
            string dateTimeExchangeField = dateTimeExchange.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
            string dateTimeExportField   = dateTimeExport.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
            string sessionDateField      = currentSessionDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

            string row =
                CurrentBar.ToString(CultureInfo.InvariantCulture) + "," +
                EscapeCsv(cachedInstrumentName) + "," +
                EscapeCsv(cachedTimeframeName) + "," +
                dateField + "," +
                timeField + "," +
                dateTimeExchangeField + "," +
                dateTimeExportField + "," +
                unixTime.ToString(CultureInfo.InvariantCulture) + "," +
                EscapeCsv(cachedSessionTemplateName) + "," +
                sessionDateField + "," +
                ExportTimeOffsetHours.ToString(CultureInfo.InvariantCulture) + "," +
                barNumberInSession.ToString(CultureInfo.InvariantCulture) + "," +
                EscapeCsv(InternalIndicatorVersion) + "," +
				currentBarRange.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentBodySize.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentBodyPctRaw.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentCloseStrengthPctRaw.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentOppTailPctRaw.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentOverlapPctRaw.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentContinuationPullbackDepthPctRaw.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentBarDirection.ToString(CultureInfo.InvariantCulture) + "," +
                currentBarType.ToString(CultureInfo.InvariantCulture) + "," +
                currentABR8.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                currentAvgBarRange8.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                currentBreakoutDisplacement.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                currentBreakoutGapScore.ToString(CultureInfo.InvariantCulture) + "," +
                currentConsecutiveTrendBars.ToString(CultureInfo.InvariantCulture) + "," +
                currentBarUniformity.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                currentTailSuppressionScore.ToString("0.########", CultureInfo.InvariantCulture) + "," +
                currentConsecutiveBreakoutCloses.ToString(CultureInfo.InvariantCulture) + "," +
                currentTrendEfficiency.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentBarStrengthScore.ToString("0.########", CultureInfo.InvariantCulture) + "," +
				currentOverlapScore.ToString("0.########", CultureInfo.InvariantCulture);

            csvWriter.WriteLine(row);
        }

        private string EscapeCsv(string value)
        {
            if (string.IsNullOrEmpty(value))
                return string.Empty;

            if (value.Contains(",") || value.Contains("\""))
                return "\"" + value.Replace("\"", "\"\"") + "\"";

            return value;
        }

        private long ToNaiveUnixTime(DateTime dateTime)
        {
            DateTime epoch = new DateTime(1970, 1, 1);
            return Convert.ToInt64((dateTime - epoch).TotalSeconds);
        }

        // ====================================================================
        // SECTION 9: SMALL LABEL HELPERS
        // ====================================================================

        private string BuildTimeframeName()
        {
            if (BarsPeriod == null)
                return string.Empty;

            switch (BarsPeriod.BarsPeriodType)
            {
                case BarsPeriodType.Minute:
                    return BarsPeriod.Value.ToString(CultureInfo.InvariantCulture) + "m";

                case BarsPeriodType.Day:
                    return BarsPeriod.Value.ToString(CultureInfo.InvariantCulture) + "D";

                case BarsPeriodType.Week:
                    return BarsPeriod.Value.ToString(CultureInfo.InvariantCulture) + "W";

                case BarsPeriodType.Month:
                    return BarsPeriod.Value.ToString(CultureInfo.InvariantCulture) + "M";

                default:
                    return BarsPeriod.ToString();
            }
        }

        // ====================================================================
        // SECTION 10: PUBLIC ACCESSORS
        // ====================================================================

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BodyPctRawSeries
        {
            get { return bodyPctRawSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> CloseStrengthPctRawSeries
        {
            get { return closeStrengthPctRawSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> OverlapPctRawSeries
        {
            get { return overlapPctRawSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> OverlapScoreSeries
        {
            get { return overlapScoreSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> ContinuationPullbackDepthPctRawSeries
        {
            get { return continuationPullbackDepthPctRawSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> OppTailPctRawSeries
        {
            get { return oppTailPctRawSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BarDirectionSeries
        {
            get { return barDirectionSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BarTypeSeries
        {
            get { return barTypeSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> ABR8Series
        {
            get { return abr8Series; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BreakoutDisplacementSeries
        {
            get { return breakoutDisplacementSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BreakoutGapScoreSeries
        {
            get { return breakoutGapScoreSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> AvgBarRange8Series
        {
            get { return avgBarRange8Series; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> ConsecutiveTrendBarsSeries
        {
            get { return consecutiveTrendBarsSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BarUniformitySeries
        {
            get { return barUniformitySeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> TailSuppressionScoreSeries
        {
            get { return tailSuppressionScoreSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> ConsecutiveBreakoutClosesSeries
        {
            get { return consecutiveBreakoutClosesSeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> TrendEfficiencySeries
        {
            get { return trendEfficiencySeries; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> BarStrengthScoreSeries
        {
            get { return barStrengthScoreSeries; }
        }
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private PAI_BarStrength_V1[] cachePAI_BarStrength_V1;
		public PAI_BarStrength_V1 PAI_BarStrength_V1(bool enableBarStrength, bool showLegLines, bool enableCsvExport, string csvFilePath, DateTime exportStartDate, DateTime exportEndDate, SessionTemplateOption exportSessionTemplate, bool useExportTimeOffset, int exportTimeOffsetHours, bool barStrengthIncludeInCsv, int barStrengthCsvOrder)
		{
			return PAI_BarStrength_V1(Input, enableBarStrength, showLegLines, enableCsvExport, csvFilePath, exportStartDate, exportEndDate, exportSessionTemplate, useExportTimeOffset, exportTimeOffsetHours, barStrengthIncludeInCsv, barStrengthCsvOrder);
		}

		public PAI_BarStrength_V1 PAI_BarStrength_V1(ISeries<double> input, bool enableBarStrength, bool showLegLines, bool enableCsvExport, string csvFilePath, DateTime exportStartDate, DateTime exportEndDate, SessionTemplateOption exportSessionTemplate, bool useExportTimeOffset, int exportTimeOffsetHours, bool barStrengthIncludeInCsv, int barStrengthCsvOrder)
		{
			if (cachePAI_BarStrength_V1 != null)
				for (int idx = 0; idx < cachePAI_BarStrength_V1.Length; idx++)
					if (cachePAI_BarStrength_V1[idx] != null && cachePAI_BarStrength_V1[idx].EnableBarStrength == enableBarStrength && cachePAI_BarStrength_V1[idx].ShowLegLines == showLegLines && cachePAI_BarStrength_V1[idx].EnableCsvExport == enableCsvExport && cachePAI_BarStrength_V1[idx].CsvFilePath == csvFilePath && cachePAI_BarStrength_V1[idx].ExportStartDate == exportStartDate && cachePAI_BarStrength_V1[idx].ExportEndDate == exportEndDate && cachePAI_BarStrength_V1[idx].ExportSessionTemplate == exportSessionTemplate && cachePAI_BarStrength_V1[idx].UseExportTimeOffset == useExportTimeOffset && cachePAI_BarStrength_V1[idx].ExportTimeOffsetHours == exportTimeOffsetHours && cachePAI_BarStrength_V1[idx].BarStrengthIncludeInCsv == barStrengthIncludeInCsv && cachePAI_BarStrength_V1[idx].BarStrengthCsvOrder == barStrengthCsvOrder && cachePAI_BarStrength_V1[idx].EqualsInput(input))
						return cachePAI_BarStrength_V1[idx];
			return CacheIndicator<PAI_BarStrength_V1>(new PAI_BarStrength_V1(){ EnableBarStrength = enableBarStrength, ShowLegLines = showLegLines, EnableCsvExport = enableCsvExport, CsvFilePath = csvFilePath, ExportStartDate = exportStartDate, ExportEndDate = exportEndDate, ExportSessionTemplate = exportSessionTemplate, UseExportTimeOffset = useExportTimeOffset, ExportTimeOffsetHours = exportTimeOffsetHours, BarStrengthIncludeInCsv = barStrengthIncludeInCsv, BarStrengthCsvOrder = barStrengthCsvOrder }, input, ref cachePAI_BarStrength_V1);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.PAI_BarStrength_V1 PAI_BarStrength_V1(bool enableBarStrength, bool showLegLines, bool enableCsvExport, string csvFilePath, DateTime exportStartDate, DateTime exportEndDate, SessionTemplateOption exportSessionTemplate, bool useExportTimeOffset, int exportTimeOffsetHours, bool barStrengthIncludeInCsv, int barStrengthCsvOrder)
		{
			return indicator.PAI_BarStrength_V1(Input, enableBarStrength, showLegLines, enableCsvExport, csvFilePath, exportStartDate, exportEndDate, exportSessionTemplate, useExportTimeOffset, exportTimeOffsetHours, barStrengthIncludeInCsv, barStrengthCsvOrder);
		}

		public Indicators.PAI_BarStrength_V1 PAI_BarStrength_V1(ISeries<double> input , bool enableBarStrength, bool showLegLines, bool enableCsvExport, string csvFilePath, DateTime exportStartDate, DateTime exportEndDate, SessionTemplateOption exportSessionTemplate, bool useExportTimeOffset, int exportTimeOffsetHours, bool barStrengthIncludeInCsv, int barStrengthCsvOrder)
		{
			return indicator.PAI_BarStrength_V1(input, enableBarStrength, showLegLines, enableCsvExport, csvFilePath, exportStartDate, exportEndDate, exportSessionTemplate, useExportTimeOffset, exportTimeOffsetHours, barStrengthIncludeInCsv, barStrengthCsvOrder);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.PAI_BarStrength_V1 PAI_BarStrength_V1(bool enableBarStrength, bool showLegLines, bool enableCsvExport, string csvFilePath, DateTime exportStartDate, DateTime exportEndDate, SessionTemplateOption exportSessionTemplate, bool useExportTimeOffset, int exportTimeOffsetHours, bool barStrengthIncludeInCsv, int barStrengthCsvOrder)
		{
			return indicator.PAI_BarStrength_V1(Input, enableBarStrength, showLegLines, enableCsvExport, csvFilePath, exportStartDate, exportEndDate, exportSessionTemplate, useExportTimeOffset, exportTimeOffsetHours, barStrengthIncludeInCsv, barStrengthCsvOrder);
		}

		public Indicators.PAI_BarStrength_V1 PAI_BarStrength_V1(ISeries<double> input , bool enableBarStrength, bool showLegLines, bool enableCsvExport, string csvFilePath, DateTime exportStartDate, DateTime exportEndDate, SessionTemplateOption exportSessionTemplate, bool useExportTimeOffset, int exportTimeOffsetHours, bool barStrengthIncludeInCsv, int barStrengthCsvOrder)
		{
			return indicator.PAI_BarStrength_V1(input, enableBarStrength, showLegLines, enableCsvExport, csvFilePath, exportStartDate, exportEndDate, exportSessionTemplate, useExportTimeOffset, exportTimeOffsetHours, barStrengthIncludeInCsv, barStrengthCsvOrder);
		}
	}
}

#endregion
