# Changelog

All notable changes to the Anime Intelligence Vault are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions use [Semantic Versioning](https://semver.org/).

For detailed implementation notes, diagnostics, and architectural analysis, see [PROGRESS.md](PROGRESS.md).

---

## [1.1.0] - 2026-03-13

### Added
- **Era filter** — Horizontal radio buttons (All Eras / Classic 2000–2009 / Modern 2010–2019 / Recent 2020+) in the FIND A SHOW tab, allowing users to scope searches by time period without typing temporal phrases
- Era selection routes through the existing hybrid SQL+FAISS filtered search path
- Query-level temporal terms (e.g., "after 2020") take precedence over the UI era selection

---

## [1.0.0] - 2026-03-13

First production release, deployed on Railway.

### Added
- **Semantic search engine** — Natural language "vibe" queries powered by FAISS vector retrieval (gemini-embedding-001, 3072-dim) and Gemini Phase 2 reranking with Pydantic structured output
- **Two discovery modes** — Intelligent Search (AI-powered semantic search) and Objective Rankings (direct database ordering with genre/temporal filters)
- **DNA Triangulation** — Enter 1–3 reference shows to find thematically similar anime via FAISS vector centroid search
- **Composite reranking** — 5-signal weighted blend (semantic similarity, Bayesian quality, popularity, input rank, recency) applied to all retrieval paths
- **Query decomposition** — Multi-concept queries (e.g., "mecha anime with romance") decomposed into independent FAISS searches with AND-semantics
- **Hybrid SQL+FAISS filtered search** — Temporal constraints ("after 2020"), demographics (shounen/seinen/josei), and genre keywords enforced as hard SQL filters before semantic ranking
- **Franchise-aware exclusion** — SHOWS LIKE THIS prevents franchise variants from appearing as recommendations
- **Confidence floors** — 50% for FIND A SHOW, 40% for SHOWS LIKE THIS; weak matches dropped before UI
- **Structured embedding documents** — Genre tags, vibe tags, synopsis, and consensus distilled into labeled sections for embedding quality
- **MAL genre augmentation** — Authoritative genre/theme/demographic tags from Jikan API backfilled for 99.93% of shows
- **Bayesian quality scores** — Raw MAL scores adjusted for vote count (prior weight: 5,000 votes)
- **Ingestion pipeline** — Seasonal sweep, targeted strike, and rolling window modes with self-healing loop, exponential backoff, and quarantine table
- **Incremental FAISS updates** — `update_index()` for adding/updating shows without full index rebuild
- **Input validation** — `max_chars` limits on all text inputs, HTML entity escaping on LLM-generated content
- **Pytest framework** — 24 tests covering SQL injection (5 attack vectors), read-only enforcement, input boundaries, FAISS index integrity, search quality, and DNA centroid retrieval
- **Telemetry** — Production logging to GCP PostgreSQL via async background thread
- **Docker deployment** — ~500 MB image, ~500 MB runtime RAM, auto-deploy from GitHub `main`

### Changed
- Embedding model migrated from BGE-M3 (local, 1024-dim) to Google gemini-embedding-001 (API, 3072-dim), removing `torch` and `transformers` dependencies
- Discovery modes consolidated from 5 lenses to 2 (Intelligent Search + Objective Rankings)
- DNA retrieval replaced LLM-generated text queries with vector centroid search (2.2x wider similarity spread)

### Removed
- SQL generation architecture (Phase 1 originally converted queries to raw SQL via Gemini)
- Local ML model dependencies (`torch`, `transformers`, `FlagEmbedding`)
- Deprecated lens modes (Hidden Gems, Crowd Pleasers, Polarizing/Edgy)
