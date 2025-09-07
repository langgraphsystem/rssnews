from chunking_simple import chunk_article


def test_contextual_overlap_characters():
    # Construct a simple two-paragraph text that will form >=2 chunks
    text = (
        "Intro paragraph with several words to make a chunk. "
        "It should be long enough.\n\n"
        "Second paragraph also has enough words for a second chunk."
    )
    meta = {}
    # Small target to force multiple chunks and check overlap
    chunks = chunk_article(
        text, meta,
        target_words=10,
        short_min_words=2,
        long_para_words=100,
        overlap_tokens=20,
    )

    assert len(chunks) >= 2

    # Offsets must be unique and non-overlapping
    prev_end = -1
    for c in chunks:
        s = c['char_start']
        e = c['char_end']
        assert 0 <= s < e <= len(text)
        assert s >= prev_end
        prev_end = e

    # text_ctx must include additional context vs base text when overlap > 0
    for c in chunks:
        assert 'text_ctx' in c
        assert len(c['text_ctx']) >= len(c['text'])
        # When not at boundaries, expect context extension on at least one side
        if c['char_start'] > 0 or c['char_end'] < len(text):
            assert len(c['text_ctx']) > len(c['text'])

