import base64, hashlib, os, json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class Crypto:
    def __init__(self,key_text):
        if not key_text: raise RuntimeError("FSE_MASTER_KEY is required")
        try:
            raw=base64.urlsafe_b64decode(key_text + '='*((4-len(key_text)%4)%4))
        except Exception: raw=b''
        if len(raw)!=32: raw=hashlib.sha256(key_text.encode()).digest()
        self.key=raw
    def encrypt(self, data:bytes, aad:bytes=b''):
        nonce=os.urandom(12); ct=AESGCM(self.key).encrypt(nonce,data,aad); return nonce,ct
    def decrypt(self, nonce, data, aad=b''): return AESGCM(self.key).decrypt(nonce,data,aad)
    def encrypt_json(self,obj):
        nonce,ct=self.encrypt(json.dumps(obj,separators=(',',':')).encode(),b'fse-catalog-v1'); return base64.urlsafe_b64encode(nonce+ct).decode()
    def decrypt_json(self,s):
        raw=base64.urlsafe_b64decode(s); return json.loads(self.decrypt(raw[:12],raw[12:],b'fse-catalog-v1'))
