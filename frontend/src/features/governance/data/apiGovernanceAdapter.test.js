import { describe, expect, it, vi } from "vitest";
import { ApiGovernanceAdapter } from "./apiGovernanceAdapter.js";

const payload = {
  version: "INTERSIGNAL_GOVERNANCE_V1", generated_at: "2026-09-18T12:00:00Z", status: "AVAILABLE", reason: null,
  meta: { read_only: true, source_contract: "GOVERNANCE", unavailable_sections: [] },
  summary: { paper_readiness: "NOT_READY", live_readiness: "NOT_READY", broker_readiness: "NOT_READY", production_readiness: "NOT_READY", broker_connection_state: "NOT_CONNECTED", blocking_violation_count: 0, open_violation_count: 0, pending_authorization_count: 1, approved_authorization_count: 0, passing_policy_count: 8, total_policy_count: 8, policy_passes_imply_readiness: false, integrity_status: "HEALTHY" },
  readiness: [], policies: [], authorizations: [], recent_audit: [], manual_overrides: [],
};
const response = (value) => ({ ok: true, status: 200, json: vi.fn().mockResolvedValue(value) });

describe("ApiGovernanceAdapter", () => {
  it("uses one overview request and preserves readiness semantics", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response(payload));
    const result = await new ApiGovernanceAdapter({ apiBaseUrl: "http://api.test/", fetchImpl }).getOverview();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/governance/overview", expect.objectContaining({ method: "GET", cache: "no-store" }));
    expect(result.summary).toMatchObject({ paperReadiness: "NOT_READY", brokerConnectionState: "NOT_CONNECTED", passingPolicyCount: 8, policyPassesImplyReadiness: false });
  });

  it("exposes all read resources and rejects incompatible contracts", async () => {
    const adapter = new ApiGovernanceAdapter({ fetchImpl: vi.fn() });
    for (const method of ["getOverview", "getReadiness", "getPolicies", "getAuthorizations", "getAudit"]) expect(typeof adapter[method]).toBe("function");
    const incompatible = new ApiGovernanceAdapter({ fetchImpl: vi.fn().mockResolvedValue(response({ ...payload, version: "V2" })) });
    await expect(incompatible.getOverview()).rejects.toMatchObject({ code: "GOVERNANCE_API_INCOMPATIBLE" });
    const offline = new ApiGovernanceAdapter({ fetchImpl: vi.fn().mockRejectedValue(new Error("private detail")) });
    await expect(offline.getOverview()).rejects.toMatchObject({ code: "GOVERNANCE_API_UNAVAILABLE", message: "Governance data couldn’t be loaded." });
  });
});
