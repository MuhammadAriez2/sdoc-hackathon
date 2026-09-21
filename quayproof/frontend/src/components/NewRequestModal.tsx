import type {FormEvent} from 'react';
import type {Config} from '../types';

type Props = {
  config: Config | null;
  busy: boolean;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export default function NewRequestModal({config, busy, onClose, onSubmit}: Props) {
  return (
    <div className="overlay">
      <form className="modal" onSubmit={onSubmit}>
        <div className="section-title">
          <h2>New shipping request</h2>
          <button type="button" onClick={onClose}>Close</button>
        </div>

        <div className="form-row">
          <label>
            Email ID
            <input name="email_id" required pattern="[A-Za-z0-9_-]{1,80}" defaultValue={'request-' + Date.now()} />
          </label>
          <label>
            Sender
            <input name="sender" placeholder="operations@example.invalid" />
          </label>
        </div>

        <label>Subject<input name="subject" required maxLength={500} /></label>
        <label>Email body<textarea name="body" required rows={5} maxLength={40000} /></label>

        <label>
          Attachments · up to six, 10 MB each
          <input name="files" type="file" multiple accept=".txt,.pdf,.docx,.xlsx" />
          <small className="field-hint">Supported files: TXT · PDF · DOCX tables · XLSX</small>
        </label>

        {config?.provider === 'gemini' && (
          <label className="checkbox">
            <input type="checkbox" name="cloud_permitted" value="true" required />
            I confirm the email and attachments are synthetic or appropriately sanitized, authorized,
            non-sensitive inputs permitted by the unpaid Gemini terms.
          </label>
        )}

        <p className="muted">
          Files are kept in the selected storage backend. The app never sends email or changes the
          source documents.
        </p>
        <button disabled={busy} className="primary">Create and process</button>
      </form>
    </div>
  );
}
