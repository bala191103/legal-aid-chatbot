"""
Main Streamlit Application - Legal Aid Chatbot UI
Integrates all modules for complete RAG-based legal assistance
# -*- coding: utf-8 -*-
"""

import streamlit as st
import logging
import re
from typing import Optional
import os
import hashlib
from pathlib import Path
import pandas as pd
import altair as alt
import base64
import numpy as np
from sentence_transformers import SentenceTransformer
import threading
import time

# Import all modules
from law_filter import is_legal_query
from pdf_processor import PDFProcessor, BatchPDFProcessor
from chunker import TextChunker, clean_chunk, validate_chunks
from retriever import LegalDocumentRetriever
from llm_handler import GroqLLMHandler, ResponseValidator
from language_utils import detect_language, translate_response
import config

# ==================== LOGGING SETUP ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="Know Your Law",
    page_icon="K",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM STYLING ====================
st.markdown("""
<style>
    .header {
        text-align: center;
        color: #1f4788;
        font-size: 2.5em;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .subtitle {
        text-align: center;
        color: #555;
        font-size: 1.1em;
        margin-bottom: 30px;
    }
    .info-box {
        background-color: #e8f4f8;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #1f4788;
        margin-bottom: 20px;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #ff9800;
        margin-bottom: 20px;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #dc3545;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==================== INITIALIZE SESSION STATE ====================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "retriever" not in st.session_state:
    st.session_state.retriever = None

if "llm_handler" not in st.session_state:
    st.session_state.llm_handler = None

if "documents_indexed" not in st.session_state:
    st.session_state.documents_indexed = False
if "indexed_file_hashes" not in st.session_state:
    st.session_state.indexed_file_hashes = set()
if "show_pdf_uploader" not in st.session_state:
    st.session_state.show_pdf_uploader = False
if "last_fast_metrics" not in st.session_state:
    st.session_state.last_fast_metrics = None
if "last_contexts" not in st.session_state:
    st.session_state.last_contexts = []
if "last_retrieval_scores" not in st.session_state:
    st.session_state.last_retrieval_scores = []
if "last_language" not in st.session_state:
    st.session_state.last_language = "en"


def enforce_language_response(text: str, detected_language: str) -> str:
    """
    Enforce strict language output.
    - English queries: return as-is.
    - Tamil queries: ensure output is Tamil-only (no Latin letters).
    """
    if detected_language != "ta":
        if re.search(r"[\u0B80-\u0BFF]", text):
            cleaned = re.sub(r"[\u0B80-\u0BFF]+", "", text)
            return " ".join(cleaned.split())
        return text
    if re.search(r"[A-Za-z]", text):
        translated = translate_response(text, "ta", st.session_state.llm_handler)
        if re.search(r"[A-Za-z]", translated):
            return config.TA_LANGUAGE_FALLBACK_MESSAGE
        return translated
    return text


@st.cache_resource
def get_embedding_model() -> SentenceTransformer:
    """
    Cache the sentence-transformer model for fast, deterministic metrics.
    """
    return SentenceTransformer(config.EMBEDDING_MODEL)


def _cosine_sim(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    denom = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b)) + 1e-8
    return float(np.dot(vec_a, vec_b) / denom)


def _normalize_cosine(score: float) -> float:
    # Map cosine similarity [-1, 1] to [0, 1]
    return max(0.0, min(1.0, (score + 1.0) / 2.0))




# ==================== SIDEBAR CONFIGURATION ====================
def setup_sidebar():
    """Configure sidebar for admin functions and settings"""
    st.sidebar.markdown("### Configuration")
    
    if st.session_state.get("show_pdf_uploader"):
        with st.sidebar.expander("Document Management", expanded=True):
            st.write("**Upload Legal Documents**")
            
            uploaded_files = st.file_uploader(
                "Upload PDF documents",
                type=["pdf"],
                accept_multiple_files=True,
                help="Upload legal documents (PDFs only)"
            )
            
            if uploaded_files:
                if st.button("Process & Index Documents"):
                    process_documents(uploaded_files)
    
    with st.sidebar.expander("Information", expanded=True):
        st.write("""
        **How to use:**
        1. Ask law-related questions
        2. Get simplified legal information
        3. Upload a legal PDF only if requested

        **Important:**
        - Only law-related questions are answered
        - Responses are for awareness only
        - Consult qualified lawyers for specific cases
        """)

    with st.sidebar.expander("Debug", expanded=False):
        st.checkbox("Show retrieved context", key="show_retrieval_context")
        st.checkbox("Show retrieval scores", key="show_retrieval_scores")
        st.caption(f"Upload enabled: {st.session_state.get('show_pdf_uploader')}")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Statistics")
    if st.session_state.documents_indexed:
        st.sidebar.success("Documents Indexed")
    else:
        st.sidebar.warning("No documents indexed yet")
    if st.session_state.retriever is not None:
        store_label = 'Local' if st.session_state.retriever.use_local else 'Pinecone'
        st.sidebar.write(f"Vector store: **{store_label}**")
        if st.session_state.retriever.use_local and st.session_state.retriever.pinecone_error:
            st.sidebar.error(f"Pinecone error: {st.session_state.retriever.pinecone_error}")



# ==================== DOCUMENT PROCESSING FUNCTION ====================
def process_documents(uploaded_files):
    """Process and index uploaded PDF documents"""
    with st.spinner("Processing documents..."):
        try:
            processor = PDFProcessor()
            chunker = TextChunker(
                chunk_size=config.CHUNK_SIZE,
                chunk_overlap=config.CHUNK_OVERLAP
            )
            
            all_chunks = []
            chunk_ids = []
            chunk_metadata = []
            chunk_id_counter = 0
            
            for uploaded_file in uploaded_files:
                # Save uploaded file temporarily
                temp_file_path = f"temp_{uploaded_file.name}"
                file_bytes = uploaded_file.getbuffer()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                if file_hash in st.session_state.indexed_file_hashes:
                    st.info(f"Info: {uploaded_file.name} already indexed. Skipping.")
                    continue
                with open(temp_file_path, "wb") as f:
                    f.write(file_bytes)
                
                try:
                    # Extract text
                    st.write(f"Processing: {uploaded_file.name}")
                    extracted_text = processor.extract_text(temp_file_path)
                    
                    # Chunk text
                    chunks = chunker.chunk_text(extracted_text)
                    chunks = [clean_chunk(chunk) for chunk in chunks]
                    chunks = validate_chunks(chunks, min_length=50)
                    
                    for chunk in chunks:
                        all_chunks.append(chunk)
                        chunk_ids.append(f"chunk_{chunk_id_counter}")
                        chunk_metadata.append({
                            "source": uploaded_file.name,
                            "type": "legal_document",
                            "file_hash": file_hash
                        })
                        chunk_id_counter += 1
                    
                    st.success(f"{uploaded_file.name}: {len(chunks)} chunks created")
                
                except Exception as e:
                    st.error(f"Error processing {uploaded_file.name}: {str(e)}")
                
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
            
            # Index documents
            if all_chunks:
                st.write(f"\nIndexing {len(all_chunks)} chunks...")
                result = st.session_state.retriever.index_documents(
                    all_chunks, chunk_ids, chunk_metadata
                )
                
                if result.get("status") == "success":
                    st.session_state.documents_indexed = True
                    indexed_count = result.get("indexed", result.get("count", 0))
                    st.success(f"Successfully indexed {indexed_count} chunks!")
                    stats = st.session_state.retriever.get_retrieval_stats()
                    record_count = (
                        stats.get("total_embeddings")
                        or stats.get("total_vector_count")
                        or stats.get("vector_count")
                        or stats.get("total_records")
                    )
                    if record_count == 0:
                        st.warning("Pinecone index shows 0 records after indexing. Please verify credentials/index name.")
                    elif record_count is not None:
                        st.info(f"Vector store record count: {record_count}")
                else:
                    st.error(f"Indexing failed: {result.get('error', 'Unknown error')}")
        
        except Exception as e:
            st.error(f"Error processing documents: {str(e)}")
            logger.error(f"Document processing error: {str(e)}")


# ==================== CHAT INTERFACE ====================
def render_chat_history():
    """Render chat history only (no input)"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def handle_user_input(user_input: str):
    """Handle a new user message and append response to history"""
    # Add user message to history
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    # Process query
    with st.spinner("Processing your question..."):
        response = process_query(user_input)

    # Add assistant response to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": response
    })


