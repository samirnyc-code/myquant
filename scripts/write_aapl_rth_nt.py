"""
Fetch AAPL 5-min agg bars from Massive.io, filter RTH, write NT8 import file.
Output: ES_MAS 06-26.Last.txt  (same format as the earlier test file)
"""
import os
import time
import requests
import pandas as pd

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY    = "YOUR_API_KEY_HERE"
DATE_START = "2026-05-05"
DATE_END   = "2026-05-30"
OUTPUT_DIR = r"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\MAS_Import"
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL  = "https://api.massive.com"
RTH_START = "08:30:00"   # CT (= 9:30 ET during CDT)
RTH_END   = "15:00:00"   # CT (= 4:00 PM ET, exclusive — last bar open is 14:55)


def fetch_aggs(date_start: str, date_end: str) -> pd.DataFrame:
    url = f"{BASE_URL}/v2/aggs/ticker/AAPL/range/5/minute/{date_start}/{date_end}"
    params = {"sort": "asc", "limit": 5000, "apiKey": API_KEY}

    rows = []
    page = 0
    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        for b in body.get("results", []):
            rows.append({
                "t": b["t"],
                "o": float(b["o"]),
                "h": float(b["h"]),
                "l": float(b["l"]),
                "c": float(b["c"]),
                "v": float(b["v"]),
            })

        url    = body.get("next_url")
        params = {"apiKey": API_KEY}  # next_url omits apiKey — must re-add
        page  += 1
        if url:
            time.sleep(0.5)
        print(f"  page {page}: {len(rows):,} bars so far")

    df = pd.DataFrame(rows)
    return df


def main():
    print(f"Fetching AAPL 5-min bars {DATE_START} to {DATE_END}")
    df = fetch_aggs(DATE_START, DATE_END)
    print(f"Total bars fetched: {len(df):,}")

    # Convert ms UTC → CT
    dt_ct = (
        pd.to_datetime(df["t"], unit="ms", utc=True)
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
    )
    df["dt_ct"] = dt_ct

    # Filter RTH
    t = df["dt_ct"].dt.strftime("%H:%M:%S")
    rth = df[(t >= RTH_START) & (t < RTH_END)].copy()
    print(f"RTH bars (08:30–14:55 CT): {len(rth):,}")

    if rth.empty:
        print("No RTH bars found — check date range or API response.")
        return

    # Show sample
    print("\nFirst 3 bars:")
    for _, row in rth.head(3).iterrows():
        print(f"  {row['dt_ct']}  O={row['o']}  H={row['h']}  L={row['l']}  C={row['c']}  V={int(row['v'])}")
    print("Last bar:")
    last = rth.iloc[-1]
    print(f"  {last['dt_ct']}  O={last['o']}  H={last['h']}  L={last['l']}  C={last['c']}  V={int(last['v'])}")

    # Write NT8 tick import: yyyyMMdd HHmmss;close;volume
    lines = []
    for _, row in rth.iterrows():
        ts  = row["dt_ct"].strftime("%Y%m%d %H%M%S")
        vol = max(1, int(round(row["v"])))
        lines.append(f"{ts};{row['c']:.4f};{vol}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "ES_MAS 06-26.Last.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nWrote {len(lines)} rows to {out_path}")


if __name__ == "__main__":
    main()
