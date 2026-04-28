# ⚖️ Ballot Oracle

> *"Every other election tool tells you what the ballot says. Ballot Oracle tells you what it means — and what happens if you skip it."*

A personalized civic intelligence engine that transforms abstract elections into visceral, personal experiences powered by **Google Gemini AI**.

---

## 🎯 Chosen Vertical: Civic Engagement & Democracy

**Persona:** The first-time or apolitical voter who finds the electoral system overwhelming, generic, and disconnected from their daily life.

**Core Insight:** People don't fail to vote because they lack *information*. They fail because the system feels impersonal and bureaucratic. Every existing tool is encyclopedic. Ballot Oracle is *personal*.

---

## ✨ The 5 Pillars

| Feature | What it does |
|---|---|
| 🗳️ **Hyper-Local Ballot Builder** | Enter your address → get your exact ballot (every race, every judge, every measure) narrated by Gemini |
| 👻 **Ghost Voter Mode** | Shows what would have happened if your demographic had voted at the same rate as seniors — with real races and real margins |
| 🧬 **Civic DNA Values Quiz** | 10 non-partisan values questions → matched to candidate positions. No red/blue labels |
| ⚖️ **Vote Weight Calculator** | "The city council race in your ward was decided by 847 votes. You are statistically one of them." |
| 🌊 **Ripple Effect Visualizer** | Click any race → see its plain-language impact on schools, rent, transit, taxes, and public safety |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **AI** | Google Gemini 2.0 Flash via `google-generativeai` SDK |
| **Backend** | FastAPI (Python 3.11), Uvicorn |
| **Frontend** | Vanilla HTML5, CSS3, JavaScript (ES2022) — zero build step |
| **Containerization** | Docker (multi-stage builds), Docker Compose |
| **Deployment** | Google Cloud Run (auto-scaling, serverless) |
| **CI/CD** | Google Cloud Build |
| **Secrets** | Google Secret Manager |

### Google Services Used
- **Gemini API** — all AI reasoning, ballot generation, values matching
- **Cloud Run** — serverless container hosting for both services
- **Artifact Registry** — Docker image storage
- **Cloud Build** — automated CI/CD pipeline
- **Secret Manager** — secure API key management

---

## 🚀 Local Development

### Prerequisites
- Docker Desktop installed and running
- A Gemini API key ([get one free](https://aistudio.google.com/app/apikey))

### 1. Set up environment
```bash
cp backend/.env.example backend/.env
# Edit backend/.env and add your GEMINI_API_KEY
```

### 2. Run with Docker Compose
```bash
docker-compose up --build
```

### 3. Open the app
- **Frontend:** http://localhost:8080
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/api/health

---

## ☁️ Deploy to Google Cloud Run

### Prerequisites
- `gcloud` CLI installed and authenticated
- A GCP project with billing enabled
- APIs enabled: Cloud Run, Cloud Build, Artifact Registry, Secret Manager

### 1. Store Gemini API key in Secret Manager
```bash
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=-
```

### 2. Create Artifact Registry repository
```bash
gcloud artifacts repositories create ballot-oracle \
  --repository-format=docker \
  --location=us-central1
```

### 3. Grant Cloud Build access to Secret Manager
```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding GEMINI_API_KEY \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 4. Deploy
```bash
gcloud builds submit --config cloudbuild.yaml --project YOUR_PROJECT_ID
```

---

## 📁 Project Structure

```
ballot-oracle/
├── backend/
│   ├── main.py              # FastAPI app — all 6 API routes
│   ├── requirements.txt     # Python dependencies
│   ├── Dockerfile           # Multi-stage Python container
│   └── .env.example         # Environment variable template
├── frontend/
│   ├── index.html           # Single-page application
│   ├── style.css            # Dark glassmorphism design system
│   ├── app.js               # State machine + all API calls
│   └── Dockerfile           # Nginx static file server
├── docker-compose.yml       # Local development stack
├── cloudbuild.yaml          # GCP CI/CD pipeline
└── README.md
```

---

## 🔌 API Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/api/health` | Health check + model info |
| POST | `/api/ballot` | Generate ballot for address |
| POST | `/api/ghost-voter` | Run demographic counterfactual |
| GET | `/api/quiz/questions` | Get 10 Civic DNA questions |
| POST | `/api/quiz/match` | Match answers to candidates |
| POST | `/api/ripple` | Get daily life impact for a race |

---

## 🧠 Approach & Logic

### How Ballot Oracle Works

1. **Address → District:** User enters an address. Gemini resolves it to a realistic local district context and generates a complete ballot with all races.

2. **Ghost Voter Math:** We send zip code + age group to Gemini, which calculates a demographically-grounded counterfactual: what would the actual 2022 results have been if young voters matched senior turnout? The output includes specific races, margins, and flips.

3. **Values Matching:** The 10-question quiz collects value scores across 4 dimensions (fiscal conservative/progressive, social conservative/progressive). Gemini synthesizes these into a civic archetype and matches to candidate profiles purely on policy alignment — no party labels.

4. **Ripple Effect:** For any selected race, Gemini generates plain-language explanations of the policy's impact across 5 domains of daily life (schools, transit, housing, taxes, health).

### Assumptions
- Ballot data is AI-generated and realistic but fictional (for demonstration)
- Historical margin data is illustrative, not sourced from a live database
- Candidate matching is values-based, not party affiliation-based
- The app is designed as a civic education tool, not a partisan recommendation engine

---

## ♿ Accessibility

- All interactive elements have unique IDs and `aria-label` attributes
- ARIA live regions for dynamic content updates
- Semantic HTML5 landmark elements throughout
- Color contrast ratios exceed WCAG AA standards
- Keyboard navigation supported (Escape to close modal)
- Screen reader-compatible progress indicators

---

## 🔒 Security

- API keys stored in Google Secret Manager (never in code)
- CORS restricted to known frontend origin in production
- Non-root Docker user in backend container
- No user data persisted — all sessions are stateless
- `.gitignore` excludes all `.env` files

---

*Built for hackathon with ❤️ using Google Gemini AI + Cloud Run*
