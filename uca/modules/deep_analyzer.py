from typing import List, Dict, Any
from ..schemas import DeepArticleAnalysis
from ..llm_client import LLMClient
import logging

logger = logging.getLogger(__name__)

class DeepAnalyzer:
    """
    Module for Deep Article Analysis.
    Extracts 10 key data points from article text using local LLM.
    """
    
    def __init__(self):
        self.llm = LLMClient()
    
    def analyze(self, news_text: str) -> DeepArticleAnalysis:
        """
        Analyze news text to extract deep insights.
        """
        
        system_prompt = """
        You are an Expert Content Analyst and Strategist.
        Your goal is to perform a deep analysis of the provided article and extract structured data points.
        
        You must extract EXACTLY these 10 elements:
        1. Keywords (SEO & Semantic core)
        2. Main Ideas (Executive summary)
        3. Triggers (Emotional, Motivational, Pain points, CTA)
        4. Trends (Market, Behavior, Tech)
        5. Target Audience (Who is this for?)
        6. Tone & Style (Voice of the author)
        7. Structure (How the content is organized)
        8. Facts & Data (Statistics, Studies, Forecasts)
        9. Insights (Hidden opportunities, gaps)
        10. Practical Utility (Models, Checklists, How-to)
        
        Return the result as a valid JSON object matching the DeepArticleAnalysis schema.
        """
        
        user_prompt = f"""
        Analyze this article text:
        
        "{news_text[:10000]}"
        
        Extract all 10 required data points. Be specific and detailed.
        """
        
        try:
            analysis = self.llm.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=DeepArticleAnalysis
            )
            return analysis
        except Exception as e:
            logger.error(f"Deep Analysis failed: {e}")
            # Fallback or re-raise depending on policy. For now, re-raise to handle in processor.
            raise e
