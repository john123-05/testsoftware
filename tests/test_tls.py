import json
import ssl
import sys
import urllib.request
import pytest
from liftpic_sync import tls

def test_windows_requests_use_verified_native_context(monkeypatch):
    context=ssl.create_default_context()
    calls=[]
    monkeypatch.setattr(tls,'_is_windows',lambda:True)
    monkeypatch.setattr(tls,'windows_context',lambda:context)
    monkeypatch.setattr(urllib.request,'urlopen',lambda request,**kwargs:calls.append((request,kwargs)) or 'response')
    assert tls.open_url('https://example.test',timeout=12)=='response'
    assert calls[0][1]=={'timeout':12,'context':context}
    assert context.check_hostname is True
    assert context.verify_mode==ssl.CERT_REQUIRED

def test_verification_failure_never_retries_without_verification(monkeypatch):
    calls=[]
    monkeypatch.setattr(tls,'_is_windows',lambda:True)
    monkeypatch.setattr(tls,'windows_context',ssl.create_default_context)
    def rejected(*args,**kwargs):
        calls.append(kwargs)
        raise ssl.SSLCertVerificationError('untrusted test issuer')
    monkeypatch.setattr(urllib.request,'urlopen',rejected)
    with pytest.raises(ssl.SSLCertVerificationError):tls.open_url('https://example.test')
    assert len(calls)==1 and calls[0]['context'].verify_mode==ssl.CERT_REQUIRED

@pytest.mark.skipif(sys.platform!='win32',reason='Windows CryptoAPI is required')
def test_windows_native_tls_reaches_the_real_customer_backend():
    context=tls.windows_context()
    assert type(context).__module__.endswith('truststore._api')
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    request=urllib.request.Request('https://kvpcwlcfgmsmarjtwpsx.supabase.co/functions/v1/online-photo-sales/config',
        data=b'{"path":"kalahari-virginia"}',headers={'Content-Type':'application/json'})
    with tls.open_url(request,timeout=30) as response:
        data=json.load(response)
    assert data['test_mode'] is True and data['currency']=='USD'
