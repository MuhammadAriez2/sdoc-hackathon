import {useEffect, useRef} from 'react';
import type {Doc, Observation} from '../types';
import {labels, type ReviewForm} from '../labels';

type Props = {
  doc: Doc;
  field?: string;
  obs?: Observation | null;
  form: ReviewForm;
  busy: boolean;
  waiting: boolean;
  canCorrect: boolean;
  onClose: () => void;
  onSave: () => void;
};

export default function EvidenceDrawer({doc, field, obs, form, busy, waiting, canCorrect, onClose, onSave}: Props) {
  const highlighted = useRef<HTMLDivElement>(null);

  // Bring the cited block into view; an operator should not have to hunt for it.
  useEffect(() => {
    highlighted.current?.scrollIntoView({block: 'center', behavior: 'smooth'});
  }, [doc.id, obs?.field]);

  return (
    <div className="overlay evidence-overlay">
      <section className="modal evidence-modal">
        <div className="section-title">
          <div>
            <span className="eyebrow">SOURCE EVIDENCE / REVISION {doc.revision}</span>
            <h2>{doc.name}</h2>
          </div>
          <button onClick={onClose}>Close</button>
        </div>

        <p className="hash">SHA-256 {doc.sha256}</p>

        {obs && (
          <div className="evidence-summary">
            <strong>{labels[obs.field]}: {obs.raw_value}</strong>
            <p>Normalized: {obs.normalized_value || 'unresolved'} · {obs.confidence}</p>
            <p>{obs.escalation_reason}</p>
            <small>{obs.method}</small>
          </div>
        )}

        <div className="source-blocks">
          {doc.blocks.length ? (
            doc.blocks.map(b => {
              const cited = !!obs?.block_ids.includes(b.id);
              return (
                <div key={b.id} ref={cited ? highlighted : undefined} className={`source-block ${cited ? 'highlight' : ''}`}>
                  <div>
                    <code>{b.id}</code>
                    <small>
                      {Object.entries(b.location).map(([k, v]) => `${k} ${v}`).join(' · ')} · {b.method}
                      {b.method === 'tesseract' ? ` · OCR ${Math.round(b.quality * 100)}/100` : ''}
                    </small>
                  </div>
                  <pre>{b.text}</pre>
                </div>
              );
            })
          ) : (
            <p>No readable source blocks. Download the original or upload a readable revision.</p>
          )}
        </div>

        {doc.active && !!doc.blocks.length && (
          <details className="review-tools" open={!!field}>
            <summary>Confirm or correct extraction</summary>
            <p className="muted">
              Use exact text and block IDs above. Values without source support are rejected. If OCR
              itself is wrong, upload a readable document revision.
            </p>
            <div className="form-row">
              <label>
                Field
                <select value={form.field} onChange={e => form.setField(e.target.value)}>
                  {Object.entries(labels).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                Source block IDs
                <input value={form.blockIds} onChange={e => form.setBlockIds(e.target.value)} placeholder="b7, b8" />
              </label>
            </div>
            <label>
              Exact source value
              <textarea value={form.raw} onChange={e => form.setRaw(e.target.value)} rows={2} />
            </label>
            <div className="form-row">
              <label>Reviewer<input value={form.actor} onChange={e => form.setActor(e.target.value)} /></label>
              <label>Reason<input value={form.reason} onChange={e => form.setReason(e.target.value)} /></label>
            </div>
            <button className="primary" disabled={busy || waiting || !canCorrect} onClick={onSave}>
              Save source-backed correction
            </button>
          </details>
        )}
      </section>
    </div>
  );
}
