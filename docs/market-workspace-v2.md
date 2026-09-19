# Market workspace v2

## Product boundary

Step 04.11B expands Market into a provider-agnostic, read-only investment-market workspace. It adds no order placement, Buy/Sell action, broker execution, strategy output, market-regime scoring, Research mutation, Portfolio OS mutation, Governance mutation, or persistent write.

Routes:

- `/app/market` — broad recorded/live market context
- `/app/market/indices` and `/app/market/indices/:symbol`
- `/app/market/stocks`
- `/app/market/instruments/:symbol`
- `/app/market/sectors` and `/app/market/sectors/:sectorId`
- `/app/market/derivatives` — future placeholder only

The Market subnavigation follows the authenticated Research/Portfolio/Data pattern. It is not pill navigation.

## Provider architecture

`MarketDataProvider` declares explicit capabilities for instrument master, search, quote, LTP, OHLC, depth, historical candles, streaming, indices, sectors, F&O, and option chains. Seeded, Groww, unavailable, and a future Zerodha or exchange-authorized adapter all emit the same normalized observations. Frontend contracts do not contain Groww CSV fields or raw provider payloads.

`MARKET_DATA_PROVIDER` accepts `seeded`, `groww`, and `none`. Selecting Groww without credentials returns `UNAVAILABLE / GROWW_NOT_CONFIGURED`; no fallback occurs. Provider readiness is available at `GET /api/market/provider/status` without secret values.

The Groww adapter follows the official [authentication](https://groww.in/trade-api/docs/curl), [live quote/LTP/OHLC](https://groww.in/trade-api/docs/curl/live-data), [instrument master](https://groww.in/trade-api/docs/curl/instruments), [historical/F&O](https://groww.in/trade-api/docs/curl/backtesting), and [feed](https://groww.in/trade-api/docs/python-sdk/feed) boundaries. Credentials exist only in backend environment settings.

## Instruments and search

The backend downloads the public instrument CSV to a safe replace-on-refresh cache, normalizes all supported identity, exchange, segment, type, ISIN, underlying, expiry, strike, lot, and tick fields into `InterSignalInstrument`, and reuses the cache for search. Seeded mode provides the recorded current NIFTY 500 member and index universe. Search ranks exact symbol, prefix, then name/underlying matches and returns at most 50 results.

`GET /api/market/instruments/search?q=` returns `INTERSIGNAL_MARKET_SEARCH_V1`. The global command palette merges those Market results with existing Research, Portfolio, and navigation results. Stocks is search-first and never renders the entire instrument universe.

## Quotes, candles, charts, and depth

`GET /api/market/instruments/{symbol}/quote` returns a normalized instrument, LTP, change, OHLC, previous close, volume, bid/ask, supported depth, source, freshness, and provider session. Groww raw responses remain inside the adapter. A two-second cache coalesces repeated quote reads, and a shared limiter normalizes 429s.

`GET /api/market/instruments/{symbol}/candles` accepts `range`, `interval`, `from`, and `to` and returns `INTERSIGNAL_MARKET_CANDLES_V1`. Initial range defaults are 1D/5m, 5D/15m, and daily candles for 1M, 3M, 6M, and 1Y; seeded recorded data truthfully resolves to daily only.

The chart is a deterministic data-driven SVG renderer for line and candlestick modes. This was chosen after reviewing the current dependency set: the two bounded read-only modes require no interaction-heavy chart engine, and adding a large runtime dependency would not improve current semantics. Candles are derived only from API OHLC rows; there is no random or fabricated series. A future high-frequency/annotation surface can replace the renderer behind the same candle contract.

Depth uses a compact read-only bid/ask table. Unsupported or absent depth displays `Market depth unavailable`; it never fabricates an order book and has no click-to-order behavior.

## Indices, sectors, and context links

Indices exposes only provider-supported observations. NIFTY 500 detail preserves breadth and coverage; NIFTY 50 remains a reference index. Missing BANK NIFTY or FINNIFTY data is not invented.

Sectors exposes index value, change, breadth, relative volume, and coverage where the selected provider can establish them. Recorded sector indices and current mapping provide detail charts and constituents; leaders/laggards are descriptive session ordering, never recommendation labels.

Instrument Portfolio context performs a read-only symbol match against the current Portfolio OS holdings. A miss displays `Not currently held`. Research context displays `No instrument-specific research linked` because no truthful instrument-level relationship currently exists.

## Streaming and live aggregation

`GrowwFeedManager` owns authentication, connection state, reference-counted subscribe/unsubscribe, normalized tick conversion, bounded exponential reconnect, last-message heartbeat, and the 1,000-instrument provider cap. The provider callback crosses threads safely onto the application event loop.

`/api/market/stream` is the browser-facing WebSocket. Clients send normalized subscribe/unsubscribe messages, are limited to 25 visible instruments, and receive `INTERSIGNAL_MARKET_STREAM_V1` events only. `MarketLiveCache` retains last normalized quotes/timestamps and reserves backend-owned breadth/sector aggregate state. Browsers do not subscribe to NIFTY 500 constituents to compute aggregates.

The instrument page subscribes only when the quote provider is live. Seeded pages remain recorded. Market overview requires only broad/index context. REST remains a feature-level fallback; partial provider errors do not collapse unrelated pages.

## Session semantics and security

Session state comes from the provider/recorded calendar and is never inferred solely from the browser or machine clock. Closed sessions retain the last quote and historical chart. Indicator states are `Live`, `Market closed`, `Recorded market data`, `Provider ready`, or `Market unavailable`.

No API response, browser bundle, local storage, screenshot, or provider log contains credentials. Provider exceptions are sanitized. The implementation performs read-only HTTP/feed operations and no platform, Research, Portfolio, or Governance writes.

## Derivatives and licensing boundary

The backend defines normalized expiry, contract, option-chain, and historical-candle boundaries for future derivatives UI. The current route is a placeholder and contains no trading action.

Broker market-data APIs are development/personal/provider sources. Commercial multi-user display or redistribution may require direct exchange/data licensing and legal review. The provider-neutral contracts allow an exchange-authorized vendor to replace Groww without a frontend rewrite. Zerodha is intentionally not implemented in this step.
