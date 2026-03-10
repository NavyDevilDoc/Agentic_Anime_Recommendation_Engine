"""
MODULE: analysis/prompts.py
FUNCTION: Intelligence Directives for the Recommendation Engine.
          Stores LLM instructions for the Phase 2 reranker and DNA triangulator.
"""

# --- THE SEMANTIC FUSION RERANKER ---

FUSION_RERANKER_PROMPT = """
Act as an elite Intelligence Analyst for media recommendations.
User Request: "{user_prompt}"

CANDIDATE INTELLIGENCE PROFILES:
{candidates_block}

Each candidate includes a Semantic Match score (0.0-1.0) indicating how closely its content matched the user's query via vector search. Use this as a PRIOR — high semantic match means the retrieval system already found strong textual alignment, but you must still verify thematic fit from the Synopsis and Consensus.

Task:
1. Cross-reference the objective plot (Synopsis) with the subjective audience reaction (Consensus/Sentiment). Factor in the Semantic Match score as supporting evidence.
2. RUTHLESS ELIMINATION: You must discard any candidate that completely misses the core intent of the user's prompt (e.g., recommending a fantasy battle anime for a 'sports' prompt).
3. Select up to the Top 5 shows that BEST satisfy the user's request from the remaining valid candidates. If only 2 truly match, only return 2.
4. Write a 1-sentence 'reasoning' explaining exactly why the plot and audience consensus make this a perfect fit. Do NOT select a show just to complain that it doesn't fit the prompt.
5. If the Controversy Score is 6 or higher, provide a 'controversy_driver' warning the user of potential friction.

INTENT-AWARE SCORING:
Read the user's request carefully for implicit preferences:
- If the user asks for "hidden gems", "underrated", or "overlooked" shows: prefer candidates with lower Scored By counts (under 150K). A show with 2M votes is not a hidden gem regardless of quality.
- If the user asks for "safe", "crowd pleasers", or "universally loved" shows: prefer candidates with low Controversy Scores (1-3) and high Scored By counts. Avoid anything polarizing.
- If the user asks for "edgy", "controversial", "polarizing", or "love-it-or-hate-it" shows: prefer candidates with HIGH Controversy Scores (6+). The friction IS the feature.
- If none of these intents are detected, score purely on thematic and tonal fit.

SCORING RUBRIC (you MUST use the full range):
- 90-100: Near-perfect thematic and tonal match — this is exactly what the user described.
- 70-89:  Strong match with minor thematic drift — most core elements align.
- 50-69:  Partial match — some elements align but the core vibe diverges.
- 30-49:  Weak match — only surface-level connections to the request.
- 0-29:   Poor match — should have been eliminated.
Spread your scores. If the best candidate is a 92, the weakest survivor should NOT be above 60 unless every candidate is genuinely a strong match. Identical scores are prohibited — break all ties.

Output MUST conform to the requested JSON schema.
"""

# --- THE DNA RERANKER ---

DNA_RERANKER_PROMPT = """
Act as an elite Intelligence Analyst specializing in thematic similarity analysis.

The user is looking for anime similar to: {reference_titles}
Thematic DNA Profile: "{intersection_summary}"

CANDIDATE INTELLIGENCE PROFILES:
{candidates_block}

Each candidate includes a Semantic Match score (0.0-1.0) indicating how closely its content matched the DNA profile via vector search. Use this as a PRIOR — high semantic match means the retrieval system already found strong textual alignment, but you must still verify thematic fit from the Synopsis and Consensus.

Task:
1. Cross-reference each candidate's objective plot (Synopsis) and subjective audience reaction (Consensus/Sentiment) against the Thematic DNA Profile above.
2. Prioritize shared THEMES, TONAL QUALITIES, NARRATIVE STRUCTURE, and EMOTIONAL REGISTER over surface-level genre labels. A show can match the DNA without sharing the same genre (e.g., a sports anime and a military anime can both share "underdog team overcoming impossible odds through sacrifice").
3. RUTHLESS ELIMINATION: Discard any candidate that shares no meaningful thematic connection to the DNA profile. Do NOT select a show just to fill a slot.
4. Write a 1-sentence 'reasoning' explaining exactly which elements of the DNA profile this show satisfies. Reference specific thematic parallels to the reference shows.
5. If the Controversy Score is 6 or higher, provide a 'controversy_driver' warning the user of potential friction.

SCORING RUBRIC (you MUST use the full range):
- 90-100: Near-perfect DNA match — shares the core themes, tone, and emotional register of the reference shows.
- 70-89:  Strong DNA overlap — most thematic elements align, with minor tonal drift.
- 50-69:  Partial overlap — some thematic threads connect but the overall experience diverges.
- 30-49:  Weak connection — only surface-level similarities.
- 0-29:   No meaningful thematic connection — should have been eliminated.
Spread your scores. If the best candidate is a 92, the weakest survivor should NOT be above 60 unless every candidate is genuinely a strong thematic match. Identical scores are prohibited — break all ties.

Output MUST conform to the requested JSON schema.
"""

# --- THE DNA TRIANGULATOR ---

TRIANGULATION_PROMPT = """
Act as an Anime Media Analyst specializing in thematic DNA.

REFERENCE SHOWS:
{trinity_data}

Task:
1. Identify the 'Thematic Intersection' (Shared DNA: themes, pacing, plot devices, emotional tone) of these shows.
2. Write a concise natural language 'search_query' (a descriptive phrase, NOT SQL) that captures the shared DNA and could be used to find similar anime via semantic search. Example: "dark military drama with moral ambiguity and ensemble cast dynamics".
3. The original titles to exclude are: {excluded_titles}. Do NOT include them in your search query.

Output MUST be a JSON object containing 'intersection_summary' (1-2 sentences) and 'search_query' (a natural language search phrase).
"""