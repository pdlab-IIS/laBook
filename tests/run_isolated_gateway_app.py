"""Run the real application behind HMAC on loopback with a fresh isolated DB.

Invoked only in a newly staged labook-integration-test-* directory on the RPi.
No production data/config/credentials are copied. The two-worker server always
stops on exit; ngrok is not started or changed.
"""
import base64
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time


def main():
    root = Path.cwd().resolve()
    if not root.name.startswith('labook-integration-test-') or (root / 'library.db').exists():
        raise RuntimeError('Use a new isolated trial directory with no database')
    from db import initialize_database
    from gateway.signing import sign_request
    initialize_database()
    c = json.loads((root / 'gateway.local.json').read_text())
    key_id, encoded = next(iter(c['signing_keys'].items()))
    secret = base64.b64decode(encoded)
    host = c['upstream_hosts'][0]
    subject = 'slack:' + c['slack_team_id'] + ':UTRIAL'
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    env = {k: os.environ[k] for k in ['PATH','LANG','LC_ALL'] if k in os.environ}
    env.update(LABOOK_GATEWAY_CONFIG=str(root / 'gateway.local.json'),
        LABOOK_OUTBOUND_ALLOWLIST='disabled.invalid', LABOOK_LOCAL_URL='',
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    for name in ['RAKUTEN_APP_ID','RAKUTEN_ACCESS_KEY','GOOGLE_API_KEY','NOTION_TOKEN','NOTION_DATABASE_ID','SLACK_WEBHOOK_URL']:
        env[name] = ''
    log = (root / 'trial-process.log').open('wb')
    process = subprocess.Popen([sys.executable,'-m','gunicorn','--workers','2','--bind',f'127.0.0.1:{port}',
        '--timeout','20','gateway.wsgi:application'], env=env, stdout=log, stderr=log, start_new_session=True)
    checks = []
    def expect(value, name):
        if not value:
            raise RuntimeError('Integration check failed: ' + name)
        checks.append(name)
    def headers(method,path,body=b'',content_type='',**changes):
        fields=dict(key_id=key_id, method=method, target=path, content_type=content_type,
            timestamp=str(int(time.time())),nonce=secrets.token_hex(16),subject=subject)
        fields.update(changes)
        signature=sign_request(secret,body=body,**fields)
        return {'Host':host,'Content-Type':content_type,'X-LaBook-Key-Id':key_id,
            'X-LaBook-Timestamp':fields['timestamp'],'X-LaBook-Nonce':fields['nonce'],
            'X-LaBook-Subject':fields['subject'],'X-LaBook-Signature':signature}
    def request(method,path,body=None,custom_headers=None):
        content_type='application/json' if isinstance(body,dict) else ''
        payload=json.dumps(body,ensure_ascii=False).encode() if isinstance(body,dict) else (body or b'')
        h=headers(method,path,payload,content_type) if custom_headers is None else custom_headers
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
        try:
            connection.request(method,path,body=payload,headers=h)
            response=connection.getresponse(); data=response.read()
            return response.status,dict(response.getheaders()),data
        finally:
            connection.close()
    def data(result):return json.loads(result[2])
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Trial server failed to start; inspect private trial log')
            try:
                if request('GET','/healthz')[0]==200:break
            except OSError:pass
            time.sleep(.1)
        else:raise RuntimeError('Trial server startup timed out')
        expect(request('GET','/readyz')[0]==200,'fresh database ready')
        expect(request('GET','/books',custom_headers={'Host':host})[0]==403,'unsigned request rejected')
        good=headers('GET','/books')
        expect(request('GET','/books',custom_headers={**good,'Host':'other.invalid'})[0]==403,'unexpected Host rejected')
        expect(request('GET','/books',custom_headers=good)[0]==200,'valid signature accepted')
        expect(request('GET','/books',custom_headers=good)[0]==403,'nonce replay rejected')
        expired=headers('GET','/books',timestamp=str(int(time.time())-120))
        expect(request('GET','/books',custom_headers=expired)[0]==403,'expired signature rejected')
        wrong_team=headers('GET','/books',subject='slack:TOTHER:UOTHER')
        expect(request('GET','/books',custom_headers=wrong_team)[0]==403,'wrong team rejected')
        payload=b'{"name":"test"}'
        expect(request('POST','/users',payload+b' ',headers('POST','/users',payload,'application/json'))[0]==403,'body tamper rejected')
        expect(data(request('GET','/books'))=={'books':[], 'total_count':0},'empty business database')
        user=request('POST','/users',{'name':'Integration Test User','can_own_books':1})
        expect(user[0]==201,'create isolated user');user_id=data(user)['user_id']
        shelf=request('POST','/shelves',{'shelf_code':'TRIAL-A','location_description':'Trial only'})
        expect(shelf[0]==201,'create isolated shelf');shelf_id=data(shelf)['shelf_id']
        book={'isbn':9000000000001,'title':'Integration trial book','owner_id':user_id,'shelf_id':shelf_id,'author':'Test'}
        expect(request('POST','/books',book)[0]==201,'create isolated book')
        expect(data(request('GET','/books?keyword=Integration'))['total_count']==1,'search query preserved')
        expect(request('PUT','/books/9000000000001',{**book,'title':'Updated trial book'})[0]==200,'update book')
        loan=request('POST','/loans',{'isbn':book['isbn'],'borrower_id':user_id})
        expect(loan[0]==201,'lend book');loan_id=data(loan)['loan_id']
        expect(request('POST','/loans',{'isbn':book['isbn'],'borrower_id':user_id})[0]==409,'duplicate active loan rejected')
        expect(request('POST',f'/loans/{loan_id}',{'returner_id':user_id})[0]==200,'return book')
        expect(request('POST',f'/loans/{loan_id}',{'returner_id':user_id})[0]==409,'duplicate return rejected')
        # Fixture bytes only: the current application accepts JPEG by filename.
        jpeg=b'\xff\xd8\xff\xe0TRIAL-JPEG-BYTES\xff\xd9'
        boundary='trial-multipart-boundary'
        multipart=('--'+boundary+'\r\nContent-Disposition: form-data; name="cover"; filename="cover.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode()+jpeg+('\r\n--'+boundary+'--\r\n').encode()
        path='/books/9000000000001/cover';type_='multipart/form-data; boundary='+boundary
        cover=request('POST',path,multipart,headers('POST',path,multipart,type_))
        expect(cover[0]==200,'multipart cover upload');cover_path='/'+data(cover)['cover_image_path']
        response=request('GET',cover_path)
        expect(response[0]==200 and response[2]==jpeg,'cover bytes preserved')
        expect('no-store' in response[1].get('Cache-Control',''),'cover caching private')
        for path in ['/','/books/manage?isbn=9000000000001','/users/manage','/scan/TRIAL-A']:
            response=request('GET',path);html=response[2].decode()
            expect(response[0]==200 and c['public_prefix']+'/static/runtime.js' in html,'page prefix '+path)
            expect('"gateway": true' in html,'gateway UI '+path)
        response=request('GET','/L/TRIAL-A')
        expect(response[0] in [302,303] and c['public_prefix']+'/?location=TRIAL-A' in response[1].get('Location',''),'shelf redirect prefix')
        expect(request('GET','/static/runtime.js')[0]==200,'static asset path')
        # Many workers race to consume exactly one nonce.
        shared=headers('GET','/healthz')
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            statuses=list(pool.map(lambda _:request('GET','/healthz',custom_headers=shared)[0],range(6)))
        expect(statuses.count(200)==1 and statuses.count(403)==5,'two-worker concurrent nonce protection')
        expect(not (root/'keys.py').exists() and not (root/'.env').exists(),'no production credentials copied')
        # The application-wide requests wrapper blocks real external hosts.
        verification=subprocess.run([sys.executable,'-c',"from outbound_policy import install_requests_allowlist; import requests; install_requests_allowlist();\ntry: requests.get('https://example.com', timeout=1)\nexcept requests.RequestException as e: print(type(e).__name__)"],env=env,capture_output=True,text=True,timeout=5)
        expect(verification.stdout.strip()=='OutboundRequestBlocked','outbound providers blocked')
        return {'status':'passed','checks':len(checks),'check_names':checks,'scope':'RPi loopback real application only; Sakura/ngrok pending'}
    finally:
        os.killpg(process.pid,signal.SIGTERM) if process.poll() is None else None
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        log.close()


if __name__=='__main__':
    result=main();result['trial_process_stopped']=True
    print(json.dumps(result))
