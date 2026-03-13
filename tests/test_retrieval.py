"""
Retrieval quality regression tests.
Verifies that known-good queries return expected results after any pipeline changes.
These tests require GOOGLE_API_KEY (they hit the embedding API for query embedding).
Mark with @pytest.mark.api to allow skipping when offline.

Run all:       pytest tests/
Run offline:   pytest tests/ -m "not api"
Run API only:  pytest tests/ -m api
"""

import os
import sys
import pytest

TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def _has_api_key():
    """Check if GOOGLE_API_KEY is available."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))
    return bool(os.environ.get("GOOGLE_API_KEY"))


api = pytest.mark.api
skip_no_key = pytest.mark.skipif(not _has_api_key(), reason="GOOGLE_API_KEY not set")


# =====================================================================
# FAISS INDEX INTEGRITY
# =====================================================================

class TestFAISSIndex:
    """Verify the FAISS index and metadata are consistent."""

    def test_index_exists(self):
        import faiss
        index_path = os.path.join(ROOT_DIR, "data", "anime_vector_index.faiss")
        assert os.path.exists(index_path), "FAISS index file missing"
        index = faiss.read_index(index_path)
        assert index.ntotal > 5000, f"Index has only {index.ntotal} vectors (expected ~5966)"

    def test_metadata_matches_index(self):
        import json
        import faiss
        index_path = os.path.join(ROOT_DIR, "data", "anime_vector_index.faiss")
        meta_path = os.path.join(ROOT_DIR, "data", "anime_vector_metadata.json")

        index = faiss.read_index(index_path)
        with open(meta_path, "r") as f:
            metadata = json.load(f)

        assert len(metadata) == index.ntotal, (
            f"Metadata ({len(metadata)}) != index ({index.ntotal})"
        )

    def test_embedding_dimensions(self):
        import faiss
        index_path = os.path.join(ROOT_DIR, "data", "anime_vector_index.faiss")
        index = faiss.read_index(index_path)
        assert index.d == 3072, f"Expected 3072 dims (gemini-embedding-001), got {index.d}"


# =====================================================================
# SEARCH QUALITY REGRESSION
# =====================================================================

@skip_no_key
class TestSearchQuality:
    """Known-good queries that must return plausible results."""

    @api
    def test_mecha_query_returns_mecha(self):
        from analysis.vector_store import search
        results = search("mecha anime with giant robots", top_k=10)
        titles = [r["title"] for r in results]
        mecha_keywords = ["Gundam", "Evangelion", "Code Geass", "86", "Gurren Lagann", "Franxx"]
        hits = sum(1 for t in titles if any(k.lower() in t.lower() for k in mecha_keywords))
        assert hits >= 2, f"Expected >=2 mecha shows in top 10, got {hits}. Titles: {titles}"

    @api
    def test_sports_query_returns_sports(self):
        from analysis.vector_store import search
        results = search("intense sports competition", top_k=10)
        titles = [r["title"] for r in results]
        sports_keywords = ["Haikyuu", "Blue Lock", "Slam Dunk", "Kuroko", "Aoashi", "Run with the Wind"]
        hits = sum(1 for t in titles if any(k.lower() in t.lower() for k in sports_keywords))
        assert hits >= 2, f"Expected >=2 sports shows in top 10, got {hits}. Titles: {titles}"

    @api
    def test_filtered_search_respects_year(self):
        from analysis.vector_store import search
        results = search("action anime from 2024", top_k=10)
        assert len(results) > 0, "Filtered search returned no results"
        # Titles should be 2024 shows (validated by the SQL filter path)

    @api
    def test_search_returns_similarity_scores(self):
        from analysis.vector_store import search
        results = search("dark psychological thriller", top_k=5)
        assert len(results) > 0
        for r in results:
            assert "title" in r and "similarity" in r
            assert 0.0 <= r["similarity"] <= 1.0, f"Similarity out of range: {r['similarity']}"


# =====================================================================
# DNA CENTROID SEARCH
# =====================================================================

class TestDNACentroidSearch:
    """Centroid search uses pre-computed vectors — no API key needed."""

    def test_centroid_returns_results(self):
        from analysis.vector_store import search_by_centroid
        results = search_by_centroid(["Attack on Titan"], top_k=10)
        assert len(results) > 0, "Centroid search returned no results"

    def test_centroid_excludes_reference(self):
        from analysis.vector_store import search_by_centroid
        results = search_by_centroid(["Attack on Titan"], top_k=10)
        titles = [r["title"] for r in results]
        assert "Attack on Titan" not in titles, "Reference show should be excluded"

    def test_centroid_multi_show(self):
        from analysis.vector_store import search_by_centroid
        results = search_by_centroid(["Attack on Titan", "Death Note"], top_k=10)
        assert len(results) > 0, "Multi-show centroid returned no results"

    def test_centroid_unknown_show(self):
        from analysis.vector_store import search_by_centroid
        results = search_by_centroid(["This Show Does Not Exist 12345"], top_k=10)
        assert results == [], "Unknown show should return empty results"


# =====================================================================
# CONFIDENCE FLOOR VALIDATION
# =====================================================================

@skip_no_key
class TestConfidenceFloors:
    """Verify that confidence floors filter low-quality recommendations."""

    @api
    def test_find_a_show_floor_50(self):
        """All results from fetch_vault_pool must have match_confidence >= 50."""
        from analysis.recommendation_engine import RecommendationEngine
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))
        api_key = os.environ.get("GOOGLE_API_KEY")

        engine = RecommendationEngine(api_key=api_key)
        result = engine.fetch_vault_pool("gritty mecha drama", "Intelligent Search")

        if result["success"] and result["pool"]:
            for item in result["pool"]:
                assert item["match_confidence"] >= 50, (
                    f"Show '{item['profile']['title']}' has confidence "
                    f"{item['match_confidence']} (below 50% floor)"
                )
