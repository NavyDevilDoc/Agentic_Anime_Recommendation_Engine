"""
MODULE: analysis/post_mission_reconciliation.py
FUNCTION: Unified post-ingestion cleanup. Handles corrupted payloads, missing localizations, 
          and CASREP board maintenance in a single sequential sweep.
"""
import sqlite3
import os
import json
import requests
import time

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def run_reconciliation_protocol():
    if not os.path.exists(DB_PATH):
        print(f"❌ CRITICAL: Vault not found at {DB_PATH}")
        return

    print("\n" + "🛡️"*20)
    print(" INITIATING POST-MISSION RECONCILIATION PROTOCOL")
    print("🛡️"*20 + "\n")

    # --- PHASE 1: DIAGNOSTIC RECONNAISSANCE ---
    corrupted_ids = []
    missing_titles = []
    ghost_casreps = 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # 1. Scan for Corrupted JSON Payloads
        cursor.execute("SELECT id, english_title, consensus_json FROM anime_info WHERE consensus_json IS NOT NULL")
        for mal_id, title, raw_json in cursor.fetchall():
            try:
                data = json.loads(raw_json)
                if not isinstance(data, dict):
                    corrupted_ids.append((mal_id, title))
            except json.JSONDecodeError:
                corrupted_ids.append((mal_id, title))

        # 2. Scan for Missing English Titles
        cursor.execute("SELECT id, romaji_title FROM anime_info WHERE english_title IS NULL OR english_title = ''")
        missing_titles = cursor.fetchall()

        # 3. Scan for "Ghost Ship" CASREPs (0-review logs)
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='intelligence_quarantine'")
        if cursor.fetchone()[0]:
            cursor.execute("SELECT COUNT(*) FROM intelligence_quarantine WHERE error_message LIKE '%Returned 0 reviews%'")
            ghost_casreps = cursor.fetchone()[0]

    # --- PHASE 2: THE DEBRIEF ---
    print("📊 RECONNAISSANCE REPORT:")
    print(f"  • Corrupted Intelligence Packets : {len(corrupted_ids)}")
    print(f"  • Missing English Localizations  : {len(missing_titles)}")
    print(f"  • Non-Actionable CASREP Logs     : {ghost_casreps}")

    if not any([corrupted_ids, missing_titles, ghost_casreps]):
        print("\n✅ Vault is in pristine condition. No reconciliation required.")
        return

    print("\n" + "⚠️"*20)
    auth = input("Type 'AUTHORIZE-SWEEP' to execute all pending maintenance tasks: ").strip()

    if auth != "AUTHORIZE-SWEEP":
        print("\n🛑 Authorization aborted. No data was modified.")
        return

    # --- PHASE 3: EXECUTION ---
    print("\n🚀 Executing Maintenance Sweep...")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Task A: Surgical JSON Wipe
        if corrupted_ids:
            print("  ➡️ Wiping corrupted AI payloads to trigger Commander re-ingestion...")
            ids_to_wipe = [c[0] for c in corrupted_ids]
            placeholders = ','.join(['?'] * len(ids_to_wipe))
            cursor.execute(f"UPDATE anime_info SET consensus_json = NULL WHERE id IN ({placeholders})", ids_to_wipe)
            conn.commit()
            print(f"     ✅ {len(ids_to_wipe)} corrupted fields nullified.")

        # Task B: Translation Backfill
        if missing_titles:
            print("  ➡️ Engaging Jikan API for missing localizations...")
            for mal_id, romaji in missing_titles:
                try:
                    url = f"https://api.jikan.moe/v4/anime/{mal_id}"
                    response = requests.get(url)
                    
                    if response.status_code == 429:
                        time.sleep(5)
                        response = requests.get(url)
                        
                    response.raise_for_status()
                    en_title = response.json().get('data', {}).get('title_english') or romaji
                    
                    cursor.execute("UPDATE anime_info SET english_title = ? WHERE id = ?", (en_title, mal_id))
                    conn.commit()
                    print(f"     ✅ Translated [{mal_id}]: {en_title}")
                    time.sleep(3.0) # Respect rate limits
                except Exception as e:
                    print(f"     ❌ Jikan Error for [{mal_id}]: {e}")

        # Task C: CASREP Board Cleanup
        if ghost_casreps > 0:
            print("  ➡️ Purging non-actionable CASREP logs...")
            cursor.execute("DELETE FROM intelligence_quarantine WHERE error_message LIKE '%Returned 0 reviews%'")
            conn.commit()
            print(f"     ✅ {ghost_casreps} ghost logs cleared from the casualty board.")

    print("\n🏁 RECONCILIATION PROTOCOL COMPLETE. Vault is secure and fully optimized.")

if __name__ == "__main__":
    run_reconciliation_protocol()