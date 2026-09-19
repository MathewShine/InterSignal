import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { marketApiFixture } from "../../test/marketApiFixture.js";
import { MarketApiError } from "./data/apiMarketAdapter.js";
import { normalizeMarketSnapshot } from "./data/marketNormalizers.js";
import { MarketPage } from "./MarketPage.jsx";

const snapshot = normalizeMarketSnapshot(marketApiFixture);
const renderPage = (dataService) => render(<MemoryRouter initialEntries={["/app/market"]}><Routes><Route element={<MarketPage dataService={dataService} />} path="*" /></Routes></MemoryRouter>);

describe("MarketPage", () => {
  it("renders the recorded contract truth from one service request", async () => {
    const dataService = { getSnapshot: vi.fn().mockResolvedValue(snapshot) };
    renderPage(dataService);
    expect(await screen.findByRole("heading", { name: "Market Intelligence" })).toBeInTheDocument();
    expect(dataService.getSnapshot).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText("Recorded market data", { exact: true })[0]).toHaveAttribute("title", "Provider mode: Seeded");
    expect(screen.queryByText("Live market data", { exact: true })).not.toBeInTheDocument();
    expect(screen.getAllByText("Closed", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("Recorded 7 Sep 2026", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText("Historical snapshot", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("498/501 · 99.4012%", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("171", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("325", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("3", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("6,434,397.70", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("0.9296×", { exact: true })).toBeInTheDocument();
    expect(within(screen.getByText("Above VWAP", { exact: true }).closest("div")).getByText("Unavailable", { exact: true })).toBeInTheDocument();
    expect(screen.queryByText(/^0(?:\.0+)?%$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/buy|sell|order ticket/i)).not.toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Sector performance" })).getAllByRole("row")).toHaveLength(24);
  });

  it("sorts all sector rows accessibly", async () => {
    const user = userEvent.setup();
    renderPage({ getSnapshot: vi.fn().mockResolvedValue(snapshot) });
    const table = await screen.findByRole("table", { name: "Sector performance" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Sort sectors" }), "name");
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("NIFTY AUTO");
    await user.selectOptions(screen.getByRole("combobox", { name: "Sort sectors" }), "breadth");
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("NIFTY HEALTHCARE");
  });

  it("keeps healthy sections visible when sector context is unavailable", async () => {
    const partial = { ...snapshot, sectors: [], availability: { ...snapshot.availability, sectors: { status: "UNAVAILABLE", reason: "TEST" } } };
    renderPage({ getSnapshot: vi.fn().mockResolvedValue(partial) });
    expect(await screen.findByText("Sector context is unavailable for this snapshot.")).toBeInTheDocument();
    expect(screen.getByText("171", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("6,434,397.70", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a compact no-fallback error and retries", async () => {
    const user = userEvent.setup();
    const dataService = { getSnapshot: vi.fn().mockRejectedValueOnce(new MarketApiError("MARKET_API_UNAVAILABLE", "Market data is unavailable.")).mockResolvedValueOnce(snapshot) };
    renderPage(dataService);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Research and Portfolio remain accessible.");
    expect(alert).toHaveTextContent("No sample market records have been substituted.");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Market Intelligence" })).toBeInTheDocument();
    expect(dataService.getSnapshot).toHaveBeenCalledTimes(2);
  });
});
