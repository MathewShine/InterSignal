import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ResearchApiError } from "./data/apiResearchAdapter.js";
import {
  normalizeBlockedList,
  normalizeEvidenceDetail,
  normalizeEvidenceList,
  normalizeFamilies,
  normalizeFamilyDetail,
  normalizeOverview,
  normalizeTimelineList,
  normalizeValidationList,
} from "./data/researchNormalizers.js";
import {
  ResearchBlockedPage,
  ResearchEvidenceDetailPage,
  ResearchEvidencePage,
  ResearchFamiliesPage,
  ResearchFamilyDetailPage,
  ResearchOverviewPage,
  ResearchValidationPage,
} from "./ResearchPages.jsx";
import {
  blocked,
  evidence,
  family,
  listPayload,
  makeEvidenceDetailPayload,
  makeFamilyDetailPayload,
  makeOverviewPayload,
  validation,
} from "../../test/researchApiFixture.js";

function makeService(overrides = {}) {
  return {
    getOverview: vi.fn().mockResolvedValue(normalizeOverview(makeOverviewPayload())),
    getFamilies: vi.fn().mockResolvedValue(normalizeFamilies(listPayload("ABCDEFG".split("").map(family)))),
    getFamily: vi.fn().mockImplementation((id) => Promise.resolve(normalizeFamilyDetail(makeFamilyDetailPayload(id)))),
    getEvidence: vi.fn().mockResolvedValue(normalizeEvidenceList(listPayload([
      evidence(),
      evidence({ evidence_id: "EDGE-NEGATIVE-G-SMA200-GATE-001", family_id: "G", title: "Family G SMA200 gate evidence", summary: "The gate reduced returns and worsened drawdown.", classification: "NEGATIVE_EVIDENCE", evidence_type: "STRATEGY_LEVEL", status: "HISTORICAL", production_relevance: "Decision evidence · not for production", action_path: "/app/research/evidence/EDGE-NEGATIVE-G-SMA200-GATE-001" }),
    ]))),
    getEvidenceDetail: vi.fn().mockResolvedValue(normalizeEvidenceDetail(makeEvidenceDetailPayload())),
    getValidation: vi.fn().mockResolvedValue(normalizeValidationList(listPayload(validation))),
    getBlocked: vi.fn().mockResolvedValue(normalizeBlockedList(listPayload(blocked))),
    getTimeline: vi.fn().mockResolvedValue(normalizeTimelineList(listPayload([]))),
    ...overrides,
  };
}

function renderPage(element, path = "/app/research", routePath = "*") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route element={element} path={routePath} /></Routes>
    </MemoryRouter>,
  );
}

