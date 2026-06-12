# Futures Products API
**Source:** https://massive.com/docs/rest/futures/products.md  
**Endpoint:** `GET /futures/v1/products`

## Purpose
Unified source for discovering all supported futures products and retrieving full product specifications.

## Query Parameters

| Parameter | Operators | Notes |
|---|---|---|
| `product_code` | `.any_of`, `.gt`, `.gte`, `.lt`, `.lte` | e.g. `ES` |
| `name` | — | Product name filter |
| `trading_venue` | — | Exchange MIC code |
| `sector` | — | Sector filter |
| `asset_class` | — | Asset class filter |
| `type` | — | `single` or `combo` |
| `date` | — | Point-in-time lookup |
| `limit` | — | Pagination, supports `next_url` |

## Response Fields

| Field | Description |
|---|---|
| `product_code` | e.g. `ES` |
| `name` | Product name |
| `asset_class` | e.g. equity index, energy |
| `sector` | Classification |
| `settlement` | Settlement method details |
| `quotation` | Pricing format |
| `currency` | Trading currency |
| `unit_of_measure` | Underlying unit spec |
| `trading_venue` | Exchange MIC code |
| `type` | `single` or `combo` |
| `updated_at` | Last update timestamp |

## Availability
All Futures plans. History: 2 years (Basic/Starter/Developer) → all history (Advanced/Business) back to 2017-04-03. Updated daily.

## Usage
Use to look up product metadata for ES (tick value, currency, settlement type). Less critical than Contracts API for bar building — mainly for product-level specs.