def process_query(query: str) -> str:
    """
    Process user query through the complete RAG pipeline
    
    Args:
        query (str): User's question
        
    Returns:
        str: Response from the chatbot
    """
    
    # ==================== STEP 0: LANGUAGE DETECTION ====================
    detected_language = detect_language(query)
    st.session_state.last_language = detected_language

    # ==================== STEP 1: LAW FILTER ====================
    is_legal, reason = is_legal_query(query)
    logger.info(f"Law filter result: {is_legal} ({reason})")
    
    if not is_legal:
        rejection = config.REJECTION_MESSAGE_TA if detected_language == "ta" else config.REJECTION_MESSAGE
        base_response = ResponseValidator.ensure_disclaimer(rejection, language=detected_language)
        st.session_state.show_pdf_uploader = False
        st.session_state.last_fast_metrics = {
            "status": "skipped",
            "reason": "Not applicable – non-legal query",
            "context_precision": 0.0,
            "context_recall": 0.0,
            "answer_relevance": 0.0,
            "faithfulness": 0.0,
            "hallucination_risk": 1.0,
            "overall_confidence": 0.0,
        }
        return enforce_language_response(base_response, detected_language)

    # ==================== STEP 2: RETRIEVE CONTEXT ====================
    try:
        retrieval_query = expand_query_for_retrieval(query)
        results = st.session_state.retriever.retrieve(retrieval_query)
    except Exception as e:
        logger.error(f"Retrieval error: {str(e)}")
        results = []

    st.session_state.last_contexts = [r.get("content", "") for r in results]
    st.session_state.last_retrieval_scores = [r.get("score", 0.0) for r in results]

    max_score = max(st.session_state.last_retrieval_scores, default=0.0)
    has_relevant_context = bool(results) and max_score >= config.RETRIEVAL_SCORE_THRESHOLD
    if not has_relevant_context:
        st.session_state.show_pdf_uploader = True
        base_response = config.NO_CONTEXT_MESSAGE
        st.session_state.last_fast_metrics = compute_fast_metrics(
            query,
            base_response,
            [],
            [],
        )
        return base_response
    
    context = build_context_from_results(results)
    if st.session_state.get("show_retrieval_scores"):
        with st.expander("Retrieval Scores", expanded=False):
            score_rows = []
            for idx, r in enumerate(results, 1):
                score_rows.append({
                    "Rank": idx,
                    "Score": r.get("score", 0),
                    "Source": r.get("metadata", {}).get("source", "unknown")
                })
            st.table(pd.DataFrame(score_rows))

    if st.session_state.get("show_retrieval_context"):
        with st.expander("Retrieved Context", expanded=False):
            st.text(context)
    
    # ==================== STEP 3: STRICT RESPONSE (CONTEXT-ONLY) ====================
    response = None
    if st.session_state.llm_handler is not None:
        response = st.session_state.llm_handler.generate_rag_response(
            query, context, language=detected_language
        )
    if response is None:
        response = build_strict_response(query, context, language=detected_language)

    if response is not None and not is_structured_response(response, detected_language):
        response = build_strict_response(query, context, language=detected_language)

    if response is not None and not is_grounded_response(response, context):
        response = None

    if response is None:
        st.session_state.show_pdf_uploader = True
        base_response = config.NO_CONTEXT_MESSAGE
        st.session_state.last_fast_metrics = compute_fast_metrics(
            query,
            base_response,
            [],
            [],
        )
        return base_response
    
    # ==================== STEP 4: VALIDATE RESPONSE ====================
    response = ResponseValidator.ensure_disclaimer(response, language=detected_language)
    st.session_state.show_pdf_uploader = False

    # ==================== STEP 5: FAST METRICS (INSTANT) ====================
    st.session_state.last_fast_metrics = compute_fast_metrics(
        query,
        response,
        st.session_state.last_contexts,
        st.session_state.last_retrieval_scores,
    )
    
    return enforce_language_response(response, detected_language)


