#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
#endregion

// S/R zone drawing tool. Two clicks place it: the first click sets the left edge (time) and
// one price corner, the second sets the opposite price corner — the zone then extends to the
// current right edge of the chart (IsOpen) instead of being bounded on both sides.
//
// Geometry and "is this zone actually placed" both come directly from StartAnchor/EndAnchor —
// deliberately NOT from any custom serialized property. Earlier versions duplicated the
// anchors' data into private fields (zoneStartTime, zoneTopPrice, isBuilding, ZoneBuildDone...)
// and every bug this tool has had (wouldn't draw, froze the UI, vanished on relabel, vanished
// on reload) traced back to that duplication: NT8 reapplies "last-used" property values to
// fresh instances for convenience properties, and our custom properties/flags were just as
// exposed to that as any Display-visible one, which is exactly wrong for state that represents
// "has this specific zone actually been placed." RiskRewardPro (NinjaTrader.Custom, used daily
// without any of these problems) is built on DrawingTool the same way and sidesteps all of it
// by only ever reading/writing the anchors themselves and their IsEditing flag — this file
// mirrors that pattern instead of inventing a parallel one.
namespace NinjaTrader.NinjaScript.DrawingTools
{
	public enum SuperZoneLabelType
	{
		Support,
		Resistance,
		Supply,
		Demand,
		ValueAreaHigh,
		ValueAreaLow,
		POC,
		Gap,
		Custom
	}

	public enum SuperZoneLabelPosition
	{
		TopLeft,
		TopRight,
		BottomLeft,
		BottomRight,
		CenterLeft,
		CenterRight,
		OutsideTop,
		OutsideBottom
	}

	public class SuperZones : DrawingTool
	{
		private const double cursorSensitivity = 15;

		private ChartAnchor	editingAnchor;
		private int				areaOpacity			= 20;
		private Brush			areaBrush;
		private DeviceBrush		areaBrushDevice		= new DeviceBrush();
		private int				outlineOpacity		= 100;
		private DeviceBrush		outlineBrushDevice	= new DeviceBrush();
		private Brush			labelBrushField;
		private DeviceBrush		labelBrushDevice	= new DeviceBrush();
		private Brush			midLineBrushField;
		private DeviceBrush		midLineBrushDevice	= new DeviceBrush();

		// One-shot error logging — OnRender runs on every chart repaint, so any Print() in its
		// path MUST be throttled or a persistent error floods the Output window fast enough to
		// freeze the UI thread (this happened once already from an unthrottled diagnostic print).
		private readonly HashSet<string> loggedOnce = new HashSet<string>();
		private void PrintOnce(string key, string msg)
		{
			if (loggedOnce.Contains(key)) return;
			loggedOnce.Add(key);
			try { Print(msg); } catch {}
		}

		// Cached DirectWrite/Stroke objects — rebuilt only when their inputs change, not on
		// every OnRender call.
		private SharpDX.DirectWrite.TextFormat	cachedTextFormat;
		private SharpDX.DirectWrite.TextLayout	cachedTextLayout;
		private string							cachedLabelText		= null;
		private int								cachedFontSize		= -1;
		private float							cachedLayoutWidth	= -1f;
		private readonly Stroke				midLineStroke		= new Stroke();

		[Browsable(false)] public ChartAnchor StartAnchor { get; set; }
		[Browsable(false)] public ChartAnchor EndAnchor   { get; set; }

		public override IEnumerable<ChartAnchor> Anchors
		{ get { return new[] { StartAnchor, EndAnchor }; } }

		public override object Icon { get { return Gui.Tools.Icons.DrawRegionHighlightY; } }

		#region Properties — Bounds

		private bool isOpenEndedRight = true;

		[Display(Name = "Open-Ended Right", Description = "Zone extends to the current right edge of the chart instead of a fixed end time.", Order = 1, GroupName = "0. Zone Bounds")]
		public bool IsOpen
		{
			get { return isOpenEndedRight; }
			set { isOpenEndedRight = value; }
		}

		#endregion

		#region Properties — Fill

		[XmlIgnore]
		[Display(Name = "Fill Color", Order = 1, GroupName = "1. Zone Fill")]
		public Brush AreaBrush
		{
			get { return areaBrush; }
			set
			{
				areaBrush = value;
				if (areaBrush != null) { if (areaBrush.IsFrozen) areaBrush = areaBrush.Clone(); areaBrush.Freeze(); }
				areaBrushDevice.Brush = null;
			}
		}

