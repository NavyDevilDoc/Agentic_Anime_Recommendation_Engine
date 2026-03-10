"""
MODULE: analysis/recommendation_engine.py
FUNCTION: The central orchestrator. Routes natural language to the LLM (prompts.py), 
          fetches data from the Vault (queries.py), and returns structured intelligence.
          Now supports Stateful Chunking and Deterministic Objective Queries.
"""

import os
import sys
import logging
from google import genai
from pydantic import BaseModel, Field

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import analysis.prompts as prompts
import analysis.queries as queries
import analysis.vector_store as vector_store
import analysis.telemetry_logger as telemetry

logger = logging.getLogger(__name__)

# --- PYDANTIC SCHEMAS FOR STRUCTURED UI OUTPUT ---

class RerankedShow(BaseModel):
    title: str = Field(description="The exact english_title of the selected show.")
    match_confidence: int = Field(description="A score from 0 to 100 indicating how well the show matches the requested vibe or DNA.")
    reasoning: str = Field(description="A 1-sentence explanation of why the objective plot and subjective consensus match the user's intent.")
    controversy_driver: str | None = Field(default=None, description="Include ONLY if Controversy Score >= 6. Explain the division.")

class TriangulationPlan(BaseModel):
    intersection_summary: str = Field(description="1-2 sentence analysis of the shared DNA.")
    search_query: str = Field(description="A natural language search phrase capturing the shared thematic DNA, suitable for semantic vector search.")

# --- THE ORCHESTRATOR ---

