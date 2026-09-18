const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_HOME_REQUEST_TIMEOUT_MS = 7000;

function normalizeBaseUrl(value) {
  return (value || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

function normalizeTimeout(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0
    ? parsed
    : DEFAULT_HOME_REQUEST_TIMEOUT_MS;
}

function normalizeHomeDataMode(value) {
  return value === "demo" ? "demo" : "api";
}

export const runtimeConfig = Object.freeze({
  apiBaseUrl: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL),
  homeDataMode: normalizeHomeDataMode(import.meta.env.VITE_HOME_DATA_MODE),
  homeRequestTimeoutMs: normalizeTimeout(
    import.meta.env.VITE_HOME_REQUEST_TIMEOUT_MS,
  ),
});

export {
  DEFAULT_API_BASE_URL,
  DEFAULT_HOME_REQUEST_TIMEOUT_MS,
  normalizeBaseUrl,
  normalizeHomeDataMode,
  normalizeTimeout,
};
