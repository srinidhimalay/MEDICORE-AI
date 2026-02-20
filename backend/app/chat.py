from fastapi import APIRouter, HTTPException, Request, status, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import List, Optional, AsyncGenerator
from datetime import datetime
from uuid import uuid4
import json
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.llm import llm_service
from app.retriever import retriever_service
from app.hybrid_retriever import hybrid_retriever_service
from app.safety import validate_message, validate_message_async, sanitize_input
from app.triage import assess_triage_level
from app.database import db_service
from app.auth import hash_password, verify_password, create_access_token
from app.live_context import get_live_context
from app.lab_reference import parse_lab_text, format_lab_table_as_context
from jose import jwt, JWTError
import logging
import os
import asyncio

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET", "your-fallback-secret")
ALGORITHM = "HS256"


# ==================== AUTH DEPENDENCY ====================

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user_id"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[str]:
    """Verify JWT token and return user_id (optional)"""
    if credentials is None:
        return None
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        return user_id
    except JWTError:
        return None


# ==================== SESSION MEMORY HELPERS ====================

async def get_session_summaries(user_id: str, limit: int = 3) -> List[str]:
    """Retrieve recent conversation summaries for cross-session memory."""
    try:
        summaries_collection = db_service.get_collection("chat_summaries")
        cursor = summaries_collection.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(limit)

        summaries = []
        async for doc in cursor:
            summaries.append(doc["summary"])
        return summaries
    except Exception as e:
        logger.warning(f"Could not fetch session summaries: {e}")
        return []


async def summarize_and_store_chat(chat_id: str, user_id: str, messages: list):
    """Summarize a completed conversation and store it for future context."""
    try:
        if len(messages) < 2:
            return

        summary = await llm_service.summarize_conversation(messages)
        if not summary:
            return

        summaries_collection = db_service.get_collection("chat_summaries")
        await summaries_collection.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "summary": summary,
                    "created_at": datetime.utcnow(),
                }
            },
            upsert=True
        )
        logger.info(f"Stored conversation summary for chat {chat_id}")
    except Exception as e:
        logger.warning(f"Could not store conversation summary: {e}")


# ==================== PYDANTIC MODELS ====================

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v not in ['user', 'assistant', 'system']:
            raise ValueError('Role must be user, assistant, or system')
        return v


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    chat_id: Optional[str] = None
    awaiting_followup: bool = Field(default=False)
    
    @field_validator('message')
    @classmethod
    def sanitize_message(cls, v):
        return sanitize_input(v)


class ChatResponse(BaseModel):
    response: str
    awaiting_followup: bool
    sources: Optional[List[str]] = None
    chat_id: str
    confidence: Optional[str] = None  # "high", "medium", "low"
    triage: Optional[dict] = None     # {"level", "reason", "color", "label", "icon"}


class NewChatResponse(BaseModel):
    chat_id: str
    message: str


class ChatHistoryItem(BaseModel):
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ChatHistoryResponse(BaseModel):
    chats: List[ChatHistoryItem]


class ChatDetailResponse(BaseModel):
    chat_id: str
    title: str
    messages: List[ChatMessage]
    created_at: datetime
    updated_at: datetime


class SimplifyRequest(BaseModel):
    chat_history: List[ChatMessage] = Field(..., min_items=1)


class SimplifyResponse(BaseModel):
    simplified: str


class TranslateRequest(BaseModel):
    text: str
    target_language: str
    source_language: Optional[str] = "auto"


class TranslateResponse(BaseModel):
    translated_text: str
    detected_language: Optional[str] = None


class DetectLanguageRequest(BaseModel):
    text: str


class DetectLanguageResponse(BaseModel):
    language: str


# ==================== HEALTH PROFILE MODELS ====================

class HealthProfileRequest(BaseModel):
    age: Optional[int] = Field(None, ge=0, le=150)
    sex: Optional[str] = Field(None, pattern="^(male|female|other)$")
    height_cm: Optional[float] = Field(None, ge=0, le=300)
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    blood_type: Optional[str] = None
    known_conditions: Optional[List[str]] = []
    current_medications: Optional[List[str]] = []
    allergies: Optional[List[str]] = []
    family_history: Optional[List[str]] = []
    smoking: Optional[str] = Field(None, pattern="^(never|former|current)$")
    alcohol: Optional[str] = Field(None, pattern="^(none|moderate|heavy)$")
    exercise: Optional[str] = Field(None, pattern="^(sedentary|moderate|active)$")


class HealthProfileResponse(BaseModel):
    age: Optional[int] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    blood_type: Optional[str] = None
    known_conditions: List[str] = []
    current_medications: List[str] = []
    allergies: List[str] = []
    family_history: List[str] = []
    smoking: Optional[str] = None
    alcohol: Optional[str] = None
    exercise: Optional[str] = None


# ==================== LAB RESULT MODELS ====================

class LabValue(BaseModel):
    test_name: str
    value: float
    unit: str
    normal_low: Optional[float] = None
    normal_high: Optional[float] = None
    status: str  # "normal" | "high" | "low" | "critical_high" | "critical_low"


