import { describe, expect, it, vi } from "vitest";
import { ApiResearchAdapter, ResearchApiError } from "./apiResearchAdapter.js";
import { normalizeOverview, statusLabel, statusTone } from "./researchNormalizers.js";
import { makeOverviewPayload } from "../../../test/researchApiFixture.js";

function response(payload, { ok = true, status = 200 } = {}) {
  return { ok, status, json: vi.fn().mockResolvedValue(payload) };
}

describe("ApiResearchAdapter", () => {
  it("loads and normalizes the backend overview contract", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(makeOverviewPayload()));
    const adapter = new ApiResearchAdapter({ apiBaseUrl: "http://api.test/", fetchImpl });
    const result = await adapter.getOverview();

    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/research/overview", expect.objectContaining({ method: "GET", credentials: "omit", cache: "no-store" }));
    expect(result.metrics).toEqual({ families: 7, reusableEvidence: 1, blockedStudies: 2, productionReady: 0 });
    expect(result.families.map((item) => item.id)).toEqual(["A", "B", "C", "D", "E", "F", "G"]);
    expect(result.retainedEvidence[0].id).toBe("EDGE-EVIDENCE-C-COMPRESSION-001");
  });

  it("rejects an unknown contract version with a controlled compatibility error", async () => {
    const payload = makeOverviewPayload({ version: "INTERSIGNAL_RESEARCH_WORKBENCH_V2" });
    const adapter = new ApiResearchAdapter({ fetchImpl: vi.fn().mockResolvedValue(response(payload)) });
    await expect(adapter.getOverview()).rejects.toMatchObject({ code: "RESEARCH_API_INCOMPATIBLE" });
  });

  it("sanitizes HTTP and network errors", async () => {
    const missing = new ApiResearchAdapter({ fetchImpl: vi.fn().mockResolvedValue(response({}, { ok: false, status: 404 })) });
    await expect(missing.getFamily("H")).rejects.toEqual(expect.objectContaining({ code: "RESEARCH_NOT_FOUND", message: "That research record could not be found." }));

    const offline = new ApiResearchAdapter({ fetchImpl: vi.fn().mockRejectedValue(new Error("secret transport detail")) });
    await expect(offline.getOverview()).rejects.toEqual(expect.objectContaining({ code: "RESEARCH_API_UNAVAILABLE", message: "Research data couldn’t be loaded." }));
  });

  it("encodes detail identifiers and supports every read-only resource method", async () => {
    const payload = makeOverviewPayload();
    const fetchImpl = vi.fn().mockResolvedValue(response(payload));
    const adapter = new ApiResearchAdapter({ apiBaseUrl: "http://api.test", fetchImpl });
    await expect(adapter.getEvidenceDetail("EDGE C/001")).rejects.toBeInstanceOf(ResearchApiError);
    expect(fetchImpl.mock.calls[0][0]).toBe("http://api.test/api/research/evidence/EDGE%20C%2F001");
    for (const method of ["getOverview", "getFamilies", "getEvidence", "getValidation", "getBlocked", "getTimeline"]) {
      expect(typeof adapter[method]).toBe("function");
    }
  });
});

describe("Research normalizers", () => {
  it("keeps formal and post-remediation semantics available", () => {
    const result = normalizeOverview(makeOverviewPayload());
    const familyA = result.families[0];
    expect(familyA.currentStatus).toBe("CLOSED_NOT_ADVANCED");
    expect(familyA.decisionStatus).toBe("REJECTED_FOR_CURRENT_CYCLE");
    expect(familyA.validationLabel).toContain("Formal: Inconclusive");
    expect(familyA.validationLabel).toContain("Post-remediation: Fail");
  });

  it("maps customer-facing statuses and restrained tones", () => {
    expect(statusLabel("PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE")).toBe("Blocked by data");
    expect(statusLabel("PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE")).toBe("Blocked by source");
    expect(statusLabel("REJECTED_FOR_CURRENT_CYCLE")).toBe("Not advanced this cycle");
    expect(statusTone("REUSABLE_SIGNAL_ONLY")).toBe("positive");
    expect(statusTone("SOURCE_BLOCKED")).toBe("caution");
    expect(statusTone("UNSUPPORTIVE")).toBe("negative");
  });
});
