"""
MODULE: analysis/view_show_report.py
FUNCTION: Tactical Intelligence Briefing with Virtual Controversy Inference.
          Now powered by the Three-Tier Fault Tolerance Engine.
"""

import sys
import os
from google import genai
from dotenv import load_dotenv

# --- SYSTEM PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import analysis.queries as queries

load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

def get_virtual_driver(summary, score):
    """
    Virtual Inference Phase:
    Briefly explains the 'Why' behind a high controversy score.
    """
    if score < 6:
        return None
    
    client = genai.Client(api_key=GOOGLE_API_KEY)
    prompt = f"""
    Analyze this anime consensus summary and the controversy score of {score}/10.
    Briefly explain (1 sentence) the likely cause of this audience division.
    
    SUMMARY: {summary}
    """
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return response.text.strip()
    except Exception:
        return "Context unavailable for this briefing."

def fetch_report(search_query):
    """Queries and formats the intelligence debriefing using the Vault Interface."""
    
    # --- TIER 1 & 2: RESOLVE THE TARGET ---
    matches = queries.resolve_show_title(search_query)
    
    if not matches:
        print(f"\n[!] Target MIA: Could not resolve '{search_query}' to any known intelligence.\n")
        return

    # FRANCHISE COLLISION LOGIC: Ask the user to clarify if multiple shows match
    if len(matches) == 1:
        resolved_title = matches[0]
    else:
        print(f"\n[?] MULTIPLE TARGETS FOUND FOR '{search_query.upper()}':")
        for i, match in enumerate(matches, 1):
            print(f"  {i}. {match}")
        
        print(f"  0. [ABORT SEARCH]")
        
        choice = input(f"\nEnter the target number (0-{len(matches)}): ").strip()
        
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(matches):
            print("\n🛑 Target acquisition aborted.\n")
            return
            
        resolved_title = matches[int(choice) - 1]

    # --- FETCH FUSION PROFILE ---
    profiles = queries.fetch_fusion_profiles([resolved_title])
    
    if not profiles:
        print(f"\n[!] Error: Intelligence missing for resolved target '{resolved_title}'.\n")
        return

    profile = profiles[0]

    # --- TIER 3: DISPLAY THE DEBRIEF ---
    print("\n" + "█"*60)
    print(f"📊 INTELLIGENCE DEBRIEF: {profile['title'].upper()}")
    print("-" * 60)
    print(f"🏢 STUDIO: {profile['studio'] or 'UNKNOWN'}")
    print(f"⭐ QUALITY: {profile['quality_score']} | 🎭 MOOD: {profile['audience_sentiment']:.2f}")
    print(f"📝 CONSENSUS: {profile['audience_consensus']}")
    
    c_score = profile['controversy_score']
    print(f"\n🔥 CONTROVERSY: {c_score}/10")
    
    if c_score >= 6:
        print("   [SYSTEM] Inferring controversy drivers...")
        driver = get_virtual_driver(profile['audience_consensus'], c_score)
        if driver:
            print(f"   CONTEXT: {driver}")
    
    print(f"\n✅ THE PROS:")
    for pro in profile.get('pros', []):
        print(f"  • {pro}")
    
    print(f"\n❌ THE CONS:")
    for con in profile.get('cons', []):
        print(f"  • {con}")
        
    print("█"*60 + "\n")

if __name__ == "__main__":
    print("\n" + "="*60)
    print(" TACTICAL INTELLIGENCE TERMINAL ONLINE")
    print(" Type 'exit' or 'quit' to terminate the session.")
    print("="*60)

    # Handle the case where a user launches it with an argument (e.g., python view_show_report.py bleach)
    if len(sys.argv) > 1:
        initial_target = " ".join(sys.argv[1:])
        fetch_report(initial_target)

    # Drop into the persistent query loop
    while True:
        target_show = input("\nEnter show title (or 'exit'): ").strip()
        
        # The Kill Switch
        if target_show.lower() in ['exit', 'quit', '0']:
            print("\n[SYSTEM] Terminating terminal session. Standing down.\n")
            break
            
        # Ignore empty accidental 'Enters'
        if not target_show:
            continue
            
        fetch_report(target_show)