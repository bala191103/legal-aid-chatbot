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

# Import all modules
from law_filter import is_legal_query
from pdf_processor import PDFProcessor, BatchPDFProcessor
from chunker import TextChunker, clean_chunk, validate_chunks
from retriever import LegalDocumentRetriever
from llm_handler import GroqLLMHandler, ResponseValidator
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


# ==================== SIDEBAR CONFIGURATION ====================
def setup_sidebar():
    """Configure sidebar for admin functions and settings"""
    st.sidebar.markdown("### ⚙️ Configuration")
    
    with st.sidebar.expander("📚 Document Management", expanded=False):
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
        1. Upload legal PDF documents
        2. Ask law-related questions
        3. Get simplified legal information

        **Important:**
        - Only law-related questions are answered
        - Responses are for awareness only
        - Consult qualified lawyers for specific cases
        """)

    with st.sidebar.expander("Debug", expanded=False):
        st.checkbox("Show retrieved context", key="show_retrieval_context")
    
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
                else:
                    st.error(f"Indexing failed: {result.get('error', 'Unknown error')}")
        
        except Exception as e:
            st.error(f"Error processing documents: {str(e)}")
            logger.error(f"Document processing error: {str(e)}")


# ==================== CHAT INTERFACE ====================
def chat_interface():
    """Main chat interface for user queries"""
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Input area
    user_input = st.chat_input(
        placeholder="Ask your legal question... E.g., What are my fundamental rights under Indian Constitution?"
    )
    
    if user_input:
        # Add user message to history
        st.session_state.messages.append({
            "role": "user",
            "content": user_input
        })
        
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Process query
        with st.spinner("Processing your question..."):
            response = process_query(user_input)
        
        # Add assistant response to history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response
        })
        
        with st.chat_message("assistant"):
            st.markdown(response)


def process_query(query: str) -> str:
    """
    Process user query through the complete RAG pipeline
    
    Args:
        query (str): User's question
        
    Returns:
        str: Response from the chatbot
    """
    
    # ==================== STEP 1: LAW FILTER ====================
    is_legal, reason = is_legal_query(query)
    logger.info(f"Law filter result: {is_legal} ({reason})")
    
    if not is_legal:
        return config.REJECTION_MESSAGE
    
    # ==================== STEP 2: CHECK DOCUMENTS ====================
    if not st.session_state.documents_indexed:
        return """
⚠️ No legal documents have been indexed yet.

Please:
1. Go to the sidebar
2. Click "Document Management"
3. Upload legal PDF documents
4. Click "Process & Index Documents"

Once documents are indexed, I'll be able to answer your questions based on legal content.
        """
    
    # ==================== STEP 3: RETRIEVE CONTEXT ====================
    try:
        context = st.session_state.retriever.retrieve_with_context(query)
    except Exception as e:
        logger.error(f"Retrieval error: {str(e)}")
        context = "Unable to retrieve legal context."

    if st.session_state.get("show_retrieval_context"):
        with st.expander("Retrieved Context", expanded=False):
            st.text(context)

    if not context or context.startswith("No relevant legal documents found"):
        return config.NO_CONTEXT_MESSAGE
    
    # ==================== STEP 4: STRICT RESPONSE (CONTEXT-ONLY) ====================
    response = build_strict_response(query, context)
    if response is None:
        return config.NO_CONTEXT_MESSAGE
    
    # ==================== STEP 5: VALIDATE RESPONSE ====================
    response = ResponseValidator.ensure_disclaimer(response)
    
    return response


def build_strict_response(query: str, context: str) -> str | None:
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
                return format_section_response(sec)
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

    return format_section_response(best)


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


def format_section_response(section: dict) -> str:
    """
    Format a response for a specific IPC section using only its body text.
    """
    number = section["number"]
    title = section["title"]
    body = section["body"]
    # Remove source labels inserted by retriever context formatting
    body = re.sub(r"\[Source[^\]]*\]\s*", "", body)
    body = " ".join(body.split())

    sentences = re.split(r"(?<=[.!?])\s+", body)
    summary = " ".join(sentences[:2]).strip()
    if not summary:
        summary = body.strip()
    if summary == body.strip() and title:
        summary = title.strip()
    if not summary:
        summary = "The document does not provide additional plain-language detail beyond the section heading."

    punishment_sentences = [
        s for s in sentences
        if re.search(r"\b(punish|punishment|imprisonment|fine|rigorous)\b", s, re.IGNORECASE)
    ]
    punishment = " ".join(punishment_sentences[:1]).strip()

    header = f"IPC Section {number}"
    if title:
        header = f"{header}: {title}"

    lines = [f"1. {header}."]
    if summary and summary.lower() != title.lower():
        lines.append(f"2. In simple terms: {summary}")
    if punishment:
        lines.append(f"{len(lines)+1}. Punishment (as stated in the document): {punishment}")
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
    
    # Setup sidebar
    setup_sidebar()
    
    # Initialize if needed
    if st.session_state.retriever is None:
        initialize_chatbot()
    
    # Main chat interface
    if st.session_state.llm_handler is not None or st.session_state.documents_indexed:
        chat_interface()
    else:
        st.warning("⚠️ Please wait for initialization or upload documents to get started.")


if __name__ == "__main__":
    main()
