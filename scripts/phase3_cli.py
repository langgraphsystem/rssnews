"""
Simple CLI to run Phase 3 orchestrator commands (/events link, /graph query).

Usage examples:
  python -m scripts.phase3_cli events --topic "AI" --lang en
  python -m scripts.phase3_cli graph --topic "AI governance" --lang en
  python -m scripts.phase3_cli events --docs sample_docs.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List


def _sample_docs() -> List[Dict[str, Any]]:
    return [
        {
            "article_id": f"d{i}",
            "title": f"Article {i} about AI governance and infra",
            "url": f"https://example.com/a{i}",
            "date": f"2025-09-2{i}",
            "lang": "en",
            "score": 0.65 + i * 0.03,
            "snippet": f"Short snippet {i}",
        }
        for i in range(1, 6)
    ]


def _build_context(command: str, topic: str, lang: str, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    now_cid = f"cli-{datetime.utcnow().strftime('%H%M%S')}"
    return {
        "command": command,
        "params": {"lang": lang, "window": "24h", "k_final": len(docs), "topic": topic},
        "retrieval": {
            "docs": docs,
            "window": "24h",
            "lang": lang,
            "sources": ["example.com"],
            "k_final": len(docs),
            "rerank_enabled": True,
        },
        "graph": {
            "enabled": command.startswith("/graph"),
            "entities": None,
            "relations": None,
            "build_policy": "on_demand" if command.startswith("/graph") else "cached_only",
            "hop_limit": 2,
        },
        "memory": {"enabled": False, "episodic": None, "semantic_keys": None},
        "models": {"primary": "gpt-5", "fallback": ["claude-4.5", "gemini-2.5-pro"]},
        "limits": {"max_tokens": 4096, "budget_cents": 50, "timeout_s": 12},
        "telemetry": {"correlation_id": now_cid, "version": "phase3-orchestrator"},
        "ab_test": {"experiment": "phase3-default", "arm": "A"},
    }


async def _run(args: argparse.Namespace) -> None:
    docs: List[Dict[str, Any]]
    if args.docs:
        with open(args.docs, "r", encoding="utf-8") as f:
            docs = json.load(f)
    else:
        docs = _sample_docs()

    if args.command == "events":
        ctx = _build_context("/events link", args.topic or "AI", args.lang, docs)
    else:
        ctx = _build_context("/graph query", args.topic or "AI", args.lang, docs)

    from services.orchestrator import execute_phase3_context

    resp = await execute_phase3_context(ctx)
    print(json.dumps(resp, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser("Phase 3 CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    common = {
        "topic": ("--topic", {"type": str, "default": None, "help": "Topic/query"}),
        "lang": ("--lang", {"type": str, "default": "en", "help": "Language (en|ru)"}),
        "docs": ("--docs", {"type": str, "default": None, "help": "Path to JSON docs array"}),
    }

    ev = sub.add_parser("events", help="Run /events link")
    for k, (flag, opts) in common.items():
        ev.add_argument(flag, **opts)

    gr = sub.add_parser("graph", help="Run /graph query")
    for k, (flag, opts) in common.items():
        gr.add_argument(flag, **opts)

    args = ap.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

