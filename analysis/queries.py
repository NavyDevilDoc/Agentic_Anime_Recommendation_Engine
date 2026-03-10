"""
MODULE: analysis/queries.py
FUNCTION: Database interface for the Recommendation Engine.
          Handles Read-Only connections, Semantic Fusion packaging, and Human Fault Tolerance.
          SQL execution (execute_lens_query) has been deprecated to queries_deprecated.py.
"""
import sqlite3
import os
import re
import difflib
import json
import logging

logger = logging.getLogger(__name__)

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def _get_readonly_connection():
    """Forces SQLite into Read-Only mode."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Vault missing at {DB_PATH}")
    uri_path = f"file:{DB_PATH}?mode=ro"
    return sqlite3.connect(uri_path, uri=True)

# --- HUMAN FAULT TOLERANCE ---

def resolve_show_title(user_input):
    """
    Three-Tier Fault Tolerance Engine.
    Returns a LIST of potential official 'english_title' matches.
    """
    if not user_input or len(user_input.strip()) < 2:
        return []

    user_input = user_input.strip()

    with _get_readonly_connection() as conn:
        cursor = conn.cursor()

        # TIER 1: The Exact Match (Fastest) - Case Insensitive
        cursor.execute("SELECT english_title FROM anime_info WHERE english_title COLLATE NOCASE = ? OR romaji_title COLLATE NOCASE = ?", (user_input, user_input))
        rows = cursor.fetchall()
        if rows:
            return list(dict.fromkeys([r[0] for r in rows]))

        # TIER 2: The Punctuation Agnostic / Substring Match (Franchise Collision catcher)
        clean_input = re.sub(r'[^\w\s]', '', user_input)
        wildcard_query = "%" + "%".join(clean_input.split()) + "%"

        cursor.execute("SELECT english_title FROM anime_info WHERE english_title LIKE ? OR romaji_title LIKE ? LIMIT 10", (wildcard_query, wildcard_query))
        rows = cursor.fetchall()
        if rows:
            return list(dict.fromkeys([r[0] for r in rows]))

        # TIER 3: The Typo-Resistant Fuzzy Match (difflib)
        cursor.execute("SELECT english_title, romaji_title FROM anime_info")
        all_titles = cursor.fetchall()

        flat_titles = [t for pair in all_titles for t in pair if t]

        matches = difflib.get_close_matches(user_input, flat_titles, n=5, cutoff=0.5)

        if matches:
            resolved_titles = []
            for match in matches:
                cursor.execute("SELECT english_title FROM anime_info WHERE english_title = ? OR romaji_title = ?", (match, match))
                result = cursor.fetchone()
                if result and result[0] not in resolved_titles:
                    resolved_titles.append(result[0])
            return resolved_titles

    return []


def find_franchise_titles(reference_titles):
    """
    Given a list of canonical english_titles, find all franchise variants
    in the DB via substring matching. Returns a set of english_titles that
    are variants of the reference shows (e.g., "Attack on Titan" matches
    "Attack on Titan Season 2", "Attack on Titan: The Final Season", etc.).
    Does NOT include the original reference titles themselves.
    """
    if not reference_titles:
        return set()

    variants = set()
    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        for title in reference_titles:
            # Use the longest meaningful prefix to catch franchise variants
            # without false positives (e.g., "86" is too short for LIKE)
            if len(title) < 4:
                continue
            # Search by english_title substring
            cursor.execute(
                "SELECT english_title FROM anime_info WHERE english_title LIKE ? AND english_title != ?",
                (f"%{title}%", title),
            )
            variants.update(row[0] for row in cursor.fetchall())
            # Also search by romaji_title to catch spelling variants
            # (e.g., "Haikyu!!" vs "Haikyuu!!" in different DB entries)
            cursor.execute(
                "SELECT romaji_title FROM anime_info WHERE english_title = ?",
                (title,),
            )
            romaji_row = cursor.fetchone()
            if romaji_row and romaji_row[0] and len(romaji_row[0]) >= 4 and romaji_row[0] != title:
                cursor.execute(
                    "SELECT english_title FROM anime_info WHERE english_title LIKE ? AND english_title != ?",
                    (f"%{romaji_row[0]}%", title),
                )
                variants.update(row[0] for row in cursor.fetchall())
    return variants


# --- BAYESIAN SCORE CONSTANTS ---
# C = global mean MAL score across all 5,952 rated shows
# m = prior weight (minimum votes before raw score is trusted)
_BAYESIAN_GLOBAL_MEAN = 7.05
_BAYESIAN_MIN_VOTES = 5000


def _bayesian_score(raw_score, vote_count):
    """
    Bayesian-adjusted MAL score that shrinks low-vote shows toward the
    global mean. Formula: (v/(v+m))*R + (m/(v+m))*C
    """
    if raw_score is None or vote_count is None:
        return 0.0
    v = vote_count
    m = _BAYESIAN_MIN_VOTES
    C = _BAYESIAN_GLOBAL_MEAN
    return (v / (v + m)) * raw_score + (m / (v + m)) * C


# --- SEMANTIC FUSION PACKAGING ---

def fetch_fusion_profiles(candidate_titles):
    """
    Takes candidate titles and builds the rich, multi-variable intelligence
    packets needed for the AI Reranker and Streamlit UI.
    """
    if not candidate_titles:
        return []

    fusion_profiles = []

    with _get_readonly_connection() as conn:
        cursor = conn.cursor()

        placeholders = ','.join(['?'] * len(candidate_titles))

        query = f"""
                SELECT id, english_title, studio, mal_score, scored_by,
                avg_sentiment, consensus_json, release_year,
                mal_synopsis
                FROM anime_info
                WHERE english_title IN ({placeholders})
        """

        cursor.execute(query, candidate_titles)
        rows = cursor.fetchall()

        for mal_id, title, studio, score, voted, sentiment, raw_json, release_year, synopsis in rows:
            try:
                consensus_data = json.loads(raw_json) if raw_json else {}

                profile = {
                    "id": mal_id,
                    "title": title,
                    "studio": studio,
                    "quality_score": round(_bayesian_score(score, voted), 1),
                    "raw_mal_score": score,
                    "scored_by": voted,
                    "audience_sentiment": sentiment,
                    "release_year": release_year,
                    "synopsis": synopsis,
                    "audience_consensus": consensus_data.get("consensus_summary", ""),
                    "pros": consensus_data.get("pros", []),
                    "cons": consensus_data.get("cons", []),
                    "controversy_score": consensus_data.get("controversy_score", 0)
                }
                fusion_profiles.append(profile)
            except json.JSONDecodeError:
                continue

    return fusion_profiles
