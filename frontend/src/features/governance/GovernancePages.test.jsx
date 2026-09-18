import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { GovernanceAuditPage, GovernanceOverviewPage } from "./GovernancePages.jsx";

const readiness = ["Paper Trading", "Live Trading", "Broker", "Production"].map((label, index) => ({ id: `R-${index}`, type: ["PAPER_TRADING_READINESS", "LIVE_TRADING_READINESS", "BROKER_READINESS", "PRODUCTION_READINESS"][index], label, subjectId: `S-${index}`, status: "NOT_READY", assessedAt: "2026-09-16T22:25:00Z", passedCriteria: 0, totalCriteria: 2, failedCriteria: ["approval required"], warnings: [], connectionState: index === 2 ? "NOT_CONNECTED" : null }));
const audit = [{ id: "AUDIT-1", source: "GOVERNANCE", eventType: "AUTHORIZATION_REQUESTED", domain: "DATA", subjectId: "DATA-SOURCE-CATALYST-HISTORY", subjectType: "DATA_SOURCE", actor: "SYSTEM", occurredAt: "2026-09-16T22:35:00Z", action: "REQUEST", result: "REQUESTED", reason: "Record unresolved authorization gate." }];
const overview = { generatedAt: "2026-09-18T12:00:00Z", status: "AVAILABLE", meta: { unavailableSections: [] }, summary: { paperReadiness: "NOT_READY", liveReadiness: "NOT_READY", brokerReadiness: "NOT_READY", productionReadiness: "NOT_READY", brokerConnectionState: "NOT_CONNECTED", blockingViolationCount: 0, pendingAuthorizationCount: 1, passingPolicyCount: 8, totalPolicyCount: 8 }, readiness, policies: [], authorizations: [{ id: "AUTH-1", type: "DATA_ACQUISITION", subjectId: "DATA-SOURCE-CATALYST-HISTORY", status: "REQUESTED", requestedAt: "2026-09-16T22:35:00Z", requestedBy: "SYSTEM", reason: "Do not acquire data.", conditions: ["Licensed source"] }], recentAudit: audit, manualOverrides: [] };
const makeService = () => ({ getOverview: vi.fn().mockResolvedValue(overview), getAudit: vi.fn().mockResolvedValue({ ...overview, items: audit, totalCount: 1, manualOverrides: [] }) });
const renderPage = (element, path = "/app/governance") => render(<MemoryRouter initialEntries={[path]}><Routes><Route element={element} path="*" /></Routes></MemoryRouter>);

describe("Governance pages", () => {
  it("shows distinct readiness, policy, authorization and violation truths", async () => {
    const dataService = makeService();
    const user = userEvent.setup();
    renderPage(<GovernanceOverviewPage dataService={dataService} />);
    expect(await screen.findByRole("heading", { name: "Governance", exact: true })).toBeInTheDocument();
    expect(screen.getAllByText("Not ready")).toHaveLength(8);
    expect(screen.getByText("8/8 policy evaluations pass.")).toBeInTheDocument();
    expect(screen.getByText(/do not imply trading readiness/i)).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(dataService.getOverview).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Open command palette" }));
    await user.type(screen.getByRole("textbox", { name: "Search commands" }), "authorizations");
    expect(screen.getByRole("option", { name: /Authorizations/i })).toBeInTheDocument();
  });

  it("shows real audit events and an honest override empty state", async () => {
    renderPage(<GovernanceAuditPage dataService={makeService()} />, "/app/governance/audit");
    expect(await screen.findByRole("heading", { name: "Audit", exact: true })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No manual overrides recorded" })).toBeInTheDocument();
    expect(screen.getByText("Record unresolved authorization gate.")).toBeInTheDocument();
  });
});
