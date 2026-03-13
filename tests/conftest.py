"""
Pytest configuration and shared fixtures for the Anime Intelligence Vault test suite.
"""

import os
import sys
import sqlite3
import pytest

# --- PATH ANCHORING ---
TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")


@pytest.fixture(scope="session")
def db_path():
    """Path to the SQLite database."""
    assert os.path.exists(DB_PATH), f"Database not found at {DB_PATH}"
    return DB_PATH


@pytest.fixture(scope="session")
def db_row_count(db_path):
    """Baseline row count — used to verify no data mutation occurred."""
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM anime_info").fetchone()[0]
    assert count > 0, "Database is empty"
    return count
