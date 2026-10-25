#region Using declarations
using System;
using System.Collections.Generic;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// Companion to SuperZones (nt8/drawingtools/SuperZones.cs): counts touches and sums volume
// for every SuperZones zone on the chart, writes the result into each zone's own StatsText
// property. Draws nothing itself — SuperZones renders the label, this just feeds it data.
//
// Resource discipline:
//   - Per-bar touch/volume counting lives in OnBarUpdate (Calculate.OnBarClose — once per
//     bar, never per tick), since a "touch" is inherently a bar-close event.
//   - New-zone / bounds-changed DISCOVERY also runs from OnRender (every chart repaint), with
//     no painting at all — confirmed necessary: on a Daily chart, OnBarUpdate doesn't fire
//     again until tomorrow's bar closes, so discovery can't wait on bar-close alone or a zone
//     drawn mid-session would show no stats until the next day.
//   - The OnRender path is still cheap in steady state: it's an O(zones) iteration + a few
//     field comparisons per zone, same order of magnitude as SuperZones' own per-frame work.
//     The only large pass (backfill over historical bars) only runs when a zone is actually
//     new or edited — not on every repaint.
namespace NinjaTrader.NinjaScript.Indicators
{
	public class SuperZoneStats : Indicator
	{
		private class ZoneState
		{
			public bool		WasInside;
			public int		Touches;
			public double	Volume;
			public double	LastTop;
			public double	LastBot;
			public long		LastStartTicks;
			// Only set true once a backfill has run AND the chart's full history was provably
			// loaded at that moment (CurrentBar caught up to Bars.Count-1). OnRender can
			// discover a zone while OnBarUpdate's historical pass is still mid-flight — an
			// attempt made then is not trusted as final, so it keeps retrying (cheap, since
			// CurrentBar is still small in that window) until it can prove it saw everything.
			public bool		Backfilled;
		}

		private readonly Dictionary<string, ZoneState>	zoneStates	= new Dictionary<string, ZoneState>();
		private bool										loggedDiag;
		private bool										loggedZoneDiag;
		private readonly HashSet<string>					loggedOnce	= new HashSet<string>();

		private void PrintOnce(string key, string msg)
		{
			if (loggedOnce.Contains(key)) return;
			loggedOnce.Add(key);
			try { Print(msg); } catch {}
		}

		protected override void OnStateChange()
		{
			if (State == State.SetDefaults)
			{
				Name				= "SuperZoneStats";
				Description			= "Counts touches and sums volume per SuperZones zone, writes the result into each zone's label. No drawing of its own.";
				Calculate			= Calculate.OnBarClose;
				IsOverlay			= true;
				DisplayInDataBox	= false;
				PaintPriceMarkers	= false;
				IsSuspendedWhileInactive = true;
			}
		}

		protected override void OnBarUpdate()
		{
			if (CurrentBar < 1) return;
			List<ZonePair> found;
			DiscoverZones(out found);
			if (found == null) return;

			for (int i = 0; i < found.Count; i++)
			{
				SuperZones zone = found[i].Zone;
				ZoneState  st   = found[i].State;

				bool insideNow = High[0] >= st.LastBot && Low[0] <= st.LastTop;
				if (insideNow)
				{
					st.Volume += Volume[0];
					if (!st.WasInside) st.Touches++;
				}
				st.WasInside = insideNow;

				WriteStats(zone, st);
			}
		}

		// Logic-only — never touches RenderTarget, draws nothing. Exists purely so a zone
		// drawn between bar closes (e.g. on a Daily chart) gets backfilled immediately instead
		// of waiting for the next bar to close.
		protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
		{
			base.OnRender(chartControl, chartScale);
			if (CurrentBar < 1) return;
			List<ZonePair> found;
			DiscoverZones(out found);
		}

		private struct ZonePair { public SuperZones Zone; public ZoneState State; }

