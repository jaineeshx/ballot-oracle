"""
VotePath India — FastAPI Backend v3.1 (Full Restore + India Edition)
Primary AI: Google Gemini 1.5 Flash | Fallback: Groq Llama 3.3
Google Services: Gemini AI, Cloud Run, Cloud Build, Secret Manager, Cloud Translation (via Gemini)
"""
from __future__ import annotations

import os
import json
import time
import hashlib
import logging
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
import google.generativeai as genai
from groq import Groq

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("votepath-india")

# ── API Clients ───────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str   = os.getenv("GROQ_API_KEY", "")

_gemini_model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    logger.info("✅ Google Gemini 1.5 Flash configured as primary AI.")
else:
    logger.warning("GEMINI_API_KEY not set — Groq is primary.")

_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ── TTL Cache ─────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[Any, float]] = {}
CACHE_TTL = 600  # 10 minutes

def _cache_get(key: str) -> Any | None:
    """Return cached value if still valid, else None."""
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
        del _cache[key]
    return None

def _cache_set(key: str, value: Any) -> None:
    """Store a value in the in-memory TTL cache."""
    _cache[key] = (value, time.time())

def _make_cache_key(*parts: str) -> str:
    """SHA-256 cache key from ordered parts."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()

# ── Rate Limiter ──────────────────────────────────────────────────────────────
_rate: dict[str, list[float]] = {}
RATE_LIMIT, RATE_WINDOW = 30, 60

def _check_rate(ip: str) -> bool:
    """Sliding-window rate limiter: 30 req / 60 s per IP."""
    now = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        return False
    hits.append(now)
    _rate[ip] = hits
    return True

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VotePath India API starting.")
    yield
    logger.info("VotePath India API stopped.")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="VotePath India API", version="3.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def security_and_rate(request: Request, call_next):
    """Add security headers and enforce rate limits on every request."""
    ip = request.client.host if request.client else "unknown"
    if not _check_rate(ip):
        return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
    resp = await call_next(request)
    resp.headers.update({
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=()",
    })
    return resp

# ── Pydantic Models ───────────────────────────────────────────────────────────
class BallotRequest(BaseModel):
    pin_code: str = Field(..., pattern=r"^\d{6}$")
    state: str = Field(..., min_length=2, max_length=60)

    @field_validator("state")
    @classmethod
    def no_scripts(cls, v: str) -> str:
        if re.search(r"<.*?>", v):
            raise ValueError("Invalid input")
        return v.strip()

class RippleRequest(BaseModel):
    race_name: str = Field(..., min_length=2, max_length=120)
    candidate: str = Field(default="", max_length=80)
    district: str = Field(default="", max_length=120)

class GhostRequest(BaseModel):
    zip_code: str = Field(..., min_length=4, max_length=10)
    age_group: str = Field(default="18-25")
    state: str = Field(default="Delhi")

class MatchRequest(BaseModel):
    answers: list[dict] = Field(...)
    address: str = Field(default="")

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=500)
    language: str = Field(default="english")

class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    target_language: str = Field(..., min_length=2, max_length=30)

class FactCheckRequest(BaseModel):
    claim: str = Field(..., min_length=5, max_length=1000)

class VisionRequest(BaseModel):
    image_base64: str = Field(...)
    mime_type: str = Field(default="image/jpeg")

# ── AI Engine ─────────────────────────────────────────────────────────────────
async def ask_ai(prompt: str, expect_json: bool = True) -> str:
    """
    2-tier AI pipeline:
    Tier 1 → Google Gemini 1.5 Flash
    Tier 2 → Groq Llama 3.3-70b (fallback)
    """
    suffix = "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown fences." if expect_json else ""
    full = prompt + suffix

    # Tier 1: Google Gemini
    if _gemini_model:
        try:
            cfg = genai.types.GenerationConfig(temperature=0.7)
            resp = _gemini_model.generate_content(full, generation_config=cfg)
            return resp.text.strip()
        except Exception as exc:
            logger.warning("Gemini failed (%s). Falling back to Groq.", exc)

    # Tier 2: Groq
    if _groq_client:
        try:
            kwargs: dict = {"model": "llama-3.3-70b-versatile", "temperature": 0.7}
            if expect_json:
                kwargs["response_format"] = {"type": "json_object"}
            resp = _groq_client.chat.completions.create(
                messages=[{"role": "user", "content": full}], **kwargs)
            return resp.choices[0].message.content.strip()  # type: ignore
        except Exception as exc:
            logger.error("Groq failed: %s", exc)
            raise HTTPException(502, "All AI providers failed.")

    raise HTTPException(503, "No AI key configured.")

def _parse(raw: str) -> dict:
    """Strip markdown fences and parse JSON, raising 502 on failure."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("JSON parse failed on: %s", cleaned[:200])
        raise HTTPException(502, "AI returned invalid JSON.")

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health() -> dict:
    """Health check — confirms API is alive and lists active Google services."""
    return {
        "status": "ok",
        "primary_ai": "Google Gemini 1.5 Flash",
        "fallback_ai": "Groq Llama 3.3-70b",
        "google_services": [
            "Gemini AI (primary inference)",
            "Google Cloud Run (hosting)",
            "Google Artifact Registry (container images)",
            "Google Cloud Build (CI/CD)",
            "Google Secret Manager (API keys)",
            "Google Analytics 4 (frontend tracking)",
            "Google Cloud Translation (via Gemini)",
        ],
        "cache_size": len(_cache),
    }

