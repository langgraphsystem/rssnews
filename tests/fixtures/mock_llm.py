from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MockLLMStats:
    total_tokens: int = 0
    total_cost: float = 0.0


class MockGeminiClient:
    def __init__(self, settings):
        self.settings = settings
        self._stats = MockLLMStats()

    async def send_refinement_request(self, chunk_text: str, chunk_metadata: Dict, prompt_type: str):
        # Deterministic behavior based on content
        text = chunk_text.strip()
        wc = len(text.split())
        action = 'keep'
        reason = 'ok'
        semantic_type = chunk_metadata.get('semantic_type', 'body')
        if wc < 8:
            action = 'merge_prev'
            reason = 'short_chunk'
        elif wc > 120:
            action = 'split'
            reason = 'long_chunk'
        elif text.startswith('Note:'):
            action = 'keep'
            semantic_type = 'intro'
            reason = 'note_intro'
        # Update accounting
        self._stats.total_tokens += max(1, len(text) // 4)
        self._stats.total_cost += 0.02
        from stage6_hybrid_chunking.src.llm.gemini_client import LLMRefinementResult
        return LLMRefinementResult(action=action, offset_adjust=0, semantic_type=semantic_type, confidence=0.9, reason=reason)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Return deterministic 8-dim vectors
        out = []
        for i, _ in enumerate(texts):
            out.append([float((i + j) % 10) / 10.0 for j in range(8)])
        # Update accounting (rough)
        self._stats.total_tokens += sum(max(1, len(t) // 4) for t in texts)
        self._stats.total_cost += 0.01 * len(texts)
        return out

    def get_stats(self):
        return {
            'total_requests': 0,
            'total_tokens': self._stats.total_tokens,
            'estimated_cost_usd': self._stats.total_cost,
            'circuit_breaker_state': 'closed'
        }

    async def close(self):
        return None

