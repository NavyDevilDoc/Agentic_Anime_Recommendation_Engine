"""
TOOL: redistill_single_tags.py
Re-distills thematic_vibe and controversy_score for shows that have only
a single vibe tag (e.g., "Generic", "Confusing"). Uses the existing
mal_synopsis from the DB — no review re-fetch required.

Only overwrites thematic_vibe and controversy_score in consensus_json;
pros, cons, and consensus_summary are preserved.

Usage:
    python tools/redistill_single_tags.py          # Full run
    python tools/redistill_single_tags.py --test   # Test mode (first 5 only)
"""

import os
import sys
import json
import sqlite3
import asyncio
import logging
import argparse

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))

from analysis.sentiment_distiller import ReviewDistiller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")


def find_single_tag_shows():
    """Find all shows with only 1 thematic_vibe tag in consensus_json."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, english_title, mal_synopsis, consensus_json "
        "FROM anime_info WHERE consensus_json IS NOT NULL"
    )
    rows = cursor.fetchall()
    conn.close()

    single_tag_shows = []
    for mal_id, title, synopsis, cj_raw in rows:
        try:
            cj = json.loads(cj_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        vibe = cj.get("thematic_vibe", "")
        tags = [t.strip() for t in vibe.split(",") if t.strip()]
        if len(tags) <= 1:
            single_tag_shows.append((mal_id, title, synopsis, cj))

    return single_tag_shows


async def redistill(test_mode=False):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set. Aborting.")
        return

    shows = find_single_tag_shows()
    logger.info(f"Found {len(shows)} single-tag shows.")

    if test_mode:
        shows = shows[:5]
        logger.info("TEST MODE: processing first 5 only.")

    distiller = ReviewDistiller(api_key=api_key)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    success = 0
    failed = 0

    for i, (mal_id, title, synopsis, existing_cj) in enumerate(shows, 1):
        context = {
            "title": title,
            "synopsis": synopsis or "No synopsis available.",
            "reviews": [],  # Synopsis-only distillation
        }

        result = await distiller.distill_sentiment(context)

        if result and result.get("thematic_vibe"):
            new_tags = [t.strip() for t in result["thematic_vibe"].split(",")]
            if len(new_tags) >= 3:
                # Merge: only overwrite thematic_vibe and controversy_score
                existing_cj["thematic_vibe"] = result["thematic_vibe"]
                existing_cj["controversy_score"] = result.get(
                    "controversy_score", existing_cj.get("controversy_score", 5)
                )

                cursor.execute(
                    "UPDATE anime_info SET consensus_json = ? WHERE id = ?",
                    (json.dumps(existing_cj, ensure_ascii=False), mal_id),
                )
                conn.commit()
                success += 1
                logger.info(
                    f"[{i}/{len(shows)}] {title}: "
                    f"'{existing_cj['thematic_vibe']}' (controversy={existing_cj['controversy_score']})"
                )
            else:
                failed += 1
                logger.warning(
                    f"[{i}/{len(shows)}] {title}: Still < 3 tags: '{result['thematic_vibe']}'"
                )
        else:
            failed += 1
            logger.warning(f"[{i}/{len(shows)}] {title}: Distillation failed.")

    conn.close()
    logger.info(f"Re-distillation complete. Success: {success}, Failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test mode: first 5 only")
    args = parser.parse_args()
    asyncio.run(redistill(test_mode=args.test))
