"""
MODULE: analysis/cli_recommender.py
FUNCTION: Terminal interface for testing the Recommendation Engine before UI integration.
"""
import os
import sys
from dotenv import load_dotenv

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from analysis.recommendation_engine import RecommendationEngine

def print_results(response):
    """Parses the engine's output dictionary into a readable CLI debrief."""
    if not response.get('success'):
        print(f"\n❌ MISSION FAILED: {response.get('error')}")
        if 'diagnostics' in response and response['diagnostics'].get('sql_used'):
            print(f"   [SQL USED]: {response['diagnostics']['sql_used']}")
        return

    print("\n" + "🌟"*20)
    print(" INTELLIGENCE ASSETS ACQUIRED")
    print("🌟"*20 + "\n")

    if 'intersection_summary' in response:
        print(f"🧬 DNA SYNTHESIS: {response['intersection_summary']}\n")

    for idx, item in enumerate(response['data'], 1):
        profile = item['profile']
        print(f"[{idx}] {profile['title'].upper()}")
        print(f"    ⭐ QUALITY: {profile['quality_score']} | 🎭 VIBE: {profile['audience_sentiment']:.2f} | 🏢 STUDIO: {profile['studio']}")
        print(f"    🧠 AI REASONING: {item['ai_reasoning']}")
        
        if item.get('controversy_warning'):
            print(f"    ⚠️ FRICTION ALERT: {item['controversy_warning']}")
        print("-" * 60)
        
    print(f"\n[DIAGNOSTICS] SQL Executed: {response['diagnostics'].get('sql_used')}")


def run_terminal():
    load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))
    api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        print("❌ CRITICAL: GOOGLE_API_KEY not found in env_variables.env")
        return

    print("Initializing Semantic Fusion Engine...")
    engine = RecommendationEngine(api_key=api_key)

    while True:
        print("\n" + "="*50)
        print(" TACTICAL RECOMMENDER TERMINAL")
        print("="*50)
        print("1. Standard Intelligence Request (Select Lens)")
        print("2. DNA Triangulation Matrix (3 Reference Shows)")
        print("0. Exit")
        
        choice = input("\nSelect operation (0-2): ").strip()
        
        if choice == '0':
            print("\n[SYSTEM] Terminating session. Good hunting.\n")
            break
            
        elif choice == '1':
            print("\nAVAILABLE LENSES:")
            print(" [1] Baseline        (Standard Vibe Match)")
            print(" [2] Deep Scan       (Hidden Gems / High Sentiment, Lower Popularity)")
            print(" [3] Friction Filter (Explicitly avoid negative traits)")
            print(" [4] Vanguard        (High Risk / High Controversy)")
            
            lens_map = {"1": "Baseline", "2": "Deep Scan", "3": "Friction Filter", "4": "Vanguard"}
            lens_choice = input("\nSelect Lens (1-4): ").strip()
            lens_name = lens_map.get(lens_choice, "Baseline")
            
            user_prompt = input(f"\nEnter {lens_name} Request (e.g., 'gritty sci-fi'): ").strip()
            
            if user_prompt:
                print("\n🔍 Generating SQL and triangulating vault data... stand by.")
                result = engine.execute_standard_pipeline(user_prompt, lens_name)
                print_results(result)
                
        elif choice == '2':
            print("\nEnter 3 distinct shows to extract shared DNA.")
            show1 = input("  Target 1: ").strip()
            show2 = input("  Target 2: ").strip()
            show3 = input("  Target 3: ").strip()
            
            if show1 and show2 and show3:
                print("\n🧬 Synthesizing DNA Matrix and querying vault... stand by.")
                result = engine.execute_dna_triangulation([show1, show2, show3])
                print_results(result)
        else:
            print("Invalid selection.")

if __name__ == "__main__":
    run_terminal()