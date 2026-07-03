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

// Converted from Nt7 and Exported with NT8B6 10/27/15
//This namespace holds Indicators in this folder and is required. Do not change it. 
namespace NinjaTrader.NinjaScript.Indicators.My
{
	public class MyStochasticsColorwithSignal : Indicator
	{
		#region variables
		private Series<double> den;
		private Series<double> nom;
		private Series<double> k;
		
		private Series<int> kSignalUp;
		private Series<int> kSignalDn;
		
		private int	periodD	= 1;	// SlowDperiod
		private int	periodK	= 8;	// Kperiod
		private int	smooth	= 1;	// SlowKperiod	
		private int alertRearmSeconds = 60;
		private Brush alertBackColor = Brushes.Blue;
		private Brush alertForeColor = Brushes.Yellow;
		private bool alertBool = false;		
		#endregion

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description							= @"The Stochastic Oscillator is made up of two lines that oscillate between a vertical scale of 0 to 100. The %K is the main line and it is drawn as a solid line. The second is the %D line and is a moving average of %K. The %D line is drawn as a dotted line. Use as a buy/sell signal generator, buying when fast moves above slow and selling when fast moves below slow.";
				Name								= "MyStochasticsColorwithSignal";
				Calculate							= Calculate.OnPriceChange;
				IsOverlay							= false;
				DisplayInDataBox					= true;
				DrawOnPricePanel					= true;
				DrawHorizontalGridLines				= true;
				DrawVerticalGridLines				= true;
				PaintPriceMarkers					= true;
				ScaleJustification					= NinjaTrader.Gui.Chart.ScaleJustification.Right;
				//Disable this property if your indicator requires custom values that cumulate with each new market data event. 
				//See Help Guide for additional information.
				IsSuspendedWhileInactive			= false;

				showLast200			= true;
				AlertBool			= true;
				AlertRearmSeconds	= 3600;
				AlertForeColor		= Brushes.Black;
				AlertBackColor		= Brushes.Yellow;
				BTCSTC_IBS			= 60;
				
				AddPlot(Brushes.Violet, "DUpper");
				AddPlot(Brushes.Turquoise, "DMiddle");
				AddPlot(Brushes.LimeGreen, "DLower");
				AddPlot(Brushes.Red, "KUpper");
				AddPlot(Brushes.Blue, "KMiddle");
				AddPlot(Brushes.LimeGreen, "KLower");
				
