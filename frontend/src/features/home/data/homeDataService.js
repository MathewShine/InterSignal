import { homeDemoData } from "./homeDemoData.js";
import { ApiHomeAdapter } from "./apiHomeAdapter.js";
import { HomeDataService } from "./homeDataServiceBase.js";
import { runtimeConfig } from "../../../config/runtimeConfig.js";

/**
 * @typedef {Object} MarketContext
 * @property {"available"|"unavailable"} status
 * @property {string} index
 * @property {string} textualSummary
 */

/** @typedef {{status: "available"|"empty", allocations?: Array<Object>}} PortfolioContext */
/** @typedef {{status: "available"|"unavailable", families?: number}} ResearchPulse */
/** @typedef {{id: string, title: string, severity: string, metadata: Object}} AttentionItem */
/** @typedef {{status: string, rows: Array<Object>}} DataHealth */
/** @typedef {{paper: string, live: string, blockingViolations: number}} GovernancePulse */
/** @typedef {{id: string, label: string, context: string}} ActivityItem */

/**
 * @typedef {Object} HomeSnapshot
 * @property {string} version
 * @property {boolean} demoMode
 * @property {MarketContext} market
 * @property {PortfolioContext} portfolio
 * @property {ResearchPulse} research
 * @property {Array<AttentionItem>} attentionItems
 * @property {DataHealth} dataHealth
 * @property {GovernancePulse} governance
 * @property {Array<ActivityItem>} recentActivity
 */

const clone = (value) => JSON.parse(JSON.stringify(value));

export { HomeDataService };

export class DemoHomeAdapter extends HomeDataService {
  constructor({ scenario = "healthy", snapshot = homeDemoData } = {}) {
    super();
    this.scenario = scenario;
    this.snapshot = clone(snapshot);
  }

  async getHomeSnapshot() {
    const snapshot = clone(this.snapshot);
    if (this.scenario === "empty-portfolio") snapshot.portfolio = { status: "empty" };
    if (this.scenario === "no-market") snapshot.market = { status: "unavailable" };
    if (this.scenario === "research-unavailable") snapshot.research = { status: "unavailable" };
    if (this.scenario === "partial") {
      snapshot.market = { status: "unavailable" };
      snapshot.dataHealth.status = "partial";
    }
    if (this.scenario === "error") throw new Error("Home snapshot is temporarily unavailable.");
    return snapshot;
  }
}

export function createHomeDataService({
  mode = runtimeConfig.homeDataMode,
  scenario = "healthy",
  ...apiOptions
} = {}) {
  if (mode === "demo") return new DemoHomeAdapter({ scenario });
  return new ApiHomeAdapter(apiOptions);
}

export const homeDataService = createHomeDataService();