		[Browsable(false)]
		public string AreaBrushSerialize
		{ get { return Serialize.BrushToString(AreaBrush); } set { AreaBrush = Serialize.StringToBrush(value); } }

		[Range(0, 100)]
		[Display(Name = "Fill Opacity", Order = 2, GroupName = "1. Zone Fill")]
		public int AreaOpacity
		{
			get { return areaOpacity; }
			set { areaOpacity = Math.Max(0, Math.Min(100, value)); areaBrushDevice.Brush = null; }
		}

		#endregion

		#region Properties — Outline

		[Display(Name = "Outline Stroke", Order = 1, GroupName = "2. Outline")]
		public Stroke OutlineStroke { get; set; }

		[Range(0, 100)]
		[Display(Name = "Outline Opacity", Order = 2, GroupName = "2. Outline")]
		public int OutlineOpacity
		{
			get { return outlineOpacity; }
			set { outlineOpacity = Math.Max(0, Math.Min(100, value)); outlineBrushDevice.Brush = null; }
		}

		#endregion

		#region Properties — Label

		private SuperZoneLabelType labelType = SuperZoneLabelType.Resistance;

		[Display(Name = "Zone Type", Order = 1, GroupName = "3. Label")]
		public SuperZoneLabelType LabelType
		{
			get { return labelType; }
			set { labelType = value; ApplyTypeDefaults(value); }
		}

		[Display(Name = "Custom Label Text", Order = 2, GroupName = "3. Label")]
		public string CustomLabel { get; set; }

		[Display(Name = "Label Visible", Order = 3, GroupName = "3. Label")]
		public bool LabelVisible { get; set; }

		[Display(Name = "Label Position", Order = 4, GroupName = "3. Label")]
		public SuperZoneLabelPosition LabelPosition { get; set; }

		[Range(2, 40)]
		[Display(Name = "Label Outside Offset (px)", Order = 5, GroupName = "3. Label")]
		public int LabelOutsideOffset { get; set; }

		[XmlIgnore]
		[Display(Name = "Label Color", Order = 6, GroupName = "3. Label")]
		public Brush LabelBrush
		{
			get { return labelBrushField; }
			set
			{
				labelBrushField = value;
				if (labelBrushField != null) { if (labelBrushField.IsFrozen) labelBrushField = labelBrushField.Clone(); labelBrushField.Freeze(); }
				labelBrushDevice.Brush = null;
			}
		}

		[Browsable(false)]
		public string LabelBrushSerialize
		{ get { return Serialize.BrushToString(LabelBrush); } set { LabelBrush = Serialize.StringToBrush(value); } }

		[Range(6, 32)]
		[Display(Name = "Label Font Size", Order = 7, GroupName = "3. Label")]
		public int LabelFontSize { get; set; }

		// Written by the companion SuperZoneStats indicator, not by the user. Appended as a
		// second label line when present.
		[Browsable(false)]
		public string StatsText { get; set; }

		#endregion

		#region Properties — MidLine

		[Display(Name = "MidLine Visible", Order = 1, GroupName = "4. MidLine")]
		public bool MidLineVisible { get; set; }

		[XmlIgnore]
		[Display(Name = "MidLine Color", Order = 2, GroupName = "4. MidLine")]
		public Brush MidLineBrush
		{
			get { return midLineBrushField; }
			set
			{
				midLineBrushField = value;
				if (midLineBrushField != null) { if (midLineBrushField.IsFrozen) midLineBrushField = midLineBrushField.Clone(); midLineBrushField.Freeze(); }
				midLineBrushDevice.Brush = null;
			}
		}

		[Browsable(false)]
		public string MidLineBrushSerialize
		{ get { return Serialize.BrushToString(MidLineBrush); } set { MidLineBrush = Serialize.StringToBrush(value); } }

		[Range(1, 6)]
		[Display(Name = "MidLine Width", Order = 3, GroupName = "4. MidLine")]
		public float MidLineWidth { get; set; }

		[Display(Name = "MidLine Dash Style", Order = 4, GroupName = "4. MidLine")]
		public DashStyleHelper MidLineDashStyle { get; set; }

		#endregion

		public override bool SupportsAlerts { get { return true; } }

