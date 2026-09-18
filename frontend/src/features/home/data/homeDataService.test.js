import { describe, expect, it } from "vitest";
import { ApiHomeAdapter } from "./apiHomeAdapter.js";
import { createHomeDataService, DemoHomeAdapter, HomeDataService } from "./homeDataService.js";

describe("HomeDataService contract", () => {
  it("exposes the complete deterministic home snapshot", async () => {
    const service = new DemoHomeAdapter();
    const snapshot = await service.getHomeSnapshot();

    expect(snapshot.version).toBe("INTERSIGNAL_INTELLIGENCE_HOME_V1");
    expect(snapshot.profile).toBe("ATTENTION_CONTEXT_PORTFOLIO_RESEARCH_HOME_V1");
    expect(snapshot.demoMode).toBe(true);
    expect(snapshot.projectState).toMatchObject({
      strategyResearch: "PAUSED",
      productionCandidates: 0,
      validatedProductionStrategies: 0,
      strategyV2: "NOT_CREATED",
      broker: "NOT_CONNECTED",
    });
  });

  it("implements every public data boundary method", async () => {
    const service = new DemoHomeAdapter();

    expect(await service.getAttentionItems()).toHaveLength(3);
    expect((await service.getMarketContext()).index).toBe("NIFTY 500");
    expect((await service.getPortfolioContext()).status).toBe("available");
    expect((await service.getResearchPulse()).families).toBe(7);
    expect((await service.getDataHealth()).rows).toHaveLength(6);
    expect((await service.getGovernancePulse()).paper).toBe("Not ready");
    expect(await service.getRecentActivity()).toHaveLength(5);
  });

  it("returns cloned fixtures so callers cannot mutate adapter state", async () => {
    const service = new DemoHomeAdapter();
    const first = await service.getHomeSnapshot();
    first.market.index = "MUTATED";
    expect((await service.getHomeSnapshot()).market.index).toBe("NIFTY 500");
  });

  it("supports deterministic empty, partial and error scenarios", async () => {
    expect((await new DemoHomeAdapter({ scenario: "empty-portfolio" }).getHomeSnapshot()).portfolio.status).toBe("empty");
    expect((await new DemoHomeAdapter({ scenario: "no-market" }).getHomeSnapshot()).market.status).toBe("unavailable");
    expect((await new DemoHomeAdapter({ scenario: "research-unavailable" }).getHomeSnapshot()).research.status).toBe("unavailable");
    await expect(new DemoHomeAdapter({ scenario: "error" }).getHomeSnapshot()).rejects.toThrow("temporarily unavailable");
  });

  it("keeps the abstract base class free of transport assumptions", async () => {
    await expect(new HomeDataService().getHomeSnapshot()).rejects.toThrow("must be implemented");
  });

  it("uses the API adapter by default and demo only when explicitly selected", () => {
    expect(createHomeDataService()).toBeInstanceOf(ApiHomeAdapter);
    expect(createHomeDataService({ mode: "demo" })).toBeInstanceOf(DemoHomeAdapter);
  });
});
