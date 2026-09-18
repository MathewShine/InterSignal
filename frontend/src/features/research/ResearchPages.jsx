import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { researchDataService } from "./data/apiResearchAdapter.js";
import { statusLabel } from "./data/researchNormalizers.js";
import {
  EmptyState,
  EvidenceTable,
  FamilyMatrix,
  FilterBar,
  LineageDisclosure,
  PageHeader,
  PartialNotice,
  ResearchError,
  ResearchLayout,
  ResearchLoading,
  SelectFilter,
  StatusPill,
  TimelineList,
  formatDate,
  useResearchResource,
} from "./components/ResearchLayout.jsx";

const searchable = (...values) => values.filter(Boolean).join(" ").toLowerCase();

function LoadedPage({ state, children, type }) {
  if (state.status === "loading") return <ResearchLoading type={type} />;
  if (state.status === "error") return <ResearchError error={state.error} onRetry={state.retry} />;
  return children(state.data);
}

export function ResearchOverviewPage({ dataService = researchDataService }) {
  const loader = useCallback((options) => dataService.getOverview(options), [dataService]);
  const state = useResearchResource(loader);
  return (
    <LoadedPage state={state}>
      {(data) => (
        <ResearchLayout connectionState={data.status === "PARTIAL" ? "PARTIAL" : "CONNECTED"}>
          <PageHeader description="Evidence, validation and research state across the programme." title="Research" />
          <PartialNotice unavailable={data.meta.unavailable_sections ?? []} />
          <section aria-label="Research summary" className="research-metrics">
            {[
              ["Families", data.metrics.families],
              ["Reusable evidence", data.metrics.reusableEvidence],
              ["Blocked studies", data.metrics.blockedStudies],
              ["Production-ready", data.metrics.productionReady],
              ["Programme", statusLabel(data.programme?.status)],
            ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
          </section>

          <section className="research-surface research-family-surface">
            <div className="research-section-heading">
              <div><span className="technical-label">CURRENT PROGRAMME STATE</span><h2>Research families</h2></div>
              <Link to="/app/research/families">View all families →</Link>
            </div>
            <FamilyMatrix compact families={data.families} />
          </section>

          <section className="research-overview-secondary">
            <article className="research-surface retained-evidence-card">
              <div className="research-section-heading"><div><span className="technical-label">RETAINED</span><h2>Reusable evidence</h2></div><Link to="/app/research/evidence">Registry →</Link></div>
              {data.retainedEvidence.length ? data.retainedEvidence.map((item) => (
                <div className="retained-evidence" key={item.id}>
                  <StatusPill value="POSITIVE REUSABLE">Reusable signal-level evidence</StatusPill>
                  <Link to={item.actionPath}>{item.id}</Link>
                  <p>{item.summary}</p>
                  <strong>Not production strategy</strong>
                </div>
              )) : <EmptyState message="No reusable evidence is currently retained." title="No retained evidence" />}
            </article>
            <article className="research-surface">
              <div className="research-section-heading"><div><span className="technical-label">CONSTRAINTS</span><h2>Blocked work</h2></div><Link to="/app/research/blocked">View blocked →</Link></div>
              {data.blocked.length ? <div className="blocked-preview">{data.blocked.map((item) => <Link key={item.familyId} to={item.actionPath}><span className="family-code">{item.familyId}</span><span><strong>{item.label}</strong><small>{item.reason}</small></span><b>→</b></Link>)}</div> : <EmptyState message="No Research studies are currently blocked." title="No blocked work" />}
            </article>
            <article className="research-surface">
              <div className="research-section-heading"><div><span className="technical-label">REGISTRY</span><h2>Recent activity</h2></div><Link to="/app/research/timeline">Timeline →</Link></div>
              <TimelineList items={data.recentActivity} limit={3} />
            </article>
          </section>

          {data.programme ? (
            <section aria-label="Programme policy" className="programme-strip">
              <div><span>Cycle</span><strong>A–G complete</strong></div>
              <div><span>Validated strategy</span><strong>None</strong></div>
              <div><span>Primary programme</span><strong>{statusLabel(data.programme.primaryProgramme)}</strong></div>
              <div><span>Secondary programme</span><strong>{statusLabel(data.programme.secondaryProgramme)}</strong></div>
              <div><span>Family H</span><strong>No family planned</strong></div>
              <div><span>Strategy V2</span><strong>No Strategy V2</strong></div>
              <div><span>Paper / live</span><strong>Not ready</strong></div>
            </section>
          ) : null}
        </ResearchLayout>
      )}
    </LoadedPage>
  );
}

export function ResearchFamiliesPage({ dataService = researchDataService }) {
  const loader = useCallback((options) => dataService.getFamilies(options), [dataService]);
  const state = useResearchResource(loader);
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [evidence, setEvidence] = useState("");
  const [blocked, setBlocked] = useState("");
  const [validation, setValidation] = useState("");

  return (
    <LoadedPage state={state}>
      {(data) => {
        const filtered = data.items.filter((family) => {
          const matchesQuery = !query || searchable(family.id, family.name, family.setup, family.evidenceState, family.blocker, family.validationLabel, ...family.keyFindings, ...family.searchTerms).includes(query.toLowerCase());
          return matchesQuery
            && (!stage || family.stage === stage)
            && (!status || family.currentStatus === status)
            && (!evidence || family.evidenceState.includes(evidence))
            && (!blocked || String(Boolean(family.blocker)) === blocked)
            && (!validation || family.validationState === validation);
        });
        return (
          <ResearchLayout>
            <PageHeader description="Hypotheses, evidence, decisions and constraints in canonical A–G order." title="Research families" />
            <FilterBar onQueryChange={setQuery} placeholder="Family, evidence, artifact, blocker or outcome" query={query}>
              <SelectFilter label="Stage" onChange={setStage} options={[...new Set(data.items.map((item) => item.stage))]} value={stage} />
              <SelectFilter label="Status" onChange={setStatus} options={[...new Set(data.items.map((item) => item.currentStatus))]} value={status} />
              <SelectFilter label="Evidence state" onChange={setEvidence} options={[...new Set(data.items.map((item) => item.evidenceState))]} value={evidence} />
              <SelectFilter label="Blocked" onChange={setBlocked} options={["true", "false"]} value={blocked} />
              <SelectFilter label="Validation" onChange={setValidation} options={[...new Set(data.items.map((item) => item.validationState))]} value={validation} />
            </FilterBar>
            <section className="research-surface research-family-surface">
              <div className="research-section-heading"><div><span className="technical-label">{filtered.length} OF {data.totalCount}</span><h2>Family matrix</h2></div></div>
              <FamilyMatrix families={filtered} />
            </section>
          </ResearchLayout>
        );
      }}
    </LoadedPage>
  );
}

export function ResearchFamilyDetailPage({ dataService = researchDataService }) {
  const { familyId = "" } = useParams();
  const loader = useCallback((options) => dataService.getFamily(familyId, options), [dataService, familyId]);
  const state = useResearchResource(loader, [familyId]);
  return (
    <LoadedPage state={state} type="detail">
      {(data) => (
        <ResearchLayout>
          <PageHeader
            actions={<><StatusPill value={data.family.currentStatus}>{data.family.currentStatusLabel}</StatusPill><Link className="research-text-link" to="/app/research/families">All families</Link></>}
            description={data.family.setup}
            eyebrow={`FAMILY ${data.family.id} · ${data.family.stage.toUpperCase()}`}
            title={data.family.name}
          />
          <nav aria-label={`Family ${data.family.id} detail sections`} className="family-detail-nav">
            {["Overview", "Evidence", "Validation", "Timeline", "Artifacts"].map((label) => <a href={`#${label.toLowerCase()}`} key={label}>{label}</a>)}
          </nav>
          <section className="family-detail-summary" id="overview">
            <article className="research-surface family-hypothesis"><span className="technical-label">HYPOTHESIS</span><p>{data.hypothesis}</p></article>
            <article className="research-surface family-decision"><span>Current decision</span><strong>{data.family.decisionLabel}</strong><code>{data.family.decisionStatus}</code></article>
          </section>
          <section aria-label="Research chronology" className="family-chronology">
            {data.sections.map((section, index) => (
              <article className="research-surface" data-tone={section.tone.toLowerCase()} id={section.id} key={section.id}>
                <span className="chronology-index">{String(index + 1).padStart(2, "0")}</span>
                <div><h2>{section.title}</h2><p>{section.summary}</p></div>
              </article>
            ))}
          </section>
          <section className="research-detail-section" id="evidence">
            <div className="research-section-heading"><div><span className="technical-label">RECORDS</span><h2>Evidence</h2></div></div>
            {data.evidence.length ? <div className="detail-record-list">{data.evidence.map((item) => <Link key={item.id} to={item.actionPath}><span><strong>{item.id}</strong><small>{item.title}</small></span><StatusPill value={`${item.classification} ${item.status}`}>{statusLabel(item.classification)}</StatusPill></Link>)}</div> : <EmptyState message="This family has no registered evidence." title="No evidence" />}
          </section>
          <section className="research-detail-section" id="validation">
            <div className="research-section-heading"><div><span className="technical-label">INTEGRITY-AWARE</span><h2>Validation and evaluation</h2></div></div>
            {data.validation.length ? <ValidationTable items={data.validation} /> : <EmptyState message="This family has no validation records." title="No validation records" />}
          </section>
          <section className="research-detail-section" id="timeline">
            <div className="research-section-heading"><div><span className="technical-label">CHRONOLOGY</span><h2>Timeline</h2></div></div>
            <TimelineList items={data.timeline} />
          </section>
          <section className="research-detail-section" id="artifacts">
            <div className="research-section-heading"><div><span className="technical-label">PROVENANCE</span><h2>Artifacts</h2></div></div>
            {data.artifacts.length ? <ArtifactTable items={data.artifacts} /> : <EmptyState message="This family has no linked artifacts." title="No artifacts" />}
            <LineageDisclosure lineage={data.lineage} />
          </section>
        </ResearchLayout>
      )}
    </LoadedPage>
  );
}

export function ResearchEvidencePage({ dataService = researchDataService }) {
  const loader = useCallback((options) => dataService.getEvidence(options), [dataService]);
  const state = useResearchResource(loader);
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [relevance, setRelevance] = useState("");
  const [sort, setSort] = useState("newest");
  return (
    <LoadedPage state={state}>
      {(data) => {
        const items = data.items.filter((item) => (!query || searchable(item.id, item.title, item.familyId, item.summary).includes(query.toLowerCase()))
          && (!family || item.familyId === family)
          && (!status || item.status === status)
          && (!type || item.type === type)
          && (!relevance || item.productionRelevance === relevance));
        items.sort((a, b) => sort === "family" ? a.familyId.localeCompare(b.familyId) || a.id.localeCompare(b.id) : sort === "id" ? a.id.localeCompare(b.id) : new Date(b.updatedAt) - new Date(a.updatedAt));
        return (
          <ResearchLayout>
            <PageHeader description="Positive, negative, validation and blocked evidence remain first-class records." title="Evidence registry" />
            <FilterBar onQueryChange={setQuery} placeholder="Evidence ID, title or family" query={query}>
              <SelectFilter label="Family" onChange={setFamily} options={[...new Set(data.items.map((item) => item.familyId))]} value={family} />
              <SelectFilter label="Status" onChange={setStatus} options={[...new Set(data.items.map((item) => item.status))]} value={status} />
              <SelectFilter label="Type" onChange={setType} options={[...new Set(data.items.map((item) => item.type))]} value={type} />
              <SelectFilter label="Production relevance" onChange={setRelevance} options={[...new Set(data.items.map((item) => item.productionRelevance))]} value={relevance} />
              <SelectFilter label="Sort" onChange={setSort} options={["newest", "family", "id"]} value={sort} />
            </FilterBar>
            <section className="research-surface registry-surface"><div className="research-section-heading"><div><span className="technical-label">{items.length} RECORDS</span><h2>Evidence</h2></div></div><EvidenceTable items={items} /></section>
          </ResearchLayout>
        );
      }}
    </LoadedPage>
  );
}

export function ResearchEvidenceDetailPage({ dataService = researchDataService }) {
  const { evidenceId = "" } = useParams();
  const loader = useCallback((options) => dataService.getEvidenceDetail(evidenceId, options), [dataService, evidenceId]);
  const state = useResearchResource(loader, [evidenceId]);
  return (
    <LoadedPage state={state} type="detail">
      {(data) => {
        const item = data.evidence;
        return (
          <ResearchLayout>
            <PageHeader actions={<StatusPill value={`${item.classification} ${item.status}`}>{statusLabel(item.classification)}</StatusPill>} description={`Family ${item.familyId} · ${item.researchContext}`} eyebrow="EVIDENCE RECORD" title={item.id} />
            <section className="evidence-detail-grid">
              <article className="research-surface evidence-detail-summary"><span className="technical-label">SUMMARY</span><h2>{item.title}</h2><p>{item.summary}</p><div className="evidence-distinction"><strong>{item.productionRelevance}</strong></div></article>
              <dl className="research-surface research-definition-list">
                <div><dt>Family</dt><dd><Link to={`/app/research/families/${item.familyId}`}>Family {item.familyId}</Link></dd></div>
                <div><dt>Classification</dt><dd>{statusLabel(item.classification)}</dd></div>
                <div><dt>Evidence type</dt><dd>{statusLabel(item.type)}</dd></div>
                <div><dt>Current disposition</dt><dd>{item.currentDisposition}</dd></div>
                <div><dt>Effective period</dt><dd>{item.effectivePeriod ?? "—"}</dd></div>
                <div><dt>Source</dt><dd>{item.source}</dd></div>
              </dl>
            </section>
            <section className="research-detail-section"><div className="research-section-heading"><div><span className="technical-label">SOURCE RECORDS</span><h2>Supporting artifacts</h2></div></div>{item.supportingArtifacts.length ? <ArtifactTable items={item.supportingArtifacts} /> : <EmptyState message="No supporting artifacts are linked." title="No artifacts" />}</section>
            <section className="research-detail-section"><div className="research-section-heading"><div><span className="technical-label">PROVENANCE</span><h2>Lineage</h2></div></div><LineageDisclosure lineage={item.lineage} /></section>
            {item.limitations.length ? <section className="research-surface evidence-limitations"><span className="technical-label">LIMITATIONS</span><ul>{item.limitations.map((limitation) => <li key={limitation}>{statusLabel(limitation)}</li>)}</ul></section> : null}
          </ResearchLayout>
        );
      }}
    </LoadedPage>
  );
}

export function ResearchValidationPage({ dataService = researchDataService }) {
  const loader = useCallback((options) => dataService.getValidation(options), [dataService]);
  const state = useResearchResource(loader);
  const [query, setQuery] = useState("");
  return (
    <LoadedPage state={state}>
      {(data) => {
        const items = data.items.filter((item) => !query || searchable(item.familyId, item.type, item.outcome, item.interpretation, item.integrity, item.notes).includes(query.toLowerCase()));
        return (
          <ResearchLayout>
            <PageHeader description="Formal validation, development evaluation and post-remediation evidence with integrity preserved." title="Validation" />
            <div className="validation-integrity-note"><strong>Integrity matters.</strong> Formal intent, result integrity and non-pristine post-outcome evidence are shown separately.</div>
            <FilterBar onQueryChange={setQuery} placeholder="Family, outcome, integrity or note" query={query} />
            <section className="research-surface registry-surface">{items.length ? <ValidationTable items={items} /> : <EmptyState message="No validation records match this search." title="No validation records" />}</section>
          </ResearchLayout>
        );
      }}
    </LoadedPage>
  );
}

export function ResearchBlockedPage({ dataService = researchDataService }) {
  const loader = useCallback((options) => dataService.getBlocked(options), [dataService]);
  const state = useResearchResource(loader);
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  const [type, setType] = useState("");
  return (
    <LoadedPage state={state}>
      {(data) => {
        const items = data.items.filter((item) => (!query || searchable(item.familyId, item.label, item.reason, item.impact, item.requiredResolution).includes(query.toLowerCase())) && (!family || item.familyId === family) && (!type || item.type === type));
        return (
          <ResearchLayout>
            <PageHeader description="Constraints that prevent trustworthy research—not failed strategies." title="Blocked research" />
            <FilterBar onQueryChange={setQuery} placeholder="Blocked reason or required resolution" query={query}>
              <SelectFilter label="Family" onChange={setFamily} options={[...new Set(data.items.map((item) => item.familyId))]} value={family} />
              <SelectFilter label="Blocker type" onChange={setType} options={[...new Set(data.items.map((item) => item.type))]} value={type} />
            </FilterBar>
            {items.length ? <div className="blocked-grid">{items.map((item) => (
              <article className="research-surface blocked-card" key={item.familyId}>
                <header><span className="family-code">{item.familyId}</span><div><span className="technical-label">FAMILY {item.familyId}</span><h2>{item.label}</h2></div><StatusPill value={item.type}>{item.status}</StatusPill></header>
                <dl><div><dt>Problem</dt><dd>{item.reason}</dd></div><div><dt>Impact</dt><dd>{item.impact}</dd></div><div><dt>Required resolution</dt><dd>{item.requiredResolution}</dd></div><div><dt>Current state</dt><dd><code>{item.currentState}</code></dd></div></dl>
                <footer><span>{item.relatedEvidence.length} linked evidence record{item.relatedEvidence.length === 1 ? "" : "s"}</span><Link to={item.actionPath}>Open Family {item.familyId} →</Link></footer>
              </article>
            ))}</div> : <EmptyState message="No blocked Research items match the current filters." title="No blockers" />}
          </ResearchLayout>
        );
      }}
    </LoadedPage>
  );
}

export function ResearchTimelinePage({ dataService = researchDataService }) {
  const loader = useCallback((options) => dataService.getTimeline(options), [dataService]);
  const state = useResearchResource(loader);
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  return (
    <LoadedPage state={state}>
      {(data) => {
        const items = data.items.filter((item) => (!query || searchable(item.event, item.category, item.result, item.relatedEvidence, ...item.relatedArtifacts).includes(query.toLowerCase())) && (!family || item.familyId === family));
        return (
          <ResearchLayout>
            <PageHeader description="Chronological events from the immutable platform registry." title="Research timeline" />
            <FilterBar onQueryChange={setQuery} placeholder="Event, artifact or evidence" query={query}><SelectFilter label="Family" onChange={setFamily} options={[...new Set(data.items.map((item) => item.familyId).filter(Boolean))]} value={family} /></FilterBar>
            <section className="research-surface timeline-surface"><TimelineList items={items} /></section>
          </ResearchLayout>
        );
      }}
    </LoadedPage>
  );
}

function ValidationTable({ items }) {
  return (
    <div className="research-table-wrap validation-table">
      <table>
        <caption className="sr-only">Validation and evaluation records</caption>
        <thead><tr><th scope="col">Family</th><th scope="col">Validation type</th><th scope="col">Period</th><th scope="col">Outcome</th><th scope="col">Integrity</th><th scope="col">Notes</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
        <tbody>{items.map((item) => <tr key={item.id}><th scope="row">{item.familyId}</th><td>{item.type}</td><td>{item.period}</td><td><StatusPill value={`${item.outcome} ${item.interpretation}`}>{statusLabel(item.outcome)}</StatusPill><span>{statusLabel(item.interpretation).toLowerCase() !== statusLabel(item.outcome).toLowerCase() ? statusLabel(item.interpretation) : null}</span></td><td><StatusPill value={item.integrity}>{statusLabel(item.integrity)}</StatusPill>{item.pristineIntent === true ? <span>Pristine intent: yes</span> : null}</td><td>{item.notes}</td><td><Link aria-label={`Open Family ${item.familyId} validation`} className="research-row-action" to={item.actionPath}>View</Link></td></tr>)}</tbody>
      </table>
    </div>
  );
}

function ArtifactTable({ items }) {
  const viewLineage = () => {
    const disclosure = document.querySelector(".lineage-disclosure");
    if (!disclosure) return;
    disclosure.open = true;
    disclosure.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };
  return (
    <div className="research-table-wrap artifact-table">
      <table>
        <caption className="sr-only">Supporting Research artifacts</caption>
        <thead><tr><th scope="col">Artifact</th><th scope="col">Type</th><th scope="col">Created</th><th scope="col">Integrity</th><th scope="col">Lineage</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead>
        <tbody>{items.map((item) => <tr key={item.artifact_id}><th scope="row"><strong>{item.name}</strong><span>{item.artifact_id}</span></th><td>{statusLabel(item.artifact_type)}</td><td>{formatDate(item.created_at)}</td><td><StatusPill value="POSITIVE">{statusLabel(item.integrity)}</StatusPill></td><td><code>{item.lineage_node_id}</code></td><td><button className="research-row-action" onClick={viewLineage} type="button">View lineage</button></td></tr>)}</tbody>
      </table>
    </div>
  );
}
