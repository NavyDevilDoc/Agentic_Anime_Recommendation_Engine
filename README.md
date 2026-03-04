---
license: apache-2.0
title: Anime_Recommendation_engine
sdk: docker
emoji: 📊
colorFrom: blue
colorTo: indigo
short_description: agentic anime intelligence app
---
    
# Anime Intelligence Vault

An end-to-end, production-grade agentic semantic search engine and intelligence 
pipeline. This system leverages multi-step LLM reasoning to autonomously ingest, 
distill, and query community sentiment for 6,000 anime titles, allowing users 
to discover media using natural language "vibe" queries and thematic DNA triangulation.


## System Architecture

This project is built on a resilient, multi-stage agentic architecture designed to handle rate-limiting, network instability, and temporal data drift.

1. **Data Acquisition (The Self-Healing Ingestor):** Interfaces with the MyAnimeList and Jikan APIs. 
It utilizes exponential backoff, automated quarantine logs, and dynamic routing to bypass rate 
limits and ensure absolute data density during multi-year sweeps.

2. **Semantic Fusion Engine (NLP Distillation):** Leverages Gemini 2.5 Flash to synthesize thousands 
of raw, unstructured community reviews into standardized JSON intelligence packets containing extracted 
Pros, Cons, Sentiment Scores, and Controversy Metrics.

3. **The Tactical Router (Streamlit UI):** A responsive, synchronous frontend that translates natural 
language directives into optimized SQL queries, routing them through specific filtering lenses (e.g., *Hidden Gems*, *Crowd Pleasers*).

4. **MLOps Telemetry:** A silent background observer logs all prompts, generated SQL, and token 
heuristics to an isolated SQLite database, allowing for offline cost-prediction and burn-rate forecasting.

5. **Targeted Drift Mitigation:** Mitigates temporal sentiment drift by bypassing 
bulk seasonal sweeps to surgically update the consensus profiles of individual shows based on 
late-stage review velocity.

6. **Memory Caching:** Implements intelligent state caching to serve identical queries instantly, eliminating 
out redundant API costs and maximizing operational efficiency.


## Key Features

* **Vibe Search:** Ditch rigid genre tags. Search for abstract concepts like *"gritty military 
drama with mecha"* or *"cozy slice-of-life set in winter."*

* **DNA Triangulation:** Input up to three reference shows. The engine extracts their shared thematic 
DNA and queries the vault for algorithmic intersections.

* **Encyclopedia Lookup** Enter a show that aired from between 2000 and 2025 for its encyclopedia card, which
contains its MyAnimeList score, distilled audience mood, viewer controversy rating, audience consensus, pros,
and cons. 

* **MyAnimeList Link** Every show comes with a link to the show's corresponding MyAnimeList page. This was made
possible thanks to their hard work and dedication to the anime community!


## Repository Structure

The codebase is organized by domain and function to ensure maintainability:

* `/src/`: Foundation modules. API clients (MAL, Jikan) and the automated seasonal ingestor.
* `/analysis/`: The core AI layer. Houses the recommendation engine, NLP sentiment distiller, SQL query generators, and MLOps cost predictors.
* `/tools/`: Standalone utility scripts for database diagnostics, targeted vault updates, and local telemetry reconciliation.
* `/tests/`: Automated security validation, including SQL injection defense and prompt boundary testing.
* `/data/`: (Local Only) Contains the SQLite databases (`anime_intelligence_v2.db` and `anime_telemetry.db`). 


## Tech Stack

* **Language:** Python 3.12
* **Database:** SQLite3
* **AI/NLP:** Google Gemini 2.5 Flash, VADER Sentiment Analysis
* **Frontend:** Streamlit
* **External APIs:** MyAnimeList (MAL) API, Jikan REST API


## Local Setup

1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Create an `env_variables.env` file in the root directory and add your Google AI Studio API key: `GOOGLE_API_KEY="your_key_here"`
4. Run `python vault_manager.py` to initialize the empty database and begin ingesting seasonal data.
5. Launch the frontend: `streamlit run app.py`