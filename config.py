"""
Configuration module for Legal Aid Chatbot
Handles environment variables and application-level settings securely
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==================== API KEYS ====================
# Store ONLY secrets in .env
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ==================== PINECONE CONFIGURATION ====================
# Pinecone no longer requires environment/region in latest SDK
PINECONE_INDEX_NAME = "kyl"
EMBEDDING_DIMENSION = 384  # sentence-transformers/all-MiniLM-L6-v2

# ==================== LLM CONFIGURATION ====================
LLM_MODEL = "llama-3.3-70b-versatile"  # Groq supported model
LLM_TEMPERATURE = 0.3  # Low temperature for factual/legal accuracy
LLM_MAX_TOKENS = 512

# ==================== EMBEDDINGS CONFIGURATION ====================
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Hybrid search weights (if sparse + dense is used)
DENSE_EMBEDDING_WEIGHTS = 0.7
SPARSE_EMBEDDING_WEIGHTS = 0.3

# ==================== CHUNKING CONFIGURATION ====================
CHUNK_SIZE = 500       # Characters per chunk
CHUNK_OVERLAP = 100    # Overlap to preserve legal context

# ==================== RETRIEVAL CONFIGURATION ====================
TOP_K_RESULTS = 5
RETRIEVAL_SCORE_THRESHOLD = 0.5

# ==================== LEGAL DISCLAIMER ====================
LEGAL_DISCLAIMER = "⚖️ This information is for general legal awareness only and does not constitute legal advice."

# ==================== LAW-ONLY QUESTION FILTER ====================
REJECTION_MESSAGE = (
    "I am designed to provide legal information only. "
    "Please ask questions related to law."
)

NO_CONTEXT_MESSAGE = "I could not find relevant information in my legal knowledge base for this question."

# ==================== LOGGING ====================
LOG_LEVEL = "INFO"
