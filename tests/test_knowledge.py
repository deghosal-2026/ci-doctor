
import pytest
import yaml

from app.knowledge.base import KnowledgeBase


@pytest.fixture
def kb(tmp_path):
    path = tmp_path / "kb.yaml"
    path.write_text(yaml.dump({"entries": [
        {"category": "flake", "signatures": ["AssertionError"], "confidence": 0.90, "remediation": "re-run test"},
        {"category": "lint", "signatures": ["F401"], "confidence": 0.85, "remediation": "remove import"},
    ]}))
    return KnowledgeBase(str(path))


class TestKnowledgeBase:
    def test_query_match(self, kb):
        result = kb.query("AssertionError in test_foo")
        assert result is not None
        assert result.category == "flake"

    def test_query_no_match(self, kb):
        assert kb.query("normal log line") is None

    def test_update(self, kb):
        kb.update({"category": "build", "signatures": ["ModuleNotFoundError"], "confidence": 0.95, "remediation": "install package"})
        result = kb.query("ModuleNotFoundError: no module")
        assert result is not None
        assert result.category == "build"

    def test_confidence_boost_on_kb_match(self, kb):
        result = kb.query("AssertionError")
        assert result.confidence >= 0.90
