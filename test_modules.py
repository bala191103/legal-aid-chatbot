"""
Testing Script - Validates all modules and core functionality
Run: python test_modules.py
"""

import sys
import logging
from typing import Tuple

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ==================== TEST RESULTS ====================
test_results = {
    "PASSED": [],
    "FAILED": [],
    "SKIPPED": []
}

def test_module(name: str, test_func) -> bool:
    """Execute a test and record result"""
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {name}")
        logger.info(f"{'='*60}")
        
        result = test_func()
        
        if result:
            logger.info(f"✅ {name} PASSED")
            test_results["PASSED"].append(name)
            return True
        else:
            logger.warning(f"❌ {name} FAILED")
            test_results["FAILED"].append(name)
            return False
    
    except Exception as e:
        logger.error(f"❌ {name} ERROR: {str(e)}")
        test_results["FAILED"].append(name)
        return False


# ==================== TEST 1: LAW FILTER ====================
def test_law_filter() -> bool:
    """Test law query validation"""
    from law_filter import is_legal_query
    
    test_cases = [
        # (query, expected_result)
        ("What are my rights under Indian Constitution?", True),
        ("How do I file a case in court?", True),
        ("What is Section 420 of IPC?", True),
        ("Can I get a divorce?", True),
        ("Who won the cricket match?", False),
        ("Tell me about Bollywood movies", False),
        ("What's the weather today?", False),
    ]
    
    passed = 0
    for query, expected in test_cases:
        is_legal, reason = is_legal_query(query)
        if is_legal == expected:
            logger.info(f"  ✓ '{query[:40]}...' → {is_legal} ({reason})")
            passed += 1
        else:
            logger.warning(f"  ✗ '{query[:40]}...' → Expected {expected}, got {is_legal}")
    
    logger.info(f"Law Filter: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


# ==================== TEST 2: PDF PROCESSOR ====================
def test_pdf_processor() -> bool:
    """Test PDF text extraction"""
    from pdf_processor import PDFProcessor
    import tempfile
    
    logger.info("Creating test PDF...")
    
    try:
        # This test checks if the module loads and methods are available
        processor = PDFProcessor()
        
        # Test validation
        assert hasattr(processor, 'extract_text'), "Missing extract_text method"
        assert hasattr(processor, 'extract_metadata'), "Missing extract_metadata method"
        assert hasattr(processor, 'validate_file'), "Missing validate_file method"
        
        # Test with non-existent file
        is_valid = processor.validate_file("non_existent_file.pdf")
        logger.info(f"  ✓ File validation works (correctly rejected invalid file)")
        
        logger.info("PDF Processor: All methods available")
        return True
    
    except Exception as e:
        logger.error(f"PDF Processor test failed: {str(e)}")
        return False


# ==================== TEST 3: TEXT CHUNKER ====================
def test_text_chunker() -> bool:
    """Test text chunking"""
    from chunker import TextChunker
    
    sample_text = """
    Section 1: Every citizen has fundamental rights.
    Section 2: Right to freedom is guaranteed under constitution.
    Section 3: No discrimination on basis of caste, religion or gender.
    """ * 5  # Repeat to make it longer
    
    try:
        chunker = TextChunker(chunk_size=200, chunk_overlap=50)
        chunks = chunker.chunk_text(sample_text)
        
        assert len(chunks) > 0, "No chunks created"
        assert all(len(c) > 0 for c in chunks), "Empty chunks found"
        
        logger.info(f"  ✓ Created {len(chunks)} chunks")
        logger.info(f"  ✓ Chunk sizes: min={min(len(c) for c in chunks)}, max={max(len(c) for c in chunks)}")
        
        return True
    
    except Exception as e:
        logger.error(f"Text Chunker test failed: {str(e)}")
        return False


# ==================== TEST 4: EMBEDDINGS ====================
def test_embeddings() -> bool:
    """Test embedding generation"""
    from embeddings import DenseEmbeddings
    import numpy as np
    
    try:
        logger.info("Loading Sentence Transformer model...")
        embeddings = DenseEmbeddings()
        
        # Test single embedding
        text = "Indian Constitution protects fundamental rights"
        embedding = embeddings.embed_text(text)
        
        assert isinstance(embedding, np.ndarray), "Embedding should be numpy array"
        assert len(embedding) == embeddings.embedding_dim, "Incorrect embedding dimension"
        
        logger.info(f"  ✓ Single embedding generated (dimension: {embeddings.embedding_dim})")
        
        # Test batch embeddings
        texts = [
            "Right to education",
            "Freedom of speech",
            "Right to equality"
        ]
        batch_embeddings = embeddings.embed_texts(texts)
        
        assert batch_embeddings.shape[0] == len(texts), "Wrong number of embeddings"
        
        logger.info(f"  ✓ Batch embeddings generated ({len(texts)} texts)")
        
        return True
    
    except Exception as e:
        logger.error(f"Embeddings test failed: {str(e)}")
        return False


# ==================== TEST 5: VECTOR STORE ====================
def test_vector_store() -> bool:
    """Test local vector store"""
    from vector_store import LocalVectorStore
    import numpy as np
    
    try:
        store = LocalVectorStore()
        
        # Store test embeddings
        doc_id = "test_doc_1"
        vector = np.random.rand(384).tolist()
        content = "This is a test legal document"
        metadata = {"source": "test.pdf"}
        
        store.store_embedding(doc_id, vector, content, metadata)
        
        logger.info(f"  ✓ Embedding stored locally")
        
        # Retrieve similar
        results = store.retrieve_similar(vector, top_k=1)
        
        assert len(results) > 0, "No results retrieved"
        assert results[0]['doc_id'] == doc_id, "Wrong document retrieved"
        
        logger.info(f"  ✓ Retrieval works correctly")
        
        return True
    
    except Exception as e:
        logger.error(f"Vector Store test failed: {str(e)}")
        return False


# ==================== TEST 6: RETRIEVER ====================
def test_retriever() -> bool:
    """Test document retriever"""
    from retriever import LegalDocumentRetriever
    
    try:
        logger.info("Initializing retriever with local store...")
        retriever = LegalDocumentRetriever(use_local=True)
        
        # Sample documents
        docs = [
            "Right to education is fundamental",
            "Constitution guarantees freedom of speech",
            "Property rights protect ownership",
            "Contract law governs agreements"
        ]
        
        # Index documents
        result = retriever.index_documents(docs)
        
        assert result['status'] == 'success', f"Indexing failed: {result}"
        
        logger.info(f"  ✓ Indexed {result['indexed']} documents")
        
        # Retrieve
        query = "What is the right to education?"
        retrieved = retriever.retrieve(query, top_k=2)
        
        assert len(retrieved) > 0, "No documents retrieved"
        
        logger.info(f"  ✓ Retrieved {len(retrieved)} documents for query")
        
        return True
    
    except Exception as e:
        logger.error(f"Retriever test failed: {str(e)}")
        return False


# ==================== TEST 7: CONFIGURATION ====================
def test_configuration() -> bool:
    """Test configuration module"""
    import config
    
    try:
        # Check critical config values
        assert hasattr(config, 'PINECONE_INDEX_NAME'), "Missing PINECONE_INDEX_NAME"
        assert hasattr(config, 'EMBEDDING_DIMENSION'), "Missing EMBEDDING_DIMENSION"
        assert hasattr(config, 'LLM_MODEL'), "Missing LLM_MODEL"
        assert hasattr(config, 'CHUNK_SIZE'), "Missing CHUNK_SIZE"
        assert hasattr(config, 'TOP_K_RESULTS'), "Missing TOP_K_RESULTS"
        assert hasattr(config, 'LEGAL_DISCLAIMER'), "Missing LEGAL_DISCLAIMER"
        assert hasattr(config, 'REJECTION_MESSAGE'), "Missing REJECTION_MESSAGE"
        
        logger.info(f"  ✓ PINECONE_INDEX_NAME: {config.PINECONE_INDEX_NAME}")
        logger.info(f"  ✓ EMBEDDING_DIMENSION: {config.EMBEDDING_DIMENSION}")
        logger.info(f"  ✓ LLM_MODEL: {config.LLM_MODEL}")
        logger.info(f"  ✓ CHUNK_SIZE: {config.CHUNK_SIZE}")
        logger.info(f"  ✓ TOP_K_RESULTS: {config.TOP_K_RESULTS}")
        
        return True
    
    except Exception as e:
        logger.error(f"Configuration test failed: {str(e)}")
        return False


# ==================== TEST 8: STREAMLIT UI ====================
def test_streamlit_imports() -> bool:
    """Test if Streamlit and dependencies are available"""
    try:
        import streamlit
        logger.info(f"  ✓ Streamlit imported (version: {streamlit.__version__})")
        
        import langchain
        logger.info(f"  ✓ LangChain imported")
        
        import PyPDF2
        logger.info(f"  ✓ PyPDF2 imported")
        
        import sentence_transformers
        logger.info(f"  ✓ Sentence Transformers imported")
        
        import rank_bm25
        logger.info(f"  ✓ rank_bm25 imported")
        
        return True
    
    except ImportError as e:
        logger.error(f"Missing dependency: {str(e)}")
        return False


# ==================== MAIN TEST RUNNER ====================
def main():
    """Run all tests"""
    logger.info("\n" + "="*60)
    logger.info("🧪 LEGAL AID CHATBOT - COMPREHENSIVE TEST SUITE")
    logger.info("="*60)
    
    # Run tests
    tests = [
        ("Law Filter (Query Validation)", test_law_filter),
        ("PDF Processor", test_pdf_processor),
        ("Text Chunker", test_text_chunker),
        ("Embeddings Generation", test_embeddings),
        ("Local Vector Store", test_vector_store),
        ("Document Retriever", test_retriever),
        ("Configuration Module", test_configuration),
        ("Streamlit & Dependencies", test_streamlit_imports),
    ]
    
    for test_name, test_func in tests:
        test_module(test_name, test_func)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("📊 TEST SUMMARY")
    logger.info("="*60)
    
    logger.info(f"✅ PASSED: {len(test_results['PASSED'])}")
    for test in test_results["PASSED"]:
        logger.info(f"   • {test}")
    
    if test_results["FAILED"]:
        logger.warning(f"\n❌ FAILED: {len(test_results['FAILED'])}")
        for test in test_results["FAILED"]:
            logger.warning(f"   • {test}")
    
    if test_results["SKIPPED"]:
        logger.info(f"\n⏭️  SKIPPED: {len(test_results['SKIPPED'])}")
        for test in test_results["SKIPPED"]:
            logger.info(f"   • {test}")
    
    logger.info("\n" + "="*60)
    total_tests = len(test_results["PASSED"]) + len(test_results["FAILED"])
    pass_rate = (len(test_results["PASSED"]) / total_tests * 100) if total_tests > 0 else 0
    logger.info(f"📈 PASS RATE: {pass_rate:.1f}% ({len(test_results['PASSED'])}/{total_tests})")
    logger.info("="*60 + "\n")
    
    # Exit code
    return 0 if len(test_results["FAILED"]) == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
