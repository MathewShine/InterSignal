import { describe, expect, it, vi } from "vitest";
import { ApiDataAdapter } from "./apiDataAdapter.js";

const payload = {
  version: "INTERSIGNAL_DATA_HEALTH_V1", generated_at: "2026-09-18T12:00:00Z", status: "AVAILABLE", reason: null,
  meta: { read_only: true, source_contract: "PLATFORM", unavailable_sections: [] },
  sources: [{ source_id: "intraday-continuity", name: "Intraday continuity", domain: "MARKET_DATA", status: "BLOCKED_FOR_RESEARCH_USE", research_use: "INSUFFICIENT_FOR_TRUSTWORTHY_FORMAL_EVALUATION", summary: "Below threshold", freshness: "STATIC_SEEDED_PLATFORM_STATE", coverage_pct: "77.826177", gap_count: 217, limitations: ["Research blocked"], evidence_refs: ["EVIDENCE-D"] }],
  lineage: { integrity_status: "HEALTHY", broken_reference_count: 0, node_count: 2, edge_count: 1, artifact_count: 1, stage_counts: { SOURCE: 2 }, nodes: [] },
  limitations: [],
};
const response = (value, ok = true) => ({ ok, status: ok ? 200 : 500, json: vi.fn().mockResolvedValue(value) });

describe("ApiDataAdapter", () => {
  it("uses the aggregate overview once and validates its contract", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(payload));
    const result = await new ApiDataAdapter({ apiBaseUrl: "http://api.test/", fetchImpl }).getOverview();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/data/overview", expect.objectContaining({ method: "GET", cache: "no-store", credentials: "omit" }));
    expect(result.sources[0]).toMatchObject({ coveragePercent: 77.826177, gapCount: 217 });
    expect(result.lineage).toMatchObject({ integrityStatus: "HEALTHY", brokenReferenceCount: 0 });
  });

  it("exposes all read resources and sanitizes errors", async () => {
    const adapter = new ApiDataAdapter({ fetchImpl: vi.fn() });
    for (const method of ["getOverview", "getSources", "getLineage", "getLimitations"]) expect(typeof adapter[method]).toBe("function");
    const incompatible = new ApiDataAdapter({ fetchImpl: vi.fn().mockResolvedValue(response({ ...payload, version: "V2" })) });
    await expect(incompatible.getOverview()).rejects.toMatchObject({ code: "DATA_API_INCOMPATIBLE" });
    const offline = new ApiDataAdapter({ fetchImpl: vi.fn().mockRejectedValue(new Error("private detail")) });
    await expect(offline.getOverview()).rejects.toMatchObject({ code: "DATA_API_UNAVAILABLE", message: "Data health couldn’t be loaded." });
  });
});
