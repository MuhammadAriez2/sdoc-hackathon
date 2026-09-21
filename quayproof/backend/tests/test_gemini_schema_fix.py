"""Offline regression tests; these never call Google or use participant data."""
import copy
import json

import httpx
import pytest

from app.config import Settings
from app.demo import BASE
from app.models import Classification, Extraction, FIELDS
from app.parsers import parse_document
from app.pipeline import compare, validate_extraction
from app.providers import Provider, ProviderError, demo_extract, gemini_response_schema
from app.storage import Store


def setup_provider(tmp_path, daily_limit=20):
    settings = Settings(provider='gemini', gemini_model='gemini-3.5-flash-lite',
                        gemini_key='private-test-key', data_dir=str(tmp_path),
                        daily_limit=daily_limit)
    store = Store(settings)
    return settings, store, Provider(settings, store)


def reply(output):
    return httpx.Response(200, json={
        'candidates': [{'content': {'parts': [{'text': json.dumps(output)}]}}]
    })


def candidate_output():
    return {
        'doc_type': 'SI', 'type_block_id': 'b1', 'type_quote': 'SHIPPING INSTRUCTION',
        'fields': [{'field': 'gross_weight_kg', 'raw_value': '12,500 kg',
                    'block_ids': ['b2'], 'quote': 'Gross Weight: 12,500 kg',
                    'uncertain': False}]
    }


def test_wire_schema_keeps_field_identity_and_required_evidence():
    original = Extraction.model_json_schema()
    wire = gemini_response_schema(Extraction)
    assert Extraction.model_json_schema() == original
    assert '$defs' in original
    encoded = json.dumps(wire)
    for keyword in ('$defs', '$ref', 'maxLength', 'maxItems', 'additionalProperties'):
        assert keyword not in encoded
    assert set(wire['required']) == {'doc_type', 'type_block_id', 'type_quote', 'fields'}
    item = wire['properties']['fields']['items']
    assert item['properties']['field']['enum'] == FIELDS
    assert set(item['required']) == {'field', 'raw_value', 'block_ids', 'quote', 'uncertain'}
    assert item['properties']['block_ids']['items']['type'] == 'string'


def test_provider_extraction_and_evidence_still_detect_real_weight_difference(tmp_path, monkeypatch):
    settings, store, provider = setup_provider(tmp_path)
    seen = []

    def fake_post(url, **kwargs):
        assert url.endswith('/gemini-3.5-flash-lite:generateContent')
        assert kwargs['headers']['x-goog-api-key'] == settings.gemini_key
        config = kwargs['json']['generationConfig']
        assert config['responseMimeType'] == 'application/json'
        assert config['responseJsonSchema']['properties']['fields']['items']['type'] == 'object'
        assert '$ref' not in json.dumps(config['responseJsonSchema'])
        blocks = json.loads(kwargs['json']['contents'][0]['parts'][0]['text'])['blocks']
        seen.append(blocks)
        return reply(demo_extract(blocks))

    monkeypatch.setattr('app.providers.httpx.post', fake_post)
    docs = []
    for ident, title, weight in [('si', 'SHIPPING INSTRUCTION', '12,500 kg'),
                                  ('bl', 'BILL OF LADING', '12,800 kg')]:
        text = title + '\n' + BASE.replace('12,500 kg', weight)
        doc = dict(id=ident, name=ident+'.txt', revision=1, active=True,
                   sha256='synthetic', blocks=parse_document('test.txt', text.encode(), settings),
                   extraction_version=provider.version)
        validate_extraction(doc, provider.extract(doc['blocks'], True))
        docs.append(doc)
    result = compare({'classification': {'category': 'BL_COMPARISON', 'uncertain': False},
                      'documents': docs})
    assert len(seen) == 2
    assert result['status'] == 'MISMATCH'
    assert result['defect_fields'] == ['gross_weight_kg']
    assert result['requires_review'] is False
    assert provider.version.endswith(':gemini-schema-2')


@pytest.mark.parametrize('invalid', ['extra', 'too_long', 'too_many_blocks', 'too_many_fields',
                                    'wrong_field', 'missing_evidence'])
def test_simpler_wire_schema_never_weakens_local_validation(tmp_path, monkeypatch, invalid):
    _, _, provider = setup_provider(tmp_path)
    output = candidate_output()
    candidate = output['fields'][0]
    if invalid == 'extra':
        candidate['unexpected'] = 'must be rejected'
    elif invalid == 'too_long':
        candidate['raw_value'] = 'x' * 4001
    elif invalid == 'too_many_blocks':
        candidate['block_ids'] = ['b2'] * 13
    elif invalid == 'too_many_fields':
        output['fields'] = [copy.deepcopy(candidate) for _ in range(29)]
    elif invalid == 'wrong_field':
        candidate['field'] = 'net_weight_kg'
    elif invalid == 'missing_evidence':
        del candidate['quote']
    monkeypatch.setattr('app.providers.httpx.post', lambda *a, **k: reply(output))
    with pytest.raises(ProviderError, match='invalid or incomplete structured output'):
        provider.extract([{'id': 'b1', 'text': 'SHIPPING INSTRUCTION'}], True)


def test_rejection_names_stage_redacts_key_and_does_not_hide_failure(tmp_path, monkeypatch):
    settings, store, provider = setup_provider(tmp_path, daily_limit=1)
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(args)
        return httpx.Response(400, json={'error': {'status': 'INVALID_ARGUMENT',
            'message': 'Schema rejected; secret=' + settings.gemini_key + '\nCheck schema'}})

    monkeypatch.setattr('app.providers.httpx.post', fake_post)
    with pytest.raises(ProviderError) as error:
        provider.extract([{'id': 'b1', 'text': 'SHIPPING INSTRUCTION'}], True)
    message = str(error.value)
    assert 'document extraction (HTTP 400)' in message
    assert 'Schema rejected' in message and '[REDACTED]' in message
    assert settings.gemini_key not in message
    assert error.value.retryable is False
    assert len(calls) == 1
    assert store.reserve_call(1) is False


def test_classification_request_remains_unchanged(tmp_path, monkeypatch):
    _, _, provider = setup_provider(tmp_path)

    def fake_post(*args, **kwargs):
        assert kwargs['json']['generationConfig']['responseJsonSchema'] == Classification.model_json_schema()
        return reply({'category': 'GENERAL', 'reason': 'Operational update',
                      'evidence': 'Arrival changed', 'uncertain': False})

    monkeypatch.setattr('app.providers.httpx.post', fake_post)
    assert provider.classify({'subject': 'Update', 'body': 'Arrival changed',
                              'documents': [], 'cloud_permitted': True})['category'] == 'GENERAL'
