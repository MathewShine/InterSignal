import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { KineticHeadline } from "../components/landing/KineticHeadline.jsx";
import { MobileProductPrototype } from "../components/landing/MobileProductPrototype.jsx";
import { MotionProvider } from "../components/motion/index.js";
import { PrimaryAction } from "../components/ui/Actions.jsx";
import { LandingPage } from "./LandingPage.jsx";

describe("kinetic public landing page", () => {
  it("renders the signal hero and six-scene story", async () => {
    const { container } = render(<LandingPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveAccessibleName(
      "SEE THE MARKET. UNDERSTAND THE SIGNAL.",
    );
    expect(await screen.findByRole(
      "heading",
      { name: /Three perspectives.*One connected view/i },
      { timeout: 3000 },
    )).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /MARKET NOISE.*BROUGHT INTO FOCUS/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /YOUR PORTFOLIO.*WITH THE MARKET.*AROUND IT/i })).toBeInTheDocument();
    expect(screen.getAllByText("Research → Market context → Portfolio")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: /SEE MORE.*DECIDE WITH CONTEXT/i })).toBeInTheDocument();
    expect(container.querySelector(".signal-field")).toBeInTheDocument();
    expect(container.querySelector(".perspective-surface")).toBeInTheDocument();
  });

  it("provides public navigation and correct CTA targets", () => {
    render(<LandingPage />);

    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(navigation.querySelector('a[href="#product"]')).toHaveTextContent("Product");
    expect(navigation.querySelector('a[href="#research"]')).toHaveTextContent("Research");
    expect(navigation.querySelector('a[href="#invest"]')).toHaveTextContent("Invest");
    expect(navigation.querySelector('a[href="#trade"]')).toHaveTextContent("Trade");
    expect(navigation.querySelector('a[href="#company"]')).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /More/ })).toHaveAttribute("aria-haspopup", "menu");
    expect(screen.getAllByRole("link", { name: /Explore InterSignal/ }).some((link) => link.getAttribute("href") === "#product")).toBe(true);
    expect(screen.getAllByRole("link", { name: "Sign in" }).every((link) => link.getAttribute("href") === "/auth?mode=signin")).toBe(true);
    expect(document.querySelectorAll(".public-header")).toHaveLength(1);
    expect(document.querySelector(".public-header")).toHaveAttribute("data-theme", "light");
    expect(document.querySelector(".public-header")).toHaveAttribute("data-materialized", "false");
  });

  it("keeps forbidden claims and internal state off the public page", async () => {
    render(<LandingPage />);
    await screen.findAllByText("Research → Market context → Portfolio");
    const publicCopy = document.body.textContent;

    [
      "Family A",
      "Strategy V2",
      "paper readiness",
      "broker disconnected",
      "fake returns",
      "institutional-grade",
      "sovereign",
      "system kernel",
      "cryptographic",
      "deterministic runtime",
    ].forEach((forbidden) => expect(publicCopy).not.toContain(forbidden));
  });

  it("opens a semantic mobile navigation without implementing auth", async () => {
    const user = userEvent.setup();
    render(<LandingPage />);
    const menuButton = screen.getByRole("button", { name: "Open navigation" });

    expect(menuButton).toHaveAttribute("aria-expanded", "false");
    await user.click(menuButton);
    expect(screen.getByRole("navigation", { name: "Mobile navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveAttribute("aria-expanded", "true");
  });

  it("removes persistent progress chrome and preserves the required scene order", async () => {
    const { container } = render(<LandingPage />);
    await screen.findAllByText("Research → Market context → Portfolio");

    expect(container.querySelector(".scene-progress")).not.toBeInTheDocument();
    expect(Array.from(container.querySelectorAll("[data-scene]")).map((scene) => scene.dataset.scene)).toEqual([
      "signal",
      "decompose",
      "focus",
      "portfolio-context",
      "reassemble",
      "resolve",
    ]);
  });

  it("gates the reassembly wordmark behind the final phase threshold", async () => {
    const { container } = render(<LandingPage />);
    await screen.findAllByText("Research → Market context → Portfolio");

    expect(container.querySelector('[data-qa="reassembly-wordmark"]')).toHaveAttribute("data-reveal-threshold", "0.94");
    expect(container.querySelector(".scene-transition-band")).not.toBeInTheDocument();
  });

  it("uses one mobile product prototype instead of a web dashboard in the hero", () => {
    const { container } = render(<LandingPage />);

    expect(screen.getByRole("article", { name: "InterSignal mobile market intelligence prototype" })).toBeInTheDocument();
    expect(container.querySelector(".signal-hero__product")).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-qa="hero-mobile-prototype"]')).toHaveLength(1);
  });

  it("offers Market, Portfolio, and Research as manual mobile-deck states", async () => {
    const user = userEvent.setup();
    render(
      <MotionProvider reducedMotionOverride>
        <MobileProductPrototype />
      </MotionProvider>,
    );

    const prototype = screen.getByRole("article", { name: "InterSignal mobile market intelligence prototype" });
    expect(prototype).toHaveAttribute("data-active-screen", "market");
    expect(screen.getByText(/Momentum/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Portfolio" }));
    expect(prototype).toHaveAttribute("data-active-screen", "portfolio");
    expect(screen.getByText("₹4,82,000")).toBeInTheDocument();
    expect(screen.getByText("Illustrative data. No recommendation.")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Research" }));
    expect(prototype).toHaveAttribute("data-active-screen", "research");
    expect(screen.getByText(/Is participation/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Research" })).toHaveAttribute("aria-selected", "true");
  });

  it("keeps the Market mobile state static when reduced motion is requested", async () => {
    vi.useFakeTimers();
    const { container } = render(
      <MotionProvider reducedMotionOverride>
        <MobileProductPrototype />
      </MotionProvider>,
    );

    await act(async () => {});
    act(() => vi.advanceTimersByTime(20_000));
    expect(container.querySelector('[data-qa="hero-mobile-prototype"]')).toHaveAttribute("data-active-screen", "market");
    vi.useRealTimers();
  });

  it("renders a static headline fallback when reduced motion is requested", async () => {
    const { container } = render(
      <MotionProvider reducedMotionOverride>
        <KineticHeadline />
      </MotionProvider>,
    );

    expect(container.firstChild).toHaveAttribute("data-reduced-motion", "true");
    const line = container.querySelector(".kinetic-headline__line");
    await waitFor(() => expect(line?.style.transform ?? "").not.toContain("translateY"));
  });

  it("avoids horizontal-viewport utility patterns", () => {
    const { container } = render(<LandingPage />);
    const classNames = Array.from(container.querySelectorAll("[class]"))
      .map((element) => element.getAttribute("class"))
      .join(" ");

    expect(container.querySelector(".kinetic-site")).toBeInTheDocument();
    expect(classNames).not.toMatch(/(?:^|\s)(w-screen|min-w-screen|overflow-x-auto|translate-x-full)(?:\s|$)/);
  });

  it("labels every portfolio example as demo data", async () => {
    render(<LandingPage />);
    expect((await screen.findAllByText("Demo portfolio")).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/No recommendation/).length).toBeGreaterThan(0);
  });

  it("keeps the primary action keyboard-focusable", async () => {
    const user = userEvent.setup();
    render(
      <MotionProvider reducedMotionOverride>
        <PrimaryAction href="#product">Explore InterSignal</PrimaryAction>
      </MotionProvider>,
    );

    await user.tab();
    expect(screen.getByRole("link", { name: /Explore InterSignal/ })).toHaveFocus();
  });
});
