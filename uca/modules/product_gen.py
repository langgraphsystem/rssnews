from typing import List, Dict, Any, Optional
from ..schemas import ProductConcept, VisualPrompt, TrendAnalysis, EmpathyMap
from ..constants import ProductCategory, AgentMode, CATEGORY_DEFINITIONS, Emotion
from ..llm_client import LLMClient

class ProductGenerator:
    """
    Module 5 & 6: Product Generation & Visual Intelligence
    Generates product concepts and constructs prompts for Flux/Midjourney using LLM.
    """
    
    def __init__(self):
        self.llm = LLMClient()
    
    def generate_products(
        self, 
        trend_data: TrendAnalysis, 
        empathy_map: EmpathyMap, 
        mode: AgentMode
    ) -> List[ProductConcept]:
        """
        Generate a list of products based on the trend and agent mode.
        """
        products = []
        dominant_emotion = trend_data.dominant_emotions[0]
        target_categories = self._select_categories(dominant_emotion, mode)
        
        for category in target_categories:
            concept = self._generate_single_concept(category, trend_data, empathy_map)
            products.append(concept)
            
        return products

    def _select_categories(self, emotion: Emotion, mode: AgentMode) -> List[ProductCategory]:
        """
        Select which 13 categories to activate.
        """
        # Logic from Table 1 (Matrix)
        if emotion == Emotion.FEAR_ANXIETY:
            return [ProductCategory.CHECKLISTS_SOP, ProductCategory.DIGITAL_PLANNERS, ProductCategory.APPAREL]
        elif emotion == Emotion.ANGER_OUTRAGE:
            return [ProductCategory.APPAREL, ProductCategory.STICKERS, ProductCategory.WALL_ART]
        elif emotion == Emotion.CONFUSION:
            return [ProductCategory.EDUCATIONAL_EBOOKS, ProductCategory.CHECKLISTS_SOP, ProductCategory.NOTION_SYSTEMS]
        elif emotion == Emotion.SURPRISE_SHOCK:
            return [ProductCategory.STICKERS, ProductCategory.APPAREL, ProductCategory.SOCIAL_TEMPLATES]
        else: # Joy
            return [ProductCategory.WALL_ART, ProductCategory.APPAREL, ProductCategory.AUDIO_PACKS]

    def _generate_single_concept(
        self, 
        category: ProductCategory, 
        trend: TrendAnalysis, 
        empathy: EmpathyMap
    ) -> ProductConcept:
        """
        Create a specific product concept using GPT-4o.
        """
        
        cat_def = CATEGORY_DEFINITIONS.get(category, {})
        engine_hint = cat_def.get("prompt_engine", "Midjourney")
        
        system_prompt = f"""
        You are a Product Designer for an algorithmic commerce brand.
        Create a product concept for the category: '{category.value}'.
        
        Context:
        - Emotion: {trend.dominant_emotions[0].value}
        - Consumer Thought: {empathy.think}
        - Consumer Saying: {empathy.say}
        
        Requirements:
        1. Title: Catchy, commercial title.
        2. Description: Persuasive 1-sentence description.
        3. Design Text (if Apparel/Sticker): A witty, viral slogan or phrase.
        4. Visual Prompt: A highly detailed prompt for {engine_hint}.
           - Use style keywords: {cat_def.get('logic', '')}
           - For Midjourney: Include --ar 2:3 or --ar 1:1
           - For Flux: Mention 'text rendering' if needed.
        
        Return JSON matching ProductConcept schema.
        """
        
        user_prompt = "Generate concept."
        
        try:
            concept = self.llm.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ProductConcept
            )
            # Ensure category_id is correct (LLM might hallucinate enum)
            concept.category_id = category
            return concept
        except Exception as e:
            print(f"LLM Product Gen failed: {e}")
            return self._fallback_concept(category, trend)

    def _fallback_concept(self, category: ProductCategory, trend: TrendAnalysis) -> ProductConcept:
        return ProductConcept(
            category_id=category,
            product_title=f"Generated {category.value}",
            description="AI Generated Product",
            visual_prompt=VisualPrompt(engine="Midjourney", prompt="Error", aspect_ratio="--ar 1:1")
        )
