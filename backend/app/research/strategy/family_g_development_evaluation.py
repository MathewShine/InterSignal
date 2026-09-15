from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_development_backtest import (
    COST_COMPONENTS,
    RebalanceSchedule,
    _cost_for_mode,
    _flatten_order_cost,
    _maximum_affordable_quantity,
    _period_row,
    _percent,
    _record_period_positions,
    _valuation,
    load_rebalance_schedules,
    summarize_simulation,
    validate_development_date,
    yearly_results,
)
from app.research.strategy.family_a_momentum import (
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_a_phase2_development_evaluation import (
    _load_market,
)
from app.research.strategy.family_g_benchmark_prehistory import (
    EXPECTED_NORMALIZED_HASH,
    EXPECTED_OVERLAP_HASH,
    EXPECTED_POST_READINESS_HASH,
    EXPECTED_RAW_HASH,
    EXPECTED_REGIME_MATRIX_HASH,
    EXPECTED_REMEDIATION_CONFIG_HASH,
    FROZEN_REBALANCE_DATES,
    verify_command_01,
)
from app.research.strategy.family_g_regime_volatility import (
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_FAMILY_F_CLOSURE_HASH,
    EXPECTED_FAMILY_G_CONFIG_HASH,
    EXPECTED_GOVERNANCE_V2_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    EXPECTED_TREATMENT_PARAMETER_HASH,
    EXPECTED_TREATMENT_PREREGISTRATION_HASH,
    FAMILY_A_IMPLEMENTATION_EVIDENCE,
    FAMILY_A_REFERENCE_EXPERIMENT,
    FAMILY_VERSION,
    MARKET_INDEX_ID,
    MARKET_INDEX_NAME,
    SMA_WINDOW,
    STARTING_CAPITAL,
    TREATMENT_ID,
    verify_family_a_reference,
    verify_family_f_closure,
    verify_governance_v2,
)


COMMAND = "Step 03.07 / Command 03"
COMMAND_VERSION = "FAMILY_G_DEVELOPMENT_EVALUATION_V1"
COMMAND_PROFILE = "QUARTERLY_REGIME_PARTICIPATION_DEVELOPMENT_V1"
MANIFEST_VERSION = "FAMILY_G_DEVELOPMENT_EVALUATION_MANIFEST_V1"
REGISTRY_VERSION = "FAMILY_G_DEVELOPMENT_REGISTRY_V1"
CONTROL_MODE = "EXECUTABLE_INTEGER_SHARE_500K"
TREATMENT_MODE = "EXECUTABLE_INTEGER_SHARE_500K_QUARTERLY_REGIME_GATE"

EXPECTED_PREHISTORY_MANIFEST_HASH = (
    "bb60b53448b8148ff8c14422c25dcf24e4acac2919013cd3d22402952c932a96"
)

CONTROL_REFERENCE = {
    "starting_equity": Decimal("500000"),
    "net_ending_equity": Decimal("955331.68"),
    "net_total_return_pct": Decimal("91.07"),
    "net_cagr_pct": Decimal("24.11"),
    "net_max_drawdown_pct": Decimal("22.92"),
}
CONTROL_TOLERANCE = {
    "net_ending_equity": Decimal("5"),
    "net_total_return_pct": Decimal("0.01"),
    "net_cagr_pct": Decimal("0.01"),
    "net_max_drawdown_pct": Decimal("0.05"),
}

REPORT_NAMES = (
    "family_g_dev_v1_summary.json",
    "family_g_dev_v1_control.csv",
    "family_g_dev_v1_g001.csv",
    "family_g_dev_v1_quarterly.csv",
    "family_g_dev_v1_yearly.csv",
    "family_g_dev_v1_criteria.csv",
    "family_g_dev_v1_cash_quarter_attribution.csv",
    "family_g_dev_v1_path_effect.csv",
    "family_g_dev_v1_drawdown.csv",
    "family_g_dev_v1_cost_turnover.csv",
    "family_g_dev_v1_comparison.csv",
)


class FamilyGDevelopmentInputMismatch(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return (
        Path(root)
        / "data/research/strategy_families/family_g/v1/development_evaluation"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash(
        {key: value for key, value in document.items() if key != hash_field}
    )


def _input_mismatch(reason: str) -> None:
    raise FamilyGDevelopmentInputMismatch(
        f"FAMILY_G_DEVELOPMENT_INPUT_MISMATCH: {reason}"
    )


def _prehistory_manifest_path(root: Path) -> Path:
    return (
        Path(root)
        / "data/research/strategy_families/family_g/v1/benchmark_prehistory/"
        "manifests/family_g_benchmark_prehistory_manifest_v1.json"
    )


def command_02_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest_path = _prehistory_manifest_path(root)
    manifest = _read_json(manifest_path)
    relative_paths = list(manifest.get("artifact_hashes", {}))
    relative_paths.append(manifest_path.relative_to(root).as_posix())
    hashes = {
        relative: file_sha256(root / relative)
        for relative in sorted(relative_paths)
    }
    semantic = {
        "manifest_canonical_hash": manifest.get(
            "family_g_benchmark_prehistory_manifest_hash"
        ),
        "generated_hashes": manifest.get("generated_hashes"),
        "artifact_hashes": hashes,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def verify_freeze_gate(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    try:
        command_01 = verify_command_01(root)
        family_f = verify_family_f_closure(root)
        governance = verify_governance_v2(root)
        family_a = verify_family_a_reference(root)
        manifest = _read_json(_prehistory_manifest_path(root))
        prehistory_summary = _read_json(
            root / "data/reports/family_g_prehistory_v1_summary.json"
        )
        a2_result = _read_json(
            root
            / "data/research/strategy_families/family_a/v1/phase2/"
            "development_evaluation/a2_002/development_result_v1.json"
        )
        expected_generated = {
            "family_g_prehistory_remediation_config_hash": (
                EXPECTED_REMEDIATION_CONFIG_HASH
            ),
            "nifty500_prehistory_raw_hash": EXPECTED_RAW_HASH,
            "nifty500_prehistory_normalized_hash": EXPECTED_NORMALIZED_HASH,
            "nifty500_overlap_reconciliation_hash": EXPECTED_OVERLAP_HASH,
            "family_g_regime_matrix_hash": EXPECTED_REGIME_MATRIX_HASH,
            "family_g_post_remediation_readiness_hash": (
                EXPECTED_POST_READINESS_HASH
            ),
        }
        expected_family_g = {
            "family_g_config_hash": EXPECTED_FAMILY_G_CONFIG_HASH,
            "control_g_000_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "regime_g_001_parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
            "regime_g_001_preregistration_hash": (
                EXPECTED_TREATMENT_PREREGISTRATION_HASH
            ),
            "family_g_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        }
        checks = {
            "family_g_frozen_hashes": (
                command_01.get("frozen_hashes") == expected_family_g
            ),
            "governance_policy_hash": (
                governance.get("governance_policy_hash")
                == EXPECTED_GOVERNANCE_V2_HASH
            ),
            "family_f_closure_hash": (
                family_f.get("family_f_closure_hash")
                == EXPECTED_FAMILY_F_CLOSURE_HASH
            ),
            "family_a_reference": family_a.get("status") == "VERIFIED",
            "a2_002_result_hash": (
                a2_result.get("development_result_hash")
                == EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH
                and _document_hash(a2_result, "development_result_hash")
                == EXPECTED_A2_002_DEVELOPMENT_RESULT_HASH
            ),
            "prehistory_manifest_hash": (
                manifest.get("family_g_benchmark_prehistory_manifest_hash")
                == EXPECTED_PREHISTORY_MANIFEST_HASH
                and _document_hash(
                    manifest, "family_g_benchmark_prehistory_manifest_hash"
                )
                == EXPECTED_PREHISTORY_MANIFEST_HASH
            ),
            "prehistory_generated_hashes": (
                manifest.get("generated_hashes") == expected_generated
            ),
            "prehistory_artifacts": all(
                (root / relative).is_file()
                and file_sha256(root / relative) == expected
                for relative, expected in manifest.get(
                    "artifact_hashes", {}
                ).items()
            ),
            "prehistory_ready": (
                prehistory_summary.get("classifications", {}).get(
                    "FAMILY_G_DEVELOPMENT_BACKTEST_READINESS"
                )
                == "YES"
            ),
            "prehistory_no_performance": (
                prehistory_summary.get("governance", {}).get(
                    "development_performance_run"
                )
                is False
            ),
            "prehistory_no_validation": (
                prehistory_summary.get("governance", {}).get(
                    "validation_accessed"
                )
                is False
            ),
            "benchmark_identity": (
                prehistory_summary.get("benchmark", {}).get("index_id")
                == MARKET_INDEX_ID
                and prehistory_summary.get("benchmark", {}).get("index_name")
                == MARKET_INDEX_NAME
                and prehistory_summary.get("immutability", {}).get(
                    "benchmark_changed"
                )
                is False
            ),
        }
        if not all(checks.values()):
            _input_mismatch(str(checks))
        return {
            "status": "VERIFIED",
            "checks": checks,
            "family_g_hashes": expected_family_g,
            "governance_policy_hash": EXPECTED_GOVERNANCE_V2_HASH,
            "prehistory_hashes": expected_generated,
            "prehistory_manifest_hash": EXPECTED_PREHISTORY_MANIFEST_HASH,
            "family_f_closure_hash": EXPECTED_FAMILY_F_CLOSURE_HASH,
            "family_a_reference": {
                "status": family_a["status"],
                "checks": family_a["checks"],
                "phase2_config_hash": family_a["phase2_config"][
                    "phase2_config_hash"
                ],
                "a2_002_parameter_hash": family_a["preregistration"][
                    "parameter_hash"
                ],
                "a2_002_preregistration_hash": family_a["preregistration"][
                    "preregistration_hash"
                ],
                "a2_002_development_result_hash": family_a["result"][
                    "development_result_hash"
                ],
            },
        }
    except FamilyGDevelopmentInputMismatch:
        raise
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        _input_mismatch(str(error))


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).lower() == "true":
        return True
    if str(value).lower() == "false":
        return False
    raise ValueError(f"Expected boolean value, received {value!r}")


def _control_simulation(root: Path) -> dict[str, Any]:
    base = (
        Path(root)
        / "data/research/strategy_families/family_a/v1/phase2/"
        "development_evaluation/a2_002"
    )

    def rows(name: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in read_csv(base / name):
            converted: dict[str, Any] = {**row, "experiment_id": CONTROL_ID}
            if name == "periods.csv":
                for field in (
                    "positive_gross_period",
                    "positive_net_period",
                    "final_partial_period",
                ):
                    converted[field] = _bool(converted[field])
            elif name == "position_returns.csv":
                for field in ("positive_position", "final_partial_period"):
                    converted[field] = _bool(converted[field])
            output.append(converted)
        return output

    return {
        "experiment_id": CONTROL_ID,
        "mode": CONTROL_MODE,
        "daily": rows("daily.csv"),
        "rebalances": rows("rebalances.csv"),
        "holdings": rows("holdings.csv"),
        "costs": rows("costs.csv"),
        "periods": rows("periods.csv"),
        "position_returns": rows("position_returns.csv"),
        "cash_reconciliation_violations": 0,
        "equity_reconciliation_violations": 0,
        "cost_model_status": "FULL_FROZEN_COST_MODEL",
    }


def _gate_rows(root: Path) -> list[dict[str, Any]]:
    document = _read_json(
        Path(root)
        / "data/research/strategy_families/family_g/v1/benchmark_prehistory/"
        "regime_matrix/family_g_regime_matrix_v1.json"
    )
    if document.get("family_g_regime_matrix_hash") != EXPECTED_REGIME_MATRIX_HASH:
        _input_mismatch("Command 02 regime matrix hash changed")
    rows = document.get("rows", [])
    if tuple(str(row["rebalance_date"]) for row in rows) != FROZEN_REBALANCE_DATES:
        _input_mismatch("frozen rebalance dates changed")
    if sum(row.get("gate_pass") is True for row in rows) != 9:
        _input_mismatch("frozen gate-pass count changed")
    if sum(row.get("gate_pass") is False for row in rows) != 2:
        _input_mismatch("frozen gate-fail count changed")
    return rows


def _selected_symbol_identity(
    schedules: Sequence[RebalanceSchedule],
    gate_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    schedule_by_date = {
        row.formation_date.isoformat(): row for row in schedules
    }
    output: list[dict[str, Any]] = []
    for gate in gate_rows:
        schedule = schedule_by_date[str(gate["rebalance_date"])]
        control = {selected.symbol for selected in schedule.selected}
        treatment = set(control) if gate["gate_pass"] else set()
        union = control | treatment
        jaccard = (
            Decimal(len(control & treatment)) / Decimal(len(union))
            if union
            else Decimal("1")
        )
        output.append(
            {
                "rebalance_date": gate["rebalance_date"],
                "execution_date": gate["execution_date"],
                "gate_pass": gate["gate_pass"],
                "control_selected_count": len(control),
                "treatment_selected_count_before_sizing": len(treatment),
                "jaccard_before_sizing": jaccard,
                "input_holdings_identical": (
                    jaccard == Decimal("1") if gate["gate_pass"] else True
                ),
            }
        )
    return output


def _control_holdings_integrity(
    control: Mapping[str, Any], gate_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in control["holdings"]:
        grouped[str(row["execution_date"])].append(
            {"symbol": row["symbol"], "quantity": int(row["quantity"])}
        )
    checks: list[dict[str, Any]] = []
    for gate in gate_rows:
        positions = sorted(
            grouped[str(gate["execution_date"])], key=lambda row: row["symbol"]
        )
        observed = canonical_hash(positions)
        expected = str(gate["control_holdings_hash"])
        checks.append(
            {
                "rebalance_date": gate["rebalance_date"],
                "execution_date": gate["execution_date"],
                "observed_hash": observed,
                "expected_hash": expected,
                "matches": observed == expected,
            }
        )
    return {
        "status": "PASS" if all(row["matches"] for row in checks) else "FAIL",
        "matched_rebalances": sum(row["matches"] for row in checks),
        "total_rebalances": len(checks),
        "checks": checks,
    }


def _realized_holding_overlap(
    identity_rows: Sequence[Mapping[str, Any]],
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    control_by_date: dict[str, set[str]] = defaultdict(set)
    treatment_by_date: dict[str, set[str]] = defaultdict(set)
    for row in control["holdings"]:
        control_by_date[str(row["execution_date"])].add(str(row["symbol"]))
    for row in treatment["holdings"]:
        treatment_by_date[str(row["execution_date"])].add(str(row["symbol"]))
    output: list[dict[str, Any]] = []
    for source in identity_rows:
        row = dict(source)
        execution = str(row["execution_date"])
        control_symbols = control_by_date[execution]
        treatment_symbols = treatment_by_date[execution]
        union = control_symbols | treatment_symbols
        row["realized_symbol_jaccard"] = (
            Decimal(len(control_symbols & treatment_symbols))
            / Decimal(len(union))
            if union
            else Decimal("1")
        )
        row["realized_symbol_divergence"] = sorted(
            control_symbols ^ treatment_symbols
        )
        output.append(row)
    return output


def simulate_treatment(
    schedules: Sequence[RebalanceSchedule],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, Any]],
    gate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validate_development_date(sessions[0])
    validate_development_date(sessions[-1])
    gate_by_execution = {
        date.fromisoformat(str(row["execution_date"])): bool(row["gate_pass"])
        for row in gate_rows
    }
    schedule_by_date = {row.execution_date: row for row in schedules}
    if set(gate_by_execution) != set(schedule_by_date):
        _input_mismatch("gate and Family A execution schedules differ")

    holdings: dict[str, int] = {}
    cash = decimal(STARTING_CAPITAL)
    cumulative_cost = Decimal("0")
    last_prices: dict[str, Decimal] = {}
    daily: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    periods: list[dict[str, Any]] = []
    position_returns: list[dict[str, Any]] = []
    period_start_date: date | None = None
    period_start_gross: Decimal | None = None
    period_start_net: Decimal | None = None
    period_positions: dict[str, tuple[Decimal, Decimal]] = {}
    current_state = "PRE_FIRST_REBALANCE_CASH"
    current_gate: bool | None = None
    cash_reconciliation_violations = 0
    equity_reconciliation_violations = 0

    for value_date in sessions:
        schedule = schedule_by_date.get(value_date)
        if schedule is not None:
            gate_pass = gate_by_execution[value_date]
            current_gate = gate_pass
            decimal_holdings = {
                key: Decimal(value) for key, value in holdings.items()
            }
            holdings_value, valuation_prices, missing_valuation = _valuation(
                decimal_holdings, value_date, bars, last_prices, use_open=True
            )
            if missing_valuation:
                raise ValueError(
                    f"Missing treatment open valuation on {value_date}: "
                    f"{missing_valuation}"
                )
            net_pre = cash + holdings_value
            gross_pre = net_pre + cumulative_cost
            if (
                period_start_date is not None
                and period_start_gross is not None
                and period_start_net is not None
            ):
                periods.append(
                    _period_row(
                        experiment_id=TREATMENT_ID,
                        mode=TREATMENT_MODE,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_gross=period_start_gross,
                        end_gross=gross_pre,
                        start_net=period_start_net,
                        end_net=net_pre,
                        final_partial=False,
                    )
                )
                position_returns.extend(
                    _record_period_positions(
                        experiment_id=TREATMENT_ID,
                        mode=TREATMENT_MODE,
                        start_date=period_start_date,
                        end_date=value_date,
                        start_positions=period_positions,
                        end_prices=valuation_prices,
                        final_partial=False,
                    )
                )

            before_symbols = {
                symbol for symbol, quantity in holdings.items() if quantity > 0
            }
            selected = schedule.selected if gate_pass else ()
            selected_symbols = {row.symbol for row in selected}
            retained = before_symbols & selected_symbols
            added = selected_symbols - before_symbols
            removed = before_symbols - selected_symbols
            start_cash = cash
            sale_proceeds = Decimal("0")
            sell_costs = Decimal("0")
            buy_notional = Decimal("0")
            buy_costs = Decimal("0")
            sell_notional = Decimal("0")
            actual_execution_prices = {
                symbol: bar.open_price
                for symbol, bar in bars.get(value_date, {}).items()
                if bar.open_price > 0
            }
            if gate_pass:
                if not schedule.sufficient_universe or not selected:
                    raise ValueError(
                        f"Gate-pass schedule unavailable on {value_date}"
                    )
                target_amount = net_pre / Decimal(len(selected))
                desired_targets = {
                    row.symbol: int(
                        (
                            target_amount / actual_execution_prices[row.symbol]
                        ).to_integral_value(rounding=ROUND_FLOOR)
                    )
                    for row in selected
                    if row.symbol in actual_execution_prices
                }
                if len(desired_targets) != len(selected):
                    raise ValueError(
                        f"Missing selected next-open price on {value_date}"
                    )
                current_state = "INVESTED"
            else:
                desired_targets = {}
                current_state = "CASH"

            for symbol in sorted(set(holdings) | set(desired_targets)):
                current = holdings.get(symbol, 0)
                target = desired_targets.get(symbol, 0)
                if target >= current:
                    continue
                price = actual_execution_prices.get(symbol)
                if price is None:
                    raise ValueError(
                        f"Missing liquidation open for {symbol} on {value_date}"
                    )
                quantity = current - target
                notional = Decimal(quantity) * price
                cost = _cost_for_mode(
                    "SELL", value_date, notional, TREATMENT_MODE
                )
                applied = decimal(cost["applied_total_cost"])
                cash += notional - applied
                holdings[symbol] = target
                if target == 0:
                    holdings.pop(symbol, None)
                sale_proceeds += notional
                sell_notional += notional
                sell_costs += applied
                cumulative_cost += applied
                cost_rows.append(
                    _flatten_order_cost(
                        experiment_id=TREATMENT_ID,
                        mode=TREATMENT_MODE,
                        execution_date=value_date,
                        symbol=symbol,
                        side="SELL",
                        quantity=Decimal(quantity),
                        price=price,
                        cost=cost,
                    )
                )

            rank_lookup = {row.symbol: row.rank for row in selected}
            for symbol in sorted(
                desired_targets,
                key=lambda item: (rank_lookup.get(item, 10**9), item),
            ):
                current = holdings.get(symbol, 0)
                desired = desired_targets[symbol]
                if desired <= current:
                    continue
                price = actual_execution_prices[symbol]
                quantity = _maximum_affordable_quantity(
                    desired - current, price, cash, value_date
                )
                if quantity <= 0:
                    continue
                notional = Decimal(quantity) * price
                cost = _cost_for_mode(
                    "BUY", value_date, notional, TREATMENT_MODE
                )
                applied = decimal(cost["applied_total_cost"])
                required = notional + applied
                if required > cash + Decimal("0.000001"):
                    raise ValueError("Treatment purchase exceeds available cash")
                cash -= required
                holdings[symbol] = current + quantity
                buy_notional += notional
                buy_costs += applied
                cumulative_cost += applied
                cost_rows.append(
                    _flatten_order_cost(
                        experiment_id=TREATMENT_ID,
                        mode=TREATMENT_MODE,
                        execution_date=value_date,
                        symbol=symbol,
                        side="BUY",
                        quantity=Decimal(quantity),
                        price=price,
                        cost=cost,
                    )
                )

            expected_cash = (
                start_cash
                + sale_proceeds
                - sell_costs
                - buy_notional
                - buy_costs
            )
            cash_mismatch = abs(cash - expected_cash)
            if cash_mismatch > Decimal("0.000001"):
                cash_reconciliation_violations += 1
            post_holdings = {
                key: Decimal(value)
                for key, value in holdings.items()
                if value > 0
            }
            post_value, post_prices, post_missing = _valuation(
                post_holdings, value_date, bars, last_prices, use_open=True
            )
            if post_missing:
                raise ValueError(
                    f"Missing post-rebalance valuation on {value_date}"
                )
            net_post = cash + post_value
            gross_post = net_post + cumulative_cost
            equity_mismatch = abs((cash + post_value) - net_post)
            if equity_mismatch > Decimal("0.000001"):
                equity_reconciliation_violations += 1
            actual_weights = {
                symbol: quantity * post_prices[symbol] / net_post
                for symbol, quantity in post_holdings.items()
                if symbol in post_prices and net_post
            }
            target_weight = (
                Decimal("1") / Decimal(len(selected)) if selected else Decimal("0")
            )
            tracking_l1 = sum(
                (
                    abs(actual_weights.get(symbol, Decimal("0")) - target_weight)
                    for symbol in selected_symbols
                ),
                Decimal("0"),
            )
            for symbol in sorted(actual_weights):
                holding_rows.append(
                    {
                        "experiment_id": TREATMENT_ID,
                        "mode": TREATMENT_MODE,
                        "execution_date": value_date.isoformat(),
                        "symbol": symbol,
                        "quantity": holdings[symbol],
                        "price": post_prices[symbol],
                        "market_value": Decimal(holdings[symbol])
                        * post_prices[symbol],
                        "actual_weight_pct": _percent(actual_weights[symbol]),
                        "cash_weight_pct": (
                            _percent(cash / net_post) if net_post else None
                        ),
                    }
                )
            largest = max(actual_weights.values(), default=Decimal("0"))
            top_five = sum(
                sorted(actual_weights.values(), reverse=True)[:5], Decimal("0")
            )
            turnover = (
                (buy_notional + sell_notional) / net_pre
                if net_pre
                else Decimal("0")
            )
            unaffordable = sum(
                holdings.get(row.symbol, 0) == 0 for row in selected
            )
            rebalances.append(
                {
                    "experiment_id": TREATMENT_ID,
                    "mode": TREATMENT_MODE,
                    "formation_date": schedule.formation_date.isoformat(),
                    "execution_date": value_date.isoformat(),
                    "status": (
                        "EXECUTED_GATE_PASS_INVESTED"
                        if gate_pass
                        else "EXECUTED_GATE_FAIL_CASH_ONLY"
                    ),
                    "gate_pass": gate_pass,
                    "treatment_state": current_state,
                    "eligible_count": schedule.eligible_count,
                    "intended_holdings": schedule.intended_count,
                    "selected_count": len(selected),
                    "actual_holdings": len(holdings),
                    "retained_count": len(retained),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "retention_rate_pct": (
                        _percent(
                            Decimal(len(retained)) / Decimal(len(before_symbols))
                        )
                        if before_symbols
                        else None
                    ),
                    "gross_buy_turnover": buy_notional,
                    "gross_sell_turnover": sell_notional,
                    "one_way_turnover": turnover,
                    "rebalance_cost": sell_costs + buy_costs,
                    "flat_delivery_cost_excluded": Decimal("0"),
                    "pre_rebalance_gross_equity": gross_pre,
                    "pre_rebalance_net_equity": net_pre,
                    "post_rebalance_gross_equity": gross_post,
                    "post_rebalance_net_equity": net_post,
                    "cash": cash,
                    "cash_residual_pct": (
                        _percent(cash / net_post) if net_post else None
                    ),
                    "unaffordable_names": unaffordable,
                    "largest_position_weight_pct": _percent(largest),
                    "top_five_weight_pct": _percent(top_five),
                    "tracking_difference_l1_pct": _percent(tracking_l1),
                    "missing_valuation_count": 0,
                    "deferred_missing_open_exits": 0,
                    "cash_reconciliation_mismatch": cash_mismatch,
                    "equity_reconciliation_mismatch": equity_mismatch,
                }
            )
            period_start_date = value_date
            period_start_gross = gross_post
            period_start_net = net_post
            period_positions = {
                symbol: (Decimal(quantity), post_prices[symbol])
                for symbol, quantity in holdings.items()
                if symbol in post_prices and quantity > 0
            }

        close_holdings = {
            key: Decimal(value) for key, value in holdings.items() if value > 0
        }
        close_value, close_prices, missing_close = _valuation(
            close_holdings, value_date, bars, last_prices, use_open=False
        )
        net_close = cash + close_value
        gross_close = net_close + cumulative_cost
        equity_mismatch = abs((cash + close_value) - net_close)
        if equity_mismatch > Decimal("0.000001"):
            equity_reconciliation_violations += 1
        daily.append(
            {
                "experiment_id": TREATMENT_ID,
                "mode": TREATMENT_MODE,
                "date": value_date.isoformat(),
                "gross_equity": gross_close,
                "net_equity": net_close,
                "cash": cash,
                "holdings_value": close_value,
                "holding_count": len(close_holdings),
                "cumulative_cost": cumulative_cost,
                "cumulative_flat_delivery_cost_excluded": Decimal("0"),
                "missing_close_valuation_count": len(missing_close),
                "equity_reconciliation_mismatch": equity_mismatch,
                "regime_state": current_state,
                "gate_pass": current_gate,
            }
        )
        for symbol, price in close_prices.items():
            last_prices[symbol] = price

    if (
        period_start_date is not None
        and period_start_gross is not None
        and period_start_net is not None
    ):
        final = daily[-1]
        periods.append(
            _period_row(
                experiment_id=TREATMENT_ID,
                mode=TREATMENT_MODE,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_gross=period_start_gross,
                end_gross=decimal(final["gross_equity"]),
                start_net=period_start_net,
                end_net=decimal(final["net_equity"]),
                final_partial=True,
            )
        )
        _, final_prices, _ = _valuation(
            close_holdings, sessions[-1], bars, last_prices, use_open=False
        )
        position_returns.extend(
            _record_period_positions(
                experiment_id=TREATMENT_ID,
                mode=TREATMENT_MODE,
                start_date=period_start_date,
                end_date=sessions[-1],
                start_positions=period_positions,
                end_prices=final_prices,
                final_partial=True,
            )
        )
    return {
        "experiment_id": TREATMENT_ID,
        "mode": TREATMENT_MODE,
        "daily": daily,
        "rebalances": rebalances,
        "holdings": holding_rows,
        "costs": cost_rows,
        "periods": periods,
        "position_returns": position_returns,
        "cash_reconciliation_violations": cash_reconciliation_violations,
        "equity_reconciliation_violations": equity_reconciliation_violations,
        "cost_model_status": "FULL_FROZEN_COST_MODEL",
    }


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _median(values: Sequence[Decimal]) -> Decimal | None:
    return decimal(statistics.median(values)) if values else None


def portfolio_metrics(simulation: Mapping[str, Any]) -> dict[str, Any]:
    analysis = summarize_simulation(
        simulation, starting_capital=STARTING_CAPITAL
    )
    summary = analysis["summary"]
    yearly = yearly_results(simulation, starting_capital=STARTING_CAPITAL)
    periods = simulation["periods"]
    quarter_returns = [decimal(row["net_period_return_pct"]) for row in periods]
    daily = simulation["daily"]
    return {
        **summary,
        "positive_quarter_rate_pct": (
            Decimal(sum(value > 0 for value in quarter_returns))
            / Decimal(len(quarter_returns))
            * Decimal("100")
        ),
        "quarter_interval_count": len(quarter_returns),
        "positive_quarter_rate_denominator": (
            "ALL_11_FROZEN_INTERVALS_INCLUDING_FINAL_PARTIAL"
        ),
        "positive_quarter_count": sum(value > 0 for value in quarter_returns),
        "negative_quarter_count": sum(value < 0 for value in quarter_returns),
        "flat_quarter_count": sum(value == 0 for value in quarter_returns),
        "median_quarter_return_pct": _median(quarter_returns),
        "worst_quarter_return_pct": min(quarter_returns),
        "best_quarter_return_pct": max(quarter_returns),
        "average_cash": _mean([decimal(row["cash"]) for row in daily]),
        "maximum_cash": max(decimal(row["cash"]) for row in daily),
        "average_invested_capital": _mean(
            [decimal(row["holdings_value"]) for row in daily]
        ),
        "average_holding_count": _mean(
            [Decimal(int(row["holding_count"])) for row in daily]
        ),
        "maximum_holding_count": max(int(row["holding_count"]) for row in daily),
        "yearly": yearly,
    }


def control_reproduction(
    metrics: Mapping[str, Any],
    holdings_integrity: Mapping[str, Any],
) -> dict[str, Any]:
    observed = {
        "starting_equity": decimal(metrics["starting_equity"]),
        "net_ending_equity": decimal(metrics["net_ending_equity"]),
        "net_total_return_pct": decimal(metrics["net_total_return_pct"]),
        "net_cagr_pct": decimal(metrics["net_cagr_pct"]),
        "net_max_drawdown_pct": abs(decimal(metrics["net_max_drawdown_pct"])),
    }
    differences = {
        key: abs(observed[key] - reference)
        for key, reference in CONTROL_REFERENCE.items()
    }
    checks = {
        "starting_equity_exact": differences["starting_equity"] == 0,
        "ending_equity_within_5_inr": (
            differences["net_ending_equity"]
            <= CONTROL_TOLERANCE["net_ending_equity"]
        ),
        "net_return_within_0_01pp": (
            differences["net_total_return_pct"]
            <= CONTROL_TOLERANCE["net_total_return_pct"]
        ),
        "net_cagr_within_0_01pp": (
            differences["net_cagr_pct"]
            <= CONTROL_TOLERANCE["net_cagr_pct"]
        ),
        "max_drawdown_within_0_05pp": (
            differences["net_max_drawdown_pct"]
            <= CONTROL_TOLERANCE["net_max_drawdown_pct"]
        ),
        "all_rebalance_holdings_match": (
            holdings_integrity["status"] == "PASS"
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "CONTROL_REPRODUCTION_FAILURE",
        "reference": CONTROL_REFERENCE,
        "observed": observed,
        "absolute_differences": differences,
        "tolerance": CONTROL_TOLERANCE,
        "checks": checks,
        "holdings_integrity": holdings_integrity,
    }


def quarterly_ledger(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    gate_rows: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    control_periods = {
        str(row["period_start"]): row for row in control["periods"]
    }
    treatment_periods = {
        str(row["period_start"]): row for row in treatment["periods"]
    }
    control_rebalances = {
        str(row["execution_date"]): row for row in control["rebalances"]
    }
    treatment_rebalances = {
        str(row["execution_date"]): row for row in treatment["rebalances"]
    }
    identity_by_date = {
        str(row["execution_date"]): row for row in identity_rows
    }
    output: list[dict[str, Any]] = []
    for gate in gate_rows:
        execution = str(gate["execution_date"])
        control_period = control_periods[execution]
        treatment_period = treatment_periods[execution]
        control_rebalance = control_rebalances[execution]
        treatment_rebalance = treatment_rebalances[execution]
        control_return = decimal(control_period["net_period_return_pct"])
        actual_treatment_return = decimal(
            treatment_period["net_period_return_pct"]
        )
        normalized_treatment_return = (
            control_return if gate["gate_pass"] else Decimal("0")
        )
        output.append(
            {
                "rebalance_date": gate["rebalance_date"],
                "execution_date": execution,
                "interval_end": treatment_period["period_end"],
                "gate_state": "PASS" if gate["gate_pass"] else "FAIL",
                "control_start_equity": control_rebalance[
                    "post_rebalance_net_equity"
                ],
                "control_end_equity": (
                    decimal(control_rebalance["post_rebalance_net_equity"])
                    + decimal(control_period["net_period_pnl"])
                ),
                "control_quarter_return_pct": control_return,
                "treatment_start_equity": treatment_rebalance[
                    "post_rebalance_net_equity"
                ],
                "treatment_end_equity": (
                    decimal(treatment_rebalance["post_rebalance_net_equity"])
                    + decimal(treatment_period["net_period_pnl"])
                ),
                "treatment_quarter_return_pct": actual_treatment_return,
                "control_turnover_x": control_rebalance["one_way_turnover"],
                "treatment_turnover_x": treatment_rebalance["one_way_turnover"],
                "control_costs": control_rebalance["rebalance_cost"],
                "treatment_costs": treatment_rebalance["rebalance_cost"],
                "treatment_state": (
                    "INVESTED" if gate["gate_pass"] else "CASH"
                ),
                "selected_holding_jaccard_before_sizing": identity_by_date[
                    execution
                ]["jaccard_before_sizing"],
                "normalized_control_return_pct": control_return,
                "normalized_treatment_return_pct": normalized_treatment_return,
                "direct_gate_effect_pp": (
                    normalized_treatment_return - control_return
                ),
                "capital_path_effect_pp": (
                    actual_treatment_return - normalized_treatment_return
                ),
            }
        )
    return output


def cash_quarter_attribution(
    ledger: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in ledger:
        if row["gate_state"] != "FAIL":
            continue
        control_return = decimal(row["control_quarter_return_pct"])
        classification = (
            "MISSED_GAIN"
            if control_return > 0
            else "AVOIDED_LOSS"
            if control_return < 0
            else "FLAT"
        )
        output.append(
            {
                "rebalance_date": row["rebalance_date"],
                "execution_date": row["execution_date"],
                "interval_end": row["interval_end"],
                "control_return_pct": control_return,
                "treatment_return_pct": row["treatment_quarter_return_pct"],
                "classification": classification,
            }
        )
    return output


def path_effect_summary(
    ledger: Sequence[Mapping[str, Any]],
    control_metrics: Mapping[str, Any],
    treatment_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_control = decimal(STARTING_CAPITAL)
    normalized_treatment = decimal(STARTING_CAPITAL)
    rows: list[dict[str, Any]] = []
    for row in ledger:
        normalized_control *= Decimal("1") + decimal(
            row["normalized_control_return_pct"]
        ) / Decimal("100")
        normalized_treatment *= Decimal("1") + decimal(
            row["normalized_treatment_return_pct"]
        ) / Decimal("100")
        rows.append(
            {
                "rebalance_date": row["rebalance_date"],
                "gate_state": row["gate_state"],
                "control_return_pct": row["control_quarter_return_pct"],
                "actual_treatment_return_pct": row[
                    "treatment_quarter_return_pct"
                ],
                "normalized_treatment_return_pct": row[
                    "normalized_treatment_return_pct"
                ],
                "direct_gate_effect_pp": row["direct_gate_effect_pp"],
                "capital_path_effect_pp": row["capital_path_effect_pp"],
                "normalized_control_index": normalized_control
                / decimal(STARTING_CAPITAL),
                "normalized_treatment_index": normalized_treatment
                / decimal(STARTING_CAPITAL),
            }
        )
    actual_gap = decimal(treatment_metrics["net_ending_equity"]) - decimal(
        control_metrics["net_ending_equity"]
    )
    direct_gap = normalized_treatment - normalized_control
    return {
        "rows": rows,
        "normalized_control_ending_equity": normalized_control,
        "normalized_treatment_ending_equity": normalized_treatment,
        "direct_gate_effect_rupees": direct_gap,
        "actual_treatment_minus_control_rupees": actual_gap,
        "capital_path_effect_rupees": actual_gap - direct_gap,
        "direct_gate_effect_summary": (
            "Gate-fail quarters replace the same-interval control return with "
            "0% cash return in the normalized diagnostic."
        ),
        "capital_path_effect_summary": (
            "After a skipped quarter, later pass-quarter differences arise only "
            "from changed capital, whole-share sizing, and the associated frozen "
            "transaction-cost path."
        ),
    }


def drawdown_episode(simulation: Mapping[str, Any]) -> dict[str, Any]:
    peak_value = decimal(STARTING_CAPITAL)
    peak_date = DEVELOPMENT_START.isoformat()
    maximum = Decimal("0")
    maximum_peak_date = peak_date
    trough_date = peak_date
    trough_peak_value = peak_value
    for row in simulation["daily"]:
        value = decimal(row["net_equity"])
        row_date = str(row["date"])
        if value > peak_value:
            peak_value = value
            peak_date = row_date
        drawdown = value / peak_value - Decimal("1") if peak_value else Decimal("0")
        if drawdown < maximum:
            maximum = drawdown
            maximum_peak_date = peak_date
            trough_date = row_date
            trough_peak_value = peak_value
    recovery_date = None
    for row in simulation["daily"]:
        if str(row["date"]) <= trough_date:
            continue
        if decimal(row["net_equity"]) >= trough_peak_value:
            recovery_date = str(row["date"])
            break
    return {
        "experiment_id": simulation["experiment_id"],
        "peak_date": maximum_peak_date,
        "trough_date": trough_date,
        "recovery_date": recovery_date,
        "max_drawdown_pct": maximum * Decimal("100"),
    }


def cash_utilization(
    treatment: Mapping[str, Any], gate_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    daily = treatment["daily"]
    full_cash = [row for row in daily if int(row["holding_count"]) == 0]
    fail_durations: list[dict[str, Any]] = []
    for index, gate in enumerate(gate_rows):
        if gate["gate_pass"]:
            continue
        start = str(gate["execution_date"])
        end = (
            str(gate_rows[index + 1]["execution_date"])
            if index + 1 < len(gate_rows)
            else (DEVELOPMENT_END.isoformat())
        )
        selected = [
            row for row in daily if start <= str(row["date"]) < end
        ]
        fail_durations.append(
            {
                "rebalance_date": gate["rebalance_date"],
                "execution_date": start,
                "next_execution_date": end,
                "cash_sessions": len(selected),
                "all_sessions_fully_cash": all(
                    int(row["holding_count"]) == 0 for row in selected
                ),
            }
        )
    gate_cash_sessions = sum(row["cash_sessions"] for row in fail_durations)
    gate_cash_rows = [row for row in daily if row["regime_state"] == "CASH"]
    return {
        "average_cash": _mean([decimal(row["cash"]) for row in daily]),
        "maximum_cash": max(decimal(row["cash"]) for row in daily),
        "maximum_gate_cash": max(
            (decimal(row["cash"]) for row in gate_cash_rows),
            default=Decimal("0"),
        ),
        "fully_cash_sessions_total": len(full_cash),
        "total_development_sessions": len(daily),
        "fraction_development_calendar_fully_cash": (
            Decimal(len(full_cash)) / Decimal(len(daily))
        ),
        "gate_caused_cash_sessions": gate_cash_sessions,
        "fraction_development_calendar_gate_cash": (
            Decimal(gate_cash_sessions) / Decimal(len(daily))
        ),
        "gate_fail_durations": fail_durations,
        "cash_return_pct": Decimal("0"),
    }


def accounting_integrity(
    treatment: Mapping[str, Any],
    gate_rows: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
    cash: Mapping[str, Any],
) -> dict[str, Any]:
    execution_dates = {str(row["execution_date"]) for row in gate_rows}
    transitions = []
    prior = None
    for row in treatment["daily"]:
        state = row["regime_state"]
        if state != prior:
            transitions.append(str(row["date"]))
            prior = state
    allowed_transitions = {str(treatment["daily"][0]["date"])} | execution_dates
    checks = {
        "causal_sma200": all(int(row["valid_session_count"]) >= SMA_WINDOW for row in gate_rows),
        "exact_nifty500_benchmark": all(row["market_index_name"] == MARKET_INDEX_NAME for row in gate_rows),
        "exact_gate_states": (
            sum(row["gate_pass"] is True for row in gate_rows) == 9
            and sum(row["gate_pass"] is False for row in gate_rows) == 2
        ),
        "exact_quarterly_schedule": tuple(str(row["rebalance_date"]) for row in gate_rows) == FROZEN_REBALANCE_DATES,
        "no_mid_quarter_change": set(transitions) <= allowed_transitions,
        "pass_date_holding_identity": all(
            decimal(row["jaccard_before_sizing"]) == 1
            and decimal(row["realized_symbol_jaccard"]) == 1
            and not row["realized_symbol_divergence"]
            for row in identity_rows
            if row["gate_pass"]
        ),
        "fail_date_cash_state": all(
            row["all_sessions_fully_cash"]
            for row in cash["gate_fail_durations"]
        ),
        "whole_share_mechanics": all(
            int(row["quantity"]) > 0
            and decimal(row["quantity"]) == Decimal(int(row["quantity"]))
            for row in treatment["holdings"]
        ),
        "cash_reconciliation": treatment["cash_reconciliation_violations"] == 0,
        "equity_reconciliation": treatment["equity_reconciliation_violations"] == 0,
        "cost_reconciliation": treatment["cost_model_status"] == "FULL_FROZEN_COST_MODEL",
        "no_lookahead": max(str(row["date"]) for row in treatment["daily"]) == DEVELOPMENT_END.isoformat(),
        "no_validation_rows": all(str(row["date"]) <= DEVELOPMENT_END.isoformat() for row in treatment["daily"]),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "state_transition_dates": transitions,
    }


def evaluate_criteria(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    accounting: Mapping[str, Any],
    invested_quarters: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    control_cagr = decimal(control["net_cagr_pct"])
    treatment_cagr = decimal(treatment["net_cagr_pct"])
    control_dd = abs(decimal(control["net_max_drawdown_pct"]))
    treatment_dd = abs(decimal(treatment["net_max_drawdown_pct"]))
    relative_dd_improvement = (
        (control_dd - treatment_dd) / control_dd * Decimal("100")
        if control_dd
        else Decimal("0")
    )
    treatment_years = [
        decimal(row["net_return_pct"]) for row in treatment["yearly"]
    ]
    criterion_values = {
        "A": treatment_cagr >= control_cagr * Decimal("0.85"),
        "B": treatment_dd <= control_dd * Decimal("0.85"),
        "C": (
            treatment_cagr > 0
            and decimal(treatment["net_ending_equity"])
            > decimal(treatment["starting_equity"])
        ),
        "D": sum(value >= 0 for value in treatment_years) >= 2,
        "E": decimal(treatment["total_cost"]) <= decimal(control["total_cost"]),
        "G": accounting["status"] == "PASS",
        "H": (
            decimal(treatment["net_annualized_volatility_pct"])
            < decimal(control["net_annualized_volatility_pct"])
        ),
        "I": decimal(treatment["net_sharpe_like"])
        > decimal(control["net_sharpe_like"]),
        "J": int(treatment["negative_quarter_count"])
        < int(control["negative_quarter_count"]),
        "K": decimal(treatment["worst_quarter_return_pct"])
        > decimal(control["worst_quarter_return_pct"]),
    }
    sample_result = (
        "PASS"
        if invested_quarters >= 6
        else "LIMITED_SAMPLE"
        if invested_quarters >= 4
        else "FATAL_SAMPLE_FAILURE"
    )
    rows = [
        {
            "criterion": "A",
            "name": "RETURN_PRESERVATION",
            "result": "PASS" if criterion_values["A"] else "FAIL",
            "observed": treatment_cagr,
            "threshold": control_cagr * Decimal("0.85"),
        },
        {
            "criterion": "B",
            "name": "DRAWDOWN_IMPROVEMENT",
            "result": "PASS" if criterion_values["B"] else "FAIL",
            "observed": treatment_dd,
            "threshold": control_dd * Decimal("0.85"),
        },
        {
            "criterion": "C",
            "name": "ABSOLUTE_PROFITABILITY",
            "result": "PASS" if criterion_values["C"] else "FAIL",
            "observed": treatment_cagr,
            "threshold": Decimal("0"),
        },
        {
            "criterion": "D",
            "name": "TEMPORAL_SUPPORT",
            "result": "PASS" if criterion_values["D"] else "FAIL",
            "observed": sum(value >= 0 for value in treatment_years),
            "threshold": 2,
        },
        {
            "criterion": "E",
            "name": "COST_EFFICIENCY",
            "result": "PASS" if criterion_values["E"] else "FAIL",
            "observed": treatment["total_cost"],
            "threshold": control["total_cost"],
        },
        {
            "criterion": "F",
            "name": "SAMPLE_ADEQUACY",
            "result": sample_result,
            "observed": invested_quarters,
            "threshold": 6,
        },
        {
            "criterion": "G",
            "name": "ACCOUNTING_DATA",
            "result": "PASS" if criterion_values["G"] else "FAIL",
            "observed": accounting["status"],
            "threshold": "PASS",
        },
        {
            "criterion": "H",
            "name": "LOWER_VOLATILITY",
            "result": "PASS" if criterion_values["H"] else "FAIL",
            "observed": treatment["net_annualized_volatility_pct"],
            "threshold": control["net_annualized_volatility_pct"],
        },
        {
            "criterion": "I",
            "name": "BETTER_SHARPE_LIKE",
            "result": "PASS" if criterion_values["I"] else "FAIL",
            "observed": treatment["net_sharpe_like"],
            "threshold": control["net_sharpe_like"],
        },
        {
            "criterion": "J",
            "name": "FEWER_NEGATIVE_QUARTERS",
            "result": "PASS" if criterion_values["J"] else "FAIL",
            "observed": treatment["negative_quarter_count"],
            "threshold": control["negative_quarter_count"],
        },
        {
            "criterion": "K",
            "name": "BETTER_WORST_QUARTER",
            "result": "PASS" if criterion_values["K"] else "FAIL",
            "observed": treatment["worst_quarter_return_pct"],
            "threshold": control["worst_quarter_return_pct"],
        },
    ]
    primary_passes = sum(
        row["result"] == "PASS" for row in rows if row["criterion"] in "ABCDEFG"
    )
    quality_passes = sum(
        row["result"] == "PASS" for row in rows if row["criterion"] in "HIJK"
    )
    fatal = sample_result == "FATAL_SAMPLE_FAILURE" or accounting["status"] != "PASS"
    all_primary = primary_passes == 7
    if (
        all_primary
        and quality_passes >= 2
        and relative_dd_improvement >= Decimal("20")
        and treatment_cagr >= control_cagr * Decimal("0.90")
    ):
        result = "STRONGLY_SUPPORTED"
    elif all_primary and quality_passes >= 1:
        result = "SUPPORTED"
    elif not fatal and primary_passes >= 5:
        result = "PARTIALLY_SUPPORTED"
    else:
        result = "FAILED"
    return rows, {
        "primary_pass_count": primary_passes,
        "quality_pass_count": quality_passes,
        "fatal_failure": fatal,
        "relative_drawdown_improvement_pct": relative_dd_improvement,
        "REGIME_G_001_DEVELOPMENT_RESULT": result,
    }


def family_result(control_status: str, treatment_result: str) -> str:
    if control_status != "PASS":
        return "INCONCLUSIVE"
    return {
        "STRONGLY_SUPPORTED": "STRONG_SUPPORT",
        "SUPPORTED": "SUPPORT",
        "PARTIALLY_SUPPORTED": "MIXED",
        "FAILED": "FAILED",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }[treatment_result]


def next_stage(treatment_result: str) -> tuple[str, str]:
    if treatment_result in {"STRONGLY_SUPPORTED", "SUPPORTED"}:
        return (
            "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN",
            "Frozen development evidence meets the preregistered support bar.",
        )
    if treatment_result == "PARTIALLY_SUPPORTED":
        return (
            "PAUSE_FAMILY_G",
            "The frozen gate is interpretable but does not justify post-result "
            "parameter tuning or an automatic second treatment.",
        )
    if treatment_result == "FAILED":
        return (
            "STOP_FAMILY_G",
            "The frozen treatment failed the preregistered development criteria.",
        )
    return "INCONCLUSIVE", "Evidence cannot be interpreted safely."


def _result_document(body: Mapping[str, Any], hash_field: str) -> dict[str, Any]:
    return {**body, hash_field: canonical_hash(body)}


def _metric_report_row(metrics: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "experiment_id",
        "starting_equity",
        "gross_ending_equity",
        "net_ending_equity",
        "gross_total_return_pct",
        "net_total_return_pct",
        "gross_cagr_pct",
        "net_cagr_pct",
        "net_max_drawdown_pct",
        "net_annualized_volatility_pct",
        "net_sharpe_like",
        "net_positive_calendar_month_rate_pct",
        "positive_quarter_rate_pct",
        "negative_quarter_count",
        "median_quarter_return_pct",
        "worst_quarter_return_pct",
        "best_quarter_return_pct",
        "total_one_way_turnover_x",
        "total_cost",
        "average_cash",
        "average_invested_capital",
        "average_holding_count",
        "maximum_holding_count",
    )
    return {field: metrics[field] for field in fields}


def _write_documentation(root: Path, summary: Mapping[str, Any]) -> Path:
    path = Path(root) / "docs/strategy-family-g-development-evaluation-v1.md"
    control = summary["control"]["metrics"]
    treatment = summary["treatment"]["metrics"]
    criteria = summary["criteria"]
    cash_rows = summary["attribution"]["cash_quarters"]
    control_drawdown, treatment_drawdown = summary["attribution"]["drawdown"]
    lines = [
        "# Strategy Family G Development Evaluation V1",
        "",
        "## Scope and frozen hypothesis",
        "",
        f"`{COMMAND_VERSION}` evaluates only `{CONTROL_ID}` against `{TREATMENT_ID}` over the frozen DEVELOPMENT window 2022-01-01 through 2024-12-31. The hypothesis is that quarterly participation only when the official NIFTY 500 close is strictly above its causal SMA200 can reduce drawdown while retaining most of the Family A momentum return. No validation data, VIX, breadth, market score, second treatment, or Strategy V2 is used.",
        "",
        "## Control reproduction",
        "",
        f"The control reads the immutable `{FAMILY_A_REFERENCE_EXPERIMENT}` / `{FAMILY_A_IMPLEMENTATION_EVIDENCE}` ₹500,000 ledger. Reproduction status is `{summary['control']['reproduction']['status']}`. Net ending equity is ₹{control['net_ending_equity']}, net return is {control['net_total_return_pct']}%, net CAGR is {control['net_cagr_pct']}%, and maximum drawdown is {control['net_max_drawdown_pct']}%.",
        "",
        "## Frozen regime gate and quarterly ledger",
        "",
        f"The exact Command 02 matrix contains {summary['treatment']['gate_pass_count']} pass and {summary['treatment']['gate_fail_count']} fail decisions. A pass uses the unchanged Family A selected-symbol set and frozen whole-share/cost mechanics. A fail liquidates to 100% cash at the next open and remains cash until the next scheduled quarterly rebalance. There is no mid-quarter re-entry. The full quarterly ledger is stored in `data/reports/family_g_dev_v1_quarterly.csv`.",
        "",
        "## Portfolio results",
        "",
        f"The treatment ends at ₹{treatment['net_ending_equity']}, with net return {treatment['net_total_return_pct']}%, net CAGR {treatment['net_cagr_pct']}%, maximum drawdown {treatment['net_max_drawdown_pct']}%, annualized volatility {treatment['net_annualized_volatility_pct']}%, and Sharpe-like metric {treatment['net_sharpe_like']}. Control and treatment costs are ₹{control['total_cost']} and ₹{treatment['total_cost']} respectively.",
        "",
        "## Skipped-quarter attribution",
        "",
    ]
    for row in cash_rows:
        lines.append(
            f"- {row['rebalance_date']}: control return {row['control_return_pct']}%; `{row['classification']}`."
        )
    lines.extend(
        [
            "",
            "## Direct gate and capital-path effects",
            "",
            summary["attribution"]["path_effect"]["direct_gate_effect_summary"],
            "",
            summary["attribution"]["path_effect"]["capital_path_effect_summary"],
            "",
            "The normalized-quarter diagnostic restarts each interval at 1.0: pass quarters reuse the control interval return, while fail quarters earn exactly 0%. This is diagnostic only and is not a second backtest or tuned strategy.",
            "",
            "## Drawdown and frozen criteria",
            "",
            f"The control maximum-drawdown peak/trough is {control_drawdown['peak_date']} to {control_drawdown['trough_date']}, recovering on {control_drawdown['recovery_date']}. Its peak-to-trough segment precedes the first gate-fail interval, although the first cash interval overlaps the recovery portion of the wider drawdown episode. The treatment maximum-drawdown peak/trough is {treatment_drawdown['peak_date']} to {treatment_drawdown['trough_date']}, recovering on {treatment_drawdown['recovery_date']}.",
            "",
            f"Relative maximum-drawdown improvement is {criteria['relative_drawdown_improvement_pct']}%. The treatment result is `{criteria['REGIME_G_001_DEVELOPMENT_RESULT']}` and the Family G result is `{summary['classifications']['FAMILY_G_DEVELOPMENT_RESULT']}`.",
            "",
            "## Next stage and governance",
            "",
            f"`FAMILY_G_NEXT_RESEARCH_STAGE = {summary['classifications']['FAMILY_G_NEXT_RESEARCH_STAGE']}`. {summary['classifications']['next_stage_reason']} Parameters and success criteria were not changed after observing results. Validation remains NOT ACCESSED, and this command does not create a validation design or Strategy V2.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_family_g_development_evaluation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    started_at = utc_now()
    freeze = verify_freeze_gate(root)
    before_snapshot = command_02_snapshot(root)
    sessions, bars = _load_market(root)
    if sessions[0] < DEVELOPMENT_START or sessions[-1] > DEVELOPMENT_END:
        _input_mismatch("development partition escaped")
    schedules = load_rebalance_schedules(root)[FAMILY_A_REFERENCE_EXPERIMENT]
    gate_rows = _gate_rows(root)
    identity = _selected_symbol_identity(schedules, gate_rows)

    control_simulation = _control_simulation(root)
    holdings_integrity = _control_holdings_integrity(
        control_simulation, gate_rows
    )
    control_metrics = portfolio_metrics(control_simulation)
    reproduction = control_reproduction(control_metrics, holdings_integrity)
    if reproduction["status"] != "PASS":
        _input_mismatch("CONTROL_REPRODUCTION_FAILURE")

    treatment_simulation = simulate_treatment(
        schedules, sessions, bars, gate_rows
    )
    identity = _realized_holding_overlap(
        identity, control_simulation, treatment_simulation
    )
    treatment_metrics = portfolio_metrics(treatment_simulation)
    ledger = quarterly_ledger(
        control_simulation, treatment_simulation, gate_rows, identity
    )
    cash_attribution = cash_quarter_attribution(ledger)
    cash = cash_utilization(treatment_simulation, gate_rows)
    accounting = accounting_integrity(
        treatment_simulation, gate_rows, identity, cash
    )
    invested_quarters = sum(row["gate_pass"] is True for row in gate_rows)
    cash_quarters = sum(row["gate_pass"] is False for row in gate_rows)
    criteria_rows, criteria_summary = evaluate_criteria(
        control_metrics, treatment_metrics, accounting, invested_quarters
    )
    treatment_result = criteria_summary["REGIME_G_001_DEVELOPMENT_RESULT"]
    mapped_family_result = family_result(reproduction["status"], treatment_result)
    next_research_stage, next_stage_reason = next_stage(treatment_result)
    path_effect = path_effect_summary(
        ledger, control_metrics, treatment_metrics
    )
    control_drawdown = drawdown_episode(control_simulation)
    treatment_drawdown = drawdown_episode(treatment_simulation)
    fail_ranges = [
        (str(row["execution_date"]), str(row["interval_end"]))
        for row in cash_attribution
    ]
    for drawdown in (control_drawdown, treatment_drawdown):
        drawdown["gate_fail_overlap_peak_to_trough"] = any(
            not (
                drawdown["trough_date"] < start
                or drawdown["peak_date"] > end
            )
            for start, end in fail_ranges
        )
        episode_end = drawdown["recovery_date"] or DEVELOPMENT_END.isoformat()
        drawdown["gate_fail_overlap_full_episode"] = any(
            not (episode_end < start or drawdown["peak_date"] > end)
            for start, end in fail_ranges
        )

    cost_reduction = decimal(control_metrics["total_cost"]) - decimal(
        treatment_metrics["total_cost"]
    )
    cost_reduction_pct = (
        cost_reduction / decimal(control_metrics["total_cost"])
        * Decimal("100")
    )
    turnover_reduction = decimal(
        control_metrics["total_one_way_turnover_x"]
    ) - decimal(treatment_metrics["total_one_way_turnover_x"])
    turnover_reduction_pct = (
        turnover_reduction
        / decimal(control_metrics["total_one_way_turnover_x"])
        * Decimal("100")
    )

    control_body = {
        "command_version": COMMAND_VERSION,
        "experiment_id": CONTROL_ID,
        "reference_experiment_id": FAMILY_A_REFERENCE_EXPERIMENT,
        "implementation_reference": FAMILY_A_IMPLEMENTATION_EVIDENCE,
        "performance": control_metrics,
        "reproduction": reproduction,
        "development_only": True,
        "validation_accessed": False,
    }
    control_result = _result_document(
        control_body, "control_g_000_result_hash"
    )
    treatment_body = {
        "command_version": COMMAND_VERSION,
        "experiment_id": TREATMENT_ID,
        "parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
        "preregistration_hash": EXPECTED_TREATMENT_PREREGISTRATION_HASH,
        "gate_pass_count": invested_quarters,
        "gate_fail_count": cash_quarters,
        "performance": treatment_metrics,
        "criteria": criteria_summary,
        "accounting": accounting,
        "cash_utilization": cash,
        "development_result": treatment_result,
        "development_only": True,
        "validation_accessed": False,
        "parameters_changed": False,
    }
    treatment_result_document = _result_document(
        treatment_body, "regime_g_001_result_hash"
    )
    registry_body = {
        "registry_version": REGISTRY_VERSION,
        "family_version": FAMILY_VERSION,
        "command_version": COMMAND_VERSION,
        "experiments": [
            {
                "experiment_id": CONTROL_ID,
                "status": "REFERENCE_REPRODUCED",
                "reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
                "result_hash": control_result["control_g_000_result_hash"],
            },
            {
                "experiment_id": TREATMENT_ID,
                "status_before": "PREREGISTERED",
                "status": "DEVELOPMENT_EVALUATED",
                "parameter_hash": EXPECTED_TREATMENT_PARAMETER_HASH,
                "preregistration_hash": EXPECTED_TREATMENT_PREREGISTRATION_HASH,
                "result_hash": treatment_result_document[
                    "regime_g_001_result_hash"
                ],
                "development_result": treatment_result,
            },
        ],
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    registry = _result_document(
        registry_body, "family_g_development_registry_hash"
    )

    yearly_report: list[dict[str, Any]] = []
    gate_by_year = defaultdict(lambda: {"invested": 0, "cash": 0})
    for row in gate_rows:
        bucket = gate_by_year[int(str(row["rebalance_date"])[:4])]
        bucket["invested" if row["gate_pass"] else "cash"] += 1
    for metrics in (control_metrics, treatment_metrics):
        for row in metrics["yearly"]:
            year = int(row["year"])
            yearly_report.append(
                {
                    **row,
                    "invested_rebalance_count": gate_by_year[year]["invested"]
                    if metrics["experiment_id"] == TREATMENT_ID
                    else len([g for g in gate_rows if str(g["rebalance_date"]).startswith(str(year))]),
                    "cash_rebalance_count": gate_by_year[year]["cash"]
                    if metrics["experiment_id"] == TREATMENT_ID
                    else 0,
                }
            )
    yearly_comparison = []
    for year in (2022, 2023, 2024):
        control_year = next(row for row in control_metrics["yearly"] if int(row["year"]) == year)
        treatment_year = next(row for row in treatment_metrics["yearly"] if int(row["year"]) == year)
        yearly_comparison.append(
            {
                "year": year,
                "control_return_pct": control_year["net_return_pct"],
                "treatment_return_pct": treatment_year["net_return_pct"],
                "difference_pp": decimal(treatment_year["net_return_pct"])
                - decimal(control_year["net_return_pct"]),
                "invested_rebalance_count": gate_by_year[year]["invested"],
                "cash_rebalance_count": gate_by_year[year]["cash"],
            }
        )

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "freeze_verification": freeze,
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "session_count": len(sessions),
            "development_only": True,
            "validation_accessed": False,
            "validation_rows_loaded": 0,
        },
        "control": {
            "experiment_id": CONTROL_ID,
            "metrics": control_metrics,
            "reproduction": reproduction,
        },
        "treatment": {
            "experiment_id": TREATMENT_ID,
            "gate_pass_count": invested_quarters,
            "gate_fail_count": cash_quarters,
            "invested_quarter_count": invested_quarters,
            "cash_quarter_count": cash_quarters,
            "fraction_invested": Decimal(invested_quarters)
            / Decimal(len(gate_rows)),
            "metrics": treatment_metrics,
        },
        "criteria": criteria_summary,
        "criteria_rows": criteria_rows,
        "attribution": {
            "cash_quarters": cash_attribution,
            "path_effect": path_effect,
            "drawdown": [control_drawdown, treatment_drawdown],
            "cash_utilization": cash,
            "cost_reduction_rupees": cost_reduction,
            "cost_reduction_pct": cost_reduction_pct,
            "turnover_reduction_x": turnover_reduction,
            "turnover_reduction_pct": turnover_reduction_pct,
            "pass_date_identity": identity,
            "yearly": yearly_comparison,
        },
        "classifications": {
            "REGIME_G_001_DEVELOPMENT_RESULT": treatment_result,
            "FAMILY_G_DEVELOPMENT_RESULT": mapped_family_result,
            "FAMILY_G_NEXT_RESEARCH_STAGE": next_research_stage,
            "next_stage_reason": next_stage_reason,
        },
        "result_hashes": {
            "control_g_000_result_hash": control_result[
                "control_g_000_result_hash"
            ],
            "regime_g_001_result_hash": treatment_result_document[
                "regime_g_001_result_hash"
            ],
            "family_g_development_registry_hash": registry[
                "family_g_development_registry_hash"
            ],
        },
        "registry": registry,
        "immutability": {
            "command_02_snapshot_before": before_snapshot["snapshot_hash"],
            "command_02_snapshot_after": None,
            "command_02_unchanged": None,
            "family_a_control_unchanged": True,
            "strategy_parameter_changed": False,
            "success_criteria_changed": False,
            "benchmark_changed": False,
            "sma_period_changed": False,
            "rebalance_schedule_changed": False,
        },
        "governance": {
            "development_performance_run": True,
            "validation_accessed": False,
            "vix_added": False,
            "breadth_added": False,
            "market_score_added": False,
            "second_treatment_created": False,
            "strategy_v2_created": False,
            "parameter_tuning_after_results": False,
        },
        "security": {
            "credentials_exposed": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "database_writes": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
        },
        "known_limitations": [
            "THREE_YEAR_DEVELOPMENT_WINDOW_ONLY",
            "ONLY_TWO_GATE_FAIL_QUARTERS",
            "QUARTERLY_SMA200_GATE_CAN_REACT_AFTER_DRAWDOWN",
            "NO_VALIDATION_EVIDENCE",
        ],
        "storage": {
            "root": output_root(root).relative_to(root).as_posix(),
            "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
            "manifest": (
                output_root(root)
                / "manifests/family_g_development_evaluation_manifest_v1.json"
            ).relative_to(root).as_posix(),
        },
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }

    out = output_root(root)
    write_json(out / "control/control_g_000_result_v1.json", control_result)
    write_csv(out / "control/daily.csv", control_simulation["daily"])
    write_csv(out / "control/rebalances.csv", control_simulation["rebalances"])
    write_json(
        out / "regime_g_001/regime_g_001_result_v1.json",
        treatment_result_document,
    )
    for name in ("daily", "rebalances", "holdings", "costs", "periods"):
        write_csv(
            out / f"regime_g_001/{name}.csv", treatment_simulation[name]
        )
    write_csv(out / "quarterly/family_g_quarterly_ledger_v1.csv", ledger)
    write_csv(out / "comparison/family_g_criteria_v1.csv", criteria_rows)
    write_csv(out / "comparison/family_g_yearly_v1.csv", yearly_report)
    write_json(
        out / "comparison/family_g_development_comparison_v1.json",
        {
            "control": _metric_report_row(control_metrics),
            "treatment": _metric_report_row(treatment_metrics),
            "yearly": yearly_comparison,
            "criteria": criteria_summary,
        },
    )
    write_csv(
        out / "diagnostics/family_g_cash_quarter_attribution_v1.csv",
        cash_attribution,
    )
    write_csv(
        out / "diagnostics/family_g_normalized_quarter_v1.csv",
        path_effect["rows"],
    )
    write_json(out / "diagnostics/family_g_path_effect_v1.json", path_effect)
    write_json(
        out / "diagnostics/family_g_drawdown_attribution_v1.json",
        {"rows": [control_drawdown, treatment_drawdown]},
    )
    write_json(out / "diagnostics/family_g_cash_utilization_v1.json", cash)
    write_csv(
        out / "ledgers/combined_daily.csv",
        [*control_simulation["daily"], *treatment_simulation["daily"]],
    )
    write_csv(
        out / "ledgers/combined_rebalances.csv",
        [*control_simulation["rebalances"], *treatment_simulation["rebalances"]],
    )
    write_json(out / "manifests/family_g_development_registry_v1.json", registry)

    reports = root / "data/reports"
    write_csv(reports / REPORT_NAMES[1], [_metric_report_row(control_metrics)])
    write_csv(
        reports / REPORT_NAMES[2],
        [
            {
                **_metric_report_row(treatment_metrics),
                "gate_pass_count": invested_quarters,
                "gate_fail_count": cash_quarters,
                "invested_quarter_count": invested_quarters,
                "cash_quarter_count": cash_quarters,
                "fraction_invested": Decimal(invested_quarters)
                / Decimal(len(gate_rows)),
            }
        ],
    )
    write_csv(reports / REPORT_NAMES[3], ledger)
    write_csv(reports / REPORT_NAMES[4], yearly_report)
    write_csv(reports / REPORT_NAMES[5], criteria_rows)
    write_csv(reports / REPORT_NAMES[6], cash_attribution)
    write_csv(reports / REPORT_NAMES[7], path_effect["rows"])
    write_csv(
        reports / REPORT_NAMES[8], [control_drawdown, treatment_drawdown]
    )
    write_csv(
        reports / REPORT_NAMES[9],
        [
            {
                "control_costs": control_metrics["total_cost"],
                "treatment_costs": treatment_metrics["total_cost"],
                "cost_reduction_rupees": cost_reduction,
                "cost_reduction_pct": cost_reduction_pct,
                "control_turnover_x": control_metrics[
                    "total_one_way_turnover_x"
                ],
                "treatment_turnover_x": treatment_metrics[
                    "total_one_way_turnover_x"
                ],
                "turnover_reduction_x": turnover_reduction,
                "turnover_reduction_pct": turnover_reduction_pct,
            }
        ],
    )
    write_csv(
        reports / REPORT_NAMES[10],
        [
            {
                "control_result": reproduction["status"],
                "treatment_result": treatment_result,
                "family_result": mapped_family_result,
                "next_stage": next_research_stage,
                "control_net_cagr_pct": control_metrics["net_cagr_pct"],
                "treatment_net_cagr_pct": treatment_metrics["net_cagr_pct"],
                "control_max_drawdown_pct": control_metrics[
                    "net_max_drawdown_pct"
                ],
                "treatment_max_drawdown_pct": treatment_metrics[
                    "net_max_drawdown_pct"
                ],
                "relative_drawdown_improvement_pct": criteria_summary[
                    "relative_drawdown_improvement_pct"
                ],
            }
        ],
    )

    after_snapshot = command_02_snapshot(root)
    if before_snapshot["snapshot_hash"] != after_snapshot["snapshot_hash"]:
        _input_mismatch("Command 02 artifacts changed during evaluation")
    summary["immutability"]["command_02_snapshot_after"] = after_snapshot[
        "snapshot_hash"
    ]
    summary["immutability"]["command_02_unchanged"] = True
    documentation = _write_documentation(root, summary)
    write_json(reports / REPORT_NAMES[0], summary)

    artifact_paths = [
        *sorted(
            path
            for path in out.rglob("*")
            if path.is_file() and path.name != "family_g_development_evaluation_manifest_v1.json"
        ),
        *(reports / name for name in REPORT_NAMES),
        documentation,
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(artifact_paths))
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "family_g_frozen_hashes": freeze["family_g_hashes"],
        "governance_policy_hash": EXPECTED_GOVERNANCE_V2_HASH,
        "prehistory_hashes": freeze["prehistory_hashes"],
        "prehistory_manifest_hash": EXPECTED_PREHISTORY_MANIFEST_HASH,
        "family_f_closure_hash": EXPECTED_FAMILY_F_CLOSURE_HASH,
        "development_window": summary["development_window"],
        "gate_states": [
            {
                "rebalance_date": row["rebalance_date"],
                "execution_date": row["execution_date"],
                "gate_pass": row["gate_pass"],
            }
            for row in gate_rows
        ],
        "result_hashes": summary["result_hashes"],
        "classifications": summary["classifications"],
        "registry": registry,
        "artifact_hashes": artifact_hashes,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "verification": summary["verification"],
    }
    manifest = _result_document(
        manifest_body, "family_g_development_evaluation_manifest_hash"
    )
    write_json(
        out / "manifests/family_g_development_evaluation_manifest_v1.json",
        manifest,
    )
    return summary


def finalize_family_g_development_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports/family_g_dev_v1_summary.json"
    manifest_path = (
        output_root(root)
        / "manifests/family_g_development_evaluation_manifest_v1.json"
    )
    summary = _read_json(summary_path)
    manifest = _read_json(manifest_path)
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": True,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    artifact_hashes = dict(manifest["artifact_hashes"])
    artifact_hashes[summary_path.relative_to(root).as_posix()] = file_sha256(
        summary_path
    )
    manifest["artifact_hashes"] = artifact_hashes
    manifest["verification"] = summary["verification"]
    manifest["family_g_development_evaluation_manifest_hash"] = _document_hash(
        manifest, "family_g_development_evaluation_manifest_hash"
    )
    write_json(manifest_path, manifest)
    return summary
