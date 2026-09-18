import { describe, expect, it, vi } from "vitest";
import { ApiPortfolioAdapter } from "./apiPortfolioAdapter.js";
import { normalizeOverview, statusLabel } from "./portfolioNormalizers.js";
import { makePortfolioOverview } from "../../../test/portfolioApiFixture.js";

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: vi.fn().mockResolvedValue(payload) };
}

describe("ApiPortfolioAdapter", () => {
  it("loads one backend overview request and normalizes the view model", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(makePortfolioOverview()));
    const adapter = new ApiPortfolioAdapter({ apiBaseUrl: "http://api.test/", fetchImpl });
    const result = await adapter.getOverview({ portfolioId: "PORT-1" });
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/portfolio/overview?portfolio_id=PORT-1", expect.objectContaining({ method: "GET", cache: "no-store", credentials: "omit" }));
    expect(result.summary).toMatchObject({ portfolioValue: 52393, invested: 10000, cash: 42393, realizedPnl: 397, unrealizedPnl: 1996 });
    expect(result.holdings[0]).toMatchObject({ name: "Synthetic Mutual Fund One", marketValue: 10000, sector: "Diversified" });
    expect(result.portfolio.sourceLabel).toBe("Demo portfolio");
  });

  it("exposes the four read-only Portfolio resources", () => {
    const adapter = new ApiPortfolioAdapter({ fetchImpl: vi.fn() });
    for (const method of ["getOverview", "getHoldings", "getActivity", "getPerformance"]) expect(typeof adapter[method]).toBe("function");
  });

  it("rejects incompatible contracts and sanitizes transport errors", async () => {
    const incompatible = new ApiPortfolioAdapter({ fetchImpl: vi.fn().mockResolvedValue(response(makePortfolioOverview({ version: "V2" }))) });
    await expect(incompatible.getOverview()).rejects.toMatchObject({ code: "PORTFOLIO_API_INCOMPATIBLE" });
    const offline = new ApiPortfolioAdapter({ fetchImpl: vi.fn().mockRejectedValue(new Error("secret transport detail")) });
    await expect(offline.getOverview()).rejects.toMatchObject({ code: "PORTFOLIO_API_UNAVAILABLE", message: "Portfolio data couldn’t be loaded." });
    const missing = new ApiPortfolioAdapter({ fetchImpl: vi.fn().mockResolvedValue(response({}, { ok: false, status: 404 })) });
    await expect(missing.getOverview()).rejects.toMatchObject({ code: "PORTFOLIO_NOT_FOUND" });
  });
});

describe("Portfolio normalizer", () => {
  it("keeps backend values and maps snake case away from components", () => {
    const result = normalizeOverview(makePortfolioOverview());
    expect(result.summary.investedPercent).toBeCloseTo(0.1908651919);
    expect(result.allocation.sectors).toEqual([{ label: "Diversified", weight: 0.1908651919 }]);
    expect(result.holdings[0].lots[0].realizedStatus).toBe("PARTIALLY_REALIZED");
    expect(result.benchmark.difference).toBe(0.02786);
  });

  it("maps raw statuses to customer language", () => {
    expect(statusLabel("SYNTHETIC")).toBe("Demo portfolio");
    expect(statusLabel("AVAILABLE")).toBe("Available");
    expect(statusLabel("PARTIAL")).toBe("Partial");
    expect(statusLabel("UNAVAILABLE")).toBe("Unavailable");
  });
});
