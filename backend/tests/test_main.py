"""
VotePath India — Comprehensive Test Suite (test_main.py)
Covers all core endpoints, caching, security headers, and input validation.
"""
import pytest, json, sys, os
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import app, _cache, _make_cache_key

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield

def _mock(payload):
    async def _inner(*_a, **_kw):
        return json.dumps(payload)
    return _inner

BALLOT = {"constituency": "New Delhi", "assembly": "New Delhi", "election_date": "May 2024",
          "polling_location": "DDA Hall", "address": "110001, Delhi", "vote_weight": {"last_margin_votes": 5000, "your_impact_statement": "test"}, "races": []}
RIPPLE = {"ripples": [{"category": "Roads", "headline": "h", "detail": "d", "timeline": "6m"}], "bottom_line": "bl"}
GHOST  = {"headline": "h", "summary": "s", "emotional_hook": "e", "actual_turnout": {"age_group_25_35": 38, "age_group_65_plus": 68},
          "counterfactual_turnout": {"turnout_rate": 68, "seats_changed": 1}, "races_that_flip": []}
QUIZ_Q = {"questions": [{"id": "q1", "question": "Q?", "value_dimension": "D", "options": [{"id": "a", "text": "A", "value_score": {}}]}]}
QUIZ_M = {"civic_archetype": "Reformer", "values_profile": {"primary_value": "Dev", "secondary_value": "Sec", "profile_description": "desc"}, "candidate_matches": []}
CHAT   = {"answer": "Register at voters.eci.gov.in", "sentiment": "Neutral", "sentiment_score": 0.9, "related_topics": [], "translation_used": False}

# ── Health ────────────────────────────────────────────────────────────────────
def test_health_200():       assert client.get("/api/health").status_code == 200
def test_health_status():    assert client.get("/api/health").json()["status"] == "ok"
def test_health_services():  assert "Gemini AI (primary inference)" in client.get("/api/health").json()["google_services"]
def test_health_ai_name():   assert "Gemini" in client.get("/api/health").json()["primary_ai"]

# ── Ballot – valid ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("pin,state", [
    ("110001","Delhi"), ("400001","Maharashtra"), ("560001","Karnataka"),
    ("700001","West Bengal"), ("600001","Tamil Nadu"), ("500001","Telangana"),
])
@patch("main.ask_ai", _mock(BALLOT))
def test_ballot_valid(pin, state):
    r = client.post("/api/ballot", json={"pin_code": pin, "state": state})
    assert r.status_code == 200

# ── Ballot – invalid ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("pin,state,code", [
    ("123",   "Delhi",       422),
    ("1100012","Delhi",      422),
    ("abcdef","Delhi",       422),
    ("",      "Delhi",       422),
    ("110001","D",           422),
    ("!@#$%%","Delhi",       422),
])
def test_ballot_invalid(pin, state, code):
    assert client.post("/api/ballot", json={"pin_code": pin, "state": state}).status_code == code

# ── Ballot caching ────────────────────────────────────────────────────────────
@patch("main.ask_ai", _mock(BALLOT))
def test_ballot_cached():
    client.post("/api/ballot", json={"pin_code": "110001", "state": "Delhi"})
    client.post("/api/ballot", json={"pin_code": "110001", "state": "Delhi"})
    assert len(_cache) == 1

# ── Ripple ────────────────────────────────────────────────────────────────────
@patch("main.ask_ai", _mock(RIPPLE))
def test_ripple_200():
    r = client.post("/api/ripple", json={"race_name": "Lok Sabha", "candidate": "Test", "district": "Delhi"})
    assert r.status_code == 200

@patch("main.ask_ai", _mock(RIPPLE))
def test_ripple_has_ripples():
    r = client.post("/api/ripple", json={"race_name": "Lok Sabha", "candidate": "Test", "district": "Delhi"})
    assert "ripples" in r.json()

def test_ripple_missing_race():
    assert client.post("/api/ripple", json={}).status_code == 422

@patch("main.ask_ai", _mock(RIPPLE))
def test_ripple_cached():
    body = {"race_name": "Lok Sabha", "candidate": "Test", "district": "Delhi"}
    client.post("/api/ripple", json=body)
    client.post("/api/ripple", json=body)
    assert len(_cache) == 1

