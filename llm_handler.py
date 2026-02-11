"""
LLM Handler Module - Integrates with Groq API for LLaMA
Generates simplified legal awareness responses with context
"""

from typing import Optional
import logging

try:
    from groq import Groq
except ImportError:
    Groq = None
    logging.warning("Groq client not installed. Install with: pip install groq")

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GroqLLMHandler:
    """
    Handles communication with Groq API for LLaMA LLM.
    Generates legal awareness responses based on retrieved context.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Groq LLM handler.
        
        Args:
            api_key (str): Groq API key (defaults to config)
        """
        self.api_key = api_key or config.GROQ_API_KEY
        self.model = config.LLM_MODEL
        self.temperature = config.LLM_TEMPERATURE
        self.max_tokens = config.LLM_MAX_TOKENS
        
        if Groq is None:
            logger.error("Groq client not installed")
            raise ImportError("Groq client not available")
        
        try:
            logger.info(f"Initializing Groq client with model: {self.model}")
            self.client = Groq(api_key=self.api_key)
            logger.info("Groq LLM handler initialized")
        except Exception as e:
            logger.error(f"Error initializing Groq: {str(e)}")
            raise
    
    def generate_response(self, query: str, context: str) -> str:
        """
        Generate a legal awareness response using LLaMA.
        
        Args:
            query (str): User question
            context (str): Retrieved legal context from RAG
            
        Returns:
            str: Generated response
        """
        # Prepare prompt with instructions
        system_prompt = """You are an NLP-based Legal Aid Chatbot that provides general legal information strictly from the provided context (Indian Penal Code and uploaded legal documents).

MANDATORY RULES:
1. Answer ONLY using the retrieved legal context provided to you.
2. Do NOT guess, do NOT use external knowledge, do NOT hallucinate IPC sections.
3. If the retrieved context contains the relevant IPC section:
   - Clearly mention the IPC section number.
   - Briefly explain the offence in simple language.
   - Mention punishment only if it is present in the context.
4. If the retrieved context does NOT include the relevant IPC section or does not directly answer the question:
   - Say that the context does not provide the specific IPC section or answer.
5. Use simple, clear, citizen-friendly language.
6. Do NOT give case-specific advice.
7. Do NOT suggest actions like filing cases or approaching police.
8. When the user asks numeric or shorthand queries (e.g., "420 section", "Section 302"), treat them as IPC section queries and match only if the context explicitly contains that section.
9. Keep the response concise and factual.
"""
        
        user_prompt = f"""Based on the following legal context, please answer the user's question:

LEGAL CONTEXT:
{context}

USER QUESTION:
{query}

Please provide a clear, simplified explanation suitable for someone without legal background."""
        
        try:
            logger.info("Calling Groq API for response generation...")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=0.95,
                stream=False
            )
            
            generated_text = response.choices[0].message.content.strip()
            logger.info("Response generated successfully")
            
            return generated_text
        
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return f"I apologize, but I encountered an error while processing your question. Error: {str(e)}"
    
    def generate_rag_response(self, query: str, context: str) -> str:
        """
        Generate RAG response (main method for chatbot).
        
        Args:
            query (str): User question
            context (str): Retrieved legal documents context
            
        Returns:
            str: Final response with disclaimer
        """
        # Generate response
        response = self.generate_response(query, context)
        return response


class ResponseFormatter:
    """
    Formats LLM responses for better readability in Streamlit UI.
    """
    
    @staticmethod
    def format_response(response: str) -> str:
        """
        Format response with better structure.
        
        Args:
            response (str): Raw response text
            
        Returns:
            str: Formatted response
        """
        # Remove extra whitespace
        response = " ".join(response.split())
        return response
    
    @staticmethod
    def add_sources(response: str, sources: list) -> str:
        """
        Append source attribution to response.
        
        Args:
            response (str): Response text
            sources (list): List of source documents
            
        Returns:
            str: Response with sources
        """
        sources_text = "\n\n**Sources Referenced:**\n"
        for i, source in enumerate(sources, 1):
            sources_text += f"{i}. {source}\n"
        
        return response + sources_text
    
    @staticmethod
    def highlight_key_terms(response: str) -> str:
        """
        Highlight important legal terms in response.
        
        Args:
            response (str): Response text
            
        Returns:
            str: Response with highlighted terms
        """
        important_terms = [
            "right", "law", "legal", "court", "judge", "contract",
            "agreement", "penalty", "compensation", "liability"
        ]
        
        formatted_response = response
        for term in important_terms:
            # Case-insensitive replacement
            formatted_response = formatted_response.replace(
                term,
                f"**{term}**"
            )
        
        return formatted_response


class ResponseValidator:
    """
    Validates that responses are legal-appropriate and contain disclaimer.
    """
    
    @staticmethod
    def validate_response(response: str) -> bool:
        """
        Check if response is valid and contains required disclaimer.
        
        Args:
            response (str): Response to validate
            
        Returns:
            bool: True if response is valid
        """
        # Check if response contains disclaimer
        has_disclaimer = "LEGAL DISCLAIMER" in response or "does not constitute legal advice" in response
        
        # Check minimum length
        has_content = len(response) > 50
        
        return has_disclaimer and has_content
    
    @staticmethod
    def ensure_disclaimer(response: str) -> str:
        """
        Ensure response includes legal disclaimer.
        
        Args:
            response (str): Response text
            
        Returns:
            str: Response with disclaimer
        """
        if config.LEGAL_DISCLAIMER not in response:
            response = f"{response}\n\n{config.LEGAL_DISCLAIMER}"
        
        return response


# ==================== TESTING FUNCTION ====================
if __name__ == "__main__":
    logger.info("LLM Handler module ready for use")
    
    # Example usage (requires valid Groq API key)
    """
    handler = GroqLLMHandler()
    
    sample_context = \"\"\"
    Right to Education Act: Every child has the right to free and compulsory education 
    up to the age of 14 years as per Article 21-A of the Constitution.
    \"\"\"
    
    sample_query = "What is the right to education in India?"
    
    response = handler.generate_rag_response(sample_query, sample_context)
    print(response)
    """
