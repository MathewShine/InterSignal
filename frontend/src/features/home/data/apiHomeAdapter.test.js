import { afterEach, describe, expect, it, vi } from "vitest";
import { makeHomeApiPayload } from "../../../test/homeApiFixture.js";
import { ApiHomeAdapter } from "./apiHomeAdapter.js";

function response(payload, { ok = true } = {}) {
  return { ok, json: vi.fn().mockResolvedValue(payload) };
}

describe("ApiHomeAdapter", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("requests the single Home endpoint and normalizes the V1 contract", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(makeHomeApiPayload()));
    const adapter = new ApiHomeAdapter({
      apiBaseUrl: "http://api.example.test/",
      fetchImpl,
      timeoutMs: 1000,
    });

    const snapshot = await adapter.getHomeSnapshot();

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.example.test/api/home/snapshot",
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        credentials: "omit",
      }),
    );
    expect(snapshot.connectionState).toBe("PARTIAL");
    expect(snapshot.availability.dataHealth.status).toBe("PARTIAL");
    expect(snapshot.market).toMatchObject({
      availability: "UNAVAILABLE",
      reason: "LIVE_MARKET_SERVICE_NOT_CONFIGURED",
      visualizationMode: "ILLUSTRATIVE",
    });
    expect(snapshot.research).toMatchObject({
      programmeState: "PAUSED",
      families: 7,
      productionCandidates: 0,
      validatedStrategies: 0,
      strategyV2: "NOT_CREATED",
      blocked: ["Family D", "Family F"],
    });
    expect(snapshot.portfolio).toMatchObject({
      sourceStatus: "SYNTHETIC",
      holdingCount: 1,
      value: "₹52,393",
    });
    expect(snapshot.governance).toMatchObject({
      paperState: "NOT_READY",
      liveState: "NOT_READY",
      brokerState: "NOT_READY",
      productionState: "NOT_READY",
      blockingViolations: 0,
      pendingAuthorizations: 1,
    });
    expect(snapshot.dataHealth.rows.map((row) => row.rawValue)).toEqual([
      "AVAILABLE",
      "AVAILABLE_WITH_CAVEATS",
      "BLOCKED_FOR_RESEARCH_USE",
      "SOURCE_BLOCKED",
      "HEALTHY",
      "0",
    ]);
    expect(snapshot.recentActivity).toEqual([
      expect.objectContaining({
        id: "AUDIT-001",
        label: "Authorization requested",
        sourceDomain: "DATA",
      }),
    ]);
    expect(snapshot.attentionItems[0]).toMatchObject({
      id: "research-family-d-blocked",
      provenance: "PLATFORM",
      sourceDomain: "RESEARCH",
    });
    expect(snapshot.attentionItems.at(-1).provenance).toBe(
      "ILLUSTRATIVE_MARKET",
    );
  });

  it("rejects unsupported contract versions with a controlled error", async () => {
    const payload = makeHomeApiPayload({
      version: "INTERSIGNAL_HOME_SNAPSHOT_V999",
    });
    const adapter = new ApiHomeAdapter({
      fetchImpl: vi.fn().mockResolvedValue(response(payload)),
    });

    await expect(adapter.getHomeSnapshot()).rejects.toMatchObject({
      code: "HOME_API_UNSUPPORTED_CONTRACT",
      message: "This Home data contract is not supported.",
    });
  });

  it("surfaces a sanitized network error without demo fallback", async () => {
    const adapter = new ApiHomeAdapter({
      fetchImpl: vi.fn().mockRejectedValue(new Error("private network detail")),
    });

    await expect(adapter.getHomeSnapshot()).rejects.toMatchObject({
      code: "HOME_API_UNAVAILABLE",
      message: "Unable to load this context.",
    });
  });

  it("aborts a request at the configured timeout", async () => {
    vi.useFakeTimers();
    const fetchImpl = vi.fn((_, { signal }) => new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      });
    }));
    const adapter = new ApiHomeAdapter({ fetchImpl, timeoutMs: 50 });

    const pending = adapter.getHomeSnapshot();
    const rejection = expect(pending).rejects.toMatchObject({
      code: "HOME_API_TIMEOUT",
    });
    await vi.advanceTimersByTimeAsync(51);

    await rejection;
    expect(fetchImpl.mock.calls[0][1].signal.aborted).toBe(true);
  });

  it("maps partial domains and an explicit empty portfolio independently", async () => {
    const payload = makeHomeApiPayload({
      availability: {
        ...makeHomeApiPayload().availability,
        portfolio: { status: "UNAVAILABLE", reason: "PORTFOLIO_SOURCE_UNAVAILABLE" },
      },
      portfolio: {
        status: "UNAVAILABLE",
        reason: "PORTFOLIO_SOURCE_UNAVAILABLE",
        has_portfolio: false,
      },
    });
    const unavailable = await new ApiHomeAdapter({
      fetchImpl: vi.fn().mockResolvedValue(response(payload)),
    }).getHomeSnapshot();
    expect(unavailable.portfolio.sourceStatus).toBe("UNAVAILABLE");
    expect(unavailable.research.status).toBe("available");
    expect(unavailable.dataHealth.status).toBe("partial");

    const emptyPayload = makeHomeApiPayload({
      portfolio: {
        status: "AVAILABLE",
        reason: "NO_PORTFOLIO_CONFIGURED",
        has_portfolio: false,
        portfolio_count: 0,
        source_type: "NONE",
      },
    });
    const empty = await new ApiHomeAdapter({
      fetchImpl: vi.fn().mockResolvedValue(response(emptyPayload)),
    }).getHomeSnapshot();
    expect(empty.portfolio).toMatchObject({
      status: "empty",
      sourceStatus: "EMPTY",
      hasPortfolio: false,
    });
  });
});
