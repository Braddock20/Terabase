import sqlite3, json, threading, time
from pathlib import Path
from .config import settings

class DB:
    def __init__(self):
        self.lock = threading.RLock()
        if settings.database_url.startswith("sqlite:///"):
            self.path = settings.database_url.removeprefix("sqlite:///")
        else:
            self.path = "data/fse.db"
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()
    def init(self):
        with self.lock:
            self.conn.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS files(
              id TEXT PRIMARY KEY,name TEXT NOT NULL,mime TEXT,size INTEGER NOT NULL,
              created REAL NOT NULL,updated REAL NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL,
              chunk_count INTEGER NOT NULL,manifest_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS chunks(
              id TEXT PRIMARY KEY,file_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
              plain_size INTEGER NOT NULL,cipher_size INTEGER NOT NULL,sha256 TEXT NOT NULL,
              nonce BLOB NOT NULL,remote_path TEXT NOT NULL,remote_md5 TEXT NOT NULL,
              status TEXT NOT NULL,FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,type TEXT NOT NULL,status TEXT NOT NULL,
              file_id TEXT,progress INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 0,
              message TEXT,created REAL NOT NULL,updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id,ordinal);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            '''); self.conn.commit()
    def execute(self, sql, args=(), commit=False):
        with self.lock:
            cur=self.conn.execute(sql,args)
            if commit:self.conn.commit()
            return cur
    def executemany(self, sql, seq, commit=False):
        with self.lock:
            cur=self.conn.executemany(sql,seq)
            if commit:self.conn.commit()
            return cur
    def file(self, fid):
        r=self.execute("SELECT * FROM files WHERE id=?",(fid,)).fetchone(); return dict(r) if r else None
    def chunks(self,fid): return [dict(r) for r in self.execute("SELECT * FROM chunks WHERE file_id=? ORDER BY ordinal",(fid,)).fetchall()]
    def all_files(self, q="", limit=100, offset=0):
        rows=self.execute("SELECT * FROM files WHERE name LIKE ? ORDER BY updated DESC LIMIT ? OFFSET ?",(f"%{q}%",limit,offset)).fetchall(); return [dict(r) for r in rows]
    def setting(self,k,default=None):
        r=self.execute("SELECT v FROM settings WHERE k=?",(k,)).fetchone(); return r[0] if r else default
    def set_setting(self,k,v): self.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",(k,v),True)
    def backup_payload(self):
        return {"version":1,"files":[dict(r) for r in self.execute("SELECT * FROM files").fetchall()],"chunks":[dict(r) for r in self.execute("SELECT * FROM chunks").fetchall()]}
    def restore_payload(self,p):
        with self.lock:
            self.conn.execute("DELETE FROM chunks"); self.conn.execute("DELETE FROM files")
            for f in p.get("files",[]): self.conn.execute("INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?)",(f['id'],f['name'],f['mime'],f['size'],f['created'],f['updated'],f['sha256'],f['status'],f['chunk_count'],f.get('manifest_version',1)))
            for c in p.get("chunks",[]): self.conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",(c['id'],c['file_id'],c['ordinal'],c['plain_size'],c['cipher_size'],c['sha256'],c['nonce'],c['remote_path'],c['remote_md5'],c['status']))
            self.conn.commit()

db=DB()
