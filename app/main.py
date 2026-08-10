import asyncio, hashlib, time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from .config import settings, require_credentials
from .db import db
from .engine import tb, upload_file, download_file, delete_file, restore_catalog, backup_catalog

def admin_key(): return hashlib.sha256((settings.terabox_client_secret+"::"+settings.terabox_private_secret).encode()).hexdigest()[:20]

# Render Free has no shell access. The owner can retrieve this from the service logs.
def print_admin_key():
    if settings.terabox_client_secret and settings.terabox_private_secret:
        print("FSE ADMIN KEY: " + admin_key(), flush=True)

async def background():
    while True:
        try: await asyncio.sleep(settings.backup_interval_seconds); await backup_catalog()
        except asyncio.CancelledError: break
        except Exception: pass

@asynccontextmanager
async def lifespan(app):
    try:
        require_credentials()
    except RuntimeError:
        # Keep the service alive while Render is waiting for credentials.
        yield
        await tb.close()
        return
    try: await restore_catalog()
    except Exception: pass
    task=asyncio.create_task(background()); yield; task.cancel(); await tb.close()

app=FastAPI(title=settings.app_name,version='1.1.0',lifespan=lifespan)
print_admin_key()
app.add_middleware(SessionMiddleware,secret_key=admin_key(),max_age=86400*30,same_site='lax',https_only=False)
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])

def auth(request):
    if not request.session.get('auth'): raise HTTPException(401,'Sign in with your storage admin key')

def tb_ready():
    if not tb.access: raise HTTPException(503,'TeraBox is not connected. Open TeraBox → Authorize.')

@app.get('/health')
async def health(): return {'ok':True,'terabox_connected':bool(tb.access),'time':time.time()}
@app.get('/api/me')
async def me(request:Request): return {'authenticated':bool(request.session.get('auth'))}
@app.post('/api/login')
async def login(request:Request):
    d=await request.json();
    if d.get('password')!=admin_key(): raise HTTPException(401,'Invalid admin key')
    request.session['auth']=True; return {'ok':True}
@app.post('/api/logout')
async def logout(request:Request): request.session.clear(); return {'ok':True}

@app.get('/api/terabox/status')
async def tb_status(request:Request):
    auth(request)
    if not tb.access:return {'connected':False}
    try:
        await tb.ensure(); info=await tb.uinfo(); return {'connected':True,'quota':info.get('total'),'used':info.get('used'),'api_domain':tb.api_domain,'expires_at':tb.expires_at,'folder':tb.folder}
    except Exception as e:return {'connected':False,'error':str(e)}

@app.post('/api/terabox/device/start')
async def device_start(request:Request):
    auth(request)
    try:
        j=await tb.device_code(); d=j.get('data',j); code=d.get('device_code') or j.get('device_code'); qr=d.get('qr_code') or j.get('qr_code');
        if not code: raise ValueError('TeraBox did not return a device code')
        request.session['device_code']=code; return {'device_code':code,'qr_code':qr,'interval':d.get('interval',5),'expires_in':d.get('expires_in')}
    except Exception as e: raise HTTPException(400,str(e))
@app.post('/api/terabox/device/poll')
async def device_poll(request:Request):
    auth(request); code=request.session.get('device_code')
    if not code: raise HTTPException(400,'Start authorization first')
    try:
        j=await tb.device_poll(code); d=j.get('data',j)
        if not d.get('access_token'): return {'authorized':False}
        await tb.connect_tokens(d['access_token'],d.get('refresh_token','')); request.session.pop('device_code',None); await restore_catalog(); return {'authorized':True}
    except Exception as e:return {'authorized':False,'error':str(e)}
@app.post('/api/terabox/connect')
async def connect(request:Request):
    auth(request); d=await request.json()
    try: await tb.connect_tokens(d['access_token'],d.get('refresh_token','')); return {'ok':True}
    except Exception as e: raise HTTPException(400,str(e))

@app.get('/api/files')
async def files(request:Request,q:str='',limit:int=100,offset:int=0): auth(request); return {'items':db.all_files(q,max(1,min(limit,500)),max(0,offset))}
@app.get('/api/files/{fid}')
async def file_info(fid,request:Request):
    auth(request); f=db.file(fid)
    if not f: raise HTTPException(404,'File not found')
    f['chunks']=db.chunks(fid); return f
@app.post('/api/files')
async def create_file(request:Request,file:UploadFile=File(...)):
    auth(request)
    try:return await upload_file(file,file.filename,file.content_type)
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
async def remote_list(request:Request,page:int=1):
    auth(request); tb_ready()
    try:return {'items':await tb.list(page=page)}
    except Exception as e:raise HTTPException(502,str(e))
@app.get('/',response_class=HTMLResponse)
async def index():
    static_file = Path(__file__).resolve().parent.parent / 'static' / 'index.html'
    return static_file.read_text(encoding='utf-8')


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
