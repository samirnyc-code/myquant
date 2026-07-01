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

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MyChartReader : Indicator
    {
        private StreamWriter writer;

        [Display(Name = "CSV File Path", Description = "Full path to output CSV file", Order = 1, GroupName = "Parameters")]
        public string CsvFilePath { get; set; }

        [Display(Name = "Print to Output Window", Description = "Also print each bar to the NT8 Output window", Order = 2, GroupName = "Parameters")]
        public bool PrintToOutput { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description             = "Exports bar data to CSV in Sierra Charts format.";
                Name                    = "MyChartReader";
                Calculate               = Calculate.OnBarClose;
                IsOverlay               = true;
                DisplayInDataBox        = false;
                DrawOnPricePanel        = false;
                DrawHorizontalGridLines = false;
                DrawVerticalGridLines   = false;
                PaintPriceMarkers       = false;
                IsSuspendedWhileInactive = true;

                CsvFilePath   = @"C:\Users\Public\Documents\NinjaTrader 8\bar_export.csv";
                PrintToOutput = false;
            }
            else if (State == State.Configure)
            {
                try
                {
                    string dir = Path.GetDirectoryName(CsvFilePath);
                    if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                        Directory.CreateDirectory(dir);

                    writer = new StreamWriter(CsvFilePath, false, Encoding.UTF8);
                }
                catch (Exception ex)
                {
                    Log("MyChartReader: Failed to open CSV file: " + ex.Message, LogLevel.Error);
                }
            }
            else if (State == State.Terminated)
            {
                if (writer != null)
                {
                    writer.Flush();
                    writer.Close();
                    writer.Dispose();
                    writer = null;
                }
            }
        }

        protected override void OnBarUpdate()
        {
            string line = string.Format("{0};{1};{2};{3};{4};{5}",
                Time[0].ToString("MM/dd/yyyy HH:mm:ss"),
                Open[0],
                High[0],
                Low[0],
                Close[0],
                (long)Volume[0]);

            if (writer != null)
            {
                writer.WriteLine(line);
                writer.Flush();
            }

            if (PrintToOutput)
                Print(line);
        }
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private MyChartReader[] cacheMyChartReader;
        public MyChartReader MyChartReader()
        {
            return MyChartReader(Input);
        }

        public MyChartReader MyChartReader(ISeries<double> input)
        {
            if (cacheMyChartReader != null)
                for (int idx = 0; idx < cacheMyChartReader.Length; idx++)
                    if (cacheMyChartReader[idx] != null && cacheMyChartReader[idx].EqualsInput(input))
                        return cacheMyChartReader[idx];
            return CacheIndicator<MyChartReader>(new MyChartReader(), input, ref cacheMyChartReader);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.MyChartReader MyChartReader()
        {
            return indicator.MyChartReader(Input);
        }

        public Indicators.MyChartReader MyChartReader(ISeries<double> input)
        {
            return indicator.MyChartReader(input);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.MyChartReader MyChartReader()
        {
            return indicator.MyChartReader(Input);
        }

        public Indicators.MyChartReader MyChartReader(ISeries<double> input)
        {
            return indicator.MyChartReader(input);
        }
    }
}

#endregion
