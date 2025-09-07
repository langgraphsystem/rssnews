from datetime import datetime


def sample_article_en():
    text = (
        # Long paragraph
        "This is a long introductory paragraph with enough words to create a deterministic chunk. "
        "It contains multiple sentences so that the chunker can decide boundaries appropriately. "
        "Furthermore, it should cross the target word threshold to trigger splitting heuristics.\n\n"
        # Short paragraph
        "Short one.\n\n"
        # List
        "- First bullet item\n- Second bullet item\n- Third bullet item\n\n"
        # Quote
        "> Quoted line with a short message.\n"
    )
    return {
        'article_id': 'SAMPLE_EN_1',
        'title': 'Sample English Article',
        'clean_text': text,
        'language': 'en',
        'published_at': datetime.utcnow().isoformat(),
        'source_domain': 'example.com',
        'url': 'https://example.com/sample-article'
    }

