import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.pipeline import process
from app.demo import BASE


@pytest.fixture
def client(tmp_path):
    app=create_app(Settings(data_dir=str(tmp_path),worker=False,provider='demo',storage='local',token='',public=False))
    with TestClient(app) as c:yield c


def drain(client):
    app=client.app
    while (case:=app.state.store.claim()):process(case,app.state.store,app.state.provider,app.state.settings)


def seed(client):
    assert client.post('/api/demo').status_code==200
    drain(client)


def test_full_demo_and_export(client):
    seed(client)
    cases={c['id']:c for c in client.get('/api/cases').json()}
    assert len(cases)==9
    assert cases['demo-01']['result']['status']=='OK'
    assert cases['demo-02']['result']['defect_fields']==['gross_weight_kg']
    assert cases['demo-03']['result']['review_reason']=='missing_value'
    assert cases['demo-04']['result']['review_reason']=='missing_attachment'
    assert cases['demo-05']['result']['review_reason']=='wrong_doc_type'
    assert cases['demo-06']['classification']['category']=='SI_REQUEST'
    exported=client.get('/api/export?include_demo=true').json()
    assert len(exported)==9 and exported['demo-07']['status']=='OK'
    assert client.get('/api/export').status_code==409


def test_pending_cannot_export(client):
    client.post('/api/demo')
    assert client.get('/api/export?include_demo=true').status_code==409


def test_approval_does_not_erase_mismatch(client):
    seed(client)
    case=client.get('/api/cases/demo-02').json()
    r=client.post('/api/cases/demo-02/review',json=dict(version=case['version'],action='approve',actor='Tester',reason='Confirmed weight discrepancy'))
    assert r.status_code==200 and r.json()['approved']
    assert r.json()['result']['status']=='MISMATCH'
    stale=client.post('/api/cases/demo-02/run',json={'version':case['version']})
    assert stale.status_code==409


def test_unknown_cannot_approve_or_invent_correction(client):
    seed(client)
    case=client.get('/api/cases/demo-03').json()
    base=dict(version=case['version'],actor='Tester',reason='Checking source')
    assert client.post('/api/cases/demo-03/review',json=dict(**base,action='approve')).status_code==409
    doc=next(d for d in case['documents'] if d['doc_type']=='BL')
    response=client.post('/api/cases/demo-03/review',json=dict(**base,action='correct_field',document_id=doc['id'],field='gross_weight_kg',block_ids=['b8'],raw_value='12.5 MT'))
    assert response.status_code==400


def test_revision_preserves_old_file_and_recompares(client):
    seed(client)
    case=client.get('/api/cases/demo-03').json()
    doc=next(d for d in case['documents'] if d['doc_type']=='BL')
    response=client.post(f"/api/cases/demo-03/documents/{doc['id']}/revision",data=dict(version=case['version'],actor='Tester',reason='Received readable revision'),files={'file':('new-draft.txt',('BILL OF LADING\n'+BASE).encode())})
    assert response.status_code==200
    drain(client)
    updated=client.get('/api/cases/demo-03').json()
    assert updated['result']['status']=='OK'
    assert len(updated['documents'])==3 and not updated['documents'][1]['active']
    assert client.get(f"/api/cases/demo-03/documents/{doc['id']}").status_code==200


def test_add_missing_attachment(client):
    seed(client)
    case=client.get('/api/cases/demo-04').json()
    r=client.post('/api/cases/demo-04/documents',data={'version':case['version']},files={'file':('draft.txt',('BILL OF LADING\n'+BASE).encode())})
    assert r.status_code==200
    drain(client)
    assert client.get('/api/cases/demo-04').json()['result']['status']=='OK'


def test_source_file_scoped_to_case(client):
    seed(client)
    doc=client.get('/api/cases/demo-01').json()['documents'][0]
    assert client.get(f"/api/cases/demo-02/documents/{doc['id']}").status_code==404


def test_auth_and_secret_redaction(tmp_path):
    app=create_app(Settings(data_dir=str(tmp_path),worker=False,token='secret',gemini_key='private-api-key'))
    with TestClient(app) as c:
        assert c.get('/api/health').status_code==200
        assert c.get('/api/cases').status_code==401
        r=c.get('/api/config',headers={'Authorization':'Bearer secret'})
        assert r.status_code==200 and 'private-api-key' not in r.text and 'secret' not in r.text


def test_public_mode_refuses_unsafe_config(tmp_path):
    with pytest.raises(ValueError):create_app(Settings(data_dir=str(tmp_path),public=True,token=''))


def test_checkpoints_survive_json_roundtrip_like_supabase(client,monkeypatch):
    import json
    store=client.app.state.store
    original=store.save
    def roundtrip(case,expected=None):
        original(case,expected)
        snapshot=json.loads(json.dumps(case))
        case.clear();case.update(snapshot)
        return case
    monkeypatch.setattr(store,'save',roundtrip)
    seed(client)
    result=client.get('/api/cases/demo-01').json()
    assert result['result']['status']=='OK'
    assert all(len(d['fields'])==7 for d in result['documents'])
