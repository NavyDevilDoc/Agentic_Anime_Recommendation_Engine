"""
MODULE: generate_season_list.py
FUNCTION: Generates a summary of all anime entries stored in the database.
"""
import sqlite3
import os

# --- FILE PATHS ---
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")
REPORT_FILE = os.path.join(ROOT_DIR, "anime_inventory_summary.txt")

def create_inventory_report():
    if not os.path.exists(DATABASE_FILE):
        print(f"❌ Error: Database not found at {DATABASE_FILE}")
        return

    connection = sqlite3.connect(DATABASE_FILE)
    db_cursor = connection.cursor()

    # Retrieve unique year/season combinations, sorted chronologically
    db_cursor.execute("""
        SELECT DISTINCT release_year, season 
        FROM anime_info 
        ORDER BY release_year DESC, 
        CASE 
            WHEN season = 'fall' THEN 1
            WHEN season = 'summer' THEN 2
            WHEN season = 'spring' THEN 3
            WHEN season = 'winter' THEN 4
            ELSE 5 
        END ASC
    """)
    available_seasons = db_cursor.fetchall()

    print(f"📊 Creating summary report for {len(available_seasons)} seasons...")

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("📑 ANIME DATABASE INVENTORY SUMMARY\n")
        f.write("A listing of all analyzed titles and their community scores.\n")
        f.write("="*50 + "\n\n")

        for year, season in available_seasons:
            # Handle legacy entries or missing data gracefully
            year_label = year if year else "Uncategorized"
            season_label = season.upper() if season else "UNCATEGORIZED"
            
            f.write(f"SEASON: {season_label} {year_label}\n")
            f.write("TITLES:\n")

            # Fetch all titles within the specific season
            db_cursor.execute("""
                SELECT english_title, mal_score 
                FROM anime_info 
                WHERE release_year IS ? AND season IS ?
                ORDER BY mal_score DESC
            """, (year, season))
            
            anime_entries = db_cursor.fetchall()
            for index, (title, score) in enumerate(anime_entries, 1):
                f.write(f"Item {index}: {title} [Score: {score if score else 'N/A'}]\n")
            
            f.write("-" * 30 + "\n\n")

    connection.close()
    print(f"🏁 Report successfully created: {REPORT_FILE}")

if __name__ == "__main__":
    create_inventory_report()