def build_context_from_results(results: list, max_tokens: int = 2000) -> str:
    """
    Build a combined context string from retriever results (same formatting as retriever).
    """
    if not results:
        return "No relevant legal documents found in knowledge base."

    context_parts = []
    total_chars = 0
    max_chars = max_tokens * 4  # Rough estimate: 1 token ≈ 4 characters

    for i, result in enumerate(results, 1):
        content = result.get("content", "")
        score = result.get("score", 0)
        source = result.get("metadata", {}).get("source", "unknown")
        part = f"[Source {i}: {source} (Relevance: {score:.2%})]\n{content}\n"

        if total_chars + len(part) > max_chars:
            context_parts.append("... [truncated - context limit reached]")
            break

        context_parts.append(part)
        total_chars += len(part)

    context = "\n".join(context_parts)
    logger.info(f"Generated context from {len(results)} documents ({len(context)} chars)")
    return context


def expand_query_for_retrieval(query: str) -> str:
    """
    Pass-through retrieval query (no hardcoded IPC overrides).
    """
    return query.strip()


def _tokenize_text(text: str) -> set[str]:
    english = re.findall(r"[a-zA-Z]{3,}", text.lower())
    tamil = re.findall(r"[\u0B80-\u0BFF]{2,}", text)
    return set(english + tamil)


