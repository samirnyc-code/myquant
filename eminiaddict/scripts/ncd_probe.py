"""Probe an NT8 .ncd tick file to reverse-engineer its layout. Read-only.
Prints multiple interpretations of the header bytes + a scan for plausible ES
prices / .NET-tick timestamps, to calibrate a real reader.
Usage: python ncd_probe.py "<path to .Last.ncd>"
"""
import struct
import sys

DOTNET_EPOCH_TICKS = 621355968000000000  # 1970-01-01 in .NET ticks


def dt(ticks):
    import datetime
    unix = (ticks - DOTNET_EPOCH_TICKS) / 1e7
    if 1.5e9 < unix < 1.9e9:
        return datetime.datetime.utcfromtimestamp(unix).isoformat()
    return None


def main():
    p = sys.argv[1]
    b = open(p, "rb").read()
    print(f"file {p}  size={len(b)}")
    print("first 48 bytes:", b[:48].hex(" "))
    print("\n-- header interpretations by offset --")
    for off in range(0, 40, 4):
        i32 = struct.unpack_from("<i", b, off)[0]
        f32 = struct.unpack_from("<f", b, off)[0]
        i64 = struct.unpack_from("<q", b, off)[0] if off + 8 <= len(b) else None
        f64 = struct.unpack_from("<d", b, off)[0] if off + 8 <= len(b) else None
        ts = dt(i64) if i64 else None
        print(f"  @{off:2d}: i32={i32:<12} f32={f32:<14.5g} i64={i64} f64={f64:.6g}"
              + (f"  <-- TIMESTAMP {ts}" if ts else ""))
    # scan whole file for plausible .NET timestamps (2026) and ES prices as int64/double
    print("\n-- scanning for .NET timestamps (2026) --")
    hits = 0
    for off in range(0, min(len(b) - 8, 4000)):
        i64 = struct.unpack_from("<q", b, off)[0]
        ts = dt(i64)
        if ts and ts.startswith("2026"):
            print(f"  @{off}: {ts}  (i64={i64})")
            hits += 1
            if hits > 6:
                break
    # scan for ES price as double (7000..8000) or int64 price/ticksize (28000..32000)
    print("\n-- scanning for ES price doubles (7000-8000) --")
    hits = 0
    for off in range(0, min(len(b) - 8, 4000)):
        f = struct.unpack_from("<d", b, off)[0]
        if 7000 < f < 8000:
            print(f"  @{off}: {f}")
            hits += 1
            if hits > 6:
                break


if __name__ == "__main__":
    main()
