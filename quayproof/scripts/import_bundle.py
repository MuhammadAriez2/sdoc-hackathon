#!/usr/bin/env python3
"""Read participant inbox records and referenced attachments only. Never open organizer archives."""
import argparse
import json
import os
from pathlib import Path
import uuid
import urllib.request
import urllib.error


def request(url,token,data=None,content_type='application/json'):
    headers={'Content-Type':content_type}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,data=data,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'App rejected request (HTTP {exc.code}): {exc.read(3000).decode()}') from exc


def encode(fields,files):
    boundary='quayproof-'+uuid.uuid4().hex
    parts=[]
    for key,value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    for name,data in files:
        # Header values must not permit header injection.
        safe=name.replace('"','_').replace('\r','_').replace('\n','_')
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{safe}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+data+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    return b''.join(parts),f'multipart/form-data; boundary={boundary}'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,help='Extracted PARTICIPANT bundle containing inbox/ and attachments/')
    parser.add_argument('--api',default='http://localhost:8000')
    parser.add_argument('--limit',type=int,default=5,help='0 imports all; start with a small batch')
    parser.add_argument('--run',action='store_true',help='Explicitly queue processing after import')
    parser.add_argument('--cloud-permitted',action='store_true',help='Attest ALL selected emails/attachments meet unpaid Gemini terms; do not use for unsanitized participant data')
    args=parser.parse_args()
    root=Path(args.source).resolve()
    inbox=(root/'inbox').resolve();attachments=(root/'attachments').resolve()
    if not inbox.is_dir() or not attachments.is_dir() or not inbox.is_relative_to(root) or not attachments.is_relative_to(root):
        parser.error('Use the extracted participant bundle, not the organizer Docker package')
    token=os.getenv('QP_ACCESS_TOKEN','')
    existing={c['id'] for c in request(args.api.rstrip('/')+'/api/cases',token)}
    records=sorted(inbox.glob('email_*.json'))
    if args.limit>0:records=records[:args.limit]
    for path in records:
        if not path.resolve().is_relative_to(inbox):raise ValueError('Inbox symlink escapes authorized directory')
        if path.stat().st_size>1000000:raise ValueError('Inbox record exceeds limit')
        email=json.loads(path.read_text(encoding='utf-8'))
        if email['email_id'] in existing:
            print(email['email_id'],'already imported; skipped');continue
        files=[]
        for reference in email.get('attachments',[]):
            candidate=(root/reference).resolve()
            if not candidate.is_relative_to(attachments):raise ValueError('Attachment reference escapes authorized attachments directory')
            if candidate.exists():
                if candidate.stat().st_size>10*1024*1024:raise ValueError('Attachment exceeds 10 MB')
                files.append((candidate.name,candidate.read_bytes()))
            else:
                print(email['email_id'],'referenced attachment absent; importing available inputs only')
        fields={'email_id':email['email_id'],'subject':email.get('subject',''),'body':email.get('body',''),'sender':email.get('from',''),'cloud_permitted':str(args.cloud_permitted).lower()}
        body,mime=encode(fields,files)
        case=request(args.api.rstrip('/')+'/api/cases',token,body,mime)
        if args.run:request(args.api.rstrip('/')+f"/api/cases/{case['id']}/run",token,json.dumps({'version':case['version']}).encode())
        print(case['id'],'queued' if args.run else 'imported')
    print('Done. Skipped existing IDs are never automatically rerun. Check failures/review cases before exporting.')


if __name__=='__main__':main()
