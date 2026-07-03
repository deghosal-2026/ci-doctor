import pytest
from app.classifier.rules import load_rules, match_rules
from app.classifier.models import Classification


SEED_RULES = [
    {"category": "flake", "patterns": ["FAILED.*test", "flaky"], "confidence": 0.95},
    {"category": "lint", "patterns": ["unused import", "line too long"], "confidence": 0.90},
    {"category": "build", "patterns": ["ModuleNotFoundError", "build failed"], "confidence": 0.90},
    {"category": "dependency", "patterns": ["version conflict", "no matching distribution"], "confidence": 0.90},
    {"category": "infra_timeout", "patterns": ["deadline exceeded", "timed out"], "confidence": 0.95},
]


def test_match_rules_flake():
    result = match_rules("FAILED test_foo", SEED_RULES)
    assert result is not None
    assert result.category == "flake"
    assert result.confidence == 0.95


def test_match_rules_lint():
    result = match_rules("unused import F401", SEED_RULES)
    assert result is not None
    assert result.category == "lint"


def test_match_rules_build():
    result = match_rules("ModuleNotFoundError: No module named 'foo'", SEED_RULES)
    assert result is not None
    assert result.category == "build"


def test_match_rules_dependency():
    result = match_rules("version conflict: requests 2.0 vs 3.0", SEED_RULES)
    assert result is not None
    assert result.category == "dependency"


def test_match_rules_timeout():
    result = match_rules("deadline exceeded after 30s", SEED_RULES)
    assert result is not None
    assert result.category == "infra_timeout"


def test_no_match_returns_none():
    result = match_rules("this is a normal log line", SEED_RULES)
    assert result is None


def test_first_match_wins():
    text = "FAILED test_module\nunused import F401"
    result = match_rules(text, SEED_RULES)
    assert result is not None
    assert result.category == "flake"


def test_case_insensitive():
    result = match_rules("Flaky test detected", SEED_RULES)
    assert result is not None
    assert result.category == "flake"
