// MzFootprintExtractor — exports MzPack's computed footprint (delta, per-price bid/ask,
// imbalance/absorption counts, SR zones, unfinished auction, divergence, COT) to CSV via
// the SANCTIONED StrategyFootprintIndicator API. NO reflection, stable across updates.
//
// REQUIRES: MzPack Full Suite license (the StrategyFootprintIndicator wrapper is paid).
// If unlicensed this compiles but StrategyFootprintIndicator returns no bars at runtime.
// For a FREE path (raw bid/ask footprint we compute ourselves) use FootprintExporter.cs.
//
// This is a STRATEGY (the StrategyXxxIndicator API lives in the strategy layer). Apply to an
// ES chart with **Tick Replay ON**; it exports every historical bar the chart loads.
// Outputs (semicolon-free CSV):
//   data\footprint\ES_bars_<date>.csv   — one row per bar (summary + flags)
//   data\footprint\ES_cells_<date>.csv  — one row per bar x price (the bid/ask ladder)
//   data\footprint\ES_zones_<date>.csv  — one row per absorption/imbalance SR zone
//
// NOTE: the exact StrategyFootprintIndicator construction is per MzPack's API docs
// (docs.mzpack.pro/api). The field reads below are confirmed public on IFootprintBar from
// our reflection dump. Verify the constructor/attach call against your installed version.
// RULE (CLAUDE.md): lives in nt8/ and stays committed.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using MZpack;
using MZpack.NT8;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class MzFootprintExtractor : Strategy
    {
        private StrategyFootprintIndicator fp;
        private StreamWriter wBars, wCells, wZones;
        private string stamp;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "MzFootprintExtractor";
                Description = "Export MzPack footprint (delta/imbalance/absorption/zones) to CSV";
                Calculate = Calculate.OnBarClose;
                IsUnmanaged = false;
                ExportDir = @"C:\Users\Admin\myquant\data\footprint";
            }
            else if (State == State.Configure)
            {
                // create the MzPack footprint engine bound to this strategy's primary series
                fp = new StrategyFootprintIndicator(this);
                fp.Calculate = Calculate.OnBarClose;      // per MzPack API docs
                // (configure TicksPerLevel / imbalance & absorption filters here to match your chart)
            }
            else if (State == State.DataLoaded)
            {
                Directory.CreateDirectory(ExportDir);
                stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                wBars = Open("bars", "BarIdx,Time,Open,High,Low,Close,Volume,BuyVolume,SellVolume,Delta," +
                    "DeltaPct,DeltaCumulative,MinDelta,MaxDelta,POC,POCVolume,VAH,VAL,COTHigh,COTLow," +
                    "BuyImbCount,SellImbCount,BuyAbsCount,SellAbsCount,BuyDeltaDiv,SellDeltaDiv," +
                    "UnfinishedHigh,UnfinishedLow,TradesNumber");
                wCells = Open("cells", "BarIdx,Time,Price,BidVol,AskVol,Delta");
                wZones = Open("zones", "BarIdx,Time,ZoneType,Side,Hi,Lo,Volume");
            }
            else if (State == State.Terminated)
            {
                Close(wBars); Close(wCells); Close(wZones);
            }
        }

        private StreamWriter Open(string kind, string header)
        {
            var w = new StreamWriter(Path.Combine(ExportDir, $"ES_{kind}_{stamp}.csv"), false);
            w.WriteLine(header);
            return w;
        }
        private void Close(StreamWriter w) { if (w != null) { w.Flush(); w.Close(); } }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 0 || fp == null || fp.FootprintBars == null) return;
            if (!fp.FootprintBars.ContainsKey(CurrentBar)) return;
            IFootprintBar b = fp.FootprintBars[CurrentBar];
            if (b == null) return;

            try
            {
                wBars.WriteLine(string.Join(",", new object[] {
                    CurrentBar, b.Time.ToString("yyyy-MM-dd HH:mm:ss"),
                    b.Open, b.Hi, b.Lo, b.Close, b.Volume, b.BuyVolume, b.SellVolume, b.Delta,
                    b.DeltaPercentage, b.DeltaCumulative, b.MinDelta, b.MaxDelta,
                    b.POC, b.POCVolume, b.VAH, b.VAL, b.COTHigh, b.COTLow,
                    b.BuyImbalanceCount, b.SellImbalanceCount, b.BuyAbsorptionCount, b.SellAbsorptionCount,
                    b.IsBuyDeltaDivergence, b.IsSellDeltaDivergence,
                    b.UnfinishedAuctionHigh, b.UnfinishedAuctionLow, b.TradesNumber }));

                // per-price ladder — BuyVolumes/SellVolumes are SortedDictionary<double,long>
                if (b.BuyVolumes != null)
                    foreach (var kv in b.BuyVolumes)
                    {
                        double price = kv.Key;
                        long ask = kv.Value;
                        long bid = 0;
                        if (b.SellVolumes != null && b.SellVolumes.ContainsKey(price)) bid = b.SellVolumes[price];
                        wCells.WriteLine($"{CurrentBar},{b.Time:yyyy-MM-dd HH:mm:ss},{price},{bid},{ask},{ask - bid}");
                    }

                DumpZones(b.AbsorptionSRZones, "absorption", b);
                DumpZones(b.ImbalanceSRZones, "imbalance", b);
            }
            catch (Exception e) { Print("MzFootprintExtractor row failed @" + CurrentBar + ": " + e.Message); }
        }

        private void DumpZones(IBarSRZones zones, string type, IFootprintBar b)
        {
            if (zones == null || !zones.HasZones || zones.Zones == null) return;
            foreach (ISRZone z in zones.Zones)
                wZones.WriteLine($"{CurrentBar},{b.Time:yyyy-MM-dd HH:mm:ss},{type},{z.Side},{z.Hi},{z.Lo},{z.Volume}");
        }

        [NinjaScriptProperty]
        [Display(Name = "ExportDir", GroupName = "Parameters", Order = 0)]
        public string ExportDir { get; set; }
    }
}
