"""
Ballot Oracle — FastAPI Backend
Powered by Groq (Llama 3.3) with Google Cloud Run, Secret Manager & Artifact Registry
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import logging
from typing import Optional, Any
from contextlib import asynccontextmanager
from functools import lru_cache

from groq import Groq
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ballot-oracle")

# ── Groq setup ─────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
MODEL_NAME: str = "llama-3.3-70b-versatile"
REQUEST_TIMEOUT: int = 45  # seconds

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client initialised with model: %s", MODEL_NAME)
else:
    groq_client = None  # type: ignore[assignment]
    logger.warning("GROQ_API_KEY not set — AI features will be unavailable")

ALLOWED_ORIGINS: list[str] = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8080,http://localhost:3000",
).split(",")

# ── Simple in-process TTL cache ────────────────────────────────────────────────
_cache: dict[str, tuple[Any, float]] = {}
CACHE_TTL: int = 600  # 10 minutes


def _cache_get(key: str) -> Any | None:
    """Return cached value if it exists and is still fresh."""
    if key in _cache:
        value, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return value
        del _cache[key]
    return None


def _cache_set(key: str, value: Any) -> None:
    """Store a value in the TTL cache."""
    _cache[key] = (value, time.time())


def _make_cache_key(*parts: str) -> str:
    """Create a stable SHA-256 cache key from the given parts."""
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Lifespan ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup / shutdown logging."""
    logger.info("Ballot Oracle backend starting up (model=%s)", MODEL_NAME)
    yield
    logger.info("Ballot Oracle backend shutting down")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Ballot Oracle API",
    description=(
        "Personalized Civic Intelligence powered by Groq + Llama 3.3, "
        "deployed on Google Cloud Run with Google Secret Manager."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Security headers middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach security-hardening HTTP headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    response.headers["Cache-Control"] = "no-store"
    return response


# ── Simple rate-limit middleware (per IP, in-process) ──────────────────────────
_rate_limit_store: dict[str, list[float]] = {}
RATE_LIMIT_REQUESTS: int = 30   # max requests …
RATE_LIMIT_WINDOW: int = 60     # … per N seconds


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    """Sliding-window rate-limiter: max 30 requests / 60 s per IP."""
    if request.url.path.startswith("/api/"):
        client_ip: str = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW
        hits = _rate_limit_store.get(client_ip, [])
        hits = [t for t in hits if t > window_start]
        if len(hits) >= RATE_LIMIT_REQUESTS:
            logger.warning("Rate limit exceeded for %s", client_ip)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": "60"},
            )
        hits.append(now)
        _rate_limit_store[client_ip] = hits
    return await call_next(request)


# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ── Pydantic Models ────────────────────────────────────────────────────────────
class AddressRequest(BaseModel):
    """Request body for ballot generation."""

    address: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="Street address or city/state to resolve the ballot for.",
    )

    @field_validator("address")
    @classmethod
    def sanitise_address(cls, v: str) -> str:
        """Strip leading/trailing whitespace and reject script injection attempts."""
        v = v.strip()
        forbidden = ["<script", "javascript:", "onerror=", "onload="]
        if any(f in v.lower() for f in forbidden):
            raise ValueError("Address contains invalid characters.")
        return v


class GhostVoterRequest(BaseModel):
    """Request body for the Ghost Voter demographic simulation."""

    zip_code: str = Field(..., min_length=5, max_length=10, pattern=r"^\d{5}(-\d{4})?$")
    age_group: str = Field(default="25-35", pattern=r"^\d{2}-\d{2}$")
    state: str = Field(default="IL", min_length=2, max_length=2)

    @field_validator("state")
    @classmethod
    def upper_state(cls, v: str) -> str:
        return v.upper()


class QuizAnswerRequest(BaseModel):
    """Request body for candidate values-matching."""

    answers: list[dict] = Field(..., min_length=1, max_length=10)
    address: str = Field(default="", max_length=200)


class RippleRequest(BaseModel):
    """Request body for the Ripple Effect analysis."""

    race_name: str = Field(..., min_length=3, max_length=200)
    candidate: str = Field(..., min_length=1, max_length=200)
    district: str = Field(default="", max_length=200)


# ── Groq AI helper ─────────────────────────────────────────────────────────────
async def ask_groq(prompt: str, *, expect_json: bool = True) -> str:
    """
    Send a prompt to Groq's LLM and return the raw text response.

    Args:
        prompt: The user prompt to send to the model.
        expect_json: If True, enforce JSON-only output and use json_object mode.

    Returns:
        The model's text response, stripped of whitespace.

    Raises:
        HTTPException 503: If the Groq client is not configured.
        HTTPException 502: If the Groq API call fails.
    """
    if not groq_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured. Please contact support.",
        )
    try:
        full_prompt = prompt
        if expect_json:
            full_prompt += (
                "\n\nIMPORTANT: Respond ONLY with valid JSON. "
                "No markdown fences, no explanation, no commentary."
            )
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": full_prompt}],
            model=MODEL_NAME,
            temperature=0.7,
            max_tokens=2048,
            response_format={"type": "json_object"} if expect_json else None,
            timeout=REQUEST_TIMEOUT,
        )
        content: str = response.choices[0].message.content or ""
        return content.strip()
    except Exception as exc:
        logger.error("Groq API error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service error: {exc}",
        )


