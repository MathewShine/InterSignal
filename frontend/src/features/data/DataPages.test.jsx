import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { DataApiError } from "./data/apiDataAdapter.js";
import { DataLineagePage, DataOverviewPage } from "./DataPages.jsx";

const overview = {
  generatedAt: "2026-09-18T12:00:00Z", status: "AVAILABLE", meta: { unavailableSections: [] },
  sources: [
    { id: "daily-history", name: "Daily market history", domain: "MARKET_DATA", status: "AVAILABLE", researchUse: "AVAILABLE", summary: "Daily history available.", freshness: "STATIC_SEEDED_PLATFORM_STATE", coveragePercent: null, gapCount: null, limitations: [] },
    { id: "intraday-continuity", name: "Intraday continuity", domain: "MARKET_DATA", status: "BLOCKED_FOR_RESEARCH_USE", researchUse: "INSUFFICIENT_FOR_TRUSTWORTHY_FORMAL_EVALUATION", summary: "Below threshold.", freshness: "STATIC_SEEDED_PLATFORM_STATE", coveragePercent: 77.826177, gapCount: 217, limitations: ["Research evaluation is blocked."] },
  ],
  lineage: { integrityStatus: "HEALTHY", brokenReferenceCount: 0, nodeCount: 9, edgeCount: 3, artifactCount: 9, stageCounts: { SOURCE: 9 }, nodes: [{ id: "LIN-1", stage: "SOURCE", label: "Frozen Research Artifact", sourceSystem: "INTERSIGNAL", status: "ACTIVE", parentCount: 0, childCount: 1 }] },
  limitations: [{ id: "LIMIT-D", title: "Intraday continuity below frozen threshold", status: "OPEN", severity: "BLOCKING", summary: "77.826177% exact prior-20 continuity leaves 217 unresolved gaps.", impact: "Insufficient for trustworthy formal evaluation.", resolution: "Provide an approved source.", sourceId: "intraday-continuity" }],
};
const service = (overrides = {}) => ({ getOverview: vi.fn().mockResolvedValue(overview), getLineage: vi.fn().mockResolvedValue({ ...overview, lineage: overview.lineage }), ...overrides });
const renderPage = (element, path = "/app/data") => render(<MemoryRouter initialEntries={[path]}><Routes><Route element={element} path="*" /></Routes></MemoryRouter>);

describe("Data pages", () => {
  it("renders backend truth and exposes deep command destinations", async () => {
    const dataService = service();
    const user = userEvent.setup();
    renderPage(<DataOverviewPage dataService={dataService} />);
    expect(await screen.findByRole("heading", { name: "Data", exact: true })).toBeInTheDocument();
    expect(screen.getByText("77.826%")).toBeInTheDocument();
    expect(screen.getByText("217")).toBeInTheDocument();
    expect(screen.getAllByText("Healthy").length).toBeGreaterThan(0);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(dataService.getOverview).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Open command palette" }));
    await user.type(screen.getByRole("textbox", { name: "Search commands" }), "limitations");
    expect(screen.getByRole("option", { name: /Data limitations/i })).toBeInTheDocument();
  });

  it("renders lineage records and a retryable sanitized error", async () => {
    const first = renderPage(<DataLineagePage dataService={service()} />, "/app/data/lineage");
    expect(await screen.findByRole("table", { name: "Recent lineage records" })).toBeInTheDocument();
    expect(screen.getByText("LIN-1")).toBeInTheDocument();
    first.unmount();
    const failing = service({ getOverview: vi.fn().mockRejectedValue(new DataApiError("DATA_API_UNAVAILABLE", "Data health couldn’t be loaded.")) });
    renderPage(<DataOverviewPage dataService={failing} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No demo records have been substituted.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
