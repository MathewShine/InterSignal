export const selectPrimaryIndex = (snapshot) => snapshot.indices.find((item) => item.symbol === snapshot.market.primaryIndex) ?? snapshot.indices[0] ?? null;

export const selectReferenceIndex = (snapshot) => snapshot.indices.find((item) => snapshot.market.referenceIndices.includes(item.symbol)) ?? snapshot.indices[1] ?? null;

const numericLast = (selector, descending = true) => (left, right) => {
  const a = selector(left);
  const b = selector(right);
  if (a === null) return b === null ? left.name.localeCompare(right.name) : 1;
  if (b === null) return -1;
  return (descending ? b - a : a - b) || left.name.localeCompare(right.name);
};

export function sortSectors(sectors, sortKey) {
  const copy = [...sectors];
  if (sortKey === "breadth") return copy.sort(numericLast((item) => item.breadthPercent));
  if (sortKey === "name") return copy.sort((left, right) => left.name.localeCompare(right.name));
  return copy.sort(numericLast((item) => item.returnPercent));
}

export const selectSectorLeaders = (snapshot, count = 3) => sortSectors(snapshot.sectors, "performance").filter((item) => item.returnPercent !== null).slice(0, count);

export const selectSectorLaggards = (snapshot, count = 3) => sortSectors(snapshot.sectors, "performance").filter((item) => item.returnPercent !== null).slice(-count).reverse();

export function breadthSummary(breadth) {
  if (!breadth) return "Participation is unavailable for this recorded session.";
  if (breadth.advancers > breadth.decliners) return "Participation tilted positive in the recorded session.";
  if (breadth.decliners > breadth.advancers) return "Participation tilted negative in the recorded session.";
  return "Participation was evenly split in the recorded session.";
}
