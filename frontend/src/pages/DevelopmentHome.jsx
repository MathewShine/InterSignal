import { StatusPanel } from "../components/StatusPanel.jsx";

export function DevelopmentHome() {
  return (
    <div className="development-home">
      <StatusPanel
        label="Frontend"
        status="ok"
        detail="Vite application shell"
      />
      <StatusPanel
        label="Backend"
        status="placeholder"
        detail="Health status placeholder"
      />
      <StatusPanel
        label="Supabase"
        status="placeholder"
        detail="Backend configuration placeholder"
      />
      <StatusPanel
        label="Historical ingestion framework"
        status="available"
        detail="CLI and provider adapters available"
      />
      <StatusPanel
        label="Groww historical provider"
        status="available"
        detail="Read-only diagnostic path"
      />
      <StatusPanel
        label="Historical dataset acquisition"
        status="available"
        detail="Nifty 500 daily pilot CLI"
      />
      <StatusPanel
        label="Daily historical data audit"
        status="available"
        detail="Groww vs NSE comparison CLI"
      />
      <StatusPanel
        label="Official NSE daily dataset"
        status="partial"
        detail="Local pilot and full-run CLI"
      />
      <StatusPanel
        label="Point-in-time Nifty 500"
        status="partial_history"
        detail="Official event reconstruction with coverage gaps"
      />
      <StatusPanel
        label="Benchmark Context"
        status="available"
        detail="Official NIFTY 50 and NIFTY 500 histories"
      />
      <StatusPanel
        label="Sector Context"
        status="limited"
        detail="Official sector index histories with current-only stock mapping"
      />
      <StatusPanel
        label="Momentum Candidate Engine"
        status="pilot"
        detail="Emerging and confirmed research candidates"
      />
      <StatusPanel
        label="Momentum Candidate Audit"
        status="available"
        detail="Structural funnel audit without outcome labels"
      />
      <StatusPanel
        label="Emerging Volume Semantics Audit"
        status="available"
        detail="RVOL confirmation semantics without outcome labels"
      />
      <StatusPanel
        label="Daily Setup Evaluator"
        status="pilot"
        detail="Breakout and continuation setup quality foundation"
      />
      <StatusPanel
        label="Daily Setup Audit"
        status="available"
        detail="Setup funnel, candle semantics, and sensitivity diagnostics"
      />
      <StatusPanel
        label="Historical Market Regime"
        status="available"
        detail="Daily EOD broad-market context foundation"
      />
      <StatusPanel
        label="Market Regime Stability Audit"
        status="available"
        detail="Structural audit without outcome labels"
      />
      <StatusPanel
        label="Strategy V1 Entry Evaluator"
        status="available"
        detail="Entry context gate foundation"
      />
      <StatusPanel
        label="Entry Evaluation Audit"
        status="available"
        detail="Structural selectivity and invariant audit"
      />
      <StatusPanel
        label="Risk Structure Engine"
        status="available"
        detail="Stop, target, reward:risk, and position-risk foundation"
      />
      <StatusPanel
        label="Risk Structure Audit"
        status="available"
        detail="Stop semantics, target fallback, and capital-risk audit"
      />
      <StatusPanel
        label="Risk Structure Foundation"
        status="complete"
        detail="Current: RISK_STRUCTURE_V1_1"
      />
      <StatusPanel
        label="Strategy V1 Scoring"
        status="complete"
        detail="Current: STRATEGY_SCORE_V1 / SWING_DAILY_EOD_V1"
      />
      <StatusPanel
        label="Strategy Score Structural Audit"
        status="available"
        detail="Score mechanics and gate-separation audit"
      />
    </div>
  );
}
