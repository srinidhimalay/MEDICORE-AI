# MEDICORE — Complete Project Architecture

> A clinical medical information assistant powered by RAG (Retrieval-Augmented Generation),
> built with FastAPI, React, MongoDB, Pinecone, and Groq LLaMA 3.1.

---

## Table of Contents

1. [High-Level Architecture Diagram](#1-high-level-architecture-diagram)
2. [How the System Works — End-to-End Flow](#2-how-the-system-works--end-to-end-flow)
3. [Tech Stack](#3-tech-stack)
4. [Project Directory Structure](#4-project-directory-structure)
5. [Backend — File-by-File Description](#5-backend--file-by-file-description)
6. [Frontend — File-by-File Description](#6-frontend--file-by-file-description)
7. [Data Ingestion Pipeline](#7-data-ingestion-pipeline)
8. [MongoDB Collections](#8-mongodb-collections)
9. [API Endpoint Reference](#9-api-endpoint-reference)
10. [Environment Variables](#10-environment-variables)
11. [Key Design Decisions](#11-key-design-decisions)

---

## 1. High-Level Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         USER'S BROWSER                                       ║
║                                                                              ║
║   ┌──────────────────────────────────────────────────────────────────────┐   ║
║   │                    REACT FRONTEND (Vite + JSX)                       │   ║
║   │                     http://localhost:5173                            │   ║
║   │                                                                      │   ║
║   │  AuthScreen ──► App.jsx (root state) ──► Sidebar                    │   ║
║   │                     │                                                │   ║
║   │            ┌─────────┼─────────────────────────────┐                │   ║
║   │            │         │                             │                │   ║
║   │       ChatInput  ChatMessage               HealthProfileForm        │   ║
║   │       VoiceCtrl  TriageBadge               SymptomChecker           │   ║
║   │       LangSel    ConfidenceBadge           LabUploadModal           │   ║
║   │       ExportPDF  FeedbackButtons                                    │   ║
║   │                                                                      │   ║
║   │                    services/api.js (axios + fetch SSE)               │   ║
║   └──────────────────────────┬───────────────────────────────────────────┘   ║
╚═════════════════════════════╪════════════════════════════════════════════════╝
                              │  HTTP / SSE  (port 8000)
                              ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║                      FASTAPI BACKEND (Python)                                ║
║                       http://localhost:8000                                  ║
║                                                                              ║
║   main.py                                                                    ║
║   ├── CORS Middleware                                                        ║
║   ├── Rate Limiter (slowapi)                                                 ║
║   └── /api  ──►  chat.py (APIRouter)                                        ║
║                      │                                                       ║
║        ┌─────────────┼──────────────────────────────────────┐               ║
║        │             │                                       │               ║
║   [AUTH]         [CHAT FLOW]                          [PROFILE/MISC]         ║
║  /auth/signup   POST /chat  ──── safety.py            POST /profile          ║
║  /auth/login    POST /chat/stream ── triage.py        GET  /profile          ║
║  /auth/logout   POST /chat/image                      POST /simplify         ║
║                 POST /chat/lab-results                POST /translate        ║
║                 GET  /chat/history                    POST /feedback         ║
║                 GET  /chat/{id}                                              ║
║                 DELETE /chat/{id}                                            ║
║                                                                              ║
║   ┌──────────────────────────────────────────────────────────────────────┐   ║
║   │                     SERVICE LAYER                                    │   ║
║   │                                                                      │   ║
║   │  llm.py          retriever.py      hybrid_retriever.py               │   ║
║   │  (Groq LLaMA)    (Pinecone vec)    (BM25 + RRF + reranker)          │   ║
║   │                                                                      │   ║
║   │  live_context.py                   lab_reference.py                  │   ║
║   │  (PubMed/RxNorm/FDA)               (30+ lab ranges + parser)         │   ║
║   │                                                                      │   ║
║   │  auth.py          database.py                                        │   ║
║   │  (JWT/bcrypt)     (Motor/MongoDB Atlas)                              │   ║
║   └──────────────────────────────────────────────────────────────────────┘   ║
╚═══════════╤══════════════════╤═════════════════════════╤════════════════════╝
            │                  │                         │
            ▼                  ▼                         ▼
    ┌──────────────┐  ┌─────────────────┐   ┌──────────────────────┐
    │  MONGODB     │  │    PINECONE      │   │   EXTERNAL APIs      │
    │  Atlas       │  │  Vector Store    │   │                      │
    │              │  │  (medicore-ai)   │   │  PubMed E-utilities  │
    │  users       │  │                  │   │  RxNorm interactions │
    │  chats       │  │  ~500K+ chunks   │   │  OpenFDA events      │
    │  chat_summ.  │  │  PubMedBERT      │   │  (2.5s timeout)      │
    │  health_prof │  │  embeddings      │   │                      │
    │  feedback    │  │  (768-dim)       │   │  Groq API            │
    └──────────────┘  └─────────────────┘   │  (LLaMA 3.1 8B)      │
                                             └──────────────────────┘
```

---

## 2. How the System Works — End-to-End Flow

### 2a. Authentication Flow

```
User opens app
      │
      ▼
AuthScreen.jsx  ──  login / signup form
      │
      ▼
api.js:login()  ──►  POST /api/auth/login
                            │
                     chat.py:login()
                            │
                     MongoDB: find user by email
                            │
                     auth.py:verify_password()  (bcrypt check)
                            │
                     auth.py:create_access_token()  (JWT, 24h expiry)
                            │
                     ◄── { access_token, user }
      │
      ▼
localStorage.setItem("medicore_token", ...)
App.jsx state: user = { id, email, name }
All future API calls: Authorization: Bearer <JWT>
```

---

### 2b. Main Chat Flow (Two-Turn RAG)

```
User types a message (e.g., "my stomach hurts")
      │
      ▼
App.jsx:handleSendMessage()
      │
      ├── [if non-English language selected]
      │       api.js:detectLanguage()  →  POST /api/detect-language
      │       api.js:translateText()   →  POST /api/translate   (to English)
      │
      ▼
api.js:sendMessageStream()  ──►  POST /api/chat/stream  (SSE)
                                          │
                                  chat.py:chat_stream()
                                          │
                            ┌─────────────▼─────────────┐
                            │      SAFETY GATE           │
                            │   safety.py:              │
                            │   validate_message_async() │
                            │                            │
                            │   Tier 1: keyword scan     │
                            │   (50+ emergency terms)    │
                            │         │                  │
                            │   Tier 2: LLM context      │
                            │   (is it ACTIVE emergency?)│
                            │         │                  │
                            │   Mental health check      │
                            │   (adds supportive msg)    │
                            └─────────────┬──────────────┘
                                          │
                            ┌─────────────▼─────────────┐
                            │    TURN 1: SPECIFICITY     │
                            │                            │
                            │  llm.py:                   │
                            │  assess_query_specificity()│
                            │                            │
                            │  LLaMA judges:             │
                            │  "stomach hurts" → VAGUE   │
                            │  → generate follow-up Q    │
                            │                            │
                            │  "What is diabetes?" →     │
                            │  SPECIFIC → skip to RAG    │
                            └─────────────┬──────────────┘
                                          │
                              [if SPECIFIC or Turn 2]
                                          │
                            ┌─────────────▼─────────────┐
                            │      QUERY REFORMULATION   │
                            │                            │
                            │  llm.py:                   │
                            │  reformulate_for_retrieval()│
                            │                            │
                            │  "stomach hurts after food"│
                            │  → "abdominal pain         │
                            │    epigastric dyspepsia    │
                            │    gastritis gallbladder"  │
                            └─────────────┬──────────────┘
                                          │
                            ┌─────────────▼─────────────┐
                            │     HYBRID RETRIEVAL       │
                            │                            │
                            │  hybrid_retriever.py:      │
                            │  hybrid_search(query, k=5) │
                            │                            │
                            │  Step 1: Pinecone vector   │
                            │  search (PubMedBERT,       │
                            │  768-dim embeddings)       │
                            │  → top 15 candidates       │
                            │                            │
                            │  Step 2: BM25 keyword      │
                            │  search on those 15 docs   │
                            │                            │
                            │  Step 3: Reciprocal Rank   │
                            │  Fusion (60% vec, 40% BM25)│
                            │                            │
                            │  Step 4: Cross-encoder     │
                            │  reranking (MiniLM-L6-v2)  │
                            │  → final top 5 chunks      │
                            └─────────────┬──────────────┘
                                          │
                            ┌─────────────▼─────────────┐
                            │     LIVE CONTEXT (async)   │
                            │                            │
                            │  live_context.py:          │
                            │  get_live_context()        │
                            │                            │
                            │  Concurrent (2.5s max):    │
                            │  • PubMed recent abstracts │
                            │  • RxNorm drug interactions│
                            │  • OpenFDA adverse events  │
                            └─────────────┬──────────────┘
                                          │
                            ┌─────────────▼─────────────┐
                            │      TRIAGE ASSESSMENT     │
                            │                            │
                            │  triage.py:                │
                            │  assess_triage_level()     │
                            │                            │
                            │  LLaMA classifies:         │
                            │  🔴 Emergency              │
                            │  🟠 Urgent (<24h)          │
                            │  🟡 Semi-urgent (1-3 days) │
                            │  🟢 Routine                │
                            │  🔵 Informational          │
                            └─────────────┬──────────────┘
                                          │
                            ┌─────────────▼─────────────┐
                            │     LLM RESPONSE GEN       │
                            │                            │
                            │  llm.py:                   │
                            │  generate_response_stream()│
                            │                            │
                            │  System prompt: MediCore   │
                            │  identity + formatting     │
                            │  rules + clinical approach │
                            │                            │
                            │  User message includes:    │
                            │  • Original query          │
                            │  • Follow-up answer        │
                            │  • Health profile (if set) │
                            │  • Session memory (3 prev) │
                            │  • RAG context chunks      │
                            │  • Live context            │
                            └─────────────┬──────────────┘
                                          │
                              SSE stream: token by token
                                          │
                            ┌─────────────▼─────────────┐
                            │     PERSIST & MEMORY       │
                            │                            │
                            │  MongoDB: save messages    │
                            │                            │
                            │  Background task:          │
                            │  summarize conversation    │
                            │  → store in chat_summaries │
                            │  (used for next session)   │
                            └─────────────┬──────────────┘
                                          │
                                          ▼
                                   Frontend renders:
                                   • Streaming text
                                   • Triage badge (color)
                                   • Confidence indicator
                                   • Sources snippets
                                   • Simplify button
                                   • Find Hospitals button
```

---

### 2c. Image Analysis Flow

```
User uploads medical image
      │
      ▼
App.jsx:handleSendWithImage()
      │
      ▼
api.js:sendImageMessage()  ──►  POST /api/chat/image  (multipart)
                                        │
                                chat.py:chat_image()
                                        │
                         Step 1: llm.py:describe_image()
                                 Model: llama-4-scout-17b (vision)
                                 → clinical description text
                                        │
                         Step 2: combined_query =
                                 user_message + image_description
                                        │
                         Step 3: reformulate_for_retrieval()
                                        │
                         Step 4: hybrid_search() → RAG chunks
                                        │
                         Step 5: generate_response() with context
                                        │
                                 ◄── structured medical response
```

---

### 2d. Lab Results Flow

```
User uploads lab report (PDF or image)
      │
      ▼
LabUploadModal (user adds context notes)
      │
      ▼
api.js:sendLabResults()  ──►  POST /api/chat/lab-results
                                        │
                              chat.py:chat_lab_results()
                                        │
                    ┌───────────────────┴────────────────────┐
                    │  PDF?                                   │  Image?
                    ▼                                         ▼
           fitz (PyMuPDF) text extract           llm:describe_image()
           → if <50 chars (scanned):             structured extraction
             vision model fallback               prompt: "TEST VALUE UNIT"
                    │                                         │
                    └──────────────┬──────────────────────────┘
                                   │
                        lab_reference.py:parse_lab_text()
                        → regex parse each line
                        → normalize test name (aliases)
                        → classify: normal/high/low/critical
                                   │
                        format_lab_table_as_context()
                        → structured table for LLM
                                   │
                        hybrid_search() → RAG context
                                   │
                        generate_response()
                        → medical interpretation
                                   │
                    ◄── { lab_values[], interpretation, sources }
                                   │
                    Frontend: lab value table + colored status badges
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend framework | React 18 + Vite | SPA with fast HMR |
| HTTP client | Axios + native Fetch | REST calls + SSE streaming |
| Backend framework | FastAPI 0.110 | Async REST API |
| ASGI server | Uvicorn | Production-grade async server |
| LLM provider | Groq (LLaMA 3.1 8B Instant) | Text generation, classification |
| Vision model | Llama-4-Scout-17B (via Groq) | Medical image description |
| Embeddings | PubMedBERT (HuggingFace) | Medical-optimized 768-dim vectors |
| Vector store | Pinecone (serverless) | Approximate nearest neighbor search |
| Keyword search | BM25 (rank-bm25) | Exact term matching |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Final relevance scoring |
| Database | MongoDB Atlas (Motor async) | Users, chats, profiles, feedback |
| Auth | JWT (python-jose) + bcrypt (passlib) | Stateless auth with 24h tokens |
| Rate limiting | slowapi | Per-IP endpoint throttling |
| Live data | PubMed + RxNorm + OpenFDA | Real-time medical evidence |
| PDF processing | PyMuPDF (fitz) | Text extraction + scanned-page render |
| Validation | Pydantic v2 | Request/response schemas |

---

## 4. Project Directory Structure

```
Medicore/
│
├── .gitignore                    ← Git exclusions (env, dist, .vs, PDFs, etc.)
├── ARCHITECTURE.md               ← This file
│
├── backend/
│   ├── main.py                   ← FastAPI app entry point, lifespan startup
│   ├── requirements.txt          ← All Python dependencies (pinned)
│   ├── .env                      ← Secrets (never committed)
│   ├── .env.example              ← Template for required env vars
│   │
│   ├── app/                      ← Core application package
│   │   ├── __init__.py
│   │   ├── chat.py               ← ALL API endpoints + request/response models
│   │   ├── llm.py                ← Groq LLM service (all LLM interactions)
│   │   ├── retriever.py          ← Pinecone vector store service
│   │   ├── hybrid_retriever.py   ← BM25 + RRF + cross-encoder reranker
│   │   ├── live_context.py       ← PubMed / RxNorm / OpenFDA real-time data
│   │   ├── lab_reference.py      ← Lab normal ranges + text parser
│   │   ├── safety.py             ← Emergency detection + content moderation
│   │   ├── triage.py             ← Clinical urgency classifier (5 levels)
│   │   ├── auth.py               ← Password hashing + JWT token creation
│   │   └── database.py           ← MongoDB Atlas connection (Motor async)
│   │
│   ├── ingestion/                ← One-time data pipeline (run before launch)
│   │   ├── rag_setup.py          ← PDF → chunks → embeddings → Pinecone upload
│   │   ├── fetch_web_sources.py  ← Optional: scrape WHO/CDC web content
│   │   └── data/pdfs/            ← 5 volumes of Gale Encyclopedia of Medicine
│   │                                (ignored by git — already in Pinecone)
│   │
│   ├── test_api.py               ← Manual HTTP smoke tests for chat endpoints
│   └── test_api_auth.py          ← Manual HTTP smoke tests for auth endpoints
│
├── frontend/
│   ├── index.html                ← Vite HTML entry point
│   ├── vite.config.js            ← Vite config (proxy → localhost:8000)
│   ├── package.json              ← Node dependencies
│   ├── .env                      ← VITE_API_URL (never committed)
│   ├── .env.example              ← Template
│   │
│   ├── public/
│   │   └── medical-icon.svg      ← Favicon / PWA icon
│   │
│   └── src/
│       ├── main.jsx              ← React root mount
│       ├── App.jsx               ← Root component, all state, all handlers
│       │
│       ├── components/
│       │   ├── AuthScreen.jsx    ← Login / Signup form
│       │   ├── Sidebar.jsx       ← Chat history list + user info
│       │   ├── ChatMessage.jsx   ← Single message renderer (markdown, badges)
│       │   ├── ChatInput.jsx     ← Text input field with keyboard shortcuts
│       │   ├── VoiceControls.jsx ← Web Speech API for voice input
│       │   ├── LoadingSpinner.jsx← Animated loading indicator
│       │   ├── LanguageSelector.jsx ← Dropdown for 12 languages
│       │   ├── HealthProfileForm.jsx ← Modal for user health data
│       │   ├── SymptomChecker.jsx   ← Guided symptom input wizard
│       │   ├── LabUploadModal.jsx   ← Modal: context notes before lab upload
│       │   ├── ExportChatPDF.jsx    ← Download conversation as PDF
│       │   ├── TriageBadge.jsx      ← Color-coded urgency display
│       │   ├── ConfidenceBadge.jsx  ← RAG confidence display
│       │   └── FeedbackButtons.jsx  ← Thumbs up/down on responses
│       │
│       ├── services/
│       │   └── api.js            ← All API calls (axios + SSE fetch)
│       │
│       └── styles/
│           ├── App.css           ← Main layout + chat styles
│           ├── AuthScreen.css    ← Login/signup card styles
│           └── Sidebar.css       ← Sidebar panel styles
```

---

## 5. Backend — File-by-File Description

---

### `backend/main.py`
**Role:** Application entry point. Creates and configures the FastAPI app.

**What it does:**
- Loads `.env` with `python-dotenv`
- Registers the `lifespan` async context manager that runs **on startup**:
  1. Connects to MongoDB Atlas (`db_service.connect()`)
  2. Pings MongoDB to verify connectivity
  3. Initializes the Pinecone vector store (`retriever_service.initialize()`)
  4. Initializes the hybrid retriever and loads the cross-encoder model (`hybrid_retriever_service.initialize()`)
- On **shutdown**: closes the MongoDB connection cleanly
- Configures CORS to allow requests from `localhost:5173` (Vite) and `localhost:3000`
- Registers `slowapi` rate limiter globally
- Mounts all routes under `/api` prefix
- Provides `/` (info) and `/health` endpoints

---

### `backend/app/chat.py`
**Role:** The central hub — all API endpoints + Pydantic models.

**Pydantic models defined here:**
- `SignupRequest`, `LoginRequest`, `AuthResponse` — auth
- `ChatRequest`, `ChatResponse`, `NewChatResponse` — chat I/O
- `ChatHistoryItem`, `ChatHistoryResponse`, `ChatDetailResponse` — history
- `HealthProfileRequest`, `HealthProfileResponse` — user profile
- `LabValue`, `LabResultResponse` — lab results
- `SimplifyRequest`, `TranslateRequest`, `FeedbackRequest` — utilities

**Auth helpers:**
- `get_current_user()` — FastAPI dependency: decodes JWT, returns `user_id`. Raises 401 if invalid.
- `get_optional_user()` — Same but returns `None` instead of raising, for endpoints that work both authenticated and anonymous.

**Session memory helpers:**
- `get_session_summaries(user_id)` — Fetches last 3 conversation summaries from `chat_summaries` collection to give the LLM cross-session context.
- `summarize_and_store_chat(chat_id, user_id, messages)` — Called as a background `asyncio.Task` after each response; uses the LLM to write a short summary of the conversation and stores it.

**API endpoints (18 total):**

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| POST | /auth/signup | No | 5/min | Register new user |
| POST | /auth/login | No | 10/min | Login, returns JWT |
| POST | /auth/logout | Yes | — | Logs out (client deletes token) |
| POST | /chat/new | Yes | — | Create empty chat session |
| GET | /chat/history | Yes | — | List all user's chats |
| GET | /chat/{id} | Yes | — | Full message list for one chat |
| DELETE | /chat/{id} | Yes | — | Delete a chat |
| POST | /chat | Optional | 20/min | Two-turn RAG (non-streaming) |
| POST | /chat/stream | Optional | 20/min | Two-turn RAG (SSE streaming) |
| POST | /chat/image | Optional | 10/min | Medical image analysis |
| POST | /chat/lab-results | Optional | 5/min | Lab report interpretation |
| POST | /simplify | Optional | — | Simplify last assistant response |
| POST | /translate | Yes | — | Translate text to target language |
| POST | /detect-language | Yes | — | Detect language of text |
| POST | /profile | Yes | — | Create/update health profile |
| GET | /profile | Yes | — | Get health profile |
| DELETE | /profile | Yes | — | Delete health profile |
| POST | /feedback | Yes | — | Submit thumbs up/down |

**Two-turn conversation logic (POST /chat and POST /chat/stream):**
1. Safety validation (emergency, inappropriate content, mental health)
2. If `awaiting_followup=False`: ask LLM to assess query specificity
   - Vague → generate one focused follow-up question → return with `awaiting_followup=True`
   - Specific → go directly to RAG pipeline
3. If `awaiting_followup=True` (Turn 2): combine original query + user's follow-up answer → RAG
4. RAG pipeline: reformulate query → hybrid search → live context → generate response
5. Assess triage level (runs concurrently)
6. Save messages to MongoDB
7. Background task: summarize and store for cross-session memory

---

### `backend/app/llm.py`
**Role:** All LLM interactions via the Groq API.

**Primary model:** `llama-3.1-8b-instant` — fast, 128K context, medical-capable.
**Vision model:** `meta-llama/llama-4-scout-17b-16e-instruct` — used only for image description.

**Methods:**

| Method | Purpose | Tokens | Temp |
|--------|---------|--------|------|
| `assess_query_specificity()` | Returns `True` if follow-up needed | 10 | 0.1 |
| `reformulate_for_retrieval()` | Converts natural query to medical search terms | 100 | 0.1 |
| `generate_followup()` | Generates one clinical clarifying question | 100 | 0.5 |
| `generate_response()` | Main RAG response (non-streaming) | 1500 | 0.7 |
| `generate_response_stream()` | Same but yields chunks via SSE | 1500 | 0.7 |
| `describe_image()` | Clinical image description for vision model | 300 | 0.3 |
| `simplify_text()` | Rewrites response in plain language | 500 | 0.5 |
| `translate_text()` | Translates to target language (12 languages) | 3000 | 0.3 |
| `detect_language()` | Returns ISO language code | 10 | 0.1 |
| `summarize_conversation()` | 2-3 sentence session summary for memory | 200 | 0.3 |

**Key implementation detail:** Groq's Python client is synchronous. All calls are wrapped with `asyncio.to_thread()` to avoid blocking the async FastAPI event loop. Streaming uses a `queue.Queue` + background thread pattern to bridge the sync Groq stream into an async generator.

**System prompt (in `_get_system_prompt()`):** The MediCore identity and all response formatting rules are defined here. The prompt enforces:
- Context-only answers (no hallucination)
- No diagnosis, no specific dosages
- Adaptive format per query type (symptom / condition / medication / general)
- Mandatory educational disclaimer at the end

---

### `backend/app/retriever.py`
**Role:** Pinecone vector store service. Pure semantic similarity search.

**Embedding model:** `pritamdeka/S-PubMedBert-MS-MARCO` (768-dimensional, medical-domain-tuned). **Must match the model used during ingestion in `rag_setup.py`.**

**Methods:**
- `initialize()` — Loads the HuggingFace embedding model and connects to the Pinecone index. Verifies the index exists (fails clearly if `rag_setup.py` was never run).
- `search(query, k=5)` — Async similarity search, returns list of text strings.
- `search_with_scores(query, k=5)` — Returns chunks with cosine similarity scores + confidence level (`high` > 0.8, `medium` > 0.5, `low` otherwise).
- `search_sync(query, k=5)` — Synchronous fallback.
- `get_retriever(k=5)` — Returns a LangChain retriever interface (used internally).

**Singleton:** `retriever_service = RetrieverService()` — one instance shared across all requests.

---

### `backend/app/hybrid_retriever.py`
**Role:** Combines vector search + BM25 + cross-encoder for higher quality retrieval.

**Pipeline for each query:**
1. **Vector search** (via `retriever_service`): fetch `k × 3 = 15` candidates with scores
2. **BM25**: build an in-memory BM25 index from those 15 docs, compute keyword scores
3. **Reciprocal Rank Fusion (RRF)**: merge vector ranks (weight 0.6) and BM25 ranks (weight 0.4) using the formula `score = weight / (60 + rank)`
4. **Cross-encoder reranking**: `cross-encoder/ms-marco-MiniLM-L-6-v2` scores each (query, document) pair → sort by score → return top 5

**Confidence from reranker scores:** `>5.0` = high, `>0.0` = medium, otherwise = low.

**Fallback:** If anything fails, falls back to basic vector search so the API never returns an error.

---

### `backend/app/live_context.py`
**Role:** Enriches the RAG context with real-time data from three public medical APIs.

**Called:** Once per query, after hybrid retrieval. Hard timeout: **2.5 seconds** for all three calls combined.

**Three concurrent fetches:**

1. **PubMed** (`fetch_pubmed_abstracts`):
   - eSearch: finds up to 3 relevant PMIDs for the query
   - eFetch: retrieves abstract text
   - Returns first 1200 chars of abstracts

2. **RxNorm** (`fetch_drug_interactions`):
   - Extracts drug names from query using `extract_drug_names()` (known-drugs lookup + suffix heuristic)
   - If ≥2 drugs found: queries RxNorm interaction list
   - Returns up to 3 interaction descriptions with severity ratings

3. **OpenFDA** (`fetch_fda_adverse_events`):
   - If any drug detected: queries FDA adverse event database
   - Returns top 5 reported adverse reactions for that drug

**Design:** All failures are silently swallowed. The main response is never blocked by live context. If all three fail, returns empty string and RAG-only context is used.

---

### `backend/app/lab_reference.py`
**Role:** Reference ranges for 60+ lab tests and a parser for extracted lab text.

**`LAB_REFERENCE_RANGES`:** Dictionary mapping canonical test name → `(unit, normal_low, normal_high, critical_low, critical_high)` for:
- CBC (hemoglobin, WBC, platelets, differentials, MCV, MCH, MCHC, RDW)
- Basic/Comprehensive Metabolic Panel (sodium, potassium, BUN, creatinine, glucose, calcium, etc.)
- Lipid Panel (cholesterol, LDL, HDL, triglycerides, VLDL)
- Liver Function Tests (ALT/SGPT, AST/SGOT, ALP, GGT, bilirubin, albumin)
- Thyroid Panel (TSH, Free T4, Free T3, T3/T4 total)
- Kidney (uric acid, eGFR, urea)
- Diabetes (HbA1c, fasting glucose, random glucose)
- Coagulation (PT, INR, APTT, fibrinogen)
- Other (PSA, ESR, CRP, ferritin, iron, vitamin B12, folate, vitamin D, amylase, lipase, troponin, BNP, D-dimer)

**`LAB_ALIASES`:** Maps 100+ alternate names and abbreviations to canonical keys (e.g., "SGPT" → "alt", "HbA1c" → "hba1c").

**`parse_lab_text(extracted_text)`:** Line-by-line regex parser. Each line: `TEST_NAME VALUE UNIT`. Normalizes name, parses numeric value, classifies status, deduplicates. Returns list of dicts.

**`format_lab_table_as_context(lab_values)`:** Formats parsed values into a fixed-width text table with highlighted abnormal/critical values, ready to be injected into the LLM prompt.

---

### `backend/app/safety.py`
**Role:** Content moderation with a two-tier emergency detection system.

**Tier 1 — Keyword Pre-screen (`check_emergency_keywords`):**
- Scans message for 50+ keywords across categories: suicide/self-harm, cardiac, stroke, breathing, bleeding, consciousness, poisoning, allergic reaction, seizures, etc.
- Fast, runs in microseconds.

**Tier 2 — LLM Context Assessment (`assess_emergency_context`):**
- Only runs if Tier 1 triggers (reduces cost and latency for normal queries).
- Asks LLaMA to classify as `ACTIVE_EMERGENCY`, `NOT_EMERGENCY`, or `UNCLEAR`.
- Distinguishes: "I'm having chest pain NOW" (ACTIVE) vs "I had chest pain last week" (NOT).
- If `UNCLEAR`, defaults to `ACTIVE_EMERGENCY` for safety.

**Other checks:**
- `check_inappropriate_content()` — Blocks hack/exploit/weapon/suicide method requests.
- `check_mental_health()` — Detects anxiety, depression, PTSD, etc. → prepends a compassionate preamble with crisis hotlines (does NOT block the query).
- `validate_message_length()` — 3–2000 character bounds.

**Emergency response:** Shows Indian emergency numbers (108, 102, 100, 112) and crisis hotlines (iCall, Vandrevala Foundation, AASRA).

---

### `backend/app/triage.py`
**Role:** Classifies query urgency into 5 clinical levels for display on the frontend.

**Levels:**
- 🔴 `EMERGENCY` — life-threatening NOW, call 108 immediately
- 🟠 `URGENT` — see doctor within 24 hours
- 🟡 `SEMI_URGENT` — see doctor within 1-3 days
- 🟢 `ROUTINE` — self-care appropriate
- 🔵 `INFO` — general question, no active symptoms

Each level has a color hex, label, and icon. The response includes a `reason` sentence explaining the classification. Defaults to `ROUTINE` on LLM error.

---

### `backend/app/auth.py`
**Role:** Password security and JWT token management.

- `hash_password(password)` — bcrypt hashing via `passlib.CryptContext`
- `verify_password(plain, hashed)` — constant-time bcrypt comparison
- `create_access_token(data)` — Creates HS256 JWT with 24-hour expiry. Payload: `{"sub": user_id, "exp": ...}`

**Secret key:** Read from `JWT_SECRET` env var. Falls back to `"your-fallback-secret"` (insecure; always set in production).

---

### `backend/app/database.py`
**Role:** MongoDB Atlas connection management.

- Uses `motor.motor_asyncio.AsyncIOMotorClient` for fully async MongoDB operations.
- Connects with `ServerApi('1')`, TLS enabled, `certifi` CA bundle for SSL certificate verification.
- Pool settings: `maxPoolSize=10`, `minPoolSize=1`, `retryWrites=True`.
- `get_collection(name)` — Returns a collection from the `medical_chatbot` database.

**Singleton:** `db_service = MongoDB()` — connection established once at startup via `lifespan`.

---

## 6. Frontend — File-by-File Description

---

### `frontend/src/main.jsx`
Entry point. Mounts `<App />` into `#root` in `index.html`. Standard React 18 `createRoot`.

---

### `frontend/src/App.jsx`
**Role:** Root component and state manager. Contains all business logic for the UI.

**State managed:**
| State | Type | Purpose |
|-------|------|---------|
| `user` | object/null | Logged-in user info (from localStorage) |
| `conversations` | array | Sidebar chat list |
| `currentChatId` | string/null | Active chat MongoDB ObjectId |
| `messages` | array | Current chat message list |
| `awaitingFollowup` | bool | Whether next send is Turn 2 |
| `loading` | bool | Disables input during API call |
| `selectedLanguage` | string | ISO code for translation (default "en") |
| `sidebarOpen` | bool | Sidebar toggle state |
| `showHealthProfile` | bool | Health profile modal visibility |
| `selectedImage` | File/null | Pending image upload |
| `selectedLabFile` | File/null | Pending lab file upload |
| `showLabModal` | bool | Lab context modal visibility |
| `showSymptomChecker` | bool | Symptom checker modal visibility |

**Key handlers:**
- `handleSendMessage()` — Translates if needed, sends to SSE stream, updates UI token-by-token
- `handleSendWithImage()` — Reads image as base64 for preview, sends multipart to `/chat/image`
- `handleSendLabResults()` — Sends lab file + context to `/chat/lab-results`, renders lab value table
- `handleSimplify()` — Extracts last assistant message, posts to `/simplify`, appends result
- `handleFindHospitals()` — Uses `navigator.geolocation` + keyword mapping to open Google Maps
- `formatMedicalResponse()` — Parses `**Section Headers**` from LLM output into structured section objects for `ChatMessage` to render with icons

---

### `frontend/src/services/api.js`
**Role:** All network communication. Single source of truth for API calls.

- Creates an **axios instance** with base URL from `VITE_API_URL` env var, 60-second timeout.
- **Request interceptor:** Reads `medicore_token` from localStorage, adds `Authorization: Bearer` header.
- **Response interceptor:** On 401, clears auth data and reloads page to show login.
- **`sendMessageStream()`** — Uses native `fetch` + `ReadableStream` to consume SSE events (`chat_id`, `content`, `triage`, `done`, `error`). Calls `onChunk(text)` callback for each content event.

---

### `frontend/src/components/AuthScreen.jsx`
Login and signup form. Toggles between login/signup mode. Calls `api.login()` or `api.signup()`, calls `onLogin(userData)` callback on success. Displays field-level error messages.

---

### `frontend/src/components/Sidebar.jsx`
Left panel with:
- "New Chat" button
- Scrollable list of past conversations (title, timestamp)
- Delete button per conversation
- User name + email display
- Logout button

Styled with `Sidebar.css`.

---

### `frontend/src/components/ChatMessage.jsx`
Renders a single message bubble. For assistant messages:
- If `formatted` (parsed sections array): renders each section with icon + header + content
- Otherwise: renders raw text
- Shows `TriageBadge` if `triage` data present
- Shows `ConfidenceBadge` if `confidence` data present
- Shows `FeedbackButtons` for thumbs up/down
- Shows lab value table with colored status badges if `isLabResult=true`
- Shows image preview thumbnail if `imageUrl` present
- Streaming: renders character-by-character as SSE chunks arrive

---

### `frontend/src/components/ChatInput.jsx`
Single-line text input. Sends on Enter (without Shift). Passes message text up via `onSend` callback. Clears after send.

---

### `frontend/src/components/VoiceControls.jsx`
Web Speech API integration. Mic button → starts `SpeechRecognition`. On result, calls `onSend` with transcribed text. Language-aware (uses `selectedLanguage` to set recognition language).

---

### `frontend/src/components/LanguageSelector.jsx`
Dropdown for 12 languages: English, Spanish, French, German, Chinese, Arabic, Hindi, Tamil, Telugu, Marathi, Bengali, Kannada. Sets `selectedLanguage` state in App.

---

### `frontend/src/components/HealthProfileForm.jsx`
Modal form for entering: age, sex, height/weight, blood type, known conditions, medications, allergies, family history, lifestyle (smoking, alcohol, exercise). Calls `api.getHealthProfile()` on mount to pre-fill. Saves with `api.updateHealthProfile()`.

---

### `frontend/src/components/SymptomChecker.jsx`
Guided wizard that walks the user through selecting symptoms by body system (head, chest, abdomen, etc.). Generates a natural language query and calls `onSend()` to submit it as a regular chat message.

---

### `frontend/src/components/LabUploadModal.jsx`
Modal that appears after a lab file is selected. Lets user add optional context notes (e.g., "patient age 45, diabetic"). On confirm, passes file + context to `handleSendLabResults()`.

---

### `frontend/src/components/ExportChatPDF.jsx`
Generates a PDF of the current conversation using the browser's print API. Formats messages with styling for clean PDF output.

---

### `frontend/src/components/TriageBadge.jsx`
Renders a colored pill badge showing triage level (🔴 Emergency / 🟠 Urgent / 🟡 Semi-Urgent / 🟢 Routine / 🔵 Informational) with the LLM's one-sentence reason.

---

### `frontend/src/components/ConfidenceBadge.jsx`
Renders a small badge showing RAG retrieval confidence: High / Medium / Low, indicating how well the knowledge base matched the query.

---

### `frontend/src/components/FeedbackButtons.jsx`
Thumbs up / thumbs down buttons on each assistant response. Calls `api.submitFeedback()` with `rating: 1` or `rating: -1`. Shows confirmation after submission.

---

### `frontend/src/components/LoadingSpinner.jsx`
Animated spinner displayed in the chat area while waiting for a response.

---

## 7. Data Ingestion Pipeline

**File:** `backend/ingestion/rag_setup.py`

**Purpose:** One-time script run before the first deployment to populate the Pinecone index. Not part of the live API.

**Process:**
```
5 PDF volumes (Gale Encyclopedia of Medicine)
        │
        ▼ PyMuPDFLoader (LangChain community)
        │  Loads each page as a Document
        │
        ▼ deduplicate_documents()
        │  MD5 hash of page content → remove duplicates
        │
        ▼ RecursiveCharacterTextSplitter
        │  chunk_size=1000, chunk_overlap=200
        │  → ~500,000+ text chunks
        │
        ▼ HuggingFaceEmbeddings
        │  Model: pritamdeka/S-PubMedBert-MS-MARCO
        │  768-dimensional vectors
        │  Batch processing to manage RAM
        │
        ▼ Pinecone.upsert()
        │  Index name: medicore-ai
        │  Checkpoint file: ingestion_checkpoint.json
        │  (resumable if interrupted)
        │
        ▼ Pinecone index ready for retrieval
```

**`fetch_web_sources.py`** — Optional companion script that scrapes WHO/CDC web pages using BeautifulSoup and adds those chunks to the Pinecone index for additional coverage.

---

## 8. MongoDB Collections

| Collection | Fields | Purpose |
|-----------|--------|---------|
| `users` | `email`, `password` (hashed), `name`, `created_at`, `updated_at` | User accounts |
| `chats` | `user_id`, `title`, `messages[]` (role+content), `created_at`, `updated_at` | Conversation history |
| `chat_summaries` | `user_id`, `chat_id`, `summary`, `created_at` | Cross-session memory (LLM-generated summaries) |
| `health_profiles` | `user_id`, `age`, `sex`, `height_cm`, `weight_kg`, `blood_type`, `known_conditions[]`, `current_medications[]`, `allergies[]`, `family_history[]`, `smoking`, `alcohol`, `exercise` | User health context for personalized responses |
| `feedback` | `user_id`, `chat_id`, `message_index`, `rating` (-1/1), `comment`, `created_at` | Thumbs up/down ratings |

---

## 9. API Endpoint Reference

```
Base URL: http://localhost:8000

Auth:
  POST   /api/auth/signup          Body: { email, password, name }
  POST   /api/auth/login           Body: { email, password }
  POST   /api/auth/logout          Header: Bearer token

Chat:
  POST   /api/chat/new             → { chat_id, message }
  GET    /api/chat/history         → { chats: [...] }
  GET    /api/chat/{chat_id}       → { chat_id, title, messages, ... }
  DELETE /api/chat/{chat_id}       → { message }
  POST   /api/chat                 Body: { message, chat_id?, awaiting_followup }
                                   → { response, awaiting_followup, sources, chat_id, confidence, triage }
  POST   /api/chat/stream          Body: same as /chat
                                   → SSE stream of { type: chat_id|content|triage|done|error }
  POST   /api/chat/image           Multipart: image file + message + chat_id?
                                   → { response, chat_id, confidence, sources }
  POST   /api/chat/lab-results     Multipart: file + context + chat_id?
                                   → { lab_values[], interpretation, chat_id, raw_extracted_text, sources }

Utilities:
  POST   /api/simplify             Body: { chat_history: [...] }
  POST   /api/translate            Body: { text, target_language, source_language? }
  POST   /api/detect-language      Body: { text }

Profile:
  POST   /api/profile              Body: health profile fields
  GET    /api/profile              → health profile
  DELETE /api/profile

Feedback:
  POST   /api/feedback             Body: { chat_id, message_index, rating, comment? }

System:
  GET    /                         → API info
  GET    /health                   → { status, mongodb, vector_store }
  GET    /api/test                 → endpoint list
  GET    /api/debug/mongodb        → MongoDB connection test
```

---

## 10. Environment Variables

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq cloud API key for LLaMA |
| `PINECONE_API_KEY` | Yes | Pinecone cloud API key |
| `PINECONE_INDEX_NAME` | No | Index name (default: `medicore-ai`) |
| `MONGODB_URI` | Yes | MongoDB Atlas connection string |
| `JWT_SECRET` | Yes | Secret key for signing JWTs (use a long random string) |
| `EMBEDDING_MODEL` | No | HuggingFace model name (default: `pritamdeka/S-PubMedBert-MS-MARCO`) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: `http://localhost:5173,http://localhost:3000`) |

### `frontend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | No | Backend URL (default: `http://localhost:8000`) |

---

## 11. Key Design Decisions

### Two-Turn Conversation
Rather than answering vague queries with generic information, the system first assesses query specificity. For vague queries ("my stomach hurts"), it asks one focused clinical question, then uses both the original query and follow-up answer to retrieve much more targeted context. This significantly improves response quality.

### Hybrid Retrieval
Pure vector search can miss exact medical terms (drug names, test abbreviations). Pure BM25 misses semantic similarity. The hybrid approach with RRF fusion and cross-encoder reranking gives the best of both: semantic understanding + keyword precision, then final relevance scoring.

### PubMedBERT Embeddings
General-purpose embeddings (like OpenAI's `text-embedding-ada-002`) are not optimized for medical text. PubMedBERT was pretrained on PubMed abstracts and MS MARCO, making it significantly better at medical terminology. **Critical requirement:** the same model must be used at both ingestion time and query time.

### Live Context with Hard Timeout
Static RAG can go stale. Real-time PubMed, RxNorm, and FDA data adds recency without blocking the response. The 2.5-second timeout ensures live context never degrades user experience — it's always best-effort.

### Two-Tier Emergency Detection
A simple keyword scan ("chest pain") would trigger emergency alerts for queries like "What causes chest pain?" or "My grandmother had chest pain last week." The two-tier system uses LLM context to distinguish active emergencies from informational queries, dramatically reducing false positives while maintaining safety for true emergencies.

### Cross-Session Memory
JWT is stateless, so session data isn't inherently persisted. After each conversation, a background task summarizes the key medical topics discussed and stores that summary. On the next session, those summaries are injected into the LLM context, allowing the assistant to reference what was discussed previously without storing full conversation history in the prompt.

### Streaming (SSE)
For a 1500-token response at LLaMA speeds, non-streaming would mean 5-15 seconds of blank screen. SSE streaming delivers tokens as they're generated, making the interaction feel instant. The SSE protocol also allows sending structured metadata events (`chat_id`, `triage`, `done`) alongside content chunks.

### Singleton Services
`llm_service`, `retriever_service`, `hybrid_retriever_service`, and `db_service` are all module-level singletons. The embedding model and cross-encoder are loaded once at startup (taking 10-60 seconds) and reused across all requests. This is critical for performance — loading a transformer model per request would be unusable.