def _parse_json(raw: str, context: str = "response") -> dict:
    """
    Parse a JSON string, stripping accidental markdown fences.

    Args:
        raw: Raw string from the LLM.
        context: Human-readable name of what is being parsed (for errors).

    Returns:
        Parsed dictionary.

    Raises:
        HTTPException 502: If JSON parsing fails.
    """
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error (%s): %s … raw=%s", context, exc, cleaned[:300])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to parse {context} data from AI service.",
        )


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/health", summary="Health check", tags=["System"])
async def health():
    """
    Return service health status and configuration metadata.

    This endpoint is used by Cloud Run health checks and monitoring.
    """
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "groq_configured": bool(GROQ_API_KEY),
        "version": "2.0.0",
        "cache_entries": len(_cache),
        "google_services": [
            "Cloud Run",
            "Artifact Registry",
            "Cloud Build",
            "Secret Manager",
        ],
    }


@app.post("/api/ballot", summary="Generate hyper-local ballot", tags=["Civic"])
async def generate_ballot(req: AddressRequest):
    """
    Generate a realistic, AI-narrated fictional ballot for the given address.

    The ballot includes federal, state, and local races as well as ballot
    measures and judicial retention votes, all contextualised to the user's
    geographical location.

    Returns:
        A structured ballot object with races, candidates, and vote-weight data.
    """
    cache_key = _make_cache_key("ballot", req.address.lower())
    if cached := _cache_get(cache_key):
        logger.info("Cache hit: ballot for '%s'", req.address)
        return cached

    prompt = f"""
You are a civic information assistant. Generate a realistic fictional local ballot for this address: "{req.address}"

Create a ballot with exactly these sections and return as JSON:

{{
  "address": "{req.address}",
  "election_date": "November 4, 2025",
  "polling_location": "A specific realistic polling location name and address near the input address",
  "district_summary": "One sentence describing the political district context",
  "vote_weight": {{
    "last_margin_votes": 847,
    "last_margin_percent": 2.3,
    "your_impact_statement": "The city council race in your ward was decided by 847 votes in 2022. Statistically, you are one of them."
  }},
  "races": [
    {{
      "office": "U.S. Senate",
      "level": "federal",
      "candidates": [
        {{"name": "A realistic name", "party": "Democrat", "tagline": "One memorable policy position"}},
        {{"name": "A realistic name", "party": "Republican", "tagline": "One memorable policy position"}}
      ],
      "what_this_controls": "Explain in 1 sentence what this office actually controls in daily life"
    }},
    {{
      "office": "State Governor",
      "level": "state",
      "candidates": [
        {{"name": "A realistic name", "party": "Democrat", "tagline": "One memorable policy position"}},
        {{"name": "A realistic name", "party": "Republican", "tagline": "One memorable policy position"}}
      ],
      "what_this_controls": "Explain in 1 sentence what this office controls"
    }},
    {{
      "office": "City Council — Ward 3",
      "level": "local",
      "candidates": [
        {{"name": "A realistic name", "party": "Independent", "tagline": "One memorable policy position"}},
        {{"name": "A realistic name", "party": "Democrat", "tagline": "One memorable policy position"}}
      ],
      "what_this_controls": "Explain in 1 sentence what this office controls"
    }},
    {{
      "office": "School Board — District 5",
      "level": "local",
      "candidates": [
        {{"name": "A realistic name", "party": "Nonpartisan", "tagline": "One memorable policy position"}},
        {{"name": "A realistic name", "party": "Nonpartisan", "tagline": "One memorable policy position"}}
      ],
      "what_this_controls": "Explain in 1 sentence what this controls"
    }},
    {{
      "office": "Ballot Measure: Prop 12 — Public Transit Funding",
      "level": "ballot_measure",
      "candidates": [
        {{"name": "YES", "party": "", "tagline": "Funds 3 new bus rapid transit lines"}},
        {{"name": "NO", "party": "", "tagline": "Opposes new tax levy"}}
      ],
      "what_this_controls": "Explain in 1 sentence what this measure does to daily commutes"
    }},
    {{
      "office": "Judge Retention — Circuit Court",
      "level": "judicial",
      "candidates": [
        {{"name": "Judge Maria Delgado", "party": "", "tagline": "Serving since 2019, 82% bar association approval"}},
        {{"name": "Retain / Not Retain", "party": "", "tagline": ""}}
      ],
      "what_this_controls": "Explain in 1 sentence what a circuit court judge controls"
    }}
  ]
}}

Make all names, places, and numbers realistic and specific. The address context should influence the state/city details.
"""
    raw = await ask_groq(prompt)
    data = _parse_json(raw, "ballot")
    _cache_set(cache_key, data)
    return data


