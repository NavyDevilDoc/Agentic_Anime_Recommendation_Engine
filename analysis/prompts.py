"""
MODULE: analysis/prompts.py
FUNCTION: Intelligence Directives for the Recommendation Engine.
          Stores all LLM instructions, SQL rules, and operational lenses.
"""

# --- BASE SQL GENERATION RULES ---
# This block is injected into every SQL-generating prompt to enforce strict boundaries.
BASE_SQL_RULES = """
CRITICAL SQL RULES & SCHEMA:
Table Name: anime_info
Available Columns: 
- english_title (TEXT)
- mal_score (REAL: 1.0 to 10.0)
- scored_by (INTEGER: Number of users who rated it)
- avg_sentiment (REAL: -1.0 to 1.0, AI-calculated audience mood)
- studio (TEXT)
- mal_synopsis (TEXT: Objective plot summary)
- consensus_json (TEXT: Subjective AI analysis containing pros, cons, vibe, and summary)
- release_year (INTEGER)

Execution Constraints:
1. Return ONLY the raw SQLite SELECT statement. No markdown, no backticks, no explanation.
2. Select ONLY the 'english_title' column (e.g., SELECT english_title FROM anime_info...).
3. Always include a LIMIT 50 clause.
4. For thematic searches, use LIKE with wildcards on 'consensus_json' and 'mal_synopsis' (e.g., consensus_json LIKE '%dark%').
5. Escape single quotes in search strings (e.g., 'Protagonist''s').
6. ELASTIC SEARCHING: When searching for themes, use OR to include synonyms (e.g., for 'gritty', search '%gritty%' OR '%dark%' OR '%mature%'). Do not rigidly require every user keyword to be present.
"""

# --- THE TARGETING LENSES (SQL GENERATORS) ---

BASELINE_LENS = f"""
{BASE_SQL_RULES}
OPERATIONAL MODE: STANDARD VIBE MATCH
User Intent: "{{user_prompt}}"

Task: Write a SQL query to find shows that best match the user's requested vibe, genre, or plot.
Strategy:
- Search 'genres', 'mal_synopsis', and 'consensus_json' for keywords related to the intent.
- Order the results by 'mal_score' DESC to prioritize quality.
"""

DEEP_SCAN_LENS = f"""
{BASE_SQL_RULES}
OPERATIONAL MODE: DEEP SCAN (HIDDEN GEMS)
User Intent: "{{user_prompt}}"

Task: Write a SQL query to find highly-loved shows that flew under the mainstream radar, matching the user intent.
Strategy:
- Filter for moderate popularity: 'scored_by' BETWEEN 10000 AND 150000.
- Filter for extremely high audience emotional response: 'avg_sentiment' > 0.65.
- Do NOT strictly require a high mal_score.
- Order by 'avg_sentiment' DESC.
"""

FRICTION_FILTER_LENS = f"""
{BASE_SQL_RULES}
OPERATIONAL MODE: FRICTION FILTER (GRIEVANCE CORRECTION)
User Intent: "{{user_prompt}}"

Task: Write a SQL query that explicitly avoids negative traits mentioned by the user while finding their desired vibe.
Strategy:
- Use 'NOT LIKE' heavily on 'consensus_json' to filter out the user's complaints (e.g., if they hate slow pacing, ensure consensus_json NOT LIKE '%slow pace%').
- Search 'mal_synopsis' for their desired positive traits.
- Order by 'mal_score' DESC.
"""

VANGUARD_LENS = f"""
{BASE_SQL_RULES}
OPERATIONAL MODE: THE VANGUARD (HIGH RISK / POLARIZING)
User Intent: "{{user_prompt}}"

Task: Write a SQL query to find avant-garde, controversial, or highly polarizing shows matching the intent.
Strategy:
- Require a high friction profile: 'consensus_json' LIKE '%"controversy_score": 6%' OR '%"controversy_score": 7%' OR '%"controversy_score": 8%' OR '%"controversy_score": 9%'.
- Order by 'avg_sentiment' ASC (prioritizing shows that actively divided or upset audiences).
"""

# --- THE SEMANTIC FUSION RERANKER ---

FUSION_RERANKER_PROMPT = """
Act as an elite Intelligence Analyst for media recommendations.
User Request: "{user_prompt}"

CANDIDATE INTELLIGENCE PROFILES:
{candidates_block}

Task:
1. Cross-reference the objective plot (Synopsis) with the subjective audience reaction (Consensus/Sentiment).
2. Select the Top 3 shows that BEST satisfy the user's request based on this fused data.
3. Write a 1-sentence 'reasoning' explaining exactly why the plot and audience consensus make this a perfect fit.
4. If the Controversy Score is 6 or higher, provide a 'controversy_driver' warning the user of potential friction.

Output MUST conform to the requested JSON schema.
"""

# --- THE DNA TRIANGULATOR ---

TRIANGULATION_PROMPT = f"""
{BASE_SQL_RULES}
Act as an Anime Media Analyst specializing in thematic DNA.

REFERENCE SHOWS:
{{trinity_data}}

Task:
1. Identify the 'Thematic Intersection' (Shared DNA: themes, pacing, plot devices, emotional tone) of these three shows.
2. Write a SQLite query targeting this shared DNA in the 'anime_info' table.
3. Exclude the original titles: {{excluded_titles}}.
4. WIDE NET PROTOCOL: You MUST use 'OR' statements aggressively when searching 'mal_synopsis' and 'consensus_json'. Do NOT use strict 'AND' statements across multiple traits, or the query will fail. We want a broad pool of candidates that share at least *some* of the DNA.

Output MUST be a JSON object containing 'intersection_summary' (1-2 sentences) and 'sql_query' (raw SQL string).
"""