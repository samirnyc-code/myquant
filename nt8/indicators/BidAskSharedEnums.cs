// BidAskSharedEnums.cs — [NinjaScriptProperty]-typed enums shared by BidAskVolumeRatio.cs,
// CumulativeDelta.cs, and CVDDivergenceOscillator.cs, kept in their OWN standalone file
// rather than prepended as a second namespace block inside each indicator's own .cs file.
// Name predates CvdCumulativeMode joining it (2026-10-19) — kept as-is rather than renamed,
// since renaming would mean re-deploying + removing the old filename from Custom for no
// functional benefit (NT8 compiles the whole Custom tree together regardless of filename).
//
// WHY A SEPARATE FILE (2026-10-19, learned the hard way): a [NinjaScriptProperty] enum must
// live in the NinjaTrader.NinjaScript namespace (the common ancestor of .Indicators,
// .MarketAnalyzerColumns, .Strategies) or NT8's own generated wrapper code in those sibling
// namespaces throws CS0246 — that part was already known (see SessionSRLevelsV9.cs's
// LevelLineStyle, CVDDivergenceOscillator.cs's CvdCumulativeMode). What was NOT known until
// today: putting that enum in a SECOND `namespace NinjaTrader.NinjaScript { }` block
// PREPENDED to the SAME file as the indicator class breaks something ELSE — NT8's generator
// writes its convenience-constructor wrapper code with a relative `My.ClassName` prefix
// (confirmed via diff against MyWedge.cs / SessionSRLevelsV10.cs, both single-namespace-
// block files, both correctly prefixed) ONLY when the file has exactly one top-level
// namespace block; with two, it emits the BARE class name instead, which can't resolve from
// `namespace NinjaTrader.NinjaScript.Indicators` (a sibling-but-not-ancestor of `.Indicators.My`,
// where the class actually lives) — a second, different CS0246, this time "type ... does not
// exist in the namespace 'NinjaTrader.NinjaScript.Indicators'". Hit this exact error on
// BidAskVolumeRatio.cs/CumulativeDelta.cs after the first fix (moving each enum into its own
// file's second namespace block) looked right locally but failed on the user's actual F5.
// Fix: ONE namespace block per indicator file, enums factored out here instead.
//
// RULE (CLAUDE.md): this .cs lives in nt8/ and stays committed.

namespace NinjaTrader.NinjaScript
{
    public enum BavrDiffMethod { AskMinusBid, BidMinusAsk }                                  // BidAskVolumeRatio.cs
    public enum BavrMaType { Simple, Exponential, Weighted, LinearRegression, Wilders, Smoothed }   // BidAskVolumeRatio.cs
    public enum CvdResetMode { Session, None }                                               // CumulativeDelta.cs
    public enum CvdCumulativeMode { Periodic, EMA }                                          // CVDDivergenceOscillator.cs
}