		protected override void Dispose(bool disposing)
		{
			base.Dispose(disposing);
			try { if (areaBrushDevice    != null) areaBrushDevice.RenderTarget    = null; } catch {}
			try { if (outlineBrushDevice != null) outlineBrushDevice.RenderTarget = null; } catch {}
			try { if (labelBrushDevice   != null) labelBrushDevice.RenderTarget   = null; } catch {}
			try { if (midLineBrushDevice != null) midLineBrushDevice.RenderTarget = null; } catch {}
			try { if (cachedTextLayout != null) cachedTextLayout.Dispose(); cachedTextLayout = null; } catch {}
			try { if (cachedTextFormat != null) cachedTextFormat.Dispose(); cachedTextFormat = null; } catch {}
		}

		// ── Color scheme per type ─────────────────────────────────────────
		private struct ZoneColors { public Color fill; public Color outline; public Color midLine; }

		private static ZoneColors GetColors(SuperZoneLabelType t)
		{
			switch (t)
			{
				case SuperZoneLabelType.Support:
					return new ZoneColors { fill=Colors.ForestGreen,   outline=Colors.ForestGreen,   midLine=Colors.LimeGreen };
				case SuperZoneLabelType.Resistance:
					return new ZoneColors { fill=Colors.Crimson,       outline=Colors.Crimson,       midLine=Colors.OrangeRed };
				case SuperZoneLabelType.Supply:
					return new ZoneColors { fill=Colors.OrangeRed,     outline=Colors.OrangeRed,     midLine=Colors.Orange };
				case SuperZoneLabelType.Demand:
					return new ZoneColors { fill=Colors.DodgerBlue,    outline=Colors.DodgerBlue,    midLine=Colors.DeepSkyBlue };
				case SuperZoneLabelType.ValueAreaHigh:
				case SuperZoneLabelType.ValueAreaLow:
					return new ZoneColors { fill=Colors.Goldenrod,     outline=Colors.Goldenrod,     midLine=Colors.Gold };
				case SuperZoneLabelType.POC:
					return new ZoneColors { fill=Colors.Yellow,        outline=Colors.Yellow,        midLine=Colors.LightYellow };
				case SuperZoneLabelType.Gap:
					return new ZoneColors { fill=Colors.MediumPurple,  outline=Colors.MediumPurple,  midLine=Colors.Plum };
				default:
					return new ZoneColors { fill=Colors.CornflowerBlue,outline=Colors.CornflowerBlue,midLine=Colors.LightBlue };
			}
		}

		private void ApplyTypeDefaults(SuperZoneLabelType t)
		{
			try
			{
				ZoneColors c = GetColors(t);
				AreaBrush = MakeBrush(c.fill);
				areaBrushDevice.Brush = null;
				if (OutlineStroke == null) OutlineStroke = new Stroke();
				OutlineStroke.Brush = new SolidColorBrush(c.outline);
				outlineBrushDevice.Brush = null;
				MidLineBrush = new SolidColorBrush(c.midLine);
				midLineBrushDevice.Brush = null;
			}
			catch {}
		}

		private Brush MakeBrush(Color c)
		{
			try { SolidColorBrush b = new SolidColorBrush(c); b.Freeze(); return b; }
			catch { return Brushes.CornflowerBlue; }
		}

		// ── Label text — cached, only recomposed when an input actually changes ───
		private string				cachedDisplayText		= null;
		private SuperZoneLabelType	cachedDisplayLabelType	= (SuperZoneLabelType)(-1);
		private string				cachedDisplayCustomLabel;
		private string				cachedDisplayStatsText;

		private string GetLabelText()
		{
			if (cachedDisplayText != null && cachedDisplayLabelType == LabelType
				&& cachedDisplayCustomLabel == CustomLabel && cachedDisplayStatsText == StatsText)
				return cachedDisplayText;

			string baseText = LabelType == SuperZoneLabelType.Custom
				? (CustomLabel ?? "")
				: (string.IsNullOrEmpty(CustomLabel) ? SplitCamelCase(LabelType.ToString()) : SplitCamelCase(LabelType.ToString()) + " — " + CustomLabel);

			string text = string.IsNullOrEmpty(StatsText) ? baseText
				: (string.IsNullOrEmpty(baseText) ? StatsText : baseText + "\n" + StatsText);

			cachedDisplayText			= text;
			cachedDisplayLabelType		= LabelType;
			cachedDisplayCustomLabel	= CustomLabel;
			cachedDisplayStatsText		= StatsText;
			return text;
		}