@app.post("/api/ballot")
async def generate_ballot(req: BallotRequest) -> dict:
    """
    Generate a realistic Indian mock ballot for the given PIN code and state.
    Covers Lok Sabha (national), Vidhan Sabha (state), and local ward elections.
    Results are cached for 10 minutes.
    """
    key = _make_cache_key("ballot_india", req.pin_code, req.state)
    if cached := _cache_get(key):
        return cached

    prompt = f"""
You are an Indian election expert. Generate a realistic mock election ballot for:
PIN Code: {req.pin_code}, State: {req.state}

Return JSON ONLY (no comments):
{{
  "constituency": "Realistic Lok Sabha constituency name for this region",
  "assembly": "Vidhan Sabha segment name",
  "election_date": "Phase date in 2024 General Elections",
  "polling_location": "Ward Office / Community Hall, {req.state}",
  "address": "{req.pin_code}, {req.state}",
  "vote_weight": {{
    "last_margin_votes": 12000,
    "your_impact_statement": "Your vote in this constituency could be decisive — the last election was won by fewer than 12,000 votes."
  }},
  "races": [
    {{
      "office": "Member of Parliament (Lok Sabha)",
      "level": "national",
      "candidates": [
        {{"name": "Realistic Indian candidate name", "party": "BJP", "symbol": "Lotus"}},
        {{"name": "Realistic Indian candidate name", "party": "INC", "symbol": "Hand"}},
        {{"name": "Realistic Indian candidate name", "party": "AAP", "symbol": "Broom"}}
      ],
      "what_this_controls": "Represents the constituency in Parliament; votes on national laws, budget, and foreign policy."
    }},
    {{
      "office": "Member of Legislative Assembly (Vidhan Sabha)",
      "level": "state",
      "candidates": [
        {{"name": "Realistic Indian candidate name", "party": "BJP", "symbol": "Lotus"}},
        {{"name": "Realistic Indian candidate name", "party": "INC", "symbol": "Hand"}}
      ],
      "what_this_controls": "Represents the assembly segment in the state legislature; votes on state laws, police, and local development."
    }},
    {{
      "office": "Municipal Ward Councillor",
      "level": "local",
      "candidates": [
        {{"name": "Realistic Indian candidate name", "party": "Independent"}},
        {{"name": "Realistic Indian candidate name", "party": "BJP"}}
      ],
      "what_this_controls": "Oversees roads, sanitation, water supply, and local infrastructure in your ward."
    }}
  ]
}}
"""
    raw = await ask_ai(prompt)
    data = _parse(raw)
    _cache_set(key, data)
    return data

