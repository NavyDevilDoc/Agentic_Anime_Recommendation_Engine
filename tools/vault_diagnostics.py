"""
MODULE: analysis/vault_diagnostics.py
FUNCTION: Comprehensive Data Quality and AI Fidelity Audit.
"""
import sqlite3
import json
import os
import sys

# --- SYSTEM PATH ANCHORING ---
current_dir = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(current_dir, '..'))
DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def get_readonly_connection():
    uri_path = f"file:{DB_PATH}?mode=ro"
    return sqlite3.connect(uri_path, uri=True)

def run_diagnostic_audit():
    if not os.path.exists(DB_PATH):
        print(f"❌ CRITICAL: Vault not found at {DB_PATH}")
        return

    print("\n" + "📊"*15)
    print(" VAULT DIAGNOSTIC INITIATED")
    print("📊"*15 + "\n")

    try:
        with get_readonly_connection() as conn:
            cursor = conn.cursor()

            # --- 1. MACRO COMPLETENESS ---
            cursor.execute("SELECT COUNT(*) FROM anime_info")
            total_records = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM anime_info WHERE consensus_json IS NULL OR consensus_json = ''")
            missing_ai = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM anime_info WHERE mal_synopsis IS NULL OR mal_synopsis = ''")
            missing_synopsis = cursor.fetchone()[0]

            print("### 1. MACRO COMPLETENESS ###")
            print(f"Total Records Indexed: {total_records}")
            print(f"Missing AI Consensus : {missing_ai} ({(missing_ai/total_records)*100:.2f}%)")
            print(f"Missing MAL Synopsis : {missing_synopsis} ({(missing_synopsis/total_records)*100:.2f}%)\n")

            # --- 2. SENTIMENT ENGINE HEALTH ---
            cursor.execute("SELECT COUNT(*) FROM anime_info WHERE avg_sentiment = 0.0")
            flat_sentiment = cursor.fetchone()[0]
            
            print("### 2. MATH ENGINE HEALTH ###")
            print(f"Zero-Value Sentiment Scores: {flat_sentiment} (May indicate missing reviews or VADER split failures)\n")

            # --- 3. AI FIDELITY & SCHEMA COMPLIANCE ---
            print("### 3. AI FIDELITY INSPECTION ###")
            cursor.execute("SELECT english_title, consensus_json FROM anime_info WHERE consensus_json IS NOT NULL")
            rows = cursor.fetchall()

            corrupted_json = 0
            empty_pros = 0
            empty_cons = 0
            lazy_summaries = 0

            for title, raw_json in rows:
                try:
                    data = json.loads(raw_json)
                    
                    # DAMAGE CONTROL: Catch "null" payloads
                    if not isinstance(data, dict):
                        corrupted_json += 1
                        continue
                    
                    # Fidelity Checks
                    if not data.get('pros'): empty_pros += 1
                    if not data.get('cons'): empty_cons += 1
                    
                    summary = data.get('consensus_summary', '')
                    if len(summary.split()) < 10: 
                        lazy_summaries += 1

                except json.JSONDecodeError:
                    corrupted_json += 1

            analyzed = total_records - missing_ai
            print(f"Successfully Parsed JSONs: {analyzed - corrupted_json}/{analyzed}")
            print(f"Corrupted JSON Payloads  : {corrupted_json}")
            print(f"Empty 'Pros' Arrays      : {empty_pros}")
            print(f"Empty 'Cons' Arrays      : {empty_cons}")
            print(f"Lazy/Short Summaries     : {lazy_summaries}\n")

    except Exception as e:
        print(f"❌ Diagnostic Failure: {e}")

if __name__ == "__main__":
    run_diagnostic_audit()