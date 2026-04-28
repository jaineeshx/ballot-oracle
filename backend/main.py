"""
Ballot Oracle — FastAPI Backend
Powered by Google Gemini 2.0 Flash
"""

import os
import json
import logging
from typing import Optional
from contextlib import asynccontextmanager

import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ballot-oracle")

# ── Gemini setup ───────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-2.0-flash"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(MODEL_NAME)
    logger.info(f"Gemini configured with model: {MODEL_NAME}")
else:
    gemini_model = None
    logger.warning("GEMINI_API_KEY not set — AI features will return mock data")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:3000").split(",")

# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ballot Oracle backend starting up...")
    yield
    logger.info("Ballot Oracle backend shutting down...")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Ballot Oracle API",
    description="Personalized Civic Intelligence powered by Google Gemini",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic Models ────────────────────────────────────────────────────────────
class AddressRequest(BaseModel):
    address: str

class GhostVoterRequest(BaseModel):
    zip_code: str
    age_group: str = "25-35"
    state: str = "IL"

class QuizAnswerRequest(BaseModel):
    answers: list[dict]
    address: str = ""

class RippleRequest(BaseModel):
    race_name: str
    candidate: str
    district: str = ""

# ── Gemini helper ──────────────────────────────────────────────────────────────
async def ask_gemini(prompt: str, expect_json: bool = True) -> str:
    if not gemini_model:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")
    try:
        full_prompt = prompt
        if expect_json:
            full_prompt += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown fences, no explanation."
        response = gemini_model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        raise HTTPException(status_code=502, detail=f"Gemini API error: {str(e)}")

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "gemini_configured": bool(GEMINI_API_KEY),
    }


@app.post("/api/ballot")
async def generate_ballot(req: AddressRequest):
    """Generate a hyper-local fictional ballot for the given address."""
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
    raw = await ask_gemini(prompt)
    try:
        # Strip any accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return data
    except json.JSONDecodeError:
        logger.error(f"JSON parse error for ballot response: {raw[:500]}")
        raise HTTPException(status_code=502, detail="Failed to parse ballot data from Gemini")


@app.post("/api/ghost-voter")
async def ghost_voter(req: GhostVoterRequest):
    """Counterfactual: What if your demographic had shown up?"""
    prompt = f"""
You are a political data analyst specializing in voter turnout analysis.

Analyze what would have happened in the 2022 midterm elections if voters aged {req.age_group} in zip code {req.zip_code} ({req.state}) had turned out at the same rate as voters aged 65+.

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
    raw = await ask_gemini(prompt)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse ghost voter data")


@app.get("/api/quiz/questions")
async def get_quiz_questions():
    """Return the 10-question Civic DNA values quiz."""
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
    raw = await ask_gemini(prompt)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse quiz questions")


@app.post("/api/quiz/match")
async def match_candidates(req: QuizAnswerRequest):
    """Match quiz answers to candidate profiles."""
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
    raw = await ask_gemini(prompt)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse quiz match results")


@app.post("/api/ripple")
async def ripple_effect(req: RippleRequest):
    """Generate plain-language daily life impact for a race."""
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
  "bottom_line": "One powerful sentence summarizing the net effect on an average resident's daily life"
}}

Be specific, grounded, and avoid political spin. Focus on tangible daily life effects.
"""
    raw = await ask_gemini(prompt)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse ripple effect data")


# ── Entry point ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