class RecommendationEngine:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"

    def _rerank_candidates(self, user_prompt, current_batch):
        """Phase 2: Evaluates a specific chunk of fusion profiles."""
        if not current_batch:
            return []

        candidates_block = ""
        for p in current_batch:
            candidates_block += f"Title: {p['title']}\n"
            candidates_block += f"Semantic Match: {p.get('semantic_similarity', 0.0):.2f}\n"
            candidates_block += f"Scored By: {p.get('scored_by', 0):,} users\n"
            candidates_block += f"Synopsis: {p['synopsis']}\n"
            candidates_block += f"Audience Consensus: {p['audience_consensus']}\n"
            candidates_block += f"Controversy Score: {p['controversy_score']}/10\n"
            candidates_block += "-"*40 + "\n"

        # Dynamically overwrite any "Top 3" language in the base prompt to match our chunk size
        raw_prompt = prompts.FUSION_RERANKER_PROMPT.replace("Top 3", "all").replace("top 3", "all")
        
        prompt = raw_prompt.format(
            user_prompt=user_prompt, 
            candidates_block=candidates_block
        )
        # Force strict compliance on chunk size
        prompt += f"\n\nCRITICAL: You MUST evaluate and return exactly {len(current_batch)} shows from the list above. Do not drop any shows. Assign a 'match_confidence' score (0-100) to each and return them in ranked order."

        try:
            response = self.client.models.generate_content(
                model=self.model_id, 
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": list[RerankedShow] 
                }
            )
            return response.parsed if response.parsed else []
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                logger.error("API Rate Limit Exceeded during Reranking.")
                return ["RATE_LIMIT_ERROR"]
            logger.error(f"LLM Reranking Error: {e}")
            return []

    def _rerank_dna_candidates(self, intersection_summary, reference_titles, current_batch):
        """Phase 2 for DNA Triangulation: scores candidates against thematic DNA, not a freeform query."""
        if not current_batch:
            return []

        candidates_block = ""
        for p in current_batch:
            candidates_block += f"Title: {p['title']}\n"
            candidates_block += f"Semantic Match: {p.get('semantic_similarity', 0.0):.2f}\n"
            candidates_block += f"Scored By: {p.get('scored_by', 0):,} users\n"
            candidates_block += f"Synopsis: {p['synopsis']}\n"
            candidates_block += f"Audience Consensus: {p['audience_consensus']}\n"
            candidates_block += f"Controversy Score: {p['controversy_score']}/10\n"
            candidates_block += "-"*40 + "\n"

        prompt = prompts.DNA_RERANKER_PROMPT.format(
            reference_titles=", ".join(reference_titles),
            intersection_summary=intersection_summary,
            candidates_block=candidates_block,
        )
        prompt += f"\n\nEvaluate all {len(current_batch)} shows above. Assign a 'match_confidence' score (0-100) to each and return them in ranked order. If a show has no meaningful thematic connection, assign it a score below 30 — it will be filtered out downstream."

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": list[RerankedShow]
                }
            )
            return response.parsed if response.parsed else []
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                logger.error("API Rate Limit Exceeded during DNA Reranking.")
                return ["RATE_LIMIT_ERROR"]
            logger.error(f"DNA Reranking Error: {e}")
            return []

    # =====================================================================
    # NEW STATEFUL ARCHITECTURE (AOT GLOBAL SCORING)
    # =====================================================================

    def fetch_vault_pool(self, user_prompt, lens_name="Intelligent Search"):
        """STEP 1: Retrieves candidates via FAISS vector search or Objective Rankings, then PRE-SCORES."""

        if lens_name == "Objective Rankings":
            search_results = vector_store.objective_rankings_search(user_prompt, top_k=50)
        else:
            search_results = vector_store.search(user_prompt, top_k=50)

        if not search_results:
            return {"success": False, "error": "No classified intelligence matched that specific combination of traits."}

        # Build similarity lookup from search results
        sim_lookup = {r["title"]: r["similarity"] for r in search_results}
        candidate_titles = [r["title"] for r in search_results]

        fusion_profiles = queries.fetch_fusion_profiles(candidate_titles)

        # Inject similarity scores into fusion profiles
        for p in fusion_profiles:
            p["semantic_similarity"] = sim_lookup.get(p["title"], 0.0)

        if lens_name == "Objective Rankings":
            # Preserve the SQL ordering (already sorted by mal_score DESC)
            title_order = {t: i for i, t in enumerate(candidate_titles)}
            pool = sorted(fusion_profiles, key=lambda x: title_order.get(x['title'], 999))
            scored_pool = []
            for idx, p in enumerate(pool[:30]):
                scored_pool.append({
                    "ai_reasoning": f"Objective Result #{idx + 1} from direct Vault query.",
                    "match_confidence": 100,
                    "controversy_warning": None,
                    "profile": p
                })
        else:
            pool = fusion_profiles[:15]
            top_picks = self._rerank_candidates(user_prompt, pool)

            if top_picks == ["RATE_LIMIT_ERROR"]:
                 return {"success": False, "error": "System cooling down. API rate limits are currently at maximum capacity. Please try again in 60 seconds."}

            top_picks = sorted(top_picks, key=lambda x: x.match_confidence, reverse=True)

            scored_pool = []
            for pick in top_picks:
                if pick.match_confidence < 50:
                    continue
                profile_data = next((p for p in pool if p['title'] == pick.title), None)
                if profile_data:
                    scored_pool.append({
                        "ai_reasoning": pick.reasoning,
                        "match_confidence": pick.match_confidence,
                        "controversy_warning": pick.controversy_driver,
                        "profile": profile_data
                    })

            if scored_pool:
                rec_titles = ", ".join([item['profile']['title'] for item in scored_pool[:5]])
                telemetry.log_engine_execution(
                    prompt=user_prompt,
                    lens=lens_name,
                    sql="RAG:FAISS",
                    candidate_count=len(pool),
                    success=True,
                    error_msg="",
                    recommendations=rec_titles
                )

        return {
            "success": True,
            "pool": scored_pool,
            "sql_used": "RAG:FAISS"
        }

    def process_next_chunk(self, user_prompt, chunk, lens_name="Intelligent Search", sql_query=""):
        """
        STEP 2: The chunk is now ALREADY SCORED. Just return it to the UI instantly.
        """
        if not chunk:
            return {"success": False, "error": "No more shows left in the pool."}

        # Bypassing the LLM entirely. We just hand the pre-scored dictionary directly to Streamlit!
        return {"success": True, "data": chunk, "diagnostics": {"sql_used": sql_query}}

    # =====================================================================
    # LEGACY WRAPPERS & TRIANGULATION
    # =====================================================================

    def execute_standard_pipeline(self, user_prompt, lens_name="Intelligent Search"):
        """Legacy wrapper for CLI tests or single-shot runs."""
        pool_response = self.fetch_vault_pool(user_prompt, lens_name)
        if not pool_response["success"]:
            # Make sure we log failures
            telemetry.log_engine_execution(user_prompt, lens_name, "FAILED/NO_DATA", 0, False, pool_response.get("error", ""))
            return pool_response

        pool = pool_response["pool"]
        sql_query = pool_response["sql_used"]
        chunk = pool[:5] # Default to top 5 for a single run

        return self.process_next_chunk(user_prompt, chunk, lens_name, sql_query)

    def execute_dna_triangulation(self, titles_list):
        """The Streamlit Endpoint for the DNA Triangulation Matrix. Now accepts any number of targets."""
        if not titles_list:
            return {"success": False, "error": "DNA Triangulation requires at least 1 target show."}

        resolved_titles = []
        for t in titles_list:
            matches = queries.resolve_show_title(t)
            if matches:
                resolved_titles.append(matches[0]) 
            else:
                return {"success": False, "error": f"Target MIA: Could not identify '{t}' in the vault."}

        reference_profiles = queries.fetch_fusion_profiles(resolved_titles)
        
        trinity_data = ""
        for p in reference_profiles:
            trinity_data += f"SHOW: {p['title']}\n"
            trinity_data += f"SYNOPSIS: {p['synopsis']}\n"
            trinity_data += f"VIBE & CONSENSUS: {p['audience_consensus']}\n\n"

        # Adapt prompt instructions based on the number of targets
        target_count = len(resolved_titles)
        task_directive = f"Analyze the shared thematic DNA between these {target_count} shows." if target_count > 1 else "Analyze the core thematic DNA of this show."

        prompt = prompts.TRIANGULATION_PROMPT.format(
            trinity_data=trinity_data,
            excluded_titles=", ".join(resolved_titles)
        )
        prompt += f"\n\n{task_directive}"

        try:
            response = self.client.models.generate_content(
                model=self.model_id, 
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": TriangulationPlan
                }
            )
            plan = response.parsed
            if not plan: raise ValueError("Failed to parse JSON")
        except Exception as e:
            return {"success": False, "error": f"DNA Synthesis Failed: {e}"}

        # Vector centroid retrieval: use the reference shows' own FAISS
        # vectors instead of embedding a lossy LLM-generated text query.
        # Franchise exclusion is handled inside search_by_centroid().
        search_results = vector_store.search_by_centroid(resolved_titles, top_k=50)

        if not search_results:
            return {"success": False, "error": "No matching targets found for this specific DNA blend."}

        sim_lookup = {r["title"]: r["similarity"] for r in search_results}
        candidate_titles = [r["title"] for r in search_results]

        fusion_profiles = queries.fetch_fusion_profiles(candidate_titles)
        for p in fusion_profiles:
            p["semantic_similarity"] = sim_lookup.get(p["title"], 0.0)
        chunk = fusion_profiles[:15]
        top_picks = self._rerank_dna_candidates(plan.intersection_summary, resolved_titles, chunk)

        # Confidence floor: drop results below 40% to prevent embarrassing
        # low-confidence recommendations from reaching the UI.
        final_results = []
        for pick in top_picks:
            if pick.match_confidence < 40:
                continue
            profile_data = next((p for p in chunk if p['title'] == pick.title), None)
            if profile_data:
                final_results.append({
                    "ai_reasoning": pick.reasoning,
                    "match_confidence": pick.match_confidence,
                    "controversy_warning": pick.controversy_driver,
                    "profile": profile_data
                })

        return {
            "success": True,
            "intersection_summary": plan.intersection_summary,
            "data": final_results,
            "diagnostics": {"sql_used": "RAG:FAISS"}
        }