import os
import logging
import asyncio
import hashlib
from typing import List, Optional
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from app.retriever import retriever_service

load_dotenv()
logger = logging.getLogger(__name__)


class HybridRetrieverService:
    """
    Hybrid retrieval combining:
    1. Pinecone vector similarity search (semantic)
    2. BM25 keyword search (exact matching)
    3. Reciprocal Rank Fusion to merge results
    4. Cross-encoder reranking for final selection
    """

    def __init__(self):
        self.bm25_index: Optional[BM25Okapi] = None
        self.corpus: List[str] = []
        self.corpus_metadata: List[dict] = []
        self.reranker: Optional[CrossEncoder] = None
        self.initialized = False

    def initialize(self):
        """Initialize BM25 index and cross-encoder reranker."""
        if self.initialized:
            return

        try:
            # Ensure base retriever is initialized
            if not retriever_service.initialized:
                retriever_service.initialize()

            # Initialize cross-encoder reranker
            logger.info("Loading cross-encoder reranker...")
            self.reranker = CrossEncoder(
                'cross-encoder/ms-marco-MiniLM-L-6-v2',
                max_length=512
            )
            logger.info("✓ Cross-encoder reranker loaded")

            self.initialized = True
            logger.info("✓ Hybrid retriever initialized")

        except Exception as e:
            logger.error(f"Failed to initialize hybrid retriever: {e}", exc_info=True)
            raise

    def _build_bm25_from_docs(self, documents: List[str]):
        """Build BM25 index from a list of document texts."""
        tokenized_corpus = [doc.lower().split() for doc in documents]
        self.bm25_index = BM25Okapi(tokenized_corpus)
        self.corpus = documents

    def _rerank(self, query: str, documents: List[str], top_k: int = 5) -> List[dict]:
        """
        Rerank documents using cross-encoder.

        Args:
            query: The search query
            documents: List of document texts to rerank
            top_k: Number of top results to return

        Returns:
            List of dicts with 'text' and 'score', sorted by relevance
        """
        if not self.reranker or not documents:
            return [{"text": doc, "score": 0.0} for doc in documents[:top_k]]

        pairs = [(query, doc) for doc in documents]
        scores = self.reranker.predict(pairs)

        # Sort by score descending
        scored_docs = list(zip(documents, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        return [
            {"text": doc, "score": float(score)}
            for doc, score in scored_docs[:top_k]
        ]

    async def hybrid_search(
        self,
        query: str,
        k: int = 5,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
        candidates_multiplier: int = 3
    ) -> dict:
        """
        Perform hybrid search with BM25 + vector + reranking.

        Args:
            query: Search query
            k: Final number of results to return
            vector_weight: Weight for vector search in RRF
            bm25_weight: Weight for BM25 search in RRF
            candidates_multiplier: How many extra candidates to fetch before reranking

        Returns:
            Dict with 'chunks' (list of text strings), 'confidence', 'avg_score'
        """
        if not self.initialized:
            self.initialize()

        try:
            num_candidates = k * candidates_multiplier

            # Step 1: Get vector search results with scores
            logger.info(f"Hybrid search for: '{query[:80]}...'")
            vector_result = await retriever_service.search_with_scores(
                query=query,
                k=num_candidates
            )
            vector_chunks = vector_result["chunks"]

            # Step 2: Build BM25 index from vector results
            # (We use the vector results as our BM25 corpus since we don't
            #  maintain a separate full-corpus BM25 index in memory)
            if vector_chunks:
                all_texts = [c["text"] for c in vector_chunks]
                self._build_bm25_from_docs(all_texts)

                # Get BM25 scores for the same documents
                tokenized_query = query.lower().split()
                bm25_scores = self.bm25_index.get_scores(tokenized_query)

                # Step 3: Reciprocal Rank Fusion
                rrf_k = 60  # Standard RRF constant

                # Build a mapping from doc hash to combined score
                doc_scores = {}
                doc_texts = {}

                # Add vector scores (already sorted by relevance)
                for rank, chunk in enumerate(vector_chunks):
                    doc_hash = hashlib.md5(chunk["text"].encode()).hexdigest()
                    rrf_score = vector_weight / (rrf_k + rank + 1)
                    doc_scores[doc_hash] = doc_scores.get(doc_hash, 0) + rrf_score
                    doc_texts[doc_hash] = chunk["text"]

                # Add BM25 scores (sort by BM25 score to get ranks)
                bm25_ranked = sorted(
                    range(len(bm25_scores)),
                    key=lambda i: bm25_scores[i],
                    reverse=True
                )
                for rank, idx in enumerate(bm25_ranked):
                    text = all_texts[idx]
                    doc_hash = hashlib.md5(text.encode()).hexdigest()
                    rrf_score = bm25_weight / (rrf_k + rank + 1)
                    doc_scores[doc_hash] = doc_scores.get(doc_hash, 0) + rrf_score
                    doc_texts[doc_hash] = text

                # Sort by fused score
                sorted_hashes = sorted(
                    doc_scores.keys(),
                    key=lambda h: doc_scores[h],
                    reverse=True
                )

                # Get top candidates for reranking
                rerank_candidates = [
                    doc_texts[h] for h in sorted_hashes[:num_candidates]
                ]

                # Step 4: Cross-encoder reranking
                logger.info(f"Reranking {len(rerank_candidates)} candidates...")
                reranked = await asyncio.to_thread(
                    self._rerank, query, rerank_candidates, k
                )

                final_chunks = [r["text"] for r in reranked]
                avg_rerank_score = (
                    sum(r["score"] for r in reranked) / len(reranked)
                    if reranked else 0.0
                )

                # Determine confidence from reranker scores
                if avg_rerank_score > 5.0:
                    confidence = "high"
                elif avg_rerank_score > 0.0:
                    confidence = "medium"
                else:
                    confidence = "low"

                logger.info(
                    f"✓ Hybrid search: {len(final_chunks)} results, "
                    f"avg_rerank_score={avg_rerank_score:.3f}, confidence={confidence}"
                )

                return {
                    "chunks": final_chunks,
                    "confidence": confidence,
                    "avg_score": avg_rerank_score
                }
            else:
                logger.warning("No vector results found")
                return {"chunks": [], "confidence": "low", "avg_score": 0.0}

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            # Fallback to basic vector search
            logger.info("Falling back to basic vector search...")
            basic_results = await retriever_service.search(query=query, k=k)
            return {
                "chunks": basic_results,
                "confidence": "low",
                "avg_score": 0.0
            }


# Singleton instance
hybrid_retriever_service = HybridRetrieverService()
