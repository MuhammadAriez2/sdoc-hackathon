import copy
import pytest
from app.config import Settings
from app.demo import BASE, demo_cases
from app.models import FIELDS
from app.normalize import normalize
from app.parsers import parse_document, DocumentError
from app.pipeline import compare, observation, validate_extraction
from app.providers import demo_classify, demo_extract, Provider, ProviderError
from app.storage import Store, Conflict


def document(text, ident='one'):
    doc = dict(id=ident,name='arbitrary.txt',sha256='synthetic',revision=1,active=True,blocks=parse_document('doc.txt',text.encode(),Settings()),extraction_version='demo-test')
    validate_extraction(doc,demo_extract(doc['blocks']))
    return doc


def comparison(si=BASE,bl=BASE):
    return compare(dict(classification=demo_classify('','Please compare the draft BL to the SI.'),documents=[document('SHIPPING INSTRUCTION\n'+si),document('BILL OF LADING\n'+bl,'two')]))


@pytest.mark.parametrize('raw,expected',[('12,500 kg','12500'),('12.5 MT','12500'),('100 lb','45.359237')])
def test_decimal_units(raw,expected):
    assert normalize('gross_weight_kg',raw)==expected


@pytest.mark.parametrize('raw',['12,50 kg','12O00 kg','12.500,00 kg','0 kg','-3 kg','12000'])
def test_weight_uncertainty_is_not_guessed(raw):
    with pytest.raises(ValueError):normalize('gross_weight_kg',raw)


def test_container_size_is_not_count():
    assert normalize('container_count',"6 x 40'HC")=='6'
    with pytest.raises(ValueError):normalize('container_count','240 cartons')


def test_match_with_aliases_and_unit_conversion():
    r=comparison(bl=BASE.replace('Port of Loading','Load Port').replace('12,500 kg','12.5 MT'))
    assert r['status']=='OK' and len(r['comparisons'])==7


def test_real_defect():
    r=comparison(bl=BASE.replace('12,500 kg','12,800 kg'))
    assert r['status']=='MISMATCH' and r['defect_fields']==['gross_weight_kg']


def test_missing_both_sides_never_matches():
    missing=BASE.replace('12,500 kg','')
    r=comparison(missing,missing)
    assert r['status']=='NEEDS_REVIEW' and 'gross_weight_kg' in r['unknown_fields']


def test_mixed_defect_unknown_retains_both():
    r=comparison(bl=BASE.replace('12,500 kg','TBC').replace('Singapore','Rotterdam'))
    assert r['status']=='MISMATCH' and r['requires_review'] and not r['comparison_complete']
    assert r['defect_fields']==['port_of_discharge']


def test_filename_cannot_make_invoice_a_bl():
    doc=document('COMMERCIAL INVOICE\n'+BASE)
    doc['name']='BL.txt'
    assert doc['doc_type']=='OTHER'


def test_fabricated_evidence_is_rejected():
    doc=document('SHIPPING INSTRUCTION\n'+BASE)
    c=dict(field='shipper',raw_value='Invented Ltd',quote='Shipper: Invented Ltd',block_ids=['b2'],uncertain=False)
    assert not observation(c,doc)['usable']
    c.update(raw_value='Harbor Paper Ltd',quote=doc['blocks'][1]['text'],block_ids=['nonexistent'])
    assert not observation(c,doc)['usable']


def test_conflicting_candidates_force_review():
    doc=document('SHIPPING INSTRUCTION\n'+BASE+'Gross Weight: 13,000 kg\n')
    assert not doc['fields']['gross_weight_kg']['usable']


def test_numeric_ocr_needs_human_confirmation():
    doc=document('SHIPPING INSTRUCTION\n'+BASE)
    doc['blocks'][-1].update(method='tesseract',quality=.99)
    c=demo_extract(doc['blocks'])['fields'][-1]
    assert not observation(c,doc)['usable']
    assert observation(c,doc,human=True)['usable']


def test_current_email_overrides_quoted_old_request():
    assert demo_classify('BL verification','Prepare a new shipping instruction.\nOn Monday someone wrote:\n> Compare the BL.')['category']=='SI_REQUEST'


def test_broken_pdf_is_visible():
    with pytest.raises(DocumentError,match='could not be parsed'):parse_document('broken.pdf',b'not a PDF',Settings())


def test_sqlite_cas_and_durable_reclaim(tmp_path):
    s=Settings(data_dir=str(tmp_path),worker=False)
    store=Store(s)
    case=store.save({'id':'x','state':'queued','attempts':0})
    stale=copy.deepcopy(case)
    claimed=store.claim()
    assert claimed['state']=='processing' and store.claim() is None
    with pytest.raises(Conflict):store.save(stale,stale['version'])
    claimed['lease_until']=0
    store.save(claimed,claimed['version'])
    assert Store(s).claim()['attempts']==2


def test_daily_cap_persists(tmp_path):
    store=Store(Settings(data_dir=str(tmp_path)))
    assert store.reserve_call(1)
    assert not Store(Settings(data_dir=str(tmp_path))).reserve_call(1)


def test_gemini_refuses_non_permitted_case_before_network(tmp_path,monkeypatch):
    settings=Settings(data_dir=str(tmp_path),provider='gemini',gemini_key='test',gemini_model='test-model')
    provider=Provider(settings,Store(settings))
    def forbidden(*a,**k):raise AssertionError('Network must not be used')
    monkeypatch.setattr('app.providers.httpx.post',forbidden)
    with pytest.raises(ProviderError,match='Cloud AI blocked'):
        provider.classify(dict(subject='x',body='x',documents=[],cloud_permitted=False))


def test_gemini_structured_contract(tmp_path,monkeypatch):
    import httpx
    import json
    settings=Settings(data_dir=str(tmp_path),provider='gemini',gemini_key='not-a-real-key',gemini_model='test-model')
    provider=Provider(settings,Store(settings))
    def fake(url,**kwargs):
        assert kwargs['headers']['x-goog-api-key']=='not-a-real-key'
        assert 'responseJsonSchema' in kwargs['json']['generationConfig']
        output={'category':'GENERAL','reason':'Operational update','evidence':'Arrival changed','uncertain':False}
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(output)}]}}]})
    monkeypatch.setattr('app.providers.httpx.post',fake)
    assert provider.classify(dict(subject='Update',body='Arrival changed',documents=[],cloud_permitted=True))['category']=='GENERAL'
