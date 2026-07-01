#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.Indicators.My;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public enum StopMode    { ChanExtreme, SwingPoint, ABR, SignalBar, WeakReversalBar }
    public enum TargetMode  { ChanExtreme, RHalf, RThreeQuarter, ROne, ROneHalf, RTwo, RTwoHalf, RThree }
	
    public enum CancelMode  { ClosesOutsideExtreme, BarsAfterBreak, PctOfChannel }

    [Gui.CategoryOrder("Setup",                   1)]
    [Gui.CategoryOrder("Strategy",                2)]
    [Gui.CategoryOrder("Session",                 3)]
    [Gui.CategoryOrder("Risk Guard",              4)]
    [Gui.CategoryOrder("Cancel Watch",            5)]
    [Gui.CategoryOrder("Entry - PB33",            6)]
    [Gui.CategoryOrder("Entry - PB50",            7)]
    [Gui.CategoryOrder("Entry - PB66",            8)]
    [Gui.CategoryOrder("Entry - BO XTR",          9)]
    [Gui.CategoryOrder("Entry - BO INT",          10)]
    [Gui.CategoryOrder("Entry - BB MC / SA MC",   11)]
    [Gui.CategoryOrder("Entry - Lmt Buy L / Lmt Sell H", 12)]
    [Gui.CategoryOrder("Entry - SE",              13)]
    [Gui.CategoryOrder("Entry - Speedo",          14)]
    [Gui.CategoryOrder("Indicator",               15)]
    [Gui.CategoryOrder("Chart Trader Buttons",    16)]
    [Gui.CategoryOrder("CSV",                     17)]
    public class MCStrategyDashboardV3 : Strategy
    {
        // ── ATM IDs per leg — PB ─────────────────────────────────────────────
        private string atmIdL33 = string.Empty;
        private string atmIdL50 = string.Empty;
        private string atmIdL66 = string.Empty;
        private string atmIdS33 = string.Empty;
        private string atmIdS50 = string.Empty;
        private string atmIdS66 = string.Empty;

        // ── Order IDs per leg — PB ────────────────────────────────────────────
        private string ordIdL33 = string.Empty;
        private string ordIdL50 = string.Empty;
        private string ordIdL66 = string.Empty;
        private string ordIdS33 = string.Empty;
        private string ordIdS50 = string.Empty;
        private string ordIdS66 = string.Empty;

        // ── Active tracking — PB ──────────────────────────────────────────────
        private bool l33Active, l50Active, l66Active;
        private bool s33Active, s50Active, s66Active;
        private bool longOrdersPlaced, shortOrdersPlaced;

        // ── Per-leg stop/target prices — PB ──────────────────────────────────
        private double stopL33, stopL50, stopL66;
        private double stopS33, stopS50, stopS66;
        private double targetL33, targetL50, targetL66;
        private double targetS33, targetS50, targetS66;

        // ── Stop/target set flags — PB ────────────────────────────────────────
        private bool l33StopTargetSet, l50StopTargetSet, l66StopTargetSet;
        private bool s33StopTargetSet, s50StopTargetSet, s66StopTargetSet;

        // ── Stop/target print flags — PB ──────────────────────────────────────
        private bool l33StopTargetPrinted, l50StopTargetPrinted, l66StopTargetPrinted;
        private bool s33StopTargetPrinted, s50StopTargetPrinted, s66StopTargetPrinted;

        // ── Callback confirmed flags — PB ─────────────────────────────────────
        private bool l33CallbackOK, l50CallbackOK, l66CallbackOK;
        private bool s33CallbackOK, s50CallbackOK, s66CallbackOK;

        // ── Stop/target calc strings — PB ─────────────────────────────────────
        private string l33StopCalc = "", l50StopCalc = "", l66StopCalc = "";
        private string l33TgtCalc  = "", l50TgtCalc  = "", l66TgtCalc  = "";
        private string s33StopCalc = "", s50StopCalc = "", s66StopCalc = "";
        private string s33TgtCalc  = "", s50TgtCalc  = "", s66TgtCalc  = "";

        // ── Last sent entry prices — PB ───────────────────────────────────────
        private double lastSentL33, lastSentL50, lastSentL66;
        private double lastSentS33, lastSentS50, lastSentS66;

        // ── Stored entry prices — PB ──────────────────────────────────────────
        private double entryL33, entryL50, entryL66;
        private double entryS33, entryS50, entryS66;

        // ── ATM IDs / Order IDs — BB MC / SA MC ──────────────────────────────
        private string atmIdBBMC  = string.Empty, ordIdBBMC  = string.Empty;
        private string atmIdSAMC  = string.Empty, ordIdSAMC  = string.Empty;

        // ── State — BB MC / SA MC ─────────────────────────────────────────────
        private bool   bbMCActive,  bbMCFilled,  bbMCCallbackOK;
        private bool   saMCActive,  saMCFilled,  saMCCallbackOK;
        private double stopBBMC,    targetBBMC,  entryBBMC,  lastSentBBMC;
        private double stopSAMC,    targetSAMC,  entrySAMC,  lastSentSAMC;
        private string bbMCStopCalc = "", bbMCTgtCalc = "";
        private string saMCStopCalc = "", saMCTgtCalc = "";

        // ── ATM IDs / Order IDs — BO XTR ─────────────────────────────────────
        private string atmIdBOXTR = string.Empty, ordIdBOXTR = string.Empty;

        // ── State — BO XTR ────────────────────────────────────────────────────
        private bool   boXTRActive, boXTRFilled, boXTRCallbackOK, boXTRIsLong;
        private double stopBOXTR, targetBOXTR, entryBOXTR;
        private double boXTRChanHigh, boXTRChanLow;
        private double boXTRLastChanLowLong = 0, boXTRLastChanHighShort = 0;
        private string boXTRStopCalc = "", boXTRTgtCalc = "";

       // ── Multi-order tracking — BB BL (Lmt Buy L) ─────────────────────────
        private List<string> atmIdsBBBL    = new List<string>();
        private List<string> ordIdsBBBL    = new List<string>();
        private List<double> stopsBBBL     = new List<double>();
        private List<double> targetsBBBL   = new List<double>();
        private List<double> entriesBBBL   = new List<double>();
        private List<bool>   filledBBBL    = new List<bool>();
        private List<bool>   callbackBBBL  = new List<bool>();
        private List<string> stopCalcsBBBL = new List<string>();
        private List<string> tgtCalcsBBBL  = new List<string>();
        private List<int>    barsAgoBBBL   = new List<int>();
        private List<bool>   inMCBBBL      = new List<bool>();

        // ── State — BB BL button ──────────────────────────────────────────────
        private bool   bbBLArmed, bbBLWaitingClick;
        private double bbBLLimitPrice;
        private int    bbBLClickedBarsAgo = -1;
        private bool   bbBLInitiatedInMC;

        // ── Multi-order tracking — SA BR (Lmt Sell H) ────────────────────────
        private List<string> atmIdsSABR    = new List<string>();
        private List<string> ordIdsSABR    = new List<string>();
        private List<double> stopsSABR     = new List<double>();
        private List<double> targetsSABR   = new List<double>();
        private List<double> entriesSABR   = new List<double>();
        private List<bool>   filledSABR    = new List<bool>();
        private List<bool>   callbackSABR  = new List<bool>();
        private List<string> stopCalcsSABR = new List<string>();
        private List<string> tgtCalcsSABR  = new List<string>();
        private List<int>    barsAgoSABR   = new List<int>();
        private List<bool>   inMCSABR      = new List<bool>();

        // ── State — SA BR button ──────────────────────────────────────────────
        private bool   saBRArmed, saBRWaitingClick;
        private double saBRLimitPrice;
        private int    saBRClickedBarsAgo = -1;
        private bool   saBRInitiatedInMC;

        // ── Multi-order tracking — SE L ───────────────────────────────────────
        private List<string> atmIdsSEL    = new List<string>();
        private List<string> ordIdsSEL    = new List<string>();
        private List<double> stopsSEL     = new List<double>();
        private List<double> targetsSEL   = new List<double>();
        private List<double> entriesSEL   = new List<double>();
        private List<bool>   filledSEL    = new List<bool>();
        private List<bool>   callbackSEL  = new List<bool>();
        private List<string> stopCalcsSEL = new List<string>();
        private List<string> tgtCalcsSEL  = new List<string>();

        // ── State — SE L button ───────────────────────────────────────────────
        private bool   seLArmed, seLWaitingClick;
        private double seLLimitPrice;
        private int    seLClickedBarsAgo = -1;
        private bool   seLInitiatedInMC;
        private Button btnSEOrderType = null;
        private Button btnSEOrderType2 = null;

        // ── Multi-order tracking — SE S ───────────────────────────────────────
        private List<string> atmIdsSES    = new List<string>();
        private List<string> ordIdsSES    = new List<string>();
        private List<double> stopsSES     = new List<double>();
        private List<double> targetsSES   = new List<double>();
        private List<double> entriesSES   = new List<double>();
        private List<bool>   filledSES    = new List<bool>();
        private List<bool>   callbackSES  = new List<bool>();
        private List<string> stopCalcsSES = new List<string>();
        private List<string> tgtCalcsSES  = new List<string>();

        // ── State — SE S button ───────────────────────────────────────────────
        private bool   seSArmed, seSWaitingClick;
        private double seSLimitPrice;
        private int    seSClickedBarsAgo = -1;
        private bool   seSInitiatedInMC;

        // ── ATM IDs / Order IDs — Speedo ─────────────────────────────────────
        private string atmIdSpeedo = string.Empty, ordIdSpeedo = string.Empty;

        // ── State — Speedo ────────────────────────────────────────────────────
        private bool   speedoArmed, speedoWaitingClick, speedoWaitingBar, speedoWaitingImpulseClose;
        private bool   speedoActive, speedoFilled, speedoCallbackOK;
        private bool   speedoIsLong;
        private bool   speedoInitiatedInMC;
       	private int    speedoImpulseBarIndex  = -1;
        private int    speedoReversalBarIndex = -1;
        private int    speedoOrderBarIndex    = -1;
        private double speedoImpulseHigh, speedoImpulseLow;
        private double speedoLimitPrice;
        private double stopSpeedo, targetSpeedo, entrySpeedo;
        private string speedoStopCalc = "", speedoTgtCalc = "";

      	private List<double> lastSwingLowsBBLSABR  = new List<double>();
		private List<double> lastSwingHighsBBLSABR = new List<double>();
		private List<double> lastSwingLowsSE       = new List<double>();
		private List<double> lastSwingHighsSE      = new List<double>();
		private List<double> lastSwingLowsSpeedo   = new List<double>();
		private List<double> lastSwingHighsSpeedo  = new List<double>();

        // ── Mouse hook guard ──────────────────────────────────────────────────
        private bool   chartMouseHooked = false;

        // ── Session iterator (for bar-click slot→barsAgo) ─────────────────────
        private NinjaTrader.Data.SessionIterator sessionIterator = null;

        // ── Channel levels ────────────────────────────────────────────────────
        private double activeChanHighLong,  activeChanLowLong;
        private double activeChanHighShort, activeChanLowShort;
        private double activePB33Long, activePB50Long, activePB66Long;
        private double activePB33Short, activePB50Short, activePB66Short;
        private int    activeChanBarsLong  = 0;
        private int    activeChanBarsShort = 0;

        // ── Cached swing indicators — PB ──────────────────────────────────────
        private NinjaTrader.NinjaScript.Indicators.Swing swingPB33    = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingPB50    = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingPB66    = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingBOXTR   = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingBOINT   = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingBBSAMC  = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingBBLSABR = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingSE      = null;
        private NinjaTrader.NinjaScript.Indicators.Swing swingSpeedo  = null;

        // ── Counters ──────────────────────────────────────────────────────────
        private int    longChannelCounter, shortChannelCounter;
        private double prevBullBarNo = 999, prevBearBarNo = 999;
        private bool   isRealtime      = false;
		private bool   testFired       = false;
		private bool   backfillMCDone  = false;

        // ── Session ───────────────────────────────────────────────────────────
        private DateTime lastSessionDate = DateTime.MinValue;

        // ── Cancel Watch state ────────────────────────────────────────────────
		private double cancelWatchHighLong  = 0;
		private double cancelWatchLowShort  = 0;
		private int    closesOutsideLongCount  = 0;
		private int    closesOutsideShortCount = 0;
		private bool   cancelWatchLockedLong  = false;
		private bool   cancelWatchLockedShort = false;

       // ── Multi-order tracking — Lmt Buy ────────────────────────────────────────
        private List<string> atmIdsLmtBuy    = new List<string>();
        private List<string> ordIdsLmtBuy    = new List<string>();
        private List<double> stopsLmtBuy     = new List<double>();
        private List<double> targetsLmtBuy   = new List<double>();
        private List<double> entriesLmtBuy   = new List<double>();
        private List<bool>   filledLmtBuy    = new List<bool>();
        private List<bool>   callbackLmtBuy  = new List<bool>();
        private List<string> stopCalcsLmtBuy = new List<string>();
        private List<string> tgtCalcsLmtBuy  = new List<string>();

        // ── Multi-order tracking — Lmt Sell ───────────────────────────────────────
        private List<string> atmIdsLmtSell    = new List<string>();
        private List<string> ordIdsLmtSell    = new List<string>();
        private List<double> stopsLmtSell     = new List<double>();
        private List<double> targetsLmtSell   = new List<double>();
        private List<double> entriesLmtSell   = new List<double>();
        private List<bool>   filledLmtSell    = new List<bool>();
        private List<bool>   callbackLmtSell  = new List<bool>();
        private List<string> stopCalcsLmtSell = new List<string>();
        private List<string> tgtCalcsLmtSell  = new List<string>();

        // ── Lmt Buy / Lmt Sell state ──────────────────────────────────────────────
        private bool   lmtBuyWaitingClick  = false;
        private bool   lmtSellWaitingClick = false;
        private Button btnLmtBuy           = null;
        private Button btnLmtSell          = null;
        private Button btnLmtBuyStpCycle   = null, btnLmtBuyTgtCycle  = null;
        private Button btnLmtBuyStpOfs     = null, btnLmtBuyTgtOfs    = null;
        private Button btnLmtSellStpCycle  = null, btnLmtSellTgtCycle = null;
        private Button btnLmtSellStpOfs    = null, btnLmtSellTgtOfs   = null;

       // ── Exit source tracking ──────────────────────────────────────────────────
		private string lastExitSource = "ATM";
		
		// ── Actual exit fill prices per leg ──────────────────────────────────────
		private double exitPriceL33, exitPriceL50, exitPriceL66;
		private double exitPriceS33, exitPriceS50, exitPriceS66;
		private double exitPriceBBMC, exitPriceSAMC;
		private double exitPriceSpeedo;
		private string exitTypeBBMC, exitTypeSAMC;
		private string exitTypeSpeedo;
		private string exitTypeL33, exitTypeL50, exitTypeL66;
		private string exitTypeS33, exitTypeS50, exitTypeS66;

        // ── Button panel ──────────────────────────────────────────────────────
        private Grid   ctButtonsGrid  = null;
        private bool   ctPanelActive  = false;
        private int    ctRowsAdded    = 0;
        private int    ctBaseRowCount = 0;

        private Button btnMCStrategy  = null;
        private bool   mcStrategyOn   = true;
        private Button btnAllPBs      = null;
        private bool   allPBsArmed    = false;
        private Button btnPB33        = null;
        private Button btnPB50        = null;
        private Button btnPB66        = null;
        private Button btnBOXTR       = null;
        private Button btnBOINT       = null;
        private Button btnCTGuard     = null;
        private bool   ctGuardOn         = false;
		private bool   pendingPBPlacement = false;
        private Button btnBBMC        = null;
        private Button btnSAMC        = null;
        private Button btnBBBL        = null;
        private Button btnSABR        = null;
        private Button btnSEL         = null;
        private Button btnSES         = null;
        private Button btnSpeedo      = null;
        private Button btnFlat        = null;
        private Button btnBE          = null;
        private Button btnCancel      = null;

        // ── Sub-row buttons — PB33 ────────────────────────────────────────────
        private Button btnPB33Ofs = null, btnPB33StpMode = null, btnPB33TgtMode = null;
        private Button btnPB33StpOfs = null, btnPB33TgtOfs = null;

        // ── Sub-row buttons — PB50 ────────────────────────────────────────────
        private Button btnPB50Ofs = null, btnPB50StpMode = null, btnPB50TgtMode = null;
        private Button btnPB50StpOfs = null, btnPB50TgtOfs = null;

        // ── Sub-row buttons — PB66 ────────────────────────────────────────────
        private Button btnPB66Ofs = null, btnPB66StpMode = null, btnPB66TgtMode = null;
        private Button btnPB66StpOfs = null, btnPB66TgtOfs = null;

        // ── Sub-row buttons — BB MC ───────────────────────────────────────────
        private Button btnBBMCOfs = null, btnBBMCStpCycle = null, btnBBMCTgtCycle = null;
        private Button btnBBMCStpOfs = null, btnBBMCTgtOfs = null;

        // ── Sub-row buttons — SA MC ───────────────────────────────────────────
        private Button btnSAMCOfs = null, btnSAMCStpCycle = null, btnSAMCTgtCycle = null;
        private Button btnSAMCStpOfs = null, btnSAMCTgtOfs = null;

        // ── Sub-row buttons — BB BL ───────────────────────────────────────────
        private Button btnBBBLOfs = null, btnBBBLStpCycle = null, btnBBBLTgtCycle = null;
        private Button btnBBBLStpOfs = null, btnBBBLTgtOfs = null;

        // ── Sub-row buttons — SA BR ───────────────────────────────────────────
        private Button btnSABROfs = null, btnSABRStpCycle = null, btnSABRTgtCycle = null;
        private Button btnSABRStpOfs = null, btnSABRTgtOfs = null;

        // ── Sub-row buttons — SE L ────────────────────────────────────────────
        private Button btnSELOfs = null, btnSELStpCycle = null, btnSELTgtCycle = null;
        private Button btnSELStpOfs = null, btnSELTgtOfs = null;

        // ── Sub-row buttons — SE S ────────────────────────────────────────────
        private Button btnSESOfs = null, btnSESStpCycle = null, btnSESTgtCycle = null;
        private Button btnSESStpOfs = null, btnSESTgtOfs = null;

        // ── Sub-row buttons — Speedo ──────────────────────────────────────────
        private Button btnSpeedoOfs = null, btnSpeedoStpCycle = null, btnSpeedoTgtCycle = null;
        private Button btnSpeedoStpOfs = null, btnSpeedoTgtOfs = null;

        // ── Sub-button visibility ─────────────────────────────────────────────
        private bool   subButtonsVisible = false;   // default: hidden
        private Button btnSubToggle      = null;

        // ── All sub-buttons list for show/hide ────────────────────────────────
        private List<Button> allSubButtons = new List<Button>();

        // ── All sub-row containers (for height collapse) ──────────────────────
        private List<UIElement> allSubContainers = new List<UIElement>();

        // ── Button states ─────────────────────────────────────────────────────
        private enum BtnState3  { Off, Armed, Filled }
        private enum BtnState3G { Off, On,    Filled }

        private bool pb33Armed  = false, pb50Armed  = false, pb66Armed  = false;
        private bool pb33Filled = false, pb50Filled = false, pb66Filled = false;

        private BtnState3G boXtrState  = BtnState3G.Off;
        private BtnState3G boIntState  = BtnState3G.Off;
        private BtnState3  bbBLState   = BtnState3.Off;
        private BtnState3  saBRState   = BtnState3.Off;
        private BtnState3  seLState    = BtnState3.Off;
        private BtnState3  seSState    = BtnState3.Off;
        private BtnState3  speedoState = BtnState3.Off;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description         = "MC Strategy Dashboard V3";
				Name                = "MCStrategyDashboardV3";
                Calculate           = Calculate.OnBarClose;
                BarsRequiredToTrade = 1;
                StartBehavior       = StartBehavior.ImmediatelySubmit;
				MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;

                // Strategy
                TestMode         = false;
                AtmTemplateName  = "ATM_Test_1c";
                AutoReArm        = true;
                BECancelUnfilled = true;

                // Session
                UseTimeFilter = false;
                StartTime     = "09:30:00";
                EndTime       = "16:00:00";

                // Risk Guard
                MaxContracts                = 5;
                EnableMaxRiskDollars        = false;
                MaxRiskDollars              = 1500;
                EnableMaxChannelPoints      = false;
                MaxChannelPoints            = 20;
                EnableMaxChannelBars        = false;
                MaxChannelBars              = 20;
                EnableMaxChannelABRMultiple = false;
                MaxChannelABRMultiple       = 3.0;
                EnableADRFilter             = false;
                MaxChannelADRMultiple       = 0.5;

                // Cancel Watch
                EnableCancelWatch     = false;
                CancelWatchMode       = CancelMode.ClosesOutsideExtreme;
                CancelAfterBars       = 3;
                CancelPctOfChannel    = 25;
                ClosesOutsideToCancel = 1;

            // PB33
                UsePB33               = true;
                PB33EntryOffsetTicks  = 1;
                PB33StopMode          = StopMode.ChanExtreme;
                PB33StopOffsetTicks   = 1;
                PB33StopABRBars       = 8;
                PB33StopABRMultiple   = 1.0;
                PB33SwingStrength     = 3;
                PB33TargetMode        = TargetMode.ChanExtreme;
                PB33RMultiple         = 1.0;
                PB33TargetOffsetTicks = 1;

                // PB50
                UsePB50               = true;
                PB50EntryOffsetTicks  = 1;
                PB50StopMode          = StopMode.ChanExtreme;
                PB50StopOffsetTicks   = 1;
                PB50StopABRBars       = 8;
                PB50StopABRMultiple   = 1.0;
                PB50SwingStrength     = 3;
                PB50TargetMode        = TargetMode.ChanExtreme;
                PB50RMultiple         = 1.0;
                PB50TargetOffsetTicks = 1;

                // PB66
                UsePB66               = true;
                PB66EntryOffsetTicks  = 1;
                PB66StopMode          = StopMode.ChanExtreme;
                PB66StopOffsetTicks   = 1;
                PB66StopABRBars       = 8;
                PB66StopABRMultiple   = 1.0;
                PB66SwingStrength     = 3;
                PB66TargetMode        = TargetMode.ChanExtreme;
                PB66RMultiple         = 1.0;
                PB66TargetOffsetTicks = 1;

                // BO XTR
                UseBO_XTR                = false;
                BOXTR_EntryOffsetTicks   = 0;
                BOXTR_StopMode           = StopMode.ChanExtreme;
                BOXTR_StopOffsetTicks    = 1;
                BOXTR_StopABRBars        = 8;
                BOXTR_StopABRMultiple    = 1.0;
                BOXTR_SwingStrength      = 3;
                BOXTR_TargetMode         = TargetMode.ROne;
                BOXTR_RMultiple          = 1.0;
                BOXTR_TargetOffsetTicks  = 1;
                BOXTR_OrderType          = OrderType.StopLimit;
				
                // BO INT
                UseBO_INT                = false;
                BOINT_EntryOffsetTicks   = 0;
                BOINT_StopMode           = StopMode.ChanExtreme;
                BOINT_StopOffsetTicks    = 1;
                BOINT_StopABRBars        = 8;
                BOINT_StopABRMultiple    = 1.0;
                BOINT_SwingStrength      = 3;
                BOINT_TargetMode         = TargetMode.ChanExtreme;
                BOINT_RMultiple          = 1.0;
                BOINT_TargetOffsetTicks  = 1;

                // BB MC / SA MC
                UseBBMC                    = false;
                UseSAMC                    = false;
                BBSAMC_EntryOffsetTicks    = 0;
                BBSAMC_StopMode            = StopMode.ChanExtreme;
                BBSAMC_StopOffsetTicks     = 1;
                BBSAMC_StopABRBars         = 8;
                BBSAMC_StopABRMultiple     = 1.0;
                BBSAMC_SwingStrength       = 3;
                BBSAMC_TargetMode          = TargetMode.ChanExtreme;
                BBSAMC_RMultiple           = 1.0;
                BBSAMC_TargetOffsetTicks   = 1;
                BBSAMC_CTGuardEnabled      = false;

                // BB BL / SA BR
                UseBBBL                    = false;
                UseSABR                    = false;
                BBLSABR_EntryOffsetTicks   = 1;
                BBLSABR_StopMode           = StopMode.SwingPoint;
                BBLSABR_StopOffsetTicks    = 1;
                BBLSABR_StopABRBars        = 8;
                BBLSABR_StopABRMultiple    = 1.0;
                BBLSABR_SwingStrength      = 3;
                BBLSABR_TargetMode         = TargetMode.ROne;
                BBLSABR_RMultiple          = 1.0;
                BBLSABR_TargetOffsetTicks  = 1;
                BBLSABR_CTGuardEnabled     = false;

               // SE
                UseSEL                  = false;
                UseSES                  = false;
                SE_EntryOffsetTicks     = 1;
                SE_StopMode             = StopMode.SwingPoint;
                SE_StopOffsetTicks      = 1;
                SE_StopABRBars          = 8;
                SE_StopABRMultiple      = 1.0;
                SE_SwingStrength        = 3;
                SE_TargetMode           = TargetMode.ROne;
                SE_RMultiple            = 1.0;
                SE_TargetOffsetTicks    = 1;
                SE_CTGuardEnabled       = false;
                SE_OrderType            = OrderType.StopMarket;

                // Speedo
                UseSpeedo                   = false;
                Speedo_EntryOffsetTicks     = 1;
                Speedo_StopMode             = StopMode.WeakReversalBar;
                Speedo_StopOffsetTicks      = 1;
                Speedo_StopABRBars          = 8;
                Speedo_StopABRMultiple      = 1.0;
                Speedo_SwingStrength        = 3;
                Speedo_TargetMode           = TargetMode.ROne;
                Speedo_RMultiple            = 2.0;
                Speedo_TargetOffsetTicks    = 1;
                Speedo_CTGuardEnabled       = false;
                Speedo_AutoCancel           = false;

                // Indicator
                ContinueMC = false;
                Show0CC    = false;
                Show1CC    = true;
                Show2CC    = true;
                Show3CC    = true;
                Show4CC    = true;
                Show5CC    = true;
                ShowCX     = true;

                // Chart Trader Buttons
                ButtonFontSize   = 11;
                SubButtonFontSize = 9;
                LblMCStrategy    = "MC STRATEGY";
                LblPB33          = "PB33";
                LblPB50          = "PB50";
                LblPB66          = "PB66";
                LblBOXTR         = "BO XTR";
                LblBOINT         = "BO INT";
                LblBBMC          = "BB MC";
                LblSAMC          = "SA MC";
              	LblBBBL          = "Lmt Buy L";
				LblSABR          = "Lmt Sell H";
                LblLmtBuy        = "Lmt Buy";
                LblLmtSell       = "Lmt Sell";
                LblSEL           = "SE L";
                LblSES           = "SE S";
                LblSpeedo        = "SPEEDO";
                LblFlat          = "FLAT";
                LblBE            = "BE";
                LblCancel        = "CANCEL ALL";
                ColorStrategyOn  = Color.FromRgb(0,   160, 0);
                ColorStrategyOff = Color.FromRgb(80,  80,  80);
                ColorArmed       = Color.FromRgb(255, 255, 0);
                ColorFilled      = Color.FromRgb(0,   255, 255);
                ColorArmedBarSel = Color.FromRgb(255, 165, 0);
                ColorWaitingBar  = Color.FromRgb(160, 0,   200);
                ColorToggleOn    = Color.FromRgb(0,   160, 0);
                ColorToggleOff   = Color.FromRgb(80,  80,  80);
                ColorFlat        = Color.FromRgb(180, 60,  0);
                ColorBE          = Color.FromRgb(80,  80,  140);
                ColorCancel      = Color.FromRgb(100, 100, 100);
                ColorFlash       = Color.FromRgb(0,   200, 0);

                // CSV
                ExportCSV     = false;
                CSVFolderPath = @"C:\Users\Admin\Documents\NinjaTrader 8\MCScale\";
                PrintToOutput = true;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Second, 1);
            }
            else if (State == State.DataLoaded)
            {
                Calculate     = Calculate.OnBarClose;
                StartBehavior = StartBehavior.ImmediatelySubmit;
                swingPB33    = Swing(PB33SwingStrength);
                swingPB50    = Swing(PB50SwingStrength);
                swingPB66    = Swing(PB66SwingStrength);
                swingBOXTR   = Swing(BOXTR_SwingStrength);
                swingBOINT   = Swing(BOINT_SwingStrength);
                swingBBSAMC  = Swing(BBSAMC_SwingStrength);
             swingBBLSABR = Swing(BBLSABR_SwingStrength);
                swingSE      = Swing(SE_SwingStrength);
                swingSpeedo  = Swing(Speedo_SwingStrength);
                sessionIterator = new NinjaTrader.Data.SessionIterator(Bars);
            }
            else if (State == State.Realtime)
            {
                isRealtime = true;
                DateTime t = Time[0];
				lastSessionDate = Time[0].TimeOfDay < new TimeSpan(17, 0, 0) ? Time[0].Date.AddDays(-1) : Time[0].Date;
                ResetLongLegs();
                ResetShortLegs();
                ResetBarSelectEntries();
                Print("═══════════════════════════════════════════════");
                Print(DateTime.Now + " MCStrategyDashboardV1 LIVE");
                Print("  TestMode=" + TestMode + "  Template=" + AtmTemplateName);
                Print("═══════════════════════════════════════════════");
                BackfillSwingCache();
if (ChartControl != null)
    ChartControl.Dispatcher.InvokeAsync((Action)CreateWPFControls);
            }
            else if (State == State.Terminated)
            {
                if (ChartControl != null)
                    ChartControl.Dispatcher.InvokeAsync((Action)DisposeWPFControls);
            }
        }

        protected override void OnBarUpdate()
        {
            if (!isRealtime) return;

            // ── 1-SEC SERIES — fill detection ─────────────────────────────────
            if (BarsInProgress == 1)
{
    CheckAtmFills();
    if (pendingPBPlacement)
    {
        pendingPBPlacement = false;
        // Bull MC active
        if (activeChanHighLong > 0 && (activePB33Long > 0 || activePB50Long > 0 || activePB66Long > 0))
        {
            double pb33 = (UsePB33 && pb33Armed && activePB33Long > 0 && !l33Active && !s33Active) ? activePB33Long : 0;
            double pb50 = (UsePB50 && pb50Armed && activePB50Long > 0 && !l50Active && !s50Active) ? activePB50Long : 0;
            double pb66 = (UsePB66 && pb66Armed && activePB66Long > 0 && !l66Active && !s66Active) ? activePB66Long : 0;
            if ((pb33 > 0 || pb50 > 0 || pb66 > 0) && !longOrdersPlaced)
            {
                Print(DateTime.Now + " IMMEDIATE PB PLACEMENT — bull MC active on arm | chanH=" + activeChanHighLong + " chanL=" + activeChanLowLong + " pb33=" + activePB33Long + " pb50=" + activePB50Long + " pb66=" + activePB66Long + " pb33Armed=" + pb33Armed + " pb50Armed=" + pb50Armed + " pb66Armed=" + pb66Armed);
                if (pb33 > 0) { string sc, tc; double entryPx = Round(pb33 + PB33EntryOffsetTicks * TickSize); double stop = CalcStop(PB33StopMode, PB33StopOffsetTicks, swingPB33, entryPx, activeChanHighLong, activeChanLowLong, true, activeChanBarsLong, activeChanBarsLong - 1, PB33StopABRBars, PB33StopABRMultiple, out sc); double tgt = CalcTarget(PB33TargetMode, PB33RMultiple, PB33TargetOffsetTicks, entryPx, stop, activeChanHighLong, activeChanLowLong, activeChanBarsLong, true, activeChanBarsLong, activeChanBarsLong - 1, out tc); l33StopCalc = sc; l33TgtCalc = tc; entryL33 = entryPx; FireSingleAtm(entryPx, stop, tgt, true, "L33", ref atmIdL33, ref ordIdL33, ref l33Active, ref stopL33, ref targetL33, ref l33StopTargetSet, () => { l33CallbackOK = true; }); l33StopTargetPrinted = false; longOrdersPlaced = true; }
                if (pb50 > 0) { string sc, tc; double entryPx = Round(pb50 + PB50EntryOffsetTicks * TickSize); double stop = CalcStop(PB50StopMode, PB50StopOffsetTicks, swingPB50, entryPx, activeChanHighLong, activeChanLowLong, true, activeChanBarsLong, activeChanBarsLong - 1, PB50StopABRBars, PB50StopABRMultiple, out sc); double tgt = CalcTarget(PB50TargetMode, PB50RMultiple, PB50TargetOffsetTicks, entryPx, stop, activeChanHighLong, activeChanLowLong, activeChanBarsLong, true, activeChanBarsLong, activeChanBarsLong - 1, out tc); l50StopCalc = sc; l50TgtCalc = tc; entryL50 = entryPx; FireSingleAtm(entryPx, stop, tgt, true, "L50", ref atmIdL50, ref ordIdL50, ref l50Active, ref stopL50, ref targetL50, ref l50StopTargetSet, () => { l50CallbackOK = true; }); l50StopTargetPrinted = false; longOrdersPlaced = true; }
                if (pb66 > 0) { string sc, tc; double entryPx = Round(pb66 + PB66EntryOffsetTicks * TickSize); double stop = CalcStop(PB66StopMode, PB66StopOffsetTicks, swingPB66, entryPx, activeChanHighLong, activeChanLowLong, true, activeChanBarsLong, activeChanBarsLong - 1, PB66StopABRBars, PB66StopABRMultiple, out sc); double tgt = CalcTarget(PB66TargetMode, PB66RMultiple, PB66TargetOffsetTicks, entryPx, stop, activeChanHighLong, activeChanLowLong, activeChanBarsLong, true, activeChanBarsLong, activeChanBarsLong - 1, out tc); l66StopCalc = sc; l66TgtCalc = tc; entryL66 = entryPx; FireSingleAtm(entryPx, stop, tgt, true, "L66", ref atmIdL66, ref ordIdL66, ref l66Active, ref stopL66, ref targetL66, ref l66StopTargetSet, () => { l66CallbackOK = true; }); l66StopTargetPrinted = false; longOrdersPlaced = true; }
            }
        }
        // Bear MC active
        if (activeChanLowShort > 0 && (activePB33Short > 0 || activePB50Short > 0 || activePB66Short > 0))
        {
            double pb33 = (UsePB33 && pb33Armed && activePB33Short > 0 && !s33Active && !l33Active) ? activePB33Short : 0;
            double pb50 = (UsePB50 && pb50Armed && activePB50Short > 0 && !s50Active && !l50Active) ? activePB50Short : 0;
            double pb66 = (UsePB66 && pb66Armed && activePB66Short > 0 && !s66Active && !l66Active) ? activePB66Short : 0;
            if ((pb33 > 0 || pb50 > 0 || pb66 > 0) && !shortOrdersPlaced)
            {
                Print(DateTime.Now + " IMMEDIATE PB PLACEMENT — bear MC active on arm | chanH=" + activeChanHighShort + " chanL=" + activeChanLowShort + " pb33=" + activePB33Short + " pb50=" + activePB50Short + " pb66=" + activePB66Short + " pb33Armed=" + pb33Armed + " pb50Armed=" + pb50Armed + " pb66Armed=" + pb66Armed);
                if (pb33 > 0) { string sc, tc; double entryPx = Round(pb33 - PB33EntryOffsetTicks * TickSize); double stop = CalcStop(PB33StopMode, PB33StopOffsetTicks, swingPB33, entryPx, activeChanHighShort, activeChanLowShort, false, activeChanBarsShort, activeChanBarsShort - 1, PB33StopABRBars, PB33StopABRMultiple, out sc); double tgt = CalcTarget(PB33TargetMode, PB33RMultiple, PB33TargetOffsetTicks, entryPx, stop, activeChanHighShort, activeChanLowShort, activeChanBarsShort, false, activeChanBarsShort, activeChanBarsShort - 1, out tc); s33StopCalc = sc; s33TgtCalc = tc; entryS33 = entryPx; FireSingleAtm(entryPx, stop, tgt, false, "S33", ref atmIdS33, ref ordIdS33, ref s33Active, ref stopS33, ref targetS33, ref s33StopTargetSet, () => { s33CallbackOK = true; }); s33StopTargetPrinted = false; shortOrdersPlaced = true; }
                if (pb50 > 0) { string sc, tc; double entryPx = Round(pb50 - PB50EntryOffsetTicks * TickSize); double stop = CalcStop(PB50StopMode, PB50StopOffsetTicks, swingPB50, entryPx, activeChanHighShort, activeChanLowShort, false, activeChanBarsShort, activeChanBarsShort - 1, PB50StopABRBars, PB50StopABRMultiple, out sc); double tgt = CalcTarget(PB50TargetMode, PB50RMultiple, PB50TargetOffsetTicks, entryPx, stop, activeChanHighShort, activeChanLowShort, activeChanBarsShort, false, activeChanBarsShort, activeChanBarsShort - 1, out tc); s50StopCalc = sc; s50TgtCalc = tc; entryS50 = entryPx; FireSingleAtm(entryPx, stop, tgt, false, "S50", ref atmIdS50, ref ordIdS50, ref s50Active, ref stopS50, ref targetS50, ref s50StopTargetSet, () => { s50CallbackOK = true; }); s50StopTargetPrinted = false; shortOrdersPlaced = true; }
                if (pb66 > 0) { string sc, tc; double entryPx = Round(pb66 - PB66EntryOffsetTicks * TickSize); double stop = CalcStop(PB66StopMode, PB66StopOffsetTicks, swingPB66, entryPx, activeChanHighShort, activeChanLowShort, false, activeChanBarsShort, activeChanBarsShort - 1, PB66StopABRBars, PB66StopABRMultiple, out sc); double tgt = CalcTarget(PB66TargetMode, PB66RMultiple, PB66TargetOffsetTicks, entryPx, stop, activeChanHighShort, activeChanLowShort, activeChanBarsShort, false, activeChanBarsShort, activeChanBarsShort - 1, out tc); s66StopCalc = sc; s66TgtCalc = tc; entryS66 = entryPx; FireSingleAtm(entryPx, stop, tgt, false, "S66", ref atmIdS66, ref ordIdS66, ref s66Active, ref stopS66, ref targetS66, ref s66StopTargetSet, () => { s66CallbackOK = true; }); s66StopTargetPrinted = false; shortOrdersPlaced = true; }
            }
        }
    }
    return;
}

            // ── PRIMARY SERIES ────────────────────────────────────────────────
           if (CurrentBar < BarsRequiredToTrade) return;

CheckSessionReset();
if (!backfillMCDone) { BackfillActiveMC(); backfillMCDone = true; }

            if (!mcStrategyOn) return;

            // ── TEST MODE ──────────────────────────────────────────────────────
            if (TestMode && !testFired)
            {
                testFired    = true;
                double entry  = Round(Close[0] - 4 * TickSize);
                double stop   = Round(entry    - 8 * TickSize);
                double target = Round(entry    + 8 * TickSize);
                Print("═══════════════════════════════════════════════");
                Print(DateTime.Now + " TEST MODE — fake L33 ATM");
                Print(string.Format("  Entry={0}  Stop={1}  Target={2}  Risk=8t", entry, stop, target));
                Print("═══════════════════════════════════════════════");
                FireSingleAtm(entry, stop, target, true, "TEST_L33",
                    ref atmIdL33, ref ordIdL33, ref l33Active,
                    ref stopL33, ref targetL33, ref l33StopTargetSet,
                    () => { l33CallbackOK = true; });
                return;
            }

            // ── NORMAL MODE ───────────────────────────────────────────────────
            var mc = MyMicroChannel(ContinueMC, Show0CC, Show1CC, Show2CC, Show3CC, Show4CC, Show5CC, ShowCX);
if (mc == null) { Print(DateTime.Now + " mc null"); return; }
Print(DateTime.Now + " OBU | bullActive=" + (mc.MC_Bull_Strong[0] > 0) + " bearActive=" + (mc.MC_Bear_Strong[0] > 0) + " pb33Armed=" + pb33Armed + " pb50Armed=" + pb50Armed + " pb66Armed=" + pb66Armed);

            bool   bullActive = mc.MC_Bull_Strong[0] > 0;
            bool   bearActive = mc.MC_Bear_Strong[0] > 0;
            double bullBarNo  = mc.MC_Bull[0];
            double bearBarNo  = mc.MC_Bear[0];

          

          // ── Speedo — auto-cancel RETIRED
            //if (speedoActive && !speedoFilled && speedoOrderBarIndex >= 0 && BarsArray[0].Count - 1 > speedoOrderBarIndex)
            //{
            //    Print(DateTime.Now + " SPEEDO AUTO-CANCEL — not filled by close of bar after WRB");
            //    if (!string.IsNullOrEmpty(ordIdSpeedo)) AtmStrategyCancelEntryOrder(ordIdSpeedo);
            //    speedoActive        = false;
            //    speedoCallbackOK    = false;
            //    speedoOrderBarIndex = -1;
            //    speedoImpulseBarIndex = -1;
            //    atmIdSpeedo = ordIdSpeedo = string.Empty;
            //    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off);
            //}

            // ── Speedo — waiting for reversal bar to close ────────────────────
            if (false && speedoWaitingBar && speedoReversalBarIndex >= 0 && BarsArray[0].Count - 1 > speedoReversalBarIndex)
            {
                int reversalBarsAgo = BarsArray[0].Count - 1 - speedoReversalBarIndex;
                double wrbHigh = High[reversalBarsAgo];
                double wrbLow  = Low[reversalBarsAgo];
                double wrbClose = Close[reversalBarsAgo];

                // Validate — reversal bar must not close beyond impulse extreme
                bool invalid = speedoIsLong  ? wrbClose >= speedoImpulseHigh
                                             : wrbClose <= speedoImpulseLow;
                if (invalid)
                {
                    string msg = string.Format("Invalid Speedo Setup — reversal bar closed {0} impulse {1} ({2} vs {3})",
                        speedoIsLong ? "above" : "below",
                        speedoIsLong ? "high" : "low",
                        wrbClose,
                        speedoIsLong ? speedoImpulseHigh : speedoImpulseLow);
                    Print(DateTime.Now + " SPEEDO INVALID — " + msg);
                    speedoWaitingBar       = false;
                    speedoArmed            = false;
                    speedoReversalBarIndex = -1;
                    speedoImpulseBarIndex  = -1;
                    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off);
                    if (ChartControl != null)
                        ChartControl.Dispatcher.InvokeAsync((Action)(() =>
                            System.Windows.MessageBox.Show(msg, "Invalid Speedo Setup", System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Warning)));
                }
                else
                {
                    // Valid — place stop limit order above impulse high (long) or below impulse low (short)
                    double entryPx = speedoIsLong
                        ? Round(speedoImpulseHigh + Speedo_EntryOffsetTicks * TickSize)
                        : Round(speedoImpulseLow  - Speedo_EntryOffsetTicks * TickSize);
                    double sp  = speedoIsLong
                        ? Round(wrbLow  - Speedo_StopOffsetTicks * TickSize)
                        : Round(wrbHigh + Speedo_StopOffsetTicks * TickSize);
                    double risk = Math.Abs(entryPx - sp);
                    if (risk < TickSize) risk = TickSize;
                    double tgt = speedoIsLong
                        ? Round(entryPx + risk * Speedo_RMultiple - Speedo_TargetOffsetTicks * TickSize)
                        : Round(entryPx - risk * Speedo_RMultiple + Speedo_TargetOffsetTicks * TickSize);
                    speedoStopCalc = string.Format("▶ {0} STOP {1}  WRB: {2}[{3}]={4} OFFSET={5} = {1}",
                        speedoIsLong ? "LONG" : "SHORT", sp,
                        speedoIsLong ? "WRB_LOW" : "WRB_HIGH",
                        reversalBarsAgo, speedoIsLong ? wrbLow : wrbHigh, Speedo_StopOffsetTicks * TickSize);
                    speedoTgtCalc = string.Format("$ {0} TARGET {1}  R_MULTIPLE: ENTRY={2} RISK={3} x R={4} OFFSET={5} = {1}",
                        speedoIsLong ? "LONG" : "SHORT", tgt, entryPx, risk, Speedo_RMultiple, Speedo_TargetOffsetTicks * TickSize);
                    entrySpeedo = entryPx;
                    Print(string.Format("│  ▶ SPEEDO FIRED {0} entry={1} stop={2} target={3}", speedoIsLong ? "LONG" : "SHORT", entryPx, sp, tgt));
                    Print("│    " + speedoStopCalc);
                    Print("│    " + speedoTgtCalc);
                    bool speedoStopTargetSetDummy = false;
                    FireSingleAtm(entryPx, sp, tgt, speedoIsLong, "SPEEDO",
                        ref atmIdSpeedo, ref ordIdSpeedo, ref speedoActive,
                        ref stopSpeedo, ref targetSpeedo, ref speedoStopTargetSetDummy,
                        () => { speedoCallbackOK = true; }, OrderType.StopLimit);
                    speedoWaitingBar       = false;
                    speedoReversalBarIndex = -1;
                    speedoOrderBarIndex    = BarsArray[0].Count - 1;
                    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Armed);
                }
            }

            // ── BULL ──────────────────────────────────────────────────────────
            if (bullActive && bullBarNo > 0)
            {
                int    barsBack = (int)(bullBarNo - 1);
                double chanLow  = Low[barsBack];
                double chanHigh = MAX(High, Math.Min(barsBack + 1, CurrentBar))[0];
                activeChanHighLong = chanHigh;
                activeChanLowLong  = chanLow;
                activeChanBarsLong = (int)bullBarNo;

                double pb33 = (mc.PB33[0] > 0 && mc.PB33[0] > chanLow && mc.PB33[0] < chanHigh) ? mc.PB33[0] : 0;
                double pb50 = (mc.PB50[0] > 0 && mc.PB50[0] > chanLow && mc.PB50[0] < chanHigh) ? mc.PB50[0] : 0;
                double pb66 = (mc.PB66[0] > 0 && mc.PB66[0] > chanLow && mc.PB66[0] < chanHigh) ? mc.PB66[0] : 0;
                activePB33Long = pb33; activePB50Long = pb50; activePB66Long = pb66;

                bool isNewBull = (bullBarNo == 1) || (bullBarNo < prevBullBarNo);
                if (isNewBull)
                {
                    longChannelCounter++;
                    ResetLongLegs();
                    cancelWatchLockedLong = false;
                    Print("╔══ NEW BULL C" + longChannelCounter + " | MC_BULL=" + (int)bullBarNo + " BARS_BACK=" + barsBack + " ══════════════════════════════════╗");
                    Print("│  CHAN_HIGH=" + chanHigh + "  CHAN_LOW=" + chanLow + "  PB33=" + pb33 + "  PB50=" + pb50 + "  PB66=" + pb66);
                    NinjaTrader.NinjaScript.DrawingTools.Draw.Text(this, "BullC" + longChannelCounter, true, "C" + longChannelCounter, barsBack, chanHigh, 10, Brushes.LimeGreen, new NinjaTrader.Gui.Tools.SimpleFont("Arial", 10), TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 0);
Print("╠══════════════════════════════════════════════════════════════════════╣");

                    // CT Guard — close short PB positions
                    if (ctGuardOn && (s33StopTargetSet || s50StopTargetSet || s66StopTargetSet || s33Active || s50Active || s66Active))
                    {
                        lastExitSource = "CT-GUARD";
                        Print(DateTime.Now + " CT GUARD — new bull MC, closing/cancelling short PB positions");
                        if (!string.IsNullOrEmpty(atmIdS33) && s33StopTargetSet) AtmStrategyClose(atmIdS33);
                        if (!string.IsNullOrEmpty(atmIdS50) && s50StopTargetSet) AtmStrategyClose(atmIdS50);
                        if (!string.IsNullOrEmpty(atmIdS66) && s66StopTargetSet) AtmStrategyClose(atmIdS66);
                        if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) AtmStrategyCancelEntryOrder(ordIdS33);
                        if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) AtmStrategyCancelEntryOrder(ordIdS50);
                        if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) AtmStrategyCancelEntryOrder(ordIdS66);
                    }
                    // CT Guard — SA MC
                    if (ctGuardOn && BBSAMC_CTGuardEnabled && saMCFilled && !string.IsNullOrEmpty(atmIdSAMC))
                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdSAMC); Print(DateTime.Now + " CT GUARD — closing SA MC"); }
                    if (ctGuardOn && BBSAMC_CTGuardEnabled && saMCActive && !string.IsNullOrEmpty(ordIdSAMC))
                        AtmStrategyCancelEntryOrder(ordIdSAMC);
                    // CT Guard — SA BR
//                    if (ctGuardOn && BBLSABR_CTGuardEnabled && saBRFilled && !string.IsNullOrEmpty(atmIdSABR))
//                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdSABR); Print(DateTime.Now + " CT GUARD — closing SA BR"); }
//                    if (ctGuardOn && BBLSABR_CTGuardEnabled && saBRActive && !string.IsNullOrEmpty(ordIdSABR))
//                        AtmStrategyCancelEntryOrder(ordIdSABR);
                    // CT Guard — SE S
//                    if (ctGuardOn && SE_CTGuardEnabled && seSFilled && !string.IsNullOrEmpty(atmIdSES))
//                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdSES); Print(DateTime.Now + " CT GUARD — closing SE S"); }
//                    // CT Guard — Speedo short
//                    if (ctGuardOn && Speedo_CTGuardEnabled && speedoFilled && !speedoIsLong && !string.IsNullOrEmpty(atmIdSpeedo))
//                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdSpeedo); Print(DateTime.Now + " CT GUARD — closing Speedo Short"); }
                    // Reset BB MC for new bull
                    ResetBBMCState();
                }
                prevBullBarNo = bullBarNo;

                // ── PB entries ────────────────────────────────────────────────
                // ── PB entries ────────────────────────────────────────────────
                if (UsePB33 && pb33Armed && !pb33Filled && pb33 > 0 && !l33Active && !s33Active)
                {
                    string sc, tc;
                    double entryPx = Round(pb33 + PB33EntryOffsetTicks * TickSize);
                    double stop    = CalcStop(PB33StopMode, PB33StopOffsetTicks, swingPB33, entryPx, chanHigh, chanLow, true, (int)bullBarNo, barsBack, PB33StopABRBars, PB33StopABRMultiple, out sc);
                    double tgt     = CalcTarget(PB33TargetMode, PB33RMultiple, PB33TargetOffsetTicks, entryPx, stop, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                    l33StopCalc = sc; l33TgtCalc = tc; entryL33 = entryPx;
                    Print(string.Format("│  ▶ L33 FIRED entry={0} stop={1} target={2} MC_BULL={3} BARS_BACK={4}", entryPx, stop, tgt, (int)bullBarNo, barsBack));
                    Print("│    " + sc);
                    Print("│    " + tc);
                    Print("│");
                    FireSingleAtm(entryPx, stop, tgt, true, "L33",
                        ref atmIdL33, ref ordIdL33, ref l33Active,
                        ref stopL33, ref targetL33, ref l33StopTargetSet,
                        () => { l33CallbackOK = true; });
                    l33StopTargetPrinted = false;
                    longOrdersPlaced = true;
                }
                if (UsePB50 && pb50Armed && !pb50Filled && pb50 > 0 && !l50Active && !s50Active)
                {
                    string sc, tc;
                    double entryPx = Round(pb50 + PB50EntryOffsetTicks * TickSize);
                    double stop    = CalcStop(PB50StopMode, PB50StopOffsetTicks, swingPB50, entryPx, chanHigh, chanLow, true, (int)bullBarNo, barsBack, PB50StopABRBars, PB50StopABRMultiple, out sc);
                    double tgt     = CalcTarget(PB50TargetMode, PB50RMultiple, PB50TargetOffsetTicks, entryPx, stop, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                    l50StopCalc = sc; l50TgtCalc = tc; entryL50 = entryPx;
                    Print(string.Format("│  ▶ L50 FIRED entry={0} stop={1} target={2} MC_BULL={3} BARS_BACK={4}", entryPx, stop, tgt, (int)bullBarNo, barsBack));
                    Print("│    " + sc);
                    Print("│    " + tc);
                    Print("│");
                    FireSingleAtm(entryPx, stop, tgt, true, "L50",
                        ref atmIdL50, ref ordIdL50, ref l50Active,
                        ref stopL50, ref targetL50, ref l50StopTargetSet,
                        () => { l50CallbackOK = true; });
                    l50StopTargetPrinted = false;
                    longOrdersPlaced = true;
                }
                if (UsePB66 && pb66Armed && !pb66Filled && pb66 > 0 && !l66Active && !s66Active)
                {
                    string sc, tc;
                    double entryPx = Round(pb66 + PB66EntryOffsetTicks * TickSize);
                    double stop    = CalcStop(PB66StopMode, PB66StopOffsetTicks, swingPB66, entryPx, chanHigh, chanLow, true, (int)bullBarNo, barsBack, PB66StopABRBars, PB66StopABRMultiple, out sc);
                    double tgt     = CalcTarget(PB66TargetMode, PB66RMultiple, PB66TargetOffsetTicks, entryPx, stop, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                    l66StopCalc = sc; l66TgtCalc = tc; entryL66 = entryPx;
                    Print(string.Format("│  ▶ L66 FIRED entry={0} stop={1} target={2} MC_BULL={3} BARS_BACK={4}", entryPx, stop, tgt, (int)bullBarNo, barsBack));
                    Print("│    " + sc);
                    Print("│    " + tc);
                    Print("│");
                    FireSingleAtm(entryPx, stop, tgt, true, "L66",
                        ref atmIdL66, ref ordIdL66, ref l66Active,
                        ref stopL66, ref targetL66, ref l66StopTargetSet,
                        () => { l66CallbackOK = true; });
                    l66StopTargetPrinted = false;
                    longOrdersPlaced = true;
                }

                // ── BB MC — RETIRED (commented out, reactivate when needed) ──────
                //if (UseBBMC && !bbMCActive && !bbMCFilled)
                //{
                //    string sc, tc;
                //    double entryPx = Round(chanLow - BBSAMC_EntryOffsetTicks * TickSize);
                //    double sp      = CalcStop(BBSAMC_StopMode, BBSAMC_StopOffsetTicks, swingBBSAMC, entryPx, chanHigh, chanLow, true, (int)bullBarNo, barsBack, BBSAMC_StopABRBars, BBSAMC_StopABRMultiple, out sc);
                //    double tgt     = CalcTarget(BBSAMC_TargetMode, BBSAMC_RMultiple, BBSAMC_TargetOffsetTicks, entryPx, sp, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                //    bbMCStopCalc = sc; bbMCTgtCalc = tc; entryBBMC = entryPx;
                //    Print(string.Format("│  ▶ BB MC FIRED LONG entry={0} stop={1} target={2} MC_BULL={3} BARS_BACK={4}", entryPx, sp, tgt, (int)bullBarNo, barsBack));
                //    Print("│    " + sc);
                //    Print("│    " + tc);
                //    Print("│");
                //    bool bbMCStopTargetSetDummy = false;
                //    FireSingleAtm(entryPx, sp, tgt, true, "BBMC",
                //        ref atmIdBBMC, ref ordIdBBMC, ref bbMCActive,
                //        ref stopBBMC, ref targetBBMC, ref bbMCStopTargetSetDummy,
                //        () => { bbMCCallbackOK = true; });
                //    UpdateBarSelectButtonColor(btnBBMC, BtnState3.Armed);
                //}

                // ── BB MC update — RETIRED ─────────────────────────────────────
                //if (bbMCActive && !bbMCFilled && bbMCCallbackOK)
                //{
                //    double newEntry = Round(chanLow - BBSAMC_EntryOffsetTicks * TickSize);
                //    if (Math.Abs(newEntry - lastSentBBMC) >= TickSize)
                //    {
                //        string[] st = GetAtmStrategyEntryOrderStatus(ordIdBBMC);
                //        if (st != null && st.Length > 2 && st[2] == "Working")
                //        {
                //            AtmStrategyChangeEntryOrder(newEntry, 0, ordIdBBMC);
                //            lastSentBBMC = newEntry;
                //            Print(DateTime.Now + " BB MC → " + newEntry);
                //        }
                //    }
                //}

                // ── BB BL — update price if initiated inside this MC ───────────
             for (int i = 0; i < atmIdsBBBL.Count; i++)
                {
                    if (filledBBBL[i] || !callbackBBBL[i] || !inMCBBBL[i]) continue;
                    int bAgo = barsAgoBBBL[i];
                    if (bAgo < 0 || bAgo > CurrentBar) continue;
                    double newEntry = Round(BarsArray[0].GetLow(BarsArray[0].Count - 1 - bAgo) - BBLSABR_EntryOffsetTicks * TickSize);
                    if (Math.Abs(newEntry - entriesBBBL[i]) >= TickSize)
                    {
                        string[] st = GetAtmStrategyEntryOrderStatus(ordIdsBBBL[i]);
                        if (st != null && st.Length > 2 && st[2] == "Working")
                        {
                            AtmStrategyChangeEntryOrder(newEntry, 0, ordIdsBBBL[i]);
                            entriesBBBL[i] = newEntry;
                            Print(DateTime.Now + " BB BL #" + i + " → " + newEntry);
                        }
                    }
                }

                // ── PB target updates for unfilled legs ───────────────────────
                if (l33Active && !l33StopTargetSet && l33CallbackOK)
                {
                    string tc; double newTgt = CalcTarget(PB33TargetMode, PB33RMultiple, PB33TargetOffsetTicks, entryL33, stopL33, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                    if (Math.Abs(newTgt - targetL33) >= TickSize) { Print(string.Format("│  ⚡ L33 TARGET UPDATED {0}  (was {1}) [MC_BULL={2} BARS_BACK={3}]", newTgt, targetL33, (int)bullBarNo, barsBack)); targetL33 = newTgt; l33TgtCalc = tc; }
                }
                if (l50Active && !l50StopTargetSet && l50CallbackOK)
                {
                    string tc; double newTgt = CalcTarget(PB50TargetMode, PB50RMultiple, PB50TargetOffsetTicks, entryL50, stopL50, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                    if (Math.Abs(newTgt - targetL50) >= TickSize) { Print(string.Format("│  ⚡ L50 TARGET UPDATED {0}  (was {1}) [MC_BULL={2} BARS_BACK={3}]", newTgt, targetL50, (int)bullBarNo, barsBack)); targetL50 = newTgt; l50TgtCalc = tc; }
                }
                if (l66Active && !l66StopTargetSet && l66CallbackOK)
                {
                    string tc; double newTgt = CalcTarget(PB66TargetMode, PB66RMultiple, PB66TargetOffsetTicks, entryL66, stopL66, chanHigh, chanLow, activeChanBarsLong, true, (int)bullBarNo, barsBack, out tc);
                    if (Math.Abs(newTgt - targetL66) >= TickSize) { Print(string.Format("│  ⚡ L66 TARGET UPDATED {0}  (was {1}) [MC_BULL={2} BARS_BACK={3}]", newTgt, targetL66, (int)bullBarNo, barsBack)); targetL66 = newTgt; l66TgtCalc = tc; }
                }

                // ── Update unfilled PB entry order prices ─────────────────────
                if ((pb33 > 0 || pb50 > 0 || pb66 > 0) && longOrdersPlaced
                    && l33CallbackOK && l50CallbackOK && l66CallbackOK)
                    UpdateLongPBOrders(pb33, pb50, pb66);
            }
            else
            {
                // Bull ended
               if (prevBullBarNo != 999 && activeChanHighLong > 0)
                {
                    cancelWatchHighLong = activeChanHighLong;
                    boXTRLastChanLowLong = activeChanLowLong;
                    closesOutsideLongCount = 0;
                    // BB MC — cancel if still unfilled when MC ends
                    if (bbMCActive && !bbMCFilled && !string.IsNullOrEmpty(ordIdBBMC))
                    { AtmStrategyCancelEntryOrder(ordIdBBMC); bbMCActive = false; bbMCCallbackOK = false; Print(DateTime.Now + " BB MC unfilled — MC ended, order cancelled"); UpdateBarSelectButtonColor(btnBBMC, BtnState3.Off); }
                    // BO XTR — place buy stop at channel high when MC ends
                    if (UseBO_XTR && !boXTRActive && cancelWatchHighLong > 0)
                        FireBOXTR(true, cancelWatchHighLong, boXTRLastChanLowLong);
                }
                boXTRLastChanLowLong = activeChanLowLong;
                prevBullBarNo      = 999;
                activeChanHighLong = activeChanLowLong = 0;
                activePB33Long     = activePB50Long = activePB66Long = 0;
                activeChanBarsLong = 0;

                // Cancel watch — PB longs
                if (EnableCancelWatch && cancelWatchHighLong > 0 && longOrdersPlaced
                    && (l33Active && !l33StopTargetSet || l50Active && !l50StopTargetSet || l66Active && !l66StopTargetSet))
                {
                    if (Close[0] > cancelWatchHighLong)
                    {
                        closesOutsideLongCount++;
                        Print(string.Format("{0} CANCEL WATCH LONG | close={1} > extreme={2} | count={3}/{4}",
                            DateTime.Now, Close[0], cancelWatchHighLong, closesOutsideLongCount, ClosesOutsideToCancel));
                        if (closesOutsideLongCount >= ClosesOutsideToCancel)
                        {
                            if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) { AtmStrategyCancelEntryOrder(ordIdL33); l33Active = false; }
							if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) { AtmStrategyCancelEntryOrder(ordIdL50); l50Active = false; }
							if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) { AtmStrategyCancelEntryOrder(ordIdL66); l66Active = false; }
							cancelWatchLockedLong  = false;
							cancelWatchHighLong    = 0;
							closesOutsideLongCount = 0;
							longOrdersPlaced       = false;
							atmIdL33 = atmIdL50 = atmIdL66 = ordIdL33 = ordIdL50 = ordIdL66 = string.Empty;
							lastSentL33 = lastSentL50 = lastSentL66 = 0;
							l33CallbackOK = l50CallbackOK = l66CallbackOK = false;
							pb33Armed = AutoReArm; pb50Armed = AutoReArm; pb66Armed = AutoReArm;
							allPBsArmed = AutoReArm;
							SetPBButtonColors();
							Print(DateTime.Now + " CANCEL WATCH LONG — cancelled unfilled PB orders, " + (AutoReArm ? "re-armed for next MC" : "PBs disarmed"));
                        }
                    }
                    else closesOutsideLongCount = 0;
                }

                // Cancel watch — BB BL unfilled orders initiated inside MC that just ended
                if (EnableCancelWatch && cancelWatchHighLong > 0 && Close[0] > cancelWatchHighLong)
                {
                    for (int i = atmIdsBBBL.Count - 1; i >= 0; i--)
                    {
                        if (filledBBBL[i] || !inMCBBBL[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsBBBL[i])) AtmStrategyCancelEntryOrder(ordIdsBBBL[i]);
                        atmIdsBBBL.RemoveAt(i); ordIdsBBBL.RemoveAt(i); stopsBBBL.RemoveAt(i);
                        targetsBBBL.RemoveAt(i); entriesBBBL.RemoveAt(i); filledBBBL.RemoveAt(i);
                        callbackBBBL.RemoveAt(i); stopCalcsBBBL.RemoveAt(i); tgtCalcsBBBL.RemoveAt(i);
                        barsAgoBBBL.RemoveAt(i); inMCBBBL.RemoveAt(i);
                        Print(DateTime.Now + " BB BL #" + i + " cancel watch — cancelled");
                    }
                    UpdateLmtButtonLabel(btnBBBL, atmIdsBBBL, "BBBL");
                }
            }

            // ── BEAR ──────────────────────────────────────────────────────────
            if (bearActive && bearBarNo > 0)
            {
                int    barsBack = (int)(bearBarNo - 1);
                double chanHigh = High[barsBack];
                double chanLow  = MIN(Low, Math.Min(barsBack + 1, CurrentBar))[0];
                activeChanHighShort = chanHigh;
                activeChanLowShort  = chanLow;
                activeChanBarsShort = (int)bearBarNo;

                double pb33 = (mc.PB33[0] > 0 && mc.PB33[0] < chanHigh && mc.PB33[0] > chanLow) ? mc.PB33[0] : 0;
                double pb50 = (mc.PB50[0] > 0 && mc.PB50[0] < chanHigh && mc.PB50[0] > chanLow) ? mc.PB50[0] : 0;
                double pb66 = (mc.PB66[0] > 0 && mc.PB66[0] < chanHigh && mc.PB66[0] > chanLow) ? mc.PB66[0] : 0;
                activePB33Short = pb33; activePB50Short = pb50; activePB66Short = pb66;

                bool isNewBear = (bearBarNo == 1) || (bearBarNo < prevBearBarNo);
                if (isNewBear)
                {
                    shortChannelCounter++;
                    ResetShortLegs();
                    cancelWatchLockedShort = false;
                    Print("╔══ NEW BEAR C" + shortChannelCounter + " | MC_BEAR=" + (int)bearBarNo + " BARS_BACK=" + barsBack + " ══════════════════════════════════╗");
                    Print("│  CHAN_HIGH=" + chanHigh + "  CHAN_LOW=" + chanLow + "  PB33=" + pb33 + "  PB50=" + pb50 + "  PB66=" + pb66);
                    NinjaTrader.NinjaScript.DrawingTools.Draw.Text(this, "BearC" + shortChannelCounter, true, "C" + shortChannelCounter, barsBack, chanLow, -10, Brushes.Red, new NinjaTrader.Gui.Tools.SimpleFont("Arial", 10), TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 0);
					Print("╠══════════════════════════════════════════════════════════════════════╣");

                    // CT Guard — close long PB positions
                    if (ctGuardOn && (l33StopTargetSet || l50StopTargetSet || l66StopTargetSet || l33Active || l50Active || l66Active))
                    {
                        lastExitSource = "CT-GUARD";
                        Print(DateTime.Now + " CT GUARD — new bear MC, closing/cancelling long PB positions");
                        if (!string.IsNullOrEmpty(atmIdL33) && l33StopTargetSet) AtmStrategyClose(atmIdL33);
                        if (!string.IsNullOrEmpty(atmIdL50) && l50StopTargetSet) AtmStrategyClose(atmIdL50);
                        if (!string.IsNullOrEmpty(atmIdL66) && l66StopTargetSet) AtmStrategyClose(atmIdL66);
                        if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) AtmStrategyCancelEntryOrder(ordIdL33);
                        if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) AtmStrategyCancelEntryOrder(ordIdL50);
                        if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) AtmStrategyCancelEntryOrder(ordIdL66);
                    }
                    // CT Guard — BB MC
                    if (ctGuardOn && BBSAMC_CTGuardEnabled && bbMCFilled && !string.IsNullOrEmpty(atmIdBBMC))
                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdBBMC); Print(DateTime.Now + " CT GUARD — closing BB MC"); }
                    if (ctGuardOn && BBSAMC_CTGuardEnabled && bbMCActive && !string.IsNullOrEmpty(ordIdBBMC))
                        AtmStrategyCancelEntryOrder(ordIdBBMC);
                    // CT Guard — BB BL
//                    if (ctGuardOn && BBLSABR_CTGuardEnabled && bbBLFilled && !string.IsNullOrEmpty(atmIdBBBL))
//                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdBBBL); Print(DateTime.Now + " CT GUARD — closing BB BL"); }
//                    if (ctGuardOn && BBLSABR_CTGuardEnabled && bbBLActive && !string.IsNullOrEmpty(ordIdBBBL))
//                        AtmStrategyCancelEntryOrder(ordIdBBBL);
                    // CT Guard — SE L
                   if (ctGuardOn && SE_CTGuardEnabled && atmIdsSEL.Count > 0 && filledSEL.Contains(true))
                    { lastExitSource = "CT-GUARD"; foreach (var id in atmIdsSEL) if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id); Print(DateTime.Now + " CT GUARD — closing SE L"); }
                    // CT Guard — Speedo long
                    if (ctGuardOn && Speedo_CTGuardEnabled && speedoFilled && speedoIsLong && !string.IsNullOrEmpty(atmIdSpeedo))
                    { lastExitSource = "CT-GUARD"; AtmStrategyClose(atmIdSpeedo); Print(DateTime.Now + " CT GUARD — closing Speedo Long"); }
                    // Reset SA MC for new bear
                    ResetSAMCState();
                }
                prevBearBarNo = bearBarNo;

                // ── PB entries ────────────────────────────────────────────────
                // ── PB entries ────────────────────────────────────────────────
                if (UsePB33 && pb33Armed && !pb33Filled && pb33 > 0 && !s33Active && !l33Active)
                {
                    string sc, tc;
                    double entryPx = Round(pb33 - PB33EntryOffsetTicks * TickSize);
                    double stop    = CalcStop(PB33StopMode, PB33StopOffsetTicks, swingPB33, entryPx, chanHigh, chanLow, false, (int)bearBarNo, barsBack, PB33StopABRBars, PB33StopABRMultiple, out sc);
                    double tgt     = CalcTarget(PB33TargetMode, PB33RMultiple, PB33TargetOffsetTicks, entryPx, stop, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                    s33StopCalc = sc; s33TgtCalc = tc; entryS33 = entryPx;
                    Print(string.Format("│  ▶ S33 FIRED entry={0} stop={1} target={2} MC_BEAR={3} BARS_BACK={4}", entryPx, stop, tgt, (int)bearBarNo, barsBack));
                    Print("│    " + sc);
                    Print("│    " + tc);
                    Print("│");
                    FireSingleAtm(entryPx, stop, tgt, false, "S33",
                        ref atmIdS33, ref ordIdS33, ref s33Active,
                        ref stopS33, ref targetS33, ref s33StopTargetSet,
                        () => { s33CallbackOK = true; });
                    s33StopTargetPrinted = false;
                    shortOrdersPlaced = true;
                }
					if (UsePB50 && pb50Armed && !pb50Filled && pb50 > 0 && !s50Active && !l50Active)                {
                    string sc, tc;
                    double entryPx = Round(pb50 - PB50EntryOffsetTicks * TickSize);
                    double stop    = CalcStop(PB50StopMode, PB50StopOffsetTicks, swingPB50, entryPx, chanHigh, chanLow, false, (int)bearBarNo, barsBack, PB50StopABRBars, PB50StopABRMultiple, out sc);
                    double tgt     = CalcTarget(PB50TargetMode, PB50RMultiple, PB50TargetOffsetTicks, entryPx, stop, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                    s50StopCalc = sc; s50TgtCalc = tc; entryS50 = entryPx;
                    Print(string.Format("│  ▶ S50 FIRED entry={0} stop={1} target={2} MC_BEAR={3} BARS_BACK={4}", entryPx, stop, tgt, (int)bearBarNo, barsBack));
                    Print("│    " + sc);
                    Print("│    " + tc);
                    Print("│");
                    FireSingleAtm(entryPx, stop, tgt, false, "S50",
                        ref atmIdS50, ref ordIdS50, ref s50Active,
                        ref stopS50, ref targetS50, ref s50StopTargetSet,
                        () => { s50CallbackOK = true; });
                    s50StopTargetPrinted = false;
                    shortOrdersPlaced = true;
                }
					if (UsePB66 && pb66Armed && !pb66Filled && pb66 > 0 && !s66Active && !l66Active)                {
                    string sc, tc;
                    double entryPx = Round(pb66 - PB66EntryOffsetTicks * TickSize);
                    double stop    = CalcStop(PB66StopMode, PB66StopOffsetTicks, swingPB66, entryPx, chanHigh, chanLow, false, (int)bearBarNo, barsBack, PB66StopABRBars, PB66StopABRMultiple, out sc);
                    double tgt     = CalcTarget(PB66TargetMode, PB66RMultiple, PB66TargetOffsetTicks, entryPx, stop, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                    s66StopCalc = sc; s66TgtCalc = tc; entryS66 = entryPx;
                    Print(string.Format("│  ▶ S66 FIRED entry={0} stop={1} target={2} MC_BEAR={3} BARS_BACK={4}", entryPx, stop, tgt, (int)bearBarNo, barsBack));
                    Print("│    " + sc);
                    Print("│    " + tc);
                    Print("│");
                    FireSingleAtm(entryPx, stop, tgt, false, "S66",
                        ref atmIdS66, ref ordIdS66, ref s66Active,
                        ref stopS66, ref targetS66, ref s66StopTargetSet,
                        () => { s66CallbackOK = true; });
                    s66StopTargetPrinted = false;
                    shortOrdersPlaced = true;
                }

                // ── SA MC — RETIRED (commented out, reactivate when needed) ──────
                //if (UseSAMC && !saMCActive && !saMCFilled)
                //{
                //    string sc, tc;
                //    double entryPx = Round(chanHigh + BBSAMC_EntryOffsetTicks * TickSize);
                //    double sp      = CalcStop(BBSAMC_StopMode, BBSAMC_StopOffsetTicks, swingBBSAMC, entryPx, chanHigh, chanLow, false, (int)bearBarNo, barsBack, BBSAMC_StopABRBars, BBSAMC_StopABRMultiple, out sc);
                //    double tgt     = CalcTarget(BBSAMC_TargetMode, BBSAMC_RMultiple, BBSAMC_TargetOffsetTicks, entryPx, sp, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                //    saMCStopCalc = sc; saMCTgtCalc = tc; entrySAMC = entryPx;
                //    Print(string.Format("│  ▶ SA MC FIRED SHORT entry={0} stop={1} target={2} MC_BEAR={3} BARS_BACK={4}", entryPx, sp, tgt, (int)bearBarNo, barsBack));
                //    Print("│    " + sc);
                //    Print("│    " + tc);
                //    Print("│");
                //    bool saMCStopTargetSetDummy = false;
                //    FireSingleAtm(entryPx, sp, tgt, false, "SAMC",
                //        ref atmIdSAMC, ref ordIdSAMC, ref saMCActive,
                //        ref stopSAMC, ref targetSAMC, ref saMCStopTargetSetDummy,
                //        () => { saMCCallbackOK = true; });
                //    UpdateBarSelectButtonColor(btnSAMC, BtnState3.Armed);
                //}

                // ── SA MC update — RETIRED ─────────────────────────────────────
                //if (saMCActive && !saMCFilled && saMCCallbackOK)
                //{
                //    double newEntry = Round(chanHigh + BBSAMC_EntryOffsetTicks * TickSize);
                //    if (Math.Abs(newEntry - lastSentSAMC) >= TickSize)
                //    {
                //        string[] st = GetAtmStrategyEntryOrderStatus(ordIdSAMC);
                //        if (st != null && st.Length > 2 && st[2] == "Working")
                //        {
                //            AtmStrategyChangeEntryOrder(newEntry, 0, ordIdSAMC);
                //            lastSentSAMC = newEntry;
                //            Print(DateTime.Now + " SA MC → " + newEntry);
                //        }
                //    }
                //}

                // ── SA BR — update price if initiated inside this MC ───────────
               for (int i = 0; i < atmIdsSABR.Count; i++)
                {
                    if (filledSABR[i] || !callbackSABR[i] || !inMCSABR[i]) continue;
                    int bAgo = barsAgoSABR[i];
                    if (bAgo < 0 || bAgo > CurrentBar) continue;
                    double newEntry = Round(BarsArray[0].GetHigh(BarsArray[0].Count - 1 - bAgo) + BBLSABR_EntryOffsetTicks * TickSize);
                    if (Math.Abs(newEntry - entriesSABR[i]) >= TickSize)
                    {
                        string[] st = GetAtmStrategyEntryOrderStatus(ordIdsSABR[i]);
                        if (st != null && st.Length > 2 && st[2] == "Working")
                        {
                            AtmStrategyChangeEntryOrder(newEntry, 0, ordIdsSABR[i]);
                            entriesSABR[i] = newEntry;
                            Print(DateTime.Now + " SA BR #" + i + " → " + newEntry);
                        }
                    }
                }
                // ── PB target updates for unfilled legs ───────────────────────
                if (s33Active && !s33StopTargetSet && s33CallbackOK)
                {
                    string tc; double newTgt = CalcTarget(PB33TargetMode, PB33RMultiple, PB33TargetOffsetTicks, entryS33, stopS33, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                    if (Math.Abs(newTgt - targetS33) >= TickSize) { Print(string.Format("│  ⚡ S33 TARGET UPDATED {0}  (was {1}) [MC_BEAR={2} BARS_BACK={3}]", newTgt, targetS33, (int)bearBarNo, barsBack)); targetS33 = newTgt; s33TgtCalc = tc; }
                }
                if (s50Active && !s50StopTargetSet && s50CallbackOK)
                {
                    string tc; double newTgt = CalcTarget(PB50TargetMode, PB50RMultiple, PB50TargetOffsetTicks, entryS50, stopS50, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                    if (Math.Abs(newTgt - targetS50) >= TickSize) { Print(string.Format("│  ⚡ S50 TARGET UPDATED {0}  (was {1}) [MC_BEAR={2} BARS_BACK={3}]", newTgt, targetS50, (int)bearBarNo, barsBack)); targetS50 = newTgt; s50TgtCalc = tc; }
                }
                if (s66Active && !s66StopTargetSet && s66CallbackOK)
                {
                    string tc; double newTgt = CalcTarget(PB66TargetMode, PB66RMultiple, PB66TargetOffsetTicks, entryS66, stopS66, chanHigh, chanLow, activeChanBarsShort, false, (int)bearBarNo, barsBack, out tc);
                    if (Math.Abs(newTgt - targetS66) >= TickSize) { Print(string.Format("│  ⚡ S66 TARGET UPDATED {0}  (was {1}) [MC_BEAR={2} BARS_BACK={3}]", newTgt, targetS66, (int)bearBarNo, barsBack)); targetS66 = newTgt; s66TgtCalc = tc; }
                }

                // ── Update unfilled PB entry order prices ─────────────────────
                if ((pb33 > 0 || pb50 > 0 || pb66 > 0) && shortOrdersPlaced
                    && s33CallbackOK && s50CallbackOK && s66CallbackOK)
                    UpdateShortPBOrders(pb33, pb50, pb66);
            }
            else
            {
                // Bear ended
                if (prevBearBarNo != 999 && activeChanLowShort > 0)
                {
                    cancelWatchLowShort = activeChanLowShort;
                    boXTRLastChanHighShort = activeChanHighShort;
                    closesOutsideShortCount = 0;
                    // SA MC — cancel if still unfilled when MC ends
                    if (saMCActive && !saMCFilled && !string.IsNullOrEmpty(ordIdSAMC))
                    { AtmStrategyCancelEntryOrder(ordIdSAMC); saMCActive = false; saMCCallbackOK = false; Print(DateTime.Now + " SA MC unfilled — MC ended, order cancelled"); UpdateBarSelectButtonColor(btnSAMC, BtnState3.Off); }
                    // BO XTR — place sell stop at channel low when MC ends
                    if (UseBO_XTR && !boXTRActive && cancelWatchLowShort > 0)
                        FireBOXTR(false, boXTRLastChanHighShort, cancelWatchLowShort);
                }
                boXTRLastChanHighShort = activeChanHighShort;
                prevBearBarNo       = 999;
                activeChanHighShort = activeChanLowShort = 0;
                activePB33Short     = activePB50Short = activePB66Short = 0;
                activeChanBarsShort = 0;

                // Cancel watch — PB shorts
                if (EnableCancelWatch && cancelWatchLowShort > 0 && shortOrdersPlaced
                    && (s33Active && !s33StopTargetSet || s50Active && !s50StopTargetSet || s66Active && !s66StopTargetSet))
                {
                    if (Close[0] < cancelWatchLowShort)
                    {
                        closesOutsideShortCount++;
                        Print(string.Format("{0} CANCEL WATCH SHORT | close={1} < extreme={2} | count={3}/{4}",
                            DateTime.Now, Close[0], cancelWatchLowShort, closesOutsideShortCount, ClosesOutsideToCancel));
                        if (closesOutsideShortCount >= ClosesOutsideToCancel)
                        {
                            if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) { AtmStrategyCancelEntryOrder(ordIdS33); s33Active = false; }
                            if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) { AtmStrategyCancelEntryOrder(ordIdS50); s50Active = false; }
                            if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) { AtmStrategyCancelEntryOrder(ordIdS66); s66Active = false; }
                            cancelWatchLockedShort  = false;
                            cancelWatchLowShort     = 0;
                            closesOutsideShortCount = 0;
                            shortOrdersPlaced       = false;
                            atmIdS33 = atmIdS50 = atmIdS66 = ordIdS33 = ordIdS50 = ordIdS66 = string.Empty;
                            lastSentS33 = lastSentS50 = lastSentS66 = 0;
                            s33CallbackOK = s50CallbackOK = s66CallbackOK = false;
                            pb33Armed = AutoReArm; pb50Armed = AutoReArm; pb66Armed = AutoReArm;
                            allPBsArmed = AutoReArm;
                            SetPBButtonColors();
                            Print(DateTime.Now + " CANCEL WATCH SHORT — cancelled unfilled PB orders, " + (AutoReArm ? "re-armed for next MC" : "PBs disarmed") + " | pb33Armed=" + pb33Armed + " pb50Armed=" + pb50Armed + " pb66Armed=" + pb66Armed);
                        }
                    }
                    else closesOutsideShortCount = 0;
                }

               // Cancel watch — SA BR unfilled orders initiated inside MC that just ended
                if (EnableCancelWatch && cancelWatchLowShort > 0 && Close[0] < cancelWatchLowShort)
                {
                    for (int i = atmIdsSABR.Count - 1; i >= 0; i--)
                    {
                        if (filledSABR[i] || !inMCSABR[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsSABR[i])) AtmStrategyCancelEntryOrder(ordIdsSABR[i]);
                        atmIdsSABR.RemoveAt(i); ordIdsSABR.RemoveAt(i); stopsSABR.RemoveAt(i);
                        targetsSABR.RemoveAt(i); entriesSABR.RemoveAt(i); filledSABR.RemoveAt(i);
                        callbackSABR.RemoveAt(i); stopCalcsSABR.RemoveAt(i); tgtCalcsSABR.RemoveAt(i);
                        barsAgoSABR.RemoveAt(i); inMCSABR.RemoveAt(i);
                        Print(DateTime.Now + " SA BR #" + i + " cancel watch — cancelled");
                    }
                    UpdateLmtButtonLabel(btnSABR, atmIdsSABR, "SABR");
                }
            }

         // ── Cache swing values for bar-select entries ─────────────────────
			if (!double.IsNaN(swingBBLSABR.SwingLow[0])  && swingBBLSABR.SwingLow[0]  > 0) { if (lastSwingLowsBBLSABR.Count  == 0 || swingBBLSABR.SwingLow[0]  != lastSwingLowsBBLSABR[0])  lastSwingLowsBBLSABR.Insert(0,  swingBBLSABR.SwingLow[0]);  }
			if (!double.IsNaN(swingBBLSABR.SwingHigh[0]) && swingBBLSABR.SwingHigh[0] > 0) { if (lastSwingHighsBBLSABR.Count == 0 || swingBBLSABR.SwingHigh[0] != lastSwingHighsBBLSABR[0]) lastSwingHighsBBLSABR.Insert(0, swingBBLSABR.SwingHigh[0]); }
			if (!double.IsNaN(swingSE.SwingLow[0])        && swingSE.SwingLow[0]        > 0) { if (lastSwingLowsSE.Count        == 0 || swingSE.SwingLow[0]        != lastSwingLowsSE[0])        lastSwingLowsSE.Insert(0,        swingSE.SwingLow[0]);        }
			if (!double.IsNaN(swingSE.SwingHigh[0])       && swingSE.SwingHigh[0]       > 0) { if (lastSwingHighsSE.Count       == 0 || swingSE.SwingHigh[0]       != lastSwingHighsSE[0])       lastSwingHighsSE.Insert(0,       swingSE.SwingHigh[0]);       }
			if (!double.IsNaN(swingSpeedo.SwingLow[0])    && swingSpeedo.SwingLow[0]    > 0) { if (lastSwingLowsSpeedo.Count    == 0 || swingSpeedo.SwingLow[0]    != lastSwingLowsSpeedo[0])    lastSwingLowsSpeedo.Insert(0,    swingSpeedo.SwingLow[0]);    }
			if (!double.IsNaN(swingSpeedo.SwingHigh[0])   && swingSpeedo.SwingHigh[0]   > 0) { if (lastSwingHighsSpeedo.Count   == 0 || swingSpeedo.SwingHigh[0]   != lastSwingHighsSpeedo[0])   lastSwingHighsSpeedo.Insert(0,   swingSpeedo.SwingHigh[0]);   }

            UpdatePBButtonColors();
        }
        

       // ── ATM FILL DETECTION — 1-sec bar ────────────────────────────────────
        private void CheckAtmFills()
        {
            bool anyChanged = false;
            anyChanged |= CheckAtmLeg(ref l33Active, ref l33StopTargetSet, ref l33StopTargetPrinted, ref l33CallbackOK, atmIdL33, stopL33, targetL33, "L33", l33StopCalc, l33TgtCalc);
            anyChanged |= CheckAtmLeg(ref l50Active, ref l50StopTargetSet, ref l50StopTargetPrinted, ref l50CallbackOK, atmIdL50, stopL50, targetL50, "L50", l50StopCalc, l50TgtCalc);
            anyChanged |= CheckAtmLeg(ref l66Active, ref l66StopTargetSet, ref l66StopTargetPrinted, ref l66CallbackOK, atmIdL66, stopL66, targetL66, "L66", l66StopCalc, l66TgtCalc);
            anyChanged |= CheckAtmLeg(ref s33Active, ref s33StopTargetSet, ref s33StopTargetPrinted, ref s33CallbackOK, atmIdS33, stopS33, targetS33, "S33", s33StopCalc, s33TgtCalc);
            anyChanged |= CheckAtmLeg(ref s50Active, ref s50StopTargetSet, ref s50StopTargetPrinted, ref s50CallbackOK, atmIdS50, stopS50, targetS50, "S50", s50StopCalc, s50TgtCalc);
            anyChanged |= CheckAtmLeg(ref s66Active, ref s66StopTargetSet, ref s66StopTargetPrinted, ref s66CallbackOK, atmIdS66, stopS66, targetS66, "S66", s66StopCalc, s66TgtCalc);
            anyChanged |= CheckAtmLegSimple(ref bbMCActive,  ref bbMCFilled,  ref bbMCCallbackOK,  atmIdBBMC,  stopBBMC,  targetBBMC,  entryBBMC,  "BBMC",   bbMCStopCalc,  bbMCTgtCalc,  btnBBMC);
            anyChanged |= CheckAtmLegSimple(ref saMCActive,  ref saMCFilled,  ref saMCCallbackOK,  atmIdSAMC,  stopSAMC,  targetSAMC,  entrySAMC,  "SAMC",   saMCStopCalc,  saMCTgtCalc,  btnSAMC);
           anyChanged |= CheckAtmLegMulti(atmIdsBBBL, ordIdsBBBL, stopsBBBL, targetsBBBL, entriesBBBL, filledBBBL, callbackBBBL, stopCalcsBBBL, tgtCalcsBBBL, true,  "BBBL", btnBBBL);
            anyChanged |= CheckAtmLegMulti(atmIdsSABR, ordIdsSABR, stopsSABR, targetsSABR, entriesSABR, filledSABR, callbackSABR, stopCalcsSABR, tgtCalcsSABR, false, "SABR", btnSABR);
            anyChanged |= CheckAtmLegMulti(atmIdsSEL,  ordIdsSEL,  stopsSEL,  targetsSEL,  entriesSEL,  filledSEL,  callbackSEL,  stopCalcsSEL,  tgtCalcsSEL,  true,  "SEL",  btnSEL);
            anyChanged |= CheckAtmLegMulti(atmIdsSES,  ordIdsSES,  stopsSES,  targetsSES,  entriesSES,  filledSES,  callbackSES,  stopCalcsSES,  tgtCalcsSES,  false, "SES",  btnSES);
          	anyChanged |= CheckAtmLegSimple(ref speedoActive, ref speedoFilled, ref speedoCallbackOK, atmIdSpeedo, stopSpeedo, targetSpeedo, entrySpeedo, "SPEEDO", speedoStopCalc, speedoTgtCalc, btnSpeedo);
            // BOXTR CheckAtmLegSimple removed — BO XTR temporarily disabled
            anyChanged |= CheckAtmLegMulti(atmIdsLmtBuy,  ordIdsLmtBuy,  stopsLmtBuy,  targetsLmtBuy,  entriesLmtBuy,  filledLmtBuy,  callbackLmtBuy,  stopCalcsLmtBuy,  tgtCalcsLmtBuy,  true,  "LmtBuy",  btnLmtBuy);
            anyChanged |= CheckAtmLegMulti(atmIdsLmtSell, ordIdsLmtSell, stopsLmtSell, targetsLmtSell, entriesLmtSell, filledLmtSell, callbackLmtSell, stopCalcsLmtSell, tgtCalcsLmtSell, false, "LmtSell", btnLmtSell);
           if (anyChanged) UpdatePBButtonColors();
        }

        private bool CheckAtmLeg(ref bool active, ref bool stopTargetSet, ref bool stopTargetPrinted,
            ref bool callbackOK, string atmId, double stopPrice, double targetPrice, string legName,
            string stopCalc, string tgtCalc)
        {
            if (!active || string.IsNullOrEmpty(atmId) || !callbackOK) return false;
            MarketPosition pos = GetAtmStrategyMarketPosition(atmId);
           if (stopTargetSet && pos == MarketPosition.Flat)
{
    double entryPx = legName == "L33" ? entryL33 : legName == "L50" ? entryL50 : legName == "L66" ? entryL66 :
                     legName == "S33" ? entryS33 : legName == "S50" ? entryS50 : entryS66;
    bool   isLong  = legName.StartsWith("L");
    double exitPx  = legName == "L33" ? exitPriceL33 : legName == "L50" ? exitPriceL50 : legName == "L66" ? exitPriceL66 :
                     legName == "S33" ? exitPriceS33 : legName == "S50" ? exitPriceS50 : exitPriceS66;
    string exitTyp = legName == "L33" ? exitTypeL33  : legName == "L50" ? exitTypeL50  : legName == "L66" ? exitTypeL66  :
                     legName == "S33" ? exitTypeS33  : legName == "S50" ? exitTypeS50  : exitTypeS66;
    if (exitPx <= 0)
{
    // Determine exit by proximity to stop vs target
    double distToStop   = Math.Abs(Close[0] - stopPrice);
    double distToTarget = Math.Abs(Close[0] - targetPrice);
    bool   hitTarget    = distToTarget <= distToStop;
    exitPx  = hitTarget ? targetPrice : stopPrice;
    exitTyp = hitTarget ? "TARGET" : "STOP";
    if (lastExitSource != "ATM") { exitPx = lastExitSource == "TARGET" ? targetPrice : stopPrice; exitTyp = lastExitSource; }
}
    double pnlPts  = isLong ? (exitPx - entryPx) : (entryPx - exitPx);
    string source  = lastExitSource == "ATM" ? (exitTyp ?? "ATM") : lastExitSource;
    Print("╠══════════════════════════════════════════════════════════════════════╣");
    Print(string.Format("│  $ {0} CLOSED", legName));
    Print(string.Format("│    SOURCE : {0}", source));
    Print(string.Format("│    ENTRY  : {0}", entryPx));
    Print(string.Format("│    EXIT   : {0}", exitPx));
    Print(string.Format("│    PnL    : {0:+0.00;-0.00} pts", pnlPts));
    Print("╚══════════════════════════════════════════════════════════════════════╝");
    if (legName == "L33") { exitPriceL33 = 0; exitTypeL33 = null; }
    else if (legName == "L50") { exitPriceL50 = 0; exitTypeL50 = null; }
    else if (legName == "L66") { exitPriceL66 = 0; exitTypeL66 = null; }
    else if (legName == "S33") { exitPriceS33 = 0; exitTypeS33 = null; }
    else if (legName == "S50") { exitPriceS50 = 0; exitTypeS50 = null; }
    else if (legName == "S66") { exitPriceS66 = 0; exitTypeS66 = null; }
    lastExitSource    = "ATM";
    active            = false;
    stopTargetSet     = false;
    stopTargetPrinted = false;
    return true;
}
            if (!stopTargetSet && pos == MarketPosition.Flat) return false;
            if (stopTargetSet && stopTargetPrinted) return false;
            string[,] stopOrders   = GetAtmStrategyStopTargetOrderStatus("Stop1",   atmId);
            string[,] targetOrders = GetAtmStrategyStopTargetOrderStatus("Target1", atmId);
            if (stopOrders == null || stopOrders.Length == 0 || targetOrders == null || targetOrders.Length == 0) return false;
          double fillPrice = GetAtmStrategyPositionAveragePrice(atmId);
double risk      = Math.Abs(fillPrice - stopPrice);
// Recalc target from actual fill price
double recalcTarget = targetPrice;
if (fillPrice > 0 && Math.Abs(fillPrice - (legName.StartsWith("L") ? fillPrice - risk : fillPrice + risk)) > TickSize)
{
    // Determine direction from legName
    bool isLong = legName.StartsWith("L");
    if (isLong)
        recalcTarget = Round(fillPrice + (targetPrice - (fillPrice + risk - stopPrice)));
    else
        recalcTarget = Round(fillPrice - risk); // R=1 recalc from actual fill
}
// Use a simpler direct recalc: preserve the R structure from original calc
// Original target was based on entryPx; shift by fill slippage
double slippage = fillPrice - (legName.StartsWith("L") ? fillPrice : fillPrice); // placeholder
// Cleanest approach: shift target by same amount entry moved
double entryShift = fillPrice - (legName.StartsWith("L") ?
    (legName == "L33" ? entryL33 : legName == "L50" ? entryL50 : entryL66) :
    (legName == "S33" ? entryS33 : legName == "S50" ? entryS50 : entryS66));
recalcTarget = Round(targetPrice + entryShift);

bool stopMoved   = AtmStrategyChangeStopTarget(0,             stopPrice,     "Stop1",   atmId);
bool targetMoved = AtmStrategyChangeStopTarget(recalcTarget,  0,             "Target1", atmId);
if (!stopTargetPrinted)
{
    Print(string.Format("│  ✔ {0} FILLED  STOP={1} moved={2}  TARGET={3} moved={4}  fillPrice={5} entryShift={6}", legName, stopPrice, stopMoved, recalcTarget, targetMoved, fillPrice, entryShift));
    Print("│    " + stopCalc);
    Print("│    " + tgtCalc);
    if (!(stopMoved && targetMoved)) Print("│  ✘ WARNING — one or both moves returned false");
    stopTargetPrinted = true;
}
stopTargetSet = true;
return true;
        }

        // ── Simplified ATM leg checker for bar-select entries (no stopTargetSet flag pattern) ──
        private bool CheckAtmLegSimple(ref bool active, ref bool filled, ref bool callbackOK,
            string atmId, double stopPrice, double targetPrice, double entryPrice, string legName,
            string stopCalc, string tgtCalc, Button btn)
        {
            if (!active || string.IsNullOrEmpty(atmId)) return false;
            if (!callbackOK && !filled) return false;
            MarketPosition pos = GetAtmStrategyMarketPosition(atmId);

            // Check for fill
            if (!filled && (pos == MarketPosition.Long || pos == MarketPosition.Short))
            {
                string[,] stopOrders   = GetAtmStrategyStopTargetOrderStatus("Stop1",   atmId);
                string[,] targetOrders = GetAtmStrategyStopTargetOrderStatus("Target1", atmId);
                if (stopOrders != null && stopOrders.Length > 0 && targetOrders != null && targetOrders.Length > 0)
                {
                    bool sm = AtmStrategyChangeStopTarget(0, stopPrice, "Stop1", atmId);
                    bool tm = AtmStrategyChangeStopTarget(targetPrice, 0, "Target1", atmId);
                  double fillPrice   = GetAtmStrategyPositionAveragePrice(atmId);
                    double slippage    = fillPrice - entryPrice;
                    int    slipTicks   = (int)Math.Round(Math.Abs(slippage) / TickSize);
                    bool   exactFill   = Math.Abs(slippage) < TickSize;
                    string fillMark    = exactFill ? "✔" : "✗";
                    string slipStr     = exactFill ? "exact" : string.Format("slippage {0}{1}t", slippage > 0 ? "+" : "-", slipTicks);
                    Print("");
                    Print(string.Format("│  ✔ {0} FILLED", legName));
                    Print(string.Format("│    FILL     = {0} {1} {2}", fillPrice, fillMark, slipStr));
                    Print(string.Format("│    PROPOSED = {0}", entryPrice));
                    Print(string.Format("│    STOP     = {0} {1}", stopPrice, sm ? "✔" : "✗ move failed"));
                    Print(string.Format("│    TARGET   = {0} {1}", targetPrice, tm ? "✔" : "✗ move failed"));
                    Print("│    ── stop calc ──");
                    Print("│    " + stopCalc);
                    Print("│    ── target calc ──");
                    Print("│    " + tgtCalc);
                    Print("");
                    filled = true;
                    if (btn != null) UpdateBarSelectButtonColor(btn, BtnState3.Filled);
                    return true;
                }
            }

            // Check for close
            if (filled && pos == MarketPosition.Flat)
            {
                Print("╠══════════════════════════════════════════════════════════════════════╣");
                Print(string.Format("│  $ {0} CLOSED  SOURCE={1}", legName, lastExitSource));
                Print(string.Format("│    ENTRY={0}  STOP={1}  TARGET={2}", entryPrice, stopPrice, targetPrice));
                Print("╚══════════════════════════════════════════════════════════════════════╝");
                lastExitSource = "ATM";
                active         = false;
                filled         = false;
                callbackOK     = false;
               if (btn != null) UpdateBarSelectButtonColor(btn, BtnState3.Off);
                ResetSubButtonsForLeg(legName);
                return true;
            }
            return false;
        }
		
		private bool CheckAtmLegMulti(
            List<string> atmIds, List<string> ordIds,
            List<double> stops, List<double> targets, List<double> entries,
            List<bool> filled, List<bool> callbacks,
            List<string> stopCalcs, List<string> tgtCalcs,
            bool isLong, string legName, Button btn)
        {
            bool anyChanged = false;
            for (int i = atmIds.Count - 1; i >= 0; i--)
            {
                if (string.IsNullOrEmpty(atmIds[i]) || !callbacks[i]) continue;
                MarketPosition pos = GetAtmStrategyMarketPosition(atmIds[i]);

                // Fill detection
                if (!filled[i] && (pos == MarketPosition.Long || pos == MarketPosition.Short))
                {
                    string[,] stopOrders   = GetAtmStrategyStopTargetOrderStatus("Stop1",   atmIds[i]);
                    string[,] targetOrders = GetAtmStrategyStopTargetOrderStatus("Target1", atmIds[i]);
                    if (stopOrders != null && stopOrders.Length > 0 && targetOrders != null && targetOrders.Length > 0)
                    {
                        bool sm = AtmStrategyChangeStopTarget(0, stops[i], "Stop1", atmIds[i]);
                        bool tm = AtmStrategyChangeStopTarget(targets[i], 0, "Target1", atmIds[i]);
                        double fillPrice = GetAtmStrategyPositionAveragePrice(atmIds[i]);
                        double slippage  = fillPrice - entries[i];
                        int    slipTicks = (int)Math.Round(Math.Abs(slippage) / TickSize);
                        bool   exact     = Math.Abs(slippage) < TickSize;
                        Print(string.Format("│  ✔ {0} #{1} FILLED", legName, i));
                        Print(string.Format("│    FILL     = {0} {1}", fillPrice, exact ? "✔ exact" : string.Format("✗ slippage {0}{1}t", slippage > 0 ? "+" : "-", slipTicks)));
                        Print(string.Format("│    PROPOSED = {0}", entries[i]));
                        Print(string.Format("│    STOP     = {0} {1}", stops[i], sm ? "✔" : "✗"));
                        Print(string.Format("│    TARGET   = {0} {1}", targets[i], tm ? "✔" : "✗"));
                        Print("│    " + stopCalcs[i]);
                        Print("│    " + tgtCalcs[i]);
                        filled[i] = true;
                        anyChanged = true;
                        UpdateLmtButtonLabel(btn, atmIds, legName);
                    }
                }

                // Close detection
                if (filled[i] && pos == MarketPosition.Flat)
                {
                    double entryPx      = entries[i];
                    double distToStop   = Math.Abs(Close[0] - stops[i]);
                    double distToTarget = Math.Abs(Close[0] - targets[i]);
                    bool   hitTarget    = distToTarget <= distToStop;
                    double exitPx       = hitTarget ? targets[i] : stops[i];
                    string exitTyp      = hitTarget ? "TARGET" : "STOP";
                    double pnl          = isLong ? (exitPx - entryPx) : (entryPx - exitPx);
                    Print("╠══════════════════════════════════════════════════════════════════════╣");
                    Print(string.Format("│  $ {0} #{1} CLOSED", legName, i));
                    Print(string.Format("│    SOURCE : {0}", exitTyp));
                    Print(string.Format("│    ENTRY  : {0}", entryPx));
                    Print(string.Format("│    EXIT   : {0}", exitPx));
                    Print(string.Format("│    PnL    : {0:+0.00;-0.00} pts", pnl));
                    Print("╚══════════════════════════════════════════════════════════════════════╝");
                    atmIds.RemoveAt(i);   ordIds.RemoveAt(i);
                    stops.RemoveAt(i);    targets.RemoveAt(i);
                    entries.RemoveAt(i);  filled.RemoveAt(i);
                    callbacks.RemoveAt(i); stopCalcs.RemoveAt(i); tgtCalcs.RemoveAt(i);
                    anyChanged = true;
                    UpdateLmtButtonLabel(btn, atmIds, legName);
                }
            }
            return anyChanged;
        }

        private void UpdateLmtButtonLabel(Button btn, List<string> atmIds, string legName)
        {
            if (btn == null || ChartControl == null) return;
            int    count    = atmIds.Count;
            string baseName = legName == "LmtBuy"  ? LblLmtBuy  :
                              legName == "LmtSell" ? LblLmtSell :
                              legName == "BBBL"    ? LblBBBL    :
                              legName == "SABR"    ? LblSABR    :
                              legName == "SEL"     ? LblSEL     :
                              legName == "SES"     ? LblSES     : legName;
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                if (btn == null) return;
                if (count > 0)
                {
                    btn.Content    = string.Format("{0} ({1})", baseName, count);
                    btn.Background = new SolidColorBrush(ColorFilled);
                    btn.Foreground = Brushes.Black;
                }
                else
                {
                    btn.Content    = baseName;
                    btn.Background = new SolidColorBrush(ColorStrategyOff);
                    btn.Foreground = Brushes.White;
                }
            }));
        }

        // ── MANUAL STOP/TARGET MOVE DETECTION ─────────────────────────────────
        protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice,
            int quantity, int filled, double averageFillPrice,
            OrderState orderState, DateTime time, ErrorCode error, string nativeError)
        {
            if (!isRealtime) return;
            if (orderState != OrderState.Accepted && orderState != OrderState.Working) return;
            CheckManualMove(order, stopPrice,  "Stop1",   "L33",    ref stopL33,    atmIdL33,    l33StopTargetSet);
            CheckManualMove(order, stopPrice,  "Stop1",   "L50",    ref stopL50,    atmIdL50,    l50StopTargetSet);
            CheckManualMove(order, stopPrice,  "Stop1",   "L66",    ref stopL66,    atmIdL66,    l66StopTargetSet);
            CheckManualMove(order, stopPrice,  "Stop1",   "S33",    ref stopS33,    atmIdS33,    s33StopTargetSet);
            CheckManualMove(order, stopPrice,  "Stop1",   "S50",    ref stopS50,    atmIdS50,    s50StopTargetSet);
            CheckManualMove(order, stopPrice,  "Stop1",   "S66",    ref stopS66,    atmIdS66,    s66StopTargetSet);
            CheckManualMove(order, stopPrice,  "Stop1",   "BBMC",   ref stopBBMC,   atmIdBBMC,   bbMCFilled);
            CheckManualMove(order, stopPrice,  "Stop1",   "SAMC",   ref stopSAMC,   atmIdSAMC,   saMCFilled);
            CheckManualMove(order, stopPrice,  "Stop1",   "SPEEDO", ref stopSpeedo, atmIdSpeedo, speedoFilled);
            CheckManualMove(order, limitPrice, "Target1", "L33",    ref targetL33,    atmIdL33,    l33StopTargetSet);
            CheckManualMove(order, limitPrice, "Target1", "L50",    ref targetL50,    atmIdL50,    l50StopTargetSet);
            CheckManualMove(order, limitPrice, "Target1", "L66",    ref targetL66,    atmIdL66,    l66StopTargetSet);
            CheckManualMove(order, limitPrice, "Target1", "S33",    ref targetS33,    atmIdS33,    s33StopTargetSet);
            CheckManualMove(order, limitPrice, "Target1", "S50",    ref targetS50,    atmIdS50,    s50StopTargetSet);
            CheckManualMove(order, limitPrice, "Target1", "S66",    ref targetS66,    atmIdS66,    s66StopTargetSet);
            CheckManualMove(order, limitPrice, "Target1", "BBMC",   ref targetBBMC,   atmIdBBMC,   bbMCFilled);
            CheckManualMove(order, limitPrice, "Target1", "SAMC",   ref targetSAMC,   atmIdSAMC,   saMCFilled);
            CheckManualMove(order, limitPrice, "Target1", "SPEEDO", ref targetSpeedo, atmIdSpeedo, speedoFilled);
        }
	
		protected override void OnExecutionUpdate(Execution execution, string executionId,
    double price, int quantity, MarketPosition marketPosition,
    string orderId, DateTime time)
{
    if (!isRealtime) return;
    if (execution == null || execution.Order == null) return;
    bool isExit = execution.Order.OrderAction == OrderAction.Sell ||
                  execution.Order.OrderAction == OrderAction.BuyToCover;
    if (!isExit) return;
  string exitType = execution.Order.OrderType == OrderType.Limit     ? "TARGET" :
                  execution.Order.OrderType == OrderType.StopMarket ? "STOP"   :
                  execution.Order.OrderType == OrderType.StopLimit  ? "STOP"   : "MARKET";
Print(DateTime.Now + " OnExecutionUpdate EXIT | price=" + price + " type=" + exitType + " action=" + execution.Order.OrderAction + " orderType=" + execution.Order.OrderType);
    if (l33StopTargetSet  && !string.IsNullOrEmpty(atmIdL33)  && GetAtmStrategyMarketPosition(atmIdL33)  == MarketPosition.Flat && exitPriceL33  == 0) { exitPriceL33  = price; exitTypeL33  = exitType; }
    if (l50StopTargetSet  && !string.IsNullOrEmpty(atmIdL50)  && GetAtmStrategyMarketPosition(atmIdL50)  == MarketPosition.Flat && exitPriceL50  == 0) { exitPriceL50  = price; exitTypeL50  = exitType; }
    if (l66StopTargetSet  && !string.IsNullOrEmpty(atmIdL66)  && GetAtmStrategyMarketPosition(atmIdL66)  == MarketPosition.Flat && exitPriceL66  == 0) { exitPriceL66  = price; exitTypeL66  = exitType; }
    if (s33StopTargetSet  && !string.IsNullOrEmpty(atmIdS33)  && GetAtmStrategyMarketPosition(atmIdS33)  == MarketPosition.Flat && exitPriceS33  == 0) { exitPriceS33  = price; exitTypeS33  = exitType; }
    if (s50StopTargetSet  && !string.IsNullOrEmpty(atmIdS50)  && GetAtmStrategyMarketPosition(atmIdS50)  == MarketPosition.Flat && exitPriceS50  == 0) { exitPriceS50  = price; exitTypeS50  = exitType; }
    if (s66StopTargetSet  && !string.IsNullOrEmpty(atmIdS66)  && GetAtmStrategyMarketPosition(atmIdS66)  == MarketPosition.Flat && exitPriceS66  == 0) { exitPriceS66  = price; exitTypeS66  = exitType; }
    if (bbMCFilled  && !string.IsNullOrEmpty(atmIdBBMC)  && GetAtmStrategyMarketPosition(atmIdBBMC)  == MarketPosition.Flat && exitPriceBBMC  == 0) { exitPriceBBMC  = price; exitTypeBBMC  = exitType; }
    if (saMCFilled  && !string.IsNullOrEmpty(atmIdSAMC)  && GetAtmStrategyMarketPosition(atmIdSAMC)  == MarketPosition.Flat && exitPriceSAMC  == 0) { exitPriceSAMC  = price; exitTypeSAMC  = exitType; }
    if (speedoFilled && !string.IsNullOrEmpty(atmIdSpeedo) && GetAtmStrategyMarketPosition(atmIdSpeedo) == MarketPosition.Flat && exitPriceSpeedo == 0) { exitPriceSpeedo = price; exitTypeSpeedo = exitType; }
}
		
		private void BackfillSwingCache()
{
    // Lists kept for OnBarUpdate live accumulation continuity only.
    // CalcStopBarSelect now uses swing[barsAgo] directly — no list needed.
    int lastBar = BarsArray[0].Count - 1;
    double prevShBBLSABR = 0, prevSlBBLSABR = 0;
    double prevShSE = 0, prevSlSE = 0;
    double prevShSpeedo = 0, prevSlSpeedo = 0;
    for (int i = 0; i <= lastBar; i++)
    {
        double sh = swingBBLSABR.SwingHigh.GetValueAt(i);
        double sl = swingBBLSABR.SwingLow.GetValueAt(i);
        if (!double.IsNaN(sh) && sh > 0 && sh != prevShBBLSABR) { lastSwingHighsBBLSABR.Insert(0, sh); prevShBBLSABR = sh; }
        if (!double.IsNaN(sl) && sl > 0 && sl != prevSlBBLSABR) { lastSwingLowsBBLSABR.Insert(0, sl);  prevSlBBLSABR = sl; }
        sh = swingSE.SwingHigh.GetValueAt(i); sl = swingSE.SwingLow.GetValueAt(i);
        if (!double.IsNaN(sh) && sh > 0 && sh != prevShSE) { lastSwingHighsSE.Insert(0, sh); prevShSE = sh; }
        if (!double.IsNaN(sl) && sl > 0 && sl != prevSlSE) { lastSwingLowsSE.Insert(0, sl);  prevSlSE = sl; }
        sh = swingSpeedo.SwingHigh.GetValueAt(i); sl = swingSpeedo.SwingLow.GetValueAt(i);
        if (!double.IsNaN(sh) && sh > 0 && sh != prevShSpeedo) { lastSwingHighsSpeedo.Insert(0, sh); prevShSpeedo = sh; }
        if (!double.IsNaN(sl) && sl > 0 && sl != prevSlSpeedo) { lastSwingLowsSpeedo.Insert(0, sl);  prevSlSpeedo = sl; }
    }
    Print("");
    Print(string.Format("{0} SWING BACKFILL — BBLSABR(str={1}) highs={2} lows={3} | SE(str={4}) highs={5} lows={6} | Speedo(str={7}) highs={8} lows={9}",
        DateTime.Now, BBLSABR_SwingStrength, lastSwingHighsBBLSABR.Count, lastSwingLowsBBLSABR.Count,
        SE_SwingStrength, lastSwingHighsSE.Count, lastSwingLowsSE.Count,
        Speedo_SwingStrength, lastSwingHighsSpeedo.Count, lastSwingLowsSpeedo.Count));
    Print("");
}
        private void CheckManualMove(Order order, double newPrice, string orderName,
            string legName, ref double storedPrice, string atmId, bool isFilledFlag)
        {
            if (!isFilledFlag || string.IsNullOrEmpty(atmId)) return;
            if (newPrice <= 0) return;
            if (Math.Abs(newPrice - storedPrice) < TickSize) return;
            string[,] orders = GetAtmStrategyStopTargetOrderStatus(orderName, atmId);
            if (orders == null || orders.Length == 0) return;
            bool isTarget = orderName == "Target1";
            Print(string.Format("│  ⚠ {0} MANUAL {1} MOVE {2}  (was {3})", legName, isTarget ? "TARGET" : "STOP", newPrice, storedPrice));
            storedPrice = newPrice;
        }

        // ── FIRE BO XTR ───────────────────────────────────────────────────────
        private void FireBOXTR(bool isLong, double chanHigh, double chanLow)
        {
            if (boXTRActive) return;
            if (isLong  && boXTRFilled && !boXTRIsLong) return;
            if (!isLong && boXTRFilled &&  boXTRIsLong) return;
            double entryPx = isLong
                ? Round(chanHigh + BOXTR_EntryOffsetTicks * TickSize)
                : Round(chanLow  - BOXTR_EntryOffsetTicks * TickSize);
            string sc, tc;
            double sp  = CalcStopBarSelect(BOXTR_StopMode, BOXTR_StopOffsetTicks, BOXTR_StopABRBars, BOXTR_StopABRMultiple, swingBOXTR, entryPx, chanHigh, chanLow, isLong, 0, out sc);
            double tgt = CalcTargetBarSelect(BOXTR_TargetMode, BOXTR_RMultiple, BOXTR_TargetOffsetTicks, entryPx, sp, chanHigh, chanLow, isLong, out tc);
            boXTRStopCalc = sc; boXTRTgtCalc = tc;
            entryBOXTR = entryPx; boXTRIsLong = isLong;
            boXTRChanHigh = chanHigh; boXTRChanLow = chanLow;
            Print("");
            Print(string.Format("│  ▶ BO XTR FIRED {0} entry={1} stop={2} target={3}", isLong ? "LONG" : "SHORT", entryPx, sp, tgt));
            Print("│    " + sc);
            Print("│    " + tc);
            bool dummy = false;
            FireSingleAtm(entryPx, sp, tgt, isLong, "BOXTR",
                ref atmIdBOXTR, ref ordIdBOXTR, ref boXTRActive,
                ref stopBOXTR, ref targetBOXTR, ref dummy,
                () => { boXTRCallbackOK = true; }, BOXTR_OrderType);
            if (btnBOXTR != null) UpdateBarSelectButtonColor(btnBOXTR, BtnState3.Armed);
        }

        // ── FIRE SINGLE ATM ───────────────────────────────────────────────────
        private void FireSingleAtm(double entryPrice, double stopPrice, double targetPrice,
            bool isLong, string legName,
            ref string atmId, ref string ordId, ref bool active,
            ref double storedStop, ref double storedTarget, ref bool stopTargetSet,
            Action onCallbackOK, OrderType orderType = OrderType.Limit)
        {
            storedStop    = stopPrice;
            storedTarget  = targetPrice;
            stopTargetSet = false;
            ordId = legName + "_ORD_" + GetAtmStrategyUniqueId();
            atmId = legName + "_ATM_" + GetAtmStrategyUniqueId();
            string capturedAtmId    = atmId;
            string capturedLegName  = legName;
            Action capturedCallback = onCallbackOK;
          Print("");
            Print(string.Format("{0} {1} AtmStrategyCreate() | entry={2} stop={3} target={4} template={5} orderType={6}",
                DateTime.Now, legName, entryPrice, stopPrice, targetPrice, AtmTemplateName, orderType));
            AtmStrategyCreate(
                isLong ? OrderAction.Buy : OrderAction.Sell,
                orderType,
                orderType == OrderType.StopMarket ? 0 : Round(entryPrice),
                orderType == OrderType.StopLimit  ? Round(entryPrice) : (orderType == OrderType.StopMarket ? Round(entryPrice) : 0),
                TimeInForce.Day,
                ordId, AtmTemplateName, capturedAtmId,
                (errCode, cbId) =>
                {
                    if (errCode == ErrorCode.NoError)
                    {
                        Print(string.Format("{0} {1} CALLBACK OK | cbId={2}", DateTime.Now, capturedLegName, cbId));
                        Print("");
                        capturedCallback?.Invoke();
                    }
                    else
                    {
                        Print(string.Format("{0} {1} CALLBACK FAILED | errCode={2}", DateTime.Now, capturedLegName, errCode));
                        Print("");
                    }
                });
            active = true;
        }

        // ── UPDATE LONG PB — only when price changed ───────────────────────────
        private void UpdateLongPBOrders(double pb33, double pb50, double pb66)
{
    if (l33Active && l33CallbackOK && pb33 > 0 && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33) && pb33 != lastSentL33)
    { string[] s = GetAtmStrategyEntryOrderStatus(ordIdL33); if (s != null && s.Length > 2 && s[2] == "Working") { double px = Round(pb33 + PB33EntryOffsetTicks * TickSize); AtmStrategyChangeEntryOrder(px, 0, ordIdL33); lastSentL33 = pb33; entryL33 = px; Print(DateTime.Now + " L33 → " + px); } }
    if (l50Active && l50CallbackOK && pb50 > 0 && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50) && pb50 != lastSentL50)
    { string[] s = GetAtmStrategyEntryOrderStatus(ordIdL50); if (s != null && s.Length > 2 && s[2] == "Working") { double px = Round(pb50 + PB50EntryOffsetTicks * TickSize); AtmStrategyChangeEntryOrder(px, 0, ordIdL50); lastSentL50 = pb50; entryL50 = px; Print(DateTime.Now + " L50 → " + px); } }
    if (l66Active && l66CallbackOK && pb66 > 0 && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66) && pb66 != lastSentL66)
    { string[] s = GetAtmStrategyEntryOrderStatus(ordIdL66); if (s != null && s.Length > 2 && s[2] == "Working") { double px = Round(pb66 + PB66EntryOffsetTicks * TickSize); AtmStrategyChangeEntryOrder(px, 0, ordIdL66); lastSentL66 = pb66; entryL66 = px; Print(DateTime.Now + " L66 → " + px); } }
}

        // ── UPDATE SHORT PB — only when price changed ──────────────────────────
        private void UpdateShortPBOrders(double pb33, double pb50, double pb66)
{
    if (s33Active && s33CallbackOK && pb33 > 0 && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33) && pb33 != lastSentS33)
    { string[] s = GetAtmStrategyEntryOrderStatus(ordIdS33); if (s != null && s.Length > 2 && s[2] == "Working") { double px = Round(pb33 - PB33EntryOffsetTicks * TickSize); AtmStrategyChangeEntryOrder(px, 0, ordIdS33); lastSentS33 = pb33; entryS33 = px; Print(DateTime.Now + " S33 → " + px); } }
    if (s50Active && s50CallbackOK && pb50 > 0 && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50) && pb50 != lastSentS50)
    { string[] s = GetAtmStrategyEntryOrderStatus(ordIdS50); if (s != null && s.Length > 2 && s[2] == "Working") { double px = Round(pb50 - PB50EntryOffsetTicks * TickSize); AtmStrategyChangeEntryOrder(px, 0, ordIdS50); lastSentS50 = pb50; entryS50 = px; Print(DateTime.Now + " S50 → " + px); } }
    if (s66Active && s66CallbackOK && pb66 > 0 && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66) && pb66 != lastSentS66)
    { string[] s = GetAtmStrategyEntryOrderStatus(ordIdS66); if (s != null && s.Length > 2 && s[2] == "Working") { double px = Round(pb66 - PB66EntryOffsetTicks * TickSize); AtmStrategyChangeEntryOrder(px, 0, ordIdS66); lastSentS66 = pb66; entryS66 = px; Print(DateTime.Now + " S66 → " + px); } }
}

        // ── STOP CALCULATION — updated with ABR mode ───────────────────────────
        private double CalcStop(StopMode mode, int offsetTicks,
            NinjaTrader.NinjaScript.Indicators.Swing swing,
            double entryPrice, double chanHigh, double chanLow, bool isLong,
            int mcBar, int barsBack, int abrBars, double abrMult,
            out string calc)
        {
            double offset = offsetTicks * TickSize;
            string mcTag  = string.Format("[MC_{0}={1} BARS_BACK={2}]", isLong ? "BULL" : "BEAR", mcBar, barsBack);
            double result;
            switch (mode)
            {
                case StopMode.ChanExtreme:
                    result = isLong ? Round(chanLow - offset) : Round(chanHigh + offset);
                    calc = string.Format("▶ {0} STOP {1}  {2} CHAN_EXTREME: {3}={4} - OFFSET={5} = {1}",
                        isLong ? "LONG" : "SHORT", result, mcTag, isLong ? "CHAN_LOW" : "CHAN_HIGH", isLong ? chanLow : chanHigh, offset);
                    return result;
                case StopMode.SwingPoint:
                    if (isLong)
                    {
                        for (int i = 0; i <= Math.Min(CurrentBar, 20); i++)
                        {
                            double sl = swing.SwingLow[i];
                            if (!double.IsNaN(sl) && sl < entryPrice)
                            {
                                if (i == 0 && Math.Abs(sl - Low[0]) < TickSize) continue;
                                result = Round(sl - offset);
                                calc = string.Format("▶ LONG STOP {0}  {1} SWING_POINT: SWING_LOW={2} - OFFSET={3} = {0} (BARS_AGO={4})", result, mcTag, sl, offset, i);
                                return result;
                            }
                        }
                        result = Round(chanLow - offset);
                        calc = string.Format("▶ LONG STOP {0}  {1} SWING_POINT: NO SWING — FALLBACK CHAN_LOW={2} - OFFSET={3} = {0}", result, mcTag, chanLow, offset);
                        return result;
                    }
                    else
                    {
                        for (int i = 0; i <= Math.Min(CurrentBar, 20); i++)
                        {
                            double sh = swing.SwingHigh[i];
                            if (!double.IsNaN(sh) && sh > entryPrice)
                            {
                                if (i == 0 && Math.Abs(sh - High[0]) < TickSize) continue;
                                result = Round(sh + offset);
                                calc = string.Format("▶ SHORT STOP {0}  {1} SWING_POINT: SWING_HIGH={2} + OFFSET={3} = {0} (BARS_AGO={4})", result, mcTag, sh, offset, i);
                                return result;
                            }
                        }
                        result = Round(chanHigh + offset);
                        calc = string.Format("▶ SHORT STOP {0}  {1} SWING_POINT: NO SWING — FALLBACK CHAN_HIGH={2} + OFFSET={3} = {0}", result, mcTag, chanHigh, offset);
                        return result;
                    }
                case StopMode.ABR:
                    double abr = CalcABR(abrBars) * abrMult;
                    result = isLong ? Round(entryPrice - abr - offset) : Round(entryPrice + abr + offset);
                    calc = string.Format("▶ {0} STOP {1}  {2} ABR: ENTRY={3} - ABR({4})x{5}={6} - OFFSET={7} = {1}",
                        isLong ? "LONG" : "SHORT", result, mcTag, entryPrice, abrBars, abrMult, CalcABR(abrBars) * abrMult, offset);
                    return result;
               case StopMode.SignalBar:
                    // SignalBar only valid for Speedo — fallback to ChanExtreme
                    result = isLong ? Round(chanLow - offset) : Round(chanHigh + offset);
                    calc = string.Format("▶ {0} STOP {1}  {2} SIGNALBAR→FALLBACK CHAN_EXTREME: {3}={4} OFFSET={5} = {1}",
                        isLong ? "LONG" : "SHORT", result, mcTag,
                        isLong ? "CHAN_LOW" : "CHAN_HIGH", isLong ? chanLow : chanHigh, offset);
                    return result;
             case StopMode.WeakReversalBar:
                // WRB stop calculated inline in Speedo OnBarUpdate — fallback to ChanExtreme
                result = isLong ? Round(chanLow - offset) : Round(chanHigh + offset);
                calc = string.Format("▶ {0} STOP {1}  WRB→FALLBACK CHAN_EXTREME OFFSET={2} = {1}",
                    isLong ? "LONG" : "SHORT", result, offset);
                return result;
                default:
                result = isLong ? Round(chanLow - offset) : Round(chanHigh + offset);
                calc = string.Format("▶ {0} STOP {1}  DEFAULT CHAN_EXTREME OFFSET={2} = {1}",
                    isLong ? "LONG" : "SHORT", result, offset);
                return result;
            }
        }

        // ── STOP CALCULATION — bar-select entries (uses clicked bar index) ─────
     private double CalcStopBarSelect(StopMode mode, int offsetTicks, int abrBars, double abrMult,
    NinjaTrader.NinjaScript.Indicators.Swing swing,
    double entryPrice, double chanHigh, double chanLow, bool isLong,
    int barsAgoSignalBar, out string calc)
{
    double offset = offsetTicks * TickSize;
    double result;
    int safeBAgo = Math.Max(0, Math.Min(barsAgoSignalBar, BarsArray[0].Count - 1));
    int barIdx   = BarsArray[0].Count - 1 - safeBAgo;
    double sigLow  = BarsArray[0].GetLow(barIdx);
    double sigHigh = BarsArray[0].GetHigh(barIdx);
    switch (mode)
    {
        case StopMode.ChanExtreme:
            if (chanHigh > 0 && chanLow > 0)
            {
                result = isLong ? Round(chanLow - offset) : Round(chanHigh + offset);
                calc = string.Format("▶ {0} STOP {1}  CHAN_EXTREME: {2}={3} OFFSET={4} = {1}",
                    isLong ? "LONG" : "SHORT", result, isLong ? "CHAN_LOW" : "CHAN_HIGH", isLong ? chanLow : chanHigh, offset);
                return result;
            }
            result = isLong ? Round(sigLow - offset) : Round(sigHigh + offset);
            calc = string.Format("▶ {0} STOP {1}  CHAN_EXTREME: no active MC — fallback SIGNAL_BAR {2} OFFSET={3} = {1}",
                isLong ? "LONG" : "SHORT", result, isLong ? sigLow : sigHigh, offset);
            return result;
        case StopMode.SignalBar:
            result = isLong ? Round(sigLow - offset) : Round(sigHigh + offset);
            calc = string.Format("▶ {0} STOP {1}  SIGNAL_BAR: {2}[{3}]={4} OFFSET={5} = {1}",
                isLong ? "LONG" : "SHORT", result, isLong ? "LOW" : "HIGH", safeBAgo,
                isLong ? sigLow : sigHigh, offset);
            return result;
			
   case StopMode.SwingPoint:
    // Use GetValueAt(absoluteBarIndex) — no 255 cap, works with infinite lookback.
    // Scan from current bar backwards to find the most recent confirmed swing
    // below entry (long) or above entry (short). Skip unconfirmed values by
    // deduplicating — each confirmed pivot repeats for SwingStrength bars.
			
    if (isLong)
    {
        var swingList = (swing == swingBBLSABR) ? lastSwingLowsBBLSABR :
                    (swing == swingSE)       ? lastSwingLowsSE       :
                                               lastSwingLowsSpeedo;
    foreach (double sl in swingList)
    {
        if (sl <= 0) continue;
        if (sl < entryPrice)
        {
            result = Round(sl - offset);
            calc = string.Format("▶ LONG STOP {0}  SWING_POINT: SwingLow={1} OFFSET={2} = {0}", result, sl, offset);
            return result;
        }
    }
    result = Round(sigLow - offset);
    calc = string.Format("▶ LONG STOP {0}  SWING_POINT: NO SWING BELOW ENTRY — FALLBACK SIG_BAR={1} OFFSET={2} = {0}", result, sigLow, offset);
    return result;
    }
   else
    {
        var swingList = (swing == swingBBLSABR) ? lastSwingHighsBBLSABR :
                    (swing == swingSE)       ? lastSwingHighsSE       :
                                               lastSwingHighsSpeedo;
    foreach (double sh in swingList)
    {
        if (sh <= 0) continue;
        if (sh > entryPrice)
        {
            result = Round(sh + offset);
            calc = string.Format("▶ SHORT STOP {0}  SWING_POINT: SwingHigh={1} OFFSET={2} = {0}", result, sh, offset);
            return result;
        }
    }
    result = Round(sigHigh + offset);
    calc = string.Format("▶ SHORT STOP {0}  SWING_POINT: NO SWING ABOVE ENTRY — FALLBACK SIG_BAR={1} OFFSET={2} = {0}", result, sigHigh, offset);
    return result;
    }
	
        case StopMode.ABR:
            double abr = CalcABR(abrBars) * abrMult;
            result = isLong ? Round(entryPrice - abr - offset) : Round(entryPrice + abr + offset);
            calc = string.Format("▶ {0} STOP {1}  ABR: ENTRY={2} ABR({3})x{4}={5} OFFSET={6} = {1}",
                isLong ? "LONG" : "SHORT", result, entryPrice, abrBars, abrMult, abr, offset);
            return result;
        default:
            result = isLong ? Round(sigLow - offset) : Round(sigHigh + offset);
            calc = string.Format("▶ {0} STOP {1}  DEFAULT SIGNAL_BAR OFFSET={2} = {1}",
                isLong ? "LONG" : "SHORT", result, offset);
            return result;
    }
}

        // ── TARGET CALCULATION ─────────────────────────────────────────────────
        private double CalcTarget(TargetMode mode, double rMultiple, int targetOffsetTicks,
            double entryPrice, double stopPrice,
            double chanHigh, double chanLow, int chanBars, bool isLong,
            int mcBar, int barsBack,
            out string calc)
        {
            double risk   = Math.Abs(entryPrice - stopPrice);
            double offset = targetOffsetTicks * TickSize;
            string mcTag  = string.Format("[MC_{0}={1} BARS_BACK={2}]", isLong ? "BULL" : "BEAR", mcBar, barsBack);
            double result;
            double r;
            switch (mode)
            {
                case TargetMode.ChanExtreme:
                    result = isLong ? Round(chanHigh - offset) : Round(chanLow + offset);
                    if (isLong  && result <= entryPrice) result = Round(entryPrice + TickSize);
                    if (!isLong && result >= entryPrice) result = Round(entryPrice - TickSize);
                    calc = string.Format("$ {0} TARGET {1}  {2} CE: {3}={4} OFFSET={5} = {1}", isLong ? "LONG" : "SHORT", result, mcTag, isLong ? "CHAN_HIGH" : "CHAN_LOW", isLong ? chanHigh : chanLow, offset);
                    return result;
                case TargetMode.RHalf:          r = 0.5;  goto RCalc;
                case TargetMode.RThreeQuarter:  r = 0.75; goto RCalc;
                case TargetMode.ROne:           r = 1.0;  goto RCalc;
                case TargetMode.ROneHalf:       r = 1.5;  goto RCalc;
                case TargetMode.RTwo:           r = 2.0;  goto RCalc;
                case TargetMode.RTwoHalf:       r = 2.5;  goto RCalc;
                case TargetMode.RThree:         r = 3.0;  goto RCalc;
                default:                        r = 1.0;  goto RCalc;
                RCalc:
                    result = isLong ? Round(entryPrice + risk * r - offset) : Round(entryPrice - risk * r + offset);
                    calc = string.Format("$ {0} TARGET {1}  {2} R={3}: ENTRY={4} RISK={5} x {3} OFFSET={6} = {1}", isLong ? "LONG" : "SHORT", result, mcTag, r, entryPrice, risk, offset);
                    return result;
            }
        }

        // ── TARGET CALCULATION — bar-select entries ────────────────────────────
        private double CalcTargetBarSelect(TargetMode mode, double rMultiple, int targetOffsetTicks,
    double entryPrice, double stopPrice, double chanHigh, double chanLow, bool isLong,
    out string calc)
{
    double offset = targetOffsetTicks * TickSize;
    double result;

    // If stop is invalid (<=0 or negative), use a default 8-tick risk for R calculation
    double rawRisk = Math.Abs(entryPrice - stopPrice);
    double risk    = (stopPrice <= 0 || rawRisk > entryPrice * 0.05)
                     ? 8 * TickSize
                     : rawRisk;
    bool riskCapped = (stopPrice <= 0 || rawRisk > entryPrice * 0.05);

    switch (mode)
    {
        case TargetMode.ROne:
            result = isLong ? Round(entryPrice + risk * rMultiple - offset) : Round(entryPrice - risk * rMultiple + offset);
            calc = string.Format("$ {0} TARGET {1}  R_MULTIPLE: ENTRY={2} RISK={3}{4} x R={5} OFFSET={6} = {1}",
                isLong ? "LONG" : "SHORT", result, entryPrice, risk,
                riskCapped ? "(CAPPED-invalid stop)" : "", rMultiple, offset);
            return result;
        case TargetMode.ChanExtreme:
            if (chanHigh > 0 && chanLow > 0)
            {
                result = isLong ? Round(chanHigh - offset) : Round(chanLow + offset);
                // Safety floor/ceiling: target must be better than entry
                if (isLong  && result <= entryPrice) result = Round(entryPrice + TickSize);
                if (!isLong && result >= entryPrice) result = Round(entryPrice - TickSize);
                calc = string.Format("$ {0} TARGET {1}  CHAN_EXTREME: {2}={3} OFFSET={4} = {1}",
                    isLong ? "LONG" : "SHORT", result, isLong ? "CHAN_HIGH" : "CHAN_LOW",
                    isLong ? chanHigh : chanLow, offset);
                return result;
            }
            // No active MC — fallback to capped R
            result = isLong ? Round(entryPrice + risk * rMultiple - offset) : Round(entryPrice - risk * rMultiple + offset);
            calc = string.Format("$ {0} TARGET {1}  CHAN_EXTREME: no active MC — fallback R({2}t) = {1}",
                isLong ? "LONG" : "SHORT", result, risk / TickSize);
            return result;
        default:
            result = isLong ? Round(entryPrice + risk * rMultiple - offset) : Round(entryPrice - risk * rMultiple + offset);
            calc = string.Format("$ {0} TARGET {1}  DEFAULT R_MULTIPLE RISK={2}{3} OFFSET={4} = {1}",
                isLong ? "LONG" : "SHORT", result, risk,
                riskCapped ? "(CAPPED)" : "", offset);
            return result;
    }
}

        // ── ABR helper ─────────────────────────────────────────────────────────
       private double CalcABR(int bars)
        {
            double sum = 0;
            int    cnt = Math.Min(bars, BarsArray[0].Count - 1);
            for (int i = 0; i < cnt; i++) sum += BarsArray[0].GetHigh(BarsArray[0].Count - 1 - i) - BarsArray[0].GetLow(BarsArray[0].Count - 1 - i);
            return cnt > 0 ? sum / cnt : 0;
        }

        // ── RESET helpers ──────────────────────────────────────────────────────
        private void ResetLongLegs()
        {
            if (!string.IsNullOrEmpty(ordIdL33) && l33Active && !l33StopTargetSet) AtmStrategyCancelEntryOrder(ordIdL33);
            if (!string.IsNullOrEmpty(ordIdL50) && l50Active && !l50StopTargetSet) AtmStrategyCancelEntryOrder(ordIdL50);
            if (!string.IsNullOrEmpty(ordIdL66) && l66Active && !l66StopTargetSet) AtmStrategyCancelEntryOrder(ordIdL66);
            l33Active = l50Active = l66Active = longOrdersPlaced = false;
            l33StopTargetSet = l50StopTargetSet = l66StopTargetSet = false;
            l33StopTargetPrinted = l50StopTargetPrinted = l66StopTargetPrinted = false;
            stopL33 = stopL50 = stopL66 = targetL33 = targetL50 = targetL66 = 0;
            entryL33 = entryL50 = entryL66 = 0;
            lastSentL33 = lastSentL50 = lastSentL66 = 0;
            atmIdL33 = atmIdL50 = atmIdL66 = ordIdL33 = ordIdL50 = ordIdL66 = string.Empty;
            l33StopCalc = l50StopCalc = l66StopCalc = "";
            l33TgtCalc  = l50TgtCalc  = l66TgtCalc  = "";
            l33CallbackOK = l50CallbackOK = l66CallbackOK = false;
            cancelWatchHighLong    = 0;
            closesOutsideLongCount = 0;
            ResetBBMCState();
        }

        private void ResetShortLegs()
        {
            if (!string.IsNullOrEmpty(ordIdS33) && s33Active && !s33StopTargetSet) AtmStrategyCancelEntryOrder(ordIdS33);
            if (!string.IsNullOrEmpty(ordIdS50) && s50Active && !s50StopTargetSet) AtmStrategyCancelEntryOrder(ordIdS50);
            if (!string.IsNullOrEmpty(ordIdS66) && s66Active && !s66StopTargetSet) AtmStrategyCancelEntryOrder(ordIdS66);
            s33Active = s50Active = s66Active = shortOrdersPlaced = false;
            s33StopTargetSet = s50StopTargetSet = s66StopTargetSet = false;
            s33StopTargetPrinted = s50StopTargetPrinted = s66StopTargetPrinted = false;
            stopS33 = stopS50 = stopS66 = targetS33 = targetS50 = targetS66 = 0;
            entryS33 = entryS50 = entryS66 = 0;
            lastSentS33 = lastSentS50 = lastSentS66 = 0;
            atmIdS33 = atmIdS50 = atmIdS66 = ordIdS33 = ordIdS50 = ordIdS66 = string.Empty;
            s33StopCalc = s50StopCalc = s66StopCalc = "";
            s33TgtCalc  = s50TgtCalc  = s66TgtCalc  = "";
            s33CallbackOK = s50CallbackOK = s66CallbackOK = false;
            cancelWatchLowShort     = 0;
            closesOutsideShortCount = 0;
            ResetSAMCState();
        }

        private void ResetBBMCState()
        {
            if (bbMCActive && !bbMCFilled && !string.IsNullOrEmpty(ordIdBBMC)) AtmStrategyCancelEntryOrder(ordIdBBMC);
            bbMCActive = bbMCFilled = bbMCCallbackOK = false;
            stopBBMC = targetBBMC = entryBBMC = lastSentBBMC = 0;
            atmIdBBMC = ordIdBBMC = string.Empty;
            bbMCStopCalc = bbMCTgtCalc = "";
            if (btnBBMC != null && !bbMCFilled) UpdateBarSelectButtonColor(btnBBMC, BtnState3.Off);
        }

        private void ResetSAMCState()
        {
            if (saMCActive && !saMCFilled && !string.IsNullOrEmpty(ordIdSAMC)) AtmStrategyCancelEntryOrder(ordIdSAMC);
            saMCActive = saMCFilled = saMCCallbackOK = false;
            stopSAMC = targetSAMC = entrySAMC = lastSentSAMC = 0;
            atmIdSAMC = ordIdSAMC = string.Empty;
            saMCStopCalc = saMCTgtCalc = "";
            if (btnSAMC != null && !saMCFilled) UpdateBarSelectButtonColor(btnSAMC, BtnState3.Off);
        }

        private void ResetBarSelectEntries()
        {
           // BB BL
            for (int i = 0; i < atmIdsBBBL.Count; i++)
                if (!filledBBBL[i] && !string.IsNullOrEmpty(ordIdsBBBL[i])) AtmStrategyCancelEntryOrder(ordIdsBBBL[i]);
            atmIdsBBBL.Clear(); ordIdsBBBL.Clear(); stopsBBBL.Clear(); targetsBBBL.Clear();
            entriesBBBL.Clear(); filledBBBL.Clear(); callbackBBBL.Clear(); stopCalcsBBBL.Clear(); tgtCalcsBBBL.Clear();
            barsAgoBBBL.Clear(); inMCBBBL.Clear();
            bbBLArmed = bbBLWaitingClick = bbBLInitiatedInMC = false; bbBLClickedBarsAgo = -1; bbBLLimitPrice = 0;
            // SA BR
            for (int i = 0; i < atmIdsSABR.Count; i++)
                if (!filledSABR[i] && !string.IsNullOrEmpty(ordIdsSABR[i])) AtmStrategyCancelEntryOrder(ordIdsSABR[i]);
            atmIdsSABR.Clear(); ordIdsSABR.Clear(); stopsSABR.Clear(); targetsSABR.Clear();
            entriesSABR.Clear(); filledSABR.Clear(); callbackSABR.Clear(); stopCalcsSABR.Clear(); tgtCalcsSABR.Clear();
            barsAgoSABR.Clear(); inMCSABR.Clear();
            saBRArmed = saBRWaitingClick = saBRInitiatedInMC = false; saBRClickedBarsAgo = -1; saBRLimitPrice = 0;
            // SE L
            for (int i = 0; i < atmIdsSEL.Count; i++)
                if (!filledSEL[i] && !string.IsNullOrEmpty(ordIdsSEL[i])) AtmStrategyCancelEntryOrder(ordIdsSEL[i]);
            atmIdsSEL.Clear(); ordIdsSEL.Clear(); stopsSEL.Clear(); targetsSEL.Clear();
            entriesSEL.Clear(); filledSEL.Clear(); callbackSEL.Clear(); stopCalcsSEL.Clear(); tgtCalcsSEL.Clear();
            seLArmed = seLWaitingClick = seLInitiatedInMC = false; seLClickedBarsAgo = -1; seLLimitPrice = 0;
            // SE S
            for (int i = 0; i < atmIdsSES.Count; i++)
                if (!filledSES[i] && !string.IsNullOrEmpty(ordIdsSES[i])) AtmStrategyCancelEntryOrder(ordIdsSES[i]);
            atmIdsSES.Clear(); ordIdsSES.Clear(); stopsSES.Clear(); targetsSES.Clear();
            entriesSES.Clear(); filledSES.Clear(); callbackSES.Clear(); stopCalcsSES.Clear(); tgtCalcsSES.Clear();
            seSArmed = seSWaitingClick = seSInitiatedInMC = false; seSClickedBarsAgo = -1; seSLimitPrice = 0;
           // BO XTR
            if (boXTRActive && !boXTRFilled && !string.IsNullOrEmpty(ordIdBOXTR)) AtmStrategyCancelEntryOrder(ordIdBOXTR);
            boXTRActive = boXTRFilled = boXTRCallbackOK = boXTRIsLong = false;
            stopBOXTR = targetBOXTR = entryBOXTR = boXTRChanHigh = boXTRChanLow = 0;
            atmIdBOXTR = ordIdBOXTR = string.Empty; boXTRStopCalc = boXTRTgtCalc = "";
            // Speedo
            if (speedoActive && !speedoFilled && !string.IsNullOrEmpty(ordIdSpeedo)) AtmStrategyCancelEntryOrder(ordIdSpeedo);
           speedoArmed = speedoWaitingClick = speedoWaitingBar = speedoWaitingImpulseClose = speedoActive = speedoFilled = speedoCallbackOK = speedoInitiatedInMC = false;
            speedoImpulseBarIndex = -1; speedoReversalBarIndex = -1; speedoOrderBarIndex = -1; speedoImpulseHigh = speedoImpulseLow = 0;
            speedoLimitPrice = stopSpeedo = targetSpeedo = entrySpeedo = 0;
            atmIdSpeedo = ordIdSpeedo = string.Empty; speedoStopCalc = speedoTgtCalc = "";
            // Lmt Buy
            for (int i = 0; i < atmIdsLmtBuy.Count; i++)
                if (!filledLmtBuy[i] && !string.IsNullOrEmpty(ordIdsLmtBuy[i])) AtmStrategyCancelEntryOrder(ordIdsLmtBuy[i]);
            atmIdsLmtBuy.Clear(); ordIdsLmtBuy.Clear(); stopsLmtBuy.Clear(); targetsLmtBuy.Clear();
            entriesLmtBuy.Clear(); filledLmtBuy.Clear(); callbackLmtBuy.Clear(); stopCalcsLmtBuy.Clear(); tgtCalcsLmtBuy.Clear();
            lmtBuyWaitingClick = false;
            // Lmt Sell
            for (int i = 0; i < atmIdsLmtSell.Count; i++)
                if (!filledLmtSell[i] && !string.IsNullOrEmpty(ordIdsLmtSell[i])) AtmStrategyCancelEntryOrder(ordIdsLmtSell[i]);
            atmIdsLmtSell.Clear(); ordIdsLmtSell.Clear(); stopsLmtSell.Clear(); targetsLmtSell.Clear();
            entriesLmtSell.Clear(); filledLmtSell.Clear(); callbackLmtSell.Clear(); stopCalcsLmtSell.Clear(); tgtCalcsLmtSell.Clear();
            lmtSellWaitingClick = false;
        }
		
		private void BackfillActiveMC()
{
    var mc = MyMicroChannel(ContinueMC, Show0CC, Show1CC, Show2CC, Show3CC, Show4CC, Show5CC, ShowCX);
    if (mc == null) { Print(DateTime.Now + " BackfillActiveMC — mc null"); return; }
    Print(DateTime.Now + " BackfillActiveMC — MC_Bull_Strong=" + mc.MC_Bull_Strong[0] + " MC_Bear_Strong=" + mc.MC_Bear_Strong[0] + " MC_Bull=" + mc.MC_Bull[0] + " MC_Bear=" + mc.MC_Bear[0]);

    double bullBarNo = mc.MC_Bull[0];
    double bearBarNo = mc.MC_Bear[0];

    if (mc.MC_Bull_Strong[0] > 0 && bullBarNo > 0)
    {
        int barsBack = (int)(bullBarNo - 1);
        activeChanHighLong = MAX(High, Math.Min(barsBack + 1, CurrentBar))[0];
        activeChanLowLong  = Low[barsBack];
        activeChanBarsLong = (int)bullBarNo;
        activePB33Long     = (mc.PB33[0] > 0 && mc.PB33[0] > activeChanLowLong && mc.PB33[0] < activeChanHighLong) ? mc.PB33[0] : 0;
        activePB50Long     = (mc.PB50[0] > 0 && mc.PB50[0] > activeChanLowLong && mc.PB50[0] < activeChanHighLong) ? mc.PB50[0] : 0;
        activePB66Long     = (mc.PB66[0] > 0 && mc.PB66[0] > activeChanLowLong && mc.PB66[0] < activeChanHighLong) ? mc.PB66[0] : 0;
        prevBullBarNo      = bullBarNo;
        Print(DateTime.Now + " BACKFILL ACTIVE BULL MC | chanH=" + activeChanHighLong + " chanL=" + activeChanLowLong + " pb33=" + activePB33Long + " pb50=" + activePB50Long + " pb66=" + activePB66Long);
    }

    if (mc.MC_Bear_Strong[0] > 0 && bearBarNo > 0)
    {
        int barsBack = (int)(bearBarNo - 1);
        activeChanHighShort = High[barsBack];
        activeChanLowShort  = MIN(Low, Math.Min(barsBack + 1, CurrentBar))[0];
        activeChanBarsShort = (int)bearBarNo;
        activePB33Short     = (mc.PB33[0] > 0 && mc.PB33[0] < activeChanHighShort && mc.PB33[0] > activeChanLowShort) ? mc.PB33[0] : 0;
        activePB50Short     = (mc.PB50[0] > 0 && mc.PB50[0] < activeChanHighShort && mc.PB50[0] > activeChanLowShort) ? mc.PB50[0] : 0;
        activePB66Short     = (mc.PB66[0] > 0 && mc.PB66[0] < activeChanHighShort && mc.PB66[0] > activeChanLowShort) ? mc.PB66[0] : 0;
        prevBearBarNo       = bearBarNo;
        Print(DateTime.Now + " BACKFILL ACTIVE BEAR MC | chanH=" + activeChanHighShort + " chanL=" + activeChanLowShort + " pb33=" + activePB33Short + " pb50=" + activePB50Short + " pb66=" + activePB66Short);
    }
}

        private void CheckSessionReset()
{
    DateTime today = Time[0].Date == DateTime.MinValue.Date ? DateTime.MinValue :
                 Time[0].TimeOfDay < new TimeSpan(17, 0, 0) ? Time[0].Date.AddDays(-1) : Time[0].Date;
    if (today == lastSessionDate) return;
    lastSessionDate = today;
    longChannelCounter = shortChannelCounter = 0;
    prevBullBarNo = prevBearBarNo = 999;
    testFired = false;
    // PB armed states intentionally preserved across session reset
    pb33Filled = false;
    pb50Filled = false;
    pb66Filled = false;
    SetPBButtonColors();
    cancelWatchLockedLong  = false;
    cancelWatchLockedShort = false;
    ResetLongLegs();
    ResetShortLegs();
    ResetBarSelectEntries();
    lastSwingLowsBBLSABR.Clear();  lastSwingHighsBBLSABR.Clear();
    lastSwingLowsSE.Clear();        lastSwingHighsSE.Clear();
    lastSwingLowsSpeedo.Clear();    lastSwingHighsSpeedo.Clear();
    Print(DateTime.Now + " New session — reset");
}

private void SaveState()
{
    try
    {
        string path = System.IO.Path.Combine(CSVFolderPath.TrimEnd('\\', '/'), "MCState.txt");
        using (var sw = new System.IO.StreamWriter(path, false))
        {
            sw.WriteLine("SESSION|" + DateTime.Now.ToString("yyyyMMdd"));
            // Single legs
            sw.WriteLine("L33|" + atmIdL33 + "|" + ordIdL33 + "|" + entryL33 + "|" + stopL33 + "|" + targetL33 + "|" + l33StopTargetSet + "|" + l33CallbackOK);
            sw.WriteLine("L50|" + atmIdL50 + "|" + ordIdL50 + "|" + entryL50 + "|" + stopL50 + "|" + targetL50 + "|" + l50StopTargetSet + "|" + l50CallbackOK);
            sw.WriteLine("L66|" + atmIdL66 + "|" + ordIdL66 + "|" + entryL66 + "|" + stopL66 + "|" + targetL66 + "|" + l66StopTargetSet + "|" + l66CallbackOK);
            sw.WriteLine("S33|" + atmIdS33 + "|" + ordIdS33 + "|" + entryS33 + "|" + stopS33 + "|" + targetS33 + "|" + s33StopTargetSet + "|" + s33CallbackOK);
            sw.WriteLine("S50|" + atmIdS50 + "|" + ordIdS50 + "|" + entryS50 + "|" + stopS50 + "|" + targetS50 + "|" + s50StopTargetSet + "|" + s50CallbackOK);
            sw.WriteLine("S66|" + atmIdS66 + "|" + ordIdS66 + "|" + entryS66 + "|" + stopS66 + "|" + targetS66 + "|" + s66StopTargetSet + "|" + s66CallbackOK);
            // Scalars
            sw.WriteLine("SCALARS|" + longOrdersPlaced + "|" + shortOrdersPlaced + "|" + pb33Armed + "|" + pb50Armed + "|" + pb66Armed + "|" + allPBsArmed);
            // Multi-leg LmtBuy
            for (int i = 0; i < atmIdsLmtBuy.Count; i++)
                sw.WriteLine("LMTBUY|" + atmIdsLmtBuy[i] + "|" + ordIdsLmtBuy[i] + "|" + entriesLmtBuy[i] + "|" + stopsLmtBuy[i] + "|" + targetsLmtBuy[i] + "|" + filledLmtBuy[i] + "|" + callbackLmtBuy[i]);
            // Multi-leg LmtSell
            for (int i = 0; i < atmIdsLmtSell.Count; i++)
                sw.WriteLine("LMTSELL|" + atmIdsLmtSell[i] + "|" + ordIdsLmtSell[i] + "|" + entriesLmtSell[i] + "|" + stopsLmtSell[i] + "|" + targetsLmtSell[i] + "|" + filledLmtSell[i] + "|" + callbackLmtSell[i]);
            // Multi-leg BBBL
            for (int i = 0; i < atmIdsBBBL.Count; i++)
                sw.WriteLine("BBBL|" + atmIdsBBBL[i] + "|" + ordIdsBBBL[i] + "|" + entriesBBBL[i] + "|" + stopsBBBL[i] + "|" + targetsBBBL[i] + "|" + filledBBBL[i] + "|" + callbackBBBL[i] + "|" + barsAgoBBBL[i] + "|" + inMCBBBL[i]);
            // Multi-leg SABR
            for (int i = 0; i < atmIdsSABR.Count; i++)
                sw.WriteLine("SABR|" + atmIdsSABR[i] + "|" + ordIdsSABR[i] + "|" + entriesSABR[i] + "|" + stopsSABR[i] + "|" + targetsSABR[i] + "|" + filledSABR[i] + "|" + callbackSABR[i] + "|" + barsAgoSABR[i] + "|" + inMCSABR[i]);
            // Multi-leg SEL
            for (int i = 0; i < atmIdsSEL.Count; i++)
                sw.WriteLine("SEL|" + atmIdsSEL[i] + "|" + ordIdsSEL[i] + "|" + entriesSEL[i] + "|" + stopsSEL[i] + "|" + targetsSEL[i] + "|" + filledSEL[i] + "|" + callbackSEL[i]);
            // Multi-leg SES
            for (int i = 0; i < atmIdsSES.Count; i++)
                sw.WriteLine("SES|" + atmIdsSES[i] + "|" + ordIdsSES[i] + "|" + entriesSES[i] + "|" + stopsSES[i] + "|" + targetsSES[i] + "|" + filledSES[i] + "|" + callbackSES[i]);
        }
    }
    catch (Exception ex) { Print("SaveState error: " + ex.Message); }
}

private void LoadState()
{
    try
    {
        string path = System.IO.Path.Combine(CSVFolderPath, "MCState.txt");
        if (!System.IO.File.Exists(path)) return;
        string[] lines = System.IO.File.ReadAllLines(path);
        if (lines.Length == 0) { System.IO.File.Delete(path); return; }

        // Check session date — ignore if stale
        string[] sessionLine = lines[0].Split('|');
        if (sessionLine.Length < 2 || sessionLine[1] != DateTime.Now.ToString("yyyyMMdd"))
        { Print(DateTime.Now + " LoadState — stale file, ignoring"); System.IO.File.Delete(path); return; }

        foreach (string line in lines)
        {
            string[] f = line.Split('|');
            switch (f[0])
            {
                case "L33":
                    atmIdL33 = f[1]; ordIdL33 = f[2]; entryL33 = double.Parse(f[3]); stopL33 = double.Parse(f[4]); targetL33 = double.Parse(f[5]); l33StopTargetSet = bool.Parse(f[6]); l33CallbackOK = bool.Parse(f[7]);
                    l33Active = !string.IsNullOrEmpty(atmIdL33); if (l33Active) longOrdersPlaced = true;
                    break;
                case "L50":
                    atmIdL50 = f[1]; ordIdL50 = f[2]; entryL50 = double.Parse(f[3]); stopL50 = double.Parse(f[4]); targetL50 = double.Parse(f[5]); l50StopTargetSet = bool.Parse(f[6]); l50CallbackOK = bool.Parse(f[7]);
                    l50Active = !string.IsNullOrEmpty(atmIdL50); if (l50Active) longOrdersPlaced = true;
                    break;
                case "L66":
                    atmIdL66 = f[1]; ordIdL66 = f[2]; entryL66 = double.Parse(f[3]); stopL66 = double.Parse(f[4]); targetL66 = double.Parse(f[5]); l66StopTargetSet = bool.Parse(f[6]); l66CallbackOK = bool.Parse(f[7]);
                    l66Active = !string.IsNullOrEmpty(atmIdL66); if (l66Active) longOrdersPlaced = true;
                    break;
                case "S33":
                    atmIdS33 = f[1]; ordIdS33 = f[2]; entryS33 = double.Parse(f[3]); stopS33 = double.Parse(f[4]); targetS33 = double.Parse(f[5]); s33StopTargetSet = bool.Parse(f[6]); s33CallbackOK = bool.Parse(f[7]);
                    s33Active = !string.IsNullOrEmpty(atmIdS33); if (s33Active) shortOrdersPlaced = true;
                    break;
                case "S50":
                    atmIdS50 = f[1]; ordIdS50 = f[2]; entryS50 = double.Parse(f[3]); stopS50 = double.Parse(f[4]); targetS50 = double.Parse(f[5]); s50StopTargetSet = bool.Parse(f[6]); s50CallbackOK = bool.Parse(f[7]);
                    s50Active = !string.IsNullOrEmpty(atmIdS50); if (s50Active) shortOrdersPlaced = true;
                    break;
                case "S66":
                    atmIdS66 = f[1]; ordIdS66 = f[2]; entryS66 = double.Parse(f[3]); stopS66 = double.Parse(f[4]); targetS66 = double.Parse(f[5]); s66StopTargetSet = bool.Parse(f[6]); s66CallbackOK = bool.Parse(f[7]);
                    s66Active = !string.IsNullOrEmpty(atmIdS66); if (s66Active) shortOrdersPlaced = true;
                    break;
                case "SCALARS":
                    longOrdersPlaced = bool.Parse(f[1]); shortOrdersPlaced = bool.Parse(f[2]);
                    pb33Armed = bool.Parse(f[3]); pb50Armed = bool.Parse(f[4]); pb66Armed = bool.Parse(f[5]); allPBsArmed = bool.Parse(f[6]);
                    break;
                case "LMTBUY":
                    atmIdsLmtBuy.Add(f[1]); ordIdsLmtBuy.Add(f[2]); entriesLmtBuy.Add(double.Parse(f[3]));
                    stopsLmtBuy.Add(double.Parse(f[4])); targetsLmtBuy.Add(double.Parse(f[5]));
                    filledLmtBuy.Add(bool.Parse(f[6])); callbackLmtBuy.Add(bool.Parse(f[7]));
                    stopCalcsLmtBuy.Add(""); tgtCalcsLmtBuy.Add("");
                    break;
                case "LMTSELL":
                    atmIdsLmtSell.Add(f[1]); ordIdsLmtSell.Add(f[2]); entriesLmtSell.Add(double.Parse(f[3]));
                    stopsLmtSell.Add(double.Parse(f[4])); targetsLmtSell.Add(double.Parse(f[5]));
                    filledLmtSell.Add(bool.Parse(f[6])); callbackLmtSell.Add(bool.Parse(f[7]));
                    stopCalcsLmtSell.Add(""); tgtCalcsLmtSell.Add("");
                    break;
                case "BBBL":
                    atmIdsBBBL.Add(f[1]); ordIdsBBBL.Add(f[2]); entriesBBBL.Add(double.Parse(f[3]));
                    stopsBBBL.Add(double.Parse(f[4])); targetsBBBL.Add(double.Parse(f[5]));
                    filledBBBL.Add(bool.Parse(f[6])); callbackBBBL.Add(bool.Parse(f[7]));
                    barsAgoBBBL.Add(int.Parse(f[8])); inMCBBBL.Add(bool.Parse(f[9]));
                    stopCalcsBBBL.Add(""); tgtCalcsBBBL.Add("");
                    break;
                case "SABR":
                    atmIdsSABR.Add(f[1]); ordIdsSABR.Add(f[2]); entriesSABR.Add(double.Parse(f[3]));
                    stopsSABR.Add(double.Parse(f[4])); targetsSABR.Add(double.Parse(f[5]));
                    filledSABR.Add(bool.Parse(f[6])); callbackSABR.Add(bool.Parse(f[7]));
                    barsAgoSABR.Add(int.Parse(f[8])); inMCSABR.Add(bool.Parse(f[9]));
                    stopCalcsSABR.Add(""); tgtCalcsSABR.Add("");
                    break;
                case "SEL":
                    atmIdsSEL.Add(f[1]); ordIdsSEL.Add(f[2]); entriesSEL.Add(double.Parse(f[3]));
                    stopsSEL.Add(double.Parse(f[4])); targetsSEL.Add(double.Parse(f[5]));
                    filledSEL.Add(bool.Parse(f[6])); callbackSEL.Add(bool.Parse(f[7]));
                    stopCalcsSEL.Add(""); tgtCalcsSEL.Add("");
                    break;
                case "SES":
                    atmIdsSES.Add(f[1]); ordIdsSES.Add(f[2]); entriesSES.Add(double.Parse(f[3]));
                    stopsSES.Add(double.Parse(f[4])); targetsSES.Add(double.Parse(f[5]));
                    filledSES.Add(bool.Parse(f[6])); callbackSES.Add(bool.Parse(f[7]));
                    stopCalcsSES.Add(""); tgtCalcsSES.Add("");
                    break;
            }
        }
       System.IO.File.Delete(path);
        Print(DateTime.Now + " LoadState — restored successfully");
        Print("  L33=" + atmIdL33 + " active=" + l33Active + " filled=" + l33StopTargetSet);
        Print("  L50=" + atmIdL50 + " active=" + l50Active + " filled=" + l50StopTargetSet);
        Print("  L66=" + atmIdL66 + " active=" + l66Active + " filled=" + l66StopTargetSet);
        Print("  S33=" + atmIdS33 + " active=" + s33Active + " filled=" + s33StopTargetSet);
        Print("  S50=" + atmIdS50 + " active=" + s50Active + " filled=" + s50StopTargetSet);
        Print("  S66=" + atmIdS66 + " active=" + s66Active + " filled=" + s66StopTargetSet);
        Print("  pb33Armed=" + pb33Armed + " pb50Armed=" + pb50Armed + " pb66Armed=" + pb66Armed + " allPBsArmed=" + allPBsArmed);
        for (int i = 0; i < atmIdsBBBL.Count; i++)
            Print("  BBBL#" + i + " atm=" + atmIdsBBBL[i] + " entry=" + entriesBBBL[i] + " stop=" + stopsBBBL[i] + " target=" + targetsBBBL[i] + " filled=" + filledBBBL[i] + " cb=" + callbackBBBL[i]);
        for (int i = 0; i < atmIdsSABR.Count; i++)
            Print("  SABR#" + i + " atm=" + atmIdsSABR[i] + " entry=" + entriesSABR[i] + " stop=" + stopsSABR[i] + " target=" + targetsSABR[i] + " filled=" + filledSABR[i] + " cb=" + callbackSABR[i]);
        for (int i = 0; i < atmIdsLmtBuy.Count; i++)
            Print("  LmtBuy#" + i + " atm=" + atmIdsLmtBuy[i] + " entry=" + entriesLmtBuy[i] + " stop=" + stopsLmtBuy[i] + " target=" + targetsLmtBuy[i] + " filled=" + filledLmtBuy[i] + " cb=" + callbackLmtBuy[i]);
        for (int i = 0; i < atmIdsLmtSell.Count; i++)
            Print("  LmtSell#" + i + " atm=" + atmIdsLmtSell[i] + " entry=" + entriesLmtSell[i] + " stop=" + stopsLmtSell[i] + " target=" + targetsLmtSell[i] + " filled=" + filledLmtSell[i] + " cb=" + callbackLmtSell[i]);
        for (int i = 0; i < atmIdsSEL.Count; i++)
            Print("  SEL#" + i + " atm=" + atmIdsSEL[i] + " entry=" + entriesSEL[i] + " stop=" + stopsSEL[i] + " target=" + targetsSEL[i] + " filled=" + filledSEL[i] + " cb=" + callbackSEL[i]);
        for (int i = 0; i < atmIdsSES.Count; i++)
            Print("  SES#" + i + " atm=" + atmIdsSES[i] + " entry=" + entriesSES[i] + " stop=" + stopsSES[i] + " target=" + targetsSES[i] + " filled=" + filledSES[i] + " cb=" + callbackSES[i]);
    }
    catch (Exception ex) { Print("LoadState error: " + ex.Message); }
}

        private void SetPBButtonColors()
        {
            if (ChartControl == null) return;
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                if (btnPB33 != null) SetBtn(btnPB33, pb33Armed ? ColorArmed : ColorStrategyOff, pb33Armed);
                if (btnPB50 != null) SetBtn(btnPB50, pb50Armed ? ColorArmed : ColorStrategyOff, pb50Armed);
                if (btnPB66 != null) SetBtn(btnPB66, pb66Armed ? ColorArmed : ColorStrategyOff, pb66Armed);
                if (btnAllPBs != null) SetBtn(btnAllPBs, allPBsArmed ? ColorStrategyOn : ColorStrategyOff);
            }));
        }

        private void UpdateBarSelectButtonColor(Button btn, BtnState3 state)
        {
            if (btn == null || ChartControl == null) return;
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                if (btn == null) return;
                switch (state)
                {
                    case BtnState3.Off:    btn.Background = new SolidColorBrush(ColorStrategyOff); btn.Foreground = Brushes.White; break;
                    case BtnState3.Armed:  btn.Background = new SolidColorBrush(ColorArmed); btn.Foreground = Brushes.Black; break;
                    case BtnState3.Filled: btn.Background = new SolidColorBrush(ColorFilled);      btn.Foreground = Brushes.Black; break;
                }
            }));
        }
		
		private void ResetSubButtonsForLeg(string legName)
        {
            if (ChartControl == null) return;
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                switch (legName)
                {
                    case "BBMC":   UpdateSubBtnColors(false, false, false, btnBBMCOfs,   btnBBMCStpCycle,   btnBBMCTgtCycle,   btnBBMCStpOfs,   btnBBMCTgtOfs);   break;
                    case "SAMC":   UpdateSubBtnColors(false, false, false, btnSAMCOfs,   btnSAMCStpCycle,   btnSAMCTgtCycle,   btnSAMCStpOfs,   btnSAMCTgtOfs);   break;
                    case "BBBL":   UpdateSubBtnColors(false, false, false, btnBBBLOfs,   btnBBBLStpCycle,   btnBBBLTgtCycle,   btnBBBLStpOfs,   btnBBBLTgtOfs);   break;
                    case "SABR":   UpdateSubBtnColors(false, false, false, btnSABROfs,   btnSABRStpCycle,   btnSABRTgtCycle,   btnSABRStpOfs,   btnSABRTgtOfs);   break;
                    case "SEL":    UpdateSubBtnColors(false, false, false, btnSELOfs,    btnSELStpCycle,    btnSELTgtCycle,    btnSELStpOfs,    btnSELTgtOfs);    break;
                    case "SES":    UpdateSubBtnColors(false, false, false, btnSESOfs,    btnSESStpCycle,    btnSESTgtCycle,    btnSESStpOfs,    btnSESTgtOfs);    break;
                    case "SPEEDO": UpdateSubBtnColors(false, false, false, btnSpeedoOfs, btnSpeedoStpCycle, btnSpeedoTgtCycle, btnSpeedoStpOfs, btnSpeedoTgtOfs); break;
                    case "BOXTR":  break;
                }
            }));
        }

        private double Round(double price) { return Math.Round(price / TickSize) * TickSize; }

        // ── BUTTON PANEL HELPERS ───────────────────────────────────────────────
        private Button MakeBtn(Style s, string label, string tip, Color bg, bool blackText = false)
        {
            return new Button() { Content = label, Style = s, Height = 36, Margin = new Thickness(1),
                FontSize = ButtonFontSize, FontWeight = FontWeights.Bold, ToolTip = tip,
                Background = new SolidColorBrush(bg),
                Foreground = blackText ? Brushes.Black : Brushes.White };
        }

        private Button MakeSmallBtn(Style s, string label, string tip, Color bg)
        {
            return new Button() { Content = label, Style = s, Height = 20, Margin = new Thickness(1),
                FontSize = SubButtonFontSize, FontWeight = FontWeights.Bold, ToolTip = tip,
                Background = new SolidColorBrush(bg), Foreground = Brushes.White };
        }

        private void SetBtn(Button btn, Color bg, bool blackText = false)
        {
            if (btn == null || ChartControl == null) return;
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                if (btn == null) return;
                btn.Background = new SolidColorBrush(bg);
                btn.Foreground = blackText ? Brushes.Black : Brushes.White;
            }));
        }

        private void AddFullRow(Grid grid, int row, Button btn)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(38) });
            Grid.SetRow(btn, row); Grid.SetColumn(btn, 0); Grid.SetColumnSpan(btn, 3);
            grid.Children.Add(btn);
        }

        private void AddHalfRow(Grid grid, int row, Button left, Button right)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(38) });
            var g = new Grid() { Margin = new Thickness(0) };
            g.ColumnDefinitions.Add(new ColumnDefinition());
            g.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
            g.Children.Add(left); g.Children.Add(right);
            Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
            grid.Children.Add(g);
        }

        private void AddHalfRowWithSubRow(Grid grid, int row, Button left, Button right,
            Button leftStp, Button leftTgt, Button rightStp, Button rightTgt)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(58) });
            var outer = new Grid() { Margin = new Thickness(0) };
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            Grid.SetRow(left, 0); Grid.SetColumn(left, 0); outer.Children.Add(left);
            Grid.SetRow(right, 0); Grid.SetColumn(right, 1); outer.Children.Add(right);

            // Sub-row left: STP | TGT
            var subL = new Grid();
            subL.ColumnDefinitions.Add(new ColumnDefinition());
            subL.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(leftStp, 0); Grid.SetColumn(leftTgt, 1);
            subL.Children.Add(leftStp); subL.Children.Add(leftTgt);
            Grid.SetRow(subL, 1); Grid.SetColumn(subL, 0); outer.Children.Add(subL);

            // Sub-row right: STP | TGT
            var subR = new Grid();
            subR.ColumnDefinitions.Add(new ColumnDefinition());
            subR.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(rightStp, 0); Grid.SetColumn(rightTgt, 1);
            subR.Children.Add(rightStp); subR.Children.Add(rightTgt);
            Grid.SetRow(subR, 1); Grid.SetColumn(subR, 1); outer.Children.Add(subR);

            Grid.SetRow(outer, row); Grid.SetColumn(outer, 0); Grid.SetColumnSpan(outer, 3);
            grid.Children.Add(outer);
        }

        private void AddFullRowWithSubRow(Grid grid, int row, Button btn, Button stpBtn, Button tgtBtn)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(58) });
            var outer = new Grid() { Margin = new Thickness(0) };
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetRow(btn, 0); Grid.SetColumn(btn, 0); outer.Children.Add(btn);
            var sub = new Grid();
            sub.ColumnDefinitions.Add(new ColumnDefinition());
            sub.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(stpBtn, 0); Grid.SetColumn(tgtBtn, 1);
            sub.Children.Add(stpBtn); sub.Children.Add(tgtBtn);
            Grid.SetRow(sub, 1); Grid.SetColumn(sub, 0); outer.Children.Add(sub);
            Grid.SetRow(outer, row); Grid.SetColumn(outer, 0); Grid.SetColumnSpan(outer, 3);
            grid.Children.Add(outer);
        }

        private void AddThirdRow(Grid grid, int row, Button b1, Button b2, Button b3)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(38) });
            var g = new Grid() { Margin = new Thickness(0) };
            g.ColumnDefinitions.Add(new ColumnDefinition());
            g.ColumnDefinitions.Add(new ColumnDefinition());
            g.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(b1, 0); Grid.SetColumn(b2, 1); Grid.SetColumn(b3, 2);
            g.Children.Add(b1); g.Children.Add(b2); g.Children.Add(b3);
            Grid.SetRow(g, row); Grid.SetColumn(g, 0); Grid.SetColumnSpan(g, 3);
            grid.Children.Add(g);
        }
		
		// ── Layout helper — third row with 3 sub-rows ─────────────────────────
        private void AddThirdRowWithSubRows(Grid grid, int row,
            Button b1, Button b2, Button b3,
            Button b1Ofs, Button b2Ofs, Button b3Ofs,
            Button b1StpMode, Button b1TgtMode,
            Button b2StpMode, Button b2TgtMode,
            Button b3StpMode, Button b3TgtMode,
            Button b1StpOfs, Button b1TgtOfs,
            Button b2StpOfs, Button b2TgtOfs,
            Button b3StpOfs, Button b3TgtOfs)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto });
            var outer = new Grid() { Margin = new Thickness(0) };
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
            outer.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto });

            // Main buttons row
            Grid.SetRow(b1, 0); Grid.SetColumn(b1, 0); outer.Children.Add(b1);
            Grid.SetRow(b2, 0); Grid.SetColumn(b2, 1); outer.Children.Add(b2);
            Grid.SetRow(b3, 0); Grid.SetColumn(b3, 2); outer.Children.Add(b3);

            // Sub-rows container (collapsible)
            var subPanel = new Grid() { Margin = new Thickness(0) };
            subPanel.ColumnDefinitions.Add(new ColumnDefinition());
            subPanel.ColumnDefinitions.Add(new ColumnDefinition());
            subPanel.ColumnDefinitions.Add(new ColumnDefinition());
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            // OFS row
            Grid.SetRow(b1Ofs, 0); Grid.SetColumn(b1Ofs, 0); subPanel.Children.Add(b1Ofs);
            Grid.SetRow(b2Ofs, 0); Grid.SetColumn(b2Ofs, 1); subPanel.Children.Add(b2Ofs);
            Grid.SetRow(b3Ofs, 0); Grid.SetColumn(b3Ofs, 2); subPanel.Children.Add(b3Ofs);
            // Mode row
            AddSubPair(subPanel, 1, 0, b1StpMode, b1TgtMode);
            AddSubPair(subPanel, 1, 1, b2StpMode, b2TgtMode);
            AddSubPair(subPanel, 1, 2, b3StpMode, b3TgtMode);
            // Offset row
            AddSubPair(subPanel, 2, 0, b1StpOfs, b1TgtOfs);
            AddSubPair(subPanel, 2, 1, b2StpOfs, b2TgtOfs);
            AddSubPair(subPanel, 2, 2, b3StpOfs, b3TgtOfs);
            Grid.SetRow(subPanel, 1); Grid.SetColumn(subPanel, 0); Grid.SetColumnSpan(subPanel, 3);
            outer.Children.Add(subPanel);
            allSubContainers.Add(subPanel);

            Grid.SetRow(outer, row); Grid.SetColumn(outer, 0); Grid.SetColumnSpan(outer, 3);
            grid.Children.Add(outer);
        }

        private void AddSubPair(Grid parent, int row, int col, Button left, Button right)
        {
            var g = new Grid();
            g.ColumnDefinitions.Add(new ColumnDefinition());
            g.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(left, 0); Grid.SetColumn(right, 1);
            g.Children.Add(left); g.Children.Add(right);
            Grid.SetRow(g, row); Grid.SetColumn(g, col);
            parent.Children.Add(g);
        }

        // ── Layout helper — half row with 3 sub-rows ──────────────────────────
    private void AddHalfRowWithFullSubRows(Grid grid, int row,
            Button left, Button right,
            Button leftStpMode, Button leftTgtMode,
            Button rightStpMode, Button rightTgtMode,
            Button leftStpOfs, Button leftTgtOfs,
            Button rightStpOfs, Button rightTgtOfs,
            Button leftOfs = null, Button rightOfs = null,
            Button leftOfs2 = null, Button rightOfs2 = null)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto });
            var outer = new Grid() { Margin = new Thickness(0) };
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.ColumnDefinitions.Add(new ColumnDefinition());
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
            outer.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto });

            Grid.SetRow(left,  0); Grid.SetColumn(left,  0); outer.Children.Add(left);
            Grid.SetRow(right, 0); Grid.SetColumn(right, 1); outer.Children.Add(right);

            var subPanel = new Grid() { Margin = new Thickness(0) };
            subPanel.ColumnDefinitions.Add(new ColumnDefinition());
            subPanel.ColumnDefinitions.Add(new ColumnDefinition());

            bool hasOfs = leftOfs != null || rightOfs != null;
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) }); // OFS row
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) }); // mode row
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) }); // offset row

            if (hasOfs)
            {
                // Left OFS — split if leftOfs2 provided
                if (leftOfs != null && leftOfs2 != null)
                {
                    var g = new Grid();
                    g.ColumnDefinitions.Add(new ColumnDefinition());
                    g.ColumnDefinitions.Add(new ColumnDefinition());
                    Grid.SetColumn(leftOfs, 0); Grid.SetColumn(leftOfs2, 1);
                    g.Children.Add(leftOfs); g.Children.Add(leftOfs2);
                    Grid.SetRow(g, 0); Grid.SetColumn(g, 0); subPanel.Children.Add(g);
                }
                else if (leftOfs != null)
                {
                    Grid.SetRow(leftOfs, 0); Grid.SetColumn(leftOfs, 0); subPanel.Children.Add(leftOfs);
                }

                // Right OFS — split if rightOfs2 provided
                if (rightOfs != null && rightOfs2 != null)
                {
                    var g = new Grid();
                    g.ColumnDefinitions.Add(new ColumnDefinition());
                    g.ColumnDefinitions.Add(new ColumnDefinition());
                    Grid.SetColumn(rightOfs, 0); Grid.SetColumn(rightOfs2, 1);
                    g.Children.Add(rightOfs); g.Children.Add(rightOfs2);
                    Grid.SetRow(g, 0); Grid.SetColumn(g, 1); subPanel.Children.Add(g);
                }
                else if (rightOfs != null)
                {
                    Grid.SetRow(rightOfs, 0); Grid.SetColumn(rightOfs, 1); subPanel.Children.Add(rightOfs);
                }
            }

            AddSubPair(subPanel, hasOfs ? 1 : 0, 0, leftStpMode,  leftTgtMode);
            AddSubPair(subPanel, hasOfs ? 1 : 0, 1, rightStpMode, rightTgtMode);
            AddSubPair(subPanel, hasOfs ? 2 : 1, 0, leftStpOfs,   leftTgtOfs);
            AddSubPair(subPanel, hasOfs ? 2 : 1, 1, rightStpOfs,  rightTgtOfs);

            Grid.SetRow(subPanel, 1); Grid.SetColumn(subPanel, 0); Grid.SetColumnSpan(subPanel, 2);
            outer.Children.Add(subPanel);
            allSubContainers.Add(subPanel);

            Grid.SetRow(outer, row); Grid.SetColumn(outer, 0); Grid.SetColumnSpan(outer, 3);
            grid.Children.Add(outer);
        }

        // ── Layout helper — full row with 3 sub-rows ──────────────────────────
        private void AddFullRowWithFullSubRows(Grid grid, int row,
            Button btn,
            Button ofsBtn,
            Button stpModeBtn, Button tgtModeBtn,
            Button stpOfsBtn, Button tgtOfsBtn)
        {
            grid.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto });
            var outer = new Grid() { Margin = new Thickness(0) };
            outer.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(36) });
            outer.RowDefinitions.Add(new RowDefinition() { Height = GridLength.Auto });
            outer.ColumnDefinitions.Add(new ColumnDefinition());

            Grid.SetRow(btn,    0); Grid.SetColumn(btn,    0); outer.Children.Add(btn);

            var subPanel = new Grid() { Margin = new Thickness(0) };
            subPanel.ColumnDefinitions.Add(new ColumnDefinition());
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            subPanel.RowDefinitions.Add(new RowDefinition() { Height = new GridLength(20) });
            Grid.SetRow(ofsBtn, 0); Grid.SetColumn(ofsBtn, 0); subPanel.Children.Add(ofsBtn);
            var modeRow = new Grid();
            modeRow.ColumnDefinitions.Add(new ColumnDefinition());
            modeRow.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(stpModeBtn, 0); Grid.SetColumn(tgtModeBtn, 1);
            modeRow.Children.Add(stpModeBtn); modeRow.Children.Add(tgtModeBtn);
            Grid.SetRow(modeRow, 1); Grid.SetColumn(modeRow, 0); subPanel.Children.Add(modeRow);
            var ofsRow = new Grid();
            ofsRow.ColumnDefinitions.Add(new ColumnDefinition());
            ofsRow.ColumnDefinitions.Add(new ColumnDefinition());
            Grid.SetColumn(stpOfsBtn, 0); Grid.SetColumn(tgtOfsBtn, 1);
            ofsRow.Children.Add(stpOfsBtn); ofsRow.Children.Add(tgtOfsBtn);
            Grid.SetRow(ofsRow, 2); Grid.SetColumn(ofsRow, 0); subPanel.Children.Add(ofsRow);
            Grid.SetRow(subPanel, 1); Grid.SetColumn(subPanel, 0); outer.Children.Add(subPanel);
            allSubContainers.Add(subPanel);

            Grid.SetRow(outer, row); Grid.SetColumn(outer, 0); Grid.SetColumnSpan(outer, 3);
            grid.Children.Add(outer);
        }

        // ── Toggle sub-button visibility ──────────────────────────────────────
        private void ToggleSubButtons()
        {
            subButtonsVisible = !subButtonsVisible;
            var vis = subButtonsVisible ? Visibility.Visible : Visibility.Collapsed;
            foreach (var btn in allSubButtons)
                if (btn != null) btn.Visibility = vis;
            foreach (var container in allSubContainers)
                if (container != null) container.Visibility = vis;
            if (btnSubToggle != null)
            {
                btnSubToggle.Content = subButtonsVisible ? "SUB ▲" : "SUB ▼";
                SetBtn(btnSubToggle, subButtonsVisible ? ColorStrategyOn : ColorStrategyOff);
            }
            Print(DateTime.Now + " Sub-buttons " + (subButtonsVisible ? "SHOWN" : "HIDDEN"));
        }

        // ── Update sub-button colors for a given entry ────────────────────────
        private void UpdateSubBtnColors(bool armed, bool filled, bool stopTargetSet,
            Button ofsBtn, Button stpModeBtn, Button tgtModeBtn,
            Button stpOfsBtn, Button tgtOfsBtn)
        {
            if (!subButtonsVisible) return;
            if (ChartControl == null) return;
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                Color ofsColor, stpModeColor, tgtModeColor, stpOfsColor, tgtOfsColor;
                if (stopTargetSet)
                {
                    ofsColor    = ColorStrategyOff;
                    stpModeColor = Color.FromRgb(160, 0, 0);
                    tgtModeColor = Color.FromRgb(0, 140, 0);
                    stpOfsColor  = Color.FromRgb(160, 0, 0);
                    tgtOfsColor  = Color.FromRgb(0, 140, 0);
                }
                else if (armed || filled)
                {
                    ofsColor = stpModeColor = tgtModeColor = stpOfsColor = tgtOfsColor = ColorArmed;
                }
                else
                {
                    ofsColor = stpModeColor = tgtModeColor = stpOfsColor = tgtOfsColor = Color.FromRgb(60, 60, 60);
                }
                bool blackText = armed || filled || stopTargetSet;
                if (ofsBtn     != null) { ofsBtn.Background     = new SolidColorBrush(ofsColor);     ofsBtn.Foreground     = blackText ? Brushes.Black : Brushes.White; }
                if (stpModeBtn != null) { stpModeBtn.Background = new SolidColorBrush(stpModeColor); stpModeBtn.Foreground = blackText ? Brushes.Black : Brushes.White; }
                if (tgtModeBtn != null) { tgtModeBtn.Background = new SolidColorBrush(tgtModeColor); tgtModeBtn.Foreground = blackText ? Brushes.Black : Brushes.White; }
                if (stpOfsBtn  != null) { stpOfsBtn.Background  = new SolidColorBrush(stpOfsColor);  stpOfsBtn.Foreground  = blackText ? Brushes.Black : Brushes.White; }
                if (tgtOfsBtn  != null) { tgtOfsBtn.Background  = new SolidColorBrush(tgtOfsColor);  tgtOfsBtn.Foreground  = blackText ? Brushes.Black : Brushes.White; }
            }));
        }

        // ── Make offset button (left=-1, right=+1) ────────────────────────────
        private Button MakeOfsBtn(Style s, string label, string tip)
        {
            return new Button() { Content = label, Style = s, Height = 20, Margin = new Thickness(1),
                FontSize = SubButtonFontSize, FontWeight = FontWeights.Bold, ToolTip = tip,
                Background = new SolidColorBrush(Color.FromRgb(60,60,60)), Foreground = Brushes.White };
        }

        // ── Cycle stop/target modes from sub-row buttons ───────────────────────
        private string StopModeAbbr(StopMode m)
        {
            switch (m)
            {
                case StopMode.ChanExtreme:      return "CE";
                case StopMode.SwingPoint:       return "SW";
                case StopMode.ABR:              return "ABR";
                case StopMode.SignalBar:        return "SB";
                case StopMode.WeakReversalBar:  return "WRB";
                default:                        return "CE";
            }
        }
        private string TargetModeAbbr(TargetMode m)
        {
            switch (m)
            {
                case TargetMode.ChanExtreme:    return "CE";
                case TargetMode.RHalf:          return "0.5R";
                case TargetMode.RThreeQuarter:  return "0.75R";
                case TargetMode.ROne:           return "1R";
                case TargetMode.ROneHalf:       return "1.5R";
                case TargetMode.RTwo:           return "2R";
                case TargetMode.RTwoHalf:       return "2.5R";
                case TargetMode.RThree:         return "3R";
                default:                        return "CE";
            }
        }
        private StopMode CycleStop(StopMode m)
{
    // ChanExtreme → SwingPoint → ABR → ChanExtreme (SignalBar not available for non-Speedo)
    switch (m)
    {
        case StopMode.ChanExtreme: return StopMode.SwingPoint;
        case StopMode.SwingPoint:  return StopMode.ABR;
        default:                   return StopMode.ChanExtreme;
    }
}
private StopMode CycleStopSpeedo(StopMode m)
{
    switch (m)
    {
        case StopMode.ChanExtreme:    return StopMode.SwingPoint;
        case StopMode.SwingPoint:     return StopMode.ABR;
        case StopMode.ABR:            return StopMode.SignalBar;
        case StopMode.SignalBar:      return StopMode.WeakReversalBar;
        default:                      return StopMode.ChanExtreme;
    }
}
        private TargetMode CycleTarget(TargetMode m)
        {
            switch (m)
            {
                case TargetMode.ChanExtreme:    return TargetMode.RHalf;
                case TargetMode.RHalf:          return TargetMode.RThreeQuarter;
                case TargetMode.RThreeQuarter:  return TargetMode.ROne;
                case TargetMode.ROne:           return TargetMode.ROneHalf;
                case TargetMode.ROneHalf:       return TargetMode.RTwo;
                case TargetMode.RTwo:           return TargetMode.RTwoHalf;
                case TargetMode.RTwoHalf:       return TargetMode.RThree;
                case TargetMode.RThree:         return TargetMode.ChanExtreme;
                default:                        return TargetMode.ChanExtreme;
            }
        }

    // ── CHART MOUSE CLICK — bar-select entries ─────────────────────────────
      // ── CHART MOUSE CLICK — bar-select entries ─────────────────────────────
        private void OnChartMouseDown(object sender, MouseButtonEventArgs e)
        {
            try
            {
            if (e.OriginalSource is Button) return;
            bool anyArmed = bbBLWaitingClick || saBRWaitingClick || seLWaitingClick || seSWaitingClick || speedoWaitingClick || lmtBuyWaitingClick || lmtSellWaitingClick;
            if (!anyArmed) return;
            if (e.Handled) return;

            // Right-click = disarm
            if (e.ChangedButton == MouseButton.Right)
            {
                if (bbBLWaitingClick)  { bbBLWaitingClick  = false; bbBLArmed  = false; UpdateBarSelectButtonColor(btnBBBL,   BtnState3.Off); Print(DateTime.Now + " BB BL disarmed"); }
                if (saBRWaitingClick)  { saBRWaitingClick  = false; saBRArmed  = false; UpdateBarSelectButtonColor(btnSABR,   BtnState3.Off); Print(DateTime.Now + " SA BR disarmed"); }
                if (seLWaitingClick)   { seLWaitingClick   = false; seLArmed   = false; UpdateBarSelectButtonColor(btnSEL,    BtnState3.Off); Print(DateTime.Now + " SE L disarmed"); }
                if (seSWaitingClick)   { seSWaitingClick   = false; seSArmed   = false; UpdateBarSelectButtonColor(btnSES,    BtnState3.Off); Print(DateTime.Now + " SE S disarmed"); }
                if (speedoWaitingClick){ speedoWaitingClick = false; speedoArmed= false; UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off); Print(DateTime.Now + " Speedo disarmed"); }
                if (lmtBuyWaitingClick)  { lmtBuyWaitingClick  = false; if (btnLmtBuy  != null) SetBtn(btnLmtBuy,  ColorStrategyOff); Print(DateTime.Now + " Lmt Buy disarmed"); }
                if (lmtSellWaitingClick) { lmtSellWaitingClick = false; if (btnLmtSell != null) SetBtn(btnLmtSell, ColorStrategyOff); Print(DateTime.Now + " Lmt Sell disarmed"); }
                return;
            }
            if (e.ChangedButton != MouseButton.Left) return;

            // Get slot index
            var pos = e.GetPosition(ChartControl);
			int barIdx = ChartBars.GetBarIdxByX(ChartControl, (int)pos.X);
			if (barIdx < 0 || barIdx >= ChartControl.BarsArray[0].Count) return;
			int barsAgo = ChartControl.BarsArray[0].Count - 1 - barIdx;
			if (barsAgo < 0 || barsAgo > CurrentBar) return;
			double clickedLow  = ChartControl.BarsArray[0].Bars.GetLow(barIdx);
			double clickedHigh = ChartControl.BarsArray[0].Bars.GetHigh(barIdx);

            bool insideBull = activeChanHighLong > 0;
            bool insideBear = activeChanHighShort > 0;

          if (bbBLWaitingClick)
            {
                Print(DateTime.Now + " bbBL block entered");
                bbBLWaitingClick = false;
                double limitPrice = Round(clickedLow - BBLSABR_EntryOffsetTicks * TickSize);
                if (GetCurrentAsk() <= limitPrice)
                {
                    bbBLArmed = false;
                    UpdateBarSelectButtonColor(btnBBBL, BtnState3.Off);
                    Print(DateTime.Now + string.Format(" BB BL REJECTED — ask={0} at/below limit={1}", GetCurrentAsk(), limitPrice));
                    e.Handled = true; return;
                }
                string sc, tc;
                double sp  = CalcStopBarSelect(BBLSABR_StopMode, BBLSABR_StopOffsetTicks, BBLSABR_StopABRBars, BBLSABR_StopABRMultiple, swingBBLSABR, limitPrice, activeChanHighLong, activeChanLowLong, true, barsAgo, out sc);
                double tgt = CalcTargetBarSelect(BBLSABR_TargetMode, BBLSABR_RMultiple, BBLSABR_TargetOffsetTicks, limitPrice, sp, activeChanHighLong, activeChanLowLong, true, out tc);
                int idx = atmIdsBBBL.Count;
                atmIdsBBBL.Add(string.Empty); ordIdsBBBL.Add(string.Empty);
                stopsBBBL.Add(sp); targetsBBBL.Add(tgt); entriesBBBL.Add(limitPrice);
                filledBBBL.Add(false); callbackBBBL.Add(false);
                stopCalcsBBBL.Add(sc); tgtCalcsBBBL.Add(tc);
                barsAgoBBBL.Add(barsAgo); inMCBBBL.Add(insideBull);
                int capturedIdx = idx;
                string ordId = "BBBL_ORD_" + GetAtmStrategyUniqueId();
                string atmId = "BBBL_ATM_" + GetAtmStrategyUniqueId();
                ordIdsBBBL[idx] = ordId; atmIdsBBBL[idx] = atmId;
                Print(string.Format("│  ▶ BB BL #{0} FIRED LONG entry={1} stop={2} target={3} bar[{4}] low={5} insideMC={6}", idx, limitPrice, sp, tgt, barsAgo, clickedLow, insideBull));
                Print("│    " + sc); Print("│    " + tc);
                AtmStrategyCreate(OrderAction.Buy, OrderType.Limit, Round(limitPrice), 0, TimeInForce.Day, ordId, AtmTemplateName, atmId,
                    (errCode, cbId) => { if (errCode == ErrorCode.NoError) { Print(DateTime.Now + " BBBL #" + capturedIdx + " CALLBACK OK"); if (capturedIdx < callbackBBBL.Count) callbackBBBL[capturedIdx] = true; } else Print(DateTime.Now + " BBBL #" + capturedIdx + " CALLBACK FAILED"); });
                bbBLWaitingClick = false;
                Print(DateTime.Now + " BBBL count before label=" + atmIdsBBBL.Count);
                if (btnBBBL != null) SetBtn(btnBBBL, ColorStrategyOff);
                UpdateLmtButtonLabel(btnBBBL, atmIdsBBBL, "BBBL");
                e.Handled = true;
            }
            else if (saBRWaitingClick)
            {
                saBRWaitingClick = false;
                double limitPrice = Round(clickedHigh + BBLSABR_EntryOffsetTicks * TickSize);
                if (GetCurrentBid() >= limitPrice)
                {
                    saBRArmed = false;
                    UpdateBarSelectButtonColor(btnSABR, BtnState3.Off);
                    Print(DateTime.Now + string.Format(" SA BR REJECTED — bid={0} at/above limit={1}", GetCurrentBid(), limitPrice));
                    e.Handled = true; return;
                }
                string sc, tc;
                double sp  = CalcStopBarSelect(BBLSABR_StopMode, BBLSABR_StopOffsetTicks, BBLSABR_StopABRBars, BBLSABR_StopABRMultiple, swingBBLSABR, limitPrice, activeChanHighShort, activeChanLowShort, false, barsAgo, out sc);
                double tgt = CalcTargetBarSelect(BBLSABR_TargetMode, BBLSABR_RMultiple, BBLSABR_TargetOffsetTicks, limitPrice, sp, activeChanHighShort, activeChanLowShort, false, out tc);
                int idx = atmIdsSABR.Count;
                atmIdsSABR.Add(string.Empty); ordIdsSABR.Add(string.Empty);
                stopsSABR.Add(sp); targetsSABR.Add(tgt); entriesSABR.Add(limitPrice);
                filledSABR.Add(false); callbackSABR.Add(false);
                stopCalcsSABR.Add(sc); tgtCalcsSABR.Add(tc);
                barsAgoSABR.Add(barsAgo); inMCSABR.Add(insideBear);
                int capturedIdx = idx;
                string ordId = "SABR_ORD_" + GetAtmStrategyUniqueId();
                string atmId = "SABR_ATM_" + GetAtmStrategyUniqueId();
                ordIdsSABR[idx] = ordId; atmIdsSABR[idx] = atmId;
                Print(string.Format("│  ▶ SA BR #{0} FIRED SHORT entry={1} stop={2} target={3} bar[{4}] high={5} insideMC={6}", idx, limitPrice, sp, tgt, barsAgo, clickedHigh, insideBear));
                Print("│    " + sc); Print("│    " + tc);
                AtmStrategyCreate(OrderAction.Sell, OrderType.Limit, Round(limitPrice), 0, TimeInForce.Day, ordId, AtmTemplateName, atmId,
                    (errCode, cbId) => { if (errCode == ErrorCode.NoError) { Print(DateTime.Now + " SABR #" + capturedIdx + " CALLBACK OK"); if (capturedIdx < callbackSABR.Count) callbackSABR[capturedIdx] = true; } else Print(DateTime.Now + " SABR #" + capturedIdx + " CALLBACK FAILED"); });
                if (btnSABR != null) SetBtn(btnSABR, ColorStrategyOff);
                UpdateLmtButtonLabel(btnSABR, atmIdsSABR, "SABR");
                saBRWaitingClick = false;
                e.Handled = true;
            }
            else if (seLWaitingClick)
            {
                seLWaitingClick = false;
                double limitPrice = Round(clickedHigh + SE_EntryOffsetTicks * TickSize);
                if (GetCurrentAsk() >= limitPrice)
                {
                    seLArmed = false;
                    UpdateBarSelectButtonColor(btnSEL, BtnState3.Off);
                    Print(DateTime.Now + string.Format(" SE L REJECTED — ask={0} at/above limit={1}", GetCurrentAsk(), limitPrice));
                    e.Handled = true; return;
                }
                string sc, tc;
                double sp  = CalcStopBarSelect(SE_StopMode, SE_StopOffsetTicks, SE_StopABRBars, SE_StopABRMultiple, swingSE, limitPrice, activeChanHighLong, activeChanLowLong, true, barsAgo, out sc);
                double tgt = CalcTargetBarSelect(SE_TargetMode, SE_RMultiple, SE_TargetOffsetTicks, limitPrice, sp, activeChanHighLong, activeChanLowLong, true, out tc);
                int idx = atmIdsSEL.Count;
                atmIdsSEL.Add(string.Empty); ordIdsSEL.Add(string.Empty);
                stopsSEL.Add(sp); targetsSEL.Add(tgt); entriesSEL.Add(limitPrice);
                filledSEL.Add(false); callbackSEL.Add(false);
                stopCalcsSEL.Add(sc); tgtCalcsSEL.Add(tc);
                int capturedIdx = idx;
                string ordId = "SEL_ORD_" + GetAtmStrategyUniqueId();
                string atmId = "SEL_ATM_" + GetAtmStrategyUniqueId();
                ordIdsSEL[idx] = ordId; atmIdsSEL[idx] = atmId;
                Print(string.Format("│  ▶ SE L #{0} FIRED LONG entry={1} stop={2} target={3} bar[{4}] high={5} insideMC={6}", idx, limitPrice, sp, tgt, barsAgo, clickedHigh, insideBull));
                Print("│    " + sc); Print("│    " + tc);
                AtmStrategyCreate(OrderAction.Buy, SE_OrderType,
                    SE_OrderType == OrderType.StopLimit ? Round(limitPrice) : 0,
                    Round(limitPrice), TimeInForce.Day, ordId, AtmTemplateName, atmId,
                    (errCode, cbId) => { if (errCode == ErrorCode.NoError) { Print(DateTime.Now + " SEL #" + capturedIdx + " CALLBACK OK"); if (capturedIdx < callbackSEL.Count) callbackSEL[capturedIdx] = true; } else Print(DateTime.Now + " SEL #" + capturedIdx + " CALLBACK FAILED"); });
                if (btnSEL != null) SetBtn(btnSEL, ColorStrategyOff);
                UpdateLmtButtonLabel(btnSEL, atmIdsSEL, "SEL");
                seLWaitingClick = false;
                e.Handled = true;
            }
            else if (seSWaitingClick)
            {
                seSWaitingClick = false;
                double limitPrice = Round(clickedLow - SE_EntryOffsetTicks * TickSize);
                if (GetCurrentBid() <= limitPrice)
                {
                    seSArmed = false;
                    UpdateBarSelectButtonColor(btnSES, BtnState3.Off);
                    Print(DateTime.Now + string.Format(" SE S REJECTED — bid={0} at/below limit={1}", GetCurrentBid(), limitPrice));
                    e.Handled = true; return;
                }
                string sc, tc;
                double sp  = CalcStopBarSelect(SE_StopMode, SE_StopOffsetTicks, SE_StopABRBars, SE_StopABRMultiple, swingSE, limitPrice, activeChanHighShort, activeChanLowShort, false, barsAgo, out sc);
                double tgt = CalcTargetBarSelect(SE_TargetMode, SE_RMultiple, SE_TargetOffsetTicks, limitPrice, sp, activeChanHighShort, activeChanLowShort, false, out tc);
                int idx = atmIdsSES.Count;
                atmIdsSES.Add(string.Empty); ordIdsSES.Add(string.Empty);
                stopsSES.Add(sp); targetsSES.Add(tgt); entriesSES.Add(limitPrice);
                filledSES.Add(false); callbackSES.Add(false);
                stopCalcsSES.Add(sc); tgtCalcsSES.Add(tc);
                int capturedIdx = idx;
                string ordId = "SES_ORD_" + GetAtmStrategyUniqueId();
                string atmId = "SES_ATM_" + GetAtmStrategyUniqueId();
                ordIdsSES[idx] = ordId; atmIdsSES[idx] = atmId;
                Print(string.Format("│  ▶ SE S #{0} FIRED SHORT entry={1} stop={2} target={3} bar[{4}] low={5} insideMC={6}", idx, limitPrice, sp, tgt, barsAgo, clickedLow, insideBear));
                Print("│    " + sc); Print("│    " + tc);
              AtmStrategyCreate(OrderAction.Sell, SE_OrderType,
                    SE_OrderType == OrderType.StopLimit ? Round(limitPrice) : 0,
                    Round(limitPrice), TimeInForce.Day, ordId, AtmTemplateName, atmId,
                    (errCode, cbId) => { if (errCode == ErrorCode.NoError) { Print(DateTime.Now + " SES #" + capturedIdx + " CALLBACK OK"); if (capturedIdx < callbackSES.Count) callbackSES[capturedIdx] = true; } else Print(DateTime.Now + " SES #" + capturedIdx + " CALLBACK FAILED"); });
                if (btnSES != null) SetBtn(btnSES, ColorStrategyOff);
                UpdateLmtButtonLabel(btnSES, atmIdsSES, "SES");
                seSWaitingClick = false;
                e.Handled = true;
            }
            else if (speedoWaitingClick && false)
            {
                speedoWaitingClick = false;
                int clickedAbsBarIdx = BarsArray[0].Count - 1 - barsAgo;

                // barsAgo == 0 — forming bar, invalid
                if (barsAgo == 0)
                {
                    string msg = "Invalid Speedo Setup — bar still forming. Click a closed bar.";
                    Print(DateTime.Now + " SPEEDO INVALID — " + msg);
                    speedoArmed = false;
                    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off);
                    if (ChartControl != null)
                        ChartControl.Dispatcher.InvokeAsync((Action)(() =>
                            System.Windows.MessageBox.Show(msg, "Invalid Speedo Setup", System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Warning)));
                    e.Handled = true; return;
                }

                // barsAgo >= 2 — too old, invalid
                if (barsAgo >= 2)
                {
                    string msg = "Invalid Speedo Setup — impulse bar too old. Click the most recent closed bar.";
                    Print(DateTime.Now + " SPEEDO INVALID — " + msg);
                    speedoArmed = false;
                    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off);
                    if (ChartControl != null)
                        ChartControl.Dispatcher.InvokeAsync((Action)(() =>
                            System.Windows.MessageBox.Show(msg, "Invalid Speedo Setup", System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Warning)));
                    e.Handled = true; return;
                }

                // barsAgo == 1 — closed bar, proceed
                double impH     = BarsArray[0].GetHigh(clickedAbsBarIdx);
                double impL     = BarsArray[0].GetLow(clickedAbsBarIdx);
                double impC     = BarsArray[0].GetClose(clickedAbsBarIdx);
                double impO     = BarsArray[0].GetOpen(clickedAbsBarIdx);
                double impRange = impH - impL;

                // Doji check
                if (impRange < TickSize)
                {
                    string msg = "Invalid Speedo Setup — doji bar, no clear direction.";
                    Print(DateTime.Now + " SPEEDO INVALID — " + msg);
                    speedoArmed = false;
                    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off);
                    if (ChartControl != null)
                        ChartControl.Dispatcher.InvokeAsync((Action)(() =>
                            System.Windows.MessageBox.Show(msg, "Invalid Speedo Setup", System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Warning)));
                    e.Handled = true; return;
                }

                double closePct = (impC - impL) / impRange;
                if (closePct >= 0.60 && impC >= impO)
                    speedoIsLong = true;
                else if (closePct <= 0.40 && impC <= impO)
                    speedoIsLong = false;
                else
                {
                    string msg = string.Format("Invalid Speedo Setup — impulse bar not decisive (closePct={0:P0}, C={1} O={2}).", closePct, impC, impO);
                    Print(DateTime.Now + " SPEEDO INVALID — " + msg);
                    speedoArmed = false;
                    UpdateBarSelectButtonColor(btnSpeedo, BtnState3.Off);
                    if (ChartControl != null)
                        ChartControl.Dispatcher.InvokeAsync((Action)(() =>
                            System.Windows.MessageBox.Show(msg, "Invalid Speedo Setup", System.Windows.MessageBoxButton.OK, System.Windows.MessageBoxImage.Warning)));
                    e.Handled = true; return;
                }

                speedoImpulseBarIndex  = clickedAbsBarIdx;
                speedoImpulseHigh      = impH;
                speedoImpulseLow       = impL;
                speedoReversalBarIndex = BarsArray[0].Count - 1;
                speedoWaitingBar       = true;
                speedoInitiatedInMC    = speedoIsLong ? insideBull : insideBear;

                Print(string.Format("{0} SPEEDO impulse bar selected | bar[{1}] high={2} low={3} close={4} closePct={5:P0} direction={6} — waiting reversal bar close",
                    DateTime.Now, barsAgo, impH, impL, impC, closePct, speedoIsLong ? "LONG" : "SHORT"));
                if (ChartControl != null)
                    ChartControl.Dispatcher.InvokeAsync((Action)(() => {
                        if (btnSpeedo != null) { btnSpeedo.Background = new SolidColorBrush(ColorWaitingBar); btnSpeedo.Foreground = Brushes.White; }
                    }));
                e.Handled = true;
            }
            else if (lmtBuyWaitingClick)
            {
                lmtBuyWaitingClick = false;
                double clickedPrice = ChartControl.ChartPanels[0].Scales[NinjaTrader.Gui.Chart.ScaleJustification.Right].GetValueByYWpf(pos.Y);
                double limitPrice   = Round(clickedPrice);
                if (GetCurrentAsk() <= limitPrice)
                { if (btnLmtBuy != null) SetBtn(btnLmtBuy, ColorStrategyOff); Print(DateTime.Now + string.Format(" Lmt Buy REJECTED — ask={0} at/below limit={1}", GetCurrentAsk(), limitPrice)); e.Handled = true; return; }
                string sc, tc;
                double sp  = CalcStopBarSelect(BBLSABR_StopMode, BBLSABR_StopOffsetTicks, BBLSABR_StopABRBars, BBLSABR_StopABRMultiple, swingBBLSABR, limitPrice, activeChanHighLong, activeChanLowLong, true, barsAgo, out sc);
                double tgt = CalcTargetBarSelect(BBLSABR_TargetMode, BBLSABR_RMultiple, BBLSABR_TargetOffsetTicks, limitPrice, sp, activeChanHighLong, activeChanLowLong, true, out tc);
                int idx = atmIdsLmtBuy.Count;
                atmIdsLmtBuy.Add(string.Empty); ordIdsLmtBuy.Add(string.Empty);
                stopsLmtBuy.Add(sp); targetsLmtBuy.Add(tgt); entriesLmtBuy.Add(limitPrice);
                filledLmtBuy.Add(false); callbackLmtBuy.Add(false);
                stopCalcsLmtBuy.Add(sc); tgtCalcsLmtBuy.Add(tc);
                int capturedIdx = idx;
                string ordId = "LMTBUY_ORD_" + GetAtmStrategyUniqueId();
                string atmId = "LMTBUY_ATM_" + GetAtmStrategyUniqueId();
                ordIdsLmtBuy[idx] = ordId; atmIdsLmtBuy[idx] = atmId;
                Print(string.Format("│  ▶ Lmt Buy #{0} FIRED entry={1} stop={2} target={3} bar[{4}]", idx, limitPrice, sp, tgt, barsAgo));
                Print("│    " + sc); Print("│    " + tc);
                AtmStrategyCreate(OrderAction.Buy, OrderType.Limit, Round(limitPrice), 0, TimeInForce.Day, ordId, AtmTemplateName, atmId,
                    (errCode, cbId) => { if (errCode == ErrorCode.NoError) { Print(DateTime.Now + " LmtBuy #" + capturedIdx + " CALLBACK OK"); if (capturedIdx < callbackLmtBuy.Count) callbackLmtBuy[capturedIdx] = true; } else { Print(DateTime.Now + " LmtBuy #" + capturedIdx + " CALLBACK FAILED"); } });
                if (btnLmtBuy != null) SetBtn(btnLmtBuy, ColorStrategyOff);
                UpdateLmtButtonLabel(btnLmtBuy, atmIdsLmtBuy, "LmtBuy");
                e.Handled = true;
            }
            else if (lmtSellWaitingClick)
            {
                lmtSellWaitingClick = false;
                double clickedPrice = ChartControl.ChartPanels[0].Scales[NinjaTrader.Gui.Chart.ScaleJustification.Right].GetValueByYWpf(pos.Y);
                double limitPrice   = Round(clickedPrice);
                if (GetCurrentBid() >= limitPrice)
                { if (btnLmtSell != null) SetBtn(btnLmtSell, ColorStrategyOff); Print(DateTime.Now + string.Format(" Lmt Sell REJECTED — bid={0} at/above limit={1}", GetCurrentBid(), limitPrice)); e.Handled = true; return; }
                string sc, tc;
                double sp  = CalcStopBarSelect(BBLSABR_StopMode, BBLSABR_StopOffsetTicks, BBLSABR_StopABRBars, BBLSABR_StopABRMultiple, swingBBLSABR, limitPrice, activeChanHighShort, activeChanLowShort, false, barsAgo, out sc);
                double tgt = CalcTargetBarSelect(BBLSABR_TargetMode, BBLSABR_RMultiple, BBLSABR_TargetOffsetTicks, limitPrice, sp, activeChanHighShort, activeChanLowShort, false, out tc);
                int idx = atmIdsLmtSell.Count;
                atmIdsLmtSell.Add(string.Empty); ordIdsLmtSell.Add(string.Empty);
                stopsLmtSell.Add(sp); targetsLmtSell.Add(tgt); entriesLmtSell.Add(limitPrice);
                filledLmtSell.Add(false); callbackLmtSell.Add(false);
                stopCalcsLmtSell.Add(sc); tgtCalcsLmtSell.Add(tc);
                int capturedIdx = idx;
                string ordId = "LMTSELL_ORD_" + GetAtmStrategyUniqueId();
                string atmId = "LMTSELL_ATM_" + GetAtmStrategyUniqueId();
                ordIdsLmtSell[idx] = ordId; atmIdsLmtSell[idx] = atmId;
                Print(string.Format("│  ▶ Lmt Sell #{0} FIRED entry={1} stop={2} target={3} bar[{4}]", idx, limitPrice, sp, tgt, barsAgo));
                Print("│    " + sc); Print("│    " + tc);
                AtmStrategyCreate(OrderAction.Sell, OrderType.Limit, Round(limitPrice), 0, TimeInForce.Day, ordId, AtmTemplateName, atmId,
                    (errCode, cbId) => { if (errCode == ErrorCode.NoError) { Print(DateTime.Now + " LmtSell #" + capturedIdx + " CALLBACK OK"); if (capturedIdx < callbackLmtSell.Count) callbackLmtSell[capturedIdx] = true; } else { Print(DateTime.Now + " LmtSell #" + capturedIdx + " CALLBACK FAILED"); } });
                if (btnLmtSell != null) SetBtn(btnLmtSell, ColorStrategyOff);
             UpdateLmtButtonLabel(btnLmtSell, atmIdsLmtSell, "LmtSell");
                e.Handled = true;
            }
            } catch (Exception ex) { Print("OnChartMouseDown EXCEPTION: " + ex.ToString()); }
        }

        // ── WPF CONTROLS ──────────────────────────────────────────────────────
       private void CreateWPFControls()
        {
            if (ctPanelActive) return;
            try
            {
                var win = Window.GetWindow(ChartControl.Parent) as NinjaTrader.Gui.Chart.Chart;
                if (win == null) { Print("CreateWPFControls: chart window not found"); return; }
                var chartTrader = win.FindFirst("ChartWindowChartTraderControl") as NinjaTrader.Gui.Chart.ChartTrader;
                if (chartTrader == null) { Print("CreateWPFControls: ChartTrader not found"); return; }
                var outerGrid = chartTrader.Content as Grid;
                if (outerGrid == null) return;
                foreach (UIElement child in outerGrid.Children)
                    if (child is Grid g) { ctButtonsGrid = g; break; }
                if (ctButtonsGrid == null) { Print("CreateWPFControls: button grid not found"); return; }

                if (!chartMouseHooked)
                { ChartControl.PreviewMouseDown += OnChartMouseDown; chartMouseHooked = true; }

                allSubButtons.Clear();
                allSubContainers.Clear();
                int r = ctButtonsGrid.RowDefinitions.Count;
                int baseRowCount = r;
                ctBaseRowCount = r;
                Style s = Application.Current.TryFindResource("Button") as Style;

                // ── Row 0: MC STRATEGY ────────────────────────────────────────
                btnMCStrategy = MakeBtn(s, LblMCStrategy, "Enable/disable MC strategy", ColorStrategyOn);
                btnMCStrategy.Click += (o, e) => { mcStrategyOn = !mcStrategyOn; SetBtn(btnMCStrategy, mcStrategyOn ? ColorStrategyOn : ColorStrategyOff); Print(DateTime.Now + " MC Strategy " + (mcStrategyOn ? "ON" : "OFF")); };
                AddFullRow(ctButtonsGrid, r + 0, btnMCStrategy);

                // ── Row 1: CT GUARD | SUB BUTTONS ────────────────────────────
                btnCTGuard = MakeBtn(s, "CT GUARD", "Counter trend guard on/off", ColorStrategyOff);
                btnCTGuard.Click += (o, e) => { ctGuardOn = !ctGuardOn; SetBtn(btnCTGuard, ctGuardOn ? ColorStrategyOn : ColorStrategyOff); Print(DateTime.Now + " CT Guard " + (ctGuardOn ? "ON" : "OFF")); };
                btnSubToggle = MakeBtn(s, "SUB ▼", "Show/hide sub-buttons", ColorStrategyOff);
                btnSubToggle.Click += (o, e) => ToggleSubButtons();
                AddHalfRow(ctButtonsGrid, r + 1, btnCTGuard, btnSubToggle);

                // ── Row 2: ALL PBs ARMED ──────────────────────────────────────
                btnAllPBs = MakeBtn(s, "ALL PBs ARMED", "Arm/disarm all PB entries", ColorStrategyOff);
                btnAllPBs.Click += (o, e) => {
                    if ((cancelWatchLockedLong || cancelWatchLockedShort) && !allPBsArmed)
                    { Print(DateTime.Now + " ALL PBs LOCKED — Cancel Watch active, wait for next MC"); return; }
                 allPBsArmed = !allPBsArmed; pb33Armed = allPBsArmed; pb50Armed = allPBsArmed; pb66Armed = allPBsArmed;
if (allPBsArmed)
{
    pendingPBPlacement = true;
}
else
{
    // Cancel all unfilled PB orders
    if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) { AtmStrategyCancelEntryOrder(ordIdL33); l33Active = false; }
    if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) { AtmStrategyCancelEntryOrder(ordIdL50); l50Active = false; }
    if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) { AtmStrategyCancelEntryOrder(ordIdL66); l66Active = false; }
    if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) { AtmStrategyCancelEntryOrder(ordIdS33); s33Active = false; }
    if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) { AtmStrategyCancelEntryOrder(ordIdS50); s50Active = false; }
    if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) { AtmStrategyCancelEntryOrder(ordIdS66); s66Active = false; }
    longOrdersPlaced  = false;
    shortOrdersPlaced = false;
    atmIdL33 = atmIdL50 = atmIdL66 = ordIdL33 = ordIdL50 = ordIdL66 = string.Empty;
    atmIdS33 = atmIdS50 = atmIdS66 = ordIdS33 = ordIdS50 = ordIdS66 = string.Empty;
    lastSentL33 = lastSentL50 = lastSentL66 = 0;
    lastSentS33 = lastSentS50 = lastSentS66 = 0;
    l33CallbackOK = l50CallbackOK = l66CallbackOK = false;
    s33CallbackOK = s50CallbackOK = s66CallbackOK = false;
}
					SetBtn(btnAllPBs, allPBsArmed ? ColorStrategyOn : ColorStrategyOff);
					SetBtn(btnPB33, allPBsArmed ? ColorArmed : ColorStrategyOff, allPBsArmed);
					SetBtn(btnPB50, allPBsArmed ? ColorArmed : ColorStrategyOff, allPBsArmed);
					SetBtn(btnPB66, allPBsArmed ? ColorArmed : ColorStrategyOff, allPBsArmed);
                    UpdateSubBtnColors(allPBsArmed, false, false, btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs);
                    UpdateSubBtnColors(allPBsArmed, false, false, btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs);
                    UpdateSubBtnColors(allPBsArmed, false, false, btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs);
                    Print(DateTime.Now + " ALL PBs " + (allPBsArmed ? "ARMED" : "DISARMED") + (allPBsArmed ? " | pendingPBPlacement set | bullMCActive=" + (activeChanHighLong > 0) + " bearMCActive=" + (activeChanLowShort > 0) : ""));
                };
                AddFullRow(ctButtonsGrid, r + 2, btnAllPBs);

               // ── Row 3: PB33 | PB50 | PB66 with sub-rows ──────────────────
                btnPB33 = MakeBtn(s, LblPB33, "Arm/disarm PB33", ColorStrategyOff);
                btnPB50 = MakeBtn(s, LblPB50, "Arm/disarm PB50", ColorStrategyOff);
                btnPB66 = MakeBtn(s, LblPB66, "Arm/disarm PB66", ColorStrategyOff);

                btnPB33Ofs     = MakeOfsBtn(s, "OFS:" + PB33EntryOffsetTicks, "PB33 entry offset — left=−1 right=+1");
                btnPB33StpMode = MakeSmallBtn(s, "STP:" + StopModeAbbr(PB33StopMode), "Cycle PB33 stop mode", Color.FromRgb(60,60,60));
                btnPB33TgtMode = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(PB33TargetMode), "Cycle PB33 target mode", Color.FromRgb(60,60,60));
                btnPB33StpOfs  = MakeOfsBtn(s, "STP:" + PB33StopOffsetTicks, "PB33 stop offset — left=−1 right=+1");
                btnPB33TgtOfs  = MakeOfsBtn(s, "TGT:" + PB33TargetOffsetTicks, "PB33 target offset — left=−1 right=+1");

                btnPB50Ofs     = MakeOfsBtn(s, "OFS:" + PB50EntryOffsetTicks, "PB50 entry offset — left=−1 right=+1");
                btnPB50StpMode = MakeSmallBtn(s, "STP:" + StopModeAbbr(PB50StopMode), "Cycle PB50 stop mode", Color.FromRgb(60,60,60));
                btnPB50TgtMode = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(PB50TargetMode), "Cycle PB50 target mode", Color.FromRgb(60,60,60));
                btnPB50StpOfs  = MakeOfsBtn(s, "STP:" + PB50StopOffsetTicks, "PB50 stop offset — left=−1 right=+1");
                btnPB50TgtOfs  = MakeOfsBtn(s, "TGT:" + PB50TargetOffsetTicks, "PB50 target offset — left=−1 right=+1");

                btnPB66Ofs     = MakeOfsBtn(s, "OFS:" + PB66EntryOffsetTicks, "PB66 entry offset — left=−1 right=+1");
                btnPB66StpMode = MakeSmallBtn(s, "STP:" + StopModeAbbr(PB66StopMode), "Cycle PB66 stop mode", Color.FromRgb(60,60,60));
                btnPB66TgtMode = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(PB66TargetMode), "Cycle PB66 target mode", Color.FromRgb(60,60,60));
                btnPB66StpOfs  = MakeOfsBtn(s, "STP:" + PB66StopOffsetTicks, "PB66 stop offset — left=−1 right=+1");
                btnPB66TgtOfs  = MakeOfsBtn(s, "TGT:" + PB66TargetOffsetTicks, "PB66 target offset — left=−1 right=+1");

                btnPB33.Click += (o, e) => {
                    if (pb33Filled) { lastExitSource = "PB33-BTN"; if (!string.IsNullOrEmpty(atmIdL33) && l33StopTargetSet) { AtmStrategyClose(atmIdL33); Print(DateTime.Now + " PB33 BTN — closing L33"); } else if (!string.IsNullOrEmpty(atmIdS33) && s33StopTargetSet) { AtmStrategyClose(atmIdS33); Print(DateTime.Now + " PB33 BTN — closing S33"); } pb33Filled = false; pb33Armed = AutoReArm; SetBtn(btnPB33, AutoReArm ? ColorArmed : ColorStrategyOff, AutoReArm); if (!AutoReArm) { allPBsArmed = false; SetBtn(btnAllPBs, ColorStrategyOff); } return; }
                    if (pb33Armed) { if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) { AtmStrategyCancelEntryOrder(ordIdL33); l33Active = false; longOrdersPlaced = false; } if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) { AtmStrategyCancelEntryOrder(ordIdS33); s33Active = false; shortOrdersPlaced = false; } pb33Armed = false; allPBsArmed = false; SetBtn(btnPB33, ColorStrategyOff); SetBtn(btnAllPBs, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs); Print(DateTime.Now + " PB33 DISARMED"); return; }
                    if (cancelWatchLockedLong || cancelWatchLockedShort) { Print(DateTime.Now + " PB33 LOCKED — Cancel Watch active, wait for next MC"); return; }
                    pb33Armed = true; pendingPBPlacement = true; SetBtn(btnPB33, ColorArmed, true); UpdateSubBtnColors(true, false, false, btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs); if (pb33Armed && pb50Armed && pb66Armed) { allPBsArmed = true; SetBtn(btnAllPBs, ColorStrategyOn); } Print(DateTime.Now + " PB33 ARMED | pendingPBPlacement set | bullMCActive=" + (activeChanHighLong > 0) + " bearMCActive=" + (activeChanLowShort > 0));
                };
                btnPB50.Click += (o, e) => {
                    if (pb50Filled) { lastExitSource = "PB50-BTN"; if (!string.IsNullOrEmpty(atmIdL50) && l50StopTargetSet) { AtmStrategyClose(atmIdL50); Print(DateTime.Now + " PB50 BTN — closing L50"); } else if (!string.IsNullOrEmpty(atmIdS50) && s50StopTargetSet) { AtmStrategyClose(atmIdS50); Print(DateTime.Now + " PB50 BTN — closing S50"); } pb50Filled = false; pb50Armed = AutoReArm; SetBtn(btnPB50, AutoReArm ? ColorArmed : ColorStrategyOff, AutoReArm); if (!AutoReArm) { allPBsArmed = false; SetBtn(btnAllPBs, ColorStrategyOff); } return; }
                    if (pb50Armed) { if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) { AtmStrategyCancelEntryOrder(ordIdL50); l50Active = false; longOrdersPlaced = false; } if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) { AtmStrategyCancelEntryOrder(ordIdS50); s50Active = false; shortOrdersPlaced = false; } pb50Armed = false; allPBsArmed = false; SetBtn(btnPB50, ColorStrategyOff); SetBtn(btnAllPBs, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs); Print(DateTime.Now + " PB50 DISARMED"); return; }
                    if (cancelWatchLockedLong || cancelWatchLockedShort) { Print(DateTime.Now + " PB50 LOCKED — Cancel Watch active, wait for next MC"); return; }
                    pb50Armed = true; pendingPBPlacement = true; SetBtn(btnPB50, ColorArmed, true); UpdateSubBtnColors(true, false, false, btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs); if (pb33Armed && pb50Armed && pb66Armed) { allPBsArmed = true; SetBtn(btnAllPBs, ColorStrategyOn); } Print(DateTime.Now + " PB50 ARMED | pendingPBPlacement set | bullMCActive=" + (activeChanHighLong > 0) + " bearMCActive=" + (activeChanLowShort > 0));
                };
                btnPB66.Click += (o, e) => {
                    if (pb66Filled) { lastExitSource = "PB66-BTN"; if (!string.IsNullOrEmpty(atmIdL66) && l66StopTargetSet) { AtmStrategyClose(atmIdL66); Print(DateTime.Now + " PB66 BTN — closing L66"); } else if (!string.IsNullOrEmpty(atmIdS66) && s66StopTargetSet) { AtmStrategyClose(atmIdS66); Print(DateTime.Now + " PB66 BTN — closing S66"); } pb66Filled = false; pb66Armed = AutoReArm; SetBtn(btnPB66, AutoReArm ? ColorArmed : ColorStrategyOff, AutoReArm); if (!AutoReArm) { allPBsArmed = false; SetBtn(btnAllPBs, ColorStrategyOff); } return; }
                    if (pb66Armed) { if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) { AtmStrategyCancelEntryOrder(ordIdL66); l66Active = false; longOrdersPlaced = false; } if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) { AtmStrategyCancelEntryOrder(ordIdS66); s66Active = false; shortOrdersPlaced = false; } pb66Armed = false; allPBsArmed = false; SetBtn(btnPB66, ColorStrategyOff); SetBtn(btnAllPBs, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs); Print(DateTime.Now + " PB66 DISARMED"); return; }
                    if (cancelWatchLockedLong || cancelWatchLockedShort) { Print(DateTime.Now + " PB66 LOCKED — Cancel Watch active, wait for next MC"); return; }
                    pb66Armed = true; pendingPBPlacement = true; SetBtn(btnPB66, ColorArmed, true); UpdateSubBtnColors(true, false, false, btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs); if (pb33Armed && pb50Armed && pb66Armed) { allPBsArmed = true; SetBtn(btnAllPBs, ColorStrategyOn); } Print(DateTime.Now + " PB66 ARMED | pendingPBPlacement set | bullMCActive=" + (activeChanHighLong > 0) + " bearMCActive=" + (activeChanLowShort > 0));
                };

                btnPB33Ofs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB33EntryOffsetTicks--; btnPB33Ofs.Content = "OFS:" + PB33EntryOffsetTicks; Print(DateTime.Now + " PB33 OFS → " + PB33EntryOffsetTicks); };
                btnPB33Ofs.PreviewMouseRightButtonDown += (o, e) => { PB33EntryOffsetTicks++; btnPB33Ofs.Content = "OFS:" + PB33EntryOffsetTicks; Print(DateTime.Now + " PB33 OFS → " + PB33EntryOffsetTicks); e.Handled = true; };
                btnPB33StpMode.Click += (o, e) => { PB33StopMode = CycleStop(PB33StopMode); btnPB33StpMode.Content = "STP:" + StopModeAbbr(PB33StopMode); Print(DateTime.Now + " PB33 Stop Mode → " + PB33StopMode); };
                btnPB33TgtMode.Click += (o, e) => { PB33TargetMode = CycleTarget(PB33TargetMode); btnPB33TgtMode.Content = "TGT:" + TargetModeAbbr(PB33TargetMode); Print(DateTime.Now + " PB33 Target Mode → " + PB33TargetMode); };
                btnPB33StpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB33StopOffsetTicks--; btnPB33StpOfs.Content = "STP:" + PB33StopOffsetTicks; Print(DateTime.Now + " PB33 Stop OFS → " + PB33StopOffsetTicks); };
                btnPB33StpOfs.PreviewMouseRightButtonDown += (o, e) => { PB33StopOffsetTicks++; btnPB33StpOfs.Content = "STP:" + PB33StopOffsetTicks; Print(DateTime.Now + " PB33 Stop OFS → " + PB33StopOffsetTicks); e.Handled = true; };
                btnPB33TgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB33TargetOffsetTicks--; btnPB33TgtOfs.Content = "TGT:" + PB33TargetOffsetTicks; Print(DateTime.Now + " PB33 Target OFS → " + PB33TargetOffsetTicks); };
                btnPB33TgtOfs.PreviewMouseRightButtonDown += (o, e) => { PB33TargetOffsetTicks++; btnPB33TgtOfs.Content = "TGT:" + PB33TargetOffsetTicks; Print(DateTime.Now + " PB33 Target OFS → " + PB33TargetOffsetTicks); e.Handled = true; };

                btnPB50Ofs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB50EntryOffsetTicks--; btnPB50Ofs.Content = "OFS:" + PB50EntryOffsetTicks; Print(DateTime.Now + " PB50 OFS → " + PB50EntryOffsetTicks); };
                btnPB50Ofs.PreviewMouseRightButtonDown += (o, e) => { PB50EntryOffsetTicks++; btnPB50Ofs.Content = "OFS:" + PB50EntryOffsetTicks; Print(DateTime.Now + " PB50 OFS → " + PB50EntryOffsetTicks); e.Handled = true; };
                btnPB50StpMode.Click += (o, e) => { PB50StopMode = CycleStop(PB50StopMode); btnPB50StpMode.Content = "STP:" + StopModeAbbr(PB50StopMode); Print(DateTime.Now + " PB50 Stop Mode → " + PB50StopMode); };
                btnPB50TgtMode.Click += (o, e) => { PB50TargetMode = CycleTarget(PB50TargetMode); btnPB50TgtMode.Content = "TGT:" + TargetModeAbbr(PB50TargetMode); Print(DateTime.Now + " PB50 Target Mode → " + PB50TargetMode); };
                btnPB50StpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB50StopOffsetTicks--; btnPB50StpOfs.Content = "STP:" + PB50StopOffsetTicks; Print(DateTime.Now + " PB50 Stop OFS → " + PB50StopOffsetTicks); };
                btnPB50StpOfs.PreviewMouseRightButtonDown += (o, e) => { PB50StopOffsetTicks++; btnPB50StpOfs.Content = "STP:" + PB50StopOffsetTicks; Print(DateTime.Now + " PB50 Stop OFS → " + PB50StopOffsetTicks); e.Handled = true; };
                btnPB50TgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB50TargetOffsetTicks--; btnPB50TgtOfs.Content = "TGT:" + PB50TargetOffsetTicks; Print(DateTime.Now + " PB50 Target OFS → " + PB50TargetOffsetTicks); };
                btnPB50TgtOfs.PreviewMouseRightButtonDown += (o, e) => { PB50TargetOffsetTicks++; btnPB50TgtOfs.Content = "TGT:" + PB50TargetOffsetTicks; Print(DateTime.Now + " PB50 Target OFS → " + PB50TargetOffsetTicks); e.Handled = true; };

                btnPB66Ofs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB66EntryOffsetTicks--; btnPB66Ofs.Content = "OFS:" + PB66EntryOffsetTicks; Print(DateTime.Now + " PB66 OFS → " + PB66EntryOffsetTicks); };
                btnPB66Ofs.PreviewMouseRightButtonDown += (o, e) => { PB66EntryOffsetTicks++; btnPB66Ofs.Content = "OFS:" + PB66EntryOffsetTicks; Print(DateTime.Now + " PB66 OFS → " + PB66EntryOffsetTicks); e.Handled = true; };
                btnPB66StpMode.Click += (o, e) => { PB66StopMode = CycleStop(PB66StopMode); btnPB66StpMode.Content = "STP:" + StopModeAbbr(PB66StopMode); Print(DateTime.Now + " PB66 Stop Mode → " + PB66StopMode); };
                btnPB66TgtMode.Click += (o, e) => { PB66TargetMode = CycleTarget(PB66TargetMode); btnPB66TgtMode.Content = "TGT:" + TargetModeAbbr(PB66TargetMode); Print(DateTime.Now + " PB66 Target Mode → " + PB66TargetMode); };
                btnPB66StpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB66StopOffsetTicks--; btnPB66StpOfs.Content = "STP:" + PB66StopOffsetTicks; Print(DateTime.Now + " PB66 Stop OFS → " + PB66StopOffsetTicks); };
                btnPB66StpOfs.PreviewMouseRightButtonDown += (o, e) => { PB66StopOffsetTicks++; btnPB66StpOfs.Content = "STP:" + PB66StopOffsetTicks; Print(DateTime.Now + " PB66 Stop OFS → " + PB66StopOffsetTicks); e.Handled = true; };
                btnPB66TgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; PB66TargetOffsetTicks--; btnPB66TgtOfs.Content = "TGT:" + PB66TargetOffsetTicks; Print(DateTime.Now + " PB66 Target OFS → " + PB66TargetOffsetTicks); };
                btnPB66TgtOfs.PreviewMouseRightButtonDown += (o, e) => { PB66TargetOffsetTicks++; btnPB66TgtOfs.Content = "TGT:" + PB66TargetOffsetTicks; Print(DateTime.Now + " PB66 Target OFS → " + PB66TargetOffsetTicks); e.Handled = true; };

                allSubButtons.AddRange(new[] { btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs,
                                               btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs,
                                               btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs });

                AddThirdRowWithSubRows(ctButtonsGrid, r + 3,
                    btnPB33, btnPB50, btnPB66,
                    btnPB33Ofs, btnPB50Ofs, btnPB66Ofs,
                    btnPB33StpMode, btnPB33TgtMode, btnPB50StpMode, btnPB50TgtMode, btnPB66StpMode, btnPB66TgtMode,
                    btnPB33StpOfs, btnPB33TgtOfs, btnPB50StpOfs, btnPB50TgtOfs, btnPB66StpOfs, btnPB66TgtOfs);

                // ── Row 4: Lmt Buy | Lmt Sell ────────────────────────────────
                btnLmtBuy  = MakeBtn(s, LblLmtBuy,  "Limit buy at clicked price — arm then click chart price level", ColorStrategyOff);
                btnLmtSell = MakeBtn(s, LblLmtSell, "Limit sell at clicked price — arm then click chart price level", ColorStrategyOff);
                btnLmtBuyStpCycle  = MakeSmallBtn(s, "STP:" + StopModeAbbr(BBLSABR_StopMode),   "Cycle Lmt Buy stop mode",   Color.FromRgb(60,60,60));
                btnLmtBuyTgtCycle  = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(BBLSABR_TargetMode), "Cycle Lmt Buy target mode", Color.FromRgb(60,60,60));
                btnLmtSellStpCycle = MakeSmallBtn(s, "STP:" + StopModeAbbr(BBLSABR_StopMode),   "Cycle Lmt Sell stop mode",  Color.FromRgb(60,60,60));
                btnLmtSellTgtCycle = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(BBLSABR_TargetMode), "Cycle Lmt Sell target mode",Color.FromRgb(60,60,60));
                btnLmtBuyStpOfs    = MakeOfsBtn(s, "STP:" + BBLSABR_StopOffsetTicks,   "Lmt Buy stop offset");
                btnLmtBuyTgtOfs    = MakeOfsBtn(s, "TGT:" + BBLSABR_TargetOffsetTicks, "Lmt Buy target offset");
                btnLmtSellStpOfs   = MakeOfsBtn(s, "STP:" + BBLSABR_StopOffsetTicks,   "Lmt Sell stop offset");
                btnLmtSellTgtOfs   = MakeOfsBtn(s, "TGT:" + BBLSABR_TargetOffsetTicks, "Lmt Sell target offset");

                btnLmtBuy.Click += (o, e) => {
                    if (lmtBuyWaitingClick) { lmtBuyWaitingClick = false; SetBtn(btnLmtBuy, ColorStrategyOff); Print(DateTime.Now + " Lmt Buy disarmed"); return; }
                    lmtSellWaitingClick = false; if (btnLmtSell != null) SetBtn(btnLmtSell, ColorStrategyOff);
                    bbBLWaitingClick = saBRWaitingClick = seLWaitingClick = seSWaitingClick = speedoWaitingClick = false;
                    lmtBuyWaitingClick = true; SetBtn(btnLmtBuy, ColorArmedBarSel, true);
                    UpdateSubBtnColors(true, false, false, null, btnLmtBuyStpCycle, btnLmtBuyTgtCycle, btnLmtBuyStpOfs, btnLmtBuyTgtOfs);
                    Print(DateTime.Now + " Lmt Buy ARMED — click a price level on the chart");
                };
             btnLmtBuy.PreviewMouseRightButtonDown += (o, e) => {
                    e.Handled = true;
                    for (int i = atmIdsLmtBuy.Count - 1; i >= 0; i--)
                    {
                        if (filledLmtBuy[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsLmtBuy[i])) AtmStrategyCancelEntryOrder(ordIdsLmtBuy[i]);
                        atmIdsLmtBuy.RemoveAt(i); ordIdsLmtBuy.RemoveAt(i);
                        stopsLmtBuy.RemoveAt(i); targetsLmtBuy.RemoveAt(i); entriesLmtBuy.RemoveAt(i);
                        filledLmtBuy.RemoveAt(i); callbackLmtBuy.RemoveAt(i);
                        stopCalcsLmtBuy.RemoveAt(i); tgtCalcsLmtBuy.RemoveAt(i);
                    }
                    UpdateLmtButtonLabel(btnLmtBuy, atmIdsLmtBuy, "LmtBuy");
                    Print(DateTime.Now + " Lmt Buy — unfilled orders cancelled");
                };
                btnLmtSell.Click += (o, e) => {
                    if (lmtSellWaitingClick) { lmtSellWaitingClick = false; SetBtn(btnLmtSell, ColorStrategyOff); Print(DateTime.Now + " Lmt Sell disarmed"); return; }
                    lmtBuyWaitingClick = false; if (btnLmtBuy != null) SetBtn(btnLmtBuy, ColorStrategyOff);
                    bbBLWaitingClick = saBRWaitingClick = seLWaitingClick = seSWaitingClick = speedoWaitingClick = false;
                    lmtSellWaitingClick = true; SetBtn(btnLmtSell, ColorArmedBarSel, true);
                    UpdateSubBtnColors(true, false, false, null, btnLmtSellStpCycle, btnLmtSellTgtCycle, btnLmtSellStpOfs, btnLmtSellTgtOfs);
                    Print(DateTime.Now + " Lmt Sell ARMED — click a price level on the chart");
                };

                btnLmtSell.PreviewMouseRightButtonDown += (o, e) => {
                    e.Handled = true;
                    for (int i = atmIdsLmtSell.Count - 1; i >= 0; i--)
                    {
                        if (filledLmtSell[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsLmtSell[i])) AtmStrategyCancelEntryOrder(ordIdsLmtSell[i]);
                        atmIdsLmtSell.RemoveAt(i); ordIdsLmtSell.RemoveAt(i);
                        stopsLmtSell.RemoveAt(i); targetsLmtSell.RemoveAt(i); entriesLmtSell.RemoveAt(i);
                        filledLmtSell.RemoveAt(i); callbackLmtSell.RemoveAt(i);
                        stopCalcsLmtSell.RemoveAt(i); tgtCalcsLmtSell.RemoveAt(i);
                    }
                    UpdateLmtButtonLabel(btnLmtSell, atmIdsLmtSell, "LmtSell");
                    Print(DateTime.Now + " Lmt Sell — unfilled orders cancelled");
                };
                btnLmtBuyStpCycle.Click  += (o, e) => { BBLSABR_StopMode   = CycleStop(BBLSABR_StopMode);     btnLmtBuyStpCycle.Content  = "STP:" + StopModeAbbr(BBLSABR_StopMode);     btnLmtSellStpCycle.Content = "STP:" + StopModeAbbr(BBLSABR_StopMode);   Print(DateTime.Now + " Lmt Buy/Sell Stop Mode → " + BBLSABR_StopMode); };
                btnLmtBuyTgtCycle.Click  += (o, e) => { BBLSABR_TargetMode = CycleTarget(BBLSABR_TargetMode); btnLmtBuyTgtCycle.Content  = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); btnLmtSellTgtCycle.Content = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); Print(DateTime.Now + " Lmt Buy/Sell Target Mode → " + BBLSABR_TargetMode); };
                btnLmtSellStpCycle.Click += (o, e) => { BBLSABR_StopMode   = CycleStop(BBLSABR_StopMode);     btnLmtBuyStpCycle.Content  = "STP:" + StopModeAbbr(BBLSABR_StopMode);     btnLmtSellStpCycle.Content = "STP:" + StopModeAbbr(BBLSABR_StopMode);   Print(DateTime.Now + " Lmt Buy/Sell Stop Mode → " + BBLSABR_StopMode); };
                btnLmtSellTgtCycle.Click += (o, e) => { BBLSABR_TargetMode = CycleTarget(BBLSABR_TargetMode); btnLmtBuyTgtCycle.Content  = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); btnLmtSellTgtCycle.Content = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); Print(DateTime.Now + " Lmt Buy/Sell Target Mode → " + BBLSABR_TargetMode); };
                btnLmtBuyStpOfs.PreviewMouseLeftButtonDown   += (o, e) => { e.Handled = true; BBLSABR_StopOffsetTicks--;   btnLmtBuyStpOfs.Content  = "STP:" + BBLSABR_StopOffsetTicks;   btnLmtSellStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; };
                btnLmtBuyStpOfs.PreviewMouseRightButtonDown  += (o, e) => { BBLSABR_StopOffsetTicks++;   btnLmtBuyStpOfs.Content  = "STP:" + BBLSABR_StopOffsetTicks;   btnLmtSellStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; e.Handled = true; };
                btnLmtBuyTgtOfs.PreviewMouseLeftButtonDown   += (o, e) => { e.Handled = true; BBLSABR_TargetOffsetTicks--; btnLmtBuyTgtOfs.Content  = "TGT:" + BBLSABR_TargetOffsetTicks; btnLmtSellTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; };
                btnLmtBuyTgtOfs.PreviewMouseRightButtonDown  += (o, e) => { BBLSABR_TargetOffsetTicks++; btnLmtBuyTgtOfs.Content  = "TGT:" + BBLSABR_TargetOffsetTicks; btnLmtSellTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; e.Handled = true; };
                btnLmtSellStpOfs.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; BBLSABR_StopOffsetTicks--;   btnLmtBuyStpOfs.Content  = "STP:" + BBLSABR_StopOffsetTicks;   btnLmtSellStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; };
                btnLmtSellStpOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_StopOffsetTicks++;   btnLmtBuyStpOfs.Content  = "STP:" + BBLSABR_StopOffsetTicks;   btnLmtSellStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; e.Handled = true; };
                btnLmtSellTgtOfs.PreviewMouseLeftButtonDown  += (o, e) => { e.Handled = true; BBLSABR_TargetOffsetTicks--; btnLmtBuyTgtOfs.Content  = "TGT:" + BBLSABR_TargetOffsetTicks; btnLmtSellTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; };
                btnLmtSellTgtOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_TargetOffsetTicks++; btnLmtBuyTgtOfs.Content  = "TGT:" + BBLSABR_TargetOffsetTicks; btnLmtSellTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; e.Handled = true; };

                allSubButtons.AddRange(new[] { btnLmtBuyStpCycle, btnLmtBuyTgtCycle, btnLmtBuyStpOfs, btnLmtBuyTgtOfs,
                                               btnLmtSellStpCycle, btnLmtSellTgtCycle, btnLmtSellStpOfs, btnLmtSellTgtOfs });
                var btnLmtBuyOfsPlaceholder  = MakeOfsBtn(s, "", "");
                var btnLmtSellOfsPlaceholder = MakeOfsBtn(s, "", "");
                btnLmtBuyOfsPlaceholder.Visibility  = Visibility.Collapsed;
                btnLmtSellOfsPlaceholder.Visibility = Visibility.Collapsed;
                AddHalfRowWithFullSubRows(ctButtonsGrid, r + 4, btnLmtBuy, btnLmtSell,
                    btnLmtBuyStpCycle, btnLmtBuyTgtCycle, btnLmtSellStpCycle, btnLmtSellTgtCycle,
                    btnLmtBuyStpOfs, btnLmtBuyTgtOfs, btnLmtSellStpOfs, btnLmtSellTgtOfs);

                // ── Row 5: Lmt Buy L | Lmt Sell H ────────────────────────────
                btnBBBL = MakeBtn(s, LblBBBL, "Limit buy below bar low — click to arm, then click chart bar", ColorStrategyOff);
                btnSABR = MakeBtn(s, LblSABR, "Limit sell above bar high — click to arm, then click chart bar", ColorStrategyOff);
                btnBBBLOfs      = MakeOfsBtn(s, "OFS:" + BBLSABR_EntryOffsetTicks, "Lmt Buy L entry offset");
                btnSABROfs      = MakeOfsBtn(s, "OFS:" + BBLSABR_EntryOffsetTicks, "Lmt Sell H entry offset");
                btnBBBLStpCycle = MakeSmallBtn(s, "STP:" + StopModeAbbr(BBLSABR_StopMode), "Cycle Lmt Buy L stop mode", Color.FromRgb(60,60,60));
                btnBBBLTgtCycle = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(BBLSABR_TargetMode), "Cycle Lmt Buy L target mode", Color.FromRgb(60,60,60));
                btnSABRStpCycle = MakeSmallBtn(s, "STP:" + StopModeAbbr(BBLSABR_StopMode), "Cycle Lmt Sell H stop mode", Color.FromRgb(60,60,60));
                btnSABRTgtCycle = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(BBLSABR_TargetMode), "Cycle Lmt Sell H target mode", Color.FromRgb(60,60,60));
                btnBBBLStpOfs   = MakeOfsBtn(s, "STP:" + BBLSABR_StopOffsetTicks, "Lmt Buy L stop offset");
                btnBBBLTgtOfs   = MakeOfsBtn(s, "TGT:" + BBLSABR_TargetOffsetTicks, "Lmt Buy L target offset");
                btnSABRStpOfs   = MakeOfsBtn(s, "STP:" + BBLSABR_StopOffsetTicks, "Lmt Sell H stop offset");
                btnSABRTgtOfs   = MakeOfsBtn(s, "TGT:" + BBLSABR_TargetOffsetTicks, "Lmt Sell H target offset");

                btnBBBL.Click += (o, e) => {
                    if (bbBLWaitingClick) { bbBLWaitingClick = false; SetBtn(btnBBBL, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnBBBLOfs, btnBBBLStpCycle, btnBBBLTgtCycle, btnBBBLStpOfs, btnBBBLTgtOfs); Print(DateTime.Now + " Lmt Buy L disarmed"); return; }
                    saBRWaitingClick = seLWaitingClick = seSWaitingClick = speedoWaitingClick = false;
                    bbBLWaitingClick = true; SetBtn(btnBBBL, ColorArmedBarSel, true);
                    UpdateSubBtnColors(true, false, false, btnBBBLOfs, btnBBBLStpCycle, btnBBBLTgtCycle, btnBBBLStpOfs, btnBBBLTgtOfs);
                    Print(""); Print(DateTime.Now + " Lmt Buy L ARMED — click a chart bar");
                };
              btnBBBL.PreviewMouseRightButtonDown += (o, e) => {
                    e.Handled = true;
                    for (int i = atmIdsBBBL.Count - 1; i >= 0; i--)
                    {
                        if (filledBBBL[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsBBBL[i])) AtmStrategyCancelEntryOrder(ordIdsBBBL[i]);
                        atmIdsBBBL.RemoveAt(i); ordIdsBBBL.RemoveAt(i);
                        stopsBBBL.RemoveAt(i); targetsBBBL.RemoveAt(i); entriesBBBL.RemoveAt(i);
                        filledBBBL.RemoveAt(i); callbackBBBL.RemoveAt(i);
                        stopCalcsBBBL.RemoveAt(i); tgtCalcsBBBL.RemoveAt(i);
                        barsAgoBBBL.RemoveAt(i); inMCBBBL.RemoveAt(i);
                    }
                    UpdateLmtButtonLabel(btnBBBL, atmIdsBBBL, "BBBL");
                    Print(DateTime.Now + " Lmt Buy L — unfilled orders cancelled");
                };
                btnSABR.Click += (o, e) => {
                    if (saBRWaitingClick) { saBRWaitingClick = false; SetBtn(btnSABR, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnSABROfs, btnSABRStpCycle, btnSABRTgtCycle, btnSABRStpOfs, btnSABRTgtOfs); Print(DateTime.Now + " Lmt Sell H disarmed"); return; }
                    bbBLWaitingClick = seLWaitingClick = seSWaitingClick = speedoWaitingClick = false;
                    saBRWaitingClick = true; SetBtn(btnSABR, ColorArmedBarSel, true);
                    UpdateSubBtnColors(true, false, false, btnSABROfs, btnSABRStpCycle, btnSABRTgtCycle, btnSABRStpOfs, btnSABRTgtOfs);
                    Print(""); Print(DateTime.Now + " Lmt Sell H ARMED — click a chart bar");
                };

                btnSABR.PreviewMouseRightButtonDown += (o, e) => {
                    e.Handled = true;
                    for (int i = atmIdsSABR.Count - 1; i >= 0; i--)
                    {
                        if (filledSABR[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsSABR[i])) AtmStrategyCancelEntryOrder(ordIdsSABR[i]);
                        atmIdsSABR.RemoveAt(i); ordIdsSABR.RemoveAt(i);
                        stopsSABR.RemoveAt(i); targetsSABR.RemoveAt(i); entriesSABR.RemoveAt(i);
                        filledSABR.RemoveAt(i); callbackSABR.RemoveAt(i);
                        stopCalcsSABR.RemoveAt(i); tgtCalcsSABR.RemoveAt(i);
                        barsAgoSABR.RemoveAt(i); inMCSABR.RemoveAt(i);
                    }
                    UpdateLmtButtonLabel(btnSABR, atmIdsSABR, "SABR");
                    Print(DateTime.Now + " Lmt Sell H — unfilled orders cancelled");
                };
                btnBBBLOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; BBLSABR_EntryOffsetTicks--; btnBBBLOfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; btnSABROfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H OFS → " + BBLSABR_EntryOffsetTicks); };
                btnBBBLOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_EntryOffsetTicks++; btnBBBLOfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; btnSABROfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H OFS → " + BBLSABR_EntryOffsetTicks); e.Handled = true; };
                btnSABROfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; BBLSABR_EntryOffsetTicks--; btnBBBLOfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; btnSABROfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H OFS → " + BBLSABR_EntryOffsetTicks); };
                btnSABROfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_EntryOffsetTicks++; btnBBBLOfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; btnSABROfs.Content = "OFS:" + BBLSABR_EntryOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H OFS → " + BBLSABR_EntryOffsetTicks); e.Handled = true; };
                btnBBBLStpCycle.Click += (o, e) => { BBLSABR_StopMode = CycleStop(BBLSABR_StopMode); btnBBBLStpCycle.Content = "STP:" + StopModeAbbr(BBLSABR_StopMode); btnSABRStpCycle.Content = "STP:" + StopModeAbbr(BBLSABR_StopMode); Print(DateTime.Now + " Lmt Buy L/Sell H Stop Mode → " + BBLSABR_StopMode); };
                btnBBBLTgtCycle.Click += (o, e) => { BBLSABR_TargetMode = CycleTarget(BBLSABR_TargetMode); btnBBBLTgtCycle.Content = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); btnSABRTgtCycle.Content = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); Print(DateTime.Now + " Lmt Buy L/Sell H Target Mode → " + BBLSABR_TargetMode); };
                btnSABRStpCycle.Click += (o, e) => { BBLSABR_StopMode = CycleStop(BBLSABR_StopMode); btnBBBLStpCycle.Content = "STP:" + StopModeAbbr(BBLSABR_StopMode); btnSABRStpCycle.Content = "STP:" + StopModeAbbr(BBLSABR_StopMode); Print(DateTime.Now + " Lmt Buy L/Sell H Stop Mode → " + BBLSABR_StopMode); };
                btnSABRTgtCycle.Click += (o, e) => { BBLSABR_TargetMode = CycleTarget(BBLSABR_TargetMode); btnBBBLTgtCycle.Content = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); btnSABRTgtCycle.Content = "TGT:" + TargetModeAbbr(BBLSABR_TargetMode); Print(DateTime.Now + " Lmt Buy L/Sell H Target Mode → " + BBLSABR_TargetMode); };
                btnBBBLStpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; BBLSABR_StopOffsetTicks--; btnBBBLStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; btnSABRStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Stop OFS → " + BBLSABR_StopOffsetTicks); };
                btnBBBLStpOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_StopOffsetTicks++; btnBBBLStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; btnSABRStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Stop OFS → " + BBLSABR_StopOffsetTicks); e.Handled = true; };
                btnBBBLTgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; BBLSABR_TargetOffsetTicks--; btnBBBLTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; btnSABRTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Target OFS → " + BBLSABR_TargetOffsetTicks); };
                btnBBBLTgtOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_TargetOffsetTicks++; btnBBBLTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; btnSABRTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Target OFS → " + BBLSABR_TargetOffsetTicks); e.Handled = true; };
                btnSABRStpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; BBLSABR_StopOffsetTicks--; btnBBBLStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; btnSABRStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Stop OFS → " + BBLSABR_StopOffsetTicks); };
                btnSABRStpOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_StopOffsetTicks++; btnBBBLStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; btnSABRStpOfs.Content = "STP:" + BBLSABR_StopOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Stop OFS → " + BBLSABR_StopOffsetTicks); e.Handled = true; };
                btnSABRTgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; BBLSABR_TargetOffsetTicks--; btnBBBLTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; btnSABRTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Target OFS → " + BBLSABR_TargetOffsetTicks); };
                btnSABRTgtOfs.PreviewMouseRightButtonDown += (o, e) => { BBLSABR_TargetOffsetTicks++; btnBBBLTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; btnSABRTgtOfs.Content = "TGT:" + BBLSABR_TargetOffsetTicks; Print(DateTime.Now + " Lmt Buy L/Sell H Target OFS → " + BBLSABR_TargetOffsetTicks); e.Handled = true; };

                allSubButtons.AddRange(new[] { btnBBBLOfs, btnBBBLStpCycle, btnBBBLTgtCycle, btnBBBLStpOfs, btnBBBLTgtOfs,
                                               btnSABROfs, btnSABRStpCycle, btnSABRTgtCycle, btnSABRStpOfs, btnSABRTgtOfs });
                AddHalfRowWithFullSubRows(ctButtonsGrid, r + 5, btnBBBL, btnSABR,
                    btnBBBLStpCycle, btnBBBLTgtCycle, btnSABRStpCycle, btnSABRTgtCycle,
                    btnBBBLStpOfs, btnBBBLTgtOfs, btnSABRStpOfs, btnSABRTgtOfs,
                    btnBBBLOfs, btnSABROfs);

                // ── Row 5: SE L | SE S ────────────────────────────────────────
                btnSEL = MakeBtn(s, LblSEL, "Signal entry long — click to arm, then click signal bar", ColorStrategyOff);
                btnSES = MakeBtn(s, LblSES, "Signal entry short — click to arm, then click signal bar", ColorStrategyOff);
               btnSELOfs      = MakeOfsBtn(s, "OFS:" + SE_EntryOffsetTicks, "SE L entry offset");
                btnSESOfs      = MakeOfsBtn(s, "OFS:" + SE_EntryOffsetTicks, "SE S entry offset");
                btnSEOrderType  = MakeSmallBtn(s, SE_OrderType == OrderType.StopMarket ? "StpMkt" : "StpLmt", "Cycle SE order type", Color.FromRgb(60,60,60));
                btnSEOrderType2 = MakeSmallBtn(s, SE_OrderType == OrderType.StopMarket ? "StpMkt" : "StpLmt", "Cycle SE order type", Color.FromRgb(60,60,60));
                btnSELStpCycle = MakeSmallBtn(s, "STP:" + StopModeAbbr(SE_StopMode), "Cycle SE stop mode", Color.FromRgb(60,60,60));
                btnSELTgtCycle = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(SE_TargetMode), "Cycle SE target mode", Color.FromRgb(60,60,60));
                btnSESStpCycle = MakeSmallBtn(s, "STP:" + StopModeAbbr(SE_StopMode), "Cycle SE S stop mode", Color.FromRgb(60,60,60));
                btnSESTgtCycle = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(SE_TargetMode), "Cycle SE S target mode", Color.FromRgb(60,60,60));
                btnSELStpOfs   = MakeOfsBtn(s, "STP:" + SE_StopOffsetTicks, "SE L stop offset");
                btnSELTgtOfs   = MakeOfsBtn(s, "TGT:" + SE_TargetOffsetTicks, "SE L target offset");
                btnSESStpOfs   = MakeOfsBtn(s, "STP:" + SE_StopOffsetTicks, "SE S stop offset");
                btnSESTgtOfs   = MakeOfsBtn(s, "TGT:" + SE_TargetOffsetTicks, "SE S target offset");

               btnSEL.Click += (o, e) => {
                    if (seLWaitingClick) { seLWaitingClick = false; SetBtn(btnSEL, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnSELOfs, btnSELStpCycle, btnSELTgtCycle, btnSELStpOfs, btnSELTgtOfs); Print(DateTime.Now + " SE L disarmed"); return; }
                    bbBLWaitingClick = saBRWaitingClick = seSWaitingClick = speedoWaitingClick = false;
                    seLWaitingClick = true; SetBtn(btnSEL, ColorArmedBarSel, true);
                    UpdateSubBtnColors(true, false, false, btnSELOfs, btnSELStpCycle, btnSELTgtCycle, btnSELStpOfs, btnSELTgtOfs);
                    Print(""); Print(DateTime.Now + " SE L ARMED — click signal bar");
                };
              btnSEL.PreviewMouseRightButtonDown += (o, e) => {
                    e.Handled = true;
                    for (int i = atmIdsSEL.Count - 1; i >= 0; i--)
                    {
                        if (filledSEL[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsSEL[i])) AtmStrategyCancelEntryOrder(ordIdsSEL[i]);
                        atmIdsSEL.RemoveAt(i); ordIdsSEL.RemoveAt(i);
                        stopsSEL.RemoveAt(i); targetsSEL.RemoveAt(i); entriesSEL.RemoveAt(i);
                        filledSEL.RemoveAt(i); callbackSEL.RemoveAt(i);
                        stopCalcsSEL.RemoveAt(i); tgtCalcsSEL.RemoveAt(i);
                    }
                    UpdateLmtButtonLabel(btnSEL, atmIdsSEL, "SEL");
                    Print(DateTime.Now + " SE L — unfilled orders cancelled");
                };
                btnSES.Click += (o, e) => {
                    if (seSWaitingClick) { seSWaitingClick = false; SetBtn(btnSES, ColorStrategyOff); UpdateSubBtnColors(false, false, false, btnSESOfs, btnSESStpCycle, btnSESTgtCycle, btnSESStpOfs, btnSESTgtOfs); Print(DateTime.Now + " SE S disarmed"); return; }
                    bbBLWaitingClick = saBRWaitingClick = seLWaitingClick = speedoWaitingClick = false;
                    seSWaitingClick = true; SetBtn(btnSES, ColorArmedBarSel, true);
                    UpdateSubBtnColors(true, false, false, btnSESOfs, btnSESStpCycle, btnSESTgtCycle, btnSESStpOfs, btnSESTgtOfs);
                    Print(""); Print(DateTime.Now + " SE S ARMED — click signal bar");
                };

                btnSES.PreviewMouseRightButtonDown += (o, e) => {
                    e.Handled = true;
                    for (int i = atmIdsSES.Count - 1; i >= 0; i--)
                    {
                        if (filledSES[i]) continue;
                        if (!string.IsNullOrEmpty(ordIdsSES[i])) AtmStrategyCancelEntryOrder(ordIdsSES[i]);
                        atmIdsSES.RemoveAt(i); ordIdsSES.RemoveAt(i);
                        stopsSES.RemoveAt(i); targetsSES.RemoveAt(i); entriesSES.RemoveAt(i);
                        filledSES.RemoveAt(i); callbackSES.RemoveAt(i);
                        stopCalcsSES.RemoveAt(i); tgtCalcsSES.RemoveAt(i);
                    }
                    UpdateLmtButtonLabel(btnSES, atmIdsSES, "SES");
                    Print(DateTime.Now + " SE S — unfilled orders cancelled");
                };
                btnSEOrderType.Click += (o, e) => {
                    SE_OrderType = SE_OrderType == OrderType.StopMarket ? OrderType.StopLimit : OrderType.StopMarket;
                    string lbl = SE_OrderType == OrderType.StopMarket ? "StpMkt" : "StpLmt";
                    btnSEOrderType.Content = lbl; btnSEOrderType2.Content = lbl;
                    Print(DateTime.Now + " SE Order Type → " + SE_OrderType);
                };
                btnSEOrderType2.Click += (o, e) => {
                    SE_OrderType = SE_OrderType == OrderType.StopMarket ? OrderType.StopLimit : OrderType.StopMarket;
                    string lbl = SE_OrderType == OrderType.StopMarket ? "StpMkt" : "StpLmt";
                    btnSEOrderType.Content = lbl; btnSEOrderType2.Content = lbl;
                    Print(DateTime.Now + " SE Order Type → " + SE_OrderType);
                };
                btnSELOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; SE_EntryOffsetTicks--; btnSELOfs.Content = "OFS:" + SE_EntryOffsetTicks; btnSESOfs.Content = "OFS:" + SE_EntryOffsetTicks; Print(DateTime.Now + " SE OFS → " + SE_EntryOffsetTicks); };
                btnSELOfs.PreviewMouseRightButtonDown += (o, e) => { SE_EntryOffsetTicks++; btnSELOfs.Content = "OFS:" + SE_EntryOffsetTicks; btnSESOfs.Content = "OFS:" + SE_EntryOffsetTicks; Print(DateTime.Now + " SE OFS → " + SE_EntryOffsetTicks); e.Handled = true; };
                btnSESOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; SE_EntryOffsetTicks--; btnSELOfs.Content = "OFS:" + SE_EntryOffsetTicks; btnSESOfs.Content = "OFS:" + SE_EntryOffsetTicks; Print(DateTime.Now + " SE OFS → " + SE_EntryOffsetTicks); };
                btnSESOfs.PreviewMouseRightButtonDown += (o, e) => { SE_EntryOffsetTicks++; btnSELOfs.Content = "OFS:" + SE_EntryOffsetTicks; btnSESOfs.Content = "OFS:" + SE_EntryOffsetTicks; Print(DateTime.Now + " SE OFS → " + SE_EntryOffsetTicks); e.Handled = true; };
                btnSELStpCycle.Click += (o, e) => { SE_StopMode = CycleStop(SE_StopMode); btnSELStpCycle.Content = "STP:" + StopModeAbbr(SE_StopMode); btnSESStpCycle.Content = "STP:" + StopModeAbbr(SE_StopMode); Print(DateTime.Now + " SE Stop Mode → " + SE_StopMode); };
                btnSELTgtCycle.Click += (o, e) => { SE_TargetMode = CycleTarget(SE_TargetMode); btnSELTgtCycle.Content = "TGT:" + TargetModeAbbr(SE_TargetMode); btnSESTgtCycle.Content = "TGT:" + TargetModeAbbr(SE_TargetMode); Print(DateTime.Now + " SE Target Mode → " + SE_TargetMode); };
                btnSESStpCycle.Click += (o, e) => { SE_StopMode = CycleStop(SE_StopMode); btnSELStpCycle.Content = "STP:" + StopModeAbbr(SE_StopMode); btnSESStpCycle.Content = "STP:" + StopModeAbbr(SE_StopMode); Print(DateTime.Now + " SE Stop Mode → " + SE_StopMode); };
                btnSESTgtCycle.Click += (o, e) => { SE_TargetMode = CycleTarget(SE_TargetMode); btnSELTgtCycle.Content = "TGT:" + TargetModeAbbr(SE_TargetMode); btnSESTgtCycle.Content = "TGT:" + TargetModeAbbr(SE_TargetMode); Print(DateTime.Now + " SE Target Mode → " + SE_TargetMode); };
                btnSELStpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; SE_StopOffsetTicks--; btnSELStpOfs.Content = "STP:" + SE_StopOffsetTicks; btnSESStpOfs.Content = "STP:" + SE_StopOffsetTicks; Print(DateTime.Now + " SE Stop OFS → " + SE_StopOffsetTicks); };
                btnSELStpOfs.PreviewMouseRightButtonDown += (o, e) => { SE_StopOffsetTicks++; btnSELStpOfs.Content = "STP:" + SE_StopOffsetTicks; btnSESStpOfs.Content = "STP:" + SE_StopOffsetTicks; Print(DateTime.Now + " SE Stop OFS → " + SE_StopOffsetTicks); e.Handled = true; };
                btnSELTgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; SE_TargetOffsetTicks--; btnSELTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; btnSESTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; Print(DateTime.Now + " SE Target OFS → " + SE_TargetOffsetTicks); };
                btnSELTgtOfs.PreviewMouseRightButtonDown += (o, e) => { SE_TargetOffsetTicks++; btnSELTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; btnSESTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; Print(DateTime.Now + " SE Target OFS → " + SE_TargetOffsetTicks); e.Handled = true; };
                btnSESStpOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; SE_StopOffsetTicks--; btnSELStpOfs.Content = "STP:" + SE_StopOffsetTicks; btnSESStpOfs.Content = "STP:" + SE_StopOffsetTicks; Print(DateTime.Now + " SE Stop OFS → " + SE_StopOffsetTicks); };
                btnSESStpOfs.PreviewMouseRightButtonDown += (o, e) => { SE_StopOffsetTicks++; btnSELStpOfs.Content = "STP:" + SE_StopOffsetTicks; btnSESStpOfs.Content = "STP:" + SE_StopOffsetTicks; Print(DateTime.Now + " SE Stop OFS → " + SE_StopOffsetTicks); e.Handled = true; };
                btnSESTgtOfs.PreviewMouseLeftButtonDown += (o, e) => { e.Handled = true; SE_TargetOffsetTicks--; btnSELTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; btnSESTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; Print(DateTime.Now + " SE Target OFS → " + SE_TargetOffsetTicks); };
                btnSESTgtOfs.PreviewMouseRightButtonDown += (o, e) => { SE_TargetOffsetTicks++; btnSELTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; btnSESTgtOfs.Content = "TGT:" + SE_TargetOffsetTicks; Print(DateTime.Now + " SE Target OFS → " + SE_TargetOffsetTicks); e.Handled = true; };

                allSubButtons.AddRange(new[] { btnSELOfs, btnSEOrderType, btnSELStpCycle, btnSELTgtCycle, btnSELStpOfs, btnSELTgtOfs,
                                               btnSESOfs, btnSEOrderType2, btnSESStpCycle, btnSESTgtCycle, btnSESStpOfs, btnSESTgtOfs });
              AddHalfRowWithFullSubRows(ctButtonsGrid, r + 6, btnSEL, btnSES,
                    btnSELStpCycle, btnSELTgtCycle, btnSESStpCycle, btnSESTgtCycle,
                    btnSELStpOfs, btnSELTgtOfs, btnSESStpOfs, btnSESTgtOfs,
                    btnSELOfs, btnSESOfs,
                    btnSEOrderType, btnSEOrderType2);

             // ── Row 6: SPEEDO — RETIRED ───────────────────────────────────
                //btnSpeedo = MakeBtn(s, LblSpeedo, "Speedo — arm then click impulse bar. L=long, R=short", ColorStrategyOff);
                //btnSpeedoOfs      = MakeOfsBtn(s, "OFS:" + Speedo_EntryOffsetTicks, "Speedo entry offset");
                //btnSpeedoStpCycle = MakeSmallBtn(s, "STP:" + StopModeAbbr(Speedo_StopMode), "Cycle Speedo stop mode", Color.FromRgb(60,60,60));
                //btnSpeedoTgtCycle = MakeSmallBtn(s, "TGT:" + TargetModeAbbr(Speedo_TargetMode), "Cycle Speedo target mode", Color.FromRgb(60,60,60));
                //btnSpeedoStpOfs   = MakeOfsBtn(s, "STP:" + Speedo_StopOffsetTicks, "Speedo stop offset");
                //btnSpeedoTgtOfs   = MakeOfsBtn(s, "TGT:" + Speedo_TargetOffsetTicks, "Speedo target offset");
                //btnSpeedo.Click += ...
                //btnSpeedoOfs.PreviewMouseLeftButtonDown += ...
                //btnSpeedoOfs.PreviewMouseRightButtonDown += ...
                //btnSpeedoStpCycle.Click += ...
                //btnSpeedoTgtCycle.Click += ...
                //btnSpeedoStpOfs.PreviewMouseLeftButtonDown += ...
                //btnSpeedoStpOfs.PreviewMouseRightButtonDown += ...
                //btnSpeedoTgtOfs.PreviewMouseLeftButtonDown += ...
                //btnSpeedoTgtOfs.PreviewMouseRightButtonDown += ...
                //allSubButtons.AddRange(new[] { btnSpeedoOfs, btnSpeedoStpCycle, btnSpeedoTgtCycle, btnSpeedoStpOfs, btnSpeedoTgtOfs });
                //AddFullRowWithFullSubRows(ctButtonsGrid, r + 7, btnSpeedo, btnSpeedoOfs, btnSpeedoStpCycle, btnSpeedoTgtCycle, btnSpeedoStpOfs, btnSpeedoTgtOfs);
                // ── Row 7: FLAT | BE ──────────────────────────────────────────
                btnFlat = MakeBtn(s, LblFlat, "Close all positions at market", ColorFlat);
                btnBE   = MakeBtn(s, LblBE,   "Move stops to breakeven",       ColorBE);
                btnFlat.PreviewMouseLeftButtonDown += (o, e) => SetBtn(btnFlat, ColorFlash);
                btnFlat.PreviewMouseLeftButtonUp   += (o, e) => { SetBtn(btnFlat, ColorFlat); OnFlatClick(o, null); };
                btnBE.PreviewMouseLeftButtonDown   += (o, e) => SetBtn(btnBE, ColorFlash);
                btnBE.PreviewMouseLeftButtonUp     += (o, e) => { SetBtn(btnBE, ColorBE); OnBEClick(); };
                AddHalfRow(ctButtonsGrid, r + 7, btnFlat, btnBE);

                // ── Row 8: CANCEL ALL ─────────────────────────────────────────
                btnCancel = MakeBtn(s, LblCancel, "Cancel all unfilled orders", ColorCancel);
                btnCancel.PreviewMouseLeftButtonDown += (o, e) => SetBtn(btnCancel, ColorFlash);
                btnCancel.PreviewMouseLeftButtonUp   += (o, e) => { SetBtn(btnCancel, ColorCancel); OnCancelClick(o, null); };
                AddFullRow(ctButtonsGrid, r + 8, btnCancel);

                ctPanelActive = true;
                if (!subButtonsVisible)
                {
                    var hidVis = Visibility.Collapsed;
                    foreach (var btn in allSubButtons)
                        if (btn != null) btn.Visibility = hidVis;
                    foreach (var container in allSubContainers)
                        if (container != null) container.Visibility = hidVis;
                }
                ctRowsAdded = ctButtonsGrid.RowDefinitions.Count - baseRowCount;
                Print(DateTime.Now + " Button panel created");
            }
            catch (Exception ex) { Print("CreateWPFControls error: " + ex.Message); }
        }
        private void DisposeWPFControls()
        {
            try
            {
                Print(DateTime.Now + " DisposeWPFControls called | ctPanelActive=" + ctPanelActive + " loop=10");
                if (!ctPanelActive || ctButtonsGrid == null) return;
               int baseRows = ctBaseRowCount;
                if (baseRows < 0) baseRows = 0;
                Print(DateTime.Now + " DISPOSE | RowDefs=" + ctButtonsGrid.RowDefinitions.Count + " Children=" + ctButtonsGrid.Children.Count + " ctRowsAdded=" + ctRowsAdded + " baseRows=" + baseRows);
                while (ctButtonsGrid.Children.Count > baseRows)
                    ctButtonsGrid.Children.RemoveAt(ctButtonsGrid.Children.Count - 1);
                while (ctButtonsGrid.RowDefinitions.Count > baseRows)
                    ctButtonsGrid.RowDefinitions.RemoveAt(ctButtonsGrid.RowDefinitions.Count - 1);
                if (chartMouseHooked && ChartControl != null)
                { ChartControl.PreviewMouseDown -= OnChartMouseDown; chartMouseHooked = false; }
                btnMCStrategy = btnAllPBs = null;
                btnPB33 = btnPB50 = btnPB66 = null;
                btnBOXTR = btnBOINT = null;
                btnCTGuard = null;
                btnBBMC = btnSAMC = btnBBBL = btnSABR = btnSEL = btnSES = btnSpeedo = null;
                btnLmtBuy = btnLmtSell = null;
                btnLmtBuyStpCycle = btnLmtBuyTgtCycle = btnLmtBuyStpOfs = btnLmtBuyTgtOfs = null;
                btnLmtSellStpCycle = btnLmtSellTgtCycle = btnLmtSellStpOfs = btnLmtSellTgtOfs = null;
              	btnPB33Ofs = btnPB33StpMode = btnPB33TgtMode = btnPB33StpOfs = btnPB33TgtOfs = null;
                btnPB50Ofs = btnPB50StpMode = btnPB50TgtMode = btnPB50StpOfs = btnPB50TgtOfs = null;
                btnPB66Ofs = btnPB66StpMode = btnPB66TgtMode = btnPB66StpOfs = btnPB66TgtOfs = null;
                btnBBMCOfs = btnBBMCStpCycle = btnBBMCTgtCycle = btnBBMCStpOfs = btnBBMCTgtOfs = null;
                btnSAMCOfs = btnSAMCStpCycle = btnSAMCTgtCycle = btnSAMCStpOfs = btnSAMCTgtOfs = null;
                btnBBBLOfs = btnBBBLStpCycle = btnBBBLTgtCycle = btnBBBLStpOfs = btnBBBLTgtOfs = null;
                btnSABROfs = btnSABRStpCycle = btnSABRTgtCycle = btnSABRStpOfs = btnSABRTgtOfs = null;
               btnSELOfs  = btnSELStpCycle  = btnSELTgtCycle  = btnSELStpOfs  = btnSELTgtOfs  = null;
                btnSESOfs  = btnSESStpCycle  = btnSESTgtCycle  = btnSESStpOfs  = btnSESTgtOfs  = null;
                btnSEOrderType = btnSEOrderType2 = null;
                btnSpeedoOfs = btnSpeedoStpCycle = btnSpeedoTgtCycle = btnSpeedoStpOfs = btnSpeedoTgtOfs = null;
                btnSubToggle = null;
                allSubButtons.Clear();
                allSubContainers.Clear();
                btnFlat = btnBE = btnCancel = null;
                ctPanelActive = false;
            }
            catch (Exception ex) { Print("DisposeWPFControls error: " + ex.Message); }
        }

        private void UpdatePBButtonColors()
        {
            if (pb33Armed && !pb33Filled) {
                if ((l33Active && l33StopTargetSet) || (s33Active && s33StopTargetSet)) {
                    pb33Filled = true;
                    if (btnPB33 != null && ChartControl != null) ChartControl.Dispatcher.InvokeAsync((Action)(() => SetBtn(btnPB33, ColorFilled, true)));
                    UpdateSubBtnColors(false, true, true, btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs);
                }
            } else if (pb33Filled) {
                if (!l33Active && !s33Active) {
                    pb33Filled = false; bool reArm = AutoReArm; if (!reArm) pb33Armed = false;
                    if (btnPB33 != null && ChartControl != null) ChartControl.Dispatcher.InvokeAsync((Action)(() => SetBtn(btnPB33, reArm ? ColorArmed : ColorStrategyOff, reArm)));
                    UpdateSubBtnColors(reArm, false, false, btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs);
                }
            }
            if (pb50Armed && !pb50Filled) {
                if ((l50Active && l50StopTargetSet) || (s50Active && s50StopTargetSet)) {
                    pb50Filled = true;
                    if (btnPB50 != null && ChartControl != null) ChartControl.Dispatcher.InvokeAsync((Action)(() => SetBtn(btnPB50, ColorFilled, true)));
                    UpdateSubBtnColors(false, true, true, btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs);
                }
            } else if (pb50Filled) {
                if (!l50Active && !s50Active) {
                    pb50Filled = false; bool reArm = AutoReArm; if (!reArm) pb50Armed = false;
                    if (btnPB50 != null && ChartControl != null) ChartControl.Dispatcher.InvokeAsync((Action)(() => SetBtn(btnPB50, reArm ? ColorArmed : ColorStrategyOff, reArm)));
                    UpdateSubBtnColors(reArm, false, false, btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs);
                }
            }
            if (pb66Armed && !pb66Filled) {
                if ((l66Active && l66StopTargetSet) || (s66Active && s66StopTargetSet)) {
                    pb66Filled = true;
                    if (btnPB66 != null && ChartControl != null) ChartControl.Dispatcher.InvokeAsync((Action)(() => SetBtn(btnPB66, ColorFilled, true)));
                    UpdateSubBtnColors(false, true, true, btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs);
                }
            } else if (pb66Filled) {
                if (!l66Active && !s66Active) {
                    pb66Filled = false; bool reArm = AutoReArm; if (!reArm) pb66Armed = false;
                    if (btnPB66 != null && ChartControl != null) ChartControl.Dispatcher.InvokeAsync((Action)(() => SetBtn(btnPB66, reArm ? ColorArmed : ColorStrategyOff, reArm)));
                    UpdateSubBtnColors(reArm, false, false, btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs);
                }
            }
        }

       private void OnFlatClick(object sender, RoutedEventArgs e)
{
    try
    {
        lastExitSource = "FLAT";
        // Close all filled positions
        if (!string.IsNullOrEmpty(atmIdL33))    AtmStrategyClose(atmIdL33);
        if (!string.IsNullOrEmpty(atmIdL50))    AtmStrategyClose(atmIdL50);
        if (!string.IsNullOrEmpty(atmIdL66))    AtmStrategyClose(atmIdL66);
        if (!string.IsNullOrEmpty(atmIdS33))    AtmStrategyClose(atmIdS33);
        if (!string.IsNullOrEmpty(atmIdS50))    AtmStrategyClose(atmIdS50);
        if (!string.IsNullOrEmpty(atmIdS66))    AtmStrategyClose(atmIdS66);
        if (!string.IsNullOrEmpty(atmIdBBMC))   AtmStrategyClose(atmIdBBMC);
        if (!string.IsNullOrEmpty(atmIdSAMC))   AtmStrategyClose(atmIdSAMC);
      	foreach (var id in atmIdsBBBL) if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id);
        foreach (var id in atmIdsSABR) if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id);
        foreach (var id in atmIdsSEL)  if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id);
        foreach (var id in atmIdsSES)  if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id);
        if (!string.IsNullOrEmpty(atmIdSpeedo)) AtmStrategyClose(atmIdSpeedo);
        foreach (var id in atmIdsLmtBuy)  if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id);
        foreach (var id in atmIdsLmtSell) if (!string.IsNullOrEmpty(id)) AtmStrategyClose(id);
        // Cancel all unfilled orders
        if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) AtmStrategyCancelEntryOrder(ordIdL33);
        if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) AtmStrategyCancelEntryOrder(ordIdL50);
        if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) AtmStrategyCancelEntryOrder(ordIdL66);
        if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) AtmStrategyCancelEntryOrder(ordIdS33);
        if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) AtmStrategyCancelEntryOrder(ordIdS50);
        if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) AtmStrategyCancelEntryOrder(ordIdS66);
        if (bbMCActive && !bbMCFilled && !string.IsNullOrEmpty(ordIdBBMC)) AtmStrategyCancelEntryOrder(ordIdBBMC);
        if (saMCActive && !saMCFilled && !string.IsNullOrEmpty(ordIdSAMC)) AtmStrategyCancelEntryOrder(ordIdSAMC);
     for (int i = 0; i < atmIdsBBBL.Count; i++) if (!filledBBBL[i] && !string.IsNullOrEmpty(ordIdsBBBL[i])) AtmStrategyCancelEntryOrder(ordIdsBBBL[i]);
        for (int i = 0; i < atmIdsSABR.Count; i++) if (!filledSABR[i] && !string.IsNullOrEmpty(ordIdsSABR[i])) AtmStrategyCancelEntryOrder(ordIdsSABR[i]);
        for (int i = 0; i < atmIdsSEL.Count;  i++) if (!filledSEL[i]  && !string.IsNullOrEmpty(ordIdsSEL[i]))  AtmStrategyCancelEntryOrder(ordIdsSEL[i]);
        for (int i = 0; i < atmIdsSES.Count;  i++) if (!filledSES[i]  && !string.IsNullOrEmpty(ordIdsSES[i]))  AtmStrategyCancelEntryOrder(ordIdsSES[i]);
        if (speedoActive && !speedoFilled && !string.IsNullOrEmpty(ordIdSpeedo)) AtmStrategyCancelEntryOrder(ordIdSpeedo);
        // Disarm everything
        pb33Armed = pb33Filled = pb50Armed = pb50Filled = pb66Armed = pb66Filled = allPBsArmed = false;
        bbBLWaitingClick = bbBLArmed = false;
        saBRWaitingClick = saBRArmed = false;
        seLWaitingClick  = seLArmed  = false;
        seSWaitingClick  = seSArmed  = false;
        atmIdsBBBL.Clear(); ordIdsBBBL.Clear(); stopsBBBL.Clear(); targetsBBBL.Clear(); entriesBBBL.Clear(); filledBBBL.Clear(); callbackBBBL.Clear(); stopCalcsBBBL.Clear(); tgtCalcsBBBL.Clear(); barsAgoBBBL.Clear(); inMCBBBL.Clear();
        atmIdsSABR.Clear(); ordIdsSABR.Clear(); stopsSABR.Clear(); targetsSABR.Clear(); entriesSABR.Clear(); filledSABR.Clear(); callbackSABR.Clear(); stopCalcsSABR.Clear(); tgtCalcsSABR.Clear(); barsAgoSABR.Clear(); inMCSABR.Clear();
        atmIdsSEL.Clear();  ordIdsSEL.Clear();  stopsSEL.Clear();  targetsSEL.Clear();  entriesSEL.Clear();  filledSEL.Clear();  callbackSEL.Clear();  stopCalcsSEL.Clear();  tgtCalcsSEL.Clear();
        atmIdsSES.Clear();  ordIdsSES.Clear();  stopsSES.Clear();  targetsSES.Clear();  entriesSES.Clear();  filledSES.Clear();  callbackSES.Clear();  stopCalcsSES.Clear();  tgtCalcsSES.Clear();
        UpdateLmtButtonLabel(btnBBBL, atmIdsBBBL, "BBBL");
        UpdateLmtButtonLabel(btnSABR, atmIdsSABR, "SABR");
        UpdateLmtButtonLabel(btnSEL,  atmIdsSEL,  "SEL");
        UpdateLmtButtonLabel(btnSES,  atmIdsSES,  "SES");
        speedoWaitingClick = speedoWaitingBar = speedoWaitingImpulseClose = speedoArmed = false;
        speedoOrderBarIndex = -1;
        lmtBuyWaitingClick = lmtSellWaitingClick = false;
        atmIdsLmtBuy.Clear(); ordIdsLmtBuy.Clear(); stopsLmtBuy.Clear(); targetsLmtBuy.Clear(); entriesLmtBuy.Clear(); filledLmtBuy.Clear(); callbackLmtBuy.Clear(); stopCalcsLmtBuy.Clear(); tgtCalcsLmtBuy.Clear();
        atmIdsLmtSell.Clear(); ordIdsLmtSell.Clear(); stopsLmtSell.Clear(); targetsLmtSell.Clear(); entriesLmtSell.Clear(); filledLmtSell.Clear(); callbackLmtSell.Clear(); stopCalcsLmtSell.Clear(); tgtCalcsLmtSell.Clear();
        UpdateLmtButtonLabel(btnLmtBuy,  atmIdsLmtBuy,  "LmtBuy");
        UpdateLmtButtonLabel(btnLmtSell, atmIdsLmtSell, "LmtSell");
        // Grey all buttons
        SetPBButtonColors();
        if (ChartControl != null)
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                if (btnBBMC   != null) SetBtn(btnBBMC,   UseBBMC ? ColorArmed : ColorStrategyOff, UseBBMC);
                if (btnSAMC   != null) SetBtn(btnSAMC,   UseSAMC ? ColorArmed : ColorStrategyOff, UseSAMC);
                if (btnBBBL   != null) SetBtn(btnBBBL,   ColorStrategyOff);
                if (btnSABR   != null) SetBtn(btnSABR,   ColorStrategyOff);
                if (btnSEL    != null) SetBtn(btnSEL,    ColorStrategyOff);
                if (btnSES    != null) SetBtn(btnSES,    ColorStrategyOff);
                if (btnSpeedo != null) SetBtn(btnSpeedo, ColorStrategyOff);
            }));
        Print(DateTime.Now + " FLAT ALL fired — all positions closed, all orders cancelled, all entries disarmed");
    }
    catch (Exception ex) { Print("OnFlatClick error: " + ex.Message); }
}

        private void OnCancelClick(object sender, RoutedEventArgs e)
{
    try
    {
        // Cancel all unfilled PB orders
        if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) AtmStrategyCancelEntryOrder(ordIdL33);
        if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) AtmStrategyCancelEntryOrder(ordIdL50);
        if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) AtmStrategyCancelEntryOrder(ordIdL66);
        if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) AtmStrategyCancelEntryOrder(ordIdS33);
        if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) AtmStrategyCancelEntryOrder(ordIdS50);
        if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) AtmStrategyCancelEntryOrder(ordIdS66);
        // Cancel all unfilled bar-select orders
        if (bbMCActive && !bbMCFilled && !string.IsNullOrEmpty(ordIdBBMC)) AtmStrategyCancelEntryOrder(ordIdBBMC);
        if (saMCActive && !saMCFilled && !string.IsNullOrEmpty(ordIdSAMC)) AtmStrategyCancelEntryOrder(ordIdSAMC);
      for (int i = 0; i < atmIdsBBBL.Count; i++) if (!filledBBBL[i] && !string.IsNullOrEmpty(ordIdsBBBL[i])) AtmStrategyCancelEntryOrder(ordIdsBBBL[i]);
        for (int i = 0; i < atmIdsSABR.Count; i++) if (!filledSABR[i] && !string.IsNullOrEmpty(ordIdsSABR[i])) AtmStrategyCancelEntryOrder(ordIdsSABR[i]);
        for (int i = 0; i < atmIdsSEL.Count;  i++) if (!filledSEL[i]  && !string.IsNullOrEmpty(ordIdsSEL[i]))  AtmStrategyCancelEntryOrder(ordIdsSEL[i]);
        for (int i = 0; i < atmIdsSES.Count;  i++) if (!filledSES[i]  && !string.IsNullOrEmpty(ordIdsSES[i]))  AtmStrategyCancelEntryOrder(ordIdsSES[i]);
        if (speedoActive && !speedoFilled && !string.IsNullOrEmpty(ordIdSpeedo)) AtmStrategyCancelEntryOrder(ordIdSpeedo);
        for (int i = 0; i < atmIdsLmtBuy.Count;  i++) if (!filledLmtBuy[i]  && !string.IsNullOrEmpty(ordIdsLmtBuy[i]))  AtmStrategyCancelEntryOrder(ordIdsLmtBuy[i]);
        for (int i = 0; i < atmIdsLmtSell.Count; i++) if (!filledLmtSell[i] && !string.IsNullOrEmpty(ordIdsLmtSell[i])) AtmStrategyCancelEntryOrder(ordIdsLmtSell[i]);
        lmtBuyWaitingClick = lmtSellWaitingClick = false;
        // Reset all PB armed/filled states
        // Reset all PB armed/filled states
        pb33Armed = pb33Filled = pb50Armed = pb50Filled = pb66Armed = pb66Filled = allPBsArmed = false;
        // Reset all bar-select armed/waiting states
        bbBLWaitingClick = bbBLArmed = false;
        saBRWaitingClick = saBRArmed = false;
        seLWaitingClick  = seLArmed  = false;
        seSWaitingClick  = seSArmed  = false;
        atmIdsBBBL.Clear(); ordIdsBBBL.Clear(); stopsBBBL.Clear(); targetsBBBL.Clear(); entriesBBBL.Clear(); filledBBBL.Clear(); callbackBBBL.Clear(); stopCalcsBBBL.Clear(); tgtCalcsBBBL.Clear(); barsAgoBBBL.Clear(); inMCBBBL.Clear();
        atmIdsSABR.Clear(); ordIdsSABR.Clear(); stopsSABR.Clear(); targetsSABR.Clear(); entriesSABR.Clear(); filledSABR.Clear(); callbackSABR.Clear(); stopCalcsSABR.Clear(); tgtCalcsSABR.Clear(); barsAgoSABR.Clear(); inMCSABR.Clear();
        atmIdsSEL.Clear();  ordIdsSEL.Clear();  stopsSEL.Clear();  targetsSEL.Clear();  entriesSEL.Clear();  filledSEL.Clear();  callbackSEL.Clear();  stopCalcsSEL.Clear();  tgtCalcsSEL.Clear();
        atmIdsSES.Clear();  ordIdsSES.Clear();  stopsSES.Clear();  targetsSES.Clear();  entriesSES.Clear();  filledSES.Clear();  callbackSES.Clear();  stopCalcsSES.Clear();  tgtCalcsSES.Clear();
        UpdateLmtButtonLabel(btnBBBL, atmIdsBBBL, "BBBL");
        UpdateLmtButtonLabel(btnSABR, atmIdsSABR, "SABR");
        UpdateLmtButtonLabel(btnSEL,  atmIdsSEL,  "SEL");
        UpdateLmtButtonLabel(btnSES,  atmIdsSES,  "SES");
        speedoWaitingClick = speedoWaitingBar = speedoArmed = false;
        // Grey all buttons
        SetPBButtonColors();
        UpdateSubBtnColors(false, false, false, btnPB33Ofs, btnPB33StpMode, btnPB33TgtMode, btnPB33StpOfs, btnPB33TgtOfs);
        UpdateSubBtnColors(false, false, false, btnPB50Ofs, btnPB50StpMode, btnPB50TgtMode, btnPB50StpOfs, btnPB50TgtOfs);
        UpdateSubBtnColors(false, false, false, btnPB66Ofs, btnPB66StpMode, btnPB66TgtMode, btnPB66StpOfs, btnPB66TgtOfs);
        UpdateSubBtnColors(false, false, false, btnBBMCOfs, btnBBMCStpCycle, btnBBMCTgtCycle, btnBBMCStpOfs, btnBBMCTgtOfs);
        UpdateSubBtnColors(false, false, false, btnSAMCOfs, btnSAMCStpCycle, btnSAMCTgtCycle, btnSAMCStpOfs, btnSAMCTgtOfs);
        UpdateSubBtnColors(false, false, false, btnBBBLOfs, btnBBBLStpCycle, btnBBBLTgtCycle, btnBBBLStpOfs, btnBBBLTgtOfs);
        UpdateSubBtnColors(false, false, false, btnSABROfs, btnSABRStpCycle, btnSABRTgtCycle, btnSABRStpOfs, btnSABRTgtOfs);
        UpdateSubBtnColors(false, false, false, btnSELOfs,  btnSELStpCycle,  btnSELTgtCycle,  btnSELStpOfs,  btnSELTgtOfs);
        UpdateSubBtnColors(false, false, false, btnSESOfs,  btnSESStpCycle,  btnSESTgtCycle,  btnSESStpOfs,  btnSESTgtOfs);
        UpdateSubBtnColors(false, false, false, btnSpeedoOfs, btnSpeedoStpCycle, btnSpeedoTgtCycle, btnSpeedoStpOfs, btnSpeedoTgtOfs);
        if (ChartControl != null)
            ChartControl.Dispatcher.InvokeAsync((Action)(() =>
            {
                if (btnBBMC   != null && !bbMCFilled)   SetBtn(btnBBMC,   ColorStrategyOff);
                if (btnSAMC   != null && !saMCFilled)   SetBtn(btnSAMC,   ColorStrategyOff);
                if (btnBBBL   != null) SetBtn(btnBBBL,   ColorStrategyOff);
                if (btnSABR   != null) SetBtn(btnSABR,   ColorStrategyOff);
                if (btnSEL    != null) SetBtn(btnSEL,    ColorStrategyOff);
                if (btnSES    != null) SetBtn(btnSES,    ColorStrategyOff);
                if (btnSpeedo != null && !speedoFilled) SetBtn(btnSpeedo, ColorStrategyOff);
            }));
        Print(DateTime.Now + " CANCEL ALL fired — full reset");
    }
    catch (Exception ex) { Print("OnCancelClick error: " + ex.Message); }
}

        private void OnBEClick()
        {
            try
            {
               bool anyLongFilled  = (l33StopTargetSet && !string.IsNullOrEmpty(atmIdL33)) || (l50StopTargetSet && !string.IsNullOrEmpty(atmIdL50)) || (l66StopTargetSet && !string.IsNullOrEmpty(atmIdL66))
                                   || (bbMCFilled && !string.IsNullOrEmpty(atmIdBBMC)) || atmIdsBBBL.Count > 0 || atmIdsSEL.Count > 0
                                   || (speedoFilled && speedoIsLong && !string.IsNullOrEmpty(atmIdSpeedo));
                bool anyShortFilled = (s33StopTargetSet && !string.IsNullOrEmpty(atmIdS33)) || (s50StopTargetSet && !string.IsNullOrEmpty(atmIdS50)) || (s66StopTargetSet && !string.IsNullOrEmpty(atmIdS66))
                                   || (saMCFilled && !string.IsNullOrEmpty(atmIdSAMC)) || atmIdsSABR.Count > 0 || atmIdsSES.Count > 0
                                   || (speedoFilled && !speedoIsLong && !string.IsNullOrEmpty(atmIdSpeedo));
                if (!anyLongFilled && !anyShortFilled) { Print(DateTime.Now + " BE — no open position"); return; }
                bool isLong = anyLongFilled;

                double totalEntry = 0; int count = 0;
              if (isLong)
                {
                    if (l33StopTargetSet && entryL33 > 0) { totalEntry += entryL33; count++; }
                    if (l50StopTargetSet && entryL50 > 0) { totalEntry += entryL50; count++; }
                    if (l66StopTargetSet && entryL66 > 0) { totalEntry += entryL66; count++; }
                    if (bbMCFilled && entryBBMC > 0)      { totalEntry += entryBBMC; count++; }
                    foreach (double ep in entriesBBBL) { if (ep > 0) { totalEntry += ep; count++; } }
                    foreach (double ep in entriesSEL)  { if (ep > 0) { totalEntry += ep; count++; } }
                    if (speedoFilled && speedoIsLong && entrySpeedo > 0) { totalEntry += entrySpeedo; count++; }
                }
                else
                {
                    if (s33StopTargetSet && entryS33 > 0) { totalEntry += entryS33; count++; }
                    if (s50StopTargetSet && entryS50 > 0) { totalEntry += entryS50; count++; }
                    if (s66StopTargetSet && entryS66 > 0) { totalEntry += entryS66; count++; }
                    if (saMCFilled && entrySAMC > 0)      { totalEntry += entrySAMC; count++; }
                    foreach (double ep in entriesSABR) { if (ep > 0) { totalEntry += ep; count++; } }
                    foreach (double ep in entriesSES)  { if (ep > 0) { totalEntry += ep; count++; } }
                    if (speedoFilled && !speedoIsLong && entrySpeedo > 0) { totalEntry += entrySpeedo; count++; }
                }
                double be           = count > 0 ? Round(totalEntry / count) : (isLong ? GetCurrentAsk() : GetCurrentBid());
                double currentPrice = isLong ? GetCurrentBid() : GetCurrentAsk();
                bool   moveStops    = (isLong && currentPrice > be) || (!isLong && currentPrice < be);
                lastExitSource      = "BE";

                if (BECancelUnfilled)
                {
                    if (l33Active && !l33StopTargetSet && !string.IsNullOrEmpty(ordIdL33)) AtmStrategyCancelEntryOrder(ordIdL33);
                    if (l50Active && !l50StopTargetSet && !string.IsNullOrEmpty(ordIdL50)) AtmStrategyCancelEntryOrder(ordIdL50);
                    if (l66Active && !l66StopTargetSet && !string.IsNullOrEmpty(ordIdL66)) AtmStrategyCancelEntryOrder(ordIdL66);
                    if (s33Active && !s33StopTargetSet && !string.IsNullOrEmpty(ordIdS33)) AtmStrategyCancelEntryOrder(ordIdS33);
                    if (s50Active && !s50StopTargetSet && !string.IsNullOrEmpty(ordIdS50)) AtmStrategyCancelEntryOrder(ordIdS50);
                    if (s66Active && !s66StopTargetSet && !string.IsNullOrEmpty(ordIdS66)) AtmStrategyCancelEntryOrder(ordIdS66);
                }
                Print(string.Format("{0} BE | pos={1} avgEntry={2} price={3} action={4}", DateTime.Now, isLong ? "LONG" : "SHORT", be, currentPrice, moveStops ? "MOVE STOPS" : "MOVE TARGETS"));

                if (moveStops)
                {
                    if (l33StopTargetSet && !string.IsNullOrEmpty(atmIdL33)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdL33);
                    if (l50StopTargetSet && !string.IsNullOrEmpty(atmIdL50)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdL50);
                    if (l66StopTargetSet && !string.IsNullOrEmpty(atmIdL66)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdL66);
                    if (s33StopTargetSet && !string.IsNullOrEmpty(atmIdS33)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdS33);
                    if (s50StopTargetSet && !string.IsNullOrEmpty(atmIdS50)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdS50);
                    if (s66StopTargetSet && !string.IsNullOrEmpty(atmIdS66)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdS66);
                    if (bbMCFilled && !string.IsNullOrEmpty(atmIdBBMC))   AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdBBMC);
                    if (saMCFilled && !string.IsNullOrEmpty(atmIdSAMC))   AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdSAMC);
                    foreach (var id in atmIdsBBBL) if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(0, be, "Stop1", id);
                    foreach (var id in atmIdsSABR) if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(0, be, "Stop1", id);
                    foreach (var id in atmIdsSEL)  if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(0, be, "Stop1", id);
                    foreach (var id in atmIdsSES)  if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(0, be, "Stop1", id);
                    if (speedoFilled && !string.IsNullOrEmpty(atmIdSpeedo)) AtmStrategyChangeStopTarget(0, be, "Stop1", atmIdSpeedo);
                }
                else
                {
                    if (l33StopTargetSet && !string.IsNullOrEmpty(atmIdL33)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdL33);
                    if (l50StopTargetSet && !string.IsNullOrEmpty(atmIdL50)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdL50);
                    if (l66StopTargetSet && !string.IsNullOrEmpty(atmIdL66)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdL66);
                    if (s33StopTargetSet && !string.IsNullOrEmpty(atmIdS33)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdS33);
                    if (s50StopTargetSet && !string.IsNullOrEmpty(atmIdS50)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdS50);
                    if (s66StopTargetSet && !string.IsNullOrEmpty(atmIdS66)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdS66);
                    if (bbMCFilled && !string.IsNullOrEmpty(atmIdBBMC))   AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdBBMC);
                    if (saMCFilled && !string.IsNullOrEmpty(atmIdSAMC))   AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdSAMC);
                  foreach (var id in atmIdsBBBL) if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(be, 0, "Target1", id);
                    foreach (var id in atmIdsSABR) if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(be, 0, "Target1", id);
                    foreach (var id in atmIdsSEL)  if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(be, 0, "Target1", id);
                    foreach (var id in atmIdsSES)  if (!string.IsNullOrEmpty(id)) AtmStrategyChangeStopTarget(be, 0, "Target1", id);
                    if (speedoFilled && !string.IsNullOrEmpty(atmIdSpeedo)) AtmStrategyChangeStopTarget(be, 0, "Target1", atmIdSpeedo);
                }
            }
            catch (Exception ex) { Print("BE error: " + ex.Message); }
        }

        #region Properties
        [Display(Name = "Test Mode", Order = 1, GroupName = "Strategy")]          public bool TestMode { get; set; }
        [Display(Name = "Auto Re-Arm After Trade", Order = 3, GroupName = "Strategy")] public bool AutoReArm { get; set; }
        [Display(Name = "BE Cancels Unfilled Orders", Order = 4, GroupName = "Strategy")] public bool BECancelUnfilled { get; set; }
        [Display(Name = "ATM Template Name", Order = 2, GroupName = "Strategy")]  public string AtmTemplateName { get; set; }
        [Display(Name = "Use Time Filter", Order = 1, GroupName = "Session")]     public bool UseTimeFilter { get; set; }
        [Display(Name = "Start Time", Order = 2, GroupName = "Session")]          public string StartTime { get; set; }
        [Display(Name = "End Time", Order = 3, GroupName = "Session")]            public string EndTime { get; set; }
        [Display(Name = "Max Contracts", Order = 1, GroupName = "Risk Guard")]    public int MaxContracts { get; set; }
        [Display(Name = "Enable Max Risk $", Order = 2, GroupName = "Risk Guard")] public bool EnableMaxRiskDollars { get; set; }
        [Display(Name = "Max Risk Dollars", Order = 3, GroupName = "Risk Guard")] public double MaxRiskDollars { get; set; }
        [Display(Name = "Enable Max Channel Points", Order = 4, GroupName = "Risk Guard")] public bool EnableMaxChannelPoints { get; set; }
        [Display(Name = "Max Channel Points", Order = 5, GroupName = "Risk Guard")] public double MaxChannelPoints { get; set; }
        [Display(Name = "Enable Max Channel Bars", Order = 6, GroupName = "Risk Guard")] public bool EnableMaxChannelBars { get; set; }
        [Display(Name = "Max Channel Bars", Order = 7, GroupName = "Risk Guard")] public int MaxChannelBars { get; set; }
        [Display(Name = "Enable Max Channel ABR Multiple", Order = 8, GroupName = "Risk Guard")] public bool EnableMaxChannelABRMultiple { get; set; }
        [Display(Name = "Max Channel ABR Multiple", Order = 9, GroupName = "Risk Guard")] public double MaxChannelABRMultiple { get; set; }
        [Display(Name = "Enable ADR Filter", Order = 10, GroupName = "Risk Guard")] public bool EnableADRFilter { get; set; }
        [Display(Name = "Max Channel ADR Multiple", Order = 11, GroupName = "Risk Guard")] public double MaxChannelADRMultiple { get; set; }
        [Display(Name = "Enable Cancel Watch", Order = 1, GroupName = "Cancel Watch")] public bool EnableCancelWatch { get; set; }
        [Display(Name = "Cancel Mode", Order = 2, GroupName = "Cancel Watch")]    public CancelMode CancelWatchMode { get; set; }
        [Display(Name = "Cancel After Bars", Order = 3, GroupName = "Cancel Watch")] public int CancelAfterBars { get; set; }
        [Display(Name = "Cancel Pct Of Channel", Order = 4, GroupName = "Cancel Watch")] public double CancelPctOfChannel { get; set; }
        [Display(Name = "Closes Outside Extreme To Cancel", Order = 5, GroupName = "Cancel Watch")] public int ClosesOutsideToCancel { get; set; }

        // PB33
        [Display(Name = "Use PB33", Order = 1, GroupName = "Entry - PB33")]               public bool UsePB33 { get; set; }
        [Display(Name = "Entry Offset Ticks", Order = 2, GroupName = "Entry - PB33")]     public int PB33EntryOffsetTicks { get; set; }
        [Display(Name = "Stop Mode", Order = 3, GroupName = "Entry - PB33")]               public StopMode PB33StopMode { get; set; }
        [Display(Name = "Stop Offset Ticks", Order = 4, GroupName = "Entry - PB33")]      public int PB33StopOffsetTicks { get; set; }
        [Display(Name = "Stop ABR Bars", Order = 5, GroupName = "Entry - PB33")]           public int PB33StopABRBars { get; set; }
        [Display(Name = "Stop ABR Multiple", Order = 6, GroupName = "Entry - PB33")]       public double PB33StopABRMultiple { get; set; }
        [Display(Name = "Swing Strength", Order = 7, GroupName = "Entry - PB33")]          public int PB33SwingStrength { get; set; }
        [Display(Name = "Target Mode", Order = 8, GroupName = "Entry - PB33")]             public TargetMode PB33TargetMode { get; set; }
        [Display(Name = "R Multiple", Order = 9, GroupName = "Entry - PB33")]              public double PB33RMultiple { get; set; }
        [Display(Name = "Target Offset Ticks", Order = 10, GroupName = "Entry - PB33")]   public int PB33TargetOffsetTicks { get; set; }

        // PB50
        [Display(Name = "Use PB50", Order = 1, GroupName = "Entry - PB50")]               public bool UsePB50 { get; set; }
        [Display(Name = "Entry Offset Ticks", Order = 2, GroupName = "Entry - PB50")]     public int PB50EntryOffsetTicks { get; set; }
        [Display(Name = "Stop Mode", Order = 3, GroupName = "Entry - PB50")]               public StopMode PB50StopMode { get; set; }
        [Display(Name = "Stop Offset Ticks", Order = 4, GroupName = "Entry - PB50")]      public int PB50StopOffsetTicks { get; set; }
        [Display(Name = "Stop ABR Bars", Order = 5, GroupName = "Entry - PB50")]           public int PB50StopABRBars { get; set; }
        [Display(Name = "Stop ABR Multiple", Order = 6, GroupName = "Entry - PB50")]       public double PB50StopABRMultiple { get; set; }
        [Display(Name = "Swing Strength", Order = 7, GroupName = "Entry - PB50")]          public int PB50SwingStrength { get; set; }
        [Display(Name = "Target Mode", Order = 8, GroupName = "Entry - PB50")]             public TargetMode PB50TargetMode { get; set; }
        [Display(Name = "R Multiple", Order = 9, GroupName = "Entry - PB50")]              public double PB50RMultiple { get; set; }
        [Display(Name = "Target Offset Ticks", Order = 10, GroupName = "Entry - PB50")]   public int PB50TargetOffsetTicks { get; set; }

        // PB66
        [Display(Name = "Use PB66", Order = 1, GroupName = "Entry - PB66")]               public bool UsePB66 { get; set; }
        [Display(Name = "Entry Offset Ticks", Order = 2, GroupName = "Entry - PB66")]     public int PB66EntryOffsetTicks { get; set; }
        [Display(Name = "Stop Mode", Order = 3, GroupName = "Entry - PB66")]               public StopMode PB66StopMode { get; set; }
        [Display(Name = "Stop Offset Ticks", Order = 4, GroupName = "Entry - PB66")]      public int PB66StopOffsetTicks { get; set; }
        [Display(Name = "Stop ABR Bars", Order = 5, GroupName = "Entry - PB66")]           public int PB66StopABRBars { get; set; }
        [Display(Name = "Stop ABR Multiple", Order = 6, GroupName = "Entry - PB66")]       public double PB66StopABRMultiple { get; set; }
        [Display(Name = "Swing Strength", Order = 7, GroupName = "Entry - PB66")]          public int PB66SwingStrength { get; set; }
        [Display(Name = "Target Mode", Order = 8, GroupName = "Entry - PB66")]             public TargetMode PB66TargetMode { get; set; }
        [Display(Name = "R Multiple", Order = 9, GroupName = "Entry - PB66")]              public double PB66RMultiple { get; set; }
        [Display(Name = "Target Offset Ticks", Order = 10, GroupName = "Entry - PB66")]   public int PB66TargetOffsetTicks { get; set; }

        // BO XTR
		[Browsable(false)] public bool UseBO_XTR { get; set; }
		[Browsable(false)] public int BOXTR_EntryOffsetTicks { get; set; }
		[Browsable(false)] public StopMode BOXTR_StopMode { get; set; }
		[Browsable(false)] public int BOXTR_StopOffsetTicks { get; set; }
		[Browsable(false)] public int BOXTR_StopABRBars { get; set; }
		[Browsable(false)] public double BOXTR_StopABRMultiple { get; set; }
		[Browsable(false)] public int BOXTR_SwingStrength { get; set; }
		[Browsable(false)] public TargetMode BOXTR_TargetMode { get; set; }
		[Browsable(false)] public double BOXTR_RMultiple { get; set; }
		[Browsable(false)] public int BOXTR_TargetOffsetTicks { get; set; }
		[Browsable(false)] public OrderType BOXTR_OrderType { get; set; }
		
		// BO INT
		[Browsable(false)] public bool UseBO_INT { get; set; }
		[Browsable(false)] public int BOINT_EntryOffsetTicks { get; set; }
		[Browsable(false)] public StopMode BOINT_StopMode { get; set; }
		[Browsable(false)] public int BOINT_StopOffsetTicks { get; set; }
		[Browsable(false)] public int BOINT_StopABRBars { get; set; }
		[Browsable(false)] public double BOINT_StopABRMultiple { get; set; }
		[Browsable(false)] public int BOINT_SwingStrength { get; set; }
		[Browsable(false)] public TargetMode BOINT_TargetMode { get; set; }
		[Browsable(false)] public double BOINT_RMultiple { get; set; }
		[Browsable(false)] public int BOINT_TargetOffsetTicks { get; set; }
        // BB MC / SA MC
     	[Browsable(false)] public bool UseBBMC { get; set; }
		[Browsable(false)] public bool UseSAMC { get; set; }
		[Browsable(false)] public int BBSAMC_EntryOffsetTicks { get; set; }
		[Browsable(false)] public StopMode BBSAMC_StopMode { get; set; }
		[Browsable(false)] public int BBSAMC_StopOffsetTicks { get; set; }
		[Browsable(false)] public int BBSAMC_StopABRBars { get; set; }
		[Browsable(false)] public double BBSAMC_StopABRMultiple { get; set; }
		[Browsable(false)] public int BBSAMC_SwingStrength { get; set; }
		[Browsable(false)] public TargetMode BBSAMC_TargetMode { get; set; }
		[Browsable(false)] public double BBSAMC_RMultiple { get; set; }
		[Browsable(false)] public int BBSAMC_TargetOffsetTicks { get; set; }
		[Browsable(false)] public bool BBSAMC_CTGuardEnabled { get; set; }

        // BB BL / SA BR
      [Display(Name = "Use Lmt Buy L", Order = 1, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]             public bool UseBBBL { get; set; }
[Display(Name = "Use Lmt Sell H", Order = 2, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]             public bool UseSABR { get; set; }
[Display(Name = "Entry Offset Ticks", Order = 3, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]    public int BBLSABR_EntryOffsetTicks { get; set; }
[Display(Name = "Stop Mode", Order = 4, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]             public StopMode BBLSABR_StopMode { get; set; }
[Display(Name = "Stop Offset Ticks", Order = 5, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]     public int BBLSABR_StopOffsetTicks { get; set; }
[Display(Name = "Stop ABR Bars", Order = 6, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]          public int BBLSABR_StopABRBars { get; set; }
[Display(Name = "Stop ABR Multiple", Order = 7, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]      public double BBLSABR_StopABRMultiple { get; set; }
[Display(Name = "Swing Strength", Order = 8, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]         public int BBLSABR_SwingStrength { get; set; }
[Display(Name = "Target Mode", Order = 9, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]            public TargetMode BBLSABR_TargetMode { get; set; }
[Display(Name = "R Multiple", Order = 10, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]            public double BBLSABR_RMultiple { get; set; }
[Display(Name = "Target Offset Ticks", Order = 11, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]   public int BBLSABR_TargetOffsetTicks { get; set; }
[Display(Name = "CT Guard Enabled", Order = 12, GroupName = "Entry - Lmt Buy L / Lmt Sell H")]      public bool BBLSABR_CTGuardEnabled { get; set; }
        // SE
        [Display(Name = "Use SE L", Order = 1, GroupName = "Entry - SE")]                 public bool UseSEL { get; set; }
        [Display(Name = "Use SE S", Order = 2, GroupName = "Entry - SE")]                 public bool UseSES { get; set; }
        [Display(Name = "Entry Offset Ticks", Order = 3, GroupName = "Entry - SE")]       public int SE_EntryOffsetTicks { get; set; }
        [Display(Name = "Stop Mode", Order = 4, GroupName = "Entry - SE")]                 public StopMode SE_StopMode { get; set; }
        [Display(Name = "Stop Offset Ticks", Order = 5, GroupName = "Entry - SE")]        public int SE_StopOffsetTicks { get; set; }
        [Display(Name = "Stop ABR Bars", Order = 6, GroupName = "Entry - SE")]             public int SE_StopABRBars { get; set; }
        [Display(Name = "Stop ABR Multiple", Order = 7, GroupName = "Entry - SE")]         public double SE_StopABRMultiple { get; set; }
        [Display(Name = "Swing Strength", Order = 8, GroupName = "Entry - SE")]            public int SE_SwingStrength { get; set; }
        [Display(Name = "Target Mode", Order = 9, GroupName = "Entry - SE")]               public TargetMode SE_TargetMode { get; set; }
        [Display(Name = "R Multiple", Order = 10, GroupName = "Entry - SE")]               public double SE_RMultiple { get; set; }
        [Display(Name = "Target Offset Ticks", Order = 11, GroupName = "Entry - SE")]     public int SE_TargetOffsetTicks { get; set; }
        [Display(Name = "CT Guard Enabled", Order = 12, GroupName = "Entry - SE")]         public bool SE_CTGuardEnabled { get; set; }
        [Display(Name = "Order Type", Order = 13, GroupName = "Entry - SE")]               public OrderType SE_OrderType { get; set; }

        // Speedo
        [Browsable(false)] public bool UseSpeedo { get; set; }
    [Browsable(false)] public int Speedo_EntryOffsetTicks { get; set; }
        [Browsable(false)] public StopMode Speedo_StopMode { get; set; }
        [Browsable(false)] public int Speedo_StopOffsetTicks { get; set; }
        [Browsable(false)] public int Speedo_StopABRBars { get; set; }
        [Browsable(false)] public double Speedo_StopABRMultiple { get; set; }
        [Browsable(false)] public int Speedo_SwingStrength { get; set; }
        [Browsable(false)] public TargetMode Speedo_TargetMode { get; set; }
        [Browsable(false)] public double Speedo_RMultiple { get; set; }
        [Browsable(false)] public int Speedo_TargetOffsetTicks { get; set; }
        [Browsable(false)] public bool Speedo_CTGuardEnabled { get; set; }
        [Browsable(false)] public bool Speedo_AutoCancel { get; set; }
        // Indicator
        [Display(Name = "Continue MC", Order = 1, GroupName = "Indicator")]  public bool ContinueMC { get; set; }
        [Display(Name = "Show 0CC", Order = 2, GroupName = "Indicator")]      public bool Show0CC { get; set; }
        [Display(Name = "Show 1CC", Order = 3, GroupName = "Indicator")]      public bool Show1CC { get; set; }
        [Display(Name = "Show 2CC", Order = 4, GroupName = "Indicator")]      public bool Show2CC { get; set; }
        [Display(Name = "Show 3CC", Order = 5, GroupName = "Indicator")]      public bool Show3CC { get; set; }
        [Display(Name = "Show 4CC", Order = 6, GroupName = "Indicator")]      public bool Show4CC { get; set; }
        [Display(Name = "Show 5CC", Order = 7, GroupName = "Indicator")]      public bool Show5CC { get; set; }
        [Display(Name = "Show CX", Order = 8, GroupName = "Indicator")]       public bool ShowCX { get; set; }

        // Chart Trader Buttons
        [Display(Name = "Button Font Size", Order = 1, GroupName = "Chart Trader Buttons")]    public int ButtonFontSize { get; set; }
        [Display(Name = "Sub Button Font Size", Order = 2, GroupName = "Chart Trader Buttons")] public int SubButtonFontSize { get; set; }
        [Display(Name = "MC Strategy Label", Order = 2, GroupName = "Chart Trader Buttons")]   public string LblMCStrategy { get; set; }
        [Display(Name = "PB33 Label", Order = 3, GroupName = "Chart Trader Buttons")]          public string LblPB33 { get; set; }
        [Display(Name = "PB50 Label", Order = 4, GroupName = "Chart Trader Buttons")]          public string LblPB50 { get; set; }
        [Display(Name = "PB66 Label", Order = 5, GroupName = "Chart Trader Buttons")]          public string LblPB66 { get; set; }
        [Display(Name = "BO XTR Label", Order = 6, GroupName = "Chart Trader Buttons")]        public string LblBOXTR { get; set; }
        [Display(Name = "BO INT Label", Order = 7, GroupName = "Chart Trader Buttons")]        public string LblBOINT { get; set; }
        [Display(Name = "BB MC Label", Order = 8, GroupName = "Chart Trader Buttons")]         public string LblBBMC { get; set; }
        [Display(Name = "SA MC Label", Order = 9, GroupName = "Chart Trader Buttons")]         public string LblSAMC { get; set; }
        [Display(Name = "Lmt Buy Label",  Order = 9,  GroupName = "Chart Trader Buttons")]     public string LblLmtBuy  { get; set; }
        [Display(Name = "Lmt Sell Label", Order = 10, GroupName = "Chart Trader Buttons")]     public string LblLmtSell { get; set; }
        [Display(Name = "BB BL Label", Order = 11, GroupName = "Chart Trader Buttons")]        public string LblBBBL { get; set; }
        [Display(Name = "SA BR Label", Order = 11, GroupName = "Chart Trader Buttons")]        public string LblSABR { get; set; }
        [Display(Name = "SE L Label", Order = 12, GroupName = "Chart Trader Buttons")]         public string LblSEL { get; set; }
        [Display(Name = "SE S Label", Order = 13, GroupName = "Chart Trader Buttons")]         public string LblSES { get; set; }
        [Display(Name = "Speedo Label", Order = 14, GroupName = "Chart Trader Buttons")]       public string LblSpeedo { get; set; }
        [Display(Name = "Flat Label", Order = 15, GroupName = "Chart Trader Buttons")]         public string LblFlat { get; set; }
        [Display(Name = "BE Label", Order = 16, GroupName = "Chart Trader Buttons")]           public string LblBE { get; set; }
        [Display(Name = "Cancel Label", Order = 17, GroupName = "Chart Trader Buttons")]       public string LblCancel { get; set; }
        [Display(Name = "Color - Strategy ON", Order = 18, GroupName = "Chart Trader Buttons")] public Color ColorStrategyOn { get; set; }
        [Display(Name = "Color - Strategy OFF", Order = 19, GroupName = "Chart Trader Buttons")] public Color ColorStrategyOff { get; set; }
        [Display(Name = "Color - Armed", Order = 20, GroupName = "Chart Trader Buttons")]      public Color ColorArmed { get; set; }
        [Display(Name = "Color - Filled", Order = 21, GroupName = "Chart Trader Buttons")]     public Color ColorFilled { get; set; }
        [Display(Name = "Color - Armed Bar Select", Order = 22, GroupName = "Chart Trader Buttons")] public Color ColorArmedBarSel { get; set; }
        [Display(Name = "Color - Waiting Bar", Order = 23, GroupName = "Chart Trader Buttons")] public Color ColorWaitingBar { get; set; }
        [Display(Name = "Color - Toggle ON", Order = 24, GroupName = "Chart Trader Buttons")]  public Color ColorToggleOn { get; set; }
        [Display(Name = "Color - Toggle OFF", Order = 25, GroupName = "Chart Trader Buttons")] public Color ColorToggleOff { get; set; }
        [Display(Name = "Color - Flat", Order = 26, GroupName = "Chart Trader Buttons")]       public Color ColorFlat { get; set; }
        [Display(Name = "Color - BE", Order = 27, GroupName = "Chart Trader Buttons")]         public Color ColorBE { get; set; }
        [Display(Name = "Color - Cancel", Order = 28, GroupName = "Chart Trader Buttons")]     public Color ColorCancel { get; set; }
        [Display(Name = "Color - Flash", Order = 29, GroupName = "Chart Trader Buttons")]      public Color ColorFlash { get; set; }

        // CSV
        [Display(Name = "Export CSV", Order = 1, GroupName = "CSV")]      public bool ExportCSV { get; set; }
        [Display(Name = "CSV Folder Path", Order = 2, GroupName = "CSV")] public string CSVFolderPath { get; set; }
        [Display(Name = "Print To Output", Order = 3, GroupName = "CSV")] public bool PrintToOutput { get; set; }
        #endregion
    }
}