				AddLine(Brushes.Black, 20, "Lower");
				AddLine(Brushes.Black, 80, "Upper");
			}
			else if (State == State.Configure)
			{
				den = new Series<double>(this);
				nom = new Series<double>(this);
				k = new Series<double>(this);
				kSignalUp = new Series<int>(this);
				kSignalDn = new Series<int>(this);
				
				Plots[0].Min = Lines[1].Value; 
				Plots[1].Max = Lines[1].Value;
				Plots[1].Min = Lines[0].Value;
				Plots[2].Max = Lines[0].Value; 
			
				Plots[3].Min = Lines[1].Value; 
				Plots[4].Max = Lines[1].Value;
				Plots[4].Min = Lines[0].Value;
				Plots[5].Max = Lines[0].Value;
				
				Plots[3].Width = 4;
				Plots[4].Width = 4;
				Plots[5].Width = 4;				
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
			if (CurrentBar<30) return;
			if (showLast200 && CurrentBar<Count-200) return;
			
			nom[0] = (Close[0] - MIN(Low, PeriodK)[0]);
			den[0] = (MAX(High, PeriodK)[0] - MIN(Low, PeriodK)[0]);										
			
			k[0] = (100 * SUM(nom, Smooth)[0] / (SUM(den, Smooth)[0] == 0 ? 1.0 : SUM(den, Smooth)[0]));	
						
			KUpper[0] = (100 * SUM(nom, Smooth)[0] / (SUM(den, Smooth)[0] == 0 ? 1.0 : SUM(den, Smooth)[0]));	
			DUpper[0] = (SMA(KUpper, PeriodD)[0]);																	
			
			KMiddle[0] = (100 * SUM(nom, Smooth)[0] / (SUM(den, Smooth)[0] == 0 ? 1.0 : SUM(den, Smooth)[0]));	
			DMiddle[0] = (SMA(KMiddle, PeriodD)[0]);	
			
			KLower[0] = (100 * SUM(nom, Smooth)[0] / (SUM(den, Smooth)[0] == 0 ? 1.0 : SUM(den, Smooth)[0]));	
			DLower[0] = (SMA(KLower, PeriodD)[0]);	
			
DrawOnPricePanel = false;
			
			if (CrossAbove(k,Lines[1].Value,1) || (Lines[1].Value<KLower[0] && KLower[1]<KLower[0]))
			{
			//	Draw.ArrowDown(this, "k_cross_dn" + (CurrentBar), true, 0, Lines[1].Value, Plots[3].Brush);
			//	Draw.ArrowDown(this, "k_cross_dn" + (CurrentBar), true, 0, 100, Plots[3].Brush);
				kSignalDn[0] = 1;
				
				if (AlertBool)
					Alert("CrossAbove", Priority.Medium, Instrument.FullName + BarsPeriod.Value.ToString("N0") + " Stochastics moved into OB" , @"C:\program Files\Ninjatrader 8\sounds\Reversing.wav", AlertRearmSeconds, AlertBackColor, AlertForeColor);
			}
			else 
			{
				RemoveDrawObject("k_cross_dn" + (CurrentBar));
				kSignalDn[0] = 0;
			}
			
			if (CrossBelow(k,Lines[0].Value,1) || (Lines[0].Value>KLower[0] && KLower[1]>KLower[0]))
			{
			//	Draw.ArrowUp(this, "k_cross_up" + (CurrentBar), true, 0, Lines[0].Value, Plots[5].Brush);
			//	Draw.ArrowUp(this, "k_cross_up" + (CurrentBar), true, 0, 0, Plots[5].Brush);
				kSignalUp[0] = 1;
				
				if (AlertBool)
					Alert("CrossBelow", Priority.Medium, Instrument.FullName + BarsPeriod.Value.ToString("N0") + " Stochastics moved into OS", @"C:\program Files\Ninjatrader 8\sounds\Reversing.wav", AlertRearmSeconds, AlertBackColor, AlertForeColor);
			}
			else 
			{
				RemoveDrawObject("k_cross_up" + (CurrentBar));
				kSignalUp[0] = 0;
			}
			
			//if (IsFirstTickOfBar)
			{
				if (kSignalUp[0]>0 && (100-BTCSTC_IBS) > (Close[0]-Low[0])/Range()[0]*100 && Range()[0]/2.7<Math.Abs(Close[0]-Open[0])) 
					BackBrushes[0] = Brushes.LightGreen;
				
				else if (kSignalDn[0]>0 && BTCSTC_IBS < (Close[0]-Low[0])/Range()[0]*100 && Range()[0]/2.7<Math.Abs(Close[0]-Open[0])) 
					BackBrushes[0] = Brushes.LightPink;
				
				else BackBrushes[0] = Brushes.Transparent;
				
				/*if (kSignalUp[0]>0 && 0<MRO(() => kSignalUp[1]>0, 1, 5)) BackBrushes[0] = Brushes.LightGreen;
				else if (kSignalDn[0]>0 && 0<MRO(() => kSignalDn[1]>0, 1, 5)) BackBrushes[0] = Brushes.LightPink;
				else BackBrushes[0] = Brushes.Transparent;*/
			}
		}