		// Finds every SuperZones on the chart, creates/updates its ZoneState, backfills new or
		// edited ones. Cheap per call (O(zones) + field comparisons) except for the backfill,
		// which only runs on an actual new-zone or bounds-change event.
		private void DiscoverZones(out List<ZonePair> foundOut)
		{
			foundOut = null;
			if (ChartControl == null || ChartPanel == null) return;

			if (!loggedDiag)
			{
				loggedDiag = true;
				try { Print("SuperZoneStats first discovery pass: ChartControl=ok ChartPanel=ok"); } catch {}
			}

			List<ZonePair> found = new List<ZonePair>();
			HashSet<string> seen = new HashSet<string>();

			foreach (Gui.NinjaScript.IChartObject obj in ChartPanel.ChartObjects)
			{
				SuperZones zone = obj as SuperZones;
				if (zone == null) continue;

				string tag = zone.Tag;

				if (zone.StartAnchor == null || zone.EndAnchor == null || zone.StartAnchor.IsEditing) continue; // not placed yet

				double top = Math.Max(zone.StartAnchor.Price, zone.EndAnchor.Price);
				double bot = Math.Min(zone.StartAnchor.Price, zone.EndAnchor.Price);
				long   startTicks = zone.StartAnchor.Time.Ticks;

				if (!loggedZoneDiag)
				{
					loggedZoneDiag = true;
					try { Print("SuperZoneStats zone seen: Tag=" + (string.IsNullOrEmpty(tag) ? "EMPTY" : tag) + " top=" + top + " bot=" + bot + " startTicks=" + startTicks); } catch {}
				}

				if (string.IsNullOrEmpty(tag)) continue;

				seen.Add(tag);

				ZoneState st;
				bool isNew = !zoneStates.TryGetValue(tag, out st);
				if (isNew) { st = new ZoneState(); zoneStates[tag] = st; }

				bool boundsChanged = !isNew && (top != st.LastTop || bot != st.LastBot || startTicks != st.LastStartTicks);
				if (boundsChanged) st.Backfilled = false;

				if (isNew || boundsChanged || !st.Backfilled)
				{
					int startBarIdx;
					try { startBarIdx = Bars.GetBar(new DateTime(startTicks)); }
					catch { startBarIdx = CurrentBar; }
					if (startBarIdx < 0) startBarIdx = 0;

					st.Touches   = 0;
					st.Volume    = 0;
					st.WasInside = false;
					Backfill(startBarIdx, top, bot, st);
					// Only trust this as the final answer once we can prove the chart's full
					// history was loaded when we did it — otherwise keep retrying next call.
					if (CurrentBar >= Bars.Count - 1) st.Backfilled = true;
					st.LastTop        = top;
					st.LastBot        = bot;
					st.LastStartTicks = startTicks;
					WriteStats(zone, st);
				}

				found.Add(new ZonePair { Zone = zone, State = st });
			}

			if (zoneStates.Count > seen.Count)
			{
				List<string> stale = null;
				foreach (string key in zoneStates.Keys)
					if (!seen.Contains(key))
					{ if (stale == null) stale = new List<string>(); stale.Add(key); }
				if (stale != null)
					foreach (string key in stale) zoneStates.Remove(key);
			}

			foundOut = found;
		}

		// Runs only when a zone is new, edited, or hasn't been provably backfilled against full
		// history yet — not per bar/frame.
		private void Backfill(int startBarIdx, double top, double bot, ZoneState st)
		{
			// Reads via Bars.GetHigh/GetLow/GetVolume (absolute bar index into the underlying
			// loaded data series) instead of the indicator's own High[]/Low[]/Volume[] (barsAgo
			// relative to CurrentBar). Confirmed necessary: when called from OnRender, the
			// indicator's own streaming buffer can lag behind what CurrentBar reports, and
			// indexing it by a CurrentBar-derived barsAgo threw ArgumentOutOfRangeException on
			// every call — Bars' own accessors read the already-loaded data series directly and
			// aren't tied to how far this indicator's OnBarUpdate has personally progressed.
			int lastBarIdxExclusive = Bars.Count - 1; // exclude the newest bar — OnBarUpdate owns that one
			if (startBarIdx >= lastBarIdxExclusive) return;

			bool wasInside = false;
			try
			{
				for (int idx = startBarIdx; idx < lastBarIdxExclusive; idx++)
				{
					double h = Bars.GetHigh(idx);
					double l = Bars.GetLow(idx);
					bool inside = h >= bot && l <= top;
					if (inside)
					{
						st.Volume += Bars.GetVolume(idx);
						if (!wasInside) st.Touches++;
					}
					wasInside = inside;
				}
			}
			catch (Exception ex) { PrintOnce("Backfill", "SuperZoneStats.Backfill: " + ex); }
			st.WasInside = wasInside;
		}

		private void WriteStats(SuperZones zone, ZoneState st)
		{
			string text = st.Touches + (st.Touches == 1 ? " touch · " : " touches · ") + FormatVolume(st.Volume);
			if (zone.StatsText != text)
				zone.StatsText = text;
		}

		private static string FormatVolume(double v)
		{
			if (v >= 1000000) return (v / 1000000).ToString("0.#") + "M";
			if (v >= 1000)    return (v / 1000).ToString("0.#") + "K";
			return v.ToString("0");
		}
	}
}
