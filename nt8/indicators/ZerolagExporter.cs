#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
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

//This namespace holds Indicators in this folder and is required. Do not change it.
namespace NinjaTrader.NinjaScript.Indicators
{
	public class ZerolagExporter : Indicator
	{
		#region Private fields

		private NinjaTrader.NinjaScript.Indicators.LizardTrader.LT_Zerolag_Oscillator lizardZLO;

		private int stochDPeriod = 4;
		private int stochDOversold = 40;
		private int stochDOverbought = 60;
		private int basePeriod = 3;
		private int rangePeriod = 20;
		private int maxGapTicks = 10;
		private int barsInTrendMomBars = 5;
		private int minPctMomBars = 80;
		private int maxPctMomBars = 250;
		private int refPeriodRangeMomBars = 10;
		private int refPeriodNewHiLoMomBars = 10;
		private int barsInTrendKeyBars = 12;
		private int maxPctKeyBars = 250;
		private int refPeriodRangeKeyBars = 10;
		private int maxPctRetBars = 250;
		private int refPeriodRangeRetBars = 10;
		private double upperThreshold2 = 5.0;
		private double upperThreshold1 = 2.5;
		private double lowerThreshold1 = -2.5;
		private double lowerThreshold2 = -5.0;
		private double rangeMultiplier = 2.0;
		private double momentumLossKeyBars = 0.7;
		private double divergenceStrengthKeyBars = 0.7;
		private double momentumLossRetBars = 0.7;
		private double divergenceStrengthRetBars = 0.7;
		private bool applyLateEntryThresholds = true;
		private bool applyExhaustionThresholds = true;
		private bool applyTrendFilter = true;
		private bool applyChopFilter = false;
		private bool applyGapFilter = true;
		private bool applyRangeFilterMomBars = true;
		private bool applyNewHiLoFilterMomBars = true;
		private bool applyRangeFilterKeyBars = false;
		private bool applyThrustFilterKeyBars = false;
		private bool applySupplyDemandFilterKeyBars = true;
		private bool applyMomentumFilterKeyBars = false;
		private bool applyDivergenceFilterKeyBars = false;
		private bool applyRangeFilterRetBars = false;
		private bool applyThrustFilterRetBars = false;
		private bool applyWeakRetracementFilterRetBars = true;
		private bool applySupplyDemandFilterRetBars = true;
		private bool applyMomentumFilterRetBars = true;
		private bool applyDivergenceFilterRetBars = true;

		private bool headerWritten;
		private int barCount;

		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description					= @"Exports LT Zerolag Oscillator data to CSV for backtesting.";
				Name						= "ZerolagExporter";
				Calculate					= Calculate.OnBarClose;
				IsOverlay					= false;
				DisplayInDataBox			= true;
				DrawOnPricePanel			= true;
				DrawHorizontalGridLines		= true;
				DrawVerticalGridLines		= true;
				PaintPriceMarkers			= true;
				ScaleJustification			= NinjaTrader.Gui.Chart.ScaleJustification.Right;
				IsSuspendedWhileInactive	= true;

				ZLOPeriod				= 144;
				ZLOSmooth				= 2;
				ZLOFractalPeriod		= 72;
				ZLOEfficiencyMult		= 0.5;
				ZLOTrendFilter			= ltZerolagTrendFilterType.EfficiencyRatio;

