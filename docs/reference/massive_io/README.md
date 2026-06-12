# Massive.io Futures API Reference
**Source:** https://massive.com/docs/rest/futures/  
**Last Updated:** 2026-06-12

## Endpoints

| File | Endpoint | Purpose |
|---|---|---|
| [contracts.md](contracts.md) | `GET /futures/v1/contracts` | Discover contracts, rollover dates, tick sizes |
| [products.md](products.md) | `GET /futures/v1/products` | Product-level specs (asset class, settlement, currency) |
| [schedules.md](schedules.md) | `GET /futures/v1/schedules` | Session open/close per day — replaces hardcoded RTH times |
| [aggregates.md](aggregates.md) | `GET /futures/v1/aggs/{ticker}` | Pre-built OHLCV bars at any resolution (5min, 1hour, etc.) |
| [trades.md](trades.md) | `GET /futures/v1/trades/{ticker}` | Tick-level trade data, nanosecond timestamps |
| [quotes.md](quotes.md) | `GET /futures/v1/quotes/{ticker}` | Bid/ask quote data |
| [contracts_snapshot.md](contracts_snapshot.md) | `GET /futures/v1/snapshot` | Real-time contract snapshots |
| [market_status.md](market_status.md) | `GET /futures/v1/market-status` | Real-time market open/close status |
| [exchanges.md](exchanges.md) | `GET /futures/v1/exchanges` | Exchange ID → acronym lookup |

## Plan Requirements Summary

| Endpoint | Basic | Starter | Developer | Advanced | Business |
|---|---|---|---|---|---|
| Contracts | ✓ | ✓ | ✓ | ✓ | ✓ |
| Products | ✓ | ✓ | ✓ | ✓ | ✓ |
| Schedules | ✓ | ✓ | ✓ | ✓ | ✓ |
| Aggs | ✓ | ✓ (10min delay) | ✓ (10min delay) | ✓ RT | ✓ RT |
| Trades | ✗ | ✗ | ✓ (10min delay) | ✓ RT | ✓ RT |
| Quotes | ✗ | ✗ | ✓ (10min delay) | ✓ RT | ✓ RT |
| Snapshot | ✗ | ✓ | ✓ | ✓ | ✓ |
| Market Status | ✓ | ✓ | ✓ | ✓ | ✓ |
| Exchanges | ✓ | ✓ | ✓ | ✓ | ✓ |

**Minimum plan for this project:** Futures Advanced or Business (CME) — needed for Trades API with full history.

## Key Facts for Bar Building

- **Timestamps:** nanosecond Unix in Trades/Quotes; CT dates in Schedules/Aggs
- **session_end_date:** shared key across all APIs — CME day ends at 17:00 CT
- **ES tick size:** 0.25 pts (from Contracts API)
- **ES ticker format:** quarterly contracts e.g. `ESH6`, `ESM6`, `ESU6`, `ESZ6`
- **Rollover:** use `last_trade_date` from Contracts API — no hardcoded dates
- **Conditions field:** irrelevant for ES futures (equities only)
- **Correction field:** exclude `correction != 0` trades
- **Pagination:** Trades/Quotes max 49,999 per page — ES needs ~10–20 pages/day
