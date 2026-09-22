// WyckoffTRZone.cs — a dedicated "Wyckoff TR Zone" drawing tool: a rectangle band drawn from
// the wick extreme to the body cluster (the user's S/R-zone method). It behaves exactly like
// the built-in Rectangle, but is its OWN type so TempoSpeedometer reads ONLY these objects and
// ignores ordinary rectangles you draw for other reasons. It appears in the chart Drawing Tools
// palette as its own item.
//
// Deploy to:  Documents\NinjaTrader 8\bin\Custom\DrawingTools\WyckoffTRZone.cs   (then F5).

#region Using declarations
using System;
using System.Windows.Media;
using NinjaTrader.Gui;
#endregion

namespace NinjaTrader.NinjaScript.DrawingTools
{
	// Inherits all Rectangle behaviour (two-anchor drag, resize, anchors, rendering). We only
	// give it a distinct name + a default soft-yellow band look so it reads as a zone.
	public class WyckoffTRZone : Rectangle
	{
		protected override void OnStateChange()
		{
			base.OnStateChange();
			if (State == State.SetDefaults)
			{
				Name          = "Wyckoff TR Zone";
				AreaBrush     = Brushes.Gold;
				AreaOpacity   = 12;
				OutlineStroke = new Stroke(Brushes.Goldenrod, 1f);
			}
		}
	}
}
