export const selectDefaultAttention = (snapshot) => snapshot.attentionItems?.[0] ?? null;

export const selectAttentionById = (snapshot, id) =>
  snapshot.attentionItems?.find((item) => item.id === id) ?? selectDefaultAttention(snapshot);

export const selectActiveExposureIds = (attentionItem) => attentionItem?.metadata?.exposureIds ?? [];

export const selectSearchItems = (snapshot) => snapshot.searchItems ?? [];

export const selectDrawerSummary = (snapshot) => ({
  researchBlockers: snapshot.research?.blocked?.length ?? 0,
  dataLimitations: snapshot.dataHealth?.rows?.filter((row) => row.tone !== "healthy").length ?? 0,
});
