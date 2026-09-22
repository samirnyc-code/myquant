"""Transcribe an EminiAddict daily video (audio wav) with faster-whisper, timestamped,
so we can mine what David Halsey actually says/draws. Copyrighted (paying subscriber) —
transcripts go to scratchpad/committed-notes as DERIVED study notes, not the raw media.

Usage: python transcribe_video.py <wav_path> <out_txt>  [model]
"""
import sys
from faster_whisper import WhisperModel

wav = sys.argv[1]
out = sys.argv[2]
model_name = sys.argv[3] if len(sys.argv) > 3 else "small.en"

print(f"loading {model_name} ...")
model = WhisperModel(model_name, device="cpu", compute_type="int8")
print("transcribing", wav)
segments, info = model.transcribe(wav, language="en", vad_filter=True,
                                  vad_parameters=dict(min_silence_duration_ms=500))
lines = []
for s in segments:
    ts = f"[{int(s.start//60):02d}:{int(s.start%60):02d}]"
    lines.append(f"{ts} {s.text.strip()}")
    if len(lines) % 20 == 0:
        print(f"  ...{lines[-1][:70]}")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print(f"wrote {out}  ({len(lines)} segments, {info.duration:.0f}s)")
