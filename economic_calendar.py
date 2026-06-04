import streamlit as st
import pandas as pd
import requests

# ── FOMC announcement dates (2:00 PM ET = 1:00 PM CT) ────────────────────────
# Source: federalreserve.gov/monetarypolicy/fomccalendars.htm
# These are the second day of each meeting — when the decision is announced.
# Verified through 2025 from the Fed's official calendar.
# 2026: confirmed by fetching federalreserve.gov directly on 2026-06-04.

_FOMC_DATES = [
    # 2015
    "2015-01-28","2015-03-18","2015-04-29","2015-06-17",
    "2015-07-29","2015-09-17","2015-10-28","2015-12-16",
    # 2016
    "2016-01-27","2016-03-16","2016-04-27","2016-06-15",
    "2016-07-27","2016-09-21","2016-11-02","2016-12-14",
    # 2017
    "2017-02-01","2017-03-15","2017-05-03","2017-06-14",
    "2017-07-26","2017-09-20","2017-11-01","2017-12-13",
    # 2018
    "2018-01-31","2018-03-21","2018-05-02","2018-06-13",
    "2018-08-01","2018-09-26","2018-11-08","2018-12-19",
    # 2019
    "2019-01-30","2019-03-20","2019-05-01","2019-06-19",
    "2019-07-31","2019-09-18","2019-10-30","2019-12-11",
    # 2020 — includes 2 emergency cuts (Mar 3 and Mar 15)
    "2020-01-29","2020-03-03","2020-03-15","2020-04-29",
    "2020-06-10","2020-07-29","2020-09-16","2020-11-05","2020-12-16",
    # 2021
    "2021-01-27","2021-03-17","2021-04-28","2021-06-16",
    "2021-07-28","2021-09-22","2021-11-03","2021-12-15",
    # 2022
    "2022-01-26","2022-03-16","2022-05-04","2022-06-15",
    "2022-07-27","2022-09-21","2022-11-02","2022-12-14",
    # 2023
    "2023-02-01","2023-03-22","2023-05-03","2023-06-14",
    "2023-07-26","2023-09-20","2023-11-01","2023-12-13",
    # 2024
    "2024-01-31","2024-03-20","2024-05-01","2024-06-12",
    "2024-07-31","2024-09-18","2024-11-07","2024-12-18",
    # 2025
    "2025-01-29","2025-03-19","2025-05-07","2025-06-18",
    "2025-07-30","2025-09-17","2025-10-29","2025-12-17",
    # 2026 — confirmed from federalreserve.gov on 2026-06-04
    "2026-01-28","2026-03-18","2026-04-29","2026-06-17",
    "2026-07-29","2026-09-16","2026-10-28","2026-12-09",
]

# ── Release times in CT ───────────────────────────────────────────────────────
# Institutionally fixed. CT is always 1 hour behind ET (both shift for DST).
# NFP / CPI: 8:30 AM ET = 7:30 AM CT — released BEFORE RTH opens (8:30 CT).
#   "Skip full day" is the most meaningful filter for these.
#   "Window ±N min" only starts affecting RTH bars when N > 60.
# FOMC: 2:00 PM ET = 1:00 PM CT — released DURING RTH.
#   Both filter modes are meaningful.

EVENT_TIME_CT = {
    "FOMC": "13:00",
    "NFP":  "07:30",
    "CPI":  "07:30",
}

EVENT_COLOR = {
    "FOMC": "#ff6b35",
    "NFP":  "#4ecdc4",
    "CPI":  "#45b7d1",
}

# ── FRED release IDs (verified by calling FRED API) ───────────────────────────
# release_id=50 → "Employment Situation" (NFP)
# release_id=10 → "Consumer Price Index"  (CPI)

_FRED_RELEASE_IDS = {
    "NFP": 50,
    "CPI": 10,
}


# ── API key ───────────────────────────────────────────────────────────────────

def _fred_key() -> str | None:
    try:
        return st.secrets.get("FRED_API_KEY") or None
    except Exception:
        return None


def fred_key_configured() -> bool:
    return _fred_key() is not None


# ── FRED fetch ────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=86_400)
def _fetch_fred_dates(release_id: int, start: str, end: str, api_key: str) -> list[str]:
    """
    Fetch all release dates for a FRED release ID.
    FRED sometimes returns multiple dates per month (initial + revision).
    We return the FIRST date per calendar month only — that is the market-moving event.
    """
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/release/dates",
            params={
                "release_id":     release_id,
                "realtime_start": start,
                "realtime_end":   end,
                "api_key":        api_key,
                "file_type":      "json",
                "sort_order":     "asc",
                "limit":          1000,
            },
            timeout=10,
        )
        resp.raise_for_status()
        raw_dates = [d["date"] for d in resp.json().get("release_dates", [])]
    except Exception:
        return []

    # Deduplicate: keep only the first release per month
    seen: set = set()
    result: list[str] = []
    for d in raw_dates:
        ym = d[:7]  # "YYYY-MM"
        if ym not in seen:
            seen.add(ym)
            result.append(d)
    return result


# ── Main public function ──────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_economic_events(event_types: tuple, start: str, end: str) -> pd.DataFrame:
    """
    Returns DataFrame: DateTime (CT, tz-naive), EventType, Color.
    DateTime is the exact announcement moment in CT.
    event_types must be a tuple for st.cache_data compatibility.
    """
    key  = _fred_key()
    rows = []
    s_dt = pd.Timestamp(start)
    e_dt = pd.Timestamp(end) + pd.Timedelta(days=1)

    for etype in event_types:
        time_ct = EVENT_TIME_CT[etype]

        if etype == "FOMC":
            dates = _FOMC_DATES
        elif key:
            dates = _fetch_fred_dates(_FRED_RELEASE_IDS[etype], start, end, key)
        else:
            dates = []

        for d in dates:
            dt = pd.Timestamp(f"{d} {time_ct}")
            if s_dt <= dt <= e_dt:
                rows.append({
                    "DateTime":  dt,
                    "EventType": etype,
                    "Color":     EVENT_COLOR[etype],
                })

    if not rows:
        return pd.DataFrame(columns=["DateTime", "EventType", "Color"])
    return pd.DataFrame(rows).sort_values("DateTime").reset_index(drop=True)
