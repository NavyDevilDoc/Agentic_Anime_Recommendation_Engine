# CRITICAL_PATH.md — Anime Intelligence Vault

## Essential Files (Required for Production)

These files are on the critical path for the deployed Streamlit application on Hugging Face Spaces.

| File | Role |
|------|------|
| `app.py` | **Entry point.** Streamlit frontend — handles user queries, session state, pagination, and result rendering. Without it, there is no UI. |
| `analysis/recommendation_engine.py` | **Core orchestrator.** Routes queries through FAISS retrieval → fusion profile hydration → Gemini Phase 2 reranking. The central hub that connects all pipeline components. |
| `analysis/vector_store.py` | **Phase 1 retrieval.** Owns FAISS index loading, BGE-M3 embedding, query decomposition, multi-pool retrieval, cross-concept reranking, composite scoring, and Objective Rankings search. The entire candidate generation layer. |
| `analysis/queries.py` | **Database interface.** SQLite read-only access for fusion profile hydration, title resolution, Bayesian quality scoring, and Objective Rankings row fetching. Every recommendation must pass through here. |
| `analysis/prompts.py` | **LLM prompt templates.** Contains `FUSION_RERANKER_PROMPT` (Phase 2 scoring rubric, intent-aware directives) and `DNA_TRIANGULATION_PROMPT`. Without these, the Gemini reranker has no instructions. |
| `analysis/telemetry_logger.py` | **Observability.** Logs engine executions to GCP PostgreSQL via async background thread. Imported directly by `app.py` and `recommendation_engine.py`. Gracefully no-ops if GCP is unavailable, so the app still runs — but it's wired into the critical import chain. |
| `data/anime_intelligence_v2.db` | **Primary data store.** SQLite database containing ~6,000 anime rows with MAL metadata, sentiment scores, and Gemini-distilled consensus_json. All queries and profile hydration read from this. |
| `data/anime_vector_index.faiss` | **Vector index.** FAISS IndexFlatIP with 5,966 vectors (1024 dims). Required for all Intelligent Search queries — without it, Phase 1 retrieval fails. |
| `data/anime_vector_metadata.json` | **Index-to-DB bridge.** Maps FAISS integer IDs to MAL IDs and english_titles. Required to translate FAISS search results into database lookups. |
| `requirements.txt` | **Dependency manifest.** Defines all pip packages needed for the Docker build on HF Spaces. Missing packages = failed deployment. |
| `Dockerfile` | **Deployment config.** Defines the HF Spaces Docker container — installs dependencies, copies files, exposes port 7860. Without it, the Space cannot build. |
| `env_variables.env` | **API credentials.** Stores `GOOGLE_API_KEY` for Gemini API access. Without it, Phase 2 reranking and DNA triangulation fail. (On HF Spaces, secrets are injected via Streamlit secrets instead.) |

---

## Non-Essential Files

These files are not required for the deployed application to serve recommendations. They support ingestion, testing, diagnostics, documentation, or historical reference.

### Ingestion Pipeline (offline, run manually)

| File | Role |
|------|------|
| `vault_manager.py` | Orchestrates data ingestion — seasonal sweeps, targeted strikes, rolling windows. Triggers the ingestor and syncs the FAISS index afterward. Only run manually with 2FA confirmation; the deployed app never imports it. |
| `src/seasonal_ingestor_v2.py` | Bulk ingestion engine with self-healing loop, exponential backoff, and quarantine table. Called by `vault_manager.py` to fetch and process anime from MAL/Jikan. Not imported at runtime. |
| `src/mal_api_client.py` | MAL OAuth2 API client for fetching anime metadata (scores, studios, synopses). Used only during ingestion. |
| `src/jikan_client.py` | Jikan REST client for scraping user reviews from MAL. Used only during ingestion to feed the sentiment distiller. |
| `analysis/sentiment_distiller.py` | Gemini-powered review distillation — converts raw user reviews into structured consensus_json (thematic_vibe, pros, cons, controversy_score). Only runs during ingestion, never at query time. |
| `token_data.json` | Stores MAL OAuth2 refresh/access tokens for the ingestion pipeline. Not used by the deployed app. |

### Tests

| File | Role |
|------|------|
| `tests/test_sql_defenses.py` | Red-team test suite that fires SQL injection payloads against the (now-deprecated) SQL generation layer. Validates that read-only mode blocks mutation attempts. Development-only. |
| `tests/test_prompt_injection.py` | Live Gemini API test that validates prompt injection defenses in the recommendation prompt. Requires `GOOGLE_API_KEY`. Development-only. |

### Deprecated Modules

| File | Role |
|------|------|
| `analysis/queries_deprecated.py` | Original SQL generation logic from the pre-RAG architecture. Preserved for test compatibility (`test_sql_defenses.py` imports it). No longer used by the recommendation pipeline. |
| `analysis/prompts_deprecated.py` | Original lens-based prompt templates (5-lens system). Preserved for test compatibility (`test_prompt_injection.py` imports it). Superseded by the unified `prompts.py`. |

### Documentation

| File | Role |
|------|------|
| `PROGRESS.md` | Detailed modification log tracking every optimization (A–I), the migration, and architectural decisions. Developer reference only. |
| `MIGRATION_PLAN.md` | Documents the SQL-to-RAG migration plan and final architecture. Developer reference only. |
| `CLAUDE.md` | AI assistant instructions for working with the codebase. Not used by any code at runtime. |
| `README.md` | Project overview for the HF Spaces landing page / GitHub repo. Not used by any code at runtime. |
| `Claude_Checkpoint_Document.txt` | Session checkpoint notes. Not used by any code at runtime. |
| `CRITICAL_PATH.md` | This file. |

### MLOps / Diagnostics

| File | Role |
|------|------|
| `analysis/cost_predictor.py` | Estimates Gemini API burn rate using token heuristics from GCP telemetry data. Standalone CLI tool, not imported by the app. |

### Tools (standalone CLI utilities)

| File | Role |
|------|------|
| `tools/cli_recommender.py` | Terminal-based recommendation interface (imports `recommendation_engine`). Useful for testing without Streamlit. |
| `tools/view_show_report.py` | Prints a detailed report for a single anime by MAL ID (imports `queries`). Diagnostic utility. |
| `tools/vault_diagnostics.py` | Database health checks — missing fields, quarantine stats, coverage reports. Standalone. |
| `tools/build_readme.py` | Auto-generates README content from database stats. Standalone. |
| `tools/fill_english_titles.py` | Backfills missing `english_title` fields via Jikan API lookups. Standalone. |
| `tools/generate_season_list.py` | Generates season/year combinations for ingestion planning. Standalone. |
| `tools/normalize_telemetry.py` | Cleans and normalizes GCP telemetry records. Standalone. |
| `tools/post_mission_reconciliation.py` | Post-ingestion reconciliation — compares expected vs. actual DB entries. Standalone. |

### Archive (excluded from git)

| File | Role |
|------|------|
| `Archive/` (entire directory) | Historical scripts from earlier iterations of the project — old ingestors, migration scripts, test harnesses, backup JSON files. Excluded from git via `.gitignore`. No code imports from this directory. |
