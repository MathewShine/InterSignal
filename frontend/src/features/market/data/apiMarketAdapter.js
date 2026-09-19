import { runtimeConfig } from "../../../config/runtimeConfig.js";
import { MarketDataService } from "./marketDataService.js";
import { MARKET_CONTRACT_VERSION, normalizeMarketSnapshot } from "./marketNormalizers.js";

const MARKET_PROVIDER_TIMEOUT_MS = 60_000;

export class MarketApiError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "MarketApiError";
    this.code = code;
  }
}

export class ApiMarketAdapter extends MarketDataService {
  constructor({ apiBaseUrl = runtimeConfig.apiBaseUrl, fetchImpl = globalThis.fetch, timeoutMs = Math.max(runtimeConfig.homeRequestTimeoutMs, MARKET_PROVIDER_TIMEOUT_MS) } = {}) {
    super();
    if (typeof fetchImpl !== "function") throw new TypeError("ApiMarketAdapter requires a fetch implementation.");
    this.fetchImpl = (...args) => fetchImpl.call(globalThis, ...args);
    this.url = `${apiBaseUrl.replace(/\/+$/, "")}/api/market/snapshot`;
    this.timeoutMs = timeoutMs;
  }

  async getSnapshot({ signal } = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    try {
      const response = await this.fetchImpl(this.url, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) throw new MarketApiError("MARKET_API_HTTP_ERROR", "Market data is unavailable.");
      let payload;
      try { payload = await response.json(); } catch { throw new MarketApiError("MARKET_API_INVALID_RESPONSE", "Market data is unavailable."); }
      if (payload?.version !== MARKET_CONTRACT_VERSION) throw new MarketApiError("MARKET_API_INCOMPATIBLE", "This Market Snapshot version isn’t supported.");
      return normalizeMarketSnapshot(payload);
    } catch (error) {
      if (error instanceof MarketApiError) throw error;
      if (signal?.aborted) throw new MarketApiError("MARKET_API_CANCELLED", "The Market request was cancelled.");
      if (timedOut) throw new MarketApiError("MARKET_API_TIMEOUT", "Market data is unavailable.");
      throw new MarketApiError("MARKET_API_UNAVAILABLE", "Market data is unavailable.");
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", cancel);
    }
  }
}

export const marketDataService = new ApiMarketAdapter();
