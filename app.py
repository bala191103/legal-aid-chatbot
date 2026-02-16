"""
Main Streamlit Application - Legal Aid Chatbot UI
Integrates all modules for complete RAG-based legal assistance
"""

import streamlit as st
import logging
import re
from typing import Optional
import os
import hashlib
from pathlib import Path
import pandas as pd
import threading
import time
import importlib.util
from concurrent.futures import ThreadPoolExecutor, Future

# Import all modules
from law_filter import is_legal_query
from pdf_processor import PDFProcessor, BatchPDFProcessor
from chunker import TextChunker, clean_chunk, validate_chunks
from retriever import LegalDocumentRetriever
from llm_handler import GroqLLMHandler, ResponseValidator
from language_utils import detect_language, translate_response
from rag_evaluation import evaluate_rag_metrics
import config

# ==================== LOGGING SETUP ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== STREAMLIT PAGE CONFIG ====================
st.set_page_config(
    page_title="Legal Aid Chatbot",
    page_icon="⚖️",
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
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = None
if "last_fast_metrics" not in st.session_state:
    st.session_state.last_fast_metrics = None
if "last_contexts" not in st.session_state:
    st.session_state.last_contexts = []
if "last_retrieval_scores" not in st.session_state:
    st.session_state.last_retrieval_scores = []
if "last_language" not in st.session_state:
    st.session_state.last_language = "en"
if "metrics_future" not in st.session_state:
    st.session_state.metrics_future = None
if "metrics_started_at" not in st.session_state:
    st.session_state.metrics_started_at = None
if "last_question" not in st.session_state:
    st.session_state.last_question = None
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None

_metrics_executor = ThreadPoolExecutor(max_workers=1)


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


def get_metrics_blocker() -> Optional[str]:
    """
    Return a user-facing error message if metrics cannot run due to missing deps.
    """
    missing = []
    for module_name in ("ragas", "datasets", "langchain_groq", "langchain_community"):
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    if missing:
        missing_list = ", ".join(missing)
        return f"RAG metrics unavailable. Missing packages: {missing_list}."
    if not config.GROQ_METRICS_API_KEY:
        return "Groq metrics API key missing. Set GROQ_METRICS_API_KEY to compute RAGAS metrics."
    return None


# ==================== SIDEBAR CONFIGURATION ====================
def setup_sidebar():
    """Configure sidebar for admin functions and settings"""
    st.sidebar.markdown("### ⚙️ Configuration")
    
    if st.session_state.get("show_pdf_uploader"):
        with st.sidebar.expander("📚 Document Management", expanded=True):
            st.write("**Upload Legal Documents**")
            
            uploaded_files = st.file_uploader(
                "Upload PDF documents",
                type=["pdf"],
                accept_multiple_files=True,
                help="Upload legal documents (PDFs only)"
            )
            
            if uploaded_files:
                if st.button("📤 Process & Index Documents"):
                    process_documents(uploaded_files)
    
    with st.sidebar.expander("ℹ️ Information", expanded=True):
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
    st.sidebar.markdown("### 📊 Statistics")
    if st.session_state.documents_indexed:
        st.sidebar.success("✓ Documents Indexed")
    else:
        st.sidebar.warning("⚠ No documents indexed yet")
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
                    st.write(f"📄 Processing: {uploaded_file.name}")
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
                    
                    st.success(f"✓ {uploaded_file.name}: {len(chunks)} chunks created")
                
                except Exception as e:
                    st.error(f"✗ Error processing {uploaded_file.name}: {str(e)}")
                
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
                    st.success(f"✅ Successfully indexed {indexed_count} chunks!")
                    stats = st.session_state.retriever.get_retrieval_stats()
                    record_count = (
                        stats.get("total_embeddings")
                        or stats.get("total_vector_count")
                        or stats.get("vector_count")
                        or stats.get("total_records")
                    )
                    if record_count == 0:
                        st.warning("⚠️ Pinecone index shows 0 records after indexing. Please verify credentials/index name.")
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
        st.session_state.last_metrics = {
            "error": "Non-legal query. RAG metrics are not applicable.",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }
        st.session_state.last_fast_metrics = {
            "status": "skipped",
            "reason": "Not applicable – non-legal query",
            "top_k_similarity": 0.0,
            "avg_similarity": 0.0,
            "coverage_ratio": 0.0,
            "hallucination_risk": 1.0,
            "context_utilization": 0.0,
            "confidence": "Low",
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
    st.session_state.last_metrics = None
    st.session_state.metrics_future = None
    st.session_state.metrics_started_at = None
    
    if not results:
        st.session_state.show_pdf_uploader = True
        base_response = (
            "The retrieved legal context is insufficient to answer this question.\n"
            "Please upload a relevant legal PDF to expand the knowledge base."
        )
        st.session_state.last_metrics = {
            "status": "not_applicable",
            "reason": "Not Applicable – No Retrieved Context",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }
        st.session_state.last_fast_metrics = compute_fast_metrics(
            base_response,
            st.session_state.last_contexts,
            st.session_state.last_retrieval_scores,
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

    if response is not None and not is_grounded_response(response, context):
        response = None

    if response is None:
        st.session_state.show_pdf_uploader = True
        base_response = (
            "The retrieved legal context is insufficient to answer this question.\n"
            "Please upload a relevant legal PDF to expand the knowledge base."
        )
        st.session_state.last_metrics = {
            "status": "not_applicable",
            "reason": "Not Applicable – No Retrieved Context",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }
        return base_response
    
    # ==================== STEP 4: VALIDATE RESPONSE ====================
    response = ResponseValidator.ensure_disclaimer(response, language=detected_language)
    st.session_state.show_pdf_uploader = False
    st.session_state.last_question = query
    st.session_state.last_answer = response

    # ==================== STEP 5: FAST METRICS (INSTANT) ====================
    st.session_state.last_fast_metrics = compute_fast_metrics(
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


def compute_fast_metrics(answer: str, contexts: list[str], scores: list[float]) -> dict:
    """
    Compute fast, retrieval-based metrics without any LLMs.
    """
    if not contexts:
        return {
            "status": "skipped",
            "reason": "Not applicable – no retrieved context",
            "top_k_similarity": 0.0,
            "avg_similarity": 0.0,
            "coverage_ratio": 0.0,
            "hallucination_risk": 1.0,
            "context_utilization": 0.0,
            "confidence": "Low",
        }
    answer_tokens = _tokenize_text(answer or "")
    context_tokens = _tokenize_text(" ".join(contexts))
    if not answer_tokens or not context_tokens:
        return {
            "status": "skipped",
            "reason": "Not applicable – insufficient text for metrics",
            "top_k_similarity": max(scores) if scores else 0.0,
            "avg_similarity": sum(scores) / max(len(scores), 1),
            "coverage_ratio": 0.0,
            "hallucination_risk": 1.0,
            "context_utilization": 0.0,
            "confidence": "Low",
        }

    coverage_ratio = len(answer_tokens.intersection(context_tokens)) / max(len(answer_tokens), 1)
    hallucination_risk = 1.0 - coverage_ratio
    context_utilization = min(len(answer_tokens) / max(len(context_tokens), 1), 1.0)
    top_k_similarity = max(scores) if scores else 0.0
    avg_similarity = sum(scores) / max(len(scores), 1)

    if coverage_ratio >= 0.7 and avg_similarity >= 0.6:
        confidence = "High"
    elif coverage_ratio >= 0.4 and avg_similarity >= 0.4:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "status": "computed",
        "reason": "",
        "top_k_similarity": round(top_k_similarity, 4),
        "avg_similarity": round(avg_similarity, 4),
        "coverage_ratio": round(coverage_ratio, 4),
        "hallucination_risk": round(hallucination_risk, 4),
        "context_utilization": round(context_utilization, 4),
        "confidence": confidence,
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


def render_metrics_dashboard():
    """Render a performance metrics dashboard for the latest response."""
    st.markdown("### 📊 RAG Metrics Dashboard")
    st.subheader("Fast Retrieval-Based Metrics")
    fast = st.session_state.get("last_fast_metrics")
    if not fast:
        st.info("No metrics available yet. Ask a legal question to generate metrics.")
    else:
        fast_rows = [
            {
                "Metric": "Top-K Cosine Similarity",
                "Score": fast.get("top_k_similarity", 0.0),
            },
            {
                "Metric": "Average Similarity",
                "Score": fast.get("avg_similarity", 0.0),
            },
            {
                "Metric": "Context Coverage Ratio",
                "Score": fast.get("coverage_ratio", 0.0),
            },
            {
                "Metric": "Hallucination Risk",
                "Score": fast.get("hallucination_risk", 1.0),
            },
            {
                "Metric": "Context Length Utilization",
                "Score": fast.get("context_utilization", 0.0),
            },
        ]
        if fast.get("status") == "skipped":
            st.warning(fast.get("reason", "Not applicable."))
        st.table(pd.DataFrame(fast_rows))

    st.markdown("---")
    st.subheader("Offline / LLM-based Evaluation (RAGAS)")
    if isinstance(st.session_state.get("metrics_future"), Future):
        future = st.session_state.metrics_future
        if future.done():
            try:
                st.session_state.last_metrics = future.result()
            except Exception as exc:
                st.session_state.last_metrics = {
                    "error": f"RAG metrics failed: {str(exc)}",
                    "context_precision": None,
                    "context_recall": None,
                    "faithfulness": None,
                    "answer_relevancy": None,
                }
            st.session_state.metrics_future = None
            st.session_state.metrics_started_at = None
            st.rerun()
        else:
            started_at = st.session_state.get("metrics_started_at")
            if started_at:
                elapsed = time.time() - started_at
                st.info(f"Evaluating metrics in the background... ({elapsed:.0f}s elapsed)")
                if elapsed > config.METRICS_TIMEOUT_SECONDS:
                    st.warning(
                        f"Metrics are taking longer than {config.METRICS_TIMEOUT_SECONDS} seconds. "
                        "They are still running in the background."
                    )
    if st.button("Run RAGAS Evaluation"):
        blocker = get_metrics_blocker()
        if blocker:
            st.session_state.last_metrics = {
                "error": blocker,
                "context_precision": None,
                "context_recall": None,
                "faithfulness": None,
                "answer_relevancy": None,
            }
        elif not st.session_state.last_contexts:
            st.session_state.last_metrics = {
                "status": "skipped",
                "reason": "Not applicable – no retrieved context",
                "context_precision": None,
                "context_recall": None,
                "faithfulness": None,
                "answer_relevancy": None,
            }
        else:
            st.session_state.last_metrics = {
                "status": "pending",
                "context_precision": None,
                "context_recall": None,
                "faithfulness": None,
                "answer_relevancy": None,
            }
            st.session_state.metrics_started_at = time.time()
            st.session_state.metrics_future = _metrics_executor.submit(
                evaluate_rag_metrics,
                question=st.session_state.last_question or "",
                answer=st.session_state.last_answer or "",
                contexts=st.session_state.last_contexts,
            )
    metrics = st.session_state.get("last_metrics")
    if not metrics:
        st.info("No metrics available yet. Ask a legal question to generate metrics.")
        return

    if metrics.get("status") == "pending":
        st.info("Evaluating metrics in the background...")
        if st.button("Refresh metrics"):
            st.rerun()
        return

    if metrics.get("status") == "not_applicable":
        st.info(metrics.get("reason", "Not Applicable – No Retrieved Context"))
        return

    if metrics.get("error"):
        st.warning(metrics["error"])

    metric_keys = [
        ("context_precision", "Context Precision"),
        ("context_recall", "Context Recall"),
        ("faithfulness", "Faithfulness"),
        ("answer_relevancy", "Answer Relevance"),
    ]

    rows = []
    status = metrics.get("status")
    if not status:
        status = "error" if metrics.get("error") else "computed"
    reason = metrics.get("reason", "")
    if not reason and metrics.get("error"):
        reason = metrics.get("error")
    fast = st.session_state.get("last_fast_metrics") or {}
    fast_fallback_map = {
        "context_precision": fast.get("coverage_ratio"),
        "context_recall": fast.get("context_utilization"),
        "faithfulness": 1.0 - fast.get("hallucination_risk", 1.0) if "hallucination_risk" in fast else None,
        "answer_relevancy": fast.get("avg_similarity"),
    }

    for key, label in metric_keys:
        value = metrics.get(key)
        score_value = value if isinstance(value, (int, float)) else None
        if score_value is None and fast_fallback_map.get(key) is not None:
            score_value = fast_fallback_map.get(key)
        rows.append({
            "Metric": label,
            "Score": score_value,
        })

    st.table(pd.DataFrame(rows))

    st.caption(
        "Score guide: 0 means poor alignment; 1 means strong alignment. "
        "Context Precision = how much of the answer is grounded in retrieved context. "
        "Context Recall = how much relevant context was captured. "
        "Faithfulness = answer is supported by context. "
        "Answer Relevance = answer addresses the question."
    )

    for key, label in metric_keys:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not pd.isna(value):
            st.write(f"{label}: {value:.2f}")
            st.progress(min(max(value, 0.0), 1.0))

    chart_values = []
    chart_labels = []
    for key, label in metric_keys:
        value = metrics.get(key)
        if not isinstance(value, (int, float)):
            value = fast_fallback_map.get(key)
        if isinstance(value, (int, float)):
            chart_labels.append(label)
            chart_values.append(value)
    if chart_values:
        chart_df = pd.DataFrame({"Score": chart_values}, index=chart_labels)
        st.bar_chart(chart_df)


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
    # Remove source labels inserted by retriever context formatting
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
            f"1. பிரிவு மற்றும் தலைப்பு: {header}",
            f"2. சட்ட வரையறை: {definition}" if definition else "2. சட்ட வரையறை: சூழலில் குறிப்பிடப்படவில்லை",
            f"3. எளிய விளக்கம்: {simple_explanation}" if simple_explanation else "3. எளிய விளக்கம்: சூழலில் குறிப்பிடப்படவில்லை",
            f"4. தண்டனை: {punishment}" if punishment else f"4. தண்டனை: {no_punishment}",
            f"5. உதாரணம்: {example}" if example else "5. உதாரணம்: சூழலில் குறிப்பிடப்படவில்லை",
        ]
        return "  \n".join(lines)

    no_punishment = "The provided document does not specify punishment for this section."
    header = f"Section {number}"
    if title:
        header = f"{header}: {title}"

    lines = [
        f"1. Section and Title: {header}",
        f"2. Legal Definition: {definition}" if definition else "2. Legal Definition: Not stated in the provided context.",
        f"3. Simple Explanation: {simple_explanation}" if simple_explanation else "3. Simple Explanation: Not stated in the provided context.",
        f"4. Punishment: {punishment}" if punishment else f"4. Punishment: {no_punishment}",
        f"5. Example: {example}" if example else "5. Example: Not stated in the provided context.",
    ]
    return "  \n".join(lines)


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
            st.error(f"⚠️ LLM initialization error: {str(e)}")
            st.info("Using local embeddings only. LLM responses will be limited.")
            st.session_state.llm_handler = None
    
    except Exception as e:
        st.error(f"❌ Initialization error: {str(e)}")
        logger.error(f"Initialization failed: {str(e)}")


# ==================== MAIN APP ====================
def main():
    """Main application function"""
    
    # Header
    st.markdown('<p class="header">⚖️ NLP-Based Legal Aid Chatbot</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Retrieval-Augmented Generation (RAG) for Legal Awareness</p>', unsafe_allow_html=True)
    
    # Disclaimer box
    st.markdown("""
    <div class="info-box">
    <strong>ℹ️ Welcome to the Legal Aid Chatbot</strong><br>
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
            st.warning("⚠️ Please wait for initialization to get started.")
    with tab_metrics:
        render_metrics_dashboard()


if __name__ == "__main__":
    main()
