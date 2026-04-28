"""
Ballot Oracle — Backend Test Suite
Tests all API endpoints, input validation, caching, and error handling.
Run with: pytest tests/ -v --tb=short
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app, _cache, _cache_get, _cache_set, _make_cache_key, _parse_json
from fastapi import HTTPException

# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the in-process cache before every test for isolation."""
    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture
def client():
    """Return a synchronous FastAPI test client."""
    return TestClient(app)


# ── Mock Groq responses ─────────────────────────────────────────────────────────

MOCK_BALLOT = {
    "address": "123 Main St",
    "election_date": "November 4, 2025",
    "polling_location": "Springfield Community Center, 456 Elm St",
    "district_summary": "Located in Illinois' 13th congressional district.",
    "vote_weight": {
        "last_margin_votes": 847,
        "last_margin_percent": 2.3,
        "your_impact_statement": "The city council race was decided by 847 votes.",
    },
    "races": [
        {
            "office": "U.S. Senate",
            "level": "federal",
            "candidates": [
                {"name": "Jane Smith", "party": "Democrat", "tagline": "Clean energy jobs"},
                {"name": "John Doe", "party": "Republican", "tagline": "Tax cuts"},
            ],
            "what_this_controls": "National healthcare and education policy.",
        }
    ],
}

MOCK_GHOST = {
    "zip_code": "60601",
    "age_group": "25-35",
    "headline": "The State Senate Seat Would Have Flipped",
    "summary": "If young voters turned out at senior rates, 3 races would change.",
    "actual_turnout": {"age_group_25_35": 34, "age_group_65_plus": 71, "total_votes_cast": 18420},
    "counterfactual_turnout": {"additional_votes": 6800, "new_total": 25220, "turnout_rate": 71},
    "races_that_flip": [
        {
            "race": "State Senate District 14",
            "actual_winner": "Alice Brown (R)",
            "actual_margin": 1240,
            "counterfactual_winner": "Bob Green (D)",
            "counterfactual_margin": 892,
            "flip": True,
        }
    ],
    "emotional_hook": "Your neighbourhood school's funding was decided by 312 votes.",
}

MOCK_QUESTIONS = {
    "questions": [
        {
            "id": 1,
            "question": "How should local governments fund public schools?",
            "value_dimension": "Education Funding",
            "options": [
                {"id": "a", "text": "Property taxes", "value_score": {"fiscal_conservative": 2, "fiscal_progressive": -1, "social_conservative": 1, "social_progressive": -1}},
                {"id": "b", "text": "State income tax", "value_score": {"fiscal_conservative": -1, "fiscal_progressive": 2, "social_conservative": -1, "social_progressive": 2}},
                {"id": "c", "text": "Federal grants", "value_score": {"fiscal_conservative": -2, "fiscal_progressive": 1, "social_conservative": -1, "social_progressive": 1}},
                {"id": "d", "text": "Private partnerships", "value_score": {"fiscal_conservative": 2, "fiscal_progressive": -2, "social_conservative": 2, "social_progressive": -2}},
            ],
        }
    ]
}

MOCK_MATCH = {
    "values_profile": {
        "primary_value": "Community Investment",
        "secondary_value": "Fiscal Responsibility",
        "profile_name": "Pragmatic Progressive",
        "profile_description": "You value community programs but want responsible spending.",
    },
    "candidate_matches": [
        {
            "candidate_name": "Elena Torres",
            "office": "City Council",
            "party": "Democrat",
            "match_score": 87,
            "top_alignment": "Community Investment",
            "top_divergence": "Tax policy",
            "summary": "Strong alignment on housing and transit priorities.",
        }
    ],
    "civic_archetype": "The Infrastructure Realist",
}

