import { runtimeConfig } from "../../../config/runtimeConfig.js";
import { DataHealthService } from "./dataHealthService.js";
import {
  DATA_CONTRACT_VERSION,
  normalizeDataLimitations,
  normalizeDataLineage,
  normalizeDataOverview,
  normalizeDataSources,
} from "./dataNormalizers.js";

export class DataApiError extends Error {
  constructor(code, message) { super(message); this.name = "DataApiError"; this.code = code; }
}

export class ApiDataAdapter extends DataHealthService {
  constructor({ apiBaseUrl = runtimeConfig.apiBaseUrl, fetchImpl = globalThis.fetch, timeoutMs = runtimeConfig.homeRequestTimeoutMs } = {}) {
    super();
    if (typeof fetchImpl !== "function") throw new TypeError("ApiDataAdapter requires a fetch implementation.");
    this.fetchImpl = (...args) => fetchImpl.call(globalThis, ...args);
    this.baseUrl = `${apiBaseUrl.replace(/\/+$/, "")}/api/data`;
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
      if (!response.ok) throw new DataApiError("DATA_API_HTTP_ERROR", "Data health couldn’t be loaded.");
      let payload;
      try { payload = await response.json(); } catch { throw new DataApiError("DATA_API_INVALID_RESPONSE", "Data health couldn’t be loaded."); }
      if (payload?.version !== DATA_CONTRACT_VERSION) throw new DataApiError("DATA_API_INCOMPATIBLE", "This Data Health version isn’t supported.");
      return normalizer(payload);
    } catch (error) {
      if (error instanceof DataApiError) throw error;
      if (signal?.aborted) throw new DataApiError("DATA_API_CANCELLED", "The Data request was cancelled.");
      if (timedOut) throw new DataApiError("DATA_API_TIMEOUT", "Data health couldn’t be loaded.");
      throw new DataApiError("DATA_API_UNAVAILABLE", "Data health couldn’t be loaded.");
    } finally { clearTimeout(timeout); signal?.removeEventListener("abort", cancel); }
  }
  getOverview(options) { return this.request("/overview", normalizeDataOverview, options); }
  getSources(options) { return this.request("/sources", normalizeDataSources, options); }
  getLineage(options) { return this.request("/lineage", normalizeDataLineage, options); }
  getLimitations(options) { return this.request("/limitations", normalizeDataLimitations, options); }
}

export const dataHealthService = new ApiDataAdapter();