def compute_fast_metrics(question: str, answer: str, contexts: list[str], scores: list[float]) -> dict:
    """
    Compute fast, deterministic proxy metrics without any LLMs.
    Deterministic proxy metrics provide fast, explainable evaluation of RAG systems
    and are suitable for real-time dashboards, while avoiding latency and instability
    of LLM-based judges.
    """
    if not contexts:
        return {
            "status": "no_context",
            "reason": "Not applicable – no retrieved context",
            "context_precision": 0.0,
            "context_recall": 0.0,
            "answer_relevance": 0.0,
            "faithfulness": 0.0,
            "hallucination_risk": 1.0,
            "overall_confidence": 0.0,
        }

    model = get_embedding_model()
    try:
        answer_text = answer or ""
        question_text = question or ""
        context_texts = contexts

        answer_emb = model.encode(answer_text, convert_to_numpy=True)
        question_emb = model.encode(question_text, convert_to_numpy=True)
        context_embs = model.encode(context_texts, convert_to_numpy=True)

        # Faithfulness: avg cosine similarity between answer and each context chunk
        faith_scores = [
            _normalize_cosine(_cosine_sim(answer_emb, ctx_emb))
            for ctx_emb in context_embs
        ]
        faithfulness = float(np.mean(faith_scores)) if faith_scores else 0.0

        # Answer Relevance: cosine similarity between question and answer
        answer_relevance = _normalize_cosine(_cosine_sim(question_emb, answer_emb))
    except Exception:
        faithfulness = 0.0
        answer_relevance = 0.0

    # Context Precision: % of retrieved chunks above threshold
    threshold = config.RETRIEVAL_SCORE_THRESHOLD
    context_precision = (
        sum(1 for s in scores if s >= threshold) / max(len(scores), 1)
        if scores
        else 0.0
    )

    # Context Recall: average similarity of top-K retrieved chunks
    context_recall = sum(scores) / max(len(scores), 1) if scores else 0.0

    # Hallucination Risk: 1 - faithfulness
    hallucination_risk = 1.0 - faithfulness

    # Overall Confidence: 0.4*Faithfulness + 0.4*Answer Relevance + 0.2*Context Precision
    overall_confidence = (
        0.4 * faithfulness + 0.4 * answer_relevance + 0.2 * context_precision
    )

    return {
        "status": "computed",
        "reason": "",
        "context_precision": round(max(0.0, min(1.0, context_precision)), 4),
        "context_recall": round(max(0.0, min(1.0, context_recall)), 4),
        "answer_relevance": round(max(0.0, min(1.0, answer_relevance)), 4),
        "faithfulness": round(max(0.0, min(1.0, faithfulness)), 4),
        "hallucination_risk": round(max(0.0, min(1.0, hallucination_risk)), 4),
        "overall_confidence": round(max(0.0, min(1.0, overall_confidence)), 4),
    }


