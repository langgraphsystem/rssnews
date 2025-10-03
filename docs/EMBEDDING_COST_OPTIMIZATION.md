# Оптимизация стоимости эмбеддингов

## 🔍 Текущая ситуация

### Используемая модель:
**OpenAI text-embedding-3-large**
- Размерность: 3072
- Цена: **$0.00013 за 1K токенов**

### Текущая реализация:

**Файл:** `local_embedding_generator.py:23-45`

```python
async def generate_embeddings(self, texts: List[str]):
    embeddings = []

    # ❌ ПРОБЛЕМА: По одному запросу на каждый текст!
    for i, text in enumerate(texts):
        embedding = await self._generate_single_embedding(client, text)
        embeddings.append(embedding)
```

**Файл:** `services/embedding_service.py:56-61`
```python
texts = [chunk.get('text', '') for chunk in chunks]  # batch_size=1500

# Вызывает generate_embeddings с 1500 текстами
embeddings = await self.generator.generate_embeddings(texts)
# → НО внутри делает 1500 отдельных HTTP запросов!
```

---

## ❌ Проблемы текущей реализации

### 1. **Нет настоящего батчинга**

Код делает вид что батчит:
- `EmbeddingService` получает 1500 chunks за раз
- Передает все в `generate_embeddings(texts)`
- **НО:** внутри цикл `for text in texts` → 1500 HTTP запросов!

### 2. **Медленная скорость**

- 1500 chunks × ~1 секунда HTTP = **~25 минут**
- Вместо 1 запроса за ~5 секунд

### 3. **Rate limits**

OpenAI лимиты для tier 1:
- **3,500 requests/minute**
- При 1500 запросах за 25 минут = ~60 RPM (в пределах лимита)
- Но неэффективно используем квоту

### 4. **Стоимость НЕ меняется** ⚠️

Важно понять:
```
Стоимость = Количество токенов × $0.00013/1K

1 запрос × 1000 токенов = $0.13
10 запросов × 100 токенов каждый = $0.13 (ТА ЖЕ ЦЕНА!)

Батчинг НЕ снижает стоимость OpenAI!
```

---

## 💰 Можно ли СНИЗИТЬ стоимость?

### ❌ Батчинг не поможет

OpenAI считает по токенам, не по запросам.

### ✅ ЧТО ДЕЙСТВИТЕЛЬНО снизит стоимость:

#### 1. **Вернуться на локальную модель embeddinggemma**

**Текущая стоимость:**
- 203,727 chunks × 750 tokens × $0.00013/1K = **$19.86** (уже потрачено)
- ~1000 новых статей/месяц = **$0.49/месяц**

**С embeddinggemma:**
- **$0.00** (полностью бесплатно)
- Работает через Ollama локально

**Недостатки:**
- Размерность: 768 вместо 3072
- Качество: немного ниже
- Скорость: медленнее (~2-3 сек на chunk)

**Код уже есть!** Просто не используется:
```python
# local_embedding_generator.py уже настроен на embeddinggemma
# Просто где-то переопределяется на OpenAI
```

---

#### 2. **Использовать text-embedding-3-small**

**Стоимость:** $0.00002 за 1K токенов (**в 6.5 раз дешевле!**)

```
Сейчас: 750 tokens × $0.00013/1K = $0.0000975 за chunk
Small:  750 tokens × $0.00002/1K = $0.000015 за chunk

Экономия: 84% дешевле!
```

**Размерность:** 1536 (вместо 3072)

**Качество:** Незначительно ниже для большинства задач

---

#### 3. **Фильтровать chunks перед генерацией**

Не генерировать эмбеддинги для:
- Очень коротких chunks (<50 слов)
- Дублирующихся chunks
- Low-quality контента (ads, boilerplate)

**Экономия:** ~10-20%

---

#### 4. **Кэшировать похожие chunks**

Если chunk очень похож на существующий (95%+ similarity), использовать тот же эмбеддинг.

