const env = import.meta.env;

export const appConfig = Object.freeze({
  appName: env.VITE_APP_NAME || "InterSignal",
  appStatus: "Research Foundation",
  environment: env.VITE_APP_ENV || env.MODE || "development",
  apiBaseUrl: env.VITE_API_BASE_URL || "",
});

export const runtimeConfigKeys = Object.freeze([
  "appName",
  "appStatus",
  "environment",
  "apiBaseUrl",
]);

