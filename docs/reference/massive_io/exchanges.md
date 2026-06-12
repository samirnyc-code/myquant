# Futures Exchanges API
**Source:** https://massive.com/docs/rest/futures/market-operations/exchanges.md  
**Endpoint:** `GET /futures/v1/exchanges`

## Purpose
Retrieve a list of supported futures exchanges with their codes, names, and details.

## Query Parameters

| Parameter | Notes |
|---|---|
| `limit` | Default 100, max 999 |

## Response Fields

| Field | Description |
|---|---|
| `acronym` | Exchange acronym, e.g. `CME`, `NYMEX` |
| `id` | Numeric exchange ID (matches `exchange` field in Trades API) |
| `locale` | Locale information |
| `mic` | Market Identifier Code per ISO 10383 |
| `name` | Official exchange name |
| `url` | Exchange website |
| `type` | Venue type classification |

## Availability
All Futures plans. Updated as needed.

## Usage
Look up exchange `id` → `acronym` mapping for display purposes. In the Trades API, the `exchange` field is a numeric ID (e.g. `1` in the sample CSV). Use this endpoint to resolve `1` → `CME`.
