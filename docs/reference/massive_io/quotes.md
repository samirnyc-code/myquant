# Futures Quotes API
**Source:** https://massive.com/docs/rest/futures/trades-quotes/quotes.md  
**Endpoint:** `GET /futures/v1/quotes/{ticker}`

## Purpose
Retrieve bid/ask quote data for futures contracts. Supports historical and real-time quote analysis.

## Path Parameters

| Parameter | Required | Notes |
|---|---|---|
| `ticker` | Yes | Contract identifier with expiration, e.g. `GCJ5` |

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `timestamp` | `.gt`, `.gte`, `.lt`, `.lte` | Multiple formats supported |
| `session_end_date` | — | YYYY-MM-DD |
| `limit` | — | Max 49,999 |
| `sort` | `.asc` / `.desc` | |

## Response Fields

| Field | Description |
|---|---|
| `bid_price` | Bid price per unit of underlying |
| `ask_price` | Ask price per unit of underlying |
| `bid_size` | Bid size |
| `ask_size` | Ask size |
| `timestamp` | Submission timestamp |
| `sequence_number` | CME sequence number |
| `exchange` | Exchange identifier |
| `session_end_date` | Trading date |

**Note:** Prices are per unit of underlying — apply contract multiplier for full contract value.

## Availability

| Plan | Access | Recency | History |
|---|---|---|---|
| Basic / Starter | **No access** | — | — |
| Developer | Yes | 10-min delay | 5 years |
| Advanced | Yes | Real-time | All (2017-04-03) |
| Business (all) | Yes | Real-time | All (2017-04-03) |

## Usage
Not required for OHLCV bar building from Last prices. Relevant if bid/ask spread analysis or tick replay (NT bid/ask format) is needed in future.
