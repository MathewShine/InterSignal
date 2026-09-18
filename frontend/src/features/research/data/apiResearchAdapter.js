import { runtimeConfig } from "../../../config/runtimeConfig.js";
import { ResearchDataService } from "./researchDataService.js";
import {
  RESEARCH_CONTRACT_VERSION,
  normalizeBlockedList,
  normalizeEvidenceDetail,
  normalizeEvidenceList,
  normalizeFamilies,
  normalizeFamilyDetail,
  normalizeOverview,
  normalizeTimelineList,
  normalizeValidationList,
} from "./researchNormalizers.js";

export class ResearchApiError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "ResearchApiError";
    this.code = code;
  }
}

export class ApiResearchAdapter extends ResearchDataService {
  constructor({
    apiBaseUrl = runtimeConfig.apiBaseUrl,
    fetchImpl = globalThis.fetch,
    timeoutMs = runtimeConfig.homeRequestTimeoutMs,
  } = {}) {
    super();
    if (typeof fetchImpl !== "function") throw new TypeError("ApiResearchAdapter requires a fetch implementation.");
    this.fetchImpl = (...args) => fetchImpl.call(globalThis, ...args);
    this.baseUrl = `${apiBaseUrl.replace(/\/+$/, "")}/api/research`;
    this.timeoutMs = timeoutMs;
  }

  async request(path, normalizer, { signal } = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.timeoutMs);

    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new ResearchApiError(
          response.status === 404 ? "RESEARCH_NOT_FOUND" : "RESEARCH_API_HTTP_ERROR",
          response.status === 404 ? "That research record could not be found." : "Research data couldn’t be loaded.",
        );
      }
      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new ResearchApiError("RESEARCH_API_INVALID_RESPONSE", "Research data couldn’t be loaded.");
      }
      if (payload?.version !== RESEARCH_CONTRACT_VERSION) {
        throw new ResearchApiError("RESEARCH_API_INCOMPATIBLE", "This Research data version isn’t supported.");
      }
      return normalizer(payload);
    } catch (error) {
      if (error instanceof ResearchApiError) throw error;
      if (signal?.aborted) throw new ResearchApiError("RESEARCH_API_CANCELLED", "The Research request was cancelled.");
      if (timedOut) throw new ResearchApiError("RESEARCH_API_TIMEOUT", "Research data couldn’t be loaded.");
      throw new ResearchApiError("RESEARCH_API_UNAVAILABLE", "Research data couldn’t be loaded.");
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", cancel);
    }
  }

  getOverview(options) { return this.request("/overview", normalizeOverview, options); }
  getFamilies(options) { return this.request("/families", normalizeFamilies, options); }
  getFamily(familyId, options) { return this.request(`/families/${encodeURIComponent(familyId)}`, normalizeFamilyDetail, options); }
  getEvidence(options) { return this.request("/evidence", normalizeEvidenceList, options); }
  getEvidenceDetail(evidenceId, options) { return this.request(`/evidence/${encodeURIComponent(evidenceId)}`, normalizeEvidenceDetail, options); }
  getValidation(options) { return this.request("/validation", normalizeValidationList, options); }
  getBlocked(options) { return this.request("/blocked", normalizeBlockedList, options); }
  getTimeline(options) { return this.request("/timeline", normalizeTimelineList, options); }
}

export const researchDataService = new ApiResearchAdapter();
