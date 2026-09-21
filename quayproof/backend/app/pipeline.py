import copy
import re
import time
from .models import FIELDS
from .normalize import current_message, normalize
from .parsers import DocumentError, parse_document
from .providers import ProviderError

# A comparison email can carry too few documents for two opposite reasons.
# "The attachments appear to have been dropped" is a genuine escalation: work
# was expected and is missing. "Please assist to send the draft BL" is an
# ordinary request with nothing to check yet, and escalating it sends an
# operator to review a case that was never broken. The only signal separating
# them is the sender's own wording, so both are matched explicitly and the
# unmatched remainder is treated as nothing-to-compare rather than a defect.
LOST_ATTACHMENT = re.compile(r'''
      (?:not|n't|never|forgot\s+to|failed\s+to|omitted\s+to)\s+(?:been\s+)?attach
    | attachment[s]?\b[^.\n]{0,40}\b(?:missing|dropped|lost|blank|empty|corrupt|not\s+received)
    | (?:missing|dropped|lost|no|without)\s+attachment
    | (?:can(?:no|')?t|unable\s+to|could\s+not)\s+(?:open|find|see|read)\s+the\s+attach
    | re-?send\s+the\s+attach
''', re.I | re.X)

REQUESTS_DOCUMENT = re.compile(r'''
      (?:please|pls|kindly|could\s+you|can\s+you|appreciate\s+if\s+you)
      [^.\n]{0,60}
      \b(?:assist|send|share|provide|forward|furnish|issue|prepare|revert|let\s+me\s+have)\b
    | \brevert\s+with\b
    | \bawait(?:ing)?\s+(?:your|the)\b
    | \bpending\s+(?:your|the)\b
''', re.I | re.X)


def attachment_intent(case, document_count):
    """Why does this comparison email have too few documents?

    Returns an escalation reason, or None with an operator-facing note when
    there is simply nothing to compare yet. One document present always means
    its counterpart is genuinely absent.
    """
    if document_count:
        return 'missing_attachment', None
    text = current_message(case.get('body', ''))
    if LOST_ATTACHMENT.search(text):
        return 'missing_attachment', None
    if REQUESTS_DOCUMENT.search(text):
        return None, 'The sender is requesting a document rather than supplying one. Nothing to compare until it arrives.'
    return None, 'This comparison request carries no documents. Nothing to compare until they arrive.'


def observation(candidate, doc, *, human=False):
    blocks = {b['id']: b for b in doc['blocks']}
    ids = candidate['block_ids']
    raw, quote = candidate['raw_value'], candidate['quote']
    reason = None
    selected = [blocks[i] for i in ids if i in blocks]
    source = '\n'.join(b['text'] for b in selected)
    if not ids or len(selected) != len(ids) or len(set(ids)) != len(ids) or not quote or quote not in source or not raw or raw not in quote:
        reason = 'Source evidence does not support this value'
    if candidate.get('uncertain') and not human:
        reason = reason or 'AI reported ambiguity'
    # OCR confidence is a heuristic, not a probability; critical digits always need confirmation.
    ocr = any(b['method'] == 'tesseract' for b in selected)
    quality = min((b['quality'] for b in selected), default=0)
    if not human and (quality < .85 or (ocr and candidate['field'] in {'gross_weight_kg', 'container_count'})):
        reason = reason or 'OCR evidence requires human confirmation'
    value = None
    try:
        value = normalize(candidate['field'], raw, source)
    except ValueError as exc:
        reason = reason or str(exc)
    return dict(field=candidate['field'], raw_value=raw, normalized_value=value, unit='kg' if candidate['field'] == 'gross_weight_kg' else None,
                document_id=doc['id'], document_hash=doc['sha256'], document_version=doc['revision'], block_ids=ids, quote=quote,
                locations=[b['location'] for b in selected], confidence='human-confirmed' if human and not reason else 'review' if reason else 'supported',
                quality_signals={'source_verified':not reason if value is None else bool(raw and quote in source and raw in quote), 'minimum_ocr_confidence':quality if ocr else None, 'ocr':ocr},
                usable=reason is None, escalation_reason=reason, method='human' if human else doc.get('extraction_version', 'unknown'))


def validate_extraction(doc, extraction):
    blocks = {b['id']:b for b in doc['blocks']}
    type_block = blocks.get(extraction['type_block_id'])
    if not type_block or not extraction['type_quote'] or extraction['type_quote'] not in type_block['text']:
        extraction['doc_type'] = 'UNKNOWN'
    doc['doc_type'] = extraction['doc_type']
    doc['type_evidence'] = {'block_id':extraction['type_block_id'], 'quote':extraction['type_quote']}
    observations = {}
    for candidate in extraction['fields']:
        item = observation(candidate, doc)
        field = item['field']
        if field in observations:
            prior = observations[field]
            if prior['normalized_value'] != item['normalized_value'] or not item['usable']:
                prior['usable'] = False
                prior['confidence'] = 'review'
                prior['escalation_reason'] = 'Conflicting or ambiguous candidates in this document'
            prior.setdefault('alternatives', []).append(item)
        else:
            observations[field] = item
    doc['fields'] = observations


