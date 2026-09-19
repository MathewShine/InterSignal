export const MARKET_CONTRACT_VERSION = "INTERSIGNAL_MARKET_SNAPSHOT_V1";

const number = (value) => value === null || value === undefined ? null : Number(value);
const quality = (value = {}) => ({
  coverageCount: Number(value.coverage_count ?? 0),
  expectedCount: Number(value.expected_count ?? 0),
  coveragePercent: number(value.coverage_pct),
  missingCount: Number(value.missing_count ?? 0),
});
const availability = (value = {}) => ({
  status: value.status ?? "UNAVAILABLE",
  reason: value.reason ?? null,
});

export function normalizeMarketSnapshot(payload) {
  return {
    version: payload.version,
    generatedAt: payload.generated_at,
    status: payload.status,
    market: {
      country: payload.market?.country,
      exchange: payload.market?.exchange,
      primaryIndex: payload.market?.primary_index,
      referenceIndices: payload.market?.reference_indices ?? [],
    },
    provider: {
      name: payload.provider?.provider_name,
      mode: payload.provider?.mode ?? "UNAVAILABLE",
      market: payload.provider?.market,
      capabilities: payload.provider?.capabilities ?? [],
    },
    freshness: {
      sourceTimestamp: payload.freshness?.source_timestamp ?? null,
      receivedAt: payload.freshness?.received_at ?? null,
      ageSeconds: number(payload.freshness?.age_seconds),
      status: payload.freshness?.freshness_status ?? "UNKNOWN",
    },
    indices: (payload.indices ?? []).map((item) => ({
      symbol: item.symbol,
      name: item.name,
      value: number(item.value),
      change: number(item.change),
      changePercent: number(item.change_pct),
      previousClose: number(item.previous_close),
      timestamp: item.timestamp,
      source: item.source,
      freshness: item.freshness,
    })),
    universe: payload.universe ? {
      name: payload.universe.name,
      memberCount: Number(payload.universe.member_count ?? 0),
      asOfDate: payload.universe.as_of_date,
      membershipKind: payload.universe.membership_kind,
      source: payload.universe.source,
    } : null,
    breadth: payload.breadth ? {
      advancers: Number(payload.breadth.advancers ?? 0),
      decliners: Number(payload.breadth.decliners ?? 0),
      unchanged: Number(payload.breadth.unchanged ?? 0),
      positivePercent: number(payload.breadth.positive_pct),
      negativePercent: number(payload.breadth.negative_pct),
      aboveVwapPercent: number(payload.breadth.above_vwap_pct),
      abovePriorClosePercent: number(payload.breadth.above_prior_close_pct),
      quality: quality(payload.breadth.quality),
    } : null,
    sectors: (payload.sectors ?? []).map((item) => ({
      name: item.sector,
      returnPercent: number(item.return_pct),
      advancers: number(item.advancers),
      decliners: number(item.decliners),
      unchanged: number(item.unchanged),
      breadthPercent: number(item.breadth_pct),
      relativeStrength: number(item.relative_strength),
      volumeContext: number(item.volume_context),
      quality: quality(item.quality),
    })),
    volume: payload.volume ? {
      aggregateTradedValue: number(payload.volume.aggregate_traded_value),
      tradedValueUnit: payload.volume.traded_value_unit,
      medianRelativeVolume: number(payload.volume.median_relative_volume),
      aboveBaselineCount: Number(payload.volume.above_20d_volume_count ?? 0),
      aboveBaselinePercent: number(payload.volume.above_20d_volume_pct),
      quality: quality(payload.volume.quality),
    } : null,
    session: payload.session ? {
      status: payload.session.status,
      marketDate: payload.session.market_date,
      timestamp: payload.session.session_timestamp,
    } : null,
    availability: Object.fromEntries(Object.entries(payload.availability ?? {}).map(([key, value]) => [key, availability(value)])),
    limitations: (payload.limitations ?? []).map((item) => ({
      id: item.limitation_id,
      section: item.section,
      summary: item.summary,
    })),
    meta: {
      readOnly: payload.meta?.read_only !== false,
      strategyOutput: payload.meta?.strategy_output === true,
      marketRegimeEngine: payload.meta?.market_regime_engine === true,
      brokerIntegration: payload.meta?.broker_integration ?? "NOT_CONNECTED",
      liveProviderImplemented: payload.meta?.live_provider_implemented === true,
      currentMembershipOnly: payload.meta?.current_membership_only !== false,
      unavailableSections: payload.meta?.unavailable_sections ?? [],
    },
  };
}
