import { runtimeConfig } from "../../../config/runtimeConfig.js";
import { GovernanceDataService } from "./governanceDataService.js";
import {
  GOVERNANCE_CONTRACT_VERSION,
  normalizeGovernanceAudit,
  normalizeGovernanceAuthorizations,
  normalizeGovernanceOverview,
  normalizeGovernancePolicies,
  normalizeGovernanceReadiness,
} from "./governanceNormalizers.js";

export class GovernanceApiError extends Error {
  constructor(code, message) { super(message); this.name = "GovernanceApiError"; this.code = code; }
}
export class ApiGovernanceAdapter extends GovernanceDataService {
  constructor({ apiBaseUrl = runtimeConfig.apiBaseUrl, fetchImpl = globalThis.fetch, timeoutMs = runtimeConfig.homeRequestTimeoutMs } = {}) {
    super();
    if (typeof fetchImpl !== "function") throw new TypeError("ApiGovernanceAdapter requires a fetch implementation.");
    this.fetchImpl = (...args) => fetchImpl.call(globalThis, ...args);
    this.baseUrl = `${apiBaseUrl.replace(/\/+$/, "")}/api/governance`;
    this.timeoutMs = timeoutMs;
  }
  async request(path, normalizer, { signal } = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, { method: "GET", headers: { Accept: "application/json" }, cache: "no-store", credentials: "omit", signal: controller.signal });
      if (!response.ok) throw new GovernanceApiError("GOVERNANCE_API_HTTP_ERROR", "Governance data couldn’t be loaded.");
      let payload;
      try { payload = await response.json(); } catch { throw new GovernanceApiError("GOVERNANCE_API_INVALID_RESPONSE", "Governance data couldn’t be loaded."); }
      if (payload?.version !== GOVERNANCE_CONTRACT_VERSION) throw new GovernanceApiError("GOVERNANCE_API_INCOMPATIBLE", "This Governance version isn’t supported.");
      return normalizer(payload);
    } catch (error) {
      if (error instanceof GovernanceApiError) throw error;
      if (signal?.aborted) throw new GovernanceApiError("GOVERNANCE_API_CANCELLED", "The Governance request was cancelled.");
      if (timedOut) throw new GovernanceApiError("GOVERNANCE_API_TIMEOUT", "Governance data couldn’t be loaded.");
      throw new GovernanceApiError("GOVERNANCE_API_UNAVAILABLE", "Governance data couldn’t be loaded.");
    } finally { clearTimeout(timeout); signal?.removeEventListener("abort", cancel); }
  }
  getOverview(options) { return this.request("/overview", normalizeGovernanceOverview, options); }
  getReadiness(options) { return this.request("/readiness", normalizeGovernanceReadiness, options); }
  getPolicies(options) { return this.request("/policies", normalizeGovernancePolicies, options); }
  getAuthorizations(options) { return this.request("/authorizations", normalizeGovernanceAuthorizations, options); }
  getAudit(options) { return this.request("/audit", normalizeGovernanceAudit, options); }
}
export const governanceDataService = new ApiGovernanceAdapter();
