"""
Vector Store Module - Integrates with Pinecone for vector database
Stores and retrieves embeddings of legal documents
"""

from typing import List, Dict, Optional
import logging
import json
from datetime import datetime

try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    Pinecone = None
    ServerlessSpec = None
    logging.warning("Pinecone not installed. Install with: pip install pinecone-client")

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PineconeVectorStore:
    """
    Vector database integration using Pinecone.
    Stores legal document embeddings for fast retrieval.
    """
    
    def __init__(self, api_key: Optional[str] = None, environment: Optional[str] = None):
        """
        Initialize Pinecone vector store.
        
        Args:
            api_key (str): Pinecone API key (defaults to config)
            environment (str): Pinecone environment (defaults to config)
        """
        self.api_key = api_key or config.PINECONE_API_KEY
        self.environment = environment or getattr(config, "PINECONE_ENV", None)
        self.index_name = config.PINECONE_INDEX_NAME
        self.embedding_dim = config.EMBEDDING_DIMENSION
        
        self.pc = None
        self.index = None
        self.document_store = {}  # Local cache of documents
        
        if Pinecone is None:
            logger.error("Pinecone not installed. Cannot initialize vector store.")
            raise ImportError("Pinecone client not available")
        
        self._initialize_pinecone()
    
    def _initialize_pinecone(self):
        """Initialize Pinecone connection and index"""
        try:
            logger.info("Initializing Pinecone connection...")
            
            # Initialize Pinecone client
            self.pc = Pinecone(api_key=self.api_key)
            
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            
            if self.index_name not in [idx.name for idx in existing_indexes]:
                logger.info(f"Creating new index: {self.index_name}")
                
                # Create index
                self.pc.create_index(
                    name=self.index_name,
                    dimension=self.embedding_dim,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1")
                )
                logger.info(f"Index '{self.index_name}' created successfully")
            else:
                logger.info(f"Index '{self.index_name}' already exists")
            
            # Get index reference
            self.index = self.pc.Index(self.index_name)
            logger.info("Pinecone vector store initialized")
        
        except Exception as e:
            logger.error(f"Error initializing Pinecone: {str(e)}")
            raise
    
    def upsert_embeddings(self, embeddings: List[tuple], namespace: str = "default") -> Dict:
        """
        Upload embeddings to Pinecone.
        
        Args:
            embeddings (List[tuple]): List of (id, vector, metadata) tuples
            namespace (str): Namespace for organizing vectors
            
        Returns:
            Dict: Upsert result
        """
        try:
            if not embeddings:
                logger.warning("No embeddings to upsert")
                return {"status": "empty", "count": 0}
            
            # Prepare data in Pinecone format
            vectors_to_upsert = [
                (str(item[0]), item[1].tolist(), item[2]) 
                for item in embeddings
            ]
            
            logger.info(f"Upserting {len(vectors_to_upsert)} embeddings to Pinecone...")
            
            # Upsert in batches
            batch_size = 100
            total_upserted = 0
            
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                self.index.upsert(vectors=batch, namespace=namespace)
                total_upserted += len(batch)
                logger.info(f"Upserted {total_upserted}/{len(vectors_to_upsert)} embeddings")
            
            logger.info(f"Successfully upserted {total_upserted} embeddings")
            return {"status": "success", "count": total_upserted}
        
        except Exception as e:
            logger.error(f"Error upserting embeddings: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def store_document(self, doc_id: str, content: str, metadata: Optional[Dict] = None):
        """
        Store document text for retrieval after vector search.
        
        Args:
            doc_id (str): Unique document identifier
            content (str): Document text content
            metadata (Dict): Additional metadata
        """
        self.document_store[doc_id] = {
            "content": content,
            "metadata": metadata or {},
            "stored_at": datetime.now().isoformat()
        }
        logger.info(f"Document stored: {doc_id}")
    
    def retrieve_embeddings(self, query_vector: List[float], top_k: int = 5, 
                          namespace: str = "default") -> List[Dict]:
        """
        Query Pinecone for similar embeddings.
        
        Args:
            query_vector (List[float]): Query embedding vector
            top_k (int): Number of results to return
            namespace (str): Namespace to search in
            
        Returns:
            List[Dict]: Retrieved documents with scores
        """
        try:
            logger.info(f"Querying Pinecone for top-{top_k} similar embeddings...")
            
            results = self.index.query(
                vector=query_vector,
                top_k=top_k,
                namespace=namespace,
                include_metadata=True
            )
            
            # Format results
            retrieved = []
            for match in results.get("matches", []):
                doc_id = match["id"]
                score = match["score"]
                metadata = match.get("metadata", {})
                
                # Get full document if available (fallback to metadata)
                doc_content = self.document_store.get(doc_id, {}).get("content", "")
                if not doc_content:
                    doc_content = metadata.get("content", "")
                
                retrieved.append({
                    "doc_id": doc_id,
                    "score": score,
                    "metadata": metadata,
                    "content": doc_content
                })
            
            logger.info(f"Retrieved {len(retrieved)} results from Pinecone")
            return retrieved
        
        except Exception as e:
            logger.error(f"Error retrieving embeddings: {str(e)}")
            return []
    
    def delete_index(self, confirm: bool = False) -> Dict:
        """
        Delete the entire index (for cleanup).
        
        Args:
            confirm (bool): Require explicit confirmation
            
        Returns:
            Dict: Deletion result
        """
        if not confirm:
            logger.warning("Index deletion not confirmed. Set confirm=True")
            return {"status": "cancelled"}
        
        try:
            logger.warning(f"Deleting index: {self.index_name}")
            self.pc.delete_index(self.index_name)
            self.index = None
            logger.info("Index deleted successfully")
            return {"status": "deleted"}
        except Exception as e:
            logger.error(f"Error deleting index: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def get_index_stats(self) -> Dict:
        """
        Get statistics about the current index.
        
        Returns:
            Dict: Index statistics
        """
        try:
            stats = self.index.describe_index_stats()
            return {
                "index_name": self.index_name,
                "total_vectors": stats.get("total_vector_count", 0),
                "namespaces": stats.get("namespaces", {}),
                "dimension": self.embedding_dim
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {str(e)}")
            return {}


class LocalVectorStore:
    """
    Fallback local vector store (for development/testing without Pinecone).
    Uses in-memory storage with numpy for similarity search.
    """
    
    def __init__(self):
        """Initialize local vector store"""
        self.vectors = {}
        self.documents = {}
        self.vector_index = None
        logger.info("Local vector store initialized")
    
    def store_embedding(self, doc_id: str, vector: List[float], 
                       content: str, metadata: Optional[Dict] = None):
        """Store embedding locally"""
        self.vectors[doc_id] = vector
        self.documents[doc_id] = {
            "content": content,
            "metadata": metadata or {},
            "stored_at": datetime.now().isoformat()
        }
        logger.info(f"Embedding stored locally: {doc_id}")
    
    def retrieve_similar(self, query_vector: List[float], top_k: int = 5) -> List[Dict]:
        """Retrieve similar embeddings using cosine similarity"""
        import numpy as np
        
        if not self.vectors:
            logger.warning("No vectors stored")
            return []
        
        # Calculate similarity scores
        scores = {}
        query_array = np.array(query_vector)
        query_norm = np.linalg.norm(query_array)
        
        for doc_id, vector in self.vectors.items():
            vector_array = np.array(vector)
            similarity = np.dot(query_array, vector_array) / (
                query_norm * np.linalg.norm(vector_array) + 1e-8
            )
            scores[doc_id] = similarity
        
        # Get top-k results
        top_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        results = [
            {
                "doc_id": doc_id,
                "score": float(score),
                "content": self.documents[doc_id]["content"],
                "metadata": self.documents[doc_id]["metadata"]
            }
            for doc_id, score in top_docs
        ]
        
        return results


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    logger.info("Vector Store module ready for use")
