#!/usr/bin/env python3
"""
Live test for /summarize and /aggregate using real GPT-5 (OpenAI Responses API)
and live RankingAPI fetch (Postgres), if PG_DSN is available.

Usage: python tests/run_live_gpt.py "query" [timeframe]

Defaults:
- timeframe: 1w (maps to 7d in RankingAPI filters)
"""

import os
import sys
import asyncio
from datetime import datetime


def _safe(a, *keys):
    for k in keys:
        v = a.get(k)
        if v:
            return v
    return ""


async def fetch_articles(query: str, timeframe: str = "1w", limit: int = 20):
    # Map timeframe to RankingAPI filter windows
    tmap = {"1w": "7d", "7d": "7d", "3d": "3d", "1d": "24h", "30d": "30d"}
    fr = tmap.get(timeframe, "7d")

    from ranking_api import RankingAPI, SearchRequest
    api = RankingAPI()
    req = SearchRequest(
        query=query,
        method='hybrid',
        limit=limit,
        filters={'time_range': fr},
        explain=False,
    )
    resp = await api.search(req)
    # Normalize to expected fields
    arts = []
    for r in resp.results[:limit]:
        arts.append({
            'title': _safe(r, 'title_norm', 'title', 'name'),
            'content': _safe(r, 'text', 'clean_text', 'content', 'description', 'summary'),
            'url': _safe(r, 'url'),
            'source': _safe(r, 'source', 'domain', 'source_domain'),
            'source_domain': _safe(r, 'domain', 'source_domain', 'source'),
            'published_at': r.get('published_at') or r.get('date')
        })
    return arts, resp


def build_summary_prompt(topic: str, articles, length: str, timeframe: str):
    # Match bot_service/advanced_bot.py summarize style
    prompt_slice = articles[:20]
    from bot_service.advanced_bot import AdvancedRSSBot  # for _format method constraints
    # Minimal inline formatter (avoid instantiating bot): mimic slicing and fields
    def _format_articles_for_gpt(arts):
        lines = []
        for i, a in enumerate(arts[:20], start=1):
            title = (a.get('title') or a.get('headline') or a.get('name') or 'No title')[:100]
            content = (a.get('content') or a.get('description') or a.get('summary') or a.get('text') or '')[:500]
            lines.append(f"Article {i}:\nTitle: {title}\nContent: {content}\n---\n")
        return "\n".join(lines)

    styles = {
        'short': 'brief bullet points',
        'medium': 'structured paragraphs',
        'detailed': 'comprehensive analysis',
        'executive': 'executive summary format',
    }
    style = styles.get(length, styles['medium'])
    return f"""Create a {style} summary of the following {len(prompt_slice)} news articles about '{topic}':

ARTICLES:
{_format_articles_for_gpt(prompt_slice)}

Requirements:
- Style: {style}
- Focus on key developments, trends, and implications
- Include specific dates and figures when available
- Highlight the most important insights
- Use clear formatting with emojis"""


def build_aggregate_prompt(metric: str, groupby: str, timeframe: str, articles):
    prompt_slice = articles[:20]
    def _format_articles_for_gpt_md(arts):
        lines = []
        for i, a in enumerate(arts[:20], start=1):
            title = (a.get('title') or a.get('headline') or a.get('name') or 'No title')[:100]
            content = (a.get('content') or a.get('description') or a.get('summary') or a.get('text') or '')[:500]
            src = (a.get('source') or a.get('domain') or a.get('source_domain') or 'Unknown')
            date = a.get('published_at') or 'Unknown date'
            lines.append(f"Article {i}:\nTitle: {title}\nContent: {content}\nSource: {src}\nDate: {date}\n---\n")
        return "\n".join(lines)
    return f"""Analyze and aggregate the following {len(prompt_slice)} news articles:

TASK: Aggregate '{metric}' grouped by '{groupby}' for timeframe '{timeframe}'

DATA:
{_format_articles_for_gpt_md(prompt_slice)}

Provide:
1. Clear statistical breakdown
2. Key patterns and trends
3. Top categories/sources/topics
4. Percentage distributions
5. Notable insights

Format with charts, tables, and visual elements using emojis."""


def main():
    if len(sys.argv) < 2:
        print("Usage: python tests/run_live_gpt.py \"query\" [timeframe]")
        sys.exit(1)
    query = sys.argv[1]
    timeframe = sys.argv[2] if len(sys.argv) > 2 else '1w'

    # Ensure OPENAI_API_KEY is present
    if not os.environ.get('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY not set in environment")
        sys.exit(2)

    # Prefer remote Ollama endpoint if local is not available
    if not os.environ.get('OLLAMA_BASE_URL'):
        os.environ['OLLAMA_BASE_URL'] = 'https://ollama.nexlify.solutions'

    # Fetch articles via RankingAPI
    arts, resp = asyncio.run(fetch_articles(query, timeframe=timeframe))
    print(f"Fetched {len(arts)} articles; method={resp.search_method}; total={resp.total_results}; time={resp.response_time_ms}ms")

    # Build and send /summarize
    from gpt5_service_new import create_gpt5_service
    gpt = create_gpt5_service('gpt-5')

    sum_prompt = build_summary_prompt(query, arts, length='detailed', timeframe=timeframe)
    sum_out = gpt.send_chat(sum_prompt, max_output_tokens=800)
    print("\n=== /summarize OUTPUT (first 800 chars) ===\n", (sum_out or '')[:800])

    # Build and send /aggregate
    agg_prompt = build_aggregate_prompt('count', 'day', timeframe, arts)
    agg_out = gpt.send_analysis(agg_prompt, max_output_tokens=800)
    print("\n=== /aggregate OUTPUT (first 800 chars) ===\n", (agg_out or '')[:800])


if __name__ == '__main__':
    main()

