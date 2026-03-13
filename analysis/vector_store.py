"""
MODULE: analysis/vector_store.py
FUNCTION: FAISS-based semantic retrieval layer for the Recommendation Engine.
          Uses Google gemini-embedding-001 for dense vector search via FAISS.
          Phase 2 (Gemini reranking) remains unchanged.
"""

import os
import sys
import re
import json
import sqlite3
import logging
import time
import numpy as np
import faiss
from google import genai
from dotenv import load_dotenv

# --- BULLETPROOF PATH ANCHORING ---
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
if os.path.basename(SCRIPT_DIR) in ['tools', 'analysis', 'src']:
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)
else:
    ROOT_DIR = SCRIPT_DIR

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(ROOT_DIR, "data", "anime_intelligence_v2.db")
INDEX_PATH = os.path.join(ROOT_DIR, "data", "anime_vector_index.faiss")
METADATA_PATH = os.path.join(ROOT_DIR, "data", "anime_vector_metadata.json")
EMBEDDING_MODEL = "gemini-embedding-001"

# Module-level singletons (populated on first call)
_client = None
_index = None
_metadata = None


def _get_client():
    """Lazy-load the Google GenAI client (singleton)."""
    global _client
    if _client is None:
        load_dotenv(os.path.join(ROOT_DIR, "env_variables.env"))
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment.")
        _client = genai.Client(api_key=api_key)
        logger.info("Google GenAI client initialized for embeddings.")
    return _client


def _embed(texts, task_type="RETRIEVAL_QUERY", batch_size=50):
    """
    Encode a list of texts into dense embeddings using Google's gemini-embedding-001.
    Returns an (N, dim) numpy float32 array, L2-normalized.

    task_type: "RETRIEVAL_DOCUMENT" for index building (documents to be searched),
               "RETRIEVAL_QUERY" for search-time queries (default).
    """
    client = _get_client()
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config={"task_type": task_type},
        )
        for emb in result.embeddings:
            all_embeddings.append(emb.values)

        # Rate-limit courtesy: small delay between batches during bulk operations
        if len(texts) > batch_size and i + batch_size < len(texts):
            time.sleep(0.5)

    result = np.array(all_embeddings, dtype=np.float32)
    faiss.normalize_L2(result)
    return result


