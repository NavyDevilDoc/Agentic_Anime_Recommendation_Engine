"""
MODULE: analysis/test_sql_defenses.py
FUNCTION: Red Team diagnostic. Actively attacks the Vault Interface to verify 
          Read-Only URI locks and SQL Injection countermeasures.
"""

import os
import sys
import sqlite3

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import analysis.queries as queries

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def check_vault_health():
    """Independent check to verify the database wasn't actually altered."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM anime_info")
            count = cursor.fetchone()[0]
            
            cursor.execute("SELECT english_title FROM anime_info WHERE english_title = 'Pwned by Red Team'")
            hacked_row = cursor.fetchone()
            
            return count, bool(hacked_row)
    except Exception as e:
        return f"CRITICAL FAILURE: {e}", True

def run_red_team_drill():
    print("\n" + "🔴"*20)
    print(" INITIATING RED TEAM SQL INJECTION DRILL")
    print("🔴"*20 + "\n")

    # Get baseline health
    initial_count, _ = check_vault_health()
    print(f"📊 Baseline Vault Row Count: {initial_count}\n")

    # The Attack Payloads
    attacks = {
        "1. THE NUKE (Drop Table)": "DROP TABLE anime_info;",
        "2. THE PURGE (Mass Delete)": "DELETE FROM anime_info;",
        "3. THE VANDAL (Mass Update)": "UPDATE anime_info SET mal_score = 1.0;",
        "4. THE FORGER (Illicit Insert)": "INSERT INTO anime_info (english_title, mal_score) VALUES ('Pwned by Red Team', 10.0);",
        "5. THE PIGGYBACK (Stacked Query)": "SELECT english_title FROM anime_info LIMIT 1; DROP TABLE anime_info;"
    }

    passed_tests = 0

    for attack_name, payload in attacks.items():
        print(f"🗡️ Launching {attack_name}")
        print(f"   Payload: {payload}")
        
        # Fire the payload through the standard LLM interface
        results = queries.execute_lens_query(payload)
        
        # If it returns an empty list, the queries.py exception handler caught the OperationalError
        if results == []:
            print("   🛡️ BLOCKED: Vault Interface successfully rejected the attack.\n")
            passed_tests += 1
        else:
            print(f"   ❌ BREACH DETECTED: Query executed successfully! Returned: {results}\n")

    # --- POST-ATTACK BATTLE DAMAGE ASSESSMENT ---
    print("\n" + "🩺"*20)
    print(" EXECUTING BATTLE DAMAGE ASSESSMENT")
    print("🩺"*20 + "\n")

    post_count, is_hacked = check_vault_health()
    
    if isinstance(post_count, str):
        print(f"💀 CATASTROPHIC KILL: The table was destroyed. Error: {post_count}")
    elif post_count != initial_count:
        print(f"⚠️ DATA LOSS DETECTED: Row count changed from {initial_count} to {post_count}.")
    elif is_hacked:
        print("⚠️ INJECTION SUCCESSFUL: Illicit data was written to the vault.")
    elif passed_tests == 5:
        print(f"✅ VAULT SECURE. All {passed_tests}/5 attacks were neutralized.")
        print(f"   Row count remains stable at {post_count}.")
    else:
        print("⚠️ UNKNOWN ANOMALY DETECTED.")

if __name__ == "__main__":
    run_red_team_drill()