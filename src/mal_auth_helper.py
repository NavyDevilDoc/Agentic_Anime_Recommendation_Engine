"""
MODULE: src/mal_auth_helper.py
FUNCTION: Manages MAL OAuth2 PKCE Handshake and Lifecycle.
"""
import secrets
import requests
import os
import sys
import json
from dotenv import load_dotenv

# --- DYNAMIC PATH ANCHOR ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
env_path = os.path.join(ROOT_DIR, "env_variables.env")
load_dotenv(env_path)

CLIENT_ID = os.getenv("MAL_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("MAL_CLIENT_SECRET", "").strip()
TOKEN_PATH = os.path.join(ROOT_DIR, "token_data.json")

def generate_pkce_verifier():
    """Generates the plain verifier (exactly 128 chars)."""
    # 96 bytes urlsafe encoded yields exactly 128 characters
    return secrets.token_urlsafe(96)[:128] 

def print_auth_url(v):
    url = (
        f"https://myanimelist.net/v1/oauth2/authorize?"
        f"response_type=code&"
        f"client_id={CLIENT_ID}&"
        f"code_challenge={v}&"
        f"code_challenge_method=plain"
    )
    print("\n" + "📡"*20)
    print(f"STEP 1: VISIT THIS URL TO AUTHORIZE:\n\n{url}")
    print("\n" + "📡"*20)

def trade_code_for_token(auth_code, verifier):
    """The initial handshake."""
    url = "https://myanimelist.net/v1/oauth2/token"
    
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code.strip(),
        'code_verifier': verifier,
        'grant_type': 'authorization_code'
    }
    
    print(f"\n[DEBUG] Attempting swap with ID: {CLIENT_ID[:5]}...")
    response = requests.post(url, data=data)
    return response.json()

def refresh_mal_token():
    """
    Reads the existing refresh_token from disk and trades it for a new access_token.
    Returns True if successful, False otherwise.
    """
    if not os.path.exists(TOKEN_PATH):
        print("❌ No existing token found to refresh.")
        return False

    with open(TOKEN_PATH, 'r') as f:
        old_token_data = json.load(f)
        
    refresh_token = old_token_data.get('refresh_token')
    if not refresh_token:
        print("❌ Existing token data is missing the refresh payload.")
        return False

    url = "https://myanimelist.net/v1/oauth2/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }

    print("\n🔄 Initiating Token Refresh Protocol...")
    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        new_token_data = response.json()
        with open(TOKEN_PATH, "w") as f:
            json.dump(new_token_data, f, indent=4)
        print("✅ Token successfully refreshed and secured in Vault.")
        return True
    else:
        print(f"❌ Refresh Failed: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    print("1. Initialize New Token (Manual Auth)")
    print("2. Refresh Existing Token")
    choice = input("\nSelect an operation (1/2): ").strip()

    if choice == '1':
        v = generate_pkce_verifier()
        print_auth_url(v)
        code = input("\nPASTE AUTHORIZATION CODE HERE: ").strip()
        print("\n🚀 Executing Handshake (Bypassing Redirect URI)...")
        token_data = trade_code_for_token(code, v)
        
        if "access_token" in token_data:
            with open(TOKEN_PATH, "w") as f:
                json.dump(token_data, f, indent=4)
            print("\n" + "🏁"*20 + "\nMISSION SUCCESS: LINK ESTABLISHED\n" + "🏁"*20)
        else:
            print(f"\n❌ Handshake Failed: {token_data}")
            
    elif choice == '2':
        refresh_mal_token()
    else:
        print("Invalid choice.")