#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
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
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

//This namespace holds Indicators in this folder and is required. Do not change it. 
namespace NinjaTrader.NinjaScript.Indicators
{
	/// <summary>
	/// Shows the OHLC of the previous week
	/// </summary>
	public class PriorWeekOHLC : Indicator
	{
//TDEU		
		NinjaTrader.Gui.Tools.SimpleFont myFont = new NinjaTrader.Gui.Tools.SimpleFont("Consolas", 14) { Size = 14, Bold = true };
//TDEU		
		
		private double weeklyOpen 		= 0;
		private double weeklyHigh 		= 0;
		private double weeklyLow 		= 0;
		private double weeklyClose 		= 0;
		
		private double prWeeklyOpen 	= 0;
		private double prWeeklyHigh 	= 0;
		private double prWeeklyLow 		= 0;
		private double prWeeklyClose 	= 0;
		
		DateTime newWeek = DateTime.MinValue;
		
		
		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description					= @"Shows the OHLC of the previous week";
				Name						= "PriorWeekOHLC";
				Calculate					= Calculate.OnBarClose;
				IsOverlay					= true;
				DisplayInDataBox			= true;
				DrawOnPricePanel			= true;
				PaintPriceMarkers			= true;
				IsSuspendedWhileInactive	= true;
				AllowRemovalOfDrawObjects	= true;
				IsAutoScale					= false;

				
				ShowClose					= true;
				ShowLow						= true;
				ShowHigh					= true;
				ShowOpen					= true;				
				
				AddPlot(new Stroke(Brushes.Transparent, DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekOpen");
				AddPlot(new Stroke(Brushes.Magenta, 	DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekHigh");
				AddPlot(new Stroke(Brushes.Cyan,		DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekLow");
				AddPlot(new Stroke(Brushes.Transparent,	DashStyleHelper.DashDot, 3), PlotStyle.HLine, "PriorWeekClose");
			}
		}
		
		public override string DisplayName
		{
	  		get 
			{
				if  (State == State.SetDefaults)
				{
					return Name + " ";
				}
				else return "";
			}
		}

		protected override void OnBarUpdate()
		{
			if (!Bars.BarsType.IsIntraday && Bars.BarsPeriod.BarsPeriodType != BarsPeriodType.Day)
			{
				Draw.TextFixed(this, "error1", "PriorWeekOHLC only works on intraday or daily data series", TextPosition.BottomRight);
				return;
			}
			
			if (newWeek < Time[0])
			{
				prWeeklyOpen 	= weeklyOpen;
				prWeeklyHigh 	= weeklyHigh;
				prWeeklyLow 	= weeklyLow;
				prWeeklyClose 	= weeklyClose;
				
				weeklyOpen 		= Open[0];
				weeklyHigh 		= High[0];
				weeklyLow 		= Low[0];
				weeklyClose 	= Close[0];
					
				newWeek = Time[0].Date.AddDays(7 - (int)Time[0].DayOfWeek);
			}
			
			if (prWeeklyOpen != 0)
			{
			
				if (ShowOpen)	PriorWeekOpen[0] 	= prWeeklyOpen;
				if (ShowHigh)	PriorWeekHigh[0] 	= prWeeklyHigh;
				if (ShowLow)	PriorWeekLow[0] 	= prWeeklyLow;
				if (ShowClose)	PriorWeekClose[0] 	= prWeeklyClose;
			}
			
			weeklyHigh 		= Math.Max(High[0], weeklyHigh);
			weeklyLow 		= Math.Min(Low[0], weeklyLow);
			weeklyClose 	= Close[0];
//TDEU
			if (IsFirstTickOfBar)
			{
				if (ShowOpen) Draw.Text(this,  "OoLWText", false, "OoLW", -3, PriorWeekOpen[0], 0, Plots[0].Brush, myFont, TextAlignment.Left, Brushes.Transparent, Brushes.Transparent, 0);
				if (ShowHigh) Draw.Text(this,  "HoLWText", false, "HoLW", -3, PriorWeekHigh[0], 15, Plots[1].Brush, myFont, TextAlignment.Left, Brushes.Transparent, Brushes.Transparent, 0);
				if (ShowLow) Draw.Text(this,   "LoLWText", false, "LoLW", -3, PriorWeekLow[0],  -15, Plots[2].Brush, myFont, TextAlignment.Left, Brushes.Transparent, Brushes.Transparent, 0);
				if (ShowClose) Draw.Text(this, "CoLWText", false, "CoLW", -3, PriorWeekClose[0],0, Plots[3].Brush, myFont, TextAlignment.Left, Brushes.Transparent, Brushes.Transparent, 0);
			}
//TDEU			
		}
		
		#region Properties
        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekOpen
        {
            get { return Values[0]; }
        }

        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekHigh
        {
            get { return Values[1]; }
        }

        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekLow
        {
            get { return Values[2]; }
        }

        [Browsable(false)]	// this line prevents the data series from being displayed in the indicator properties dialog, do not remove
        [XmlIgnore()]		// this line ensures that the indicator can be saved/recovered as part of a chart template, do not remove
        public Series<double> PriorWeekClose
        {
            get { return Values[3]; }
        }
		
		[Display(ResourceType = typeof(Custom.Resource), Name = "Show Weekly Close", GroupName = "NinjaScriptParameters", Order = 0)]
		public bool ShowClose
		{ get; set; }

		[Display(ResourceType = typeof(Custom.Resource), Name = "Show Weekly High", GroupName = "NinjaScriptParameters", Order = 1)]
		public bool ShowHigh
		{ get; set; }

		[Display(ResourceType = typeof(Custom.Resource), Name = "Show Weekly Low", GroupName = "NinjaScriptParameters", Order = 2)]
		public bool ShowLow
		{ get; set; }

		[Display(ResourceType = typeof(Custom.Resource), Name = "Show Weekly Open", GroupName = "NinjaScriptParameters", Order = 3)]
		public bool ShowOpen
		{ get; set; }		
        #endregion
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private PriorWeekOHLC[] cachePriorWeekOHLC;
		public PriorWeekOHLC PriorWeekOHLC()
		{
			return PriorWeekOHLC(Input);
		}

		public PriorWeekOHLC PriorWeekOHLC(ISeries<double> input)
		{
			if (cachePriorWeekOHLC != null)
				for (int idx = 0; idx < cachePriorWeekOHLC.Length; idx++)
					if (cachePriorWeekOHLC[idx] != null &&  cachePriorWeekOHLC[idx].EqualsInput(input))
						return cachePriorWeekOHLC[idx];
			return CacheIndicator<PriorWeekOHLC>(new PriorWeekOHLC(), input, ref cachePriorWeekOHLC);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.PriorWeekOHLC PriorWeekOHLC()
		{
			return indicator.PriorWeekOHLC(Input);
		}

		public Indicators.PriorWeekOHLC PriorWeekOHLC(ISeries<double> input )
		{
			return indicator.PriorWeekOHLC(input);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.PriorWeekOHLC PriorWeekOHLC()
		{
			return indicator.PriorWeekOHLC(Input);
		}

		public Indicators.PriorWeekOHLC PriorWeekOHLC(ISeries<double> input )
		{
			return indicator.PriorWeekOHLC(input);
		}
	}
}

#endregion
