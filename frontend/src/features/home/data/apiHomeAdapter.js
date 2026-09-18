import { runtimeConfig } from "../../../config/runtimeConfig.js";
import { HomeDataService } from "./homeDataServiceBase.js";
import {
  HOME_SNAPSHOT_CONTRACT_VERSION,
  normalizeHomeSnapshot,
} from "./homeSnapshotNormalizer.js";

export class HomeApiError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "HomeApiError";
    this.code = code;
  }
}

export class ApiHomeAdapter extends HomeDataService {
  constructor({
    apiBaseUrl = runtimeConfig.apiBaseUrl,
    fetchImpl = globalThis.fetch,
    timeoutMs = runtimeConfig.homeRequestTimeoutMs,
  } = {}) {
    super();
    if (typeof fetchImpl !== "function") {
      throw new TypeError("ApiHomeAdapter requires a fetch implementation.");
    }
    this.fetchImpl = (...args) => fetchImpl.call(globalThis, ...args);
    this.timeoutMs = timeoutMs;
    this.url = `${apiBaseUrl.replace(/\/+$/, "")}/api/home/snapshot`;
  }

  async getHomeSnapshot({ signal } = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const cancelRequest = () => controller.abort();
    signal?.addEventListener("abort", cancelRequest, { once: true });
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.timeoutMs);

    try {
      const response = await this.fetchImpl(this.url, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new HomeApiError(
          "HOME_API_HTTP_ERROR",
          "Unable to load this context.",
        );
      }

      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new HomeApiError(
          "HOME_API_INVALID_RESPONSE",
          "Unable to load this context.",
        );
      }
      if (payload?.version !== HOME_SNAPSHOT_CONTRACT_VERSION) {
        throw new HomeApiError(
          "HOME_API_UNSUPPORTED_CONTRACT",
          "This Home data contract is not supported.",
        );
      }
      return normalizeHomeSnapshot(payload);
    } catch (error) {
      if (error instanceof HomeApiError) throw error;
      if (timedOut) {
        throw new HomeApiError(
          "HOME_API_TIMEOUT",
          "The Home request timed out.",
        );
      }
      if (signal?.aborted) {
        throw new HomeApiError(
          "HOME_API_CANCELLED",
          "The Home request was cancelled.",
        );
      }
      throw new HomeApiError(
        "HOME_API_UNAVAILABLE",
        "Unable to load this context.",
      );
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", cancelRequest);
    }
  }
}
