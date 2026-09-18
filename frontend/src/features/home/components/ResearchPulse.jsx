import { Link } from "react-router-dom";

export function ResearchPulse({ focused = false, research }) {
  if (!research || research.status === "unavailable") {
    return <section aria-labelledby="research-title" className={`home-pulse home-pulse--empty${focused ? " is-context-focused" : ""}`}><h2 id="research-title">Research</h2><p>Research information is unavailable right now.</p></section>;
  }
  const evidence = research.reusableEvidenceItems?.[0];
  return (
    <section aria-labelledby="research-title" className={`home-pulse research-pulse${focused ? " is-context-focused" : ""}`}>
      <header><div><h2 id="research-title">Research</h2><p>Programme overview</p></div><span className="state-tag">{research.programmeLabel ?? research.programmeState}</span></header>
      <div className="research-pulse__summary"><div className="research-pulse__lead"><strong className="metric-value">{research.families}</strong><span>Research families</span></div><dl><div><dt>Evidence retained</dt><dd>{research.reusableEvidenceItems?.length ?? (research.reusableEvidence ? 1 : 0)}</dd></div><div><dt>Blocked studies</dt><dd>{research.blocked.length}</dd></div><div><dt>Production-ready</dt><dd>{research.productionCandidates}</dd></div></dl></div>
      <div className="research-pulse__finding"><span>{evidence?.family ? `Family ${evidence.family}` : "Latest finding"}</span><strong>Compression evidence retained</strong><p>{research.evidenceQualification}</p></div>
      <footer><span>{research.blocked.join(" and ")} remain limited</span><Link to="/app/research">View research →</Link></footer>
    </section>
  );
}
