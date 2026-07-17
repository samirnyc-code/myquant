// MzPackInspector — reflection dump of MzPack's loaded types + their OWN members, to see
// what mzFootprint exposes PUBLICLY (readable free from our own NinjaScript) vs what's
// gated behind the paid StrategyFootprintIndicator API — and whether the DLL is obfuscated
// (mangled member names => reflection not viable). Legitimate TYPE introspection to inform
// the buy/skip decision; it does NOT read live footprint data.
//
// Install: apply **mzFootprint to an ES chart FIRST** (so the MzPack assembly is loaded),
// THEN apply this indicator to the same chart. It writes data\mzpack_inspect.csv once.
// RULE (CLAUDE.md): lives in nt8/ and stays committed.
//
// Read the CSV: look for a Type like mzFootprint / IFootprintBar / StrategyFootprintIndicator
// with members Delta / Imbalances / FootprintBars / POC. If those are Access=public -> we can
// read them free. If Access=nonpublic (or names are mangled like a/b/x1) -> paid API needed.

#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Linq;
using System.Reflection;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MzPackInspector : Indicator
    {
        private bool done = false;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "MzPackInspector";
                Description = "Reflection dump of MzPack types/members -> CSV (API-surface diagnostic)";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                ExportPath = @"C:\Users\Admin\myquant\data\mzpack_inspect.csv";
            }
        }

        protected override void OnBarUpdate()
        {
            if (done || CurrentBar < 0) return;
            done = true;
            try { Dump(); Log("MzPackInspector wrote " + ExportPath, LogLevel.Information); }
            catch (Exception e) { Log("MzPackInspector failed: " + e.Message, LogLevel.Error); }
        }

        private void Dump()
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
            Directory.CreateDirectory(Path.GetDirectoryName(ExportPath));
            using (var w = new StreamWriter(ExportPath, false))
            {
                w.WriteLine("Assembly,Type,Kind,Member,MemberType,Access");
                int typeCount = 0;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type[] types;
                    try { types = asm.GetTypes(); }
                    catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray(); }
                    catch { continue; }

                    foreach (var t in types)
                    {
                        if (t == null) continue;
                        string tag = ((t.Namespace ?? "") + "." + t.Name);
                        if (tag.IndexOf("mz", StringComparison.OrdinalIgnoreCase) < 0 &&
                            tag.IndexOf("footprint", StringComparison.OrdinalIgnoreCase) < 0)
                            continue;
                        typeCount++;
                        string a = asm.GetName().Name;

                        foreach (var p in t.GetProperties(flags))
                        {
                            if (p.DeclaringType != t) continue;   // MzPack's OWN members only
                            w.WriteLine(Row(a, t.FullName, "Property", p.Name, Safe(() => p.PropertyType.Name),
                                (p.GetGetMethod(true) != null && p.GetGetMethod(true).IsPublic) ? "public" : "nonpublic"));
                        }
                        foreach (var f in t.GetFields(flags))
                        {
                            if (f.DeclaringType != t) continue;
                            w.WriteLine(Row(a, t.FullName, "Field", f.Name, Safe(() => f.FieldType.Name),
                                f.IsPublic ? "public" : "nonpublic"));
                        }
                        foreach (var m in t.GetMethods(flags))
                        {
                            if (m.DeclaringType != t || m.IsSpecialName) continue;  // skip prop accessors
                            w.WriteLine(Row(a, t.FullName, "Method", m.Name, Safe(() => m.ReturnType.Name),
                                m.IsPublic ? "public" : "nonpublic"));
                        }
                    }
                }
                w.WriteLine(Row("--", "SUMMARY", "types_matched", typeCount.ToString(), "", ""));
            }
        }

        private static string Safe(Func<string> f) { try { return f(); } catch { return "?"; } }

        private string Row(params string[] c)
        {
            return string.Join(",", c.Select(x => "\"" + (x ?? "").Replace("\"", "'") + "\""));
        }

        [NinjaScriptProperty]
        [Display(Name = "ExportPath", GroupName = "Parameters", Order = 0)]
        public string ExportPath { get; set; }
    }
}
