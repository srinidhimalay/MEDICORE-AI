# MEDICORE AI — Medical Information Chatbot

An AI-powered medical information assistant built with **FastAPI**, **React**, **MongoDB Atlas**, **Pinecone**, and **Groq LLaMA 3.1**. Uses Retrieval-Augmented Generation (RAG) with hybrid search to answer medical questions grounded in the Gale Encyclopedia of Medicine, enriched with real-time data from PubMed, RxNorm, and OpenFDA.

> **Disclaimer:** MEDICORE is for educational purposes only. It is not a substitute for professional medical advice, diagnosis, or treatment.

---

## Features

- **Two-turn conversation flow** — asks a clarifying question for vague queries before answering
- **Hybrid RAG retrieval** — vector search (PubMedBERT) + BM25 + cross-encoder reranking
- **Live context enrichment** — real-time PubMed abstracts, drug interactions (RxNorm), FDA adverse events
- **Medical image analysis** — upload a photo for AI-assisted clinical description + RAG response
- **Lab report interpretation** — upload a PDF or image lab report; extracts, classifies, and explains values
- **Two-tier safety system** — keyword + LLM-based emergency detection with Indian crisis helplines
- **Clinical triage badges** — every response is classified: Emergency / Urgent / Semi-Urgent / Routine / Info
- **Health profile** — personalize responses with age, conditions, medications, and allergies
- **Symptom checker wizard** — guided body-system symptom selector
- **Multilingual support** — 12 languages with auto-detect and response translation
- **Voice input** — Web Speech API microphone support
- **Cross-session memory** — LLM-generated conversation summaries carried into future sessions
- **Export to PDF** — download full chat history as a PDF
- **Streaming responses** — Server-Sent Events (SSE) for token-by-token output
- **User authentication** — JWT-based login/signup with bcrypt passwords

---

## Prerequisites

Make sure the following are installed before you begin:

| Tool    | Minimum Version | Check              |
| ------- | --------------- | ------------------ |
| Python  | 3.10+           | `python --version` |
| Node.js | 18+             | `node --version`   |
| npm     | 9+              | `npm --version`    |
| Git     | any             | `git --version`    |

You also need accounts and API keys for:

| Service           | Purpose                    | Get it at                 |
| ----------------- | -------------------------- | ------------------------- |
| **Groq**          | LLM inference (LLaMA 3.1)  | https://console.groq.com  |
| **Pinecone**      | Vector database            | https://app.pinecone.io   |
| **MongoDB Atlas** | Database (free tier works) | https://cloud.mongodb.com |

---

## Project Structure

```
Medicore/
├── backend/          ← FastAPI Python backend
├── frontend/         ← React + Vite frontend
├── .gitignore
├── ARCHITECTURE.md   ← Full technical architecture doc
└── README.md         ← This file
```

---

## Setup — Step by Step

### Step 1 — Clone the Repository

```bash
git clone <your-repo-url>
cd Medicore
```

---

### Step 2 — Backend Setup

#### 2a. Create and activate a virtual environment

```bash
# From the project root (Medicore/)
pypy -3.10 -m venv env

# Activate — Windows
env\Scripts\activate

# Activate — macOS / Linux
source env/bin/activate
```

#### 2b. Install Python dependencies

```bash
pip install -r backend/requirements.txt
```

> This installs all packages including PyTorch, Transformers, and the PubMedBERT model.
> First-time install can take **5–10 minutes** depending on your connection.

#### 2c. Create the backend environment file

```bash
cp backend/.env.example backend/.env
```

Then open `backend/.env` and fill in your credentials:

```env
# ── Required ──────────────────────────────────────────────────
GROQ_API_KEY=gsk_...              # From console.groq.com
PINECONE_API_KEY=pcsk_...         # From app.pinecone.io
PINECONE_INDEX_NAME=medicore-ai   # Name of your Pinecone index
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
JWT_SECRET=change-this-to-a-long-random-string-in-production

# ── Optional (defaults shown) ──────────────────────────────────
EMBEDDING_MODEL=pritamdeka/S-PubMedBert-MS-MARCO
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
HOST=0.0.0.0
PORT=8000
```

> **Important:** Never commit `.env` to git. It is already in `.gitignore`.

---

### Step 3 — Pinecone Index Setup

Before starting the backend, you need a Pinecone index populated with medical knowledge.

