"""
Security tests: SQL injection, read-only enforcement, and input boundary validation.
These tests run without any API keys — they only touch the local database and code paths.
"""

import os
import sys
import sqlite3
import pytest

TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import analysis.queries as queries
import analysis.queries_deprecated as queries_deprecated


# =====================================================================
# SQL INJECTION RED TEAM
# =====================================================================

class TestSQLInjection:
    """Verify that the read-only SQLite interface blocks all mutation attempts."""

    ATTACK_PAYLOADS = [
        ("DROP TABLE", "DROP TABLE anime_info;"),
        ("DELETE", "DELETE FROM anime_info;"),
        ("UPDATE", "UPDATE anime_info SET mal_score = 1.0;"),
        ("INSERT", "INSERT INTO anime_info (english_title, mal_score) VALUES ('Pwned', 10.0);"),
        ("STACKED QUERY", "SELECT english_title FROM anime_info LIMIT 1; DROP TABLE anime_info;"),
    ]

    @pytest.mark.parametrize("name,payload", ATTACK_PAYLOADS, ids=[a[0] for a in ATTACK_PAYLOADS])
    def test_sql_injection_blocked(self, payload, name, db_path, db_row_count):
        """Each attack payload must be rejected, and the DB must remain intact."""
        # Fire the payload through the legacy raw SQL execution interface
        result = queries_deprecated.execute_lens_query(payload)
        assert result == [], f"Attack '{name}' was not blocked — returned: {result}"

        # Verify no data mutation occurred
        with sqlite3.connect(db_path) as conn:
            post_count = conn.execute("SELECT COUNT(*) FROM anime_info").fetchone()[0]
        assert post_count == db_row_count, f"Row count changed after '{name}' attack"

    def test_no_illicit_data_written(self, db_path):
        """Verify no injected rows exist in the database."""
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM anime_info WHERE english_title = 'Pwned'"
            ).fetchone()[0]
        assert row == 0, "Illicit data found in database"


# =====================================================================
# READ-ONLY ENFORCEMENT
# =====================================================================

class TestReadOnlyEnforcement:
    """Verify that the database connections enforce read-only mode."""

    def test_queries_module_readonly(self):
        """queries.py must open DB in read-only URI mode."""
        conn = queries._get_readonly_connection()
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("INSERT INTO anime_info (id) VALUES (999999)")
        finally:
            conn.close()

    def test_vector_store_readonly(self):
        """vector_store.py must open DB in read-only URI mode."""
        from analysis.vector_store import _get_readonly_connection
        conn = _get_readonly_connection()
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("INSERT INTO anime_info (id) VALUES (999999)")
        finally:
            conn.close()


# =====================================================================
# INPUT BOUNDARY TESTING
# =====================================================================

class TestInputBoundaries:
    """Verify that edge-case inputs don't crash the system."""

    def test_empty_query_returns_empty(self):
        """An empty string should not crash — should return empty or no results."""
        result = queries.resolve_show_title("")
        assert isinstance(result, list)

    def test_special_characters_handled(self):
        """SQL metacharacters in input must not cause crashes."""
        dangerous_inputs = [
            "'; DROP TABLE anime_info; --",
            "<script>alert('xss')</script>",
            "' OR '1'='1",
            "Robert'); DROP TABLE Students;--",
            "\x00\x01\x02",  # null bytes
        ]
        for inp in dangerous_inputs:
            result = queries.resolve_show_title(inp)
            assert isinstance(result, list), f"Crashed on input: {repr(inp)}"

    def test_unicode_input_handled(self):
        """Unicode characters (Japanese, emoji) must not cause crashes."""
        unicode_inputs = [
            "進撃の巨人",       # Attack on Titan in Japanese
            "🔥 anime 🔥",
            "Stein's;Gate",     # semicolon in title
        ]
        for inp in unicode_inputs:
            result = queries.resolve_show_title(inp)
            assert isinstance(result, list), f"Crashed on unicode input: {repr(inp)}"

    def test_oversized_input_handled(self):
        """A very long input string must not cause crashes or hangs."""
        long_input = "a" * 10000
        result = queries.resolve_show_title(long_input)
        assert isinstance(result, list)
