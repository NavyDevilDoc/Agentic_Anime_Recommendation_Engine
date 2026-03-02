"""
MODULE: tools/fill_english_titles.py
FUNCTION: Scans the vault for missing English titles, lists them for review, 
          and queries Jikan to backfill them upon authorization.
"""
import sqlite3
import os
import requests
import time

# --- SYSTEM PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

# If the script is inside 'tools', 'analysis', or 'src', go up one level. 
# Otherwise, assume we are already in the root directory.
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def backfill_english_titles():
    if not os.path.exists(DB_PATH):
        print(f"❌ CRITICAL: Vault not found at {DB_PATH}")
        return

    print("\n" + "🌐"*15)
    print(" INITIATING TRANSLATION SWEEPER")
    print("🌐"*15 + "\n")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Find rows where english_title is missing or empty
            cursor.execute("SELECT id, romaji_title FROM anime_info WHERE english_title IS NULL OR english_title = ''")
            targets = cursor.fetchall()

            if not targets:
                print("✅ All intelligence files have localized titles. Sweeper standing down.")
                return

            # --- TARGET VERIFICATION PHASE ---
            print(f"⚠️ DETECTED {len(targets)} FILES REQUIRING LOCALIZATION:\n")
            for i, (_, romaji) in enumerate(targets, 1):
                print(f"  {i}. {romaji}")

            print("\n" + "🌐"*15)
            auth = input("\nType 'COMMENCE-SWEEP' to begin fetching translations from Jikan: ").strip()

            if auth != "COMMENCE-SWEEP":
                print("\n🛑 Authorization aborted. Sweeper returning to base.")
                return

            # --- EXECUTION PHASE ---
            print("\n🚀 Engaging Jikan API...")
            for mal_id, romaji in targets:
                try:
                    url = f"https://api.jikan.moe/v4/anime/{mal_id}"
                    response = requests.get(url)
                    
                    if response.status_code == 429:
                        print("  ⏳ Jikan Rate Limit hit. Pausing for 5 seconds...")
                        time.sleep(5)
                        response = requests.get(url)
                        
                    response.raise_for_status()
                    data = response.json().get('data', {})
                    
                    en_title = data.get('title_english')
                    if not en_title:
                        en_title = data.get('title', romaji)

                    cursor.execute("UPDATE anime_info SET english_title = ? WHERE id = ?", (en_title, mal_id))
                    conn.commit()
                    
                    print(f"  ✅ Updated: [{mal_id}] -> '{en_title}'")
                    time.sleep(3.0)

                except Exception as e:
                    print(f"  ❌ Failed to fetch title for ID {mal_id}: {e}")

            print("\n🏁 Translation Sweep Complete.")

    except Exception as e:
        print(f"❌ Database Error: {e}")

if __name__ == "__main__":
    backfill_english_titles()