def is_grounded_response(response: str, context: str) -> bool:
    """
    Simple grounding check: ensure sufficient keyword overlap with context.
    """
    response_words = _tokenize_text(response)
    context_words = _tokenize_text(context)
    if not response_words or not context_words:
        return False

    # Section number match is a strong grounding signal
    response_sections = set(re.findall(r"\b(\d{1,4}[A-Za-z]?)\b", response))
    if response_sections:
        for sec in response_sections:
            if re.search(rf"\b{re.escape(sec)}\b", context, re.IGNORECASE):
                return True
    overlap = response_words.intersection(context_words)
    return len(overlap) >= 2


def is_structured_response(response: str, language: str) -> bool:
    """
    Check whether the response follows the required structured format.
    """
    if language == "ta":
        required = [
            "பிரிவு மற்றும் தலைப்பு",
            "சட்ட வரையறை",
            "எளிய விளக்கம்",
            "தண்டனை",
            "உதாரணம்",
        ]
    else:
        required = [
            "Section",
            "Legal Definition",
            "Simple Explanation",
            "Punishment",
            "Example",
        ]
    return all(term in response for term in required)


def render_metrics_dashboard():
    """Render a performance metrics dashboard for the latest response."""
    st.markdown("### \U0001F4CA RAG Metrics Dashboard")
    st.subheader("Deterministic Proxy Metrics (Real-Time)")
    fast = st.session_state.get("last_fast_metrics")
    if not fast:
        st.info("No metrics available yet. Ask a legal question to generate metrics.")
        return

    # Deterministic proxy metrics for real-time evaluation (no LLMs).
    fast_rows = [
        {"Metric": "\U0001F7E2 Faithfulness (Context-Grounded)", "Score": fast.get("faithfulness", 0.0)},
        {"Metric": "\U0001F7E2 Answer Relevance (Retrieval-Based)", "Score": fast.get("answer_relevance", 0.0)},
        {"Metric": "\U0001F7E2 Context Precision (Retrieval Quality)", "Score": fast.get("context_precision", 0.0)},
        {"Metric": "\U0001F7E2 Context Recall", "Score": fast.get("context_recall", 0.0)},
        {"Metric": "\U0001F534 Hallucination Risk (Derived)", "Score": fast.get("hallucination_risk", 1.0)},
        {"Metric": "\U0001F7E2 Overall Response Confidence", "Score": fast.get("overall_confidence", 0.0)},
    ]

    if fast.get("status") == "skipped":
        st.info(f"Status: Skipped — {fast.get('reason', 'Not applicable.')}")
    elif fast.get("status") == "no_context":
        st.warning(f"Status: No Context — {fast.get('reason', 'Not applicable.')}")
    else:
        st.success("Status: Computed")

    def _interpret(score: float) -> str:
        if score >= 0.7:
            return "High"
        if score >= 0.4:
            return "Medium"
        return "Low"

    table_df = pd.DataFrame(fast_rows)
    table_df["Interpretation"] = table_df["Score"].apply(_interpret)
    st.table(table_df)

    def _band(score: float) -> str:
        if score >= 0.7:
            return "High"
        if score >= 0.4:
            return "Medium"
        return "Low"

    bar_metrics = [
        ("\U0001F7E2 Faithfulness (Context-Grounded)", fast.get("faithfulness", 0.0)),
        ("\U0001F7E2 Answer Relevance (Retrieval-Based)", fast.get("answer_relevance", 0.0)),
        ("\U0001F7E2 Context Precision (Retrieval Quality)", fast.get("context_precision", 0.0)),
        ("\U0001F7E2 Context Recall", fast.get("context_recall", 0.0)),
        ("\U0001F534 Hallucination Risk (Derived)", fast.get("hallucination_risk", 1.0)),
        ("\U0001F7E2 Overall Response Confidence", fast.get("overall_confidence", 0.0)),
    ]
    bar_df = pd.DataFrame({"Metric": [m for m, _ in bar_metrics], "Score": [v for _, v in bar_metrics]})
    bar_df["Band"] = bar_df["Score"].apply(_band)
    bar_chart = (
        alt.Chart(bar_df)
        .mark_bar()
        .encode(
            x=alt.X("Metric:N", sort=None),
            y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color(
                "Band:N",
                scale=alt.Scale(
                    domain=["High", "Medium", "Low"],
                    range=["#2ecc71", "#f1c40f", "#e74c3c"],
                ),
                legend=alt.Legend(title="Score Band"),
            ),
            tooltip=["Metric", "Score", "Band"],
        )
    )
    st.altair_chart(bar_chart, use_container_width=True)


