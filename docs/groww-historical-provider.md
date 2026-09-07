# Groww Historical Provider

Current phase: Step 02.3B - Groww Historical Connection Validation

This provider validates read-only historical candle access for one NSE cash equity. It does not implement strategy logic, indicators, backtesting, paper trading, live trading, order placement, or database persistence.

## Official SDK And APIs

- SDK package: `growwapi==1.5.0`
- TOTP helper: `pyotp==2.10.0`
- Official SDK docs: https://groww.in/trade-api/docs/python-sdk
- Official backtesting historical candle docs: https://groww.in/trade-api/docs/python-sdk/backtesting
- Official instrument docs: https://groww.in/trade-api/docs/python-sdk/instruments

The provider uses:

- `GrowwAPI.get_access_token(api_key=..., totp=...)`
- `GrowwAPI(access_token)`
- `GrowwAPI.get_historical_candles(...)`

The SDK constructor prints to stdout, so InterSignal suppresses SDK stdout while creating clients and calling Groww APIs. Diagnostic output is generated only by InterSignal code.

## Credentials

Groww credentials must live only in `backend/.env`:

```text
GROWW_TOTP_TOKEN=
GROWW_TOTP_SECRET=
```

`backend/.env` is ignored by Git. `backend/.env.example` must keep these values blank. If either value is missing, the provider fails safely with `GROWW_NOT_CONFIGURED`.

Do not paste credentials into prompts, docs, README files, test files, source code, or tracked environment examples.

## Symbol Scope

Step 02.3B uses one NSE cash equity only:

```text
Exchange: NSE
Segment: CASH
Trading symbol: RELIANCE
Groww symbol: NSE-RELIANCE
```

The Groww symbol mapping is isolated inside the Groww adapter. Step 02.3B does not acquire the full Nifty 500 universe.

## Candle Format

Groww historical candles are normalized into the generic provider contract:

```text
[timestamp, open, high, low, close, volume, open_interest]
```

InterSignal currently stores:

- Daily: trading date, OHLC, volume, source
- Intraday: Asia/Kolkata timestamp, interval, OHLC, volume, source

Open interest is not used for cash-equity validation. VWAP and traded value are not supplied by this API response and remain `None`.

Rows missing required OHLCV fields are skipped and counted as incomplete provider rows. Malformed rows with bad timestamps or nonnumeric OHLCV values are reported as parse errors.

## Supported Intervals

The provider supports the documented Groww historical intervals:

```text
1m, 2m, 3m, 5m, 10m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo
```

Request range limits from the official docs:

```text
1m, 2m, 3m, 5m: max 30 days
10m, 15m, 30m: max 90 days
1h, 4h, 1d, 1w, 1mo: max 180 days
```

Historical data is documented as available from 2020.

## Read-Only Diagnostic

Run from `backend`:

```bash
.venv\Scripts\python.exe scripts\test_groww_history.py --symbol RELIANCE --daily-start 2025-01-01 --daily-end 2025-03-31
```

The diagnostic performs:

- Daily dry-run validation for `2025-01-01` to `2025-03-31`
- Five-minute intraday dry-run validation for the previous weekday by default
- Normalization through `GrowwHistoricalProvider`
- Validation through `HistoricalIngestionService`

It does not:

- Place orders
- Persist rows
- Apply database migrations
- Download the full instrument universe
- Print credentials or access tokens
