"""Simple deterministic chunker for Stage 6.

Implements paragraph/sentence-based chunking with semantic hints and boundary confidence.
No overlap to keep char ranges non-overlapping.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
PARA_SPLIT = re.compile(r"\n\s*\n")
LIST_BULLET = re.compile(r"^\s*([\-\*•]|\d+\.)\s+", re.MULTILINE)
QUOTE_LINE = re.compile(r"^>\s+", re.MULTILINE)
CODE_BLOCK = re.compile(r"```[\s\S]*?```|^\s{4,}.*$", re.MULTILINE)
HEADING_LINE = re.compile(r"^(#{1,6}\s+.+|[A-Z0-9][A-Z0-9\s\-:]{3,}$)")


def word_count(text: str) -> int:
    return len(text.split())


def _semantic_of_block(text: str) -> str:
    if CODE_BLOCK.search(text):
        return "code"
    if QUOTE_LINE.search(text):
        return "quote"
    if LIST_BULLET.search(text):
        return "list"
    if HEADING_LINE.search(text.strip().splitlines()[0] if text.strip().splitlines() else ""):
        return "intro"
    return "body"


def _split_long_paragraph(p_text: str, p_start: int, target_words: int) -> List[Tuple[str, int, int]]:
    """Split long paragraph by sentence boundaries, return list of (text, start, end)."""
    sentences = SENT_SPLIT.split(p_text)
    chunks: List[Tuple[str, int, int]] = []
    cursor = 0
    acc = []
    acc_start = 0
    acc_words = 0
    while cursor < len(p_text):
        break
    # Simpler: greedy by words, scanning by regex finditer
    parts = re.split(r"(\S+\s+)", p_text)
    acc_text = ""
    acc_wc = 0
    offset = 0
    start = 0
    for part in parts:
        if part is None:
            continue
        acc_text += part
        acc_wc += 1 if part.strip() else 0
        if acc_wc >= target_words:
            end = start + len(acc_text)
            chunks.append((acc_text.strip(), p_start + start, p_start + end))
            start = end
            acc_text = ""
            acc_wc = 0
    if acc_text.strip():
        end = start + len(acc_text)
        chunks.append((acc_text.strip(), p_start + start, p_start + end))
    return chunks


def chunk_article(clean_text: str,
                  meta: Dict,
                  target_words: int = 400,
                  short_min_words: int = 40,
                  long_para_words: int = 450,
                  overlap_tokens: int = 0) -> List[Dict]:
    """Chunk clean_text into chunks with char offsets and semantic tags.

    Returns list of dicts with: chunk_index, text, word_count_chunk, char_start, char_end,
    semantic_type, boundary_confidence.
    """
    if not clean_text:
        return []

    chunks: List[Dict] = []
    paragraphs = PARA_SPLIT.split(clean_text)

    # Compute char offsets for paragraphs by scanning original text
    idx = 0
    para_offsets: List[Tuple[str, int, int]] = []
    for p in paragraphs:
        start = clean_text.find(p, idx)
        if start == -1:
            start = idx
        end = start + len(p)
        para_offsets.append((p, start, end))
        idx = end

    acc_text = ""
    acc_start = None
    acc_end = None
    acc_words = 0
    acc_sem_types: List[str] = []
    boundary_conf = 1.0

    def flush_chunk():
        nonlocal acc_text, acc_start, acc_end, acc_words, acc_sem_types, boundary_conf
        if acc_text.strip() and acc_start is not None and acc_end is not None:
            semantic = "body"
            if acc_sem_types:
                # choose most specific: intro > list > quote > code > body
                order = {"intro": 5, "list": 4, "quote": 3, "code": 2, "body": 1}
                semantic = sorted(acc_sem_types, key=lambda s: -order.get(s, 0))[0]
            chunks.append({
                'chunk_index': len(chunks),
                'text': acc_text.strip(),
                'word_count_chunk': acc_words,
                'char_start': acc_start,
                'char_end': acc_end,
                'semantic_type': semantic,
                'boundary_confidence': boundary_conf,
                'llm_action': 'noop',
                'llm_confidence': 0.0,
                'llm_reason': None,
            })
        acc_text = ""
        acc_start = None
        acc_end = None
        acc_words = 0
        acc_sem_types = []
        boundary_conf = 1.0

    for p_text, p_start, p_end in para_offsets:
        wc = word_count(p_text)
        sem = _semantic_of_block(p_text)
        if wc > long_para_words:
            # split into subparts
            subparts = _split_long_paragraph(p_text, p_start, target_words)
            for sp_text, sp_start, sp_end in subparts:
                sp_wc = word_count(sp_text)
                # flush accumulator if adding would exceed target
                if acc_words + sp_wc > target_words and acc_text:
                    flush_chunk()
                # start new if empty
                if acc_start is None:
                    acc_start = sp_start
                acc_text += ("\n\n" if acc_text else "") + sp_text
                acc_end = sp_end
                acc_words += sp_wc
                acc_sem_types.append(sem)
                # sentence-level split => slightly lower confidence
                boundary_conf = min(boundary_conf, 0.7)
                if acc_words >= target_words:
                    flush_chunk()
            # prefer paragraph boundary for next
            boundary_conf = min(boundary_conf, 1.0)
            continue

        # Short paragraph: consider merging
        if wc < short_min_words and sem not in ("intro", "list"):
            if acc_start is None:
                acc_start = p_start
            acc_text += ("\n\n" if acc_text else "") + p_text
            acc_end = p_end
            acc_words += wc
            acc_sem_types.append(sem)
            if acc_words >= target_words:
                flush_chunk()
            # keep going to accumulate
            continue

        # Normal paragraph
        # If accumulator has content and adding this would exceed target, flush first
        if acc_words > 0 and acc_words + wc > target_words:
            flush_chunk()
        if acc_start is None:
            acc_start = p_start
        acc_text += ("\n\n" if acc_text else "") + p_text
        acc_end = p_end
        acc_words += wc
        acc_sem_types.append(sem)
        # paragraph boundary leads to high confidence
        boundary_conf = min(boundary_conf, 1.0)
        if acc_words >= target_words:
            flush_chunk()

    # Flush remainder
    flush_chunk()

    # First/last chunk semantic hints
    if chunks:
        chunks[0]['semantic_type'] = 'intro' if chunks[0]['semantic_type'] in ('intro', 'body') else chunks[0]['semantic_type']
        chunks[-1]['semantic_type'] = 'conclusion' if chunks[-1]['semantic_type'] in ('body',) else chunks[-1]['semantic_type']

    # Add contextual overlap text (reading-only), without changing offsets
    if overlap_tokens and chunks:
        n = len(clean_text)
        for c in chunks:
            s = int(c['char_start'])
            e = int(c['char_end'])
            ext_s = max(0, s - overlap_tokens)
            ext_e = min(n, e + overlap_tokens)
            c['text_ctx'] = clean_text[ext_s:ext_e]
    else:
        for c in chunks:
            c['text_ctx'] = c['text']

    return chunks
