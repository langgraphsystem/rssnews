from utils.url import canonicalize_url, compute_url_hash


def test_compute_url_hash_canonicalization():
    u1 = "https://example.com/Path/?utm_source=x&ref=y"
    u2 = "https://EXAMPLE.com/Path"
    h1 = compute_url_hash(canonicalize_url(u1))
    h2 = compute_url_hash(canonicalize_url(u2))
    assert h1 == h2