describe("Research Overview", () => {
  it("renders the real programme summary, A–G matrix and retained evidence", async () => {
    const service = makeService();
    renderPage(<ResearchOverviewPage dataService={service} />);

    expect(await screen.findByRole("heading", { name: "Research", exact: true })).toBeInTheDocument();
    const metrics = within(screen.getByRole("region", { name: "Research summary" }));
    expect(metrics.getByText("Families").parentElement).toHaveTextContent("7");
    expect(metrics.getByText("Reusable evidence").parentElement).toHaveTextContent("1");
    expect(metrics.getByText("Blocked studies").parentElement).toHaveTextContent("2");
    expect(metrics.getByText("Production-ready").parentElement).toHaveTextContent("0");
    expect(metrics.getByText("Programme").parentElement).toHaveTextContent("Paused");
    expect(screen.getAllByText(/Family [A-G]/).length).toBeGreaterThanOrEqual(7);
    expect(screen.queryByRole("link", { name: "Open Family H" })).not.toBeInTheDocument();
    expect(screen.getByText("No family planned")).toBeInTheDocument();
    expect(screen.getByText("EDGE-EVIDENCE-C-COMPRESSION-001")).toBeInTheDocument();
    expect(screen.getByText("Not production strategy")).toBeInTheDocument();
    expect(screen.getByText("No Strategy V2")).toBeInTheDocument();
    expect(service.getOverview).toHaveBeenCalledTimes(1);
  });

  it("surfaces Family C retained evidence and D/F blockers truthfully", async () => {
    renderPage(<ResearchOverviewPage dataService={makeService()} />);
    await screen.findByRole("heading", { name: "Research", exact: true });
    expect(screen.getByText("Reusable signal-level evidence")).toBeInTheDocument();
    expect(screen.getAllByText("Data blocker").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Source authorization blocker").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Blocked by data quality").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Blocked pending authorized source").length).toBeGreaterThan(0);
  });

  it("offers Research destinations through the command palette", async () => {
    const user = userEvent.setup();
    renderPage(<ResearchOverviewPage dataService={makeService()} />);
    await screen.findByRole("heading", { name: "Research", exact: true });
    await user.click(screen.getByRole("button", { name: "Open command palette" }));
    await user.type(screen.getByRole("textbox", { name: "Search commands" }), "Family G");
    expect(screen.getByRole("option", { name: /Family G/ })).toBeInTheDocument();
  });

  it("labels a partial backend response without hiding available families", async () => {
    const payload = makeOverviewPayload({
      status: "PARTIAL",
      reason: "RESEARCH_SECTIONS_UNAVAILABLE",
      meta: { ...makeOverviewPayload().meta, unavailable_sections: ["timeline"] },
    });
    const service = makeService({ getOverview: vi.fn().mockResolvedValue(normalizeOverview(payload)) });
    renderPage(<ResearchOverviewPage dataService={service} />);
    expect(await screen.findByText(/Some Research sections are temporarily unavailable: timeline/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Open Family A/ }).length).toBeGreaterThan(0);
  });

  it("shows skeleton loading and a sanitized retryable error without demo fallback", async () => {
    const pending = makeService({ getOverview: vi.fn(() => new Promise(() => {})) });
    const { unmount } = renderPage(<ResearchOverviewPage dataService={pending} />);
    expect(screen.getByRole("status", { name: "Loading Research" })).toBeInTheDocument();
    unmount();

    const failing = makeService({ getOverview: vi.fn().mockRejectedValue(new ResearchApiError("RESEARCH_API_UNAVAILABLE", "Research data couldn’t be loaded.")) });
    renderPage(<ResearchOverviewPage dataService={failing} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Research data couldn’t be loaded.");
    expect(screen.getByText(/no demo data has been substituted/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("Research families", () => {
  it("filters the family matrix by blocker and local search", async () => {
    const user = userEvent.setup();
    renderPage(<ResearchFamiliesPage dataService={makeService()} />, "/app/research/families");
    await screen.findByRole("heading", { name: "Research families" });
    const search = screen.getByRole("searchbox", { name: "Search" });
    await user.type(search, "history-availability");
    expect(screen.getAllByRole("link", { name: /Family B/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /Family D/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "ART-B");
    expect(screen.getAllByRole("link", { name: /Family B/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /Family D/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.selectOptions(screen.getByRole("combobox", { name: "Blocked" }), "true");
    expect(screen.getAllByRole("link", { name: /Family D/ }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Family F/ }).length).toBeGreaterThan(0);
  });

  it("preserves all mandatory Family A semantics simultaneously", async () => {
    renderPage(<ResearchFamilyDetailPage dataService={makeService()} />, "/app/research/families/A", "/app/research/families/:familyId");
    expect(await screen.findByRole("heading", { name: "Medium-Term Cross-Sectional Momentum" })).toBeInTheDocument();
    expect(screen.getAllByText("Formal validation").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/INCONCLUSIVE/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Post-remediation evaluation").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/FAIL \/ UNSUPPORTIVE/).length).toBeGreaterThan(0);
    expect(screen.getByText(/2025–26 holdout contaminated/)).toBeInTheDocument();
    expect(screen.getByText("Inconclusive")).toBeInTheDocument();
    expect(screen.getByText("Fail")).toBeInTheDocument();
    expect(screen.getByText("Unsupportive")).toBeInTheDocument();
    expect(screen.queryByText("Family A validation failed", { exact: false })).not.toBeInTheDocument();
  });
});

describe("Evidence, validation and blocked research", () => {
  it("renders and filters positive and negative evidence", async () => {
    const user = userEvent.setup();
    renderPage(<ResearchEvidencePage dataService={makeService()} />, "/app/research/evidence");
    expect(await screen.findByRole("heading", { name: "Evidence registry" })).toBeInTheDocument();
    expect(screen.getByText("EDGE-EVIDENCE-C-COMPRESSION-001")).toBeInTheDocument();
    expect(screen.getByText("EDGE-NEGATIVE-G-SMA200-GATE-001")).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Family" }), "G");
    expect(screen.queryByText("EDGE-EVIDENCE-C-COMPRESSION-001")).not.toBeInTheDocument();
    expect(screen.getByText("EDGE-NEGATIVE-G-SMA200-GATE-001")).toBeInTheDocument();
  });

  it("shows evidence context, safe artifacts and collapsed lineage access", async () => {
    const user = userEvent.setup();
    renderPage(<ResearchEvidenceDetailPage dataService={makeService()} />, "/app/research/evidence/EDGE-EVIDENCE-C-COMPRESSION-001", "/app/research/evidence/:evidenceId");
    expect(await screen.findByRole("heading", { name: "EDGE-EVIDENCE-C-COMPRESSION-001" })).toBeInTheDocument();
    expect(screen.getAllByText("Reusable signal evidence · not production strategy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cross-Family Positive Evidence Registry").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/View lineage/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "View lineage" }));
    expect(document.querySelector(".lineage-disclosure")).toHaveAttribute("open");
    expect(screen.queryByText(/C:\\Users/i)).not.toBeInTheDocument();
  });

  it("keeps Family A formal and post-remediation validation as separate rows", async () => {
    renderPage(<ResearchValidationPage dataService={makeService()} />, "/app/research/validation");
    expect(await screen.findByRole("heading", { name: "Validation" })).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Formal one-shot")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Inconclusive")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Implementation defect")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Post-remediation evaluation")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Fail")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Unsupportive")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Non-pristine")).toBeInTheDocument();
  });

  it("states that D is data-blocked and F is source-blocked without performance claims", async () => {
    renderPage(<ResearchBlockedPage dataService={makeService()} />, "/app/research/blocked");
    expect(await screen.findByRole("heading", { name: "Blocked research" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Data blocker" })).toBeInTheDocument();
    expect(screen.getByText(/77.826%/)).toBeInTheDocument();
    expect(screen.getByText(/trustworthy formal evaluation/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Source authorization blocker" })).toBeInTheDocument();
    expect(screen.getByText(/authorized historical announcement source/i)).toBeInTheDocument();
    expect(screen.queryByText(/failed strategy/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/performance conclusion/i)).not.toBeInTheDocument();
  });

  it("distinguishes empty registries from loading and error states", async () => {
    const service = makeService({
      getEvidence: vi.fn().mockResolvedValue(normalizeEvidenceList(listPayload([]))),
      getValidation: vi.fn().mockResolvedValue(normalizeValidationList(listPayload([]))),
      getBlocked: vi.fn().mockResolvedValue(normalizeBlockedList(listPayload([]))),
    });
    const evidenceView = renderPage(<ResearchEvidencePage dataService={service} />, "/app/research/evidence");
    expect(await screen.findByRole("heading", { name: "No evidence found" })).toBeInTheDocument();
    evidenceView.unmount();
    const validationView = renderPage(<ResearchValidationPage dataService={service} />, "/app/research/validation");
    expect(await screen.findByRole("heading", { name: "No validation records" })).toBeInTheDocument();
    validationView.unmount();
    renderPage(<ResearchBlockedPage dataService={service} />, "/app/research/blocked");
    expect(await screen.findByRole("heading", { name: "No blockers" })).toBeInTheDocument();
  });
});
