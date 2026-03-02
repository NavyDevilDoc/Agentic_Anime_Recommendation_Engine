import requests
import json
import os

class MALClient:
    def __init__(self, token_path="token_data.json"):
        self.token_path = token_path
        self.session = requests.Session()
        self.headers = {} # Re-initializing the explicit attribute for the ingestor
        self._load_token()

    def _load_token(self):
        if not os.path.exists(self.token_path):
            raise FileNotFoundError(f"Missing MAL token file at: {self.token_path}")
            
        with open(self.token_path, 'r') as f:
            token_data = json.load(f)
            self.token = token_data.get('access_token')
            
        # Expose the headers for external requests.get() calls, and apply to session
        self.headers = {'Authorization': f'Bearer {self.token}'}
        self.session.headers.update(self.headers)
            
        with open(self.token_path, 'r') as f:
            token_data = json.load(f)
            self.token = token_data.get('access_token')
            
        self.session.headers.update({'Authorization': f'Bearer {self.token}'})

    def get_anime_details(self, anime_id):
        fields = "synopsis,genres,studios,mean,rank,popularity"
        url = f"https://api.myanimelist.net/v2/anime/{anime_id}?fields={fields}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ MAL Details Fetch Error for {anime_id}: {e}")
            return {}