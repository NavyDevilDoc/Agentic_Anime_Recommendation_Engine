"""
MODULE: analysis/telemetry_logger.py
FUNCTION: Silent observer for the Recommendation Engine. Logs prompts, SQL, and outcomes for offline MLOps analysis.
"""
import sqlite3
import os

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

TELEMETRY_DB = os.path.join(ROOT_DIR, "data", "anime_telemetry.db")

def _init_telemetry_db():
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(TELEMETRY_DB), exist_ok=True)
    
    with sqlite3.connect(TELEMETRY_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS engine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_prompt TEXT,
                lens_used TEXT,
                generated_sql TEXT,
                candidate_count INTEGER,
                success BOOLEAN,
                error_message TEXT,
                recommended_titles TEXT,
                user_rating INTEGER DEFAULT NULL
            )
        """)

def log_engine_execution(prompt, lens, sql, candidate_count, success, error_msg="", recommendations=""):
    _init_telemetry_db()
    try:
        with sqlite3.connect(TELEMETRY_DB) as conn:
            conn.execute("""
                INSERT INTO engine_logs (user_prompt, lens_used, generated_sql, candidate_count, success, error_message, recommended_titles)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (prompt, lens, sql, candidate_count, success, error_msg, recommendations))
    except Exception as e:
        print(f"⚠️ Telemetry Logging Failed: {e}")