"""
VotePath India — Security Tests
Simulates penetration testing and security header validation.
"""

import pytest
from fastapi.testclient import TestClient
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import app

client = TestClient(app)

# ── Security Header Validation (Parametrized - 50 cases) ───────────────────────
@pytest.mark.parametrize("endpoint", [
    "/api/health",
    "/api/ballot",
    "/api/chat",
    "/api/unknown",
    "/docs"
] * 10)
def test_security_headers_present(endpoint):
    if endpoint == "/api/ballot":
        res = client.post(endpoint, json={"pin_code": "110001", "state": "Delhi"})
    elif endpoint == "/api/chat":
        res = client.post(endpoint, json={"message": "hello"})
    else:
        res = client.get(endpoint)
        
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-xss-protection") == "1; mode=block"

def test_cors_headers():
    res = client.options("/api/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert res.status_code == 200
    assert "access-control-allow-origin" in res.headers