				CsvOutputPath			= @"C:\Users\Admin\Documents\NinjaTrader 8\ZLO_Export.csv";
			}
			else if (State == State.Configure)
			{
			}
			else if (State == State.DataLoaded)
			{
				lizardZLO = LT_Zerolag_Oscillator(
					ZLOPeriod, ZLOSmooth, stochDPeriod, stochDOversold,
					stochDOverbought, applyLateEntryThresholds, upperThreshold1, lowerThreshold1,
					applyExhaustionThresholds, upperThreshold2, lowerThreshold2, applyTrendFilter,
					ZLOTrendFilter, applyChopFilter, ZLOFractalPeriod, ZLOEfficiencyMult, basePeriod,
					rangePeriod, rangeMultiplier, applyGapFilter, maxGapTicks, barsInTrendMomBars,
					applyRangeFilterMomBars, minPctMomBars, maxPctMomBars, refPeriodRangeMomBars,
					applyNewHiLoFilterMomBars, refPeriodNewHiLoMomBars, barsInTrendKeyBars,
					applyRangeFilterKeyBars, maxPctKeyBars, refPeriodRangeKeyBars, applyThrustFilterKeyBars,
					applySupplyDemandFilterKeyBars, applyMomentumFilterKeyBars, momentumLossKeyBars,
					applyDivergenceFilterKeyBars, divergenceStrengthKeyBars, applyRangeFilterRetBars,
					maxPctRetBars, refPeriodRangeRetBars, applyThrustFilterRetBars,
					applyWeakRetracementFilterRetBars,
					applySupplyDemandFilterRetBars, applyMomentumFilterRetBars, momentumLossRetBars,
					applyDivergenceFilterRetBars, divergenceStrengthRetBars);

				headerWritten = false;
				barCount = 0;

				if (File.Exists(CsvOutputPath))
					File.Delete(CsvOutputPath);
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < ZLOPeriod)
				return;

			barCount++;

