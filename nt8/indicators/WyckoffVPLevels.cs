// WyckoffVPLevels.cs — draws the Stage-1 LOCATION lane on the ES chart.
// S120-wyckoff. Reads the levels + full distribution that scripts/volume_profile.py computes
// from OUR tick troves (tick-accurate, composite-capable, with naked VPOCs across days) and
// renders them:
//   VPOC (red) · Value Area hi/lo (green, shaded band) · bias HVN (purple) · HVN (green) ·
//   LVN (orange) · naked VPOCs (blue, date-labelled) · optional FULL volume-at-price histogram.
//
// WHY a file-fed drawer (not compute-on-chart): the Python engine reads the raw tick trove,
// so the profile is exact and can span many sessions / find prior-session naked VPOCs — things
// a chart-bars profile can't. The engine writes two stable files this indicator watches:
//   data\vp_levels\current.csv          type,price,label   (VPOC/VAH/VAL/BIAS/HVN/LVN/NVP)
//   data\vp_levels\current_profile.csv  price,volume       (the whole distribution)
// Re-run volume_profile.py and the chart updates on the next render (mtime-watched).
//
// Labels are de-collided into 3 right-side columns with leader lines — text never overlaps a
// line or another label (HARD rule chart-label-no-overlap), same pattern as PATsProfile.
//
// RULE (CLAUDE.md): lives in nt8/ committed. Deploy to Documents\...\Custom\Indicators\ then F5.
// ⚠ OnRender/SharpDX errors are NOT caught by nt8_compile_check — F5 is the real test.

