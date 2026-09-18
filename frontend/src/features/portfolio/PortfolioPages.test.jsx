import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { PortfolioApiError } from "./data/apiPortfolioAdapter.js";
import { normalizeActivityList, normalizeHoldings, normalizeOverview, normalizePerformanceResponse } from "./data/portfolioNormalizers.js";
import { PortfolioActivityPage, PortfolioHoldingsPage, PortfolioOverviewPage, PortfolioPerformancePage } from "./PortfolioPages.jsx";
import { makeActivityPayload, makeEmptyPortfolio, makeHoldingsPayload, makePerformancePayload, makePortfolioOverview } from "../../test/portfolioApiFixture.js";

function makeService(overrides = {}) {
  return {
    getOverview: vi.fn().mockResolvedValue(normalizeOverview(makePortfolioOverview())),
    getHoldings: vi.fn().mockResolvedValue(normalizeHoldings(makeHoldingsPayload())),
    getActivity: vi.fn().mockResolvedValue(normalizeActivityList(makeActivityPayload())),
    getPerformance: vi.fn().mockResolvedValue(normalizePerformanceResponse(makePerformancePayload())),
    ...overrides,
  };
}

function renderPage(element, path = "/app/portfolio") {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route element={element} path="*" /></Routes></MemoryRouter>);
}

describe("Portfolio overview", () => {
  it("renders backend summary, allocation, holdings, P&L and activity", async () => {
    const service = makeService();
    renderPage(<PortfolioOverviewPage dataService={service} />);
    expect(await screen.findByRole("heading", { name: "Portfolio", exact: true })).toBeInTheDocument();
    const summary = within(screen.getByRole("region", { name: "Portfolio summary" }));
    expect(summary.getByText("₹52,393")).toBeInTheDocument();
    expect(summary.getByText("₹10,000")).toBeInTheDocument();
    expect(summary.getByText("₹42,393")).toBeInTheDocument();
    expect(screen.getAllByText("Demo portfolio").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Synthetic Mutual Fund One").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Diversified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+4.79%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("₹397.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("₹1,996.00").length).toBeGreaterThan(0);
    expect(screen.getByText("Sell")).toBeInTheDocument();
    expect(service.getOverview).toHaveBeenCalledTimes(1);
  });

  it("opens a keyboard-accessible holding detail with FIFO lots", async () => {
    const user = userEvent.setup();
    renderPage(<PortfolioOverviewPage dataService={makeService()} />);
    await screen.findByRole("heading", { name: "Portfolio", exact: true });
    await user.click(screen.getAllByRole("button", { name: "View" })[0]);
    const dialog = screen.getByRole("dialog", { name: /Synthetic Mutual Fund One holding detail/ });
    expect(dialog).toHaveTextContent("FIFO lots");
    expect(dialog).toHaveTextContent("Partly realised");
    expect(within(dialog).getByRole("button", { name: "Close holding detail" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: /holding detail/ })).not.toBeInTheDocument();
  });

  it("keeps available sections visible in a partial response", async () => {
    const payload = makePortfolioOverview({ status: "PARTIAL", reason: "PORTFOLIO_SECTIONS_UNAVAILABLE", performance: null, meta: { ...makePortfolioOverview().meta, unavailable_sections: ["performance"] } });
    const service = makeService({ getOverview: vi.fn().mockResolvedValue(normalizeOverview(payload)) });
    renderPage(<PortfolioOverviewPage dataService={service} />);
    expect(await screen.findByText(/temporarily unavailable: performance/)).toBeInTheDocument();
    expect(screen.getAllByText("Synthetic Mutual Fund One").length).toBeGreaterThan(0);
    expect(screen.getByText("Performance data unavailable.")).toBeInTheDocument();
  });

  it("shows an honest empty state without fake holdings", async () => {
    const service = makeService({ getOverview: vi.fn().mockResolvedValue(normalizeOverview(makeEmptyPortfolio())) });
    renderPage(<PortfolioOverviewPage dataService={service} />);
    expect(await screen.findByRole("heading", { name: "No portfolio yet." })).toBeInTheDocument();
    expect(screen.getByText("Add holdings manually.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Connect broker/ })).toBeDisabled();
    expect(screen.queryByText("Synthetic Mutual Fund One")).not.toBeInTheDocument();
  });

  it("shows shaped loading then a sanitized retryable error", async () => {
    const pending = makeService({ getOverview: vi.fn(() => new Promise(() => {})) });
    const first = renderPage(<PortfolioOverviewPage dataService={pending} />);
    expect(screen.getByRole("status", { name: "Loading Portfolio" })).toBeInTheDocument();
    first.unmount();
    const failing = makeService({ getOverview: vi.fn().mockRejectedValue(new PortfolioApiError("PORTFOLIO_API_UNAVAILABLE", "Portfolio data couldn’t be loaded.")) });
    renderPage(<PortfolioOverviewPage dataService={failing} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Portfolio data couldn’t be loaded.");
    expect(screen.getByText("No demo holdings have been substituted.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("retries after an error", async () => {
    const service = makeService();
    service.getOverview.mockRejectedValueOnce(new PortfolioApiError("PORTFOLIO_API_UNAVAILABLE", "Portfolio data couldn’t be loaded.")).mockResolvedValueOnce(normalizeOverview(makePortfolioOverview()));
    const user = userEvent.setup();
    renderPage(<PortfolioOverviewPage dataService={service} />);
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("₹52,393")).toBeInTheDocument();
    expect(service.getOverview).toHaveBeenCalledTimes(2);
  });
});

describe("Portfolio detail routes", () => {
  it("searches, filters and sorts holdings", async () => {
    const user = userEvent.setup();
    renderPage(<PortfolioHoldingsPage dataService={makeService()} />, "/app/portfolio/holdings");
    expect(await screen.findByRole("heading", { name: "Holdings", exact: true })).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search" }), "missing");
    expect(screen.getByText("No holdings in this portfolio.")).toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox", { name: "Search" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Sector" }), "Diversified");
    expect(screen.getAllByText("Synthetic Mutual Fund One").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Sort by Security" }));
    expect(screen.getByText(/sorted by name ascending/i)).toBeInTheDocument();
  });

  it("renders backend activity and performance routes", async () => {
    const activity = renderPage(<PortfolioActivityPage dataService={makeService()} />, "/app/portfolio/activity");
    expect(await screen.findByRole("heading", { name: "Portfolio activity", exact: true })).toBeInTheDocument();
    expect(screen.getByText("Sell")).toBeInTheDocument();
    activity.unmount();
    renderPage(<PortfolioPerformancePage dataService={makeService()} />, "/app/portfolio/performance");
    expect(await screen.findByRole("heading", { name: "Performance", exact: true, level: 1 })).toBeInTheDocument();
    expect(screen.getByText("2 valuation dates")).toBeInTheDocument();
    expect(screen.getByText(/No time series has been inferred/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Recorded Portfolio OS performance points" })).toBeInTheDocument();
  });

  it("exposes all Portfolio command destinations", async () => {
    const user = userEvent.setup();
    renderPage(<PortfolioOverviewPage dataService={makeService()} />);
    await screen.findByRole("heading", { name: "Portfolio", exact: true });
    await user.click(screen.getByRole("button", { name: "Open command palette" }));
    const input = screen.getByRole("textbox", { name: "Search commands" });
    for (const label of ["Portfolio", "Holdings", "Portfolio activity", "Performance"]) {
      await user.clear(input);
      await user.type(input, label);
      expect(screen.getAllByRole("option", { name: new RegExp(label, "i") }).length).toBeGreaterThan(0);
    }
  });
});
