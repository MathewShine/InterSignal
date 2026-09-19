import { expect, test } from "@playwright/test";

const expectedInstruments = [
  "NIFTY 50",
  "NIFTY 500",
  "BANK NIFTY",
  "FINNIFTY",
  "RELIANCE",
  "TCS",
  "HDFCBANK",
];

const runningSession = {
  version: "INTERSIGNAL_MARKET_SESSION_V1",
  session_id: "monday-evidence",
  market: "INDIA_NSE",
  market_date: "2026-09-21",
  provider: "GROWW",
  provider_mode: "LIVE",
  started_at: "2026-09-21T03:44:00Z",
  ended_at: null,
  exchange_session_state: "OPEN",
  status: "RUNNING",
  instrument_count: 7,
  stream_state: "CONNECTED",
  first_tick_at: "2026-09-21T03:45:01Z",
  last_tick_at: "2026-09-21T03:45:05Z",
  tick_count: 42,
  disconnect_count: 0,
  reconnect_count: 0,
  stale_interval_count: 0,
  error_count: 0,
  summary_snapshot_count: 1,
  last_provider_heartbeat_at: "2026-09-21T03:45:05Z",
  last_market_event_at: "2026-09-21T03:45:05Z",
  coverage_summary: {
    expected_instruments: expectedInstruments,
    active_instruments: expectedInstruments,
    observed_instruments: expectedInstruments,
    missing_instruments: [],
    coverage_pct: 100,
  },
  monitored_instruments: [],
  notes: [],
  verdict: null,
  warnings: [],
  failures: [],
  read_only: true,
};

const event = {
  event_id: "event-1",
  timestamp: "2026-09-21T03:45:05Z",
  event_type: "TICK_RECEIVED",
  instrument_id: "RELIANCE",
  freshness: "FRESH",
  reason_code: null,
};

async function routeSessionApi(page, {
  current = { session: null },
  provider,
  events = [],
  startSession = null,
  stopSummary = null,
  mutationDelayMs = 0,
} = {}) {
  let currentResponse = current;
  await page.route("**/api/market/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/provider/status")) {
      return route.fulfill({
        json: provider ?? {
          provider: "GROWW",
          mode: "LIVE",
          configured: true,
          connected: true,
          stream_state: "CONNECTED",
          market_session: "OPEN",
        },
      });
    }
    if (path.endsWith("/session/current")) {
      if (currentResponse instanceof Error) {
        return route.fulfill({ status: 503, json: { code: "SESSION_UNAVAILABLE" } });
      }
      return route.fulfill({ json: currentResponse });
    }
    if (path.endsWith("/session/start") && route.request().method() === "POST" && startSession) {
      if (mutationDelayMs) await new Promise((resolve) => setTimeout(resolve, mutationDelayMs));
      currentResponse = { session: startSession };
      return route.fulfill({ json: startSession });
    }
    if (path.endsWith("/session/stop") && route.request().method() === "POST" && stopSummary) {
      if (mutationDelayMs) await new Promise((resolve) => setTimeout(resolve, mutationDelayMs));
      currentResponse = { session: stopSummary.session };
      return route.fulfill({ json: stopSummary });
    }
    if (/\/sessions\/[^/]+\/events$/.test(path)) return route.fulfill({ json: { items: events } });
    return route.fulfill({ status: 404, json: { code: "TEST_ROUTE_UNHANDLED" } });
  });
}

