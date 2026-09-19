import { describe, expect, it, vi } from "vitest";
import { marketApiFixture } from "../../../test/marketApiFixture.js";
import { ApiMarketAdapter } from "./apiMarketAdapter.js";

const response = (value, ok = true) => ({ ok, status: ok ? 200 : 500, json: vi.fn().mockResolvedValue(value) });

describe("ApiMarketAdapter", () => {
  it("requests the snapshot exactly once and normalizes numeric contract fields", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(marketApiFixture));
    const result = await new ApiMarketAdapter({ apiBaseUrl: "http://api.test/", fetchImpl }).getSnapshot();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/market/snapshot", expect.objectContaining({ method: "GET", cache: "no-store", credentials: "omit" }));
    expect(result).toMatchObject({ status: "PARTIAL", provider: { mode: "SEEDED" }, session: { status: "CLOSED", marketDate: "2026-09-07" } });
    expect(result.breadth).toMatchObject({ advancers: 171, decliners: 325, aboveVwapPercent: null, quality: { coveragePercent: 99.4012 } });
    expect(result.sectors).toHaveLength(23);
  });

  it("rejects unknown contracts and sanitizes transport failures", async () => {
    const incompatible = new ApiMarketAdapter({ fetchImpl: vi.fn().mockResolvedValue(response({ ...marketApiFixture, version: "V2" })) });
    await expect(incompatible.getSnapshot()).rejects.toMatchObject({ code: "MARKET_API_INCOMPATIBLE" });
    const offline = new ApiMarketAdapter({ fetchImpl: vi.fn().mockRejectedValue(new Error("private provider detail")) });
    await expect(offline.getSnapshot()).rejects.toMatchObject({ code: "MARKET_API_UNAVAILABLE", message: "Market data is unavailable." });
  });
});