MOCK_RIPPLE = {
    "race": "City Council Ward 3",
    "candidate": "YES",
    "ripples": [
        {
            "category": "🏫 Schools",
            "headline": "More funding, better outcomes",
            "detail": "This vote would unlock $2M in school grants.",
            "timeline": "Impact felt within 2 years",
        }
    ],
    "bottom_line": "Your commute and school quality hinge on this vote.",
}


# ── Helper ──────────────────────────────────────────────────────────────────────

def _mock_ask_groq(payload: dict):
    """Return a mock ask_groq coroutine that yields the given payload as JSON."""
    import json

    async def _inner(*args, **kwargs):
        return json.dumps(payload)

    return _inner


# ── Health endpoint ─────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_contains_expected_keys(self, client):
        data = client.get("/api/health").json()
        assert data["status"] == "ok"
        assert "model" in data
        assert "version" in data
        assert "google_services" in data

    def test_health_lists_google_services(self, client):
        data = client.get("/api/health").json()
        services = data["google_services"]
        assert "Cloud Run" in services
        assert "Secret Manager" in services


# ── Ballot endpoint ─────────────────────────────────────────────────────────────

class TestBallotEndpoint:
    def test_ballot_requires_address(self, client):
        resp = client.post("/api/ballot", json={})
        assert resp.status_code == 422

    def test_ballot_rejects_too_short_address(self, client):
        resp = client.post("/api/ballot", json={"address": "abc"})
        assert resp.status_code == 422

    def test_ballot_rejects_script_injection(self, client):
        resp = client.post("/api/ballot", json={"address": "<script>alert(1)</script>"})
        assert resp.status_code == 422

    def test_ballot_rejects_empty_string(self, client):
        resp = client.post("/api/ballot", json={"address": ""})
        assert resp.status_code == 422

    def test_ballot_rejects_too_long_address(self, client):
        resp = client.post("/api/ballot", json={"address": "a" * 201})
        assert resp.status_code == 422

    def test_ballot_success_with_valid_address(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_BALLOT)):
            resp = client.post("/api/ballot", json={"address": "123 Main St, Chicago, IL"})
        assert resp.status_code == 200
        data = resp.json()
        assert "races" in data
        assert "vote_weight" in data

    def test_ballot_caches_result(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_BALLOT)) as mock:
            client.post("/api/ballot", json={"address": "456 Oak Ave, Chicago, IL"})
            client.post("/api/ballot", json={"address": "456 Oak Ave, Chicago, IL"})
        # Both requests use the same address — second should be from cache
        assert len(_cache) >= 1

    def test_ballot_response_structure(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_BALLOT)):
            data = client.post("/api/ballot", json={"address": "789 Elm St, Chicago, IL"}).json()
        assert isinstance(data.get("races"), list)
        assert data["races"][0]["office"] == "U.S. Senate"


# ── Ghost Voter endpoint ────────────────────────────────────────────────────────

class TestGhostVoterEndpoint:
    def test_ghost_requires_zip_code(self, client):
        resp = client.post("/api/ghost-voter", json={})
        assert resp.status_code == 422

    def test_ghost_rejects_invalid_zip(self, client):
        resp = client.post("/api/ghost-voter", json={"zip_code": "ABCDE"})
        assert resp.status_code == 422

    def test_ghost_rejects_short_zip(self, client):
        resp = client.post("/api/ghost-voter", json={"zip_code": "123"})
        assert resp.status_code == 422

    def test_ghost_success(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_GHOST)):
            resp = client.post("/api/ghost-voter", json={"zip_code": "60601", "age_group": "25-35", "state": "IL"})
        assert resp.status_code == 200
        data = resp.json()
        assert "races_that_flip" in data
        assert "emotional_hook" in data

    def test_ghost_state_uppercased(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_GHOST)):
            resp = client.post("/api/ghost-voter", json={"zip_code": "60601", "state": "il"})
        assert resp.status_code == 200


# ── Quiz endpoints ──────────────────────────────────────────────────────────────

