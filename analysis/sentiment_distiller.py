"""
MODULE: src/sentiment_distiller.py
FUNCTION: Pure AI Distillation Engine. Receives live data and returns structured JSON.
"""
import json
import logging
from google import genai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# --- SCHEMA DEFINITION ---
class ConsensusData(BaseModel):
    thematic_vibe: str = Field(description="Extract 3 specific tags (e.g., 'Grimdark', 'Philosophical').")
    pros: list[str] = Field(description="Identify high-signal positive critiques about production and writing.")
    cons: list[str] = Field(description="Identify high-signal negative critiques about production and writing.")
    controversy_score: int = Field(description="Scale 1-10 (how polarized is the audience?).")
    consensus_summary: str = Field(description="A 2-4 sentence executive summary of the audience mood.")

class ReviewDistiller:
    def __init__(self, api_key):
        """
        Initializes the AI Analyst with the 2026 GenAI SDK.
        """
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.0-flash" # Optimized for high-speed distillation

    async def distill_sentiment(self, context_data):
        """
        The 'Inference' Phase:
        Receives live 'context_data' (title, synopsis, and reviews) 
        and returns a clean, structured JSON object.
        """
        title = context_data.get('title', 'Unknown')
        synopsis = context_data.get('synopsis', 'No synopsis available.')
        reviews = context_data.get('reviews', [])

        # Build a dense 'Intelligence Packet' for Gemini
        corpus = f"--- SHOW: {title} ---\nSYNOPSIS: {synopsis}\n\nREVIEWS:\n"
        for i, review in enumerate(reviews):
            # Expanded truncation to 5000 chars to maximize the 1M token window
            corpus += f"Review {i+1}: {review[:5000]}\n\n" 

        prompt = f"""
        Act as a Media Intelligence Analyst. Analyze the audience corpus for: {title}.
        Focus on identifying the 'Emotional Signature' and 'Narrative Quality'.
        
        CORPUS:
        {corpus}

        TASK:
        1. thematic_vibe: Extract 3 specific tags (e.g., 'Grimdark', 'Philosophical').
        2. pros/cons: Identify high-signal critiques about production and writing.
        3. controversy_score: Scale 1-10 (how polarized is the audience?).
        4. consensus_summary: A 2-4 sentence executive summary of the audience mood.
        """

        try:
            # Native SDK Structured Output using True Async
            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": ConsensusData,
                }
            )
            
            # The SDK safely parses the Pydantic object
            if response.parsed:
                return response.parsed.model_dump()
            else:
                # Fallback to standard json loading if parsed is somehow empty but text isn't
                return json.loads(response.text.strip())

        except Exception as e:
            logger.error(f"AI Distillation Error for {title}: {e}")
            return None