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
	public class OHLCExporter : Indicator
	{
		private StreamWriter _txtWriter;
		private StreamWriter _csvWriter;
		private int          _barsWritten;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description              = "Exports every bar's DateTime, OHLC and Volume to a semicolon-delimited TXT (app import) and optionally a CSV.";
				Name                     = "OHLCExporter";
				Calculate                = Calculate.OnBarClose;
				IsOverlay                = true;
				DisplayInDataBox         = false;
				DrawOnPricePanel         = false;
				PaintPriceMarkers        = false;
				IsSuspendedWhileInactive = true;
				BarsRequiredToPlot       = 0;

				TxtOutputPath   = @"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\OHLC 5M\ES_5M_export.txt";
				TxtAppendMode   = false;
				EnableCsvOutput = false;
				CsvOutputPath   = @"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\OHLC 5M\ES_5M_export.csv";
				CsvAppendMode   = false;
			}
			else if (State == State.DataLoaded)
			{
				Print("OHLCExporter: DataLoaded");
				Print("  Instrument  : " + Instrument.FullName);
				Print("  Bar period  : " + BarsPeriod);
				Print("  Exchange TZ : " + BarsArray[0].TradingHours.TimeZoneInfo.DisplayName);

				_barsWritten = 0;

				// -- TXT writer -----------------------------------------------
				if (ValidateFilePath(TxtOutputPath, "TXT"))
				{
					try
					{
						EnsureDirectory(TxtOutputPath);
						_txtWriter = new StreamWriter(TxtOutputPath, TxtAppendMode, Encoding.UTF8);
						Print("  TXT output  : " + TxtOutputPath + (TxtAppendMode ? " (append)" : " (overwrite)"));
					}
					catch (Exception ex)
					{
						Print("  ERROR opening TXT file: " + ex.Message);
					}
				}

				// -- CSV writer -----------------------------------------------
				if (EnableCsvOutput)
				{
					if (ValidateFilePath(CsvOutputPath, "CSV"))
					{
						try
						{
							EnsureDirectory(CsvOutputPath);
							bool writeHeader = !CsvAppendMode || !File.Exists(CsvOutputPath);
							_csvWriter = new StreamWriter(CsvOutputPath, CsvAppendMode, Encoding.UTF8);
							if (writeHeader)
								_csvWriter.WriteLine("DateTime,Open,High,Low,Close,Volume");
							Print("  CSV output  : " + CsvOutputPath + (CsvAppendMode ? " (append)" : " (overwrite)"));
						}
						catch (Exception ex)
						{
							Print("  ERROR opening CSV file: " + ex.Message);
						}
					}
				}
				else
				{
					Print("  CSV output  : disabled");
				}
			}
			else if (State == State.Terminated)
			{
				Print("OHLCExporter: Terminated - flushing and closing files");
				CloseWriter(ref _txtWriter);
				CloseWriter(ref _csvWriter);
				Print("OHLCExporter: Done - wrote " + _barsWritten + " bars");
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 0)
				return;

			// In NT with Calculate.OnBarClose, Time[0] IS the bar close time (CT/exchange time).
			// Do NOT call BarCloseTime() — that would add another period and shift all bars 5 min late.
			DateTime closeTime = Time[0];
			DateTime openTime  = BarOpenTime(closeTime);

			// TXT: CT close time — Python parser subtracts 5 min to get bar open time
			string txtLine = string.Format(CultureInfo.InvariantCulture,
				"{0:dd/MM/yyyy HH:mm:ss};{1:F2};{2:F2};{3:F2};{4:F2};{5}",
				closeTime,
				Open[0], High[0], Low[0], Close[0], (long)Volume[0]);

			string csvLine = string.Format(CultureInfo.InvariantCulture,
				"{0:yyyy-MM-dd HH:mm:ss},{1:F2},{2:F2},{3:F2},{4:F2},{5}",
				openTime,
				Open[0], High[0], Low[0], Close[0], (long)Volume[0]);

			// -- Write TXT -----------------------------------------------------
			if (_txtWriter != null)
			{
				try
				{
					_txtWriter.WriteLine(txtLine);
				}
				catch (Exception ex)
				{
					Print("OHLCExporter: ERROR writing TXT bar " + CurrentBar + " - " + ex.Message);
				}
			}

			// -- Write CSV -----------------------------------------------------
			if (_csvWriter != null)
			{
				try
				{
					_csvWriter.WriteLine(csvLine);
				}
				catch (Exception ex)
				{
					Print("OHLCExporter: ERROR writing CSV bar " + CurrentBar + " - " + ex.Message);
				}
			}

			_barsWritten++;

			// Print first bar so you can verify the format immediately
			if (_barsWritten == 1)
			{
				Print("OHLCExporter: first bar written");
				Print("  TXT line : " + txtLine);
				if (_csvWriter != null)
					Print("  CSV line : " + csvLine);
			}

			// Progress update every 1000 bars
			if (_barsWritten % 1000 == 0)
				Print("OHLCExporter: " + _barsWritten + " bars written  (bar "
					+ CurrentBar + "  " + openTime.ToString("yyyy-MM-dd HH:mm") + ")");

			// Flush to disk every 500 bars
			if (CurrentBar % 500 == 0)
			{
				_txtWriter?.Flush();
				_csvWriter?.Flush();
			}
		}

		// -- Helpers -----------------------------------------------------------

		// Time[0] in NT OnBarClose is the close time; subtract the bar period to get open time.
		private DateTime BarOpenTime(DateTime closeTime)
		{
			switch (BarsPeriod.BarsPeriodType)
			{
				case BarsPeriodType.Minute: return closeTime.AddMinutes(-BarsPeriod.Value);
				case BarsPeriodType.Day:    return closeTime.AddDays(-BarsPeriod.Value);
				default:                   return closeTime;
			}
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
				Print("         Fix: add a filename at the end, e.g. ...\\ohlc_export.txt");
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

		private static void CloseWriter(ref StreamWriter writer)
		{
			if (writer == null) return;
			try
			{
				writer.Flush();
				writer.Close();
				writer.Dispose();
			}
			catch { }
			writer = null;
		}

		// -- Properties --------------------------------------------------------

		#region TXT output

		[NinjaScriptProperty]
		[Display(Name = "TXT output path", Order = 1, GroupName = "TXT output (app import)",
				 Description = "Semicolon-delimited file - drop into the app's OHLC uploader.")]
		public string TxtOutputPath { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Append to existing TXT", Order = 2, GroupName = "TXT output (app import)",
				 Description = "False = overwrite on each chart load.  True = append new bars only.")]
		public bool TxtAppendMode { get; set; }

		#endregion

		#region CSV output

		[NinjaScriptProperty]
		[Display(Name = "Enable CSV output", Order = 1, GroupName = "CSV output",
				 Description = "Toggle CSV writing on or off.")]
		public bool EnableCsvOutput { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "CSV output path", Order = 2, GroupName = "CSV output",
				 Description = "Comma-delimited with header. DateTime is bar open time in exchange timezone.")]
		public string CsvOutputPath { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Append to existing CSV", Order = 3, GroupName = "CSV output",
				 Description = "False = overwrite. True = append (header skipped if file already exists).")]
		public bool CsvAppendMode { get; set; }

		#endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private OHLCExporter[] cacheOHLCExporter;
		public OHLCExporter OHLCExporter(string txtOutputPath, bool txtAppendMode, bool enableCsvOutput, string csvOutputPath, bool csvAppendMode)
		{
			return OHLCExporter(Input, txtOutputPath, txtAppendMode, enableCsvOutput, csvOutputPath, csvAppendMode);
		}

		public OHLCExporter OHLCExporter(ISeries<double> input, string txtOutputPath, bool txtAppendMode, bool enableCsvOutput, string csvOutputPath, bool csvAppendMode)
		{
			if (cacheOHLCExporter != null)
				for (int idx = 0; idx < cacheOHLCExporter.Length; idx++)
					if (cacheOHLCExporter[idx] != null && cacheOHLCExporter[idx].TxtOutputPath == txtOutputPath && cacheOHLCExporter[idx].TxtAppendMode == txtAppendMode && cacheOHLCExporter[idx].EnableCsvOutput == enableCsvOutput && cacheOHLCExporter[idx].CsvOutputPath == csvOutputPath && cacheOHLCExporter[idx].CsvAppendMode == csvAppendMode && cacheOHLCExporter[idx].EqualsInput(input))
						return cacheOHLCExporter[idx];
			return CacheIndicator<OHLCExporter>(new OHLCExporter(){ TxtOutputPath = txtOutputPath, TxtAppendMode = txtAppendMode, EnableCsvOutput = enableCsvOutput, CsvOutputPath = csvOutputPath, CsvAppendMode = csvAppendMode }, input, ref cacheOHLCExporter);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.OHLCExporter OHLCExporter(string txtOutputPath, bool txtAppendMode, bool enableCsvOutput, string csvOutputPath, bool csvAppendMode)
		{
			return indicator.OHLCExporter(Input, txtOutputPath, txtAppendMode, enableCsvOutput, csvOutputPath, csvAppendMode);
		}

		public Indicators.OHLCExporter OHLCExporter(ISeries<double> input , string txtOutputPath, bool txtAppendMode, bool enableCsvOutput, string csvOutputPath, bool csvAppendMode)
		{
			return indicator.OHLCExporter(input, txtOutputPath, txtAppendMode, enableCsvOutput, csvOutputPath, csvAppendMode);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.OHLCExporter OHLCExporter(string txtOutputPath, bool txtAppendMode, bool enableCsvOutput, string csvOutputPath, bool csvAppendMode)
		{
			return indicator.OHLCExporter(Input, txtOutputPath, txtAppendMode, enableCsvOutput, csvOutputPath, csvAppendMode);
		}

		public Indicators.OHLCExporter OHLCExporter(ISeries<double> input , string txtOutputPath, bool txtAppendMode, bool enableCsvOutput, string csvOutputPath, bool csvAppendMode)
		{
			return indicator.OHLCExporter(input, txtOutputPath, txtAppendMode, enableCsvOutput, csvOutputPath, csvAppendMode);
		}
	}
}

#endregion
