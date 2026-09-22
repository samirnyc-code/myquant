WT = r"C:/Users/Admin/myquant-regime/nt8/indicators/RegimePhaseMachine.cs"
s = open(WT, encoding="utf-8").read()
orig = s
def rep(old, new, s):
    assert s.count(old) == 1, "anchor not unique/found:\n" + old[:80]
    return s.replace(old, new)
s = rep("\t\tprivate System.IO.StreamWriter tlog;",
        "\t\tprivate System.IO.StreamWriter tlog;\n\t\tprivate System.IO.StreamWriter mlog;\n\t\tprivate DateTime marksDay = DateTime.MinValue;", s)
tlog_method = ('\t\tprivate void TLog(string evt, int b, double px)\n\t\t{\n'
 '\t\t\tif (tlog == null) return;\n'
 '\t\t\ttry { tlog.WriteLine(string.Format(System.Globalization.CultureInfo.InvariantCulture,\n'
 '\t\t\t\t"{0:yyyy-MM-dd HH:mm:ss},{1},{2},{3},{4:F2}", Time[0], b + 1, evt, mode, px)); tlog.Flush(); }\n'
 '\t\t\tcatch { }\n\t\t}')
dump_method = ('\n\n\t\tprivate void DumpMarks()\n\t\t{\n'
 '\t\t\tif (mlog == null || piv == null || piv.Count == 0 || marksDay == DateTime.MinValue) return;\n'
 '\t\t\ttry {\n'
 '\t\t\t\tstring ds = marksDay.ToString("yyyy-MM-dd");\n'
 '\t\t\t\tforeach (Piv p in piv)\n'
 '\t\t\t\t\tmlog.WriteLine(string.Format(System.Globalization.CultureInfo.InvariantCulture,\n'
 '\t\t\t\t\t\t"{0},{1},pivot,{2},{3},{4},{5},{6}", ds, p.Bar + 1,\n'
 '\t\t\t\t\t\tp.IsH ? "H" : "L", p.Tag, p.Disp, p.Major ? 1 : 0, p.MajLab ?? ""));\n'
 '\t\t\t\tmlog.Flush();\n\t\t\t} catch { }\n\t\t}')
s = rep(tlog_method, tlog_method + dump_method, s)
s = rep('\t\t\t\t\ttlog.WriteLine("time,bar,event,mode,px");\n\t\t\t\t}\n\t\t\t\tcatch { tlog = null; }',
        '\t\t\t\t\ttlog.WriteLine("time,bar,event,mode,px");\n'
        '\t\t\t\t\tmlog = new System.IO.StreamWriter(\n'
        '\t\t\t\t\t\t@"C:\\Users\\Admin\\myquant\\data\\regime\\nt8_marks.csv", false);\n'
        '\t\t\t\t\tmlog.WriteLine("date,bar,event,side,minor_tag,disp,is_major,major_lab");\n'
        '\t\t\t\t}\n\t\t\t\tcatch { tlog = null; mlog = null; }', s)
s = rep('\t\t\t\tif (tlog != null) { try { tlog.Close(); } catch { } tlog = null; }',
        '\t\t\t\tDumpMarks();\n'
        '\t\t\t\tif (tlog != null) { try { tlog.Close(); } catch { } tlog = null; }\n'
        '\t\t\t\tif (mlog != null) { try { mlog.Close(); } catch { } mlog = null; }', s)
s = rep('\t\t\t\tsessHigh = double.MinValue; sessLow = double.MaxValue;\n\t\t\t\tResetDay();\n\t\t\t\tTLog("RESET", -1, Close[0]);',
        '\t\t\t\tDumpMarks();\n'
        '\t\t\t\tsessHigh = double.MinValue; sessLow = double.MaxValue;\n\t\t\t\tResetDay();\n\t\t\t\tTLog("RESET", -1, Close[0]);', s)
s = rep('\t\t\t\tsessionIt.GetNextSession(Time[0], true);',
        '\t\t\t\tsessionIt.GetNextSession(Time[0], true);\n\t\t\t\tmarksDay = sessionIt.ActualSessionBegin.Date;', s)
assert s != orig
open(WT, "w", encoding="utf-8", newline="").write(s)
print("PATCHED worktree source OK")
