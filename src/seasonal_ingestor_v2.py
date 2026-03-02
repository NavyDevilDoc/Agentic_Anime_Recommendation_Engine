"""
MODULE: src/seasonal_ingestor_v2.py
FUNCTION: Hybrid Ingestion with Deep Diagnostic Telemetry.
"""
import os
import sys
import sqlite3
import json
import math
import requests
import asyncio
import time
from tqdm import tqdm
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# --- PATH HANDLER ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))

from src.mal_api_client import MALClient
from src.jikan_client import JikanClient
from analysis.sentiment_distiller import ReviewDistiller

# Default path used if none is injected
DEFAULT_DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")

class SentimentEngine:
    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()

    def calculate_jit_sentiment(self, reviews):
        if not reviews: return 0.0
        
        sum_weighted_sentiments = 0.0
        sum_weights = 0.0
        
        for r in reviews:
            content = r.get('content', '')
            interactions = r.get('reactions', {}).get('overall', 0)
            user_score = r.get('score', 0)
            if not content or len(content.strip()) < 10: continue

            # Clean the sentences to avoid empty strings
            sentences = [s.strip() for s in content.split('.') if s.strip()]
            
            # EDGE CASE FIX: If review is 2 sentences or less, do a flat sentiment analysis
            if len(sentences) <= 2:
                raw_sentiment = self.analyzer.polarity_scores(content)['compound']
            else:
                split_point = int(len(sentences) * 0.75)
                intro = ". ".join(sentences[:split_point])
                concl = ". ".join(sentences[split_point:])
                
                intro_score = self.analyzer.polarity_scores(intro)['compound']
                concl_score = self.analyzer.polarity_scores(concl)['compound']
                raw_sentiment = (intro_score * 0.3) + (concl_score * 0.7)

            final_sentiment = raw_sentiment
            if user_score >= 9: final_sentiment = max(raw_sentiment, 0.5)
            elif user_score <= 3: final_sentiment = min(raw_sentiment, -0.2)

            # True Weighted Average Calculation
            hype_weight = math.log10(interactions + 1) + 1
            sum_weighted_sentiments += (final_sentiment * hype_weight)
            sum_weights += hype_weight

        # Divide the total weighted sentiment by the total weight
        return sum_weighted_sentiments / sum_weights if sum_weights > 0 else 0.0

