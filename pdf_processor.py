"""
PDF Processor Module - Extracts text from legal PDF documents
Handles multi-page PDFs and preserves legal document structure
"""

import PyPDF2
from pathlib import Path
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Processes PDF documents and extracts text content.
    Designed specifically for legal documents.
    """
    
    def __init__(self, max_pages: Optional[int] = None):
        """
        Initialize PDF processor.
        
        Args:
            max_pages (int): Maximum pages to process (None = all pages)
        """
        self.max_pages = max_pages
        self.supported_formats = {".pdf"}
    
    def validate_file(self, file_path: str) -> bool:
        """
        Validate if file is a valid PDF.
        
        Args:
            file_path (str): Path to the PDF file
            
        Returns:
            bool: True if valid PDF
        """
        path = Path(file_path)
        
        # Check if file exists
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return False
        
        # Check file extension
        if path.suffix.lower() not in self.supported_formats:
            logger.error(f"Unsupported file format: {path.suffix}")
            return False
        
        # Check if file is readable
        if not path.is_file():
            logger.error(f"Path is not a file: {file_path}")
            return False
        
        logger.info(f"File validation passed: {file_path}")
        return True
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from PDF file.
        
        Args:
            file_path (str): Path to the PDF file
            
        Returns:
            str: Extracted text from PDF
            
        Raises:
            ValueError: If PDF is invalid or cannot be read
        """
        # Validate file
        if not self.validate_file(file_path):
            raise ValueError(f"Invalid PDF file: {file_path}")
        
        try:
            extracted_text = []
            
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                total_pages = len(pdf_reader.pages)
                
                logger.info(f"Processing PDF: {file_path}")
                logger.info(f"Total pages: {total_pages}")
                
                # Determine pages to process
                pages_to_process = min(total_pages, self.max_pages or total_pages)
                
                # Extract text from each page
                for page_num in range(pages_to_process):
                    try:
                        page = pdf_reader.pages[page_num]
                        text = page.extract_text()
                        
                        if text.strip():  # Only add non-empty pages
                            # Add page marker for reference
                            extracted_text.append(f"\n[Page {page_num + 1}]\n{text}")
                            logger.info(f"Extracted page {page_num + 1}/{pages_to_process}")
                        else:
                            logger.warning(f"Page {page_num + 1} is empty or unreadable")
                    
                    except Exception as e:
                        logger.warning(f"Error processing page {page_num + 1}: {str(e)}")
                        continue
            
            # Combine all text
            full_text = "\n".join(extracted_text)
            
            if not full_text.strip():
                raise ValueError("No text could be extracted from the PDF")
            
            logger.info(f"Successfully extracted {len(full_text)} characters")
            return full_text
        
        except Exception as e:
            logger.error(f"Error reading PDF: {str(e)}")
            raise ValueError(f"Cannot read PDF file: {str(e)}")
    
    def extract_metadata(self, file_path: str) -> dict:
        """
        Extract metadata from PDF (title, author, creation date).
        
        Args:
            file_path (str): Path to the PDF file
            
        Returns:
            dict: PDF metadata
        """
        if not self.validate_file(file_path):
            return {}
        
        try:
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                metadata = pdf_reader.metadata
                
                return {
                    "title": metadata.get("/Title", "Unknown") if metadata else "Unknown",
                    "author": metadata.get("/Author", "Unknown") if metadata else "Unknown",
                    "creator": metadata.get("/Creator", "Unknown") if metadata else "Unknown",
                    "creation_date": metadata.get("/CreationDate", "Unknown") if metadata else "Unknown",
                    "pages": len(pdf_reader.pages)
                }
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return {}


class BatchPDFProcessor:
    """
    Process multiple PDF files in batch.
    """
    
    def __init__(self, max_pages: Optional[int] = None):
        """
        Initialize batch PDF processor.
        
        Args:
            max_pages (int): Maximum pages per PDF
        """
        self.processor = PDFProcessor(max_pages=max_pages)
    
    def process_directory(self, directory_path: str) -> dict:
        """
        Process all PDFs in a directory.
        
        Args:
            directory_path (str): Path to directory containing PDFs
            
        Returns:
            dict: Dictionary mapping filename to extracted text
        """
        results = {}
        pdf_dir = Path(directory_path)
        
        if not pdf_dir.is_dir():
            logger.error(f"Directory not found: {directory_path}")
            return results
        
        pdf_files = list(pdf_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files")
        
        for pdf_file in pdf_files:
            try:
                text = self.processor.extract_text(str(pdf_file))
                results[pdf_file.name] = text
                logger.info(f"✓ Processed: {pdf_file.name}")
            except Exception as e:
                logger.error(f"✗ Failed to process {pdf_file.name}: {str(e)}")
        
        return results


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    # Example usage
    processor = PDFProcessor()
    
    # Test with a sample PDF (uncomment when you have a test file)
    # try:
    #     text = processor.extract_text("sample_legal_document.pdf")
    #     print(f"Extracted text length: {len(text)} characters")
    #     print("First 500 characters:")
    #     print(text[:500])
    # except Exception as e:
    #     print(f"Error: {str(e)}")