def _get_readonly_connection():
    """Opens SQLite in read-only mode."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Vault missing at {DB_PATH}")
    uri_path = f"file:{DB_PATH}?mode=ro"
    return sqlite3.connect(uri_path, uri=True)


def _expand_vibe_tags(vibe_str):
    """
    Cross-references AI-distilled thematic_vibe tags against the concept
    vocabulary and expands them with standardized synonyms.  This fixes
    inconsistencies like "Romantic" (no "Romance") or missing "Mecha" on
    mecha shows whose vibe was distilled as "Coming-of-age, Mecha, Dystopian".

    Example: "Nostalgic, Musical, Romantic"
         ->  "Nostalgic, Musical, Romantic, romance, romantic, love story, love interest"
    """
    if not vibe_str:
        return vibe_str

    vibe_lower = vibe_str.lower()
    expansions = []

    for concept, synonyms in _CONCEPT_VOCABULARY.items():
        # Check if any synonym of this concept appears in the vibe string
        matched = any(syn in vibe_lower for syn in synonyms)
        # Also check the concept name itself (e.g., "mecha" in "Coming-of-age, Mecha")
        if not matched and concept in vibe_lower:
            matched = True
        if matched:
            # Add all synonyms that aren't already present
            for syn in synonyms:
                if syn not in vibe_lower:
                    expansions.append(syn)

    if expansions:
        return vibe_str + ", " + ", ".join(expansions)
    return vibe_str


def _build_embedding_document(title, synopsis, consensus_json, genres=None):
    """
    Build a structured natural-language embedding document from raw DB fields.
    Front-loads genre keywords so they fall within the model's attention
    window, and strips JSON structural noise from consensus_json.

    Uses authoritative MAL genre tags (from the `genres` column) as the
    primary genre signal, with AI-distilled thematic_vibe tags as a
    secondary vibe/mood layer. Both are expanded via _expand_vibe_tags().
    """
    parts = []

    # Parse consensus_json for structured fields
    consensus = {}
    if consensus_json:
        try:
            consensus = json.loads(consensus_json)
        except json.JSONDecodeError:
            pass

    # 1. Title (helps with franchise/sequel matching)
    parts.append(f"Title: {title}")

    # 2. MAL Genre tags — authoritative editorial taxonomy, placed first
    if genres:
        expanded_genres = _expand_vibe_tags(genres)
        parts.append(f"Genres: {expanded_genres}")

    # 3. AI-distilled vibe tags — secondary mood/theme signal
    vibe = consensus.get("thematic_vibe", "")
    if vibe:
        expanded_vibe = _expand_vibe_tags(vibe)
        parts.append(f"Vibe: {expanded_vibe}")

    # 3. Synopsis
    if synopsis:
        parts.append(f"Synopsis: {synopsis}")

    # 4. Audience consensus summary (natural language, not raw JSON)
    summary = consensus.get("consensus_summary", "")
    if summary:
        parts.append(f"Audience Consensus: {summary}")

    # 5. Pros/cons as thematic keywords
    pros = consensus.get("pros", [])
    cons = consensus.get("cons", [])
    if pros:
        parts.append(f"Strengths: {', '.join(pros)}")
    if cons:
        parts.append(f"Weaknesses: {', '.join(cons)}")

    return "\n".join(parts)


def build_index():
    """
    Reads all rows from SQLite, builds structured embedding documents,
    and writes a FAISS index + metadata mapping to disk.
    """
    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, english_title, mal_synopsis, consensus_json, genres FROM anime_info"
        )
        rows = cursor.fetchall()

    documents = []
    metadata = []

    for mal_id, title, synopsis, consensus_json, genres in rows:
        if not synopsis and not consensus_json:
            continue

        doc_text = _build_embedding_document(title, synopsis, consensus_json, genres)
        documents.append(doc_text)
        metadata.append({"id": mal_id, "english_title": title})

    if not documents:
        raise ValueError("No embeddable documents found in the database.")

    logger.info(f"Embedding {len(documents)} anime documents via Google API...")
    embeddings = _embed(documents, task_type="RETRIEVAL_DOCUMENT")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)

    logger.info(
        f"Index built: {index.ntotal} vectors, dim={dim}. "
        f"Saved to {INDEX_PATH} and {METADATA_PATH}"
    )
    return index.ntotal


def update_index(mal_ids):
    """
    Incrementally update the FAISS index for a list of MAL IDs.
    - Existing IDs: removes old vectors, re-embeds, and appends updated vectors.
    - New IDs: embeds and appends.
    Saves the updated index + metadata to disk and clears singletons.
    """
    global _index, _metadata

    if not mal_ids:
        return 0

    # Load current index + metadata
    index, metadata = _load_index()

    # Build a lookup: MAL ID -> positional index in FAISS
    id_to_pos = {entry["id"]: i for i, entry in enumerate(metadata)}

    # Separate into existing (update) vs new (append)
    update_ids = [mid for mid in mal_ids if mid in id_to_pos]
    new_ids = [mid for mid in mal_ids if mid not in id_to_pos]

    # Remove old vectors for shows being updated
    if update_ids:
        positions_to_remove = np.array(
            [id_to_pos[mid] for mid in update_ids], dtype=np.int64
        )
        id_selector = faiss.IDSelectorArray(positions_to_remove)
        index.remove_ids(id_selector)

        # Remove corresponding metadata entries (iterate in reverse to preserve indices)
        for pos in sorted(positions_to_remove, reverse=True):
            metadata.pop(pos)

    # Fetch fresh data from SQLite for all target IDs
    all_target_ids = update_ids + new_ids
    placeholders = ",".join(["?"] * len(all_target_ids))
    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, english_title, mal_synopsis, consensus_json, genres "
            f"FROM anime_info WHERE id IN ({placeholders})",
            all_target_ids,
        )
        rows = cursor.fetchall()

    documents = []
    new_metadata = []
    for mal_id, title, synopsis, consensus_json, genres in rows:
        if not synopsis and not consensus_json:
            continue
        doc_text = _build_embedding_document(title, synopsis, consensus_json, genres)
        documents.append(doc_text)
        new_metadata.append({"id": mal_id, "english_title": title})

    if not documents:
        logger.warning("No embeddable documents found for the given MAL IDs.")
        return 0

    # Embed and append
    embeddings = _embed(documents, task_type="RETRIEVAL_DOCUMENT")
    index.add(embeddings)
    metadata.extend(new_metadata)

    # Save to disk
    faiss.write_index(index, INDEX_PATH)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)

    # Clear singletons so next search picks up fresh data
    _index = None
    _metadata = None

    logger.info(
        f"Index updated: {len(update_ids)} replaced, {len(new_ids)} added. "
        f"Total vectors: {index.ntotal}"
    )
    return len(documents)


def _load_index():
    """Lazy-load the FAISS index and metadata mapping (singletons)."""
    global _index, _metadata
    if _index is None:
        if not os.path.exists(INDEX_PATH) or not os.path.exists(METADATA_PATH):
            raise FileNotFoundError(
                "FAISS index not found. Run build_index() first."
            )
        _index = faiss.read_index(INDEX_PATH)
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            _metadata = json.load(f)
        logger.info(f"FAISS index loaded: {_index.ntotal} vectors.")
    return _index, _metadata


def _parse_objective_query(query):
    """
    Parse an Objective Rankings query into structured filters.
    Extracts season, year/year-range, and genre keywords.

    Returns a dict with:
        season: str or None (e.g., "Winter")
        year: int or None (exact year)
        year_min: int or None (for "after YYYY" / "since YYYY")
        year_max: int or None (for "before YYYY")
        genres: list[str] (detected genre keywords from _CONCEPT_VOCABULARY)

    Examples:
        "top sports anime from fall 2019" -> {season: "Fall", year: 2019, genres: ["sports"]}
        "best romance anime after 2020"   -> {year_min: 2021, genres: ["romance"]}
        "top anime of 2023"               -> {year: 2023, genres: []}
    """
    query_lower = query.lower()

    # Season detection
    season = None
    for s in ["winter", "spring", "summer", "fall"]:
        if s in query_lower:
            season = s.capitalize()
            break

    # Temporal range detection ("after/since YYYY", "before YYYY")
    year = None
    year_min = None
    year_max = None

    # Year range: "2018 to 2022", "2018-2022"
    range_match = re.search(r'((?:19|20)\d{2})\s*(?:to|-)\s*((?:19|20)\d{2})', query_lower)
    if range_match:
        year_min = int(range_match.group(1))
        year_max = int(range_match.group(2))
    else:
        after_match = re.search(r'(?:after|since)\s+((?:19|20)\d{2})', query_lower)
        before_match = re.search(r'before\s+((?:19|20)\d{2})', query_lower)

        if after_match:
            year_min = int(after_match.group(1)) + 1  # "after 2020" means >= 2021
        if before_match:
            year_max = int(before_match.group(1)) - 1  # "before 2020" means <= 2019

    # Exact year (only if no range was detected)
    if not year_min and not year_max:
        year_match = re.search(r'\b(19|20)\d{2}\b', query)
        if year_match:
            year = int(year_match.group())

    # Genre detection via concept vocabulary
    genres = []
    for concept, synonyms in _CONCEPT_VOCABULARY.items():
        for syn in synonyms:
            if syn in query_lower:
                genres.append(concept)
                break

    return {
        "season": season,
        "year": year,
        "year_min": year_min,
        "year_max": year_max,
        "genres": genres,
    }


def objective_rankings_search(query, top_k=50):
    """
    Structured database query for Objective Rankings mode.
    Handles compound queries like "top sports anime from fall 2019"
    by combining temporal filters with genre matching via thematic_vibe.
    """
    parsed = _parse_objective_query(query)
    season = parsed["season"]
    year = parsed["year"]
    year_min = parsed["year_min"]
    year_max = parsed["year_max"]
    genres = parsed["genres"]

    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        where_clauses = ["consensus_json IS NOT NULL"]
        params = []

        # Temporal filters
        if season and year:
            where_clauses.append("season = ?")
            params.append(f"{season}_{year}")
        elif year:
            where_clauses.append("release_year = ?")
            params.append(year)
        if year_min:
            where_clauses.append("release_year >= ?")
            params.append(year_min)
        if year_max:
            where_clauses.append("release_year <= ?")
            params.append(year_max)

        # If genres detected, fetch wider pool for post-filtering
        fetch_limit = top_k * 5 if genres else top_k

        cursor.execute(
            f"SELECT english_title, consensus_json, mal_synopsis, genres FROM anime_info "
            f"WHERE {' AND '.join(where_clauses)} "
            f"ORDER BY mal_score DESC LIMIT ?",
            params + [fetch_limit],
        )
        rows = cursor.fetchall()

    # Genre post-filter: match against genres column, thematic_vibe, and synopsis
    if genres:
        # Expand genre keywords using concept vocabulary for broader matching
        genre_terms = set()
        for g in genres:
            genre_terms.add(g)
            if g in _CONCEPT_VOCABULARY:
                genre_terms.update(_CONCEPT_VOCABULARY[g])

        filtered = []
        for title, raw_json, synopsis, db_genres in rows:
            try:
                data = json.loads(raw_json) if raw_json else {}
                vibe = data.get("thematic_vibe", "").lower()
                synopsis_lower = (synopsis or "").lower()
                genres_lower = (db_genres or "").lower()
                # Check genres column, vibe tags, and synopsis for any genre term
                searchable = genres_lower + " " + vibe + " " + synopsis_lower
                if any(term in searchable for term in genre_terms):
                    filtered.append(title)
            except json.JSONDecodeError:
                continue
        results = [{"title": t, "similarity": 1.0} for t in filtered[:top_k]]
    else:
        results = [{"title": row[0], "similarity": 1.0} for row in rows[:top_k]]

    return results


# --- FILTERED RETRIEVAL (Hybrid SQL + FAISS) ---

# Regex patterns for temporal terms to strip from queries before embedding
_TEMPORAL_PATTERNS = [
    re.compile(r'\b(?:released?|airing|aired|came out|from|of|in)\s+(?:after|since|before|during)?\s*(?:(?:19|20)\d{2})\b', re.IGNORECASE),
    re.compile(r'\b(?:after|since|before)\s+(?:19|20)\d{2}\b', re.IGNORECASE),
    re.compile(r'\b(?:19|20)\d{2}\s*(?:to|-)\s*(?:19|20)\d{2}\b', re.IGNORECASE),
    re.compile(r'\b(?:winter|spring|summer|fall)\s+(?:19|20)\d{2}\b', re.IGNORECASE),
    re.compile(r'\b(?:19|20)\d{2}\b'),
]


def _extract_filters(query):
    """
    Extract structured filters (temporal, genre) from a natural language query.
    Reuses _parse_objective_query() for parsing, then determines if any hard
    filters should be applied.

    Returns a dict with:
        has_filters: bool — whether any hard filters were detected
        year: int or None
        year_min: int or None
        year_max: int or None
        season: str or None
        genres: list[str] — canonical genre names from _CONCEPT_VOCABULARY
        genre_db_terms: list[str] — SQL LIKE terms for the genres column
    """
    parsed = _parse_objective_query(query)

    has_temporal = any([parsed["year"], parsed["year_min"], parsed["year_max"], parsed["season"]])

    # Only trigger filtered path when temporal constraints are present.
    # Genre-only queries are well-served by the standard FAISS semantic path
    # since genre concepts are already embedded. Temporal constraints are what
    # FAISS fundamentally cannot handle.

    # Map concept vocabulary genres to MAL genre column terms
    # e.g., "harem" -> "Harem", "sci-fi" -> "Sci-Fi"
    _CONCEPT_TO_MAL_GENRE = {
        "mecha": "Mecha", "romance": "Romance", "action": "Action",
        "comedy": "Comedy", "horror": "Horror", "psychological": "Psychological",
        "thriller": "Suspense", "sports": "Sports", "fantasy": "Fantasy",
        "sci-fi": "Sci-Fi", "drama": "Drama", "slice of life": "Slice of Life",
        "mystery": "Mystery", "supernatural": "Supernatural", "military": "Military",
        "music": "Music", "school": "School", "adventure": "Adventure",
        "harem": "Harem", "ecchi": "Ecchi",
        "shounen": "Shounen", "seinen": "Seinen", "josei": "Josei",
        "kodomomuke": "Kids",
    }

    # Demographic concepts are publishing categories, not thematic descriptors.
    # They embed poorly (uniformly weak semantic signal across all anime) so they
    # must be enforced as hard SQL filters on the genres column rather than
    # relying on FAISS similarity.
    _DEMOGRAPHIC_CONCEPTS = {"shounen", "seinen", "josei", "kodomomuke"}

    genre_db_terms = []
    has_demographic = False
    for g in parsed["genres"]:
        mal_genre = _CONCEPT_TO_MAL_GENRE.get(g)
        if mal_genre:
            genre_db_terms.append(mal_genre)
        if g in _DEMOGRAPHIC_CONCEPTS:
            has_demographic = True

    return {
        "has_filters": has_temporal or has_demographic,
        "year": parsed["year"],
        "year_min": parsed["year_min"],
        "year_max": parsed["year_max"],
        "season": parsed["season"],
        "genres": parsed["genres"],
        "genre_db_terms": genre_db_terms,
    }


def _strip_filter_terms(query, filters):
    """
    Remove temporal phrases and demographic terms from the query text so the
    embedding focuses on semantic content rather than structured constraints
    that FAISS can't handle.

    Thematic genre keywords are KEPT because they carry valuable semantic signal
    for the embedding model. Demographic terms (shounen, seinen, josei, kodomomuke)
    are STRIPPED because they are publishing categories with uniformly weak
    embedding discrimination — the SQL pre-filter enforces them as hard constraints.

    "harem anime released after 2020" -> "harem anime"
    "gritty military show from spring 2024" -> "gritty military show"
    "shounen sports anime" -> "sports anime"
    """
    stripped = query

    # Strip temporal phrases (year ranges, after/before/since, season+year, bare years)
    for pattern in _TEMPORAL_PATTERNS:
        stripped = pattern.sub("", stripped)

    # Clean up residual temporal connectors left behind
    stripped = re.sub(r'\b(released|airing|aired|came out|from|after|since|before)\b',
                      '', stripped, flags=re.IGNORECASE)

    # Strip demographic terms — they are enforced via SQL, not embedding
    _DEMOGRAPHIC_TERMS = re.compile(
        r'\b(shounen|shonen|seinen|josei|kodomomuke|kodomo)\b', re.IGNORECASE
    )
    stripped = _DEMOGRAPHIC_TERMS.sub("", stripped)

    stripped = re.sub(r'\s+', ' ', stripped).strip()

    # If stripping removed everything meaningful, fall back to genre terms as the query
    if len(stripped.split()) < 2:
        # Use non-demographic genres for the fallback query
        _DEMOGRAPHIC_CONCEPTS = {"shounen", "seinen", "josei", "kodomomuke"}
        thematic_genres = [g for g in filters["genres"] if g not in _DEMOGRAPHIC_CONCEPTS]
        stripped = " ".join(thematic_genres) + " anime" if thematic_genres else query

    return stripped


def _filtered_vector_search(query, filters, top_k=50):
    """
    Hybrid SQL + FAISS search for queries with structured constraints.

    1. Queries SQLite for all shows matching genre/temporal hard filters
    2. Maps those shows to their FAISS index positions
    3. Reconstructs their vectors and computes similarity against the
       stripped query embedding
    4. Returns results sorted by similarity, ready for composite reranking

    Guarantees 100% recall for the filtered set — no candidates are lost
    to FAISS over-fetch limits.
    """
    index, metadata = _load_index()

    # Build title -> FAISS position lookup
    title_to_pos = {m["english_title"]: i for i, m in enumerate(metadata)}

    # Query SQLite for matching shows
    where_clauses = ["consensus_json IS NOT NULL"]
    params = []

    if filters["season"] and filters["year"]:
        where_clauses.append("season = ?")
        params.append(f"{filters['season']}_{filters['year']}")
    elif filters["year"]:
        where_clauses.append("release_year = ?")
        params.append(filters["year"])
    if filters["year_min"]:
        where_clauses.append("release_year >= ?")
        params.append(filters["year_min"])
    if filters["year_max"]:
        where_clauses.append("release_year <= ?")
        params.append(filters["year_max"])

    # Genre filter using the authoritative genres column
    for mal_genre in filters["genre_db_terms"]:
        where_clauses.append("genres LIKE ?")
        params.append(f"%{mal_genre}%")

    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT english_title FROM anime_info "
            f"WHERE {' AND '.join(where_clauses)}",
            params,
        )
        matching_titles = [row[0] for row in cursor.fetchall()]

    if not matching_titles:
        logger.warning("Filtered search: no shows match the constraints. Falling back to unfiltered.")
        return None  # Signal caller to use unfiltered path

    # Map to FAISS positions and reconstruct vectors
    valid_titles = []
    positions = []
    for title in matching_titles:
        pos = title_to_pos.get(title)
        if pos is not None:
            valid_titles.append(title)
            positions.append(pos)

    if not valid_titles:
        logger.warning("Filtered search: no matching shows found in FAISS index.")
        return None

    # Reconstruct vectors for the filtered set
    vectors = np.array(
        [index.reconstruct(pos) for pos in positions],
        dtype=np.float32,
    )

    # Embed the stripped query and compute similarities
    stripped_query = _strip_filter_terms(query, filters)
    query_embedding = _embed([stripped_query])

    similarities = np.dot(vectors, query_embedding[0])

    # Build results sorted by similarity
    results = []
    for i, title in enumerate(valid_titles):
        results.append({
            "title": title,
            "similarity": float(similarities[i]),
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)

    logger.info(
        f"Filtered search: {len(valid_titles)} candidates from SQL "
        f"(query: '{stripped_query}'). "
        f"Filters: genres={filters['genre_db_terms']}, "
        f"year={filters.get('year')}, year_min={filters.get('year_min')}, "
        f"year_max={filters.get('year_max')}"
    )

    return results


# --- QUERY DECOMPOSITION ---

# Genre/theme vocabulary for concept extraction.
# Each key is a canonical concept; values are synonyms/variants that signal it.
_CONCEPT_VOCABULARY = {
    "mecha": ["mecha", "mech", "robot", "giant robot", "gundam", "piloting"],
    "romance": ["romance", "romantic", "love story", "love interest", "relationship"],
    "action": ["action", "battle", "fighting", "combat", "martial arts"],
    "comedy": ["comedy", "comedic", "funny", "humor", "gag", "slapstick"],
    "horror": ["horror", "scary", "creepy", "terrifying", "gore"],
    "psychological": ["psychological", "mind game", "mental", "psyche"],
    "thriller": ["thriller", "suspense", "suspenseful", "tense"],
    "sports": ["sports", "sport", "athletic", "tournament", "competition"],
    "fantasy": ["fantasy", "magic", "magical", "isekai", "sorcery"],
    "sci-fi": ["sci-fi", "science fiction", "futuristic", "space", "cyberpunk"],
    "drama": ["drama", "dramatic", "emotional", "tragedy", "tragic"],
    "slice of life": ["slice of life", "everyday life", "daily life", "mundane"],
    "mystery": ["mystery", "detective", "whodunit", "investigation"],
    "supernatural": ["supernatural", "ghost", "spirit", "paranormal", "demon"],
    "military": ["military", "war", "army", "soldier", "warfare"],
    "music": ["music", "musical", "band", "idol", "singing"],
    "school": ["school", "high school", "academy", "student council"],
    "dark": ["dark", "gritty", "bleak", "nihilistic", "dystopian"],
    "wholesome": ["wholesome", "heartwarming", "feel-good", "healing", "iyashikei"],
    "adventure": ["adventure", "journey", "quest", "exploration"],
    "harem": ["harem", "reverse harem", "love triangle"],
    "ecchi": ["ecchi", "fanservice", "fan service"],
    "shounen": ["shounen", "shonen", "boys", "battle anime", "fighting spirit", "tournament arc"],
    "seinen": ["seinen", "mature", "adult themes", "cerebral"],
    "josei": ["josei", "adult romance", "working woman", "mature romance"],
    "kodomomuke": ["kodomomuke", "kodomo", "kids", "children", "family friendly"],
}


def _decompose_query(query):
    """
    Detect distinct thematic concepts in a user query using keyword matching.
    Returns a list of concept phrases suitable for independent FAISS searches.

    For single-concept queries, returns an empty list (caller should use the
    original query as-is). For multi-concept queries, returns one search
    phrase per detected concept.

    Examples:
        "mecha anime with romance aspects" -> ["mecha robot giant robot anime",
                                                "romance romantic love story anime"]
        "dark psychological thriller"      -> ["dark gritty bleak anime",
                                                "psychological mind game anime",
                                                "thriller suspense anime"]
        "best action anime"                -> [] (single concept, no decomposition)
    """
    query_lower = query.lower()

    # Find all concepts present in the query
    detected = []
    for concept, synonyms in _CONCEPT_VOCABULARY.items():
        for syn in synonyms:
            if syn in query_lower:
                detected.append(concept)
                break

    # Single concept or none: no decomposition needed
    if len(detected) <= 1:
        return []

    # Build an expanded sub-query per concept using its synonym list
    sub_queries = []
    for concept in detected:
        synonyms = _CONCEPT_VOCABULARY[concept]
        # Include top synonyms + "anime" to anchor the embedding
        phrase = " ".join(synonyms[:4]) + " anime"
        sub_queries.append(phrase)

    return sub_queries


def _search_faiss_raw(query_embedding, fetch_k):
    """
    Low-level FAISS search returning list of {title, similarity} dicts.
    Shared by both single-query and decomposed-query paths.
    """
    index, metadata = _load_index()
    actual_k = min(fetch_k, index.ntotal)
    scores, indices = index.search(query_embedding, actual_k)

    results = []
    for i, idx in enumerate(indices[0]):
        if 0 <= idx < len(metadata):
            results.append({
                "title": metadata[idx]["english_title"],
                "similarity": float(scores[0][i]),
            })
    return results


def _cross_concept_rerank(original_results, sub_query_embeddings):
    """
    Re-score candidates using AND-semantics: for each candidate in the
    original results, compute its similarity to every sub-query concept
    via the FAISS index, then use min(concept_similarities) as a boost.

    This promotes titles that match ALL query concepts (e.g., mecha AND
    romance) over titles that only match the dominant concept.

    Returns a list of {title, similarity} dicts where similarity is the
    original query similarity (for Phase 2) but ordering reflects
    cross-concept coverage.
    """
    index, metadata = _load_index()

    # Build title -> FAISS vector index lookup
    title_to_idx = {}
    for i, m in enumerate(metadata):
        title_to_idx[m["english_title"]] = i

    # For each candidate, compute similarity to each sub-query concept
    candidate_scores = []
    for r in original_results:
        title = r["title"]
        faiss_idx = title_to_idx.get(title)
        if faiss_idx is None:
            candidate_scores.append({
                "title": title,
                "similarity": r["similarity"],
                "_cross_concept_min": 0.0,
            })
            continue

        # Reconstruct this title's vector from the index
        vec = index.reconstruct(faiss_idx).reshape(1, -1)

        # Compute similarity to each sub-query concept
        concept_sims = []
        for sq_emb in sub_query_embeddings:
            sim = float(np.dot(vec[0], sq_emb[0]))
            concept_sims.append(sim)

        candidate_scores.append({
            "title": title,
            "similarity": r["similarity"],
            "_cross_concept_min": min(concept_sims),
        })

    # Sort by cross-concept minimum (AND-semantics), descending
    candidate_scores.sort(key=lambda x: x["_cross_concept_min"], reverse=True)

    return [
        {"title": c["title"], "similarity": c["similarity"]}
        for c in candidate_scores
    ]


# --- METADATA-AWARE RERANKING ---

# Weights for the composite retrieval score
_W_SIMILARITY = 0.50  # Semantic relevance (FAISS cosine)
_W_QUALITY = 0.25     # Bayesian-adjusted MAL score (normalized 0-1)
_W_POPULARITY = 0.05  # Log-scaled vote count (normalized 0-1)
_W_INPUT_RANK = 0.15  # Preserves cross-concept AND-ordering from decomposition
_W_RECENCY = 0.05     # Favors newer shows to counteract old-show embedding bias

# Quality floor: candidates below this raw MAL score are dropped before
# composite scoring.  Non-destructive — DB and FAISS index are untouched.
_QUALITY_FLOOR = 6.0

# Normalization constants (derived from DB statistics)
_MAL_SCORE_MIN = 2.87
_MAL_SCORE_MAX = 9.28
_LOG_VOTES_MAX = np.log1p(3_035_579)  # log(1 + max scored_by)
_YEAR_MIN = 2000
_YEAR_MAX = 2025

# Bayesian constants (must match queries.py)
_BAYESIAN_GLOBAL_MEAN = 7.05
_BAYESIAN_MIN_VOTES = 5000


def _composite_rerank(candidates):
    """
    Re-scores candidates using a weighted blend of semantic similarity,
    Bayesian-adjusted quality, log-scaled popularity, input rank
    (which reflects cross-concept AND-semantics when decomposition was used),
    and recency.

    Applies a quality floor first: candidates with raw MAL score below
    _QUALITY_FLOOR are dropped before scoring to prevent low-quality shows
    from consuming ranking slots.

    Returns results sorted by composite score with the original similarity
    preserved for Phase 2.
    """
    if not candidates:
        return candidates

    titles = [r["title"] for r in candidates]
    placeholders = ",".join(["?"] * len(titles))

    with _get_readonly_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT english_title, mal_score, scored_by, release_year FROM anime_info "
            f"WHERE english_title IN ({placeholders})",
            titles,
        )
        db_lookup = {}
        for eng_title, mal_score, scored_by, release_year in cursor.fetchall():
            db_lookup[eng_title] = (mal_score or 0.0, scored_by or 0, release_year or 0)

    # G1: Quality floor — drop candidates below the threshold
    filtered_candidates = []
    dropped = 0
    for r in candidates:
        raw_score = db_lookup.get(r["title"], (0.0, 0, 0))[0]
        if raw_score >= _QUALITY_FLOOR or raw_score == 0.0:
            filtered_candidates.append(r)
        else:
            dropped += 1
    if dropped:
        logger.info(f"Quality floor ({_QUALITY_FLOOR}): dropped {dropped} candidates.")
    candidates = filtered_candidates

    n = len(candidates)
    reranked = []
    for input_rank, r in enumerate(candidates):
        title = r["title"]
        sim = r["similarity"]
        raw_score, votes, year = db_lookup.get(title, (0.0, 0, 0))

        # Bayesian-adjusted quality, normalized to [0, 1]
        v, m, C = votes, _BAYESIAN_MIN_VOTES, _BAYESIAN_GLOBAL_MEAN
        bayesian = (v / (v + m)) * raw_score + (m / (v + m)) * C
        norm_quality = (bayesian - _MAL_SCORE_MIN) / (_MAL_SCORE_MAX - _MAL_SCORE_MIN)
        norm_quality = max(0.0, min(1.0, norm_quality))

        # Log-scaled popularity, normalized to [0, 1]
        norm_pop = np.log1p(votes) / _LOG_VOTES_MAX
        norm_pop = max(0.0, min(1.0, norm_pop))

        # Input rank signal: preserves cross-concept ordering from
        # _cross_concept_rerank (1.0 for rank 0, decaying toward 0)
        norm_rank = 1.0 - (input_rank / n) if n > 1 else 1.0

        # G4: Recency signal — newer shows get a mild boost (0.0 to 1.0)
        if year and year >= _YEAR_MIN:
            norm_recency = (year - _YEAR_MIN) / (_YEAR_MAX - _YEAR_MIN)
            norm_recency = max(0.0, min(1.0, norm_recency))
        else:
            norm_recency = 0.5  # Neutral for unknown years

        composite = (
            _W_SIMILARITY * sim
            + _W_QUALITY * norm_quality
            + _W_POPULARITY * norm_pop
            + _W_INPUT_RANK * norm_rank
            + _W_RECENCY * norm_recency
        )

        reranked.append({
            "title": title,
            "similarity": sim,
            "_composite": composite,
        })

    reranked.sort(key=lambda x: x["_composite"], reverse=True)

    return [{"title": r["title"], "similarity": r["similarity"]} for r in reranked]


def search(query, top_k=50):
    """
    Embeds the user query, retrieves a large candidate pool from FAISS,
    applies metadata-aware composite reranking (blending semantic similarity
    with Bayesian quality and popularity), and returns a list of
    {title, similarity} dicts.

    If the query contains structured constraints (temporal or genre filters),
    routes through the hybrid SQL+FAISS filtered path first. Falls back to
    the standard unfiltered FAISS path if no filters are detected or if the
    filtered search yields no results.
    """
    # --- FILTERED PATH (COA 2) ---
    filters = _extract_filters(query)
    if filters["has_filters"]:
        filtered_results = _filtered_vector_search(query, filters, top_k=300)
        if filtered_results is not None:
            logger.info(
                f"Filtered path: {len(filtered_results)} candidates. "
                f"Routing to composite reranking."
            )
            reranked = _composite_rerank(filtered_results)
            return reranked[:top_k]
        # else: fall through to unfiltered path

    # --- UNFILTERED PATH (standard FAISS retrieval) ---
    index, metadata = _load_index()

    query_embedding = _embed([query])

    # Over-fetch: pull 300 candidates so composite reranking has room to
    # promote high-quality relevant shows after the quality floor filter
    # drops sub-6.0 candidates from the pool.
    fetch_k = 300
    original_results = _search_faiss_raw(query_embedding, fetch_k)

    # Query decomposition: for multi-concept queries, compute each
    # candidate's similarity to every concept independently, then
    # re-rank by min(concept_similarities) to enforce AND-semantics.
    sub_queries = _decompose_query(query)
    if sub_queries:
        sub_query_embeddings = [_embed([sq]) for sq in sub_queries]

        # Multi-pool retrieval — search FAISS with each sub-query
        # independently and merge into the candidate pool.
        seen_titles = {r["title"] for r in original_results}
        injected = 0
        for sq_emb in sub_query_embeddings:
            sq_results = _search_faiss_raw(sq_emb, 150)
            for r in sq_results:
                if r["title"] not in seen_titles:
                    original_results.append(r)
                    seen_titles.add(r["title"])
                    injected += 1
        if injected:
            logger.info(
                f"Multi-pool retrieval: injected {injected} candidates "
                f"from {len(sub_queries)} sub-queries. "
                f"Total pool: {len(original_results)}."
            )

        cross_ranked = _cross_concept_rerank(original_results, sub_query_embeddings)
        logger.info(
            f"Query decomposed into {len(sub_queries)} concepts: "
            f"{sub_queries}. Cross-concept reranked {len(cross_ranked)} candidates."
        )
    else:
        cross_ranked = original_results

    # Composite rerank: blend similarity + quality + popularity
    reranked = _composite_rerank(cross_ranked)

    return reranked[:top_k]


# --- CENTROID-BASED RETRIEVAL (DNA / Shows Like This) ---

def search_by_centroid(titles, top_k=50):
    """
    Retrieves similar anime by computing the vector centroid of 1+ reference
    shows and searching FAISS directly — no text embedding, no query
    decomposition.

    For multi-show inputs, averages the reference vectors and L2-normalizes
    the centroid. For single-show inputs, uses the show's own vector directly
    (nearest-neighbor lookup).

    Returns a list of {title, similarity} dicts after composite reranking,
    with reference shows and their franchise variants excluded.
    """
    index, metadata = _load_index()

    # Build title -> FAISS position lookup
    title_to_pos = {m["english_title"]: i for i, m in enumerate(metadata)}

    # Collect reference vectors
    ref_vectors = []
    for title in titles:
        pos = title_to_pos.get(title)
        if pos is not None:
            ref_vectors.append(index.reconstruct(pos))
        else:
            logger.warning(f"Centroid search: '{title}' not found in FAISS index.")

    if not ref_vectors:
        logger.error("Centroid search: no valid reference vectors found.")
        return []

    # Compute centroid (or use single vector directly)
    centroid = np.mean(ref_vectors, axis=0)
    centroid = centroid / np.linalg.norm(centroid)
    centroid = centroid.reshape(1, -1).astype(np.float32)

    # Search FAISS — over-fetch to give composite reranking room
    fetch_k = 300
    scores, indices = index.search(centroid, fetch_k)

    # Build results, excluding reference shows and franchise variants
    excluded = set(titles)
    from analysis.queries import find_franchise_titles
    excluded.update(find_franchise_titles(titles))

    results = []
    for i in range(fetch_k):
        idx = int(indices[0][i])
        if 0 <= idx < len(metadata):
            title = metadata[idx]["english_title"]
            if title not in excluded:
                results.append({
                    "title": title,
                    "similarity": float(scores[0][i]),
                })

    logger.info(
        f"Centroid search: {len(ref_vectors)} reference vector(s), "
        f"{len(results)} candidates (after excluding {len(excluded)} "
        f"reference/franchise titles)."
    )

    # Apply composite reranking (quality, popularity, recency)
    reranked = _composite_rerank(results)
    return reranked[:top_k]


# --- CLI ENTRY POINT ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Building FAISS index from anime_intelligence_v2.db...")
    count = build_index()
    print(f"Done. Indexed {count} anime.")
