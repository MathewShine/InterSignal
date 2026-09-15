# InterSignal Family G benchmark-prehistory remediation V1

Step 03.07 / Command 02 is benchmark-infrastructure remediation only. Command 01 stopped with `READY_WITH_LIMITATIONS` and `METHODOLOGY_FIX_REQUIRED` because the frozen local NIFTY 500 benchmark began on 2021-09-07. That supplied only 141 causal benchmark sessions through the first Family G rebalance on 2022-03-31, short of the required 200.

The remediation does not shorten SMA200, drop the first quarter, guess its regime, substitute NIFTY 50, synthesize a current-constituent proxy, or mutate the existing benchmark. It creates `NIFTY500_BENCHMARK_PREHISTORY_V1` as a separate extension layer.

## Source and request method

The extension uses the same approved official source semantics as Command 01: NIFTY 500 records from the NSE historical index-data endpoint `https://www.nseindia.com/api/historicalOR/indicesHistory`, whose project source page is `https://www.nseindia.com/reports-indices-historical-index-data`.

The existing `DAILY_HISTORY_PREHISTORY_V2` official NSE bhavcopy evidence supplies the pre-2021-09-07 session calendar. It identifies 2021-06-14 as the exact start needed for the missing 59 sessions. A deterministic 15-valid-session safety buffer sets the requested start to 2021-05-24. Retrieval ends on 2021-09-17 to provide a narrow overlap with the frozen benchmark.

Each normalized extension row must identify NIFTY 500, contain a positive numeric close, be supported by an official NSE cash-market session, and have no unresolved duplicate. Weekends and official-source gaps are not counted or fabricated. Raw official payloads, OHLC fields, source identity, request metadata, source file, and normalization version are retained in the versioned extension.

## Reconciliation and structural result

Overlapping dates are compared by date, identity, OHLC, and close. Each row is classified as `EXACT_MATCH`, `SOURCE_EQUIVALENT`, `EXPLAINED_DIFFERENCE`, or `UNEXPLAINED_DIFFERENCE`. Any material unexplained difference blocks readiness promotion.

The official retrieval produced 82 unique valid raw rows across two request windows. Seventy-four rows precede the frozen 2021-09-07 boundary and form the normalized extension; eight rows from 2021-09-07 through 2021-09-17 form the overlap sample. All eight overlap rows are exact OHLC matches, with no explained or unexplained differences. The frozen existing benchmark file remains byte-identical.

For every frozen Family G rebalance, SMA200 remains the simple mean of the latest 200 valid NIFTY 500 sessions including T and using no future data. The unchanged rule is strictly `market_close[T] > market_sma200[T]`; equality holds cash. Pass-date treatment holdings must equal the frozen Family A control holdings, fail dates must hold zero equities, and the decision remains unchanged until the next quarterly rebalance.

The combined calendar explicitly reconciles the official NIFTY 500 row on the 2021-11-04 Muhurat special session, which the standard bhavcopy calendar had marked unknown. That official special session is valid and is not fabricated. With it, the extension provides 215 valid causal sessions through 2022-03-31. The first-rebalance NIFTY 500 close is 14894.5 and its exact SMA200 is 14636.07325, so the strict gate passes. All 11 frozen rebalances now have SMA200: nine pass and two fail. The yearly pass/fail counts are 3/1 for 2022, 3/1 for 2023, and 3/0 for 2024. Pass-date holding identity is 9/9, fail-date zero-equity state is 2/2, and the quarterly-only decision invariant passes.

The post-remediation classifications are `FAMILY_G_DATA_READINESS = READY`, `FAMILY_G_ARCHITECTURE_RESULT = READY_FOR_DEVELOPMENT_BACKTEST`, and `FAMILY_G_DEVELOPMENT_BACKTEST_READINESS = YES`. These classifications authorize no performance by themselves; a DEVELOPMENT backtest still requires a separate command.

This command calculates no portfolio return, CAGR, drawdown, Sharpe-like measure, quarter return, treatment advantage, or ending equity. It accesses no validation data and creates no Strategy V2. Development readiness is granted only if all 11 causal SMA200 values are available, overlap is clean, all structural invariants pass, and the frozen Family G and Family A inputs remain unchanged.
