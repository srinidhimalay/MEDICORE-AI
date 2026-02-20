import warnings
warnings.filterwarnings("ignore", message=".*resume_download.*", category=FutureWarning)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import os

# Load environment variables
load_dotenv()

# Import routers and services
from app.chat import router as chat_router
from app.retriever import retriever_service
from app.hybrid_retriever import hybrid_retriever_service
from app.database import db_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    logger.info("🚀 Starting Medical Chatbot backend...")
    
    try:
        # Initialize MongoDB
        db_service.connect()
        logger.info("✓ MongoDB connected successfully")
        
        # Test the connection with a simple operation
        try:
            await db_service.db.command('ping')
            logger.info("✓ MongoDB ping successful")
        except Exception as e:
            logger.warning(f"⚠️ MongoDB ping failed: {e}")
            logger.info("Server will continue, but database operations may fail")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        logger.info("⚠️ Server starting WITHOUT database connection")
        logger.info("Please check your MONGODB_URI in .env file")
    
    warmup_models = os.getenv("WARMUP_MODELS_ON_STARTUP", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

    if warmup_models:
        try:
            # Initialize vector store
            retriever_service.initialize()
            logger.info("✓ Vector store initialized successfully")

            # Initialize hybrid retriever (BM25 + reranker)
            hybrid_retriever_service.initialize()
            logger.info("✓ Hybrid retriever initialized successfully")
        except Exception as e:
            logger.error(f"⚠️ Vector store initialization warning: {e}")
            logger.info("Server will continue, but RAG features may not work")
    else:
        logger.info("Skipping model warm-up at startup (WARMUP_MODELS_ON_STARTUP=false)")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down Medical Chatbot backend...")
    if db_service.client:
        db_service.client.close()
        logger.info("✓ MongoDB connection closed")


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title="Medical Chatbot API",
    description="RAG-based Medical Chatbot with Authentication",
    version="2.0.0",
    lifespan=lifespan
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=False,  # Important when using "*"
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Added OPTIONS
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(chat_router, prefix="/api", tags=["chat"])


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Medical Chatbot API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "features": [
            "User Authentication (Signup/Login/Logout)",
            "Chat History Management",
            "Automatic New Chat Creation",
            "Chat Saving & Deletion",
            "RAG with Pinecone vector store",
            "Groq LLM (LLaMA 3.1 8B Instant)",
            "PubMedBERT embeddings (medical-optimized)",
            "Two-turn conversation flow",
            "Safety content moderation",
            "Text simplification",
            "Multi-language translation"
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    mongo_status = "unhealthy"
    try:
        if db_service.db is not None:
            await db_service.db.command('ping')
            mongo_status = "healthy"
    except Exception as e:
        logger.error(f"Health check MongoDB error: {e}")
    
    vector_status = "initialized" if retriever_service.initialized else "not_initialized"
    
    return {
        "status": "healthy" if mongo_status == "healthy" else "degraded",
        "service": "Medical Chatbot Backend",
        "version": "2.0.0",
        "mongodb": mongo_status,
        "vector_store": vector_status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