		private static string SplitCamelCase(string s)
		{
			if (string.IsNullOrEmpty(s)) return s;
			System.Text.StringBuilder sb = new System.Text.StringBuilder();
			for (int i = 0; i < s.Length; i++)
			{
				if (i > 0 && char.IsUpper(s[i]) && !char.IsUpper(s[i - 1]))
					sb.Append(' ');
				sb.Append(s[i]);
			}
			return sb.ToString();
		}

		// ── Pixel rect from the anchors directly ──────────────────────────
		private bool TryGetPixelRect(ChartControl cc, ChartPanel cp, ChartScale cs, out SharpDX.RectangleF rect)
		{
			rect = new SharpDX.RectangleF();
			try
			{
				if (cc==null || cs==null || cp==null || StartAnchor==null || EndAnchor==null) return false;
				double x1 = cc.GetXByTime(StartAnchor.Time);
				double x2 = isOpenEndedRight ? cp.X + cp.W : cc.GetXByTime(EndAnchor.Time);
				double y1 = cs.GetYByValue(Math.Max(StartAnchor.Price, EndAnchor.Price));
				double y2 = cs.GetYByValue(Math.Min(StartAnchor.Price, EndAnchor.Price));
				float left=(float)Math.Min(x1,x2), top=(float)Math.Min(y1,y2);
				float w=(float)Math.Abs(x2-x1),    h=(float)Math.Abs(y2-y1);
				// clamp instead of bailing — two clicks close together in price (easy on a
				// zoomed-out chart, where a 1-tick gap can be sub-pixel) must still draw
				// something, not silently vanish
				if (w<2f) w=2f;
				if (h<2f) h=2f;
				rect = new SharpDX.RectangleF(left, top, w, h);
				return true;
			}
			catch (Exception ex) { PrintOnce("TryGetPixelRect", "SuperZones.TryGetPixelRect: " + ex); return false; }
		}

		// ── NT overrides ──────────────────────────────────────────────────

		public override void OnCalculateMinMax()
		{
			try
			{
				MinValue = double.MaxValue;
				MaxValue = double.MinValue;
				if (!IsVisible || StartAnchor == null || EndAnchor == null) return;
				MinValue = Math.Min(StartAnchor.Price, EndAnchor.Price);
				MaxValue = Math.Max(StartAnchor.Price, EndAnchor.Price);
			}
			catch {}
		}

		public override Point[] GetSelectionPoints(ChartControl cc, ChartScale cs)
		{
			try
			{
				ChartPanel cp = cc.ChartPanels[PanelIndex];
				SharpDX.RectangleF r;
				if (!TryGetPixelRect(cc,cp,cs,out r)) return new Point[0];
				return new[]{new Point(r.Left,r.Top),new Point(r.Right,r.Top),new Point(r.Left,r.Bottom),new Point(r.Right,r.Bottom)};
			}
			catch { return new Point[0]; }
		}

		public override IEnumerable<AlertConditionItem> GetAlertConditionItems()
		{ yield return new AlertConditionItem{Name="SuperZone",ShouldOnlyDisplayName=true}; }

		public override IEnumerable<Condition> GetValidAlertConditions()
		{ return new[]{Condition.CrossInside,Condition.CrossOutside}; }

		public override bool IsAlertConditionTrue(AlertConditionItem item,Condition condition,
			ChartAlertValue[] values,ChartControl cc,ChartScale cs)
		{
			try
			{
				double minP=Math.Min(StartAnchor.Price,EndAnchor.Price),maxP=Math.Max(StartAnchor.Price,EndAnchor.Price);
				DateTime minT=StartAnchor.Time;
				DateTime maxT=isOpenEndedRight ? DateTime.MaxValue : EndAnchor.Time;
				return MathHelper.DidPredicateCross(values,v=>{bool i=v.Value>=minP&&v.Value<=maxP&&v.Time>=minT&&v.Time<=maxT;return condition==Condition.CrossInside?i:!i;});
			}
			catch { return false; }
		}

		public override bool IsVisibleOnChart(ChartControl cc,ChartScale cs,DateTime first,DateTime last)
		{
			try
			{
				if (StartAnchor.IsEditing) return true; // still being built, always show the preview
				if (isOpenEndedRight) return StartAnchor.Time <= last;
				return StartAnchor.Time <= last && EndAnchor.Time >= first;
			}
			catch { return true; }
		}

