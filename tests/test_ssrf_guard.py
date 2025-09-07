import os
from net.http import HttpClient


def test_ssrf_guard_blocks_localhost_ipv4():
    http = HttpClient()
    resp, final = http.get("http://127.0.0.1")
    assert resp is None
    assert final and "Blocked" in final


def test_ssrf_guard_blocks_metadata():
    http = HttpClient()
    resp, final = http.get("http://169.254.169.254")
    assert resp is None
    assert final and "Blocked" in final