			try
			{
				using (StreamWriter w = new StreamWriter(CsvOutputPath, true))
				{
					if (!headerWritten)
					{
						w.WriteLine(string.Join(",",
							"DateTime",
							"Open", "High", "Low", "Close",
							"Oscillator",
							"BaseTrend",
							"TrendState",
							"LongMomSig",
							"ShortMomSig",
							"LongKeyRetSig",
							"ShortKeyRetSig",
							"LongRetSig",
							"ShortRetSig"
						));
						headerWritten = true;
					}

					w.WriteLine(string.Join(",",
						Time[0].ToString("yyyy-MM-dd HH:mm:ss"),
						Open[0].ToString("F2"),
						High[0].ToString("F2"),
						Low[0].ToString("F2"),
						Close[0].ToString("F2"),
						lizardZLO.Oscillator[0].ToString("F4"),
						lizardZLO.BaseTrend[0].ToString("F0"),
						lizardZLO.TrendState[0].ToString("F0"),
						lizardZLO.LongMomentumSignal[0].ToString("F0"),
						lizardZLO.ShortMomentumSignal[0].ToString("F0"),
						lizardZLO.LongKeyRetracementSignal[0].ToString("F0"),
						lizardZLO.ShortKeyRetracementSignal[0].ToString("F0"),
						lizardZLO.LongRetracementSignal[0].ToString("F0"),
						lizardZLO.ShortRetracementSignal[0].ToString("F0")
					));
				}
			}
			catch (Exception ex)
			{
				Print("[ZerolagExporter] CSV error: " + ex.Message);
			}
		}

		#region Properties

		[NinjaScriptProperty]
		[Display(Name = "CSV Output Path", GroupName = "A - Output", Order = 1)]
		public string CsvOutputPath
		{ get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Period", Description = "Oscillator period", GroupName = "B - ZLO Settings", Order = 1)]
		public int ZLOPeriod
		{ get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Smooth", Description = "Smoothing period", GroupName = "B - ZLO Settings", Order = 2)]
		public int ZLOSmooth
		{ get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Fractal Period", Description = "Fractal period for Efficiency Ratio", GroupName = "B - ZLO Settings", Order = 3)]
		public int ZLOFractalPeriod
		{ get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Efficiency Multiplier", Description = "ER multiplier for trend/chop boundary", GroupName = "B - ZLO Settings", Order = 4)]
		public double ZLOEfficiencyMult
		{ get; set; }

		[NinjaScriptProperty]
		[Display(Name = "Trend Filter Type", Description = "EfficiencyRatio or SuperTrend", GroupName = "B - ZLO Settings", Order = 5)]
		public ltZerolagTrendFilterType ZLOTrendFilter
		{ get; set; }

		#endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private ZerolagExporter[] cacheZerolagExporter;
		public ZerolagExporter ZerolagExporter(string csvOutputPath, int zLOPeriod, int zLOSmooth, int zLOFractalPeriod, double zLOEfficiencyMult, ltZerolagTrendFilterType zLOTrendFilter)
		{
			return ZerolagExporter(Input, csvOutputPath, zLOPeriod, zLOSmooth, zLOFractalPeriod, zLOEfficiencyMult, zLOTrendFilter);
		}

		public ZerolagExporter ZerolagExporter(ISeries<double> input, string csvOutputPath, int zLOPeriod, int zLOSmooth, int zLOFractalPeriod, double zLOEfficiencyMult, ltZerolagTrendFilterType zLOTrendFilter)
		{
			if (cacheZerolagExporter != null)
				for (int idx = 0; idx < cacheZerolagExporter.Length; idx++)
					if (cacheZerolagExporter[idx] != null && cacheZerolagExporter[idx].CsvOutputPath == csvOutputPath && cacheZerolagExporter[idx].ZLOPeriod == zLOPeriod && cacheZerolagExporter[idx].ZLOSmooth == zLOSmooth && cacheZerolagExporter[idx].ZLOFractalPeriod == zLOFractalPeriod && cacheZerolagExporter[idx].ZLOEfficiencyMult == zLOEfficiencyMult && cacheZerolagExporter[idx].ZLOTrendFilter == zLOTrendFilter && cacheZerolagExporter[idx].EqualsInput(input))
						return cacheZerolagExporter[idx];
			return CacheIndicator<ZerolagExporter>(new ZerolagExporter(){ CsvOutputPath = csvOutputPath, ZLOPeriod = zLOPeriod, ZLOSmooth = zLOSmooth, ZLOFractalPeriod = zLOFractalPeriod, ZLOEfficiencyMult = zLOEfficiencyMult, ZLOTrendFilter = zLOTrendFilter }, input, ref cacheZerolagExporter);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.ZerolagExporter ZerolagExporter(string csvOutputPath, int zLOPeriod, int zLOSmooth, int zLOFractalPeriod, double zLOEfficiencyMult, ltZerolagTrendFilterType zLOTrendFilter)
		{
			return indicator.ZerolagExporter(Input, csvOutputPath, zLOPeriod, zLOSmooth, zLOFractalPeriod, zLOEfficiencyMult, zLOTrendFilter);
		}

		public Indicators.ZerolagExporter ZerolagExporter(ISeries<double> input , string csvOutputPath, int zLOPeriod, int zLOSmooth, int zLOFractalPeriod, double zLOEfficiencyMult, ltZerolagTrendFilterType zLOTrendFilter)
		{
			return indicator.ZerolagExporter(input, csvOutputPath, zLOPeriod, zLOSmooth, zLOFractalPeriod, zLOEfficiencyMult, zLOTrendFilter);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.ZerolagExporter ZerolagExporter(string csvOutputPath, int zLOPeriod, int zLOSmooth, int zLOFractalPeriod, double zLOEfficiencyMult, ltZerolagTrendFilterType zLOTrendFilter)
		{
			return indicator.ZerolagExporter(Input, csvOutputPath, zLOPeriod, zLOSmooth, zLOFractalPeriod, zLOEfficiencyMult, zLOTrendFilter);
		}

		public Indicators.ZerolagExporter ZerolagExporter(ISeries<double> input , string csvOutputPath, int zLOPeriod, int zLOSmooth, int zLOFractalPeriod, double zLOEfficiencyMult, ltZerolagTrendFilterType zLOTrendFilter)
		{
			return indicator.ZerolagExporter(input, csvOutputPath, zLOPeriod, zLOSmooth, zLOFractalPeriod, zLOEfficiencyMult, zLOTrendFilter);
		}
	}
}

#endregion