#### 3a. Create the index in Pinecone

Log in to [app.pinecone.io](https://app.pinecone.io) and create a **Serverless** index with:

- **Name:** `medicore-ai` (or whatever you set in `PINECONE_INDEX_NAME`)
- **Dimensions:** `768`
- **Metric:** `cosine`
- **Cloud:** AWS (or any region)

#### 3b. Add your PDF source files

Place your medical PDF files inside:

```
backend/ingestion/data/pdfs/
```

The project was built using the **Gale Encyclopedia of Medicine (5 volumes)**, but any medical reference PDFs will work.

#### 3c. Run the ingestion script

```bash
# Make sure your virtual environment is active
cd backend
python ingestion/rag_setup.py
```

This will:

1. Load all PDFs page by page
2. Deduplicate content
3. Split into 1000-character chunks with 200-char overlap
4. Generate PubMedBERT embeddings (768-dim)
5. Upload to Pinecone in batches

Progress is saved in `ingestion_checkpoint.json` — if interrupted, re-run the script and it will resume from where it stopped.

> **Time estimate:** Expect 30–120 minutes depending on the size of your PDFs and hardware.
> This is a **one-time operation**. You do not re-run it unless you add new documents.

---

### Step 4 — MongoDB Setup

1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) and create a free **M0 cluster**
2. Create a database user with read/write access
3. Whitelist your IP address (or use `0.0.0.0/0` for development)
4. Click **Connect → Drivers** and copy the connection string
5. Replace `<password>` in the string and paste it into `MONGODB_URI` in `backend/.env`

The backend will automatically create the following collections on first use:

- `users`
- `chats`
- `chat_summaries`
- `health_profiles`
- `feedback`

No manual database or collection creation is needed.

---

### Step 5 — Frontend Setup

#### 5a. Install Node dependencies

```bash
cd frontend
npm install
```

#### 5b. Create the frontend environment file

```bash
# From the frontend/ directory
cp .env.example .env
```

Edit `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

> If your backend runs on a different port or host, update this value.

---

## Running the Application

Open **two terminals** simultaneously.

### Terminal 1 — Start the backend

```bash
# From the project root, with virtualenv active
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should see:

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     🚀 Starting Medical Chatbot backend...
INFO:     ✓ MongoDB connected successfully
INFO:     ✓ MongoDB ping successful
INFO:     Initializing embedding model: pritamdeka/S-PubMedBert-MS-MARCO
INFO:     ✓ Vector store initialized successfully
INFO:     ✓ Cross-encoder reranker loaded
INFO:     ✓ Hybrid retriever initialized successfully
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> **First startup** downloads the PubMedBERT and cross-encoder models from HuggingFace (≈ 500MB total). Subsequent starts use the local cache and are much faster.

### Terminal 2 — Start the frontend

```bash
cd frontend
npm run dev
```

You should see:

```
  VITE v7.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.x.x:5173/
```

The browser opens automatically. If it doesn't, navigate to **http://localhost:5173**.

---

## Verifying Everything Works

### 1. Backend health check

Open your browser or run:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "Medical Chatbot Backend",
  "version": "2.0.0",
  "mongodb": "healthy",
  "vector_store": "initialized"
}
```

### 2. API documentation

FastAPI auto-generates interactive API docs at:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### 3. Frontend

- Go to http://localhost:5173
- Click **Sign Up** and create an account
- Start a conversation — try "What is diabetes?" or "I have a headache"

---

## Environment Variables Reference

### `backend/.env`

| Variable              | Required | Default                            | Description                                              |
| --------------------- | -------- | ---------------------------------- | -------------------------------------------------------- |
| `GROQ_API_KEY`        | Yes      | —                                  | Groq API key for LLaMA inference                         |
| `PINECONE_API_KEY`    | Yes      | —                                  | Pinecone API key                                         |
| `PINECONE_INDEX_NAME` | No       | `medicore-ai`                      | Name of your Pinecone index                              |
| `MONGODB_URI`         | Yes      | —                                  | MongoDB Atlas connection string                          |
| `JWT_SECRET`          | Yes      | insecure default                   | Secret for signing JWT tokens — use a long random string |
| `EMBEDDING_MODEL`     | No       | `pritamdeka/S-PubMedBert-MS-MARCO` | Must match what was used during ingestion                |
| `CORS_ORIGINS`        | No       | `http://localhost:5173,...`        | Comma-separated list of allowed frontend origins         |
| `HOST`                | No       | `0.0.0.0`                          | Backend bind address                                     |
| `PORT`                | No       | `8000`                             | Backend port                                             |

