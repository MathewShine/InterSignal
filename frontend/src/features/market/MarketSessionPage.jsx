import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MarketWorkspaceHeader, MarketWorkspaceLayout } from "./components/MarketWorkspaceLayout.jsx";
import { marketSessionSummaryUrl, marketWorkspaceApi } from "./data/marketWorkspaceApi.js";

const POLL_INTERVAL_MS = 15_000;
const MONDAY_SELECTED_INSTRUMENT_COUNT = 7;
const MONDAY_SAMPLE_SECONDS = 5;
const MONDAY_SUMMARY_SECONDS = 60;

export const SESSION_UI_STATES = Object.freeze({
  NO_SESSION: "NO_SESSION",
  CREATED: "CREATED",
  PRE_OPEN: "PRE_OPEN",
  RUNNING: "RUNNING",
  DEGRADED: "DEGRADED",
  CLOSED: "CLOSED",
  FAILED: "FAILED",
  COMPLETED: "COMPLETED",
  API_ERROR: "API_ERROR",
});

const ACTIVE_STATES = new Set([
  SESSION_UI_STATES.CREATED,
  SESSION_UI_STATES.PRE_OPEN,
  SESSION_UI_STATES.RUNNING,
  SESSION_UI_STATES.DEGRADED,
  SESSION_UI_STATES.CLOSED,
]);

export function deriveSessionUiState(session, apiError = null) {
  if (apiError) return SESSION_UI_STATES.API_ERROR;
  if (!session) return SESSION_UI_STATES.NO_SESSION;
  return SESSION_UI_STATES[session.status] ?? SESSION_UI_STATES.FAILED;
}

function formatTimestamp(value) {
  if (!value) return "Not recorded";
  return new Date(value).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "medium" });
}

