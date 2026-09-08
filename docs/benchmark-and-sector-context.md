# Benchmark And Sector Context

Current phase: Step 02.4 / Command 02 - official benchmark and sector relative-strength foundation

## Status

- Benchmark context version: BENCHMARK_CONTEXT_V1
- Sector context version: SECTOR_CONTEXT_V1
- Feature version decision: DAILY_FEATURES_V1 retained with context-version metadata.
- Full feature regeneration completed: True
- Ready for review: True

## Official Sources

- Official NSE historical index data endpoint: https://www.nseindia.com/api/historicalOR/indicesHistory
- Official NSE historical index page: https://www.nseindia.com/reports-indices-historical-index-data
- Official NSE live index inventory endpoint: https://www.nseindia.com/api/allIndices
- Current official Nifty 500 constituent CSV: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv

## Formulas And Timing

- benchmark_return_Nd = index_close_T / index_close_T-N - 1.
- relative_return_Nd_vs_nifty500 = adjusted_stock_return_Nd - NIFTY_500_return_Nd.
- relative_return_Nd_vs_sector = adjusted_stock_return_Nd - sector_index_return_Nd when mapping is approved for T.
- All benchmark and sector features are DAILY_EOD and become NEXT_SESSION_DECISION_INPUT for the next session.
- Missing official index sessions are not forward-filled.
- Corporate-action blocked stock windows also block benchmark and sector relative returns.

## Benchmark Coverage

- NIFTY_50 (NIFTY 50): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage
- NIFTY_500 (NIFTY 500): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage

## Sector Index Coverage

- NIFTY500_HEALTHCARE (NIFTY500 HEALTHCARE): 2025-11-07 to 2026-09-07, 207/1240 sessions, 1033 missing, 16.6935% coverage, usable=True
- NIFTY_AUTO (NIFTY AUTO): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_BANK (NIFTY BANK): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_CAPITAL_GOODS (NIFTY CAPITAL GOODS):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_CEMENT (NIFTY CEMENT): 2026-02-17 to 2026-09-07, 137/1240 sessions, 1103 missing, 11.0484% coverage, usable=True
- NIFTY_CHEMICALS (NIFTY CHEMICALS): 2025-03-11 to 2026-09-07, 369/1240 sessions, 871 missing, 29.7581% coverage, usable=True
- NIFTY_COMMERCIAL_AND_TRANSPORT_SERVICES (NIFTY COMMERCIAL & TRANSPORT SERVICES):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_CONSTRUCTION (NIFTY CONSTRUCTION):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_CONSUMER_DURABLES (NIFTY CONSUMER DURABLES): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_CONSUMER_SERVICES (NIFTY CONSUMER SERVICES):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_FINANCIAL_SERVICES (NIFTY FINANCIAL SERVICES): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_FINANCIAL_SERVICES_25_50 (NIFTY FINANCIAL SERVICES 25/50): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_FINANCIAL_SERVICES_EX_BANK (NIFTY FINANCIAL SERVICES EX-BANK): 2024-12-16 to 2026-09-07, 429/1240 sessions, 811 missing, 34.5968% coverage, usable=True
- NIFTY_FMCG (NIFTY FMCG): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_HEALTHCARE_INDEX (NIFTY HEALTHCARE INDEX): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_HOSPITALS (NIFTY HOSPITALS):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_HOUSING_FINANCE (NIFTY HOUSING FINANCE):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_INSURANCE (NIFTY INSURANCE):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_IT (NIFTY IT): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_MEDIA (NIFTY MEDIA): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_METAL (NIFTY METAL): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_MIDSMALL_FINANCIAL_SERVICES (NIFTY MIDSMALL FINANCIAL SERVICES): 2024-12-16 to 2026-09-07, 429/1240 sessions, 811 missing, 34.5968% coverage, usable=True
- NIFTY_MIDSMALL_HEALTHCARE (NIFTY MIDSMALL HEALTHCARE): 2024-04-08 to 2026-09-07, 600/1240 sessions, 640 missing, 48.3871% coverage, usable=True
- NIFTY_MIDSMALL_IT_AND_TELECOM (NIFTY MIDSMALL IT & TELECOM): 2024-12-16 to 2026-09-07, 429/1240 sessions, 811 missing, 34.5968% coverage, usable=True
- NIFTY_NBFC (NIFTY NBFC):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_OIL_AND_GAS (NIFTY OIL & GAS): 2021-09-07 to 2026-09-07, 1232/1240 sessions, 8 missing, 99.3548% coverage, usable=True
- NIFTY_PHARMA (NIFTY PHARMA): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_POWER (NIFTY POWER):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_PRIVATE_BANK (NIFTY PRIVATE BANK): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_PSU_BANK (NIFTY PSU BANK): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_REALTY (NIFTY REALTY): 2021-09-07 to 2026-09-07, 1239/1240 sessions, 1 missing, 99.9194% coverage, usable=True
- NIFTY_REITS_AND_REALTY (NIFTY REITS & REALTY): 2026-05-11 to 2026-09-07, 84/1240 sessions, 1156 missing, 6.7742% coverage, usable=True
- NIFTY_RETAIL (NIFTY RETAIL):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False
- NIFTY_TELECOMMUNICATIONS (NIFTY TELECOMMUNICATIONS):  to , 0/1240 sessions, 1240 missing, 0.0000% coverage, usable=False

## Stock-Sector Mapping

- Mapping policy: Only POINT_IN_TIME_VERIFIED and INFERRED_WITH_EVIDENCE mappings are eligible for sector-relative features.
- POINT_IN_TIME_VERIFIED and INFERRED_WITH_EVIDENCE are eligible for sector-relative features.
- CURRENT_ONLY is not projected backward and produces null sector-relative fields.
- Generated rows with CURRENT_ONLY: 448517
- Generated rows with UNAVAILABLE: 149407

## Regenerated Feature Coverage

- Total feature rows: 597924
- Benchmark-relative rows available: 569087 (95.1771%)
- Sector-relative rows available: 0 (0.0000%)
- 5-session relative-strength usable: 98.6227%
- 20-session relative-strength usable: 95.1771%

## Known Limitations

- Historical Nifty 500 membership remains PARTIAL_HISTORY.
- Public point-in-time stock-sector membership archives were not available inside this command scope.
- No strategy scores, candidate selection, labels, backtests, orders, remote migrations, or Supabase bulk writes are performed.
