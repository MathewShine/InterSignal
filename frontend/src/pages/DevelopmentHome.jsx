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
    </div>
  );
}
