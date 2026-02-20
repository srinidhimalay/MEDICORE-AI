import os
import logging
import asyncio
from typing import List, Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM service using Groq (LLaMA 3.1 8B Instant).
    Handles all LLM interactions for the medical chatbot.
    """

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not found in environment. "
                "Please add it to your .env file."
            )
        
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.1-8b-instant"
        logger.info("✓ LLM Service initialized with Groq")

    async def _chat_completion(self, **kwargs):
        """
        Thread-safe async wrapper for Groq API calls.
        Groq client is blocking, so we run it in a thread pool.
        """
        def _call():
            return self.client.chat.completions.create(**kwargs)

        return await asyncio.to_thread(_call)

    async def _chat_completion_stream(self, **kwargs):
        """
        Streaming wrapper for Groq API calls.
        Yields chunks as they arrive.
        """
        import queue
        import threading

        q = queue.Queue()

        def _stream():
            try:
                kwargs['stream'] = True
                stream = self.client.chat.completions.create(**kwargs)
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        q.put(chunk.choices[0].delta.content)
                q.put(None)  # Signal completion
            except Exception as e:
                q.put(e)

        thread = threading.Thread(target=_stream)
        thread.start()

        while True:
            try:
                item = await asyncio.to_thread(q.get, timeout=30)
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
            except Exception:
                break

        thread.join(timeout=5)

    async def assess_query_specificity(self, question: str) -> bool:
        """
        Determine if a follow-up question is needed based on query specificity.

        Returns:
            True if follow-up is needed, False if query is specific enough
        """
        try:
            prompt = f"""Analyze this medical query and determine if a follow-up clarifying question is needed BEFORE providing information.

Query: "{question}"

A follow-up is NEEDED when:
- Symptoms are vague (e.g., "I feel bad", "my stomach hurts", "I'm not well")
- Multiple possible body systems could be involved
- No duration, severity, or context is provided
- The query is ambiguous and could mean many different things

A follow-up is NOT needed when:
- The query asks about a specific condition (e.g., "What is diabetes?", "Tell me about asthma")
- The query asks about a specific medication (e.g., "Side effects of aspirin", "What is ibuprofen?")
- The query is already detailed with duration/severity/context (e.g., "I've had a sharp pain in my lower right abdomen for 2 days")
- The query asks a general health question (e.g., "How to lower cholesterol?", "Benefits of exercise")
- The query asks about a specific procedure or test (e.g., "What is an MRI?")

Respond with ONLY one word: NEEDED or NOT_NEEDED"""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You classify medical queries. Respond with exactly one word."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=10,
            )

            result = completion.choices[0].message.content.strip().upper()
            needs_followup = "NEEDED" in result and "NOT" not in result

            logger.info(f"Query specificity assessment: {'needs followup' if needs_followup else 'specific enough'}")
            return needs_followup

        except Exception as e:
            logger.error(f"Query specificity assessment error: {e}", exc_info=True)
            return True  # Default to asking follow-up on error

    async def reformulate_for_retrieval(self, user_query: str, followup_answer: str = "") -> str:
        """
        Convert conversational query into optimized medical search terms.

        Args:
            user_query: Original user question
            followup_answer: User's answer to follow-up question (if any)

        Returns:
            Reformulated search query optimized for vector retrieval
        """
        try:
            context_part = f'\nAdditional context from patient: "{followup_answer}"' if followup_answer else ''

            prompt = f"""Convert this patient query into an optimized medical search query for retrieving relevant medical encyclopedia entries.

Patient query: "{user_query}"{context_part}

Rules:
- Include both layman terms AND medical terminology
- Extract key symptoms, body parts, and conditions mentioned
- Add related medical terms that would appear in a medical encyclopedia
- Keep it under 50 words
- Output ONLY the search query, nothing else

Example:
Patient: "my stomach hurts after eating greasy food"
Search: "abdominal pain epigastric pain after eating fatty foods dyspepsia gastritis gallbladder disease postprandial pain"

Example:
Patient: "my head hurts really bad on the right side"
Search: "headache unilateral cephalgia right-sided head pain migraine cluster headache tension headache severe headache"
"""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You convert patient queries into medical search terms. Output only the search query."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100,
            )

            reformulated = completion.choices[0].message.content.strip()

            # Ensure reasonable length
            if len(reformulated) > 300:
                reformulated = reformulated[:300]

            logger.info(f"Query reformulated: {reformulated[:100]}...")
            return reformulated or user_query

        except Exception as e:
            logger.error(f"Query reformulation error: {e}", exc_info=True)
            return user_query  # Fall back to original query

    async def generate_followup(
        self,
        question: str,
        max_tokens: int = 100
    ) -> str:
        """
        Generate a single follow-up question to gather more context.
        
        Args:
            question: User's initial question
            max_tokens: Maximum tokens for response
            
        Returns:
            Follow-up question string
        """
        try:
            prompt = f"""A patient seeking medical information said: "{question}"

