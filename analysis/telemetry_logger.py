"""
MODULE: analysis/telemetry_logger.py
FUNCTION: Silent observer for the Recommendation Engine. Logs prompts, SQL, and outcomes for offline MLOps analysis via GCP.
"""
import os
import streamlit as st
from sqlalchemy import create_engine, text

# Smart Credential Routing: Checks Streamlit Secrets first (for HF), then local env vars
def get_db_uri():
    try:
        return st.secrets["GCP_POSTGRES_URI"]
    except Exception:
        return os.environ.get("GCP_POSTGRES_URI")

def log_engine_execution(prompt, lens, sql, candidate_count, success, error_msg="", recommendations=""):
    """
    Transmits an execution payload directly to the GCP PostgreSQL Single Source of Truth.
    """
    uri = get_db_uri()
    
    if not uri:
        print("⚠️ Telemetry Warning: GCP_POSTGRES_URI not found. Log aborted.")
        return

    try:
        # Create the connection engine
        engine = create_engine(uri)
        
        # engine.begin() automatically commits the transaction if successful
        with engine.begin() as conn:
            # Using SQLAlchemy's text() for safe, parameterized SQL injection
            query = text("""
                INSERT INTO telemetry_logs (user_prompt, lens_used, generated_sql, candidate_count, success, error_message, recommended_titles)
                VALUES (:prompt, :lens, :sql, :candidate_count, :success, :error_msg, :recommendations)
            """)
            
            conn.execute(query, {
                "prompt": prompt,
                "lens": lens,
                "sql": sql,
                "candidate_count": candidate_count,
                "success": success,
                "error_msg": error_msg,
                "recommendations": recommendations
            })
            
        print("📡 Telemetry successfully beamed to GCP Cloud.")
        
    except Exception as e:
        print(f"⚠️ Telemetry Logging Failed: {e}")