class LabResultResponse(BaseModel):
    lab_values: List[LabValue]
    interpretation: str
    chat_id: str
    raw_extracted_text: str
    sources: Optional[List[str]] = None


# ==================== FEEDBACK MODELS ====================

class FeedbackRequest(BaseModel):
    chat_id: str
    message_index: int = Field(..., ge=0)
    rating: int = Field(..., ge=-1, le=1)  # -1 thumbs down, 1 thumbs up
    comment: Optional[str] = Field(None, max_length=500)


class DetectLanguageResponse(BaseModel):
    language: str


# ==================== AUTH ENDPOINTS ====================

@router.post("/auth/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(request: Request, signup_data: SignupRequest):
    """User registration"""
    try:
        users_collection = db_service.get_collection("users")

        # Check if user exists
        existing_user = await users_collection.find_one({"email": signup_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hash password
        hashed_password = hash_password(signup_data.password)

        # Create user
        user_doc = {
            "email": signup_data.email,
            "password": hashed_password,
            "name": signup_data.name,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = await users_collection.insert_one(user_doc)
        user_id = str(result.inserted_id)

        # Generate token
        access_token = create_access_token({"sub": user_id})

        logger.info(f"New user registered: {signup_data.email}")

        return AuthResponse(
            access_token=access_token,
            user={
                "id": user_id,
                "email": signup_data.email,
                "name": signup_data.name
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signup failed"
        )


@router.post("/auth/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(request: Request, login_data: LoginRequest):
    """User login"""
    try:
        users_collection = db_service.get_collection("users")

        # Find user
        user = await users_collection.find_one({"email": login_data.email})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Verify password
        if not verify_password(login_data.password, user["password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        user_id = str(user["_id"])

        # Generate token
        access_token = create_access_token({"sub": user_id})

        logger.info(f"User logged in: {login_data.email}")

        return AuthResponse(
            access_token=access_token,
            user={
                "id": user_id,
                "email": user["email"],
                "name": user["name"]
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/auth/logout")
async def logout(user_id: str = Depends(get_current_user)):
    """User logout (client should delete token)"""
    logger.info(f"User logged out: {user_id}")
    return {"message": "Logged out successfully"}


# ==================== CHAT ENDPOINTS ====================

@router.post("/chat/new", response_model=NewChatResponse)
async def create_new_chat(user_id: str = Depends(get_current_user)):
    """Create a new chat session"""
    try:
        chats_collection = db_service.get_collection("chats")
        
        chat_doc = {
            "user_id": user_id,
            "title": "New Chat",
            "messages": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await chats_collection.insert_one(chat_doc)
        chat_id = str(result.inserted_id)
        
        logger.info(f"New chat created: {chat_id} for user: {user_id}")
        
        return NewChatResponse(
            chat_id=chat_id,
            message="New chat created successfully"
        )
    
    except Exception as e:
        logger.error(f"Create chat error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create new chat"
        )


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(user_id: str = Depends(get_current_user)):
    """Get all chat sessions for user"""
    try:
        chats_collection = db_service.get_collection("chats")
        
        cursor = chats_collection.find(
            {"user_id": user_id}
        ).sort("updated_at", -1)
        
        chats = []
        async for chat in cursor:
            chats.append(ChatHistoryItem(
                chat_id=str(chat["_id"]),
                title=chat.get("title", "New Chat"),
                created_at=chat["created_at"],
                updated_at=chat["updated_at"],
                message_count=len(chat.get("messages", []))
            ))
        
        return ChatHistoryResponse(chats=chats)
    
    except Exception as e:
        logger.error(f"Get history error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat history"
        )


@router.get("/chat/{chat_id}", response_model=ChatDetailResponse)
async def get_chat_detail(chat_id: str, user_id: str = Depends(get_current_user)):
    """Get specific chat details"""
    try:
        from bson import ObjectId
        chats_collection = db_service.get_collection("chats")
        
        chat = await chats_collection.find_one({
            "_id": ObjectId(chat_id),
            "user_id": user_id
        })
        
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        
        return ChatDetailResponse(
            chat_id=str(chat["_id"]),
            title=chat.get("title", "New Chat"),
            messages=chat.get("messages", []),
            created_at=chat["created_at"],
            updated_at=chat["updated_at"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chat detail error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chat details"
        )


@router.delete("/chat/{chat_id}")
async def delete_chat(chat_id: str, user_id: str = Depends(get_current_user)):
    """Delete a chat session"""
    try:
        from bson import ObjectId
        chats_collection = db_service.get_collection("chats")
        
        result = await chats_collection.delete_one({
            "_id": ObjectId(chat_id),
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat not found"
            )
        
        logger.info(f"Chat deleted: {chat_id}")
        
        return {"message": "Chat deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete chat error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete chat"
        )


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(request: ChatRequest, req: Request, user_id: Optional[str] = Depends(get_optional_user)):
    """Main chat endpoint with two-turn conversation flow"""
    try:
        from bson import ObjectId
        chats_collection = db_service.get_collection("chats")
        
        # Use anonymous ID for unauthenticated users
        if user_id is None:
            user_id = f"anonymous_{uuid4().hex[:8]}"
        
        logger.info(f"Incoming message: {request.message[:100]}")

        # Create new chat if no chat_id provided
        if not request.chat_id:
            chat_doc = {
                "user_id": user_id,
                "title": request.message[:50],
                "messages": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = await chats_collection.insert_one(chat_doc)
            chat_id = str(result.inserted_id)
        else:
            chat_id = request.chat_id
            
            # Verify chat belongs to user
            chat = await chats_collection.find_one({
                "_id": ObjectId(chat_id),
                "user_id": user_id
            })
            if not chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )

        # Safety validation (two-tier emergency detection + mental health pathway)
        is_valid, safety_message, mental_health_preamble = await validate_message_async(
            request.message, llm_service
        )
        if not is_valid:
            logger.warning(f"Safety check failed: {safety_message[:50]}")

            # Save to database
            await chats_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$push": {
                        "messages": {
                            "$each": [
                                {"role": "user", "content": request.message},
                                {"role": "assistant", "content": safety_message}
                            ]
                        }
                    },
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            return ChatResponse(
                response=safety_message,
                awaiting_followup=False,
                sources=None,
                chat_id=chat_id
            )

        # Fetch health profile for personalized responses (if user is authenticated)
        user_profile = None
        if user_id and not user_id.startswith("anonymous_"):
            try:
                profiles_collection = db_service.get_collection("health_profiles")
                profile = await profiles_collection.find_one({"user_id": user_id})
                if profile:
                    user_profile = {
                        "age": profile.get("age"),
                        "sex": profile.get("sex"),
                        "known_conditions": profile.get("known_conditions", []),
                        "current_medications": profile.get("current_medications", []),
                        "allergies": profile.get("allergies", []),
                    }
            except Exception as e:
                logger.warning(f"Could not fetch health profile: {e}")

        # Fetch session memory for cross-session continuity
        session_memory = []
        if user_id and not user_id.startswith("anonymous_"):
            session_memory = await get_session_summaries(user_id, limit=3)

        # Turn 1: Assess if follow-up is needed or go directly to response
        if not request.awaiting_followup:
            # Check if the query is specific enough to skip follow-up
            needs_followup = await llm_service.assess_query_specificity(request.message)

            if needs_followup:
                # Vague query - ask a follow-up question
                logger.info("Turn 1: Query is vague, generating follow-up question...")

                followup = await llm_service.generate_followup(question=request.message)
                response_text = f"**Follow-up Question:** {followup}"

                # Save to database
                await chats_collection.update_one(
                    {"_id": ObjectId(chat_id)},
                    {
                        "$push": {
                            "messages": {
                                "$each": [
                                    {"role": "user", "content": request.message},
                                    {"role": "assistant", "content": response_text}
                                ]
                            }
                        },
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )

                logger.info(f"Follow-up generated: {followup}")

                return ChatResponse(
                    response=response_text,
                    awaiting_followup=True,
                    sources=None,
                    chat_id=chat_id
                )
            else:
                # Specific query - skip follow-up, go directly to RAG response
                logger.info("Turn 1: Query is specific, skipping follow-up, going directly to RAG...")

                # Reformulate query for better retrieval
                search_query = await llm_service.reformulate_for_retrieval(request.message)

                # Retrieve context using hybrid search (BM25 + vector + reranking)
                retrieval_result = await hybrid_retriever_service.hybrid_search(
                    query=search_query, k=5
                )
                context_chunks = retrieval_result["chunks"]
                confidence = retrieval_result["confidence"]

                if context_chunks:
                    logger.info(f"Retrieved {len(context_chunks)} context chunks (confidence: {confidence})")
                else:
                    logger.warning("No context chunks retrieved")

                # Live context enrichment (PubMed abstracts, drug interactions, FDA events)
                try:
                    live_ctx = await get_live_context(search_query)
                    if live_ctx:
                        context_chunks = context_chunks + [live_ctx]
                        logger.info("Live context appended (%d chars)", len(live_ctx))
                except Exception as lc_err:
                    logger.debug("Live context skipped: %s", lc_err)

                # Generate response (no follow-up answer since we skipped it)
                response_text = await llm_service.generate_response(
                    query=request.message,
                    followup_answer="",
                    context_chunks=context_chunks,
                    user_profile=user_profile,
                    session_memory=session_memory
                )

                # Add confidence caveat for low-confidence results
                if confidence == "low" and context_chunks:
                    response_text = "**Note:** My knowledge base has limited information on this topic. The following is based on the best available matches.\n\n" + response_text

                # Add mental health preamble if applicable
                if mental_health_preamble:
                    response_text = mental_health_preamble + response_text

                logger.info(f"Direct response generated ({len(response_text)} chars)")

                # Save to database
                await chats_collection.update_one(
                    {"_id": ObjectId(chat_id)},
                    {
                        "$push": {
                            "messages": {
                                "$each": [
                                    {"role": "user", "content": request.message},
                                    {"role": "assistant", "content": response_text}
                                ]
                            }
                        },
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )

                # Assess triage level
                triage_result = await assess_triage_level(request.message, llm_service)

                # Return sources
                sources = None
                if context_chunks:
                    sources = [chunk[:200] + "..." if len(chunk) > 200 else chunk
                              for chunk in context_chunks[:3]]

                # Background: summarize this conversation for cross-session memory
                if user_id and not user_id.startswith("anonymous_"):
                    chat_doc = await chats_collection.find_one({"_id": ObjectId(chat_id)})
                    if chat_doc:
                        asyncio.create_task(summarize_and_store_chat(
                            chat_id, user_id, chat_doc.get("messages", [])
                        ))

                return ChatResponse(
                    response=response_text,
                    awaiting_followup=False,
                    sources=sources,
                    chat_id=chat_id,
                    confidence=confidence,
                    triage=triage_result
                )

        # Turn 2: RAG-based response (after follow-up was asked)
        logger.info("Turn 2: Generating RAG-based response after follow-up...")

        # Get chat history to extract original query
        chat = await chats_collection.find_one({"_id": ObjectId(chat_id)})
        messages = chat.get("messages", [])

        original_query = request.message
        if len(messages) >= 1:
            for msg in reversed(messages):
                if msg["role"] == "user":
                    original_query = msg["content"]
                    break

        logger.info(f"Original query: {original_query[:100]}")

        # Reformulate query for better retrieval (combine original + followup context)
        search_query = await llm_service.reformulate_for_retrieval(original_query, request.message)

        # Retrieve context using hybrid search (BM25 + vector + reranking)
        retrieval_result = await hybrid_retriever_service.hybrid_search(
            query=search_query, k=5
        )
        context_chunks = retrieval_result["chunks"]
        confidence = retrieval_result["confidence"]

        if context_chunks:
            logger.info(f"Retrieved {len(context_chunks)} context chunks (confidence: {confidence})")
        else:
            logger.warning("No context chunks retrieved")

        # Live context enrichment
        try:
            live_ctx = await get_live_context(search_query)
            if live_ctx:
                context_chunks = context_chunks + [live_ctx]
                logger.info("Live context appended (%d chars)", len(live_ctx))
        except Exception as lc_err:
            logger.debug("Live context skipped: %s", lc_err)

        # Generate response
        response_text = await llm_service.generate_response(
            query=original_query,
            followup_answer=request.message,
            context_chunks=context_chunks,
            user_profile=user_profile,
            session_memory=session_memory
        )

        # Add confidence caveat for low-confidence results
        if confidence == "low" and context_chunks:
            response_text = "**Note:** My knowledge base has limited information on this topic. The following is based on the best available matches.\n\n" + response_text

        # Add mental health preamble if applicable
        if mental_health_preamble:
            response_text = mental_health_preamble + response_text

        logger.info(f"Response generated ({len(response_text)} chars)")

        # Save to database
        await chats_collection.update_one(
            {"_id": ObjectId(chat_id)},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {"role": "user", "content": request.message},
                            {"role": "assistant", "content": response_text}
                        ]
                    }
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

        # Assess triage level using original query
        triage_result = await assess_triage_level(original_query, llm_service)

        # Return sources
        sources = None
        if context_chunks:
            sources = [chunk[:200] + "..." if len(chunk) > 200 else chunk
                      for chunk in context_chunks[:3]]

        # Background: summarize this conversation for cross-session memory
        if user_id and not user_id.startswith("anonymous_"):
            chat_doc = await chats_collection.find_one({"_id": ObjectId(chat_id)})
            if chat_doc:
                asyncio.create_task(summarize_and_store_chat(
                    chat_id, user_id, chat_doc.get("messages", [])
                ))

        return ChatResponse(
            response=response_text,
            awaiting_followup=False,
            sources=sources,
            chat_id=chat_id,
            confidence=confidence,
            triage=triage_result
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat request: {str(e)}"
        )


@router.post("/chat/stream")
@limiter.limit("20/minute")
async def chat_stream(request: Request, chat_request: ChatRequest, user_id: Optional[str] = Depends(get_optional_user)):
    """Streaming chat endpoint using Server-Sent Events (SSE)"""
    from bson import ObjectId

    async def generate_sse() -> AsyncGenerator[str, None]:
        try:
            chats_collection = db_service.get_collection("chats")

            effective_user_id = user_id or f"anonymous_{uuid4().hex[:8]}"

            # Create or verify chat
            if not chat_request.chat_id:
                chat_doc = {
                    "user_id": effective_user_id,
                    "title": chat_request.message[:50],
                    "messages": [],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                result = await chats_collection.insert_one(chat_doc)
                chat_id = str(result.inserted_id)
            else:
                chat_id = chat_request.chat_id

            # Send chat_id immediately
            yield f"data: {json.dumps({'type': 'chat_id', 'chat_id': chat_id})}\n\n"

            # Safety validation
            is_valid, safety_message, mental_health_preamble = await validate_message_async(
                chat_request.message, llm_service
            )
            if not is_valid:
                yield f"data: {json.dumps({'type': 'content', 'content': safety_message})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'awaiting_followup': False})}\n\n"

                # Save emergency/safety message to DB so it persists
                await chats_collection.update_one(
                    {"_id": ObjectId(chat_id)},
                    {
                        "$push": {"messages": {"$each": [
                            {"role": "user", "content": chat_request.message},
                            {"role": "assistant", "content": safety_message}
                        ]}},
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )
                return

            # Handle follow-up assessment for non-followup turns
            if not chat_request.awaiting_followup:
                needs_followup = await llm_service.assess_query_specificity(chat_request.message)

                if needs_followup:
                    followup = await llm_service.generate_followup(question=chat_request.message)
                    response_text = f"**Follow-up Question:** {followup}"
                    yield f"data: {json.dumps({'type': 'content', 'content': response_text})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'awaiting_followup': True})}\n\n"

                    # Save to DB
                    await chats_collection.update_one(
                        {"_id": ObjectId(chat_id)},
                        {
                            "$push": {"messages": {"$each": [
                                {"role": "user", "content": chat_request.message},
                                {"role": "assistant", "content": response_text}
                            ]}},
                            "$set": {"updated_at": datetime.utcnow()}
                        }
                    )
                    return

            # Get original query for Turn 2
            original_query = chat_request.message
            if chat_request.awaiting_followup:
                chat = await chats_collection.find_one({"_id": ObjectId(chat_id)})
                msgs = chat.get("messages", []) if chat else []
                for msg in reversed(msgs):
                    if msg["role"] == "user":
                        original_query = msg["content"]
                        break

            # Fetch profile
            user_profile = None
            if effective_user_id and not effective_user_id.startswith("anonymous_"):
                try:
                    profiles_collection = db_service.get_collection("health_profiles")
                    profile = await profiles_collection.find_one({"user_id": effective_user_id})
                    if profile:
                        user_profile = {
                            "age": profile.get("age"),
                            "sex": profile.get("sex"),
                            "known_conditions": profile.get("known_conditions", []),
                            "current_medications": profile.get("current_medications", []),
                            "allergies": profile.get("allergies", []),
                        }
                except Exception:
                    pass

            # Fetch session memory
            session_memory = []
            if effective_user_id and not effective_user_id.startswith("anonymous_"):
                session_memory = await get_session_summaries(effective_user_id, limit=3)

            # Reformulate and retrieve
            search_query = await llm_service.reformulate_for_retrieval(
                original_query,
                chat_request.message if chat_request.awaiting_followup else ""
            )
            retrieval_result = await hybrid_retriever_service.hybrid_search(query=search_query, k=5)
            context_chunks = retrieval_result["chunks"]
            confidence = retrieval_result["confidence"]

            # Live context enrichment
            try:
                live_ctx = await get_live_context(search_query)
                if live_ctx:
                    context_chunks = context_chunks + [live_ctx]
                    logger.info("Live context appended (%d chars)", len(live_ctx))
            except Exception as lc_err:
                logger.debug("Live context skipped: %s", lc_err)

            # Triage
            triage_result = await assess_triage_level(original_query, llm_service)
            yield f"data: {json.dumps({'type': 'triage', 'triage': triage_result, 'confidence': confidence})}\n\n"

            # Add mental health preamble if needed
            if mental_health_preamble:
                yield f"data: {json.dumps({'type': 'content', 'content': mental_health_preamble})}\n\n"

            # Confidence caveat
            if confidence == "low" and context_chunks:
                caveat_text = "**Note:** My knowledge base has limited information on this topic. The following is based on the best available matches.\n\n"
                caveat_data = json.dumps({"type": "content", "content": caveat_text})
                yield f"data: {caveat_data}\n\n"

            # Stream the response
            full_response = ""
            async for chunk in llm_service.generate_response_stream(
                query=original_query,
                followup_answer=chat_request.message if chat_request.awaiting_followup else "",
                context_chunks=context_chunks,
                user_profile=user_profile,
                session_memory=session_memory
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

            # Send sources and completion
            sources = None
            if context_chunks:
                sources = [c[:200] + "..." if len(c) > 200 else c for c in context_chunks[:3]]

            yield f"data: {json.dumps({'type': 'done', 'awaiting_followup': False, 'sources': sources})}\n\n"

            # Save full response to DB
            await chats_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$push": {"messages": {"$each": [
                        {"role": "user", "content": chat_request.message},
                        {"role": "assistant", "content": full_response}
                    ]}},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

            # Background: summarize for cross-session memory
            if effective_user_id and not effective_user_id.startswith("anonymous_"):
                chat_doc = await chats_collection.find_one({"_id": ObjectId(chat_id)})
                if chat_doc:
                    asyncio.create_task(summarize_and_store_chat(
                        chat_id, effective_user_id, chat_doc.get("messages", [])
                    ))

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/chat/image")
@limiter.limit("10/minute")
async def chat_image(
    request: Request,
    image: UploadFile = File(...),
    message: str = Form(default="Please analyze this medical image."),
    chat_id: Optional[str] = Form(default=None),
    user_id: Optional[str] = Depends(get_optional_user),
):
    """Analyze an uploaded image using the vision model"""
    import base64
    from bson import ObjectId

    try:
        # Validate file type
        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPEG, PNG, and WebP images are supported"
            )

        # Read and validate size (4MB max)
        contents = await image.read()
        if len(contents) > 4 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image must be under 4MB"
            )

        effective_user_id = user_id or f"anonymous_{uuid4().hex[:8]}"
        chats_collection = db_service.get_collection("chats")

        # Create or use existing chat
        if not chat_id:
            chat_doc = {
                "user_id": effective_user_id,
                "title": message[:50] if message else "Image Analysis",
                "messages": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = await chats_collection.insert_one(chat_doc)
            chat_id = str(result.inserted_id)

        # Step 1: Get clinical description from vision model
        image_b64 = base64.b64encode(contents).decode("utf-8")
        image_description = await llm_service.describe_image(
            image_base64=image_b64,
            mime_type=image.content_type,
            user_message=message,
        )
        logger.info(f"Image described: {image_description[:100]}")

        # Step 2: Combine user message + image description for RAG query
        combined_query = f"{message}\n\nImage observation: {image_description}"

        # Step 3: Reformulate for retrieval
        search_query = await llm_service.reformulate_for_retrieval(combined_query)

        # Step 4: Retrieve context via hybrid search
        retrieval_result = await hybrid_retriever_service.hybrid_search(
            query=search_query, k=5
        )
        context_chunks = retrieval_result["chunks"]
        confidence = retrieval_result["confidence"]
        logger.info(f"Retrieved {len(context_chunks)} chunks for image query (confidence: {confidence})")

        # Step 5: Fetch user profile if authenticated
        user_profile = None
        if effective_user_id and not effective_user_id.startswith("anonymous_"):
            try:
                profiles_collection = db_service.get_collection("health_profiles")
                profile = await profiles_collection.find_one({"user_id": effective_user_id})
                if profile:
                    user_profile = {
                        "age": profile.get("age"),
                        "sex": profile.get("sex"),
                        "known_conditions": profile.get("known_conditions", []),
                        "current_medications": profile.get("current_medications", []),
                        "allergies": profile.get("allergies", []),
                    }
            except Exception:
                pass

        # Step 6: Generate full response through normal RAG pipeline
        response_text = await llm_service.generate_response(
            query=combined_query,
            followup_answer="",
            context_chunks=context_chunks,
            user_profile=user_profile,
        )

        # Save to chat history
        await chats_collection.update_one(
            {"_id": ObjectId(chat_id)},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {"role": "user", "content": f"[Image uploaded] {message}"},
                            {"role": "assistant", "content": response_text}
                        ]
                    }
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

        logger.info(f"Image analyzed for chat {chat_id}")

        sources = None
        if context_chunks:
            sources = [c[:200] + "..." if len(c) > 200 else c for c in context_chunks[:3]]

        return {
            "response": response_text,
            "chat_id": chat_id,
            "awaiting_followup": False,
            "sources": sources,
            "confidence": confidence,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image analysis error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image analysis failed: {str(e)}"
        )


@router.post("/chat/lab-results", response_model=LabResultResponse)
@limiter.limit("5/minute")
async def chat_lab_results(
    request: Request,
    file: UploadFile = File(...),
    context: str = Form(default=""),
    chat_id: Optional[str] = Form(default=None),
    user_id: Optional[str] = Depends(get_optional_user),
):
    """Interpret uploaded lab report (image or PDF) using vision model + RAG pipeline."""
    import base64
    import fitz  # PyMuPDF
    from bson import ObjectId

    try:
        allowed_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPEG, PNG, WebP images or PDF files are supported",
            )

        contents = await file.read()
        max_size = 10 * 1024 * 1024 if file.content_type == "application/pdf" else 4 * 1024 * 1024
        if len(contents) > max_size:
            max_mb = 10 if file.content_type == "application/pdf" else 4
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File must be under {max_mb}MB",
            )

        effective_user_id = user_id or f"anonymous_{uuid4().hex[:8]}"
        chats_collection = db_service.get_collection("chats")

        if not chat_id:
            chat_doc = {
                "user_id": effective_user_id,
                "title": "Lab Results" if not context else context[:50],
                "messages": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            result = await chats_collection.insert_one(chat_doc)
            chat_id = str(result.inserted_id)

        # ── Extract text from file ─────────────────────────────────────────────
        extracted_text = ""

        if file.content_type == "application/pdf":
            # Try PyMuPDF text extraction first
            try:
                pdf_doc = fitz.open(stream=contents, filetype="pdf")
                pages_text = []
                for page in pdf_doc:
                    pages_text.append(page.get_text())
                extracted_text = "\n".join(pages_text).strip()
                pdf_doc.close()
            except Exception as pdf_err:
                logger.warning("PyMuPDF extraction failed: %s", pdf_err)

            # If PDF has no text layer (scanned), fall back to vision model on first page
            if len(extracted_text) < 50:
                logger.info("PDF appears scanned — using vision model for extraction")
                try:
                    pdf_doc = fitz.open(stream=contents, filetype="pdf")
                    page = pdf_doc[0]
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    pdf_doc.close()
                    image_b64 = base64.b64encode(img_bytes).decode("utf-8")
                    extracted_text = await llm_service.describe_image(
                        image_base64=image_b64,
                        mime_type="image/png",
                        user_message=(
                            "This is a medical laboratory report. "
                            "Extract ALL lab test values. For each test output exactly one line: "
                            "TEST_NAME VALUE UNIT\n"
                            "Example: Hemoglobin 12.5 g/dL\n"
                            "Only output the data lines."
                        ),
                    )
                except Exception as vision_err:
                    logger.warning("Vision fallback for PDF failed: %s", vision_err)
        else:
            # Image: use vision model with structured extraction prompt
            image_b64 = base64.b64encode(contents).decode("utf-8")
            extracted_text = await llm_service.describe_image(
                image_base64=image_b64,
                mime_type=file.content_type,
                user_message=(
                    "This is a medical laboratory report. "
                    "Extract ALL lab test values. For each test output exactly one line: "
                    "TEST_NAME VALUE UNIT\n"
                    "Example: Hemoglobin 12.5 g/dL\n"
                    "Only output the data lines, no other text."
                ),
            )

        logger.info("Extracted %d chars from lab report", len(extracted_text))

        # ── Parse and classify lab values ──────────────────────────────────────
        lab_values_raw = parse_lab_text(extracted_text)
        logger.info("Parsed %d recognized lab values", len(lab_values_raw))

        # ── Build LLM context ──────────────────────────────────────────────────
        lab_table = format_lab_table_as_context(lab_values_raw)
        if not lab_table and not extracted_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract any text from the uploaded file",
            )

        combined_query = (
            f"Lab report interpretation.\n"
            f"{('Patient notes: ' + context + chr(10)) if context else ''}"
            f"\n{lab_table if lab_table else extracted_text[:2000]}"
        )

        # ── RAG retrieval ──────────────────────────────────────────────────────
        search_query = await llm_service.reformulate_for_retrieval(combined_query)
        retrieval_result = await hybrid_retriever_service.hybrid_search(query=search_query, k=5)
        context_chunks = retrieval_result["chunks"]

        # Prepend the lab table as the most important context chunk
        if lab_table:
            context_chunks = [lab_table] + context_chunks

        # ── Fetch user profile ─────────────────────────────────────────────────
        user_profile = None
        if effective_user_id and not effective_user_id.startswith("anonymous_"):
            try:
                profiles_collection = db_service.get_collection("health_profiles")
                profile = await profiles_collection.find_one({"user_id": effective_user_id})
                if profile:
                    user_profile = {
                        "age": profile.get("age"),
                        "sex": profile.get("sex"),
                        "known_conditions": profile.get("known_conditions", []),
                        "current_medications": profile.get("current_medications", []),
                        "allergies": profile.get("allergies", []),
                    }
            except Exception:
                pass

        # ── Generate interpretation ────────────────────────────────────────────
        interpretation = await llm_service.generate_response(
            query=combined_query,
            followup_answer="",
            context_chunks=context_chunks,
            user_profile=user_profile,
        )

        # ── Save to chat history ───────────────────────────────────────────────
        await chats_collection.update_one(
            {"_id": ObjectId(chat_id)},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {"role": "user", "content": f"[Lab results uploaded] {context or 'Lab report for interpretation'}"},
                            {"role": "assistant", "content": interpretation},
                        ]
                    }
                },
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

        sources = None
        if context_chunks:
            sources = [c[:200] + "..." if len(c) > 200 else c for c in context_chunks[:3]]

        lab_value_models = [
            LabValue(
                test_name=lv["test_name"],
                value=lv["value"],
                unit=lv["unit"],
                normal_low=lv["normal_low"],
                normal_high=lv["normal_high"],
                status=lv["status"],
            )
            for lv in lab_values_raw
        ]

        return LabResultResponse(
            lab_values=lab_value_models,
            interpretation=interpretation,
            chat_id=chat_id,
            raw_extracted_text=extracted_text[:3000],
            sources=sources,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Lab results error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lab result interpretation failed: {str(e)}",
        )


@router.post("/simplify", response_model=SimplifyResponse)
async def simplify(request: SimplifyRequest, user_id: Optional[str] = Depends(get_optional_user)):
    """Simplify text"""
    try:
        logger.info("Processing simplification request...")
        
        last_response = None
        for msg in reversed(request.chat_history):
            if msg.role == "assistant":
                last_response = msg.content
                break
        
        if not last_response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No assistant response found"
            )
        
        simplified = await llm_service.simplify_text(last_response)
        
        return SimplifyResponse(simplified=simplified)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simplify error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simplification failed"
        )


@router.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest, user_id: str = Depends(get_current_user)):
    """Translate text"""
    try:
        logger.info(f"Translating to {request.target_language}...")
        
        detected_lang = None
        if request.source_language == "auto":
            detected_lang = await llm_service.detect_language(request.text)
        else:
            detected_lang = request.source_language
        
        translated = await llm_service.translate_text(
            text=request.text,
            target_language=request.target_language,
            source_language=detected_lang
        )
        
        return TranslateResponse(
            translated_text=translated,
            detected_language=detected_lang
        )
    
    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Translation failed"
        )


@router.post("/detect-language", response_model=DetectLanguageResponse)
async def detect_language(request: DetectLanguageRequest, user_id: str = Depends(get_current_user)):
    """Detect language"""
    try:
        detected_lang = await llm_service.detect_language(request.text)
        return DetectLanguageResponse(language=detected_lang)
    
    except Exception as e:
        logger.error(f"Detection error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Language detection failed"
        )


# ==================== HEALTH PROFILE ENDPOINTS ====================

@router.post("/profile", response_model=HealthProfileResponse)
async def update_health_profile(request: HealthProfileRequest, user_id: str = Depends(get_current_user)):
    """Create or update user health profile"""
    try:
        profiles_collection = db_service.get_collection("health_profiles")

        profile_data = {
            "user_id": user_id,
            "age": request.age,
            "sex": request.sex,
            "height_cm": request.height_cm,
            "weight_kg": request.weight_kg,
            "blood_type": request.blood_type,
            "known_conditions": request.known_conditions or [],
            "current_medications": request.current_medications or [],
            "allergies": request.allergies or [],
            "family_history": request.family_history or [],
            "smoking": request.smoking,
            "alcohol": request.alcohol,
            "exercise": request.exercise,
            "updated_at": datetime.utcnow()
        }

        # Upsert: update if exists, create if not
        await profiles_collection.update_one(
            {"user_id": user_id},
            {"$set": profile_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )

        logger.info(f"Health profile updated for user: {user_id}")
        return HealthProfileResponse(**{k: v for k, v in profile_data.items() if k not in ("user_id", "updated_at", "created_at")})

    except Exception as e:
        logger.error(f"Profile update error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update health profile"
        )


@router.get("/profile", response_model=HealthProfileResponse)
async def get_health_profile(user_id: str = Depends(get_current_user)):
    """Get user health profile"""
    try:
        profiles_collection = db_service.get_collection("health_profiles")
        profile = await profiles_collection.find_one({"user_id": user_id})

        if not profile:
            return HealthProfileResponse()

        return HealthProfileResponse(
            age=profile.get("age"),
            sex=profile.get("sex"),
            height_cm=profile.get("height_cm"),
            weight_kg=profile.get("weight_kg"),
            blood_type=profile.get("blood_type"),
            known_conditions=profile.get("known_conditions", []),
            current_medications=profile.get("current_medications", []),
            allergies=profile.get("allergies", []),
            family_history=profile.get("family_history", []),
            smoking=profile.get("smoking"),
            alcohol=profile.get("alcohol"),
            exercise=profile.get("exercise"),
        )

    except Exception as e:
        logger.error(f"Get profile error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve health profile"
        )


@router.delete("/profile")
async def delete_health_profile(user_id: str = Depends(get_current_user)):
    """Delete user health profile"""
    try:
        profiles_collection = db_service.get_collection("health_profiles")
        result = await profiles_collection.delete_one({"user_id": user_id})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No health profile found"
            )

        logger.info(f"Health profile deleted for user: {user_id}")
        return {"message": "Health profile deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete profile error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete health profile"
        )


# ==================== FEEDBACK ENDPOINT ====================

@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest, user_id: str = Depends(get_current_user)):
    """Submit feedback (thumbs up/down) on a response"""
    try:
        feedback_collection = db_service.get_collection("feedback")

        feedback_doc = {
            "user_id": user_id,
            "chat_id": request.chat_id,
            "message_index": request.message_index,
            "rating": request.rating,
            "comment": request.comment,
            "created_at": datetime.utcnow()
        }

        await feedback_collection.insert_one(feedback_doc)

        logger.info(f"Feedback submitted: chat={request.chat_id}, rating={request.rating}")
        return {"message": "Feedback submitted successfully"}

    except Exception as e:
        logger.error(f"Feedback error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback"
        )


@router.get("/test")
async def test_endpoint():
    """Test endpoint"""
    return {
        "status": "ok",
        "message": "Chat API is working",
        "endpoints": [
            "POST /api/auth/signup",
            "POST /api/auth/login",
            "POST /api/auth/logout",
            "POST /api/chat/new",
            "GET /api/chat/history",
            "GET /api/chat/{chat_id}",
            "DELETE /api/chat/{chat_id}",
            "POST /api/chat",
            "POST /api/simplify",
            "POST /api/translate",
            "POST /api/detect-language",
            "POST /api/profile",
            "GET /api/profile",
            "DELETE /api/profile",
            "POST /api/feedback"
        ]
    }


@router.get("/debug/mongodb")
async def debug_mongodb():
    """Debug MongoDB connection"""
    try:
        from app.database import db_service
        
        # Try to ping database
        users_collection = db_service.get_collection("users")
        
        # Try to count documents (this will test the connection)
        count = await users_collection.count_documents({})
        
        return {
            "status": "success",
            "message": "MongoDB is working",
            "user_count": count,
            "database": "medical_chatbot"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__
        }