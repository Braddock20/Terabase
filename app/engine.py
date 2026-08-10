import asyncio, hashlib, io, json, os, time, uuid
from pathlib import Path
from .config import settings
from .crypto import Crypto
from .db import db
from .providers.terabox import TeraBox, TeraBoxError

crypto=Crypto(settings.fse_master_key)
tb=TeraBox(db)

async def upload_file(upload, filename, mime):
    fid=str(uuid.uuid4()); now=time.time(); total=0; file_hash=hashlib.sha256(); chunks=[]; ordinal=0
    safe=Path(filename).name or 'file'; temp=Path('data')/f'.upload-{fid}.bin'
    with temp.open('wb') as out:
        while True:
            part=await upload.read(settings.chunk_size)
            if not part: break
            total += len(part)
            if total>settings.max_upload_bytes: raise ValueError('Upload exceeds MAX_UPLOAD_BYTES')
            file_hash.update(part); aad=f'{fid}:{ordinal}'.encode(); nonce,cipher=crypto.encrypt(part,aad); out.write(cipher)
            cid=str(uuid.uuid4()); remote=f'{tb.safe_path(fid)}/{ordinal:08d}.bin'; md5=hashlib.md5(cipher).hexdigest()
            chunks.append((cid,fid,ordinal,len(part),len(cipher),hashlib.sha256(cipher).hexdigest(),nonce,remote,md5,'PENDING')); ordinal+=1
    if total==0:
        nonce,cipher=crypto.encrypt(b'',f'{fid}:0'.encode()); temp.write_bytes(cipher); chunks.append((str(uuid.uuid4()),fid,0,0,len(cipher),hashlib.sha256(cipher).hexdigest(),nonce,f'{tb.safe_path(fid)}/00000000.bin',hashlib.md5(cipher).hexdigest(),'PENDING')); ordinal=1
    db.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?)',(fid,safe,mime or 'application/octet-stream',total,now,now,file_hash.hexdigest(),'UPLOADING',ordinal,1),True)
    db.executemany('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)',chunks,True)
    # Re-read encrypted chunks from temp sequentially. Each encrypted record is fixed cipher size = plain + 28.
    with temp.open('rb') as f:
        for c in chunks:
            cipher=f.read(c[4]);
            if hashlib.sha256(cipher).hexdigest()!=c[5]: raise ValueError('Local ciphertext integrity failure')
            await tb.put_bytes(c[7],cipher)
            db.execute('UPDATE chunks SET status=? WHERE id=?',('STORED',c[0]),True)
    db.execute('UPDATE files SET status=?,updated=? WHERE id=?',('READY',time.time(),fid),True)
    try: temp.unlink()
    except: pass
    await backup_catalog()
    return db.file(fid)

async def download_file(fid):
    f=db.file(fid)
    if not f: raise FileNotFoundError
    chunks=db.chunks(fid); out=io.BytesIO(); h=hashlib.sha256()
    for c in chunks:
        cipher=await tb.get_bytes(c['remote_path'])
        if hashlib.sha256(cipher).hexdigest()!=c['sha256']: raise TeraBoxError(f'Integrity failure for chunk {c["ordinal"]}')
        plain=crypto.decrypt(c['nonce'],cipher,f'{fid}:{c["ordinal"]}'.encode());
        if len(plain)!=c['plain_size']: raise TeraBoxError('Plaintext size mismatch')
        h.update(plain); out.write(plain)
    if h.hexdigest()!=f['sha256']: raise TeraBoxError('File integrity verification failed')
    out.seek(0); return f,out

async def delete_file(fid):
    f=db.file(fid)
    if not f:return
    paths=[c['remote_path'] for c in db.chunks(fid)]
    if paths: await tb.delete(paths)
    db.execute('DELETE FROM chunks WHERE file_id=?',(fid,),True); db.execute('DELETE FROM files WHERE id=?',(fid,),True); await backup_catalog()

async def backup_catalog():
    if not tb.access:return
    try:
        payload=db.backup_payload(); enc=crypto.encrypt_json(payload); await tb.put_bytes(tb.safe_path('_system/catalog.json.enc'),enc.encode())
    except Exception:
        pass

async def restore_catalog():
    if db.execute('SELECT COUNT(*) FROM files').fetchone()[0]>0 or not tb.access:return False
    try:
        raw=await tb.get_bytes(tb.safe_path('_system/catalog.json.enc')); p=crypto.decrypt_json(raw.decode()); db.restore_payload(p); return True
    except Exception:return False
