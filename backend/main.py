"""
Ballot Oracle — Indian Democratic Context
Powered by Google Gemini 1.5 Flash (Primary) and Groq Llama 3 (Fallback)
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import logging
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

import google.generativeai as genai
from groq import Groq

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ballot-oracle")

# ── API Clients ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
REQUEST_TIMEOUT: int = 45

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Google Gemini configured as primary AI.")
else:
    logger.warning("GEMINI_API_KEY not set — trying Groq fallback.")

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None

# ── In-Process Cache ───────────────────────────────────────────────────────────
_cache: dict[str, tuple[Any, float]] = {}
CACHE_TTL: int = 600

def _cache_get(key: str) -> Any | None:
    if key in _cache:
        value, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return value
        del _cache[key]
    return None

def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (value, time.time())

def _make_cache_key(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()

# ── Lifespan ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ballot Oracle (India Edition) starting up.")
    yield
    logger.info("Shutting down.")

# ── App Definition ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="VotePath India API",
    description="Indian Civic Intelligence powered by Google Gemini.",
    version="3.0.0",
    lifespan=lifespan,
)

# ── Middleware ──────────────────────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Models ────────────────────────────────────────────────────────────
class IndianAddressRequest(BaseModel):
    pin_code: str = Field(..., pattern=r"^\d{6}$", description="6-digit Indian PIN code")
    state: str = Field(..., min_length=2)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=500)
    language: str = Field(default="english")

# ── AI Engine ───────────────────────────────────────────────────────────────────
async def ask_ai(prompt: str, expect_json: bool = True) -> str:
    """
    Tiered AI Pipeline:
    1. Tries Google Gemini 1.5 Flash
    2. Falls back to Groq Llama 3
    """
    full_prompt = prompt
    if expect_json:
        full_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown."

    # Tier 1: Gemini
    if GEMINI_API_KEY:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    response_mime_type="application/json" if expect_json else "text/plain",
                )
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini failed: {e}. Falling back to Groq.")
    
    # Tier 2: Groq
    if groq_client:
        try:
            response = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": full_prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                response_format={"type": "json_object"} if expect_json else None,
            )
            return response.choices[0].message.content.strip() # type: ignore
        except Exception as e:
            logger.error(f"Groq failed: {e}")
            raise HTTPException(status_code=502, detail="All AI providers failed.")
            
    raise HTTPException(status_code=503, detail="No AI keys configured.")

def _parse_json(raw: str) -> dict:
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Failed to parse AI JSON.")

# ── Endpoints ───────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "primary_ai": "Google Gemini 1.5",
        "google_services": ["Gemini AI", "Cloud Run", "Google Analytics (Frontend)"]
    }

@app.post("/api/ballot")
async def generate_indian_ballot(req: IndianAddressRequest):
    """Generates a mock Indian Lok Sabha/Vidhan Sabha ballot based on PIN code."""
    cache_key = _make_cache_key("india_ballot", req.pin_code)
    if cached := _cache_get(cache_key):
        return cached

    prompt = f"""
    You are an Election Commission of India (ECI) expert. Generate a realistic mock ballot for PIN Code {req.pin_code} in State {req.state}.
    Return JSON format:
    {{
      "constituency": "Realistic Lok Sabha Constituency name",
      "assembly": "Realistic Vidhan Sabha segment",
      "polling_date": "Next General Election Phase Date",
      "races": [
        {{
          "office": "Member of Parliament (Lok Sabha)",
          "level": "national",
          "candidates": [
            {{"name": "Realistic Indian Name 1", "party": "National Party A", "symbol": "Lotus/Hand/etc"}},
            {{"name": "Realistic Indian Name 2", "party": "National Party B", "symbol": "Symbol"}}
          ],
          "what_this_controls": "Explains MP duties in 1 sentence."
        }}
      ]
    }}
    """
    raw = await ask_ai(prompt)
    data = _parse_json(raw)
    _cache_set(cache_key, data)
    return data

@app.post("/api/chat")
async def election_chat(req: ChatRequest):
    """
    Indian Election Chatbot. Uses Gemini for answers, sentiment analysis, and translation.
    """
    prompt = f"""
    User query: "{req.message}"
    Language requested: {req.language}
    
    You are a helpful assistant for the Election Commission of India.
    Provide a helpful answer. Also perform sentiment analysis on the user's query.
    Return JSON:
    {{
      "answer": "Your helpful answer in {req.language}. If they ask about forms, mention Form 6 for new voters.",
      "sentiment": "Positive, Neutral, or Frustrated",
      "translation_used": true
    }}
    """
    raw = await ask_ai(prompt)
    return _parse_json(raw)
