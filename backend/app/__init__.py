"""
Medical Chatbot Application Package

This package contains the core application logic for the medical chatbot,
including chat endpoints, LLM service, vector store retrieval, and safety filters.
"""

__version__ = "1.0.0"
__author__ = "Medical Chatbot Team"

# Import main components for easier access
from app.chat import router as chat_router
from app.llm import llm_service
from app.retriever import retriever_service
from app.safety import validate_message

__all__ = [
    "chat_router",
    "llm_service",
    "retriever_service",
    "validate_message",
]