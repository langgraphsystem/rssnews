from enum import Enum
from typing import Dict, List, Any

# === 2.2 Психологическое профилирование ===

class Emotion(str, Enum):
    FEAR_ANXIETY = "Fear / Anxiety"
    ANGER_OUTRAGE = "Anger / Outrage"
    JOY_NOSTALGIA = "Joy / Nostalgia"
    CONFUSION = "Confusion"
    SURPRISE_SHOCK = "Surprise / Shock"

# Матрица трансмутации эмоций (Таблица 1)
EMOTION_TRANSMUTATION_MATRIX = {
    Emotion.FEAR_ANXIETY: {
        "driver": "Желание контроля, подготовки, безопасности",
        "formats": ["Checklists", "Planners", "SOPs", "Survival Guides"],
        "logic": "Страх вызывает потребность в структуре. Продукты, снижающие неопределенность."
    },
    Emotion.ANGER_OUTRAGE: {
        "driver": "Сигнализация идентичности, Протест, Принадлежность",
        "formats": ["Apparel (T-shirts)", "Stickers", "SVG Slogans"],
        "logic": "Эмоция высокой активации. Импульсивные покупки для заявления позиции."
    },
    Emotion.JOY_NOSTALGIA: {
        "driver": "Празднование, Сохранение памяти, Эстетика",
        "formats": ["Wall Art", "Posters", "Cards"],
        "logic": "Позитивные эмоции якорят чувство в пространстве. Ностальгия стимулирует коллекционирование."
    },
    Emotion.CONFUSION: {
        "driver": "Жажда знаний, Ясность, Понимание",
        "formats": ["E-books", "Mini-courses", "Webinars", "Guides"],
        "logic": "Сложные новости требуют объяснения. Спрос на экспертный контент."
    },
    Emotion.SURPRISE_SHOCK: {
        "driver": "Поиск новизны, Социальный обмен",
        "formats": ["Memes", "TikTok Filters", "Viral Merch"],
        "logic": "Высокая социальная скорость. Продукты должны быть визуальными и готовыми к репостам."
    }
}

# === 3.1 Жизненный цикл тренда ===

class TrendLifecycle(str, Enum):
    ULTRA_HYPE = "Ultra-Hype (Micro-trend)"       # 48h - 1 week
    SHORT_TERM_SHIFT = "Short-Term Shift"         # 1 - 6 months
    LONG_TERM_SHIFT = "Long-Term Shift (Macro)"   # Years

# === 5. 13 Коммерческих товарных категорий ===

class ProductCategory(str, Enum):
    # 5.1 Физическая печать (POD)
    APPAREL = "Apparel (T-shirts/Hoodies)"
    WALL_ART = "Wall Art / Posters"
    STICKERS = "Stickers / Decals"
    
    # 5.2 Цифровые загрузки (Потребительские)
    DIGITAL_PLANNERS = "Digital Planners / Journals"
    EDUCATIONAL_EBOOKS = "Educational E-books / Mini-courses"
    CHECKLISTS_SOP = "Checklists / SOPs"
    WORKSHEETS = "Worksheets / Activities"
    
    # 5.3 Креативные активы (B2B/Creator)
    SVG_CRAFT_FILES = "SVG / Craft Files"
    MODELS_3D = "3D Models / Print Files"
    AUDIO_PACKS = "Audio / Sound Packs"
    
    # 5.4 Бизнес и маркетинг
    SOCIAL_TEMPLATES = "Social Media Templates"
    NOTION_SYSTEMS = "Notion Systems"
    STOCK_MEDIA = "Stock Media Assets"

# Описания категорий для Агента
CATEGORY_DEFINITIONS = {
    ProductCategory.APPAREL: {
        "logic": "Извлекает короткие, высококонтрастные лозунги. Гнев/Юмор.",
        "prompt_engine": "Flux.1 (Text rendering)"
    },
    ProductCategory.WALL_ART: {
        "logic": "Фокус на Эстетике и Вдохновении. Абстрактные темы.",
        "prompt_engine": "Midjourney V6 (Artistic style)"
    },
    ProductCategory.STICKERS: {
        "logic": "Микро-выражение. Высококонтекстные шутки.",
        "prompt_engine": "Flux.1 (Vector contours)"
    },
    ProductCategory.DIGITAL_PLANNERS: {
        "logic": "Потребность в отслеживании привычек или управлении.",
        "output": "PDF structures"
    },
    ProductCategory.EDUCATIONAL_EBOOKS: {
        "logic": "Активируется Замешательством. Главы, цели обучения.",
        "output": "Text Content"
    },
    ProductCategory.CHECKLISTS_SOP: {
        "logic": "Немедленная полезность. Правила/Безопасность -> Действия.",
        "output": "One-page forms"
    },
    ProductCategory.WORKSHEETS: {
        "logic": "Интерактивное обучение (дети/студенты).",
        "output": "Line art prompts"
    },
    ProductCategory.SVG_CRAFT_FILES: {
        "logic": "DIY/Cricut рынок. Лозунги и иконография.",
        "prompt_engine": "Flux.1 (B&W Vector)"
    },
    ProductCategory.MODELS_3D: {
        "logic": "Нишевые новости об оборудовании.",
        "output": "Descriptions/Depth maps"
    },
    ProductCategory.AUDIO_PACKS: {
        "logic": "Настроение/Амбиент.",
        "output": "Audio Gen Prompts"
    },
    ProductCategory.SOCIAL_TEMPLATES: {
        "logic": "Для инфлюенсеров. Canva style.",
        "output": "Layout descriptions"
    },
    ProductCategory.NOTION_SYSTEMS: {
        "logic": "Высокомаржинальная цифровая организация.",
        "output": "JSON Schema for DB"
    },
    ProductCategory.STOCK_MEDIA: {
        "logic": "B2B для новостников.",
        "prompt_engine": "Midjourney (Editorial photo)"
    }
}

# === 11. Режимы работы ===
class AgentMode(str, Enum):
    CREATOR = "Creator Mode"       # Focus: Virality, Risk: High
    STORE_OWNER = "Store Owner"    # Focus: Margin, Risk: Low
    CONSULTING = "Consulting Mode" # Focus: B2B, Tone: Academic
