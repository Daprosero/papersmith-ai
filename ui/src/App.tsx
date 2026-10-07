import { useCallback, useEffect, useMemo, useState } from 'react';
import { useWorkspaceEvents } from './hooks/useWorkspaceEvents';
import { usePaperPreview } from './hooks/usePaperPreview';
import { useAtlas } from './hooks/useAtlas';
import { useDecisions } from './hooks/useDecisions';
import { useTheme } from './hooks/useTheme';
import PipelineGraph from './components/dag/PipelineGraph';
import ElementDetailPanel from './components/dag/ElementDetailPanel';
import { buildGraph } from './components/dag/graph';
import HarnessStatus from './components/health/HarnessStatus';
import WiringMatrix from './components/health/WiringMatrix';
import DiagnosticLog from './components/health/DiagnosticLog';
import SectionMatrix from './components/sections/SectionMatrix';
import HistoryView from './components/history/HistoryView';
import PreviewView from './components/preview/PreviewView';
import AtlasView from './components/atlas/AtlasView';
import DecisionsView from './components/decisions/DecisionsView';
import ArtifactViewer from './components/artifacts/ArtifactViewer';
import { StatusBadge } from './components/StatusBadge';
import { ThemeToggle } from './components/ThemeToggle';
import { asText, formatCount, formatTime } from './lib/format';
import { TABS, formatHash, parseHash, type HashRoute, type TabId } from './lib/hash';
import type { WorkspaceState } from './types';

function readRoute(): HashRoute {
  return parseHash(window.location.hash);
}

function TotalsBar({ state }: { state: WorkspaceState | null }) {
  const totals = state?.totals;
  const chips: { label: string; value: string }[] = [
    { label: 'sections', value: formatCount(totals?.sections) },
    { label: 'blocks', value: `${formatCount(totals?.blocks_written)}/${formatCount(totals?.blocks_total)}` },
    { label: 'words', value: formatCount(totals?.word_count) },
    { label: 'placeholder citations', value: formatCount(totals?.placeholder_citations) },
    { label: 'gates passed', value: `${formatCount(totals?.gates_passed)}/${formatCount(totals?.gates_total)}` },
  ];
  return (
    <div className="totals">
      {chips.map((chip) => (
        <span key={chip.label} className="totals__chip">
          <strong>{chip.value}</strong>
          {chip.label}
        </span>
      ))}
    </div>
  );
}