### `frontend/.env`

| Variable       | Required | Default                 | Description      |
| -------------- | -------- | ----------------------- | ---------------- |
| `VITE_API_URL` | No       | `http://localhost:8000` | Backend base URL |

---

## Common Issues & Fixes

### Backend won't start — "GROQ_API_KEY not found"

Make sure `backend/.env` exists and contains a valid `GROQ_API_KEY`. The file must be inside the `backend/` folder, not the project root.

### "Pinecone index 'medicore-ai' not found"

You need to run the ingestion script first (`python ingestion/rag_setup.py`), and the index name in `.env` must exactly match the one you created in Pinecone.

### Embedding model download is slow / fails

The first startup downloads ~450MB from HuggingFace. If it times out, re-run — it will resume. If HuggingFace is blocked in your region, set:

```env
HF_ENDPOINT=https://hf-mirror.com
```

### MongoDB connection fails — SSL errors

The backend uses `certifi` for CA bundle. If you see SSL errors, make sure your IP is whitelisted in MongoDB Atlas under **Network Access**.

### Frontend shows "Network Error" or blank screen

- Check that the backend is running on port 8000
- Check `frontend/.env` has `VITE_API_URL=http://localhost:8000`
- Check browser console for CORS errors — make sure `CORS_ORIGINS` includes `http://localhost:5173`

### "No context chunks retrieved" in responses

The Pinecone index may be empty. Run `python ingestion/rag_setup.py` to populate it with your PDFs.

### Cross-encoder / reranker slow to load

The cross-encoder model (`ms-marco-MiniLM-L-6-v2`) is ~90MB and is downloaded on first startup. Subsequent starts use the local cache.

---

## Development Tips

### Backend auto-reload

The `--reload` flag in the uvicorn command watches for file changes and restarts automatically. Remove it in production.

### Exploring the API interactively

Use Swagger UI at http://localhost:8000/docs to test any endpoint directly in the browser — no Postman needed. Use the **Authorize** button to paste a JWT token from login.

### Testing without the Pinecone index

You can start the server even if the Pinecone index is missing — the API will work but RAG responses will have no context. Chat will still function (using only live context and LLM knowledge).

### Re-ingesting after adding new PDFs

Add new PDFs to `backend/ingestion/data/pdfs/`, then re-run `python ingestion/rag_setup.py`. The checkpoint system means only new files will be processed.

---

## Building for Production

### Backend

```bash
# Run without --reload for production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

> Use `--workers 1` because the embedding model and Pinecone client are not fork-safe. For horizontal scaling, run multiple single-worker instances behind a load balancer.

### Frontend

```bash
cd frontend
npm run build
```

This produces a `frontend/dist/` folder with static files ready to be served by Nginx, Vercel, Netlify, or any static host.

Update `VITE_API_URL` in `frontend/.env` to your production backend URL before building.

---

## Tech Stack Summary

| Layer          | Technology                           |
| -------------- | ------------------------------------ |
| Frontend       | React 19, Vite 7, Axios              |
| Backend        | FastAPI 0.110, Uvicorn, Python 3.10+ |
| LLM            | Groq — LLaMA 3.1 8B Instant          |
| Vision         | Groq — Llama 4 Scout 17B             |
| Embeddings     | PubMedBERT (HuggingFace, 768-dim)    |
| Vector DB      | Pinecone (serverless)                |
| Keyword search | BM25 (rank-bm25)                     |
| Reranker       | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Database       | MongoDB Atlas (Motor async driver)   |
| Auth           | JWT (python-jose) + bcrypt (passlib) |
| Rate limiting  | slowapi                              |
| PDF processing | PyMuPDF (fitz)                       |
| Live data      | PubMed E-utilities, RxNorm, OpenFDA  |

---

## Learn More

- See [ARCHITECTURE.md](ARCHITECTURE.md) for a complete technical deep-dive including system diagrams, every file explained, and all design decisions.
- Backend API docs: http://localhost:8000/docs (when running)

## Note: This project was developed as an academic exercise. Replace with open-licensed medical sources for any public deployment.
