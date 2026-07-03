#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// Exports the "MyStochasticsColorwithSignal" stochastic reading per bar to a
	// CSV, for joining onto MC/RevFT signals in the Python app (Bar Analysis
	// overlay, same pattern as the ZLO overlay).
	//
	// SELF-CONTAINED: it recomputes %K and %D with the SAME math as
	// MyStochasticsColorwithSignal so it does not depend on that indicator being
	// on the chart:
	//     nom = Close - MIN(Low, PeriodK)
	//     den = MAX(High, PeriodK) - MIN(Low, PeriodK)
	//     K   = 100 * SUM(nom, Smooth) / SUM(den, Smooth)   (den==0 -> 1)
	//     D   = SMA(K, PeriodD)
	// It also reproduces the two zone flags and the filtered reversal-bar signal:
	//     KSignalUp = 1  -> K moved into OVERSOLD   (CrossBelow OS,  or K<OS and falling)   -> long/reversal-up context
	//     KSignalDn = 1  -> K moved into OVERBOUGHT (CrossAbove OB,  or K>OB and rising)    -> short/reversal-dn context
	//     ZoneSignal = +1 -> LightGreen bull bar (KSignalUp + IBS + body-size filters)
	//     ZoneSignal = -1 -> LightPink bear bar (KSignalDn + IBS + body-size filters)
	//     ZoneSignal =  0 -> none
	//
	// DateTime is the bar CLOSE time converted into the target timezone (default
	// Chicago / "Central Standard Time") so it lines up with the close-stamped
	// MC/RevFT signal timestamps for the as-of join.
	//
	// IMPORTANT: run this on the SAME chart / session template that generated the
	// signals. The stochastic lookback (MIN/MAX/SUM over PeriodK/Smooth bars) sees
	// exactly the bars on the chart, so an RTH-only template and a 24h template
	// give different K/D at the RTH open. Keep them consistent.
	//
	// Designed for a 5-minute chart with Calculate.OnBarClose. Rows are
	// accumulated in memory and written atomically on Terminated so re-running
	// never blocks on a held file lock.
	public class MyStochasticExporter : Indicator
	{
		private List<string> _csvLines;
		private bool         _csvNeedsHeader;
		private int          _rowsWritten;

		private Series<double> _nom;
		private Series<double> _den;
		private Series<double> _k;

		private int _rthStartMinutes;   // RTH open, minutes-of-day (exclusive lower bound)
		private int _rthEndMinutes;     // RTH close, minutes-of-day (inclusive upper bound)

		private TimeZoneInfo _sourceTz;
		private TimeZoneInfo _targetTz;
		private bool         _convertTz;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description              = "Exports per-bar stochastic %K/%D (MyStochasticsColorwithSignal math) plus zone/reversal signals to a CSV, in Chicago time, for the Python Bar Analysis overlay.";
				Name                     = "MyStochasticExporter";
				Calculate                = Calculate.OnBarClose;
				IsOverlay                = false;
				DisplayInDataBox         = false;
				DrawOnPricePanel         = false;
				PaintPriceMarkers        = false;
				IsSuspendedWhileInactive = true;
				BarsRequiredToPlot       = 0;

				CsvOutputPath = @"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\Stoch\ES_stoch.csv";
				CsvAppendMode = false;
				TimeZoneId    = "Central Standard Time";

				// Stochastic params — match MyStochasticsColorwithSignal defaults.
				PeriodK = 8;   // K lookback
				PeriodD = 1;   // SMA period over K (=> %D). 1 means D == K.
				Smooth  = 1;   // SUM smoothing on numerator/denominator (SlowK)

				// Zone thresholds (indicator uses fixed 20/80 lines).
				OSLevel = 20;
				OBLevel = 80;

				// Reversal-bar (background color) filters — match indicator.
				IbsFilter    = 60;    // BTCSTC_IBS: bull wants IBS < (100-IBS); bear wants IBS > IBS
				BodyDivisor  = 2.7;   // body must exceed Range / BodyDivisor

				// RTH filter — export only bars whose close is inside the RTH window.
				RthOnly      = false; // false = export every bar the chart holds
				RthStartHHmm = 830;   // exclusive lower bound (first RTH bar closes 08:35)
				RthEndHHmm   = 1515;  // inclusive upper bound (last RTH bar closes 15:15)
			}
			else if (State == State.Configure)
			{
				_nom = new Series<double>(this);
				_den = new Series<double>(this);
				_k   = new Series<double>(this);
			}
			else if (State == State.DataLoaded)
			{
				_rthStartMinutes = HHmmToMinutes(RthStartHHmm);
				_rthEndMinutes   = HHmmToMinutes(RthEndHHmm);

				_sourceTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
				try
				{
					_targetTz = string.IsNullOrWhiteSpace(TimeZoneId)
						? _sourceTz
						: TimeZoneInfo.FindSystemTimeZoneById(TimeZoneId);
				}
				catch (Exception ex)
				{
					Print("MyStochasticExporter: WARNING - unknown TimeZoneId '" + TimeZoneId
						+ "', falling back to NT display timezone. (" + ex.Message + ")");
					_targetTz = _sourceTz;
				}
				_convertTz = !_targetTz.Equals(_sourceTz);

				Print("MyStochasticExporter: DataLoaded");
				Print("  Instrument  : " + Instrument.FullName);
				Print("  Bar period  : " + BarsPeriod);
				Print("  NT clock TZ : " + _sourceTz.DisplayName);
				Print("  Target TZ   : " + _targetTz.DisplayName + (_convertTz ? " (converting)" : " (no conversion)"));
				Print("  Stoch       : K=" + PeriodK + " D=" + PeriodD + " Smooth=" + Smooth + "  OS/OB=" + OSLevel + "/" + OBLevel);
				Print("  RTH filter  : " + (RthOnly ? ("(" + MinutesToHHmm(_rthStartMinutes) + ", " + MinutesToHHmm(_rthEndMinutes) + "]") : "off (all bars)"));
				Print("  CSV output  : " + CsvOutputPath + (CsvAppendMode ? " (append)" : " (overwrite)"));

				_rowsWritten    = 0;
				_csvLines       = new List<string>();
				_csvNeedsHeader = !CsvAppendMode || !File.Exists(CsvOutputPath);
			}
			else if (State == State.Terminated)
			{
				try
				{
					if (_csvLines != null && ValidateFilePath(CsvOutputPath, "CSV"))
					{
						EnsureDirectory(CsvOutputPath);
						IEnumerable<string> csvOut = _csvNeedsHeader
							? new[] { "DateTime,Open,High,Low,Close,K,D,KSignalUp,KSignalDn,ZoneSignal" }.Concat(_csvLines)
							: (IEnumerable<string>)_csvLines;
						if (CsvAppendMode)
							File.AppendAllLines(CsvOutputPath, csvOut, Encoding.UTF8);
						else
							File.WriteAllLines(CsvOutputPath, csvOut, Encoding.UTF8);
					}
				}
				catch (Exception ex)
				{
					Print("MyStochasticExporter: ERROR writing file - " + ex.Message);
				}
				Print("MyStochasticExporter: Done - wrote " + _rowsWritten + " bars");
			}
		}

		protected override void OnBarUpdate()
		{
			// Need enough history for the lookback + one prior K for the rising/falling test.
			if (CurrentBar < Math.Max(PeriodK, Smooth) + 1)
				return;

			// --- Stochastic math (identical to MyStochasticsColorwithSignal) ---
			_nom[0] = Close[0] - MIN(Low, PeriodK)[0];
			_den[0] = MAX(High, PeriodK)[0] - MIN(Low, PeriodK)[0];

			double sumDen = SUM(_den, Smooth)[0];
			_k[0] = 100.0 * SUM(_nom, Smooth)[0] / (sumDen == 0 ? 1.0 : sumDen);
			double d = SMA(_k, PeriodD)[0];

			// --- Zone signals (kSignalDn = OB, kSignalUp = OS) ---
			int kSignalDn = (CrossAbove(_k, OBLevel, 1) || (OBLevel < _k[0] && _k[1] < _k[0])) ? 1 : 0;
			int kSignalUp = (CrossBelow(_k, OSLevel, 1) || (OSLevel > _k[0] && _k[1] > _k[0])) ? 1 : 0;

			// --- Filtered reversal-bar signal (the background color) ---
			double rng = High[0] - Low[0];
			int zoneSignal = 0;
			if (rng > 0)
			{
				double ibs  = (Close[0] - Low[0]) / rng * 100.0;   // internal bar strength 0..100
				double body = Math.Abs(Close[0] - Open[0]);
				bool bigBody = (rng / BodyDivisor) < body;
				if (kSignalUp > 0 && (100.0 - IbsFilter) > ibs && bigBody)
					zoneSignal = 1;    // LightGreen bull
				else if (kSignalDn > 0 && IbsFilter < ibs && bigBody)
					zoneSignal = -1;   // LightPink bear
			}

			// --- Timezone + RTH filter on the bar CLOSE time ---
			DateTime t = _convertTz
				? TimeZoneInfo.ConvertTime(Time[0], _sourceTz, _targetTz)
				: Time[0];

			if (RthOnly)
			{
				int todMin = (int)t.TimeOfDay.TotalMinutes;
				if (todMin <= _rthStartMinutes || todMin > _rthEndMinutes)
					return;
			}

			string line = string.Format(CultureInfo.InvariantCulture,
				"{0:yyyy-MM-dd HH:mm:ss},{1:F2},{2:F2},{3:F2},{4:F2},{5:F4},{6:F4},{7},{8},{9}",
				t, Open[0], High[0], Low[0], Close[0], _k[0], d, kSignalUp, kSignalDn, zoneSignal);
			_csvLines.Add(line);
			_rowsWritten++;
			if (_rowsWritten == 1 || _rowsWritten % 2000 == 0)
				Print("MyStochasticExporter: row " + _rowsWritten + " — " + line);
		}

		// -- Helpers -----------------------------------------------------------

		private static int HHmmToMinutes(int hhmm)
		{
			int h = hhmm / 100;
			int m = hhmm % 100;
			return h * 60 + m;
		}

		private static string MinutesToHHmm(int minutes)
		{
			return string.Format("{0:D2}:{1:D2}", minutes / 60, minutes % 60);
		}

		private bool ValidateFilePath(string path, string label)
		{
			if (string.IsNullOrWhiteSpace(path))
			{
				Print("  ERROR: " + label + " path is empty.");
				return false;
			}
			string ext = Path.GetExtension(path);
			if (string.IsNullOrEmpty(ext))
			{
				Print("  ERROR: " + label + " path has no file extension - looks like a folder, not a file.");
				Print("         Got: " + path);
				return false;
			}
			if (Directory.Exists(path))
			{
				Print("  ERROR: " + label + " path is an existing directory, not a file.");
				Print("         Got: " + path);
				return false;
			}
			return true;
		}

		private static void EnsureDirectory(string filePath)
		{
			string dir = Path.GetDirectoryName(filePath);
			if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
				Directory.CreateDirectory(dir);
		}

		// -- Properties --------------------------------------------------------

		[NinjaScriptProperty]
		[Display(Name = "CSV output path", Order = 1, GroupName = "Output",
				 Description = "Comma-delimited file with header. One row per bar.")]
		public string CsvOutputPath { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Append to existing CSV", Order = 2, GroupName = "Output",
				 Description = "False = overwrite on each chart load. True = append (header skipped if file exists).")]
		public bool CsvAppendMode { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Timezone id (Windows)", Order = 3, GroupName = "Output",
				 Description = "Windows timezone the DateTime column is written in. 'Central Standard Time' = Chicago (auto CST/CDT). Match the MC/RevFT signal timestamps.")]
		public string TimeZoneId { get; set; }

		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name = "Period K", Order = 1, GroupName = "Stochastic",
				 Description = "Bars used for the K lookback (MIN/MAX).")]
		public int PeriodK { get; set; }

		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name = "Period D", Order = 2, GroupName = "Stochastic",
				 Description = "SMA period over K to form %D. 1 => D equals K.")]
		public int PeriodD { get; set; }

		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name = "Smooth", Order = 3, GroupName = "Stochastic",
				 Description = "SUM smoothing on numerator/denominator (SlowK).")]
		public int Smooth { get; set; }

		[Range(0, 100)]
		[NinjaScriptProperty]
		[Display(Name = "Oversold level", Order = 4, GroupName = "Stochastic",
				 Description = "OS threshold (indicator uses 20).")]
		public double OSLevel { get; set; }

		[Range(0, 100)]
		[NinjaScriptProperty]
		[Display(Name = "Overbought level", Order = 5, GroupName = "Stochastic",
				 Description = "OB threshold (indicator uses 80).")]
		public double OBLevel { get; set; }

		[Range(1, 100)]
		[NinjaScriptProperty]
		[Display(Name = "IBS filter (1-100)", Order = 6, GroupName = "Stochastic",
				 Description = "BTCSTC_IBS: bull reversal bar needs IBS < (100-this); bear needs IBS > this.")]
		public double IbsFilter { get; set; }

		[Range(0.1, 100)]
		[NinjaScriptProperty]
		[Display(Name = "Body divisor", Order = 7, GroupName = "Stochastic",
				 Description = "Reversal bar body must exceed Range / this (indicator uses 2.7).")]
		public double BodyDivisor { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "RTH only", Order = 1, GroupName = "RTH filter",
				 Description = "True = export only bars whose close is inside the RTH window below. K/D are still computed from all bars on the chart.")]
		public bool RthOnly { get; set; }

		[Range(0, 2359)]
		[NinjaScriptProperty]
		[Display(Name = "RTH start (HHmm)", Order = 2, GroupName = "RTH filter",
				 Description = "Exclusive lower bound, e.g. 830 = 08:30 (first RTH bar closes 08:35).")]
		public int RthStartHHmm { get; set; }

		[Range(0, 2359)]
		[NinjaScriptProperty]
		[Display(Name = "RTH end (HHmm)", Order = 3, GroupName = "RTH filter",
				 Description = "Inclusive upper bound, e.g. 1515 = 15:15 (last RTH bar closes 15:15).")]
		public int RthEndHHmm { get; set; }
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private MyStochasticExporter[] cacheMyStochasticExporter;
		public MyStochasticExporter MyStochasticExporter(string csvOutputPath, bool csvAppendMode, string timeZoneId, int periodK, int periodD, int smooth, double oSLevel, double oBLevel, double ibsFilter, double bodyDivisor, bool rthOnly, int rthStartHHmm, int rthEndHHmm)
		{
			return MyStochasticExporter(Input, csvOutputPath, csvAppendMode, timeZoneId, periodK, periodD, smooth, oSLevel, oBLevel, ibsFilter, bodyDivisor, rthOnly, rthStartHHmm, rthEndHHmm);
		}

		public MyStochasticExporter MyStochasticExporter(ISeries<double> input, string csvOutputPath, bool csvAppendMode, string timeZoneId, int periodK, int periodD, int smooth, double oSLevel, double oBLevel, double ibsFilter, double bodyDivisor, bool rthOnly, int rthStartHHmm, int rthEndHHmm)
		{
			if (cacheMyStochasticExporter != null)
				for (int idx = 0; idx < cacheMyStochasticExporter.Length; idx++)
					if (cacheMyStochasticExporter[idx] != null && cacheMyStochasticExporter[idx].CsvOutputPath == csvOutputPath && cacheMyStochasticExporter[idx].CsvAppendMode == csvAppendMode && cacheMyStochasticExporter[idx].TimeZoneId == timeZoneId && cacheMyStochasticExporter[idx].PeriodK == periodK && cacheMyStochasticExporter[idx].PeriodD == periodD && cacheMyStochasticExporter[idx].Smooth == smooth && cacheMyStochasticExporter[idx].OSLevel == oSLevel && cacheMyStochasticExporter[idx].OBLevel == oBLevel && cacheMyStochasticExporter[idx].IbsFilter == ibsFilter && cacheMyStochasticExporter[idx].BodyDivisor == bodyDivisor && cacheMyStochasticExporter[idx].RthOnly == rthOnly && cacheMyStochasticExporter[idx].RthStartHHmm == rthStartHHmm && cacheMyStochasticExporter[idx].RthEndHHmm == rthEndHHmm && cacheMyStochasticExporter[idx].EqualsInput(input))
						return cacheMyStochasticExporter[idx];
			return CacheIndicator<MyStochasticExporter>(new MyStochasticExporter(){ CsvOutputPath = csvOutputPath, CsvAppendMode = csvAppendMode, TimeZoneId = timeZoneId, PeriodK = periodK, PeriodD = periodD, Smooth = smooth, OSLevel = oSLevel, OBLevel = oBLevel, IbsFilter = ibsFilter, BodyDivisor = bodyDivisor, RthOnly = rthOnly, RthStartHHmm = rthStartHHmm, RthEndHHmm = rthEndHHmm }, input, ref cacheMyStochasticExporter);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.MyStochasticExporter MyStochasticExporter(string csvOutputPath, bool csvAppendMode, string timeZoneId, int periodK, int periodD, int smooth, double oSLevel, double oBLevel, double ibsFilter, double bodyDivisor, bool rthOnly, int rthStartHHmm, int rthEndHHmm)
		{
			return indicator.MyStochasticExporter(Input, csvOutputPath, csvAppendMode, timeZoneId, periodK, periodD, smooth, oSLevel, oBLevel, ibsFilter, bodyDivisor, rthOnly, rthStartHHmm, rthEndHHmm);
		}

		public Indicators.MyStochasticExporter MyStochasticExporter(ISeries<double> input , string csvOutputPath, bool csvAppendMode, string timeZoneId, int periodK, int periodD, int smooth, double oSLevel, double oBLevel, double ibsFilter, double bodyDivisor, bool rthOnly, int rthStartHHmm, int rthEndHHmm)
		{
			return indicator.MyStochasticExporter(input, csvOutputPath, csvAppendMode, timeZoneId, periodK, periodD, smooth, oSLevel, oBLevel, ibsFilter, bodyDivisor, rthOnly, rthStartHHmm, rthEndHHmm);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.MyStochasticExporter MyStochasticExporter(string csvOutputPath, bool csvAppendMode, string timeZoneId, int periodK, int periodD, int smooth, double oSLevel, double oBLevel, double ibsFilter, double bodyDivisor, bool rthOnly, int rthStartHHmm, int rthEndHHmm)
		{
			return indicator.MyStochasticExporter(Input, csvOutputPath, csvAppendMode, timeZoneId, periodK, periodD, smooth, oSLevel, oBLevel, ibsFilter, bodyDivisor, rthOnly, rthStartHHmm, rthEndHHmm);
		}

		public Indicators.MyStochasticExporter MyStochasticExporter(ISeries<double> input , string csvOutputPath, bool csvAppendMode, string timeZoneId, int periodK, int periodD, int smooth, double oSLevel, double oBLevel, double ibsFilter, double bodyDivisor, bool rthOnly, int rthStartHHmm, int rthEndHHmm)
		{
			return indicator.MyStochasticExporter(input, csvOutputPath, csvAppendMode, timeZoneId, periodK, periodD, smooth, oSLevel, oBLevel, ibsFilter, bodyDivisor, rthOnly, rthStartHHmm, rthEndHHmm);
		}
	}
}

#endregion
