//
// Copyright (C) 2022, NinjaTrader LLC <www.ninjatrader.com>.
// NinjaTrader reserves the right to modify or overwrite this NinjaScript component with each release.
//
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

// This namespace holds indicators in this folder and is required. Do not change it.
namespace NinjaTrader.NinjaScript.Indicators
{
	#region Comments
    /*{
		PaintBar: AMA_Breakouts_PB	[BOPB]
		For: MultiCharts
		Ali Moin Afshari
		Ver 6
		May 26, 2023
		
		>Finds and Marks Simple Price Action Breakouts2<
		
		>>> Research <<<
		
		This code paints three types of signals based on the breakout
		concept in the technical analysis of price action:
		1. Breakouts (BO)
		   Controlled by _ShowBLBO and _ShowBRBO inputs 
		2. Outside Bars (OB)
		   Controlled by _ShowOutsideBars input, paints OBs according
		   to the side that has a bigger BO as compared with H and L of
		   the prior bar. If the OB is completely balanced, then it is 
		   painted as a doji using _DojiColor. 
		3. Climaxes (CX)
		   Controlled by _ShowCX, finds climactic bars based on the 
		   value set for _CXfactor.
		
		_ShowBigBO:
			Identifies big breakout bars that are not outside bars but
			whose range is equal to or bigger than average bar range 
			multiplied by _BigBORageFactor.
		
		_BigBObyZscore:
			Enables big BO identification based on Z score measurement
			of the past _zLength bars. If this mode is enabled, then
			_BigBORangeFactor is the min threshold value for the signal.
			If Z score of the bar is equal or greater than that value
			the bar will be marked as a big BO bar. There are two 
			comparison methos: 
			1. _CompareRange2Range: compares entire bar range
			2. _CompareBody2Body: compares only the range of the body 
			   of the bar
			Only one method can be enabled at a time. 
		
		_ShowCX:
			Show Climax measures distance (BL case) from L to L[1] and
			compares is to distance from H to H[1]. If the latter is a
			lot bigger, the bar is likely a CX bar that can PB soon. 
		
		_RangeFilter:
			Filters signal bars whose range is smaller than average bar
			range.
		
		_PaintFTBar:
			A complex filter that can identify follow-through bars after
			a breakout, based on continuation of breakout or a new close
			beyond the previous breakout signal bar. 
		
		_FTbarNotRangeLimited:
			Allows a smaller bar to pass through the _RangeFilter when 
			it is strong follow-through for the last breakout. 
		
		Alerts:
		You can enable TradeStation's Text-To-Speech feature for audio
		alerts. In this case, if you would like to selectively disable
		an alert, simply enter a null string "" for the input value. 
		
		Signal Plot Priority:
		Priority is with climaxes, then outside bars, and finally BOs. 
		For example, if a bar is simultaneously a breakout and an 
		outside bar and a climax bar, considering all three signal types
		are enabled, it is painted as a climax. 
		
		The goal of this code is to illustrate:
		1. Simple price action definitions can be used for effective
		   programming. 
		2. No or not much optimization is required for these signals
		   because price action is already optimized. 
		3. Minimal definitions are powerful and can generate high
		   quality, tradable, signals. 
		
		--------------------------------------------------
		Ver 1 - Aug 20, 2022: initial code
		Ver 2 - Aug 23, 2022: Debug OB algo, all signals can now be plotted simultaneously
							  Add variables: OBsignal, CXsignal. Changed plot algo.
		Ver 3 - Jan 18, 2023: Added _RangeFilter, _RangeLookBack, _PaintFTBar, _FTbarMustBO, 
							  _FTbarMustCloseBeyond, _ChartData, _FTbarNotRangeLimited, _FTcolorSameAsBO,
							  FTflag, _FTafterOB, Streamlined code logic and debugged BO algo code, and
							  added signal Alerts
		Ver 4 - Jan 25, 2023: Add IBS signal and FT bar filters
		Ver 5 - Feb  4, 2023: Add _DoNotIBSfilterOB, _DoNotRangeLimitOB
		Ver 6 - May 26, 2023: Add _ShowBigBO, _BigBObyZscore
		}
		
		Ninja Trader History by Alex Obradovic, aobradovic@gmail.com
        -Ported to NinjaTrader by Alex Obradovic on Aug 21, 2021 -  Based on TS Ver 1 - Aug 20, 2022:
		-Ported Ver 2 to NinjaTrader by Alex Obradovic on Aug 25, 2021 -  Based on TS Ver 2 - Aug 23, 2022
			Fixed double / int data types affecting precision - Aug 27, 2022 ver 2.1
			Fixed index out of range message, added support for debugging, organized properties.  - Aug 27, 2022 ver 2.2
			Alex - changed brush colors set defaults - 10-30-2022
		-Ported ver 6 to NinjaTrader 8.1.1.6 on Jun 24, 2023, based on 4-AMA_Breakouts_PB - PaintBar - Ver 6.txt, updated colors
    */
	#endregion
	
    public class AMABreakoutsPB6 : Indicator
    {
		NinjaTrader.Gui.Tools.SimpleFont myFont			= new NinjaTrader.Gui.Tools.SimpleFont("Arial", 14) {Bold = true };
		NinjaTrader.Gui.Tools.SimpleFont myFont_Large	= new NinjaTrader.Gui.Tools.SimpleFont("Arial", 25) {Bold = true };
		
        public class ParamNotAllowedException : Exception
        {
            public ParamNotAllowedException()
            {
            }

            public ParamNotAllowedException(string message)
           : base(message)
            {
            }
        }

		#region variables
        private Series<double> Signal;
        private Series<double> CXsignal;
        private Series<double> OBsignal;

        //private Series<double> OBsignal;
        //private Series<double> Signal;
        private ISeries<double> H;
        private ISeries<double> L;
        private ISeries<double> C;
        private ISeries<double> O;

        private Series<double> OB;
        private Series<double> IB;
        private double IBS;
        private Series<double> BarDir; // bar direction flag: BL = 1, BR = -1
        private double BOup;
        private double BOdn;
        private double HHdist;
        private double LLdist;
        private Series<double> BarRange;
        private Series<double> AvgRange;
        private int BODir;
        private SessionIterator sessionIterator;
        private int FTflag;
        private int ExceptionFlag;
        private double StatAvrg;
        private double RangeSTDev;
        private double RangeZ;
        private Series<double> BodyRange;
        private int BigBOFlag;
//TD		
		private Brush BO_BLBody;
		private Brush CX_BLBody;
//TD
		#endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = NinjaTrader.Custom.Resource.NinjaScriptIndicatorDescriptionEMA;
				
                Name						= "AMABreakoutsPB6";
                IsOverlay					= true;
                IsSuspendedWhileInactive	= true;
				AllowRemovalOfDrawObjects	= true;
				
                IBS = 0;
                BOup = 0;
                BOdn = 0;
                HHdist = 0;
                LLdist = 0;
				
//TD				
		        ShowAIFlip = true;
		        ColorBars = true;
//TD
                _ShowBLBO = 1;
                _ShowBRBO = 1;
                _ShowBigBO = 0;
                _BigBORangeFactor = 1.05;
                _ShowOutsideBars = 1;
                _StrictOB = 1;
                _ShowCX = 0;
                _CXfactor = 1.8;

                _BigBObyZscore = 1;
                _CompareRange2Range = 0;
                _CompareBody2Body = 0;
                _zLength = 20;

                _RangeFilter = 0;
                _RangeLookBack = 8;
                _DoNotRangeLimitOB = 0;

                _BLsignalIBS = 60;
                _BRsignalIBS = 40;
                _BLFTbarIBS = 40;
                _BRFTbarIBS = 60;
                _DoNotIBSfilterOB = 1;

				PaintFTBar=1;
                _FTbarMustBO = 1;
                _FTbarMustCloseBeyond = 1;
                _FTbarNotRangeLimited = 1;
                _FTafterOB = 0;
                _FTcolorSameAsBO = 0;
                _IgnoreOpenGap = 1;
                _SessOpenTime = -1;
				
                BODir = 0;
                FTflag = 0;
                ExceptionFlag = 0;
                StatAvrg = 0;
                RangeSTDev = 0;
                RangeZ = 0;
                BigBOFlag = 0;
                AlertEnabled = 0;
                _RangeLookBack = 8;


                #region -- Alerts --
                _AlertText_BLBO = "Bull Breakout";
                _AlertText_BRBO = "Bear Breakout";
                _AlertText_BigBLBO = "Big Bull Breakout";
                _AlertText_BigBRBO = "Big Bear Breakout";
                _AlertText_BLOB = "Bull Outside Bar";
                _AlertText_BROB = "Bear Outside Bar";
                _AlertText_DojiOB = "Neutral Outside Bar";
                _AlertText_BLCX = "Buy Climax";
                _AlertText_BRCX = "Sell Climax";
                _AlertText_BLFT = "Bull Breakout and Follow Through";
                _AlertText_BRFT = "Bear Breakout and Follow Through";
                _AlertText_IB = "Inside Bar";
                _AlertText_OB = "Outside Bar";
				#endregion


                Version = "AMA_Breakouts_PB Ver 6 (20240113)-AO6.11";

				//AO-1-13-2024 fixed IBS filtering for FT logic
				
			//	BLBOBrush = new SolidColorBrush(Color.FromRgb(0, 128, 255));
		    //  BLBOBrush.Freeze();
				BLBOBrush = Brushes.DodgerBlue;
		        
			//	BRBOBrush = new SolidColorBrush(Color.FromRgb(200, 0, 0));
		    //  BRBOBrush.Freeze();
				BRBOBrush = Brushes.DarkRed;
		        
		        BigBLBOBrush = new SolidColorBrush(Color.FromRgb(0, 230, 230));
		        BigBLBOBrush.Freeze();
		        
				BigBRBOBrush = new SolidColorBrush(Color.FromRgb(255, 0, 255));
		        BigBRBOBrush.Freeze();
				
			//	BLOBBrush = new SolidColorBrush(Color.FromRgb(0, 128, 0));
		    //  BLOBBrush.Freeze();
				BLOBBrush = Brushes.Green;
		        
			//	BROBBrush = new SolidColorBrush(Color.FromRgb(255, 128, 0));
		    //  BROBBrush.Freeze();
				BROBBrush = Brushes.DarkOrange;
		        
			//	BLCXBrush = new SolidColorBrush(Color.FromRgb(0, 200, 255));
		    //  BLCXBrush.Freeze();
				BLCXBrush = Brushes.MediumOrchid;
		      
			//	BRCXBrush = new SolidColorBrush(Color.FromRgb(255, 128, 128));
		    //  BRCXBrush.Freeze();
				BRCXBrush = Brushes.MediumOrchid;
		        
			//	DojiBrush = new SolidColorBrush(Color.FromRgb(255, 0, 255));
		    //  DojiBrush.Freeze();
				DojiBrush = Brushes.Magenta;
				
		    //  BLFTBrush = new SolidColorBrush(Color.FromRgb(64, 200, 255));
		    //  BLFTBrush.Freeze();
		    	BLFTBrush = Brushes.Cyan;
		        
			//	BRFTBrush = new SolidColorBrush(Color.FromRgb(255, 64, 64));
		    //  BRFTBrush.Freeze();
				BRFTBrush = Brushes.Crimson;

//TD
				#region Plots for Market Analyzer
				IsAutoScale = false;
        		ArePlotsConfigurable = true;
        		ShowTransparentPlotsInDataBox = true;  
				
				AddPlot(new Stroke(Brushes.Transparent, 2), PlotStyle.Bar, "_Signal");
				AddPlot(new Stroke(Brushes.Transparent, 2), PlotStyle.Bar, "_FTflag");
				
				AddPlot(new Stroke(Brushes.Green, 8),		PlotStyle.Dot,	"Flip_Long");
				AddPlot(new Stroke(Brushes.Firebrick, 8),	PlotStyle.Dot,	"Flip_Short");
				
				AddPlot(new Stroke(Brushes.Transparent, 2), PlotStyle.Bar, "_ZScore");
				#endregion
//TD				
            }
			
            else if (State == State.Historical)
            {
                //stores the sessions once bars are ready, but before OnBarUpdate is called
                sessionIterator = new SessionIterator(Bars);
            }
			