		public override Cursor GetCursor(ChartControl cc,ChartPanel cp,ChartScale cs,Point point)
		{
			try
			{
				switch (DrawingState)
				{
					case DrawingState.Building: return Cursors.Pen;
					case DrawingState.Editing:  return IsLocked ? Cursors.No : Cursors.SizeNS;
					case DrawingState.Moving:   return IsLocked ? Cursors.No : Cursors.SizeAll;
					default:
						ChartAnchor closest = GetClosestAnchor(cc, cp, cs, cursorSensitivity, point);
						if (closest != null)
							return IsLocked ? Cursors.Arrow : Cursors.SizeNS;

						SharpDX.RectangleF rect;
						if (!TryGetPixelRect(cc,cp,cs,out rect)) return null;
						if (point.X>=rect.Left && point.X<=rect.Right && point.Y>=rect.Top && point.Y<=rect.Bottom)
							return IsLocked ? Cursors.Arrow : Cursors.SizeAll;
						return null;
				}
			}
			catch { return null; }
		}

		public override void OnMouseDown(ChartControl cc,ChartPanel cp,ChartScale cs,ChartAnchor dataPoint)
		{
			try
			{
				switch (DrawingState)
				{
					case DrawingState.Building:
						if (StartAnchor.IsEditing)
						{
							dataPoint.CopyDataValues(StartAnchor);
							dataPoint.CopyDataValues(EndAnchor);
							StartAnchor.IsEditing = false;
						}
						else if (EndAnchor.IsEditing)
						{
							dataPoint.Time      = StartAnchor.Time;      // single shared left edge
							dataPoint.SlotIndex  = StartAnchor.SlotIndex;
							dataPoint.CopyDataValues(EndAnchor);
							EndAnchor.IsEditing = false;
						}
						if (!StartAnchor.IsEditing && !EndAnchor.IsEditing)
						{
							double tick = AttachedTo!=null ? AttachedTo.Instrument.MasterInstrument.TickSize : 0.25;
							if (Math.Abs(StartAnchor.Price-EndAnchor.Price) < tick*0.5)
								EndAnchor.Price = StartAnchor.Price - tick;
							DrawingState = DrawingState.Normal;
							IsSelected   = false;
						}
						break;

					case DrawingState.Normal:
						Point point = dataPoint.GetPoint(cc, cp, cs);
						editingAnchor = GetClosestAnchor(cc, cp, cs, cursorSensitivity, point);
						if (editingAnchor != null)
						{
							editingAnchor.IsEditing = true;
							DrawingState = DrawingState.Editing;
						}
						else
						{
							SharpDX.RectangleF rect;
							if (TryGetPixelRect(cc,cp,cs,out rect)
								&& point.X>=rect.Left && point.X<=rect.Right && point.Y>=rect.Top && point.Y<=rect.Bottom)
								DrawingState = DrawingState.Moving;
							else
								IsSelected = false;
						}
						break;
				}
			}
			catch (Exception ex) { PrintOnce("OnMouseDown", "SuperZones.OnMouseDown: " + ex); }
		}

		public override void OnMouseMove(ChartControl cc,ChartPanel cp,ChartScale cs,ChartAnchor dataPoint)
		{
			try
			{
				if (IsLocked && DrawingState != DrawingState.Building) return;

				if (DrawingState == DrawingState.Building && EndAnchor.IsEditing)
				{
					dataPoint.Time = StartAnchor.Time; // keep pinned to the left edge while dragging price
					dataPoint.CopyDataValues(EndAnchor);
				}
				else if (DrawingState == DrawingState.Editing && editingAnchor != null)
				{
					editingAnchor.Price = dataPoint.Price; // price only — keeps the shared left edge in sync
				}
				else if (DrawingState == DrawingState.Moving)
				{
					foreach (ChartAnchor anchor in Anchors)
						anchor.MoveAnchor(InitialMouseDownAnchor, dataPoint, cc, cp, cs, this);
				}
			}
			catch (Exception ex) { PrintOnce("OnMouseMove", "SuperZones.OnMouseMove: " + ex); }
		}

