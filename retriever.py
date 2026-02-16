"""
Retriever Module - Performs semantic search and retrieves relevant legal documents
Integrates embeddings and vector store for RAG
"""

from typing import List, Dict, Optional
import logging
import numpy as np
import re

from embeddings import HybridEmbeddings
from vector_store import PineconeVectorStore, LocalVectorStore
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LegalDocumentRetriever:
    """
    Retrieves relevant legal documents based on user queries.
    Uses hybrid embeddings and vector store for RAG pipeline.
    """
    
    def __init__(self, use_local: bool = False):
        """
        Initialize retriever with embeddings and vector store.
        
        Args:
            use_local (bool): Use local vector store instead of Pinecone
        """
        self.hybrid_embeddings = HybridEmbeddings(
            dense_weight=config.DENSE_EMBEDDING_WEIGHTS,
            sparse_weight=config.SPARSE_EMBEDDING_WEIGHTS
        )
        
        # Initialize vector store
        self.pinecone_error = None
        if use_local:
            logger.info("Using local vector store for development")
            self.vector_store = LocalVectorStore()
            self.use_local = True
        else:
            try:
                logger.info("Initializing Pinecone vector store")
                self.vector_store = PineconeVectorStore()
                self.use_local = False
            except Exception as e:
                self.pinecone_error = str(e)
                logger.warning(f"Pinecone initialization failed: {str(e)}")
                logger.info("Falling back to local vector store")
                self.vector_store = LocalVectorStore()
                self.use_local = True
        
        self.retrieval_threshold = config.RETRIEVAL_SCORE_THRESHOLD
        self.top_k = config.TOP_K_RESULTS
        
        logger.info("Legal Document Retriever initialized")
    
    def index_documents(self, documents: List[str], document_ids: Optional[List[str]] = None,
                       metadata: Optional[List[Dict]] = None) -> Dict:
        """
        Index legal documents for retrieval.
        
        Args:
            documents (List[str]): List of document texts to index
            document_ids (List[str]): Optional document identifiers
            metadata (List[Dict]): Optional metadata for each document
            
        Returns:
            Dict: Indexing result
        """
        try:
            logger.info(f"Indexing {len(documents)} documents...")
            
            if document_ids is None:
                document_ids = [f"doc_{i}" for i in range(len(documents))]
            
            if metadata is None:
                metadata = [{"source": "unknown"} for _ in documents]
            
            # Generate embeddings
            embeddings = self.hybrid_embeddings.dense.embed_texts(documents)
            
            # Store in vector store
            if self.use_local:
                for doc_id, text, embedding, doc_metadata in zip(
                    document_ids, documents, embeddings, metadata
                ):
                    self.vector_store.store_embedding(
                        doc_id, embedding.tolist(), text, doc_metadata
                    )
                result = {"status": "success", "indexed": len(documents)}
            else:
                # Prepare for Pinecone
                vectors_to_upsert = []
                for i, (doc_id, embedding) in enumerate(zip(document_ids, embeddings)):
                    meta = metadata[i].copy()
                    meta["content"] = documents[i]
                    vectors_to_upsert.append((doc_id, embedding, meta))
                result = self.vector_store.upsert_embeddings(vectors_to_upsert)
                
                # Also store documents locally for retrieval
                for doc_id, text, doc_metadata in zip(document_ids, documents, metadata):
                    self.vector_store.store_document(doc_id, text, doc_metadata)
            
            logger.info(f"Successfully indexed {len(documents)} documents")
            return result
        
        except Exception as e:
            logger.error(f"Error indexing documents: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Dict]:
        """
        Retrieve relevant legal documents for a query.
        
        Args:
            query (str): User query
            top_k (int): Number of results (defaults to config.TOP_K_RESULTS)
            
        Returns:
            List[Dict]: Retrieved documents with scores
        """
        top_k = top_k or self.top_k
        is_section_query = self._is_section_query(query)
        if is_section_query:
            top_k = max(top_k, 10)
        
        try:
            logger.info(f"Retrieving top-{top_k} documents for query: {query[:50]}...")

            direct_matches = self._direct_section_match(query, top_k)
            if direct_matches:
                logger.info(f"Direct section match found: returning {len(direct_matches)} results")
                return direct_matches
            
            # Generate query embedding
            query_embedding = self.hybrid_embeddings.dense.embed_text(query)
            
            # Retrieve from vector store
            if self.use_local:
                results = self.vector_store.retrieve_similar(query_embedding.tolist(), top_k)
            else:
                results = self.vector_store.retrieve_embeddings(query_embedding.tolist(), top_k)
            
            # Filter by threshold (skip for explicit section queries)
            if is_section_query:
                filtered_results = results
            else:
                filtered_results = [r for r in results if r["score"] >= self.retrieval_threshold]
            
            if not filtered_results:
                logger.warning(f"No documents retrieved above threshold ({self.retrieval_threshold})")
            else:
                logger.info(f"Retrieved {len(filtered_results)} documents")
            
            return filtered_results
        
        except Exception as e:
            logger.error(f"Error retrieving documents: {str(e)}")
            return []

    def _direct_section_match(self, query: str, top_k: int) -> List[Dict]:
        """
        If a query includes a numeric section reference, attempt direct text match.
        This helps with shorthand queries like "Section 420".
        """
        match = re.search(r"\b(\d{1,4}[A-Za-z]?)\b", query)
        if not match:
            return []

        section_num = match.group(1)
        pattern = re.compile(
            rf"\b(?:Section|Sec\.?)\s+{re.escape(section_num)}\b|(?:^|\n)\s*{re.escape(section_num)}\s*[:.\-]",
            re.IGNORECASE
        )

        doc_store = None
        if hasattr(self.vector_store, "documents"):
            doc_store = self.vector_store.documents
        elif hasattr(self.vector_store, "document_store"):
            doc_store = self.vector_store.document_store

        if not doc_store:
            return []

        results = []
        for doc_id, doc in doc_store.items():
            content = doc.get("content", "")
            if pattern.search(content):
                results.append({
                    "doc_id": doc_id,
                    "score": 1.0,
                    "content": content,
                    "metadata": doc.get("metadata", {})
                })

        return results[:top_k]

    def _is_section_query(self, query: str) -> bool:
        query_lower = query.lower()
        if "section" in query_lower:
            return True
        return re.search(r"\b\d{1,4}[a-z]?\b", query_lower) is not None
    
    def retrieve_with_context(self, query: str, max_tokens: int = 2000) -> str:
        """
        Retrieve relevant documents and combine into a context string.
        
        Args:
            query (str): User query
            max_tokens (int): Maximum tokens in combined context
            
        Returns:
            str: Combined context from retrieved documents
        """
        results = self.retrieve(query)
        
        if not results:
            return "No relevant legal documents found in knowledge base."
        
        # Combine results with separators
        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4  # Rough estimate: 1 token ≈ 4 characters
        
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            score = result.get("score", 0)
            source = result.get("metadata", {}).get("source", "unknown")
            
            part = f"[Source {i}: {source} (Relevance: {score:.2%})]\n{content}\n"
            
            if total_chars + len(part) > max_chars:
                context_parts.append(f"... [truncated - context limit reached]")
                break
            
            context_parts.append(part)
            total_chars += len(part)
        
        context = "\n".join(context_parts)
        logger.info(f"Generated context from {len(results)} documents ({len(context)} chars)")
        
        return context
    
    def get_retrieval_stats(self) -> Dict:
        """Get statistics about the vector store"""
        try:
            if self.use_local:
                return {
                    "store_type": "local",
                    "total_embeddings": len(self.vector_store.vectors),
                    "total_documents": len(self.vector_store.documents)
                }
            else:
                return self.vector_store.get_index_stats()
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {}


# Backward-compat alias for older import typo
LegalDocumentRetrieve = LegalDocumentRetriever


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    # Sample legal documents
    sample_documents = [
        """
        Article 14: Equality before law. The State shall not deny to any person 
        equality before the law or the equal protection of the laws within the territory of India.
        """,
        """
        Section 2: Definitions. 'Act' means the Indian Penal Code. 
        'Person' includes any company or association or body of individuals.
        """,
        """
        Fundamental Rights: Every citizen has the right to freedom of speech and expression, 
        freedom of assembly, and freedom of petition.
        """,
        """
        Contract Law: A contract is an agreement made between two or more parties 
        with the intention of creating legal obligations.
        """,
        """
        Right to Education: Education is a fundamental right of every child 
        up to the age of 14 years.
        """
    ]
    
    # Initialize retriever
    print("Initializing Legal Document Retriever...")
    retriever = LegalDocumentRetriever(use_local=True)
    
    # Index documents
    print("\nIndexing sample documents...")
    index_result = retriever.index_documents(sample_documents)
    print(f"Indexing result: {index_result}")
    
    # Retrieve documents
    queries = [
        "What is the right to equality?",
        "Tell me about freedom of speech",
        "How are contracts formed?"
    ]
    
    print("\n" + "="*60)
    print("RETRIEVAL TESTS")
    print("="*60)
    
    for query in queries:
        print(f"\nQuery: {query}")
        results = retriever.retrieve(query, top_k=2)
        for i, result in enumerate(results, 1):
            print(f"\n  [Result {i}] Score: {result['score']:.3f}")
            print(f"  Content: {result['content'][:100]}...")
