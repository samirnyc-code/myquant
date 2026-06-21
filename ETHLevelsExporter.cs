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

namespace NinjaTrader.NinjaScript
{
	// Defined in the PARENT namespace (NinjaTrader.NinjaScript), NOT in .Indicators,
	// so the auto-generated wrapper code in the sibling .MarketAnalyzerColumns and
	// .Strategies namespaces can resolve the bare name "ETHSessionDefinition".
	// NinjaTrader regenerates that wrapper region on every compile using the
	// unqualified enum name, so the enum must live where all three child
	// namespaces can see it by walking up to this common parent.
	//
	// GlobexOnly   = the standard 17:00->08:30 overnight range.
	// FullInterRTH = everything since the RTH close (prior 15:15->08:30), which
	//                also captures the 15:15-16:00 post-close tail that can print
	//                the overnight extreme on a post-close news spike.
	public enum ETHSessionDefinition
	{
		GlobexOnly,
		FullInterRTH
	}
}

namespace NinjaTrader.NinjaScript.Indicators
{
	// Exports the ETH (Electronic / overnight) session High and Low for each
	// trading day to a CSV. One row per ETH session.
	//
	// ETH window, defined in a configurable target timezone (default Chicago /
	// "Central Standard Time"). Bar timestamps are converted from NT's display
	// clock into that zone before the window is applied. Two definitions:
	//     GlobexOnly    17:00 -> 08:30 next morning  (standard overnight)
	//     FullInterRTH  prior 15:15 -> 08:30         (everything since RTH close)
	//
	// The session that ENDS on the morning of day D is labelled date D. So the
	// evening portion (17:00 -> 24:00 of D-1) and the morning portion
	// (00:00 -> 08:30 of D) are both folded into one row dated D.
	//
	// Designed for an ES 5-minute chart with Calculate.OnBarClose. Bars are
	// accumulated in memory and the file is written atomically on Terminated,
	// so re-running the indicator never blocks on a held file lock.
	public class ETHLevelsExporter : Indicator
	{
		private List<string> _csvLines;
		private bool         _csvNeedsHeader;

		// Current ETH session being accumulated.
		private DateTime _curSessionDate;     // session_end_date = RTH trade date D (the morning the session ends into)
		private bool     _haveSession;
		private double   _ethHigh;
		private double   _ethLow;
		private DateTime _ethHighTime;
		private DateTime _ethLowTime;
		private DateTime _sessionStartTime;   // first ETH bar close time
		private DateTime _sessionEndTime;     // last  ETH bar close time
		private int      _sessionBars;

		private int _eveningStartMinutes;     // evening open, minutes-of-day (depends on definition)
		private int _endMinutes;              // ETH end,     minutes-of-day (510 = 08:30)
		private int _sessionsWritten;

		private TimeZoneInfo _sourceTz;       // timezone Time[0] is expressed in
		private TimeZoneInfo _targetTz;       // timezone the ETH window is defined in
		private bool         _convertTz;      // false when source == target (no-op)

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description              = "Exports the ETH (overnight) session high and low per trading day to a CSV, based on exchange (Chicago) time.";
				Name                     = "ETHLevelsExporter";
				Calculate                = Calculate.OnBarClose;
				IsOverlay                = true;
				DisplayInDataBox         = false;
				DrawOnPricePanel         = false;
				PaintPriceMarkers        = false;
				IsSuspendedWhileInactive = true;
				BarsRequiredToPlot       = 0;

				CsvOutputPath = @"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\ETH\ES_ETH_levels.csv";
				CsvAppendMode = false;

				// Session definition:
				//   GlobexOnly   = 17:00 -> 08:30          (standard overnight / Globex range)
				//   FullInterRTH = prior 15:15 -> 08:30    (everything since the RTH close,
				//                                           includes the 15:15-16:00 post-close tail)
				EthDefinition = ETHSessionDefinition.GlobexOnly;

				// HHmm form: 1700 = 17:00, 1515 = 15:15, 830 = 08:30.
				EthStartHHmm = 1700;   // evening open used by GlobexOnly
				RthCloseHHmm = 1515;   // evening open used by FullInterRTH (your RTH close)
				EthEndHHmm   = 830;    // first RTH bar time (exclusive); last ETH bar closes 08:25

