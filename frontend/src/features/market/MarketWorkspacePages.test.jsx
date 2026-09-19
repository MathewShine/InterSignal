import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MarketIndicesPage,
  MarketInstrumentPage,
  MarketSectorsPage,
  MarketStocksPage,
  applyMarketTick,
} from "./MarketWorkspacePages.jsx";
import { marketIndicator } from "./components/MarketWorkspaceLayout.jsx";

const instrument = { instrument_id: "NSE:CASH:RELIANCE", symbol: "RELIANCE", display_name: "Reliance Industries", exchange: "NSE", segment: "CASH", instrument_type: "EQUITY", underlying: null, expiry: null };
const quote = { instrument, timestamp: "2026-09-18T10:00:00Z", ltp: "2890.15", change: "12.10", change_pct: "0.42", open: "2875", high: "2905", low: "2861", close: "2890.15", previous_close: "2878.05", volume: 123456, bid: "2889.9", ask: "2890.2", buy_depth: [{ price: "2889.9", quantity: 50 }], sell_depth: [{ price: "2890.2", quantity: 25 }], source: "NSE_OFFICIAL_RECORDED_EOD", freshness: "RECORDED", market_session: "CLOSED" };
const candles = { version: "INTERSIGNAL_MARKET_CANDLES_V1", status: "AVAILABLE", source: "INTERSIGNAL_RECORDED_NSE", interval: "1d", range: "1M", last_recorded_candle_at: "2026-09-18T10:00:00Z", candles: [{ timestamp: "2026-09-17T10:00:00Z", open: "2800", high: "2860", low: "2790", close: "2850", volume: 1000 }, { timestamp: "2026-09-18T10:00:00Z", open: "2850", high: "2905", low: "2840", close: "2890.15", volume: 1234 }] };
const providerStatus = { mode: "SEEDED", provider: "INTERSIGNAL_RECORDED_NSE", configured: true, connected: false, market_session: "CLOSED" };

function response(payload) { return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) }); }

function mockApi({ candlesFail = false } = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
    const value = String(url);
    if (value.includes("provider/status")) return response(providerStatus);
    if (value.includes("instruments/search")) return response({ status: "AVAILABLE", items: [instrument], instrument_master_refreshed_at: "2026-09-18T10:00:00Z" });
    if (value.includes("/quote")) return response({ status: "AVAILABLE", provider_mode: "SEEDED", capabilities: ["QUOTE", "HISTORICAL_CANDLES", "MARKET_DEPTH"], quote });
    if (value.includes("/candles")) return candlesFail ? Promise.reject(new Error("Candle service unavailable")) : response(candles);
    if (value.endsWith("/indices")) return response({ status: "AVAILABLE", provider: "INTERSIGNAL_RECORDED_NSE", items: [{ symbol: "NIFTY_50", name: "NIFTY 50", value: "23779.15", change: "-118.55", change_pct: "-0.49", open: "23890", high: "23910", low: "23700", status: "RECORDED" }] });
    if (value.endsWith("/sectors")) return response({ status: "AVAILABLE", provider: "INTERSIGNAL_RECORDED_NSE", items: [{ sector_id: "NIFTY_AUTO", name: "NIFTY AUTO", index_value: "26100", change_pct: "0.41", breadth_pct: "57", relative_volume: "1.02", coverage_count: 14, expected_count: 15 }] });
    if (value.includes("portfolio/holdings")) return response({ items: [] });
    throw new Error(`Unexpected URL ${value}`);
  });
}

function renderRoute(element, path, entry) {
  return render(<MemoryRouter initialEntries={[entry]}><Routes><Route element={element} path={path} /></Routes></MemoryRouter>);
}

afterEach(() => vi.restoreAllMocks());

describe("Market workspace", () => {
  it("renders the provider-normalized index board", async () => {
    mockApi();
    renderRoute(<MarketIndicesPage />, "/app/market/indices", "/app/market/indices");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Indices" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /NIFTY 50/ })).toBeInTheDocument();
    expect(await screen.findByText("Recorded market data")).toBeInTheDocument();
    expect(screen.queryByText(/buy|sell/i)).not.toBeInTheDocument();
  });

  it("searches the instrument master without rendering the full universe", async () => {
    const user = userEvent.setup();
    mockApi();
    renderRoute(<MarketStocksPage />, "/app/market/stocks", "/app/market/stocks");
    await user.type(screen.getByRole("searchbox"), "RELIANCE");
    expect(await screen.findByRole("link", { name: /Reliance Industries/ })).toHaveAttribute("href", "/app/market/instruments/RELIANCE");
  });

  it("renders quote, chart, depth, research and portfolio truthfully", async () => {
    const user = userEvent.setup();
    mockApi();
    renderRoute(<MarketInstrumentPage />, "/app/market/instruments/:symbol", "/app/market/instruments/RELIANCE");
    expect(await screen.findByRole("heading", { name: "Reliance Industries" })).toBeInTheDocument();
    expect(screen.getByText("Market closed", { exact: true })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Chart" }));
    expect(screen.getByRole("img", { name: /Line chart/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Candlestick" }));
    expect(screen.getByRole("img", { name: /Candlestick chart/ })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Depth" }));
    expect(screen.getByText("2,889.90")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Research" }));
    expect(screen.getByText("No instrument-specific research linked.")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Portfolio" }));
    expect(await screen.findByText("Not currently held")).toBeInTheDocument();
  });

  it("keeps the quote and depth usable when candles fail", async () => {
    const user = userEvent.setup();
    mockApi({ candlesFail: true });
    renderRoute(<MarketInstrumentPage />, "/app/market/instruments/:symbol", "/app/market/instruments/RELIANCE");
    expect(await screen.findByRole("heading", { name: "Reliance Industries" })).toBeInTheDocument();
    expect(screen.getAllByText("2,890.15").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Chart" }));
    expect(screen.getByText("Historical candles are unavailable for this range.")).toBeInTheDocument();
    expect(screen.getByText("Historical candles unavailable; the current quote remains usable.")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Depth" }));
    expect(screen.getByText("2,889.90")).toBeInTheDocument();
  });

  it("renders sector breadth, volume and coverage", async () => {
    mockApi();
    renderRoute(<MarketSectorsPage />, "/app/market/sectors", "/app/market/sectors");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Sectors" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "NIFTY AUTO" })).toBeInTheDocument();
    expect(screen.getByText("14/15")).toBeInTheDocument();
  });

  it("applies only normalized ticks for the active instrument", () => {
    expect(applyMarketTick(quote, { event: "INSTRUMENT_UPDATE", symbol: "RELIANCE", ltp: "2900", freshness: "FRESH" }).ltp).toBe("2900");
    expect(applyMarketTick(quote, { event: "INSTRUMENT_UPDATE", symbol: "TCS", ltp: "4000" })).toBe(quote);
    expect(applyMarketTick(quote, { event: "GROWW_PACKET", symbol: "RELIANCE", ltp: "9999" })).toBe(quote);
  });

  it("labels live data only when the provider stream is connected", () => {
    const base = { mode: "LIVE", configured: true, connected: true, market_session: "OPEN" };
    expect(marketIndicator({ ...base, stream_state: "DISCONNECTED" }).label).toBe("Provider ready");
    expect(marketIndicator({ ...base, stream_state: "CONNECTED" }).label).toBe("Live");
    expect(marketIndicator({ ...base, stream_state: "CONNECTED", market_session: "CLOSED" }).label).toBe("Market closed");
  });
});
