import asyncio, hashlib, time, uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from .config import settings
from .db import db
from .engine import provider, providers, upload_file, download_file, delete_file, restore_catalog, backup_catalog

ADMIN_KEY=hashlib.sha256((settings.terabox_client_secret+'::'+settings.terabox_private_secret).encode()).hexdigest()[:20] if settings.terabox_client_secret and settings.terabox_private_secret else (settings.terabox_private_secret or 'change-me')

async def background():
    while True:
        try:
            await asyncio.sleep(settings.backup_interval_seconds); await backup_catalog()
        except asyncio.CancelledError: break
        except Exception: pass

@asynccontextmanager
async def lifespan(app):
    try: await restore_catalog()
    except Exception: pass
    task=asyncio.create_task(background()); yield; task.cancel()
    for p in list(providers.values()):
        try: await p.close()
        except Exception: pass

app=FastAPI(title=settings.app_name,version='2.0.0',lifespan=lifespan)
app.add_middleware(SessionMiddleware,secret_key=hashlib.sha256(ADMIN_KEY.encode()).hexdigest(),max_age=86400*30,same_site='lax',https_only=False)
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])

def auth(request):
    if not request.session.get('auth'): raise HTTPException(401,'Sign in first')

def acct(aid):
    a=db.account(aid)
    if not a: raise HTTPException(404,'TeraBox account not found')
    if not a['enabled']: raise HTTPException(409,'TeraBox account is disabled')
    return a

@app.get('/health')
async def health(): return {'ok':True,'accounts':len(db.accounts(True)),'time':time.time()}
@app.get('/api/me')
async def me(request:Request): return {'authenticated':bool(request.session.get('auth'))}
@app.post('/api/login')
async def login(request:Request):
    d=await request.json()
    if d.get('password') not in {ADMIN_KEY,settings.terabox_private_secret}: raise HTTPException(401,'Invalid admin key')
    request.session['auth']=True; return {'ok':True}
@app.post('/api/logout')
async def logout(request:Request): request.session.clear(); return {'ok':True}

@app.get('/api/accounts')
async def accounts(request:Request):
    auth(request); return {'items':db.accounts(True)}
@app.post('/api/accounts')
async def add_account(request:Request):
    auth(request); d=await request.json(); name=(d.get('name') or 'TeraBox Account').strip()[:80]; access=d.get('access_token','').strip(); refresh=d.get('refresh_token','').strip()
    if not access or not refresh: raise HTTPException(400,'Access token and refresh token are required')
    aid=str(uuid.uuid4()); folder='/From: Other Applications/FSE-Storage-'+aid[:8]+'-'; db.add_account(aid,name,access,refresh,folder)
    p=provider(aid)
    try: await p.token_info(force=True)
    except Exception:
        db.remove_account(aid); raise HTTPException(400,'TeraBox authorization tokens were rejected')
    return {'ok':True,'account':db.account(aid)}
@app.delete('/api/accounts/{aid}')
async def remove_account(aid:str,request:Request):
    auth(request); acct(aid)
    if db.execute('SELECT COUNT(*) FROM chunks WHERE account_id=?',(aid,)).fetchone()[0]: raise HTTPException(409,'Account contains managed chunks. Migrate or delete dependent files first.')
    p=providers.pop(aid,None)
    if p:
        try: await p.close()
        except Exception: pass
    db.remove_account(aid); await backup_catalog(); return {'ok':True}
@app.post('/api/accounts/{aid}/disable')
async def disable_account(aid:str,request:Request):
    auth(request); acct(aid); db.update_account(aid,enabled=0); return {'ok':True}
@app.post('/api/accounts/{aid}/enable')
async def enable_account(aid:str,request:Request):
    auth(request); a=db.account(aid)
    if not a: raise HTTPException(404,'Account not found')
    db.update_account(aid,enabled=1); return {'ok':True}