class SeasonalIngestor:
    def __init__(self, db_path=None):
        self.db_path = db_path if db_path else DEFAULT_DB_PATH
        self.mal = MALClient(token_path=os.path.join(ROOT_DIR, "token_data.json"))
        self.jikan = JikanClient()
        self.distiller = ReviewDistiller(api_key=os.getenv("GOOGLE_API_KEY"))
        self.sentiment_engine = SentimentEngine()
        self.jikan.rate_limit_delay = 3.0
        self._init_quarantine()
        
        print(f"📡 Ingestor Initialized. Target Database: {self.db_path}")


    async def ingest_single_anime(self, mal_id):
        """
        [ADDED] Capability: The Sniper Mode. 
        Bypasses the season sweep and ingests/updates a single show directly by ID.
        """
        print(f"\n🎯 DIRECT INGESTION MISSION: ID {mal_id}")
        
        # 1. Fetch exact metadata from MAL
        url = f"https://api.myanimelist.net/v2/anime/{mal_id}"
        params = {'fields': 'synopsis,genres,studios,mean,num_scoring_users,alternative_titles,media_type,start_season'}
        
        try:
            response = requests.get(url, headers=self.mal.headers, params=params)
            response.raise_for_status()
            node = response.json() # For a single anime, the payload IS the node
        except Exception as e:
            print(f" ❌ MAL API FATAL ERROR FOR ID {mal_id}: {e}")
            return
            
        title = node.get('title', f"Unknown ID {mal_id}")
        
        # 2. Extract season/year dynamically
        start_season = node.get('start_season', {})
        year = start_season.get('year', 9999)
        season = start_season.get('season', 'unknown')
        season_tag = f"{season.capitalize()}_{year}"

        if self._show_exists(mal_id):
            self._clear_casualty(mal_id)
            # If called via vault_manager, consensus_json is usually NULLed first,
            # so this check safely ignores fully complete shows but allows forced updates.
            print(f" ⚠️ Show '{title}' already exists with full intelligence. Skipping.")
            return

        # 3. Fetch Reviews
        print(f" ⏳ Fetching Jikan reviews for {title}...")
        reviews = self.jikan.get_anime_reviews(mal_id)
        if not reviews:
            self._log_casualty(mal_id, title, season_tag, "JIKAN_API", "Returned 0 reviews. Cannot distill.")
            return

        # 4. Math & AI Distillation
        avg_sentiment = self.sentiment_engine.calculate_jit_sentiment(reviews)

        context = {
            "title": title, 
            "synopsis": node.get('synopsis', ''), 
            "reviews": [r.get('content', '') for r in reviews[:15]]
        }
        
        try:
            print(f" 🧠 Distilling consensus for {title}...")
            await asyncio.sleep(2.0)
            consensus_json = await self.distiller.distill_sentiment(context)
            
            if not consensus_json:
                self._log_casualty(mal_id, title, season_tag, "AI_DISTILLATION", "Gemini returned None. Possible safety filter or parsing failure.")
                return

            # 5. Save to Vault
            self._save_to_db(node, consensus_json, avg_sentiment, year, season)
            self._clear_casualty(mal_id)
            print(f" ✅ MISSION ACCOMPLISHED: '{title}' vaulted.")
            
        except Exception as e:
            if "429" in str(e):
                print(f"   ⏳ Quota hit for {title}. Cooling down...")
                await asyncio.sleep(30)
            else:
                print(f"   ❌ DISTILLATION ERROR for {title}: {e}")
                self._log_casualty(mal_id, title, season_tag, "UNHANDLED_EXCEPTION", str(e))


    async def ingest_season(self, year, season, target_ids=None):
        print(f"\n🚀 MISSION START: {season.upper()} {year}")
        if target_ids:
            print(f"🎯 TARGETED STRIKE: Focusing strictly on {len(target_ids)} missing/incomplete shows.")
        
        url = f"https://api.myanimelist.net/v2/anime/season/{year}/{season}"
        # ADDED 'media_type' to the fields parameter
        params = {'limit': 100, 'fields': 'synopsis,genres,studios,mean,num_scoring_users,alternative_titles,media_type'}
        
        anime_list = []
        
        try:
            while url:
                response = requests.get(url, headers=self.mal.headers, params=params)
                response.raise_for_status()
                payload = response.json()
                
                # Extract the raw page data
                page_data = payload.get('data', [])
                
                # THE MEDIA FILTER: Keep only standard TV broadcasts
                tv_only_data = [entry for entry in page_data if entry['node'].get('media_type') == 'tv']
                
                anime_list.extend(tv_only_data)
                
                paging = payload.get('paging', {})
                url = paging.get('next') 
                params = None 
                
            if target_ids is not None:
                anime_list = [entry for entry in anime_list if entry['node']['id'] in target_ids]
                
            print(f"✅ MAL API: Successfully extracted {len(anime_list)} TV titles for this season.")
            
        except Exception as e:
            print(f"❌ MAL API FATAL ERROR: {e}")
            return

        for entry in tqdm(anime_list, desc=f"Vaulting {season}", unit="show"):
            node = entry['node']
            mal_id = node['id']
            title = node['title']
            season_tag = f"{season.capitalize()}_{year}"
            
            if self._show_exists(mal_id):
                # If it already has complete intelligence, clear any old casualties and skip
                self._clear_casualty(mal_id)
                continue

            # --- DIAGNOSTIC STEP 1: JIKAN REVIEWS ---
            reviews = self.jikan.get_anime_reviews(mal_id)
            if not reviews:
                # CASUALTY: No audience data found.
                self._log_casualty(mal_id, title, season_tag, "JIKAN_API", "Returned 0 reviews. Cannot distill.")
                continue

            # --- DIAGNOSTIC STEP 2: MATH ---
            avg_sentiment = self.sentiment_engine.calculate_jit_sentiment(reviews)

            # --- DIAGNOSTIC STEP 3: AI ---
            context = {
                "title": title, 
                "synopsis": node.get('synopsis', ''), 
                "reviews": [r.get('content', '') for r in reviews[:15]] # Safe .get extraction
            }
            
            try:
                await asyncio.sleep(2.0)
                consensus_json = await self.distiller.distill_sentiment(context)
                
                # CASUALTY: Gemini returned None (likely a Pydantic parse error or safety block)
                if not consensus_json:
                    self._log_casualty(mal_id, title, season_tag, "AI_DISTILLATION", "Gemini returned None. Possible safety filter or parsing failure.")
                    continue

                # --- DIAGNOSTIC STEP 4: DATABASE ---
                self._save_to_db(node, consensus_json, avg_sentiment, year, season)
                
                # HEALED: Successfully vaulted. Clear from CASREP.
                self._clear_casualty(mal_id)
                
            except Exception as e:
                if "429" in str(e):
                    print(f"   ⏳ Quota hit for {title}. Cooling down...")
                    await asyncio.sleep(30)
                else:
                    print(f"   ❌ DISTILLATION ERROR for {title}: {e}")
                    self._log_casualty(mal_id, title, season_tag, "UNHANDLED_EXCEPTION", str(e))
                continue

    def _show_exists(self, mal_id):
        """Checks if a show is not just present, but has 'Complete Intelligence'."""
        with sqlite3.connect(self.db_path, timeout=20) as conn:
            # We only skip if the show has BOTH a synopsis AND the AI consensus
            query = "SELECT 1 FROM anime_info WHERE id = ? AND consensus_json IS NOT NULL AND mal_synopsis IS NOT NULL"
            return conn.execute(query, (mal_id,)).fetchone() is not None

    def _save_to_db(self, node, consensus_json, avg_sentiment, year, season):
        try:
            with sqlite3.connect(self.db_path, timeout=20) as conn:
                studio = node.get('studios', [{}])[0].get('name', 'Unknown') if node.get('studios') else "Unknown"
                eng_title = node.get('alternative_titles', {}).get('en') or node['title']

                cursor = conn.cursor()
                # UPSERT LOGIC: Insert new, or update specific columns if the ID exists
                cursor.execute("""
                    INSERT INTO anime_info (
                        id, romaji_title, english_title, mal_score, 
                        season, scored_by, studio, avg_sentiment, 
                        consensus_json, mal_synopsis, release_year
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        avg_sentiment=excluded.avg_sentiment,
                        consensus_json=excluded.consensus_json,
                        mal_synopsis=excluded.mal_synopsis;
                """, (
                    node['id'], node['title'], eng_title, node.get('mean'), 
                    f"{season.capitalize()}_{year}", node.get('num_scoring_users'), 
                    studio, avg_sentiment, json.dumps(consensus_json), 
                    node.get('synopsis', ''), year
                ))
                conn.commit()
                print(f"  💾 UPSERT SUCCESS: '{eng_title}' secured in Vault.")
        except Exception as e:
            print(f"  ❌ DATABASE WRITE ERROR for {node['title']}: {e}")

    def _init_quarantine(self):
        """Creates the CASREP tracking table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligence_quarantine (
                    mal_id INTEGER PRIMARY KEY,
                    title TEXT,
                    season TEXT,
                    failure_node TEXT,
                    error_message TEXT,
                    last_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _log_casualty(self, mal_id, title, season, node, error_msg):
        """Logs a failure to the CASREP table."""
        try:
            with sqlite3.connect(self.db_path, timeout=20) as conn:
                conn.execute("""
                    INSERT INTO intelligence_quarantine (mal_id, title, season, failure_node, error_message, last_attempt)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(mal_id) DO UPDATE SET
                        failure_node=excluded.failure_node,
                        error_message=excluded.error_message,
                        last_attempt=CURRENT_TIMESTAMP;
                """, (mal_id, title, season, node, str(error_msg)))
        except Exception as e:
            print(f"  ❌ CASREP LOGGING FAILED for {title}: {e}")

    def _clear_casualty(self, mal_id):
        """Removes a show from quarantine if it successfully heals."""
        try:
            with sqlite3.connect(self.db_path, timeout=20) as conn:
                conn.execute("DELETE FROM intelligence_quarantine WHERE mal_id = ?", (mal_id,))
        except Exception:
            pass