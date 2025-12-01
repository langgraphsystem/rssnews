from typing import List, Dict, Any
from ..schemas import TrendAnalysis
from ..constants import TrendLifecycle, Emotion
from ..llm_client import LLMClient
import logging

logger = logging.getLogger(__name__)

class TrendAnalyzer:
    """
    Module 3: Trend Lifecycle Analysis & Classification
    Calculates Trend Velocity (Vt) and determines lifecycle stage using LLM.
    """
    
    def __init__(self):
        self.llm = LLMClient()
    
    def analyze(self, news_text: str, search_volume_delta: float = 0.0) -> TrendAnalysis:
        """
        Analyze news text to determine trend metrics using GPT-4o.
        """
        
        system_prompt = """
        You are an expert Trend Analyst for an algorithmic commerce system.
        Your goal is to analyze news text and determine its 'Commercial Velocity' and 'Lifecycle Stage'.
        
        1. Velocity Score (0-10): How fast is this story moving? Is it viral/urgent?
        2. Lifecycle: 
           - Ultra-Hype (Micro-trend): Memes, celebrity gossip, sudden shocks (48h lifespan).
           - Short-Term Shift: Seasonal events, policy changes (1-6 months).
           - Long-Term Shift: Macro trends, societal shifts (Years).
        3. Dominant Emotions: Identify the primary emotions driving this story.
        4. Viability: Can we sell products based on this?
        
        Return a structured JSON.
        """
        
        user_prompt = f"""
        Analyze this news story:
        "{news_text[:2000]}"
        
        Search Volume Delta (Context): {search_volume_delta}
        """
        
        try:
            analysis = self.llm.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=TrendAnalysis
            )
            print(f"DEBUG: LLM Analysis Result: {analysis}")
            return analysis
        except Exception as e:
            logger.error(f"LLM Analysis failed: {e}")
            print(f"LLM Analysis failed: {e}") # Force print
            return self._fallback_analyze(news_text)

    def _fallback_analyze(self, news_text: str) -> TrendAnalysis:
        # Simple fallback if API fails
        from ..schemas import EmpathyMap
        return TrendAnalysis(
            lifecycle_stage=TrendLifecycle.SHORT_TERM_SHIFT,
            velocity_score=5.0,
            dominant_emotions=[Emotion.CONFUSION],
            empathy_map=EmpathyMap(think="Error", feel="Error", say="Error", do="Error"),
            commercial_viability_score=0.5
        )
