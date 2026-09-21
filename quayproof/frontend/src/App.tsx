import {useCallback, useEffect, useState, FormEvent} from 'react';
import type {Case, Config, Doc, Observation} from './types';
import {categories, categoryFilters, matchesFilter, nice, stateLabel} from './labels';
import InboxList from './components/InboxList';
import ComparisonTable from './components/ComparisonTable';
import EvidenceDrawer from './components/EvidenceDrawer';
import NewRequestModal from './components/NewRequestModal';

export default function App() {
  const [token, setToken] = useState(sessionStorage.getItem('qp-token') || '');
  const [needsAuth, setNeedsAuth] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Case | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('all');
  const [showNew, setShowNew] = useState(false);
  const [evidence, setEvidence] = useState<{doc: Doc; field?: string; obs?: Observation | null} | null>(null);

  // Review-form state is shared by the evidence drawer and the audit panel.
  const [actor, setActor] = useState('Team reviewer');
  const [reason, setReason] = useState('Verified against the source document');
  const [raw, setRaw] = useState('');
  const [blockIds, setBlockIds] = useState('');
  const [reviewField, setReviewField] = useState('gross_weight_kg');
  const [category, setCategory] = useState('GENERAL');
  const form = {
    actor, setActor, reason, setReason, raw, setRaw,
    blockIds, setBlockIds, field: reviewField, setField: setReviewField,
  };

  const api = useCallback(async (path: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch('/api' + path, {...options, headers});
    if (response.status === 401) setNeedsAuth(true);
    if (!response.ok) {
      const body = await response.json().catch(() => ({detail: 'Server unavailable'}));
      throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
    }
    return response;
  }, [token]);

  const reload = useCallback(async () => {
    const [cfg, list] = await Promise.all([
      api('/config').then(r => r.json()),
      api('/cases').then(r => r.json()),
    ]);
    setNeedsAuth(false);
    setConfig(cfg);
    setCases(list);
    if (selected) setDetail(await api(`/cases/${selected}`).then(r => r.json()));
  }, [api, selected]);

  useEffect(() => {
    void reload().catch(e => setError(e.message));
    const id = setInterval(() => void reload().catch(e => setError(e.message)), 3000);
    return () => clearInterval(id);
  }, [reload]);

  useEffect(() => { setEvidence(null); }, [selected]);

  useEffect(() => {
    const current = cases.find(c => c.id === selected);
    if (current && !matchesFilter(current, filter)) {
      setSelected(''); setDetail(null); setEvidence(null);
    }
  }, [cases, selected, filter]);

  function chooseFilter(next: string) {
    setFilter(next); setSelected(''); setDetail(null); setEvidence(null);
  }

  async function action(fn: () => Promise<void>) {
    setBusy(true); setError('');
    try { await fn(); await reload(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  const post = (path: string, data: unknown) =>
    api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});

  function inspect(doc: Doc, field?: string, obs?: Observation | null) {
    setEvidence({doc, field, obs});
    setRaw(obs?.raw_value || '');
    setBlockIds(obs?.block_ids.join(', ') || '');
    setReviewField(field || 'gross_weight_kg');
  }

  async function download(path: string, name: string) {
    const res = await api(path);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (!(data.get('files') as File)?.name) data.delete('files');
    await action(async () => {
      const created = await api('/cases', {method: 'POST', body: data}).then(r => r.json());
      await post(`/cases/${created.id}/run`, {version: created.version});
      setFilter('all'); setSelected(created.id); setShowNew(false);
    });
  }

  async function review(kind: string) {
    if (!detail) return;
    await action(async () => {
      await post(`/cases/${detail.id}/review`, {
        version: detail.version, action: kind, actor, reason,
        ...(kind === 'classify' ? {category} : {}),
        ...(kind === 'correct_field' ? {
          document_id: evidence?.doc.id, field: reviewField, raw_value: raw,
          block_ids: blockIds.split(',').map(x => x.trim()).filter(Boolean),
        } : {}),
      });
      setEvidence(null);
    });
  }

  /** Cloud consent is re-asked per upload; the backend refuses Gemini without it. */
  function consentForUpload() {
    if (config?.provider !== 'gemini') return {ok: true, consent: false};
    const consent = window.confirm(
      'This file is synthetic or sanitized, non-sensitive and permitted under the unpaid Gemini terms. Allow cloud AI processing?');
    return {ok: consent, consent};
  }

  async function revise(file: File, doc: Doc) {
    if (!detail) return;
    const {ok, consent} = consentForUpload();
    if (!ok) return;
    const data = new FormData();
    data.set('version', String(detail.version));
    data.set('actor', actor); data.set('reason', reason);
    data.set('file', file); data.set('cloud_permitted', String(consent));
    await action(async () => {
      await api(`/cases/${detail.id}/documents/${doc.id}/revision`, {method: 'POST', body: data});
      setEvidence(null);
    });
  }

  async function addAttachment(file: File) {
    if (!detail) return;
    const {ok, consent} = consentForUpload();
    if (!ok) return;
    const data = new FormData();
    data.set('version', String(detail.version));
    data.set('file', file); data.set('cloud_permitted', String(consent));
    await action(async () => {
      await api(`/cases/${detail.id}/documents`, {method: 'POST', body: data});
    });
  }

  const totals = {
    all: cases.length,
    defects: cases.filter(c => c.result?.has_defect).length,
    review: cases.filter(c => c.result?.requires_review).length,
    clear: cases.filter(c => c.result?.status === 'OK').length,
  };
  const categoryCounts = Object.fromEntries(
    categoryFilters.map(([key]) => [key, cases.filter(c => matchesFilter(c, key)).length]));
  const visible = cases.filter(c => matchesFilter(c, filter));
  const active = detail?.documents?.filter(d => d.active) || [];
  const waiting = detail?.state === 'queued' || detail?.state === 'processing';
  const failures = cases.filter(c => c.state === 'failed').length;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand"><span className="mark">Q</span>QuayProof</div>
        <p className="rail-caption">SHIPPING ASSURANCE</p>
        <button className={`nav ${filter !== 'review' && filter !== 'failures' ? 'active' : ''}`} onClick={() => chooseFilter('all')}>
          ▤ &nbsp; Operations inbox <span>{totals.all}</span>
        </button>
        <button className={`nav ${filter === 'review' ? 'active' : ''}`} onClick={() => chooseFilter('review')}>
          ◈ &nbsp; Review queue <span>{totals.review}</span>
        </button>
        <button className={`nav ${filter === 'failures' ? 'active' : ''}`} onClick={() => chooseFilter('failures')}>
          ↻ &nbsp; Processing failures <span>{failures}</span>
        </button>
        <div className="rail-bottom"><p>Every decision,<br />backed by evidence.</p></div>
      </aside>

      <main>
        <header>
          <div>
            <span className="eyebrow">CONTROL DESK / INBOX</span>
            <h1>Know what can ship.</h1>
            <p>Compare the instruction. Verify the draft. Resolve the exceptions.</p>
          </div>
          <div className="header-actions">
            <button disabled={busy} onClick={() => void action(async () => { await api('/demo', {method: 'POST'}); })}>
              Load demo inbox
            </button>
            <button className="primary" onClick={() => setShowNew(true)}>+ New request</button>
          </div>
        </header>

        <div className="mode">
          <span className="dot" />
          <strong>{config?.provider === 'demo' ? 'Offline demo · deterministic fixtures' : `${config?.provider || 'Connecting'} AI`}</strong>
          <span>
            {config?.provider === 'demo'
              ? 'Connect Gemini or Ollama to enable AI classification and extraction.'
              : 'Decisions use source evidence and deterministic comparisons.'}
          </span>
          <span className="mode-right">{config?.daily_call_limit || 100} AI calls/day app cap</span>
        </div>

        {error && <div className="alert" role="alert">{error}<button onClick={() => setError('')}>Dismiss</button></div>}
        {config && !config.provider_configured && (
          <div className="alert">AI settings are incomplete. Check the backend environment and restart it.</div>
        )}

        <section className="stats">
          {([['all', 'Total emails'], ['clear', 'All seven match'], ['defects', 'Confirmed defects'], ['review', 'Need human review']] as const).map(([key, label]) => (
            <button key={key} className={filter === key ? 'stat selected' : 'stat'} onClick={() => chooseFilter(key)} aria-pressed={filter === key}>
              <span>{label}</span>
              <strong>{totals[key]}</strong>
              <small>
                {key === 'all' ? 'Current workspace'
                  : key === 'clear' ? 'Comparison complete'
                  : key === 'defects' ? 'May also need review'
                  : 'Uncertainty stays visible'}
              </small>
            </button>
          ))}
        </section>

        <section className="category-section" aria-labelledby="category-heading">
          <div className="category-heading"><h2 id="category-heading">Email categories</h2></div>
          <div className="category-filters" role="group" aria-label="Filter emails by category">
            {categoryFilters.map(([key, label]) => (
              <button
                key={key}
                className={`category-filter ${filter === key ? 'selected' : ''}`}
                aria-pressed={filter === key}
                aria-label={`${label}: ${categoryCounts[key]} emails`}
                onClick={() => chooseFilter(key)}
              >
                <span>{label}</span>
                <span className="category-count" aria-hidden="true">{categoryCounts[key]}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="workspace">
          <InboxList
            visible={visible}
            total={totals.all}
            hasAnyCase={cases.length > 0}
            filter={filter}
            selected={selected}
            onSelect={id => { setSelected(id); setDetail(null); }}
            onChooseFilter={chooseFilter}
            onExport={() => void action(() => download('/export', 'submission.json'))}
          />

          <div className="case-panel">
            {!detail || detail.id !== selected || !matchesFilter(detail, filter) ? (
              <div className="empty large">
                <span>◎</span>
                <h2>{selected ? 'Loading email…' : 'One decision. The whole evidence trail.'}</h2>
                <p>Select an email to see its classification and source evidence.</p>
              </div>
            ) : (
              <>
                <div className="case-heading">
                  <div>
                    <span className="eyebrow">{detail.id} / {detail.synthetic ? 'SYNTHETIC DEMO' : 'SHIPPING REQUEST'}</span>
                    <h2>{detail.subject}</h2>
                  </div>
                  <span className={`badge big ${detail.result?.status || detail.state}`}>{nice(stateLabel(detail))}</span>
                </div>

                <p className="email-body">{detail.body}</p>

                <div className="classification">
                  <strong>{detail.classification ? nice(detail.classification.category) : 'Awaiting classification'}</strong>
                  <p>{detail.classification?.reason || 'Run the pipeline to classify the current email intent.'}</p>
                  {detail.classification?.evidence && <blockquote>{detail.classification.evidence}</blockquote>}
                </div>

                <div className="toolbar">
                  <button disabled={busy || waiting} onClick={() => void action(async () => { await post(`/cases/${detail.id}/run`, {version: detail.version}); })}>
                    {detail.state === 'failed' ? 'Retry processing' : 'Run / resume'}
                  </button>
                  <span>{waiting ? `Processing · ${detail.stage}` : detail.approved ? 'Report acknowledged' : 'Source instruction is the reference'}</span>
                </div>

                {detail.error && <div className="alert">{detail.error}</div>}

                {detail.result?.requires_review && (
                  <div className="review-banner">
                    <strong>Human review required</strong>
                    <p>
                      {detail.result.review_note || nice(detail.result.review_reason || 'unknown value')}.
                      Confirmed differences remain visible. Approval is blocked until uncertainty is resolved.
                    </p>
                  </div>
                )}

                {detail.result?.status === 'OK' && detail.result.review_note && !detail.result.requires_review && (
                  <div className="note-banner">
                    <strong>Nothing to compare</strong>
                    <p>{detail.result.review_note}</p>
                  </div>
                )}

                {detail.result && <ComparisonTable result={detail.result} activeDocs={active} onInspect={inspect} />}

                <div className="section-title"><h3>Source documents</h3><small>Immutable revisions</small></div>
                <div className="documents">
                  {detail.documents.map(doc => (
                    <div className={`document ${!doc.active ? 'archived' : ''}`} key={doc.id}>
                      <div>
                        <strong>{doc.doc_type || 'Document'} · {doc.name}</strong>
                        <small>Revision {doc.revision} {doc.active ? '· active' : '· superseded'}</small>
                        {doc.parse_error && <p className="error-text">{doc.parse_error}</p>}
                      </div>
                      <button onClick={() => inspect(doc)}>Evidence</button>
                      <button onClick={() => void action(() => download(`/cases/${detail.id}/documents/${doc.id}`, doc.name))}>Original</button>
                      {doc.active && (
                        <label className={`button ${waiting ? 'disabled' : ''}`}>
                          New revision
                          <input
                            aria-label={`New revision for ${doc.name}`}
                            type="file" accept=".txt,.pdf,.docx,.xlsx" disabled={busy || waiting}
                            onChange={e => { if (e.target.files?.[0]) void revise(e.target.files[0], doc); e.target.value = ''; }}
                          />
                        </label>
                      )}
                    </div>
                  ))}
                </div>

                {active.length < 6 && (
                  <label className="button">
                    + Add missing attachment
                    <input
                      aria-label="Add missing attachment"
                      type="file" accept=".txt,.pdf,.docx,.xlsx" disabled={busy || waiting}
                      onChange={e => { if (e.target.files?.[0]) void addAttachment(e.target.files[0]); e.target.value = ''; }}
                    />
                  </label>
                )}

                <details className="review-tools">
                  <summary>Review actions and audit trail</summary>
                  <div className="form-row">
                    <label>Reviewer<input value={actor} onChange={e => setActor(e.target.value)} /></label>
                    <label>Reason<input value={reason} onChange={e => setReason(e.target.value)} /></label>
                  </div>
                  <div className="toolbar">
                    <select aria-label="Override email category" value={category} onChange={e => setCategory(e.target.value)}>
                      {categories.map(c => <option key={c}>{c}</option>)}
                    </select>
                    <button disabled={busy || waiting} onClick={() => void review('classify')}>Correct category</button>
                    <button
                      disabled={busy || waiting || detail.state !== 'complete' || detail.result?.requires_review}
                      onClick={() => void review('approve')}
                    >
                      Acknowledge report
                    </button>
                  </div>
                  <p className="muted">
                    Acknowledgement preserves the comparison result. Reviewer names are team-entered;
                    this prototype does not verify individual identities.
                  </p>
                  {detail.audit.map((a, i) => (
                    <div className="audit" key={i}>
                      <strong>{nice(a.action)} · {a.actor}</strong>
                      <span>{new Date(a.at * 1000).toLocaleString()}</span>
                      <p>{a.reason}</p>
                    </div>
                  ))}
                </details>
              </>
            )}
          </div>
        </section>
      </main>

      {needsAuth && (
        <div className="overlay">
          <form
            className="modal compact"
            onSubmit={e => { e.preventDefault(); sessionStorage.setItem('qp-token', token); void action(reload); }}
          >
            <span className="eyebrow">TEAM WORKSPACE</span>
            <h2>Enter your access token</h2>
            <p>Ask the teammate who deployed QuayProof. API keys never belong here.</p>
            <input aria-label="Team access token" type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} required />
            <button className="primary">Open workspace</button>
          </form>
        </div>
      )}

      {showNew && <NewRequestModal config={config} busy={busy} onClose={() => setShowNew(false)} onSubmit={create} />}

      {evidence && detail && (
        <EvidenceDrawer
          doc={evidence.doc}
          field={evidence.field}
          obs={evidence.obs}
          form={form}
          busy={busy}
          waiting={waiting}
          canCorrect={detail.state === 'complete'}
          onClose={() => setEvidence(null)}
          onSave={() => void review('correct_field')}
        />
      )}
    </div>
  );
}
