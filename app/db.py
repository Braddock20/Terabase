import sqlite3, json, threading, time
from .config import settings

class DB:
    def __init__(self):
        self.lock=threading.RLock(); self.conn=sqlite3.connect(settings.database_path,check_same_thread=False); self.conn.row_factory=sqlite3.Row; self.init()
    def init(self):
        with self.lock:
            self.conn.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT,size INTEGER NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL,chunk_count INTEGER NOT NULL,manifest_version INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,file_id TEXT NOT NULL,ordinal INTEGER NOT NULL,plain_size INTEGER NOT NULL,cipher_size INTEGER NOT NULL,sha256 TEXT NOT NULL,nonce BLOB NOT NULL,remote_path TEXT NOT NULL,remote_md5 TEXT NOT NULL,status TEXT NOT NULL,account_id TEXT,FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,name TEXT NOT NULL,provider TEXT NOT NULL DEFAULT 'terabox',access_token TEXT NOT NULL,refresh_token TEXT NOT NULL,api_domain TEXT,upload_domain TEXT,expires_at REAL NOT NULL DEFAULT 0,folder TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL,updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id,ordinal);
            CREATE INDEX IF NOT EXISTS idx_chunks_account ON chunks(account_id);
            ''')
            # Lightweight migration for databases created by the earlier build.
            cols=[r[1] for r in self.conn.execute('PRAGMA table_info(chunks)').fetchall()]
            if 'account_id' not in cols: self.conn.execute('ALTER TABLE chunks ADD COLUMN account_id TEXT')
            self.conn.commit()
    def execute(self,sql,args=(),commit=False):
        with self.lock:
            c=self.conn.execute(sql,args)
            if commit:self.conn.commit()
            return c
    def file(self,fid):
        r=self.execute('SELECT * FROM files WHERE id=?',(fid,)).fetchone(); return dict(r) if r else None
    def chunks(self,fid): return [dict(r) for r in self.execute('SELECT * FROM chunks WHERE file_id=? ORDER BY ordinal',(fid,)).fetchall()]
    def all_files(self,q='',limit=100,offset=0): return [dict(r) for r in self.execute('SELECT * FROM files WHERE name LIKE ? ORDER BY updated DESC LIMIT ? OFFSET ?',(f'%{q}%',limit,offset)).fetchall()]
    def setting(self,k,default=None):
        r=self.execute('SELECT v FROM settings WHERE k=?',(k,)).fetchone(); return r[0] if r else default
    def set_setting(self,k,v): self.execute('INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v',(k,v),True)
    def accounts(self,enabled_only=False):
        q='SELECT id,name,provider,api_domain,upload_domain,expires_at,folder,enabled,created,updated FROM accounts'
        if enabled_only:q+=' WHERE enabled=1'
        q+=' ORDER BY created ASC'; return [dict(r) for r in self.execute(q).fetchall()]
    def account(self,aid):
        r=self.execute('SELECT * FROM accounts WHERE id=?',(aid,)).fetchone(); return dict(r) if r else None
    def add_account(self,aid,name,access,refresh,folder,api='',upload='',expires=0):
        now=time.time(); self.execute('INSERT OR REPLACE INTO accounts(id,name,provider,access_token,refresh_token,api_domain,upload_domain,expires_at,folder,enabled,created,updated) VALUES (?,?,?,?,?,?,?,?,?,1,COALESCE((SELECT created FROM accounts WHERE id=?),?),?)',(aid,name,'terabox',access,refresh,api,upload,float(expires or 0),folder,aid,now,now),True)
    def update_account(self,aid,**kw):
        if not kw:return
        allowed={'name','access_token','refresh_token','api_domain','upload_domain','expires_at','folder','enabled'}
        vals={k:v for k,v in kw.items() if k in allowed}
        if not vals:return
        vals['updated']=time.time(); sql='UPDATE accounts SET '+','.join(f'{k}=?' for k in vals)+' WHERE id=?'; self.execute(sql,tuple(vals.values())+(aid,),True)
    def remove_account(self,aid): self.execute('DELETE FROM accounts WHERE id=?',(aid,),True)
    def backup_payload(self):
        return {'version':3,'files':[dict(r) for r in self.execute('SELECT * FROM files').fetchall()],'chunks':[dict(r) for r in self.execute('SELECT * FROM chunks').fetchall()],'accounts':[dict(r) for r in self.execute('SELECT * FROM accounts').fetchall()],'settings':{r[0]:r[1] for r in self.execute('SELECT k,v FROM settings').fetchall() if not r[0].startswith('tb_')}}
    def restore_payload(self,p):
        with self.lock:
            self.conn.execute('DELETE FROM chunks'); self.conn.execute('DELETE FROM files'); self.conn.execute('DELETE FROM accounts')
            for f in p.get('files',[]): self.conn.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?)',(f['id'],f['name'],f['mime'],f['size'],f['created'],f['updated'],f['sha256'],f['status'],f['chunk_count'],f.get('manifest_version',1)))
            for c in p.get('chunks',[]): self.conn.execute('INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)',(c['id'],c['file_id'],c['ordinal'],c['plain_size'],c['cipher_size'],c['sha256'],c['nonce'],c['remote_path'],c['remote_md5'],c['status'],c.get('account_id')))
            for a in p.get('accounts',[]):
                self.conn.execute('INSERT OR REPLACE INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(a['id'],a['name'],a.get('provider','terabox'),a['access_token'],a['refresh_token'],a.get('api_domain',''),a.get('upload_domain',''),a.get('expires_at',0),a['folder'],a.get('enabled',1),a.get('created',time.time()),a.get('updated',time.time())))
            for k,v in p.get('settings',{}).items(): self.conn.execute('INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)',(k,v))
            self.conn.commit()

db=DB()
