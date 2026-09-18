export class HomeDataService {
  async getHomeSnapshot() {
    throw new Error("HomeDataService.getHomeSnapshot must be implemented.");
  }

  async getAttentionItems(options) {
    return (await this.getHomeSnapshot(options)).attentionItems;
  }

  async getMarketContext(options) {
    return (await this.getHomeSnapshot(options)).market;
  }

  async getPortfolioContext(options) {
    return (await this.getHomeSnapshot(options)).portfolio;
  }

  async getResearchPulse(options) {
    return (await this.getHomeSnapshot(options)).research;
  }

  async getDataHealth(options) {
    return (await this.getHomeSnapshot(options)).dataHealth;
  }

  async getGovernancePulse(options) {
    return (await this.getHomeSnapshot(options)).governance;
  }

  async getRecentActivity(options) {
    return (await this.getHomeSnapshot(options)).recentActivity;
  }
}