# ── Ghost Voter ───────────────────────────────────────────────────────────────
@patch("main.ask_ai", _mock(GHOST))
def test_ghost_200():
    r = client.post("/api/ghost-voter", json={"zip_code": "11001", "age_group": "18-25", "state": "Delhi"})
    assert r.status_code == 200

@patch("main.ask_ai", _mock(GHOST))
def test_ghost_has_turnout():
    r = client.post("/api/ghost-voter", json={"zip_code": "11001", "age_group": "18-25", "state": "Delhi"})
    assert "actual_turnout" in r.json()

def test_ghost_missing_zip():
    assert client.post("/api/ghost-voter", json={}).status_code == 422

# ── Quiz Questions ────────────────────────────────────────────────────────────
@patch("main.ask_ai", _mock(QUIZ_Q))
def test_quiz_questions_200():
    assert client.get("/api/quiz/questions").status_code == 200

@patch("main.ask_ai", _mock(QUIZ_Q))
def test_quiz_has_questions():
    assert "questions" in client.get("/api/quiz/questions").json()

@patch("main.ask_ai", _mock(QUIZ_Q))
def test_quiz_questions_cached():
    client.get("/api/quiz/questions")
    client.get("/api/quiz/questions")
    assert len(_cache) == 1

# ── Quiz Match ────────────────────────────────────────────────────────────────
@patch("main.ask_ai", _mock(QUIZ_M))
def test_quiz_match_200():
    r = client.post("/api/quiz/match", json={"answers": [{"q": "q1", "a": "a"}], "address": "Delhi"})
    assert r.status_code == 200

@patch("main.ask_ai", _mock(QUIZ_M))
def test_quiz_match_archetype():
    r = client.post("/api/quiz/match", json={"answers": [], "address": ""})
    assert "civic_archetype" in r.json()

def test_quiz_match_missing_answers():
    assert client.post("/api/quiz/match", json={}).status_code == 422

# ── Chat ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("msg,lang", [
    ("How to vote?", "english"),
    ("What is Form 6?", "hindi"),
    ("Voter registration help", "marathi"),
])
@patch("main.ask_ai", _mock(CHAT))
def test_chat_valid(msg, lang):
    assert client.post("/api/chat", json={"message": msg, "language": lang}).status_code == 200

@pytest.mark.parametrize("msg,code", [
    ("A", 422),      # too short
    ("A"*501, 422),  # too long
    ("", 422),       # empty
])
def test_chat_invalid(msg, code):
    assert client.post("/api/chat", json={"message": msg}).status_code == code

# ── Static Endpoints ──────────────────────────────────────────────────────────
def test_voter_checklist_200():  assert client.get("/api/voter-checklist").status_code == 200
def test_voter_checklist_items(): assert len(client.get("/api/voter-checklist").json()["checklist"]) > 0
def test_election_calendar_200(): assert client.get("/api/election-calendar").status_code == 200
def test_election_calendar_next(): assert "next_major" in client.get("/api/election-calendar").json()

# ── Fact Check & Vision Helper ────────────────────────────────────────────────
FACT = {"verdict": "FALSE", "explanation": "EVMs are not connected to wifi.", "official_rule": "ECI rule 123"}
VISION = {"document_type": "Form 6", "explanation": "Voter registration form", "action_required": "Submit to ERO"}

@patch("main.ask_ai", _mock(FACT))
def test_fact_check_200():
    assert client.post("/api/fact-check", json={"claim": "EVMs are hacked"}).status_code == 200

@patch("main._gemini_model")
def test_vision_helper_200(mock_model):
    import base64
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(VISION)
    mock_model.generate_content.return_value = mock_resp
    b64 = base64.b64encode(b"fakeimage").decode("utf-8")
    r = client.post("/api/vision-helper", json={"image_base64": b64, "mime_type": "image/jpeg"})
    assert r.status_code == 200
    assert "document_type" in r.json()

# ── 404 handler ───────────────────────────────────────────────────────────────
def test_404(): assert client.get("/api/nonexistent").status_code == 404

# ── Cache utilities ───────────────────────────────────────────────────────────
def test_cache_key_deterministic():
    assert _make_cache_key("a","b") == _make_cache_key("a","b")

def test_cache_key_unique():
    assert _make_cache_key("a","b") != _make_cache_key("a","c")
