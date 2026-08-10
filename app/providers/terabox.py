import asyncio, base64, hashlib, json, time, urllib.parse
from pathlib import Path
import httpx
from ..config import settings

class TeraBoxError(RuntimeError): pass

class TeraBox:
    AUTH='https://www.terabox.com'
    def __init__(self, db):
        self.db=db
        self.client=httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout, connect=30), follow_redirects=True)
        self.access=settings.terabox_access_token or db.setting('tb_access','')
        self.refresh=settings.terabox_refresh_token or db.setting('tb_refresh','')
        self.api_domain=db.setting('tb_api_domain','')
        self.upload_domain=db.setting('tb_upload_domain','')
        self.expires_at=float(db.setting('tb_expires_at','0') or 0)
        self.folder='/From: Other Applications/' + settings.terabox_app_folder.strip('/').replace('/','_') + '-'
    async def close(self): await self.client.aclose()
    def _sign(self,ts): return hashlib.md5(f"{settings.terabox_client_id}_{ts}_{settings.terabox_client_secret}_{settings.terabox_private_secret}".encode()).hexdigest()
    async def _post(self,path,data):
        r=await self.client.post(self.AUTH+path,data=data); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or f'TeraBox error {j.get("errno")}')
        return j
    async def refresh_token(self):
        if not self.refresh or not settings.terabox_client_id: raise TeraBoxError('TeraBox authorization is not configured')
        ts=int(time.time()); j=await self._post('/oauth/refreshtoken',{'client_id':settings.terabox_client_id,'client_secret':settings.terabox_client_secret,'refresh_token':self.refresh,'timestamp':ts,'sign':self._sign(ts)})
        d=j['data']; self.access=d['access_token']; self.refresh=d['refresh_token']; self.expires_at=time.time()+int(d.get('expires_in',172800));
        self.db.set_setting('tb_access',self.access); self.db.set_setting('tb_refresh',self.refresh); self.db.set_setting('tb_expires_at',str(self.expires_at)); await self.token_info(force=True); return d
    async def token_info(self,force=False):
        if not self.access: raise TeraBoxError('Connect TeraBox first')
        if not force and self.api_domain and self.upload_domain and time.time() < float(self.db.setting('tb_domain_expires','0') or 0): return
        j=await self._post('/oauth/tokeninfo',{'access_token':self.access}); d=j.get('data',{})
        self.api_domain=d.get('api_domain','').rstrip('/'); self.upload_domain=d.get('upload_domain','').rstrip('/')
        self.expires_at=time.time()+int(d.get('expires_in',172800)); self.db.set_setting('tb_api_domain',self.api_domain); self.db.set_setting('tb_upload_domain',self.upload_domain); self.db.set_setting('tb_domain_expires',str(time.time()+3600)); self.db.set_setting('tb_expires_at',str(self.expires_at))
    async def ensure(self):
        if self.access and time.time() > self.expires_at-120:
            try: await self.refresh_token()
            except Exception:
                if not self.api_domain: raise
        await self.token_info()
    def q(self,path,**params):
        params['access_tokens']=self.access; return self.api_domain+path+'?'+urllib.parse.urlencode(params)
    def safe_path(self,p): return self.folder+'/'+p.lstrip('/')
    async def quota(self):
        await self.ensure(); j=await self.client.get(self.q('/openapi/api/quota')); j.raise_for_status(); data=j.json();
        if data.get('errno',0)!=0: raise TeraBoxError(data.get('show_msg') or str(data))
        return data
    async def uinfo(self):
        await self.ensure(); r=await self.client.get(self.q('/openapi/uinfo')); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j
    async def precreate(self,path,block_list):
        await self.ensure(); r=await self.client.post(self.q('/openapi/api/precreate'),data={'autoinit':'1','path':path,'block_list':json.dumps(block_list,separators=(',',':'))}); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j
    async def upload_shard(self,path,uploadid,partseq,data):
        await self.ensure(); url=self.upload_domain+'/rest/2.0/pcs/superfile2?'+urllib.parse.urlencode({'method':'upload','app_id':'250528','path':path,'uploadid':uploadid,'partseq':partseq,'access_tokens':self.access});
        r=await self.client.post(url,files={'file':('chunk.bin',data,'application/octet-stream')}); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j
    async def create(self,path,size,uploadid,block_list,rtype=0):
        await self.ensure(); r=await self.client.post(self.q('/openapi/api/create'),data={'path':path,'size':str(size),'uploadid':uploadid,'block_list':json.dumps(block_list,separators=(',',':')),'rtype':str(rtype)}); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j
    async def put_bytes(self,remote_path,data):
        md5=hashlib.md5(data).hexdigest(); pre=await self.precreate(remote_path,[md5])
        if pre.get('return_type')==2: return pre.get('info',{})
        uploadid=pre.get('uploadid'); needed=pre.get('block_list') or [0]
        for i in needed: await self.upload_shard(remote_path,uploadid,i,data)
        return await self.create(remote_path,len(data),uploadid,[md5],0)
    async def filemeta(self,path,dlink=1):
        await self.ensure(); target=json.dumps([path],separators=(',',':')); r=await self.client.get(self.q('/openapi/api/filemetas',target=target,dlink=dlink)); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return (j.get('dlink') or j.get('info') or [None])[0]
    async def get_bytes(self,path):
        m=await self.filemeta(path,1); url=m.get('dlink') if isinstance(m,dict) else None
        if not url: raise TeraBoxError('No download link returned')
        r=await self.client.get(url); r.raise_for_status(); return r.content
    async def delete(self,paths):
        await self.ensure(); r=await self.client.post(self.q('/openapi/api/filemanager',opera='delete',**{'async':'0'}),data={'filelist':json.dumps(paths,separators=(',',':'))}); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j
    async def list(self,dir_path=None,page=1,num=100):
        await self.ensure(); d=dir_path or self.folder; r=await self.client.get(self.q('/openapi/api/list',page=page,num=num,dir=d,order='time',desc=1)); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j.get('list',[])
    async def device_code(self):
        if not settings.terabox_client_id: raise TeraBoxError('TERABOX_CLIENT_ID is required')
        r=await self.client.get(self.AUTH+'/oauth/devicecode',params={'client_id':settings.terabox_client_id}); r.raise_for_status(); j=r.json();
        if j.get('errno',0)!=0: raise TeraBoxError(j.get('show_msg') or str(j)); return j
    async def device_poll(self,code):
        ts=int(time.time()); return await self._post('/oauth/gettoken',{'client_id':settings.terabox_client_id,'client_secret':settings.terabox_client_secret,'grant_type':'device_code','code':code,'timestamp':ts,'sign':self._sign(ts)})
    async def connect_tokens(self,access,refresh):
        self.access=access; self.refresh=refresh; self.db.set_setting('tb_access',access); self.db.set_setting('tb_refresh',refresh); await self.token_info(force=True)
        self.db.set_setting('tb_expires_at',str(self.expires_at))