@app.post("/api/ghost-voter", summary="Run Ghost Voter demographic simulation", tags=["Civic"])
async def ghost_voter(req: GhostVoterRequest):
    """
    Simulate what would have happened if the user's demographic had voted
    at the same rate as the 65+ age group in the 2022 midterm elections.

    Returns:
        Counterfactual analysis including flipped races and emotional narrative.
    """
    cache_key = _make_cache_key("ghost", req.zip_code, req.age_group, req.state)
    if cached := _cache_get(cache_key):
        logger.info("Cache hit: ghost-voter for zip=%s", req.zip_code)
        return cached

    prompt = f"""
You are a political data analyst specialising in voter turnout analysis.

Analyse what would have happened in the 2022 midterm elections if voters aged {req.age_group} in zip code {req.zip_code} ({req.state}) had turned out at the same rate as voters aged 65+.

Return this exact JSON structure:

{{
  "zip_code": "{req.zip_code}",
  "age_group": "{req.age_group}",
  "headline": "A dramatic, specific headline about what would have changed (e.g., 'The State Senate Seat Would Have Flipped')",
  "summary": "2-3 sentence explanation of the counterfactual result with specific numbers",
  "actual_turnout": {{
    "age_group_25_35": 34,
    "age_group_65_plus": 71,
    "total_votes_cast": 18420
  }},
  "counterfactual_turnout": {{
    "additional_votes": 6800,
    "new_total": 25220,
    "turnout_rate": 71
  }},
  "races_that_flip": [
    {{
      "race": "State Senate District 14",
      "actual_winner": "Realistic name (party)",
      "actual_margin": 1240,
      "counterfactual_winner": "Realistic name (party)",
      "counterfactual_margin": 892,
      "flip": true
    }},
    {{
      "race": "City Council Ward 3",
      "actual_winner": "Realistic name (party)",
      "actual_margin": 312,
      "counterfactual_winner": "Realistic name (party)",
      "counterfactual_margin": 1100,
      "flip": true
    }}
  ],
  "emotional_hook": "One powerful sentence about what this means for schools, transit, or housing in that zip code"
}}

Use realistic numbers consistent with actual demographic data for that region. Be specific and dramatic but factually plausible.
"""
    raw = await ask_groq(prompt)
    data = _parse_json(raw, "ghost-voter")
    _cache_set(cache_key, data)
    return data


@app.get("/api/quiz/questions", summary="Get Civic DNA quiz questions", tags=["Quiz"])
async def get_quiz_questions():
    """
    Return 10 non-partisan values-based civic quiz questions.

    Questions are cached for 10 minutes to improve performance. Each question
    maps answers to value scores across fiscal and social dimensions.

    Returns:
        A list of 10 structured quiz questions with scoring rubrics.
    """
    cache_key = _make_cache_key("quiz-questions")
    if cached := _cache_get(cache_key):
        logger.info("Cache hit: quiz questions")
        return cached

    prompt = """
Generate a 10-question values-based civic quiz (NOT party-affiliated). Each question tests a civic value like:
- Role of government
- Economic priorities
- Environmental policy
- Education funding
- Criminal justice
- Healthcare approach
- Housing policy
- Immigration
- Tax policy
- Community investment

Return this exact JSON:
{
  "questions": [
    {
      "id": 1,
      "question": "Full question text",
      "value_dimension": "e.g. 'Economic Role of Government'",
      "options": [
        {"id": "a", "text": "Option A text", "value_score": {"fiscal_conservative": 2, "fiscal_progressive": -1, "social_conservative": 0, "social_progressive": 0}},
        {"id": "b", "text": "Option B text", "value_score": {"fiscal_conservative": -1, "fiscal_progressive": 2, "social_conservative": 0, "social_progressive": 0}},
        {"id": "c", "text": "Option C text", "value_score": {"fiscal_conservative": 0, "fiscal_progressive": 1, "social_conservative": 0, "social_progressive": 1}},
        {"id": "d", "text": "Option D text", "value_score": {"fiscal_conservative": 1, "fiscal_progressive": 0, "social_conservative": 1, "social_progressive": -1}}
      ]
    }
  ]
}

Generate all 10 questions. Make them thoughtful, non-leading, and genuinely reveal values.
"""
    raw = await ask_groq(prompt)
    data = _parse_json(raw, "quiz-questions")
    _cache_set(cache_key, data)
    return data


