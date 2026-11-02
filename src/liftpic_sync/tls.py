"""Verified HTTPS with Windows' native certificate-chain validation.

Python's OpenSSL verifier does not build every missing intermediate chain the
way Windows does. Use the pinned native trust-store adapter on Windows; keep
hostname verification and CERT_REQUIRED. No insecure fallback is permitted.
"""
from functools import lru_cache
import ssl
import sys
import urllib.request

@lru_cache(maxsize=1)
def windows_context():
    from ._vendor.truststore import SSLContext
    context = SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError('Native TLS verification must stay enabled')
    return context

def _is_windows():
    return sys.platform == 'win32'

def open_url(request, *, timeout: float = 30):
    if _is_windows():
        return urllib.request.urlopen(request, timeout=timeout, context=windows_context())
    return urllib.request.urlopen(request, timeout=timeout)
