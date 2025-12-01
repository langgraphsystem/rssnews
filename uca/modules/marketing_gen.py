from typing import List, Dict, Any
import logging
from uca.llm_client import LLMClient
from uca.schemas import MarketingAssets, TikTokCampaign, SeoTags, ProductConcept, TrendAnalysis

logger = logging.getLogger(__name__)

class MarketingGenerator:
    """
    Generates marketing assets (TikTok scripts, SEO tags) for UCA products.
    """
    
    def __init__(self):
        self.llm = LLMClient()

    def generate(self, products: List[ProductConcept], trend_data: TrendAnalysis) -> MarketingAssets:
        """
        Generate marketing assets for the lead product.
        """
        if not products:
            logger.warning("No products provided for marketing generation.")
            return MarketingAssets(
                tiktok_campaign=TikTokCampaign(
                    hook_type="Error",
                    script_audio="N/A",
                    script_visual="N/A",
                    caption="No products generated",
                    hashtags=[]
                ),
                seo_tags=SeoTags(amazon_kdp=[], etsy=[])
            )

        # Focus on the first product (Lead Magnet)
        lead_product = products[0]
        
        system_prompt = """
        You are a Viral Marketing Expert and SEO Specialist.
        Your goal is to create high-conversion assets for a new product based on a trending news topic.
        
        Output must be valid JSON matching the MarketingAssets schema.
        """
        
        user_prompt = f"""
        ## Context
        **Trend/Topic:** {lead_product.product_title}
        **Velocity:** {trend_data.velocity_score}
        **Emotion:** {trend_data.dominant_emotions[0]}
        
        ## Product
        **Title:** {lead_product.product_title}
        **Description:** {lead_product.description}
        **Category:** {lead_product.category_id}
        
        ## Tasks
        1. **TikTok Campaign:** Create a viral TikTok script.
           - **Hook:** Must be a "Pattern Interrupt" or "Curiosity Gap".
           - **Audio:** Suggest a trending audio vibe.
           - **Visual:** Describe the video sequence.
           - **Caption:** Short, punchy, with 3-5 hashtags.
           
        2. **SEO Tags:** Generate high-volume keywords.
           - **Amazon KDP:** 7 backend keywords (max 50 chars each).
           - **Etsy:** 13 tags (max 20 chars each).
        """
        
        try:
            return self.llm.generate_structured(system_prompt, user_prompt, MarketingAssets)
        except Exception as e:
            logger.error(f"Marketing generation failed: {e}")
            # Fallback
            return MarketingAssets(
                tiktok_campaign=TikTokCampaign(
                    hook_type="Fallback Hook",
                    script_audio="Trending Sound",
                    script_visual="Show product image with text overlay",
                    caption=f"Check out {lead_product.product_title} #trending",
                    hashtags=["#fyp", "#viral"]
                ),
                seo_tags=SeoTags(
                    amazon_kdp=["gift idea", "trending now"],
                    etsy=["custom gift", "unique find"]
                )
            )