		public override void OnMouseUp(ChartControl cc,ChartPanel cp,ChartScale cs,ChartAnchor dataPoint)
		{
			try
			{
				if (DrawingState == DrawingState.Building) return;
				if (DrawingState == DrawingState.Editing || DrawingState == DrawingState.Moving)
					DrawingState = DrawingState.Normal;
				if (editingAnchor != null) editingAnchor.IsEditing = false;
				editingAnchor = null;
			}
			catch {}
		}

		public override void OnRender(ChartControl cc,ChartScale cs)
		{
			try
			{
				if (cc==null||cs==null) return;
				ChartPanel cp=cc.ChartPanels[PanelIndex];
				if (cp==null) return;
				if (StartAnchor==null || EndAnchor==null || StartAnchor.IsEditing) return; // nothing placed yet

				SharpDX.RectangleF rect;
				if (!TryGetPixelRect(cc,cp,cs,out rect)) return;

				RenderTarget.AntialiasMode=SharpDX.Direct2D1.AntialiasMode.PerPrimitive;

				// Fill
				try
				{
					if (!IsInHitTest&&areaBrush!=null)
					{
						if (areaBrushDevice.Brush==null)
						{ Brush c=areaBrush.Clone();c.Opacity=areaOpacity/100d;areaBrushDevice.Brush=c; }
						areaBrushDevice.RenderTarget=RenderTarget;
						if (areaBrushDevice.BrushDX!=null)
							RenderTarget.FillRectangle(rect,areaBrushDevice.BrushDX);
					}
				}
				catch (Exception ex) { areaBrushDevice.Brush=null; PrintOnce("Fill", "SuperZones.OnRender Fill: " + ex); }

				// Outline
				try
				{
					if (OutlineStroke!=null)
					{
						OutlineStroke.RenderTarget=RenderTarget;
						if (outlineBrushDevice.Brush==null&&OutlineStroke.Brush!=null)
						{ Brush c=OutlineStroke.Brush.Clone();c.Opacity=outlineOpacity/100d;outlineBrushDevice.Brush=c; }
						outlineBrushDevice.RenderTarget=RenderTarget;
						SharpDX.Direct2D1.Brush dx=IsInHitTest?cc.SelectionBrush:outlineBrushDevice.BrushDX??OutlineStroke.BrushDX;
						if (dx!=null) RenderTarget.DrawRectangle(rect,dx,OutlineStroke.Width,OutlineStroke.StrokeStyle);
					}
				}
				catch (Exception ex) { outlineBrushDevice.Brush=null; PrintOnce("Outline", "SuperZones.OnRender Outline: " + ex); }

				// MidLine
				if (!IsInHitTest&&MidLineVisible&&midLineBrushField!=null)
				{
					try
					{
						if (midLineBrushDevice.Brush==null)
						{ Brush c=midLineBrushField.Clone();midLineBrushDevice.Brush=c; }
						midLineBrushDevice.RenderTarget=RenderTarget;
						if (midLineBrushDevice.BrushDX!=null)
						{
							float midY=rect.Top+rect.Height/2f;
							midLineStroke.DashStyleHelper=MidLineDashStyle;
							midLineStroke.RenderTarget=RenderTarget;
							RenderTarget.DrawLine(
								new SharpDX.Vector2(rect.Left,midY),
								new SharpDX.Vector2(rect.Right,midY),
								midLineBrushDevice.BrushDX,MidLineWidth,midLineStroke.StrokeStyle);
						}
					}
					catch { midLineBrushDevice.Brush=null; }
				}

				// Label
				if (!IsInHitTest&&LabelVisible)
				{
					try
					{
						string txt=GetLabelText();
						if (!string.IsNullOrEmpty(txt))
						{
							if (labelBrushDevice.Brush==null)
							{ Brush lb=(labelBrushField??Brushes.White).Clone();labelBrushDevice.Brush=lb; }
							labelBrushDevice.RenderTarget=RenderTarget;
							if (labelBrushDevice.BrushDX!=null)
							{
								if (cachedTextFormat==null||cachedFontSize!=LabelFontSize)
								{
									if (cachedTextLayout != null) cachedTextLayout.Dispose();
									cachedTextLayout=null;
									if (cachedTextFormat != null) cachedTextFormat.Dispose();
									cachedTextFormat=new SharpDX.DirectWrite.TextFormat(
										Core.Globals.DirectWriteFactory,"Arial",
										SharpDX.DirectWrite.FontWeight.Bold,
										SharpDX.DirectWrite.FontStyle.Normal,
										SharpDX.DirectWrite.FontStretch.Normal,
										(float)LabelFontSize);
									cachedTextFormat.TextAlignment=SharpDX.DirectWrite.TextAlignment.Leading;
									cachedTextFormat.WordWrapping =SharpDX.DirectWrite.WordWrapping.NoWrap;
									cachedFontSize=LabelFontSize;
								}

								float layoutWidth=rect.Width+200f;
								if (cachedTextLayout==null||cachedLabelText!=txt||Math.Abs(cachedLayoutWidth-layoutWidth)>0.5f)
								{
									if (cachedTextLayout != null) cachedTextLayout.Dispose();
									int lineCount=1; foreach(char ch in txt) if (ch=='\n') lineCount++;
									cachedTextLayout=new SharpDX.DirectWrite.TextLayout(
										Core.Globals.DirectWriteFactory,txt,cachedTextFormat,layoutWidth,(float)(LabelFontSize*lineCount)+4f);
									cachedLabelText=txt;
									cachedLayoutWidth=layoutWidth;
								}

								SharpDX.DirectWrite.TextLayout tl=cachedTextLayout;
								float th=tl.Metrics.Height,tw=tl.Metrics.Width;
								float midY=rect.Top+rect.Height/2f;
								float offset=(float)LabelOutsideOffset;
								float x,y;
								switch(LabelPosition)
								{
									case SuperZoneLabelPosition.TopLeft:      x=rect.Left+4f;     y=rect.Top+3f;          break;
									case SuperZoneLabelPosition.TopRight:     x=rect.Right-tw-4f; y=rect.Top+3f;          break;
									case SuperZoneLabelPosition.BottomLeft:   x=rect.Left+4f;     y=rect.Bottom-th-3f;    break;
									case SuperZoneLabelPosition.BottomRight:  x=rect.Right-tw-4f; y=rect.Bottom-th-3f;    break;
									case SuperZoneLabelPosition.CenterLeft:   x=rect.Left+4f;     y=midY-th-2f;           break;
									case SuperZoneLabelPosition.CenterRight:  x=rect.Right-tw-4f; y=midY-th-2f;           break;
									case SuperZoneLabelPosition.OutsideTop:   x=rect.Left+4f;     y=rect.Top-th-offset;   break;
									case SuperZoneLabelPosition.OutsideBottom:x=rect.Left+4f;     y=rect.Bottom+offset;   break;
									default:                                  x=rect.Left+4f;     y=rect.Top+3f;          break;
								}
								RenderTarget.DrawTextLayout(new SharpDX.Vector2(x,y),tl,labelBrushDevice.BrushDX,SharpDX.Direct2D1.DrawTextOptions.NoSnap);
							}
						}
					}
					catch (Exception ex) { labelBrushDevice.Brush=null; PrintOnce("Label", "SuperZones.OnRender Label: " + ex); }
				}
			}
			catch (Exception ex) { PrintOnce("OnRender", "SuperZones.OnRender: " + ex); }
		}

