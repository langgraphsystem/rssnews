from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from datetime import datetime
from .constants import Emotion, TrendLifecycle, ProductCategory, AgentMode

# === 2.3 Карта эмпатии ===
class EmpathyMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    think: str = Field(..., description="Внутренние тревоги, надежды, невысказанные мысли")
    feel: str = Field(..., description="Непосредственная эмоциональная реакция")
    say: str = Field(..., description="Вернакуляр, хештеги, сленг")
    do: str = Field(..., description="Поисковое поведение, действия")

# === 3. Анализ тренда ===
class TrendAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lifecycle_stage: TrendLifecycle
    velocity_score: float = Field(..., ge=0.0, le=10.0, description="Скорость тренда (0-10)")
    dominant_emotions: List[Emotion]
    empathy_map: EmpathyMap
    commercial_viability_score: float = Field(..., description="Оценка коммерческой пригодности")

# === 6. Визуальные промпты ===
class VisualPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: str = Field(..., description="Midjourney V6 или Flux.1")
    prompt: str = Field(..., description="Сконструированный промпт")
    aspect_ratio: str = Field(..., description="--ar 2:3 и т.д.")
    negative_prompt: Optional[str] = None

# === 5. Продукт ===
class ProductConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: ProductCategory
    product_title: str
    description: str
    design_text: Optional[str] = Field(None, description="Текст для нанесения (для POD)")
    visual_prompt: Optional[VisualPrompt] = None
    file_structure: Optional[str] = Field(None, description="Для цифровых товаров (структура PDF/Notion) в виде текста")
    price_point_suggestion: Optional[str] = None

# === 7. Маркетинг (TikTok) ===
class TikTokCampaign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hook_type: str = Field(..., description="Tension, Curiosity Gap, Visual, Contrarian")
    script_audio: str = Field(..., description="Рекомендация по звуку/музыке")
    script_visual: str = Field(..., description="Описание визуального ряда")
    caption: str = Field(..., description="Текст поста с хештегами")
    hashtags: List[str]

class SeoTags(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amazon_kdp: List[str] = Field(..., description="Long-tail keywords")
    etsy: List[str] = Field(..., description="Aesthetic/Occasion keywords")

class MarketingAssets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tiktok_campaign: TikTokCampaign
    seo_tags: SeoTags

# === 8. Юридическая безопасность ===
class LegalCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(..., description="PASSED / FLAGGED / FAILED")
    flagged_terms: List[str]
    risk_level: str = Field(..., description="Low / Medium / High")
    notes: Optional[str] = None

# === 10. Воронки ===
class FunnelStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_name: str
    core_product: str
    order_bump: str
    upsell: str
    logic: str

class UCAMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_mode: str
    timestamp: str
    source_id: str

# === 12.1 Итоговая структура (Root) ===
class UCAOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: UCAMeta = Field(..., description="agent_mode, timestamp, source_id")
    trend_analysis: TrendAnalysis
    commercial_opportunities: List[ProductConcept]
    marketing_assets: MarketingAssets
    legal_check: LegalCheck
    funnel_strategy: FunnelStrategy

# === 13. Глубокий анализ статьи ===
class DeepArticleAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    keywords: List[str] = Field(default_factory=list, description="1. Ключевые слова и словосочетания")
    main_ideas: List[str] = Field(default_factory=list, description="2. Основные идеи и тезисы")
    triggers: Dict[str, List[str]] = Field(default_factory=dict, description="3. Триггеры (эмоциональные, мотивационные, CTA)")
    trends: List[str] = Field(default_factory=list, description="4. Тренды и тенденции")
    target_audience: str = Field(default="", description="5. ЦА (целевая аудитория)")
    tone_style: str = Field(default="", description="6. Тональность и стиль")
    structure_format: str = Field(default="", description="7. Структура и формат подачи")
    facts_data: List[str] = Field(default_factory=list, description="8. Факты, данные и выводы")
    insights: List[str] = Field(default_factory=list, description="9. Потенциальные инсайты")
    practical_utility: List[str] = Field(default_factory=list, description="10. Формулы, модели, чек-листы")

    @field_validator('triggers', mode='before')
    @classmethod
    def parse_triggers(cls, v):
        if isinstance(v, list):
            # If model returns a list instead of dict, wrap it in a default key
            # Also normalize items if they are dicts
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    new_list.append(" ".join(str(val) for val in item.values()))
                else:
                    new_list.append(str(item))
            return {"general": new_list}
            
        if isinstance(v, dict):
            for key, value in v.items():
                if isinstance(value, str):
                    # Split by comma or newline if it's a string
                    v[key] = [item.strip() for item in value.replace('\n', ',').split(',') if item.strip()]
                elif isinstance(value, list):
                    # Check if list items are dicts
                    new_list = []
                    for item in value:
                        if isinstance(item, dict):
                            new_list.append(" ".join(str(val) for val in item.values()))
                        else:
                            new_list.append(str(item))
                    v[key] = new_list
        return v

    @field_validator('keywords', 'main_ideas', 'trends', 'facts_data', 'insights', 'practical_utility', mode='before')
    @classmethod
    def normalize_string_list(cls, v):
        if isinstance(v, dict):
            # If model returns dict instead of list, flatten all values
            result = []
            for key, value in v.items():
                if isinstance(value, list):
                    result.extend(value)
                else:
                    result.append(str(value))
            return result
            
        if isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    # Extract values from dict if model returns objects instead of strings
                    new_list.append(" ".join(str(val) for val in item.values()))
                else:
                    new_list.append(str(item))
            return new_list
        return v

    @field_validator('target_audience', 'tone_style', 'structure_format', mode='before')
    @classmethod
    def normalize_string_field(cls, v):
        if isinstance(v, dict):
            # Try to find a likely key containing the text
            for key in ['description', 'value', 'text', 'content']:
                if key in v and isinstance(v[key], str):
                    return v[key]
            # Fallback: join all string values
            return " ".join(str(val) for val in v.values() if isinstance(val, (str, int, float)))
        
        if isinstance(v, list):
            return " ".join(str(item) for item in v)
            
        return str(v)

