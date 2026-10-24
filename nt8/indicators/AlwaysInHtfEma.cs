#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// Plots an EMA calculated on the primary (tick) series and colours it by Always In state:
    /// N consecutive 5-minute closes above the tick EMA = Always In Long,
    /// N consecutive 5-minute closes below the tick EMA = Always In Short.
    /// </summary>
    public class AlwaysInHtfEma : Indicator
    {
        private EMA ema;
        private SMA abr; // average bar range of the tick bars
        private int aboveCount;
        private int belowCount;
        private int aiState; // 1 = AIL, -1 = AIS, 0 = neutral

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description               = "Tick-chart EMA coloured by Always In state from consecutive 5-min closes.";
                Name                      = "AlwaysInHtfEma";
                Calculate                 = Calculate.OnBarClose;
                IsOverlay                 = true;
                DisplayInDataBox          = true;
                DrawOnPricePanel          = true;
                PaintPriceMarkers         = true;
                IsSuspendedWhileInactive  = true;

                Period            = 20;
                ConsecutiveCloses = 2;
                UseStrongBreakout = true;
                StrongBodyMultiplier = 3.0;
                AbrPeriod         = 8;
                UseGapAsBody      = true;
                LongBrush         = Brushes.LimeGreen;
                ShortBrush        = Brushes.Red;
                NeutralBrush      = Brushes.Gray;

                AddPlot(new Stroke(Brushes.Gray, 2), PlotStyle.Line, "AlwaysInEma");
            }
            else if (State == State.Configure)
            {
                // Hardcoded on purpose: NinjaTrader requires AddDataSeries arguments to be constants.
                AddDataSeries(BarsPeriodType.Minute, 5);
            }
            else if (State == State.DataLoaded)
            {
                ema        = EMA(Closes[0], Period);
                abr        = SMA(Range(BarsArray[0]), AbrPeriod);
                aboveCount = 0;
                belowCount = 0;
                aiState    = 0;
            }
        }

        protected override void OnBarUpdate()
        {
            // Primary tick series: plot the EMA and colour it by the current state
            if (BarsInProgress == 0)
            {
                // Opening gap treated as a 5-min bar: body = session open - prior session close.
                // Evaluated as soon as the first tick bar of the session has closed.
                if (UseStrongBreakout && UseGapAsBody)
                {
                    bool closedAtZero = Calculate == Calculate.OnBarClose
                                        || (State == State.Historical && !Bars.IsTickReplay);
                    int i = closedAtZero ? 0 : 1;

                    if (CurrentBar > Math.Max(Period, AbrPeriod) + i
                        && (closedAtZero || IsFirstTickOfBar)
                        && Bars.IsFirstBarOfSessionByIndex(CurrentBar - i))
                    {
                        double gap       = Open[i] - Close[i + 1];
                        double threshold = StrongBodyMultiplier * abr[i];

                        if (threshold > 0 && Math.Abs(gap) > threshold)
                        {
                            if (gap > 0 && Close[i] > ema[i])
                            {
                                aiState    = 1;
                                aboveCount = 0;
                                belowCount = 0;
                            }
                            else if (gap < 0 && Close[i] < ema[i])
                            {
                                aiState    = -1;
                                aboveCount = 0;
                                belowCount = 0;
                            }
                        }
                    }
                }

                Value[0] = ema[0];
                PlotBrushes[0][0] = aiState == 1 ? LongBrush
                                  : aiState == -1 ? ShortBrush
                                  : NeutralBrush;
                return;
            }

            // 5-minute series: evaluate each completed 5-min bar against the tick EMA
            if (BarsInProgress == 1)
            {
                if (CurrentBars[0] < Math.Max(Period, AbrPeriod))
                    return;

                // With OnBarClose (or historical without Tick Replay) the closed 5-min bar is at index 0.
                // With OnEachTick / OnPriceChange it is at index 1 on the first tick of the new bar.
                bool closedBarAtZero = Calculate == Calculate.OnBarClose
                                       || (State == State.Historical && !BarsArray[0].IsTickReplay);

                int idx = closedBarAtZero ? 0 : 1;
                if (!closedBarAtZero && (!IsFirstTickOfBar || CurrentBars[1] < 1))
                    return;

                double htfClose = Closes[1][idx];
                double htfOpen  = Opens[1][idx];
                double bodyStart = htfOpen;

                double emaValue = ema[0];

                if (htfClose > emaValue)
                {
                    aboveCount++;
                    belowCount = 0;
                }
                else if (htfClose < emaValue)
                {
                    belowCount++;
                    aboveCount = 0;
                }
                else
                {
                    aboveCount = 0;
                    belowCount = 0;
                }

                // Strong breakout: body > multiplier x tick ABR, closing on the breakout side of the EMA
                bool strongBull = false, strongBear = false;
                if (UseStrongBreakout)
                {
                    double body      = Math.Abs(htfClose - bodyStart);
                    double threshold = StrongBodyMultiplier * abr[0];
                    if (threshold > 0 && body > threshold)
                    {
                        strongBull = htfClose > bodyStart && htfClose > emaValue;
                        strongBear = htfClose < bodyStart && htfClose < emaValue;
                    }
                }

                if (strongBull || aboveCount >= ConsecutiveCloses)
                    aiState = 1;
                else if (strongBear || belowCount >= ConsecutiveCloses)
                    aiState = -1;
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "EMA period", Order = 1, GroupName = "Parameters")]
        public int Period { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Consecutive 5-min closes", Order = 2, GroupName = "Parameters")]
        public int ConsecutiveCloses { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Use strong breakout", Order = 1, GroupName = "Strong breakout")]
        public bool UseStrongBreakout { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, double.MaxValue)]
        [Display(Name = "Body > x ABR", Order = 2, GroupName = "Strong breakout")]
        public double StrongBodyMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "ABR period (tick bars)", Order = 3, GroupName = "Strong breakout")]
        public int AbrPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Opening gap counts as strong bar", Order = 4, GroupName = "Strong breakout")]
        public bool UseGapAsBody { get; set; }

        [XmlIgnore]
        [Display(Name = "Always In Long colour", Order = 1, GroupName = "Colours")]
        public Brush LongBrush { get; set; }

        [Browsable(false)]
        public string LongBrushSerializable
        {
            get { return Serialize.BrushToString(LongBrush); }
            set { LongBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Always In Short colour", Order = 2, GroupName = "Colours")]
        public Brush ShortBrush { get; set; }

        [Browsable(false)]
        public string ShortBrushSerializable
        {
            get { return Serialize.BrushToString(ShortBrush); }
            set { ShortBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Neutral colour", Order = 3, GroupName = "Colours")]
        public Brush NeutralBrush { get; set; }

        [Browsable(false)]
        public string NeutralBrushSerializable
        {
            get { return Serialize.BrushToString(NeutralBrush); }
            set { NeutralBrush = Serialize.StringToBrush(value); }
        }
        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private AlwaysInHtfEma[] cacheAlwaysInHtfEma;
		public AlwaysInHtfEma AlwaysInHtfEma(int period, int consecutiveCloses, bool useStrongBreakout, double strongBodyMultiplier, int abrPeriod, bool useGapAsBody)
		{
			return AlwaysInHtfEma(Input, period, consecutiveCloses, useStrongBreakout, strongBodyMultiplier, abrPeriod, useGapAsBody);
		}

		public AlwaysInHtfEma AlwaysInHtfEma(ISeries<double> input, int period, int consecutiveCloses, bool useStrongBreakout, double strongBodyMultiplier, int abrPeriod, bool useGapAsBody)
		{
			if (cacheAlwaysInHtfEma != null)
				for (int idx = 0; idx < cacheAlwaysInHtfEma.Length; idx++)
					if (cacheAlwaysInHtfEma[idx] != null && cacheAlwaysInHtfEma[idx].Period == period && cacheAlwaysInHtfEma[idx].ConsecutiveCloses == consecutiveCloses && cacheAlwaysInHtfEma[idx].UseStrongBreakout == useStrongBreakout && cacheAlwaysInHtfEma[idx].StrongBodyMultiplier == strongBodyMultiplier && cacheAlwaysInHtfEma[idx].AbrPeriod == abrPeriod && cacheAlwaysInHtfEma[idx].UseGapAsBody == useGapAsBody && cacheAlwaysInHtfEma[idx].EqualsInput(input))
						return cacheAlwaysInHtfEma[idx];
			return CacheIndicator<AlwaysInHtfEma>(new AlwaysInHtfEma(){ Period = period, ConsecutiveCloses = consecutiveCloses, UseStrongBreakout = useStrongBreakout, StrongBodyMultiplier = strongBodyMultiplier, AbrPeriod = abrPeriod, UseGapAsBody = useGapAsBody }, input, ref cacheAlwaysInHtfEma);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.AlwaysInHtfEma AlwaysInHtfEma(int period, int consecutiveCloses, bool useStrongBreakout, double strongBodyMultiplier, int abrPeriod, bool useGapAsBody)
		{
			return indicator.AlwaysInHtfEma(Input, period, consecutiveCloses, useStrongBreakout, strongBodyMultiplier, abrPeriod, useGapAsBody);
		}

		public Indicators.AlwaysInHtfEma AlwaysInHtfEma(ISeries<double> input , int period, int consecutiveCloses, bool useStrongBreakout, double strongBodyMultiplier, int abrPeriod, bool useGapAsBody)
		{
			return indicator.AlwaysInHtfEma(input, period, consecutiveCloses, useStrongBreakout, strongBodyMultiplier, abrPeriod, useGapAsBody);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.AlwaysInHtfEma AlwaysInHtfEma(int period, int consecutiveCloses, bool useStrongBreakout, double strongBodyMultiplier, int abrPeriod, bool useGapAsBody)
		{
			return indicator.AlwaysInHtfEma(Input, period, consecutiveCloses, useStrongBreakout, strongBodyMultiplier, abrPeriod, useGapAsBody);
		}

		public Indicators.AlwaysInHtfEma AlwaysInHtfEma(ISeries<double> input , int period, int consecutiveCloses, bool useStrongBreakout, double strongBodyMultiplier, int abrPeriod, bool useGapAsBody)
		{
			return indicator.AlwaysInHtfEma(input, period, consecutiveCloses, useStrongBreakout, strongBodyMultiplier, abrPeriod, useGapAsBody);
		}
	}
}

#endregion
