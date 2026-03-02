"""
MODULE: vault_manager.py
FUNCTION: Unified Self-Healing Commander. Orchestrates ingestion with 
          real-time quality auditing and autonomous retries.
"""
import os
import sys
import sqlite3
import asyncio
import json
import time
import requests
from tqdm import tqdm
from datetime import datetime # [ADDED] For rolling window calculations

# --- DYNAMIC PATH ANCHOR ---
current_dir = os.path.abspath(os.path.dirname(__file__))

# Auto-detect if we are in the root or inside the 'src' folder
if os.path.exists(os.path.join(current_dir, 'data')):
    ROOT_DIR = current_dir
else:
    ROOT_DIR = os.path.abspath(os.path.join(current_dir, '..'))

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.seasonal_ingestor_v2 import SeasonalIngestor
import analysis.queries as queries # [ADDED] To resolve human-typed titles to DB records

# --- CONFIG ---
DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

def ensure_db_ready(force_nuke=False):
    """Initializes or connects to the database with manual authorization locks."""
    
    # 1. THE NUKE PROTOCOL (Requires 2FA)
    if force_nuke and os.path.exists(DB_PATH):
        print("\n" + "⚠️"*20)
        print(" CRITICAL WARNING: DATABASE DESTRUCTION PROTOCOL INITIATED")
        print(f" Target: {DB_PATH}")
        print("⚠️"*20)
        
        auth = input("\nType 'CONFIRM-NUKE' to authorize permanent deletion: ").strip()
        if auth == "CONFIRM-NUKE":
            os.remove(DB_PATH)
            print("🔥 DATABASE NUKED: Starting from zero.")
        else:
            print("🛑 Authorization failed or aborted. Exiting program to protect data.")
            sys.exit(1) # Instantly kills the script

    # 2. THE INITIALIZATION PROTOCOL (Requires 2FA)
    if not os.path.exists(DB_PATH):
        print("\n" + "⚠️"*20)
        print(f" ATTENTION: No database found at {DB_PATH}")
        print("⚠️"*20)
        
        auth = input("\nType 'INIT-VAULT' to authorize creating a new, empty schema: ").strip()
        if auth == "INIT-VAULT":
            print("✅ Authorization accepted. Initializing Pristine Schema...")
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE anime_info (
                        id INTEGER PRIMARY KEY,
                        romaji_title TEXT,
                        english_title TEXT,
                        mal_score REAL,
                        season TEXT,
                        scored_by INTEGER,
                        studio TEXT,
                        avg_sentiment REAL,
                        consensus_json TEXT,
                        mal_synopsis TEXT,
                        release_year INTEGER
                    )
                """)
        else:
            print("🛑 Initialization aborted. Check your file paths and try again.")
            sys.exit(1)
            
    # 3. STANDARD OPERATING PROCEDURE
    else:
        print(f"📡 DATABASE DETECTED: Operating in Persistence Mode.")



def run_seasonal_audit(year, season_name):
    """
    Performs a targeted quality check on a specific season.
    Returns a list of IDs that failed to meet quality standards.
    """
    season_tag = f"{season_name.capitalize()}_{year}"
    failed_ids = []
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, english_title, consensus_json, avg_sentiment 
            FROM anime_info 
            WHERE season = ?
        """, (season_tag,))
        rows = cursor.fetchall()

        for row in rows:
            mal_id, title, c_json_str, sentiment = row
            try:
                data = json.loads(c_json_str) if c_json_str else None
                # Check for NULLs or missing intelligence packets
                if not data or not isinstance(data, dict):
                    failed_ids.append(mal_id)
                    continue
                
                # Check for low-density/failed distillation
                if not data.get('pros') or len(data.get('pros')) == 0:
                    pass
            except:
                failed_ids.append(mal_id)
                
    return failed_ids