def build_strict_response(query: str, context: str, language: str = "en") -> str | None:
    """
    Build a strict, context-only response. Returns None if no relevant section found.
    """
    sections = extract_sections_from_context(context)
    if not sections:
        return None

    query_lower = query.lower()
    section_match = re.search(r"\bsection\s+(\d{1,4}[a-z]?)\b", query_lower)
    number_match = re.search(r"\b(\d{1,4}[a-z]?)\b", query_lower)

    # If user asked for a specific section number, return only if present in context
    if section_match or ("section" in query_lower and number_match):
        target = (section_match.group(1) if section_match else number_match.group(1)).lower()
        for sec in sections:
            if sec["number"].lower() == target:
                return format_section_response(sec, language=language)
        return None

    # Otherwise, try keyword matching on section title/body
    keywords = extract_keywords(query_lower)
    best = None
    best_score = 0
    for sec in sections:
        haystack = f"{sec['title']} {sec['body']}".lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > best_score:
            best_score = score
            best = sec

    if best_score == 0 or best is None:
        return None

    return format_section_response(best, language=language)


def extract_sections_from_context(context: str) -> list[dict]:
    """
    Extract sections from retrieved context based on "Section <number>" headings.
    """
    pattern = re.compile(
        r"(?:^|\n)\s*(?:Section|Sec\.?)\s+(\d{1,4}[A-Za-z]?)\s*[:.\-]?\s*(.*)"
        r"|(?:^|\n)\s*(\d{1,4}[A-Za-z]?)\s*[:.\-]\s*(.*)",
        re.IGNORECASE
    )
    matches = list(pattern.finditer(context))
    if not matches:
        return []

    sections = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(context)
        if match.group(1):
            number = match.group(1).strip()
            title = match.group(2).strip() if match.group(2) else ""
        else:
            number = match.group(3).strip()
            title = match.group(4).strip() if match.group(4) else ""
        body = context[start:end].strip()
        sections.append({
            "number": number,
            "title": title,
            "body": body
        })
    return sections


def extract_keywords(text: str) -> list[str]:
    stopwords = {
        "what", "is", "are", "the", "a", "an", "under", "ipc", "section",
        "explain", "define", "meaning", "tell", "me", "about", "of", "for",
        "and", "to", "in", "on", "which", "applies", "apply", "person",
        "someone", "another", "takes", "taking", "money"
    }
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return [w for w in words if w not in stopwords]


