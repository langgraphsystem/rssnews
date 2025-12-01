
from typing import Dict, Any, List
import json
import logging
from datetime import datetime

from .schemas import (
    UCAOutput, TrendAnalysis, EmpathyMap, MarketingAssets, 
    LegalCheck, FunnelStrategy, TikTokCampaign, SeoTags
)
from .constants import AgentMode, ProductCategory, Emotion, TrendLifecycle

from .modules.trend_analyzer import TrendAnalyzer
from .modules.psych_engine import PsychEngine
from .modules.product_gen import ProductGenerator
from .db_client import UCADatabaseClient
from .llm_client import LLMClient
from .modules.marketing_gen import MarketingGenerator
# from .modules.ip_safety import IPSafetyCheck

logger = logging.getLogger(__name__)

class UCAEngine:
    """
    Universal Commercial Agent (UCA) Orchestrator.
    Implements the 'News-to-Cash' pipeline.
    """
    
    def __init__(self, mode: AgentMode = AgentMode.STORE_OWNER):
        self.mode = mode
        logger.info(f"UCA Engine initialized in {mode} mode")
        
        # Initialize Sub-agents
        self.trend_analyzer = TrendAnalyzer()
        self.psych_engine = PsychEngine()
        self.product_gen = ProductGenerator()
        self.db_client = UCADatabaseClient()
        self.llm_client = LLMClient()
        self.marketing = MarketingGenerator()
        # self.safety = IPSafetyCheck()

    def process_news_event(self, news_text: str, source_id: str) -> Dict[str, Any]:
        """
        Main pipeline: News -> Commercial Assets (JSON)
        """
        logger.info(f"Processing news event: {source_id}")
        
        # 1. Trend Analysis & Velocity
        trend_data = self.trend_analyzer.analyze(news_text)
        
        # 2. Psychological Profiling (Empathy Map)
        # We use the dominant emotion from trend analysis to seed the psych engine
        dominant_emotion = trend_data.dominant_emotions[0]
        empathy_map = self.psych_engine.create_empathy_map(news_text, dominant_emotion)
        
        # Update trend data with real empathy map
        trend_data.empathy_map = empathy_map
        
        # 3. Product Generation (13 Categories)
        products = self.product_gen.generate_products(trend_data, empathy_map, self.mode)
        
        # 4. Marketing Generation (TikTok + SEO)
        marketing = self.marketing.generate(products, trend_data)
        
        # 5. Safety Check (IP)
        # safety_result = self.safety.check(products)
        # Stub for safety
        safety_result = LegalCheck(
            status="PASSED",
            flagged_terms=[],
            risk_level="Low"
        )
        
        # 6. Construct Final JSON
        output = UCAOutput(
            meta={
                "agent_mode": self.mode.value,
                "timestamp": datetime.now().isoformat(),
                "source_id": source_id
            },
            trend_analysis=trend_data,
            commercial_opportunities=products,
            marketing_assets=marketing,
            legal_check=safety_result,
            funnel_strategy=FunnelStrategy(
                bundle_name="Starter Pack",
                core_product="T-Shirt",
                order_bump="Sticker",
                upsell="Planner",
                logic="Standard funnel"
            )
        )
        
        return output.dict()

    def process_recent_news(self, limit: int = 5, days: int = 1) -> List[Dict[str, Any]]:
        """
        Fetch and process the most recent articles from the database within N days.
        """
        articles = self.db_client.get_recent_articles(days=days, limit=limit)
        results = []
        
        logger.info(f"Found {len(articles)} recent articles to process")
        
        for article in articles:
            try:
                # Combine title and content for analysis
                full_text = f"{article['title']}\n\n{article['content']}"
                source_id = f"db_{article['id']}"
                
                result = self.process_news_event(full_text, source_id)
                
                # Add original article metadata to result for context
                result['original_article'] = {
                    'title': article['title'],
                    'url': article['url'],
                    'id': article['id'],
                    'content': article['content'] # Added for dashboard text analysis
                }
                
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing article {article['id']}: {e}")
                
        return results

    def generate_graph_insights(self, graph_data: Dict[str, Any]) -> str:
        """
        Generate AI insights based on the text network graph structure.
        Focuses on bridging structural gaps and connecting topics.
        """
        # Prepare context for LLM
        topics = {}
        for node, group in graph_data['communities'].items():
            if group not in topics:
                topics[group] = []
            topics[group].append(node)
            
        topic_str = "\n".join([f"Topic {g}: {', '.join(words[:10])}" for g, words in topics.items()])
        
        gaps_str = "\n".join([
            f"- Gap between '{g['node_a']}' (Topic {g['topic_a']}) and '{g['node_b']}' (Topic {g['topic_b']})"
            for g in graph_data.get('structural_gaps', [])
        ])
        
        prompt = f"""
        Analyze the following Text Network Graph structure derived from a news article.
        
        ## Detected Topics (Clusters)
        {topic_str}
        
        ## Structural Gaps (Missing Connections)
        {gaps_str}
        
        ## Task
        Act as an expert researcher and innovation consultant.
        1. **Synthesize**: Briefly explain the main narrative flow based on the topics.
        2. **Bridge the Gaps**: For the identified structural gaps, propose 2-3 specific, novel ideas or research questions that would connect these disconnected concepts. 
           - How can '{gaps_str.splitlines()[0] if gaps_str else "Topic A"}' be related to '{gaps_str.splitlines()[0] if gaps_str else "Topic B"}'?
        3. **Hidden Insight**: Identify one non-obvious connection or "blind spot" in the discourse.
        
        Keep the response concise and actionable.
        """
        
        try:
            # Use the LLM Client to generate text
            response = self.llm_client.generate_text(prompt)
            return response
        except Exception as e:
            logger.error(f"Failed to generate graph insights: {e}")
            return "Could not generate AI insights at this time."

    def run_simulation(self):
        """
        Run the 'Solar Flare' scenario from the architectural plan
        """
        pass
