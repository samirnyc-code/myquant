"""Reverse-engineer NinjaTrader 8 .ncd tick files, validated against ground truth.

Ground truth: data/ticks_continuous/2026-07-09.parquet (from RawTickExporter, CT-naive,
RTH, cols DateTime/Price/Volume). We decode the matching ES 09-26 *.Last.ncd hour files
and check the decoder reproduces those ticks exactly before trusting it for 7/10+.

Header (28 bytes): int32 version | float64 tickSize | float64 basePrice | int64 baseTime(.NET ticks)
Records: proprietary — explored here.
"""
import struct
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

NCD_DIR = Path(r"C:\Users\Admin\Documents\NinjaTrader 8\db\tick\ES 09-26")
GT = Path(r"c:\Users\Admin\myquant\data\ticks_continuous\2026-07-09.parquet")
NET_EPOCH = datetime(1, 1, 1)


def net_ticks_to_dt(t):
    return NET_EPOCH + timedelta(microseconds=t / 10)


def read_header(b):
    ver = struct.unpack_from("<i", b, 0)[0]
    tick = struct.unpack_from("<d", b, 4)[0]
    base_px = struct.unpack_from("<d", b, 12)[0]
    base_t = struct.unpack_from("<q", b, 20)[0]
    return ver, tick, base_px, base_t


# pick an RTH hour: 13:00 UTC file ~ 08:00 CT (has the 08:30 open); explore a couple
for hh in ("1300", "1400"):
    f = NCD_DIR / f"202607091{hh[1:]}.Last.ncd" if False else NCD_DIR / f"20260709{hh}.Last.ncd"
    if not f.exists():
        print(f"missing {f.name}"); continue
    raw = f.read_bytes()
    ver, tick, base_px, base_t = read_header(raw)
    bt = net_ticks_to_dt(base_t)
    print(f"\n=== {f.name}  ({len(raw)} bytes) ===")
    print(f"version={ver} tickSize={tick} basePrice={base_px} baseTime(UTC?)={bt}")
    print(f"basePrice in ticks = {base_px/tick:.1f}")
    print("first 48 record bytes:", raw[28:28+48].hex(" "))

# ground truth around the open
gt = pd.read_parquet(GT)
gt["DateTime"] = pd.to_datetime(gt["DateTime"])
print("\n=== ground truth 7/09 first 12 RTH ticks (CT-naive) ===")
print(gt.head(12).to_string())
print("...last 3:", gt.tail(3)[["DateTime", "Price", "Volume"]].to_string())
print("n ticks 7/09:", len(gt), "price range", gt.Price.min(), gt.Price.max())
