"""library_chart_post.py — POST a library_chart_build.py JSON to the Trade
Playbook's shared Library tab (/api/ingest/library-chart).

Reuses the same secret/base_url the NT8 journal uploader already posts with
(Desktop/trade-playbook/scripts/uploader_config.json) — one shared
INGEST_SECRET for both pipelines, nothing new to configure.

  python scripts/library_chart_post.py 2026-10-07 [--bar-type 2000t]
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import requests

WT = Path(__file__).resolve().parent.parent
UPLOADER_CONFIG = Path(r"C:/Users/Admin/Desktop/trade-playbook/scripts/uploader_config.json")
DATA_DIR = WT / "data" / "annotations" / "library"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--bar-type", default="2000t", help="e.g. 1000t, 2000t, 4000t, 5m, 15m")
    a = ap.parse_args()

    cfg = json.loads(UPLOADER_CONFIG.read_text())
    secret, base_url = cfg["secret"], cfg["base_url"].rstrip("/")

    path = DATA_DIR / f"{a.date}_ES_{a.bar_type}_ETH.json"
    if not path.exists():
        raise SystemExit(f"no built chart at {path} — run library_chart_build.py first")
    payload = json.loads(path.read_text())

    r = requests.post(f"{base_url}/api/ingest/library-chart",
                       headers={"x-ingest-secret": secret, "Content-Type": "application/json"},
                       json=payload, timeout=30)
    r.raise_for_status()
    print(f"{a.date} [{a.bar_type}]: posted -> {base_url}/library  ({r.json()})")


if __name__ == "__main__":
    main()
