import copy
import hashlib
import json
import re
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import Settings, ROOT, MAX_FILE_BYTES, MAX_ATTACHMENTS
from .demo import demo_cases
from .models import ReviewRequest, RunRequest
from .pipeline import compare, observation, worker_loop
from .providers import Provider
from .storage import Store, Conflict


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate()
    store = Store(settings)
    provider = Provider(settings, store)
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        thread = None
        if settings.worker:
            thread = threading.Thread(target=worker_loop, args=(stop,store,provider,settings), daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=2)

    app = FastAPI(title='QuayProof', version='1.0.0', lifespan=lifespan, docs_url=None if settings.public else '/docs', redoc_url=None, openapi_url=None if settings.public else '/openapi.json')
    app.state.store, app.state.provider, app.state.settings = store, provider, settings

    def authenticated(request: Request):
        if settings.token and not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+settings.token):
            raise HTTPException(401, 'Enter the team access token')

    @app.middleware('http')
    async def safe_headers(request, call_next):
        length = request.headers.get('content-length', '0')
        if not length.isdigit() or int(length) > 65*1024*1024:
            return JSONResponse({'detail':'Request exceeds 65 MB limit'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({'detail':str(exc)}, status_code=409)

    def get_case(case_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',case_id):
            raise HTTPException(400,'Invalid case ID')
        case = store.get(case_id)
        if not case:
            raise HTTPException(404,'Case not found')
        return case

    def writable(case, version):
        if case['version'] != version:
            raise Conflict('Case changed; refresh and try again')
        if case['state'] in {'processing','queued'}:
            raise Conflict('Wait for processing before editing this case')

    def doc_record(name, data, revision=1):
        name = Path(name.replace('\\','/')).name
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413,'Attachment exceeds 10 MB')
        if Path(name).suffix.lower() not in {'.txt','.pdf','.docx','.xlsx'}:
            raise HTTPException(400,'Supported formats: TXT, PDF, DOCX, XLSX')
        document_id = uuid.uuid4().hex
        store.put_file(document_id, data)
        return dict(id=document_id,name=name,sha256=hashlib.sha256(data).hexdigest(),revision=revision,active=True,blocks=[],fields={})

    def add_case(case_id, subject, body, sender, attachments, permitted, synthetic=False):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', case_id):
            raise HTTPException(400,'Email ID must use 1–80 letters, digits, underscores or hyphens')
        if store.get(case_id):
            raise Conflict('Email ID already exists')
        if len(store.list()) >= settings.max_cases:
            raise HTTPException(409,'Prototype case limit reached; use a separate project or explicitly increase MAX_CASES')
        if len(attachments)>MAX_ATTACHMENTS or len(body)>40000 or len(subject)>500:
            raise HTTPException(413,'Email exceeds prototype limits')
        docs = [doc_record(name,data) for name,data in attachments]
        case = dict(id=case_id, subject=subject, body=body, sender=sender[:300], documents=docs, cloud_permitted=permitted, synthetic=synthetic,
                    created_at=time.time(),state='draft',stage='ready',attempts=0,next_attempt=0,classification=None,result=None,error=None,approved=False,audit=[],history=[])
        return store.save(case)

    @app.get('/api/health')
    def health():
        return {'status':'ok','service':'QuayProof'}

    @app.get('/api/config', dependencies=[Depends(authenticated)])
    def config():
        return {'provider':settings.provider,'storage':settings.storage,'public':settings.public,'daily_call_limit':settings.daily_limit,
                'provider_configured':settings.provider=='demo' or bool(settings.gemini_key and settings.gemini_model) if settings.provider!='ollama' else bool(settings.ollama_model)}

    @app.get('/api/cases', dependencies=[Depends(authenticated)])
    def cases():
        return [{k:c.get(k) for k in ['id','version','subject','sender','state','stage','classification','result','error','approved','synthetic','updated_at']} for c in store.list()]

    @app.get('/api/cases/{case_id}', dependencies=[Depends(authenticated)])
    def detail(case_id: str):
        return get_case(case_id)

    @app.post('/api/cases', dependencies=[Depends(authenticated)], status_code=201)
    async def create_case(email_id: Annotated[str,Form()], subject: Annotated[str,Form()], body: Annotated[str,Form()], sender: Annotated[str,Form()]='', cloud_permitted: Annotated[bool,Form()]=False, files: Annotated[list[UploadFile] | None,File()]=None):
        files = files or []
        if len(files)>MAX_ATTACHMENTS:
            raise HTTPException(413,'Maximum six attachments')
        attachments = [(f.filename or 'document.txt',await f.read(MAX_FILE_BYTES+1)) for f in files]
        return add_case(email_id,subject,body,sender,attachments,cloud_permitted)

    @app.post('/api/demo', dependencies=[Depends(authenticated)])
    def seed_demo():
        inserted = []
        for ident, subject, body, attachments in demo_cases():
            if not store.get(ident):
                case = add_case(ident,subject,body,'synthetic@example.invalid',[(n,t.encode()) for n,t in attachments],True,True)
                case.update(state='queued',stage='queued')
                store.save(case,case['version'])
                inserted.append(ident)
        return {'inserted':inserted,'note':'Synthetic fixtures; results are computed through the selected provider'}

    @app.post('/api/cases/{case_id}/run', dependencies=[Depends(authenticated)])
    def run(case_id: str, body: RunRequest):
        case = get_case(case_id)
        writable(case,body.version)
        case.update(state='queued',stage='queued',error=None,result=None,attempts=0,next_attempt=0,approved=False)
        store.save(case,case['version'])
        return case

    @app.post('/api/cases/{case_id}/review', dependencies=[Depends(authenticated)])
    def review(case_id: str, action: ReviewRequest):
        case = get_case(case_id)
        writable(case,action.version)
        before = copy.deepcopy(case.get('result'))
        old_value = None
        if action.action=='approve':
            if case['state']!='complete' or not case.get('result') or case['result']['requires_review']:
                raise HTTPException(409,'Resolve processing and review issues before acknowledging the report')
            case['approved'] = True
        elif action.action=='classify':
            if not action.category:
                raise HTTPException(400,'Choose a category')
            old_value = case.get('classification')
            case['classification'] = dict(category=action.category,uncertain=False,evidence='Human classification',reason=action.reason,method='human')
            case.update(approved=False,error=None,provider_version=provider.version)
            if action.category=='BL_COMPARISON':
                case.update(state='queued',stage='queued',result=None,attempts=0,next_attempt=0)
            else:
                case.update(state='complete',stage='complete',result=compare(case))
        else:
            if case['state']!='complete':
                raise HTTPException(409,'Finish processing before correcting a field')
            doc = next((d for d in case['documents'] if d['id']==action.document_id and d['active']),None)
            if not doc or not action.field:
                raise HTTPException(400,'Select an active document and field')
            old_value = copy.deepcopy(doc['fields'].get(action.field))
            blocks = {b['id']:b for b in doc['blocks']}
            quote = '\n'.join(blocks[i]['text'] for i in action.block_ids if i in blocks)
            item = observation(dict(field=action.field,raw_value=action.raw_value,quote=quote,block_ids=action.block_ids,uncertain=False),doc,human=True)
            if not item['usable']:
                raise HTTPException(400,item['escalation_reason'])
            doc['fields'][action.field] = item
            case.update(result=compare(case),approved=False)
        case['audit'].append(dict(at=time.time(),action=action.action,actor=action.actor,reason=action.reason,document_id=action.document_id,field=action.field,before=old_value,after=action.raw_value or action.category,result_before=before,result_after=copy.deepcopy(case.get('result'))))
        store.save(case,case['version'])
        return case

    @app.post('/api/cases/{case_id}/documents/{document_id}/revision', dependencies=[Depends(authenticated)])
    async def revision(case_id: str, document_id: str, version: Annotated[int,Form()], actor: Annotated[str,Form()], reason: Annotated[str,Form()], file: Annotated[UploadFile,File()], cloud_permitted: Annotated[bool,Form()]=False):
        case = get_case(case_id)
        writable(case,version)
        doc = next((d for d in case['documents'] if d['id']==document_id and d['active']),None)
        if not doc or len(reason.strip())<3 or not actor.strip():
            raise HTTPException(400,'Active document, reviewer and reason are required')
        replacement = doc_record(file.filename or doc['name'],await file.read(MAX_FILE_BYTES+1),doc['revision']+1)
        doc['active'] = False
        replacement['replaces'] = doc['id']
        case['documents'].append(replacement)
        case['audit'].append(dict(at=time.time(),action='revision',actor=actor,reason=reason,old_document=doc['id'],new_document=replacement['id']))
        case.update(state='queued',stage='queued',classification=None,result=None,approved=False,error=None,attempts=0,next_attempt=0,cloud_permitted=case['cloud_permitted'] and cloud_permitted)
        store.save(case,case['version'])
        return case

    @app.post('/api/cases/{case_id}/documents', dependencies=[Depends(authenticated)])
    async def add_attachment(case_id: str, version: Annotated[int,Form()], file: Annotated[UploadFile,File()], cloud_permitted: Annotated[bool,Form()]=False):
        case = get_case(case_id)
        writable(case,version)
        if sum(d['active'] for d in case['documents']) >= MAX_ATTACHMENTS:
            raise HTTPException(409,'Maximum six active attachments')
        doc = doc_record(file.filename or 'document.txt',await file.read(MAX_FILE_BYTES+1))
        case['documents'].append(doc)
        case['audit'].append(dict(at=time.time(),action='add_attachment',actor='Team token holder',reason='Supplied missing attachment',document_id=doc['id']))
        case.update(state='queued',stage='queued',classification=None,result=None,approved=False,error=None,attempts=0,next_attempt=0,cloud_permitted=case['cloud_permitted'] and cloud_permitted)
        store.save(case,case['version'])
        return case

    @app.get('/api/cases/{case_id}/documents/{document_id}', dependencies=[Depends(authenticated)])
    def original(case_id: str, document_id: str):
        case = get_case(case_id)
        doc = next((d for d in case['documents'] if d['id']==document_id),None)
        if not doc:
            raise HTTPException(404,'Document not found')
        name = re.sub(r'[^A-Za-z0-9._-]', '_', doc['name'])
        return Response(store.read_file(doc['id']), media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{name}"'})

    @app.get('/api/export', dependencies=[Depends(authenticated)])
    def export(include_demo: bool=False):
        selected = [c for c in store.list() if include_demo or not c['synthetic']]
        if not selected:
            raise HTTPException(409,'No imported cases to export; demo fixtures are excluded by default')
        blocked = [c['id'] for c in selected if c['state']!='complete' or not c.get('result') or c['classification']['uncertain'] or (c['result']['has_defect'] and c['result']['requires_review'])]
        if blocked:
            raise HTTPException(409,{'message':'Resolve pending, failed, ambiguous classifications and mixed defect/unknown cases before export','case_ids':blocked})
        output = {}
        for case in selected:
            result = case['result']
            output[case['id']] = dict(category=result['category'],status=result['status'] or 'OK',review_reason=result['review_reason'],defect_fields=result['defect_fields'],has_defect=result['has_defect'])
        return JSONResponse(output,headers={'Content-Disposition':'attachment; filename="submission.json"'})

    frontend = ROOT/'frontend'/'dist'
    if frontend.exists():
        app.mount('/assets',StaticFiles(directory=frontend/'assets'),name='assets')

        @app.get('/')
        def index():
            return FileResponse(frontend/'index.html')
    else:
        @app.get('/')
        def development_hint():
            return {'message':'API ready. Run the Vite frontend on http://localhost:5173 or build frontend/dist.'}
    return app


app = create_app()