def format_section_response(section: dict, language: str = "en") -> str:
    """
    Format a response for a specific IPC section using only its body text.
    """
    language = (language or "en").lower()
    number = section["number"]
    title = section["title"]
    body = section["body"]
    body = re.sub(r"\[Source[^\]]*\]\s*", "", body)
    body = " ".join(body.split())

    sentences = re.split(r"(?<=[.!?])\s+", body)
    sentences = [s.strip() for s in sentences if s.strip()]

    definition = sentences[0] if sentences else body.strip()
    simple_explanation = sentences[1] if len(sentences) > 1 else definition

    punishment_sentences = [
        s for s in sentences
        if re.search(r"\b(punish|punishment|imprisonment|fine|rigorous)\b", s, re.IGNORECASE)
    ]
    punishment = " ".join(punishment_sentences[:1]).strip()

    example_sentences = [
        s for s in sentences
        if re.search(r"\b(example|illustration|for example|e\.g\.)\b", s, re.IGNORECASE)
    ]
    example = " ".join(example_sentences[:1]).strip()

    if language == "ta":
        no_punishment = "இந்த பிரிவுக்கான தண்டனை விவரம் வழங்கப்பட்ட ஆவணத்தில் குறிப்பிடப்படவில்லை."
        header = f"பிரிவு {number}"
        if title:
            header = f"{header}: {title}"
        lines = [
            f"- **பிரிவு மற்றும் தலைப்பு:** {header}",
            f"- **சட்ட வரையறை:** {definition}" if definition else "- **சட்ட வரையறை:** சூழலில் குறிப்பிடப்படவில்லை",
            f"- **எளிய விளக்கம்:** {simple_explanation}" if simple_explanation else "- **எளிய விளக்கம்:** சூழலில் குறிப்பிடப்படவில்லை",
            f"- **தண்டனை / விளைவு:** {punishment}" if punishment else f"- **தண்டனை / விளைவு:** {no_punishment}",
            f"- **உதாரணம்:** {example}" if example else "- **உதாரணம்:** சூழலில் குறிப்பிடப்படவில்லை",
        ]
        return "\n".join(lines)

    no_punishment = "The provided document does not specify punishment for this section."
    header = f"Section {number}"
    if title:
        header = f"{header}: {title}"

    lines = [
        f"- **Section & Title:** {header}",
        f"- **Legal Definition:** {definition}" if definition else "- **Legal Definition:** Not stated in the provided context.",
        f"- **Simple Explanation:** {simple_explanation}" if simple_explanation else "- **Simple Explanation:** Not stated in the provided context.",
        f"- **Punishment / Consequence:** {punishment}" if punishment else f"- **Punishment / Consequence:** {no_punishment}",
        f"- **Example:** {example}" if example else "- **Example:** Not stated in the provided context.",
    ]
    return "\n".join(lines)

# ==================== INITIALIZATION ====================
def initialize_chatbot():
    """Initialize retriever and LLM handler"""
    try:
        # Initialize retriever
        st.session_state.retriever = LegalDocumentRetriever(use_local=False)
        
        # Initialize LLM handler
        try:
            st.session_state.llm_handler = GroqLLMHandler()
        except Exception as e:
            st.error(f"LLM initialization error: {str(e)}")
            st.info("Using local embeddings only. LLM responses will be limited.")
            st.session_state.llm_handler = None
    
    except Exception as e:
        st.error(f"Initialization error: {str(e)}")
        logger.error(f"Initialization failed: {str(e)}")


# ==================== MAIN APP ====================
def main():
    """Main application function"""
    
    # Header
    # Use HTML entity for the emoji to avoid encoding issues.
    st.markdown(
        """
        <div style="text-align:center;margin-top:4px;margin-bottom:6px;">
            <span style="font-size:64px;line-height:1;">&#x2696;&#xFE0F;</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.title("Know Your Law")
    st.markdown('<p class="subtitle">Retrieval-Augmented Generation (RAG) for Legal Awareness</p>', unsafe_allow_html=True)
    
    # Disclaimer box
    st.markdown("""
    <div class="info-box">
    <strong>Welcome to the Legal Aid Chatbot</strong><br>
    This chatbot provides <strong>general legal information</strong> for awareness purposes only. 
    It does not replace professional legal advice. Always consult a qualified lawyer for specific legal matters.
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize if needed
    if st.session_state.retriever is None:
        initialize_chatbot()
    
    # Chat input must be outside tabs
    user_input = st.chat_input(
        placeholder="Ask your legal question... E.g., What are my fundamental rights under Indian Constitution?"
    )
    if user_input:
        handle_user_input(user_input)

    # Setup sidebar (after input handling so dynamic upload flag is applied)
    setup_sidebar()

    tab_chat, tab_metrics = st.tabs(["Legal Chatbot", "RAG Metrics Dashboard"])
    with tab_chat:
        if st.session_state.retriever is not None:
            render_chat_history()
        else:
            st.warning("Please wait for initialization to get started.")
    with tab_metrics:
        render_metrics_dashboard()


if __name__ == "__main__":
    main()

