**Экономия:** ~5-10% для новостных сайтов с шаблонами

---

## 🚀 Рекомендации

### Вариант 1: Батчинг для СКОРОСТИ (не стоимости)

**Цель:** Ускорить генерацию в ~100 раз

**Изменения в `local_embedding_generator.py`:**

```python
async def generate_embeddings(self, texts: List[str], batch_size: int = 100):
    """Generate embeddings with TRUE batching"""

    if not texts:
        return []

    embeddings = []

    # Разбиваем на батчи по 100 (лимит OpenAI = 2048)
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        try:
            # ОДИН запрос для всего батча
            batch_embeddings = await self._generate_batch_embeddings(batch)
            embeddings.extend(batch_embeddings)

            logger.info(f"Generated {len(embeddings)}/{len(texts)} embeddings")

        except Exception as e:
            logger.error(f"Batch failed: {e}")
            # Fallback: по одному
            for text in batch:
                emb = await self._generate_single_embedding(client, text)
                embeddings.append(emb)

    return embeddings

async def _generate_batch_embeddings(self, texts: List[str]):
    """Generate embeddings for batch via OpenAI API"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = await client.embeddings.create(
        model="text-embedding-3-large",
        input=texts  # Весь батч одним запросом!
    )

    return [item.embedding for item in response.data]
```

**Результат:**
- ⚡ Скорость: 1500 chunks за ~30 секунд (вместо 25 минут)
- 💸 Стоимость: **та же** ($0.00013/1K tokens)

---

### Вариант 2: Переход на text-embedding-3-small

**Экономия:** 84% стоимости

```python
# .env
EMBEDDING_MODEL=text-embedding-3-small

# Изменить размерность pgvector
ALTER TABLE article_chunks DROP COLUMN embedding_vector;
ALTER TABLE article_chunks ADD COLUMN embedding_vector vector(1536);
```

**Стоимость:**
- Было: $0.49/месяц
- Станет: **$0.08/месяц**

---

### Вариант 3: Вернуться на embeddinggemma (локально)

**Экономия:** 100% стоимости

**Найти где используется OpenAI:**
```bash
# Поискать где переопределяется на OpenAI
grep -r "text-embedding-3-large" .
grep -r "OpenAI" services/
grep -r "embeddings.create" .
```

**Изменить обратно на локальную модель**

**Стоимость:** **$0.00/месяц**

---

## 📊 Сравнение вариантов

| Вариант | Скорость | Стоимость/месяц | Качество | Сложность |
|---------|----------|-----------------|----------|-----------|
| **Текущий (без батчинга)** | 🐢 Медленно | $0.49 | ⭐⭐⭐⭐⭐ | - |
| **Батчинг OpenAI** | ⚡ Быстро | $0.49 | ⭐⭐⭐⭐⭐ | Легко |
| **text-embedding-3-small** | ⚡ Быстро | **$0.08** | ⭐⭐⭐⭐ | Средне |
| **embeddinggemma (local)** | 🐢 Медленно | **$0.00** | ⭐⭐⭐ | Нужно найти где OpenAI |

---

## 🎯 Итоговая рекомендация

### Короткий срок (сейчас):
✅ **Внедрить батчинг** для ускорения (не снижает стоимость, но ускоряет в ~100 раз)

### Средний срок (если бюджет критичен):
✅ **Переход на text-embedding-3-small** - экономия 84%, почти такое же качество

### Долгий срок (если $0.49/мес не проблема):
✅ **Оставить как есть** - лучшее качество, небольшая стоимость

---

## 💡 Главный вывод

**Батчинг НЕ снизит стоимость OpenAI API!**

Стоимость = количество токенов × цена.
Батчинг только ускоряет запросы.

Чтобы снизить стоимость:
1. Более дешевая модель (3-small)
2. Локальная модель (embeddinggemma)
3. Фильтрация chunks
4. Кэширование

**Текущая стоимость $0.49/месяц - это очень мало.**
Возможно, не стоит оптимизировать.