@app.post("/api/quiz/match", summary="Match quiz answers to candidate profiles", tags=["Quiz"])
async def match_candidates(req: QuizAnswerRequest):
    """
    Analyse the user's quiz answers and match them to fictional candidate profiles.

    Returns:
        A values profile, civic archetype, and ordered list of candidate alignment scores.
    """
    answers_str = json.dumps(req.answers)
    prompt = f"""
You are a nonpartisan political analyst. Based on these quiz answers: {answers_str}

Generate a values profile and match fictional candidates to the user's values.

Return this exact JSON:
{{
  "values_profile": {{
    "primary_value": "e.g. 'Community Investment'",
    "secondary_value": "e.g. 'Fiscal Responsibility'",
    "profile_name": "e.g. 'Pragmatic Progressive'",
    "profile_description": "2-sentence description of this voter's values profile"
  }},
  "candidate_matches": [
    {{
      "candidate_name": "Realistic fictional name",
      "office": "City Council",
      "party": "Democrat",
      "match_score": 87,
      "top_alignment": "Strongest shared value",
      "top_divergence": "Biggest values gap",
      "summary": "One sentence on why they align"
    }},
    {{
      "candidate_name": "Realistic fictional name",
      "office": "City Council",
      "party": "Republican",
      "match_score": 61,
      "top_alignment": "Strongest shared value",
      "top_divergence": "Biggest values gap",
      "summary": "One sentence on why they partially align"
    }},
    {{
      "candidate_name": "Realistic fictional name",
      "office": "State Senate",
      "party": "Independent",
      "match_score": 74,
      "top_alignment": "Strongest shared value",
      "top_divergence": "Biggest values gap",
      "summary": "One sentence on why they align"
    }}
  ],
  "civic_archetype": "A memorable civic archetype name like 'The Infrastructure Realist' or 'The Community Builder'"
}}

Do not use red/blue framing. Focus purely on values alignment.
"""
    raw = await ask_groq(prompt)
    return _parse_json(raw, "quiz-match")


@app.post("/api/ripple", summary="Get daily-life Ripple Effect for a race", tags=["Civic"])
async def ripple_effect(req: RippleRequest):
    """
    Translate a ballot race into plain-language daily-life impact across 5 domains.

    Returns:
        Ripple effect data covering schools, transit, housing, taxes, and health.
    """
    cache_key = _make_cache_key("ripple", req.race_name.lower(), req.candidate.lower())
    if cached := _cache_get(cache_key):
        logger.info("Cache hit: ripple for '%s'", req.race_name)
        return cached

    prompt = f"""
You are a civic translator who explains politics in terms of everyday life.

The race is: "{req.race_name}"
Relevant candidate/option: "{req.candidate}"
District: "{req.district}"

Generate a "Ripple Effect" analysis showing how this race affects daily life.

Return this exact JSON:
{{
  "race": "{req.race_name}",
  "candidate": "{req.candidate}",
  "ripples": [
    {{
      "category": "🏫 Schools",
      "headline": "Short dramatic headline",
      "detail": "2-sentence plain-language explanation of the impact on local schools",
      "timeline": "e.g. 'Impact felt within 2 years'"
    }},
    {{
      "category": "🚌 Transit & Roads",
      "headline": "Short dramatic headline",
      "detail": "2-sentence explanation of transit/infrastructure impact",
      "timeline": "Impact timeline"
    }},
    {{
      "category": "🏠 Housing & Rent",
      "headline": "Short dramatic headline",
      "detail": "2-sentence explanation of housing/zoning impact",
      "timeline": "Impact timeline"
    }},
    {{
      "category": "💰 Your Tax Bill",
      "headline": "Short dramatic headline",
      "detail": "2-sentence explanation of tax impact",
      "timeline": "Impact timeline"
    }},
    {{
      "category": "🏥 Health & Safety",
      "headline": "Short dramatic headline",
      "detail": "2-sentence explanation of public health/safety impact",
      "timeline": "Impact timeline"
    }}
  ],
  "bottom_line": "One powerful sentence summarising the net effect on an average resident's daily life"
}}

Be specific, grounded, and avoid political spin. Focus on tangible daily life effects.
"""
    raw = await ask_groq(prompt)
    data = _parse_json(raw, "ripple")
    _cache_set(cache_key, data)
    return data


# ── Global error handlers ──────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Return a structured JSON 404 response."""
    return JSONResponse(
        status_code=404,
        content={"detail": f"Route '{request.url.path}' not found.", "status": 404},
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """Return a structured JSON 500 response without leaking internals."""
    logger.error("Unhandled server error on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred.", "status": 500},
    )


# ── Entry point ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, workers=2)
