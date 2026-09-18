import { runtimeConfig } from "../../../config/runtimeConfig.js";
import { PortfolioDataService } from "./portfolioDataService.js";
import {
  PORTFOLIO_CONTRACT_VERSION,
  normalizeActivityList,
  normalizeHoldings,
  normalizeOverview,
  normalizePerformanceResponse,
} from "./portfolioNormalizers.js";

export class PortfolioApiError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "PortfolioApiError";
    this.code = code;
  }
}

export class ApiPortfolioAdapter extends PortfolioDataService {
  constructor({
    apiBaseUrl = runtimeConfig.apiBaseUrl,
    fetchImpl = globalThis.fetch,
    timeoutMs = runtimeConfig.homeRequestTimeoutMs,
  } = {}) {
    super();
    if (typeof fetchImpl !== "function") throw new TypeError("ApiPortfolioAdapter requires a fetch implementation.");
    this.fetchImpl = (...args) => fetchImpl.call(globalThis, ...args);
    this.baseUrl = `${apiBaseUrl.replace(/\/+$/, "")}/api/portfolio`;
    this.timeoutMs = timeoutMs;
  }

  async request(path, normalizer, { signal, portfolioId } = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    const query = portfolioId ? `?portfolio_id=${encodeURIComponent(portfolioId)}` : "";
    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}${query}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new PortfolioApiError(
          response.status === 404 ? "PORTFOLIO_NOT_FOUND" : "PORTFOLIO_API_HTTP_ERROR",
          response.status === 404 ? "That portfolio could not be found." : "Portfolio data couldn’t be loaded.",
        );
      }
      let payload;
      try { payload = await response.json(); } catch {
        throw new PortfolioApiError("PORTFOLIO_API_INVALID_RESPONSE", "Portfolio data couldn’t be loaded.");
      }
      if (payload?.version !== PORTFOLIO_CONTRACT_VERSION) {
        throw new PortfolioApiError("PORTFOLIO_API_INCOMPATIBLE", "This Portfolio data version isn’t supported.");
      }
      return normalizer(payload);
    } catch (error) {
      if (error instanceof PortfolioApiError) throw error;
      if (signal?.aborted) throw new PortfolioApiError("PORTFOLIO_API_CANCELLED", "The Portfolio request was cancelled.");
      if (timedOut) throw new PortfolioApiError("PORTFOLIO_API_TIMEOUT", "Portfolio data couldn’t be loaded.");
      throw new PortfolioApiError("PORTFOLIO_API_UNAVAILABLE", "Portfolio data couldn’t be loaded.");
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", cancel);
    }
  }

  getOverview(options) { return this.request("/overview", normalizeOverview, options); }
  getHoldings(options) { return this.request("/holdings", normalizeHoldings, options); }
  getActivity(options) { return this.request("/activity", normalizeActivityList, options); }
  getPerformance(options) { return this.request("/performance", normalizePerformanceResponse, options); }
}

export const portfolioDataService = new ApiPortfolioAdapter();
