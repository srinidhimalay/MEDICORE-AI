import os
import logging
from typing import List, Optional
from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone

load_dotenv()
logger = logging.getLogger(__name__)


class RetrieverService:
    """
    Vector store service for similarity search using Pinecone.
    Uses the SAME embedding model as ingestion (PubMedBERT).
    """

    def __init__(self):
        self.vectorstore: Optional[PineconeVectorStore] = None
        self.embedding_model: Optional[HuggingFaceEmbeddings] = None
        self.initialized = False

    def initialize(self):
        """Initialize embedding model and Pinecone connection"""
        if self.initialized:
            logger.info("Vector store already initialized")
            return

        try:
            # Get environment variables
            pinecone_api_key = os.getenv("PINECONE_API_KEY")
            pinecone_index = os.getenv("PINECONE_INDEX_NAME", "medicore-ai")
            
            # IMPORTANT: Must match the model used in rag_setup.py
            embedding_model_name = os.getenv(
                "EMBEDDING_MODEL",
                "pritamdeka/S-PubMedBert-MS-MARCO"
            )

            if not pinecone_api_key:
                raise RuntimeError("PINECONE_API_KEY not found in environment")

            logger.info(f"Initializing embedding model: {embedding_model_name}")
            
            # Initialize embedding model - MUST match ingestion
            self.embedding_model = HuggingFaceEmbeddings(
                model_name=embedding_model_name,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={
                    'normalize_embeddings': True,
                    'batch_size': 32  # For retrieval, smaller batch is fine
                }
            )

            logger.info(f"Connecting to Pinecone index: {pinecone_index}")
            
            # Initialize Pinecone client
            pc = Pinecone(api_key=pinecone_api_key)
            
            # Verify index exists
            existing_indexes = [index.name for index in pc.list_indexes()]
            if pinecone_index not in existing_indexes:
                raise RuntimeError(
                    f"Pinecone index '{pinecone_index}' not found. "
                    f"Please run ingestion/rag_setup.py first."
                )
            
            # Create vector store
            self.vectorstore = PineconeVectorStore(
                index_name=pinecone_index,
                embedding=self.embedding_model,
                pinecone_api_key=pinecone_api_key
            )

            self.initialized = True
            logger.info("✓ Vector store initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}", exc_info=True)
            raise

    async def search(self, query: str, k: int = 5) -> List[str]:
        """
        Perform similarity search and return context chunks.

        Args:
            query: Search query
            k: Number of results to return (default: 5)

        Returns:
            List of text chunks (strings)
        """
        if not self.initialized:
            self.initialize()

        try:
            logger.info(f"Searching for: '{query[:100]}'...")

            # Perform async similarity search
            docs = await self.vectorstore.asimilarity_search(query, k=k)

            # Extract text content from documents
            context_chunks = [doc.page_content for doc in docs]

            logger.info(f"✓ Found {len(context_chunks)} relevant chunks")

            return context_chunks

        except Exception as e:
            logger.error(f"Similarity search failed: {e}", exc_info=True)
            return []

    async def search_with_scores(self, query: str, k: int = 5) -> dict:
        """
        Perform similarity search and return context chunks with confidence scores.

        Args:
            query: Search query
            k: Number of results to return (default: 5)

        Returns:
            Dict with 'chunks' (list of dicts with text, score, metadata)
            and 'confidence' (high/medium/low) and 'avg_score' (float)
        """
        if not self.initialized:
            self.initialize()

        try:
            logger.info(f"Searching with scores for: '{query[:100]}'...")

            # Perform similarity search with scores
            docs_with_scores = await self.vectorstore.asimilarity_search_with_score(query, k=k)

            chunks = []
            scores = []
            for doc, score in docs_with_scores:
                chunks.append({
                    "text": doc.page_content,
                    "score": float(score),
                    "metadata": doc.metadata
                })
                scores.append(float(score))

            # Compute confidence level based on average score
            # Note: Pinecone cosine similarity returns higher = more similar
            avg_score = sum(scores) / len(scores) if scores else 0.0

            if avg_score > 0.8:
                confidence = "high"
            elif avg_score > 0.5:
                confidence = "medium"
            else:
                confidence = "low"

            logger.info(f"✓ Found {len(chunks)} chunks, avg_score={avg_score:.3f}, confidence={confidence}")

            return {
                "chunks": chunks,
                "confidence": confidence,
                "avg_score": avg_score
            }

        except Exception as e:
            logger.error(f"Scored similarity search failed: {e}", exc_info=True)
            return {"chunks": [], "confidence": "low", "avg_score": 0.0}

    def search_sync(self, query: str, k: int = 5) -> List[str]:
        """
        Synchronous version of search (for non-async contexts).
        """
        if not self.initialized:
            self.initialize()

        try:
            logger.info(f"Searching (sync) for: '{query[:100]}'...")
            
            # Perform synchronous similarity search
            docs = self.vectorstore.similarity_search(query, k=k)
            
            # Extract text content
            context_chunks = [doc.page_content for doc in docs]
            
            logger.info(f"✓ Found {len(context_chunks)} relevant chunks")
            
            return context_chunks

        except Exception as e:
            logger.error(f"Sync similarity search failed: {e}", exc_info=True)
            return []

    def get_retriever(self, k: int = 5):
        """
        Get LangChain retriever interface.
        
        Args:
            k: Number of results to return
            
        Returns:
            LangChain retriever object
        """
        if not self.initialized:
            self.initialize()
        
        return self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )


# Singleton instance
retriever_service = RetrieverService()