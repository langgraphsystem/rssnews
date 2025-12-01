from typing import Dict, Any
from ..schemas import EmpathyMap
from ..constants import Emotion
from ..llm_client import LLMClient

class PsychEngine:
    """
    Module 2.2 & 2.3: Psychological Transmutation Engine
    Generates Empathy Maps and maps emotions to product formats using LLM.
    """
    
    def __init__(self):
        self.llm = LLMClient()

    def create_empathy_map(self, news_text: str, dominant_emotion: Emotion) -> EmpathyMap:
        """
        Generates the 'Think, Feel, Say, Do' map using GPT-4o.
        """
        
        system_prompt = f"""
        You are a Psychological Profiler for a commercial AI agent.
        Your task is to create an 'Empathy Map' for the target audience of a specific news story.
        
        The dominant emotion identified is: {dominant_emotion.value}
        
        Answer 4 questions from the perspective of the consumer:
        1. THINK: What are their internal anxieties, hopes, or unspoken thoughts?
        2. FEEL: What is their immediate visceral emotional reaction?
        3. SAY: What are they posting on social media? (Slang, hashtags, vernacular)
        4. DO: What actions are they taking? (Searching, buying, sharing)
        
        Return a structured JSON matching the EmpathyMap schema.
        """
        
        user_prompt = f"""
        News Context:
        "{news_text[:2000]}"
        """
        
        try:
            empathy_map = self.llm.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=EmpathyMap
            )
            return empathy_map
        except Exception as e:
            print(f"LLM Psych Profiling failed: {e}")
            return self._fallback_map(dominant_emotion)

    def _fallback_map(self, dominant_emotion: Emotion) -> EmpathyMap:
        # Fallback templates
        return EmpathyMap(
            think="I need to understand this.",
            feel=f"Feeling {dominant_emotion.value}",
            say="#news",
            do="Reading more."
        )

    def get_product_formats(self, emotion: Emotion) -> Dict[str, Any]:
        """
        Returns the recommended product formats from the Transmutation Matrix.
        """
        from ..constants import EMOTION_TRANSMUTATION_MATRIX
        return EMOTION_TRANSMUTATION_MATRIX.get(emotion, {})
