"""
Configuration module for Legal Aid Chatbot
Handles environment variables and application-level settings securely
# -*- coding: utf-8 -*-
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
# Allow override via .env so the app can target the actual index name.
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "kyl")
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

# ==================== METRICS CONFIGURATION ====================
# Deterministic proxy metrics only (no LLM judge).

# ==================== LEGAL DISCLAIMER ====================
LEGAL_DISCLAIMER = "This chatbot provides general legal information only and does not constitute legal advice."
LEGAL_DISCLAIMER_TA = "இந்த அரட்டையாளர் பொதுவான சட்டத் தகவலை மட்டுமே வழங்குகிறது; இது சட்ட ஆலோசனை அல்ல."

# ==================== LAW-ONLY QUESTION FILTER ====================
REJECTION_MESSAGE = "I am designed to provide legal information only. Please ask questions related to law or legal awareness."
REJECTION_MESSAGE_TA = "நான் சட்டத் தகவலை மட்டுமே வழங்குகிறேன். சட்டம் அல்லது சட்ட விழிப்புணர்வுடன் தொடர்புடைய கேள்விகளை கேளுங்கள்."

NO_CONTEXT_MESSAGE = "The retrieved legal context is insufficient to answer this question. Please upload a relevant legal PDF to expand the knowledge base."
UPLOAD_REQUEST_MESSAGE = ("The retrieved legal context is insufficient to answer this question. Please upload a relevant legal PDF to expand the knowledge base.")
UPLOAD_REQUEST_MESSAGE_TA = ("இந்த கேள்விக்கான தொடர்புடைய சட்டத் தகவல் கிடைக்கவில்லை. தயவுசெய்து தொடர்புடைய சட்ட PDF ஐ பதிவேற்றவும்.")

# ==================== LANGUAGE FALLBACK ====================
TA_LANGUAGE_FALLBACK_MESSAGE = ("தேவையான பதிலை முழுமையாக தமிழில் வழங்க இயலவில்லை. தயவுசெய்து தொடர்புடைய சட்ட PDF ஐ பதிவேற்றவும்.")

# ==================== LOGGING ====================
LOG_LEVEL = "INFO"