				// Windows timezone id the ETH window is defined in. "Central
				// Standard Time" = Chicago (handles CST/CDT automatically).
				TimeZoneId = "Central Standard Time";
			}
			else if (State == State.DataLoaded)
			{
				_eveningStartMinutes = HHmmToMinutes(
					EthDefinition == ETHSessionDefinition.FullInterRTH ? RthCloseHHmm : EthStartHHmm);
				_endMinutes = HHmmToMinutes(EthEndHHmm);

				// Time[0] is expressed in NT's global display timezone. Resolve
				// the target timezone the ETH window is defined in and convert
				// per-bar so the export is correct regardless of NT's setting.
				_sourceTz = NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo;
				try
				{
					_targetTz = string.IsNullOrWhiteSpace(TimeZoneId)
						? _sourceTz
						: TimeZoneInfo.FindSystemTimeZoneById(TimeZoneId);
				}
				catch (Exception ex)
				{
					Print("ETHLevelsExporter: WARNING - unknown TimeZoneId '" + TimeZoneId
						+ "', falling back to NT display timezone. (" + ex.Message + ")");
					_targetTz = _sourceTz;
				}
				_convertTz = !_targetTz.Equals(_sourceTz);

				Print("ETHLevelsExporter: DataLoaded");
				Print("  Instrument  : " + Instrument.FullName);
				Print("  Bar period  : " + BarsPeriod);
				Print("  NT clock TZ : " + _sourceTz.DisplayName);
				Print("  Target TZ   : " + _targetTz.DisplayName + (_convertTz ? " (converting)" : " (no conversion)"));
				Print("  Definition  : " + EthDefinition);
				Print("  ETH window  : (" + MinutesToHHmm(_eveningStartMinutes) + ", " + MinutesToHHmm(_endMinutes) + ") exclusive — last ETH bar closes one period before " + MinutesToHHmm(_endMinutes) + " (target time, crosses midnight)");
				Print("  CSV output  : " + CsvOutputPath + (CsvAppendMode ? " (append)" : " (overwrite)"));

				_sessionsWritten = 0;
				_haveSession     = false;
				_csvLines        = new List<string>();
				_csvNeedsHeader  = !CsvAppendMode || !File.Exists(CsvOutputPath);
			}
			else if (State == State.Terminated)
			{
				// Flush the final in-progress session.
				if (_haveSession)
					FlushSession();

				try
				{
					if (_csvLines != null && ValidateFilePath(CsvOutputPath, "CSV"))
					{
						EnsureDirectory(CsvOutputPath);
						IEnumerable<string> csvOut = _csvNeedsHeader
							? new[] { "session_end_date,ETH_High,ETH_Low,ETH_Start,ETH_End,Bars" }.Concat(_csvLines)
							: (IEnumerable<string>)_csvLines;
						if (CsvAppendMode)
							File.AppendAllLines(CsvOutputPath, csvOut, Encoding.UTF8);
						else
							File.WriteAllLines(CsvOutputPath, csvOut, Encoding.UTF8);
					}
				}
				catch (Exception ex)
				{
					Print("ETHLevelsExporter: ERROR writing file - " + ex.Message);
				}
				Print("ETHLevelsExporter: Done - wrote " + _sessionsWritten + " ETH sessions");
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0)
				return;

			// With Calculate.OnBarClose, Time[0] is the bar's close time in NT's
			// display timezone. Convert into the target (ETH) timezone so the
			// window and the trade-date label are correct. A 5-min bar covering
			// (17:00, 17:05] closes at 17:05; the last ETH bar covers (08:20, 08:25]
			// and closes at 08:25 (the 08:30 bar holds the RTH open and is excluded).
			DateTime t = _convertTz
				? TimeZoneInfo.ConvertTime(Time[0], _sourceTz, _targetTz)
				: Time[0];
			int todMin = (int)t.TimeOfDay.TotalMinutes;