            else if (State == State.Configure)
            {
                // CX
                if (_CXfactor == 0)
                {
                    throw new ParamNotAllowedException("Property Setting: _CXfactor cannot be zero.");
                }

                // Algo Confg Sanity Checks:
                if (_ShowBLBO <= 0 && _ShowBRBO <= 0 && _ShowOutsideBars <= 0 && _ShowCX <= 0)
                {
                    throw new ParamNotAllowedException("Config Error: No signal is enabled.");
                }

                if (_ShowBigBO > 0 && _BigBObyZscore > 0)
                {

                    if (_CompareRange2Range > 0 && _CompareBody2Body > 0)
                    {
                        throw new ParamNotAllowedException("Config Error: Big BO based on Z score enabled, but both Compate methods are enabled too, disable one.");
                    }
                    if (_CompareRange2Range <= 0 && _CompareBody2Body <= 0)
                    {
                        throw new ParamNotAllowedException("Config Error: Big BO based on Z score enabled, but both Compare methods are enabled, enable one.");
                    }
                    if (_zLength <= 0)
                    {
                        throw new ParamNotAllowedException("Config Error: _zLength must be a positive integer number.");
                    }
                }

                // Range Lookback
                if (_RangeFilter > 0 && _RangeLookBack <= 0)
                {
                    throw new ParamNotAllowedException("Config Error: _RangeLookBack must be a positive integer number.");
                }
                // CX
                if (_CXfactor == 0)
                {
                    throw new ParamNotAllowedException("Config Error: _CXfactor cannot be zero.");
                }
                // Session Open Time
                if (_SessOpenTime < 0)
                {
                    //SessOpenTime = CalcTime(SessionStartTime(0, 1), BarInterval);
                }
                else
                {

                    //SessOpenTime = _SessOpenTime;
                }
            }
			