@app.get('/api/accounts/{aid}/status')
async def account_status(aid:str,request:Request):
    auth(request); a=acct(aid); p=provider(aid)
    try:
        info=await p.uinfo(); quota=await p.quota(); return {'connected':True,'account':a,'uinfo':info,'quota':quota}
    except Exception as e:return {'connected':False,'account':a,'error':str(e)}

@app.post('/api/terabox/device/start')
async def device_start(request:Request):
    auth(request)
    from .providers.terabox import TeraBox
    temp=TeraBox(db,None)
    try:
        j=await temp.device_code(); d=j.get('data',j); code=d.get('device_code') or j.get('device_code'); qr=d.get('qr_code') or j.get('qr_code')
        if not code: raise ValueError('TeraBox did not return a device code')
        request.session['device_code']=code; await temp.close(); return {'device_code':code,'qr_code':qr,'interval':d.get('interval',5),'expires_in':d.get('expires_in')}
    except Exception as e:
        await temp.close(); raise HTTPException(400,str(e))
@app.post('/api/terabox/device/poll')
async def device_poll(request:Request):
    auth(request); code=request.session.get('device_code')
    if not code: raise HTTPException(400,'Start authorization first')
    from .providers.terabox import TeraBox
    temp=TeraBox(db,None)
    try:
        j=await temp.device_poll(code); d=j.get('data',j)
        if not d.get('access_token'): await temp.close(); return {'authorized':False}
        aid=str(uuid.uuid4()); folder='/From: Other Applications/FSE-Storage-'+aid[:8]+'-'; db.add_account(aid,'TeraBox Account',d['access_token'],d.get('refresh_token',''),folder); p=provider(aid); await p.token_info(force=True); request.session.pop('device_code',None); await temp.close(); return {'authorized':True,'account':db.account(aid)}
    except Exception as e:
        await temp.close(); return {'authorized':False,'error':str(e)}

@app.get('/api/files')
async def files(request:Request,q:str='',limit:int=100,offset:int=0): auth(request); return {'items':db.all_files(q,max(1,min(limit,500)),max(0,offset))}
@app.get('/api/files/{fid}')
async def file_info(fid,request:Request):
    auth(request); f=db.file(fid)
    if not f: raise HTTPException(404,'File not found')
    f['chunks']=db.chunks(fid); return f
@app.post('/api/files')
async def create_file(request:Request,file:UploadFile=File(...),account_id:str|None=None):
    auth(request)
    try:return await upload_file(file,file.filename,file.content_type,account_id)
    except ValueError as e:raise HTTPException(413,str(e))
    except Exception as e:raise HTTPException(502,str(e))
@app.get('/api/files/{fid}/download')
async def get_file(fid,request:Request):
    auth(request)
    try:
        f,out=await download_file(fid); return StreamingResponse(out,media_type=f['mime'],headers={'Content-Disposition':f'attachment; filename="{f["name"].replace(chr(34),"")}"','Content-Length':str(f['size'])})
    except FileNotFoundError:raise HTTPException(404,'File not found')
    except Exception as e:raise HTTPException(502,str(e))
@app.delete('/api/files/{fid}')
async def remove_file(fid,request:Request):
    auth(request)
    try:await delete_file(fid); return {'ok':True}
    except Exception as e:raise HTTPException(502,str(e))
@app.post('/api/files/{fid}/verify')
async def verify_file(fid,request:Request):
    auth(request)
    try:f,_=await download_file(fid); return {'ok':True,'sha256':f['sha256']}
    except Exception as e:raise HTTPException(502,str(e))

@app.get('/api/terabox/list')
async def remote_list(request:Request,account_id:str,page:int=1):
    auth(request); a=acct(account_id)
    try:return {'items':await provider(a['id']).list(page=page)}
    except Exception as e:raise HTTPException(502,str(e))
@app.get('/',response_class=HTMLResponse)
async def index(): return (Path(__file__).resolve().parent.parent/'static'/'index.html').read_text(encoding='utf-8')

if __name__=='__main__':
    import os,uvicorn; uvicorn.run('app.main:app',host='0.0.0.0',port=int(os.getenv('PORT','10000')))
