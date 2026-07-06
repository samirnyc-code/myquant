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
	// ── TDUSecondEntryExporter ────────────────────────────────────────────────
	// Hosts the commercial TDU Price Action indicator (TradeDevils) and exports
	// every signal it emits to CSV via its DOCUMENTED strategy plots
	// (tradedevils-indicators.com/pages/tdu-price-action-docs):
	//     3  Long Signal price (0 = none)     7  Short Signal price
	//     4  Long Stoploss                    8  Short Stoploss
	//     6  Long Signalbar Strength %       10  Short Signalbar Strength %
	//    11  Trap Long price                 12  Trap Short price
	//    13  Congestion flag                 14  EMA
	//
	// With TDU's default display settings ("Show 0-1" and "Show Higher Entries"
	// OFF) the signal plots correspond to SECOND ENTRIES (2EL/2ES) only.
	// VERIFY after first export: row count per day should match the 2EL/2ES
	// labels on the chart. If you changed TDU display settings, the plots may
	// include other entry numbers.
	//
	// Conventions (match the myquant sim engine / RevFT lessons):
	//   - SignalTime = bar CLOSE time (NT convention) — the moment the signal
	//     is actionable. Fills must occur strictly after it.
	//   - StopPrice here is the ACTUAL stop level from TDU (plot 4/8), NOT a
	//     setup extreme. Do not offset it again in the sim.
	//
	// Run on an ES 5-minute RTH chart, Calculate.OnBarClose, full lookback.
	// Rows accumulate in memory; file is written atomically on Terminated.
	public class TDUSecondEntryExporter : Indicator
	{
		private TDU.TDUPriceAction _tdu;
		private List<string>       _rows;
		private string             _outPath;

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description  = "Exports TDU Price Action signals (2nd entries + traps) to CSV via its documented plots.";
				Name         = "TDUSecondEntryExporter";
				Calculate    = Calculate.OnBarClose;
				IsOverlay    = true;
				IsSuspendedWhileInactive = false;

				// TDU ctor settings (enum-backed params exposed as ints so this
				// file compiles without knowing the vendor enum member names:
				// 0 = first/default member = Mack rules / default ATM).
				LegCountMethodIndex = 0;
				ResetCountAtDTDB    = true;
				ATMTypeIndex        = 0;
				TrapOffsetTicks     = 1;
				MaxStopLossTicks    = 200;
				StoplossTicksOffset = 1;
				ExportFileName      = "";   // empty -> Documents\tdu_signals_<instrument>.csv
			}
			else if (State == State.DataLoaded)
			{
				_rows = new List<string>();
				_outPath = string.IsNullOrWhiteSpace(ExportFileName)
					? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
						string.Format("tdu_signals_{0}.csv",
							Instrument.MasterInstrument.Name))
					: ExportFileName;

				// Position-sizing params pinned to 1 fixed contract — sizing is
				// irrelevant for signal export; our sim handles sizing itself.
				_tdu = TDUPriceAction(Close,
					(TDUPatsRules)LegCountMethodIndex,
					ResetCountAtDTDB,
					(TDUPatsTradeManagement)ATMTypeIndex,
					0,                      // commissions — n/a for export
					TrapOffsetTicks,
					MaxStopLossTicks,
					StoplossTicksOffset,
					(TDUPATSPositionSizing)0, 1, 0, 0, 1,
					(TDUPATSPositionSizingRunner)0, 1, 0, 0, 1);
			}
			else if (State == State.Terminated)
			{
				if (_rows == null || _rows.Count == 0)
					return;
				try
				{
					var sb = new StringBuilder();
					sb.AppendLine("Date,SignalTime,BarNum,EventType,Direction,SignalPrice,StopPrice,StrengthPct,Open,High,Low,Close,Volume,EMA,Congestion,BarSizeTicks");
					foreach (var r in _rows)
						sb.AppendLine(r);
					var tmp = _outPath + ".tmp";
					File.WriteAllText(tmp, sb.ToString());
					if (File.Exists(_outPath))
						File.Delete(_outPath);
					File.Move(tmp, _outPath);
					Print(string.Format("TDUSecondEntryExporter: {0} rows -> {1}", _rows.Count, _outPath));
				}
				catch (Exception ex)
				{
					Print("TDUSecondEntryExporter write failed: " + ex.Message);
				}
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 1 || _tdu == null)
				return;

			_tdu.Update();

			double longSig   = _tdu.Values[3][0];
			double longStop  = _tdu.Values[4][0];
			double longStr   = _tdu.Values[6][0];
			double shortSig  = _tdu.Values[7][0];
			double shortStop = _tdu.Values[8][0];
			double shortStr  = _tdu.Values[10][0];
			double trapLong  = _tdu.Values[11][0];
			double trapShort = _tdu.Values[12][0];
			double congest   = _tdu.Values[13][0];
			double ema       = _tdu.Values[14][0];
			double barTicks  = _tdu.Values[1][0];

			if (longSig != 0)
				AddRow("SecondEntry", "Long", longSig, longStop, longStr, ema, congest, barTicks);
			if (shortSig != 0)
				AddRow("SecondEntry", "Short", shortSig, shortStop, shortStr, ema, congest, barTicks);
			if (trapLong != 0)
				AddRow("Trap", "Long", trapLong, 0, 0, ema, congest, barTicks);
			if (trapShort != 0)
				AddRow("Trap", "Short", trapShort, 0, 0, ema, congest, barTicks);
		}

		private void AddRow(string eventType, string direction, double sigPx,
			double stopPx, double strength, double ema, double congest, double barTicks)
		{
			var ci = CultureInfo.InvariantCulture;
			// Time[0] on a closed bar = bar CLOSE time (see header note).
			int barNum = Bars.BarsSinceNewTradingDay + 1;
			_rows.Add(string.Join(",",
				Time[0].ToString("yyyy-MM-dd", ci),
				Time[0].ToString("yyyy-MM-dd HH:mm:ss", ci),
				barNum.ToString(ci),
				eventType,
				direction,
				sigPx.ToString("F2", ci),
				stopPx.ToString("F2", ci),
				strength.ToString("F1", ci),
				Open[0].ToString("F2", ci),
				High[0].ToString("F2", ci),
				Low[0].ToString("F2", ci),
				Close[0].ToString("F2", ci),
				Volume[0].ToString("F0", ci),
				ema.ToString("F2", ci),
				congest.ToString("F0", ci),
				barTicks.ToString("F0", ci)));
		}

		#region Properties
		[NinjaScriptProperty]
		[Range(0, 10)]
		[Display(Name = "LegCountMethodIndex (0=Mack default, 1=Brooks)", GroupName = "TDU Settings", Order = 0)]
		public int LegCountMethodIndex { get; set; }

		[NinjaScriptProperty]
		[Display(Name = "ResetCountAtDTDB", GroupName = "TDU Settings", Order = 1)]
		public bool ResetCountAtDTDB { get; set; }

		[NinjaScriptProperty]
		[Range(0, 10)]
		[Display(Name = "ATMTypeIndex (0=default)", GroupName = "TDU Settings", Order = 2)]
		public int ATMTypeIndex { get; set; }

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "TrapOffsetTicks", GroupName = "TDU Settings", Order = 3)]
		public int TrapOffsetTicks { get; set; }

		[NinjaScriptProperty]
		[Range(1, 10000)]
		[Display(Name = "MaxStopLossTicks", GroupName = "TDU Settings", Order = 4)]
		public int MaxStopLossTicks { get; set; }

		[NinjaScriptProperty]
		[Range(0, 100)]
		[Display(Name = "StoplossTicksOffset", GroupName = "TDU Settings", Order = 5)]
		public int StoplossTicksOffset { get; set; }

		[Display(Name = "ExportFileName (empty = Documents\\tdu_signals_<instr>.csv)", GroupName = "Export", Order = 10)]
		public string ExportFileName { get; set; }
		#endregion
	}
}
