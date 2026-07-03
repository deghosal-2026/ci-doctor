import yaml
from pathlib import Path

import pytest
from app.report.trend import aggregate, load_decisions
from app.report.cost import compute_cost_report


SAMPLE_DECISIONS = [
    {"timestamp": "2026-07-01T00:00:00", "category": "flake", "action": "auto_rerun", "outcome": "resolved", "token_cost": 0.0},
    {"timestamp": "2026-07-01T00:00:00", "category": "lint", "action": "suggest_fix", "outcome": "resolved", "token_cost": 0.02},
    {"timestamp": "2026-07-01T00:00:00", "category": "build", "action": "escalate", "outcome": "pending", "token_cost": 0.0},
]


class TestTrendReport:
    def test_aggregate(self):
        result = aggregate(SAMPLE_DECISIONS)
        assert result["total"] == 3
        assert result["auto_resolved"] == 2
        assert result["auto_resolve_rate"] == 66.7
        assert result["by_category"]["flake"] == 1
        assert result["by_category"]["lint"] == 1

    def test_empty_decisions(self):
        result = aggregate([])
        assert result["total"] == 0
        assert result["auto_resolve_rate"] == 0


class TestCostReport:
    def test_cost_calculation(self):
        result = compute_cost_report(SAMPLE_DECISIONS, hourly_rate=100)
        assert result["total_spend"] == 0.02
        assert result["time_saved_minutes"] == 15
        assert result["dollar_value"] == 25.0
        assert result["multiplier"] == 1250.0