def compare(case):
    classification = case.get('classification')
    if not classification:
        return None
    base = dict(category=classification['category'], status=None, review_reason=None, has_defect=False, defect_fields=[], unknown_fields=[], comparisons=[], requires_review=classification['uncertain'], comparison_complete=False)
    if classification['uncertain']:
        base['review_note'] = 'Confirm email classification before document comparison'
        return base
    if classification['category'] != 'BL_COMPARISON':
        base['comparison_complete'] = True
        return base
    docs = [d for d in case['documents'] if d['active']]
    reason = None
    if len(docs) < 2:
        reason, note = attachment_intent(case, len(docs))
        if not reason:
            base.update(
                status='OK',
                comparison_complete=True,
                review_note=note,
            )
            return base

    elif any(d.get('parse_error') for d in docs):
        reason = next(
            d['parse_reason']
            for d in docs
            if d.get('parse_error')
        )
    si, bl = [d for d in docs if d.get('doc_type') == 'SI'], [d for d in docs if d.get('doc_type') == 'BL']
    if not reason and (len(si) != 1 or len(bl) != 1 or len(docs) != 2):
        reason = 'wrong_doc_type'
    if reason:
        base.update(status='NEEDS_REVIEW', review_reason=reason, requires_review=True)
        return base
    for field in FIELDS:
        left, right = si[0].get('fields', {}).get(field), bl[0].get('fields', {}).get(field)
        if not left or not right or not left['usable'] or not right['usable']:
            outcome = 'UNKNOWN'; base['unknown_fields'].append(field)
        elif left['normalized_value'] == right['normalized_value']:
            outcome = 'MATCH'
        else:
            outcome = 'DIFFERENT'; base['defect_fields'].append(field)
        base['comparisons'].append(dict(field=field, si=left, bl=right, outcome=outcome))
    base['has_defect'] = bool(base['defect_fields'])
    base['requires_review'] = bool(base['unknown_fields'])
    base['comparison_complete'] = not base['unknown_fields']
    # Confirmed defects remain visible even when other fields are unknown.
    base['status'] = 'MISMATCH' if base['has_defect'] else 'NEEDS_REVIEW' if base['requires_review'] else 'OK'
    if base['requires_review']:
        base['review_reason'] = 'missing_value'
    return base


def process(case, store, provider, settings):

    def checkpoint(stage):
        case.update(stage=stage, lease_until=time.time() + 1800)
        store.save(case, case['version'])

    if case.get('provider_version') != provider.version:
        case['classification'] = None
        for d in case['documents']:
            if d.get('fields'):
                d['fields'] = {}
            d.pop('extraction_version', None)
        case['provider_version'] = provider.version
    if not case.get('classification'):
        case['classification'] = provider.classify(case)
        checkpoint('classified')
    if case['classification']['category'] == 'BL_COMPARISON' and not case['classification']['uncertain']:
        for document_id in [d['id'] for d in case['documents'] if d['active']]:
            doc = next(d for d in case['documents'] if d['id'] == document_id)
            if not doc.get('blocks') and not doc.get('parse_error'):
                try:
                    doc['blocks'] = parse_document(doc['name'], store.read_file(doc['id']), settings)
                except DocumentError as exc:
                    doc.update(parse_error=str(exc), parse_reason=exc.reason)
                checkpoint('parsed ' + doc['name'])
                # A REST checkpoint replaces nested objects with a decoded JSON snapshot.
                doc = next(d for d in case['documents'] if d['id'] == document_id)
            if doc.get('blocks') and doc.get('extraction_version') != provider.version:
                extraction = provider.extract(doc['blocks'], case['cloud_permitted'])
                doc['extraction_version'] = provider.version
                validate_extraction(doc, extraction)
                checkpoint('extracted ' + doc['name'])
    case['result'] = compare(case)
    case.update(state='complete', stage='complete', error=None, lease_until=0, approved=False)
    case.setdefault('history', []).append({'at':time.time(), 'action':'comparison', 'provider_version':provider.version, 'result':copy.deepcopy(case['result'])})
    store.save(case, case['version'])


def worker_loop(stop, store, provider, settings):
    import logging
    from .storage import Conflict
    while not stop.is_set():
        case = None
        try:
            case = store.claim()
            if case:
                if case['attempts'] > 3:
                    raise ProviderError('Retry budget exhausted after interrupted processing; review and retry explicitly')
                process(case, store, provider, settings)
        except Conflict:
            logging.warning('Worker checkpoint superseded; discarding stale result')
        except Exception as exc:
            logging.warning('Processing failed: %s', type(exc).__name__)
            if case:
                retry = isinstance(exc, ProviderError) and exc.retryable and case['attempts'] < 3
                case.update(state='queued' if retry else 'failed', stage='retry_wait' if retry else 'failed', next_attempt=time.time() + 30 * case['attempts'], lease_until=0,
                            error=str(exc) if isinstance(exc, (ProviderError, DocumentError)) else 'Processing infrastructure failed; check server configuration and retry', result=None)
                try:
                    store.save(case, case['version'])
                except Exception:
                    logging.warning('Could not persist failure; lease will permit recovery')
        stop.wait(1 if case else 2)