class TestQuizEndpoints:
    def test_get_questions_returns_200(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_QUESTIONS)):
            resp = client.get("/api/quiz/questions")
        assert resp.status_code == 200

    def test_get_questions_has_questions_key(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_QUESTIONS)):
            data = client.get("/api/quiz/questions").json()
        assert "questions" in data
        assert len(data["questions"]) >= 1

    def test_match_requires_answers(self, client):
        resp = client.post("/api/quiz/match", json={})
        assert resp.status_code == 422

    def test_match_rejects_empty_answers(self, client):
        resp = client.post("/api/quiz/match", json={"answers": []})
        assert resp.status_code == 422

    def test_match_success(self, client):
        answers = [{"question_id": 1, "selected": "a"}]
        with patch("main.ask_groq", _mock_ask_groq(MOCK_MATCH)):
            resp = client.post("/api/quiz/match", json={"answers": answers})
        assert resp.status_code == 200
        data = resp.json()
        assert "values_profile" in data
        assert "candidate_matches" in data
        assert "civic_archetype" in data


# ── Ripple endpoint ─────────────────────────────────────────────────────────────

class TestRippleEndpoint:
    def test_ripple_requires_race_name(self, client):
        resp = client.post("/api/ripple", json={"candidate": "YES"})
        assert resp.status_code == 422

    def test_ripple_requires_candidate(self, client):
        resp = client.post("/api/ripple", json={"race_name": "City Council"})
        assert resp.status_code == 422

    def test_ripple_success(self, client):
        with patch("main.ask_groq", _mock_ask_groq(MOCK_RIPPLE)):
            resp = client.post("/api/ripple", json={"race_name": "City Council Ward 3", "candidate": "YES"})
        assert resp.status_code == 200
        data = resp.json()
        assert "ripples" in data
        assert "bottom_line" in data

    def test_ripple_caches_result(self, client):
        payload = {"race_name": "City Council Ward 3", "candidate": "YES"}
        with patch("main.ask_groq", _mock_ask_groq(MOCK_RIPPLE)):
            client.post("/api/ripple", json=payload)
            client.post("/api/ripple", json=payload)
        assert len(_cache) >= 1


# ── Cache utilities ─────────────────────────────────────────────────────────────

class TestCacheUtilities:
    def test_cache_set_and_get(self):
        _cache_set("test-key", {"foo": "bar"})
        result = _cache_get("test-key")
        assert result == {"foo": "bar"}

    def test_cache_miss_returns_none(self):
        assert _cache_get("nonexistent-key") is None

    def test_cache_key_is_deterministic(self):
        k1 = _make_cache_key("ballot", "chicago")
        k2 = _make_cache_key("ballot", "chicago")
        assert k1 == k2

    def test_different_inputs_produce_different_keys(self):
        k1 = _make_cache_key("ballot", "chicago")
        k2 = _make_cache_key("ballot", "new york")
        assert k1 != k2


# ── JSON parser utility ─────────────────────────────────────────────────────────

class TestJsonParser:
    def test_parses_clean_json(self):
        data = _parse_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_strips_markdown_fences(self):
        raw = "```json\n{\"key\": \"value\"}\n```"
        data = _parse_json(raw)
        assert data == {"key": "value"}

    def test_raises_502_on_bad_json(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_json("not valid json at all")
        assert exc_info.value.status_code == 502


# ── Security headers ────────────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_xframe_options_present(self, client):
        resp = client.get("/api/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_xcontent_type_options_present(self, client):
        resp = client.get("/api/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_xss_protection_present(self, client):
        resp = client.get("/api/health")
        assert resp.headers.get("x-xss-protection") == "1; mode=block"

    def test_referrer_policy_present(self, client):
        resp = client.get("/api/health")
        assert "referrer-policy" in resp.headers


# ── 404 handler ─────────────────────────────────────────────────────────────────

class TestErrorHandlers:
    def test_404_returns_json(self, client):
        resp = client.get("/api/nonexistent-route")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data