Ask exactly ONE focused clarifying question (under 25 words) that will most improve the quality of information you can provide.

Choose the single most clinically relevant dimension:
- Duration and onset: "How long?" and "Sudden or gradual?"
- Severity and pattern: "Constant or intermittent?" "Mild, moderate, or severe?"
- Location and radiation: "Where exactly?" "Does it spread?"
- Associated symptoms: "Any other symptoms like fever, nausea, or fatigue?"
- Triggers and relief: "What makes it better or worse?"
- Medical history relevance: "Any known conditions or current medications?"

Output ONLY the question. Be conversational, not clinical."""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a medical triage assistant. Ask ONE precise, conversational follow-up question to gather the most useful clinical detail."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=max_tokens,
            )

            followup = completion.choices[0].message.content.strip()
            
            # Clean up - take only first line/question
            followup = followup.split("\n")[0].strip()
            
            # Remove any numbering or bullets
            if followup.startswith(("1.", "2.", "-", "•", "*")):
                followup = followup[2:].strip()
            
            # Ensure reasonable length
            if len(followup) > 150:
                followup = followup[:147] + "..."

            logger.info(f"Generated follow-up: {followup}")
            return followup or "How long have you been experiencing this?"

        except Exception as e:
            logger.error(f"Follow-up generation error: {e}", exc_info=True)
            return "Could you provide more details about your symptoms?"

    async def generate_response(
        self,
        query: str,
        followup_answer: str,
        context_chunks: List[str],
        max_tokens: int = 1500,
        user_profile: Optional[dict] = None,
        session_memory: Optional[List[str]] = None
    ) -> str:
        """
        Generate main medical response using RAG context.

        Args:
            query: Original user question
            followup_answer: User's answer to follow-up question
            context_chunks: Retrieved context from vector store
            max_tokens: Maximum tokens for response
            user_profile: Optional user health profile for personalization

        Returns:
            Formatted medical response
        """
        try:
            system_prompt = self._get_system_prompt()

            # Prepare context
            if context_chunks:
                context_parts = []
                for chunk in context_chunks:
                    context_parts.append(chunk)
                context_text = "\n\n---\n\n".join(context_parts)
            else:
                context_text = "No specific context available from medical knowledge base."

            # Build profile context if available
            profile_context = ""
            if user_profile:
                profile_parts = []
                if user_profile.get("age"):
                    profile_parts.append(f"Age: {user_profile['age']}")
                if user_profile.get("sex"):
                    profile_parts.append(f"Sex: {user_profile['sex']}")
                if user_profile.get("known_conditions"):
                    profile_parts.append(f"Known conditions: {', '.join(user_profile['known_conditions'])}")
                if user_profile.get("current_medications"):
                    profile_parts.append(f"Current medications: {', '.join(user_profile['current_medications'])}")
                if user_profile.get("allergies"):
                    profile_parts.append(f"Allergies: {', '.join(user_profile['allergies'])}")
                if profile_parts:
                    profile_context = "\n\nPatient Context (provided by user, use to personalize response):\n" + "\n".join(f"- {p}" for p in profile_parts)

            # Build session memory context
            memory_context = ""
            if session_memory:
                memory_context = "\n\nPrevious Session Context (use for continuity, do NOT repeat this info unless relevant):\n" + "\n".join(f"- {s}" for s in session_memory[:3])

            # Build user message
            followup_section = f"\nAdditional Information: {followup_answer}" if followup_answer else ""
            user_message = f"""Original Question: {query}{followup_section}{profile_context}{memory_context}

Medical Context from Knowledge Base:
{context_text}

