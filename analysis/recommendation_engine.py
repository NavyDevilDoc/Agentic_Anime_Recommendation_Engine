"""
MODULE: analysis/recommendation_engine.py
FUNCTION: The central orchestrator. Routes natural language to the LLM (prompts.py), 
          fetches data from the Vault (queries.py), and returns structured intelligence.
          Now supports Stateful Chunking and Deterministic Objective Queries.
"""

import os
import sys
import random
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
    sql_query: str = Field(description="A valid SQLite SELECT statement returning 'english_title'.")

# --- THE ORCHESTRATOR ---

class RecommendationEngine:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"
        
        # Map UI Dropdown selections to our Prompt Lenses
        self.lenses = {
            "Baseline": prompts.BASELINE_LENS,
            "Deep Scan": prompts.DEEP_SCAN_LENS,
            "Friction Filter": prompts.FRICTION_FILTER_LENS,
            "Vanguard": prompts.VANGUARD_LENS,
            # We reuse the baseline prompt for SQL translation, but bypass the AI reranker later
            "Objective Rankings": prompts.BASELINE_LENS 
        }

    def _generate_sql(self, user_prompt, lens_name="Baseline"):
        """Phase 1: Translates natural language into a targeted SQL query."""
        system_instruction = self.lenses.get(lens_name, prompts.BASELINE_LENS)
        prompt = system_instruction.format(user_prompt=user_prompt)
        
        try:
            response = self.client.models.generate_content(
                model=self.model_id, 
                contents=prompt
            )
            raw_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
            return raw_sql
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                logger.error("API Rate Limit Exceeded during SQL Generation.")
                return "RATE_LIMIT_ERROR"
            logger.error(f"LLM SQL Generation Error: {e}")
            return None

    def _rerank_candidates(self, user_prompt, current_batch):
        """Phase 2: Evaluates a specific chunk of fusion profiles."""
        if not current_batch:
            return []

        candidates_block = ""
        for p in current_batch:
            candidates_block += f"Title: {p['title']}\n"
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

    # =====================================================================
    # NEW STATEFUL ARCHITECTURE
    # =====================================================================

    def fetch_vault_pool(self, user_prompt, lens_name="Baseline"):
        """STEP 1: Generates SQL, queries Vault, and prepares the master data pool."""
        sql_query = self._generate_sql(user_prompt, lens_name)
        if sql_query == "RATE_LIMIT_ERROR":
            return {"success": False, "error": "System cooling down. API rate limits are currently at maximum capacity. Please try again in 60 seconds."}
        if not sql_query:
            return {"success": False, "error": "Failed to generate search strategy."}

        candidate_titles = queries.execute_lens_query(sql_query)
        if not candidate_titles:
            return {"success": False, "error": "No classified intelligence matched that specific combination of traits."}

        fusion_profiles = queries.fetch_fusion_profiles(candidate_titles)

        # STATEFUL PREP: Shuffle for Vibe searches, maintain strict descending order for Objective.
        if lens_name == "Objective Rankings":
            # HARD OVERRIDE: Sort descending by quality score, ignoring whatever order the SQL returned
            pool = sorted(fusion_profiles, key=lambda x: x.get('quality_score', 0.0), reverse=True)
        else:
            pool = fusion_profiles[:30] 
            #random.shuffle(pool)        

        return {
            "success": True, 
            "pool": pool, 
            "sql_used": sql_query
        }

    def process_next_chunk(self, user_prompt, chunk, lens_name="Baseline", sql_query=""):
        """
        STEP 2: Takes a chunk (e.g., 5 shows) from the cached pool, 
        bypasses or runs the LLM reranker, and packages it for the UI.
        """
        if not chunk:
            return {"success": False, "error": "No more shows left in the pool."}

        if lens_name == "Objective Rankings":
            # DIRECT BYPASS: No AI reasoning needed. Raw deterministic data formatting.
            final_results = []
            for idx, p in enumerate(chunk):
                final_results.append({
                    "ai_reasoning": f"Objective Result #{idx + 1} from direct Vault query.",
                    "match_confidence": 100, # Factually matches the SQL parameters
                    "controversy_warning": None,
                    "profile": p
                })
        else:
            # VIBE MODE: Run the Reranker on this specific chunk
            top_picks = self._rerank_candidates(user_prompt, chunk)
            if top_picks == ["RATE_LIMIT_ERROR"]:
                 return {"success": False, "error": "System cooling down. API rate limits are currently at maximum capacity. Please try again in 60 seconds."}
            
            # HARD OVERRIDE: Force Python to sort the LLM's output by match_confidence DESC
            top_picks = sorted(top_picks, key=lambda x: x.match_confidence, reverse=True)
            
            final_results = []
            for pick in top_picks:
                profile_data = next((p for p in chunk if p['title'] == pick.title), None)
                if profile_data:
                    final_results.append({
                        "ai_reasoning": pick.reasoning,
                        "match_confidence": pick.match_confidence,
                        "controversy_warning": pick.controversy_driver,
                        "profile": profile_data
                    })

        # LOGGING
        if final_results:
            rec_titles = ", ".join([item['profile']['title'] for item in final_results])
            telemetry.log_engine_execution(
                prompt=user_prompt, 
                lens=lens_name, 
                sql=sql_query, 
                candidate_count=len(chunk), 
                success=True,
                error_msg="",
                recommendations=rec_titles
            )

        return {"success": True, "data": final_results, "diagnostics": {"sql_used": sql_query}}

    # =====================================================================
    # LEGACY WRAPPERS & TRIANGULATION
    # =====================================================================

    def execute_standard_pipeline(self, user_prompt, lens_name="Baseline"):
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

        candidate_titles = queries.execute_lens_query(plan.sql_query)
        candidate_titles = [t for t in candidate_titles if t not in resolved_titles]

        if not candidate_titles:
            return {"success": False, "error": "No matching targets found for this specific DNA blend."}

        fusion_profiles = queries.fetch_fusion_profiles(candidate_titles)
        chunk = fusion_profiles[:5] 
        top_picks = self._rerank_candidates(plan.intersection_summary, chunk)

        final_results = []
        for pick in top_picks:
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
            "diagnostics": {"sql_used": plan.sql_query}
        }