		protected override void OnStateChange()
		{
			if (State==State.SetDefaults)
			{
				Name         = "SuperZones";
				DrawingState = DrawingState.Building;
				StartAnchor  = new ChartAnchor{DisplayName="Start",IsEditing=true,DrawingTool=this};
				EndAnchor    = new ChartAnchor{DisplayName="End",  IsEditing=true,DrawingTool=this};

				// Defaults for Resistance
				AreaBrush      = MakeBrush(Colors.Crimson);
				AreaOpacity    = 20;
				OutlineStroke  = new Stroke(new SolidColorBrush(Colors.Crimson),DashStyleHelper.Solid,1f);
				OutlineOpacity = 100;

				labelType         = SuperZoneLabelType.Resistance;
				CustomLabel       = "";
				LabelVisible      = true;
				LabelPosition     = SuperZoneLabelPosition.TopLeft;
				LabelOutsideOffset= 6;
				LabelBrush        = Brushes.White;
				LabelFontSize     = 11;

				MidLineVisible   = true;
				MidLineBrush     = new SolidColorBrush(Colors.OrangeRed);
				MidLineWidth     = 1f;
				MidLineDashStyle = DashStyleHelper.Dash;

				isOpenEndedRight = true;
			}
			else if (State==State.Terminated)
				Dispose();
		}
	}
}
