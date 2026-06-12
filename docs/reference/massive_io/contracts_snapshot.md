# Futures Contracts Snapshot API
**Source:** https://massive.com/docs/rest/futures/snapshots/contracts-snapshot.md  
**Endpoint:** `GET /futures/v1/snapshot`

## Purpose
Real-time snapshots for a set of futures contracts including latest trade, quote, session metrics, and settlement prices.

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `product_code` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ES` |
| `ticker` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ESZ24` |
| `limit` | — | Default 100, max 50000 |
| `sort` | `.asc` / `.desc` | |

## Response Structure

Each result contains five objects:

| Object | Fields |
|---|---|
| `last_trade` | price, size |
| `last_quote` | bid price, ask price, bid size, ask size, timestamp |
| `last_minute` | OHLCV for past minute |
| `session` | daily OHLCV, settlement price, change metrics |
| `details` | open interest, settlement date |

## Availability

| Plan | Access | Recency |
|---|---|---|
| Basic | **No access** | — |
| Starter / Developer | Yes | 10-min delay |
| Advanced | Yes | Real-time |
| Business (all) | Yes | Real-time |

## Usage
Not needed for bar building or validation. Useful for live monitoring of current contract prices if the App adds a live data view in the future.
