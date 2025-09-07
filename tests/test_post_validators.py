from stage6_hybrid_chunking.src.stage6.interfaces import _apply_edits_safely


def build_chunk(s, e, text, idx=0, sem='body'):
    return {
        'chunk_index': idx,
        'char_start': s,
        'char_end': e,
        'text': text,
        'word_count_chunk': len(text.split()),
        'semantic_type': sem,
    }


def test_merge_two_chunks():
    t = "Hello world. This is a test."
    c0 = build_chunk(0, 12, t[0:12], 0)
    c1 = build_chunk(12, len(t), t[12:], 1)
    edits = [{'op': 'merge', 'indices': [0, 1]}]
    out = _apply_edits_safely([c0, c1], edits)
    assert len(out) == 1
    assert out[0]['char_start'] == 0 and out[0]['char_end'] == len(t)
    assert out[0]['semantic_type'] == 'merged'


def test_split_into_three_segments():
    t = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    c = build_chunk(0, len(t), t, 0)
    # Split at 8 and 16
    edits = [{'op': 'split', 'index': 0, 'rel_offsets': [8, 16]}]
    out = _apply_edits_safely([c], edits)
    assert len(out) == 3
    assert out[0]['char_start'] == 0 and out[0]['char_end'] == 8
    assert out[1]['char_start'] == 8 and out[1]['char_end'] == 16
    assert out[2]['char_start'] == 16 and out[2]['char_end'] == len(t)


def test_retype_intro_to_conclusion():
    t = "Intro paragraph"
    c = build_chunk(0, len(t), t, 0, sem='intro')
    edits = [{'op': 'retype', 'index': 0, 'semantic_type': 'conclusion'}]
    out = _apply_edits_safely([c], edits)
    assert out[0]['semantic_type'] == 'conclusion'


def test_invalid_edit_triggers_rollback():
    t = "abcdefg"
    c = build_chunk(0, len(t), t, 0)
    # Invalid split: offsets including bounds cause empty segment
    edits = [{'op': 'split', 'index': 0, 'rel_offsets': [0, 3]}]
    out = _apply_edits_safely([c], edits)
    # Rollback -> one chunk unchanged and annotated with noop/post_check_failed
    assert len(out) == 1
    assert out[0]['char_start'] == 0 and out[0]['char_end'] == len(t)
    assert out[0]['llm_action'] == 'noop'
    assert out[0]['llm_reason'] == 'post_check_failed'