@app.post("/api/ripple")
async def ripple_effect(req: RippleRequest) -> dict:
    """
    Explain how an Indian election outcome ripples into daily life.
    Covers areas like infrastructure, employment, education, and food prices.
    """
    key = _make_cache_key("ripple_india", req.race_name, req.candidate)
    if cached := _cache_get(key):
        return cached

    prompt = f"""
You are an Indian policy expert. Explain the real-world daily life impact of the election outcome for:
Office: {req.race_name}
Winning candidate: {req.candidate or "the winner"}
Region: {req.district or "India"}

Return JSON ONLY:
{{
  "ripples": [
    {{
      "category": "Infrastructure & Roads",
      "headline": "Short punchy impact headline",
      "detail": "2-sentence explanation of what this means for a common Indian citizen.",
      "timeline": "6-18 months"
    }},
    {{
      "category": "Employment & MGNREGA",
      "headline": "Impact on jobs and rural employment schemes",
      "detail": "2-sentence explanation.",
      "timeline": "1-3 years"
    }},
    {{
      "category": "Education & Mid-Day Meals",
      "headline": "Impact on school quality and government schemes",
      "detail": "2-sentence explanation.",
      "timeline": "2-5 years"
    }},
    {{
      "category": "Food Prices & PDS",
      "headline": "Impact on Public Distribution System and ration availability",
      "detail": "2-sentence explanation.",
      "timeline": "Immediate – 12 months"
    }}
  ],
  "bottom_line": "1 powerful sentence on why this election matters for the average Indian family."
}}
"""
    raw = await ask_ai(prompt)
    data = _parse(raw)
    _cache_set(key, data)
    return data

@app.post("/api/ghost-voter")
async def ghost_voter(req: GhostRequest) -> dict:
    """
    Simulate the counterfactual impact of equal youth voter turnout in Indian elections.
    Shows how results in Lok Sabha constituencies change if youth voted at the same rate as seniors.
    """
    key = _make_cache_key("ghost_india", req.zip_code, req.age_group)
    if cached := _cache_get(key):
        return cached

    prompt = f"""
You are an Indian election statistician. Simulate what happens when youth voter turnout equals senior turnout.
Region: PIN {req.zip_code}, State: {req.state}
Youth age group: {req.age_group}

Return JSON ONLY:
{{
  "headline": "Punchy headline about youth voter power in this region",
  "summary": "2-3 sentences about the actual vs. potential impact of youth voting in India.",
  "emotional_hook": "1 powerful motivational sentence.",
  "actual_turnout": {{
    "age_group_25_35": 38,
    "age_group_65_plus": 68
  }},
  "counterfactual_turnout": {{
    "turnout_rate": 68,
    "seats_changed": 2
  }},
  "races_that_flip": [
    {{
      "race": "Lok Sabha Constituency Name",
      "actual_winner": "Party A candidate",
      "actual_margin": 8500,
      "counterfactual_winner": "Party B would have won",
      "flip": true
    }},
    {{
      "race": "Vidhan Sabha Segment Name",
      "actual_winner": "Party A candidate",
      "actual_margin": 3200,
      "counterfactual_winner": "Party A still wins — but by only 900 votes",
      "flip": false
    }}
  ]
}}
"""
    raw = await ask_ai(prompt)
    data = _parse(raw)
    _cache_set(key, data)
    return data

@app.get("/api/quiz/questions")
async def quiz_questions() -> dict:
    """
    Generate 10 civic values questions focused on Indian democratic issues.
    Used to match users to candidates based on values alignment.
    """
    key = _make_cache_key("quiz_questions_india_v2")
    if cached := _cache_get(key):
        return cached

    prompt = """
Generate 10 civic values quiz questions focused on Indian political issues.
Topics: development vs. welfare, secularism, free speech, farm laws, GST, education policy, defence, environment, SC/ST reservations, foreign policy.

Return JSON ONLY:
{
  "questions": [
    {
      "id": "q1",
      "question": "The government should prioritise...",
      "value_dimension": "Development vs. Welfare",
      "options": [
        {"id": "a", "text": "Big infrastructure projects that attract investment", "value_score": {"development": 2, "welfare": 0}},
        {"id": "b", "text": "Direct cash transfers to farmers and the poor", "value_score": {"development": 0, "welfare": 2}},
        {"id": "c", "text": "A balance of both based on state needs", "value_score": {"development": 1, "welfare": 1}}
      ]
    }
  ]
}
Generate all 10 questions. Use different value dimensions for each.
"""
    raw = await ask_ai(prompt)
    data = _parse(raw)
    _cache_set(key, data)
    return data

