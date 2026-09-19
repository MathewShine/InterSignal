import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MarketSessionPage, SESSION_UI_STATES, deriveSessionUiState } from "./MarketSessionPage.jsx";

const coverage = {
  expected_instruments: ["NIFTY 50", "NIFTY 500", "BANK NIFTY", "FINNIFTY", "RELIANCE", "TCS", "HDFCBANK"],
  active_instruments: ["NIFTY 50", "NIFTY 500", "BANK NIFTY", "FINNIFTY", "RELIANCE", "TCS", "HDFCBANK"],
  observed_instruments: ["NIFTY 50", "NIFTY 500", "BANK NIFTY", "FINNIFTY", "RELIANCE", "TCS", "HDFCBANK"],
  missing_instruments: [],
  coverage_pct: 100,
};

const baseSession = {
  version: "INTERSIGNAL_MARKET_SESSION_V1", session_id: "monday-session", market: "INDIA_NSE", market_date: "2026-09-21",
  provider: "GROWW", provider_mode: "LIVE", started_at: "2026-09-21T03:44:00Z", ended_at: null,
  exchange_session_state: "OPEN", status: "RUNNING", instrument_count: 7, stream_state: "CONNECTED",
  first_tick_at: "2026-09-21T03:45:01Z", last_tick_at: "2026-09-21T03:45:05Z", tick_count: 42,
  disconnect_count: 1, reconnect_count: 1, stale_interval_count: 0, error_count: 0, summary_snapshot_count: 4,
  last_provider_heartbeat_at: "2026-09-21T03:45:05Z", last_market_event_at: "2026-09-21T03:45:05Z",
  coverage_summary: coverage, monitored_instruments: [], notes: [], verdict: null, warnings: [], failures: [], read_only: true,
};

const events = [{
  version: "INTERSIGNAL_MARKET_OBSERVATION_EVENT_V1", event_id: "event-1", session_id: "monday-session",
  timestamp: "2026-09-21T03:45:05Z", event_type: "INDEX_UPDATE", provider: "GROWW", instrument_id: "NIFTY 50",
  source_timestamp: "2026-09-21T03:45:05Z", received_at: "2026-09-21T03:45:05Z", freshness: "FRESH",
  payload_summary: { ltp: "25123.50" }, reason_code: null, metadata: {},
}];

const closedProvider = { provider: "GROWW", mode: "LIVE", configured: true, connected: true, stream_state: "CONNECTED", market_session: "CLOSED" };
const openProvider = { ...closedProvider, market_session: "OPEN" };

function response(payload) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
}

function mockApi({ initialSession = null, provider = closedProvider, failCurrent = false } = {}) {
  let currentSession = initialSession;
  let currentFailures = failCurrent ? 1 : 0;
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((url, options = {}) => {
    const value = String(url);
    if (value.includes("/provider/status")) return response(provider);
    if (value.includes("/session/current")) {
      if (currentFailures) { currentFailures -= 1; return Promise.reject(new Error("session API unavailable")); }
      return response({ session: currentSession });
    }
    if (value.includes(`/sessions/${currentSession?.session_id}/events`)) return response({ items: events });
    if (value.includes("/session/start") && options.method === "POST") {
      currentSession = { ...baseSession, status: "PRE_OPEN", exchange_session_state: "PRE_OPEN", tick_count: 0, first_tick_at: null, last_tick_at: null, last_market_event_at: null };
      return response(currentSession);
    }
    if (value.includes("/session/stop") && options.method === "POST") {
      currentSession = { ...baseSession, status: "COMPLETED", ended_at: "2026-09-21T10:01:00Z", verdict: "PASS" };
      return response({ session: currentSession });
    }
    throw new Error(`Unexpected URL ${value}`);
  });
  return { fetchMock, get currentSession() { return currentSession; } };
}

function renderPage() {
  return render(<MemoryRouter><MarketSessionPage /></MemoryRouter>);
}

afterEach(() => vi.restoreAllMocks());

