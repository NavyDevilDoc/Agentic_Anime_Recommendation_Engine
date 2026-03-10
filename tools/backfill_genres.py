"""
TOOL: backfill_genres.py
Fetches MAL genre/theme/demographic tags from Jikan API for all anime in the
database and stores them in a new `genres` column (comma-separated string).

Usage:
    python tools/backfill_genres.py          # Full run (all shows missing genres)
    python tools/backfill_genres.py --test   # Test mode (first 5 shows only)

Resumable: skips rows that already have a non-NULL genres value.
"""

import os
import sys
import sqlite3
import time
import logging
import argparse

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.jikan_client import JikanClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")


def ensure_genres_column(conn):
    """Add the genres column if it doesn't exist yet."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(anime_info)")
    columns = {row[1] for row in cursor.fetchall()}
    if "genres" not in columns:
        cursor.execute("ALTER TABLE anime_info ADD COLUMN genres TEXT")
        conn.commit()
        logger.info("Added 'genres' column to anime_info.")
    else:
        logger.info("'genres' column already exists.")


def backfill(test_mode=False):
    conn = sqlite3.connect(DB_PATH)
    ensure_genres_column(conn)

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, english_title FROM anime_info WHERE genres IS NULL ORDER BY id"
    )
    rows = cursor.fetchall()
    total = len(rows)

    if test_mode:
        rows = rows[:5]
        logger.info(f"TEST MODE: processing first 5 of {total} shows.")
    else:
        logger.info(f"Found {total} shows missing genres.")

    client = JikanClient()
    client.rate_limit_delay = 0.5  # Genre metadata is lightweight; 0.5s is safe
    success = 0
    failed = 0

    for i, (mal_id, title) in enumerate(rows, 1):
        tags = client.get_anime_genres(mal_id)

        if tags is not None:
            genres_str = ", ".join(tags) if tags else ""
            cursor.execute(
                "UPDATE anime_info SET genres = ? WHERE id = ?",
                (genres_str, mal_id),
            )
            conn.commit()
            success += 1
            logger.info(
                f"[{i}/{len(rows)}] {title}: {genres_str or '(no tags)'}"
            )
        else:
            failed += 1
            logger.warning(f"[{i}/{len(rows)}] {title}: FAILED (ID {mal_id})")

        # Progress checkpoint every 100 shows
        if i % 100 == 0:
            logger.info(
                f"--- Progress: {i}/{len(rows)} | "
                f"Success: {success} | Failed: {failed} ---"
            )

    conn.close()
    logger.info(
        f"Backfill complete. Success: {success}, Failed: {failed}, "
        f"Total: {len(rows)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test mode: first 5 shows only")
    args = parser.parse_args()
    backfill(test_mode=args.test)
