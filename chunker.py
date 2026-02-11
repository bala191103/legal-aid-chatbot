"""
Chunking Module - Splits extracted legal text into manageable chunks
Uses LangChain text splitter for optimal chunking strategy
"""

from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextChunker:
    """
    Splits long legal documents into smaller, semantically coherent chunks.
    Uses recursive character-level splitting to preserve legal structure.
    """
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        """
        Initialize text chunker.
        
        Args:
            chunk_size (int): Size of each chunk in characters
            chunk_overlap (int): Overlap between consecutive chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize LangChain splitter
        # It tries to split on sentences, then paragraphs, then by newline
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )
        self.section_pattern = re.compile(
            r"(?:^|\n)\s*(Section|SECTION|Sec\.?|SEC\.?)\s+(\d+[A-Za-z]?)\s*[:.\-]?\s*(.*)"
            r"|(?:^|\n)\s*(\d{1,4}[A-Za-z]?)\s*[:.\-]\s*(.*)",
            re.MULTILINE
        )
        
        logger.info(f"Text chunker initialized (size={chunk_size}, overlap={chunk_overlap})")

    def _split_by_section(self, text: str) -> List[Dict[str, str]]:
        """
        Split text by legal section headings and return structured sections.
        """
        matches = list(self.section_pattern.finditer(text))
        if not matches:
            return []

        sections = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            if match.group(1):
                section_number = match.group(2).strip()
                section_title = match.group(3).strip()
            else:
                section_number = match.group(4).strip()
                section_title = match.group(5).strip()

            header = f"Section {section_number}"
            if section_title:
                header = f"{header} {section_title}"

            body = text[start:end].strip()
            sections.append({"header": header.strip(), "body": body})

        return sections
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks.
        
        Args:
            text (str): Text to be chunked
            
        Returns:
            List[str]: List of text chunks
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for chunking")
            return []
        
        try:
            # First, try section-aware chunking
            sections = self._split_by_section(text)
            chunks = []

            if sections:
                for section in sections:
                    header = section["header"]
                    body = section["body"]

                    if not body:
                        chunks.append(header)
                        continue

                    combined = f"{header}\n{body}".strip()
                    if len(combined) <= self.chunk_size:
                        chunks.append(combined)
                    else:
                        body_chunks = self.splitter.split_text(body)
                        for body_chunk in body_chunks:
                            chunk = f"{header}\n{body_chunk}".strip()
                            chunks.append(chunk)

                logger.info(f"Created {len(chunks)} section-aware chunks")
            else:
                # Fallback: standard recursive chunking
                chunks = self.splitter.split_text(text)
                logger.info(f"Created {len(chunks)} chunks from text")

            # Filter out empty chunks
            non_empty_chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
            logger.info(f"Non-empty chunks: {len(non_empty_chunks)}")

            return non_empty_chunks
        
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            return []
    
    def chunk_with_metadata(self, text: str, source: str = "unknown") -> List[dict]:
        """
        Chunk text and attach metadata to each chunk.
        
        Args:
            text (str): Text to be chunked
            source (str): Source document name or identifier
            
        Returns:
            List[dict]: List of chunks with metadata
        """
        chunks = self.chunk_text(text)
        
        chunked_data = []
        for idx, chunk in enumerate(chunks):
            chunked_data.append({
                "content": chunk,
                "source": source,
                "chunk_id": idx,
                "length": len(chunk)
            })
        
        logger.info(f"Created {len(chunked_data)} chunks with metadata from {source}")
        return chunked_data


class AdaptiveChunker:
    """
    Advanced chunker that adapts chunk size based on content type.
    Handles legal documents with varying complexity.
    """
    
    def __init__(self):
        """Initialize adaptive chunker"""
        self.small_chunker = TextChunker(chunk_size=300, chunk_overlap=50)    # For detailed legal text
        self.medium_chunker = TextChunker(chunk_size=500, chunk_overlap=100)   # Default
        self.large_chunker = TextChunker(chunk_size=800, chunk_overlap=200)    # For complex sections
    
    def detect_content_type(self, text: str) -> str:
        """
        Detect if text is detailed legal provisions or general information.
        
        Args:
            text (str): Text sample to analyze
            
        Returns:
            str: Content type ('detailed', 'moderate', 'overview')
        """
        lines = text.split('\n')
        avg_line_length = sum(len(line) for line in lines) / max(len(lines), 1)
        
        # Detailed legal text has longer lines with complex sentences
        if avg_line_length > 100:
            return "detailed"
        elif avg_line_length > 60:
            return "moderate"
        else:
            return "overview"
    
    def chunk_adaptively(self, text: str, source: str = "unknown") -> List[dict]:
        """
        Chunk text using adaptive strategy based on content complexity.
        
        Args:
            text (str): Text to chunk
            source (str): Source document
            
        Returns:
            List[dict]: Adaptively chunked text with metadata
        """
        content_type = self.detect_content_type(text)
        logger.info(f"Detected content type: {content_type}")
        
        if content_type == "detailed":
            chunker = self.small_chunker
        elif content_type == "moderate":
            chunker = self.medium_chunker
        else:
            chunker = self.large_chunker
        
        return chunker.chunk_with_metadata(text, source=source)


# ==================== UTILITY FUNCTIONS ====================

def clean_chunk(chunk: str) -> str:
    """
    Clean and normalize a text chunk.
    
    Args:
        chunk (str): Text chunk to clean
        
    Returns:
        str: Cleaned chunk
    """
    # Remove multiple spaces
    chunk = " ".join(chunk.split())
    # Remove special characters but keep basic punctuation
    chunk = chunk.replace("\x00", "").replace("\r", "")
    return chunk.strip()


def validate_chunks(chunks: List[str], min_length: int = 50) -> List[str]:
    """
    Validate chunks and filter out too-short ones.
    
    Args:
        chunks (List[str]): List of chunks to validate
        min_length (int): Minimum character length for a valid chunk
        
    Returns:
        List[str]: Validated chunks
    """
    valid_chunks = [chunk for chunk in chunks if len(chunk) >= min_length]
    filtered_count = len(chunks) - len(valid_chunks)
    
    if filtered_count > 0:
        logger.info(f"Filtered out {filtered_count} chunks (too short)")
    
    return valid_chunks


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    # Example usage
    sample_text = """
    Section 1: General Provisions
    Every citizen has the right to equal protection under the law. 
    No person shall be discriminated against based on caste, creed, religion, or gender.
    
    Section 2: Rights and Duties
    The fundamental rights guaranteed under this act include freedom of speech, 
    freedom of assembly, and the right to petition the government. 
    Citizens must also fulfill their duties as prescribed by law.
    """
    
    chunker = TextChunker(chunk_size=200, chunk_overlap=50)
    chunks = chunker.chunk_text(sample_text)
    
    print("Chunks created:")
    for i, chunk in enumerate(chunks, 1):
        print(f"\n[Chunk {i}] ({len(chunk)} chars)")
        print(chunk)
    
    # Test adaptive chunker
    print("\n" + "="*60)
    print("Testing Adaptive Chunker")
    print("="*60)
    
    adaptive_chunker = AdaptiveChunker()
    adaptive_chunks = adaptive_chunker.chunk_adaptively(sample_text, source="sample_act.pdf")
    
    for chunk_data in adaptive_chunks:
        print(f"\nSource: {chunk_data['source']}, Chunk: {chunk_data['chunk_id']}")
        print(f"Length: {chunk_data['length']} characters")
        print(f"Content: {chunk_data['content'][:100]}...")
