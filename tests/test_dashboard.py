"""Tests for the live dashboard module."""

import unittest

from agi_runtime.diagnostics.dashboard import DashboardStats, render_dashboard


class TestDashboardStats(unittest.TestCase):
    def test_initial_state(self):
        stats = DashboardStats()
        assert stats.total_requests == 0
        assert stats.cache_hits == 0
        assert stats.cache_hit_rate == 0.0

    def test_load_from_missing_journal(self):
        stats = DashboardStats(journal_path="nonexistent.jsonl")
        stats.load_from_journal()
        assert stats.total_requests == 0

    def test_cache_hit_rate_calculation(self):
        stats = DashboardStats()
        stats.cache_hits = 3
        stats.total_requests = 7
        assert stats.cache_hit_rate == 30.0


class TestRenderDashboard(unittest.TestCase):
    def test_renders_without_agent(self):
        output = render_dashboard()
        assert "HelloAGI" in output

    def test_renders_with_stats(self):
        stats = DashboardStats()
        stats.governance["allow"] = 10
        stats.governance["deny"] = 2
        output = render_dashboard(stats=stats)
        assert "Allow" in output or "allow" in output.lower()


if __name__ == "__main__":
    unittest.main()
