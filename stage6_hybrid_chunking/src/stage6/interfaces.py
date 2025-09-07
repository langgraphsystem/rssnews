"""Stage 6 interfaces: deterministic boundaries + optional LLM refine.

Functions here are thin wrappers that combine a simple deterministic
chunking pass with routing and LLM refinement. They are intentionally
lightweight and avoid coupling to the orchestration layer.
"""

from typing import Dict, List, Tuple
import logging

# Lazy import of LLM client within functions to avoid heavy imports during test collection

# Avoid importing chunker at module import time; import within function

logger = logging.getLogger(__name__)


def determine_boundaries(text: str, meta: Dict) -> List[Dict]:
    """Deterministic pass: paragraph/sentence-based chunking with scores."""
    # Lazy import to avoid heavy settings import at module import time
    from ..config.settings import get_settings
    settings = get_settings()
    if not text:
        return []
    # chunk_article returns list[dict] with boundary_confidence and semantic_type
    # Local import to avoid package path issues in tests
    try:
        from chunking_simple import chunk_article
    except Exception:
        # Fallback: relative import if package layout requires it
        from ....chunking_simple import chunk_article  # type: ignore
    chunks = chunk_article(
        text,
        meta,
        target_words=settings.chunking.target_words,
        short_min_words=max(30, settings.chunking.min_words // 2),
        long_para_words=max(300, settings.chunking.max_words),
        overlap_tokens=int(getattr(settings.chunking, 'overlap_tokens', 0) or 0)
    )
    # Ensure required fields
    for i, c in enumerate(chunks):
        c['chunk_index'] = i
        c.setdefault('boundary_confidence', 0.8)
        c.setdefault('semantic_type', 'body')
    logger.info("stage6.determine_boundaries", count=len(chunks))
    return chunks


def should_send_to_llm(chunk: Dict, signals: Dict) -> Tuple[bool, str]:
    """Basic routing heuristic used for ad-hoc calls (pipeline uses QualityRouter)."""
    from ..config.settings import get_settings
    settings = get_settings()
    # Simple rules: low boundary confidence, too short/too long
    bc = float(chunk.get('boundary_confidence', 0.0))
    wc = int(chunk.get('word_count_chunk', 0))
    target = settings.chunking.target_words
    too_short = wc < max(40, int(0.4 * target))
    too_long = wc > int(1.6 * target)
    if bc < 0.5 or too_short or too_long:
        return True, "low_confidence_or_length"
    return False, "ok"


def refine_boundaries(chunks: List[Dict], meta: Dict) -> List[Dict]:
    """Refine selected chunks with Gemini; fallback to deterministic if unavailable.

    Expects chunk dicts with keys: text, chunk_index, char_start/end, semantic_type.
    Adds llm_action/llm_confidence/llm_reason and may adjust semantic_type.
    """
    from ..config.settings import get_settings
    settings = get_settings()
    api_key = settings.gemini.api_key.get_secret_value() if settings.gemini.api_key else None
    if not api_key or not settings.features.llm_chunk_refine_enabled:
        # Tag all as noop
        for c in chunks:
            c.setdefault('llm_action', 'noop')
            c.setdefault('llm_confidence', 0.0)
            c.setdefault('llm_reason', 'disabled')
        return chunks

    # Lazy import router to avoid package import issues in isolated tests
    from ..chunking.quality_router import QualityRouter
    router = QualityRouter(settings)
    # Build minimal article metadata for routing
    art_meta = {
        'url': meta.get('url', ''),
        'quality_score': meta.get('quality_score', 0.5),
        'language_confidence': 1.0,
    }
    # Convert chunk dicts into pseudo RawChunk-like objects for the router
    from dataclasses import dataclass
    @dataclass
    class _RC:
        index: int
        text: str
        semantic_type: str
        importance_score: float
        word_count: int
        needs_review: bool = False

    rc_list = [
        _RC(index=int(c.get('chunk_index', i)),
            text=c.get('text', ''),
            semantic_type=c.get('semantic_type', 'body'),
            importance_score=0.5,
            word_count=c.get('word_count', len(c.get('text', '').split())),
            needs_review=c.get('needs_review', False))
        for i, c in enumerate(chunks)
    ]

    routed = router.route_chunks(rc_list, art_meta, batch_context={})

    # Prepare Gemini client
    from ..llm.gemini_client import GeminiClient, LLMRefinementResult
    client = GeminiClient(settings)
    refined: List[Dict] = [dict(c) for c in chunks]

    async def _refine_one(idx: int, c: Dict, decision) -> Dict:
        if not decision.should_use_llm:
            c.setdefault('llm_action', 'noop')
            c.setdefault('llm_confidence', 0.0)
            c.setdefault('llm_reason', 'not_routed')
            return c
        try:
            # Build minimal metadata for prompt selection
            meta_local = {
                'title': meta.get('title_norm', meta.get('title', '')),
                'source_domain': meta.get('source_domain', ''),
                'language': meta.get('language', 'en'),
                'published_at': str(meta.get('published_at', '')),
                'target_words': settings.chunking.target_words,
                'max_offset': settings.chunking.max_offset,
            }
            # Execute per-chunk refine
            result: LLMRefinementResult | None = await client.send_refinement_request(
                chunk_text=c.get('text', ''),
                chunk_metadata={
                    'chunk_index': int(c.get('chunk_index', idx)),
                    'char_start': int(c.get('char_start', 0)),
                    'char_end': int(c.get('char_end', 0)),
                    'semantic_type': c.get('semantic_type', 'body')
                },
                prompt_type='base'
            )
            if result is None:
                c.setdefault('llm_action', 'noop')
                c.setdefault('llm_confidence', 0.0)
                c.setdefault('llm_reason', 'fallback')
                return c
            # Map results (we do not change offsets here; only annotate)
            action_map = {
                'keep': 'noop',
                'merge_prev': 'merge_with_prev',
                'merge_next': 'merge_with_next',
                'drop': 'drop',
            }
            c['llm_action'] = action_map.get(result.action, 'noop')
            c['llm_confidence'] = float(result.confidence)
            c['llm_reason'] = result.reason or ''
            # Adjust semantic type if suggested
            if result.semantic_type:
                c['semantic_type'] = result.semantic_type
            return c
        except Exception as e:
            logger.warning("stage6.llm.refine.error", err=str(e))
            c.setdefault('llm_action', 'noop')
            c.setdefault('llm_confidence', 0.0)
            c.setdefault('llm_reason', 'error')
            return c

    import asyncio
    # Enforce LLM_MAX_SHARE and daily cost cap
    max_share = settings.rate_limit.max_llm_percentage_per_batch
    max_llm = max(0, int(len(refined) * max_share))
    chosen = 0
    spent_cap = float(getattr(settings.rate_limit, 'daily_cost_limit_usd', 0.0) or 0.0)
    budget_guard = spent_cap > 0.0
    # Sequential refinement to honor budget cap deterministically
    for i, (rc, dec) in enumerate(routed):
        c = refined[i]
        if not dec.should_use_llm or chosen >= max_llm:
            c.setdefault('llm_action', 'noop')
            c.setdefault('llm_confidence', 0.0)
            c.setdefault('llm_reason', 'not_routed_or_quota')
            continue
        # Budget check before call
        if budget_guard:
            try:
                stats = client.get_stats()
                if float(stats.get('estimated_cost_usd', 0.0)) >= spent_cap:
                    c.setdefault('llm_action', 'noop')
                    c.setdefault('llm_confidence', 0.0)
                    c.setdefault('llm_reason', 'budget_exceeded')
                    continue
            except Exception:
                pass
        # Do refine
        out = asyncio.get_event_loop().run_until_complete(_refine_one(rc.index, c, dec))
        refined[i] = out
        chosen += 1
    # Close client
    try:
        asyncio.get_event_loop().run_until_complete(client.close())
    except Exception:
        pass
    # Optionally apply edits safely
    if settings.features.apply_chunk_edits:
        try:
            # Build edits from annotations
            edits: List[Dict] = []
            # Merge groups: collect consecutive indices marked for merge
            merge_indices = []
            for c in refined:
                act = c.get('llm_action')
                if act in ('merge_with_prev', 'merge_with_next'):
                    merge_indices.append(int(c.get('chunk_index', 0)))
            merge_indices = sorted(set(merge_indices))
            if merge_indices:
                # Build consecutive groups
                group = [merge_indices[0]]
                for idx in merge_indices[1:]:
                    if idx == group[-1] + 1:
                        group.append(idx)
                    else:
                        if len(group) >= 2:
                            edits.append({'op': 'merge', 'indices': group.copy()})
                        group = [idx]
                if len(group) >= 2:
                    edits.append({'op': 'merge', 'indices': group.copy()})
            # Splits: simple mid-split for any marked 'split'
            for c in refined:
                if c.get('llm_action') == 'split':
                    t = c.get('text', '')
                    mid = max(1, len(t)//2)
                    edits.append({'op': 'split', 'index': int(c.get('chunk_index', 0)), 'rel_offsets': [mid]})
            # Retypes: if llm suggested type via semantic_type but action noop
            for c in refined:
                if c.get('llm_action') == 'noop' and c.get('semantic_type') in ('intro','quote','list','conclusion','code'):
                    edits.append({'op': 'retype', 'index': int(c.get('chunk_index', 0)), 'semantic_type': c.get('semantic_type')})
            if edits:
                applied = _apply_edits_safely(refined, edits)
                refined = applied
        except Exception as e:
            logger.warning("stage6.apply_edits.failed", err=str(e))
    logger.info("stage6.llm.refine.done", refined=sum(1 for c in refined if c.get('llm_action') != 'noop'))
    return refined


def _apply_edits_safely(chunks: List[Dict], edits: List[Dict]) -> List[Dict]:
    """Apply merge/split/retype edits; validate; rollback on failure.

    Edits format:
    - {'op': 'merge', 'indices': [i, j, ...]} merges consecutive chunks (by index order)
    - {'op': 'split', 'index': i, 'rel_offsets': [o1, o2, ...]} split chunk i at relative offsets (in characters)
    - {'op': 'retype', 'index': i, 'semantic_type': 'conclusion'} change type
    """
    orig = [dict(c) for c in chunks]
    try:
        # Work on a local copy
        work = [dict(c) for c in chunks]

        # Helper to recompute indices
        def renumber(ws: List[Dict]):
            for k, cc in enumerate(ws):
                cc['chunk_index'] = k

        # Apply edits in order
        for e in edits or []:
            op = e.get('op')
            if op == 'merge':
                idxs = sorted(set(int(i) for i in e.get('indices', [])))
                if not idxs:
                    continue
                # Must be consecutive
                for a, b in zip(idxs, idxs[1:]):
                    if b != a + 1:
                        raise ValueError('merge indices must be consecutive')
                first = idxs[0]
                last = idxs[-1]
                if first < 0 or last >= len(work):
                    raise IndexError('merge indices out of range')
                start = int(work[first]['char_start'])
                end = int(work[last]['char_end'])
                text = ''.join(work[i]['text'] for i in idxs)
                merged = dict(work[first])
                merged['text'] = text
                merged['char_start'] = start
                merged['char_end'] = end
                merged['word_count_chunk'] = len(text.split())
                merged['semantic_type'] = 'merged'
                # Replace range with single merged chunk
                new_work = work[:first] + [merged] + work[last+1:]
                work = new_work
                renumber(work)
            elif op == 'split':
                i = int(e.get('index'))
                rel_offsets = sorted(int(x) for x in e.get('rel_offsets', []))
                if i < 0 or i >= len(work):
                    raise IndexError('split index out of range')
                base = work[i]
                base_text = base.get('text', '')
                if not rel_offsets:
                    continue
                # Validate offsets strictly inside (not at bounds)
                if rel_offsets[0] <= 0 or rel_offsets[-1] >= len(base_text):
                    raise ValueError('split offsets out of bounds')
                # Build segments
                segments = []
                prev = 0
                for off in rel_offsets + [len(base_text)]:
                    seg_text = base_text[prev:off]
                    if not seg_text.strip():
                        raise ValueError('empty segment produced')
                    seg = dict(base)
                    seg['text'] = seg_text
                    seg['char_start'] = int(base['char_start']) + prev
                    seg['char_end'] = int(base['char_start']) + off
                    seg['word_count_chunk'] = len(seg_text.split())
                    segments.append(seg)
                    prev = off
                # Replace
                work = work[:i] + segments + work[i+1:]
                renumber(work)
            elif op == 'retype':
                i = int(e.get('index'))
                if i < 0 or i >= len(work):
                    raise IndexError('retype index out of range')
                st = e.get('semantic_type') or 'body'
                work[i]['semantic_type'] = st
            else:
                # Unknown op: ignore
                continue

        # Post-validate: strictly increasing, no overlaps, positive word counts
        if not _validate_no_overlap(work):
            raise ValueError('overlap detected')
        for cc in work:
            if int(cc['char_end']) <= int(cc['char_start']):
                raise ValueError('invalid range')
            if max(0, len(cc.get('text', '').split())) == 0:
                raise ValueError('empty text')
        return work
    except Exception:
        # Rollback
        for c in orig:
            c['llm_action'] = 'noop'
            c['llm_reason'] = 'post_check_failed'
        return orig


def _validate_no_overlap(chunks: List[Dict]) -> bool:
    last_end = 0
    for c in chunks:
        s = int(c.get('char_start', 0))
        e = int(c.get('char_end', 0))
        if s < last_end:
            return False
        last_end = e
    return True
