# Futures Market Status API
**Source:** https://massive.com/docs/rest/futures/market-operations/market-status.md  
**Endpoint:** `GET /futures/v1/market-status`

## Purpose
Retrieve real-time market status indicators (open, pause, close) for futures products.

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `product_code` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ES` |
| `limit` | — | Default 10, max 99 |

## Response Fields

| Field | Description |
|---|---|
| `market_event` | Current status: open, pause, close, etc. |
| `name` | Product description |
| `product_code` | e.g. `ES` |
| `session_end_date` | Trading date |
| `timestamp` | Event time |
| `trading_venue` | Exchange MIC code |

## Availability
All Futures plans. Updated in real time. No historical data tracking.

## Usage
Not needed for historical bar building or validation. Useful if App adds a live market status indicator.
