import hmac
from hashlib import sha256


def verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
