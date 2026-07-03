#region Using declarations
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
#endregion

// RolloverProbe — one-shot diagnostic. Prints each instrument's
// MasterInstrument.RolloverCollection (ContractMonth / Date / Offset) to the
// NinjaScript Output window AND writes a clean CSV into the repo. Add it to ANY
// chart once; the charted instrument does not matter — it loops the list below.
namespace NinjaTrader.NinjaScript.Indicators
{
	public class RolloverProbe : Indicator
	{
		// MasterInstrument name -> a few candidate contract months to resolve it.
		// RolloverCollection lives on the MasterInstrument, so ANY valid contract
		// of that instrument exposes the FULL set of rollovers.
		private static readonly Dictionary<string, string[]> Candidates =
			new Dictionary<string, string[]>
		{
			{ "ES", new[]{ "09-26","12-26","06-26","03-27" } },
			{ "NQ", new[]{ "09-26","12-26","06-26","03-27" } },
			{ "YM", new[]{ "09-26","12-26","06-26","03-27" } },
			{ "6E", new[]{ "09-26","12-26","06-26","03-27" } },
			{ "6J", new[]{ "09-26","12-26","06-26","03-27" } },
			{ "GC", new[]{ "08-26","12-26","10-26","02-27" } },
			{ "CL", new[]{ "08-26","09-26","10-26","12-26" } },
		};

		// Written straight into the repo so Python can parse it with no transcription.
		private const string CsvPath = @"C:\Users\Admin\myquant\data\nt_rollovers_export.csv";

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name        = "RolloverProbe";
				Description = "Dumps MasterInstrument.RolloverCollection to the Output window and writes a CSV into the repo.";
				IsOverlay   = true;
				Calculate   = Calculate.OnBarClose;
			}
			else if (State == State.DataLoaded)   // Print/file IO available here
			{
				ProbeAll();
			}
		}

		private void ProbeAll()
		{
			Print("===== RolloverProbe START " + DateTime.Now + " =====");
			var csv = new StringBuilder();
			csv.AppendLine("instrument,contract_month,rollover_date,offset");
			foreach (var kv in Candidates)
				ProbeOne(kv.Key, kv.Value, csv);

			try
			{
				File.WriteAllText(CsvPath, csv.ToString());
				Print("CSV written -> " + CsvPath);
			}
			catch (Exception ex)
			{
				Print("CSV WRITE FAILED: " + ex.Message);
			}
			Print("===== RolloverProbe END =====");
		}

		private void ProbeOne(string masterName, string[] monthCandidates, StringBuilder csv)
		{
			Instrument instr = Resolve(masterName, monthCandidates);
			if (instr == null || instr.MasterInstrument == null)
			{
				Print(masterName + ": NO instrument found in DB — open a chart of it once, then re-run.");
				return;
			}

			var coll = instr.MasterInstrument.RolloverCollection;
			if (coll == null)
			{
				Print(masterName + ": RolloverCollection is NULL (resolved via " + instr.FullName + ").");
				return;
			}

			int n = 0;
			foreach (Rollover r in coll)
			{
				csv.AppendLine(string.Format("{0},{1:yyyy-MM},{2:yyyy-MM-dd},{3}",
					masterName, r.ContractMonth, r.Date, r.Offset));
				n++;
			}

			Print(string.Format("{0}: {1} rollover entries (resolved via {2}).",
				masterName, n, instr.FullName));
		}

		private Instrument Resolve(string masterName, string[] monthCandidates)
		{
			foreach (string mm in monthCandidates)
			{
				string full = masterName + " " + mm;   // e.g. "YM 09-26"
				try
				{
					Instrument ins = Instrument.GetInstrument(full);
					if (ins != null) return ins;
				}
				catch { /* not in DB — try next */ }
			}
			try { return Instrument.GetInstrument(masterName); } catch { return null; }
		}
	}
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private RolloverProbe[] cacheRolloverProbe;
		public RolloverProbe RolloverProbe()
		{
			return RolloverProbe(Input);
		}

		public RolloverProbe RolloverProbe(ISeries<double> input)
		{
			if (cacheRolloverProbe != null)
				for (int idx = 0; idx < cacheRolloverProbe.Length; idx++)
					if (cacheRolloverProbe[idx] != null &&  cacheRolloverProbe[idx].EqualsInput(input))
						return cacheRolloverProbe[idx];
			return CacheIndicator<RolloverProbe>(new RolloverProbe(), input, ref cacheRolloverProbe);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.RolloverProbe RolloverProbe()
		{
			return indicator.RolloverProbe(Input);
		}

		public Indicators.RolloverProbe RolloverProbe(ISeries<double> input )
		{
			return indicator.RolloverProbe(input);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.RolloverProbe RolloverProbe()
		{
			return indicator.RolloverProbe(Input);
		}

		public Indicators.RolloverProbe RolloverProbe(ISeries<double> input )
		{
			return indicator.RolloverProbe(input);
		}
	}
}

#endregion
