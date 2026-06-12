# Futures Aggregate Bars (OHLC) API
**Source:** https://massive.com/docs/rest/futures/aggregates.md  
**Endpoint:** `GET /futures/v1/aggs/{ticker}`

## Purpose
Retrieve historical OHLC and volume data for futures contracts with customizable time intervals and date ranges. All times in Central Time (CT).

## Path Parameters

| Parameter | Required | Notes |
|---|---|---|
| `ticker` | Yes | Contract identifier, e.g. `ESM6` |

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `resolution` | — | Candle size: `1min`, `5min`, `1hour`, `1session`, etc. |
| `window_start` | `.gte`, `.gt`, `.lte`, `.lt` | YYYY-MM-DD or nanosecond Unix timestamp |
| `limit` | — | Default 1000, max 50000 |
| `sort` | `.asc` / `.desc` | |

## Response Fields

| Field | Description |
|---|---|
| `open` | Bar open price |
| `high` | Bar high price |
| `low` | Bar low price |
| `close` | Bar close price |
| `volume` | Contract volume |
| `dollar_volume` | Dollar volume |
| `transaction_count` | Number of trades in bar |
| `settlement_price` | Settlement price (session bars) |
| `session_end_date` | Trading date in CT |
| `window_start` | Bar start timestamp |

## Availability

| Plan | Data Freshness | History |
|---|---|---|
| Basic | 8-hour delay | 2 years |
| Starter/Developer | 10-min delay | 2 years |
| Advanced | Real-time | All history (2017-04-03) |
| Business (all) | Real-time | All history (2017-04-03) |

## Usage in Three-Way Validation
- Fetch `resolution=5min` for ES contract over target date range
- This is the **massive.io reference bar** in the three-way comparison
- Compare against: NT 5M bars (built from imported ticks) + App 5M bars (built from Trades API ticks)
- All three should match → full confidence in App bar builder