Please provide a comprehensive response following the format specified."""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=max_tokens,
            )

            response = completion.choices[0].message.content.strip()
            
            logger.info(f"Generated response ({len(response)} chars)")
            return response

        except Exception as e:
            logger.error(f"Response generation error: {e}", exc_info=True)
            raise

    async def generate_response_stream(
        self,
        query: str,
        followup_answer: str,
        context_chunks: List[str],
        max_tokens: int = 1500,
        user_profile: Optional[dict] = None,
        session_memory: Optional[List[str]] = None
    ):
        """
        Stream main medical response using RAG context via SSE.
        Yields text chunks as they arrive from the LLM.
        """
        try:
            # Use the same system prompt as non-streaming version
            system_prompt = self._get_system_prompt()

            # Build context and user message (same logic as generate_response)
            if context_chunks:
                context_parts = []
                for chunk in context_chunks:
                    context_parts.append(chunk)
                context_text = "\n\n---\n\n".join(context_parts)
            else:
                context_text = "No specific context available from medical knowledge base."

            profile_context = ""
            if user_profile:
                profile_parts = []
                if user_profile.get("age"):
                    profile_parts.append(f"Age: {user_profile['age']}")
                if user_profile.get("sex"):
                    profile_parts.append(f"Sex: {user_profile['sex']}")
                if user_profile.get("known_conditions"):
                    profile_parts.append(f"Known conditions: {', '.join(user_profile['known_conditions'])}")
                if user_profile.get("current_medications"):
                    profile_parts.append(f"Current medications: {', '.join(user_profile['current_medications'])}")
                if user_profile.get("allergies"):
                    profile_parts.append(f"Allergies: {', '.join(user_profile['allergies'])}")
                if profile_parts:
                    profile_context = "\n\nPatient Context (provided by user, use to personalize response):\n" + "\n".join(f"- {p}" for p in profile_parts)

            memory_context = ""
            if session_memory:
                memory_context = "\n\nPrevious Session Context (use for continuity, do NOT repeat this info unless relevant):\n" + "\n".join(f"- {s}" for s in session_memory[:3])

            followup_section = f"\nAdditional Information: {followup_answer}" if followup_answer else ""
            user_message = f"""Original Question: {query}{followup_section}{profile_context}{memory_context}

Medical Context from Knowledge Base:
{context_text}

Please provide a comprehensive response following the format specified."""

            async for chunk in self._chat_completion_stream(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=max_tokens,
            ):
                yield chunk

        except Exception as e:
            logger.error(f"Streaming response error: {e}", exc_info=True)
            yield f"\n\nError generating response: {str(e)}"

    def _get_system_prompt(self) -> str:
        """Return the system prompt (extracted for reuse between streaming/non-streaming)."""
        return """You are MediCore, a clinical medical information assistant built for educational purposes.

IDENTITY AND SCOPE:
- You provide evidence-based medical information sourced ONLY from the provided context.
- You do NOT diagnose, prescribe, or replace professional medical judgment.
- You serve patients seeking to understand their health better.

CORE RULES:
1. ONLY use information present in the provided medical context. If the context does not contain relevant information, say: "My knowledge base does not contain sufficient information on this topic. Please consult a healthcare professional."
2. NEVER fabricate medical facts, statistics, drug dosages, or treatment protocols.
3. NEVER state or imply a diagnosis. Use language like "this could be consistent with" or "common causes include" rather than "you have" or "this is."
4. When the user describes symptoms, reason through them systematically before presenting information.
5. Distinguish clearly between emergency, urgent, and routine situations.

CLINICAL REASONING APPROACH:
When a user describes symptoms, follow this internal reasoning (do not output these steps):
- Identify the primary complaint and any secondary symptoms.
- Consider the anatomical system(s) involved.
- Match symptoms against the provided context for relevant conditions.
- Assess severity indicators (duration, intensity, red flags).
- Formulate an informative, layered response.

RESPONSE STRUCTURE - Adapt format to query type. Do NOT force irrelevant sections:

For SYMPTOM queries (e.g., "I have a headache"):
  **Understanding Your Concern** - Empathetic acknowledgment and clinical context.
  **What This Could Indicate** - Conditions from context, most common first, with distinguishing features.
  **Key Symptoms to Monitor** - Symptoms that differentiate conditions or indicate worsening.
  **Recommended Steps** - Self-care, what to track, lifestyle modifications.
  **Seek Medical Attention If** - Concrete red flags (e.g., "if pain persists beyond 72 hours" not "if it gets worse").

For CONDITION/DISEASE queries (e.g., "What is diabetes?"):
  **Overview** - Clear explanation.
  **Causes and Risk Factors** - From context.
  **Signs and Symptoms** - Characteristic presentation.
  **Management and Treatment** - General approaches (never prescribe specific doses).
  **Living With This Condition** - Practical lifestyle guidance.

For MEDICATION queries (e.g., "Tell me about ibuprofen"):
  **Medication Overview** - What it is and drug class.
  **Common Uses** - Approved indications.
  **Important Safety Information** - Side effects, contraindications, interactions.
  **Usage Guidance** - General guidance (defer to prescribing physician for dosing).

For GENERAL HEALTH queries (e.g., "How to improve sleep?"):
  Use clear, well-organized headings appropriate to the topic. No forced clinical structure.

TONE: Professional yet warm. Use plain language first, medical terms in parentheses. Acknowledge uncertainty honestly.

