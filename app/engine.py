import hashlib, io, time, uuid
from pathlib import Path
from .config import settings
from .crypto import Crypto
from .db import db
from .providers.terabox import TeraBox, TeraBoxError

crypto=Crypto(); providers={}

def provider(aid):
    if not aid: raise TeraBoxError('No TeraBox account selected')
    if aid not in providers: providers[aid]=TeraBox(db,aid)
    return providers[aid]

def account_capacity():
    return db.accounts(True)

def choose_account():
    accounts=account_capacity()
    if not accounts: raise TeraBoxError('No connected TeraBox account. Add an account first.')
    # Prefer the account with the most known free space; fall back to first.
    def free(a): return max(0, float(a.get('quota_free',0)))
    return max(accounts,key=free)['id']

async def upload_file(upload,filename,mime,account_id=None):
    aid=account_id or choose_account(); tb=provider(aid); fid=str(uuid.uuid4()); safe=Path(filename or 'file').name or 'file'; now=time.time(); total=0; fh=hashlib.sha256(); ordinal=0
    db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?)',(fid,safe,mime or 'application/octet-stream',0,now,now,'','UPLOADING',0,1),True)
    try:
        while True:
            part=await upload.read(settings.chunk_size)
            if not part: break
            total += len(part)
            if total > settings.max_upload_bytes: raise ValueError('Upload exceeds 40 GiB limit')
            fh.update(part); aad=f'{fid}:{ordinal}'.encode(); nonce,cipher=crypto.encrypt(part,aad); remote=f'{tb.safe_path(fid)}/{ordinal:08d}.bin'; cid=str(uuid.uuid4()); sha=hashlib.sha256(cipher).hexdigest(); md5=hashlib.md5(cipher).hexdigest()
            db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)',(cid,fid,ordinal,len(part),len(cipher),sha,nonce,remote,md5,'UPLOADING',aid),True)
            await tb.put_bytes(remote,cipher); db.execute('UPDATE chunks SET status=? WHERE id=?',('STORED',cid),True); ordinal+=1
        if ordinal==0:
            nonce,cipher=crypto.encrypt(b'',f'{fid}:0'.encode()); remote=f'{tb.safe_path(fid)}/00000000.bin'; cid=str(uuid.uuid4()); sha=hashlib.sha256(cipher).hexdigest(); md5=hashlib.md5(cipher).hexdigest(); db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)',(cid,fid,0,0,len(cipher),sha,nonce,remote,md5,'UPLOADING',aid),True); await tb.put_bytes(remote,cipher); db.execute('UPDATE chunks SET status=? WHERE id=?',('STORED',cid),True); ordinal=1
        db.execute('UPDATE files SET size=?,updated=?,sha256=?,status=?,chunk_count=? WHERE id=?',(total,time.time(),fh.hexdigest(),'READY',ordinal,fid),True); await backup_catalog(); return db.file(fid)
    except Exception:
        db.execute('UPDATE files SET size=?,updated=?,sha256=?,status=?,chunk_count=? WHERE id=?',(total,time.time(),fh.hexdigest(),'FAILED',ordinal,fid),True); raise

async def download_file(fid):
    f=db.file(fid)
    if not f: raise FileNotFoundError
    out=io.BytesIO(); h=hashlib.sha256()
    for c in db.chunks(fid):
        tb=provider(c['account_id']); cipher=await tb.get_bytes(c['remote_path'])
        if hashlib.sha256(cipher).hexdigest()!=c['sha256']: raise TeraBoxError(f'Integrity failure for chunk {c["ordinal"]}')
        plain=crypto.decrypt(c['nonce'],cipher,f'{fid}:{c["ordinal"]}'.encode());
        if len(plain)!=c['plain_size']: raise TeraBoxError('Plaintext size mismatch')
        h.update(plain); out.write(plain)
    if h.hexdigest()!=f['sha256']: raise TeraBoxError('File integrity verification failed')
    out.seek(0); return f,out

async def delete_file(fid):
    if not db.file(fid):return
    groups={}
    for c in db.chunks(fid):groups.setdefault(c['account_id'],[]).append(c['remote_path'])
    for aid,paths in groups.items(): await provider(aid).delete(paths)
    db.execute('DELETE FROM chunks WHERE file_id=?',(fid,),True); db.execute('DELETE FROM files WHERE id=?',(fid,),True); await backup_catalog()

async def backup_catalog():
    accounts=db.accounts(True)
    if not accounts:return
    # Catalog is encrypted before being stored. Store one copy per enabled account for recoverability.
    enc=crypto.encrypt_json(db.backup_payload()).encode()
    for a in accounts:
        try: await provider(a['id']).put_bytes(provider(a['id']).safe_path('_system/catalog.json.enc'),enc)
        except Exception: pass

async def restore_catalog():
    if db.execute('SELECT COUNT(*) FROM files').fetchone()[0]>0:return False
    for a in db.accounts(True):
        try:
            raw=await provider(a['id']).get_bytes(provider(a['id']).safe_path('_system/catalog.json.enc')); db.restore_payload(crypto.decrypt_json(raw.decode())); return True
        except Exception: continue
    return False
