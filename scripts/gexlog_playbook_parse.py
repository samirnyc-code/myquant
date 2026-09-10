"""Parse every archived GexLog MORNING playbook into machine-usable rules.

Step 1 of the "trade ONLY the report's playbook" backtest (user request S116):
for each day and each scenario (primary / alternative / neutral), extract
  - trigger: direction (>, <, between) + level(s), parsed from trigger text
  - structure: bull_call_debit / bear_put_debit / iron_condor / credit spread /
    butterfly / other, parsed from bias text
  - strike hints: "short strike near X", "targeting Y and Z" numbers
and measure parse coverage so the sim only runs on days we can execute
mechanically (unparseable days are listed, not silently dropped).

Output (dated):
  data/options_sim/playbook_rules_<YYYYMMDD>.csv   one row per day x scenario
  printed coverage summary
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
RAW = ROOT / "data" / "gexlog" / "raw"
OUT = ROOT / "data" / "options_sim"
STAMP = dt.date.today().strftime("%Y%m%d")

NUM = r"([0-9][0-9,]{2,7}(?:\.\d+)?)"


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def parse_trigger(t: str) -> dict:
    """'Holding > 7700 (...)' / 'Break < 7625' / 'between 7625 (Put Wall) and 7700'."""
    t = re.sub(r"\([^)]*\)", " ", t or "")  # parentheticals break the between-form
    m = re.search(rf"between\s+\D{{0,12}}?{NUM}\D{{0,25}}?and\s+\D{{0,12}}?{NUM}", t, re.I)
    if m:
        lo, hi = sorted([_f(m.group(1)), _f(m.group(2))])
        return {"trig_kind": "between", "trig_lo": lo, "trig_hi": hi}
    m = re.search(rf"(?:fade|rejection|rejects?)\s*(?:at|of|near)?\s*{NUM}", t, re.I)
    if m:
        return {"trig_kind": "reject_at", "trig_level": _f(m.group(1))}
    m = re.search(rf"(?:>|above|over|reclaim(?:s|ing)?\s*(?:of)?)\s*{NUM}", t, re.I)
    if m:
        return {"trig_kind": "above", "trig_level": _f(m.group(1))}
    m = re.search(rf"(?:<|below|under|break(?:s|down)?\s*(?:of|below)?)\s*{NUM}", t, re.I)
    if m:
        return {"trig_kind": "below", "trig_level": _f(m.group(1))}
    # 'Holding 7625 - 7700' range without the word between
    m = re.search(rf"{NUM}\s*(?:-|–|to)\s*{NUM}", t)
    if m:
        lo, hi = sorted([_f(m.group(1)), _f(m.group(2))])
        if hi - lo > 5:  # avoid matching a single decimal level
            return {"trig_kind": "between", "trig_lo": lo, "trig_hi": hi}
    return {"trig_kind": "unparsed"}


STRUCT_PATTERNS = [
    ("bull_call_debit", r"bull call (?:debit )?spread|call debit|debit call (?:spread|vertical)"),
    ("bear_put_debit", r"bear put (?:debit )?spread|put debit|debit put (?:spread|vertical)"),
    ("iron_condor", r"iron condor"),
    ("iron_fly", r"iron (?:butter)?fly|butterfly"),
    ("put_credit", r"(?:bull put|put credit) spread"),
    ("call_credit", r"(?:bear call|call credit) spread"),
    ("long_call", r"long call(?!\s*spread)"),
    ("long_put", r"long put(?!\s*spread)"),
    ("debit_spread_generic", r"debit spread"),
    ("credit_spread_generic", r"credit spread"),
]


def parse_structure(bias: str) -> dict:
    b = (bias or "").lower()
    struct = "unparsed"
    for name, rx in STRUCT_PATTERNS:
        if re.search(rx, b):
            struct = name
            break
    out = {"structure": struct}
    m = re.search(rf"short strikes? (?:near|at|around)\s*{NUM}", b)
    if m:
        out["short_hint"] = _f(m.group(1))
    tgts = re.findall(rf"(?:target(?:ing|s)?|toward|objectives?)[^.]*?{NUM}", b)
    if tgts:
        out["target1"] = _f(tgts[0])
        m2 = re.search(rf"target(?:ing|s)?[^.]*?{NUM}[^.]*?(?:and|then)[^.]*?{NUM}", b)
        if m2:
            out["target2"] = _f(m2.group(2))
    return out


def main():
    rows = []
    for f in sorted(glob.glob(str(RAW / "*_morning.json"))):
        date = Path(f).name[:10]
        d = json.load(open(f, encoding="utf-8"))
        pb = d.get("playbook") or {}
        lv = d.get("levels") or {}
        base = {"date": date, "pb_source": pb.get("source"),
                "putWall": lv.get("putWall"), "callWall": lv.get("callWall"),
                "current": lv.get("current"),
                "emLower": lv.get("emLower"), "emUpper": lv.get("emUpper"),
                "r1": lv.get("r1"), "r2": lv.get("r2"),
                "s1": lv.get("s1"), "s2": lv.get("s2")}
        scens = {k: v for k, v in pb.items() if isinstance(v, dict)}
        if not scens:
            rows.append(dict(base, scenario="NONE", trig_kind="no-playbook"))
            continue
        for name, sc in scens.items():
            r = dict(base, scenario=name, scen_name=sc.get("scenario"),
                     trigger_text=(sc.get("trigger") or "")[:160],
                     bias_text=(sc.get("bias") or "")[:300])
            r.update(parse_trigger(sc.get("trigger") or ""))
            r.update(parse_structure(sc.get("bias") or ""))
            rows.append(r)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"playbook_rules_{STAMP}.csv", index=False)

    days = df["date"].nunique()
    nopb = df[df["scenario"] == "NONE"]["date"].nunique()
    sc = df[df["scenario"] != "NONE"]
    print(f"mornings on disk: {days}  ({df['date'].min()}..{df['date'].max()})")
    print(f"  no playbook block: {nopb} days")
    print(f"  scenario rows: {len(sc)}  (per-day: {sc.groupby('date').size().mean():.1f})")
    print(f"\ntrigger parse:  {sc['trig_kind'].value_counts().to_dict()}")
    print(f"structure parse: {sc['structure'].value_counts().to_dict()}")
    ok = sc[(sc["trig_kind"] != "unparsed") & (sc["structure"] != "unparsed")]
    full_days = ok.groupby("date").size()
    full3 = (full_days >= 3).sum()
    print(f"\nscenario fully parsed (trigger+structure): {len(ok)}/{len(sc)}")
    print(f"days with ALL 3 scenarios parsed: {full3}/{days - nopb}")
    bad = sc[(sc["trig_kind"] == "unparsed") | (sc["structure"] == "unparsed")]
    if len(bad):
        print("\nUNPARSED rows (date scenario | trigger | bias-head):")
        for r in bad.itertuples(index=False):
            print(f"  {r.date} {r.scenario:11} trig={r.trig_kind:8} struct={r.structure:22} "
                  f"| {str(r.trigger_text)[:70]}")
    print(f"\nsaved: playbook_rules_{STAMP}.csv")


if __name__ == "__main__":
    main()
