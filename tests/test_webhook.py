import hmac
from hashlib import sha256

from app.webhook.dedup import DedupSet
from app.webhook.verifier import verify_signature


class TestSignature:
    def test_valid_signature(self):
        payload = b'{"test": true}'
        secret = "my-secret"
        sig = "sha256=" + hmac.new(secret.encode(), payload, sha256).hexdigest()
        assert verify_signature(payload, sig, secret)

    def test_invalid_signature(self):
        assert not verify_signature(b"payload", "sha256:wrong", "secret")

    def test_empty_signature(self):
        assert not verify_signature(b"payload", "", "secret")


class TestDedup:
    def test_new_event(self):
        d = DedupSet()
        assert not d.seen("evt-1")

    def test_repeat_event(self):
        d = DedupSet()
        d.add("evt-1")
        assert d.seen("evt-1")

    def test_multiple_events(self):
        d = DedupSet()
        d.add("evt-1")
        d.add("evt-2")
        assert d.seen("evt-1")
        assert d.seen("evt-2")
        assert not d.seen("evt-3")

    def test_clear(self):
        d = DedupSet()
        d.add("evt-1")
        d.clear()
        assert not d.seen("evt-1")