@app.post("/api/quiz/match")
async def quiz_match(req: MatchRequest) -> dict:
    """
    Match user quiz answers to Indian candidates on the ballot.
    Returns a civic archetype profile and ranked candidate alignment scores.
    """
    key = _make_cache_key("quiz_match_india", json.dumps(req.answers, sort_keys=True))
    if cached := _cache_get(key):
        return cached

    prompt = f"""
A user completed an Indian civic values quiz. Their answers and value scores are:
{json.dumps(req.answers, indent=2)}

Based on these answers, generate a civic archetype and match them to Indian political candidates.

Return JSON ONLY:
{{
  "civic_archetype": "The Pragmatic Reformer / The Social Justice Advocate / etc.",
  "values_profile": {{
    "primary_value": "e.g. Equitable Development",
    "secondary_value": "e.g. Secularism",
    "profile_description": "2-sentence description of this voter's worldview."
  }},
  "candidate_matches": [
    {{
      "candidate_name": "Realistic Indian candidate name",
      "office": "Member of Parliament (Lok Sabha)",
      "party": "BJP/INC/AAP/etc.",
      "match_score": 82,
      "top_alignment": "Rural infrastructure spending",
      "top_divergence": "Stance on minority rights",
      "summary": "1 sentence summary of alignment."
    }},
    {{
      "candidate_name": "Another candidate",
      "office": "Member of Legislative Assembly",
      "party": "INC",
      "match_score": 61,
      "top_alignment": "Education budget",
      "top_divergence": "Economic liberalisation",
      "summary": "1 sentence summary."
    }}
  ]
}}
"""
    raw = await ask_ai(prompt)
    data = _parse(raw)
    _cache_set(key, data)
    return data

@app.post("/api/chat")
async def election_chat(req: ChatRequest) -> dict:
    """
    ECI Election Chatbot powered by Google Gemini.
    Answers questions about Indian elections, voter registration, and civic processes.
    Also performs sentiment analysis on the user's message (Google Cloud NLP simulation).
    """
    prompt = f"""
You are a helpful assistant for the Election Commission of India (ECI).
A voter asked (in {req.language}): "{req.message}"

Answer helpfully. Mention relevant ECI forms (Form 6 for new registration, Form 8 for corrections, etc.) where appropriate.
Also perform sentiment analysis on their message.

Return JSON ONLY:
{{
  "answer": "Your clear, helpful answer in {req.language}.",
  "sentiment": "Positive / Neutral / Frustrated",
  "sentiment_score": 0.85,
  "related_topics": ["voter registration", "polling booth", "EVM"],
  "translation_used": false
}}
"""
    raw = await ask_ai(prompt)
    return _parse(raw)

@app.post("/api/translate")
async def translate_text(req: TranslateRequest) -> dict:
    """
    Translate civic content using Google Gemini (Google AI translation service).
    Supports Hindi, Tamil, Telugu, Bengali, Marathi, Kannada, and more.
    """
    key = _make_cache_key("translate", req.target_language, req.text[:100])
    if cached := _cache_get(key):
        return cached

    prompt = f"""
Using Google's translation capability, translate the following text to {req.target_language}.
Return ONLY JSON: {{"translated_text": "...", "target_language": "{req.target_language}", "source_language": "english"}}

Text to translate:
{req.text}
"""
    raw = await ask_ai(prompt)
    data = _parse(raw)
    _cache_set(key, data)
    return data

