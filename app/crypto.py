import base64, hashlib, json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from .config import settings

# Deterministic key: no extra FSE secret is required in Render.
# Changing TeraBox client credentials requires a planned data migration.
def master_key():
    material=(settings.terabox_client_secret + "\0" + settings.terabox_private_secret).encode()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"fse-terabox-v1", info=b"storage-engine-key").derive(material)

class Crypto:
    def __init__(self): self.key=master_key()
    def encrypt(self, plaintext, aad=b""):
        nonce=__import__('os').urandom(12); return nonce,AESGCM(self.key).encrypt(nonce,plaintext,aad)
    def decrypt(self, nonce,ciphertext,aad=b""): return AESGCM(self.key).decrypt(nonce,ciphertext,aad)
    def encrypt_json(self,obj):
        n,c=self.encrypt(json.dumps(obj,separators=(",",":"),default=self._default).encode(),b"catalog"); return base64.b64encode(n+c).decode()
    def decrypt_json(self,s):
        raw=base64.b64decode(s); return json.loads(self.decrypt(raw[:12],raw[12:],b"catalog"))
    @staticmethod
    def _default(x):
        if isinstance(x,(bytes,bytearray)): return {"__bytes__":base64.b64encode(x).decode()}
        raise TypeError(type(x).__name__)
