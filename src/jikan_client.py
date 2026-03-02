import requests
import time
import logging

logger = logging.getLogger(__name__)

class JikanClient:
    def __init__(self):
        self.base_url = "https://api.jikan.moe/v4"
        self.rate_limit_delay = 3.0 
        # PERFORMANCE: Use a session to pool TCP connections
        self.session = requests.Session()

    def get_anime_reviews(self, mal_id, attempt=1, max_attempts=3):
        endpoint = f"{self.base_url}/anime/{mal_id}/reviews"
        
        try:
            response = self.session.get(endpoint)
            
            if response.status_code == 429:
                if attempt > max_attempts:
                    logger.error(f"❌ Jikan Rate Limit: Max retries exhausted for ID {mal_id}")
                    return []
                
                # Exponential backoff for safety
                wait_time = 2 ** attempt 
                logger.warning(f"⚠️ Rate limited by Jikan. Cooling down for {wait_time}s (Attempt {attempt})...")
                time.sleep(wait_time)
                return self.get_anime_reviews(mal_id, attempt + 1, max_attempts)
            
            response.raise_for_status()
            data = response.json()
            
            reviews = []
            for item in data.get('data', []):
                reviews.append({
                    "content": item.get('review', ""),
                    "score": item.get('score', 0),
                    "tags": item.get('tags', []),
                    "reactions": item.get('reactions', {}) # CRITICAL FIX: Restored for VADER
                })
            
            time.sleep(self.rate_limit_delay)
            return reviews

        except Exception as e:
            logger.error(f"❌ Jikan Error for ID {mal_id}: {e}")
            return []