			// ETH membership on the bar CLOSE time. NT buckets a tick into the bar
			// whose close time is the first >= the tick time, so a bar stamped HH:MM
			// covers (HH:MM-period, HH:MM] and HOLDS the tick that lands exactly on
			// HH:MM. Both boundaries are therefore EXCLUSIVE so no RTH boundary tick
			// leaks into ETH:
			//   morning: todMin <  end   -> the bar stamped at the RTH open (08:30,
			//            which holds the 08:30:00.000 first RTH tick) is excluded;
			//            last ETH bar closes 08:25.
			//   evening: todMin >  eveningStart -> the bar stamped at the open
			//            (17:00 reopen, or 15:15 RTH close for FullInterRTH) is
			//            excluded; first ETH bar closes one period later.
			// Midnight close (00:00 -> covers 23:55-24:00) has todMin == 0, which
			// satisfies todMin < end and maps to the same morning date. Good.
			bool eveningPart = todMin > _eveningStartMinutes;
			bool morningPart = todMin < _endMinutes;
			if (!eveningPart && !morningPart)
				return;   // RTH / outside ETH — skip

			// Label date = the morning date D. Evening bars (of D-1) roll forward.
			DateTime sessionDate = eveningPart ? t.Date.AddDays(1) : t.Date;

			if (!_haveSession || sessionDate != _curSessionDate)
			{
				if (_haveSession)
					FlushSession();
				StartSession(sessionDate, t);
			}