MANDATORY CLOSING (always include):
---
*This information is for educational purposes only and is not a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider.*"""

    async def describe_image(self, image_base64: str, mime_type: str, user_message: str) -> str:
        """
        Use the vision model to produce a concise clinical description of the image.
        This description is then fed into the normal RAG pipeline.
        """
        try:
            completion = await self._chat_completion(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a clinical observation assistant. Describe the medical image in 2-4 sentences. "
                            "Include: what body part or area is shown, visible abnormalities (color, texture, shape, size), "
                            "and any notable features. Use precise medical terminology. Do NOT diagnose or give advice — "
                            "only describe what you see."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_message or "Describe this medical image."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.3,
                max_tokens=300,
            )

            description = completion.choices[0].message.content.strip()
            logger.info(f"Image described: {description[:100]}...")
            return description

        except Exception as e:
            logger.error(f"Image description error: {e}", exc_info=True)
            raise

    async def simplify_text(self, text: str, max_tokens: int = 500) -> str:
        """
        Simplify medical text for easier understanding.
        
        Args:
            text: Complex medical text to simplify
            max_tokens: Maximum tokens for response
            
        Returns:
            Simplified text
        """
        try:
            prompt = f"""Simplify this medical explanation using very simple language that anyone can understand.

Rules:
- Use short, simple sentences
- Avoid medical jargon
- Explain technical terms in plain language
- Keep it concise (2-3 paragraphs max)
- Maintain accuracy

Text to simplify:
{text}

Provide ONLY the simplified version, nothing else."""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You simplify medical information for general audiences using clear, simple language."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=max_tokens,
            )

            simplified = completion.choices[0].message.content.strip()
            
            logger.info("Text simplified successfully")
            return simplified

        except Exception as e:
            logger.error(f"Simplification error: {e}", exc_info=True)
            return "Unable to simplify the text at this time. Please try again."

    async def translate_text(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
        max_tokens: int = 3000
    ) -> str:
        """
        Translate text to target language using LLM.
        
        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'es', 'fr', 'hi')
            source_language: Source language code (default: auto-detect)
            max_tokens: Maximum tokens for response
            
        Returns:
            Translated text
        """
        try:
            # Language name mappings
            language_names = {
                "en": "English",
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "zh": "Chinese",
                "ar": "Arabic",
                "hi": "Hindi",
                "ta": "Tamil",
                "te": "Telugu",
                "mr": "Marathi",
                "bn": "Bengali",
                "kn": "Kannada"
            }
            
            target_name = language_names.get(target_language, target_language)
            
            prompt = f"""Translate the following text to {target_name}. 
Maintain medical terminology accuracy and professional tone.
Only output the translated text, nothing else.

Text to translate:
{text}"""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a professional medical translator. Translate accurately to {target_name}."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=max_tokens,
            )

            translated = completion.choices[0].message.content.strip()
            
            logger.info(f"Text translated to {target_language}")
            return translated

        except Exception as e:
            logger.error(f"Translation error: {e}", exc_info=True)
            return text  # Return original text if translation fails

    async def detect_language(self, text: str) -> str:
        """
        Detect the language of the input text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Language code (e.g., 'en', 'es', 'hi')
        """
        try:
            prompt = f"""Detect the language of this text and return ONLY the language code (e.g., 'en', 'es', 'fr', 'hi', 'ta'):

Text: {text}

Language code:"""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a language detector. Return only the ISO language code."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=10,
            )

            lang_code = completion.choices[0].message.content.strip().lower()
            
            # Validate and normalize
            valid_codes = ["en", "es", "fr", "de", "zh", "ar", "hi", "ta", "te", "mr", "bn", "kn"]
            if lang_code in valid_codes:
                return lang_code
            else:
                return "en"  # Default to English

        except Exception as e:
            logger.error(f"Language detection error: {e}", exc_info=True)
            return "en"

    async def summarize_conversation(self, messages: list) -> str:
        """
        Summarize a completed conversation for cross-session memory.

        Args:
            messages: List of {"role": str, "content": str} dicts

        Returns:
            A concise summary of the conversation's medical topics and key points.
        """
        try:
            conversation_text = "\n".join(
                f"{'Patient' if m['role'] == 'user' else 'MediCore'}: {m['content'][:300]}"
                for m in messages[:10]
            )

            prompt = f"""Summarize this medical conversation in 2-3 sentences. Focus on:
- The patient's main concern or question
- Key conditions, symptoms, or medications discussed
- Any important advice or follow-up recommendations given

Conversation:
{conversation_text}

Summary:"""

            completion = await self._chat_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You summarize medical conversations concisely for context continuity."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200,
            )

            summary = completion.choices[0].message.content.strip()
            logger.info(f"Conversation summarized ({len(summary)} chars)")
            return summary

        except Exception as e:
            logger.error(f"Summarization error: {e}", exc_info=True)
            return ""


# Singleton instance
llm_service = LLMService()