		#region Properties
		[Display(Name = "Show Last 200 Bars only", GroupName = "Parameters", Description = "Show for last 200 bars only", Order = 0)]
		public bool showLast200
		{ get; set; }
		
		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name="Period D", Description="Numbers of bars used for moving average over K values", Order=1, GroupName="Parameters")]
		public int PeriodD
		{ 
			get { return periodD;}
			set { periodD = value;}
		}

		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name="Period K", Description="Numbers of bars used for calculating the K values", Order=2, GroupName="Parameters")]
		public int PeriodK
		{ 
			get { return periodK;}
			set { periodK = value;}
		}

		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name="Smooth", Description="Number of bars for smoothing the slow K values", Order=3, GroupName="Parameters")]
		public int Smooth
		{ 
			get { return smooth;}
			set { smooth = value;}
		}
		
		[Range(1, 100), NinjaScriptProperty]
		[Display(Name = "IBS Filter (1-100)", GroupName = "Parameters", Description = "Bull IBS, vice versa for bear", Order = 10)]
		public double BTCSTC_IBS
		{ get; set; }
		

		[Range(1, int.MaxValue)]
		[NinjaScriptProperty]
		[Display(Name="Alert Rearm Seconds", Description="Seconds to wait until alert rearms", Order=4, GroupName="Parameters")]
		public int AlertRearmSeconds
		{ 
			get { return alertRearmSeconds;}
			set { alertRearmSeconds = value;}
		}

		[NinjaScriptProperty]
		[Display(Name="Enable Alerts", Description="Send an alert to Alerts window when the K plot moves out of oversold or overbought.", Order=5, GroupName="Parameters")]
		public bool AlertBool
		{ 
			get { return alertBool;}
			set { alertBool = value;}
		}

		[XmlIgnore]
		[Display(Name="Alert BackColor", Description="Alerts back color", Order=6, GroupName="Parameters")]
		public Brush AlertBackColor
		{ 
			get { return alertBackColor;}
			set { alertBackColor = value;}
		}

		[Browsable(false)]
		public string AlertBackColorSerializable
		{
			get { return Serialize.BrushToString(alertBackColor); }
			set { alertBackColor = Serialize.StringToBrush(value); }
		}			

		[XmlIgnore]
		[Display(Name="Alert ForeColor", Description="Alert font color", Order=7, GroupName="Parameters")]
		public Brush AlertForeColor
		{ 
			get { return alertForeColor;}
			set { alertForeColor = value;}
		}

		[Browsable(false)]
		public string AlertForeColorSerializable
		{
			get { return Serialize.BrushToString(alertForeColor); }
			set { alertForeColor = Serialize.StringToBrush(value); }
		}			

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> DUpper
		{
			get { return Values[0]; }
		}

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> DMiddle
		{
			get { return Values[1]; }
		}

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> DLower
		{
			get { return Values[2]; }
		}

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> KUpper
		{
			get { return Values[3]; }
		}

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> KMiddle
		{
			get { return Values[4]; }
		}

		[Browsable(false)]
		[XmlIgnore]
		public Series<double> KLower
		{
			get { return Values[5]; }
		}


		#endregion

	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private My.MyStochasticsColorwithSignal[] cacheMyStochasticsColorwithSignal;
		public My.MyStochasticsColorwithSignal MyStochasticsColorwithSignal(int periodD, int periodK, int smooth, double bTCSTC_IBS, int alertRearmSeconds, bool alertBool)
		{
			return MyStochasticsColorwithSignal(Input, periodD, periodK, smooth, bTCSTC_IBS, alertRearmSeconds, alertBool);
		}

		public My.MyStochasticsColorwithSignal MyStochasticsColorwithSignal(ISeries<double> input, int periodD, int periodK, int smooth, double bTCSTC_IBS, int alertRearmSeconds, bool alertBool)
		{
			if (cacheMyStochasticsColorwithSignal != null)
				for (int idx = 0; idx < cacheMyStochasticsColorwithSignal.Length; idx++)
					if (cacheMyStochasticsColorwithSignal[idx] != null && cacheMyStochasticsColorwithSignal[idx].PeriodD == periodD && cacheMyStochasticsColorwithSignal[idx].PeriodK == periodK && cacheMyStochasticsColorwithSignal[idx].Smooth == smooth && cacheMyStochasticsColorwithSignal[idx].BTCSTC_IBS == bTCSTC_IBS && cacheMyStochasticsColorwithSignal[idx].AlertRearmSeconds == alertRearmSeconds && cacheMyStochasticsColorwithSignal[idx].AlertBool == alertBool && cacheMyStochasticsColorwithSignal[idx].EqualsInput(input))
						return cacheMyStochasticsColorwithSignal[idx];
			return CacheIndicator<My.MyStochasticsColorwithSignal>(new My.MyStochasticsColorwithSignal(){ PeriodD = periodD, PeriodK = periodK, Smooth = smooth, BTCSTC_IBS = bTCSTC_IBS, AlertRearmSeconds = alertRearmSeconds, AlertBool = alertBool }, input, ref cacheMyStochasticsColorwithSignal);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.My.MyStochasticsColorwithSignal MyStochasticsColorwithSignal(int periodD, int periodK, int smooth, double bTCSTC_IBS, int alertRearmSeconds, bool alertBool)
		{
			return indicator.MyStochasticsColorwithSignal(Input, periodD, periodK, smooth, bTCSTC_IBS, alertRearmSeconds, alertBool);
		}

		public Indicators.My.MyStochasticsColorwithSignal MyStochasticsColorwithSignal(ISeries<double> input , int periodD, int periodK, int smooth, double bTCSTC_IBS, int alertRearmSeconds, bool alertBool)
		{
			return indicator.MyStochasticsColorwithSignal(input, periodD, periodK, smooth, bTCSTC_IBS, alertRearmSeconds, alertBool);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.My.MyStochasticsColorwithSignal MyStochasticsColorwithSignal(int periodD, int periodK, int smooth, double bTCSTC_IBS, int alertRearmSeconds, bool alertBool)
		{
			return indicator.MyStochasticsColorwithSignal(Input, periodD, periodK, smooth, bTCSTC_IBS, alertRearmSeconds, alertBool);
		}

		public Indicators.My.MyStochasticsColorwithSignal MyStochasticsColorwithSignal(ISeries<double> input , int periodD, int periodK, int smooth, double bTCSTC_IBS, int alertRearmSeconds, bool alertBool)
		{
			return indicator.MyStochasticsColorwithSignal(input, periodD, periodK, smooth, bTCSTC_IBS, alertRearmSeconds, alertBool);
		}
	}
}

#endregion