			if (High[0] > _ethHigh) { _ethHigh = High[0]; _ethHighTime = t; }
			if (Low[0]  < _ethLow)  { _ethLow  = Low[0];  _ethLowTime  = t; }
			_sessionEndTime = t;
			_sessionBars++;
		}

		// -- Session bookkeeping ----------------------------------------------

		private void StartSession(DateTime sessionDate, DateTime barCloseTime)
		{
			_curSessionDate   = sessionDate;
			_haveSession      = true;
			_ethHigh          = High[0];
			_ethLow           = Low[0];
			_ethHighTime      = barCloseTime;
			_ethLowTime       = barCloseTime;
			_sessionStartTime = barCloseTime;
			_sessionEndTime   = barCloseTime;
			_sessionBars      = 0;
		}

		private void FlushSession()
		{
			string line = string.Format(CultureInfo.InvariantCulture,
				"{0:yyyy-MM-dd},{1:F2},{2:F2},{3:yyyy-MM-dd HH:mm:ss},{4:yyyy-MM-dd HH:mm:ss},{5}",
				_curSessionDate, _ethHigh, _ethLow, _sessionStartTime, _sessionEndTime, _sessionBars);
			_csvLines.Add(line);
			_sessionsWritten++;
			if (_sessionsWritten == 1 || _sessionsWritten % 200 == 0)
				Print("ETHLevelsExporter: session " + _sessionsWritten + " — " + line);
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
				 Description = "Comma-delimited file with header. One row per ETH session.")]
		public string CsvOutputPath { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Append to existing CSV", Order = 2, GroupName = "Output",
				 Description = "False = overwrite on each chart load. True = append (header skipped if file exists).")]
		public bool CsvAppendMode { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Timezone id (Windows)", Order = 3, GroupName = "Output",
				 Description = "Windows timezone the ETH window is defined in. 'Central Standard Time' = Chicago (auto CST/CDT). Bar times are converted from NT's display clock into this zone.")]
		public string TimeZoneId { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Session definition", Order = 1, GroupName = "ETH session (target timezone)",
				 Description = "GlobexOnly = 17:00->08:30 (standard overnight). FullInterRTH = prior 15:15->08:30 (everything since the RTH close, includes the post-close tail).")]
		public ETHSessionDefinition EthDefinition { get; set; }

		[NinjaScriptProperty]
		[Range(0, 2359)]
		[Display(Name = "Globex start (HHmm)", Order = 2, GroupName = "ETH session (target timezone)",
				 Description = "Evening open for GlobexOnly, e.g. 1700 = 17:00.")]
		public int EthStartHHmm { get; set; }

		[NinjaScriptProperty]
		[Range(0, 2359)]
		[Display(Name = "RTH close (HHmm)", Order = 3, GroupName = "ETH session (target timezone)",
				 Description = "Evening open for FullInterRTH, e.g. 1515 = 15:15 (your RTH close).")]
		public int RthCloseHHmm { get; set; }

		[NinjaScriptProperty]
		[Range(0, 2359)]
		[Display(Name = "ETH end / RTH open (HHmm)", Order = 4, GroupName = "ETH session (target timezone)",
				 Description = "First RTH bar time, e.g. 830 = 08:30. EXCLUSIVE: the bar stamped at this time holds the RTH open tick (08:30:00.000) and is left out, so the last ETH bar closes one period earlier (08:25 on a 5-min chart). Shared by both definitions.")]
		public int EthEndHHmm { get; set; }
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private ETHLevelsExporter[] cacheETHLevelsExporter;
		public ETHLevelsExporter ETHLevelsExporter(string csvOutputPath, bool csvAppendMode, string timeZoneId, ETHSessionDefinition ethDefinition, int ethStartHHmm, int rthCloseHHmm, int ethEndHHmm)
		{
			return ETHLevelsExporter(Input, csvOutputPath, csvAppendMode, timeZoneId, ethDefinition, ethStartHHmm, rthCloseHHmm, ethEndHHmm);
		}

		public ETHLevelsExporter ETHLevelsExporter(ISeries<double> input, string csvOutputPath, bool csvAppendMode, string timeZoneId, ETHSessionDefinition ethDefinition, int ethStartHHmm, int rthCloseHHmm, int ethEndHHmm)
		{
			if (cacheETHLevelsExporter != null)
				for (int idx = 0; idx < cacheETHLevelsExporter.Length; idx++)
					if (cacheETHLevelsExporter[idx] != null && cacheETHLevelsExporter[idx].CsvOutputPath == csvOutputPath && cacheETHLevelsExporter[idx].CsvAppendMode == csvAppendMode && cacheETHLevelsExporter[idx].TimeZoneId == timeZoneId && cacheETHLevelsExporter[idx].EthDefinition == ethDefinition && cacheETHLevelsExporter[idx].EthStartHHmm == ethStartHHmm && cacheETHLevelsExporter[idx].RthCloseHHmm == rthCloseHHmm && cacheETHLevelsExporter[idx].EthEndHHmm == ethEndHHmm && cacheETHLevelsExporter[idx].EqualsInput(input))
						return cacheETHLevelsExporter[idx];
			return CacheIndicator<ETHLevelsExporter>(new ETHLevelsExporter(){ CsvOutputPath = csvOutputPath, CsvAppendMode = csvAppendMode, TimeZoneId = timeZoneId, EthDefinition = ethDefinition, EthStartHHmm = ethStartHHmm, RthCloseHHmm = rthCloseHHmm, EthEndHHmm = ethEndHHmm }, input, ref cacheETHLevelsExporter);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.ETHLevelsExporter ETHLevelsExporter(string csvOutputPath, bool csvAppendMode, string timeZoneId, ETHSessionDefinition ethDefinition, int ethStartHHmm, int rthCloseHHmm, int ethEndHHmm)
		{
			return indicator.ETHLevelsExporter(Input, csvOutputPath, csvAppendMode, timeZoneId, ethDefinition, ethStartHHmm, rthCloseHHmm, ethEndHHmm);
		}

		public Indicators.ETHLevelsExporter ETHLevelsExporter(ISeries<double> input , string csvOutputPath, bool csvAppendMode, string timeZoneId, ETHSessionDefinition ethDefinition, int ethStartHHmm, int rthCloseHHmm, int ethEndHHmm)
		{
			return indicator.ETHLevelsExporter(input, csvOutputPath, csvAppendMode, timeZoneId, ethDefinition, ethStartHHmm, rthCloseHHmm, ethEndHHmm);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.ETHLevelsExporter ETHLevelsExporter(string csvOutputPath, bool csvAppendMode, string timeZoneId, ETHSessionDefinition ethDefinition, int ethStartHHmm, int rthCloseHHmm, int ethEndHHmm)
		{
			return indicator.ETHLevelsExporter(Input, csvOutputPath, csvAppendMode, timeZoneId, ethDefinition, ethStartHHmm, rthCloseHHmm, ethEndHHmm);
		}

		public Indicators.ETHLevelsExporter ETHLevelsExporter(ISeries<double> input , string csvOutputPath, bool csvAppendMode, string timeZoneId, ETHSessionDefinition ethDefinition, int ethStartHHmm, int rthCloseHHmm, int ethEndHHmm)
		{
			return indicator.ETHLevelsExporter(input, csvOutputPath, csvAppendMode, timeZoneId, ethDefinition, ethStartHHmm, rthCloseHHmm, ethEndHHmm);
		}
	}
}

#endregion
