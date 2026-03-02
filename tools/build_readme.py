"""
MODULE: tools/build_readme.py
FUNCTION: Generates the repository README.md file to ensure standardized documentation.
"""
import os

# --- PATH ANCHORING ---
TOOLS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TOOLS_DIR, '..'))
README_PATH = os.path.join(ROOT_DIR, "README.md")

def generate_readme():
    markdown_content = """# Anime Intelligence Vault

An end-to-end, production-grade agentic semantic search engine and intelligence 
pipeline. This system leverages multi-step LLM reasoning to autonomously ingest, 
distill, and query community sentiment for over 6,000 anime titles, allowing users 
to discover media using natural language "vibe" queries and thematic DNA triangulation.

## 🏗️ System Architecture

This project is built on a resilient, multi-stage architecture designed to handle rate-limiting, network instability, and temporal data drift.

1. **Data Acquisition (The Self-Healing Ingestor):** Interfaces with the MyAnimeList and Jikan APIs. 
It utilizes exponential backoff, automated quarantine logs (CASREP), and dynamic routing to bypass rate 
limits and ensure absolute data density during multi-year sweeps.

2. **Semantic Fusion Engine (NLP Distillation):** Leverages Gemini 2.5 Flash to synthesize thousands 
of raw, unstructured community reviews into standardized JSON intelligence packets containing extracted 
Pros, Cons, Sentiment Scores, and Controversy Metrics.

3. **The Tactical Router (Streamlit UI):** A responsive, synchronous frontend that translates natural 
language directives into optimized SQL queries, routing them through specific filtering lenses (e.g., *Hidden Gems*, *Crowd Pleasers*).

4. **MLOps Telemetry:** A silent background observer logs all prompts, generated SQL, and token 
heuristics to an isolated SQLite database, allowing for offline cost-prediction and burn-rate forecasting.

## 🚀 Key Features

* **Vibe Search:** Ditch rigid genre tags. Search for abstract concepts like *"gritty military 
drama with mecha"* or *"cozy slice-of-life set in winter."*

* **DNA Triangulation:** Input three reference shows. The engine extracts their shared thematic 
DNA and queries the vault for exact algorithmic intersections.

* **Targeted Drift Mitigation (Sniper Mode):** Mitigates temporal sentiment drift by bypassing 
bulk seasonal sweeps to surgically update the consensus profiles of individual shows based on 
late-stage review velocity.

* **Memory Caching:** Implements intelligent state caching to serve identical queries instantly, zeroing 
out redundant API costs and maximizing operational efficiency.

## 📂 Repository Structure

The codebase is organized by domain and function to ensure maintainability:

* `/src/`: Foundation modules. API clients (MAL, Jikan) and the automated seasonal ingestor.
* `/analysis/`: The core AI layer. Houses the recommendation engine, NLP sentiment distiller, SQL query generators, and MLOps cost predictors.
* `/tools/`: Standalone utility scripts for database diagnostics, targeted vault updates, and local telemetry reconciliation.
* `/tests/`: Automated security validation, including SQL injection defense and prompt boundary testing.
* `/data/`: (Local Only) Contains the SQLite databases (`anime_intelligence_v2.db` and `anime_telemetry.db`). 

*Note: For security and footprint management, `.env` files and the `.db` storage volumes are excluded from version control.*

## 🛠️ Tech Stack

* **Language:** Python 3.12
* **Database:** SQLite3
* **AI/NLP:** Google Gemini 2.5 Flash, VADER Sentiment Analysis
* **Frontend:** Streamlit
* **External APIs:** MyAnimeList (MAL) API, Jikan REST API

## ⚙️ Local Setup

1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Create an `env_variables.env` file in the root directory and add your Google AI Studio API key: `GOOGLE_API_KEY="your_key_here"`
4. Run `python vault_manager.py` to initialize the empty database and begin ingesting seasonal data.
5. Launch the frontend: `streamlit run app.py`

---
*Data attribution: Objective metadata and raw community reviews are sourced from MyAnimeList.net via the open-source Jikan API.*
"""

    try:
        with open(README_PATH, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"✅ SUCCESS: README.md generated successfully at {README_PATH}")
    except Exception as e:
        print(f"❌ ERROR: Failed to write README.md. Details: {e}")

if __name__ == "__main__":
    generate_readme()