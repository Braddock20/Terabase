import asyncio, base64, io, os, time
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from .config import settings
from .db import db
from .engine import tb, upload_file, download_file, delete_file, restore_catalog, backup_catalog
from .providers.terabox import TeraBoxError

pending_device={}

async def background():
    while True:
        try:
            await asyncio.sleep(settings.backup_interval_seconds)
            await backup_catalog()
        except asyncio.CancelledError: break
        except Exception: pass

@asynccontextmanager
async def lifespan(app):
    try: await restore_catalog()
    except Exception: pass
    task=asyncio.create_task(background())
    yield
    task.cancel(); await tb.close()

app=FastAPI(title=settings.app_name, version='1.0.0', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret or 'dev-only-change-me', max_age=86400*7, same_site='lax', https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

def auth(request:Request):
    if not settings.app_password: return
    if not request.session.get('auth'): raise HTTPException(401,'Authentication required')

def tb_ready():
    if not tb.access: raise HTTPException(503,'TeraBox is not connected')

@app.get('/health')
async def health():
    return {'ok':True,'service':settings.app_name,'terabox_connected':bool(tb.access),'time':time.time()}

@app.get('/api/me')
async def me(request:Request):
    return {'authenticated': bool(request.session.get('auth')) if settings.app_password else True}

@app.post('/api/login')
async def login(request:Request):
    data=await request.json()
    if settings.app_password and data.get('password')!=settings.app_password: raise HTTPException(401,'Invalid password')
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
        if not code: raise TeraBoxError('TeraBox did not return a device code')
        pending_device[request.session.get('_sid','default')]=code
        return {'device_code':code,'qr_code':qr,'interval':d.get('interval',5),'expires_in':d.get('expires_in')}
    except Exception as e: raise HTTPException(400,str(e))

@app.post('/api/terabox/device/poll')
async def device_poll(request:Request):
    auth(request); code=pending_device.get(request.session.get('_sid','default'))
    if not code: raise HTTPException(400,'Start authorization first')
    try:
        j=await tb.device_poll(code); d=j.get('data',j)
        if not d.get('access_token'): return {'authorized':False,'response':j}
        await tb.connect_tokens(d['access_token'],d.get('refresh_token','')); pending_device.pop(request.session.get('_sid','default'),None); return {'authorized':True}
    except Exception as e: return {'authorized':False,'error':str(e)}

@app.post('/api/terabox/connect')
async def connect(request:Request):
    auth(request); data=await request.json()
    try: await tb.connect_tokens(data['access_token'],data.get('refresh_token','')); return {'ok':True}
    except Exception as e: raise HTTPException(400,str(e))

@app.get('/api/providers')
async def providers(request:Request):
    auth(request); st=await tb_status(request); return [{'id':'terabox','name':'TeraBox','type':'primary','connected':st.get('connected',False),'quota':st.get('quota'),'used':st.get('used'),'folder':tb.folder}]

@app.get('/api/files')
async def files(request:Request,q:str='',limit:int=100,offset:int=0):
    auth(request); return {'items':db.all_files(q,max(1,min(limit,500)),max(0,offset))}

@app.get('/api/files/{fid}')
async def file_info(fid,request:Request):
    auth(request); f=db.file(fid)
    if not f: raise HTTPException(404,'File not found')
    f['chunks']=db.chunks(fid); return f

@app.post('/api/files')
async def create_file(request:Request,file:UploadFile=File(...)):
    auth(request)
    try:
        return await upload_file(file,file.filename,file.content_type)
    except TeraBoxError as e: raise HTTPException(502,str(e))
    except ValueError as e: raise HTTPException(413,str(e))
    except Exception as e: raise HTTPException(500,str(e))

@app.get('/api/files/{fid}/download')
async def get_file(fid,request:Request):
    auth(request)
    try:
        f,out=await download_file(fid); return StreamingResponse(out,media_type=f['mime'],headers={'Content-Disposition':f'attachment; filename="{f["name"].replace(chr(34),"")}"','Content-Length':str(f['size'])})
    except FileNotFoundError: raise HTTPException(404,'File not found')
    except Exception as e: raise HTTPException(502,str(e))

@app.delete('/api/files/{fid}')
async def remove_file(fid,request:Request):
    auth(request)
    try: await delete_file(fid); return {'ok':True}
    except Exception as e: raise HTTPException(502,str(e))

@app.post('/api/files/{fid}/verify')
async def verify_file(fid,request:Request):
    auth(request)
    try: f,_=await download_file(fid); return {'ok':True,'sha256':f['sha256']}
    except Exception as e: raise HTTPException(502,str(e))

@app.get('/api/terabox/list')
async def remote_list(request:Request,page:int=1):
    auth(request); tb_ready()
    try:return {'items':await tb.list(page=page)}
    except Exception as e: raise HTTPException(502,str(e))

@app.get('/',response_class=HTMLResponse)
async def index(): return open('static/index.html',encoding='utf-8').read()
