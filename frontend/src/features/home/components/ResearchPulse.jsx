import { Link } from "react-router-dom";

export function ResearchPulse({ research }) {
  if (!research || research.status === "unavailable") {
    return <section aria-labelledby="research-title" className="home-pulse home-pulse--empty"><span className="technical-label">RESEARCH PULSE</span><h2 id="research-title">Research context unavailable.</h2><p>The rest of Home remains usable.</p></section>;
  }
  return (
    <section aria-labelledby="research-title" className="home-pulse research-pulse">
      <header><div><span className="technical-label">RESEARCH PULSE</span><h2 id="research-title">Research pulse</h2></div><span className="state-tag">{research.programmeState}</span></header>
      <div className="research-pulse__facts"><span>Families <b className="metric-value">{research.families}</b></span><span>Reusable evidence <b>{research.reusableEvidence}</b></span><span>Candidates <b className="metric-value">{research.productionCandidates}</b></span><span>Blocked <b>{research.blocked.join(" / ")}</b></span></div>
      <blockquote>“{research.evidence}”</blockquote>
      <footer><span><b>{research.evidenceLabel}</b> · {research.evidenceQualification}</span><Link to="/app/research">Open Research →</Link></footer>
    </section>
  );
}
