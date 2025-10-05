import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

# Ensure root on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.context.phase3_context_builder import Phase3ContextBuilder


@pytest.mark.asyncio
async def test_retrieval_accepts_title_norm():
    builder = Phase3ContextBuilder()

    async def fake_retrieve(**kwargs):
        return [
            {
                'article_id': 1,
                'title_norm': 'Ceasefire Update',
                'url': 'https://example.com/article',
                'date': '2025-10-05',
                'lang': 'en',
                'snippet': 'Negotiators resume indirect talks.',
                'score': '0.87',
            }
        ]

    builder.retrieval_client = SimpleNamespace(retrieve=fake_retrieve)

    params = {
        'query': 'Israel–Hamas ceasefire talks',
        'window': '24h',
        'lang': 'auto',
        'sources': None,
        'k_final': 5,
        'flags': {'rerank_enabled': True},
    }
    feature_flags = {
        'auto_expand_window': False,
        'relax_filters_on_empty': False,
        'fallback_rerank_false_on_empty': False,
    }

    retrieval, warnings = await builder._perform_retrieval_with_recovery(params, feature_flags, 'ctx-test')

    assert not warnings
    assert retrieval['docs'], 'expected docs to be present'
    first_doc = retrieval['docs'][0]
    assert first_doc['title'] == 'Ceasefire Update'
    assert first_doc['score'] == 0.87
