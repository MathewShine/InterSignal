export class PortfolioDataService {
  async getOverview() {
    throw new Error("PortfolioDataService.getOverview must be implemented.");
  }

  async getHoldings() {
    throw new Error("PortfolioDataService.getHoldings must be implemented.");
  }

  async getActivity() {
    throw new Error("PortfolioDataService.getActivity must be implemented.");
  }

  async getPerformance() {
    throw new Error("PortfolioDataService.getPerformance must be implemented.");
  }
}
