#!/usr/bin/env python3
import os
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
print(f"Проверяю ключ: {api_key[:20]}...{api_key[-10:]}")

client = OpenAI(api_key=api_key)
result = client.embeddings.create(
    input=['test'],
    model='text-embedding-3-large'
)

print(f"✅ API ключ валидный!")
print(f"Размерность: {len(result.data[0].embedding)}")
print(f"Первые 5 значений: {result.data[0].embedding[:5]}")
