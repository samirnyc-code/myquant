#region Using declarations
using System;
using System.IO;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
	// ── LTReversalCandidateExporter ───────────────────────────────────────────
	// Exports LizardTrader Auction Bars reversal-bar CANDIDATES (pre-confirmation)
	// and confirmed signals to CSV. Per the LT Auction Bars user manual §11
	// ("Automated Trading"), the indicator exposes non-repainting public series:
	//     IsReversalUp1Candidate    IsReversalDown1Candidate     (single bar)
	//     IsReversalUp2Candidate    IsReversalDown2Candidate     (composite)
	//     IsConfirmedReversalUp1    IsConfirmedReversalDown1
	//     IsConfirmedReversalUp2    IsConfirmedReversalDown2
	//     ReversalSellStopUp1  ReversalBuyStopDown1  (stop levels, single)
	//     ReversalSellStopUp2  ReversalBuyStopDown2  (stop levels, composite)
	//
	// WHY: the MyReversals csv only contains CONFIRMED signals — the failed
	// breaks are missing (survivorship). The candidate series here are stamped
	// at the candidate bar itself, so this export gives the full, causally
	// clean reversal-bar universe including failures.
	//
	// USAGE (order matters):
	//   1. Apply LT Auction Bars to an ES 5M RTH chart (max days loaded) with
	//      your chosen settings. 2. Add THIS exporter to the same chart.
	//   3. The exporter locates the LT instance on the chart BY NAME (see the
	//      SourceIndicatorName parameter — set it to the exact name shown in
	//      the chart's indicator list, substring match, case-insensitive).
	//   4. It reads the series via reflection each closed bar — no reference
	//      to the vendor assembly is needed, so this compiles standalone.
	//   5. The CSV is written AUTOMATICALLY when the historical load finishes
	//      (and re-written at every new session while live). No need to remove
	//      the indicator or close the chart. Output:
	//      Documents\lt_revcand_<instrument>.csv.
	//
	// Conventions (match the myquant sim engine):
	//   - SignalTime = bar CLOSE time; candidates are actionable at that close.
	//   - One row per bar per event type. CandUp/CandDown rows are the honest
	//     setup universe; ConfUp/ConfDown rows should reconcile against the
	//     MyReversals-style confirmed exports only in COUNT SHAPE (different
	//     detector, so no 1:1 match expected).
	//   - The manual is NT7; series types in the NT8 build may be Series<bool>
	//     or Series<double>. Reflection handles both (nonzero/true = flag set).
	public class LTReversalCandidateExporter : Indicator
	{
		private object       _src;          // the LT Auction Bars instance on the chart
		private bool         _searched;
		private List<string> _rows;
		private List<string> _plotRows;     // unconditional per-bar dump of ALL source plots
		private string       _outPath;
		private string       _plotPath;
		private string       _plotHeader;
		private readonly Dictionary<string, MethodInfo> _getters = new Dictionary<string, MethodInfo>();
		private readonly Dictionary<string, object>     _series  = new Dictionary<string, object>();

		private static readonly string[] FlagSeries = {
			"IsReversalUp1Candidate", "IsReversalDown1Candidate",
			"IsReversalUp2Candidate", "IsReversalDown2Candidate",
			"IsConfirmedReversalUp1", "IsConfirmedReversalDown1",
			"IsConfirmedReversalUp2", "IsConfirmedReversalDown2" };
		private static readonly string[] StopSeries = {
			"ReversalSellStopUp1", "ReversalBuyStopDown1",
			"ReversalSellStopUp2", "ReversalBuyStopDown2" };

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Description = "Exports LizardTrader Auction Bars reversal candidates + confirmations to CSV (reflection host).";
				Name        = "LTReversalCandidateExporter";
				Calculate   = Calculate.OnBarClose;
				IsOverlay   = true;
				IsSuspendedWhileInactive = false;

				SourceIndicatorName = "Auction";   // substring of the LT indicator's name on the chart
				ExportFileName      = "";          // empty -> Documents\lt_revcand_<instrument>.csv
			}
			else if (State == State.DataLoaded)
			{
				_rows = new List<string>();
				_plotRows = new List<string>();
				_outPath = string.IsNullOrWhiteSpace(ExportFileName)
					? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
						string.Format("lt_revcand_{0}.csv", Instrument.MasterInstrument.Name))
					: ExportFileName;
				_plotPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
					string.Format("lt_plots_{0}.csv", Instrument.MasterInstrument.Name));
			}
			else if (State == State.Realtime)
			{
				// historical processing is complete -> write the file NOW
				Flush("historical load complete");
			}
			else if (State == State.Terminated)
			{
				Flush("terminated");   // fallback / final flush
			}
		}

		private void DumpPlots()
		{
			try
			{
				var ib = _src as IndicatorBase;
				if (ib == null || ib.Values == null || ib.Values.Length == 0)
					return;
				var ci = CultureInfo.InvariantCulture;
				if (_plotHeader == null)
				{
					var names = new List<string>();
					for (int p = 0; p < ib.Values.Length; p++)
					{
						string nm = "P" + p;
						try { if (ib.Plots != null && p < ib.Plots.Length && !string.IsNullOrEmpty(ib.Plots[p].Name)) nm = ib.Plots[p].Name.Replace(",", "_"); }
						catch { }
						names.Add(nm);
					}
					_plotHeader = "Date,SignalTime,BarNum,Open,High,Low,Close,Volume," + string.Join(",", names);
					Print("LTReversalCandidateExporter: dumping " + ib.Values.Length + " plots -> " + _plotPath);
				}
				var vals = new List<string>();
				for (int p = 0; p < ib.Values.Length; p++)
				{
					double v = double.NaN;
					try { if (ib.Values[p].IsValidDataPointAt(CurrentBar)) v = ib.Values[p].GetValueAt(CurrentBar); }
					catch { }
					vals.Add(double.IsNaN(v) ? "" : v.ToString("F2", ci));
				}
				_plotRows.Add(string.Join(",",
					Time[0].ToString("yyyy-MM-dd", ci),
					Time[0].ToString("yyyy-MM-dd HH:mm:ss", ci),
					(Bars.BarsSinceNewTradingDay + 1).ToString(ci),
					Open[0].ToString("F2", ci), High[0].ToString("F2", ci),
					Low[0].ToString("F2", ci), Close[0].ToString("F2", ci),
					Volume[0].ToString("F0", ci), string.Join(",", vals)));
			}
			catch { }
		}

		private void Flush(string why)
		{
			if (_plotRows != null && _plotRows.Count > 0 && _plotHeader != null)
			{
				try
				{
					var sbp = new StringBuilder();
					sbp.AppendLine(_plotHeader);
					foreach (var r in _plotRows) sbp.AppendLine(r);
					File.WriteAllText(_plotPath + ".tmp", sbp.ToString());
					if (File.Exists(_plotPath)) File.Delete(_plotPath);
					File.Move(_plotPath + ".tmp", _plotPath);
					Print(string.Format("LTReversalCandidateExporter: {0} plot rows -> {1} ({2})", _plotRows.Count, _plotPath, why));
				}
				catch (Exception ex) { Print("plot dump write failed: " + ex.Message); }
			}
			if (_rows == null || _rows.Count == 0)
				return;
			try
			{
				var sb = new StringBuilder();
				sb.AppendLine("Date,SignalTime,BarNum,EventType,Direction,StopLevel,Open,High,Low,Close,Volume");
				foreach (var r in _rows)
					sb.AppendLine(r);
				var tmp = _outPath + ".tmp";
				File.WriteAllText(tmp, sb.ToString());
				if (File.Exists(_outPath))
					File.Delete(_outPath);
				File.Move(tmp, _outPath);
				Print(string.Format("LTReversalCandidateExporter: {0} rows -> {1} ({2})", _rows.Count, _outPath, why));
			}
			catch (Exception ex)
			{
				Print("LTReversalCandidateExporter write failed: " + ex.Message);
			}
		}

		private void FindSource()
		{
			_searched = true;
			try
			{
				if (ChartControl == null)
				{
					Print("LTReversalCandidateExporter: no ChartControl — apply on a chart.");
					return;
				}
				foreach (var ind in ChartControl.Indicators)
				{
					if (ind == this)
						continue;
					var nm = ind.Name ?? ind.GetType().Name;
					if (nm.IndexOf(SourceIndicatorName, StringComparison.OrdinalIgnoreCase) < 0)
						continue;
					// verify it actually exposes the candidate series
					if (ind.GetType().GetProperty("IsReversalUp1Candidate") == null)
						continue;
					_src = ind;
					break;
				}
				if (_src == null)
				{
					Print(string.Format(
						"LTReversalCandidateExporter: no chart indicator matching '{0}' with IsReversalUp1Candidate. " +
						"Chart indicators found: {1}",
						SourceIndicatorName,
						string.Join(" | ", ChartControl.Indicators.Select(i => i.Name ?? i.GetType().Name))));
					return;
				}
				foreach (var s in FlagSeries.Concat(StopSeries))
				{
					var pi = _src.GetType().GetProperty(s,
						BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
					if (pi == null)
					{
						Print("LTReversalCandidateExporter: MISSING property: " + s);
						continue;
					}
					object ser = null;
					try { ser = pi.GetValue(_src); } catch (Exception gx)
					{ Print("LTReversalCandidateExporter: getter threw for " + s + ": " + gx.Message); }
					if (ser == null)
					{
						Print(string.Format("LTReversalCandidateExporter: {0} is NULL (type {1}) — will retry.",
							s, pi.PropertyType.Name));
						continue;
					}
					var gm = ser.GetType().GetMethod("GetValueAt", new[] { typeof(int) });
					if (gm == null)
					{
						Print(string.Format("LTReversalCandidateExporter: {0} resolved (type {1}) but has no GetValueAt(int).",
							s, ser.GetType().Name));
						continue;
					}
					_series[s]  = ser;
					_getters[s] = gm;
				}
				Print(string.Format("LTReversalCandidateExporter: hooked '{0}', {1}/{2} series resolved.",
					(_src as IndicatorBase)?.Name ?? _src.GetType().Name, _series.Count,
					FlagSeries.Length + StopSeries.Length));
				if (_series.Count == 0)
				{
					// dump what the source actually exposes, so we can adapt names
					var props = _src.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
						.Where(p => p.PropertyType.Name.Contains("Series") || p.Name.ToLower().Contains("reversal")
							|| p.Name.ToLower().Contains("candidate") || p.Name.ToLower().Contains("stop"))
						.Select(p => p.Name + ":" + p.PropertyType.Name);
					Print("LTReversalCandidateExporter: source exposes -> " + string.Join(" | ", props));
				}
			}
			catch (Exception ex)
			{
				Print("LTReversalCandidateExporter FindSource failed: " + ex.Message);
			}
		}

		private bool Flag(string name, int barIdx)
		{
			MethodInfo gm;
			if (!_getters.TryGetValue(name, out gm))
				return false;
			var v = gm.Invoke(_series[name], new object[] { barIdx });
			if (v is bool)   return (bool)v;
			if (v is double) return Math.Abs((double)v) > 1e-9;
			return false;
		}

		private double Level(string name, int barIdx)
		{
			MethodInfo gm;
			if (!_getters.TryGetValue(name, out gm))
				return 0;
			var v = gm.Invoke(_series[name], new object[] { barIdx });
			return v is double ? (double)v : 0;
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 1)
				return;
			// retry resolution every 200 bars until the series appear (the source
			// indicator may initialize its series after our first probe)
			if (_series.Count == 0 && (!_searched || CurrentBar % 200 == 0))
			{
				_searched = true;
				_src = null; _series.Clear(); _getters.Clear();
				FindSource();
			}
			if (_src == null)
				return;

			DumpPlots();   // unconditional: every plot of the source, every bar

			// while live: re-write the files at each new session so they stay current
			if (State == State.Realtime && Bars.IsFirstBarOfSession)
				Flush("new session");

			if (_series.Count == 0)
				return;

			int i = CurrentBar;   // GetValueAt uses absolute bar index

			if (Flag("IsReversalUp1Candidate",   i)) AddRow("CandUp1",   "Long",  Level("ReversalSellStopUp1",   i));
			if (Flag("IsReversalDown1Candidate", i)) AddRow("CandDown1", "Short", Level("ReversalBuyStopDown1",  i));
			if (Flag("IsReversalUp2Candidate",   i)) AddRow("CandUp2",   "Long",  Level("ReversalSellStopUp2",   i));
			if (Flag("IsReversalDown2Candidate", i)) AddRow("CandDown2", "Short", Level("ReversalBuyStopDown2",  i));
			if (Flag("IsConfirmedReversalUp1",   i)) AddRow("ConfUp1",   "Long",  Level("ReversalSellStopUp1",   i));
			if (Flag("IsConfirmedReversalDown1", i)) AddRow("ConfDown1", "Short", Level("ReversalBuyStopDown1",  i));
			if (Flag("IsConfirmedReversalUp2",   i)) AddRow("ConfUp2",   "Long",  Level("ReversalSellStopUp2",   i));
			if (Flag("IsConfirmedReversalDown2", i)) AddRow("ConfDown2", "Short", Level("ReversalBuyStopDown2",  i));
		}

		private void AddRow(string eventType, string direction, double stopLevel)
		{
			var ci = CultureInfo.InvariantCulture;
			int barNum = Bars.BarsSinceNewTradingDay + 1;
			_rows.Add(string.Join(",",
				Time[0].ToString("yyyy-MM-dd", ci),
				Time[0].ToString("yyyy-MM-dd HH:mm:ss", ci),
				barNum.ToString(ci),
				eventType,
				direction,
				stopLevel.ToString("F2", ci),
				Open[0].ToString("F2", ci),
				High[0].ToString("F2", ci),
				Low[0].ToString("F2", ci),
				Close[0].ToString("F2", ci),
				Volume[0].ToString("F0", ci)));
		}

		#region Properties
		[NinjaScriptProperty]
		[Display(Name = "SourceIndicatorName (substring match)", GroupName = "Source", Order = 0)]
		public string SourceIndicatorName { get; set; }

		[Display(Name = "ExportFileName (empty = Documents\\lt_revcand_<instr>.csv)", GroupName = "Export", Order = 1)]
		public string ExportFileName { get; set; }
		#endregion
	}
}
