#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
#endregion

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
		private enum DragHandle { None, TopLeft, TopRight, BottomLeft, BottomRight, Body }

		private const double Hit = 12;

		// ── Zone bounds (computed from snap + extend) ─────────────────────
		private DateTime	zoneStartTime		= DateTime.MinValue;
		private DateTime	zoneEndTime			= DateTime.MinValue;
		private double		zoneTopPrice		= double.NaN;
		private double		zoneBotPrice		= double.NaN;

		// ── Original snap session — base for extend calculations ──────────
		private DateTime	snapSessionStart	= DateTime.MinValue;
		private DateTime	snapSessionEnd		= DateTime.MinValue;

		// ── Build state ───────────────────────────────────────────────────
		private bool		isBuilding			= true;
		private bool		buildPhase1Done		= false;

		// ── Drag state ────────────────────────────────────────────────────
		private DragHandle	dragHandle			= DragHandle.None;
		private double		dragStartPrice;
		private DateTime	dragStartTime;

		// ── Cached bars for session iteration ────────────────────────────
		private NinjaTrader.Data.Bars cachedBars;

		// ── Device brushes ────────────────────────────────────────────────
		private int			areaOpacity			= 20;
		private Brush		areaBrush;
		private DeviceBrush	areaBrushDevice		= new DeviceBrush();
		private int			outlineOpacity		= 100;
		private DeviceBrush	outlineBrushDevice	= new DeviceBrush();
		private Brush		labelBrushField;
		private DeviceBrush	labelBrushDevice	= new DeviceBrush();
		private Brush		midLineBrushField;
		private DeviceBrush	midLineBrushDevice	= new DeviceBrush();

		// Serialization anchors only — not used for rendering
		[Browsable(false)] public ChartAnchor StartAnchor { get; set; }
		[Browsable(false)] public ChartAnchor EndAnchor   { get; set; }

		public override IEnumerable<ChartAnchor> Anchors
		{ get { return new[] { StartAnchor, EndAnchor }; } }

		public override object Icon { get { return Gui.Tools.Icons.DrawRegionHighlightY; } }

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

		#region Properties — Session

		[Display(Name = "Snap To Session On Draw", Order = 1, GroupName = "5. Session")]
		public bool SnapToSession { get; set; }

		private int extendRight = 0;
		[Range(0, 50)]
		[Display(Name = "Extend Right (sessions)", Order = 2, GroupName = "5. Session")]
		public int ExtendRight
		{
			get { return extendRight; }
			set { extendRight = Math.Max(0, value); RecalcExtendedBounds(); }
		}

		private int extendLeft = 0;
		[Range(0, 50)]
		[Display(Name = "Extend Left (sessions)", Order = 3, GroupName = "5. Session")]
		public int ExtendLeft
		{
			get { return extendLeft; }
			set { extendLeft = Math.Max(0, value); RecalcExtendedBounds(); }
		}

		#endregion

		#region Serialization fields

		[Browsable(false)]
		public long ZoneStartTimeTicks
		{ get { return zoneStartTime.Ticks; } set { zoneStartTime = new DateTime(value); } }

		[Browsable(false)]
		public long ZoneEndTimeTicks
		{ get { return zoneEndTime.Ticks; } set { zoneEndTime = new DateTime(value); } }

		[Browsable(false)]
		public double ZoneTopPrice
		{ get { return zoneTopPrice; } set { zoneTopPrice = value; } }

		[Browsable(false)]
		public double ZoneBotPrice
		{ get { return zoneBotPrice; } set { zoneBotPrice = value; } }

		[Browsable(false)]
		public bool ZoneBuildDone
		{ get { return !isBuilding; } set { isBuilding = !value; buildPhase1Done = value; } }

		[Browsable(false)]
		public long SnapSessionStartTicks
		{ get { return snapSessionStart.Ticks; } set { snapSessionStart = new DateTime(value); } }

		[Browsable(false)]
		public long SnapSessionEndTicks
		{ get { return snapSessionEnd.Ticks; } set { snapSessionEnd = new DateTime(value); } }

		#endregion

		public override bool SupportsAlerts { get { return true; } }

		protected override void Dispose(bool disposing)
		{
			base.Dispose(disposing);
			try { if (areaBrushDevice    != null) areaBrushDevice.RenderTarget    = null; } catch {}
			try { if (outlineBrushDevice != null) outlineBrushDevice.RenderTarget = null; } catch {}
			try { if (labelBrushDevice   != null) labelBrushDevice.RenderTarget   = null; } catch {}
			try { if (midLineBrushDevice != null) midLineBrushDevice.RenderTarget = null; } catch {}
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

		// ── Label text — only Custom shows text ───────────────────────────
		private string GetLabelText()
		{
			if (LabelType == SuperZoneLabelType.Custom) return CustomLabel ?? "";
			return "";
		}

		// ── Zone validity ─────────────────────────────────────────────────
		private bool ZoneValid()
		{
			return zoneStartTime != DateTime.MinValue && zoneEndTime != DateTime.MinValue
				&& !double.IsNaN(zoneTopPrice) && !double.IsNaN(zoneBotPrice);
		}

		// ── Pixel rect from zone times + prices ───────────────────────────
		private bool TryGetPixelRect(ChartControl cc, ChartScale cs, out SharpDX.RectangleF rect)
		{
			rect = new SharpDX.RectangleF();
			try
			{
				if (!ZoneValid() || cc==null || cs==null) return false;
				double x1 = cc.GetXByTime(zoneStartTime);
				double x2 = cc.GetXByTime(zoneEndTime);
				double y1 = cs.GetYByValue(Math.Max(zoneTopPrice, zoneBotPrice));
				double y2 = cs.GetYByValue(Math.Min(zoneTopPrice, zoneBotPrice));
				float left=(float)Math.Min(x1,x2), top=(float)Math.Min(y1,y2);
				float w=(float)Math.Abs(x2-x1),    h=(float)Math.Abs(y2-y1);
				if (w<1f||h<1f) return false;
				rect = new SharpDX.RectangleF(left, top, w, h);
				return true;
			}
			catch { return false; }
		}

		// ── Hit testing ───────────────────────────────────────────────────
		private DragHandle GetHandleAtPoint(Point pt, ChartControl cc, ChartScale cs)
		{
			try
			{
				if (!ZoneValid()||cc==null||cs==null) return DragHandle.None;
				double x1=cc.GetXByTime(zoneStartTime), x2=cc.GetXByTime(zoneEndTime);
				double y1=cs.GetYByValue(Math.Max(zoneTopPrice,zoneBotPrice));
				double y2=cs.GetYByValue(Math.Min(zoneTopPrice,zoneBotPrice));
				double l=Math.Min(x1,x2),r=Math.Max(x1,x2),t=Math.Min(y1,y2),b=Math.Max(y1,y2);
				if ((pt-new Point(l,t)).Length<=Hit) return DragHandle.TopLeft;
				if ((pt-new Point(r,t)).Length<=Hit) return DragHandle.TopRight;
				if ((pt-new Point(l,b)).Length<=Hit) return DragHandle.BottomLeft;
				if ((pt-new Point(r,b)).Length<=Hit) return DragHandle.BottomRight;
				if (pt.X>=l-Hit&&pt.X<=r+Hit&&pt.Y>=t-Hit&&pt.Y<=b+Hit) return DragHandle.Body;
			}
			catch {}
			return DragHandle.None;
		}

		// ── Session snap — finds session CONTAINING the click time ────────
		private void TrySnapToSession(DateTime clickTime, ChartControl cc)
		{
			try
			{
				if (!SnapToSession||cc==null) return;
				NinjaTrader.Data.Bars bars = GetBars(cc);
				if (bars==null) return;

				SessionIterator si = new SessionIterator(bars);
				// includeCurrentSession=true ensures we find the session that contains clickTime
				// rather than skipping to the next one
				si.GetNextSession(clickTime, true);
				snapSessionStart = si.ActualSessionBegin;
				snapSessionEnd   = si.ActualSessionEnd;

				// Apply extend
				RecalcExtendedBoundsWithIterator(si);
			}
			catch {}
		}

		// ── Recalc zone start/end from snap + extend properties ───────────
		private void RecalcExtendedBounds()
		{
			try
			{
				if (snapSessionStart==DateTime.MinValue||snapSessionEnd==DateTime.MinValue) return;
				if (cachedBars==null) return;
				SessionIterator si = new SessionIterator(cachedBars);
				si.GetNextSession(snapSessionStart, true);
				RecalcExtendedBoundsWithIterator(si);
				SyncAnchors();
			}
			catch {}
		}

		private void RecalcExtendedBoundsWithIterator(SessionIterator si)
		{
			try
			{
				// Extend right from snap session end
				DateTime end = snapSessionEnd;
				for (int i=0;i<extendRight;i++)
				{
					si.GetNextSession(end.AddSeconds(1), false);
					end = si.ActualSessionEnd;
				}
				zoneEndTime = end;

				// Extend left from snap session start — walk backward
				// We step back by calling GetNextSession on a time slightly before
				// each found session begin
				DateTime start = snapSessionStart;
				SessionIterator si2 = new SessionIterator(cachedBars);
				for (int i=0;i<extendLeft;i++)
				{
					// Step back 1 minute before current start to land in previous session
					si2.GetNextSession(start.AddMinutes(-1), true);
					start = si2.ActualSessionBegin;
				}
				zoneStartTime = start;
			}
			catch {}
		}

		private NinjaTrader.Data.Bars GetBars(ChartControl cc)
		{
			try
			{
				if (cachedBars!=null) return cachedBars;
				var ba=cc.BarsArray;
				if (ba!=null)
					foreach (var cb in ba)
						if (cb!=null&&cb.Bars!=null) { cachedBars=cb.Bars; return cachedBars; }
			}
			catch {}
			return null;
		}

		private void SyncAnchors()
		{
			try
			{
				if (StartAnchor!=null) { StartAnchor.Time=zoneStartTime; StartAnchor.Price=Math.Max(zoneTopPrice,zoneBotPrice); }
				if (EndAnchor  !=null) { EndAnchor.Time  =zoneEndTime;   EndAnchor.Price  =Math.Min(zoneTopPrice,zoneBotPrice); }
			}
			catch {}
		}

		// ── NT overrides ──────────────────────────────────────────────────

		public override void OnCalculateMinMax()
		{
			try
			{
				MinValue=double.MaxValue; MaxValue=double.MinValue;
				if (!IsVisible||!ZoneValid()) return;
				MinValue=Math.Min(zoneTopPrice,zoneBotPrice);
				MaxValue=Math.Max(zoneTopPrice,zoneBotPrice);
			}
			catch {}
		}

		public override Point[] GetSelectionPoints(ChartControl cc, ChartScale cs)
		{
			try
			{
				SharpDX.RectangleF r;
				if (!TryGetPixelRect(cc,cs,out r)) return new Point[0];
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
				double minP=Math.Min(zoneTopPrice,zoneBotPrice),maxP=Math.Max(zoneTopPrice,zoneBotPrice);
				DateTime minT=zoneStartTime<zoneEndTime?zoneStartTime:zoneEndTime;
				DateTime maxT=zoneStartTime<zoneEndTime?zoneEndTime:zoneStartTime;
				return MathHelper.DidPredicateCross(values,v=>{bool i=v.Value>=minP&&v.Value<=maxP&&v.Time>=minT&&v.Time<=maxT;return condition==Condition.CrossInside?i:!i;});
			}
			catch { return false; }
		}

		public override bool IsVisibleOnChart(ChartControl cc,ChartScale cs,DateTime first,DateTime last)
		{
			try
			{
				if (isBuilding) return true;
				if (!ZoneValid()) return false;
				DateTime minT=zoneStartTime<zoneEndTime?zoneStartTime:zoneEndTime;
				DateTime maxT=zoneStartTime<zoneEndTime?zoneEndTime:zoneStartTime;
				return minT<=last&&maxT>=first;
			}
			catch { return true; }
		}

		public override Cursor GetCursor(ChartControl cc,ChartPanel cp,ChartScale cs,Point point)
		{
			try
			{
				if (isBuilding) return Cursors.Pen;
				if (!ZoneValid()) return null;
				if (DrawingState==DrawingState.Moving)  return IsLocked?Cursors.No:Cursors.SizeAll;
				if (DrawingState==DrawingState.Editing) return IsLocked?Cursors.No:Cursors.SizeAll;
				DragHandle h=GetHandleAtPoint(point,cc,cs);
				switch(h)
				{
					case DragHandle.TopLeft:  case DragHandle.BottomRight: return IsLocked?Cursors.Arrow:Cursors.SizeNWSE;
					case DragHandle.TopRight: case DragHandle.BottomLeft:  return IsLocked?Cursors.Arrow:Cursors.SizeNESW;
					case DragHandle.Body:      return IsLocked?Cursors.Arrow:Cursors.SizeAll;
					default:                  return null;
				}
			}
			catch { return null; }
		}

		public override void OnMouseDown(ChartControl cc,ChartPanel cp,ChartScale cs,ChartAnchor dataPoint)
		{
			try
			{
				if (isBuilding)
				{
					if (!buildPhase1Done)
					{
						// Cache bars for session iteration
						GetBars(cc);
						zoneStartTime   = dataPoint.Time;
						zoneEndTime     = dataPoint.Time;
						zoneTopPrice    = dataPoint.Price;
						zoneBotPrice    = dataPoint.Price;
						snapSessionStart= dataPoint.Time;
						snapSessionEnd  = dataPoint.Time;
						TrySnapToSession(dataPoint.Time, cc);
						buildPhase1Done = true;
					}
					else
					{
						zoneBotPrice = dataPoint.Price;
						double tick  = AttachedTo!=null?AttachedTo.Instrument.MasterInstrument.TickSize:0.25;
						if (Math.Abs(zoneTopPrice-zoneBotPrice)<tick*0.5) zoneBotPrice=zoneTopPrice-tick;
						isBuilding   = false;
						DrawingState = DrawingState.Normal;
						IsSelected   = false;
						SyncAnchors();
					}
					return;
				}

				dragHandle     = GetHandleAtPoint(dataPoint.GetPoint(cc,cp,cs),cc,cs);
				dragStartPrice = dataPoint.Price;
				dragStartTime  = dataPoint.Time;
				if (dragHandle==DragHandle.None) IsSelected=false;
				else DrawingState=dragHandle==DragHandle.Body?DrawingState.Moving:DrawingState.Editing;
			}
			catch {}
		}

		public override void OnMouseMove(ChartControl cc,ChartPanel cp,ChartScale cs,ChartAnchor dataPoint)
		{
			try
			{
				if (IsLocked&&!isBuilding) return;

				if (isBuilding&&buildPhase1Done)
				{
					zoneBotPrice=dataPoint.Price;
					if (!SnapToSession) zoneEndTime=dataPoint.Time;
					return;
				}

				if (DrawingState!=DrawingState.Moving&&DrawingState!=DrawingState.Editing) return;

				double   dp=dataPoint.Price-dragStartPrice;
				TimeSpan dt=dataPoint.Time -dragStartTime;

				switch(dragHandle)
				{
					case DragHandle.Body:        zoneTopPrice+=dp;zoneBotPrice+=dp;zoneStartTime=zoneStartTime.Add(dt);zoneEndTime=zoneEndTime.Add(dt);snapSessionStart=snapSessionStart.Add(dt);snapSessionEnd=snapSessionEnd.Add(dt);break;
					case DragHandle.TopLeft:     zoneTopPrice+=dp;zoneStartTime=zoneStartTime.Add(dt);snapSessionStart=snapSessionStart.Add(dt);break;
					case DragHandle.TopRight:    zoneTopPrice+=dp;zoneEndTime=zoneEndTime.Add(dt);snapSessionEnd=snapSessionEnd.Add(dt);break;
					case DragHandle.BottomLeft:  zoneBotPrice+=dp;zoneStartTime=zoneStartTime.Add(dt);snapSessionStart=snapSessionStart.Add(dt);break;
					case DragHandle.BottomRight: zoneBotPrice+=dp;zoneEndTime=zoneEndTime.Add(dt);snapSessionEnd=snapSessionEnd.Add(dt);break;
				}

				dragStartPrice=dataPoint.Price;
				dragStartTime =dataPoint.Time;
				SyncAnchors();
			}
			catch {}
		}

		public override void OnMouseUp(ChartControl cc,ChartPanel cp,ChartScale cs,ChartAnchor dataPoint)
		{
			try
			{
				if (isBuilding) return;
				DrawingState=DrawingState.Normal;
				dragHandle=DragHandle.None;
				SyncAnchors();
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
				if (isBuilding&&!buildPhase1Done) return;

				// Cache bars if not yet done
				if (cachedBars==null) GetBars(cc);

				SharpDX.RectangleF rect;
				if (!TryGetPixelRect(cc,cs,out rect)) return;

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
				catch { areaBrushDevice.Brush=null; }

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
				catch { outlineBrushDevice.Brush=null; }

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
							Stroke tmp=new Stroke();tmp.DashStyleHelper=MidLineDashStyle;tmp.RenderTarget=RenderTarget;
							RenderTarget.DrawLine(
								new SharpDX.Vector2(rect.Left,midY),
								new SharpDX.Vector2(rect.Right,midY),
								midLineBrushDevice.BrushDX,MidLineWidth,tmp.StrokeStyle);
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
								using (SharpDX.DirectWrite.TextFormat tf=new SharpDX.DirectWrite.TextFormat(
									Core.Globals.DirectWriteFactory,"Arial",
									SharpDX.DirectWrite.FontWeight.Bold,
									SharpDX.DirectWrite.FontStyle.Normal,
									SharpDX.DirectWrite.FontStretch.Normal,
									(float)LabelFontSize))
								{
									tf.TextAlignment=SharpDX.DirectWrite.TextAlignment.Leading;
									tf.WordWrapping =SharpDX.DirectWrite.WordWrapping.NoWrap;
									using (SharpDX.DirectWrite.TextLayout tl=new SharpDX.DirectWrite.TextLayout(
										Core.Globals.DirectWriteFactory,txt,tf,rect.Width+200f,(float)LabelFontSize+4f))
									{
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
						}
					}
					catch { labelBrushDevice.Brush=null; }
				}
			}
			catch {}
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

				SnapToSession = false;
				extendRight   = 0;
				extendLeft    = 0;
			}
			else if (State==State.Active)
			{
				if (ZoneBuildDone&&ZoneValid())
				{
					isBuilding      = false;
					buildPhase1Done = true;
					DrawingState    = DrawingState.Normal;
				}
			}
			else if (State==State.Terminated)
				Dispose();
		}
	}
}