function formatDuration(startedAt, endedAt) {
  if (!startedAt) return "—";
  const seconds = Math.max(0, Math.round((new Date(endedAt ?? Date.now()) - new Date(startedAt)) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours ? `${hours}h ${minutes}m` : minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function relativeAge(value) {
  if (!value) return "No market event yet";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value)) / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
}

function titleCase(value, fallback = "Unavailable") {
  if (!value) return fallback;
  return String(value).toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function streamLabel(value) {
  if (value === "CONNECTED") return "Connected";
  if (!value || value === "NOT_AVAILABLE") return "Idle";
  return titleCase(value);
}

function coverageLabel(session) {
  const coverage = session?.coverage_summary;
  if (!coverage) return "0 / 0";
  return `${coverage.observed_instruments?.length ?? 0} / ${coverage.expected_instruments?.length ?? 0}`;
}

function sessionTitle(uiState) {
  return {
    [SESSION_UI_STATES.NO_SESSION]: "No observation session yet.",
    [SESSION_UI_STATES.CREATED]: "Observation preparing",
    [SESSION_UI_STATES.PRE_OPEN]: "Observation preparing",
    [SESSION_UI_STATES.RUNNING]: "Observation active",
    [SESSION_UI_STATES.DEGRADED]: "Observation degraded",
    [SESSION_UI_STATES.CLOSED]: "Market closed",
    [SESSION_UI_STATES.FAILED]: "Observation failed",
    [SESSION_UI_STATES.COMPLETED]: "Observation completed",
    [SESSION_UI_STATES.API_ERROR]: "Session evidence couldn’t be loaded.",
  }[uiState];
}

function verdictLabel(value) {
  return value === "PASS_WITH_WARNINGS" ? "PASS WITH WARNINGS" : value ?? "In progress";
}

function degradedReason(session) {
  if (session?.stream_state && session.stream_state !== "CONNECTED") return "Provider stream disconnected or unavailable.";
  if (session?.stale_interval_count > 0) return "Stale market data was detected.";
  if (session?.coverage_summary?.missing_instruments?.length) return "Observed coverage is below the expected subscription set.";
  return "Operational session criteria indicate degraded evidence quality.";
}

function useSessionObservation({ includeEvents = false } = {}) {
  const [state, setState] = useState({
    loadStatus: "loading",
    uiState: null,
    session: null,
    providerStatus: null,
    events: [],
    eventsError: null,
    error: null,
  });
  const [operation, setOperation] = useState(null);

  const refresh = useCallback(async ({ signal } = {}) => {
    const providerRequest = marketWorkspaceApi.getProviderStatus({ signal }).catch(() => null);
    try {
      const current = await marketWorkspaceApi.getCurrentSession({ signal });
      const session = current.session ?? null;
      let events = [];
      let eventsError = null;
      if (includeEvents && session) {
        try {
          events = (await marketWorkspaceApi.getSessionEvents(session.session_id, { signal })).items ?? [];
        } catch (error) {
          if (error.code !== "MARKET_WORKSPACE_CANCELLED") eventsError = error;
        }
      }
      const providerStatus = await providerRequest;
      setState({
        loadStatus: "ready",
        uiState: deriveSessionUiState(session),
        session,
        providerStatus,
        events,
        eventsError,
        error: null,
      });
    } catch (error) {
      if (error.code === "MARKET_WORKSPACE_CANCELLED") return;
      setState((value) => ({ ...value, loadStatus: "error", uiState: SESSION_UI_STATES.API_ERROR, error }));
    }
  }, [includeEvents]);

  useEffect(() => {
    const controller = new AbortController();
    refresh({ signal: controller.signal });
    const timer = window.setInterval(() => refresh({ signal: controller.signal }), POLL_INTERVAL_MS);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [refresh]);

  const start = useCallback(async () => {
    if (operation) return;
    setOperation("starting");
    try {
      const session = await marketWorkspaceApi.startSession();
      setState((value) => ({ ...value, loadStatus: "ready", uiState: deriveSessionUiState(session), session, events: [], error: null }));
      await refresh();
    } catch (error) {
      setState((value) => ({ ...value, loadStatus: "error", uiState: SESSION_UI_STATES.API_ERROR, error }));
    } finally {
      setOperation(null);
    }
  }, [operation, refresh]);

  const stop = useCallback(async () => {
    if (operation) return;
    setOperation("stopping");
    try {
      const summary = await marketWorkspaceApi.stopSession();
      const session = summary.session ?? null;
      setState((value) => ({ ...value, loadStatus: "ready", uiState: deriveSessionUiState(session), session, error: null }));
      await refresh();
    } catch (error) {
      setState((value) => ({ ...value, loadStatus: "error", uiState: SESSION_UI_STATES.API_ERROR, error }));
    } finally {
      setOperation(null);
    }
  }, [operation, refresh]);

  return { ...state, operation, refresh, start, stop };
}

function StartButton({ observation }) {
  return <button className="button button--primary" disabled={Boolean(observation.operation)} onClick={observation.start} type="button">{observation.operation === "starting" ? "Starting…" : "Start observation"}</button>;
}

function NoSessionState({ observation }) {
  const provider = observation.providerStatus;
  const marketClosed = provider?.market_session === "CLOSED";
  return (
    <section className="market-session-empty market-workspace-surface">
      <div><span className="technical-label">MARKET OBSERVATION</span><h2>No observation session yet.</h2><p>Start an observation session to record provider health, coverage, freshness and reconnect evidence.</p></div>
      {marketClosed ? <>
        <dl className="market-session-context">
          <div><dt>Market</dt><dd>Closed</dd></div>
          <div><dt>Provider</dt><dd>{titleCase(provider.provider)}</dd></div>
          <div><dt>Stream</dt><dd>{streamLabel(provider.stream_state)}</dd></div>
          <div><dt>Recording</dt><dd>Not started</dd></div>
          <div><dt>Selected instruments</dt><dd>{MONDAY_SELECTED_INSTRUMENT_COUNT}</dd></div>
          <div><dt>Sampling</dt><dd>{MONDAY_SAMPLE_SECONDS} sec</dd></div>
          <div><dt>Summary cadence</dt><dd>{MONDAY_SUMMARY_SECONDS} sec</dd></div>
        </dl>
        <p className="market-session-helper">Starting now will create a closed-market verification session. For full live-session evidence, start during the NSE session.</p>
      </> : null}
      <div className="market-session-empty__action"><StartButton observation={observation} /></div>
    </section>
  );
}

function ApiErrorState({ observation }) {
  return <section className="market-session-error market-workspace-surface" role="alert"><span className="technical-label">MARKET OBSERVATION</span><h2>Session evidence couldn’t be loaded.</h2><p>The Market workspace remains available while the session API is retried.</p><button className="button button--primary" onClick={() => observation.refresh()} type="button">Retry</button></section>;
}

export function MarketSessionOverviewCard() {
  const observation = useSessionObservation();
  const session = observation.session;
  const uiState = observation.uiState;
  const canStop = ACTIVE_STATES.has(uiState);
  const title = uiState ? sessionTitle(uiState) : "Loading observation";
  const provider = session?.provider ?? observation.providerStatus?.provider;
  const stream = session?.stream_state ?? observation.providerStatus?.stream_state;
  const stop = () => {
    if (window.confirm("Stop this observation session?\n\nStopping finalizes recorded evidence.")) observation.stop();
  };

  return (
    <section aria-label="Market session observation" className="market-session-card" data-session-state={uiState ?? "LOADING"}>
      <div><span className="technical-label">SESSION OBSERVATION</span><h2>{title}</h2><p>{uiState === SESSION_UI_STATES.NO_SESSION ? "Record provider health, coverage, freshness and reconnect evidence." : uiState === SESSION_UI_STATES.API_ERROR ? "Session evidence is temporarily unavailable." : "Read-only operational evidence for the NSE market session."}</p></div>
      <dl><div><dt>Provider</dt><dd>{titleCase(provider, "Not started")}</dd></div><div><dt>Stream</dt><dd>{streamLabel(stream)}</dd></div><div><dt>Last market event</dt><dd>{relativeAge(session?.last_market_event_at)}</dd></div><div><dt>Coverage</dt><dd>{coverageLabel(session)}</dd></div></dl>
      <div className="market-session-card__actions"><Link className="market-text-link" to="/app/market/session">Open session evidence</Link>{canStop ? <button className="button button--secondary" disabled={Boolean(observation.operation)} onClick={stop} type="button">{observation.operation === "stopping" ? "Stopping…" : "Stop observation"}</button> : uiState === SESSION_UI_STATES.NO_SESSION || uiState === SESSION_UI_STATES.COMPLETED || uiState === SESSION_UI_STATES.FAILED ? <StartButton observation={observation} /> : uiState === SESSION_UI_STATES.API_ERROR ? <button className="button button--secondary" onClick={() => observation.refresh()} type="button">Retry</button> : null}</div>
    </section>
  );
}

function Metric({ label, value }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function SessionMetrics({ session, uiState }) {
  return <section aria-label="Session metrics" className="market-session-metrics"><Metric label="Provider" value={titleCase(session.provider)} /><Metric label="Stream" value={streamLabel(session.stream_state)} /><Metric label="Last market event" value={relativeAge(session.last_market_event_at)} /><Metric label="Session duration" value={formatDuration(session.started_at, session.ended_at)} /><Metric label="Observed coverage" value={coverageLabel(session)} /><Metric label="Tick observations" value={session.tick_count.toLocaleString("en-GB")} /><Metric label="Disconnects" value={session.disconnect_count} /><Metric label="Reconnects" value={session.reconnect_count} /><Metric label="Stale intervals" value={session.stale_interval_count} /><Metric label="Errors" value={session.error_count} />{uiState === SESSION_UI_STATES.COMPLETED ? <Metric label="Summary snapshots" value={session.summary_snapshot_count} /> : null}</section>;
}

function PreparationState({ session }) {
  return <section className="market-workspace-surface market-session-preparing"><div><span className="technical-label">OBSERVATION PREPARING</span><h2>Observation preparing</h2></div><dl className="market-session-context"><div><dt>Provider state</dt><dd>{titleCase(session.provider)} · {session.provider_mode}</dd></div><div><dt>Stream state</dt><dd>{streamLabel(session.stream_state)}</dd></div><div><dt>Subscriptions</dt><dd>{session.coverage_summary?.active_instruments?.length ?? 0} / {session.instrument_count}</dd></div><div><dt>Start time</dt><dd>{formatTimestamp(session.started_at)}</dd></div></dl></section>;
}

export function MarketSessionPage() {
  const observation = useSessionObservation({ includeEvents: true });
  const [confirmStop, setConfirmStop] = useState(false);
  const session = observation.session;
  const uiState = observation.uiState;
  const coverage = session?.coverage_summary;
  const canStop = ACTIVE_STATES.has(uiState);
  const recentEvents = useMemo(() => [...observation.events].reverse().slice(0, 50), [observation.events]);
  const stop = async () => { setConfirmStop(false); await observation.stop(); };

  return (
    <MarketWorkspaceLayout>
      <MarketWorkspaceHeader actions={canStop ? <button className="button button--secondary" disabled={Boolean(observation.operation)} onClick={() => setConfirmStop(true)} type="button">{observation.operation === "stopping" ? "Stopping…" : "Stop observation"}</button> : null} description="Auditable provider, stream, freshness, coverage and reconnect evidence. No trading actions." eyebrow="NSE · OPERATIONAL EVIDENCE · READ-ONLY MARKET DATA" title="Market Session" />
      {confirmStop ? <section aria-labelledby="stop-observation-title" aria-modal="false" className="market-session-confirm" role="alertdialog"><div><h2 id="stop-observation-title">Stop this observation session?</h2><p>Stopping finalizes recorded evidence.</p></div><div><button className="button button--secondary" onClick={() => setConfirmStop(false)} type="button">Cancel</button><button className="button button--primary" onClick={stop} type="button">Finalize observation</button></div></section> : null}
      {observation.loadStatus === "loading" ? <section className="market-workspace-state is-compact" role="status"><h2>Loading session evidence…</h2></section> : null}
      {uiState === SESSION_UI_STATES.API_ERROR ? <ApiErrorState observation={observation} /> : null}
      {uiState === SESSION_UI_STATES.NO_SESSION ? <NoSessionState observation={observation} /> : null}
      {session ? <>
        <section className="market-session-hero market-workspace-surface" data-session-state={uiState}><div><span className="technical-label">SESSION STATUS</span><h2>{sessionTitle(uiState)}</h2><p>{titleCase(session.provider)} · {session.provider_mode} · {titleCase(session.exchange_session_state)}</p>{uiState === SESSION_UI_STATES.DEGRADED ? <small>{degradedReason(session)}</small> : null}{uiState === SESSION_UI_STATES.CLOSED ? <small>Closed-market quiet periods are not classified as stale or degraded.</small> : null}</div><div className="market-session-verdict"><span>Operational result</span><strong data-state={session.verdict ?? uiState}>{verdictLabel(session.verdict)}</strong></div></section>
        {uiState === SESSION_UI_STATES.CREATED || uiState === SESSION_UI_STATES.PRE_OPEN ? <PreparationState session={session} /> : <SessionMetrics session={session} uiState={uiState} />}
        {uiState === SESSION_UI_STATES.COMPLETED ? <section className="market-session-completed-actions market-workspace-surface"><div><span className="technical-label">FINALIZED EVIDENCE</span><h2>{verdictLabel(session.verdict)}</h2><p>Duration {formatDuration(session.started_at, session.ended_at)} · First tick {formatTimestamp(session.first_tick_at)} · Last tick {formatTimestamp(session.last_tick_at)}</p></div><div><a className="market-text-link" href="#session-timeline">View event timeline</a><a className="market-text-link" href={marketSessionSummaryUrl(session.session_id)} rel="noreferrer" target="_blank">View session report</a></div></section> : null}
        <section className="market-workspace-surface"><div className="market-section-heading"><div><span className="technical-label">MONITORED COVERAGE</span><h2>Expected instruments</h2></div><span>{coverage?.coverage_pct?.toFixed?.(1) ?? "0.0"}% observed</span></div><div className="market-session-instruments">{(coverage?.expected_instruments ?? []).map((instrument) => <span data-observed={coverage?.observed_instruments?.includes(instrument)} key={instrument}>{instrument}</span>)}</div>{coverage?.missing_instruments?.length ? <p className="market-source-note">Not actively subscribed: {coverage.missing_instruments.join(", ")}.</p> : null}</section>
        <section className="market-workspace-surface" id="session-timeline"><div className="market-section-heading"><div><span className="technical-label">APPEND-ONLY EVIDENCE</span><h2>Recent operational events</h2></div><span>{observation.events.length} recorded</span></div>{observation.eventsError ? <div className="market-empty-copy">The event timeline is temporarily unavailable; session status remains usable.</div> : recentEvents.length ? <div className="market-table-wrap"><table aria-label="Market session event timeline"><thead><tr><th>Time</th><th>Event</th><th>Instrument / scope</th><th>State</th><th>Reason</th></tr></thead><tbody>{recentEvents.map((event) => <tr key={event.event_id}><td>{formatTimestamp(event.timestamp)}</td><td>{event.event_type.replaceAll("_", " ")}</td><td>{event.instrument_id ?? "Session"}</td><td>{event.freshness ?? session.status}</td><td>{event.reason_code ?? "—"}</td></tr>)}</tbody></table></div> : <div className="market-empty-copy">No operational events have been recorded.</div>}</section>
      </> : null}
    </MarketWorkspaceLayout>
  );
}

export { POLL_INTERVAL_MS, coverageLabel, sessionTitle };
