#!/usr/bin/env python3
"""Run participant emails through QuayProof/Gemini, one case at a time.

Python 3.10+; standard library only. Run on your laptop while QuayProof is up.
Reads inbox/email_*.json and only their referenced attachments. Never reads an
organizer archive, scorer, label file, or answer key. Results are predictions,
not an accuracy measurement or a competition submission.

Example (from the quayproof directory):
  python3 scripts/test_ai_bundle.py --source "$QUAYPROOF_DATASET_DIR" --limit 5 --cloud-permitted
  python3 scripts/test_ai_bundle.py --source "$QUAYPROOF_DATASET_DIR" --limit 0 --cloud-permitted

After resolving a failure or waiting for quota renewal, repeat with
--retry-failed. Completed Gemini cases are skipped. Ctrl+C stops this runner;
the one case already queued may finish in the backend. Do not run two copies.

The report is a snapshot of the selected cases inspected in this invocation.
Re-running with --limit 0 rebuilds it from persisted app records. No API key
belongs in this script. If app authentication is enabled, set QP_ACCESS_TOKEN.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ACTIVE = {'queued', 'processing'}
PRIVATE_NAME = re.compile(
    r'ground[\W_]*truth|answer[\W_]*key|scoring[\W_]*labels|'
    r'(?:secret|private)[\W_]*(?:labels|scoring)', re.I)


class StopBatch(RuntimeError):
    pass


class Client:
    def __init__(self, api, token=''):
        self.api, self.token = api.rstrip('/'), token

    def request(self, route, data=None, mime='application/json'):
        headers = {'Content-Type': mime}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        req = urllib.request.Request(self.api + route, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read(3000).decode('utf-8', errors='replace')
            if self.token:
                detail = detail.replace(self.token, '[REDACTED]')
            raise StopBatch(f'App HTTP {exc.code}: {detail}') from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise StopBatch('Cannot reach QuayProof. Check Docker and --api, then rerun. '
                            'A request already accepted by the app may still finish.') from exc

    def create(self, fields, files):
        boundary = 'quayproof-' + uuid.uuid4().hex
        parts = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; '
                         f'name="{name}"\r\n\r\n{value}\r\n'.encode())
        for name, data in files:
            # These are also the names used when comparing a resumed upload.
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                         f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                         + data + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        return self.request('/api/cases', b''.join(parts),
                            f'multipart/form-data; boundary={boundary}')


def check_config(client):
    config = client.request('/api/config')
    if config.get('provider') != 'gemini' or not config.get('provider_configured'):
        raise StopBatch('The running app must have AI_PROVIDER=gemini and a configured '
                        'key/model. Recreate its Docker container after changing .env.')
    return config


def bounded_read(path, maximum):
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise StopBatch(f'File exceeds the app size limit: {path.name}')
    return data


def load_record(path, inbox, attachments, root, prefix):
    resolved = path.resolve()
    if not resolved.is_relative_to(inbox) or PRIVATE_NAME.search(path.name):
        raise StopBatch('Inbox reference is outside the authorized inputs.')
    email = json.loads(bounded_read(resolved, 1_000_000))
    if not isinstance(email, dict) or not isinstance(email.get('email_id'), str):
        raise StopBatch(f'Expected an email record in {path.name}')
    original_id = email['email_id']
    case_id = prefix + original_id
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', case_id):
        raise StopBatch(f'Invalid or overly long case ID in {path.name}')
    fields = {'email_id': case_id, 'subject': email.get('subject', ''),
              'body': email.get('body', ''), 'sender': email.get('from', ''),
              'cloud_permitted': 'true'}
    if any(not isinstance(value, str) for value in fields.values()):
        raise StopBatch(f'Expected text email fields in {path.name}')
    if len(fields['subject']) > 500 or len(fields['body']) > 40000:
        raise StopBatch(f'{original_id}: email exceeds app limits; input was not truncated.')
    references = email.get('attachments', [])
    if not isinstance(references, list) or len(references) > 6:
        raise StopBatch(f'{original_id}: expected at most six attachment references.')
    files, missing = [], []
    for reference in references:
        if not isinstance(reference, str):
            raise StopBatch(f'{original_id}: attachment reference must be a path string.')
        candidate = (root / reference).resolve()
        if not candidate.is_relative_to(attachments):
            raise StopBatch(f'{original_id}: attachment escapes the authorized attachments folder.')
        if PRIVATE_NAME.search(reference) or PRIVATE_NAME.search(candidate.name):
            raise StopBatch(f'{original_id}: refusing a possible private answer/label file.')
        if not candidate.exists():
            missing.append(reference)
            continue
        if not candidate.is_file() or candidate.suffix.lower() not in {'.txt', '.pdf', '.docx', '.xlsx'}:
            raise StopBatch(f'{original_id}: unsupported attachment; no file was silently dropped.')
        name = re.sub(r'["\r\n\\]', '_', candidate.name)
        files.append((name, bounded_read(candidate, 10 * 1024 * 1024)))
    if missing:
        print(f'{case_id}: {len(missing)} referenced attachment(s) absent; using available inputs.', flush=True)
    return original_id, fields, files, missing


def verify_inputs(case, fields, files):
    expected = sorted((name, hashlib.sha256(data).hexdigest()) for name, data in files)
    actual = sorted((doc['name'], doc['sha256']) for doc in case.get('documents', []) if doc['active'])
    same = (case.get('subject') == fields['subject'] and case.get('body') == fields['body']
            and case.get('sender') == fields['sender'][:300] and actual == expected)
    if not same:
        raise StopBatch(f"{case['id']}: saved inputs differ from this bundle. Restore the original "
                        'inputs or use a new --prefix; no case was overwritten.')
    if not case.get('cloud_permitted'):
        raise StopBatch(f"{case['id']}: this saved case has no cloud permission. "
                        'Use a new --prefix for cloud-permitted synthetic inputs.')


def verify_completed(case):
    if not case.get('result') or ':gemini:' not in case.get('provider_version', ''):
        raise StopBatch(f"{case['id']}: completion is not recorded as Gemini processing. "
                        'Use a new --prefix to create a fresh Gemini test.')
    for doc in case.get('documents', []):
        if doc.get('active') and doc.get('fields') and ':gemini:' not in doc.get('extraction_version', ''):
            raise StopBatch(f"{case['id']}: document extraction is not recorded as Gemini.")


def wait_for_case(client, case, timeout):
    deadline, last_stage = time.monotonic() + timeout, None
    while case['state'] in ACTIVE:
        stage = case.get('stage', case['state'])
        if stage != last_stage:
            print(f"  {case['id']}: {stage}", flush=True)
            last_stage = stage
        if time.monotonic() >= deadline:
            raise StopBatch(f"{case['id']}: timed out waiting. Check ENABLE_WORKER=true and "
                            'the app dashboard. This case may still finish; rerun to resume.')
        time.sleep(2)
        case = client.request('/api/cases/' + case['id'])
    return case


def report_entry(original_id, case, missing):
    result, classification = case.get('result') or {}, case.get('classification') or {}
    human = classification.get('method') == 'human' or any(
        field.get('method') == 'human' for doc in case.get('documents', [])
        for field in doc.get('fields', {}).values())
    return dict(email_id=original_id, app_case_id=case['id'], state=case['state'],
                provider_version=case.get('provider_version'), category=classification.get('category'),
                classification_uncertain=classification.get('uncertain'), status=result.get('status'),
                defect_fields=result.get('defect_fields', []), requires_review=result.get('requires_review'),
                review_reason=result.get('review_reason'), human_assisted=human,
                missing_attachment_count=len(missing), error=case.get('error'))


def save_report(path, rows, total_found, selected, stopped=None):
    complete = [row for row in rows if row['state'] == 'complete']
    report = dict(kind='QuayProof Gemini predictions; NOT ground truth or an official submission',
                  updated_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  total_inbox_records=total_found, selected_records=selected,
                  inspected_records=len(rows), completed_records=len(complete),
                  review_records=sum(bool(row['requires_review']) for row in complete),
                  human_assisted_records=sum(row['human_assisted'] for row in complete),
                  categories=dict(Counter(row['category'] for row in complete)),
                  bl_statuses=dict(Counter(row['status'] for row in complete
                                          if row['category'] == 'BL_COMPARISON')),
                  stopped_reason=stopped, predictions=rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run(args, client=None):
    root = Path(args.source).expanduser().resolve()
    inbox, attachments = (root / 'inbox').resolve(), (root / 'attachments').resolve()
    if (not inbox.is_dir() or not attachments.is_dir()
            or not inbox.is_relative_to(root) or not attachments.is_relative_to(root)):
        raise StopBatch('Select the extracted PARTICIPANT folder containing inbox/ and attachments/.')
    report_path = Path(args.report).expanduser().resolve()
    if report_path.is_relative_to(root):
        raise StopBatch('Keep --report outside the participant folder so source files stay untouched.')
    paths = sorted(inbox.glob('email_*.json'))
    total = len(paths)
    if not total:
        raise StopBatch('No inbox/email_*.json records found in the selected participant folder.')
    if args.limit:
        paths = paths[:args.limit]
    client = client or Client(args.api, os.getenv('QP_ACCESS_TOKEN', ''))
    config = check_config(client)
    existing = {case['id'] for case in client.request('/api/cases')}
    print(f"Provider: gemini | App daily AI-call cap: {config['daily_call_limit']}", flush=True)
    print(f'Selected {len(paths)} of {total} emails. Test prefix: {args.prefix}', flush=True)
    print(f'{args.pause:g}s pause between processed cases; Google RPM/TPM/RPD limits still apply.', flush=True)
    rows, seen, newly_completed, last_processed = [], set(), 0, None
    try:
        for index, path in enumerate(paths, 1):
            original_id, fields, files, missing = load_record(path, inbox, attachments, root, args.prefix)
            case_id = fields['email_id']
            if case_id in seen:
                raise StopBatch(f'Duplicate email_id: {original_id}')
            seen.add(case_id)
            case = client.request('/api/cases/' + case_id) if case_id in existing else None
            if case:
                verify_inputs(case, fields, files)
            if case and case['state'] == 'complete':
                verify_completed(case)
                rows.append(report_entry(original_id, case, missing))
                print(f'[{index}/{len(paths)}] {case_id}: already complete; skipped', flush=True)
                save_report(report_path, rows, total, len(paths))
                continue
            if case and case['state'] == 'failed' and not args.retry_failed:
                rows.append(report_entry(original_id, case, missing))
                raise StopBatch(f"{case_id}: {case.get('error')}. Fix the cause or wait for quota "
                                'renewal, then rerun with --retry-failed.')
            if case and case['state'] not in ACTIVE | {'draft', 'failed'}:
                raise StopBatch(f"{case_id}: unexpected state {case['state']!r}.")
            if not case or case['state'] not in ACTIVE:
                if last_processed is not None:
                    remaining = args.pause - (time.monotonic() - last_processed)
                    if remaining > 0:
                        print(f'  Pacing: waiting {remaining:.0f}s before the next case.', flush=True)
                        time.sleep(remaining)
                check_config(client)
                busy = [c['id'] for c in client.request('/api/cases') if c['state'] in ACTIVE]
                if busy:
                    raise StopBatch('Another case is already queued/processing: ' + busy[0]
                                    + '. Wait for it to finish before resuming this batch.')
                if case is None:
                    case = client.create(fields, files)
                    existing.add(case_id)
                client.request('/api/cases/' + case_id + '/run',
                               json.dumps({'version': case['version']}).encode())
                case = client.request('/api/cases/' + case_id)
            case = wait_for_case(client, case, args.timeout)
            rows.append(report_entry(original_id, case, missing))
            if case['state'] != 'complete':
                raise StopBatch(f"{case_id}: {case.get('error') or case['state']}. Remaining emails "
                                'were not queued. Fix the cause or wait for quota renewal, then '
                                'rerun with --retry-failed.')
            verify_completed(case)
            last_processed = time.monotonic()
            newly_completed += 1
            result = case['result']
            label = result.get('status') or 'routed'
            review = ' | human review required' if result.get('requires_review') else ''
            print(f"[{index}/{len(paths)}] {case_id}: {result['category']} | {label}{review}", flush=True)
            save_report(report_path, rows, total, len(paths))
    except (StopBatch, KeyboardInterrupt, OSError, ValueError) as exc:
        reason = str(exc) or 'Interrupted; the active backend case may still finish.'
        save_report(report_path, rows, total, len(paths), stopped=reason)
        raise
    save_report(report_path, rows, total, len(paths))
    print(f'Done: {len(rows)} completed; {newly_completed} processed this invocation. '
          f'Report: {report_path}', flush=True)
    print('These are AI predictions and processing counts, not accuracy scores. '
          'Inspect source evidence and review cases in the dashboard.', flush=True)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', required=True, help='Extracted participant folder')
    parser.add_argument('--api', default='http://localhost:8000')
    parser.add_argument('--limit', type=int, default=5, help='First N records; 0 = all')
    parser.add_argument('--prefix', default='ai-', help='Separate test IDs; reuse this prefix to resume')
    parser.add_argument('--pause', type=float, default=60, help='Seconds between cases (default: 60)')
    parser.add_argument('--timeout', type=float, default=900, help='Max seconds waiting for each case')
    parser.add_argument('--report', default='ai-test-report.json', help='Local prediction/progress report')
    parser.add_argument('--retry-failed', action='store_true', help='Explicitly retry failed cases once their cause is resolved')
    parser.add_argument('--cloud-permitted', action='store_true',
                        help='Attest these inputs are authorized for unpaid Gemini; no sensitive/confidential data')
    args = parser.parse_args(argv)
    if not args.cloud_permitted:
        parser.error('--cloud-permitted is required for authorized, non-sensitive synthetic inputs.')
    if args.limit < 0 or not (0 <= args.pause < float('inf')) or not (0 < args.timeout < float('inf')):
        parser.error('Use --limit >= 0, a finite --pause >= 0, and a finite --timeout > 0.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,30}', args.prefix):
        parser.error('--prefix must be 1-30 letters, digits, underscores or hyphens.')
    parsed = urllib.parse.urlsplit(args.api)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error('--api must be an HTTP(S) app URL, without credentials, query or fragment.')
    try:
        run(args)
    except KeyboardInterrupt:
        print('\nStopped. The active backend case may still finish. Repeat the command to resume.', file=sys.stderr)
        return 130
    except (StopBatch, OSError, ValueError) as exc:
        print(f'\nBatch stopped: {exc}\nProgress is saved in QuayProof. Report: {args.report}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