describe("MarketSessionPage state semantics", () => {
  it("defines every frontend session state without conflating no-session and API error", () => {
    expect(deriveSessionUiState(null)).toBe(SESSION_UI_STATES.NO_SESSION);
    expect(deriveSessionUiState(null, new Error("offline"))).toBe(SESSION_UI_STATES.API_ERROR);
    for (const status of ["CREATED", "PRE_OPEN", "RUNNING", "DEGRADED", "CLOSED", "FAILED", "COMPLETED"]) {
      expect(deriveSessionUiState({ status })).toBe(status);
    }
  });

  it("renders a successful no-session response as a neutral state without Retry", async () => {
    mockApi({ provider: openProvider });
    renderPage();
    expect(await screen.findByRole("heading", { name: "No observation session yet." })).toBeInTheDocument();
    expect(screen.getByText("Start an observation session to record provider health, coverage, freshness and reconnect evidence.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start observation" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("shows compact Retry UI only for an actual current-session API failure", async () => {
    const user = userEvent.setup();
    mockApi({ failCurrent: true });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Session evidence couldn’t be loaded." })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "No observation session yet." })).toBeInTheDocument();
  });

  it("shows truthful closed-market context without classifying it as degraded", async () => {
    mockApi();
    renderPage();
    await screen.findByRole("heading", { name: "No observation session yet." });
    const context = screen.getByText("Recording").closest("dl");
    expect(within(context).getByText("Closed")).toBeInTheDocument();
    expect(within(context).getByText("Groww")).toBeInTheDocument();
    expect(within(context).getByText("Not started")).toBeInTheDocument();
    expect(screen.getByText("7", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("5 sec")).toBeInTheDocument();
    expect(screen.getByText("60 sec")).toBeInTheDocument();
    expect(screen.getByText(/Starting now will create a closed-market verification session/)).toBeInTheDocument();
    expect(screen.queryByText("Observation degraded")).not.toBeInTheDocument();
  });

  it("starts once, prevents duplicate clicks, and renders the returned pre-open session", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi();
    renderPage();
    const start = await screen.findByRole("button", { name: "Start observation" });
    await user.click(start);
    expect(
      (await screen.findAllByRole("heading", { name: "Observation preparing" })).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Groww · LIVE · Pre Open/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/session/start"))).toHaveLength(1);
  });

  it("renders understandable running metrics without trading controls", async () => {
    mockApi({ initialSession: baseSession, provider: openProvider });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Observation active" })).toBeInTheDocument();
    const metrics = screen.getByLabelText("Session metrics");
    expect(within(metrics).getByText("42")).toBeInTheDocument();
    expect(within(metrics).getByText("7 / 7")).toBeInTheDocument();
    expect(within(metrics).getByText("Disconnects")).toBeInTheDocument();
    expect(screen.queryByText(/buy|sell|paper order|p&l/i)).not.toBeInTheDocument();
  });

  it("uses warning treatment and a concrete reason only for degraded evidence", async () => {
    mockApi({ initialSession: { ...baseSession, status: "DEGRADED", stale_interval_count: 1 }, provider: openProvider });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Observation degraded" })).toBeInTheDocument();
    expect(screen.getByText("Stale market data was detected.")).toBeInTheDocument();
  });

  it.each(["PASS", "PASS_WITH_WARNINGS", "FAIL"])("renders a completed %s verdict with report and timeline actions", async (verdict) => {
    mockApi({ initialSession: { ...baseSession, status: "COMPLETED", ended_at: "2026-09-21T10:01:00Z", verdict } });
    renderPage();
    expect(await screen.findByRole("heading", { name: "Observation completed" })).toBeInTheDocument();
    expect(screen.getAllByText(verdict === "PASS_WITH_WARNINGS" ? "PASS WITH WARNINGS" : verdict).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "View event timeline" })).toHaveAttribute("href", "#session-timeline");
    expect(screen.getByRole("link", { name: "View session report" })).toHaveAttribute("href", expect.stringContaining("/sessions/monday-session/summary"));
    expect(screen.getByText("Summary snapshots")).toBeInTheDocument();
  });

  it("requires a restrained confirmation before stop finalizes evidence", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi({ initialSession: baseSession, provider: openProvider });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Stop observation" }));
    const confirmation = screen.getByRole("alertdialog", { name: "Stop this observation session?" });
    expect(confirmation).toHaveTextContent("Stopping finalizes recorded evidence.");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/session/stop"))).toHaveLength(0);
    await user.click(within(confirmation).getByRole("button", { name: "Finalize observation" }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/session/stop"))).toHaveLength(1));
    expect(await screen.findByRole("heading", { name: "Observation completed" })).toBeInTheDocument();
  });
});