            else if (State == State.DataLoaded)
            {
                // Create a new Series object and assign it to the variable declared in the ‘Variables’ region above
                BarDir = new Series<double>(this);
                Signal = new Series<double>(this);
                CXsignal = new Series<double>(this);
                OBsignal = new Series<double>(this);
                //Signal= new Series<double>(this);
                BarRange = new Series<double>(this);
                AvgRange = new Series<double>(this);
                IB = new Series<double>(this);
                OB = new Series<double>(this);
                H = new Series<double>(this);
                L = new Series<double>(this);
                C = new Series<double>(this);
                O = new Series<double>(this);
                BodyRange = new Series<double>(this);

                BarDir[0] = 0;
                Signal[0] = 0;
                //OBsignal[0] = 0;
                //CXsignal[0] = 0;
                BarRange[0] = 0;
                AvgRange[0] = 0;
                IB[0] = 0;
                OB[0] = 0;
				
//TD				
				CX_BLBody = new SolidColorBrush(Color.FromArgb((byte) 20, 58, 0, 83));
				CX_BLBody.Freeze();
				BO_BLBody = new SolidColorBrush(Color.FromArgb((byte) 50, 12, 56, 100));
				BO_BLBody.Freeze();
				
//TD				
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

        protected Brush getBrush(Color mycolor)
        {

            var converter = new System.Windows.Media.BrushConverter();
            return (Brush)converter.ConvertFromString("#" + mycolor.R.ToString("X2") + mycolor.G.ToString("X2") + mycolor.B.ToString("X2"));

        }
		
        protected override void OnBarUpdate()
        {
//TD
			if (CurrentBar<20) return;
//TD
            H = High;
            L = Low;
            C = Close;
            O = Open;

            BarRange[0] = High[0] - Low[0];

            if (_RangeFilter > 0 || _ShowBigBO > 0)
            {
                AvgRange[0] = SMA(BarRange, _RangeLookBack)[0];
            }

            try
            {

                //rewrite
                /*
				if current bar high is greater than the previous bar high 
                and if current bar low is lower than the previous bar
                it is outside bar
				
				  |
				| |	
				  |
				
				*/
                if (H.Count > 0)
                {
                    #region --- Outide Bars ---
		            //Determine if this bar is an outside bar

                    if (H[0] > H[1] && L[0] < L[1])
                    {
                        OB[0] = 1;

                        /*
                        if not a strict mode then 
                        also count outside bar if low = the previous low and the high is higher 

                           |
                        |  |
                        |  |	


                        */
                    }
                    else if (_StrictOB <= 0 && H[0] > H[1] && L[0] == L[1])
                    {

                        OB[0] = 1;

                        /*
                            if not a strict mode then 
                                also count outside bar if high = the previous high and the low is lower 

                        | 	|
                        |  

                        */
                    }
                    else if (_StrictOB <= 0 && H[0] == H[1] && L[0] < L[1])
                    {
                        OB[0] = 1;
                        //if none matches, then it is not outside bar
                    }
                    else
                    {
                        OB[0] = 0;
                    }
					#endregion

                    #region --- Inside Bars ---
                    //Determine if this bar is an inside bar

                    /*
					if current high is lower than previous high
	                and current low greater than previous low
	              
					|
					| |
					|
					
					*/
                    if (H[0] < H[1] && L[0] > L[1])
                    {
                        IB[0] = 1;

                        /*

                        |  
                        |  |
                        |  |


                        */
                    }
                    else if (H[0] < H[1] && L[0] == L[1])
                    {
                        IB[0] = 1;

                        /*

                        |  |
                        |  |
                        |  


                        */

                    }
                    else if (H[0] == H[1] && L[0] > L[1])
                    {
                        IB[0] = 1;
                    }
                    else
                    {
                        IB[0] = 0;
                    }
					#endregion

                    #region --- IBS ---
                    //InternaL[0]Bar Strength: measures position of close as a
                    //percentage value of bar range

                    //what is close minus low over the range
                    if (BarRange[0] != 0)
                    {
                        IBS = (C[0] - L[0]) / BarRange[0] * 100;
                    }
					#endregion

                    #region --- Bar Direction ---
                    //
                    //	Classify bars based on their direction into only two
                    //	categories,either BL[0](+1) || BR (-1)
                    //



                    //if close is greater than open and if internal bar strength is greater than 50%
                    if (C[0] > O[0] && IBS >= 50)
                    {
                        BarDir[0] = 1;
                    }
                    //going down if close less than open and internal bar strength less than 50%
                    else if (C[0] < O[0] && IBS <= 50)
                    {
                        BarDir[0] = -1;
                    }
                    //close = open but the ibs is above 50%
                    else if (C[0] == O[0] && IBS > 50)
                    {
                        BarDir[0] = 1;
                    }

                    //close = open and IBS is less than 50, mark as red
                    else if (C[0] == O[0] && IBS < 50)
                    {
                        BarDir[0] = -1;
                    }

                    //close = open and IBS is exactly 50%, mark the bar as the previous direction
                    else if (C[0] == O[0] && IBS == 50)
                    {
                        BarDir[0] = BarDir[1];
                    }
                    //close les then open but IBS greater than 50%, this is positive direction
                    //ok
                    else if (C[0] < O[0] && IBS > 50)
                    {
                        BarDir[0] = 1;
                    }
                    //close greater than open but IBS less than 50, going down
                    //ok
                    else if (C[0] > O[0] && IBS < 50)
                    {
                        BarDir[0] = -1;
                    }
                    //if ibs = 50%, use the previous bar value
                    //ok
                    else if (IBS == 50)
                    {
                        BarDir[0] = BarDir[1];
                    }
                    //and if anything else, use the previous bar direction
                    //ok
                    else
                    {
                        BarDir[0] = BarDir[1];
                    }
					#endregion

                    #region --- Find Breakouts ---
                    /*
	                Use minimum number of rules to define a breakout:
					1. A BO is when H[0] (BL[0] case) of a bar goes 1 tick above the
					   H[0] of the prior bar
					2. The bar cannot be an outside bar
					*/


                    Signal[0] = 0;

                    //if current high is greater than the previous high 
                    if (H[0] > H[1])
                    {
                        //breakout up = int of high current - high prev
                        BOup = (H[0] - H[1]);
                    }
                    else
                    {
                        //otherwise no breakout
                        BOup = 0;

                    }



                    //if we fell below the previous low
                    if (L[0] < L[1])
                    {
                        //breakout down = previous higher low - current low
                        BOdn = (L[1] - L[0]);
                    }
                    else
                    {
                        //else there is no breakout 
                        BOdn = 0;
                    }


                    //if we are showing breakouts up
                    if (_ShowBLBO > 0 && OB[0] == 0)
                    {
                        //higher high ahd higher low
                        if (H[0] > H[1] && L[0] >= L[1]) // change from Ver 2: L >= L[1] instead of L > L[1]
                        {
                            Signal[0] = 1;
                        }
                    }

                    //if we are showing breakouts down
                    if (_ShowBRBO > 0 && OB[0] == 0)
                    {
                        //lower high and lower low
                        if (H[0] <= H[1] && L[0] < L[1]) // change from Ver 2: H <= H[1] instead of H < H[1]
                        {
                            Signal[0] = -1;
                        }
                    }


                    //{
                    //	BODir preserves BO dir info regardless of Signal, which could be
                    //	changed and manipulated based on chart context. It is also used to 
                    //	reset Signal during the filtering processes. Because BO dir is
                    //	critical info, it cannot depend on whether BO detection is enabled
                    //	or not, so even when BO detection is disabled, BODir will still be
                    //	calculated since it is used in FT signal determination of outside
                    //	bars. Inside bars result in BODir = 0.
                    //}
                    if (OB[0] == 0 && H[0] > H[1])
                    {
                        BODir = 1;
                    }
                    else if (OB[0] == 0 && L[0] < L[1])
                    {
                        BODir = -1;
                    }
                    else
                    {
                        BODir = 0;
                    }
					#endregion

                    #region --- Climax Breakouts ---
                    //	Detect climactic bars

                    if (_ShowCX > 0)
                    {

                        HHdist = 0;
                        LLdist = 0;

                        if (BOup > 0 && BOdn == 0)
                        {   //BL[0] BO
                            HHdist = (H[0] - H[1]);
                            LLdist = (L[0] - L[1]);
                        };

                        if (BOup == 0 && BOdn > 0)
                        {   //BR BO
                            LLdist = (L[1] - L[0]);
                            HHdist = (H[1] - H[0]);
                        };

                        if (HHdist > LLdist * _CXfactor)
                        {
                            Signal[0] = 2;
                        }
                        else if (LLdist > HHdist * _CXfactor)
                        {
                            Signal[0] = -2;
                        }


                        // Climax SignaL[0] Filters -------------------------
                        if (Math.Abs(Signal[0]) == 2)
                        {
                            // Filter Climaxes when prior bar is an inside bar
                            if (IB[1] == 1)
                            {
                                Signal[0] = BODir;
                            }
                            // Filter Climaxes when climax bar is an outside bar
                            if (OB[0] == 1)
                            {
                                Signal[0] = BODir;
                            }
                            // Filter Climaxes that follow an opposite bar
                            if (BarDir[0] != BarDir[1])
                            {
                                Signal[0] = BODir;
                            }
                        }//TD;

                        // Filter Climaxes that didn't close beyond prior bar's tr} extreme
                        if (Signal[0] == 2 && C[0] <= H[1])
                        {
                            Signal[0] = BODir;
                        }

                        if (Signal[0] == -2 && C[0] >= L[1])
                        {
                            Signal[0] = BODir;
                        }
                    }//TD;
					#endregion

                    #region --- Outside Bar (Breakout) ---
                    //
                    //	Classify OBs based on their breakout tendencies:
                    //	The side that has the bigger BO determines the tone, so a
                    //	BR OB that goes more above the H[0]of prior bar than below 
                    //	its L, has a bullisH[0]tone and wilL[0]be painted in BL[0]color.
                    //}



                    if (_ShowOutsideBars > 0 && OB[0] > 0)
                    {

                        HHdist = (H[0] - H[1]);
                        LLdist = (L[1] - L[0]);
                        if (HHdist > LLdist)
                        {
                            Signal[0] = 3;
                        }
                        else if (HHdist < LLdist)
                        {
                            Signal[0] = -3;
                        }
                        else if (HHdist == LLdist)
                        {
                            if (C[0] == O[0] && IBS == 50)
                            {
                                // OB is perfect doji
                                Signal[0] = 4;
                            }
                            else if (BarDir[0] == 1)
                            {
                                Signal[0] = 3;
                            }
                            else if (BarDir[0] == -1)
                            {
                                Signal[0] = -3;
                            }

                        }


                    }
					#endregion

                    #region --- Follow-Through Filters ---
                    //{
                    //	These filters impose two different rules:
                    //	1. _FTbarMustBO: looks for a BO beyond the previous bar's trend extreme,
                    //	   but the follow through bar does not have to also close beyond it. 
                    //	   For example, a BL FT bar's H must go above the H of previous BL bar
                    //	   but the FT bar's close can be below the H of previous bar. 
                    //	2. _FTbarMustCloseBeyond: requires the FT bar to close beyond the trend
                    //	   extreme of the previous bar. For example, a BR FT bar must close 
                    //	   below the L of the previous BR bar to not get filtered. 
                    //}
					
					//Print(Time[0] + " " + " _PaintFTbar:"+ _PaintFTbar.ToString());
					
					// for future use && (_IgnoreOpenGap <= 0 || (_IgnoreOpenGap > 0 ))) //&& (sessionIterator.IsInSession(DateTime.Now, true, true)
					
                    if (PaintFTBar > 0 ) 
                    {
						//Print(Time[0] + " " + " _AO2");
                        // Reset FT Flag
                        FTflag = 0;

                        // FT must only Breakout (but not necessarily close beyond, too)
                        if (_FTbarMustBO > 0 && _FTbarMustCloseBeyond <= 0)
                        {

                            if (Signal[1] > 0 && BODir == 1)
                            {

                                Signal[0] = 1;
                                FTflag = 1;
                            }
                            else if (Signal[1] < 0 && BODir == -1)
                            {

                                Signal[0] = -1;
                                FTflag = -1;
                            }
                            else
                            //	//No FT Conditions:
                            //1. When BarDir = Signal[1] but BODir = 0 the FT bar did not BO in
                            //   the correct direction or it is an inside bar.
                            //2. If this bar is an OB and painting OB is allowed, an exception
                            //   must be made. 
                            //The IF statement below summarizes the longer version, with same
                            //exact effect:
                            //   "If BarDir = Signal[1] And (BODir = 0 OR BODir <> BarDir) Then"

                            if (BarDir[0] == Signal[1])
                            {

                                if (OB[0] == 1 && _ShowOutsideBars > 0)
                                {

                                    FTflag = 0;
                                }
                                else
                                {
                                    Signal[0] = 0;
                                    FTflag = 0;
                                }
                            }
                        }
						//Print(Time[0] + " " + " FTflag A:"+FTflag.ToString());
					
                        // FT must BOTH Breakout and Close beyond trend extreme of previous bar
                        if (_FTbarMustCloseBeyond > 0)
                        {

                            if (Signal[1] > 0 && C[0] > H[1])
                            {

                                Signal[0] = 1;
                                FTflag = 1;
                            }
                            else
                            if (Signal[1] < 0 && C[0] < L[1])
                            {

                                Signal[0] = -1;
                                FTflag = -1;
                            }
                            else
                            //No FT Consitions:
                            //1. When BarDir = Signal[1] but BODir = 0 the FT bar did not BO in
                            //   the correct direction or it is an inside bar.
                            //2. If this bar is an OB and painting OB is allowed, an exception
                            //   must be made. 
                            //The IF statement below summarizes the longer version, with same
                            //exact effect:
                            //  "If BarDir = Signal[1] And (BODir = 0 OR BODir <> BarDir) Then"

                            if (BarDir[0] == Signal[1])
                            {

                                if (OB[0] == 1 && _ShowOutsideBars > 0)
                                {

                                    FTflag = 0;
                                }
                                else
                                {
                                    Signal[0] = 0;
                                    FTflag = 0;
                                }
                            }
                            else
                            //
                            //Catch All Else Filter:
                            //A New BO cannot happen following a FT or BO bar in the same leg 
                            //without a closing beyond the trend extreme of the previous (FT) 
                            //bar.

                            if (Signal[1] > 0 && BODir == 1 && C[0] < H[1])
                            {

                                Signal[0] = 0;
                                FTflag = 0;
                            }
                            else
                            if (Signal[1] < 0 && BODir == -1 && C[0] > L[1])
                            {

                                Signal[0] = 0;
                                FTflag = 0;
                            }
							//Print(Time[0] + " " + " FTflag B:"+FTflag.ToString());
                        }
						//Print(Time[0] + " " + " FTflag C:"+FTflag.ToString());
                    }
					//Print(Time[0] + " " + " FTflag D:"+FTflag.ToString());
					#endregion

                    #region --- Range Filter ---
                    //{
                    //	When enabled, filters out BO bars whose range are smaller than the
                    //	average bar range over the lookback period. If _FTbarNotRangeLimited
                    //	is enabled and this bar is a FT bar, Range Filter will not be applied
                    //	to the FT bar. A flag (ExceptionFlag) is set. This flag is not used
                    //	in Ver 3, it is reserved for future development. 
                    //	
                    //	This filter has a pass-through feature to allow outside bars to not
                    //	get filtered when _DoNotRangeLimitOB is enabled. 
                    //}
					
                    if (_RangeFilter > 0 && Signal[0] != 0 && ((_DoNotRangeLimitOB > 0 && Math.Abs(Signal[0]) != 3) || _DoNotRangeLimitOB <= 0))
                    {
                        // Handle Range Filter Exception for FT bars
                        if (PaintFTBar > 0 && _FTbarNotRangeLimited > 0)
                        {

                            ExceptionFlag = 0;

                            if (Signal[1] != 0 && BarDir[0] == Signal[1])
                            {
                                ExceptionFlag = 1;
                            }
                            if (_FTafterOB > 0 && Math.Abs(Signal[1]) == 3 && Math.Sign(BarDir[0]) == Math.Sign(Signal[1]))
                            {
                                ExceptionFlag = 1;
                            }
                        }
                        else    // Apply Range Filter
                        if (BarRange[0] < AvgRange[0] * _RangeFilter)
                        {
                            Signal[0] = 0;
                        }
                    }
					#endregion

                    #region --- Big Breakout ---
                    //{
                    //	When enabled, detects and identifies bars that are bigger in range
                    //	than the average bar range multiplied by the _BigBORangeFactor. A 
                    //	big BO bar cannot be an outside bar. If Z Score measurement is 
                    //	enabled, Z score is calculated and used for signal identification.
                    //	Sample population is used for calculating Standard Deviation. 
                    //}
                    if (_ShowBigBO > 0)
                    {

                        if (_BigBObyZscore > 0)
                        {

                            // Calculate Z-Score
                            if (_CompareRange2Range > 0 && _CompareBody2Body <= 0)
                            {

                                // compare range of current bar with range of lookback period 
								StatAvrg=0;
								RangeSTDev=0;
								RangeZ=0;
								
                                if (BarRange.Count > 0 && BarRange[0] > 0)
                                {
                                    StatAvrg = SMA(BarRange, _zLength)[0];
                                    RangeSTDev = StdDev(BarRange, _zLength)[0]; //StandardDev(BarRange, _zLength, 2);
                                    if (RangeSTDev != 0)
                                    {
                                        RangeZ = (BarRange[0] - StatAvrg) / RangeSTDev;
                                    }
                                }
							}
							else if (_CompareRange2Range <= 0 && _CompareBody2Body > 0)
							{

                                // compare body size of current bar with body size of lookback period 
                                BodyRange[0] = Math.Abs(Close[0] - Open[0]);

								StatAvrg=0;
								RangeSTDev=0;
								RangeZ=0;
								
                                if (BodyRange.Count > 0 && BodyRange[0] > 0)
                                {
                                    StatAvrg = SMA(BodyRange, _zLength)[0];
                                    RangeSTDev = StdDev(BodyRange, _zLength)[0];//StandardDev(BodyRange, _zLength, 2);
                                    if (RangeSTDev != 0)
                                    {
                                        RangeZ = (BodyRange[0] - StatAvrg) / RangeSTDev;
                                    }
                                }
                            }
							
							 //Print(Time[0] + " " + "   RangeZ: " + RangeZ.ToString() + ",  _BigBORangeFactor: " + _BigBORangeFactor.ToString()+" OB[0]:"+OB[0].ToString());
                            // Identify Big BO based on Z-Score
                            if (RangeZ >= _BigBORangeFactor && OB[0] == 0)
                            {

                                if (BarDir[0] == 1 && _ShowBLBO > 0)
                                {
                                    BigBOFlag = 1;
                                }
                                else
                                if (BarDir[0] == -1 && _ShowBRBO > 0)
                                {
                                    BigBOFlag = -1;
                                }
                                else
                                {
                                    BigBOFlag = 0;
                                }
                            }
                            else
                            {
                                BigBOFlag = 0;
                            }
                         }
                            else {
								if (BODir != 0 && OB[0] == 0)
	                            {

	                                if (BarRange[0] >= AvgRange[0] * _BigBORangeFactor)
	                                {

	                                    if (BarDir[0] == 1 && _ShowBLBO > 0)
	                                    {
	                                        BigBOFlag = 1;
	                                    }
	                                    else if (BarDir[0] == -1 && _ShowBRBO > 0)
	                                    {
	                                        BigBOFlag = -1;
	                                    }
	                                    else
	                                    {
	                                        BigBOFlag = 0;
	                                    }
	                                }
	                                else
	                                {
	                                    BigBOFlag = 0;
	                                }
	                            }
								
	                          

                        }
							
						//  Assign Signal for Big BO
                        if (Signal[0] != 0 && OB[0] == 0)
                        {

                            if (BigBOFlag == 1)
                            {
                                Signal[0] = 5;
                            }
                            if (BigBOFlag == -1)
                            {
                                Signal[0] = -5;
                            }
                        }
                    }
					#endregion
					
                    #region--- IBS Filters ---
                    //
                    //	This filter has a pass-through feature to allow outside bars to not
                    //	get filtered when _DoNotIBSfilterOB is enabled. 
                    //

                    if (_DoNotIBSfilterOB > 0 && Math.Abs(Signal[0]) != 3 || _DoNotIBSfilterOB <= 0)
                    {
                        if (_BLsignalIBS > -1 && Signal[0] > 0 && FTflag == 0 && IBS < _BLsignalIBS)
                        {
                            Signal[0] = 0;
                        }
                        if (_BRsignalIBS > -1 && Signal[0] < 0 && FTflag == 0 && IBS > _BRsignalIBS)
                        {
                            Signal[0] = 0;
                        }
                        // FT bar IBS filters
                        if (_BLFTbarIBS > -1 && Signal[0] > 0 && FTflag == 1 && IBS < _BLFTbarIBS)
                        {
                            Signal[0] = 0;
							FTflag = 0;
                        }
                        if (_BRFTbarIBS > -1 && Signal[0] < 0 && FTflag == -1 && IBS > _BRFTbarIBS)
                        {
                            Signal[0] = 0;
							FTflag = 0;
                        }
                    }
					#endregion
					
                    #region --- Alerts ---
                    /*
					{
						Alerts are issued on the closing tick of each bar.
					}
					*/
                    if (AlertEnabled == 1)
                    {

                        switch ((int)Signal[0])
                        {

                            case 0:     // IB or OB bars
                                if (IB[0] == 1 && _AlertText_IB != "")
                                {
                                    Alert("IB", Priority.High, _AlertText_IB, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                if (OB[0] == 1 && _AlertText_OB != "")
                                {
                                    Alert("OB", Priority.High, _AlertText_OB, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
								
                            case 1:     // BL BO
                                if (FTflag == 0 && _AlertText_BLBO != "")
                                {

                                    Alert("BLBO", Priority.High, _AlertText_BLBO, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                else if (FTflag != 0 && _AlertText_BLFT != "")
                                {
                                    Alert("BLFT", Priority.High, _AlertText_BLFT, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
								
                            case 2:     // BL CX
                                if (FTflag == 0 && _AlertText_BLCX != "")
                                {
                                    Alert("BLCX", Priority.High, _AlertText_BLCX, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                else if (FTflag != 0 && _AlertText_BLFT != "")
                                {
                                    Alert("BLFT", Priority.High, _AlertText_BLFT, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
								
                            case 3:     // BL OB
                                if (FTflag == 0 && _AlertText_BLOB != "")
                                {
                                    Alert("BLOB", Priority.High, _AlertText_BLOB, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                else if (FTflag != 0 && _AlertText_BLFT != "")
                                {
                                    Alert("BLFT", Priority.High, _AlertText_BLFT, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
								
                            case 4:     // Doji OB
								if (_AlertText_DojiOB != "")
                                Alert("DojiOB", Priority.High, _AlertText_DojiOB, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                break;
								
                            case 5:     // Big BL BO
								if (_AlertText_BigBLBO != "")
                                Alert("BigBLBO", Priority.High, _AlertText_BigBLBO, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                break;
								
                            case -5:    // Big BR BO
								if (_AlertText_BigBRBO != "")
                                Alert("BigBRBO", Priority.High, _AlertText_BigBRBO, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                break;
								
                            case -3:    // BR OB
                                if (FTflag == 0 && _AlertText_BROB != "")
                                {
                                    Alert("BROB", Priority.High, _AlertText_BROB, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                else if (FTflag != 0 && _AlertText_BRFT != "")
                                {
                                    Alert("BRFT", Priority.High, _AlertText_BRFT, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
								
                            case -2:    // BR CX
                                if (FTflag == 0 && _AlertText_BRCX != "")
                                {
                                    Alert("BRCX", Priority.High, _AlertText_BRCX, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                else if (FTflag != 0 && _AlertText_BRFT != "")
                                {
                                    Alert("BRFT", Priority.High, _AlertText_BRFT, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
								
                            case -1:    // BR BO
                                if (FTflag == 0 && _AlertText_BRBO != "")
                                {
                                    Alert("BRBO", Priority.High, _AlertText_BRBO, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                else if (FTflag != 0 && _AlertText_BRFT != "")
                                {
                                    Alert("BRFT", Priority.High, _AlertText_BRFT, NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.Black, Brushes.Yellow);
                                }
                                break;
                        }
                    }
					#endregion

//TD
				if (ColorBars)
				{
                    #region --- Plot and Color Control ---
                    /*NoPlot(1); 
					NoPlot(2); 
					NoPlot(3); 
					NoPlot(4); */

                    switch ((int)Signal[0])
                    {
                        case 1:     // BL BO
                                    //PlotPB(H, L, O, C, "BO", _BLBOcolor);
                            CandleOutlineBrush = BLBOBrush; 

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BLBOBrush; 
                            }
//TD
//							else BarBrush = BO_BLBody;
                            break;
							
                        case 2:     // BL CX
                                    //PlotPB(H, L, O, C, "BO", _BLCXcolor);
                            CandleOutlineBrush = BLCXBrush; 

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BLCXBrush; 
                            }
//TD
							else BarBrush = CX_BLBody;
                            break;
							
                        case 3:     // BL OB
                                    //PlotPB(H, L, O, C, "BO", _BLOBcolor);
                            CandleOutlineBrush = BLOBBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BLOBBrush;
                            }
                            break;
                        case 4:     // Doji OB
                                    //PlotPB(H, L, O, C, "BO", _DojiColor);
                            CandleOutlineBrush = DojiBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = DojiBrush;
                            }
                            break;
                        case 5:     // Big BL BO
                                    //PlotPB(H, L, O, C, "BO", _BigBLBOcolor);
//TD                        	CandleOutlineBrush = BigBLBOBrush;
                          	CandleOutlineBrush = BLBOBrush; 
//TD
                            if (Close[0] < Open[0])
                            {
                                BarBrush = BigBLBOBrush;
								CandleOutlineBrush = BigBLBOBrush;
							//	BackBrushesAll[0] = Brushes.Yellow;
                            }
//TD							
							else BarBrush = BigBLBOBrush;//Brushes.LightGreen;
//TD							
                            break;
                        case -5:    // Big BR BO
                                    //PlotPB(H, L, O, C, "BO", _BigBRBOcolor);
                            CandleOutlineBrush = BigBRBOBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BigBRBOBrush;
                            }
                            break;
                        case -3:    // BR OB
                                    //PlotPB(H, L, O, C, "BO", _BROBcolor);
                            CandleOutlineBrush = BROBBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BROBBrush;
                            }
                            break;
                        case -2:    // BR CX
                                    //PlotPB(H, L, O, C, "BO", _BRCXcolor);
                            CandleOutlineBrush = BRCXBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BRCXBrush;
                            }
                            break;
                        case -1:    // BR BO
                                    //PlotPB(H, L, O, C, "BO", _BRBOcolor);
                            CandleOutlineBrush = BRBOBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BRBOBrush;
                            }
                            break;
                    }
					
                    // Set Colors for Follow-Through Bars
                    /*
					{
						If FT bar is a Big Breakout and big BO detection is enabled, 
						the Big BO signal takes precedence and FT color is not painted.
					}
					*/
					
					//Print(ELDateToString(date), Time:8:0, AO_GetBarNum:4:0 , "   _FTcolorSameAsBO: ", _FTcolorSameAsBO:3:0, "  Signal: ", Signal:4:0, " FTflag:", FTflag:4:0);
					//Print(Time[0] + " " + "   _FTcolorSameAsBO, : " + _FTcolorSameAsBO.ToString() + ", Signal: " + Signal[0].ToString()+" FTflag"+FTflag.ToString());
					
                    if (_FTcolorSameAsBO <= 0 && Math.Abs(Signal[0]) != 5)
                    {
                        // color FT bar differently when FTflag is set
                        if (FTflag == 1)
                        {
                            //SetPlotColor(1, _BLFTcolor)		//BL FT bar

                            CandleOutlineBrush = BLFTBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BLFTBrush;
                            }
							else BarBrush = null;

                        }
                        if (FTflag == -1)
                        {
                            //SetPlotColor(1, _BRFTcolor);	//BR FT bar


                            CandleOutlineBrush = BRFTBrush;

                            if (Close[0] < Open[0])
                            {
                                BarBrush = BRFTBrush;
                            }

                        }
                    }
					#endregion
				}
					#region Debug
                    if (_DebugON )
                    {
						if (Signal.Count>0){
						
                        	Print(Time[0] + " " + "   FTflag: " + FTflag.ToString() + ",  Signal: " + Signal[0].ToString());
						}
                        //Print(ELDateToString(date), Time:6:0, "   Doji OB,  ",  "H: ", HHdist:0:2, ",  L: ", LLdist:0:2);
                    }
					#endregion

//TD Plots & Z Score
                    #region Plots
					
					//Z Sore
					StatAvrg=0;
					RangeSTDev=0;
					RangeZ=0;
					
                    if (BarRange.Count > 0 && BarRange[0] > 0)
                    {
                        StatAvrg = SMA(BarRange, _zLength)[0];
                        RangeSTDev = StdDev(BarRange, _zLength)[0]; //StandardDev(BarRange, _zLength, 2);
                        if (RangeSTDev != 0)
                        {
                            RangeZ = (BarRange[0] - StatAvrg) / RangeSTDev;
                        }
                    }
					_ZScore[0] = RangeZ;
					
					_Signal[0] = Signal[0];
					_FTflag[0] = FTflag;
					
					#endregion
					
					#region AI Flip
					
					#region variables
					double IBS1		= (C[1] - L[1]) / BarRange[1] * 100;

					double EMA0		= EMA(20)[0];
					double EMA1		= EMA(20)[1];
					double EMA2		= EMA(20)[2];
					double EMA3		= EMA(20)[3];
					BodyRange[0]	= Math.Abs(Close[0] - Open[0]);
					
					double offset	= Math.Max(5*TickSize, ATR(50)[1]/4);
					#endregion
					
//if (_Signal[0]==1 && _FTflag[0]!=1 && Range()[0]/4>BodyRange[0]) BackBrushes[0] = Brushes.LightGreen;
//if (_Signal[0]==-1 && _FTflag[0]!=-1 && Range()[0]/4>BodyRange[0]) BackBrushes[0] = Brushes.LightPink;
					
					if (ShowAIFlip && BarsPeriod.BarsPeriodType == BarsPeriodType.Minute && BarsPeriod.Value<=5)
					{
						double MyAvgRange0	= SMA(Range(),8)[0];
						double MyAvgRange1	= SMA(Range(),8)[1];
						double MyAvgRange2	= SMA(Range(),8)[2];
						
						#region Gap Open
					//Bull gap
						if (Bars.IsFirstBarOfSession && High[1]+MyAvgRange0<Low[0] &&
							(CountIf(delegate {return EMA(20)[1]>Close[1];},10)>4 || Close[1]+2.5*MyAvgRange0<Open[0]))
						{
							//Accept
							if (Median[0]<Close[0] && Open[0]<Close[0])
							{
								if (Open[0]<Close[0] && Range()[0]/3<BodyRange[0] && IBS>=75 && MAX(High,81)[1]-MyAvgRange0<High[0])
								{
									Draw.Text(this, "LongAccept"+(CurrentBar), true, "Accept\nSE b1 &\nB lower", 1, High[0], 0, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
								//	BackBrushes[0] = Brushes.Yellow;
								}
								else
								{
									Draw.Text(this, "LongAccept"+(CurrentBar), true, "Wait for\nBO & SE", 1, High[0], 0, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
								//	BackBrushes[0] = Brushes.Yellow;
								}
							}
							//Reject
							else
							{
								if (Range()[0]/3<BodyRange[0] && IBS<=11 && 
									(EMA0+Range()[0]<Low[0] || MAX(High,80)[1]<High[0]))
								{
									Draw.Text(this, "LongReject"+(CurrentBar), true, "Strong\nReject\nalso SA", 1, High[0], 0, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
									Draw.Text(this, "ZScoreShortb1"+(CurrentBar), true, "Z", 1, Close[0]+0.0*offset, 0, Brushes.Yellow, myFont_Large, TextAlignment.Right, Brushes.Transparent, Brushes.Black, 50);
								//	BackBrushes[0] = Brushes.Yellow;
								}
								else if (!(Range()[0]/2<BodyRange[0] && IBS<30 && 1.8<RangeZ))
								{
									Draw.Text(this, "LongReject"+(CurrentBar), true, "Wait for\nBO & SE", 1, High[0], 0, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
								//	BackBrushes[0] = Brushes.Yellow;
								}
							}	
						}
						else 
							if (Bars.IsFirstBarOfSession && Signal[0]==1 && EMA(20)[0]<Close[0] && 
								CountIf(delegate {return EMA(20)[1]>Close[1];},6)>3 &&
								!(1.8<RangeZ && Range()[0]/2<=BodyRange[0] && Open[0]<Close[0] && Open[0]<EMA0 && EMA0<Close[0]))
							{
								Draw.Text(this, "LongAccept"+(CurrentBar), true, "Accept\nwait\nfor FT", 1, High[0], 0, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
							//	BackBrushes[0] = Brushes.Yellow;
							}
						
					//Bear gap
						if (Bars.IsFirstBarOfSession && Low[1]-MyAvgRange0>High[0] &&
							(CountIf(delegate {return EMA(20)[1]<Close[1];},10)>4 || Close[1]-2.5*MyAvgRange0>Open[0])) 
						{
							//Accept
							if (Median[0]>Close[0] && Open[0]>Close[0])
							{
								if (Open[0]>Close[0] && Range()[0]/3<BodyRange[0] && IBS<=25 && MIN(Low,81)[1]+MyAvgRange0>Low[0])
								{
									Draw.Text(this, "ShortAccept"+(CurrentBar), true, "Accept\nSE b1 &\nS higher", 1, Low[0], 0, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
								//	BackBrushes[0] = Brushes.Yellow;
								}
								else
								{
									Draw.Text(this, "ShortAccept"+(CurrentBar), true, "Wait for\nBO & SE", 1, Low[0], 0, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
								//	BackBrushes[0] = Brushes.Yellow;
								}
							}
							//Reject
							else
							{
								if (Range()[0]/3<BodyRange[0] && IBS>=89 && 
									(EMA0-Range()[0]>High[0] || MIN(Low,80)[1]>Low[0]))
								{
									Draw.Text(this, "ShortReject"+(CurrentBar), true, "Strong\nReject\nalso BB", 1, Low[0], 0, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
									Draw.Text(this, "ZScoreLongb1"+(CurrentBar), true, "Z", 1, Close[0]-0.0*offset, 0, Brushes.Yellow, myFont_Large, TextAlignment.Center, Brushes.Transparent, Brushes.Black, 50);
								//	BackBrushes[0] = Brushes.Yellow;
								}
								else if (!(Range()[0]/2<BodyRange[0] && IBS>70 && 1.8<RangeZ))
								{
									Draw.Text(this, "ShortReject"+(CurrentBar), true, "Wait for\nBO & SE", 1, Low[0], 0, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
								//	BackBrushes[0] = Brushes.Yellow;
								}
							}	
						}
						else 
							if (Bars.IsFirstBarOfSession && Signal[0]==-1 && EMA(20)[0]>Close[0] && 
								CountIf(delegate {return EMA(20)[1]<Close[1];},6)>3 &&
								!(1.8<RangeZ && Range()[0]/2<=BodyRange[0] && Open[0]>Close[0] && Open[0]>EMA0 && EMA0>Close[0]))
							{
								Draw.Text(this, "ShortAccept"+(CurrentBar), true, "Accept\nwait\nfor FT", 1, Low[0], 0, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
							//	BackBrushes[0] = Brushes.Yellow;
							}
						
						#endregion
						
						#region BO+FT through EMA
						if ((Open[1]<=EMA1 || Bars.BarsSinceNewTradingDay<5) && 
							EMA1<=Close[1] && (Signal[1]==1 || Signal[1]==3 || (Signal[1]==-3 && High[1]<Close[0])) &&
							!((Signal[1]==3 || Signal[1]==-3) && Open[1]>Close[1]) &&
							
							(FTflag==1 || Median[0]<=Close[0]) && 
							Open[0]<Close[0] && Close[1]<Close[0] && Signal[0]==1 && Low[1]<=Low[0] &&

							//switch from short
							(CountIf(delegate {return EMA(20)[2]>Close[2];},10)>3 || 
							 CountIf(delegate {return Flip_Short[0]>0 && EMA3>Close[0];},4)>0 ||
							 Bars.BarsSinceNewTradingDay<8) &&
							
							!(EMA1+MyAvgRange1*0.5>High[0]) &&
							
							CountIf(delegate {return Flip_Long[1]>0 && PlotBrushes[2][1]!=Brushes.Blue;},3)<1)
						{
							Flip_Long[0] = Low[0]-offset;
							
						//	if (Median[0]>=Close[0]) BackBrushes[0] = Brushes.LightGreen;
						}
						
						if ((Open[1]>=EMA1 || Bars.BarsSinceNewTradingDay<5) &&
							EMA1>=Close[1] && (Signal[1]==-1 || Signal[1]==-3 || (Signal[1]==3 && Low[1]>Close[0])) &&
							
							(FTflag==-1 || Median[0]>=Close[0]) && 
							Open[0]>Close[0] && Close[1]>Close[0] && Signal[0]==-1 && High[1]>=High[0] &&
							
							//switch from long
							(CountIf(delegate {return EMA(20)[2]<Close[2];},10)>3 ||
							 CountIf(delegate {return Flip_Long[0]>0 && EMA3<Close[0];},4)>0 ||
							 Bars.BarsSinceNewTradingDay<8) &&
							
							!(EMA1-MyAvgRange1*0.5<Low[0]) &&
							
							CountIf(delegate {return Flip_Short[1]>0 && PlotBrushes[3][1]!=Brushes.Blue;},3)<1)
						{
							Flip_Short[0] = High[0]+offset;
							
						//	if (Median[0]<=Close[0]) BackBrushes[0] = Brushes.LightPink;
						}
						#endregion

						#region 3CC Closes beyond EMA
						
						Brush Bear3CC_Color = Brushes.OrangeRed;
						Brush Bull3CC_Color = Brushes.MediumSeaGreen;
						
						if ((EMA2<Close[2] || 
							(High[3]<Close[2] && CountIf(delegate {return High[0]-Range()[0]/2.5<Close[0];},3)>2 && EMA1+TickSize<Close[1]) ||
							(1.8<RangeZ && Range()[0]/2<=BodyRange[0])) &&
							
							EMA1<Close[1] && EMA0<Close[0] &&
							Open[2]<=Close[2] && Open[1]<=Close[1] && Open[0]<=Close[0] &&
							CountIf(delegate {return Close[1]<Close[0];},3)>2 &&
							CountIf(delegate {return Open[0]==Close[0] && Median[0]>Close[0];},3)<2 &&
							
							CountIf(delegate {return Range()[0]/10>BodyRange[0];},3)<2 &&
							
							((CountIf(delegate {return Median[0]<=Close[0];},3)>2 && IBS>60) || 
							 CountIf(delegate {return Open[0]<Close[0];},4)>3 || 
							 CountIf(delegate {return High[1]<Close[0];},3)>1) &&

							//switch from short
							(CountIf(delegate {return EMA(20)[3]>Close[3];},10)>2 || 
							 CountIf(delegate {return Flip_Short[3]>0 && EMA3>Close[3];},4)>0) &&
							
							//no prior long
							CountIf(delegate {return Flip_Long[3]>0 && EMA3<Close[3];},6)<1 &&
							CountIf(delegate {return Flip_Long[1]>0 && EMA3<Close[1] && PlotBrushes[2][1]==Bull3CC_Color;},10)<1 &&
							CountIf(delegate {return Flip_Long[0]>0;},5)<1 &&
							
							//weak switch
							!(CountIf(delegate {return Median[0]>Close[0];},3)>1 && CountIf(delegate {return Low[1]<=Low[0];},2)<2) &&
							!(EMA2+MyAvgRange0>High[0] && CountIf(delegate {return IB[0]==1;},3)>0) &&
							!(EMA2+MyAvgRange0>High[0] && CountIf(delegate {return High[1]<High[0];},3)<3) &&
							!(EMA2>Median[2] && BarDir[1]==-1 && (BarDir[0]==-1 || IB[0]==1)))
						{
							Flip_Long[0] = Low[0]-offset; PlotBrushes[2][0] = Bull3CC_Color;
							
						//	if (CountIf(delegate {return Median[0]>Close[0];},3)>1 && CountIf(delegate {return Low[1]<=Low[0];},2)<2) BackBrushes[0] = Brushes.LightGreen;
						}
						
						if ((EMA2>Close[2] || 
							(Low[3]>Close[2] && CountIf(delegate {return Low[0]+Range()[0]/2.5>Close[0];},3)>2 && EMA1-TickSize>Close[1]) ||
							(1.8<RangeZ && Range()[0]/2<=BodyRange[0])) &&
							
							EMA1>Close[1] && EMA0>Close[0] &&
							Open[2]>=Close[2] && Open[1]>=Close[1] && Open[0]>=Close[0] &&
							CountIf(delegate {return Close[1]>Close[0];},3)>2 &&
							CountIf(delegate {return Open[0]==Close[0] && Median[0]<Close[0];},3)<2 &&
							
							CountIf(delegate {return Range()[0]/10>BodyRange[0];},3)<2 &&
							
							((CountIf(delegate {return Median[0]>=Close[0];},3)>2 && IBS<60) || 
							 CountIf(delegate {return Open[0]>Close[0];},4)>3 || 
							 CountIf(delegate {return Low[1]>Close[0];},3)>1) &&
							
							//switch from long
							(CountIf(delegate {return EMA(20)[3]<Close[3];},10)>2 || 
							 CountIf(delegate {return Flip_Long[3]>0 && EMA3<Close[3];},4)>0) &&
							
							//no prior short
							CountIf(delegate {return Flip_Short[3]>0 && EMA3>Close[3];},6)<1 &&
							CountIf(delegate {return Flip_Short[1]>0 && EMA1>Close[1] && PlotBrushes[3][1]==Bear3CC_Color;},10)<1 &&
							CountIf(delegate {return Flip_Short[0]>0;},5)<1 &&
							
							//weak switch
							!(CountIf(delegate {return Median[0]<Close[0];},3)>1 && CountIf(delegate {return High[1]>=High[0];},2)<2) &&
							!(EMA2-MyAvgRange0<Low[0] && CountIf(delegate {return IB[0]==1;},3)>0) &&
							!(EMA2-MyAvgRange0<Low[0] && CountIf(delegate {return Low[1]>Low[0];},3)<3) &&
							!(EMA2<Median[2] && BarDir[1]==1 && (BarDir[0]==1 || IB[0]==1)))
						{
							Flip_Short[0] = High[0]+offset; PlotBrushes[3][0] = Bear3CC_Color;
							
						//	if (CountIf(delegate {return Median[0]<Close[0];},3)>1 && CountIf(delegate {return High[1]>=High[0];},2)<2) BackBrushes[0] = Brushes.LightPink;
						}
						#endregion

						//strong MC with gaps breaks EMA
						//https://app.screencast.com/ilelqITy9LIgr						

						#region BIG BO bar
						//one large bar
						if (2.1<RangeZ)
						{
							if ((Signal[0]==1 || Signal[0]==3) && Open[0]<Close[0] && 
								
								Range()[0]/4<=BodyRange[0] &&
								
								(High[1]<=Median[0] || 
								 Signal[0]==3 || 
								 (Signal[1]==-3 && Open[1]<Close[0]) ||
								 (_ZScore[1]>1.5 && Open[1]>Close[1] && High[1]<Close[0] && OB[0]<1)) &&
								
								//no OO
								!(OB[1]==1 && OB[0]==1) &&
								
								Open[0]<EMA0 && EMA0<Close[0] &&
								(CountIf(delegate {return EMA(20)[2]>Close[2];},10)>2 || 
								 ((Signal[1]==-1 || Signal[0]==-3) && EMA1>Close[1]) ||
								 CountIf(delegate {return Flip_Long[1]>0 && EMA1<Close[1];},8)<1))
							{
								Flip_Long[0] = Low[0]-offset; PlotBrushes[2][0] = Brushes.Blue;
								Draw.Text(this, "ZScoreLong"+(CurrentBar), true, "Z", 0, Low[0]-2.5*offset, 0, Brushes.Blue, myFont_Large, TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 100);
								Draw.Text(this, "ZScoreLong1", true, "weak Rev\nFT or BP", 0, High[0], 50, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Transparent, 100);
								
							//	if (_ZScore[1]>1.5 && Open[1]>Close[1] && High[1]<Close[0] && OB[0]<1) BackBrushes[0] = Brushes.LightGreen;
							}
							
							if ((Signal[0]==-1 || Signal[0]==-3) && Open[0]>Close[0] &&
								
								Range()[0]/4<=BodyRange[0] && 
								
								(Low[1]>=Median[0] || 
								 Signal[0]==-3 || 
								 (Signal[1]==3 && Open[1]>Close[0]) ||
								 (_ZScore[1]>1.5 && Open[1]<Close[1] && Low[1]>Close[0] && OB[0]<1)) &&
								
								//no OO
								!(OB[1]==1 && OB[0]==1) &&
								
								Open[0]>EMA0 && EMA0>Close[0] &&
								(CountIf(delegate {return EMA(20)[2]<Close[2];},10)>2 || 
								 ((Signal[1]==1 || Signal[0]==3) && EMA1<Close[1]) ||
								 CountIf(delegate {return Flip_Short[1]>0 && EMA1>Close[1];},8)<1))
							{
								Flip_Short[0] = High[0]+offset; PlotBrushes[3][0] = Brushes.Blue;
								Draw.Text(this, "ZScoreShort"+(CurrentBar), true, "Z", 0, High[0]+2.5*offset, 0, Brushes.Blue, myFont_Large, TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 100);
								Draw.Text(this, "ZScoreShort1", true, "weak Rev\nFT or BP", 0, Low[0], -50, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Transparent, 100);
								
							//	if (_ZScore[1]>1.5 && Open[1]<Close[1] && Low[1]>Close[0] && OB[0]<1) BackBrushes[0] = Brushes.LightPink;
							}
						}
						
						//two smaller bars
						if (1.5<_ZScore[1] && 1.2<_ZScore[0] && Range()[1]/2.1<BodyRange[1])
						{
							if ((Signal[1]==1 || Signal[1]==3 || Signal[1]==-3) && Signal[0]==1 &&
								Open[1]<Close[1] && Open[0]<Close[0] &&
								Open[1]<EMA1 && EMA0<Close[0] &&
								CountIf(delegate {return EMA(20)[2]>Close[2];},10)>4 &&
								!(Flip_Long[1]>0) && !(Flip_Long[0]>0))
							{
								Flip_Long[0] = Low[0]-offset; PlotBrushes[2][0] = Brushes.Blue;
								Draw.Text(this, "ZScoreLong"+(CurrentBar), true, "Z", 0, Low[0]-2.5*offset, 0, Brushes.Blue, myFont_Large, TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 100);
								Draw.Text(this, "ZScoreLong1", true, "weak Rev\nFT or BP", 0, High[0], 50, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Transparent, 100);
							//	if (EMA0>Median[0]) BackBrushes[0] = Brushes.Yellow;
							}
						}
						
						if (1.5<_ZScore[1] && 1.2<_ZScore[0] && Range()[1]/2.1<BodyRange[1])
						{
							if ((Signal[1]==-1 || Signal[1]==-3 || Signal[1]==3) && Signal[0]==-1 &&
								Open[1]>Close[1] && Open[0]>Close[0] &&
								Open[1]>EMA1 && EMA0>Close[0] &&
								CountIf(delegate {return EMA(20)[2]<Close[2];},10)>4 &&
								!(Flip_Short[1]>0) && !(Flip_Short[0]>0))
							{
								Flip_Short[0] = High[0]+offset; PlotBrushes[3][0] = Brushes.Blue;
								Draw.Text(this, "ZScoreShort"+(CurrentBar), true, "Z", 0, High[0]+2.5*offset, 0, Brushes.Blue, myFont_Large, TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 100);
								Draw.Text(this, "ZScoreShort1", true, "weak Rev\nFT or BP", 0, Low[0], -50, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Transparent, 100);
							//	if (EMA0>Median[0]) BackBrushes[0] = Brushes.Yellow;
							}
						}
						
						#endregion

						#region Bars 1&2
						//counter to a gap
						if (Bars.BarsSinceNewTradingDay==1 && (2<_ZScore[1] || 2<_ZScore[0]) && BarDir[1]==BarDir[0] &&
							(Range()[1]/4<BodyRange[1] || (Range()[1]/5<BodyRange[1] && (IBS1>=89 || IBS1<=11))) && 
							Range()[0]/4<BodyRange[0])
						{
							if (High[1]<Close[0] && Open[1]<Close[1] && Open[0]<Close[0] && EMA0-Range()[0]>High[0]) 
							{
								Flip_Long[0] = Low[0]-1.5*offset;
								Draw.Text(this, "ZScoreLong"+(CurrentBar), true, "Z", 2, Low[0]-1.0*offset, 0, Brushes.Yellow, myFont_Large, TextAlignment.Right, Brushes.Transparent, Brushes.Black, 50);
								Draw.Text(this, "ZScoreLongb2"+(CurrentBar), true, "SE b2", 1, High[0], 0, Brushes.Green, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
							//	BackBrushes[0] = Brushes.Yellow;
							}
							
							if (Low[1]>Close[0] && Open[1]>Close[1] && Open[0]>Close[0] && EMA0+Range()[0]<Low[0]) 
							{
								Flip_Short[0] = High[0]+1.5*offset;
								Draw.Text(this, "ZScoreShort"+(CurrentBar), true, "Z", 2, High[0]+1.0*offset, 0, Brushes.Yellow, myFont_Large, TextAlignment.Right, Brushes.Transparent, Brushes.Black, 50);
								Draw.Text(this, "ZScoreShortb2"+(CurrentBar), true, "SE b2", 1, Low[0], 0, Brushes.Crimson, myFont, TextAlignment.Right, Brushes.Transparent, Brushes.Yellow, 60);
							//	BackBrushes[0] = Brushes.Yellow;
							}
						}
						#endregion
					}
					
					#endregion
					
					#region wrong OB+FT
					if (ShowAIFlip && BarsPeriod.BarsPeriodType == BarsPeriodType.Minute && BarsPeriod.Value==5 &&
						Bars.BarsSinceNewTradingDay>1)
					{
						double OBRectH	= SMA(Range(),50)[1]/20;
						
						if (Signal[1]==-3 && Open[1]<Close[1] && IBS1>70 &&
							Open[0]<Close[0] && High[1]<Close[0] &&
							!(High[2]>Close[1] && (Range()[0]/2.5>BodyRange[0] || IBS<60)))
						{
							NinjaTrader.NinjaScript.DrawingTools.Rectangle myRect = Draw.Rectangle(this, "OB_BT"+(CurrentBar-1), false, 2, High[1]-OBRectH, -4, High[1]+OBRectH, Brushes.Transparent, Brushes.Yellow, 100, true);
							myRect.ZOrder = -1;
							
						//	BackBrushes[0] = Brushes.LightGreen;
						//	if (High[2]>Close[1] && (Range()[0]/2.5>BodyRange[0] || IBS<60)) BackBrushes[1] = Brushes.Yellow;
						}
						
						if (Signal[1]==3 && Open[1]>Close[1] && IBS1<30 &&
							Open[0]>Close[0] && Low[1]>Close[0] &&
							!(Low[2]<Close[1] && (Range()[0]/2.5>BodyRange[0] || IBS>40)))
						{
							NinjaTrader.NinjaScript.DrawingTools.Rectangle myRect = Draw.Rectangle(this, "OB_BT"+(CurrentBar-1), false, 2, Low[1]+OBRectH, -4, Low[1]-OBRectH, Brushes.Transparent, Brushes.Yellow, 100, true);
							myRect.ZOrder = -1;
							
						//	BackBrushes[0] = Brushes.LightPink;
						//	if (Low[2]<Close[1] && (Range()[0]/2.5>BodyRange[0] || IBS>40)) BackBrushes[1] = Brushes.Yellow;
						}
					}
					#endregion
//TD
                }

            }//end if H.count > 0
			
            #region This is the block where we handle the caught exception.
            catch (ArgumentOutOfRangeException argumentIndexEx)
            {
                // Submits an entry into the Control Center logs to inform the user of an error				
                Log("Index out of range." + argumentIndexEx.ToString(), NinjaTrader.Cbi.LogLevel.Warning);
            }
            catch (Exception e)
            {
                // In case the indicator has already been Terminated, you can safely ignore errors
                if (State >= State.Terminated)
                    return;

                /* With our caught exception we are able to generate log entries that go to the Control Center logs and also print more detailed information
				about the error to the Output Window. */

                // Submits an entry into the Control Center logs to inform the user of an error				
                Log("Exception Error: Please check your indicator for errors.", NinjaTrader.Cbi.LogLevel.Warning);

                // Prints the caught exception in the Output Window
                Print(Time[0] + " " + e.ToString());
            }
			#endregion
        }
		
        #region Properties
		
//TD
		#region Plots
		[Browsable(false)]
		[XmlIgnore]
		public Series<double> _Signal
		{
			get { return Values[0]; }
		}
		
		[Browsable(false)]
		[XmlIgnore]
		public Series<double> _FTflag
		{
			get { return Values[1]; }
		}
		
		[Browsable(false)]
		[XmlIgnore]
		public Series<double> Flip_Long
		{
			get { return Values[2]; }
		}
		
		[Browsable(false)]
		[XmlIgnore]
		public Series<double> Flip_Short
		{
			get { return Values[3]; }
		}
		
		[Browsable(false)]
		[XmlIgnore]
		public Series<double> _ZScore
		{
			get { return Values[4]; }
		}
		#endregion
//TD

        /*


        //-- Signal/Output Control --
        //INT	_PaintRevOnly(0 {0: Disable}),		// for future Dev.
        INT _PaintFTBar(0  {0: Disable}),
        INT _FTbarMustBO(0  {0: Disable}),
        INT _FTbarMustCloseBeyond(1  {0: Disable}),
        INT _FTbarNotRangeLimited(1  {0: Disable}),
        INT _FTafterOB(1  {0: Disable}),			// marks favorable FT after an outside bar
        INT _FTcolorSameAsBO(0 {0: Disable}),
        INT _IgnoreOpenGap(0 {0: Disable}),
        INT _SessOpenTime(-1 {-1: Auto | Time HHMM}),

        //-- Colors --
        INT _BLBOcolor(RGB(0, 128, 255)),
        INT _BRBOcolor(RGB(200, 0, 0)),
        INT _BigBLBOcolor(RGB(0, 230, 230)),
        INT _BigBRBOcolor(RGB(255, 0, 255)),
        INT _BLOBcolor(RGB(0, 128, 0)),
        INT _BROBcolor(RGB(255, 128, 0)),
        INT _BLCXcolor(RGB(0, 200, 255)),
        INT _BRCXcolor(RGB(255, 128, 255)),
        INT _DojiColor(RGB(255, 128, 255)),

        // FT colors
        INT _BLFTcolor(RGB(64, 200, 255)),
        INT _BRFTcolor(RGB(255, 64, 64)),

        //-- Alerts --
            _AlertText.BLBO("Bull Breakout"),
            _AlertText.BRBO("Bear Breakout"),
            //
            _AlertText.BigBLBO("Big Bull Breakout"),
            _AlertText.BigBRBO("Big Bear Breakout"),
            //
            _AlertText.BLOB("Bull Outside Bar"),
            _AlertText.BROB("Bear Outside Bar"),
            _AlertText.DojiOB("Neutral Outside Bar"),
            _AlertText.BLCX("Buy Climax"),
            _AlertText.BRCX("Sell Climax"),
            //
            _AlertText.BLFT("Bull Breakout and Follow Through"),
            _AlertText.BRFT("Bear Breakout and Follow Through"),
            //
            _AlertText.IB("Inside Bar"),
            _AlertText.OB("Outside Bar"),
        //
        INT _ChartData(1),
            _DebugON(False),
        INT Version.6(20230526);


            */
//TD
        [Display(Name = "Show AI Flip", Description = "", Order = 0, GroupName = "00. Tweak by TD")]
        public bool ShowAIFlip
        { get; set; }
		
        [Display(Name = "Paint Bars", Description = "", Order = 1, GroupName = "00. Tweak by TD")]
        public bool ColorBars
        { get; set; }
//TD
        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_ShowBLBO", Description = "Show Bull breakout", Order = 1, GroupName = "01. BO, OB, CX")]
        public int _ShowBLBO
        { get; set; }



        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_ShowBRBO", Description = "Show Bear breakout", Order = 2, GroupName = "01. BO, OB, CX")]
        public int _ShowBRBO
        { get; set; }


        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_ShowBigBO", Description = "Show Big breakout ", Order = 3, GroupName = "01. BO, OB, CX")]
        public int _ShowBigBO
        { get; set; }


        [Range(0, 10)]
        [NinjaScriptProperty]
        [Display(Name = "_BigBORangeFactor", Description = "Big BO Range Factor", Order = 4, GroupName = "01. BO, OB, CX")]
        public double _BigBORangeFactor
        { get; set; }



        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_ShowOutsideBars", Description = "Show Outside bars", Order = 5, GroupName = "01. BO, OB, CX")]
        public int _ShowOutsideBars
        { get; set; }


        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_StrictOB", Description = "Strict Outside bars", Order = 6, GroupName = "01. BO, OB, CX")]
        public int _StrictOB
        { get; set; }

        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_ShowCX", Description = "Show Climaxes", Order = 7, GroupName = "01. BO, OB, CX")]
        public int _ShowCX
        { get; set; }

        [Range(0, 10)]
        [NinjaScriptProperty]
        [Display(Name = "_CXfactor", Description = "Climax Factor", Order = 8, GroupName = "01. BO, OB, CX")]
        public double _CXfactor
        { get; set; }

        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_BigBObyZscore", Description = "Big Breakout by Z score", Order = 9, GroupName = "02. Z score")]
        public int _BigBObyZscore
        { get; set; }

        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_CompareRange2Range", Description = "Compare Range to Range", Order = 10, GroupName = "02. Z score")]
        public int _CompareRange2Range
        { get; set; }

        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_CompareBody2Body", Description = "Compare Body to Body", Order = 11, GroupName = "02. Z score")]
        public int _CompareBody2Body
        { get; set; }

        [Range(0, 1000)]
        [NinjaScriptProperty]
        [Display(Name = "_zLength", Description = "Z length", Order = 12, GroupName = "02. Z score")]
        public int _zLength
        { get; set; }

        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_RangeFilter", Description = "Range Filter", Order = 13, GroupName = "03. Range Filter")]
        public int _RangeFilter
        { get; set; }

        [Range(0, 1000)]
        [NinjaScriptProperty]
        [Display(Name = "_RangeLookBack", Description = "Range Lookback", Order = 14, GroupName = "03. Range Filter")]
        public int _RangeLookBack
        { get; set; }

        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_DoNotRangeLimitOB", Description = "Do Not Range Limit OB", Order = 15, GroupName = "03. Range Filter")]
        public int _DoNotRangeLimitOB
        { get; set; }

        [Range(-1, 100)]
        [NinjaScriptProperty]
        [Display(Name = "_BLsignalIBS", Description = "Bull signal IBS", Order = 16, GroupName = "04. IBS Filters")]
        public int _BLsignalIBS
        { get; set; }

        [Range(-1, 100)]
        [NinjaScriptProperty]
        [Display(Name = "_BRsignalIBS", Description = "Bear signal IBS", Order = 17, GroupName = "04. IBS Filters")]
        public int _BRsignalIBS
        { get; set; }

        [Range(-1, 100)]
        [NinjaScriptProperty]
        [Display(Name = "_BLFTbarIBS", Description = "Bull Follow through bar IBS", Order = 18, GroupName = "04. IBS Filters")]
        public int _BLFTbarIBS
        { get; set; }


        [Range(-1, 100)]
        [NinjaScriptProperty]
        [Display(Name = "_BRFTbarIBS", Description = "Bear Follow through bar IBS", Order = 19, GroupName = "04. IBS Filters")]
        public int _BRFTbarIBS
        { get; set; }

        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_DoNotIBSfilterOB", Description = "Do Not IBS filter OB", Order = 20, GroupName = "04. IBS Filters")]
        public int _DoNotIBSfilterOB
        { get; set; }


        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_PaintFTBar", Description = "Paint FT Bar", Order = 21, GroupName = "05. Signal/Output Control")]
        public int PaintFTBar
        { get; set; }


        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_FTbarMustBO", Description = "FT Bar Must Break Out", Order = 22, GroupName = "05. Signal/Output Control")]
        public int _FTbarMustBO
        { get; set; }


        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_FTbarMustCloseBeyond", Description = "FT bar Must Close Beyond", Order = 23, GroupName = "05. Signal/Output Control")]
        public int _FTbarMustCloseBeyond
        { get; set; }


        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_FTbarNotRangeLimited", Description = "FT bar Not Range Limited", Order = 24, GroupName = "05. Signal/Output Control")]
        public int _FTbarNotRangeLimited
        { get; set; }





        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_FTafterOB", Description = "FT After OB", Order = 25, GroupName = "05. Signal/Output Control")]
        public int _FTafterOB
        { get; set; }



        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_FTcolorSameAsBO", Description = "FT Color Same As BO", Order = 26, GroupName = "05. Signal/Output Control")]
        public int _FTcolorSameAsBO
        { get; set; }



        [Range(-1, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_IgnoreOpenGap", Description = "Ignore Open Gap", Order = 27, GroupName = "05. Signal/Output Control")]
        public int _IgnoreOpenGap
        { get; set; }


        [Range(-1, 9999)]
        [NinjaScriptProperty]
        [Display(Name = "_SessOpenTime", Description = "NOT USED (Automatically handled in NT)", Order = 28, GroupName = "05. Signal/Output Control")]
        public int _SessOpenTime
        { get; set; }


        //Colors

        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bull Breakout", GroupName = "06. Colors", Order = 29)]
        public Brush BLBOBrush
        { get; set; }


        // Serialize our Color object
        [Browsable(false)]
        public string BLBOBrushSerialize
        {
            get { return Serialize.BrushToString(BLBOBrush); }
            set { BLBOBrush = Serialize.StringToBrush(value); }
        }



        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bear Breakout", GroupName = "06. Colors", Order = 30)]
        public Brush BRBOBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BRBOBrushSerialize
        {
            get { return Serialize.BrushToString(BRBOBrush); }
            set { BRBOBrush = Serialize.StringToBrush(value); }
        }


        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Big Bull Breakout", GroupName = "06. Colors", Order = 31)]
        public Brush BigBLBOBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BigBLBOBrushSerialize
        {
            get { return Serialize.BrushToString(BigBLBOBrush); }
            set { BigBLBOBrush = Serialize.StringToBrush(value); }
        }

        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Big Bear Breakout", GroupName = "06. Colors", Order = 32)]
        public Brush BigBRBOBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BigBRBOBrushSerialize
        {
            get { return Serialize.BrushToString(BigBRBOBrush); }
            set { BigBRBOBrush = Serialize.StringToBrush(value); }
        }


        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bull Outside Bar", GroupName = "06. Colors", Order = 33)]
        public Brush BLOBBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BLOBBrushSerialize
        {
            get { return Serialize.BrushToString(BLOBBrush); }
            set { BLOBBrush = Serialize.StringToBrush(value); }
        }


        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bear Outside Bar", GroupName = "06. Colors", Order = 34)]
        public Brush BROBBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BROBBrushSerialize
        {
            get { return Serialize.BrushToString(BROBBrush); }
            set { BROBBrush = Serialize.StringToBrush(value); }
        }


        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bull Climax", GroupName = "06. Colors", Order = 35)]
        public Brush BLCXBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BLCXBrushSerialize
        {
            get { return Serialize.BrushToString(BLCXBrush); }
            set { BLCXBrush = Serialize.StringToBrush(value); }
        }

        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bear Climax", GroupName = "06. Colors", Order = 36)]
        public Brush BRCXBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BRCXBrushSerialize
        {
            get { return Serialize.BrushToString(BRCXBrush); }
            set { BRCXBrush = Serialize.StringToBrush(value); }
        }

        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Doji", GroupName = "06. Colors", Order = 37)]
        public Brush DojiBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string DojiBrushSerialize
        {
            get { return Serialize.BrushToString(DojiBrush); }
            set { DojiBrush = Serialize.StringToBrush(value); }
        }

        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bull Follow Through", GroupName = "07. FT Colors", Order = 38)]
        public Brush BLFTBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BLFTBrushSerialize
        {
            get { return Serialize.BrushToString(BLFTBrush); }
            set { BLFTBrush = Serialize.StringToBrush(value); }
        }

        // Create our user definable color input
        [XmlIgnore()]
        [Display(Name = "Bear Follow Through", GroupName = "07. FT Colors", Order = 39)]
        public Brush BRFTBrush
        { get; set; }

        // Serialize our Color object
        [Browsable(false)]
        public string BRFTBrushSerialize
        {
            get { return Serialize.BrushToString(BRFTBrush); }
            set { BRFTBrush = Serialize.StringToBrush(value); }
        }

        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "AlertEnabled", Description = "Show Alerts", Order = 40, GroupName = "08. Alerts")]
        public int AlertEnabled
        { get; set; }


        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BLBO", Description = "AlertText BLBO ", Order = 41, GroupName = "08. Alerts")]
        public string _AlertText_BLBO
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BRBO", Description = "_AlertText_BRBO", Order = 42, GroupName = "08. Alerts")]
        public string _AlertText_BRBO
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BigBLBO", Description = "_AlertText_BigBLBO", Order = 43, GroupName = "08. Alerts")]
        public string _AlertText_BigBLBO
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BigBRBO", Description = "_AlertText_BigBRBO", Order = 44, GroupName = "08. Alerts")]
        public string _AlertText_BigBRBO
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BLOB", Description = "_AlertText_BLOB", Order = 45, GroupName = "08. Alerts")]
        public string _AlertText_BLOB
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BROB", Description = "_AlertText_BROB", Order = 46, GroupName = "08. Alerts")]
        public string _AlertText_BROB
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_DojiOB", Description = "_AlertText_DojiOB", Order = 47, GroupName = "08. Alerts")]
        public string _AlertText_DojiOB
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BLCX", Description = "_AlertText_BLCX", Order = 48, GroupName = "08. Alerts")]
        public string _AlertText_BLCX
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BRCX", Description = "_AlertText_BRCX", Order = 49, GroupName = "08. Alerts")]
        public string _AlertText_BRCX
        { get; set; }


        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BLFT", Description = "_AlertText_BLFT", Order = 50, GroupName = "08. Alerts")]
        public string _AlertText_BLFT
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_BRFT", Description = "_AlertText_BRFT", Order = 51, GroupName = "08. Alerts")]
        public string _AlertText_BRFT
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "_AlertText_IB", Description = "_AlertText_IB", Order = 52, GroupName = "08. Alerts")]
        public string _AlertText_IB
        { get; set; }


        [NinjaScriptProperty]
        [Display(Name = "_AlertText_OB", Description = "_AlertText_OB", Order = 53, GroupName = "08. Alerts")]
        public string _AlertText_OB
        { get; set; }


        [NinjaScriptProperty]
        [Display(Name = "Version", Description = "Version", Order = 54, GroupName = "09. Misc")]
        public string Version
        { get; set; }


        [NinjaScriptProperty]
        [Display(Name = "Debug On", Description = "Debug", Order = 55, GroupName = "09. Misc")]
        public bool _DebugON
        { get; set; }


        [Range(0, 1)]
        [NinjaScriptProperty]
        [Display(Name = "_ChartData", Description = "NOT USED _ChartData", Order = 56, GroupName = "09. Misc")]
        public int _ChartData
        { get; set; }
		
        //-- IBS Filters -- (for future dev)
        //	_BLbarIBS(-1 {-1: Disable | 0-100}),
        //	_BRbarIBS(-1 {-1: Disable | 0-100}),




        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private AMABreakoutsPB6[] cacheAMABreakoutsPB6;
		public AMABreakoutsPB6 AMABreakoutsPB6(int _showBLBO, int _showBRBO, int _showBigBO, double _bigBORangeFactor, int _showOutsideBars, int _strictOB, int _showCX, double _cXfactor, int _bigBObyZscore, int _compareRange2Range, int _compareBody2Body, int _zLength, int _rangeFilter, int _rangeLookBack, int _doNotRangeLimitOB, int _bLsignalIBS, int _bRsignalIBS, int _bLFTbarIBS, int _bRFTbarIBS, int _doNotIBSfilterOB, int paintFTBar, int _fTbarMustBO, int _fTbarMustCloseBeyond, int _fTbarNotRangeLimited, int _fTafterOB, int _fTcolorSameAsBO, int _ignoreOpenGap, int _sessOpenTime, int alertEnabled, string _alertText_BLBO, string _alertText_BRBO, string _alertText_BigBLBO, string _alertText_BigBRBO, string _alertText_BLOB, string _alertText_BROB, string _alertText_DojiOB, string _alertText_BLCX, string _alertText_BRCX, string _alertText_BLFT, string _alertText_BRFT, string _alertText_IB, string _alertText_OB, string version, bool _debugON, int _chartData)
		{
			return AMABreakoutsPB6(Input, _showBLBO, _showBRBO, _showBigBO, _bigBORangeFactor, _showOutsideBars, _strictOB, _showCX, _cXfactor, _bigBObyZscore, _compareRange2Range, _compareBody2Body, _zLength, _rangeFilter, _rangeLookBack, _doNotRangeLimitOB, _bLsignalIBS, _bRsignalIBS, _bLFTbarIBS, _bRFTbarIBS, _doNotIBSfilterOB, paintFTBar, _fTbarMustBO, _fTbarMustCloseBeyond, _fTbarNotRangeLimited, _fTafterOB, _fTcolorSameAsBO, _ignoreOpenGap, _sessOpenTime, alertEnabled, _alertText_BLBO, _alertText_BRBO, _alertText_BigBLBO, _alertText_BigBRBO, _alertText_BLOB, _alertText_BROB, _alertText_DojiOB, _alertText_BLCX, _alertText_BRCX, _alertText_BLFT, _alertText_BRFT, _alertText_IB, _alertText_OB, version, _debugON, _chartData);
		}

		public AMABreakoutsPB6 AMABreakoutsPB6(ISeries<double> input, int _showBLBO, int _showBRBO, int _showBigBO, double _bigBORangeFactor, int _showOutsideBars, int _strictOB, int _showCX, double _cXfactor, int _bigBObyZscore, int _compareRange2Range, int _compareBody2Body, int _zLength, int _rangeFilter, int _rangeLookBack, int _doNotRangeLimitOB, int _bLsignalIBS, int _bRsignalIBS, int _bLFTbarIBS, int _bRFTbarIBS, int _doNotIBSfilterOB, int paintFTBar, int _fTbarMustBO, int _fTbarMustCloseBeyond, int _fTbarNotRangeLimited, int _fTafterOB, int _fTcolorSameAsBO, int _ignoreOpenGap, int _sessOpenTime, int alertEnabled, string _alertText_BLBO, string _alertText_BRBO, string _alertText_BigBLBO, string _alertText_BigBRBO, string _alertText_BLOB, string _alertText_BROB, string _alertText_DojiOB, string _alertText_BLCX, string _alertText_BRCX, string _alertText_BLFT, string _alertText_BRFT, string _alertText_IB, string _alertText_OB, string version, bool _debugON, int _chartData)
		{
			if (cacheAMABreakoutsPB6 != null)
				for (int idx = 0; idx < cacheAMABreakoutsPB6.Length; idx++)
					if (cacheAMABreakoutsPB6[idx] != null && cacheAMABreakoutsPB6[idx]._ShowBLBO == _showBLBO && cacheAMABreakoutsPB6[idx]._ShowBRBO == _showBRBO && cacheAMABreakoutsPB6[idx]._ShowBigBO == _showBigBO && cacheAMABreakoutsPB6[idx]._BigBORangeFactor == _bigBORangeFactor && cacheAMABreakoutsPB6[idx]._ShowOutsideBars == _showOutsideBars && cacheAMABreakoutsPB6[idx]._StrictOB == _strictOB && cacheAMABreakoutsPB6[idx]._ShowCX == _showCX && cacheAMABreakoutsPB6[idx]._CXfactor == _cXfactor && cacheAMABreakoutsPB6[idx]._BigBObyZscore == _bigBObyZscore && cacheAMABreakoutsPB6[idx]._CompareRange2Range == _compareRange2Range && cacheAMABreakoutsPB6[idx]._CompareBody2Body == _compareBody2Body && cacheAMABreakoutsPB6[idx]._zLength == _zLength && cacheAMABreakoutsPB6[idx]._RangeFilter == _rangeFilter && cacheAMABreakoutsPB6[idx]._RangeLookBack == _rangeLookBack && cacheAMABreakoutsPB6[idx]._DoNotRangeLimitOB == _doNotRangeLimitOB && cacheAMABreakoutsPB6[idx]._BLsignalIBS == _bLsignalIBS && cacheAMABreakoutsPB6[idx]._BRsignalIBS == _bRsignalIBS && cacheAMABreakoutsPB6[idx]._BLFTbarIBS == _bLFTbarIBS && cacheAMABreakoutsPB6[idx]._BRFTbarIBS == _bRFTbarIBS && cacheAMABreakoutsPB6[idx]._DoNotIBSfilterOB == _doNotIBSfilterOB && cacheAMABreakoutsPB6[idx].PaintFTBar == paintFTBar && cacheAMABreakoutsPB6[idx]._FTbarMustBO == _fTbarMustBO && cacheAMABreakoutsPB6[idx]._FTbarMustCloseBeyond == _fTbarMustCloseBeyond && cacheAMABreakoutsPB6[idx]._FTbarNotRangeLimited == _fTbarNotRangeLimited && cacheAMABreakoutsPB6[idx]._FTafterOB == _fTafterOB && cacheAMABreakoutsPB6[idx]._FTcolorSameAsBO == _fTcolorSameAsBO && cacheAMABreakoutsPB6[idx]._IgnoreOpenGap == _ignoreOpenGap && cacheAMABreakoutsPB6[idx]._SessOpenTime == _sessOpenTime && cacheAMABreakoutsPB6[idx].AlertEnabled == alertEnabled && cacheAMABreakoutsPB6[idx]._AlertText_BLBO == _alertText_BLBO && cacheAMABreakoutsPB6[idx]._AlertText_BRBO == _alertText_BRBO && cacheAMABreakoutsPB6[idx]._AlertText_BigBLBO == _alertText_BigBLBO && cacheAMABreakoutsPB6[idx]._AlertText_BigBRBO == _alertText_BigBRBO && cacheAMABreakoutsPB6[idx]._AlertText_BLOB == _alertText_BLOB && cacheAMABreakoutsPB6[idx]._AlertText_BROB == _alertText_BROB && cacheAMABreakoutsPB6[idx]._AlertText_DojiOB == _alertText_DojiOB && cacheAMABreakoutsPB6[idx]._AlertText_BLCX == _alertText_BLCX && cacheAMABreakoutsPB6[idx]._AlertText_BRCX == _alertText_BRCX && cacheAMABreakoutsPB6[idx]._AlertText_BLFT == _alertText_BLFT && cacheAMABreakoutsPB6[idx]._AlertText_BRFT == _alertText_BRFT && cacheAMABreakoutsPB6[idx]._AlertText_IB == _alertText_IB && cacheAMABreakoutsPB6[idx]._AlertText_OB == _alertText_OB && cacheAMABreakoutsPB6[idx].Version == version && cacheAMABreakoutsPB6[idx]._DebugON == _debugON && cacheAMABreakoutsPB6[idx]._ChartData == _chartData && cacheAMABreakoutsPB6[idx].EqualsInput(input))
						return cacheAMABreakoutsPB6[idx];
			return CacheIndicator<AMABreakoutsPB6>(new AMABreakoutsPB6(){ _ShowBLBO = _showBLBO, _ShowBRBO = _showBRBO, _ShowBigBO = _showBigBO, _BigBORangeFactor = _bigBORangeFactor, _ShowOutsideBars = _showOutsideBars, _StrictOB = _strictOB, _ShowCX = _showCX, _CXfactor = _cXfactor, _BigBObyZscore = _bigBObyZscore, _CompareRange2Range = _compareRange2Range, _CompareBody2Body = _compareBody2Body, _zLength = _zLength, _RangeFilter = _rangeFilter, _RangeLookBack = _rangeLookBack, _DoNotRangeLimitOB = _doNotRangeLimitOB, _BLsignalIBS = _bLsignalIBS, _BRsignalIBS = _bRsignalIBS, _BLFTbarIBS = _bLFTbarIBS, _BRFTbarIBS = _bRFTbarIBS, _DoNotIBSfilterOB = _doNotIBSfilterOB, PaintFTBar = paintFTBar, _FTbarMustBO = _fTbarMustBO, _FTbarMustCloseBeyond = _fTbarMustCloseBeyond, _FTbarNotRangeLimited = _fTbarNotRangeLimited, _FTafterOB = _fTafterOB, _FTcolorSameAsBO = _fTcolorSameAsBO, _IgnoreOpenGap = _ignoreOpenGap, _SessOpenTime = _sessOpenTime, AlertEnabled = alertEnabled, _AlertText_BLBO = _alertText_BLBO, _AlertText_BRBO = _alertText_BRBO, _AlertText_BigBLBO = _alertText_BigBLBO, _AlertText_BigBRBO = _alertText_BigBRBO, _AlertText_BLOB = _alertText_BLOB, _AlertText_BROB = _alertText_BROB, _AlertText_DojiOB = _alertText_DojiOB, _AlertText_BLCX = _alertText_BLCX, _AlertText_BRCX = _alertText_BRCX, _AlertText_BLFT = _alertText_BLFT, _AlertText_BRFT = _alertText_BRFT, _AlertText_IB = _alertText_IB, _AlertText_OB = _alertText_OB, Version = version, _DebugON = _debugON, _ChartData = _chartData }, input, ref cacheAMABreakoutsPB6);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.AMABreakoutsPB6 AMABreakoutsPB6(int _showBLBO, int _showBRBO, int _showBigBO, double _bigBORangeFactor, int _showOutsideBars, int _strictOB, int _showCX, double _cXfactor, int _bigBObyZscore, int _compareRange2Range, int _compareBody2Body, int _zLength, int _rangeFilter, int _rangeLookBack, int _doNotRangeLimitOB, int _bLsignalIBS, int _bRsignalIBS, int _bLFTbarIBS, int _bRFTbarIBS, int _doNotIBSfilterOB, int paintFTBar, int _fTbarMustBO, int _fTbarMustCloseBeyond, int _fTbarNotRangeLimited, int _fTafterOB, int _fTcolorSameAsBO, int _ignoreOpenGap, int _sessOpenTime, int alertEnabled, string _alertText_BLBO, string _alertText_BRBO, string _alertText_BigBLBO, string _alertText_BigBRBO, string _alertText_BLOB, string _alertText_BROB, string _alertText_DojiOB, string _alertText_BLCX, string _alertText_BRCX, string _alertText_BLFT, string _alertText_BRFT, string _alertText_IB, string _alertText_OB, string version, bool _debugON, int _chartData)
		{
			return indicator.AMABreakoutsPB6(Input, _showBLBO, _showBRBO, _showBigBO, _bigBORangeFactor, _showOutsideBars, _strictOB, _showCX, _cXfactor, _bigBObyZscore, _compareRange2Range, _compareBody2Body, _zLength, _rangeFilter, _rangeLookBack, _doNotRangeLimitOB, _bLsignalIBS, _bRsignalIBS, _bLFTbarIBS, _bRFTbarIBS, _doNotIBSfilterOB, paintFTBar, _fTbarMustBO, _fTbarMustCloseBeyond, _fTbarNotRangeLimited, _fTafterOB, _fTcolorSameAsBO, _ignoreOpenGap, _sessOpenTime, alertEnabled, _alertText_BLBO, _alertText_BRBO, _alertText_BigBLBO, _alertText_BigBRBO, _alertText_BLOB, _alertText_BROB, _alertText_DojiOB, _alertText_BLCX, _alertText_BRCX, _alertText_BLFT, _alertText_BRFT, _alertText_IB, _alertText_OB, version, _debugON, _chartData);
		}

		public Indicators.AMABreakoutsPB6 AMABreakoutsPB6(ISeries<double> input , int _showBLBO, int _showBRBO, int _showBigBO, double _bigBORangeFactor, int _showOutsideBars, int _strictOB, int _showCX, double _cXfactor, int _bigBObyZscore, int _compareRange2Range, int _compareBody2Body, int _zLength, int _rangeFilter, int _rangeLookBack, int _doNotRangeLimitOB, int _bLsignalIBS, int _bRsignalIBS, int _bLFTbarIBS, int _bRFTbarIBS, int _doNotIBSfilterOB, int paintFTBar, int _fTbarMustBO, int _fTbarMustCloseBeyond, int _fTbarNotRangeLimited, int _fTafterOB, int _fTcolorSameAsBO, int _ignoreOpenGap, int _sessOpenTime, int alertEnabled, string _alertText_BLBO, string _alertText_BRBO, string _alertText_BigBLBO, string _alertText_BigBRBO, string _alertText_BLOB, string _alertText_BROB, string _alertText_DojiOB, string _alertText_BLCX, string _alertText_BRCX, string _alertText_BLFT, string _alertText_BRFT, string _alertText_IB, string _alertText_OB, string version, bool _debugON, int _chartData)
		{
			return indicator.AMABreakoutsPB6(input, _showBLBO, _showBRBO, _showBigBO, _bigBORangeFactor, _showOutsideBars, _strictOB, _showCX, _cXfactor, _bigBObyZscore, _compareRange2Range, _compareBody2Body, _zLength, _rangeFilter, _rangeLookBack, _doNotRangeLimitOB, _bLsignalIBS, _bRsignalIBS, _bLFTbarIBS, _bRFTbarIBS, _doNotIBSfilterOB, paintFTBar, _fTbarMustBO, _fTbarMustCloseBeyond, _fTbarNotRangeLimited, _fTafterOB, _fTcolorSameAsBO, _ignoreOpenGap, _sessOpenTime, alertEnabled, _alertText_BLBO, _alertText_BRBO, _alertText_BigBLBO, _alertText_BigBRBO, _alertText_BLOB, _alertText_BROB, _alertText_DojiOB, _alertText_BLCX, _alertText_BRCX, _alertText_BLFT, _alertText_BRFT, _alertText_IB, _alertText_OB, version, _debugON, _chartData);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.AMABreakoutsPB6 AMABreakoutsPB6(int _showBLBO, int _showBRBO, int _showBigBO, double _bigBORangeFactor, int _showOutsideBars, int _strictOB, int _showCX, double _cXfactor, int _bigBObyZscore, int _compareRange2Range, int _compareBody2Body, int _zLength, int _rangeFilter, int _rangeLookBack, int _doNotRangeLimitOB, int _bLsignalIBS, int _bRsignalIBS, int _bLFTbarIBS, int _bRFTbarIBS, int _doNotIBSfilterOB, int paintFTBar, int _fTbarMustBO, int _fTbarMustCloseBeyond, int _fTbarNotRangeLimited, int _fTafterOB, int _fTcolorSameAsBO, int _ignoreOpenGap, int _sessOpenTime, int alertEnabled, string _alertText_BLBO, string _alertText_BRBO, string _alertText_BigBLBO, string _alertText_BigBRBO, string _alertText_BLOB, string _alertText_BROB, string _alertText_DojiOB, string _alertText_BLCX, string _alertText_BRCX, string _alertText_BLFT, string _alertText_BRFT, string _alertText_IB, string _alertText_OB, string version, bool _debugON, int _chartData)
		{
			return indicator.AMABreakoutsPB6(Input, _showBLBO, _showBRBO, _showBigBO, _bigBORangeFactor, _showOutsideBars, _strictOB, _showCX, _cXfactor, _bigBObyZscore, _compareRange2Range, _compareBody2Body, _zLength, _rangeFilter, _rangeLookBack, _doNotRangeLimitOB, _bLsignalIBS, _bRsignalIBS, _bLFTbarIBS, _bRFTbarIBS, _doNotIBSfilterOB, paintFTBar, _fTbarMustBO, _fTbarMustCloseBeyond, _fTbarNotRangeLimited, _fTafterOB, _fTcolorSameAsBO, _ignoreOpenGap, _sessOpenTime, alertEnabled, _alertText_BLBO, _alertText_BRBO, _alertText_BigBLBO, _alertText_BigBRBO, _alertText_BLOB, _alertText_BROB, _alertText_DojiOB, _alertText_BLCX, _alertText_BRCX, _alertText_BLFT, _alertText_BRFT, _alertText_IB, _alertText_OB, version, _debugON, _chartData);
		}

		public Indicators.AMABreakoutsPB6 AMABreakoutsPB6(ISeries<double> input , int _showBLBO, int _showBRBO, int _showBigBO, double _bigBORangeFactor, int _showOutsideBars, int _strictOB, int _showCX, double _cXfactor, int _bigBObyZscore, int _compareRange2Range, int _compareBody2Body, int _zLength, int _rangeFilter, int _rangeLookBack, int _doNotRangeLimitOB, int _bLsignalIBS, int _bRsignalIBS, int _bLFTbarIBS, int _bRFTbarIBS, int _doNotIBSfilterOB, int paintFTBar, int _fTbarMustBO, int _fTbarMustCloseBeyond, int _fTbarNotRangeLimited, int _fTafterOB, int _fTcolorSameAsBO, int _ignoreOpenGap, int _sessOpenTime, int alertEnabled, string _alertText_BLBO, string _alertText_BRBO, string _alertText_BigBLBO, string _alertText_BigBRBO, string _alertText_BLOB, string _alertText_BROB, string _alertText_DojiOB, string _alertText_BLCX, string _alertText_BRCX, string _alertText_BLFT, string _alertText_BRFT, string _alertText_IB, string _alertText_OB, string version, bool _debugON, int _chartData)
		{
			return indicator.AMABreakoutsPB6(input, _showBLBO, _showBRBO, _showBigBO, _bigBORangeFactor, _showOutsideBars, _strictOB, _showCX, _cXfactor, _bigBObyZscore, _compareRange2Range, _compareBody2Body, _zLength, _rangeFilter, _rangeLookBack, _doNotRangeLimitOB, _bLsignalIBS, _bRsignalIBS, _bLFTbarIBS, _bRFTbarIBS, _doNotIBSfilterOB, paintFTBar, _fTbarMustBO, _fTbarMustCloseBeyond, _fTbarNotRangeLimited, _fTafterOB, _fTcolorSameAsBO, _ignoreOpenGap, _sessOpenTime, alertEnabled, _alertText_BLBO, _alertText_BRBO, _alertText_BigBLBO, _alertText_BigBRBO, _alertText_BLOB, _alertText_BROB, _alertText_DojiOB, _alertText_BLCX, _alertText_BRCX, _alertText_BLFT, _alertText_BRFT, _alertText_IB, _alertText_OB, version, _debugON, _chartData);
		}
	}
}

#endregion
