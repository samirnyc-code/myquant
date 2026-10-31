"""Dig into every 'stood_down_broken' (zero/negative credit) stand-down across
the full live window: is it a GENUINE breach (spot really is already past the
short strike at fire time) or a QUOTE/LIQUIDITY GLITCH (strike was still a
healthy distance away, so est_net<=0 must have come from a bad/crossed quote,
not price action)? gate()'s check is simply `est_net <= 0` -- it does not
distinguish the two causes, and the printed message ("wall already blown
through") asserts the breach explanation unconditionally.

Method per stood-down trigger:
  EOD-anchored (eodic_p/eodic_c): structure is resolved PREMARKET (prior close
  +/- EM), so trig['structure']['short'] is always a real number even when
  stood down. Compare directly to that morning's actual open (no live-spot
  lookup needed).
  Open-anchored (openic_p/openic_c) / GexLog-wall (gx_bps/gx_bcs): structure
  for open-anchored is 'vertical_dynamic' (offset only, no resolved strike) --
  reconstruct the implied strike from the underlying tape at the trigger's own
  fire['not_before'] time (09:05 on WAIT days, 08:30 otherwise). GexLog-wall
  structures ARE resolved premarket (putWall/callWall), same as EOD.

Classification: breach if spot is AT OR THROUGH the implied strike at fire
time (<=2pt buffer for call, >=-2pt for put, to allow for tape granularity);
glitch if the strike was still >5pt away; ambiguous in between.

Run: .venv/Scripts/python.exe scripts/broken_wall_forensics_20261101.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def g(d, *path, default=None):
    for k in path:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return d if d is not None else default


def nearest_tape_spot(date, hhmm_target):
    f = SIM / f"underlying_{date.replace('-', '')}.csv"
    if not f.exists():
        return None, None
    u = pd.read_csv(f)
    if not len(u):
        return None, None
    target = pd.to_datetime(f"{date} {hhmm_target}:00")
    u["ts"] = pd.to_datetime(date + " " + u["ts_et"])
    u["dt"] = (u["ts"] - target).abs()
    row = u.loc[u["dt"].idxmin()]
    return row["und"], row["ts_et"]


def main():
    rows = []
    for f in sorted(glob.glob(str(SIM / "gameplan_*.json"))):
        date_raw = Path(f).stem.replace("gameplan_", "")
        date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
        try:
            p = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        for t in p.get("triggers", []):
            if t.get("status") != "stood_down_broken":
                continue
            setup = t.get("setup")
            right = g(t, "structure", "right")
            kind = g(t, "structure", "kind")
            not_before = g(t, "fire", "not_before", default="08:30")
            is_wait_day = "WAIT day" in (t.get("grade_basis") or "")

            if kind == "vertical":
                strike = g(t, "structure", "short")
                spot_src = "resolved premarket"
                spot, spot_ts = nearest_tape_spot(date, "08:30")
            else:  # vertical_dynamic -- reconstruct from the tape at fire time
                offset = g(t, "structure", "offset")
                spot, spot_ts = nearest_tape_spot(date, not_before)
                strike = round(spot + offset) if (spot is not None and offset is not None) else None
                spot_src = f"reconstructed @ {not_before}"

            if strike is None or spot is None:
                verdict = "unresolvable"
                dist = None
            else:
                dist = (strike - spot) if right == "C" else (spot - strike)
                if dist <= 2:
                    verdict = "GENUINE BREACH"
                elif dist <= 5:
                    verdict = "ambiguous"
                else:
                    verdict = "LIKELY GLITCH"

            rows.append({
                "date": date, "setup": setup, "right": right, "is_wait_day": is_wait_day,
                "not_before": not_before, "strike": strike, "spot": spot, "spot_src": spot_src,
                "spot_ts": spot_ts, "dist_pts": round(dist, 1) if dist is not None else None,
                "verdict": verdict,
            })

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "broken_wall_forensics_20261101.csv", index=False)

    print(f"total 'stood_down_broken' events across the full window: {len(df)}\n")
    print("=== by setup ===")
    print(df.groupby("setup")["verdict"].value_counts().unstack(fill_value=0).to_string())
    print("\n=== by WAIT-day flag ===")
    print(df.groupby("is_wait_day")["verdict"].value_counts().unstack(fill_value=0).to_string())
    print("\n=== overall verdict counts ===")
    print(df["verdict"].value_counts().to_string())
    print("\n=== sample of LIKELY GLITCH rows (should NOT be called 'wall blown through') ===")
    print(df[df["verdict"] == "LIKELY GLITCH"][["date", "setup", "right", "is_wait_day", "strike", "spot", "dist_pts"]].to_string(index=False))
    print("\n=== sample of GENUINE BREACH rows ===")
    print(df[df["verdict"] == "GENUINE BREACH"][["date", "setup", "right", "is_wait_day", "strike", "spot", "dist_pts"]].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
