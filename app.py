"""
MODULE: app.py
FUNCTION: The main Streamlit frontend for the Anime Intelligence Engine.
          Features stateful pagination and objective deterministic routing.
"""
import streamlit as st
import os
import sys
import sqlite3
import pandas as pd
from dotenv import load_dotenv

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import analysis.queries as queries
from analysis.recommendation_engine import RecommendationEngine

load_dotenv(os.path.join(SCRIPT_DIR, "env_variables.env"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

st.set_page_config(page_title="Anime Intelligence Vault", layout="wide", page_icon="🗄️")

# --- STATE MANAGEMENT (Short-Term Memory) ---
if "active_pool" not in st.session_state:
    st.session_state.active_pool = []
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "current_results" not in st.session_state:
    st.session_state.current_results = []
if "sql_used" not in st.session_state:
    st.session_state.sql_used = ""
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "last_lens" not in st.session_state:
    st.session_state.last_lens = ""

st.markdown("""
    <style>
    .hero-header { font-size: 3.5rem !important; font-weight: 800; margin-bottom: 0px; color: #ffffff; line-height: 1.2; }
    .friction-box { background-color: #3e2723; border: 1px solid #d32f2f; padding: 12px; border-radius: 6px; color: #ffcdd2; font-size: 0.9rem; margin-top: 10px; margin-bottom: 10px; }
    .dna-box { background-color: #0d47a1; border: 1px solid #64b5f6; padding: 15px; border-radius: 8px; color: #e3f2fd; margin-bottom: 20px; }
    .score-badge { font-size: 1.2rem; font-weight: bold; color: #ffd700; }
    .mal-attribution { font-size: 0.85rem; color: #888; text-align: center; margin-top: 50px; padding-top: 20px; border-top: 1px solid #333;}
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def get_engine():
    return RecommendationEngine(api_key=GOOGLE_API_KEY)

engine = get_engine()

@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch_pool(query, lens):
    """Caches the heavy SQL generation and DB retrieval for 1 hour."""
    return engine.fetch_vault_pool(query, lens)

# --- SIDEBAR ---
with st.sidebar:
    st.title("📂 Encyclopedia Status")
    try:
        db_path = os.path.join(SCRIPT_DIR, "data", "anime_intelligence_v2.db")
        with sqlite3.connect(db_path) as conn:
            total_shows = conn.execute("SELECT COUNT(*) FROM anime_info").fetchone()[0]
            avg_score = conn.execute("SELECT AVG(mal_score) FROM anime_info").fetchone()[0]
        st.metric("Total Files Indexed", f"{total_shows:,}")
        st.metric("Avg MAL Score", f"{avg_score:.2f}")
    except Exception:
        st.warning("Database offline.")
    
    st.divider()
    st.markdown("### 📖 Definitions")
    st.write("**MAL Score:** Show's MyAnimeList score.")
    st.write("**Mood (Sentiment):** AI-distilled emotional tone (-1.0 to +1.0).")
    st.write("**Match Confidence:** How well the AI believes the show fits your specific prompt.")

# --- MAIN HEADER ---
st.markdown('<p class="hero-header">Anime Discovery Engine</p>', unsafe_allow_html=True)
st.caption("Find your next favorite show using AI and community consensus.")
st.divider()

# --- NAVIGATION TABS ---
tab_search, tab_triangulate, tab_archive = st.tabs(["🔍 FIND A SHOW", "🧬 SHOWS LIKE THIS", "🗄️ ENCYCLOPEDIA"])

# ==========================================
# TAB 1: SMART RECOMMENDATIONS (Stateful)
# ==========================================
with tab_search:
    st.subheader("AI Vibe Search")
    st.write("Scan the encyclopedia for specific themes, tones, or objective rankings.")
    
    lens_info = {
        "Standard Match": "Finds the best overall thematic and narrative fit.",
        "Hidden Gems": "Prioritizes highly-rated shows with smaller audiences.",
        "Crowd Pleasers": "Explicitly avoids highly controversial or divisive elements.",
        "Polarizing/Edgy": "High Risk / High Reward. Recommends polarizing, 'love-it-or-hate-it' shows.",
        "Objective Rankings": "Bypasses AI reasoning to return hard database rankings (e.g., 'Top 10 of Winter 2024')."
    }

    backend_lens_map = {
        "Standard Match": "Baseline",
        "Hidden Gems": "Deep Scan",
        "Crowd Pleasers": "Friction Filter",
        "Polarizing/Edgy": "Vanguard",
        "Objective Rankings": "Objective Rankings"
    }
    
    col1, col2 = st.columns([3, 1])
    with col1:
        user_query = st.text_input("Search Directive:", placeholder="e.g., 'gritty military drama with mecha' or 'Top 5 Winter 2023 shows'")
    with col2:
        lens_choice = st.selectbox("Discovery Mode:", list(lens_info.keys()))
        st.caption(f"*{lens_info[lens_choice]}*")
    
    submitted = st.button("Execute Search", type="primary", use_container_width=True)

    # 1. NEW SEARCH EXECUTION
    if submitted and user_query:
        with st.spinner("Triangulating vault data..."):
            engine_lens_name = backend_lens_map[lens_choice]
            
            # Fetch the pool of up to 30 shows
            pool_response = cached_fetch_pool(user_query, engine_lens_name)
            
            if not pool_response.get("success"):
                st.error(f"**Mission Failed:** {pool_response.get('error')}")
                st.session_state.current_results = []
            else:
                # Save the pool and metadata to Session State
                st.session_state.active_pool = pool_response["pool"]
                st.session_state.sql_used = pool_response["sql_used"]
                st.session_state.current_index = 0
                st.session_state.last_query = user_query
                st.session_state.last_lens = engine_lens_name
                
                # Slice the first 5 and process them
                chunk = st.session_state.active_pool[0:5]
                chunk_response = engine.process_next_chunk(user_query, chunk, engine_lens_name, st.session_state.sql_used)
                
                if chunk_response.get("success"):
                    st.session_state.current_results = chunk_response["data"]
                else:
                    st.error(f"**AI Synthesis Failed:** {chunk_response.get('error')}")

    # 2. DISPLAY RESULTS FROM MEMORY
    if st.session_state.current_results:
        st.success(f"Displaying results {st.session_state.current_index + 1} - {min(st.session_state.current_index + 5, len(st.session_state.active_pool))} of {len(st.session_state.active_pool)} potential targets.")
        
        for idx, item in enumerate(st.session_state.current_results):
            profile = item["profile"]
            with st.container(border=True):
                st.markdown(f"### {profile['title']} ({profile.get('release_year', 'Unknown')})")
                col_a, col_b, col_c = st.columns(3)
                col_a.write(f"**Studio:** {profile['studio']}")
                col_b.write(f"**Quality:** <span class='score-badge'>{profile['quality_score']}</span>", unsafe_allow_html=True)
                
                # Only show match confidence for Vibe Searches
                if st.session_state.last_lens != "Objective Rankings":
                    col_c.write(f"**Match Confidence:** {item.get('match_confidence', 'N/A')}%")
                else:
                    col_c.write("**Match:** Direct DB Hit")
                
                st.info(f"**AI Reasoning:** {item['ai_reasoning']}")
                
                if item.get("controversy_warning"):
                    st.markdown(f'<div class="friction-box"><b>⚠️ Friction Alert:</b> {item["controversy_warning"]}</div>', unsafe_allow_html=True)
                
                st.link_button("🌐 View on MyAnimeList", f"https://myanimelist.net/anime/{profile.get('id', '')}")

        # 3. PAGINATION BUTTON
        if len(st.session_state.active_pool) > st.session_state.current_index + 5:
            if st.button("🔄 Show Me 5 More", use_container_width=True):
                st.session_state.current_index += 5
                start = st.session_state.current_index
                chunk = st.session_state.active_pool[start : start + 5]
                
                with st.spinner("Processing next batch..."):
                    chunk_response = engine.process_next_chunk(
                        st.session_state.last_query, 
                        chunk, 
                        st.session_state.last_lens, 
                        st.session_state.sql_used
                    )
                    if chunk_response.get("success"):
                        st.session_state.current_results = chunk_response["data"]
                        st.rerun()
                    else:
                        st.error("Failed to process the next batch.")

# ==========================================
# TAB 2: DNA TRIANGULATION
# ==========================================
with tab_triangulate:
    st.subheader("Find Similar Shows")
    st.write("Enter up to three shows. The engine will extract their core thematic DNA and find matches.")
    
    with st.form("triangulation_form"):
        t1, t2, t3 = st.columns(3)
        ref_a = t1.text_input("Target 1 (Required)", placeholder="e.g., '86'")
        ref_b = t2.text_input("Target 2 (Optional)")
        ref_c = t3.text_input("Target 3 (Optional)")
        
        tri_submitted = st.form_submit_button("Synthesize DNA", type="primary", use_container_width=True)

    # Only require the first target to be filled out
    if tri_submitted and ref_a:
        # Filter out any empty text boxes
        active_targets = [target.strip() for target in [ref_a, ref_b, ref_c] if target.strip()]
        
        with st.spinner(f"Extracting shared DNA from {len(active_targets)} target(s) and cross-referencing vault..."):
            result = engine.execute_dna_triangulation(active_targets)
            
            if not result.get("success"):
                st.error(f"**Lookup Failed:** {result.get('error')}")
            else:
                st.markdown(f'<div class="dna-box"><b>🧬 DNA Synthesis Complete:</b><br>{result["intersection_summary"]}</div>', unsafe_allow_html=True)
                
                for item in result["data"]:
                    profile = item["profile"]
                    with st.container(border=True):
                        st.markdown(f"#### {profile['title']} ({profile.get('release_year', 'Unknown')})")
                        st.write(f"**Confidence:** {item.get('match_confidence', 'N/A')}% | **Quality:** {profile['quality_score']} | **Studio:** {profile['studio']}")
                        st.write(f"**Reasoning:** {item['ai_reasoning']}")
                        if item.get("controversy_warning"):
                            st.error(f"**Friction Alert:** {item['controversy_warning']}")
                        st.link_button("🌐 View on MyAnimeList", f"https://myanimelist.net/anime/{profile.get('id', '')}")

# ==========================================
# TAB 3: THE VAULT ARCHIVE
# ==========================================
with tab_archive:
    st.subheader("Anime Encyclopedia")
    st.write("Access the complete encyclopedia entry for a specific show. Resists typos and partial names.")
    
    search_target = st.text_input("Show Title:", placeholder="e.g., 'Evangelion' or 'Code Geas'")
    
    if search_target:
        matches = queries.resolve_show_title(search_target)
        
        if not matches:
            st.warning(f"Target '{search_target}' not found in the database.")
        else:
            if len(matches) > 1:
                st.info("Multiple shows detected. Please clarify your objective:")
                resolved_title = st.selectbox("Select specific show:", matches)
            else:
                resolved_title = matches[0]
            
            profiles = queries.fetch_fusion_profiles([resolved_title])
            
            if profiles:
                profile = profiles[0]
                st.markdown(f"## 📋 DEBRIEF: {profile['title'].upper()} ({profile.get('release_year', 'Unknown')})")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("MAL Score", profile['quality_score'])
                m2.metric("Audience Mood", f"{profile['audience_sentiment']:.2f}")
                m3.metric("Controversy Level", f"{profile['controversy_score']}/10")
                
                st.write(f"**Studio:** {profile['studio']}")
                st.info(f"**Audience Consensus:** {profile['audience_consensus']}")
                
                p_col, c_col = st.columns(2)
                with p_col:
                    st.success("✅ **THE PROS**")
                    for pro in profile.get('pros', []):
                        st.write(f"• {pro}")
                with c_col:
                    st.error("❌ **THE CONS**")
                    for con in profile.get('cons', []):
                        st.write(f"• {con}")
                
                st.write("") # Spacer
                st.link_button("🌐 View on MyAnimeList", f"https://myanimelist.net/anime/{profile.get('id', '')}", type="secondary")

# --- ATTRIBUTION FOOTER ---
st.markdown("""
<div class="mal-attribution">
    <b>Data & Community Attribution</b><br>
    The vast majority of the objective metadata, scores, and raw community reviews powering this intelligence engine are graciously provided by the community at <b><a href='https://myanimelist.net/' target='_blank' style='color:#64b5f6;'>MyAnimeList.net</a></b> and accessed via the open-source <b><a href='https://jikan.moe/' target='_blank' style='color:#64b5f6;'>Jikan API</a></b>.<br> 
    <i>Without their decades of curation, this semantic fusion project would not be possible. Please support their platform.</i>
</div>
""", unsafe_allow_html=True)