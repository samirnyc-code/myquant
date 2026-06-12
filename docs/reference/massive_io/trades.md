# Futures Trades API
**Source:** https://massive.com/docs/rest/futures/trades-quotes/trades.md  
**Endpoint:** `GET /futures/v1/trades/{ticker}`

## Purpose
Retrieve tick-level trade data for a futures contract over a defined time range. Individual trade events with nanosecond-precision timestamps.

## Path Parameters

| Parameter | Required | Notes |
|---|---|---|
| `ticker` | Yes | Contract identifier with expiration, e.g. `ESM6` |

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `timestamp` | `.gt`, `.gte`, `.lt`, `.lte` | Nanosecond Unix timestamp or ISO format |
| `session_end_date` | `.gt`, `.gte`, `.lt`, `.lte` | YYYY-MM-DD — filter by trading date |
| `limit` | — | Default 10, **max 49,999** |
| `sort` | `.asc` / `.desc` | |

## Response Fields

| Field | Description |
|---|---|
| `ticker` | Contract identifier |
| `timestamp` | Nanosecond-precision Unix timestamp |
| `price` | Trade price |
| `size` | Contract size (volume) |
| `sequence_number` | CME sequence number |
| `conditions` | Trade condition codes — **does not apply to ES** (equities only) |
| `correction` | Correction flag — exclude non-zero values |
| `exchange` | Exchange numeric ID |
| `session_end_date` | Trading date (CT convention) |

## Pagination
Response includes `next_url` cursor. With max 49,999 per page, ES intraday volume (~500k–1M ticks/day) requires ~10–20 pages per trading day.

## Availability

| Plan | Access | Recency | History |
|---|---|---|---|
| Basic / Starter | **No access** | — | — |
| Developer | Yes | 10-min delay | 5 years |
| Advanced | Yes | Real-time | All (2017-04-03) |
| Business (all) | Yes | Real-time | All (2017-04-03) |

## Usage in Bar Builder
- Primary tick source for App 5M bar construction
- Also source for NT import conversion (tick → NT format)
- Filter: `correction == 0` only (exclude cancelled/corrected trades)
- `conditions` field: ignore for ES futures (applies to equities only)
- Timestamps are nanosecond Unix — convert to CT for session boundary matching
- Cache locally after fetch (parquet recommended) — do not re-fetch on every run

## NT Import Conversion
NT tick import format: `yyyyMMdd HHmmss;price;volume` (second precision)  
Or sub-second: `yyyyMMdd HHmmss.fff;price;volume`  
File naming: `ESM6.Last.txt`  
Timezone for import: specify source timezone (CT) in NT Historical Data window
