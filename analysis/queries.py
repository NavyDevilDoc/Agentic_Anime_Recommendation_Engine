"""
MODULE: analysis/queries.py
FUNCTION: Database interface for the Recommendation Engine. 
          Handles Read-Only SQL execution, Semantic Fusion packaging, and Human Fault Tolerance.
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
    """Forces SQLite into Read-Only mode to prevent LLM SQL Injection."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Vault missing at {DB_PATH}")
    uri_path = f"file:{DB_PATH}?mode=ro"
    return sqlite3.connect(uri_path, uri=True)

# --- TIER 1: HUMAN FAULT TOLERANCE ---

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
            return list(dict.fromkeys([r[0] for r in rows])) # Deduplicate and return

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
        
        # Increase n=5 to return up to 5 fuzzy matches
        matches = difflib.get_close_matches(user_input, flat_titles, n=5, cutoff=0.5)
        
        if matches:
            resolved_titles = []
            for match in matches:
                cursor.execute("SELECT english_title FROM anime_info WHERE english_title = ? OR romaji_title = ?", (match, match))
                result = cursor.fetchone()
                if result and result[0] not in resolved_titles:
                    resolved_titles.append(result[0])
            return resolved_titles

    return [] # Target completely MIA

# --- TIER 2: LLM SQL EXECUTION ---

def execute_lens_query(sql_string):
    """
    Executes the LLM-generated SQL from the Targeting Lenses.
    Returns a list of candidate english_titles.
    """
    try:
        with _get_readonly_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_string)
            # Fetch the first column (which our prompt forces to be english_title)
            return [row[0] for row in cursor.fetchall() if row[0]]
    except sqlite3.OperationalError as e:
        logger.error(f"SQL Execution Blocked (Potential Injection or Syntax Error): {e}")
        return []
    except Exception as e:
        logger.error(f"Database Error: {e}")
        return []

# --- TIER 3: SEMANTIC FUSION PACKAGING ---
def fetch_fusion_profiles(candidate_titles):
    """
    Takes the winning titles from the Lens Query and builds the rich, 
    multi-variable intelligence packets needed for the final AI Reranker 
    and Streamlit UI.
    """
    if not candidate_titles:
        return []

    fusion_profiles = []
    
    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        
        # Safe parameterized querying for a list of items
        placeholders = ','.join(['?'] * len(candidate_titles))
        
        # FIX: Removed controversy_score from the SELECT statement. We now have 8 columns.
        query = f"""
                SELECT id, english_title, studio, mal_score, 
                avg_sentiment, consensus_json, release_year, 
                mal_synopsis 
                FROM anime_info 
                WHERE english_title IN ({placeholders})
        """
        
        cursor.execute(query, candidate_titles)
        rows = cursor.fetchall()

        # FIX: Safely unpack exactly 8 variables
        for mal_id, title, studio, score, sentiment, raw_json, release_year, synopsis in rows:
            try:
                consensus_data = json.loads(raw_json) if raw_json else {}
                
                # Assemble the Semantic Fusion Packet
                profile = {
                    "id": mal_id,
                    "title": title,
                    "studio": studio,
                    "quality_score": score,
                    "audience_sentiment": sentiment,
                    "release_year": release_year,
                    "synopsis": synopsis,
                    "audience_consensus": consensus_data.get("consensus_summary", ""),
                    "pros": consensus_data.get("pros", []),
                    "cons": consensus_data.get("cons", []),
                    "controversy_score": consensus_data.get("controversy_score", 0) # <-- Extracted from JSON here!
                }
                fusion_profiles.append(profile)
            except json.JSONDecodeError:
                continue

    return fusion_profiles