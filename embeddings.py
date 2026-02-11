"""
Embeddings Module - Generates dense and sparse embeddings for legal documents
Combines Sentence Transformers (dense) and BM25 (sparse) for hybrid search
"""

import numpy as np
from typing import List, Tuple, Dict
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DenseEmbeddings:
    """
    Generate dense embeddings using Sentence Transformers.
    Better for semantic similarity matching.
    """
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize dense embedding model.
        
        Args:
            model_name (str): HuggingFace model name for Sentence Transformers
        """
        self.model_name = model_name
        
        try:
            logger.info(f"Loading embedding model: {model_name}")
            self.model = SentenceTransformer(model_name)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"Model loaded successfully (dimension: {self.embedding_dim})")
        except Exception as e:
            logger.error(f"Error loading embedding model: {str(e)}")
            raise
    
    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.
        
        Args:
            text (str): Text to embed
            
        Returns:
            np.ndarray: Embedding vector
        """
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            logger.error(f"Error embedding text: {str(e)}")
            return np.zeros(self.embedding_dim)
    
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for multiple texts (batch processing).
        
        Args:
            texts (List[str]): List of texts to embed
            batch_size (int): Batch size for processing
            
        Returns:
            np.ndarray: 2D array of embeddings (n_texts x embedding_dim)
        """
        try:
            logger.info(f"Generating embeddings for {len(texts)} texts")
            embeddings = self.model.encode(texts, batch_size=batch_size, convert_to_numpy=True)
            logger.info(f"Successfully generated embeddings (shape: {embeddings.shape})")
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            return np.zeros((len(texts), self.embedding_dim))
    
    def similarity_search(self, query_embedding: np.ndarray, 
                         document_embeddings: np.ndarray, 
                         top_k: int = 5) -> List[Tuple[int, float]]:
        """
        Find most similar documents using cosine similarity.
        
        Args:
            query_embedding (np.ndarray): Query embedding vector
            document_embeddings (np.ndarray): 2D array of document embeddings
            top_k (int): Number of top results to return
            
        Returns:
            List[Tuple[int, float]]: List of (document_index, similarity_score)
        """
        # Calculate cosine similarity
        similarities = np.dot(document_embeddings, query_embedding) / (
            np.linalg.norm(document_embeddings, axis=1) * np.linalg.norm(query_embedding) + 1e-8
        )
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = [(idx, similarities[idx]) for idx in top_indices]
        
        return results


class SparseEmbeddings:
    """
    Generate sparse embeddings using BM25 algorithm.
    Better for keyword matching and exact term matches.
    """
    
    def __init__(self):
        """Initialize sparse embedding (BM25)"""
        self.bm25_model = None
        self.documents = []
        self.tokenized_docs = []
        logger.info("Sparse embedding (BM25) initialized")
    
    def fit(self, documents: List[str]):
        """
        Fit BM25 model on documents.
        
        Args:
            documents (List[str]): List of documents to index
        """
        try:
            self.documents = documents
            # Tokenize documents (simple whitespace tokenization)
            self.tokenized_docs = [doc.lower().split() for doc in documents]
            self.bm25_model = BM25Okapi(self.tokenized_docs)
            logger.info(f"BM25 model fitted on {len(documents)} documents")
        except Exception as e:
            logger.error(f"Error fitting BM25 model: {str(e)}")
    
    def similarity_search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """
        Find most similar documents using BM25.
        
        Args:
            query (str): Query text
            top_k (int): Number of top results to return
            
        Returns:
            List[Tuple[int, float]]: List of (document_index, BM25_score)
        """
        if self.bm25_model is None:
            logger.error("BM25 model not fitted. Call fit() first.")
            return []
        
        try:
            # Tokenize query
            query_tokens = query.lower().split()
            
            # Get BM25 scores
            scores = self.bm25_model.get_scores(query_tokens)
            
            # Get top-k indices
            top_indices = np.argsort(scores)[::-1][:top_k]
            results = [(idx, scores[idx]) for idx in top_indices if scores[idx] > 0]
            
            return results
        except Exception as e:
            logger.error(f"Error in BM25 search: {str(e)}")
            return []


class HybridEmbeddings:
    """
    Combines dense (Sentence Transformers) and sparse (BM25) embeddings.
    Provides better retrieval by leveraging both semantic and keyword matching.
    """
    
    def __init__(self, dense_weight: float = 0.7, sparse_weight: float = 0.3):
        """
        Initialize hybrid embedding system.
        
        Args:
            dense_weight (float): Weight for dense embeddings (0-1)
            sparse_weight (float): Weight for sparse embeddings (0-1)
        """
        self.dense = DenseEmbeddings()
        self.sparse = SparseEmbeddings()
        
        # Normalize weights
        total = dense_weight + sparse_weight
        self.dense_weight = dense_weight / total
        self.sparse_weight = sparse_weight / total
        
        self.documents = []
        self.dense_embeddings = None
        
        logger.info(f"Hybrid embedding initialized (dense: {self.dense_weight:.2f}, sparse: {self.sparse_weight:.2f})")
    
    def fit(self, documents: List[str]):
        """
        Index documents with both dense and sparse embeddings.
        
        Args:
            documents (List[str]): List of documents to index
        """
        self.documents = documents
        
        logger.info(f"Indexing {len(documents)} documents...")
        
        # Generate dense embeddings
        self.dense_embeddings = self.dense.embed_texts(documents)
        
        # Fit sparse embeddings (BM25)
        self.sparse.fit(documents)
        
        logger.info("Hybrid indexing complete")
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Hybrid search combining dense and sparse results.
        
        Args:
            query (str): Query text
            top_k (int): Number of top results to return
            
        Returns:
            List[Dict]: List of results with document index, score, and content
        """
        if not self.documents or self.dense_embeddings is None:
            logger.error("No documents indexed. Call fit() first.")
            return []
        
        try:
            # Dense search
            query_embedding = self.dense.embed_text(query)
            dense_results = self.dense.similarity_search(query_embedding, self.dense_embeddings, top_k=top_k)
            
            # Sparse search
            sparse_results = self.sparse.similarity_search(query, top_k=top_k)
            
            # Combine results
            combined_scores = {}
            
            for idx, score in dense_results:
                combined_scores[idx] = combined_scores.get(idx, 0) + (self.dense_weight * score)
            
            for idx, score in sparse_results:
                # Normalize BM25 scores to 0-1 range
                normalized_score = min(score / 50, 1.0)
                combined_scores[idx] = combined_scores.get(idx, 0) + (self.sparse_weight * normalized_score)
            
            # Sort by combined score
            sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
            
            # Format results
            final_results = [
                {
                    "index": idx,
                    "score": float(score),
                    "content": self.documents[idx],
                    "content_preview": self.documents[idx][:100] + "..."
                }
                for idx, score in sorted_results
            ]
            
            logger.info(f"Hybrid search returned {len(final_results)} results for query")
            return final_results
        
        except Exception as e:
            logger.error(f"Error in hybrid search: {str(e)}")
            return []


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    # Sample legal documents
    sample_docs = [
        "Right to education is a fundamental right of every citizen.",
        "The Indian Constitution protects freedom of speech and expression.",
        "Contract law governs agreements between two or more parties.",
        "Criminal law deals with offenses against the state or society.",
        "Property rights protect ownership and transfer of assets."
    ]
    
    print("Testing Hybrid Embeddings")
    print("="*60)
    
    # Initialize and fit hybrid embeddings
    hybrid = HybridEmbeddings(dense_weight=0.7, sparse_weight=0.3)
    hybrid.fit(sample_docs)
    
    # Test search
    query = "What are fundamental rights in constitution?"
    results = hybrid.search(query, top_k=3)
    
    print(f"\nQuery: {query}\n")
    print("Top Results:")
    for i, result in enumerate(results, 1):
        print(f"\n[Result {i}] Score: {result['score']:.3f}")
        print(f"Content: {result['content']}")
