# InterSignal Portfolio OS accounting v1

## Transaction ledger

Transactions are immutable and append-only. Corrections must be represented by a new `REVERSAL` or `ADJUSTMENT` record with correction linkage in the external reference or metadata; existing transactions are not edited or deleted.

The supported transaction vocabulary is `BUY`, `SELL`, `DIVIDEND`, `INTEREST`, `FEE`, `TAX`, `DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, `TRANSFER_OUT`, `CORPORATE_ACTION`, `ADJUSTMENT`, and `REVERSAL`. Cash follows a signed net-flow convention: inflows are positive; buys and other outflows are negative. For buys, net cash is `-(gross + fees + taxes)`; for sells it is `gross - fees - taxes`.

The cash ledger orders records by trade date, settlement date, and transaction ID, then sums `net_amount` by currency and account. A recorded latest cash balance reconciles to the corresponding account ledger. Cash events such as deposits, withdrawals, dividends, fees, taxes, and transfers are therefore represented without provider-specific behavior.

## FIFO lots

The initial lot policy is deterministic FIFO. Eligible buys and sells are ordered by trade date, settlement date, and transaction ID. Each buy opens a lot whose all-in unit entry price includes buy fees and taxes. A sell consumes the oldest available units first. Sell proceeds are net of sell fees and taxes.

Realized P&L is:

`net sell proceeds - FIFO cost basis consumed`

Selling more than the available position raises `InsufficientPosition`. No short sale is inferred. Tax-lot optimization is intentionally absent.

Remaining lots are aggregated by account and security. Holding cost basis is the sum of remaining lot cost bases, average cost is cost basis divided by remaining quantity, market value is quantity times current price, and unrealized P&L is:

`market value - remaining cost basis`

The rebuild requires an explicit current price for every open security. This makes the output deterministic and prevents hidden live-market access.

## Valuation and reconciliation

Portfolio net liquidation value is `gross market value + cash`. Total P&L is `realized P&L + unrealized P&L`. Reconciliation checks recorded cash against the transaction ledger, non-negative/missing positions, transaction references and dates, lot-to-holding cost basis, and valuation components against the latest holdings and cash.

All arithmetic uses `Decimal`. Tiny equality checks use a fixed decimal tolerance only where aggregate comparison is necessary.

## Currency policy

Every account, transaction, security, holding, cash balance, valuation, benchmark, attribution, and goal carries an explicit currency. The domain accepts multi-currency state, and exposure/reconciliation emits `FX_CONVERSION_REQUIRED` when currencies differ from the portfolio base currency. A base-currency valuation is rejected while conversion would be required because v1 has no FX engine.

## Corporate actions and mutual funds

Corporate actions may be represented as transactions/events with the stable placeholders `SPLIT`, `BONUS`, `DIVIDEND`, `RIGHTS`, and `MERGER_DEMERGER_ADJUSTMENT`. V1 does not transform lots for those actions.

Mutual funds use the same security, transaction, lot, holding, cash, and valuation abstractions as other long-only instruments. This is sufficient for manual units, NAV marks, and FIFO disposal. SIP scheduling and provider-specific fund processing are outside this command.

## Known limitations

There is no FX conversion, shorting, derivatives accounting, wash-sale/tax optimizer, automated corporate-action adjustment, SIP scheduler, live pricing, broker sync, or order placement. The simple attribution method is descriptive and does not attempt causal or factor attribution.