test("shows a neutral no-session state without retry", async ({ page }) => {
  await routeSessionApi(page);

  await page.goto("/app/market/session");
  await expect(page.getByRole("heading", { name: "No observation session yet." })).toBeVisible();
  await expect(page.getByText("Start an observation session to record provider health, coverage, freshness and reconnect evidence.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start observation" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
});

test("reserves the compact error state and retry action for API failure", async ({ page }) => {
  await routeSessionApi(page, { current: new Error("request failed") });

  await page.goto("/app/market/session");
  await expect(page.getByRole("heading", { name: "Session evidence couldn’t be loaded." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start observation" })).toHaveCount(0);
});

test("shows truthful closed-market metadata before recording starts", async ({ page }) => {
  await routeSessionApi(page, {
    provider: {
      provider: "GROWW",
      mode: "LIVE",
      configured: true,
      connected: false,
      stream_state: "NOT_AVAILABLE",
      market_session: "CLOSED",
    },
  });

  await page.goto("/app/market/session");
  const context = page.locator(".market-session-context");
  await expect(context).toContainText("MarketClosed");
  await expect(context).toContainText("ProviderGroww");
  await expect(context).toContainText("StreamIdle");
  await expect(context).toContainText("RecordingNot started");
  await expect(context).toContainText("Selected instruments7");
  await expect(context).toContainText("Sampling5 sec");
  await expect(context).toContainText("Summary cadence60 sec");
  await expect(page.getByText(/Starting now will create a closed-market verification session/)).toBeVisible();
});

test("shows running observation metrics and the event timeline", async ({ page }) => {
  await routeSessionApi(page, { current: { session: runningSession }, events: [event] });

  await page.goto("/app/market/session");
  await expect(page.getByRole("heading", { name: "Observation active" })).toBeVisible();
  await expect(page.getByLabel("Session metrics")).toContainText("Observed coverage7 / 7");
  await expect(page.getByLabel("Session metrics")).toContainText("Tick observations42");
  await expect(page.getByRole("table", { name: "Market session event timeline" })).toContainText("TICK RECEIVED");
  await expect(page.getByText(/buy|sell|paper order/i)).toHaveCount(0);
});

test("shows a concrete warning reason for degraded evidence", async ({ page }) => {
  const degraded = { ...runningSession, status: "DEGRADED", stale_interval_count: 1 };
  await routeSessionApi(page, { current: { session: degraded } });

  await page.goto("/app/market/session");
  await expect(page.getByRole("heading", { name: "Observation degraded" })).toBeVisible();
  await expect(page.getByText("Stale market data was detected.")).toBeVisible();
});

test("starts once, exposes pending state, and renders the returned pre-open session", async ({ page }) => {
  const preOpen = {
    ...runningSession,
    status: "PRE_OPEN",
    exchange_session_state: "PRE_OPEN",
    first_tick_at: null,
    last_tick_at: null,
    last_market_event_at: null,
    tick_count: 0,
  };
  await routeSessionApi(page, { startSession: preOpen, mutationDelayMs: 250 });

  await page.goto("/app/market/session");
  const start = page.getByRole("button", { name: "Start observation" });
  await start.click();
  await expect(page.getByRole("button", { name: "Starting…" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "Observation preparing" }).first()).toBeVisible();
  await expect(page.getByText(/Groww · LIVE · Pre Open/)).toBeVisible();
});

test("requires restrained confirmation before stopping and finalizing", async ({ page }) => {
  const completed = {
    ...runningSession,
    status: "COMPLETED",
    ended_at: "2026-09-21T10:01:00Z",
    verdict: "PASS",
  };
  await routeSessionApi(page, {
    current: { session: runningSession },
    stopSummary: { session: completed },
  });

  await page.goto("/app/market/session");
  await page.getByRole("button", { name: "Stop observation" }).click();
  const confirmation = page.getByRole("alertdialog", { name: "Stop this observation session?" });
  await expect(confirmation).toContainText("Stopping finalizes recorded evidence.");
  await confirmation.getByRole("button", { name: "Cancel" }).click();
  await expect(confirmation).toHaveCount(0);
  await page.getByRole("button", { name: "Stop observation" }).click();
  await page.getByRole("button", { name: "Finalize observation" }).click();
  await expect(page.getByRole("heading", { name: "Observation completed" })).toBeVisible();
});

test("shows completed PASS WITH WARNINGS verdict and links to the report and timeline", async ({ page }) => {
  const completed = {
    ...runningSession,
    status: "COMPLETED",
    ended_at: "2026-09-21T10:01:00Z",
    verdict: "PASS_WITH_WARNINGS",
    summary_snapshot_count: 376,
    warnings: ["One brief provider disconnect recovered."],
  };
  await routeSessionApi(page, { current: { session: completed }, events: [event] });

  await page.goto("/app/market/session");
  await expect(page.getByRole("heading", { name: "Observation completed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "PASS WITH WARNINGS" })).toBeVisible();
  await expect(page.getByRole("link", { name: "View event timeline" })).toHaveAttribute("href", "#session-timeline");
  await expect(page.getByRole("link", { name: "View session report" })).toHaveAttribute("href", /\/api\/market\/sessions\/monday-evidence\/summary$/);
});

for (const verdict of ["PASS", "FAIL"]) {
  test(`shows completed ${verdict} verdict`, async ({ page }) => {
    const completed = {
      ...runningSession,
      status: "COMPLETED",
      ended_at: "2026-09-21T10:01:00Z",
      verdict,
      summary_snapshot_count: 376,
      failures: verdict === "FAIL" ? ["first_tick_received_during_open_session"] : [],
    };
    await routeSessionApi(page, { current: { session: completed }, events: [event] });

    await page.goto("/app/market/session");
    await expect(page.getByRole("heading", { name: "Observation completed" })).toBeVisible();
    await expect(page.getByRole("heading", { name: verdict })).toBeVisible();
    await expect(page.getByLabel("Session metrics")).toContainText("Summary snapshots376");
  });
}