#region Using declarations
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class WyckoffVPLevels : Indicator
    {
        private string levelsPath = @"C:\Users\Admin\myquant\data\vp_levels\current.csv";
        private string profilePath = @"C:\Users\Admin\myquant\data\vp_levels\current_profile.csv";

        private class Level { public string type; public double price; public string label; }
        private class Lbl { public float y; public float trueY; public string text; public SolidColorBrush brush; public int col; }

        private List<Level> levels = new List<Level>();
        private double[] profPrice = new double[0];
        private double[] profVol = new double[0];
        private double profMax = 0;
        private DateTime lvlStamp = DateTime.MinValue, profStamp = DateTime.MinValue;

        #region Parameters
        [NinjaScriptProperty] [Display(Name = "Show level lines", Order = 0, GroupName = "1 Display")]
        public bool ShowLevels { get; set; }
        [NinjaScriptProperty] [Display(Name = "Show labels", Order = 1, GroupName = "1 Display")]
        public bool ShowLabels { get; set; }
        [NinjaScriptProperty] [Display(Name = "Show naked VPOCs", Order = 2, GroupName = "1 Display")]
        public bool ShowNaked { get; set; }
        [NinjaScriptProperty] [Display(Name = "Show FULL profile histogram", Order = 3, GroupName = "1 Display")]
        public bool ShowProfile { get; set; }
        [NinjaScriptProperty] [Range(20, 600)] [Display(Name = "Profile width (px)", Order = 4, GroupName = "1 Display")]
        public int ProfileWidthPx { get; set; }
        [NinjaScriptProperty] [Range(1, 20)] [Display(Name = "Label font size", Order = 5, GroupName = "1 Display")]
        public int LabelFontSize { get; set; }
        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "WyckoffVPLevels";
                Description = "Draws trove-computed Volume Profile levels (VPOC/VA/HVN/LVN/naked) + optional full histogram from volume_profile.py.";
                IsOverlay = true;
                IsChartOnly = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                ShowLevels = true; ShowLabels = true; ShowNaked = true; ShowProfile = false;
                ProfileWidthPx = 140; LabelFontSize = 11;
            }
        }

        // ---- file load (mtime-watched; cheap no-op when unchanged) ----
        private void Reload()
        {
            try
            {
                if (File.Exists(levelsPath))
                {
                    DateTime t = File.GetLastWriteTimeUtc(levelsPath);
                    if (t != lvlStamp)
                    {
                        lvlStamp = t;
                        var list = new List<Level>();
                        foreach (string line in File.ReadAllLines(levelsPath))
                        {
                            string[] p = line.Split(',');
                            if (p.Length < 2 || p[0] == "type") continue;
                            double px;
                            if (!double.TryParse(p[1], NumberStyles.Any, CultureInfo.InvariantCulture, out px)) continue;
                            list.Add(new Level { type = p[0], price = px, label = p.Length > 2 ? p[2] : "" });
                        }
                        levels = list;
                    }
                }
                if (ShowProfile && File.Exists(profilePath))
                {
                    DateTime t = File.GetLastWriteTimeUtc(profilePath);
                    if (t != profStamp)
                    {
                        profStamp = t;
                        var pr = new List<double>(); var vo = new List<double>(); double mx = 0;
                        foreach (string line in File.ReadAllLines(profilePath))
                        {
                            string[] p = line.Split(',');
                            if (p.Length < 2 || p[0] == "price") continue;
                            double px, v;
                            if (!double.TryParse(p[0], NumberStyles.Any, CultureInfo.InvariantCulture, out px)) continue;
                            if (!double.TryParse(p[1], NumberStyles.Any, CultureInfo.InvariantCulture, out v)) continue;
                            pr.Add(px); vo.Add(v); if (v > mx) mx = v;
                        }
                        profPrice = pr.ToArray(); profVol = vo.ToArray(); profMax = mx;
                    }
                }
            }
            catch { /* a half-written file this render; next render re-reads */ }
        }

        protected override void OnBarUpdate() { }

        private static Color4 C(float r, float g, float b, float a) { return new Color4(r, g, b, a); }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (RenderTarget == null || ChartPanel == null) return;
            Reload();
            if (levels.Count == 0 && (profPrice.Length == 0 || !ShowProfile)) return;

            float panelLeft = (float)ChartPanel.X;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);

            var vpocBr  = new SolidColorBrush(RenderTarget, C(0.89f, 0.31f, 0.31f, 0.95f));  // red
            var vaBr    = new SolidColorBrush(RenderTarget, C(0.33f, 0.64f, 0.29f, 0.90f));  // green
            var vaBand  = new SolidColorBrush(RenderTarget, C(0.33f, 0.64f, 0.29f, 0.10f));
            var biasBr  = new SolidColorBrush(RenderTarget, C(0.62f, 0.31f, 0.87f, 0.95f));  // purple
            var hvnBr   = new SolidColorBrush(RenderTarget, C(0.33f, 0.64f, 0.29f, 0.55f));  // faint green
            var lvnBr   = new SolidColorBrush(RenderTarget, C(0.96f, 0.52f, 0.09f, 0.75f));  // orange
            var nvpBr   = new SolidColorBrush(RenderTarget, C(0.20f, 0.45f, 0.90f, 0.90f));  // blue
            var profBr  = new SolidColorBrush(RenderTarget, C(0.30f, 0.47f, 0.66f, 0.22f));  // histogram
            var profVaBr= new SolidColorBrush(RenderTarget, C(0.30f, 0.47f, 0.66f, 0.40f));

            // value-area bounds (for band + histogram shading)
            double vah = double.NaN, val = double.NaN;
            foreach (Level L in levels) { if (L.type == "VAH") vah = L.price; else if (L.type == "VAL") val = L.price; }

            // ---- full histogram (optional), anchored at the left edge ----
            if (ShowProfile && profPrice.Length > 0 && profMax > 0)
            {
                float rowH = Math.Abs(chartScale.GetYByValue(0.0) - chartScale.GetYByValue(0.25));
                if (rowH < 1f) rowH = 1f;
                for (int i = 0; i < profPrice.Length; i++)
                {
                    float y = chartScale.GetYByValue(profPrice[i]);
                    float w = (float)(ProfileWidthPx * profVol[i] / profMax);
                    bool inva = !double.IsNaN(vah) && profPrice[i] >= val && profPrice[i] <= vah;
                    RenderTarget.FillRectangle(new RectangleF(panelLeft, y - rowH / 2f, w, Math.Max(1f, rowH - 0.5f)),
                                               inva ? profVaBr : profBr);
                }
            }

            // ---- level lines + VA band ----
            if (ShowLevels)
            {
                if (!double.IsNaN(vah) && !double.IsNaN(val))
                {
                    float y1 = chartScale.GetYByValue(vah), y2 = chartScale.GetYByValue(val);
                    RenderTarget.FillRectangle(new RectangleF(panelLeft, Math.Min(y1, y2), panelRight - panelLeft, Math.Abs(y2 - y1)), vaBand);
                }
                foreach (Level L in levels)
                {
                    if (!ShowNaked && L.type == "NVP") continue;
                    SolidColorBrush br; float wdt = 1f;
                    switch (L.type)
                    {
                        case "VPOC": br = vpocBr; wdt = 2f; break;
                        case "VAH": case "VAL": br = vaBr; wdt = 1.2f; break;
                        case "BIAS": br = biasBr; wdt = 1.6f; break;
                        case "HVN": br = hvnBr; break;
                        case "LVN": br = lvnBr; break;
                        case "NVP": br = nvpBr; wdt = 1.2f; break;
                        default: continue;
                    }
                    float y = chartScale.GetYByValue(L.price);
                    RenderTarget.DrawLine(new Vector2(panelLeft, y), new Vector2(panelRight, y), br, wdt);
                }
            }

            // ---- de-collided labels (3 columns: key / nodes / naked) ----
            if (ShowLabels)
            {
                var labels = new List<Lbl>();
                foreach (Level L in levels)
                {
                    int col; SolidColorBrush br; string txt;
                    switch (L.type)
                    {
                        case "VPOC": col = 0; br = vpocBr; txt = "VPOC " + F(L.price); break;
                        case "VAH":  col = 0; br = vaBr;   txt = "VAH " + F(L.price); break;
                        case "VAL":  col = 0; br = vaBr;   txt = "VAL " + F(L.price); break;
                        case "BIAS": col = 0; br = biasBr; txt = "bias " + F(L.price); break;
                        case "HVN":  col = 1; br = hvnBr;  txt = "HVN " + F(L.price); break;
                        case "LVN":  col = 1; br = lvnBr;  txt = "LVN " + F(L.price); break;
                        case "NVP":  if (!ShowNaked) continue; col = 2; br = nvpBr; txt = "nVPOC " + F(L.price) + (L.label != "" ? " " + L.label : ""); break;
                        default: continue;
                    }
                    float y = chartScale.GetYByValue(L.price);
                    labels.Add(new Lbl { y = y, trueY = y, text = txt, brush = br, col = col });
                }
                DrawLabels(labels, panelRight - (LabelFontSize * 20f), panelRight);
            }

            vpocBr.Dispose(); vaBr.Dispose(); vaBand.Dispose(); biasBr.Dispose();
            hvnBr.Dispose(); lvnBr.Dispose(); nvpBr.Dispose(); profBr.Dispose(); profVaBr.Dispose();
        }

        private void DrawLabels(List<Lbl> labels, float baseX, float rightEdge)
        {
            if (labels.Count == 0) return;
            float colW = LabelFontSize * 6.5f;
            float gap = LabelFontSize + 4f;
            TextFormat tf = new TextFormat(NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", LabelFontSize);
            for (int c = 0; c <= 2; c++)
            {
                var col = new List<Lbl>();
                foreach (Lbl L in labels) if (L.col == c) col.Add(L);
                if (col.Count == 0) continue;
                col.Sort(delegate (Lbl a, Lbl b) { return a.y.CompareTo(b.y); });
                for (int i = 1; i < col.Count; i++)
                    if (col[i].y < col[i - 1].y + gap) col[i].y = col[i - 1].y + gap;
                float x = baseX + c * colW;
                foreach (Lbl L in col)
                {
                    if (Math.Abs(L.y - L.trueY) > 1.5f)
                        RenderTarget.DrawLine(new Vector2(x - 6f, L.trueY), new Vector2(x - 1f, L.y + LabelFontSize * 0.5f), L.brush, 0.6f);
                    RenderTarget.DrawText(L.text, tf, new RectangleF(x, L.y, colW, LabelFontSize + 6f), L.brush);
                }
            }
            tf.Dispose();
        }

        private static string F(double p) { return p.ToString("0.##", CultureInfo.InvariantCulture); }
    }
}
