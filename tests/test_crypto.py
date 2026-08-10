import os
os.environ['TERABOX_CLIENT_ID']='test-client'
os.environ['TERABOX_CLIENT_SECRET']='test-secret'
os.environ['TERABOX_PRIVATE_SECRET']='test-private'
from app.crypto import Crypto

def test_roundtrip():
    c=Crypto(); n,x=c.encrypt(b'hello',b'a'); assert c.decrypt(n,x,b'a')==b'hello'
