import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { makeHomeApiPayload } from "../../test/homeApiFixture.js";
import { HomePage } from "./HomePage.jsx";
import { HomeApiError } from "./data/apiHomeAdapter.js";
import { DemoHomeAdapter } from "./data/homeDataService.js";
import { normalizeHomeSnapshot } from "./data/homeSnapshotNormalizer.js";

function renderHome({ service = new DemoHomeAdapter(), path = "/app" } = {}) {
  return render(<MemoryRouter initialEntries={[path]}><HomePage dataService={service} reducedMotionOverride /></MemoryRouter>);
}

describe("InterSignal Intelligence Home", () => {
  it("renders the shell, compact overview and primary intelligence surfaces", async () => {
    renderHome();
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Application navigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Market overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Portfolio" })).toBeInTheDocument();
    expect(screen.getByText("Sample market data")).toBeInTheDocument();
  });

  it("links attention selection to market and portfolio context", async () => {
    const user = userEvent.setup();
    const { container } = renderHome();
    await screen.findByRole("heading", { name: "Important today" });

    await user.click(screen.getByRole("button", { name: /Technology momentum softened/ }));
    expect(container.querySelector(".market-canvas")).toHaveAttribute("data-active-context", "sector");
    expect(container.querySelector('[title="Technology 9%"]')).toHaveClass("is-active");
  });

  it("represents research and data truthfully", async () => {
    renderHome();
    expect(await screen.findByText("Compression evidence retained")).toBeInTheDocument();
    expect(screen.getByText(/Not production strategy/)).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Production-ready").parentElement).toHaveTextContent("0");
  });

  it("opens and searches the keyboard-accessible command palette", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByRole("heading", { name: "Overview" });

    await user.click(screen.getByRole("button", { name: "Open command palette" }));
    const search = screen.getByRole("textbox", { name: "Search commands" });
    await user.type(search, "Family D");
    expect(screen.getByRole("option", { name: /Family D continuity blocker/ })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument());
  });

  it("renders desktop rail and mobile navigation destinations", async () => {
    renderHome();
    await screen.findByRole("heading", { name: "Overview" });
    expect(within(screen.getByRole("navigation", { name: "Primary app" })).getByRole("link", { name: "Research" })).toHaveAttribute("href", "/app/research");
    expect(screen.getByRole("navigation", { name: "Mobile app" })).toBeInTheDocument();
  });

  it("opens contextual Research, Data, Governance and Alerts detail", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByRole("heading", { name: "Overview" });
    await user.click(screen.getAllByRole("button", { name: "Open contextual drawer" })[0]);
    expect(screen.getByRole("dialog", { name: "Context drawer" })).toBeInTheDocument();
    expect(screen.getByText("Research", { selector: ".context-drawer__section-label" })).toBeInTheDocument();
    expect(screen.getByText("Governance", { selector: ".context-drawer__section-label" })).toBeInTheDocument();
  });

  it("provides an honest empty-portfolio experience", async () => {
    renderHome({ service: new DemoHomeAdapter({ scenario: "empty-portfolio" }) });
    expect(await screen.findByRole("heading", { name: "No portfolio yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Connect broker/ })).toBeDisabled();
    expect(screen.getByText("Coming later")).toBeInTheDocument();
  });

  it("keeps Home useful when market or research context is unavailable", async () => {
    const { unmount } = renderHome({ service: new DemoHomeAdapter({ scenario: "no-market" }) });
    expect(await screen.findByText("Market information is unavailable right now.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /portfolio/i })).toBeInTheDocument();
    unmount();

    renderHome({ service: new DemoHomeAdapter({ scenario: "research-unavailable" }) });
    expect(await screen.findByText("Research information is unavailable right now.")).toBeInTheDocument();
  });

  it("shows a local loading state while the service resolves", () => {
    const service = { getHomeSnapshot: vi.fn(() => new Promise(() => {})) };
    renderHome({ service });
    expect(screen.getByText("Loading your overview…")).toBeInTheDocument();
  });

  it("renders a sanitized disconnected view with retry rather than demo domains", async () => {
    renderHome({ service: new DemoHomeAdapter({ scenario: "error" }) });
    expect(await screen.findByRole("status")).toHaveTextContent("Some data couldn’t be refreshed");
    expect(screen.getByRole("heading", { name: "Market overview" })).toBeInTheDocument();
    expect(screen.getByText("Research information is unavailable right now.")).toBeInTheDocument();
    expect(screen.getByText("Portfolio information is unavailable right now.")).toBeInTheDocument();
    expect(screen.getByText("Readiness information is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("does not treat unavailable live market data as an API failure", async () => {
    const service = {
      getHomeSnapshot: vi.fn().mockResolvedValue(
        normalizeHomeSnapshot(makeHomeApiPayload()),
      ),
    };
    renderHome({ service });

    expect(await screen.findByText("Sample market data")).toBeInTheDocument();
    expect(screen.getByText("Demo portfolio")).toBeInTheDocument();
    expect(screen.getByText("Compression evidence retained")).toBeInTheDocument();
    expect(screen.queryByText("Some data couldn’t be refreshed.")).not.toBeInTheDocument();
    expect(service.getHomeSnapshot).toHaveBeenCalledTimes(1);
  });

  it("renders API-derived partial domains independently", async () => {
    const payload = makeHomeApiPayload({
      portfolio: {
        status: "UNAVAILABLE",
        reason: "PORTFOLIO_SOURCE_UNAVAILABLE",
        has_portfolio: false,
      },
    });
    const service = {
      getHomeSnapshot: vi.fn().mockResolvedValue(normalizeHomeSnapshot(payload)),
    };
    renderHome({ service });

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Research" })).toBeInTheDocument();
    expect(screen.getByText("Portfolio information is unavailable right now.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Readiness" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Data health" })).toBeInTheDocument();
    expect(screen.getByText("Sample market data")).toBeInTheDocument();
    expect(screen.queryByText("Some data couldn’t be refreshed.")).not.toBeInTheDocument();
    expect(screen.queryByText(/BACKEND|API CONNECTED|LOCAL DATA/)).not.toBeInTheDocument();
  });

  it("uses the API empty-portfolio state without synthetic fallback", async () => {
    const payload = makeHomeApiPayload({
      portfolio: {
        status: "AVAILABLE",
        reason: "NO_PORTFOLIO_CONFIGURED",
        has_portfolio: false,
        portfolio_count: 0,
        source_type: "NONE",
      },
    });
    const service = {
      getHomeSnapshot: vi.fn().mockResolvedValue(normalizeHomeSnapshot(payload)),
    };
    renderHome({ service });

    expect(await screen.findByRole("heading", { name: "No portfolio yet" })).toBeInTheDocument();
    expect(screen.queryByText("Demo portfolio")).not.toBeInTheDocument();
  });

  it("focuses backend operational attention on its source domain", async () => {
    const snapshot = normalizeHomeSnapshot(makeHomeApiPayload());
    const service = { getHomeSnapshot: vi.fn().mockResolvedValue(snapshot) };
    const { container } = renderHome({ service });

    expect(await screen.findByRole("heading", { name: "Important today" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Family D research remains blocked/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Technology momentum softened/ })).not.toBeInTheDocument();
    expect(container.querySelector(".research-pulse")).toHaveClass("is-context-focused");
    expect(container.querySelector(".market-canvas")).toHaveAttribute("data-active-context", "breadth");
  });

  it("retries a failed API request without reloading the page", async () => {
    const service = {
      getHomeSnapshot: vi.fn()
        .mockRejectedValueOnce(new HomeApiError("HOME_API_UNAVAILABLE", "Unable to load this context."))
        .mockResolvedValueOnce(normalizeHomeSnapshot(makeHomeApiPayload())),
    };
    const user = userEvent.setup();
    renderHome({ service });

    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(service.getHomeSnapshot).toHaveBeenCalledTimes(2);
  });

  it("cancels the in-flight request when Home unmounts", () => {
    let requestSignal;
    const service = {
      getHomeSnapshot: vi.fn(({ signal }) => {
        requestSignal = signal;
        return new Promise(() => {});
      }),
    };
    const { unmount } = renderHome({ service });
    unmount();
    expect(requestSignal.aborted).toBe(true);
  });
});