export default function App() {
  const { state, health, connected, lastChanged, revision, loading, error, smoke, history, historyError, runSmoke, clearSmoke } =
    useWorkspaceEvents();
  // App is the single owner of the route: the tab and the selected diagram
  // element, mirrored into the URL hash.
  const [route, setRoute] = useState<HashRoute>(() => readRoute());
  const tab = route.tab;
  // Lazy: the preview is fetched only while its tab is open, and again when the workspace changes.
  const preview = usePaperPreview(tab === 'preview', revision);
  // Atlas files are not watched: fetched when its tab opens and on its Refresh button only.
  const atlas = useAtlas(tab === 'atlas');
  // Decision sources are not watched either: tab open and Refresh only.
  const decisions = useDecisions(tab === 'decisions');
  const { theme, toggle: toggleTheme } = useTheme();

  useEffect(() => {
    const onHashChange = () => setRoute(readRoute());
    window.addEventListener('hashchange', onHashChange);
    // Normalize `#` and unknown fragments to a real tab on first paint,
    // keeping a valid deep-linked element id.
    const canonical = formatHash(route.tab, route.el);
    if (window.location.hash !== canonical) {
      window.history.replaceState(null, '', canonical);
    }
    return () => window.removeEventListener('hashchange', onHashChange);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial normalization only
  }, []);

  // Readiness signal for the visual checker: "1" once a state payload is
  // applied, "error" when the state could not be loaded at all.
  const ready = state !== null ? '1' : !loading && error ? 'error' : null;
  useEffect(() => {
    if (ready === null) {
      delete document.body.dataset.ready;
    } else {
      document.body.dataset.ready = ready;
    }
    return () => {
      delete document.body.dataset.ready;
    };
  }, [ready]);

  /**
   * Set the tab and the selected element together. State is set directly (so
   * selecting the same element twice never depends on `hashchange`) and the
   * hash is written with replaceState; a tab change adds one history entry.
   */
  const navigate = useCallback((next: TabId, el: string | null = null) => {
    const hash = formatHash(next, el);
    if (window.location.hash !== hash) {
      if (next !== readRoute().tab) window.history.pushState(null, '', hash);
      else window.history.replaceState(null, '', hash);
    }
    setRoute({ tab: next, el });
  }, []);

  const pipelineGraph = useMemo(() => buildGraph(state, 'pipeline'), [state]);
  const writingGraph = useMemo(() => buildGraph(state, 'writing'), [state]);
  // The detail panel and the deep links are shared, so the active tab decides
  // which flow an element id resolves against.
  const graph = tab === 'writing' ? writingGraph : pipelineGraph;
  const presentIds = useMemo(() => new Set(graph.nodes.map((node) => node.id)), [graph]);
  const selectElement = useCallback(
    (id: string | null) => navigate(tab === 'writing' ? 'writing' : 'pipeline', id),
    [navigate, tab],
  );

  const selectTab = useCallback((next: TabId) => navigate(next), [navigate]);

  const workspace = state?.workspace;
  const paper = state?.paper_metadata;
  const authors = (paper?.authors ?? []).map(asText).filter((author): author is string => Boolean(author));

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar__identity">
          <h1>Paper Command Center</h1>
          <p className="topbar__subtitle">
            {workspace?.name ?? paper?.title ?? 'no workspace loaded'}
            {workspace?.version ? ` · v${workspace.version}` : ''}
            {state?.generated_at ? ` · state read ${formatTime(state.generated_at)}` : ''}
          </p>
        </div>
        <div className="topbar__status">
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <StatusBadge label={connected ? 'LIVE' : 'RECONNECTING'} tone={connected ? 'ok' : 'warn'} />
          {lastChanged.length > 0 ? (
            <span className="topbar__changed" title={lastChanged.join('\n')}>
              changed: {lastChanged.slice(0, 3).join(', ')}
              {lastChanged.length > 3 ? ` (+${lastChanged.length - 3})` : ''}
            </span>
          ) : null}
        </div>
      </header>

      <nav className="tabs" aria-label="Dashboard sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            className="tabs__button"
            data-active={tab === entry.id}
            aria-current={tab === entry.id ? 'page' : undefined}
            onClick={() => selectTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {error ? <p className="banner banner--bad">{error}</p> : null}

        {tab === 'pipeline' ? (
          <>
            <section className="panel panel--paper">
              <div className="panel__header">
                <h2>{paper?.title ?? paper?.name ?? 'Paper metadata unavailable'}</h2>
                <span className="panel__meta">
                  {paper?.venue_target ?? 'no venue target'} · {paper?.domain_profile ?? 'no domain profile'}
                </span>
              </div>
              <dl className="meta-strip">
                <div>
                  <dt>Topic</dt>
                  <dd>{paper?.topic ?? '—'}</dd>
                </div>
                <div>
                  <dt>Authors</dt>
                  <dd>{authors.length > 0 ? authors.join(', ') : '—'}</dd>
                </div>
                <div>
                  <dt>Compute target</dt>
                  <dd>{paper?.compute_target ?? '—'}</dd>
                </div>
                <div>
                  <dt>Active tools</dt>
                  <dd>{(paper?.tools ?? []).map(asText).filter(Boolean).join(', ') || '—'}</dd>
                </div>
                <div>
                  <dt>Workspace root</dt>
                  <dd className="mono">{workspace?.root ?? '—'}</dd>
                </div>
              </dl>
              <TotalsBar state={state} />
            </section>

            <PipelineGraph graph={graph} selectedId={route.el} onSelect={selectElement} />
            {route.el ? (
              <ElementDetailPanel
                elementId={route.el}
                state={state}
                graph={graph}
                history={history}
                onSelect={selectElement}
              />
            ) : null}

            <section className="panel">
              <div className="panel__header">
                <h2>Gate detail</h2>
                <span className="panel__meta">{formatCount(state?.gates?.length)} gate(s)</span>
              </div>
              {(state?.gates ?? []).length === 0 ? (
                <p className="panel__empty">No gate results in the latest state payload.</p>
              ) : (
                <ul className="gate-list">
                  {(state?.gates ?? []).map((gate) => (
                    <li key={gate.id} className="gate-list__item">
                      <div className="gate-list__head">
                        <span className="cell-title">{gate.name ?? gate.id}</span>
                        <StatusBadge
                          label={gate.state ?? 'UNKNOWN'}
                          tone={
                            gate.state === 'PASSED' ? 'ok' : gate.state === 'BLOCKED' ? 'bad' : 'warn'
                          }
                        />
                      </div>
                      <p className="mono gate-list__id">{gate.id}</p>
                      {(gate.reasons ?? []).length > 0 ? (
                        <ul className="reason-list">
                          {(gate.reasons ?? []).map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="cell-sub">no blocking reason</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}

        {tab === 'writing' ? (
          <>
            <PipelineGraph
              flow="writing"
              graph={writingGraph}
              selectedId={route.el}
              onSelect={selectElement}
            />
            {route.el ? (
              <ElementDetailPanel
                elementId={route.el}
                state={state}
                graph={writingGraph}
                history={history}
                onSelect={selectElement}
              />
            ) : null}
          </>
        ) : null}

        {tab === 'health' ? (
          <>
            <HarnessStatus health={health} />
            <WiringMatrix health={health} />
            <DiagnosticLog smoke={smoke} runSmoke={runSmoke} clearSmoke={clearSmoke} connected={connected} />
          </>
        ) : null}

        {tab === 'sections' ? <SectionMatrix sections={state?.sections ?? []} /> : null}

        {tab === 'history' ? (
          <HistoryView history={history} error={historyError} presentIds={state === null ? null : presentIds} onSelect={selectElement} />
        ) : null}

        {tab === 'preview' ? (
          <PreviewView data={preview.data} loading={preview.loading} error={preview.error} retry={preview.retry} />
        ) : null}

        {tab === 'atlas' ? (
          <AtlasView data={atlas.data} loading={atlas.loading} error={atlas.error} refresh={atlas.refresh} retry={atlas.retry} />
        ) : null}

        {tab === 'decisions' ? (
          <DecisionsView
            data={decisions.data}
            loading={decisions.loading}
            error={decisions.error}
            refresh={decisions.refresh}
            retry={decisions.retry}
          />
        ) : null}

        {tab === 'artifacts' ? <ArtifactViewer state={state} /> : null}

        {loading && state === null && health === null ? (
          <p className="banner banner--info">Loading the workspace snapshot…</p>
        ) : null}
      </main>
    </div>
  );
}
