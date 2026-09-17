import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage.jsx";
import { DemoHomeAdapter } from "./data/homeDataService.js";

function renderHome({ service = new DemoHomeAdapter(), path = "/app" } = {}) {
  return render(<MemoryRouter initialEntries={[path]}><HomePage dataService={service} reducedMotionOverride /></MemoryRouter>);
}

describe("InterSignal Intelligence Home", () => {
  it("renders the shell, greeting and dominant intelligence canvas", async () => {
    renderHome();
    expect(await screen.findByRole("heading", { name: "Here’s what matters." })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Application navigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NIFTY 500" })).toBeInTheDocument();
    expect(screen.getByText("DEMO / LOCAL DATA")).toBeInTheDocument();
  });

  it("links attention selection to market and portfolio context", async () => {
    const user = userEvent.setup();
    const { container } = renderHome();
    await screen.findByRole("heading", { name: "What deserves attention" });

    await user.click(screen.getByRole("button", { name: /Technology momentum softened/ }));
    expect(container.querySelector(".market-canvas")).toHaveAttribute("data-active-context", "sector");
    expect(container.querySelector('[title="Technology 9%"]')).toHaveClass("is-active");
  });

  it("represents research and data truthfully", async () => {
    renderHome();
    expect(await screen.findByText("Family C compression")).toBeInTheDocument();
    expect(screen.getByText(/Not production strategy/)).toBeInTheDocument();
    expect(screen.getByText("Source blocked")).toBeInTheDocument();
    expect(screen.getByText("Broken refs").parentElement).toHaveTextContent("0");
  });

  it("opens and searches the keyboard-accessible command palette", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByRole("heading", { name: "Here’s what matters." });

    await user.click(screen.getByRole("button", { name: "Open command palette" }));
    const search = screen.getByRole("textbox", { name: "Search commands" });
    await user.type(search, "Family D");
    expect(screen.getByRole("option", { name: /Family D continuity blocker/ })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument());
  });

  it("renders desktop rail and mobile navigation destinations", async () => {
    renderHome();
    await screen.findByRole("heading", { name: "Here’s what matters." });
    expect(within(screen.getByRole("navigation", { name: "Primary app" })).getByRole("link", { name: "Research" })).toHaveAttribute("href", "/app/research");
    expect(screen.getByRole("navigation", { name: "Mobile app" })).toBeInTheDocument();
  });

  it("opens contextual Research, Data, Governance and Alerts detail", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByRole("heading", { name: "Here’s what matters." });
    await user.click(screen.getAllByRole("button", { name: "Open contextual drawer" })[0]);
    expect(screen.getByRole("dialog", { name: "Context drawer" })).toBeInTheDocument();
    expect(screen.getByText("Research", { selector: ".context-drawer__section-label" })).toBeInTheDocument();
    expect(screen.getByText("Governance", { selector: ".context-drawer__section-label" })).toBeInTheDocument();
  });

  it("provides an honest empty-portfolio experience", async () => {
    renderHome({ service: new DemoHomeAdapter({ scenario: "empty-portfolio" }) });
    expect(await screen.findByRole("heading", { name: "No portfolio connected yet." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Connect broker/ })).toBeDisabled();
    expect(screen.getByText("Coming later")).toBeInTheDocument();
  });

  it("keeps Home useful when market or research context is unavailable", async () => {
    const { unmount } = renderHome({ service: new DemoHomeAdapter({ scenario: "no-market" }) });
    expect(await screen.findByRole("heading", { name: "Market context unavailable." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /portfolio/i })).toBeInTheDocument();
    unmount();

    renderHome({ service: new DemoHomeAdapter({ scenario: "research-unavailable" }) });
    expect(await screen.findByRole("heading", { name: "Research context unavailable." })).toBeInTheDocument();
  });

  it("shows a local loading state while the service resolves", () => {
    const service = { getHomeSnapshot: vi.fn(() => new Promise(() => {})) };
    renderHome({ service });
    expect(screen.getByText(/Assembling market, portfolio and research context/)).toBeInTheDocument();
  });

  it("renders an inline error with retry rather than a full-page failure", async () => {
    renderHome({ service: new DemoHomeAdapter({ scenario: "error" }) });
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
