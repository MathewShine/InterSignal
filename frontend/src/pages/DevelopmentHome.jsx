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
    </div>
  );
}
