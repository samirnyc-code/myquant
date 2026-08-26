#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// ── WedgeExporter ─────────────────────────────────────────────────────────
	// Hosts the black-box MyWedge indicator (Indicators.My.MyWedge) and exports
	// every SIGNAL BAR it emits to CSV, over the whole loaded history. Purpose:
	// pull ~5yr of MyWedge setups off a continuous 2000-tick ES chart into the
	// python trove so we can run the stop/target (MAE/MFE) sweep on real ticks.
	//
	// MyWedge plots consumed (by NAME, so plot ordering is irrelevant):
	//     WedgeBL   > 0  = bull wedge CONDITION active on this bar (context/color)
	//     WedgeBR   > 0  = bear wedge CONDITION active on this bar (context/color)
	//     WedgeBLSB > 0  = bull-wedge SIGNAL BAR  (the entry trigger)   -> "BL"
	//     WedgeBRSB > 0  = bear-wedge SIGNAL BAR  (the entry trigger)   -> "BR"
	//
	// One row is written per bar on which EITHER SB plot is > 0. Direction is left
	// UNINTERPRETED here (recorded as the raw plot name BL/BR + all four values);
	// the python study maps BL/BR -> long/short so a sign convention never gets
	// hard-coded on the NT side. The condition plots (WedgeBL/BR) are carried on
	// the row as context.
	//
	// Conventions (match TDUSecondEntryExporter / the myquant sim engine):
	//   - SignalTime = bar CLOSE time (NT convention). Fills occur strictly after.
	//   - The 10 MyWedge ctor params are exposed below — SET THEM IN THE DIALOG TO
	//     MATCH THE MyWedge INSTANCE ON YOUR CHART, or the exported signals will
	//     not match what you trade.
	//
	// Run on an ES continuous 2000-tick RTH chart, Calculate.OnBarClose, with as
	// much lookback as NT8 will load (chunk by year if it chokes; the file name
	// carries the instrument so chunks can be concatenated in python).
	public class WedgeExporter : Indicator
	{
		private My.MyWedge   _wedge;
		private List<string> _rows;
		private string       _outPath;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description  = "Exports MyWedge signal bars (WedgeBLSB/WedgeBRSB > 0) to CSV over full history for the stop/target study.";
				Name         = "WedgeExporter";
				Calculate    = Calculate.OnBarClose;
				IsOverlay    = true;
				IsSuspendedWhileInactive = false;

				// ── MyWedge ctor defaults ──────────────────────────────────────
				// PLACEHOLDERS. These MUST be set to match the MyWedge instance on
				// your chart. I do not know MyWedge's own defaults; verify each
				// against your chart's indicator dialog before exporting.
				LookBack       = 20;
				ShowW2L        = true;
				WedgeSymmetry  = 0;
				OLSensitivity  = 0;
				CTSB_Ignore    = false;
				IB_Ignore      = false;
				ShowWedgeSB    = true;
				SignalBarIBS   = 0.0;
				ContinueMC     = false;
				ContinueOnGap  = false;

				ExportFileName = "";   // empty -> Documents\wedge_signals_<instrument>.csv
			}
			else if (State == State.DataLoaded)
			{
				_rows = new List<string>();
				_outPath = string.IsNullOrWhiteSpace(ExportFileName)
					? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
						string.Format("wedge_signals_{0}.csv",
							Instrument.MasterInstrument.Name))
					: ExportFileName;

				_wedge = MyWedge(Input, LookBack, ShowW2L, WedgeSymmetry, OLSensitivity,
					CTSB_Ignore, IB_Ignore, ShowWedgeSB, SignalBarIBS, ContinueMC, ContinueOnGap);
			}
			else if (State == State.Realtime)
			{
				// Historical load just finished (NT flips historical -> realtime).
				// Flush here so the file appears automatically the moment loading
				// completes — no need to remove the indicator.
				WriteFile();
			}
			else if (State == State.Terminated)
			{
				// Backstop: historical-only runs (Strategy Analyzer / no live feed)
				// never hit State.Realtime, so also write on teardown. Also captures
				// any realtime signals added after the historical flush.
				WriteFile();
			}
		}

		private void WriteFile()
		{
			if (_rows == null || _rows.Count == 0 || string.IsNullOrEmpty(_outPath))
				return;
			try
			{
				var sb = new StringBuilder();
				sb.AppendLine("Date,SignalTime,BarNum,Signal,WedgeBL,WedgeBR,WedgeBLSB,WedgeBRSB,Open,High,Low,Close,Volume");
				foreach (var r in _rows)
					sb.AppendLine(r);
				var tmp = _outPath + ".tmp";
				File.WriteAllText(tmp, sb.ToString());
				if (File.Exists(_outPath))
					File.Delete(_outPath);
				File.Move(tmp, _outPath);
				Print(string.Format("WedgeExporter: {0} signal rows -> {1}", _rows.Count, _outPath));
			}
			catch (Exception ex)
			{
				Print("WedgeExporter write failed: " + ex.Message);
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 1 || _wedge == null)
				return;

			_wedge.Update();

			double bl    = _wedge.WedgeBL[0];
			double br    = _wedge.WedgeBR[0];
			double blSb  = _wedge.WedgeBLSB[0];
			double brSb  = _wedge.WedgeBRSB[0];

			if (blSb > 0)
				AddRow("BL", bl, br, blSb, brSb);
			if (brSb > 0)
				AddRow("BR", bl, br, blSb, brSb);
		}

		private void AddRow(string signal, double bl, double br, double blSb, double brSb)
		{
			var ci = CultureInfo.InvariantCulture;
			// Time[0] on a closed bar = bar CLOSE time (see header note).
			int barNum = Bars.BarsSinceNewTradingDay + 1;
			_rows.Add(string.Join(",",
				Time[0].ToString("yyyy-MM-dd", ci),
				Time[0].ToString("yyyy-MM-dd HH:mm:ss", ci),
				barNum.ToString(ci),
				signal,
				bl.ToString("F4", ci),
				br.ToString("F4", ci),
				blSb.ToString("F4", ci),
				brSb.ToString("F4", ci),
				Open[0].ToString("F2", ci),
				High[0].ToString("F2", ci),
				Low[0].ToString("F2", ci),
				Close[0].ToString("F2", ci),
				Volume[0].ToString("F0", ci)));
		}

		#region Properties
		[NinjaScriptProperty]
		[Range(1, 10000)]
		[Display(Name = "LookBack", GroupName = "MyWedge Settings", Order = 0)]
		public int LookBack { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ShowW2L", GroupName = "MyWedge Settings", Order = 1)]
		public bool ShowW2L { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10000)]
		[Display(Name = "WedgeSymmetry", GroupName = "MyWedge Settings", Order = 2)]
		public int WedgeSymmetry { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10000)]
		[Display(Name = "OLSensitivity", GroupName = "MyWedge Settings", Order = 3)]
		public int OLSensitivity { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "CTSB_Ignore", GroupName = "MyWedge Settings", Order = 4)]
		public bool CTSB_Ignore { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "IB_Ignore", GroupName = "MyWedge Settings", Order = 5)]
		public bool IB_Ignore { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ShowWedgeSB", GroupName = "MyWedge Settings", Order = 6)]
		public bool ShowWedgeSB { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "SignalBarIBS", GroupName = "MyWedge Settings", Order = 7)]
		public double SignalBarIBS { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ContinueMC", GroupName = "MyWedge Settings", Order = 8)]
		public bool ContinueMC { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ContinueOnGap", GroupName = "MyWedge Settings", Order = 9)]
		public bool ContinueOnGap { get; set; }

		[Display(Name = "ExportFileName (empty = Documents\\wedge_signals_<instr>.csv)", GroupName = "Export", Order = 20)]
		public string ExportFileName { get; set; }
		#endregion
	}
}