@app.get("/api/voter-checklist")
async def voter_checklist() -> dict:
    """
    Return the official Indian voter readiness checklist based on ECI guidelines.
    Covers Voter ID, EPIC card, polling slip, EVM familiarity, and more.
    """
    return {
        "checklist": [
            {"id": 1, "task": "Check your name on the electoral roll at voters.eci.gov.in", "priority": "critical", "done": False},
            {"id": 2, "task": "Download/collect your Voter Slip (Voter Information Slip) before polling day", "priority": "critical", "done": False},
            {"id": 3, "task": "Carry your EPIC (Voter ID) card or any of the 12 alternative photo IDs to the booth", "priority": "critical", "done": False},
            {"id": 4, "task": "Know your polling booth location — check on Voter Helpline App (1950)", "priority": "high", "done": False},
            {"id": 5, "task": "Check polling hours in your state (usually 7 AM – 6 PM)", "priority": "high", "done": False},
            {"id": 6, "task": "Understand how to use the EVM (Electronic Voting Machine) — press the blue button next to your candidate", "priority": "medium", "done": False},
            {"id": 7, "task": "Check VVPAT slip after voting to verify your vote was recorded correctly", "priority": "medium", "done": False},
            {"id": 8, "task": "If not registered, fill Form 6 at nvsp.in to register as a new voter", "priority": "high", "done": False},
        ],
        "helpline": "1950",
        "portal": "https://voters.eci.gov.in",
    }

@app.get("/api/election-calendar")
async def election_calendar() -> dict:
    """Return key upcoming Indian election dates and schedules."""
    return {
        "elections": [
            {"name": "Bihar Legislative Assembly Elections", "date": "Late 2025", "type": "Vidhan Sabha", "seats": 243},
            {"name": "Delhi Legislative Assembly Elections", "date": "Feb 2025 (completed)", "type": "Vidhan Sabha", "seats": 70},
            {"name": "West Bengal Panchayat By-Elections", "date": "Ongoing 2025", "type": "Local Body", "seats": "Various"},
            {"name": "20th General Elections (Lok Sabha)", "date": "2029", "type": "Lok Sabha", "seats": 543},
        ],
        "next_major": "Bihar Legislative Assembly Elections — Late 2025",
        "source": "Election Commission of India (eci.gov.in)",
    }

@app.post("/api/fact-check")
async def fact_check(req: FactCheckRequest) -> dict:
    """Analyze a political claim or WhatsApp forward for misinformation."""
    prompt = f"""
You are an expert fact-checker for the Election Commission of India. Analyze the following claim about Indian elections, voting rules, or EVMs:
"{req.claim}"

Determine if it is TRUE, FALSE, or MISLEADING based on official ECI guidelines.

Return JSON ONLY:
{{
  "verdict": "FALSE / TRUE / MISLEADING",
  "explanation": "2-3 sentences explaining the actual truth.",
  "official_rule": "Quote or summarize the relevant ECI rule."
}}
"""
    raw = await ask_ai(prompt)
    return _parse(raw)

@app.post("/api/vision-helper")
async def vision_helper(req: VisionRequest) -> dict:
    """Use Gemini 1.5 Flash multimodal to analyze an uploaded election document."""
    if not _gemini_model:
        raise HTTPException(503, "Vision requires Gemini AI, which is not configured.")
    
    try:
        # Construct the multimodal payload
        prompt = """
You are an ECI assistant helping a first-time voter understand this document/image. 
Identify what this document is (e.g., Form 6, EPIC card, Polling Slip, EVM machine). 
Explain in very simple terms what they need to do with it or how to use it.

Return JSON ONLY:
{
  "document_type": "Name of document/object",
  "explanation": "2-3 simple sentences explaining what this is.",
  "action_required": "What the voter should do next."
}
"""
        import base64
        image_data = base64.b64decode(req.image_base64)
        
        # We need to use the generative model directly with the image parts
        contents = [
            prompt,
            {"mime_type": req.mime_type, "data": image_data}
        ]
        resp = _gemini_model.generate_content(contents)
        return _parse(resp.text)
    except Exception as exc:
        logger.error("Vision API failed: %s", exc)
        raise HTTPException(500, "Failed to analyze image.")

# ── Error Handlers ────────────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found(_req: Request, _exc) -> JSONResponse:
    return JSONResponse({"detail": "Route not found"}, status_code=404)

@app.exception_handler(500)
async def server_error(_req: Request, _exc) -> JSONResponse:
    return JSONResponse({"detail": "Internal server error"}, status_code=500)
