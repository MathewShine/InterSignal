import { runtimeConfig } from "../../../config/runtimeConfig.js";

const apiRoot = `${runtimeConfig.apiBaseUrl.replace(/\/+$/, "")}/api`;
const marketRoot = `${apiRoot}/market`;

export class MarketWorkspaceApiError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "MarketWorkspaceApiError";
    this.code = code;
  }
}

async function request(path, { signal, method = "GET" } = {}) {
  try {
    const response = await fetch(`${marketRoot}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "omit",
      method,
      signal,
    });
    if (!response.ok) throw new MarketWorkspaceApiError("MARKET_WORKSPACE_HTTP_ERROR", "Market data is unavailable.");
    return await response.json();
  } catch (error) {
    if (error instanceof MarketWorkspaceApiError) throw error;
    if (signal?.aborted) throw new MarketWorkspaceApiError("MARKET_WORKSPACE_CANCELLED", "The Market request was cancelled.");
    throw new MarketWorkspaceApiError("MARKET_WORKSPACE_UNAVAILABLE", "Market data is unavailable.");
  }
}

export const marketWorkspaceApi = {
  getProviderStatus: (options) => request("/provider/status", options),
  search: (query, options) => request(`/instruments/search?q=${encodeURIComponent(query)}`, options),
  getQuote: (symbol, options) => request(`/instruments/${encodeURIComponent(symbol)}/quote`, options),
  getCandles: (symbol, range = "1M", options) => request(`/instruments/${encodeURIComponent(symbol)}/candles?range=${encodeURIComponent(range)}`, options),
  getIndices: (options) => request("/indices", options),
  getIndex: (symbol, options) => request(`/indices/${encodeURIComponent(symbol)}`, options),
  getSectors: (options) => request("/sectors", options),
  getSector: (sectorId, options) => request(`/sectors/${encodeURIComponent(sectorId)}`, options),
  getCurrentSession: (options) => request("/session/current", options),
  getSessions: (options) => request("/sessions", options),
  getSession: (sessionId, options) => request(`/sessions/${encodeURIComponent(sessionId)}`, options),
  getSessionEvents: (sessionId, options) => request(`/sessions/${encodeURIComponent(sessionId)}/events`, options),
  getSessionSummary: (sessionId, options) => request(`/sessions/${encodeURIComponent(sessionId)}/summary`, options),
  startSession: (options = {}) => request("/session/start", { ...options, method: "POST" }),
  stopSession: (options = {}) => request("/session/stop", { ...options, method: "POST" }),
  async getPortfolioContext(symbol, { signal } = {}) {
    const response = await fetch(`${apiRoot}/portfolio/holdings`, {
      headers: { Accept: "application/json" }, cache: "no-store", credentials: "omit", signal,
    });
    if (!response.ok) return null;
    const payload = await response.json();
    return (payload.items ?? []).find((item) => item.symbol?.toUpperCase() === symbol.toUpperCase()) ?? null;
  },
};

export async function searchMarketInstruments(query, options) {
  if (query.trim().length < 2) return [];
  const payload = await marketWorkspaceApi.search(query, options);
  return (payload.items ?? []).map((item) => ({
    id: item.instrument_id,
    group: "Market",
    label: `${item.display_name} · ${item.exchange} · ${item.symbol}`,
    path: item.instrument_type === "INDEX"
      ? `/app/market/indices/${encodeURIComponent(item.symbol)}`
      : `/app/market/instruments/${encodeURIComponent(item.symbol)}`,
  }));
}

export function marketStreamUrl() {
  return `${marketRoot.replace(/^http/, "ws")}/stream`;
}

export function marketSessionSummaryUrl(sessionId) {
  return `${marketRoot}/sessions/${encodeURIComponent(sessionId)}/summary`;
}
