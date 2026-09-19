import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx


class Conflict(RuntimeError):
    pass


class Store:
    """The same case/checkpoint contract for SQLite and Supabase/PostgREST."""
    def __init__(self, settings):
        self.s = settings
        self.root = Path(settings.data_dir).resolve()
        if settings.storage == 'local':
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root/'documents').mkdir(exist_ok=True)
            with self.db() as db:
                db.executescript('''CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_usage (day TEXT PRIMARY KEY, calls INTEGER NOT NULL);''')

    def db(self):
        conn = sqlite3.connect(self.root/'quayproof.db', timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def remote(self, method, path, **kwargs):
        headers = {'apikey': self.s.supabase_key, 'Authorization': f'Bearer {self.s.supabase_key}'}
        headers.update(kwargs.pop('headers', {}))
        response = httpx.request(method, self.s.supabase_url+path, headers=headers, timeout=30, **kwargs)
        if response.status_code == 409 or (response.status_code >= 400 and 'QP_CONFLICT' in response.text):
            raise Conflict('Case changed; refresh before retrying')
        if response.status_code >= 400:
            raise RuntimeError(f'Supabase request failed (HTTP {response.status_code}); check schema, credentials and bucket')
        return response

    def list(self):
        if self.s.storage == 'supabase':
            # Explicit pagination: never silently export the PostgREST default first page only.
            rows, offset = [], 0
            while True:
                batch = self.remote('GET', f'/rest/v1/qp_cases?select=payload&order=id&limit=200&offset={offset}').json()
                rows.extend(r['payload'] for r in batch)
                if len(batch) < 200:
                    return rows
                offset += 200
        with self.db() as db:
            return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM cases ORDER BY id')]

    def get(self, case_id):
        if self.s.storage == 'supabase':
            rows = self.remote('GET', f'/rest/v1/qp_cases?id=eq.{case_id}&select=payload').json()
            return rows[0]['payload'] if rows else None
        with self.db() as db:
            row = db.execute('SELECT payload FROM cases WHERE id=?', (case_id,)).fetchone()
            return json.loads(row['payload']) if row else None

    def save(self, case, expected=None):
        updated = dict(case, version=0 if expected is None else expected+1, updated_at=time.time())
        if self.s.storage == 'supabase':
            saved = self.remote('POST', '/rest/v1/rpc/qp_save_case', json={'p_id':case['id'], 'p_expected':expected, 'p_payload':updated}).json()
        else:
            with self.db() as db:
                if expected is None:
                    try:
                        db.execute('INSERT INTO cases VALUES (?,?,?)', (case['id'],0,json.dumps(updated)))
                    except sqlite3.IntegrityError as exc:
                        raise Conflict('Email ID already exists') from exc
                else:
                    cursor = db.execute('UPDATE cases SET version=?,payload=? WHERE id=? AND version=?', (updated['version'],json.dumps(updated),case['id'],expected))
                    if cursor.rowcount != 1:
                        raise Conflict('Case changed; refresh before retrying')
            saved = updated
        case.clear(); case.update(saved)
        return case

    def claim(self):
        now = time.time()
        if self.s.storage == 'supabase':
            return self.remote('POST', '/rest/v1/rpc/qp_claim_case', json={'p_now':now}).json()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM cases WHERE (json_extract(payload,'$.state')='queued' AND coalesce(json_extract(payload,'$.next_attempt'),0)<=?) OR (json_extract(payload,'$.state')='processing' AND coalesce(json_extract(payload,'$.lease_until'),0)<?) ORDER BY id LIMIT 1", (now,now)).fetchone()
            if row is None:
                return None
            case = json.loads(row['payload'])
            case.update(state='processing', lease_until=now+1800, version=row['version']+1, attempts=case.get('attempts',0)+1, updated_at=now)
            db.execute('UPDATE cases SET version=?,payload=? WHERE id=?', (case['version'],json.dumps(case),case['id']))
            return case

    def reserve_call(self, limit):
        day = datetime.now(timezone.utc).date().isoformat()
        if self.s.storage == 'supabase':
            return self.remote('POST', '/rest/v1/rpc/qp_reserve_call', json={'p_day':day,'p_limit':limit}).json()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO ai_usage VALUES (?,0)', (day,))
            return db.execute('UPDATE ai_usage SET calls=calls+1 WHERE day=? AND calls<?', (day,limit)).rowcount == 1

    def put_file(self, document_id, data):
        if self.s.storage == 'supabase':
            self.remote('POST', f'/storage/v1/object/{self.s.bucket}/{document_id}', content=data, headers={'Content-Type':'application/octet-stream','x-upsert':'false'})
        else:
            (self.root/'documents'/document_id).write_bytes(data)

    def read_file(self, document_id):
        if self.s.storage == 'supabase':
            return self.remote('GET', f'/storage/v1/object/{self.s.bucket}/{document_id}').content
        return (self.root/'documents'/document_id).read_bytes()
