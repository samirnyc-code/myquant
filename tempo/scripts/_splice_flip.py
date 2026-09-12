"""_splice_flip.py — replace RenderClimaxFlips block in TempoSpeedometer.cs with
the one-trade-at-a-time version from _flip_method.cs.txt (S117-tempo)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
cs = ROOT / "nt8" / "indicators" / "TempoSpeedometer.cs"
src = cs.read_text(encoding="utf-8")
start = src.index("\t\t// climax-flip helpers")
end = src.index("\t\tprivate SharpDX.Color4 HeatColor")
method = (ROOT / "tempo" / "scripts" / "_flip_method.cs.txt").read_text(encoding="utf-8")
if not method.endswith("\n"):
    method += "\n"
cs.write_text(src[:start] + method + "\n" + src[end:], encoding="utf-8")
print("spliced OK")
