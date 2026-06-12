# Futures Contracts API
**Source:** https://massive.com/docs/rest/futures/contracts.md  
**Endpoint:** `GET /futures/v1/contracts`

## Purpose
Single source for discovering all listed futures contracts and retrieving complete contract specifications.

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `ticker` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ESM6` |
| `product_code` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ES` |
| `first_trade_date` | `.gt`, `.gte`, `.lt`, `.lte` | YYYY-MM-DD |
| `last_trade_date` | `.gt`, `.gte`, `.lt`, `.lte` | YYYY-MM-DD |
| `active` | — | Filter to active contracts only |
| `type` | — | `single` or `combo` (combo available from 2025-03-12) |
| `limit` | — | Default 100, max 1000 |
| `sort` | `.asc` / `.desc` | Customizable by column |

## Response Fields

| Field | Description |
|---|---|
| `ticker` | Contract identifier (e.g. `ESM6`) |
| `product_code` | Underlying product (e.g. `ES`) |
| `name` | Contract name |
| `first_trade_date` | First trading date |
| `last_trade_date` | Last trading date — use as rollover boundary |
| `settlement_date` | Settlement date |
| `days_to_maturity` | Calculated days remaining |
| `tick_size` | Tick size for trades (ES = 0.25) |
| `tick_size_spread` | Tick size for spreads |
| `tick_size_settlement` | Tick size for settlement |
| `min_order_qty` | Minimum order quantity |
| `max_order_qty` | Maximum order quantity |
| `trading_venue` | Exchange MIC code |
| `active` | Boolean — currently active |
| `type` | `single` or `combo` |

## Pagination
Response includes `next_url` cursor for additional pages.

## Availability
All Futures plans. History: 2 years (Basic/Starter) → all history (Advanced/Business) back to 2017-04-03.

## Usage in Bar Builder
- Query `product_code=ES&type=single` for date range → get all ES quarterly contracts
- Sort by `first_trade_date` → build rollover map
- `last_trade_date` = rollover boundary — switch contracts on this date
- `tick_size` = 0.25 for ES — used in bar builder tolerance checks
