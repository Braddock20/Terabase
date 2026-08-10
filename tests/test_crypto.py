import base64,os
os.environ['FSE_MASTER_KEY']=base64.urlsafe_b64encode(os.urandom(32)).decode()
from app.crypto import Crypto

def test_roundtrip():
 c=Crypto(os.environ['FSE_MASTER_KEY']); n,x=c.encrypt(b'hello',b'a'); assert c.decrypt(n,x,b'a')==b'hello'