async def execute_self_healing_campaign(targets):
    """
    The Loop: Ingest -> Audit -> Retry with Exponential Backoff and Stagnation Detection.
    Ensures high-fidelity data density without risking infinite loops.
    """
    import src.seasonal_ingestor_v2 as ingestor_mod
    ingestor_mod.DEFAULT_DB_PATH = DB_PATH
    ingestor = SeasonalIngestor(db_path=DB_PATH)

    for t in targets:
        attempt = 1
        max_attempts = 5  
        last_gap_count = float('inf')
        
        while attempt <= max_attempts:
            print(f"\n📡 MISSION: {t['season'].upper()} {t['year']} (Attempt {attempt})")
            
            # 1. INGEST: Attempt to fill the vault
            await ingestor.ingest_season(t['year'], t['season'], target_ids=gaps if attempt > 1 else None)
            
            # 2. AUDIT: Immediately verify the results
            gaps = run_seasonal_audit(t['year'], t['season'])
            
            # SUCCESS CASE: All shows validated
            if not gaps:
                with sqlite3.connect(DB_PATH) as conn:
                    count = conn.execute("SELECT COUNT(*) FROM anime_info WHERE season = ?", (f"{t['season'].capitalize()}_{t['year']}",)).fetchone()[0]
                
                if count > 0:
                    print(f"✅ VERIFIED: {t['season'].upper()} {t['year']} is 100% complete.")
                    break
                else:
                    # [MODIFIED] Break the loop instead of setting gaps = None to prevent runaway API calls on empty seasons
                    print(f"⏩ SEASON SKIPPED: No records found for {t['season'].upper()} {t['year']}. (Likely too early for community reviews). Moving to next target.")
                    break 
            
            # PROGRESS CHECK: Detecting if the API is ignoring us
            current_gap_count = len(gaps) if gaps is not None else 0
            
            if current_gap_count == last_gap_count and gaps is not None:
                print(f"⚠️  STAGNATION: No new intelligence distilled in Attempt {attempt}.")
            last_gap_count = current_gap_count

            # FAILURE CASE: Exhausted retry budget
            if attempt == max_attempts:
                print(f"🛑 MISSION ABORTED: {current_gap_count if gaps is not None else 'All'} shows persistently failing after {max_attempts} tries.")
                break

            # HEALING PHASE: Exponential backoff to clear rate limits
            wait_time = 15 * attempt 
            print(f"⚠️  GAP DETECTED: {current_gap_count} shows failed validation. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            attempt += 1

    print(f"\n🏁 ALL CAMPAIGNS COMPLETE: Intelligence asset verified at {DB_PATH}")


# =========================================================================
# [ADDED] TARGETED DRIFT MITIGATION MODULE
# =========================================================================

async def _force_update_targets(target_dict):
    """
    [ADDED] Helper function: Takes a dictionary of {season_tag: [mal_ids]} 
    and forces the ingestor to re-process them by clearing their consensus.
    """
    import src.seasonal_ingestor_v2 as ingestor_mod
    ingestor_mod.DEFAULT_DB_PATH = DB_PATH
    ingestor = SeasonalIngestor(db_path=DB_PATH)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for season_tag, ids in target_dict.items():
            if not ids: continue
            
            # Trick the ingestor into reprocessing by deleting the old intelligence payload
            placeholders = ','.join(['?'] * len(ids))
            cursor.execute(f"UPDATE anime_info SET consensus_json = NULL WHERE id IN ({placeholders})", ids)
            conn.commit()

            # Parse season_tag (e.g., "Spring_2024")
            try:
                s_name, s_year = season_tag.split('_')
                s_year = int(s_year)
            except ValueError:
                print(f"⚠️ Could not parse season tag '{season_tag}'. Skipping.")
                continue

            print(f"\n🎯 EXECUTING TARGETED STRIKE: {season_tag.upper()} ({len(ids)} targets)")
            await asyncio.sleep(3)
            # Pass the specific IDs to the ingestor, which will fetch fresh Jikan data and hit Gemini
            await ingestor.ingest_season(s_year, s_name.lower(), target_ids=ids)
            
    print("\n🏁 TARGETED UPDATES COMPLETE.")

async def update_specific_targets(titles_list):
    """
    [MODIFIED] Capability A: Targeted Strike (Sniper Mode)
    Uses the Live API to get the MAL ID, clears its intelligence payload, 
    and directly feeds it to the Ingestor's Sniper Mode.
    Leaves the seasonal bulk ingestion logic completely untouched.
    """
    print(f"\n🔍 Resolving {len(titles_list)} specific targets via Live API...")
    
    import src.seasonal_ingestor_v2 as ingestor_mod
    ingestor_mod.DEFAULT_DB_PATH = DB_PATH
    ingestor = SeasonalIngestor(db_path=DB_PATH)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        for t in titles_list:
            print(f"\n 🌐 Pinging Jikan API for definitive ID: '{t}'...")
            try:
                time.sleep(1.5) # Strict pacing for Jikan Rate Limits
                
                search_url = f"https://api.jikan.moe/v4/anime?q={t}&type=tv&limit=1"
                response = requests.get(search_url)
                
                if response.status_code == 200:
                    data = response.json().get('data', [])
                    if data:
                        show_data = data[0]
                        mal_id = show_data.get('mal_id')
                        title_en = show_data.get('title_english') or show_data.get('title')
                        
                        print(f" ✨ Target Acquired: {title_en} (ID: {mal_id})")
                        
                        # Set consensus to NULL to authorize the overwrite
                        cursor.execute("UPDATE anime_info SET consensus_json = NULL WHERE id = ?", (mal_id,))
                        conn.commit()
                        
                        # Fire the Sniper Mode safely
                        await ingestor.ingest_single_anime(mal_id)
                        
                    else:
                        print(f" ❌ Target Ghosted: Jikan API found zero TV results for '{t}'.")
                else:
                    print(f" ❌ API Error: Jikan returned status {response.status_code} for '{t}'.")
            except Exception as e:
                print(f" ❌ Network Error during live search for '{t}': {e}")
                
    print("\n🏁 TARGETED UPDATES COMPLETE.")

async def update_recent_releases(years_back=2):
    """
    [ADDED] Capability B: The Rolling Window
    Updates all shows released within the last X years to capture late review velocity.
    """
    current_year = datetime.now().year
    cutoff_year = current_year - years_back
    print(f"\n📅 Initiating Rolling Window Update (Releases >= {cutoff_year})...")
    
    target_dict = {}
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, season FROM anime_info WHERE release_year >= ?", (cutoff_year,))
        rows = cursor.fetchall()
        
        for mal_id, season_tag in rows:
            if season_tag not in target_dict:
                target_dict[season_tag] = []
            target_dict[season_tag].append(mal_id)
            
    total_targets = sum(len(ids) for ids in target_dict.values())
    print(f"✅ Found {total_targets} targets in the rolling window.")
    
    if target_dict:
        await _force_update_targets(target_dict)

# =========================================================================

if __name__ == "__main__":
    ensure_db_ready(force_nuke=False) 

    # --- CHOOSE YOUR OPERATION MODE ---
    # Uncomment the ONE mode you wish to execute:
    
    # MODE 1: Standard Seasonal Ingestion (Original)
    years = [2026] # or years = range(start_year, end_year) where the end_year is not included in the range 
    seasons = ['winter'] # 'summer', 'winter', 'fall', 'spring'
    campaign_targets = [{'year': y, 'season': s} for y in years for s in seasons]
    asyncio.run(execute_self_healing_campaign(campaign_targets))

    """
    # MODE 2: Targeted Strike (Specific Shows)
    targets_to_update = ["Lycoris Recoil"]
    asyncio.run(update_specific_targets(targets_to_update))
    """

    """
    # MODE 3: Rolling Window Update (Last 2 Years)
    asyncio.run(update_recent_releases(years_back=2))
    """
    
    print("⚠️  No operation selected. Uncomment a MODE in the __main__ block to run.")