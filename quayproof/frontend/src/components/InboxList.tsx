import type {Case} from '../types';
import {filterLabels, nice, stateLabel} from '../labels';

type Props = {
  visible: Case[];
  total: number;
  hasAnyCase: boolean;
  filter: string;
  selected: string;
  onSelect: (id: string) => void;
  onChooseFilter: (filter: string) => void;
  onExport: () => void;
};

export default function InboxList({visible, total, hasAnyCase, filter, selected, onSelect, onChooseFilter, onExport}: Props) {
  return (
    <div className="inbox">
      <div className="section-title">
        <div>
          <h2>{filterLabels[filter] || 'All emails'}</h2>
          <small className="inbox-count" aria-live="polite">
            Showing {visible.length} of {total} emails
          </small>
        </div>
        <button
          title="Export the whole workspace, not only this view"
          className="text-button"
          onClick={onExport}
        >
          Export
        </button>
      </div>

      {visible.length === 0 ? (
        <div className="empty">
          <span>◫</span>
          <h3>{hasAnyCase ? 'No emails in this view.' : 'Your inbox is ready.'}</h3>
          <p>
            {hasAnyCase
              ? 'Choose another category or return to all emails.'
              : 'Load nine synthetic examples or add an email with optional attachments.'}
          </p>
          {filter !== 'all' && (
            <button className="empty-reset" onClick={() => onChooseFilter('all')}>
              Show all emails
            </button>
          )}
        </div>
      ) : (
        visible.map(c => (
          <button
            className={`inbox-item ${selected === c.id ? 'chosen' : ''}`}
            key={c.id}
            onClick={() => onSelect(c.id)}
          >
            <div>
              <code>{c.id}</code>
              <span className={`badge ${c.result?.status || c.state}`}>{nice(stateLabel(c))}</span>
            </div>
            <strong>{c.subject}</strong>
            <p>{c.classification ? nice(c.classification.category) : c.stage}</p>
            <small>
              {c.result?.has_defect ? `${c.result.defect_fields.length} field discrepancy · ` : ''}
              {c.synthetic ? 'Synthetic demo' : c.sender || 'Imported request'}
              {c.approved ? ' · Acknowledged' : ''}
            </small>
          </button>
        ))
      )}
    </div>
  );
}
