import type {Doc, Observation, Result} from '../types';
import {labels} from '../labels';

type Props = {
  result: Result;
  activeDocs: Doc[];
  onInspect: (doc: Doc, field?: string, obs?: Observation | null) => void;
};

const decisionLabel: Record<string, string> = {
  MATCH: '✓ Match',
  DIFFERENT: '≠ Difference',
  UNKNOWN: '? Review',
};

export default function ComparisonTable({result, activeDocs, onInspect}: Props) {
  if (!result.comparisons.length) return null;

  return (
    <>
      <div className="section-title">
        <h3>The seven-field check</h3>
        <small>Click a value for source evidence</small>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>SI · source of truth</th>
              <th>Draft BL</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {result.comparisons.map(row => (
              <tr key={row.field} className={row.outcome}>
                <th>{labels[row.field]}</th>
                {(['si', 'bl'] as const).map(side => {
                  const obs = row[side];
                  const doc =
                    activeDocs.find(d => d.id === obs?.document_id) ||
                    activeDocs.find(d => d.doc_type === side.toUpperCase());
                  return (
                    <td key={side}>
                      <button className="value" disabled={!doc} onClick={() => doc && onInspect(doc, row.field, obs)}>
                        {obs?.raw_value || 'Missing value'}
                        <small>
                          {obs?.normalized_value || 'Unresolved'}
                          {obs?.confidence === 'human-confirmed' ? ' · human confirmed' : ''}
                        </small>
                      </button>
                    </td>
                  );
                })}
                <td>
                  <span className={`decision ${row.outcome}`}>{decisionLabel[row.outcome] ?? row.outcome}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
