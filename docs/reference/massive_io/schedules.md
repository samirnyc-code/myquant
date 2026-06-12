# Futures Schedules API
**Source:** https://massive.com/docs/rest/futures/schedules.md  
**Endpoint:** `GET /futures/v1/schedules`

## Purpose
Retrieve precise session open/close times, intraday breaks, and holiday/special-event adjustments for futures markets.

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `product_code` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ES` |
| `session_end_date` | `.gt`, `.gte`, `.lt`, `.lte` | YYYY-MM-DD — trading date |
| `trading_venue` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | Exchange MIC code |
| `limit` | — | Default 10, max 1000 |
| `sort` | `.asc` / `.desc` | Comma-separated columns |

## Response Fields

| Field | Description |
|---|---|
| `event` | Session event type: `pre_open`, `open`, `close`, etc. |
| `product_code` | e.g. `ES` |
| `product_name` | Product name |
| `session_end_date` | Trading date (sessions end at 17:00 CT) |
| `timestamp` | UTC timestamp for this event |
| `trading_venue` | Exchange MIC code |

## Pagination
Response includes `next_url` cursor.

## Availability
All Futures plans. History: 2 years (Basic/Starter) → all history (Advanced/Business) back to 2017-04-03. Updated daily.

## Usage in Bar Builder
- **Critical:** replaces hardcoded RTH session boundaries (08:30–15:15 CT)
- Query by `product_code=ES` + `session_end_date` range
- Filter `event=open` → RTH open timestamp per day
- Filter `event=close` → RTH close timestamp per day
- Handles holidays and shortened sessions automatically
- `session_end_date` convention: CME trading day ends at 17:00 CT — same key used across Trades, Contracts, and Schedules APIs
