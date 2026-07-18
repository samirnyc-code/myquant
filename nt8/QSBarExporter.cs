// QSBarExporter — appends each completed bar to a CSV for the myquant pipeline (S73).
//
// Purpose: bridge NT8's live ES feed into c:\Users\Admin\myquant\data\nt8_es_1m.csv
// so the options dashboard / sim can use real-time ES (Massive pipeline died 2026-07-14;
// IB ES is delayed). Apply to a 1-minute ES chart; writes one line per closed bar:
//   yyyy-MM-dd HH:mm:ss,open,high,low,close,volume   (bar CLOSE timestamp, exchange tz)
//
// Install: NinjaTrader 8 -> New > NinjaScript Editor -> Indicators -> paste -> compile.
// Add to a 1-min ES chart, set ExportPath if the repo lives elsewhere.
// RULE (CLAUDE.md): this file lives in nt8/ in the repo and must stay committed.

#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.Data;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class QSBarExporter : Indicator
    {
        private StreamWriter writer;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Appends each closed bar as CSV for the myquant pipeline";
                Name = "QSBarExporter";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportPath = @"C:\Users\Admin\myquant\data\nt8_es_1m.csv";
            }
            else if (State == State.Terminated)
            {
                if (writer != null) { writer.Flush(); writer.Close(); writer = null; }
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 0) return;
            try
            {
                if (writer == null)
                {
                    bool fresh = !File.Exists(ExportPath);
                    writer = new StreamWriter(ExportPath, true);
                    if (fresh) writer.WriteLine("DateTime,Open,High,Low,Close,Volume");
                }
                writer.WriteLine(string.Format("{0:yyyy-MM-dd HH:mm:ss},{1},{2},{3},{4},{5}",
                    Time[0], Open[0], High[0], Low[0], Close[0], Volume[0]));
                writer.Flush();   // pipeline reads the tail — keep it current
            }
            catch (Exception e)
            {
                Log("QSBarExporter write failed: " + e.Message, LogLevel.Warning);
            }
        }

        [NinjaScriptProperty]
        [Display(Name = "ExportPath", GroupName = "Parameters", Order = 0)]
        public string ExportPath { get; set; }
    }
}
